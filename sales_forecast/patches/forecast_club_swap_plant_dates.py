# Copyright (c) 2026, sales_forecast contributors
# License: MIT

"""Swap the two pairs in the right column of the Forecast Club header: put Plant +
Forecast Type on top, and Forecast Start/End Date below them (requested reorder).

The live layout is governed by a `field_order` Property Setter (Customize Form), so we
rewrite that segment. Idempotent; no-op if the structure isn't as expected."""

import json

import frappe

DT = "Forecast Club"
# Right-column order we want (between column_break_wdxe and section_break_zgmv).
DESIRED = [
	"plant",
	"forecast_type",
	"special_reason",       # conditional (shows when Forecast Type = Special); stays by its type
	"forecast_start_date",
	"forecast_end_date",
	"amended_from",         # hidden/system; parked at the end
]


def execute():
	ps = frappe.db.get_value(
		"Property Setter",
		{"doc_type": DT, "property": "field_order", "doctype_or_field": "DocType"},
		["name", "value"],
		as_dict=True,
	)
	if not ps:
		return

	try:
		order = json.loads(ps.value)
	except (ValueError, TypeError):
		return

	if "column_break_wdxe" not in order or "section_break_zgmv" not in order:
		return

	start = order.index("column_break_wdxe") + 1
	end = order.index("section_break_zgmv")
	segment = order[start:end]

	# Reorder only the fields we know; keep any unexpected extras at the end (safety).
	known = [f for f in DESIRED if f in segment]
	extras = [f for f in segment if f not in DESIRED]
	new_segment = known + extras

	new_order = order[:start] + new_segment + order[end:]
	if new_order == order:
		return

	frappe.db.set_value("Property Setter", ps.name, "value", json.dumps(new_order))
	frappe.clear_cache(doctype=DT)
