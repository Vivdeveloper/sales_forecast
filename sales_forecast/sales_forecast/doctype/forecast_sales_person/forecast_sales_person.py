# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class ForecastSalesPerson(Document):
	def validate(self):
		self.validate_dates()
		self.validate_duplicate_date_range()
		self.validate_items()

	def before_insert(self):
		self.enforce_sales_person_for_current_user()

	def enforce_sales_person_for_current_user(self):
		"""A logged-in Sales Person (no System Manager/Sales Manager role) can only
		create forecasts against their own linked Sales Person record. The client
		script pre-fills and locks the field, but this is the server-side backstop
		in case the request bypasses the form (API, data import, etc.).
		"""
		if "System Manager" in frappe.get_roles() or "Sales Manager" in frappe.get_roles():
			return

		own_sales_person = get_current_user_sales_person()
		if own_sales_person and self.sales_person != own_sales_person:
			frappe.throw(_("You can only create a forecast for your own Sales Person record"))

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


	def validate_duplicate_date_range(self):
		"""Block another Forecast Sales Person for the same sales person + company whose
		forecast date range overlaps this one, so the same month cannot be forecasted
		twice for a sales person.
		"""
		from frappe.utils import format_date

		if not self.forecast_start_date or not self.forecast_end_date:
			return

		# "Special" forecasts are allowed to repeat the same sales person + company +
		# month (a Reason is captured instead). Only "Normal" forecasts are blocked.
		if self.forecast_type == "Special":
			# mandatory_depends_on only binds the form, so a Special forecast coming in
			# over the API could otherwise skip the duplicate check without a Reason.
			if not self.special_reason:
				frappe.throw(_("Reason is mandatory for a Special forecast"), title=_("Reason Required"))
			return

		existing = frappe.db.get_value(
			"Forecast Sales Person",
			{
				"sales_person": self.sales_person,
				"company": self.company,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name or "new-forecast-sales-person"],
				# Overlap: existing.start <= this.end AND existing.end >= this.start
				"forecast_start_date": ["<=", self.forecast_end_date],
				"forecast_end_date": [">=", self.forecast_start_date],
			},
			["name", "forecast_start_date", "forecast_end_date"],
			as_dict=True,
		)

		if existing:
			frappe.throw(
				_(
					"{0} already forecasts {1} for {2} ({3} to {4}). Set Forecast Type to <b>Special</b> with a Reason to forecast this period again."
				).format(
					frappe.bold(existing.name),
					frappe.bold(self.sales_person),
					frappe.bold(self.company),
					format_date(existing.forecast_start_date),
					format_date(existing.forecast_end_date),
				),
				title=_("Duplicate Forecast"),
			)

	def validate_items(self):
		"""Validate forecast_sales_person items for duplicates (no filter or required check on item_code)"""
		if not self.items:
			frappe.throw(_("Please add at least one item in the ForecastSalesPerson Items table"))

		seen_combinations = {}
		seen_items = {}

		for idx, item in enumerate(self.items, start=1):
			# Skip duplicate checks when item_code is blank (item_code has no validation)
			if not item.item_code:
				continue

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


@frappe.whitelist()
def get_current_user_sales_person():
	"""Return the Sales Person linked (via Sales Person.custom_user) to the logged-in user, if any."""
	return frappe.db.get_value("Sales Person", {"custom_user": frappe.session.user}, "name")
