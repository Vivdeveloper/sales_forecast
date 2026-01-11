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
		{"fieldname": "week_number", "label": _("Week Number"), "fieldtype": "Data", "width": 100},
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "batch_size", "label": _("Batch Size"), "fieldtype": "Float", "width": 100},
		{"fieldname": "number_of_batches", "label": _("Number of Batches"), "fieldtype": "Int", "width": 140},
		{"fieldname": "total_qty", "label": _("Total Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "wo_created", "label": _("WO Created"), "fieldtype": "Int", "width": 110},
		{"fieldname": "wo_completed", "label": _("WO Completed"), "fieldtype": "Int", "width": 120},
		{"fieldname": "wo_in_progress", "label": _("WO In Progress"), "fieldtype": "Int", "width": 130},
		{"fieldname": "remaining_batches", "label": _("Remaining Batches"), "fieldtype": "Int", "width": 140},
		{"fieldname": "work_order_status", "label": _("Work Order Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 100},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	# Get all forecast club items with their weekly batches
	query = """
		SELECT
			fc.name as forecast_club,
			fci.item_code as item_code,
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

			# Get batch data for this week
			batch_count = frappe.db.get_value(
				"Forecast Club Item",
				item.forecast_club_item_name,
				batch_field
			) or 0

			if batch_count == 0:
				continue  # Skip weeks with no batches planned

			total_qty = batch_count * item.batch_size

			# Get Work Order statistics
			wo_stats = get_work_order_stats(
				item.forecast_club,
				item.forecast_club_item_name,
				week_field
			)

			remaining_batches = batch_count - wo_stats['created_count']
			if remaining_batches < 0:
				remaining_batches = 0

			# Determine priority based on remaining batches and week
			priority = get_priority(week_num, remaining_batches, batch_count)

			# Determine work order status
			if wo_stats['completed_count'] == batch_count:
				wo_status = "Completed"
			elif wo_stats['created_count'] == 0:
				wo_status = "Not Started"
			elif wo_stats['in_progress_count'] > 0:
				wo_status = "In Progress"
			else:
				wo_status = "Partially Complete"

			data.append({
				"forecast_club": item.forecast_club,
				"week_number": f"Week {week_num}",
				"item_code": item.item_code,
				"item_name": item.item_name,
				"batch_size": item.batch_size,
				"number_of_batches": batch_count,
				"total_qty": total_qty,
				"wo_created": wo_stats['created_count'],
				"wo_completed": wo_stats['completed_count'],
				"wo_in_progress": wo_stats['in_progress_count'],
				"remaining_batches": remaining_batches,
				"work_order_status": wo_status,
				"priority": priority,
				"company": item.company
			})

	return data


def get_work_order_stats(forecast_club, forecast_club_item, week_field):
	"""Get Work Order statistics for a specific week"""
	stats = frappe.db.sql("""
		SELECT
			COUNT(*) as created_count,
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
			'completed_count': stats[0].completed_count or 0,
			'in_progress_count': stats[0].in_progress_count or 0
		}

	return {'created_count': 0, 'completed_count': 0, 'in_progress_count': 0}


def get_priority(week_num, remaining_batches, total_batches):
	"""Calculate priority based on week number and remaining batches"""
	if remaining_batches == 0:
		return "Completed"

	completion_rate = ((total_batches - remaining_batches) / total_batches) * 100 if total_batches > 0 else 0

	# Week 1 is highest priority
	if week_num == 1:
		if completion_rate < 50:
			return "Critical"
		else:
			return "High"
	elif week_num == 2:
		if completion_rate < 30:
			return "High"
		else:
			return "Medium"
	elif week_num == 3:
		return "Medium"
	else:  # Week 4
		return "Low"


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

	if filters.get("week_number"):
		week_num = filters.get("week_number")
		# This filter will be applied in get_data function
		pass

	return " ".join(conditions) if conditions else ""
