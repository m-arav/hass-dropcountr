# Dropcountr for Home Assistant

Home Assistant custom integration for [Dropcountr](https://dropcountr.com) water meters.

## Features

Per meter (service connection):

| Entity | Description |
|--------|-------------|
| Today / yesterday / week / month **usage** | Gallons for those periods in the **premise timezone**. Attributes include the server-aligned `during`, `during_start`, and `during_end` (local wall clock with the real offset, not the API's false UTC `Z`). |
| **Last reported hour** | Latest hourly bucket today whose gallons are not `null`. Query is start-of-day/end-of-day in the premise timezone. |
| Today **irrigation / indoor / irrigation share** | Outdoor vs indoor split for today. Week/month usage sensors expose the same split as attributes. |
| **Billing period** usage / irrigation / indoor / cost / goal | Current utility billing cycle (`billing` period). Unavailable if the meter lacks the `billing_period` feature. |
| Day / week / month **cost** | Estimated cost for those periods |
| Day / week / month **goal** | Goal gallons for those periods |
| Goal **remaining / % used** | Today, week, month, and billing cycle. Remaining can go negative when over the goal. |
| **Read lag** | Vendor reporting delay from `usage_stats.lag` (ISO-8601 duration, shown in hours) |
| **7 / 30 / 90-day completeness** | Diagnostic meter-read coverage from `usage_stats` (`read_frequency` and raw `lag` are attributes) |
| **API health** | Diagnostic connectivity sensor for the account (last success, last error, meter count) |
| **Open leak** | On when an unresolved leak appears in the last-7-days leaks API |
| Leak estimated **volume / hourly / cost** | Populated while an open leak is active |

Icons use Material Design Icons (`mdi:water`, `mdi:pipe-leak`, `mdi:currency-usd`, etc.).

## Requirements

- Home Assistant 2024.8+
- [`dropcountr-py==0.3.1`](https://pypi.org/project/dropcountr-py/) (installed automatically by HA)

## Install

### HACS (recommended)

1. Add this repo as a custom repository (Integration).
2. Install **Dropcountr**.
3. Restart Home Assistant.
4. Settings → Devices & services → Add integration → **Dropcountr**.

### Manual

```bash
mkdir -p "$HOME/homeassistant/config/custom_components"
git clone https://github.com/m-arav/hass-dropcountr.git /tmp/hass-dropcountr
cp -r /tmp/hass-dropcountr/custom_components/dropcountr \
  "$HOME/homeassistant/config/custom_components/"
docker restart homeassistant
```

Then add the integration in the UI.

## Configuration

Enter your Dropcountr email and password.

After setup, open the integration → **Configure** to set:

- **Poll interval** (minutes, default 15)
- **Meters** to include (multi-select). Leave empty for all premises/meters.

If your password changes, HA will prompt to **reauthenticate**.

## Brand icon

Made-up gauge/wave brand art ships in `custom_components/dropcountr/brand/` (not official Dropcountr branding). Needs Home Assistant **2026.3+**. After updating, restart HA and hard-refresh the browser.

## License

MIT
