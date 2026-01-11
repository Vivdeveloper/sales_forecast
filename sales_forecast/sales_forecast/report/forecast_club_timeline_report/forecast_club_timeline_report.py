# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, getdate


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"fieldname": "forecast_club", "label": _("Forecast Club"), "fieldtype": "Link", "options": "Forecast Club", "width": 120},
		{"fieldname": "date_created", "label": _("Date Created"), "fieldtype": "Date", "width": 100},
		{"fieldname": "forecast_period", "label": _("Forecast Period"), "fieldtype": "Data", "width": 180},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "material_request_date", "label": _("Material Request Date"), "fieldtype": "Date", "width": 130},
		{"fieldname": "material_request_id", "label": _("Material Request ID"), "fieldtype": "Link", "options": "Material Request", "width": 150},
		{"fieldname": "mr_status", "label": _("MR Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "work_orders_count", "label": _("Work Orders Count"), "fieldtype": "Int", "width": 140},
		{"fieldname": "wo_completed_count", "label": _("WO Completed"), "fieldtype": "Int", "width": 130},
		{"fieldname": "wo_in_progress_count", "label": _("WO In Progress"), "fieldtype": "Int", "width": 130},
		{"fieldname": "days_in_status", "label": _("Days in Current Status"), "fieldtype": "Int", "width": 150},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	query = """
		SELECT
			fc.name as forecast_club,
			fc.date as date_created,
			CONCAT(DATE_FORMAT(fc.forecast_start_date, '%%d-%%b-%%Y'), ' to ',
			       DATE_FORMAT(fc.forecast_end_date, '%%d-%%b-%%Y')) as forecast_period,
			fc.status as status,
			fc.modified as last_modified,
			fc.company as company
		FROM
			`tabForecast Club` fc
		WHERE
			fc.docstatus = 1
			{conditions}
		ORDER BY
			fc.date DESC, fc.name
	""".format(conditions=conditions)

	data = frappe.db.sql(query, filters, as_dict=1)

	# Enrich data with Material Request and Work Order information
	for row in data:
		# Get Material Request information
		mr_data = frappe.db.sql("""
			SELECT
				mr.name as material_request_id,
				mr.transaction_date as material_request_date,
				mr.status as mr_status
			FROM
				`tabMaterial Request` mr
			INNER JOIN
				`tabMaterial Request Item` mri ON mr.name = mri.parent
			WHERE
				mri.custom_forecast_club = %s
				AND mr.docstatus != 2
			GROUP BY
				mr.name
			ORDER BY
				mr.transaction_date ASC
			LIMIT 1
		""", (row['forecast_club'],), as_dict=1)

		if mr_data:
			row['material_request_date'] = mr_data[0].material_request_date
			row['material_request_id'] = mr_data[0].material_request_id
			row['mr_status'] = mr_data[0].mr_status
		else:
			row['material_request_date'] = None
			row['material_request_id'] = None
			row['mr_status'] = None

		# Get Work Order statistics
		wo_stats = frappe.db.sql("""
			SELECT
				COUNT(*) as total_count,
				SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_count,
				SUM(CASE WHEN status IN ('Not Started', 'In Process') THEN 1 ELSE 0 END) as in_progress_count
			FROM
				`tabWork Order`
			WHERE
				custom_forecast_club = %s
				AND docstatus != 2
		""", (row['forecast_club'],), as_dict=1)

		if wo_stats:
			row['work_orders_count'] = wo_stats[0].total_count or 0
			row['wo_completed_count'] = wo_stats[0].completed_count or 0
			row['wo_in_progress_count'] = wo_stats[0].in_progress_count or 0
		else:
			row['work_orders_count'] = 0
			row['wo_completed_count'] = 0
			row['wo_in_progress_count'] = 0

		# Calculate days in current status
		today = getdate()
		last_modified = getdate(row['last_modified'])
		row['days_in_status'] = date_diff(today, last_modified)

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

	return " ".join(conditions) if conditions else ""
