# Live Ynison Protocol Research: Official Android Client

Date: 2026-09-01

## Scope

This session observed an official Yandex Music Android client controlling a real
Yandex Station and a Music Assistant Ynison device on the same account. The goal
was to validate protocol assumptions used by this provider, not to extract
credentials or bypass application protections.

Environment:

- Yandex Music Android `2026.08.3 #161gpr` on Android 17;
- a real Yandex Station (`DEVICE_STATION` below);
- Music Assistant with this provider (`DEVICE_MA` below);
- an official Android client (`DEVICE_PHONE` below);
- RADIO/My Wave queue playback.

All identifiers in this document are aliases. OAuth values, redirect tickets,
session IDs, real device IDs, queue IDs, and account data were not retained.

## Collection Method

1. ADB was used to operate the official client and inspect Android media-session
   state.
2. A temporary mitmproxy CA was installed and a system proxy was enabled through
   `adb reverse`.
3. The app rejected the user CA for Yandex Music and Ynison hosts before HTTP or
   WebSocket traffic was available. No pinning or trust-manager bypass was
   attempted.
4. The proxy was removed, and the current provider's debug logging was used as
   the server-side observation point. This captured the JSON state that Ynison
   delivered to a real provider session.
5. Temporary instrumentation emitted a sanitized trace containing aliases,
   message kinds, queue sizes, version authors, playback flags, and timing. The
   instrumentation was kept outside this repository and removed after the run.
6. The installed APK was decompiled to map protocol models and command classes.
   This was static inspection only; no application code was modified or run.

## Confirmed Protocol Behaviour

### Device transfer to Music Assistant

Selecting `DEVICE_MA` while playback was paused produced a state with:

- `active_device_id_optional = DEVICE_MA`;
- the existing RADIO queue and index unchanged;
- `status.paused = true`;
- `status.version.device_id = DEVICE_PHONE`.

Pressing play in the Android client then produced a phone-authored status update
with the same queue. Music Assistant started the AudioSource at the reported
progress and playback was audible.

### Official client commands

The following commands all arrived with `status.version.device_id = DEVICE_PHONE`:

- play and pause;
- a seek performed by tapping the Android seek bar;
- next-track navigation.

The seek interaction emitted multiple legitimate states: pause, play, then a new
paused position. Consumers must not assume one UI seek gesture maps to exactly one
Ynison state or that the final paused flag equals the initial flag.

Next-track navigation changed both `current_playable_index` and the current
playable ID. When issued while paused, the next item remained paused at zero.
When issued while playing, the next item remained playing at zero.

### Provider heartbeat echoes

`update_playing_status` responses were materially different from the current
echo-detection assumption. Ynison returned:

```json
{
  "status": {
    "version": {
      "device_id": "",
      "version": "0",
      "timestamp_ms": "0"
    }
  }
}
```

The empty version was repeated for periodic progress updates. Responses arrived
about 15-48 ms after the corresponding outbound heartbeat. Progress normally
matched exactly and differed by 1 ms in one sample. It was also present in state
returned after the provider extended a RADIO queue through `update_player_state`.

This contradicts the comment in `provider/ynison_client.py` that the provider's
device ID is preserved end-to-end after server restamping. With the current
AND-authorship rule, these provider-originated updates are classified as external
events and repeatedly reach the playback handler.

### RADIO replenishment

At index 7 of a 9-item RADIO queue, the provider requested five rotor tracks,
extended the queue to 14 items, and published the new state. The official client
continued playback and reflected the extended queue. This validates the current
near-tail replenishment approach against a live RADIO session.

### Transfer from Music Assistant to Yandex Station

Selecting `DEVICE_STATION` while Music Assistant was playing first delivered:

```json
{
  "status": {
    "paused": true,
    "version": {
      "device_id": "server-paused-on-active-device-disconnecting"
    }
  }
}
```

The raw disconnect message omitted `active_device_id_optional`. The client's
parsed state still identified `DEVICE_MA` as active because `_parse_state()`
preserves the previous value whenever this field is absent. Music Assistant
stopped its local stream, while playback continued on the Station.

