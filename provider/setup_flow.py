"""Setup flow for linking Ynison to one configured Yandex Music account."""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry, ConfigValueOption
from music_assistant_models.enums import ConfigEntryType

from music_assistant.helpers.config_entries import create_player_selector
from music_assistant.models.setup_flow import AbortFlow, SetupFlowError

from .config_helpers import list_yandex_music_instances
from .constants import (
    CONF_MASS_PLAYER_ID,
    CONF_PUBLISH_NAME,
    CONF_YM_INSTANCE,
    DEFAULT_DISPLAY_NAME,
    LEGACY_AUTH_KEYS,
    LEGACY_YM_INSTANCE_OWN,
    PLAYER_ID_AUTO,
)

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigValueType

    from music_assistant.mass import MusicAssistant
    from music_assistant.models.setup_flow import SetupSession


async def run_setup(session: SetupSession) -> None:
    """Collect the linked Yandex Music instance and Ynison device identity."""
    ym_instances = list_yandex_music_instances(session.mass)
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

    errors: dict[str, str] | None = None
    while True:
        submitted = await session.form(
            [
                _source_entry(selected_source, ym_instances),
                _player_entry(session.mass, selected_player),
                ConfigEntry(
                    key=CONF_PUBLISH_NAME,
                    type=ConfigEntryType.STRING,
                    required=True,
                    default_value=selected_name,
                    value=selected_name,
                ),
            ],
            step_id="user",
            errors=errors,
            last_step=True,
        )
        selected_source = str(submitted[CONF_YM_INSTANCE])
        selected_player = str(submitted[CONF_MASS_PLAYER_ID])
        selected_name = str(submitted[CONF_PUBLISH_NAME])
        collected = dict(setup_data)
        collected.update(submitted)
        if legacy_present:
            collected.update(dict.fromkeys(LEGACY_AUTH_KEYS))
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


def _player_entry(mass: MusicAssistant, selected_player: str) -> ConfigEntry:
    """Build a player selector while retaining the provider's automatic option."""
    entry = create_player_selector(mass, CONF_MASS_PLAYER_ID, selected_player)
    entry.options = [
        ConfigValueOption(value=PLAYER_ID_AUTO),
        *(option for option in entry.options if option.value != PLAYER_ID_AUTO),
    ]
    selected = (
        selected_player
        if any(option.value == selected_player for option in entry.options)
        else PLAYER_ID_AUTO
    )
    entry.default_value = selected
    entry.value = selected
    return entry
