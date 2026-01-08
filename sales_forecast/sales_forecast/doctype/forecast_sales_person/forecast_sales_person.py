# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class ForecastSalesPerson(Document):
	def validate(self):
		self.validate_dates()
		self.validate_items()

	def validate_dates(self):
		"""Validate forecast start and end dates"""
		from frappe.utils import getdate

		# Check if dates are provided
		if not self.forecast_start_date:
			frappe.throw(_("Forecast Start Date is mandatory"))

		if not self.forecast_end_date:
			frappe.throw(_("Forecast End Date is mandatory"))

		# Check if end date is before start date
		if getdate(self.forecast_end_date) < getdate(self.forecast_start_date):
			frappe.throw(_("Forecast End Date cannot be before Forecast Start Date"))


	def validate_items(self):
		"""Validate forecast_sales_person items for duplicates and blank entries"""
		if not self.items:
			frappe.throw(_("Please add at least one item in the ForecastSalesPerson Items table"))

		seen_combinations = {}
		seen_items = {}

		for idx, item in enumerate(self.items, start=1):
			# Check if item_code is blank
			if not item.item_code:
				frappe.throw(_("Row #{0}: Item Code cannot be blank").format(idx))

			# Check for duplicate item_code + customer combination
			if item.customer:
				combination_key = f"{item.item_code}||{item.customer}"
				if combination_key in seen_combinations:
					frappe.throw(
						_("Row #{0}: Duplicate entry found for Item Code '{1}' and Customer '{2}'. Same combination exists in Row #{3}").format(
							idx,
							item.item_code,
							item.customer,
							seen_combinations[combination_key]
						)
					)
				seen_combinations[combination_key] = idx
			else:
				# Check for duplicate item_code only (when customer is not provided)
				if item.item_code in seen_items:
					frappe.throw(
						_("Row #{0}: Duplicate Item Code '{1}' found. Same item exists in Row #{2}").format(
							idx,
							item.item_code,
							seen_items[item.item_code]
						)
					)
				seen_items[item.item_code] = idx
