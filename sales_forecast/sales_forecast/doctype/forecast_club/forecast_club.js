// Copyright (c) 2026, Viv Choudhary and contributors
// For license information, please see license.txt

// Wrap frappe.format so Packing Material Stock shows numbers in bold (item - stock)
(function () {
	const _format = frappe.format;
	frappe.format = function (value, df, options, doc) {
		let result = _format.apply(this, arguments);
		if (
			doc &&
			doc.doctype === "Forecast Club Item" &&
			df &&
			df.fieldname === "custom__item_packaging_material" &&
			typeof result === "string" &&
			result
		) {
			result = result.replace(/([-:])\s*(\d+(?:\.\d+)?)/g, "$1 <strong>$2</strong>");
		}
		return result;
	};
})();

frappe.ui.form.on("Forecast Club", {
	refresh(frm) {
		// Ensure grid docfield formatter is set (backup for format wrap above)
		const packaging_formatter = function (value) {
			if (value == null || value === "") return value;
			return value.replace(/([-:])\s*(\d+(?:\.\d+)?)/g, "$1 <strong>$2</strong>");
		};
		const df_orig = frappe.meta.docfield_map["Forecast Club Item"] && frappe.meta.docfield_map["Forecast Club Item"]["custom__item_packaging_material"];
		if (df_orig) df_orig.formatter = packaging_formatter;
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (grid && grid.docfields) {
			grid.docfields.forEach((df) => {
				if (df.fieldname === "custom__item_packaging_material") df.formatter = packaging_formatter;
			});
			frm.refresh_field("items");
		}

		// BOM: show only BOMs where BOM.item = row's item_code (production item)
		// Store current row when BOM field is focused so get_query can read item_code (link passes parent doc)
		let _bom_row_item_code = null;
		const bom_get_query = function (doc, cdt, cdn) {
			let item_code = _bom_row_item_code;
			if (!item_code && doc && doc.doctype === "Forecast Club Item" && doc.item_code) {
				item_code = doc.item_code;
			}
			if (!item_code && cdt && cdn) {
				try {
					const row = frappe.model.get_doc(cdt, cdn);
					item_code = row ? row.item_code : null;
				} catch (e) {
					item_code = null;
				}
			}
			if (!item_code && doc && doc.items && cdn) {
				const row = doc.items.find((r) => r.name === cdn);
				item_code = row ? row.item_code : null;
			}
			if (!item_code) {
				return { filters: [["name", "=", "__never__"]] };
			}
			// 3-element filters: Frappe adds doctype when building query
			return {
				filters: [
					["item", "=", item_code],
					["docstatus", "=", 1]
				]
			};
		};
		frm.set_query("bom", "items", bom_get_query);

		// Items: only show items belonging to the selected Plant
		// (Item.custom_manufacturing_location == Plant Warehouse's WIP FG warehouse)
		// Plant Warehouse only has 2 rows, so refetch it on every refresh and cache
		// on frm -- the item_code query filter below reads the cache synchronously.
		frappe.db.get_list("Plant Warehouse", { fields: ["name", "wip_fg_warehouse"], limit_page_length: 0 })
			.then(function (rows) {
				const map = {};
				rows.forEach(function (r) { map[r.name] = r.wip_fg_warehouse; });
				frm._plant_warehouse_map = map;
			});
		frm.set_query("item_code", "items", function () {
			const warehouse = (frm._plant_warehouse_map || {})[frm.doc.plant];
			if (!warehouse) {
				return {};
			}
			return { filters: { custom_manufacturing_location: warehouse } };
		});
		// Apply BOM query and focus handler so we know which row's item_code to use
		function apply_bom_query_to_rows() {
			if (!grid || !grid.grid_rows) return;
			grid.grid_rows.forEach(function (row) {
				const field = row.on_grid_fields_dict && row.on_grid_fields_dict["bom"];
				if (field) {
					field.get_query = bom_get_query;
					// On focus, store this row's item_code for get_query (link passes parent doc, not row)
					if (field.$input && !field.$input.data("bom-focus-bound")) {
						field.$input.on("focus", function () {
							_bom_row_item_code = row.doc ? row.doc.item_code : null;
						});
						field.$input.data("bom-focus-bound", true);
					}
				}
			});
		}
		apply_bom_query_to_rows();
		// Re-apply after grid refresh (e.g. new row added)
		if (grid && grid.refresh) {
			const _refresh = grid.refresh.bind(grid);
			grid.refresh = function () {
				_refresh();
				setTimeout(apply_bom_query_to_rows, 0);
			};
		}

		// Add "Split Work Orders" button
		if (frm.doc.docstatus === 1 && frm.doc.items && frm.doc.items.length > 0) {
			frm.add_custom_button(__('Split Work Orders'), function() {
				show_work_order_dialog(frm);
			});
		}

		// Fetch live stock + packing for all existing rows on load (display only, no dirty)
		refresh_all_rows_stock(frm);
	},

	validate(frm) {
		validate_week_and_batch_fields(frm);
	},

	after_save(frm) {
		// Non-blocking warning (shown after save so the dialog renders with content even
		// for a new doc that re-routes on first save): any week (with demand) having 0
		// Batch Capacity or 0 Batch Quantity.
		warn_zero_capacity_or_batch_qty(frm);
	},

	set_warehouse(frm) {
		// Auto-refresh stock when set_warehouse is changed by the user.
		// Skipped for programmatic changes (plant -> warehouse); that flow refreshes itself.
		if (_suspend_warehouse_refresh) return;
		if (frm.doc.material_request_items && frm.doc.material_request_items.length > 0) {
			refresh_stock_quantities(frm);
		}
	},

	set_warehouse_2(frm) {
		// Auto-refresh stock when set_warehouse_2 is changed
		if (_suspend_warehouse_refresh) return;
		if (frm.doc.material_request_items && frm.doc.material_request_items.length > 0) {
			refresh_stock_quantities(frm);
		}
	},

	get_fetch_material_request_item(frm) {
		queue_doc_call(() => frm.call({
			method: 'fetch_material_request_items',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('Fetching material request items...'),
			callback: function(r) {
				console.log(r);
				if (!r.exc && r.message) {
					frm.refresh_field('material_request_items');

					if (r.message.status === 'error') {
						frappe.msgprint({
							title: __('Error'),
							indicator: 'red',
							message: r.message.message
						});
					} 
					// else {
					// 	frm.save().then(() => {
					// 		// Show success message
					// 		frappe.show_alert({
					// 			message: __(r.message.message || 'Material Request Items fetched successfully'),
					// 			indicator: 'green'
					// 		});

					// 		// Show warning if any items don't have BOM
					// 		if (r.message.warning) {
					// 			frappe.msgprint({
					// 				title: __('Warning'),
					// 				indicator: 'orange',
					// 				message: r.message.warning
					// 			});
					// 		}
					// 	});
					// }
				}
			}
		}));
	},

	forecast_start_date(frm) {
		fetch_sales_forecasts_if_dates_set(frm);
	},

	forecast_end_date(frm) {
		fetch_sales_forecasts_if_dates_set(frm);
	},

	company(frm) {
		fetch_sales_forecasts_if_dates_set(frm);
	},

	plant(frm) {
		// Re-fetch items for the newly selected plant (items are filtered by
		// the item's Manufacturing Location matching the plant's FG warehouse).
		// The warehouse is set *after* the fetch response lands -- see queue_doc_call().
		fetch_sales_forecasts_if_dates_set(frm);
		queue_doc_call(() => set_warehouse_for_plant(frm));
	}
});

