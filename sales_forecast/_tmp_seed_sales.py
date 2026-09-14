import frappe
import traceback


def seed():
    """TEMP: seed FG00021 sales history in Aug 2026 (Stock Receipt -> SO -> DN -> SI) so the
    Forecast Sales Person Sales Qty/Amount columns can be tested, then re-save SF00102."""
    frappe.set_user("Administrator")
    from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

    comp = "Pratap Texchem Private Limited"
    uom = frappe.db.get_value("Item", "FG00021", "stock_uom")
    wh = "Plant 1 WIP FG - PTPL"
    cust = frappe.db.get_value("Forecast Sales Person Wise Item",
                               {"parent": "SF00102", "idx": 1}, "customer") or frappe.get_all(
        "Customer", pluck="name", limit=1)[0]
    out = []

    # 1) stock for FG00021 so the Delivery Notes can ship
    try:
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Receipt"
        se.company = comp
        se.posting_date = "2026-08-01"
        se.set_posting_time = 1
        se.append("items", {"item_code": "FG00021", "qty": 200, "t_warehouse": wh,
                            "basic_rate": 500, "uom": uom, "use_serial_batch_fields": 1})
        se.insert(ignore_permissions=True)
        se.submit()
        out.append("STOCK RECEIPT: %s (+200 @ %s)" % (se.name, wh))
    except Exception:
        out.append("STOCK RECEIPT FAILED: %s" % traceback.format_exc().splitlines()[-1])

    made = []
    for pdate, qty, rate in [("2026-08-05", 50, 900), ("2026-08-18", 20, 1250), ("2026-08-25", 50, 900)]:
        try:
            so = frappe.new_doc("Sales Order")
            so.customer = cust
            so.company = comp
            so.transaction_date = pdate
            so.delivery_date = pdate
            so.append("items", {"item_code": "FG00021", "qty": qty, "rate": rate, "uom": uom,
                                "delivery_date": pdate, "warehouse": wh})
            so.insert(ignore_permissions=True)
            so.submit()

            dn = make_delivery_note(so.name)
            dn.posting_date = pdate
            dn.set_posting_time = 1
            for d in dn.items:
                d.warehouse = wh
                d.use_serial_batch_fields = 1
            dn.insert(ignore_permissions=True)
            dn.submit()

            si = make_sales_invoice(dn.name)
            si.posting_date = pdate
            si.set_posting_time = 1
            si.due_date = pdate
            si.insert(ignore_permissions=True)
            si.submit()
            made.append((si.name, pdate, qty, si.base_net_total))
        except Exception:
            out.append("CHAIN FAILED %s: %s" % (pdate, traceback.format_exc().splitlines()[-1]))

    frappe.db.commit()
    out.append("SALES INVOICES: %s" % made)

    # 2) re-save SF00102 so validate re-pulls the sales columns
    try:
        fsp = frappe.get_doc("Forecast Sales Person", "SF00102")
        fsp.save(ignore_permissions=True)
        frappe.db.commit()
        r0 = fsp.items[0]
        out.append("SF00102 row1 sales qty: w1=%s w2=%s w3=%s w4=%s total=%s" % (
            r0.sales_qty_week_1, r0.sales_qty_week_2, r0.sales_qty_week_3, r0.sales_qty_week_4, r0.sales_total_qty))
        out.append("SF00102 row1 sales amt: w1=%s w2=%s w3=%s w4=%s total=%s" % (
            r0.sales_amount_week_1, r0.sales_amount_week_2, r0.sales_amount_week_3, r0.sales_amount_week_4, r0.total_sales_amount))
    except Exception:
        out.append("SF00102 RESAVE FAILED: %s" % traceback.format_exc().splitlines()[-1])

    print("\n".join("RESULT " + x for x in out))
