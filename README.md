# Dropcountr for Home Assistant

Home Assistant custom integration for [Dropcountr](https://dropcountr.com) water meters.

## Features (v1)

Per meter (service connection):

- **Week usage** — gallons in the current calendar week
- **Month usage** — gallons in the current calendar month
- **Open leak** — binary sensor from the leaks API (last 7 days, unresolved / open-ended leaks)

Does **not** use the usage series `is_leaking` flag.

## Requirements

- Home Assistant 2024.8+
- Published package [`dropcountr-py==0.2.0`](https://pypi.org/project/dropcountr-py/) (installed automatically by HA)

## Install

### HACS (recommended)

1. Add this repo as a custom repository (Integration).
2. Install **Dropcountr**.
3. Restart Home Assistant.
4. Settings → Devices & services → Add integration → **Dropcountr**.

### Manual

Copy `custom_components/dropcountr` into your HA `config/custom_components/` directory, restart, then add the integration.

## Configuration

Enter your Dropcountr email and password. One config entry polls all premises and meters on the account every hour.

## Entities

Each meter becomes a device named `{premise} {meter}` (e.g. `2030 3rd St apt 8 Potable`) with:

| Entity | Description |
|--------|-------------|
| Week usage | Calendar week gallons (`period=week`) |
| Month usage | Calendar month gallons (`period=month`) |
| Open leak | On when an open-ended leak (`resolved_at` empty) is returned for the last 7 days |

Open leak attributes include leak id, started_at, estimated volume, and estimated cost when present.

## License

MIT
