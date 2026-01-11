# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def validate(doc, method):
	"""Validate Sales Person custom fields"""
	validate_duplicate_items(doc)
	validate_duplicate_customers(doc)


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