The literal author value is therefore a server control sentinel, not a normal
device ID. It should be represented as a named protocol constant if code needs to
branch on it.

### Passive-event muting and transfer back

The provider registers with `mute_events_if_passive=true`. After transfer to the
Station, it received no Station progress/state updates. When the Android client
selected `DEVICE_MA` again, the official UI showed Music Assistant as selected,
but the provider did not receive the current playing state and remained stopped.
It later received retained copies of the server-disconnect pause instead.

This is a live interoperability failure: the provider cannot reliably observe a
transfer back after another device becomes active.

A follow-up live run registered with `mute_events_if_passive=false`. Ynison
accepted the parameter, but the provider still received neither the Station's
active-device transition nor its playing progress. It retained the stale
`DEVICE_MA`, paused state while the official client showed the Station playing.
Changing this flag alone is therefore not a fix.

### Session parameter and resynchronization matrix

Four registration variants were compared against the same retained account
state:

- the provider baseline;
- no `update_session_params` message;
- `mute_events_if_passive=false` before `update_full_state`;
- `mute_events_if_passive=false` after `update_full_state`.

Every variant received the same retained paused queue and not the state of the
Station that had been playing. The registration order did not change the result.

`sync_state_from_eov` with an empty queue ID produced no fresh Station state while
the provider was passive. The retained queue itself had an empty queue ID, so a
genuinely non-empty `actual_queue_id` could not be tested. Running sync before or
after `update_active_device(DEVICE_MA)` also did not recover Station progress. The
claim changed the observed active device to `DEVICE_MA` but left the stale paused
queue and progress intact. The official Station continued playing, demonstrating
that the observed Ynison ownership and physical playback could diverge.

Selecting `DEVICE_MA` in the official Android client behaved differently: the
phone published its current queue and status while transferring ownership. That
phone-authored state allowed Music Assistant playback to start correctly.

### Seek race and natural track completion

A phone-authored seek was followed once by an older provider heartbeat before the
new position arrived. Ordering is therefore not guaranteed across the phone's
state update and an already in-flight provider heartbeat. Echo suppression must
not allow that older heartbeat to overwrite the newer seek.

Natural completion was observed through multiple RADIO tracks. The provider:

- sent a final progress update at duration;
- advanced `current_playable_index`;
- started the next playable at zero;
- continued to replenish the RADIO queue near its tail.

At the exact end boundary, an empty-version completion response was treated as an
external seek by the current authorship logic. This is the same empty-version
heartbeat issue, but on a delivery-critical state transition.

### Repeat semantics

The official client published phone-authored queue states for `repeat_mode=ALL`
and `repeat_mode=ONE`. The queue version changed while the status version could
remain unchanged, confirming that repeat is a queue option rather than a playback
status command.

With `repeat_mode=ONE`, natural completion in Music Assistant still advanced from
the current index to the next index. The provider's completion path always uses
`current_playable_index + 1` and does not consult `player_queue.options`. Repeat
ONE is therefore synchronized in the UI but not implemented in playback.

### Shuffle and queue editing

The live shuffled queue contained:

```json
{
  "shuffle_optional": {
    "playable_indices": ["one entry per playable"]
  }
}
```

There were eight shuffle indices for eight playables. Shuffle is not represented
by `options.shuffle` or by simply replacing `playable_list`; it is an optional
index mapping alongside the original list. A queue-item context menu exposed
`Remove from queue`, and using it changed the visible queue. Passive-event muting
prevented that first edit from being captured as a live inbound wire diff.

Static command classes in the official client independently confirm the Ynison
queue editing surface:

- `YnisonEditQueueCommand.AddNext` with a playable list;
- `YnisonEditQueueCommand.AddLast` with a playable list;
- `YnisonEditQueueCommand.RemoveAt` with a queue position;
- `YnisonEditQueueCommand.Move` with `from` and `to` positions.

