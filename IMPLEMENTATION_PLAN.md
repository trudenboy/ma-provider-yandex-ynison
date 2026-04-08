# Implementation Plan: Yandex Ynison Plugin for Music Assistant

## Overview

This plugin makes any Music Assistant player appear as a playback device in the official
Yandex Music app. When a user selects the MA device in the Yandex Music app, audio streams
through MA to the configured player (Chromecast, DLNA, AirPlay, etc.).

The architecture follows the proven `spotify_connect` pattern from MA server — a `PluginProvider`
with `AUDIO_SOURCE` feature that acts as a bridge between an external music service protocol
and MA's player infrastructure.

---

## Phase 1: Ynison WebSocket Client (`ynison_client.py`)

**Goal**: Standalone, testable WebSocket client that connects to Ynison and receives state updates.

### 1.1 — Redirector handshake

- Connect to `wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison`
- Send authentication headers:
  ```
  Authorization: OAuth {token}
  Origin: https://music.yandex.ru
  Sec-WebSocket-Protocol: Bearer, v2, {device_info_json}
  ```
- `device_info_json` contains:
  - `Ynison-Device-Id`: UUID (generated once per instance, persisted)
  - `Ynison-Device-Info`: `{"app_name": "Music Assistant", "type": 1}`
- Parse response: extract `host`, `redirect_ticket`, `session_id`
- Handle errors: invalid token, network timeout, rate limiting

### 1.2 — State Service connection

- Connect to `wss://{host}/ynison_state.YnisonStateService/PutYnisonState`
- Same auth headers, plus `Ynison-Redirect-Ticket` and `Ynison-Session-Id` in the protocol header
- Send initial `update_full_state` message declaring this device:
  ```json
  {
    "update_full_state": {
      "player_state": {
        "status": {
          "paused": true,
          "duration_ms": 0,
          "progress_ms": 0,
          "playback_speed": 1.0
        },
        "player_queue": {
          "current_playable_index": 0,
          "playable_list": [],
          "options": {"repeat_mode": "NONE"}
        }
      },
      "device": {
        "info": {
          "device_id": "{uuid}",
          "title": "{display_name}",
          "type": "SPEAKER",
          "app_name": "Music Assistant",
          "app_version": "1.0.0"
        },
        "capabilities": {
          "can_be_player": true,
          "can_be_remote_controller": false,
          "volume_granularity": 100
        },
        "volume_info": {
          "volume": 1.0
        }
      }
    }
  }
  ```

### 1.3 — Message handling loop

- Receive `PutYnisonStateResponse` messages containing:
  - `player_state`: current playback status + queue
  - `devices`: list of connected devices
  - `active_device_id_optional`: which device is playing
- Parse incoming state, emit events via callbacks:
  - `on_state_update(player_state, active_device_id, devices)`
  - `on_active_device_changed(device_id)`
  - `on_disconnect()`

### 1.4 — Sending state updates

Methods to send state changes back to Ynison:
- `update_playing_status(progress_ms, duration_ms, paused)` — play/pause/seek
- `update_volume(volume: float)` — volume change
- `update_active_device(device_id)` — transfer playback to this device
- `update_player_state(player_state)` — full state sync (queue change, track skip)

### 1.5 — Connection lifecycle

- Auto-reconnect with exponential backoff on disconnection
- Periodic keepalive (based on `keep_alive_params` from redirector response)
- Graceful shutdown (WebSocket close frame)
- Thread-safe send via asyncio lock

### Tests for Phase 1

- `tests/test_ynison_client.py`:
  - Mock WebSocket to test redirector handshake
  - Test state message parsing
  - Test reconnection logic
  - Test send methods produce correct JSON

---

## Phase 2: Plugin Provider (`provider.py`, `__init__.py`)

**Goal**: Integrate the Ynison client as a MA PluginProvider with audio source.

### 2.1 — Provider class skeleton

```python
class YandexYnisonProvider(PluginProvider):
    """Yandex Music Connect via Ynison protocol."""
```

- Declare `supported_features = {ProviderFeature.AUDIO_SOURCE}`
- Instance attributes:
  - `_ynison_client: YnisonClient | None`
  - `_source_details: PluginSource`
  - `_active_player_id: str | None`
  - `_device_id: str` (persisted UUID)
  - `_yandex_provider: MusicProvider | None` (linked yandex_music provider)

### 2.2 — Configuration entries (`__init__.py`)

Config options (following `spotify_connect` pattern):

| Key | Type | Description |
|-----|------|-------------|
| `token` | SECURE_STRING | Yandex Music OAuth token (auto-populated by QR auth) |
| `x_token` | SECURE_STRING | Session token for auto-refresh (hidden) |
| `auth_qr` | ACTION | QR code authentication flow |
| `clear_auth` | ACTION | Reset credentials |
| `remember_session` | BOOLEAN | Store session token for auto-refresh |
| `player` | STRING | Target MA player ID (or "auto") |
| `allow_player_switch` | BOOLEAN | Allow manual player switching |
| `display_name` | STRING | Device name shown in Yandex Music app |

