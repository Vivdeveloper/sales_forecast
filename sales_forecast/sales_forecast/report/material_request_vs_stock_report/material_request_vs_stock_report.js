// Copyright (c) 2026, Viv Choudhary and contributors
// For license information, please see license.txt

frappe.query_reports["Material Request vs Stock Report"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "forecast_club",
			"label": __("Forecast Club"),
			"fieldtype": "Link",
			"options": "Forecast Club"
		},
		{
			"fieldname": "status",
			"label": __("Forecast Status"),
			"fieldtype": "Select",
			"options": "\nForecast Planned\nMaterial Requested\nProduction Started\nCompleted"
		},
		{
			"fieldname": "item_code",
			"label": __("Raw Material Item"),
			"fieldtype": "Link",
			"options": "Item"
		}
	]
};
