# Dropcountr for Home Assistant

Home Assistant custom integration for [Dropcountr](https://dropcountr.com) water meters.

## Features

Per meter (service connection):

| Entity | Description |
|--------|-------------|
| Today / yesterday / week / month **usage** | Gallons for those periods. Attributes include the server-aligned `during`, `during_start`, and `during_end`. |
| Day / week / month **cost** | Estimated cost for those periods |
| Day / week / month **goal** | Goal gallons for those periods |
| **Open leak** | On when an unresolved leak appears in the last-7-days leaks API |
| Leak estimated **volume / hourly / cost** | Populated while an open leak is active |

Does **not** use the usage series `is_leaking` flag.

Icons use Material Design Icons (`mdi:water`, `mdi:pipe-leak`, `mdi:currency-usd`, etc.).

## Requirements

- Home Assistant 2024.8+
- [`dropcountr-py==0.2.0`](https://pypi.org/project/dropcountr-py/) (installed automatically by HA)

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

## License

MIT
