# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def validate(doc, method):
	"""Validate Sales Person custom fields"""
	validate_duplicate_items(doc)
	validate_duplicate_customers(doc)
	validate_duplicate_monthly_targets(doc)


def validate_duplicate_monthly_targets(doc):
	"""Prevent the same Fiscal Year + Month appearing twice in Monthly Targets."""
	if not doc.get("custom_monthly_targets"):
		return

	seen = set()
	for row in doc.get("custom_monthly_targets"):
		if not row.month:
			continue
		key = (row.fiscal_year, row.month)
		if key in seen:
			frappe.throw(
				_("Row #{0}: {1} {2} is already added in Monthly Targets. Each month can only be added once per fiscal year.").format(
					row.idx, frappe.bold(row.month), frappe.bold(row.fiscal_year or "")
				)
			)
		seen.add(key)


def validate_duplicate_items(doc):
	"""Prevent duplicate item_code in custom_sales_person_wise_items"""
	if not doc.get("custom_sales_person_wise_items"):
		return

	item_codes = []
	for row in doc.get("custom_sales_person_wise_items"):
		if row.item_code:
			if row.item_code in item_codes:
				frappe.throw(
					_("Row #{0}: Duplicate Item Code {1} found in Sales Person Wise Items. Each item can only be added once.").format(
						row.idx, frappe.bold(row.item_code)
					)
				)
			item_codes.append(row.item_code)


def validate_duplicate_customers(doc):
	"""Prevent duplicate customer in custom_sales_person_wise_customers"""
	if not doc.get("custom_sales_person_wise_customers"):
		return

	customers = []
	for row in doc.get("custom_sales_person_wise_customers"):
		if row.customer:
			if row.customer in customers:
				frappe.throw(
					_("Row #{0}: Duplicate Customer {1} found in Sales Person Wise Customers. Each customer can only be added once.").format(
						row.idx, frappe.bold(row.customer)
					)
				)
			customers.append(row.customer)
