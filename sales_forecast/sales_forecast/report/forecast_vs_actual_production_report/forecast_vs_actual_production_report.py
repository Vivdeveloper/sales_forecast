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
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 140
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 180
		},
		{
			"fieldname": "batch_size",
			"label": _("Batch Size"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "week_1_forecast",
			"label": _("Week 1 Forecast Qty"),
			"fieldtype": "Float",
			"width": 140
		},
		{
			"fieldname": "week_1_batches",
			"label": _("Week 1 Batches"),
			"fieldtype": "Int",
			"width": 120
		},
		{
			"fieldname": "week_1_wo_created",
			"label": _("Week 1 WO Created"),
			"fieldtype": "Int",
			"width": 130
		},
		{
			"fieldname": "week_1_wo_completed",
			"label": _("Week 1 WO Completed"),
			"fieldtype": "Int",
			"width": 150
		},
		{
			"fieldname": "week_2_forecast",
			"label": _("Week 2 Forecast Qty"),
			"fieldtype": "Float",
			"width": 140
		},
		{
			"fieldname": "week_2_batches",
			"label": _("Week 2 Batches"),
			"fieldtype": "Int",
			"width": 120
		},
		{
			"fieldname": "week_2_wo_created",
			"label": _("Week 2 WO Created"),
			"fieldtype": "Int",
			"width": 130
		},
		{
			"fieldname": "week_2_wo_completed",
			"label": _("Week 2 WO Completed"),
			"fieldtype": "Int",
			"width": 150
		},
		{
			"fieldname": "week_3_forecast",
			"label": _("Week 3 Forecast Qty"),
			"fieldtype": "Float",
			"width": 140
		},
		{
			"fieldname": "week_3_batches",
			"label": _("Week 3 Batches"),
			"fieldtype": "Int",
			"width": 120
		},
		{
			"fieldname": "week_3_wo_created",
			"label": _("Week 3 WO Created"),
			"fieldtype": "Int",
			"width": 130
		},
		{
			"fieldname": "week_3_wo_completed",
			"label": _("Week 3 WO Completed"),
			"fieldtype": "Int",
			"width": 150
		},
		{
			"fieldname": "week_4_forecast",
			"label": _("Week 4 Forecast Qty"),
			"fieldtype": "Float",
			"width": 140
		},
		{
			"fieldname": "week_4_batches",
			"label": _("Week 4 Batches"),
			"fieldtype": "Int",
			"width": 120
		},
		{
			"fieldname": "week_4_wo_created",
			"label": _("Week 4 WO Created"),
			"fieldtype": "Int",
			"width": 130
		},
		{
			"fieldname": "week_4_wo_completed",
			"label": _("Week 4 WO Completed"),
			"fieldtype": "Int",
			"width": 150
		},
		{
			"fieldname": "total_forecast_qty",
			"label": _("Total Forecast Qty"),
			"fieldtype": "Float",
			"width": 140
		},
		{
			"fieldname": "total_batches",
			"label": _("Total Batches"),
			"fieldtype": "Int",
			"width": 110
		},
		{
			"fieldname": "total_wo_created",
			"label": _("Total WO Created"),
			"fieldtype": "Int",
			"width": 130
		},
		{
			"fieldname": "total_wo_completed",
			"label": _("Total WO Completed"),
			"fieldtype": "Int",
			"width": 150
		},
		{
			"fieldname": "completion_percentage",
			"label": _("Completion %"),
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"fieldname": "status",
			"label": _("Status"),
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

	# Main query to get forecast data
	query = """
		SELECT
			fc.name as forecast_club,
			fc.date as forecast_date,
			CONCAT(DATE_FORMAT(fc.forecast_start_date, '%%d-%%b-%%Y'), ' to ',
			       DATE_FORMAT(fc.forecast_end_date, '%%d-%%b-%%Y')) as forecast_period,
			fci.item_code as item_code,
			fci.item_name as item_name,
			fci.batch_size as batch_size,
			fci.week_1 as week_1_forecast,
			fci.w1_batch as week_1_batches,
			fci.week_2 as week_2_forecast,
			fci.w2_batch as week_2_batches,
			fci.week_3 as week_3_forecast,
			fci.w3_batch as week_3_batches,
			fci.week_4 as week_4_forecast,
			fci.w4_batch as week_4_batches,
			fci.total_qty as total_forecast_qty,
			fci.total_batch_qty as total_batches,
			fc.status as status,
			fc.company as company
		FROM
			`tabForecast Club` fc
		INNER JOIN
			`tabForecast Club Item` fci ON fc.name = fci.parent
		WHERE
			fc.docstatus = 1
			{conditions}
		ORDER BY
			fc.date DESC, fc.name, fci.item_code
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	# Get Work Order counts for each item and week
	for row in data:
		# Week 1
		week_1_wo = get_work_order_counts(row['forecast_club'], row['item_code'], 'week_1')
		row['week_1_wo_created'] = week_1_wo['created']
		row['week_1_wo_completed'] = week_1_wo['completed']

		# Week 2
		week_2_wo = get_work_order_counts(row['forecast_club'], row['item_code'], 'week_2')
		row['week_2_wo_created'] = week_2_wo['created']
		row['week_2_wo_completed'] = week_2_wo['completed']

		# Week 3
		week_3_wo = get_work_order_counts(row['forecast_club'], row['item_code'], 'week_3')
		row['week_3_wo_created'] = week_3_wo['created']
		row['week_3_wo_completed'] = week_3_wo['completed']

		# Week 4
		week_4_wo = get_work_order_counts(row['forecast_club'], row['item_code'], 'week_4')
		row['week_4_wo_created'] = week_4_wo['created']
		row['week_4_wo_completed'] = week_4_wo['completed']

		# Calculate totals
		row['total_wo_created'] = (
			row['week_1_wo_created'] + row['week_2_wo_created'] +
			row['week_3_wo_created'] + row['week_4_wo_created']
		)
		row['total_wo_completed'] = (
			row['week_1_wo_completed'] + row['week_2_wo_completed'] +
			row['week_3_wo_completed'] + row['week_4_wo_completed']
		)

		# Calculate completion percentage
		if row['total_batches'] > 0:
			row['completion_percentage'] = (row['total_wo_completed'] / row['total_batches']) * 100
		else:
			row['completion_percentage'] = 0

	return data


def get_work_order_counts(forecast_club, item_code, week):
	"""Get Work Order counts for a specific item and week"""
	wo_data = frappe.db.sql("""
		SELECT
			COUNT(*) as created,
			SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed
		FROM
			`tabWork Order`
		WHERE
			custom_forecast_club = %s
			AND production_item = %s
			AND custom_weekly = %s
			AND docstatus != 2
	""", (forecast_club, item_code, week), as_dict=1)

	if wo_data:
		return {
			'created': wo_data[0].created or 0,
			'completed': wo_data[0].completed or 0
		}
	return {'created': 0, 'completed': 0}


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
		conditions.append("AND fci.item_code = %(item_code)s")

	return " ".join(conditions) if conditions else ""
