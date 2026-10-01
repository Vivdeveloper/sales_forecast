// Copyright (c) 2026, Viv Choudhary and contributors
// For license information, please see license.txt

frappe.ui.form.on("Forecast Sales Person", {
	refresh(frm) {
		// Set up date filters when form loads
		setup_date_filters(frm);
		setup_item_group_filter(frm);
		setup_item_customer_filters(frm);
		setup_packed_goods_filter(frm);
		show_sales_person_info(frm);
		apply_week_locks(frm);
		lock_sales_person_for_current_user(frm);
		update_monthly_target(frm);
		render_week_totals(frm);
		setup_secondary_customer_query(frm);
		init_channel_partner_flags(frm);
	},

	posting_date(frm) {
		if (frm.doc.posting_date) {
			validate_posting_date(frm);
			setup_date_filters(frm);
			auto_set_forecast_dates(frm);
		}
		apply_week_locks(frm);
	},

	sales_person(frm) {
		if (frm.doc.sales_person) {
			setup_item_customer_filters(frm);
			show_sales_person_info(frm);
		}
		update_monthly_target(frm);
	},

	forecast_start_date(frm) {
		if (frm.doc.forecast_start_date) {
			validate_forecast_date(frm, 'forecast_start_date');
		}
		update_monthly_target(frm);
	},

	forecast_end_date(frm) {
		if (frm.doc.forecast_end_date) {
			validate_forecast_date(frm, 'forecast_end_date');
		}
		update_monthly_target(frm);
	}
});

// Pull the Sales Person's Monthly Target totals for the forecast period and show
// them in the read-only Target fields.
function update_monthly_target(frm) {
	if (!frm.doc.sales_person || !frm.doc.forecast_start_date || !frm.doc.forecast_end_date) {
		frm.set_value('monthly_target_qty', 0);
		frm.set_value('monthly_target_amount', 0);
		recompute_summary(frm);
		return;
	}

	frappe.call({
		method: 'sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.get_monthly_target_summary',
		args: {
			sales_person: frm.doc.sales_person,
			start_date: frm.doc.forecast_start_date,
			end_date: frm.doc.forecast_end_date
		},
		callback: function(r) {
			if (r.message) {
				frm.set_value('monthly_target_qty', r.message.target_qty);
				frm.set_value('monthly_target_amount', r.message.target_amount);
				// target changed -> the shortfall vs forecast changes too
				recompute_summary(frm);
			}
		}
	});
}

// Forecast Quantity / Amount = the loose-material grand totals; Difference = how much the
// forecast is SHORT of the target (Target − Forecast, floored at 0 — never negative). These
// are read-only display fields kept in sync live; the server recomputes them on save (source
// of truth), so assign directly to avoid marking a saved doc dirty just by viewing it.
function recompute_summary(frm) {
	let loose_qty = 0, loose_amt = 0;
	(frm.doc.items || []).forEach((row) => {
		loose_qty += flt(row.total_week_quantity_loose);
		loose_amt += flt(row.total_month_rate_loose);
	});
	const diff_qty = Math.max(0, flt(frm.doc.monthly_target_qty) - loose_qty);
	const diff_amt = Math.max(0, flt(frm.doc.monthly_target_amount) - loose_amt);

	const assign = (field, val) => {
		if (frm.doc[field] !== val) { frm.doc[field] = val; frm.refresh_field(field); }
	};
	assign('forecast_qty', loose_qty);
	assign('forecast_amount', loose_amt);
	assign('difference_qty', diff_qty);
	assign('difference_amount', diff_amt);
}

