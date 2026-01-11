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
		{
			"fieldname": "forecast_club",
			"label": _("Forecast Club"),
			"fieldtype": "Link",
			"options": "Forecast Club",
			"width": 120
		},
		{
			"fieldname": "forecast_date",
			"label": _("Forecast Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "forecast_period",
			"label": _("Forecast Period"),
			"fieldtype": "Data",
			"width": 180
		},
		{
			"fieldname": "club_item",
			"label": _("Club Item (Product)"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
		{
			"fieldname": "raw_material_item",
			"label": _("Raw Material Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 180
		},
		{
			"fieldname": "bom_qty",
			"label": _("BOM Qty Required"),
			"fieldtype": "Float",
			"width": 120
		},
		{
			"fieldname": "actual_qty",
			"label": _("Stock (Warehouse 1)"),
			"fieldtype": "Float",
			"width": 140
		},
		{
			"fieldname": "actual_qty_2",
			"label": _("Stock (Warehouse 2)"),
			"fieldtype": "Float",
			"width": 140
		},
		{
			"fieldname": "total_available",
			"label": _("Total Available Stock"),
			"fieldtype": "Float",
			"width": 150
		},
		{
			"fieldname": "qty_to_request",
			"label": _("Qty to Request"),
			"fieldtype": "Float",
			"width": 120
		},
		{
			"fieldname": "company_total_stock",
			"label": _("Company Total Stock"),
			"fieldtype": "Float",
			"width": 150
		},
		{
			"fieldname": "material_request",
			"label": _("Material Request"),
			"fieldtype": "Link",
			"options": "Material Request",
			"width": 140
		},
		{
			"fieldname": "mr_status",
			"label": _("MR Status"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "mr_qty",
			"label": _("MR Qty"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "status",
			"label": _("Forecast Status"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 150
		}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	query = """
		SELECT
			fc.name as forecast_club,
			fc.date as forecast_date,
			CONCAT(DATE_FORMAT(fc.forecast_start_date, '%%d-%%b-%%Y'), ' to ',
			       DATE_FORMAT(fc.forecast_end_date, '%%d-%%b-%%Y')) as forecast_period,
			fci.item_code as club_item,
			fcmi.item_code as raw_material_item,
			item.item_name as item_name,
			fcmi.bom_qty as bom_qty,
			fcmi.actual_qty as actual_qty,
			fcmi.actual_qty_2 as actual_qty_2,
			(COALESCE(fcmi.actual_qty, 0) + COALESCE(fcmi.actual_qty_2, 0)) as total_available,
			fcmi.qty as qty_to_request,
			fcmi.company_total_stock as company_total_stock,
			mr.name as material_request,
			mr.status as mr_status,
			mri.qty as mr_qty,
			fc.status as status,
			fc.company as company
		FROM
			`tabForecast Club` fc
		LEFT JOIN
			`tabForecast Club Item` fci ON fc.name = fci.parent
		LEFT JOIN
			`tabForecast Club Material Request Item` fcmi ON fc.name = fcmi.parent
		LEFT JOIN
			`tabItem` item ON item.name = fcmi.item_code
		LEFT JOIN
			`tabMaterial Request Item` mri ON mri.custom_forecast_club = fc.name
			AND mri.item_code = fcmi.item_code
		LEFT JOIN
			`tabMaterial Request` mr ON mr.name = mri.parent AND mr.docstatus != 2
		WHERE
			fc.docstatus = 1
			{conditions}
		ORDER BY
			fc.date DESC, fc.name, fcmi.item_code
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	return data


def get_conditions(filters):
	conditions = []

	if filters.get("company"):
		conditions.append("AND fc.company = %(company)s")

	if filters.get("from_date"):
		conditions.append("AND fc.date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("AND fc.date <= %(to_date)s")

	if filters.get("forecast_club"):
		conditions.append("AND fc.name = %(forecast_club)s")

	if filters.get("status"):
		conditions.append("AND fc.status = %(status)s")

	if filters.get("item_code"):
		conditions.append("AND fcmi.item_code = %(item_code)s")

	return " ".join(conditions) if conditions else ""
