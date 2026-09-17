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
		self.set_monthly_target_totals()
		self.set_actual_qty()
		self.set_item_sales_uom()
		self.set_loose_material()
		self.set_last_month_sales()

	def set_loose_material(self):
		"""Loose Material Week N = Filling Capacity × Week N (per item row)."""
		from frappe.utils import flt

		for row in self.items or []:
			fc = flt(row.get("filling_capacity"))
			for n in (1, 2, 3, 4):
				row.set(f"loose_material_week_{n}", fc * flt(row.get(f"week_{n}")))

	def set_last_month_sales(self):
		"""Populate each row's week-wise Sales Qty and Sales Amount (without GST) from LAST
		MONTH's submitted Sales Invoices for that item (+customer). 'Last month' = the calendar
		month before the forecast start date."""
		from frappe.utils import flt

		ref = self.forecast_start_date or self.posting_date
		for row in self.items or []:
			if not row.item_code:
				continue
			data = get_last_month_sales(row.item_code, row.customer, ref, self.company)
			q, a = data["qty"], data["amount"]
			for n in (1, 2, 3, 4):
				row.set(f"sales_qty_week_{n}", flt(q.get(str(n))))
				row.set(f"sales_amount_week_{n}", flt(a.get(str(n))))
			row.sales_total_qty = flt(q.get("total"))
			row.total_sales_amount = flt(a.get("total"))

	def set_item_sales_uom(self):
		"""Fill each item's Sales UOM from the item master (this bench labels
		Item.stock_uom as 'Sales UOM'). Guarantees it on save even if the client-side
		fetch_from didn't fire (e.g. API/import)."""
		for row in self.items or []:
			if row.item_code:
				row.sales_uom = frappe.db.get_value("Item", row.item_code, "stock_uom")

	def set_monthly_target_totals(self):
		"""Store the Sales Person's monthly-target qty for the forecast period."""
		summary = get_monthly_target_summary(
			self.sales_person, self.forecast_start_date, self.forecast_end_date
		)
		self.monthly_target_qty = summary["target_qty"]

	def set_actual_qty(self):
		"""Actual Qty = sum of Week 1..Week 4 across all forecast items."""
		from frappe.utils import flt

		self.actual_qty = sum(
			flt(row.week_1) + flt(row.week_2) + flt(row.week_3) + flt(row.week_4)
			for row in (self.items or [])
		)

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
		"""Validate items for duplicates. Uniqueness is on (item_code, customer, packed_good) —
		the same item may repeat across rows for different Packed Goods (and/or customers)."""
		if not self.items:
			frappe.throw(_("Please add at least one item in the ForecastSalesPerson Items table"))

		seen = {}
		for idx, item in enumerate(self.items, start=1):
			# Skip duplicate checks when item_code is blank (item_code has no validation)
			if not item.item_code:
				continue

			key = (item.item_code, item.get("customer") or "", item.get("packed_goods") or "")
			if key in seen:
				parts = [_("Item Code '{0}'").format(item.item_code)]
				if item.get("customer"):
					parts.append(_("Customer '{0}'").format(item.customer))
				if item.get("packed_goods"):
					parts.append(_("Packed Goods '{0}'").format(item.packed_goods))
				frappe.throw(
					_("Row #{0}: Duplicate entry for {1}. Same combination exists in Row #{2}").format(
						idx, ", ".join(parts), seen[key]
					)
				)
			seen[key] = idx