frappe.ui.form.on("Forecast Sales Person Wise Item", {
	items_add(frm) {
		setup_item_group_filter(frm);
		setup_item_customer_filters(frm);
		apply_week_locks(frm);
		render_week_totals(frm);
	},
	items_remove(frm) {
		render_week_totals(frm);
	},
	// Manual Week N -> recompute that row's Loose Material (= Filling Capacity × Week N).
	week_1: (frm, cdt, cdn) => { recompute_loose_material(frm, cdt, cdn); render_week_totals(frm); },
	week_2: (frm, cdt, cdn) => { recompute_loose_material(frm, cdt, cdn); render_week_totals(frm); },
	week_3: (frm, cdt, cdn) => { recompute_loose_material(frm, cdt, cdn); render_week_totals(frm); },
	week_4: (frm, cdt, cdn) => { recompute_loose_material(frm, cdt, cdn); render_week_totals(frm); },

	// Filling Capacity changed (e.g. after picking Packed Goods) -> recompute Loose Material,
	// then re-render the totals + Forecast/Difference summary so it all updates live.
	filling_capacity(frm, cdt, cdn) {
		recompute_loose_material(frm, cdt, cdn);
		render_week_totals(frm);
	},

	// Changing the item changes which packing materials are valid — clear stale selections,
	// then pull last month's week-wise sales for the new item.
	item_code(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "packed_goods", null);
		frappe.model.set_value(cdt, cdn, "filling_capacity", 0);
		fetch_last_month_sales(frm, cdt, cdn);
		// Item changed -> packed good cleared above, so the rate has no basis; clear it.
		fetch_customer_rate(frm, cdt, cdn);
		// Vertical is fetched from the item (async); re-render the by-vertical totals once it lands.
		setTimeout(() => render_week_totals(frm), 500);
	},

	// Vertical changed (fetched from the item) -> re-group the by-vertical total tables.
	vertical(frm) {
		render_week_totals(frm);
	},

	// Customer scopes the sales history -> refetch. Customer and Miscellaneous Customer are
	// mutually exclusive: picking a Customer clears + disables the Misc flag.
	customer(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.customer && row.miscellaneous_customer) {
			frappe.model.set_value(cdt, cdn, "miscellaneous_customer", 0);
			// misc got cleared -> also clear its auto-filled price fields
			frappe.model.set_value(cdt, cdn, "rate_per_unit", 0);
			frappe.model.set_value(cdt, cdn, "rate", 0);
		}
		enforce_customer_exclusivity(frm);
		fetch_last_month_sales(frm, cdt, cdn);
		// Customer drives Rate Per Unit + Rate (Customer Special -> Standard Selling).
		fetch_customer_rate(frm, cdt, cdn);
		// If the customer is a Channel Partner, enable + populate the Secondary Customer
		// dropdown (shown only in the row popup, never as a grid column).
		update_channel_partner_secondary(frm, cdt, cdn);
	},

	// Miscellaneous Customer: on tick, fill Rate/Rate Per Unit from the packed good's Standard
	// Selling (company) price. Mutually exclusive with Customer: ticking it clears + disables Customer.
	miscellaneous_customer(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.miscellaneous_customer && row.customer) {
			frappe.model.set_value(cdt, cdn, "customer", "");
		}
		enforce_customer_exclusivity(frm);
		fetch_customer_rate(frm, cdt, cdn);
	},

	// Selecting a Packed Goods fetches its Filling Capacity from the item's Packing
	// Material Details (which then recomputes Loose Material via the filling_capacity event).
	packed_goods(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || !row.packed_goods) {
			frappe.model.set_value(cdt, cdn, "filling_capacity", 0);
			return;
		}
		frappe.call({
			method: "sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.get_packing_filling_capacity",
			args: { item_code: row.item_code, packed_goods: row.packed_goods },
			callback: (r) => frappe.model.set_value(cdt, cdn, "filling_capacity", flt(r.message)),
		});
		// Sales/pipeline history is keyed off the packed good -> (re)pull it now.
		fetch_last_month_sales(frm, cdt, cdn);
		// Rate Per Unit + Rate come from the packed good's Item Price (per customer / misc = company).
		fetch_customer_rate(frm, cdt, cdn);
	}
});

// Re-render the Items grid so each row's read_only_depends_on (Customer <-> Miscellaneous
// Customer mutual exclusion) is re-evaluated and the disabled cell reflects the current row.
function enforce_customer_exclusivity(frm) {
	frm.refresh_field("items");
}

// Loose Material Week N = Filling Capacity × Week N (read-only, auto). Then roll up the
// loose totals.
function recompute_loose_material(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const fc = flt(row.filling_capacity);
	[1, 2, 3, 4].forEach((n) => {
		frappe.model.set_value(cdt, cdn, `loose_material_week_${n}`, fc * flt(row[`week_${n}`]));
	});
	recompute_loose_totals(frm, cdt, cdn);
}

