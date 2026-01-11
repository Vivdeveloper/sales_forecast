# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 100},
		{"fieldname": "sales_person", "label": _("Sales Person"), "fieldtype": "Link", "options": "Sales Person", "width": 150},
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "forecasted_qty", "label": _("Forecasted Qty"), "fieldtype": "Float", "width": 130},
		{"fieldname": "actual_production_qty", "label": _("Actual Production Qty"), "fieldtype": "Float", "width": 160},
		{"fieldname": "actual_sales_qty", "label": _("Actual Sales Qty"), "fieldtype": "Float", "width": 140},
		{"fieldname": "accuracy_percentage", "label": _("Accuracy %"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Float", "width": 100},
		{"fieldname": "trend", "label": _("Trend"), "fieldtype": "Data", "width": 120},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 150}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	# Get forecast data from Sales Person
	forecast_query = """
		SELECT
			DATE_FORMAT(fsp.posting_date, '%%Y-%%m') as month,
			fsp.sales_person as sales_person,
			fspi.item_code as item_code,
			item.item_name as item_name,
			SUM(fspi.total_qty) as forecasted_qty,
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
		GROUP BY
			DATE_FORMAT(fsp.posting_date, '%%Y-%%m'), fsp.sales_person, fspi.item_code, fsp.company
		ORDER BY
			month DESC, sales_person, item_code
	""".format(conditions=conditions)

	data = frappe.db.sql(forecast_query, filters, as_dict=1)

	# Enrich data with actual production and sales quantities
	for row in data:
		# Get actual production quantity from Work Orders
		production_qty = get_actual_production_qty(
			row['item_code'],
			row['month'],
			row['company']
		)
		row['actual_production_qty'] = production_qty

		# Get actual sales quantity from Sales Invoices
		sales_qty = get_actual_sales_qty(
			row['item_code'],
			row['month'],
			row['company']
		)
		row['actual_sales_qty'] = sales_qty

		# Calculate accuracy based on actual sales (or production if sales not available)
		actual_qty = sales_qty if sales_qty > 0 else production_qty
		forecasted_qty = row['forecasted_qty'] or 0

		if forecasted_qty > 0 and actual_qty > 0:
			# Calculate accuracy percentage
			accuracy = (min(actual_qty, forecasted_qty) / max(actual_qty, forecasted_qty)) * 100
			row['accuracy_percentage'] = accuracy

			# Calculate variance
			row['variance'] = actual_qty - forecasted_qty

			# Determine trend
			if row['variance'] > 0:
				row['trend'] = "Over-forecasted"
			elif row['variance'] < 0:
				row['trend'] = "Under-forecasted"
			else:
				row['trend'] = "Accurate"
		else:
			row['accuracy_percentage'] = 0
			row['variance'] = 0
			if forecasted_qty > 0 and actual_qty == 0:
				row['trend'] = "No Production/Sales"
			else:
				row['trend'] = "N/A"

	return data


def get_actual_production_qty(item_code, month, company):
	"""Get actual production quantity from Work Orders"""
	year, month_num = month.split('-')

	production_data = frappe.db.sql("""
		SELECT
			SUM(produced_qty) as total_produced
		FROM
			`tabWork Order`
		WHERE
			production_item = %s
			AND company = %s
			AND status = 'Completed'
			AND YEAR(actual_end_date) = %s
			AND MONTH(actual_end_date) = %s
			AND docstatus = 1
	""", (item_code, company, year, month_num), as_dict=1)

	if production_data and production_data[0].total_produced:
		return production_data[0].total_produced
	return 0


def get_actual_sales_qty(item_code, month, company):
	"""Get actual sales quantity from Sales Invoices"""
	year, month_num = month.split('-')

	sales_data = frappe.db.sql("""
		SELECT
			SUM(sii.qty) as total_sales
		FROM
			`tabSales Invoice` si
		INNER JOIN
			`tabSales Invoice Item` sii ON si.name = sii.parent
		WHERE
			sii.item_code = %s
			AND si.company = %s
			AND YEAR(si.posting_date) = %s
			AND MONTH(si.posting_date) = %s
			AND si.docstatus = 1
	""", (item_code, company, year, month_num), as_dict=1)

	if sales_data and sales_data[0].total_sales:
		return sales_data[0].total_sales
	return 0


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

	if filters.get("item_code"):
		conditions.append("AND fspi.item_code = %(item_code)s")

	return " ".join(conditions) if conditions else ""
