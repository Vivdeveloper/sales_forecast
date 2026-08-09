// Sales Person — Monthly Targets grid.
// The Month link on each row only offers months not already used in the table,
// so a month can be picked once per fiscal year. (Server-side validation in
// overrides/sales_person.py is the safety net.)

frappe.ui.form.on("Sales Person", {
	setup(frm) {
		frm.set_query("month", "custom_monthly_targets", (doc, cdt, cdn) => {
			const current = locals[cdt][cdn];
			// Only block months already used in OTHER rows of the SAME fiscal year.
			// A month can be reused in a different fiscal year.
			const used = (frm.doc.custom_monthly_targets || [])
				.filter(
					(row) =>
						row.name !== current.name &&
						row.month &&
						row.fiscal_year === current.fiscal_year
				)
				.map((row) => row.month);

			const filters = {};
			if (used.length) {
				filters.name = ["not in", used];
			}
			return { filters };
		});
	},
});