// Derive the loose totals + revenue columns for a row (read-only, auto):
//   Total Sales (total_week_quantity_loose) = sum of the four Week N Total Sales (loose).
//   Week N Total Revenue (sales_amount_week_N) = Week N Total Sales × Rate Per Unit.
//   Total Revenue (total_sales_amount)         = Total Sales × Rate Per Unit.
//   Total Month Rate (Loose)                   = Total Sales × Rate Per Unit.
function recompute_loose_totals(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const rpu = flt(row.rate_per_unit);
	let total_loose = 0;
	[1, 2, 3, 4].forEach((n) => {
		const lw = flt(row[`loose_material_week_${n}`]);
		total_loose += lw;
		frappe.model.set_value(cdt, cdn, `sales_amount_week_${n}`, lw * rpu);
	});
	frappe.model.set_value(cdt, cdn, "total_week_quantity_loose", total_loose);
	frappe.model.set_value(cdt, cdn, "total_sales_amount", total_loose * rpu);
	frappe.model.set_value(cdt, cdn, "total_month_rate_loose", total_loose * rpu);
}

// Fill the row's Rate Per Unit + Rate. Live, on change.
//   - Real Customer + Packing Material -> the MOST RECENT Sales Invoice for that exact
//     (customer + packing material) combination. If no such invoice exists, the row is
//     switched to Miscellaneous Customer (Standard Selling company rate) instead.
//   - Miscellaneous Customer (no specific customer) -> Standard Selling (company rate).
// No packed good -> no pricing basis, clear both.
function fetch_customer_rate(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	// No packed good yet -> nothing to price against, clear.
	if (!row.packed_goods) {
		frappe.model.set_value(cdt, cdn, "rate_per_unit", 0);
		frappe.model.set_value(cdt, cdn, "rate", 0);
		return;
	}
	// Real customer -> price from the last invoice for this (customer + packing material).
	if (row.customer && !row.miscellaneous_customer) {
		fetch_rate_from_last_invoice(frm, cdt, cdn);
		return;
	}
	// Miscellaneous / no customer -> Standard Selling (company) rate from the Item Price.
	fetch_rate_from_item_price(frm, cdt, cdn);
}

// Standard Selling (company) rate from the PACKED GOOD's Item Price — used for Miscellaneous
// Customer rows (and as the fallback when a customer has no past invoice).
function fetch_rate_from_item_price(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.packed_goods) return;
	const customer = row.miscellaneous_customer ? "" : (row.customer || "");
	frappe.call({
		method: "sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.get_customer_item_rate",
		args: { item_code: row.packed_goods, customer: customer },
		callback: (r) => {
			const d = r.message || {};
			if (d.rate_per_unit === undefined && d.rate === undefined) return;
			frappe.model.set_value(cdt, cdn, "rate_per_unit", flt(d.rate_per_unit));
			frappe.model.set_value(cdt, cdn, "rate", flt(d.rate));
			recompute_loose_totals(frm, cdt, cdn);
			render_week_totals(frm);
		},
	});
}

// Most recent Sales Invoice rate + rate-per-unit for this (customer + packing material). If
// none is found, auto-tick Miscellaneous Customer so the row falls back to Standard Selling.
function fetch_rate_from_last_invoice(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.call({
		method: "sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.get_last_invoice_rate",
		args: { customer: row.customer, item_code: row.packed_goods },
		callback: (r) => {
			const d = r.message || {};
			if (d.found) {
				frappe.model.set_value(cdt, cdn, "rate_per_unit", flt(d.rate_per_unit));
				frappe.model.set_value(cdt, cdn, "rate", flt(d.rate));
				recompute_loose_totals(frm, cdt, cdn);
				render_week_totals(frm);
			} else {
				// No past invoice for this customer + packing material -> treat as misc customer.
				frappe.show_alert({
					message: __("No past invoice for {0} + {1}. Switched to Miscellaneous Customer (Standard Selling rate).",
						[row.customer, row.packed_goods]),
					indicator: "orange",
				});
				// Ticking misc clears the customer and fetches the Standard Selling rate.
				frappe.model.set_value(cdt, cdn, "miscellaneous_customer", 1);
			}
		},
	});
}

