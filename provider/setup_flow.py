"""Setup flow for linking Ynison to one configured Yandex Music account."""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry, ConfigValueOption
from music_assistant_models.enums import ConfigEntryType

from music_assistant.helpers.config_entries import create_player_selector
<<<<<<< provider
from music_assistant.models.setup_flow import AbortFlow, SetupFlowError
||||||| upstream-base
from music_assistant.models.setup_flow import SetupFlowError, StepExpiredError
=======
from music_assistant.models.setup_flow import AbortFlow, SetupFlowError, StepExpiredError
>>>>>>> upstream-head

from .config_helpers import list_yandex_music_instances
from .constants import (
    CONF_MASS_PLAYER_ID,
<<<<<<< provider
    CONF_PUBLISH_NAME,
||||||| upstream-base
    CONF_PUBLISH_NAME,
    CONF_REMEMBER_SESSION,
    CONF_TOKEN,
    CONF_X_TOKEN,
=======
    CONF_REMEMBER_SESSION,
    CONF_TOKEN,
    CONF_X_TOKEN,
>>>>>>> upstream-head
    CONF_YM_INSTANCE,
<<<<<<< provider
    DEFAULT_DISPLAY_NAME,
    LEGACY_AUTH_KEYS,
    LEGACY_YM_INSTANCE_OWN,
    PLAYER_ID_AUTO,
||||||| upstream-base
    DEFAULT_DISPLAY_NAME,
    PLAYER_ID_AUTO,
    YM_INSTANCE_OWN,
=======
    YM_INSTANCE_OWN,
>>>>>>> upstream-head
)

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigValueType

    from music_assistant.models.setup_flow import SetupSession


async def run_setup(session: SetupSession) -> None:
<<<<<<< provider
    """Collect the linked Yandex Music instance and Ynison device identity."""
||||||| upstream-base
    """
    Run the Ynison setup flow: pick the account source, then borrow or QR-log in.

    :param session: The setup session driving the flow.
    """
=======
    """
    Run the Ynison setup flow: pick the account source, then borrow or QR-log in.

    :param session: The setup session driving the flow.
    """
    if not session.mass.players.all_players(False, False):
        raise AbortFlow("no_players")
>>>>>>> upstream-head
    ym_instances = list_yandex_music_instances(session.mass)
<<<<<<< provider
    if not ym_instances:
        raise AbortFlow("missing_dependency")

    setup_data: dict[str, ConfigValueType] = dict(session.context.setup_data)
    original_values = session.context.values
    prefill: dict[str, ConfigValueType] = {**original_values, **setup_data}
    valid_sources = {instance_id for instance_id, _name in ym_instances}
    existing_source = prefill.get(CONF_YM_INSTANCE)
    selected_source = (
        existing_source
        if isinstance(existing_source, str) and existing_source in valid_sources
        else ym_instances[0][0]
        if len(ym_instances) == 1
        else None
    )
    selected_player = str(
        prefill.get(CONF_MASS_PLAYER_ID) or prefill.get("player") or PLAYER_ID_AUTO
    )
    selected_name = str(
        prefill.get(CONF_PUBLISH_NAME) or prefill.get("display_name") or DEFAULT_DISPLAY_NAME
    )
    legacy_present = existing_source == LEGACY_YM_INSTANCE_OWN or any(
        key in setup_data or key in original_values for key in LEGACY_AUTH_KEYS
    )
||||||| upstream-base
    valid_sources = {inst_id for inst_id, _ in ym_instances}
    setup_data = dict(session.context.setup_data)
    prefill: dict[str, ConfigValueType] = {**session.context.values, **setup_data}
    default_source = str(prefill.get(CONF_YM_INSTANCE) or YM_INSTANCE_OWN)
    if default_source != YM_INSTANCE_OWN and default_source not in valid_sources:
        default_source = YM_INSTANCE_OWN
    default_player = prefill.get(CONF_MASS_PLAYER_ID)
    default_name = str(prefill.get(CONF_PUBLISH_NAME) or DEFAULT_DISPLAY_NAME)
=======
    valid_sources = {inst_id for inst_id, _ in ym_instances}
    setup_data = dict(session.context.setup_data)
    prefill: dict[str, ConfigValueType] = {**session.context.values, **setup_data}
    default_source = str(prefill.get(CONF_YM_INSTANCE) or YM_INSTANCE_OWN)
    if default_source != YM_INSTANCE_OWN and default_source not in valid_sources:
        default_source = YM_INSTANCE_OWN
    default_player = prefill.get(CONF_MASS_PLAYER_ID)
