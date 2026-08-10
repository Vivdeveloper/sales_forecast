"""Backfill Sales UOM on existing forecast item rows.

The new `sales_uom` column is populated via fetch_from on item selection, but
pre-existing rows (and already-submitted docs) never got it. This one-time patch
fills it from the item master (Item.stock_uom, which this bench labels "Sales UOM").
Idempotent: only touches rows where sales_uom is blank.
"""

import frappe


def execute():
	for child in ("Forecast Sales Person Wise Item", "Forecast Club Item"):
		if not frappe.db.has_column(child, "sales_uom"):
			continue
		frappe.db.sql(f"""
			UPDATE `tab{child}` t
			JOIN `tabItem` i ON i.name = t.item_code
			SET t.sales_uom = i.stock_uom
			WHERE (t.sales_uom IS NULL OR t.sales_uom = '')
			  AND t.item_code IS NOT NULL AND t.item_code != ''
		""")
	frappe.db.commit()
