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
		{"fieldname": "forecast_club", "label": _("Forecast Club"), "fieldtype": "Link", "options": "Forecast Club", "width": 120},
		{"fieldname": "product_item", "label": _("Product Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "week_number", "label": _("Week Number"), "fieldtype": "Data", "width": 100},
		{"fieldname": "batch_size", "label": _("Batch Size"), "fieldtype": "Float", "width": 100},
		{"fieldname": "total_batches_planned", "label": _("Total Batches Planned"), "fieldtype": "Int", "width": 150},
		{"fieldname": "planned_qty", "label": _("Planned Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "wo_created_count", "label": _("Work Orders Created"), "fieldtype": "Int", "width": 150},
		{"fieldname": "wo_created_qty", "label": _("WO Created Qty"), "fieldtype": "Float", "width": 130},
		{"fieldname": "wo_completed_count", "label": _("Work Orders Completed"), "fieldtype": "Int", "width": 160},
		{"fieldname": "wo_in_progress_count", "label": _("Work Orders In Progress"), "fieldtype": "Int", "width": 170},
		{"fieldname": "remaining_batches", "label": _("Remaining Batches"), "fieldtype": "Int", "width": 140},
		{"fieldname": "completion_percentage", "label": _("Completion %"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	# Get all forecast club items with their weekly batches
	query = """
		SELECT
			fc.name as forecast_club,
			fci.item_code as product_item,
			fci.item_name as item_name,
			fci.batch_size as batch_size,
			fc.company as company,
			fci.name as forecast_club_item_name
		FROM
			`tabForecast Club` fc
		INNER JOIN
			`tabForecast Club Item` fci ON fc.name = fci.parent
		WHERE
			fc.docstatus = 1
			{conditions}
		ORDER BY
			fc.name, fci.item_code
	""".format(conditions=conditions)

	forecast_items = frappe.db.sql(query, filters, as_dict=1)

	data = []

	for item in forecast_items:
		# Process each week for this item
		for week_num in range(1, 5):
			week_field = f"week_{week_num}"
			batch_field = f"w{week_num}_batch"
			batch_qty_field = f"w{week_num}_batch_qty"

			# Get batch data for this week
			batch_data = frappe.db.get_value(
				"Forecast Club Item",
				item.forecast_club_item_name,
				[batch_field, batch_qty_field],
				as_dict=1
			)

			total_batches = batch_data.get(batch_field) or 0
			planned_qty = batch_data.get(batch_qty_field) or 0

			if total_batches == 0:
				continue  # Skip weeks with no batches planned

			# Get Work Order statistics
			wo_stats = get_work_order_stats(
				item.forecast_club,
				item.forecast_club_item_name,
				week_field
			)

			remaining_batches = total_batches - wo_stats['created_count']
			if remaining_batches < 0:
				remaining_batches = 0

			completion_pct = 0
			if total_batches > 0:
				completion_pct = (wo_stats['completed_count'] / total_batches) * 100

			data.append({
				"forecast_club": item.forecast_club,
				"product_item": item.product_item,
				"item_name": item.item_name,
				"week_number": f"Week {week_num}",
				"batch_size": item.batch_size,
				"total_batches_planned": total_batches,
				"planned_qty": planned_qty,
				"wo_created_count": wo_stats['created_count'],
				"wo_created_qty": wo_stats['created_qty'],
				"wo_completed_count": wo_stats['completed_count'],
				"wo_in_progress_count": wo_stats['in_progress_count'],
				"remaining_batches": remaining_batches,
				"completion_percentage": completion_pct,
				"company": item.company
			})

	return data


def get_work_order_stats(forecast_club, forecast_club_item, week_field):
	"""Get Work Order statistics for a specific week"""
	stats = frappe.db.sql("""
		SELECT
			COUNT(*) as created_count,
			SUM(qty) as created_qty,
			SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_count,
			SUM(CASE WHEN status IN ('Not Started', 'In Process') THEN 1 ELSE 0 END) as in_progress_count
		FROM
			`tabWork Order`
		WHERE
			custom_forecast_club = %s
			AND custom_forecast_club_item = %s
			AND custom_weekly = %s
			AND docstatus != 2
	""", (forecast_club, forecast_club_item, week_field), as_dict=1)

	if stats:
		return {
			'created_count': stats[0].created_count or 0,
			'created_qty': stats[0].created_qty or 0,
			'completed_count': stats[0].completed_count or 0,
			'in_progress_count': stats[0].in_progress_count or 0
		}

	return {'created_count': 0, 'created_qty': 0, 'completed_count': 0, 'in_progress_count': 0}


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
		conditions.append("AND fci.item_code = %(item_code)s")

	return " ".join(conditions) if conditions else ""