// Pull last month's week-wise Sales Qty + Sales Amount (without GST) for the row's
// PACKED GOODS item (+customer) from submitted Sales Invoices, and fill the read-only
// columns. The sales/GRN/invoice history lives against the packed good, not the main item,
// so the pipeline figures are keyed off packed_goods. No packed good -> clear the columns.
function fetch_last_month_sales(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	// Only the last-month actual Sales QTY columns come from invoices. Revenue columns
	// (Week N Total Revenue / Total Revenue) are forecast = loose × Rate Per Unit and are
	// handled by recompute_loose_totals — never touched here.
	if (!row.packed_goods) {
		[1, 2, 3, 4].forEach((n) => {
			frappe.model.set_value(cdt, cdn, `sales_qty_week_${n}`, 0);
		});
		frappe.model.set_value(cdt, cdn, "sales_total_qty", 0);
		return;
	}
	frappe.call({
		method: "sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.get_last_month_sales",
		args: {
			item_code: row.packed_goods,
			customer: row.customer || "",
			ref_date: frm.doc.forecast_start_date || frm.doc.posting_date || "",
			company: frm.doc.company || "",
		},
		callback: (r) => {
			const d = r.message || {};
			const q = d.qty || {};
			[1, 2, 3, 4].forEach((n) => {
				frappe.model.set_value(cdt, cdn, `sales_qty_week_${n}`, flt(q[n]));
			});
			frappe.model.set_value(cdt, cdn, "sales_total_qty", flt(q.total));
		},
	});
}

// Restrict the "Packed Goods" dropdown to the packing materials of each row's item
// (its Item > Packing Material Details tab).
function setup_packed_goods_filter(frm) {
	frm.set_query("packed_goods", "items", function (doc, cdt, cdn) {
		const row = locals[cdt][cdn];
		return {
			query: "sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.packed_goods_query",
			filters: { item_code: row.item_code || "" },
		};
	});
}

