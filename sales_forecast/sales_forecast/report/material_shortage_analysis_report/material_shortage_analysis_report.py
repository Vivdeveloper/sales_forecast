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
		{"fieldname": "raw_material_item", "label": _("Raw Material Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "required_qty", "label": _("Required Qty"), "fieldtype": "Float", "width": 120},
		{"fieldname": "available_stock_wh1", "label": _("Available Stock (WH1)"), "fieldtype": "Float", "width": 160},
		{"fieldname": "available_stock_wh2", "label": _("Available Stock (WH2)"), "fieldtype": "Float", "width": 160},
		{"fieldname": "total_available_stock", "label": _("Total Available Stock"), "fieldtype": "Float", "width": 160},
		{"fieldname": "shortage_qty", "label": _("Shortage Qty"), "fieldtype": "Float", "width": 120},
		{"fieldname": "forecast_clubs_affected", "label": _("Forecast Clubs Affected"), "fieldtype": "Data", "width": 180},
		{"fieldname": "impact_on_production", "label": _("Impact on Production"), "fieldtype": "Data", "width": 150},
		{"fieldname": "mr_status", "label": _("Material Request Status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "purchase_status", "label": _("Purchase Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	# Get all raw material requirements from Forecast Clubs
	query = """
		SELECT
			fcmi.item_code as raw_material_item,
			item.item_name as item_name,
			SUM(fcmi.bom_qty) as required_qty,
			SUM(COALESCE(fcmi.actual_qty, 0)) as available_stock_wh1,
			SUM(COALESCE(fcmi.actual_qty_2, 0)) as available_stock_wh2,
			SUM(COALESCE(fcmi.actual_qty, 0) + COALESCE(fcmi.actual_qty_2, 0)) as total_available_stock,
			SUM(fcmi.qty) as shortage_qty,
			fcmi.company_total_stock as company_total_stock,
			fc.company as company,
			GROUP_CONCAT(DISTINCT fc.name SEPARATOR ', ') as forecast_clubs_affected
		FROM
			`tabForecast Club` fc
		INNER JOIN
			`tabForecast Club Material Request Item` fcmi ON fc.name = fcmi.parent
		LEFT JOIN
			`tabItem` item ON item.name = fcmi.item_code
		WHERE
			fc.docstatus = 1
			AND fcmi.qty > 0
			{conditions}
		GROUP BY
			fcmi.item_code, fc.company
		HAVING
			shortage_qty > 0
		ORDER BY
			shortage_qty DESC
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	# Enrich data with Material Request and Purchase Order information
	for row in data:
		# Calculate impact on production
		affected_clubs = row['forecast_clubs_affected'].split(', ')
		row['impact_on_production'] = f"{len(affected_clubs)} Forecast Club(s)"

		# Get Material Request status for this item
		mr_info = frappe.db.sql("""
			SELECT
				mr.status as mr_status,
				SUM(mri.qty) as mr_qty
			FROM
				`tabMaterial Request` mr
			INNER JOIN
				`tabMaterial Request Item` mri ON mr.name = mri.parent
			WHERE
				mri.item_code = %s
				AND mr.docstatus != 2
				AND mri.custom_forecast_club IN ({clubs})
			GROUP BY
				mr.status
		""".format(clubs=', '.join(['%s'] * len(affected_clubs))),
		tuple([row['raw_material_item']] + affected_clubs), as_dict=1)

		if mr_info:
			mr_statuses = [f"{info.mr_status} ({info.mr_qty} qty)" for info in mr_info]
			row['mr_status'] = ", ".join(mr_statuses)
		else:
			row['mr_status'] = "Not Created"

		# Get Purchase Order status for this item
		po_info = frappe.db.sql("""
			SELECT
				po.status as po_status,
				SUM(poi.qty) as po_qty,
				SUM(poi.received_qty) as received_qty
			FROM
				`tabPurchase Order` po
			INNER JOIN
				`tabPurchase Order Item` poi ON po.name = poi.parent
			WHERE
				poi.item_code = %s
				AND po.docstatus != 2
			GROUP BY
				po.status
		""", (row['raw_material_item'],), as_dict=1)

		if po_info:
			po_statuses = []
			for info in po_info:
				if info.received_qty and info.received_qty > 0:
					po_statuses.append(f"{info.po_status} ({info.received_qty}/{info.po_qty} received)")
				else:
					po_statuses.append(f"{info.po_status} ({info.po_qty} qty)")
			row['purchase_status'] = ", ".join(po_statuses)
		else:
			row['purchase_status'] = "Not Ordered"

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

	if filters.get("item_code"):
		conditions.append("AND fcmi.item_code = %(item_code)s")

	return " ".join(conditions) if conditions else ""
