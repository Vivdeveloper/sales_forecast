// Copyright (c) 2026, Viv Choudhary and contributors
// For license information, please see license.txt

frappe.ui.form.on("Forecast Sales Person", {
	refresh(frm) {
		// Set up date filters when form loads
		setup_date_filters(frm);
		setup_item_group_filter(frm);
		setup_item_customer_filters(frm);
		show_sales_person_info(frm);
		apply_week_locks(frm);
		lock_sales_person_for_current_user(frm);
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
	},

	forecast_start_date(frm) {
		if (frm.doc.forecast_start_date) {
			validate_forecast_date(frm, 'forecast_start_date');
		}
	},

	forecast_end_date(frm) {
		if (frm.doc.forecast_end_date) {
			validate_forecast_date(frm, 'forecast_end_date');
		}
	}
});

frappe.ui.form.on("Forecast Sales Person Wise Item", {
	items_add(frm) {
		setup_item_group_filter(frm);
		setup_item_customer_filters(frm);
		apply_week_locks(frm);
	}
});

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
