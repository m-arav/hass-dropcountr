# Dropcountr for Home Assistant

Home Assistant custom integration for [Dropcountr](https://dropcountr.com) water meters.

This is a community project and is **not** an official Dropcountr product or integration. Dropcountr does not endorse, support, or maintain it.

## Features

Per meter (service connection):

| Entity | Description |
|--------|-------------|
| **Total usage** | Synthetic running total (`total_increasing`) built by summing **reported** hourly gallons. Add this under **Energy → Water consumption**. History is backfilled for the last 30 days, then caught up each poll. Hours with `null` gallons are omitted (gaps, not zeros). This is not the physical meter index. |
| **Total cost** | Synthetic running total of Dropcountr’s hourly estimated **cost**. That figure is whatever the API billed for the hour — usage tiers **and** amortized static/fixed charges — not a flat `$ / gal`. In Energy → Water, set **Use an entity tracking the total costs** to this sensor. Same 30-day backfill and catch-up as Total usage. |
| Today / week **usage** | Gallons in the **premise timezone**. Attributes include the server-aligned `during`, `during_start`, and `during_end` (local wall clock with the real offset, not the API's false UTC `Z`). |
| Month **or** billing **usage** | Billing cycle when the meter has `billing_period`; otherwise calendar month. Never both. |
| **Last reported hour** | Latest hourly bucket in yesterday–today whose gallons are not `null`. |
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

## Home Assistant

After the first successful poll, each meter is a device with usage, cost, goal, leak, and diagnostic entities. **Total usage** and **Total cost** stay unavailable until the 30-day hourly import finishes (usually a minute or two).

### Energy dashboard (water and cost)

Dropcountr pricing is not a flat `$ / gal`. The API’s hourly cost already includes usage tiers **and** amortized static/fixed charges. Energy cannot model that as a unit price; it has to track a running cost total.

1. Reload the integration (or restart HA) after installing **0.7.0+**.
2. Confirm **Total usage** and **Total cost** have numbers (not unavailable). Optional: **Developer Tools → Statistics** and search `total_usage` / `total_cost` for hourly rows.
3. **Settings → Dashboards → Energy** (sometimes **Settings → Energy**).
4. Under **Water consumption**, **Add water source** and pick that meter’s **Total usage**.
5. For cost, choose **Use an entity tracking the total costs** and pick the same meter’s **Total cost**.
6. Save, then open the **Energy** dashboard and switch the graph to water.

Do **not** use a fixed price, a “current price” entity, or Day / Week / Billing cost here. Those reset or assume a single `$ / gal` and will not match the bill.

History is the last 30 days of **reported** hours, then catch-up each poll. Hours with `null` gallons are gaps, not zeros. The totals are not the physical meter index or a lifetime bill; they start at 0 at the first imported hour.

### Other notes

- Today / week / month-or-billing sensors are for cards and automations. Energy’s day/week/month bars come from **Total usage** / **Total cost**.
- Open leak and leak diagnostics stay on the meter device; they are not Energy sources.
- After an update, restart HA. For the brand icon (HA **2026.3+**), hard-refresh the browser.
- Entities removed in a later version can linger in the entity registry until you delete them.

## Brand icon

Made-up droplet-and-meter brand art ships in `custom_components/dropcountr/brand/` (not official Dropcountr branding). Needs Home Assistant **2026.3+**. After updating, restart HA and hard-refresh the browser.

## License

MIT
