# Copyright (c) 2026, Viv Choudhary and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


FG_WAREHOUSE_STOCK_FIELDS = {
	"custom_plant_1_fg_loose_qty": "Plant 1 FG - PTPL",
	"custom_plant_2_fg_loose_qty": "Plant 2 FG - PTPL",
	"custom_mainstore_fg": "Main Store FG - PTPL",
}

# Current Stock WIP: only these two WIP FG warehouses count, not all warehouses.
CURRENT_STOCK_WAREHOUSES = ["Plant 1 WIP FG - PTPL", "Plant 2 WIP FG - PTPL"]

# FG Company Stock's loose-stock component: only these warehouses count, not all warehouses/companies.
FG_COMPANY_STOCK_WAREHOUSES = [
	"Plant 1 WIP FG - PTPL",
	"Plant 2 WIP FG - PTPL",
	"Main Store FG - PTPL",
	"FG Pune Warehouse  - PTPL",
]

# Plant selection maps to the item's Manufacturing Location (Item.custom_manufacturing_location).
# Only items whose manufacturing location matches the selected plant's warehouse belong to that plant.
PLANT_WAREHOUSE = {
	"Plant 1": "Plant 1 FG - PTPL",
	"Plant 2": "Plant 2 FG - PTPL",
}


class ForecastClub(Document):
	def validate(self):
		self.validate_items()
		self.check_duplicate_items()
		self.validate_plant_items()
		self.validate_duplicate_date_range()

	def on_submit(self):
		"""Set initial status on submit"""
		self.db_set("status", "Forecast Planned")

	def before_save(self):
		"""Calculate totals for each item and set custom_company_stock, custom_item_packaging_material"""
		for item in self.items:
			if flt(item.batch_capacity_1):
				item.w1_batch_qty = (item.w1_batch or 0) * flt(item.batch_capacity_1)
			if flt(item.batch_capacity_2):
				item.w2_batch_qty = (item.w2_batch or 0) * flt(item.batch_capacity_2)
			if flt(item.batch_capacity_3):
				item.w3_batch_qty = (item.w3_batch or 0) * flt(item.batch_capacity_3)
			if flt(item.batch_capacity_4):
				item.w4_batch_qty = (item.w4_batch or 0) * flt(item.batch_capacity_4)

			# Calculate total_batch_qty as sum of all weekly batches
			item.total_batch_qty = (
				(item.w1_batch or 0) +
				(item.w2_batch or 0) +
				(item.w3_batch or 0) +
				(item.w4_batch or 0)
			)

			# Calculate total_qty as sum of all weekly batch quantities
			item.total_qty = (
				(item.w1_batch_qty or 0) +
				(item.w2_batch_qty or 0) +
				(item.w3_batch_qty or 0) +
				(item.w4_batch_qty or 0)
			)

			# Forecast Quantity: total sales-forecast demand (sum of weekly forecast qtys)
			if hasattr(item, "forecast_quantity"):
				item.forecast_quantity = (
					flt(item.week_1) + flt(item.week_2) + flt(item.week_3) + flt(item.week_4)
				)

			# Planned Quantity: total planned production qty (same as total_qty)
			if hasattr(item, "planned_quantity"):
				item.planned_quantity = flt(item.total_qty)

			# Current Stock WIP: item's stock in Plant 1 WIP FG + Plant 2 WIP FG warehouses only
			if item.item_code and hasattr(item, "current_stock"):
				item.current_stock = self._get_item_stock_in_warehouses(item.item_code, CURRENT_STOCK_WAREHOUSES)

			# Last Month Sales: qty sold via submitted Sales Invoices in the previous calendar month
			if item.item_code and hasattr(item, "last_month_sales"):
				item.last_month_sales = self._get_last_month_sales(item.item_code)

			# Set custom_company_stock: FG loose stock in Plant 1 WIP FG, Plant 2 WIP FG,
			# Main Store FG, FG Pune Warehouse + packing material loose qty
			if item.item_code and hasattr(item, "custom_company_stock"):
				item.custom_company_stock = (
					self._get_item_stock_in_warehouses(item.item_code, FG_COMPANY_STOCK_WAREHOUSES)
					+ self._get_total_packing_loose_qty(item.item_code)
				)

			# Set warehouse-wise FG stock fields (Plant 1 FG, Plant 2 FG, Mainstore FG)
			if item.item_code:
				for fieldname, warehouse in FG_WAREHOUSE_STOCK_FIELDS.items():
					if hasattr(item, fieldname):
						item.set(fieldname, self._get_item_stock_in_warehouse(item.item_code, warehouse))

				# Mainstore FG = Main Store FG warehouse stock + total loose qty of all packing materials
				if hasattr(item, "custom_mainstore_fg"):
					item.custom_mainstore_fg = flt(item.custom_mainstore_fg) + self._get_total_packing_loose_qty(item.item_code, company=self.company)

			# Set custom_item_packaging_material / custom__item_packaging_material: packaging materials with stock in company (item - stock)
			packaging_value = self._get_item_packaging_materials(item.item_code, company=self.company) if item.item_code else ""
			if item.item_code:
				if hasattr(item, "custom_item_packaging_material"):
					item.custom_item_packaging_material = packaging_value
				if hasattr(item, "custom__item_packaging_material"):
					item.custom__item_packaging_material = packaging_value

	def _get_item_stock_in_all_companies(self, item_code):
		"""Return total stock for item across all companies (sum of actual_qty in all warehouses)."""
		result = frappe.db.sql("""
			SELECT COALESCE(SUM(b.actual_qty), 0)
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON b.warehouse = w.name
			WHERE b.item_code = %s
		""", (item_code,))
		return flt(result[0][0]) if result else 0

	def _get_item_stock_in_company(self, item_code, company):
		"""Return total stock for item in the given company (sum of actual_qty in company warehouses)."""
		if not company:
			return 0
		result = frappe.db.sql("""
			SELECT COALESCE(SUM(b.actual_qty), 0)
			FROM `tabBin` b
			INNER JOIN `tabWarehouse` w ON b.warehouse = w.name
			WHERE b.item_code = %s AND w.company = %s
		""", (item_code, company))
		return flt(result[0][0]) if result else 0

	def _get_item_sales_qty_last_month(self, item_code):
		"""Qty of a single item sold via submitted Sales Invoices in the previous
		calendar month (relative to today) for this document's company."""
		from frappe.utils import add_months, get_first_day, get_last_day, today

		if not item_code:
			return 0

		prev_month_ref = add_months(today(), -1)
		first_day = get_first_day(prev_month_ref)
		last_day = get_last_day(prev_month_ref)

		result = frappe.db.sql("""
			SELECT COALESCE(SUM(sii.qty), 0)
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
			WHERE sii.item_code = %s
			  AND si.docstatus = 1
			  AND si.company = %s
			  AND si.posting_date BETWEEN %s AND %s
		""", (item_code, self.company, first_day, last_day))
		return flt(result[0][0]) if result else 0

	def _get_last_month_sales(self, item_code):
		"""Last month sales in loose (base) units. Sales happen on the FG's packing
		materials (the sellable SKUs), so convert each packing material's sold qty into
		loose units the same way loose stock is computed: Filling Capacity * sold qty.

		e.g. LUBECOGREEN210 sold 2 units last month * Filling Capacity 210 = 420 loose.
		"""
		child_doctype, item_field = self._get_packing_material_details_config()
		if not item_code or not child_doctype or not item_field or not frappe.db.table_exists(child_doctype):
			return 0
		try:
			packing_items = frappe.get_all(
				child_doctype,
				filters={"parent": item_code, "parenttype": "Item"},
				fields=[item_field],
				pluck=item_field,
			)
		except Exception:
			return 0

		total = 0
		for pkg_item in packing_items:
			if not pkg_item:
				continue
			sold_qty = self._get_item_sales_qty_last_month(pkg_item)
			filling_capacity = flt(frappe.db.get_value("Item", pkg_item, "custom_filling_capacity"))
			total += filling_capacity * sold_qty
		return total

	def _get_item_stock_in_warehouse(self, item_code, warehouse):
		"""Return actual_qty for item in a specific warehouse."""
		if not item_code or not warehouse:
			return 0
		qty = frappe.db.get_value(
			"Bin",
			{"item_code": item_code, "warehouse": warehouse},
			"actual_qty",
		)
		return flt(qty)

	def _get_item_stock_in_warehouses(self, item_code, warehouses):
		"""Return total actual_qty for item summed across a specific list of warehouses."""
		if not item_code or not warehouses:
			return 0
		result = frappe.db.sql("""
			SELECT COALESCE(SUM(actual_qty), 0)
			FROM `tabBin`
			WHERE item_code = %s AND warehouse IN %s
		""", (item_code, tuple(warehouses)))
		return flt(result[0][0]) if result else 0

	def _get_total_packing_loose_qty(self, item_code, company=None):
		"""Sum of loose qty (Filling Capacity * stock) across all packing materials of the item.
		If company is given, use that company's stock; otherwise use stock across all companies."""
		child_doctype, item_field = self._get_packing_material_details_config()
		if not item_code or not child_doctype or not item_field or not frappe.db.table_exists(child_doctype):
			return 0
		try:
			rows = frappe.get_all(
				child_doctype,
				filters={"parent": item_code, "parenttype": "Item"},
				fields=[item_field],
				pluck=item_field,
			)
		except Exception:
			return 0
		total = 0
		for pkg_item in rows:
			if not pkg_item:
				continue
			if company:
				stock = self._get_item_stock_in_company(pkg_item, company)
			else:
				stock = self._get_item_stock_in_all_companies(pkg_item)
			filling_capacity = flt(frappe.db.get_value("Item", pkg_item, "custom_filling_capacity"))
			total += filling_capacity * stock
		return total

	def _get_item_packaging_materials(self, item_code, company=None):
		"""Return string: for each packaging material from Item's 'Packing Material Details',
		show both the warehouse stock and the loose qty. Loose qty = packing item's Filling
		Capacity (from Item master) * its available qty (company stock).
		Format: 'ITEM-A - 2.0 (Loose: 20.0), ITEM-B - 1.0 (Loose: 210.0)'.
		"""
		child_doctype, item_field = self._get_packing_material_details_config()
		if not child_doctype or not item_field or not frappe.db.table_exists(child_doctype):
			return ""
		try:
			rows = frappe.get_all(
				child_doctype,
				filters={"parent": item_code, "parenttype": "Item"},
				fields=[item_field],
				pluck=item_field,
			)
			items_list = [x for x in rows if x]
			if not items_list:
				return ""
			if company:
				parts = []
				for pkg_item in items_list:
					stock = self._get_item_stock_in_company(pkg_item, company)
					filling_capacity = flt(frappe.db.get_value("Item", pkg_item, "custom_filling_capacity"))
					loose_qty = filling_capacity * stock
					parts.append(f"{pkg_item} - {stock} (Loose: {loose_qty})")
				return ", ".join(parts)
			return ", ".join(items_list)
		except Exception:
			return ""

	def _get_packing_material_details_config(self):
		"""Resolve child doctype and 'item' field for Item's 'Packing Material Details' table."""
		meta = frappe.get_meta("Item")
		for df in meta.get_table_fields():
			if not df.label or "Packing Material Details" not in df.label:
				continue
			child_doctype = df.options
			if not child_doctype or not frappe.db.table_exists(child_doctype):
				continue
			child_meta = frappe.get_meta(child_doctype)
			# Prefer field "item", else "item_code"
			for f in child_meta.fields:
				if f.fieldname in ("item", "item_code") and f.fieldtype == "Link" and f.options == "Item":
					return (child_doctype, f.fieldname)
		return (None, None)

	@staticmethod
	@frappe.whitelist()
	def get_item_stock_and_packaging(item_code, company=None):
		"""Return custom_company_stock and packaging list (item - stock in company) for an item (for client-side use)."""
		if not item_code:
			return {
				"custom_company_stock": 0,
				"custom_item_packaging_material": "",
				"current_stock": 0,
				"last_month_sales": 0,
			}
		doc = frappe.new_doc("Forecast Club")
		# _get_last_month_sales reads self.company, so the throwaway doc has to carry it.
		doc.company = company
		stock = doc._get_item_stock_in_warehouses(item_code, FG_COMPANY_STOCK_WAREHOUSES) + doc._get_total_packing_loose_qty(item_code)
		packaging = doc._get_item_packaging_materials(item_code, company=company)
		result = {
			"custom_company_stock": stock,
			"custom_item_packaging_material": packaging,
			# Same helpers before_save uses, so the pre-save preview matches what gets stored.
			"current_stock": doc._get_item_stock_in_warehouses(item_code, CURRENT_STOCK_WAREHOUSES),
			"last_month_sales": doc._get_last_month_sales(item_code),
		}
		for fieldname, warehouse in FG_WAREHOUSE_STOCK_FIELDS.items():
			result[fieldname] = doc._get_item_stock_in_warehouse(item_code, warehouse)
		# Mainstore FG = Main Store FG warehouse stock + total loose qty of all packing materials
		result["custom_mainstore_fg"] = flt(result.get("custom_mainstore_fg")) + doc._get_total_packing_loose_qty(item_code, company=company)
		return result

	def check_duplicate_items(self):
		"""Check for duplicate items in the items table"""
		from frappe import _

		# Skip validation if no items
		if not self.items:
			return

		# Dictionary to track item codes with their row numbers
		item_codes = {}

		for idx, item in enumerate(self.items, start=1):
			if not item.item_code:
				continue

			# Check if item_code already exists
			if item.item_code in item_codes:
				frappe.throw(
					_("Row #{0}: Duplicate item {1}. This item already exists in Row #{2}").format(
						idx, frappe.bold(item.item_code), item_codes[item.item_code]
					)
				)

			# Store item_code with its row number
			item_codes[item.item_code] = idx

	def validate_plant_items(self):
		"""Every item must belong to the selected Plant.

		An item belongs to a plant when its Manufacturing Location
		(Item.custom_manufacturing_location) is that plant's FG warehouse.
		Two plants are supported: Plant 1 -> "Plant 1 FG - PTPL", Plant 2 -> "Plant 2 FG - PTPL".
		"""
		from frappe import _

		if not self.plant or not self.items:
			return

		plant_warehouse = PLANT_WAREHOUSE.get(self.plant)
		if not plant_warehouse:
			return

		for idx, item in enumerate(self.items, start=1):
			if not item.item_code:
				continue

			manufacturing_location = frappe.db.get_value(
				"Item", item.item_code, "custom_manufacturing_location"
			)

			if manufacturing_location != plant_warehouse:
				frappe.throw(
					_(
						"Row #{0}: Item {1} does not belong to {2}. Its Manufacturing Location is {3}, "
						"but {2} expects {4}."
					).format(
						idx,
						frappe.bold(item.item_code),
						frappe.bold(self.plant),
						frappe.bold(manufacturing_location or _("not set")),
						frappe.bold(plant_warehouse),
					)
				)

	def validate_duplicate_date_range(self):
		"""Block another Forecast Club for the same company + plant whose forecast date
		range overlaps this one, so the same month cannot be forecasted twice for a plant.
		"""
		from frappe import _
		from frappe.utils import getdate

		if not self.forecast_start_date or not self.forecast_end_date:
			return

		if getdate(self.forecast_end_date) < getdate(self.forecast_start_date):
			frappe.throw(_("Forecast End Date cannot be before Forecast Start Date"))

		# "Special" forecasts are allowed to repeat the same company + plant + month
		# (a Reason is captured instead). Only "Normal" forecasts are blocked.
		if self.forecast_type == "Special":
			return

		filters = {
			"company": self.company,
			"docstatus": ["!=", 2],
			"name": ["!=", self.name or "new-forecast-club"],
			# Overlap: existing.start <= this.end AND existing.end >= this.start
			"forecast_start_date": ["<=", self.forecast_end_date],
			"forecast_end_date": [">=", self.forecast_start_date],
		}
		if self.plant:
			filters["plant"] = self.plant

		existing = frappe.db.get_value(
			"Forecast Club",
			filters,
			["name", "forecast_start_date", "forecast_end_date"],
			as_dict=True,
		)

		if existing:
			frappe.throw(
				_(
					"A Forecast Club ({0}) already exists for {1}{2} covering {3} to {4}, which overlaps "
					"the selected dates. You cannot create another forecast for the same period."
				).format(
					frappe.bold(existing.name),
					frappe.bold(self.company),
					_(" / {0}").format(self.plant) if self.plant else "",
					frappe.bold(existing.forecast_start_date),
					frappe.bold(existing.forecast_end_date),
				)
			)

	def validate_items(self):
		"""Validate items before save"""
		from frappe import _

		# Skip validation if no items
		if not self.items:
			return

		for idx, item in enumerate(self.items, start=1):
			# BOM must be connected to this row's item_code (BOM.item = item_code)
			if item.item_code and item.bom:
				bom_item = frappe.db.get_value("BOM", item.bom, "item")
				if bom_item != item.item_code:
					frappe.throw(
						_("Row #{0}: BOM {1} is not for item {2}. Please select a BOM where Item = {2}.").format(
							idx, item.bom, item.item_code
						)
					)

			# (No batch-size validation here: weekly batch sizes come from the blender
			# capacity and may legitimately be unset at save time.)

	@frappe.whitelist()
	def fetch_material_request_items(self):
		"""Fetch raw materials from BOM based on total_qty for each item"""
		if not self.items:
			return {"message": "No items found. Please fetch forecasts first.", "status": "error"}

		# Clear existing material request items
		self.material_request_items = []

		# Dictionary to aggregate raw materials by item_code
		materials_dict = {}

		items_without_bom = []
		for item in self.items:
			if not item.item_code:
				continue

			if not item.bom:
				items_without_bom.append(item.item_code)
				continue

			if not item.total_qty:
				continue

			# BOMs are built for `bom.quantity` units of the finished good (often > 1,
			# e.g. 113.83), so each BOM Item qty must be scaled down to a per-unit rate
			# before multiplying by total_qty. This mirrors ERPNext's get_bom_items_as_dict
			# (bom_item.qty / bom.quantity), which is what the Work Order uses — without it
			# the required qty here comes out bom.quantity times too high.
			bom_quantity = flt(frappe.db.get_value("BOM", item.bom, "quantity")) or 1

			# Get BOM items (raw materials)
			bom_items = frappe.db.get_all(
				"BOM Item",
				filters={"parent": item.bom},
				fields=["item_code", "item_name", "qty", "uom", "stock_uom"]
			)

			for bom_item in bom_items:
				key = bom_item.item_code

				# Required quantity: per-unit BOM qty * total_qty
				required_bom_qty = (bom_item.qty / bom_quantity) * item.total_qty

				if key not in materials_dict:
					materials_dict[key] = {
						"item_code": bom_item.item_code,
						"item_name": bom_item.item_name,
						"bom_qty": 0,
						"uom": bom_item.uom or bom_item.stock_uom
					}

				# Aggregate bom_qty
				materials_dict[key]["bom_qty"] += required_bom_qty

		# Add aggregated materials to material_request_items child table
		for material_data in materials_dict.values():
			item_code = material_data["item_code"]

			# Get actual_qty from set_warehouse
			actual_qty = 0
			if self.set_warehouse:
				actual_qty = frappe.db.get_value(
					"Bin",
					{"item_code": item_code, "warehouse": self.set_warehouse},
					"actual_qty"
				) or 0

			# Get actual_qty_2 from set_warehouse_2
			actual_qty_2 = 0
			if self.set_warehouse_2:
				actual_qty_2 = frappe.db.get_value(
					"Bin",
					{"item_code": item_code, "warehouse": self.set_warehouse_2},
					"actual_qty"
				) or 0

			# Get company_total_stock (sum of all warehouses in the company)
			company_total_stock = 0
			if self.company:
				company_total_stock = frappe.db.sql("""
					SELECT SUM(b.actual_qty)
					FROM `tabBin` b
					INNER JOIN `tabWarehouse` w ON b.warehouse = w.name
					WHERE b.item_code = %s AND w.company = %s
				""", (item_code, self.company))[0][0] or 0

			# Calculate qty based on ignore_available_stock checkbox
			bom_qty = material_data["bom_qty"]

			if self.ignore_available_stock:
				# If ignore_available_stock is checked, qty = bom_qty
				qty_needed = bom_qty
			else:
				# Otherwise, qty = bom_qty - (actual_qty + actual_qty_2)
				# Treat negative stock values as 0
				actual_qty_positive = max(0, actual_qty)
				actual_qty_2_positive = max(0, actual_qty_2)
				total_available_stock = actual_qty_positive + actual_qty_2_positive
				qty_needed = bom_qty - total_available_stock
				# Ensure qty is not negative
				if qty_needed < 0:
					qty_needed = 0

			self.append("material_request_items", {
				"item_code": material_data["item_code"],
				"item_name": material_data["item_name"],
				"bom_qty": bom_qty,
				"qty": qty_needed,
				"uom": material_data["uom"],
				"actual_qty": actual_qty,
				"actual_qty_2": actual_qty_2,
				"company_total_stock": company_total_stock
			})

		# Return result with message
		result = {
			"status": "success",
			"message": f"Fetched {len(materials_dict)} raw materials from BOMs"
		}

		if items_without_bom:
			result["warning"] = f"No BOM found for items: {', '.join(items_without_bom)}"

		return result

	@frappe.whitelist()
	def fetch_sales_forecasts(self):
		"""Fetch and aggregate sales forecasts from Forecast Sales Person based on date range"""
		if not self.forecast_start_date or not self.forecast_end_date:
			frappe.msgprint("Please set Forecast Start Date and Forecast End Date")
			return

		if not self.company:
			frappe.msgprint("Please set Company")
			return

		# Clear existing items
		self.items = []

		# Get all submitted Forecast Sales Person documents matching the date range
		forecast_docs = frappe.db.get_all(
			"Forecast Sales Person",
			filters={
				"forecast_start_date": self.forecast_start_date,
				"forecast_end_date": self.forecast_end_date,
				"company": self.company,
				"docstatus": 1
			},
			fields=["name"]
		)

		if not forecast_docs:
			frappe.msgprint("No matching Forecast Sales Person records found for the selected date range and company")
			return

		# Dictionary to aggregate items by item_code
		items_dict = {}

		# Fetch all items from matching forecast documents
		for doc in forecast_docs:
			forecast_items = frappe.db.get_all(
				"Forecast Sales Person Wise Item",
				filters={"parent": doc.name},
				fields=["item_code", "item_name", "week_1", "week_2", "week_3", "week_4"]
			)

			for item in forecast_items:
				key = item.item_code

				if key not in items_dict:
					items_dict[key] = {
						"item_code": item.item_code,
						"item_name": item.item_name,
						"week_1": 0,
						"week_2": 0,
						"week_3": 0,
						"week_4": 0
					}

				# Aggregate weekly quantities
				items_dict[key]["week_1"] += (item.week_1 or 0)
				items_dict[key]["week_2"] += (item.week_2 or 0)
				items_dict[key]["week_3"] += (item.week_3 or 0)
				items_dict[key]["week_4"] += (item.week_4 or 0)

		# Restrict to the selected plant's items (Item.custom_manufacturing_location == plant warehouse)
		plant_warehouse = PLANT_WAREHOUSE.get(self.plant) if self.plant else None

		# Add aggregated items to the items child table
		for item_data in items_dict.values():
			# Skip items that do not belong to the selected plant
			if plant_warehouse:
				manufacturing_location = frappe.db.get_value(
					"Item", item_data["item_code"], "custom_manufacturing_location"
				)
				if manufacturing_location != plant_warehouse:
					continue

			# Get BOM for the item if it exists
			bom = frappe.db.get_value("BOM", {"item": item_data["item_code"], "is_default": 1, "is_active": 1}, "name")

			self.append("items", {
				"item_code": item_data["item_code"],
				"item_name": item_data["item_name"],
				"bom": bom,
				"week_1": item_data["week_1"],
				"week_2": item_data["week_2"],
				"week_3": item_data["week_3"],
				"week_4": item_data["week_4"]
			})

		plant_note = f" for {self.plant}" if self.plant else ""
		frappe.msgprint(f"Fetched {len(self.items)} items{plant_note} from {len(forecast_docs)} sales forecasts")

	@frappe.whitelist()
	def create_material_requests(self):
		"""Create Material Requests from Forecast Club material request items"""
		from frappe import _

		if not self.material_request_items:
			frappe.msgprint("No material request items found. Please fetch material request items first.")
			return

		if self.docstatus != 1:
			frappe.throw(_("Please submit the Forecast Club document before creating Material Requests"))

		# Check if Material Request already exists for this Forecast Club (excluding cancelled)
		existing_mr = frappe.db.sql("""
			SELECT mri.name
			FROM `tabMaterial Request Item` mri
			INNER JOIN `tabMaterial Request` mr ON mri.parent = mr.name
			WHERE mri.custom_forecast_club = %s
			AND mr.docstatus != 2
			LIMIT 1
		""", self.name)

		if existing_mr:
			frappe.throw(_("Material Request already exists for this Forecast Club. Please check existing Material Requests."))

		# Create single Material Request with all items
		mr_items = []
		for item in self.material_request_items:
			# Use qty field from material request items
			# Skip if qty is 0 or not set
			if not item.qty or item.qty <= 0:
				continue

			mr_items.append({
				"item_code": item.item_code,
				"qty": item.qty,
				"schedule_date": self.forecast_end_date,
				"warehouse": self.set_warehouse,
				"custom_forecast_club": self.name
			})

		if not mr_items:
			frappe.msgprint("No items with quantity greater than 0 found. Please set qty for items.")
			return

		# Create Material Request
		mr = frappe.get_doc({
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": self.company,
			"transaction_date": self.date,
			"schedule_date": self.forecast_end_date,
			"items": mr_items
		})

		mr.insert()

		# Add tag "From Forecast" to Material Request
		frappe.get_doc("Material Request", mr.name).add_tag("From Forecast")

		# Update status to Material Requested
		self.db_set("status", "Material Requested")

		frappe.msgprint(f"Created Material Request: {mr.name}")
		return [mr.name]

	@frappe.whitelist()
	def create_work_orders(self):
		"""Create Work Orders from Forecast Club items based on weekly batches"""
		from frappe import _

		if not self.items:
			frappe.msgprint("No items found in Forecast Club.")
			return

		if self.docstatus != 1:
			frappe.throw(_("Please submit the Forecast Club document before creating Work Orders"))

		work_orders_created = []

		for item in self.items:
			if not item.item_code or not item.bom:
				continue

			# Define weeks mapping
			weeks = [
				{"week": "week_1", "batch": "w1_batch", "batch_qty": "w1_batch_qty", "wo_field": "w1_wo", "week_name": "Week 1"},
				{"week": "week_2", "batch": "w2_batch", "batch_qty": "w2_batch_qty", "wo_field": "w2_wo", "week_name": "Week 2"},
				{"week": "week_3", "batch": "w3_batch", "batch_qty": "w3_batch_qty", "wo_field": "w3_wo", "week_name": "Week 3"},
				{"week": "week_4", "batch": "w4_batch", "batch_qty": "w4_batch_qty", "wo_field": "w4_wo", "week_name": "Week 4"}
			]

			for week_data in weeks:
				batch_count = getattr(item, week_data["batch"], 0) or 0
				batch_qty = getattr(item, week_data["batch_qty"], 0) or 0

				# Skip if no batches for this week
				if batch_count <= 0 or batch_qty <= 0:
					continue

				# Check if Work Order already exists for this item and week
				existing_wo = frappe.db.exists("Work Order", {
					"custom_forecast_club": self.name,
					"production_item": item.item_code,
					"custom_weekly": week_data["week"],
					"docstatus": ["!=", 2]  # Not cancelled
				})

				if existing_wo:
					continue

				# Create Work Order
				wo = frappe.get_doc({
					"doctype": "Work Order",
					"production_item": item.item_code,
					"bom_no": item.bom,
					"qty": batch_qty,  # Use weekly batch quantity
					"company": self.company,
					"batch_size": item.batch_size,
					"custom_forecast_club": self.name,
					"custom_forecast_club_item": item.name,
					"custom_weekly": week_data["week"],
					"fg_warehouse": self.set_warehouse if self.set_warehouse else None,
					"wip_warehouse": self.set_warehouse if self.set_warehouse else None,
				})

				wo.insert()
				work_orders_created.append(wo.name)

		if work_orders_created:
			frappe.msgprint(f"Created {len(work_orders_created)} Work Orders: {', '.join(work_orders_created)}")
		else:
			frappe.msgprint("No Work Orders created. Either they already exist or no weekly batches are set.")

		return work_orders_created


