# Copyright (c) 2026, sales_forecast contributors
# License: MIT

"""Lay out the "Packing Material Requirement" section of Forecast Club Item cleanly:
keep the forecast HTML table full-width, then put Total Batch Qty / Last Month Sales /
Current Stock WIP / FG Company Stock as a single 4-column row (removes the blank space).

The live layout is governed by a `field_order` Property Setter (from Customize Form), so we
add two Column Breaks and rewrite that Property Setter. Idempotent."""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DT = "Forecast Club Item"
# The 4 scalar fields that should sit side by side under the forecast table.
ROW_BLOCK = [
	"section_break_pkg",       # unlabeled section that holds the 4-field row
	"total_batch_qty",
	"column_break_item",
	"last_month_sales",
	"custom_cb_pmr_2",
	"current_stock",
	"custom_cb_pmr_3",
	"custom_company_stock",
]


def execute():
	# 1) two extra Column Breaks so the four fields render in four columns.
	create_custom_fields(
		{
			DT: [
				{
					"fieldname": "custom_cb_pmr_2",
					"fieldtype": "Column Break",
					"insert_after": "last_month_sales",
					"module": "Sales Forecast",
				},
				{
					"fieldname": "custom_cb_pmr_3",
					"fieldtype": "Column Break",
					"insert_after": "current_stock",
					"module": "Sales Forecast",
				},
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype=DT)

	# 2) rebuild the field order: forecast table (full width) THEN the 4-field row.
	meta = frappe.get_meta(DT)
	order = [f.fieldname for f in meta.fields]
	for cb in ("custom_cb_pmr_2", "custom_cb_pmr_3"):
		if cb not in order:
			order.append(cb)

	# pull the row block out of wherever it currently sits
	order = [f for f in order if f not in ROW_BLOCK]

	# re-insert it right after the forecast table (and its hidden data field)
	anchor = (
		"custom_packed_goods_weekly_data"
		if "custom_packed_goods_weekly_data" in order
		else "custom_packed_goods_weekly"
	)
	if anchor not in order:
		return  # unexpected structure — leave it alone
	idx = order.index(anchor) + 1
	new_order = order[:idx] + ROW_BLOCK + order[idx:]

	value = json.dumps(new_order)
	ps_name = frappe.db.get_value(
		"Property Setter",
		{"doc_type": DT, "property": "field_order", "doctype_or_field": "DocType"},
		"name",
	)
	if ps_name:
		frappe.db.set_value("Property Setter", ps_name, "value", value)
	else:
		frappe.make_property_setter(
			{
				"doctype": DT,
				"doctype_or_field": "DocType",
				"property": "field_order",
				"value": value,
				"property_type": "Data",
			}
		)
	frappe.clear_cache(doctype=DT)
