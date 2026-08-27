# Audio Source Control Payload Compatibility

## Provenance

- Upstream change: `music-assistant/server#5880`
- Provider pull request: `trudenboy/ma-provider-yandex-ynison#142`
- Compatible Music Assistant baseline: `f84a9dbc3ae1f622e8beedd21984df8a37d3f9c1`
- Compatible models baseline: `music-assistant-models==1.1.194`

## Problem

Music Assistant widened the plugin source-control payload from seek-only
integers to `SourceControlValue`: integers, booleans, repeat modes, or no
value. Python booleans are integer subclasses, so forwarding a misrouted
boolean to Ynison's seek handler would turn it into a zero- or one-second seek.
Internal callers may also provide fractional numeric positions even though the
public models contract uses integer seconds.

## Contract

- `on_source_control` uses Music Assistant's `SourceControlValue` override.
- Play, pause, next, and previous dispatch remain unchanged.
- Seek accepts integer or fractional numeric positions and truncates them to
  whole seconds before sending them to Ynison.
- Boolean payloads are never interpreted as seek positions.
- Shuffle, repeat, volume, and absent payloads are not implemented because the
  Ynison source does not advertise those capabilities.

## Compatibility

The dependency lock moves to the first Music Assistant merge containing the
shared payload alias and stream-slot API while retaining the setup selector
contract used before upstream #6026. Later reverse-sync ports advance this pin
at their own API boundaries.

Music Assistant's standalone Git package omits the provider requirements from
`requirements_all.txt`; local verification therefore installs its matching
`hass-client==1.3.0` workspace pin after `uv sync --frozen`. Upstream-layout CI
already installs the complete requirements file.

## Verification

- RED: boolean payloads changed seek state and `12.75` remained fractional.
- GREEN: boolean payloads have no playback side effects and fractional seek is
  sent as 12 seconds.
- `uv lock --check`
- `uv run pytest` — 338 tests
- `uv run ruff check provider tests`
- `uv run ruff format --check provider tests`
- `uv run mypy`
- `uv run pre-commit run --all-files`