// Show live, UI-only week-wise total tables below the Items table (not data rows), CLUBBED
// BY VERTICAL — one row per unique vertical, plus a grand-total row:
//   1. Packed Goods Week-wise Total  — sum of week_1..4 (packed qty)
//   2. Loose Material Week-wise Total — sum of loose_material_week_1..4 (Week N Total Sales)
//   3. Amount Week-wise Total         — per week: sum of (loose qty × Rate Per Unit) = revenue
// Each cell is 0 when there is nothing to add.
function render_week_totals(frm) {
	const wrapper = frm.fields_dict.week_totals_html && frm.fields_dict.week_totals_html.$wrapper;
	if (!wrapper) return;

	const NO_VERTICAL = "(No Vertical)";
	const zero = () => ({ week_1: 0, week_2: 0, week_3: 0, week_4: 0 });
	// key "vertical||packsize" -> { vertical, pack_size, packed, loose, amount }
	const groups = {};
	const ensure = (vertical, pack_size) => {
		const key = vertical + "||" + pack_size;
		if (!groups[key]) {
			groups[key] = { vertical, pack_size, packed: zero(), loose: zero(), amount: zero() };
		}
		return groups[key];
	};

	let packed_grand_all = 0;
	(frm.doc.items || []).forEach((row) => {
		const v = row.vertical || NO_VERTICAL;
		const ps = flt(row.filling_capacity);   // Pack Size Qty
		const g = ensure(v, ps);
		const rpu = flt(row.rate_per_unit);
		[1, 2, 3, 4].forEach((n) => {
			const pk = flt(row[`week_${n}`]);
			const lw = flt(row[`loose_material_week_${n}`]);
			g.packed[`week_${n}`] += pk;
			g.loose[`week_${n}`] += lw;
			g.amount[`week_${n}`] += lw * rpu;   // revenue = loose qty × Rate Per Unit, per week
			packed_grand_all += pk;
		});
	});

	const fmt = (v) => format_number(v, null, 3);
	const fmt2 = (v) => format_number(v, null, 2);

	// Actual Qty field = grand total of all PACKED weeks (across every group). Assign
	// directly (server validate persists it) so viewing a saved doc doesn't mark it dirty.
	if (frm.doc.actual_qty !== packed_grand_all) {
		frm.doc.actual_qty = packed_grand_all;
		frm.refresh_field('actual_qty');
	}

	// Sort by Vertical (name), then by Pack Size, so same-vertical pack sizes group together.
	const keys = Object.keys(groups).sort((a, b) => {
		const A = groups[a], B = groups[b];
		if (A.vertical !== B.vertical) return A.vertical < B.vertical ? -1 : 1;
		return A.pack_size - B.pack_size;
	});

	// One table = heading + one row per (Vertical + Pack Size) + a grand-total row.
	const total_table = (heading, pick, cellfmt) => {
		const grand = zero();
		const body = keys
			.map((k) => {
				const grp = groups[k];
				const t = grp[pick];
				const rowtot = t.week_1 + t.week_2 + t.week_3 + t.week_4;
				[1, 2, 3, 4].forEach((n) => {
					grand[`week_${n}`] += t[`week_${n}`];
				});
				return `
					<tr>
						<td>${frappe.utils.escape_html(grp.vertical)}</td>
						<td class="text-right">${fmt(grp.pack_size)}</td>
						<td class="text-right">${cellfmt(t.week_1)}</td>
						<td class="text-right">${cellfmt(t.week_2)}</td>
						<td class="text-right">${cellfmt(t.week_3)}</td>
						<td class="text-right">${cellfmt(t.week_4)}</td>
						<td class="text-right">${cellfmt(rowtot)}</td>
					</tr>`;
			})
			.join("");
		const gtot = grand.week_1 + grand.week_2 + grand.week_3 + grand.week_4;
		return `
			<table class="table table-bordered" style="margin-bottom:12px;">
				<thead>
					<tr style="background-color:#e9ecef;font-weight:600;">
						<th style="width:32%;background-color:#e9ecef;">${heading} (by Vertical + Pack Size)</th>
						<th class="text-right" style="background-color:#e9ecef;">Pack Size</th>
						<th class="text-right" style="background-color:#e9ecef;">Week 1</th>
						<th class="text-right" style="background-color:#e9ecef;">Week 2</th>
						<th class="text-right" style="background-color:#e9ecef;">Week 3</th>
						<th class="text-right" style="background-color:#e9ecef;">Week 4</th>
						<th class="text-right" style="background-color:#e9ecef;">Total</th>
					</tr>
				</thead>
				<tbody>
					${body}
					<tr>
						<td class="text-muted" colspan="2"><b>Grand Total</b></td>
						<td class="text-right"><b>${cellfmt(grand.week_1)}</b></td>
						<td class="text-right"><b>${cellfmt(grand.week_2)}</b></td>
						<td class="text-right"><b>${cellfmt(grand.week_3)}</b></td>
						<td class="text-right"><b>${cellfmt(grand.week_4)}</b></td>
						<td class="text-right"><b>${cellfmt(gtot)}</b></td>
					</tr>
				</tbody>
			</table>`;
	};

	wrapper.html(`
		<div class="week-totals" style="margin-top:8px;">
			${total_table('Total Pack Qty Week-wise Total', 'packed', fmt)}
			${total_table('Total Sales Weekwise Total', 'loose', fmt)}
			${total_table('Total Revenue Week-wise Total', 'amount', fmt2)}
		</div>
	`);

	// keep the Target vs Forecast summary fields in sync with these totals
	recompute_summary(frm);
}

// Restrict the Item Code picker in the Items table to Finished Goods (and its
// child item groups), so raw materials/packing material etc. don't show up.
function setup_item_group_filter(frm) {
	frm.set_query('item_code', 'items', function() {
		return {
			filters: [
				['Item', 'item_group', 'descendants of (inclusive)', 'Finished Goods']
			]
		};
	});
}

// Week boundaries within the forecast month:
//   Week 1 -> days 1-7, Week 2 -> 8-14, Week 3 -> 15-21, Week 4 -> 22+
function get_week_of_month(day) {
	if (day <= 7) return 1;
	if (day <= 14) return 2;
	if (day <= 21) return 3;
	return 4;
}

// Months as a single comparable number, so "is this month before that one" is one check.
function month_index(year, month) {
	return year * 12 + month;
}

function get_today_parts() {
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	return { year: today.getFullYear(), month: today.getMonth(), day: today.getDate() };
}

