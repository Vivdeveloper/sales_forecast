# Copyright (c) 2026, Viv Choudhary and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

PLANT_1_WAREHOUSE = "Plant 1 WIP FG - PTPL"
PLANT_2_WAREHOUSE = "Plant 2 WIP FG - PTPL"


def _make_item(item_code, manufacturing_location):
	"""Create (or update) a stock Item tagged to a plant via custom_manufacturing_location."""
	if frappe.db.exists("Item", item_code):
		frappe.db.set_value("Item", item_code, "custom_manufacturing_location", manufacturing_location)
		return item_code

	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"custom_manufacturing_location": manufacturing_location,
		}
	)
	item.insert(ignore_permissions=True, ignore_mandatory=True)
	return item.name


class TestForecastClub(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.plant1_item = _make_item("_Test FC Plant1 Item", PLANT_1_WAREHOUSE)
		cls.plant2_item = _make_item("_Test FC Plant2 Item", PLANT_2_WAREHOUSE)

	def _new_fc(self, plant, item_code, start, end):
		doc = frappe.new_doc("Forecast Club")
		doc.company = self.company
		doc.plant = plant
		doc.date = start
		doc.forecast_start_date = start
		doc.forecast_end_date = end
		doc.append("items", {"item_code": item_code})
		return doc

	# --- Plant <-> item validation (Plant 1 and Plant 2) ---

	def test_plant1_rejects_plant2_item(self):
		doc = self._new_fc("Plant 1", self.plant2_item, "2027-06-01", "2027-06-30")
		with self.assertRaises(frappe.ValidationError):
			doc.validate_plant_items()

	def test_plant1_accepts_plant1_item(self):
		doc = self._new_fc("Plant 1", self.plant1_item, "2027-06-01", "2027-06-30")
		# Should not raise
		doc.validate_plant_items()

	def test_plant2_rejects_plant1_item(self):
		doc = self._new_fc("Plant 2", self.plant1_item, "2027-06-01", "2027-06-30")
		with self.assertRaises(frappe.ValidationError):
			doc.validate_plant_items()

	def test_plant2_accepts_plant2_item(self):
		doc = self._new_fc("Plant 2", self.plant2_item, "2027-06-01", "2027-06-30")
		doc.validate_plant_items()

	# --- Duplicate / overlapping date-range validation ---

	def test_overlapping_dates_same_plant_blocked(self):
		first = self._new_fc("Plant 1", self.plant1_item, "2027-07-01", "2027-07-31")
		first.flags.ignore_mandatory = True
		first.insert(ignore_permissions=True, ignore_mandatory=True)

		# Second forecast for same company + plant overlapping July -> blocked
		second = self._new_fc("Plant 1", self.plant1_item, "2027-07-10", "2027-07-20")
		with self.assertRaises(frappe.ValidationError):
			second.validate_duplicate_date_range()

	def test_different_plant_same_month_allowed(self):
		first = self._new_fc("Plant 1", self.plant1_item, "2027-08-01", "2027-08-31")
		first.flags.ignore_mandatory = True
		first.insert(ignore_permissions=True, ignore_mandatory=True)

		# Plant 2 forecast for the same month is allowed (per-plant scope)
		second = self._new_fc("Plant 2", self.plant2_item, "2027-08-01", "2027-08-31")
		second.validate_duplicate_date_range()

	def test_non_overlapping_dates_allowed(self):
		first = self._new_fc("Plant 1", self.plant1_item, "2027-09-01", "2027-09-30")
		first.flags.ignore_mandatory = True
		first.insert(ignore_permissions=True, ignore_mandatory=True)

		# October does not overlap September -> allowed
		second = self._new_fc("Plant 1", self.plant1_item, "2027-10-01", "2027-10-31")
		second.validate_duplicate_date_range()