// Every frm.call({doc: frm.doc}) posts the whole client doc and its response re-syncs
// the whole doc back (frappe.model.sync on response.docs). Two of them in flight at once
// means the slower response overwrites whatever the faster one produced -- that is why
// freshly fetched items disappeared and set_warehouse reverted. Keep them strictly
// sequential, and queue local doc edits that must survive a sync onto the same chain.
let _doc_call_chain = Promise.resolve();

function queue_doc_call(fn) {
	_doc_call_chain = _doc_call_chain.then(fn).catch(() => {});
	return _doc_call_chain;
}

// Set Warehouse follows the selected Plant.
// NOTE: "Plant 2 WIP RM  - PTPL" has a double space before the dash — that is the real
// warehouse name; do not "fix" it.
const PLANT_SET_WAREHOUSE = {
	"Plant 1": "Plant 1 WIP FG - PTPL",
	"Plant 2": "Plant 2 WIP RM  - PTPL",
};

// Set warehouse is a Link -- a name that does not exist is rejected and the field is left
// blank. Because of the irregular spacing above, fall back to a whitespace-tolerant match
// rather than silently leaving the field empty.
async function resolve_warehouse(name) {
	if (await frappe.db.exists("Warehouse", name)) return name;
	const rows = await frappe.db.get_list("Warehouse", {
		filters: [["name", "like", name.replace(/\s+/g, "%")]],
		fields: ["name"],
		limit: 1
	});
	return rows && rows.length ? rows[0].name : null;
}