// Lock (make read-only) the week columns of the FORECAST month that have already
// elapsed as of today -- that is what blocks backdated entry. The weeks belong to the
// forecast month, not to the posting date's own month, so a forecast for a future month
// keeps all four weeks editable even when the posting date itself falls in week 4.
// e.g. posting on 27-Jul forecasts August and locks nothing; a backdated forecast for
// July viewed on 27-Jul locks Weeks 1-3 and leaves the running Week 4 editable.
function apply_week_locks(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;

	let current_week = 1;
	if (frm.doc.posting_date) {
		const forecast_month = get_forecast_month(frm.doc.posting_date);
		const today = get_today_parts();
		// get_forecast_month() never returns a fully elapsed month, so the forecast month
		// is either the current one (weeks before today's week are locked) or a future one
		// (nothing locked).
		if (month_index(forecast_month.year, forecast_month.month) === month_index(today.year, today.month)) {
			current_week = get_week_of_month(today.day);
		}
	}

	[1, 2, 3, 4].forEach((week) => {
		// Weeks strictly before the current week are locked (read-only).
		const locked = week < current_week ? 1 : 0;
		grid.update_docfield_property(`week_${week}`, "read_only", locked);
	});

	grid.refresh();
}

function validate_posting_date(frm) {
	let posting_date = frappe.datetime.str_to_obj(frm.doc.posting_date);
	let day = posting_date.getDate();

	// Posting date should be between 25th-31st OR 1st-5th only
	// Days 6-24 are NOT allowed
	if (day >= 6 && day <= 24) {
		frappe.msgprint({
			title: __('Invalid Posting Date'),
			indicator: 'red',
			message: __('Posting Date must be between 25th-31st OR 1st-5th of the month only. Days 6-24 are not allowed.')
		});
		frm.set_value('posting_date', '');
		return false;
	}
	return true;
}

function get_forecast_month(posting_date) {
	// Get forecast month based on posting date
	let date = frappe.datetime.str_to_obj(posting_date);
	let day = date.getDate();

	let year = date.getFullYear();
	let month = date.getMonth();

	// If posting date is between 25-31, forecast month is next month
	// If posting date is between 1-5, forecast month is current month
	if (day >= 25) {
		// Next month
		month = month + 1;
		// Handle year rollover (December to January)
		if (month > 11) {
			month = 0;
			year = year + 1;
		}
	}

	// A backdated posting date lands on a month whose weeks have all elapsed, which would
	// leave every week column read-only. Roll forward to the first month that still has an
	// editable week -- the current month always does, since today's own week is open.
	const today = get_today_parts();
	if (month_index(year, month) < month_index(today.year, today.month)) {
		year = today.year;
		month = today.month;
	}

	return {
		year: year,
		month: month
	};
}

function auto_set_forecast_dates(frm) {
	if (!frm.doc.posting_date) return;

	let forecast_month = get_forecast_month(frm.doc.posting_date);

	// First day of forecast month
	let start_date = new Date(forecast_month.year, forecast_month.month, 1);

	// Last day of forecast month
	let end_date = new Date(forecast_month.year, forecast_month.month + 1, 0);

	// Auto-set forecast_start_date to first day of forecast month
	frm.set_value('forecast_start_date', frappe.datetime.obj_to_str(start_date));

	// Auto-set forecast_end_date to last day of forecast month
	frm.set_value('forecast_end_date', frappe.datetime.obj_to_str(end_date));
}

function setup_date_filters(frm) {
	if (!frm.doc.posting_date) return;

	let forecast_month = get_forecast_month(frm.doc.posting_date);

	// First day of forecast month
	let start_date = new Date(forecast_month.year, forecast_month.month, 1);

	// Last day of forecast month
	let end_date = new Date(forecast_month.year, forecast_month.month + 1, 0);

	// Set filters for forecast_start_date
	frm.set_query('forecast_start_date', function() {
		return {
			filters: {
				'date': ['>=', frappe.datetime.obj_to_str(start_date)],
				'date': ['<=', frappe.datetime.obj_to_str(end_date)]
			}
		};
	});

	// Set date picker options for forecast dates. The datepicker only exists once the
	// control has been rendered, so guard it -- refresh() runs this before apply_week_locks()
	// and a throw here would leave the week columns unlocked.
	['forecast_start_date', 'forecast_end_date'].forEach((fieldname) => {
		const field = frm.fields_dict[fieldname];
		if (field && field.datepicker) {
			field.datepicker.update({
				minDate: start_date,
				maxDate: end_date
			});
		}
	});
}

