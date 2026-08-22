"""Constants for the Dropcountr integration."""

from datetime import timedelta

DOMAIN = "dropcountr"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

UPDATE_INTERVAL = timedelta(hours=1)

ATTR_PREMISE_NAME = "premise_name"
ATTR_METER_ID = "meter_id"
ATTR_SERVICE_TYPE = "service_type"
ATTR_LEAK_ID = "leak_id"
ATTR_LEAK_STARTED_AT = "leak_started_at"
ATTR_LEAK_VOLUME = "leak_est_volume_gallons"
ATTR_LEAK_COST = "leak_est_cost"
ATTR_LEAK_CURRENCY = "leak_est_cost_currency"