@frappe.whitelist()
def get_item_stock_and_packaging(item_code, company=None):
	"""Whitelisted wrapper for client calls. Returns custom_company_stock and packaging list for an item."""
	return ForecastClub.get_item_stock_and_packaging(item_code, company=company)


@frappe.whitelist()
def get_work_order_summary(forecast_club, week):
	"""Get count of Work Orders created for each item in a specific week"""
	# Get all Work Orders for this Forecast Club and week
	existing_wos = frappe.db.get_all(
		"Work Order",
		filters={
			"custom_forecast_club": forecast_club,
			"custom_weekly": week,
			"docstatus": ["!=", 2]  # Not cancelled
		},
		fields=["production_item"]
	)

	# Count Work Orders per item
	wo_count = {}
	for wo in existing_wos:
		item_code = wo.production_item
		wo_count[item_code] = wo_count.get(item_code, 0) + 1

	return wo_count


@frappe.whitelist()
def create_work_orders_for_week(forecast_club, week, selected_items):
	"""Create Work Orders for selected items in a specific week"""
	from frappe import _

	if isinstance(selected_items, str):
		import json
		selected_items = json.loads(selected_items)

	# Get Forecast Club document
	fc_doc = frappe.get_doc("Forecast Club", forecast_club)

	if fc_doc.docstatus != 1:
		frappe.throw(_("Forecast Club must be submitted"))

	# Map week field to batch fields
	week_to_fields_map = {
		"week_1": {"batch": "w1_batch", "batch_qty": "w1_batch_qty", "wo_field": "w1_wo"},
		"week_2": {"batch": "w2_batch", "batch_qty": "w2_batch_qty", "wo_field": "w2_wo"},
		"week_3": {"batch": "w3_batch", "batch_qty": "w3_batch_qty", "wo_field": "w3_wo"},
		"week_4": {"batch": "w4_batch", "batch_qty": "w4_batch_qty", "wo_field": "w4_wo"}
	}

	week_fields = week_to_fields_map.get(week)
	if not week_fields:
		frappe.throw(_("Invalid week selected"))

	work_orders_created = []

	for item in fc_doc.items:
		# Check if this item is in the selected items list
		if item.name not in selected_items:
			continue

		if not item.item_code or not item.bom:
			continue

		batch_count = getattr(item, week_fields["batch"], 0) or 0
		batch_qty = getattr(item, week_fields["batch_qty"], 0) or 0

		# Skip if no batches for this week
		if batch_count <= 0 or batch_qty <= 0:
			continue

		# Check if Work Order already exists for this item and week
		existing_wo = frappe.db.exists("Work Order", {
			"custom_forecast_club": fc_doc.name,
			"production_item": item.item_code,
			"custom_weekly": week,
			"docstatus": ["!=", 2]  # Not cancelled
		})

		if existing_wo:
			continue

		# Create Work Order
		wo = frappe.get_doc({
			"doctype": "Work Order",
			"production_item": item.item_code,
			"bom_no": item.bom,
			"qty": batch_qty,  # Use weekly batch quantity
			"company": fc_doc.company,
			"batch_size": item.batch_size,
			"custom_forecast_club": fc_doc.name,
			"custom_forecast_club_item": item.name,
			"custom_weekly": week,
			"fg_warehouse": fc_doc.set_warehouse if fc_doc.set_warehouse else None,
			"wip_warehouse": fc_doc.set_warehouse if fc_doc.set_warehouse else None,
		})

		wo.insert()
		work_orders_created.append(wo.name)

	if work_orders_created:
		frappe.msgprint(f"Created {len(work_orders_created)} Work Orders: {', '.join(work_orders_created)}")

	return work_orders_created