The generated queue model contains field 7, `shuffle_optional`, whose nested
message is a repeated integer `playable_indices` list. `SetShuffleCommand` also
carries a boolean, an optional new original position, and optional shuffle
positions. These models establish the data shape, but not the exact JSON envelope
used for every edit.

### Reconnect, errors, and authentication expiry

A controlled WebSocket close scheduled reconnect after approximately five
seconds and recovered successfully. An invalid JSON frame produced a text error
response with gRPC code 2 and HTTP code 500, followed by transport loss. Two
successive reconnects were scheduled after 5.5 and 4.1 seconds because each
successful connection reset the local attempt counter. Neither redirect response
included server backoff or go-away headers.

Authentication expiry exposed a separate failure mode. After replacing the token
with a known invalid value and closing the established socket, the redirect
WebSocket handshake still succeeded. Its response omitted `host` and
`redirect_ticket` rather than returning an HTTP 401 or 403. The client raised a
generic `ConnectionError`, so its `LoginFailed` branch and token-refresh callback
were never reached. It then used the local jittered schedule at roughly 5, 10,
and 30 seconds while repeatedly retrying the same invalid token.

This means the existing refresh path handles handshake authentication errors but
not the invalid-token response produced by the live redirector.

## Static Official-Client Evidence

The installed APK contains generated Ynison protocol symbols for:

- `ynison_redirect.YnisonRedirectService` and
  `ynison_state.YnisonStateService`;
- `Ynison-Device-Info`, `Ynison-Backoff-Millis`, `Ynison-Error-Code`, and
  `Ynison-Go-Away-For-Seconds` headers;
- queue commands for add-next, add-last, move, remove, next, back, original
  position, repeat, reverse, and shuffle;
- a generated queue field `shuffle_optional.playable_indices` and command models
  carrying shuffle positions;
- separate channel error categories for I/O, generic channel, and Ynison errors.

These symbols do not prove wire semantics by themselves, but they identify useful
future capture targets. In particular, the provider currently handles only a
subset of the official queue and server-directed backoff surface.

## Recommended Changes

### P0: Restore transfer back from passive devices

Determine how the official client re-synchronizes after passive playback and
implement an explicit refresh or reconnect strategy. Do not merely change
`mute_events_if_passive`: a live test with `false` still missed the Station state.

Required regression test:

- connect/register;
- become passive after a server-disconnect pause;
- request or receive current peer state while passive or on reactivation;
- become active again and resume from the latest progress.

### P0: Replace authorship-only heartbeat echo detection

Do not treat `status.version.device_id` as a reliable provider-origin marker for
`update_playing_status`; live responses use the empty/zero version block.

A safer design needs an outbound status watermark containing track, paused flag,
progress, duration, and send time. An inbound empty-version status can be treated
as a probable echo only when it matches a recent watermark within bounded timing
and progress tolerances. Queue changes and phone-authored status updates must
continue through the handler.

Required regression tests:

- matching empty-version heartbeat is suppressed;
- phone-authored play/pause with identical values is not suppressed;
- queue change plus matching heartbeat is not suppressed;
- expired watermark is not suppressed;
- seek sequences containing pause/play/new-position remain observable.

### P0: Clear stale ownership on the disconnect sentinel

Do not retain `active_device_id` when a server-authored
`server-paused-on-active-device-disconnecting` status arrives without an active
device field. Treat this specific combination as ownership becoming unknown; do
not globally interpret every omitted field as a clear because ordinary Ynison
messages are partial updates.

Required regression tests:

- an ordinary status-only update preserves active ownership;
- the disconnect sentinel without `active_device_id_optional` clears ownership;
- a subsequent phone-authored transfer establishes the new active device.

### P0: Implement synchronized repeat and shuffle semantics

Honor `repeat_mode=ONE` at natural completion by restarting the current playable.
Define and test end-of-queue behavior for `ALL` and `NONE`. Parse and preserve
`shuffle_optional.playable_indices`; advancing a shuffled queue must follow that
mapping rather than assuming original-list index order.