**Auth reuse**: Reuse `yandex_auth.py` from `ma-provider-yandex-music` (copy or shared package).

### 2.3 — Initialization (`handle_async_init`)

1. Load/validate token (same flow as yandex-music provider: try music token, fallback to x_token refresh)
2. Generate or load persisted device UUID
3. Create `PluginSource`:
   ```python
   self._source_details = PluginSource(
       id=self.instance_id,
       name=config.get_value(CONF_DISPLAY_NAME) or DEFAULT_DISPLAY_NAME,
       passive=not config.get_value(CONF_ALLOW_PLAYER_SWITCH),
       can_play_pause=False,   # enabled when yandex_music provider linked
       can_seek=False,
       can_next_previous=False,
       audio_format=AudioFormat(
           content_type=ContentType.PCM_S16LE,
           sample_rate=44100,
           bit_depth=16,
           channels=2,
       ),
       stream_type=StreamType.CUSTOM,
   )
   ```
4. Create `YnisonClient` with token and device config
5. Start Ynison connection in background task
6. Detect linked `yandex_music` MusicProvider (match by user account)

### 2.4 — `get_source()` and `get_audio_stream()`

- `get_source()` — returns `self._source_details`
- `get_audio_stream(player_id)` — async generator:
  1. Get current track_id from Ynison state
  2. Obtain stream URL from Yandex Music API (via linked provider or direct API call)
  3. Fetch audio, decode if encrypted (AES), convert to PCM
  4. Yield PCM chunks

### 2.5 — Event handling from Ynison

When Ynison reports this device becomes active:
1. Determine target player via `_get_target_player_id()` (auto or configured)
2. Call `mass.players.select_source(player_id, self.instance_id)`
3. Set `_source_details.in_use_by = player_id`
4. Update metadata from player_state (track title, artist, album, artwork)
5. Call `mass.players.trigger_player_update(player_id)`

When track changes:
1. Update `_source_details.metadata` with new track info
2. Trigger player update

When playback paused/stopped by remote:
1. Clear `in_use_by` if stopped
2. Trigger player update

### 2.6 — Bidirectional control (link with yandex_music provider)

When a `yandex_music` MusicProvider is detected with matching user_id:
1. Store reference as `self._yandex_provider`
2. Enable control callbacks:
   ```python
   self._source_details.can_play_pause = True
   self._source_details.can_seek = True
   self._source_details.can_next_previous = True
   self._source_details.on_play = self._on_play
   self._source_details.on_pause = self._on_pause
   self._source_details.on_next = self._on_next
   self._source_details.on_previous = self._on_previous
   self._source_details.on_seek = self._on_seek
   self._source_details.on_volume = self._on_volume
   ```
3. Control callbacks send corresponding `update_playing_status` / `update_player_state` to Ynison

### Tests for Phase 2

- `tests/test_provider.py`:
  - Test initialization with mock Ynison client
  - Test source creation with correct audio format
  - Test event handling (device activation, track change)
  - Test player switching logic
  - Test control callback wiring when yandex_music provider linked

---

## Phase 3: Audio Streaming

**Goal**: Fetch and deliver audio from Yandex Music when this device is selected for playback.

### 3.1 — Track resolution

When Ynison state indicates a track is playing on this device:
1. Extract `track_id` from `player_state.player_queue.playable_list[current_index].playable_id`
2. If linked `yandex_music` provider exists, use its `streaming.get_stream_details(track_id)`
3. Otherwise, make direct API calls to get download info (requires own client)

### 3.2 — Audio stream pipeline

```
Yandex CDN -> encrypted audio bytes
  -> AES decryption (if needed)
  -> ffmpeg conversion to PCM S16LE 44.1kHz
  -> yield chunks via get_audio_stream()
  -> MA player receives PCM
```

Options for PCM conversion:
- **Option A**: Reuse `YandexMusicStreamingManager` from the yandex-music provider directly
- **Option B**: Use MA's built-in stream handling — return StreamDetails and let MA handle conversion
- **Option C**: Self-contained ffmpeg subprocess pipe (like librespot in spotify_connect)

Recommended: **Option A** if linked provider available, **Option B** as fallback.

### 3.3 — Queue management

Track the Ynison queue state to support track transitions:
- When `current_playable_index` changes, switch to new track
- When queue is updated remotely, prepare next track
- Handle special queue types: WaveQueue (recommendations), GenerativeQueue (AI radio)

### Tests for Phase 3

- `tests/test_streaming.py`:
  - Test track ID extraction from Ynison state
  - Test stream details resolution via linked provider
  - Test PCM chunk delivery

---

## Phase 4: Authentication & Token Management

**Goal**: Seamless auth flow, reusing patterns from yandex-music provider.

### 4.1 — QR authentication

Copy/adapt `yandex_auth.py` from `ma-provider-yandex-music`:
- QR code generation via Yandex Passport
- CSRF token extraction
- Session polling for auth completion
- Extract x_token and music_token

### 4.2 — Token auto-refresh

- Store x_token (encrypted) for automatic music_token refresh
- On startup: try music_token first, fallback to x_token refresh
- Same logic as yandex-music provider's `handle_async_init`