let _suspend_warehouse_refresh = false;

async function set_warehouse_for_plant(frm) {
	const preferred = PLANT_SET_WAREHOUSE[frm.doc.plant];
	if (!preferred) return;

	const warehouse = await resolve_warehouse(preferred);
	if (!warehouse) {
		frappe.show_alert({
			message: __("No Set Warehouse found for {0} ({1})", [frm.doc.plant, preferred]),
			indicator: "orange"
		});
		return;
	}
	if (frm.doc.set_warehouse === warehouse) return;

	_suspend_warehouse_refresh = true;
	try {
		await frm.set_value("set_warehouse", warehouse);
	} finally {
		_suspend_warehouse_refresh = false;
	}

	// The refresh the set_warehouse handler would normally do. Called unqueued because we
	// are already running inside the queue -- re-queueing here would wait on ourselves.
	if (frm.doc.material_request_items && frm.doc.material_request_items.length > 0) {
		await do_refresh_stock_quantities(frm);
	}
}

function validate_week_and_batch_fields(frm) {
	// Allow save even when w1_batch, w2_batch, w3_batch, w4_batch are 0.
	// No validation that blocks save for zero batch values.
}

function warn_zero_capacity_or_batch_qty(frm) {
	// Non-blocking warning shown before save: for any week that has demand (week_N > 0),
	// flag if its Batch Capacity is 0 or its Batch Quantity is 0. Save still proceeds.
	if (!frm.doc.items || !frm.doc.items.length) return;

	const weeks = [
		{ n: 1, week: 'week_1', cap: 'batch_capacity_1', qty: 'w1_batch_qty' },
		{ n: 2, week: 'week_2', cap: 'batch_capacity_2', qty: 'w2_batch_qty' },
		{ n: 3, week: 'week_3', cap: 'batch_capacity_3', qty: 'w3_batch_qty' },
		{ n: 4, week: 'week_4', cap: 'batch_capacity_4', qty: 'w4_batch_qty' }
	];

	let issues = [];
	frm.doc.items.forEach(function(row, idx) {
		weeks.forEach(function(w) {
			if (flt(row[w.week]) > 0) {
				let cap_zero = flt(row[w.cap]) === 0;
				let qty_zero = flt(row[w.qty]) === 0;
				if (cap_zero || qty_zero) {
					let what = [];
					if (cap_zero) what.push(__('Batch Capacity'));
					if (qty_zero) what.push(__('Batch Quantity'));
					issues.push(__('Row #{0} ({1}) — Week {2}: {3} is 0',
						[idx + 1, row.item_code || '', w.n, what.join(' & ')]));
				}
			}
		});
	});

	if (issues.length) {
		frappe.msgprint({
			title: __('Warning'),
			indicator: 'orange',
			message: __('Please review the following before continuing:') + '<br>• ' + issues.join('<br>• ')
		});
	}
}

function fetch_sales_forecasts_if_dates_set(frm) {
	// Only fetch if all required fields are set (plant drives item filtering)
	if (frm.doc.forecast_start_date && frm.doc.forecast_end_date && frm.doc.company && frm.doc.plant) {
		return queue_doc_call(() => frm.call({
			method: 'fetch_sales_forecasts',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('Fetching sales forecasts...'),
			callback: function(r) {
				if (!r.exc) {
					frm.refresh_field('items');
					// Fetch stock + packing (loose qty) for the freshly fetched rows
					refresh_all_rows_stock(frm);
					frappe.show_alert({
						message: __('Sales Forecasts fetched successfully'),
						indicator: 'green'
					});
				}
			}
		}));
	}
	return Promise.resolve();
}