@frappe.whitelist()
def create_work_orders_batch_wise(forecast_club, week, items):
	"""Create multiple Work Orders - one per batch for each item"""
	from frappe import _
	import json

	if isinstance(items, str):
		items = json.loads(items)

	# Get Forecast Club document
	fc_doc = frappe.get_doc("Forecast Club", forecast_club)

	if fc_doc.docstatus != 1:
		frappe.throw(_("Forecast Club must be submitted"))

	work_orders_created = []

	for item_data in items:
		forecast_club_item_name = item_data.get("forecast_club_item")
		batches_to_create = int(flt(item_data.get("batches", 0)))
		batch_size = flt(item_data.get("batch_size", 0))

		if batches_to_create <= 0 or batch_size <= 0:
			continue

		# Find the Forecast Club Item
		fc_item = None
		for item in fc_doc.items:
			if item.name == forecast_club_item_name:
				fc_item = item
				break

		if not fc_item:
			continue

		# Create multiple Work Orders - one for each batch
		for batch_number in range(1, batches_to_create + 1):
			try:
				wo = frappe.get_doc({
					"doctype": "Work Order",
					"production_item": fc_item.item_code,
					"bom_no": fc_item.bom,
					"qty": batch_size,  # Each Work Order has batch_size quantity
					"company": fc_doc.company,
					"batch_size": batch_size,
					"custom_forecast_club": fc_doc.name,
					"custom_forecast_club_item": fc_item.name,
					"custom_weekly": week,
					"fg_warehouse": fc_doc.set_warehouse if fc_doc.set_warehouse else None,
					"wip_warehouse": fc_doc.set_warehouse if fc_doc.set_warehouse else None,
				})

				wo.insert()
				work_orders_created.append(wo.name)

			except Exception as e:
				frappe.log_error(f"Error creating Work Order for {fc_item.item_code} batch {batch_number}: {str(e)}")

	if work_orders_created:
		frappe.msgprint(f"Created {len(work_orders_created)} Work Orders: {', '.join(work_orders_created)}")

	return work_orders_created


