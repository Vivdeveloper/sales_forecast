app_name = "sales_forecast"
app_title = "Sales Forecast"
app_publisher = "Viv Choudhary"
app_description = "Sales Forecast"
app_email = "choudharyvivek195@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "sales_forecast",
# 		"logo": "/assets/sales_forecast/logo.png",
# 		"title": "Sales Forecast",
# 		"route": "/sales_forecast",
# 		"has_permission": "sales_forecast.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/sales_forecast/css/sales_forecast.css"
# app_include_js = "/assets/sales_forecast/js/sales_forecast.js"

# include js, css files in header of web template
# web_include_css = "/assets/sales_forecast/css/sales_forecast.css"
# web_include_js = "/assets/sales_forecast/js/sales_forecast.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "sales_forecast/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "sales_forecast/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "sales_forecast.utils.jinja_methods",
# 	"filters": "sales_forecast.utils.jinja_filters"
# }


# Installation
# ------------

# before_install = "sales_forecast.install.before_install"
# after_install = "sales_forecast.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "sales_forecast.uninstall.before_uninstall"
# after_uninstall = "sales_forecast.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "sales_forecast.utils.before_app_install"
# after_app_install = "sales_forecast.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "sales_forecast.utils.before_app_uninstall"
# after_app_uninstall = "sales_forecast.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "sales_forecast.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Material Request": {
		"on_cancel": "sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.on_material_request_cancel",
		"on_trash": "sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.on_material_request_delete"
	},
	"Work Order": {
		"on_submit": "sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.on_work_order_submit",
		"on_cancel": "sales_forecast.sales_forecast.doctype.forecast_club.forecast_club.on_work_order_cancel"
	},
	"Sales Person": {
		"validate": "sales_forecast.overrides.sales_person.validate"
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"sales_forecast.tasks.all"
# 	],
# 	"daily": [
# 		"sales_forecast.tasks.daily"
# 	],
# 	"hourly": [
# 		"sales_forecast.tasks.hourly"
# 	],
# 	"weekly": [
# 		"sales_forecast.tasks.weekly"
# 	],
# 	"monthly": [
# 		"sales_forecast.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "sales_forecast.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "sales_forecast.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "sales_forecast.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["sales_forecast.utils.before_request"]
# after_request = ["sales_forecast.utils.after_request"]

# Job Events
# ----------
# before_job = ["sales_forecast.utils.before_job"]
# after_job = ["sales_forecast.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"sales_forecast.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