frappe.ui.form.on("Forecast Club Item", {
	item_code(frm, cdt, cdn) {
		check_duplicate_item(frm, cdt, cdn);
		fetch_item_stock_and_packaging(frm, cdt, cdn);
		// Clear BOM when item changes so user picks a BOM for the new item
		frappe.model.set_value(cdt, cdn, "bom", "");
	},

	week_1(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_1', 'w1_batch', 'Week 1');
		calculate_totals(frm, cdt, cdn);
	},

	week_2(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_2', 'w2_batch', 'Week 2');
		calculate_totals(frm, cdt, cdn);
	},

	week_3(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_3', 'w3_batch', 'Week 3');
		calculate_totals(frm, cdt, cdn);
	},

	week_4(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_4', 'w4_batch', 'Week 4');
		calculate_totals(frm, cdt, cdn);
	},

	w1_batch(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_1', 'w1_batch', 'Week 1');
		calculate_totals(frm, cdt, cdn);
	},

	w2_batch(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_2', 'w2_batch', 'Week 2');
		calculate_totals(frm, cdt, cdn);
	},

	w3_batch(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_3', 'w3_batch', 'Week 3');
		calculate_totals(frm, cdt, cdn);
	},

	w4_batch(frm, cdt, cdn) {
		validate_week_batch_relationship(frm, cdt, cdn, 'week_4', 'w4_batch', 'Week 4');
		calculate_totals(frm, cdt, cdn);
	},

	// Recompute when batch capacity changes (also fires when fetched from the blender)
	batch_capacity_1(frm, cdt, cdn) { calculate_totals(frm, cdt, cdn); },
	batch_capacity_2(frm, cdt, cdn) { calculate_totals(frm, cdt, cdn); },
	batch_capacity_3(frm, cdt, cdn) { calculate_totals(frm, cdt, cdn); },
	batch_capacity_4(frm, cdt, cdn) { calculate_totals(frm, cdt, cdn); },

	// Blender selection fetches batch_capacity_N (fetch_from); recompute after the fetch settles
	blender_week_1(frm, cdt, cdn) { setTimeout(() => calculate_totals(frm, cdt, cdn), 500); },
	blender_week_2(frm, cdt, cdn) { setTimeout(() => calculate_totals(frm, cdt, cdn), 500); },
	blender_week_3(frm, cdt, cdn) { setTimeout(() => calculate_totals(frm, cdt, cdn), 500); },
	blender_week_4(frm, cdt, cdn) { setTimeout(() => calculate_totals(frm, cdt, cdn), 500); }
});

function validate_week_batch_relationship(frm, cdt, cdn, week_field, batch_field, week_label) {
	let row = locals[cdt][cdn];
	const week_value = row[week_field] || 0;
	const batch_value = row[batch_field] || 0;

	// If week value is greater than 0, batch must also be greater than 0
	// if (week_value > 0 && batch_value === 0) {
	// 	frappe.msgprint({
	// 		title: __('Validation Error'),
	// 		indicator: 'orange',
	// 		message: __('{0} has a value of {1}, but {2} Batch is 0 or empty. Please enter a batch value when week value is greater than 0.',
	// 			[week_label, week_value, week_label])
	// 	});
	// }
}

function fetch_item_stock_and_packaging(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.item_code) return;

	frappe.call({
		method: 'sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.get_item_stock_and_packaging',
		args: { item_code: row.item_code, company: frm.doc.company },
		callback: function(r) {
			if (r && r.message) {
				frappe.model.set_value(cdt, cdn, 'custom_company_stock', r.message.custom_company_stock);
				['current_stock', 'last_month_sales'].forEach(function(f) {
					if (r.message[f] !== undefined) {
						frappe.model.set_value(cdt, cdn, f, r.message[f]);
					}
				});
				['custom_plant_1_fg_loose_qty', 'custom_plant_2_fg_loose_qty', 'custom_mainstore_fg'].forEach(function(f) {
					if (r.message[f] !== undefined) {
						frappe.model.set_value(cdt, cdn, f, r.message[f]);
					}
				});
				if (r.message.custom_item_packaging_material !== undefined) {
					frappe.model.set_value(cdt, cdn, 'custom_item_packaging_material', r.message.custom_item_packaging_material);
					frappe.model.set_value(cdt, cdn, 'custom__item_packaging_material', r.message.custom_item_packaging_material);
				}
			}
		}
	});
}

