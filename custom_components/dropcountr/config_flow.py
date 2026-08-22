"""Config flow for Dropcountr."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from dropcountr import DropcountrClient
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_EMAIL,
    CONF_METER_IDS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _validate_login(email: str, password: str) -> str:
    """Validate credentials; return account title (user name)."""
    client = DropcountrClient(email=email, password=password)
    try:
        response = client.login()
        if response.status_code >= 400:
            raise InvalidAuth
        user = client.me()
        return user.name or email
    except InvalidAuth:
        raise
    except Exception as err:
        _LOGGER.exception("Unexpected Dropcountr login error")
        raise CannotConnect from err
    finally:
        client.close()


def _list_meters(email: str, password: str) -> dict[str, str]:
    """Return meter_id -> label for option selection."""
    client = DropcountrClient(email=email, password=password)
    try:
        response = client.login()
        if response.status_code >= 400:
            raise InvalidAuth
        user = client.me()
        options: dict[str, str] = {}
        for premise_ref in user.premises:
            premise = client.premise(premise_ref.id)
            premise_name = premise.name or premise.id
            for sc in premise.service_connections:
                meter_id = sc.meter_id or sc.id
                meter_name = sc.name or "Meter"
                if sc.name and sc.meter_id:
                    label = f"{premise_name} — {sc.name} ({sc.meter_id})"
                elif sc.meter_id:
                    label = f"{premise_name} — {sc.meter_id}"
                else:
                    label = f"{premise_name} — {meter_name}"
                options[meter_id] = label
        return options
    except InvalidAuth:
        raise
    except Exception as err:
        _LOGGER.exception("Failed to list Dropcountr meters")
        raise CannotConnect from err
    finally:
        client.close()


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate user input and return info for the config entry."""
    title = await hass.async_add_executor_job(
        _validate_login, data[CONF_EMAIL], data[CONF_PASSWORD]
    )
    return {"title": title}


class DropcountrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dropcountr."""

    VERSION = 1
    _reauth_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DropcountrOptionsFlow:
        """Get the options flow for this handler."""
        return DropcountrOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_METER_IDS: [],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauth when credentials stop working."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect a new password and update the config entry."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        email = self._reauth_entry.data[CONF_EMAIL]

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            try:
                await validate_input(
                    self.hass, {CONF_EMAIL: email, CONF_PASSWORD: password}
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected reauth exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"email": email},
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )


class DropcountrOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Handle Dropcountr options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__(config_entry)
        self._meter_labels: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage Dropcountr options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            meter_ids = user_input.get(CONF_METER_IDS, [])
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_METER_IDS: list(meter_ids),
                },
            )

        try:
            self._meter_labels = await self.hass.async_add_executor_job(
                _list_meters,
                self.config_entry.data[CONF_EMAIL],
                self.config_entry.data[CONF_PASSWORD],
            )
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:
            _LOGGER.exception("Unexpected options exception")
            errors["base"] = "unknown"

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_meters = self.config_entry.options.get(CONF_METER_IDS, [])
        # Keep only meters that still exist
        current_meters = [m for m in current_meters if m in self._meter_labels]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current_interval
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="minutes",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        if self._meter_labels and not errors:
            options = [
                {"value": meter_id, "label": label}
                for meter_id, label in sorted(
                    self._meter_labels.items(), key=lambda item: item[1].lower()
                )
            ]
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current_interval
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="minutes",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_METER_IDS, default=current_meters
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "meter_hint": "Leave meters empty to include all premises/meters."
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
