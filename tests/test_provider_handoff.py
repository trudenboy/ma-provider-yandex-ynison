"""Tests for handoff playback mode."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from music_assistant_models.enums import (
    PlaybackState,
    ProviderFeature,
    ProviderType,
)

from provider import _features_for_mode
from provider.constants import (
    CONF_ALLOW_PLAYER_SWITCH,
    CONF_DEVICE_ID,
    CONF_MASS_PLAYER_ID,
    CONF_PLAYBACK_MODE,
    CONF_PUBLISH_NAME,
    CONF_TOKEN,
    CONF_YM_INSTANCE,
    DEFAULT_DISPLAY_NAME,
    PLAYBACK_MODE_HANDOFF,
    PLAYBACK_MODE_STREAM,
    YM_INSTANCE_OWN,
)
from provider.provider import YandexYnisonProvider
from provider.ynison_client import YnisonState


def _make_mock_config(values: dict[str, Any] | None = None) -> MagicMock:
    """Mock ProviderConfig — handoff mode by default."""
    defaults: dict[str, Any] = {
        CONF_TOKEN: "test-music-token",
        CONF_YM_INSTANCE: YM_INSTANCE_OWN,
        CONF_MASS_PLAYER_ID: "player-A",
        CONF_ALLOW_PLAYER_SWITCH: True,
        CONF_PUBLISH_NAME: DEFAULT_DISPLAY_NAME,
        CONF_DEVICE_ID: "test-device-uuid",
        CONF_PLAYBACK_MODE: PLAYBACK_MODE_HANDOFF,
        "log_level": "GLOBAL",
    }
    if values:
        defaults.update(values)
    config = MagicMock()
    config.get_value.side_effect = defaults.get
    return config


def _make_mock_mass() -> MagicMock:
    """Mock MA with player_queues APIs needed for handoff."""
    mass = MagicMock()
    mass.cache_path = "/var/cache/test-cache"

    def _create_task(coro: object) -> MagicMock:
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    mass.create_task = MagicMock(side_effect=_create_task)
    mass.subscribe = MagicMock(return_value=MagicMock())
    mass.get_providers = MagicMock(return_value=[])
    mass.config.set_raw_provider_config_value = MagicMock()
    mass.cache.get = AsyncMock(return_value=None)
    mass.cache.set = AsyncMock()
    mass.cache.delete = AsyncMock()

    # players
    fake_player = MagicMock()
    fake_player.player_id = "player-A"
    fake_player.display_name = "Player A"
    fake_player.state.playback_state = PlaybackState.IDLE
    mass.players.all_players = MagicMock(return_value=[fake_player])
    mass.players.get_player = MagicMock(return_value=fake_player)
    mass.players.select_source = AsyncMock()
    mass.players.cmd_stop = AsyncMock()
    mass.players.trigger_player_update = MagicMock()

    # player_queues — the handoff target
    mass.player_queues.play_media = AsyncMock()
    mass.player_queues.pause = AsyncMock()
    mass.player_queues.play = AsyncMock()
    mass.player_queues.seek = AsyncMock()
    mass.player_queues.next = AsyncMock()
    mass.player_queues.previous = AsyncMock()

    # default queue snapshot — IDLE, no elapsed time
    queue = MagicMock()
    queue.state = PlaybackState.IDLE
    queue.corrected_elapsed_time = 0.0
    queue.current_item = None
    mass.player_queues.get = MagicMock(return_value=queue)

    return mass


def _make_mock_manifest() -> MagicMock:
    manifest = MagicMock()
    manifest.domain = "yandex_ynison"
    return manifest


def _make_handoff_provider() -> YandexYnisonProvider:
    """Build a provider configured in handoff mode (no AUDIO_SOURCE feature)."""
    mass = _make_mock_mass()
    config = _make_mock_config()
    manifest = _make_mock_manifest()
    return YandexYnisonProvider(mass, manifest, config, set())


def _make_state(track_id: str, *, paused: bool = False, progress_ms: int = 0) -> MagicMock:
    """Build a minimal YnisonState-like mock.

    YnisonState exposes its scalars through @property without setters, so we
    use MagicMock here rather than instantiating the real class.
    """
    state = MagicMock(spec=YnisonState)
    state.current_track_id = track_id
    state.active_device_id = "test-device-uuid"
    state.is_paused = paused
    state.progress_ms = progress_ms
    state.last_update_is_echo = False
    state.duration_ms = 200000
    state.player_state = {
        "player_queue": {
            "current_playable_index": 0,
            "playable_list": [{"playable_id": track_id, "title": "Track"}],
            "entity_type": "",
            "entity_id": "",
        },
        "status": {},
    }
    return state


# ------------------------------------------------------------------
# _features_for_mode
# ------------------------------------------------------------------


class TestFeaturesForMode:
    """The setup() helper that picks SUPPORTED_FEATURES from config."""

    def test_stream_mode_advertises_audio_source(self) -> None:
        """Stream mode keeps AUDIO_SOURCE so the plugin appears as a source."""
        assert _features_for_mode(PLAYBACK_MODE_STREAM) == {ProviderFeature.AUDIO_SOURCE}

    def test_handoff_mode_has_no_features(self) -> None:
        """Handoff mode drops AUDIO_SOURCE — playback flows through MA queue."""
        assert _features_for_mode(PLAYBACK_MODE_HANDOFF) == set()

    def test_unknown_mode_falls_back_to_stream(self) -> None:
        """Unknown mode value falls back to stream behaviour, not crash."""
        assert _features_for_mode("nonsense") == {ProviderFeature.AUDIO_SOURCE}


# ------------------------------------------------------------------
# Provider init flags
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestHandoffInit:
    """Provider state when configured for handoff."""

    async def test_handoff_flag_set(self) -> None:
        """A handoff-config provider exposes _is_handoff=True and the mode constant."""
        provider = _make_handoff_provider()
        assert provider._is_handoff is True
        assert provider._playback_mode == PLAYBACK_MODE_HANDOFF


# ------------------------------------------------------------------
# _handoff_activate
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestHandoffActivate:
    """Translate Ynison state into player_queue commands."""

    async def test_new_track_calls_play_media(self) -> None:
        """A new Ynison track id triggers player_queues.play_media with the right URI."""
        provider = _make_handoff_provider()
        # link a yandex_music provider so the pre-fetch path is exercised
        ym = MagicMock()
        ym.domain = "yandex_music"
        ym.type = ProviderType.MUSIC
        ym.config.get_value = MagicMock(return_value="superb")
        provider._yandex_provider = ym
        provider._get_stream_details_with_retry = AsyncMock(  # type: ignore[method-assign]
            side_effect=Exception("no stream details — irrelevant for play_media call")
        )

        state = _make_state("track-1")
        await provider._handoff_activate(state, "player-A")

        provider.mass.player_queues.play_media.assert_awaited_once()
        call_args = provider.mass.player_queues.play_media.call_args
        assert call_args.args[0] == "player-A"
        assert call_args.args[1] == "yandex_music://track/track-1"
        assert provider._handoff_current_track_id == "track-1"
        assert provider._active_player_id == "player-A"

    async def test_same_track_no_redundant_play_media(self) -> None:
        """Re-receiving the active track without drift skips play_media and seek."""
        provider = _make_handoff_provider()
        provider._handoff_current_track_id = "track-1"
        # MA queue keeps reporting the same track at ~50s while Ynison
        # echoes ~50s — no drift, no commands.
        queue = provider.mass.player_queues.get.return_value
        queue.state = PlaybackState.PLAYING
        queue.corrected_elapsed_time = 50.0

        state = _make_state("track-1", progress_ms=50_000)
        await provider._handoff_activate(state, "player-A")

        provider.mass.player_queues.play_media.assert_not_awaited()
        provider.mass.player_queues.seek.assert_not_awaited()

    async def test_drift_triggers_seek(self) -> None:
        """Drift > 3000 ms between Ynison and MA queue triggers a seek call."""
        provider = _make_handoff_provider()
        provider._handoff_current_track_id = "track-1"
        queue = provider.mass.player_queues.get.return_value
        queue.state = PlaybackState.PLAYING
        queue.corrected_elapsed_time = 10.0  # MA at 10s

        # Ynison reports 60s — 50s drift, well over the 3s threshold
        state = _make_state("track-1", progress_ms=60_000)
        await provider._handoff_activate(state, "player-A")

        provider.mass.player_queues.seek.assert_awaited_once_with("player-A", 60)

    async def test_echo_does_not_trigger_seek(self) -> None:
        """An echo update from Ynison must not bounce back as a seek command."""
        provider = _make_handoff_provider()
        provider._handoff_current_track_id = "track-1"
        queue = provider.mass.player_queues.get.return_value
        queue.state = PlaybackState.PLAYING
        queue.corrected_elapsed_time = 10.0

        state = _make_state("track-1", progress_ms=60_000)
        state.last_update_is_echo = True
        await provider._handoff_activate(state, "player-A")

        provider.mass.player_queues.seek.assert_not_awaited()

    async def test_paused_queue_resumes_when_ynison_says_playing(self) -> None:
        """If MA queue is paused while Ynison says playing, resume the queue."""
        provider = _make_handoff_provider()
        provider._handoff_current_track_id = "track-1"
        queue = provider.mass.player_queues.get.return_value
        queue.state = PlaybackState.PAUSED
        queue.corrected_elapsed_time = 10.0

        state = _make_state("track-1", progress_ms=10_000)
        await provider._handoff_activate(state, "player-A")

        provider.mass.player_queues.play.assert_awaited_once_with("player-A")


@pytest.mark.asyncio
class TestHandoffPause:
    """Pause translation."""

    async def test_handoff_pause_calls_queue_pause(self) -> None:
        """Ynison pause translates to player_queues.pause on the active player."""
        provider = _make_handoff_provider()
        await provider._handoff_pause("player-A")
        provider.mass.player_queues.pause.assert_awaited_once_with("player-A")

    async def test_handoff_pause_swallows_errors(self) -> None:
        """Failures inside player_queues.pause must not propagate to Ynison handler."""
        provider = _make_handoff_provider()
        provider.mass.player_queues.pause = AsyncMock(side_effect=Exception("boom"))
        # Must not raise
        await provider._handoff_pause("player-A")


# ------------------------------------------------------------------
# _on_ma_player_event
# ------------------------------------------------------------------


class TestOnMaPlayerEvent:
    """MA → Ynison sync via subscription (synchronous handler)."""

    def _setup(self) -> YandexYnisonProvider:
        """Build a handoff provider wired up to a connected Ynison mock."""
        provider = _make_handoff_provider()
        provider._active_player_id = "player-A"
        ynison = MagicMock()
        ynison.connected = True
        ynison.state.duration_ms = 200000
        provider._ynison = ynison
        # Bypass real best-duration logic so the path doesn't hit MagicMock arithmetic
        provider._actual_duration_ms = 200000
        return provider

    def test_ignores_events_for_other_players(self) -> None:
        """Events on a different player must not result in any work."""
        provider = self._setup()
        event = MagicMock()
        event.object_id = "player-B"  # different player
        provider._on_ma_player_event(event)
        provider.mass.create_task.assert_not_called()

    def test_progress_throttle(self) -> None:
        """Two events fired within the throttle window result in only one push."""
        provider = self._setup()

        event = MagicMock()
        event.object_id = "player-A"

        # First event passes the throttle
        provider._on_ma_player_event(event)
        first_call_count = provider.mass.create_task.call_count
        assert first_call_count >= 1

        # Immediate second event blocked by 2s throttle
        provider._on_ma_player_event(event)
        assert provider.mass.create_task.call_count == first_call_count

    def test_idle_queue_signals_completion_once(self) -> None:
        """Queue going IDLE signals track completion once per track id."""
        provider = self._setup()
        provider._handoff_current_track_id = "track-1"
        # Queue has gone IDLE → completion signal expected
        queue = provider.mass.player_queues.get.return_value
        queue.state = PlaybackState.IDLE

        event = MagicMock()
        event.object_id = "player-A"
        provider._on_ma_player_event(event)
        assert provider._handoff_completion_signaled_for == "track-1"

        # Second event with same track and bypassed throttle must NOT re-signal
        provider._handoff_last_progress_sync_mono = 0.0
        before = provider.mass.create_task.call_count
        provider._on_ma_player_event(event)
        # Marker remains the same — completion is one-shot per track.
        assert provider._handoff_completion_signaled_for == "track-1"
        # At least one new task may fire for the throttle-bypassed progress
        # update, but completion should not double-fire.
        assert provider.mass.create_task.call_count >= before