function refresh_all_rows_stock(frm) {
	// Fetch latest stock + packing (loose qty) for every existing item row.
	// Values are assigned directly to the row (not via set_value) so opening the
	// form does NOT mark it dirty -- it just shows current data, same as a save would.
	// Once submitted, stock is frozen at submit-time values and must not be refreshed.
	if (frm.doc.docstatus === 1) return;
	if (!frm.doc.items || !frm.doc.items.length) return;
	frm.doc.items.forEach(function(row) {
		if (!row.item_code) return;
		// Derived from values already on the row, so no server round-trip needed.
		row.forecast_quantity = flt(row.week_1) + flt(row.week_2) + flt(row.week_3) + flt(row.week_4);
		row.planned_quantity = flt(row.w1_batch_qty) + flt(row.w2_batch_qty) + flt(row.w3_batch_qty) + flt(row.w4_batch_qty);
		frappe.call({
			method: 'sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.get_item_stock_and_packaging',
			args: { item_code: row.item_code, company: frm.doc.company },
			callback: function(r) {
				if (!r || !r.message) return;
				let m = r.message;
				row.custom_company_stock = m.custom_company_stock;
				['current_stock', 'last_month_sales', 'custom_plant_1_fg_loose_qty', 'custom_plant_2_fg_loose_qty', 'custom_mainstore_fg'].forEach(function(f) {
					if (m[f] !== undefined) row[f] = m[f];
				});
				if (m.custom_item_packaging_material !== undefined) {
					row.custom_item_packaging_material = m.custom_item_packaging_material;
					row.custom__item_packaging_material = m.custom_item_packaging_material;
				}
				frm.refresh_field('items');
			}
		});
	});
}

function check_duplicate_item(frm, cdt, cdn) {
	let row = locals[cdt][cdn];

	if (!row.item_code) {
		return;
	}

	// Count occurrences of this item_code
	let duplicate_found = false;
	let first_row_idx = null;

	frm.doc.items.forEach((item, idx) => {
		if (item.item_code === row.item_code) {
			if (first_row_idx === null) {
				first_row_idx = idx + 1;
			} else if (item.name === row.name) {
				// This is the duplicate row
				duplicate_found = true;
				frappe.msgprint({
					title: __('Duplicate Item'),
					indicator: 'orange',
					message: __('Item {0} already exists in Row #{1}. Please select a different item or remove the duplicate.',
						[frappe.bold(row.item_code), first_row_idx])
				});
			}
		}
	});

	// If duplicate found, clear the item_code
	if (duplicate_found) {
		frappe.model.set_value(cdt, cdn, 'item_code', '');
	}
}

function calculate_totals(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row) return;

	// Weekly batch qty = that week's batch capacity (from blender) * number of batches
	let q1 = flt(row.batch_capacity_1) * flt(row.w1_batch);
	let q2 = flt(row.batch_capacity_2) * flt(row.w2_batch);
	let q3 = flt(row.batch_capacity_3) * flt(row.w3_batch);
	let q4 = flt(row.batch_capacity_4) * flt(row.w4_batch);

	frappe.model.set_value(cdt, cdn, 'w1_batch_qty', q1);
	frappe.model.set_value(cdt, cdn, 'w2_batch_qty', q2);
	frappe.model.set_value(cdt, cdn, 'w3_batch_qty', q3);
	frappe.model.set_value(cdt, cdn, 'w4_batch_qty', q4);

	// Total batch qty = sum of weekly batches
	let total_batch_qty = flt(row.w1_batch) + flt(row.w2_batch) + flt(row.w3_batch) + flt(row.w4_batch);
	frappe.model.set_value(cdt, cdn, 'total_batch_qty', total_batch_qty);

	// Total qty = sum of weekly batch quantities
	frappe.model.set_value(cdt, cdn, 'total_qty', q1 + q2 + q3 + q4);

	// Forecast Quantity = total weekly demand; Planned Quantity = total planned production.
	// before_save recomputes both server-side; mirroring them here shows them before save.
	frappe.model.set_value(cdt, cdn, 'forecast_quantity',
		flt(row.week_1) + flt(row.week_2) + flt(row.week_3) + flt(row.week_4));
	frappe.model.set_value(cdt, cdn, 'planned_quantity', q1 + q2 + q3 + q4);

	frm.refresh_field('items');
}