Required regression tests:

- ONE restarts the current item at zero;
- ALL wraps at the logical end;
- NONE stops at the logical end;
- shuffle mapping determines next and previous while preserving the original
  playable list;
- queue remove and move keep current and shuffled positions coherent.

### P1: Refresh authentication on an empty redirect ticket

The live redirector did not use a 401/403 handshake for a known invalid token.
Allow a missing redirect host/ticket response to trigger one bounded credential
refresh before reverting to transient reconnect handling. The retry must be
bounded so malformed server responses cannot create a refresh loop.

Required regression tests:

- 401/403 still raises `LoginFailed`;
- a successful redirect handshake with no host/ticket invokes one refresh;
- a refreshed token reconnects;
- repeated empty redirects use backoff without repeatedly refreshing.

### P1: Model the server disconnect sentinel

Add a named constant for `server-paused-on-active-device-disconnecting` and a
fixture covering the transition. This allows intentional handling and prevents
the value from being mistaken for a real device.

### P2: Respect server backoff metadata

Parse `Ynison-Backoff-Millis`, `Ynison-Go-Away-For-Seconds`, and
`Ynison-Error-Code` when present. Controlled close and HTTP-500 tests did not emit
these headers, so precedence and units still require a capture where the server
actually supplies them. Until then, retain bounded local exponential backoff.

## Residual Gaps

- TLS payloads from the official app were not decrypted because the production
  app rejected user-installed CAs.
- A genuinely non-empty EOV queue ID was unavailable, so the differing-ID sync
  path was not exercised.
- Add-next, add-last, and move were confirmed statically but their complete live
  JSON diffs were not captured. Remove was exercised in the UI, but its first
  state update was suppressed while the observer was passive.
- No server-directed backoff headers were observed, so the official client's
  precedence rules remain static evidence only.
- Transport loss was represented by controlled close and server HTTP-500 paths;
  the phone's physical network was not disabled.
- The Station's own transport was observed only through shared Ynison state and
  audible behaviour, not through Station-local logs.

## Implementation Follow-up

A 4.3.0 candidate was exercised against the same official-client environment after
reconfiguring the provider to use the linked Yandex Music account and a concrete Web
player. The updated provider connected successfully and received the retained paused
RADIO queue.

The first follow-up incorrectly appeared to reproduce the transfer-back blocker. The
cause was test operation, not Ynison: coordinates read from a scaled screenshot were
sent to the larger native ADB surface, so the Music Assistant device row had not been
selected. Repeating the matrix with UIAutomator bounds moved the official-client
checkmark to Music Assistant and immediately delivered a phone-authored active-device,
queue, status, and current progress state.

Five consecutive Music Assistant-to-Station-to-Music-Assistant cycles then succeeded.
Each transfer away delivered the server disconnect sentinel without an active-device
field; the candidate cleared ownership and stopped locally. Each transfer back first
allowed a retained paused state and then delivered an authoritative phone-authored
playing state with current progress, from which Music Assistant resumed.

Live shuffle behavior confirmed the candidate's position model. For an original
index of 4 and mapping `[0, 1, 3, 4, 2]`, official Next selected original index 2.
Thus `current_playable_index` addresses `playable_list`, while
`shuffle_optional.playable_indices` defines logical playback order. RADIO append kept
the existing mapping and appended new original indices to its logical tail.

Repeat controls progressed from NONE to ALL to ONE as queue-only updates. A near-end
Repeat ONE test initially produced two completion events: Ynison attached the complete
unchanged queue to a delayed empty-version completion heartbeat, while the classifier
accepted only status-only heartbeat echoes. The classifier was tightened to accept a
matching heartbeat with an unchanged attached queue but still reject a real queue
mutation. On the repeated live test, exactly one completion occurred, the same index
and track restarted at zero, and progress increased monotonically afterward.

No server backoff/go-away response headers were obtained during the follow-up, so
their parser remains deferred rather than inferred.