@frappe.whitelist()
def get_current_user_sales_person():
	"""Return the Sales Person linked (via Sales Person.custom_user) to the logged-in user, if any."""
	return frappe.db.get_value("Sales Person", {"custom_user": frappe.session.user}, "name")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def packed_goods_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field query for a forecast item's "Packed Goods": returns the packed-goods Items
	whose "Finished Item" (Item.custom_finished_item) is the selected forecast item. Each
	option shows the packed-goods item code + name."""
	item_code = (filters or {}).get("item_code")
	if not item_code:
		return []

	like = "%%%s%%" % (txt or "")
	return frappe.db.sql(
		"""
		SELECT name, item_name FROM `tabItem`
		WHERE custom_finished_item = %(fi)s AND IFNULL(disabled, 0) = 0
		  AND (name LIKE %(txt)s OR item_name LIKE %(txt)s)
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
		""",
		{"fi": item_code, "txt": like, "start": start, "page_len": page_len},
	)


def _week_of_month(day):
	"""Week bucket within a month: 1 -> days 1-7, 2 -> 8-14, 3 -> 15-21, 4 -> 22+."""
	if day <= 7:
		return 1
	if day <= 14:
		return 2
	if day <= 21:
		return 3
	return 4


@frappe.whitelist()
def get_last_month_sales(item_code, customer=None, ref_date=None, company=None):
	"""Week-wise Sales Qty and Sales Amount (WITHOUT GST) for `item_code` (+optional customer)
	from LAST MONTH's submitted Sales Invoices. 'Last month' = the calendar month before
	`ref_date` (the forecast start date). Qty is in stock UOM; amount is base_net_amount
	(net of taxes/GST, company currency). Returns {"qty": {..,"total"}, "amount": {..,"total"}}."""
	from frappe.utils import getdate, nowdate, add_months, get_first_day, get_last_day, flt

	empty = {
		"qty": {"1": 0, "2": 0, "3": 0, "4": 0, "total": 0},
		"amount": {"1": 0, "2": 0, "3": 0, "4": 0, "total": 0},
	}
	if not item_code:
		return empty

	ref = getdate(ref_date) if ref_date else getdate(nowdate())
	last = add_months(ref, -1)
	start, end = get_first_day(last), get_last_day(last)

	conds = ["si.docstatus = 1", "sii.item_code = %(item)s", "si.posting_date BETWEEN %(start)s AND %(end)s"]
	params = {"item": item_code, "start": start, "end": end}
	if customer:
		conds.append("si.customer = %(customer)s")
		params["customer"] = customer
	if company:
		conds.append("si.company = %(company)s")
		params["company"] = company

	rows = frappe.db.sql(
		"""
		SELECT si.posting_date AS posting_date, sii.stock_qty AS qty, sii.base_net_amount AS amt
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {conds}
		""".format(conds=" AND ".join(conds)),
		params,
		as_dict=True,
	)

	qty = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
	amt = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
	for r in rows:
		wk = _week_of_month(getdate(r.posting_date).day)
		qty[wk] += flt(r.qty)
		amt[wk] += flt(r.amt)

	return {
		"qty": {"1": qty[1], "2": qty[2], "3": qty[3], "4": qty[4], "total": sum(qty.values())},
		"amount": {"1": amt[1], "2": amt[2], "3": amt[3], "4": amt[4], "total": sum(amt.values())},
	}


@frappe.whitelist()
def get_packing_filling_capacity(item_code, packed_goods):
	"""Filling Capacity of the chosen Packed Goods = that packed-goods Item's own Filling
	Capacity (Item.custom_filling_capacity, shown below its Description)."""
	if not packed_goods:
		return 0
	return frappe.db.get_value("Item", packed_goods, "custom_filling_capacity") or 0


@frappe.whitelist()
def get_standard_selling_price(item_code):
	"""Return the Standard Selling price for the Miscellaneous Customer flow. `item_code`
	is the PACKED GOOD item (its Item Price carries Rate Per Unit + Rate; the main item's
	price list does not). The "Standard Selling" price list is only the FILTER used to pick
	the right Item Price. Returns {"rate_per_unit": .., "rate": ..} (latest valid_from)."""
	from frappe.utils import flt

	empty = {"rate_per_unit": 0, "rate": 0}
	if not item_code:
		return empty

	def _latest(filters):
		rows = frappe.get_all(
			"Item Price",
			filters=filters,
			fields=["custom_rate_per_unit", "price_list_rate"],
			order_by="valid_from desc, modified desc",
			limit=1,
		)
		return rows[0] if rows else None

	# 1) Prefer the "Standard Selling" price list explicitly; else any selling price list.
	row = _latest({"item_code": item_code, "price_list": "Standard Selling", "selling": 1})
	if not row:
		row = _latest({"item_code": item_code, "selling": 1})

	if not row:
		return empty
	return {
		"rate_per_unit": flt(row.get("custom_rate_per_unit")),
		"rate": flt(row.get("price_list_rate")),
	}


MONTH_NAMES = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]


def _target_month_date(fiscal_year, month):
	"""Resolve a (Fiscal Year, Month name) monthly-target row to the 1st of that
	calendar month, using the Fiscal Year's own start/end dates so it works for
	any fiscal-year layout (Apr-Mar, Jan-Dec, etc.)."""
	from frappe.utils import getdate, nowdate
	import datetime

	if not month or month not in MONTH_NAMES:
		return None
	month_no = MONTH_NAMES.index(month) + 1

	fy = None
	if fiscal_year:
		fy = frappe.db.get_value(
			"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
		)
	if fy and fy.year_start_date:
		ys, ye = getdate(fy.year_start_date), getdate(fy.year_end_date)
		year = ys.year if month_no >= ys.month else ye.year
	else:
		year = getdate(nowdate()).year

	return datetime.date(year, month_no, 1)


@frappe.whitelist()
def get_monthly_target_summary(sales_person, start_date, end_date):
	"""Sum the Sales Person's Monthly Targets whose month overlaps the forecast
	period [start_date, end_date]. Returns {"target_qty": .., "target_amount": ..}."""
	from frappe.utils import getdate, get_last_day, flt

	empty = {"target_qty": 0.0, "target_amount": 0.0}
	if not (sales_person and start_date and end_date):
		return empty

	start, end = getdate(start_date), getdate(end_date)

	rows = frappe.get_all(
		"Sales Person Monthly Target",
		filters={"parent": sales_person, "parenttype": "Sales Person"},
		fields=["fiscal_year", "month", "target_amount", "target_qty"],
	)

	total_qty = total_amount = 0.0
	for r in rows:
		d = _target_month_date(r.fiscal_year, r.month)
		if not d:
			continue
		m_start = d
		m_end = getdate(get_last_day(d))
		# month overlaps the forecast window
		if m_start <= end and m_end >= start:
			total_qty += flt(r.target_qty)
			total_amount += flt(r.target_amount)

	return {"target_qty": total_qty, "target_amount": total_amount}
