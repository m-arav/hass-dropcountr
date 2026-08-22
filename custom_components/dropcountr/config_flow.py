"""Config flow for Dropcountr."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from dropcountr import DropcountrClient
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

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


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate user input and return info for the config entry."""
    title = await hass.async_add_executor_job(
        _validate_login, data[CONF_EMAIL], data[CONF_PASSWORD]
    )
    return {"title": title}


class DropcountrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dropcountr."""

    VERSION = 1

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
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