def on_material_request_cancel(doc, method):
	"""Update Forecast Club status when Material Request is cancelled"""
	_update_forecast_club_status_on_mr_cancel_or_delete(doc)


def on_material_request_delete(doc, method):
	"""Update Forecast Club status when Material Request is deleted"""
	_update_forecast_club_status_on_mr_cancel_or_delete(doc)


def _update_forecast_club_status_on_mr_cancel_or_delete(doc):
	"""Common function to update Forecast Club status when Material Request is cancelled or deleted"""
	# Get all forecast club references from the Material Request
	forecast_clubs = set()
	for item in doc.items:
		if hasattr(item, 'custom_forecast_club') and item.custom_forecast_club:
			forecast_clubs.add(item.custom_forecast_club)

	# Update status for each Forecast Club
	for fc_name in forecast_clubs:
		try:
			# Check if Forecast Club still exists
			if not frappe.db.exists("Forecast Club", fc_name):
				continue

			# Check if there are any other active Material Requests for this Forecast Club
			# Query Material Request directly to check for non-cancelled MRs
			other_mrs = frappe.db.sql("""
				SELECT COUNT(DISTINCT mr.name)
				FROM `tabMaterial Request` mr
				INNER JOIN `tabMaterial Request Item` mri ON mri.parent = mr.name
				WHERE mri.custom_forecast_club = %s
				AND mr.docstatus != 2
				AND mr.name != %s
			""", (fc_name, doc.name))[0][0]

			# If no other active Material Requests exist, reset status to Forecast Planned
			if other_mrs == 0:
				frappe.db.set_value("Forecast Club", fc_name, "status", "Forecast Planned")
				frappe.msgprint(f"Forecast Club {fc_name} status updated to 'Forecast Planned'")

		except Exception as e:
			frappe.log_error(f"Error updating Forecast Club {fc_name}: {str(e)}")