function show_work_order_dialog(frm) {
	// First dialog: Select week
	let week_dialog = new frappe.ui.Dialog({
		title: __('Select Week for Work Orders'),
		fields: [
			{
				fieldname: 'week',
				fieldtype: 'Select',
				label: __('Week'),
				options: [
					'Week 1',
					'Week 2',
					'Week 3',
					'Week 4'
				],
				reqd: 1,
				default: 'Week 1'
			}
		],
		primary_action_label: __('Next'),
		primary_action(values) {
			week_dialog.hide();
			show_items_selection_dialog(frm, values.week);
		}
	});

	week_dialog.show();
}

function show_items_selection_dialog(frm, selected_week) {
	// Map week display name to field names
	const week_map = {
		'Week 1': { week_field: 'week_1', batch_field: 'w1_batch', batch_qty_field: 'w1_batch_qty', wo_field: 'w1_wo', batch_capacity_field: 'batch_capacity_1' },
		'Week 2': { week_field: 'week_2', batch_field: 'w2_batch', batch_qty_field: 'w2_batch_qty', wo_field: 'w2_wo', batch_capacity_field: 'batch_capacity_2' },
		'Week 3': { week_field: 'week_3', batch_field: 'w3_batch', batch_qty_field: 'w3_batch_qty', wo_field: 'w3_wo', batch_capacity_field: 'batch_capacity_3' },
		'Week 4': { week_field: 'week_4', batch_field: 'w4_batch', batch_qty_field: 'w4_batch_qty', wo_field: 'w4_wo', batch_capacity_field: 'batch_capacity_4' }
	};

	const week_data = week_map[selected_week];

	// Get existing Work Order count for each item
	frappe.call({
		method: 'sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.get_work_order_summary',
		args: {
			forecast_club: frm.doc.name,
			week: week_data.week_field
		},
		callback: function(r) {
			if (!r.exc && r.message) {
				let wo_summary = r.message;

				// Filter items that have batch quantity for this week
				let items_with_batch = frm.doc.items.filter(item => {
					let batch_qty = item[week_data.batch_qty_field] || 0;
					return batch_qty > 0 && item.item_code && item.bom;
				});

				if (items_with_batch.length === 0) {
					frappe.msgprint(__('No items found with batch quantity for {0}.', [selected_week]));
					return;
				}

				show_items_table(frm, selected_week, week_data, items_with_batch, wo_summary);
			}
		}
	});
}

