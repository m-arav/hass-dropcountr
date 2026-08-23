# Dropcountr for Home Assistant

Home Assistant custom integration for [Dropcountr](https://dropcountr.com) water meters.

This is a community project and is **not** an official Dropcountr product or integration. Dropcountr does not endorse, support, or maintain it.

## Features

Per meter (service connection):

| Entity | Description |
|--------|-------------|
| Today / week **usage** | Gallons in the **premise timezone**. Attributes include the server-aligned `during`, `during_start`, and `during_end` (local wall clock with the real offset, not the API's false UTC `Z`). |
| Month **or** billing **usage** | Billing cycle when the meter has `billing_period`; otherwise calendar month. Never both. |
| **Last reported hour** | Latest hourly bucket today whose gallons are not `null`. Query is start-of-day/end-of-day in the premise timezone. |
| Month **or** billing **indoor / irrigation share** | Indoor gallons and outdoor share for the same window as month-or-billing usage. Irrigation gallons stay as attributes on usage sensors. |
| Billing **cost / goal** | Only when the meter has `billing_period`. |
| Day / week **cost** | Estimated cost for those periods. Month cost is created only when billing is missing. |
| Month **or** billing **goal / % used** | Goal gallons and percent used for the same window as month-or-billing usage. |
| **Read lag** | Vendor reporting delay from `usage_stats.lag` (ISO-8601 duration, shown in hours) |
| **7 / 30 / 90-day completeness** | Diagnostic meter-read coverage from `usage_stats` (`read_frequency` and raw `lag` are attributes) |
| **API health** | Diagnostic connectivity sensor for the account (last success, last error, meter count) |
| **Open leak** | On when an unresolved leak appears in the last-7-days leaks API |
| Leak estimated **volume / hourly / cost** and **started** | Diagnostics while an open leak is active. `Leak started` is a timestamp. |

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

Made-up droplet-and-meter brand art ships in `custom_components/dropcountr/brand/` (not official Dropcountr branding). Needs Home Assistant **2026.3+**. After updating, restart HA and hard-refresh the browser.

## License

MIT