def on_work_order_submit(doc, method):
	"""Update Forecast Club item's weekly work order count when Work Order is submitted"""
	if not doc.custom_forecast_club or not doc.custom_forecast_club_item:
		return

	# Get the week field name (week_1, week_2, etc.)
	week_field = doc.custom_weekly

	if not week_field:
		return

	# Map week field to wo field
	week_to_wo_map = {
		"week_1": "w1_wo",
		"week_2": "w2_wo",
		"week_3": "w3_wo",
		"week_4": "w4_wo"
	}

	wo_field = week_to_wo_map.get(week_field)

	if not wo_field:
		return

	try:
		# Get the Forecast Club document
		fc_doc = frappe.get_doc("Forecast Club", doc.custom_forecast_club)

		# Find the matching item in Forecast Club
		for item in fc_doc.items:
			if item.name == doc.custom_forecast_club_item:
				# Get total quantity from all Work Orders for this week
				total_wo_qty = frappe.db.sql("""
					SELECT SUM(qty) as total_qty
					FROM `tabWork Order`
					WHERE custom_forecast_club = %s
					AND custom_forecast_club_item = %s
					AND custom_weekly = %s
					AND docstatus != 2
				""", (doc.custom_forecast_club, doc.custom_forecast_club_item, week_field), as_dict=1)

				new_wo_qty = total_wo_qty[0].total_qty if total_wo_qty else 0

				# Update the wo field with total quantity
				frappe.db.set_value(
					"Forecast Club Item",
					item.name,
					wo_field,
					new_wo_qty or 0
				)

				frappe.msgprint(f"Updated Forecast Club {doc.custom_forecast_club}: {wo_field} = {new_wo_qty}")
				break

	except Exception as e:
		frappe.log_error(f"Error updating Forecast Club {doc.custom_forecast_club}: {str(e)}")