function validate_forecast_date(frm, fieldname) {
	if (!frm.doc.posting_date) {
		frappe.msgprint({
			title: __('Missing Posting Date'),
			indicator: 'orange',
			message: __('Please select Posting Date first')
		});
		frm.set_value(fieldname, '');
		return;
	}

	let forecast_month = get_forecast_month(frm.doc.posting_date);
	let forecast_date = frappe.datetime.str_to_obj(frm.doc[fieldname]);

	// Check if forecast date is in the correct month
	if (forecast_date.getFullYear() !== forecast_month.year ||
		forecast_date.getMonth() !== forecast_month.month) {

		let month_name = frappe.datetime.str_to_user(
			new Date(forecast_month.year, forecast_month.month, 1).toISOString().split('T')[0]
		).split(' ')[0];

		frappe.msgprint({
			title: __('Invalid Forecast Date'),
			indicator: 'red',
			message: __('Forecast dates must be within {0} {1}', [month_name, forecast_month.year])
		});
		frm.set_value(fieldname, '');
	}
}

function setup_item_customer_filters(frm) {
	if (!frm.doc.sales_person) return;

	// Fetch Sales Person's allowed items and customers
	frappe.call({
		method: 'frappe.client.get',
		args: {
			doctype: 'Sales Person',
			name: frm.doc.sales_person
		},
		callback: function(r) {
			if (r.message) {
				let sales_person_doc = r.message;

				// Get allowed item codes
				let allowed_items = [];
				if (sales_person_doc.custom_sales_person_wise_items) {
					allowed_items = sales_person_doc.custom_sales_person_wise_items
						.map(row => row.item_code)
						.filter(item => item);
				}

				// Get allowed customers
				let allowed_customers = [];
				if (sales_person_doc.custom_sales_person_wise_customers) {
					allowed_customers = sales_person_doc.custom_sales_person_wise_customers
						.map(row => row.customer)
						.filter(customer => customer);
				}

				console.log('Allowed Items:', allowed_items);
				console.log('Allowed Customers:', allowed_customers);

				// Set filter for customer in child table
				frm.set_query('customer', 'items', function() {
					if (allowed_customers.length > 0) {
						return {
							filters: [
								['Customer', 'name', 'in', allowed_customers]
							]
						};
					} else {
						// If no customers configured, show none
						return {
							filters: [
								['Customer', 'name', '=', '___no_customer___']
							]
						};
					}
				});

				// Refresh the child table fields
				frm.refresh_field('items');
			}
		}
	});
}

// A Sales Manager/System Manager may create a forecast for any Sales Person, so the
// field stays open and empty for them. Anyone else (a Sales Person logging in themselves)
// only ever forecasts on their own behalf, so their own name is filled in and locked.
function lock_sales_person_for_current_user(frm) {
	if (frappe.user_roles.includes('Sales Manager')) {
		return;
	}

	frappe.call({
		method: 'sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.get_current_user_sales_person',
		callback: function(r) {
			const own_sales_person = r.message;
			if (!own_sales_person) return;

			if (frm.is_new() && !frm.doc.sales_person) {
				frm.set_value('sales_person', own_sales_person);
			}

			if (frm.doc.sales_person === own_sales_person) {
				frm.set_df_property('sales_person', 'read_only', 1);
			}
		}
	});
}

