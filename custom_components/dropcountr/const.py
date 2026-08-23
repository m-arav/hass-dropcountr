"""Constants for the Dropcountr integration."""

from datetime import timedelta

DOMAIN = "dropcountr"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_METER_IDS = "meter_ids"

DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 1440

UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

ATTR_PREMISE_NAME = "premise_name"
ATTR_PREMISE_TIMEZONE = "premise_timezone"
ATTR_METER_ID = "meter_id"
ATTR_SERVICE_TYPE = "service_type"
ATTR_READ_FREQUENCY = "read_frequency"
ATTR_LAG = "lag"
ATTR_LEAK_ID = "leak_id"
ATTR_LEAK_STARTED_AT = "leak_started_at"
ATTR_LEAK_VOLUME = "leak_est_volume_gallons"
ATTR_LEAK_HOURLY_VOLUME = "leak_est_hourly_gallons"
ATTR_LEAK_COST = "leak_est_cost"
ATTR_LEAK_CURRENCY = "leak_est_cost_currency"
ATTR_LEAK_IGNORED = "leak_is_ignored"
ATTR_LEAK_ARCHIVED = "leak_is_archived"
ATTR_DAY_GOAL = "day_goal_gallons"
ATTR_WEEK_GOAL = "week_goal_gallons"
ATTR_MONTH_GOAL = "month_goal_gallons"
ATTR_DAY_COST = "day_cost"
ATTR_WEEK_COST = "week_cost"
ATTR_MONTH_COST = "month_cost"
ATTR_COST_CURRENCY = "cost_currency"
ATTR_DURING = "during"
ATTR_DURING_START = "during_start"
ATTR_DURING_END = "during_end"
ATTR_LAST_SUCCESS = "last_success"
ATTR_LAST_ERROR = "last_error"
ATTR_METER_COUNT = "meter_count"
ATTR_SCAN_INTERVAL = "scan_interval_minutes"