### 4.3 — Account linking

Detect matching `yandex_music` MusicProvider instances:
- Compare user_id from Ynison connection with loaded yandex_music providers
- If match found, enable bidirectional control
- Subscribe to MA provider events to detect when yandex_music provider loads/unloads

---

## Phase 5: Metadata & UX Polish

**Goal**: Rich metadata display and smooth user experience.

### 5.1 — Track metadata

Update `PluginSource.metadata` with:
- `title`: track name
- `artist`: artist name(s)
- `album`: album name
- `image_url`: album cover URL
- `duration`: track duration
- `elapsed_time`: current playback position

Fetch metadata via:
- Yandex Music API `tracks/{track_id}` (linked provider or direct)
- Cache track metadata to avoid repeated API calls

### 5.2 — Volume synchronization

- When MA player volume changes -> `update_volume()` to Ynison
- When Ynison volume changes -> `mass.players.cmd_volume_set()`

### 5.3 — Multi-instance support

Each plugin instance = one Ynison device:
- Unique device_id per instance
- Unique display_name per instance
- Independent connection lifecycle

---

## Phase 6: Integration & CI

### 6.1 — Register in ma-provider-tools

Add entry to `providers.yml` in `trudenboy/ma-provider-tools`:

```yaml
- domain: yandex_ynison
  display_name: Yandex Music Connect (Ynison)
  repo: trudenboy/ma-provider-yandex-ynison
  default_branch: dev
  manifest_path: provider/manifest.json
  provider_path: provider/
  provider_type: plugin_provider
  locale: ru
  service_url: https://music.yandex.ru
  auth_method: "Yandex OAuth / QR"
  max_quality: "Source quality (passthrough from Yandex Music)"
  features:
    - label: "Yandex Music Connect (Ynison protocol)"
    - label: "MA player appears as device in Yandex Music app"
    - label: "Bidirectional playback control"
    - label: "Volume synchronization"
    - label: "Multi-instance (one per MA player)"
  skip_wrappers:
    - sync-from-upstream.yml.j2
    - upstream-pr.yml.j2
    - rebuild-integration.yml.j2
    - sync-kion-from-yandex.yml.j2
```

### 6.2 — GitHub repository setup

- Create repo `trudenboy/ma-provider-yandex-ynison`
- Configure `FORK_SYNC_PAT` secret
- Enable GitHub Pages for docs
- Set branch protection on `main`

### 6.3 — Documentation

- `docs-site/` with Starlight docs (setup guide, architecture, troubleshooting)
- `README.md` with quick start

---

## Implementation Order (recommended)

| Step | Phase | Deliverable | Depends on |
|------|-------|-------------|------------|
| 1 | 1.1-1.2 | Ynison client: connect + handshake | — |
| 2 | 1.3 | Ynison client: receive state updates | Step 1 |
| 3 | 1.4-1.5 | Ynison client: send updates + reconnect | Step 2 |
| 4 | 4.1-4.2 | QR auth + token management | — |
| 5 | 2.1-2.3 | Plugin provider skeleton + config | Step 3, Step 4 |
| 6 | 2.4-2.5 | Audio source + Ynison event handling | Step 5 |
| 7 | 3.1-3.3 | Audio streaming pipeline | Step 6 |
| 8 | 2.6 | Bidirectional control (link yandex_music) | Step 7 |
| 9 | 5.1-5.3 | Metadata, volume sync, multi-instance | Step 8 |
| 10 | 6.1-6.3 | CI registration, docs, repo setup | Step 9 |

---

## Key Technical Decisions

### JSON vs Protobuf
The Ynison protocol uses JSON over WebSocket despite having protobuf schemas. We will use
JSON serialization (no protobuf dependency needed). This matches all known open-source
implementations.

### Audio delivery: `StreamType.CUSTOM` with `get_audio_stream()`
Unlike Spotify Connect (which uses librespot + named pipe), we control the audio fetch
ourselves. Using `StreamType.CUSTOM` and yielding PCM bytes from `get_audio_stream()`
gives us full control without external binaries.

### Auth reuse
Copy `yandex_auth.py` from `ma-provider-yandex-music` rather than creating a shared package.
This avoids coupling the two repos and keeps each provider self-contained. Can be refactored
to a shared package later if more providers need it.

### Device capabilities
Register as `can_be_player: true, can_be_remote_controller: false`. This makes the device
appear as a playback target in the Yandex Music app without trying to control other devices.

---

## Open Questions

1. **Encrypted streams**: Does the Ynison protocol itself deliver audio, or do we fetch from
   the regular Yandex Music CDN? (Answer: We fetch from CDN — Ynison only syncs state.)

2. **Queue injection**: When Yandex Music app adds tracks to queue, how should MA handle
   queue updates? (Initial approach: follow queue changes passively.)

3. **Multiple Yandex accounts**: Can different plugin instances use different Yandex accounts?
   (Yes, each instance has its own token.)

4. **Rate limiting**: Does Ynison enforce connection rate limits? Need to test and add
   appropriate backoff. (Reference implementations use 15s timeout.)