function show_sales_person_info(frm) {
	// Clear all previous intro messages
	frm.set_intro();

	if (!frm.doc.sales_person) {
		frm.set_intro(__('Please select a Sales Person to configure forecast items'), 'blue');
		// Reset dashboard when no sales person
		frm.dashboard.reset();
		return;
	}

	// Show development note - only once
	frm.set_intro(
		__('<b>Important Notes:</b><br>') +
		__('• Posting Date must be between 25th-31st OR 1st-5th of the month<br>') +
		__('• Forecast dates are automatically set based on posting date<br>') +
		__('• Only items and customers assigned to the selected Sales Person will be available for selection'),
		'orange'
	);

	// Fetch Sales Person info for dashboard
	frappe.call({
		method: 'frappe.client.get',
		args: {
			doctype: 'Sales Person',
			name: frm.doc.sales_person
		},
		callback: function(r) {
			if (r.message) {
				let sales_person_doc = r.message;

				// Count assigned items
				let items_count = 0;
				if (sales_person_doc.custom_sales_person_wise_items) {
					items_count = sales_person_doc.custom_sales_person_wise_items.length;
				}

				// Count assigned customers
				let customers_count = 0;
				if (sales_person_doc.custom_sales_person_wise_customers) {
					customers_count = sales_person_doc.custom_sales_person_wise_customers.length;
				}

				// Create link to Sales Person
				let sales_person_link = `<a href="/app/sales-person/${encodeURIComponent(frm.doc.sales_person)}" target="_blank">${frm.doc.sales_person}</a>`;

				// Reset dashboard before adding new indicators
				frm.dashboard.reset();

				// Add dashboard indicators
				frm.dashboard.add_indicator(
					__('Sales Person: {0}', [sales_person_link]),
					'blue'
				);

				frm.dashboard.add_indicator(
					__('Assigned Items: {0}', [items_count]),
					items_count > 0 ? 'green' : 'red'
				);

				frm.dashboard.add_indicator(
					__('Assigned Customers: {0}', [customers_count]),
					customers_count > 0 ? 'green' : 'red'
				);
			}
		}
	});
}

// ---------------------------------------------------------------------------
// Channel Partner -> Secondary Customer dropdown
//
// When a row's Customer is a Channel Partner (it has secondary customers in its
// "Secondary Customer" table), the row's Secondary Customer Link field is enabled
// and its options are limited to that partner's secondary customers. The field is
// shown ONLY in the row edit popup (in_list_view = 0), not as a grid column, and is
// gated by depends_on: is_channel_partner.
// ---------------------------------------------------------------------------
const SECONDARY_CUSTOMERS_METHOD =
	"sales_forecast.sales_forecast.doctype.forecast_sales_person.forecast_sales_person.get_secondary_customers";

function setup_secondary_customer_query(frm) {
	frm.set_query("secondary_customer", "items", function (doc, cdt, cdn) {
		const row = locals[cdt][cdn];
		const list = (frm._sec_cust_cache && frm._sec_cust_cache[row.customer]) || [];
		// "__none__" guarantees an empty result when the customer isn't a channel partner.
		return { filters: { name: ["in", list.length ? list : ["__none__"]] } };
	});
}

function update_channel_partner_secondary(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	// A customer change invalidates any previous secondary selection.
	frappe.model.set_value(cdt, cdn, "secondary_customer", "");
	frappe.model.set_value(cdt, cdn, "is_channel_partner", 0);
	if (!row.customer) {
		return;
	}
	frappe.call({
		method: SECONDARY_CUSTOMERS_METHOD,
		args: { channel_partner: row.customer },
		callback(r) {
			const list = (r.message || []).map((d) => d.name);
			frm._sec_cust_cache = frm._sec_cust_cache || {};
			frm._sec_cust_cache[row.customer] = list;
			frappe.model.set_value(cdt, cdn, "is_channel_partner", list.length ? 1 : 0);
		},
	});
}

// On load, rebuild the dropdown cache + channel-partner flag for existing rows so the
// Secondary Customer field shows correctly without re-picking the customer.
function init_channel_partner_flags(frm) {
	frm._sec_cust_cache = frm._sec_cust_cache || {};
	const customers = [...new Set((frm.doc.items || []).map((d) => d.customer).filter(Boolean))];
	customers.forEach((cust) => {
		frappe.call({
			method: SECONDARY_CUSTOMERS_METHOD,
			args: { channel_partner: cust },
			callback(r) {
				const list = (r.message || []).map((d) => d.name);
				frm._sec_cust_cache[cust] = list;
				let changed = false;
				(frm.doc.items || []).forEach((d) => {
					if (d.customer === cust) {
						const flag = list.length ? 1 : 0;
						if (d.is_channel_partner !== flag) {
							d.is_channel_partner = flag;
							changed = true;
						}
					}
				});
				if (changed) frm.refresh_field("items");
			},
		});
	});
}