function show_items_table(frm, selected_week, week_data, items_with_batch, wo_summary) {

	// Prepare items data for child table
	let items_data = items_with_batch.map(item => {
		let batch_count = item[week_data.batch_field] || 0;
		// let batch_size = item.batch_size || 0;
		let wo_created = wo_summary[item.item_code] || 0;
		let remaining_batches = batch_count - wo_created;

		return {
			item_code: item.item_code,
			item_name: item.item_name || '',
			// batch_size: batch_size,
			// "Batch Quantity" column shows this week's Batch Capacity (batch_capacity_N)
			batch_capacity: item[week_data.batch_capacity_field] || 0,
			total_batches: batch_count,
			wo_created: wo_created,
			remaining_batches: remaining_batches,
			batches_to_create: remaining_batches > 0 ? remaining_batches : 0,
			forecast_club_item: item.name
		};
	});

	let items_dialog = new frappe.ui.Dialog({
		title: __('Create Work Orders for {0}', [selected_week]),
		fields: [
			{
				fieldtype: 'Table',
				fieldname: 'items',
				label: __('Items'),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				data: items_data,
				get_data: () => {
					return items_data;
				},
				fields: [
					{
						fieldtype: 'Data',
						fieldname: 'item_code',
						label: __('Item Code'),
						in_list_view: 1,
						read_only: 1,
						columns: 2
					},
					{
						fieldtype: 'Data',
						fieldname: 'item_name',
						label: __('Item Name'),
						in_list_view: 1,
						read_only: 1,
						columns: 2
					},
					// {
					// 	fieldtype: 'Float',
					// 	fieldname: 'batch_size',
					// 	label: __('Batch Size'),
					// 	in_list_view: 1,
					// 	read_only: 1,
					// 	columns: 1
					// },
					{
						fieldtype: 'Data',
						fieldname: 'batch_capacity',
						label: __('Batch Quantity'),
						in_list_view: 1,
						read_only: 1,
						columns: 1
					},
					{
						fieldtype: 'Int',
						fieldname: 'batches_to_create',
						label: __('No. of Batches to Create'),
						in_list_view: 1,
						columns: 1
					},
					{
						fieldtype: 'Int',
						fieldname: 'total_batches',
						label: __('Total Batches'),
						in_list_view: 1,
						read_only: 1,
						columns: 1
					},
					{
						fieldtype: 'Int',
						fieldname: 'wo_created',
						label: __('WO Created'),
						in_list_view: 1,
						read_only: 1,
						columns: 1
					},
					{
						fieldtype: 'Int',
						fieldname: 'remaining_batches',
						label: __('Remaining'),
						in_list_view: 1,
						read_only: 1,
						columns: 1
					},
					{
						fieldtype: 'Data',
						fieldname: 'forecast_club_item',
						label: __('Forecast Club Item'),
						hidden: 1
					}
				]
			}
		],
		size: 'extra-large',
		primary_action_label: __('Create Work Orders'),
		primary_action(values) {
			// Get selected rows from the table
			let table_field = items_dialog.fields_dict.items;
			let selected_rows = table_field.grid.get_selected_children();

			// Check if any rows are selected
			if (selected_rows.length === 0) {
				frappe.msgprint({
					title: __('No Items Selected'),
					indicator: 'orange',
					message: __('Please select at least one item by checking the checkbox on the left side of the row')
				});
				return;
			}

			// Validate and collect items to create (only selected rows)
			let items_to_create = [];

			selected_rows.forEach(row => {
				let batches = parseInt(row.batches_to_create) || 0;
				if (batches > 0) {
					// Validate batches_to_create doesn't exceed remaining
					if (batches > row.remaining_batches) {
						frappe.msgprint({
							title: __('Validation Error'),
							indicator: 'red',
							message: __('Item {0}: Batches to create ({1}) cannot exceed remaining batches ({2})',
								[row.item_code, batches, row.remaining_batches])
						});
						frappe.validated = false;
						return false;
					}

					items_to_create.push({
						forecast_club_item: row.forecast_club_item,
						item_code: row.item_code,
						// "Batch Quantity" column holds this week's batch capacity -> WO qty per batch
						batch_size: flt(row.batch_capacity),
						batches: batches
					});
				}
			});

			if (items_to_create.length === 0) {
				frappe.msgprint({
					title: __('No Batches to Create'),
					indicator: 'orange',
					message: __('Please set "Batches to Create" for the selected items')
				});
				return;
			}

			items_dialog.hide();

			// Call server method to create work orders
			frappe.call({
				method: 'sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.create_work_orders_batch_wise',
				args: {
					forecast_club: frm.doc.name,
					week: week_data.week_field,
					items: items_to_create
				},
				freeze: true,
				freeze_message: __('Creating Work Orders...'),
				callback: function(r) {
					if (!r.exc && r.message && r.message.length > 0) {
						frappe.show_alert({
							message: __('Created {0} Work Orders', [r.message.length]),
							indicator: 'green'
						});
						frm.reload_doc();
					} else if (r.message && r.message.length === 0) {
						frappe.msgprint(__('No Work Orders created.'));
					}
				}
			});
		}
	});

	items_dialog.show();
}

function refresh_stock_quantities(frm) {
	return queue_doc_call(() => do_refresh_stock_quantities(frm));
}

function do_refresh_stock_quantities(frm) {
	// Re-fetch material request items to update stock quantities
	return frm.call({
		method: 'fetch_material_request_items',
		doc: frm.doc,
		freeze: true,
		freeze_message: __('Updating stock quantities...'),
		callback: function(r) {
			if (!r.exc && r.message) {
				frm.refresh_field('material_request_items');
				frappe.show_alert({
					message: __('Stock quantities updated'),
					indicator: 'green'
				});
			}
		}
	});
}