def on_work_order_cancel(doc, method):
	"""Update Forecast Club item's weekly work order count when Work Order is cancelled"""
	if not doc.custom_forecast_club or not doc.custom_forecast_club_item:
		return

	# Get the week field name (week_1, week_2, etc.)
	week_field = doc.custom_weekly

	if not week_field:
		return

	# Map week field to wo field
	week_to_wo_map = {
		"week_1": "w1_wo",
		"week_2": "w2_wo",
		"week_3": "w3_wo",
		"week_4": "w4_wo"
	}

	wo_field = week_to_wo_map.get(week_field)

	if not wo_field:
		return

	try:
		# Get the Forecast Club document
		fc_doc = frappe.get_doc("Forecast Club", doc.custom_forecast_club)

		# Find the matching item in Forecast Club
		for item in fc_doc.items:
			if item.name == doc.custom_forecast_club_item:
				# Recalculate total quantity from all remaining Work Orders for this week
				total_wo_qty = frappe.db.sql("""
					SELECT SUM(qty) as total_qty
					FROM `tabWork Order`
					WHERE custom_forecast_club = %s
					AND custom_forecast_club_item = %s
					AND custom_weekly = %s
					AND docstatus != 2
				""", (doc.custom_forecast_club, doc.custom_forecast_club_item, week_field), as_dict=1)

				new_wo_qty = total_wo_qty[0].total_qty if total_wo_qty else 0

				# Update the wo field with total quantity
				frappe.db.set_value(
					"Forecast Club Item",
					item.name,
					wo_field,
					new_wo_qty or 0
				)

				frappe.msgprint(f"Updated Forecast Club {doc.custom_forecast_club}: {wo_field} = {new_wo_qty}")
				break

	except Exception as e:
		frappe.log_error(f"Error updating Forecast Club {doc.custom_forecast_club}: {str(e)}")