>>>>>>> upstream-head

    errors: dict[str, str] | None = None
    while True:
        submitted = await session.form(
            [
                _source_entry(selected_source, ym_instances),
                create_player_selector(
                    session.mass,
                    CONF_MASS_PLAYER_ID,
<<<<<<< provider
                    selected_player,
                    PLAYER_ID_AUTO,
                ),
                ConfigEntry(
                    key=CONF_PUBLISH_NAME,
                    type=ConfigEntryType.STRING,
                    required=True,
                    default_value=selected_name,
                    value=selected_name,
||||||| upstream-base
                    default_player,
                    PLAYER_ID_AUTO,
                ),
                ConfigEntry(
                    key=CONF_PUBLISH_NAME,
                    type=ConfigEntryType.STRING,
                    required=True,
                    default_value=default_name,
                    value=default_name,
=======
                    default_player,
>>>>>>> upstream-head
                ),
            ],
            step_id="user",
            errors=errors,
            last_step=True,
        )
<<<<<<< provider
        selected_source = str(submitted[CONF_YM_INSTANCE])
        selected_player = str(submitted[CONF_MASS_PLAYER_ID])
        selected_name = str(submitted[CONF_PUBLISH_NAME])
        collected = dict(setup_data)
        collected.update(submitted)
        if legacy_present:
            collected.update(dict.fromkeys(LEGACY_AUTH_KEYS))
||||||| upstream-base
        source = str(values[CONF_YM_INSTANCE])
        remember = bool(values[CONF_REMEMBER_SESSION])
        default_player = values[CONF_MASS_PLAYER_ID]
        default_name = str(values[CONF_PUBLISH_NAME])
        identity: dict[str, ConfigValueType] = {
            CONF_MASS_PLAYER_ID: default_player,
            CONF_PUBLISH_NAME: default_name,
        }
        if source != YM_INSTANCE_OWN:
            # borrow mode: the linked Yandex Music instance owns authentication
            try:
                await session.finish({CONF_YM_INSTANCE: source, **identity})
                return
            except SetupFlowError as err:
                errors = {"base": err.translation_key or str(err)}
                default_source = source
                continue
        # own credentials: QR login
        try:
            creds = await _qr_login(session)
        except YaPassportError as err:
            errors = {"base": str(err)}
            continue
        if creds.music_token is None:
            errors = {"base": "no_music_token"}
            continue
        collected: dict[str, ConfigValueType] = {
            CONF_YM_INSTANCE: YM_INSTANCE_OWN,
            CONF_TOKEN: creds.music_token.get_secret(),
            CONF_X_TOKEN: creds.x_token.get_secret() if remember else None,
            CONF_ACCOUNT_LOGIN: creds.display_login,
            **identity,
        }
=======
        source = str(values[CONF_YM_INSTANCE])
        remember = bool(values[CONF_REMEMBER_SESSION])
        default_player = values[CONF_MASS_PLAYER_ID]
        identity: dict[str, ConfigValueType] = {
            CONF_MASS_PLAYER_ID: default_player,
        }
        if source != YM_INSTANCE_OWN:
            # borrow mode: the linked Yandex Music instance owns authentication
            try:
                await session.finish({CONF_YM_INSTANCE: source, **identity})
                return
            except SetupFlowError as err:
                errors = {"base": err.translation_key or str(err)}
                default_source = source
                continue
        # own credentials: QR login
        try:
            creds = await _qr_login(session)
        except YaPassportError as err:
            errors = {"base": str(err)}
            continue
        if creds.music_token is None:
            errors = {"base": "no_music_token"}
            continue
        collected: dict[str, ConfigValueType] = {
            CONF_YM_INSTANCE: YM_INSTANCE_OWN,
            CONF_TOKEN: creds.music_token.get_secret(),
            CONF_X_TOKEN: creds.x_token.get_secret() if remember else None,
            CONF_ACCOUNT_LOGIN: creds.display_login,
            **identity,
        }
>>>>>>> upstream-head
        try:
            await session.finish(collected)
            return
        except SetupFlowError as err:
            errors = {"base": err.translation_key or str(err)}
            setup_data = collected


def _source_entry(
    selected_source: str | None,
    ym_instances: list[tuple[str, str]],
) -> ConfigEntry:
    """Build the required linked Yandex Music provider selector."""
    return ConfigEntry(
        key=CONF_YM_INSTANCE,
        type=ConfigEntryType.STRING,
        required=True,
        default_value=selected_source,
        value=selected_source,
        options=[
            ConfigValueOption(value=instance_id, title=f"Yandex Music: {name}")
            for instance_id, name in ym_instances
        ],
    )
