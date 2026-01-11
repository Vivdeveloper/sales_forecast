# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Link", "options": "Sales Person", "width": 150},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "forecast_period", "label": _("Forecast Period"), "fieldtype": "Data", "width": 180},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 150},
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "week_1_qty", "label": _("Week 1 Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "week_2_qty", "label": _("Week 2 Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "week_3_qty", "label": _("Week 3 Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "week_4_qty", "label": _("Week 4 Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "total_forecast_qty", "label": _("Total Forecast Qty"), "fieldtype": "Float", "width": 140},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	query = """
		SELECT
			fsp.sales_person as sales_person,
			fsp.posting_date as posting_date,
			CONCAT(DATE_FORMAT(fsp.forecast_start_date, '%%d-%%b-%%Y'), ' to ',
			       DATE_FORMAT(fsp.forecast_end_date, '%%d-%%b-%%Y')) as forecast_period,
			fspi.customer as customer,
			fspi.item_code as item_code,
			item.item_name as item_name,
			fspi.week_1 as week_1_qty,
			fspi.week_2 as week_2_qty,
			fspi.week_3 as week_3_qty,
			fspi.week_4 as week_4_qty,
			fspi.total_qty as total_forecast_qty,
			fsp.status as status,
			fsp.company as company
		FROM
			`tabForecast Sales Person` fsp
		INNER JOIN
			`tabForecast Sales Person Item` fspi ON fsp.name = fspi.parent
		LEFT JOIN
			`tabItem` item ON item.name = fspi.item_code
		WHERE
			fsp.docstatus = 1
			{conditions}
		ORDER BY
			fsp.posting_date DESC, fsp.sales_person, fspi.customer, fspi.item_code
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	return data


def get_conditions(filters):
	conditions = []

	if filters.get("company"):
		conditions.append("AND fsp.company = %(company)s")

	if filters.get("from_date"):
		conditions.append("AND fsp.posting_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("AND fsp.posting_date <= %(to_date)s")

	if filters.get("sales_person"):
		conditions.append("AND fsp.sales_person = %(sales_person)s")

	if filters.get("customer"):
		conditions.append("AND fspi.customer = %(customer)s")

	if filters.get("item_code"):
		conditions.append("AND fspi.item_code = %(item_code)s")

	if filters.get("status"):
		conditions.append("AND fsp.status = %(status)s")

	return " ".join(conditions) if conditions else ""
