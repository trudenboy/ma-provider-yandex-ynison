---
id: "0006"
title: "Passthrough-aware stream chain: no-hint lossless floor + drop inner ffmpeg -re + player-rate snap + log output rate"
size: L
status: done
priority: P2
effort_minutes: 30
feature_id:
---

## Problem Statement

Since upstream MA gained the realtime `AudioSource` passthrough fast path
(`select_pcm_format` short-circuits for `AUDIO_SOURCE`, and the per-item
stream iterator forwards the provider's PCM bytes directly when the declared
format already matches what the player can accept), MA's outer ffmpeg step is
skipped during normal playback. The PCM format this plugin produces is no
longer an intermediate that a second ffmpeg pass re-derives — **it is the
audio delivered to the player**. Two choices made before the passthrough
landed now degrade the otherwise-lossless path in ways a listener can hear:

1. **No-hint lossless floor is 48 kHz.** When the pre-play format pre-fetch
   does not return in time (slow/erroring Yandex API), the lossless profile
   falls back to 48 kHz. The bulk of the Yandex lossless catalogue is
   CD-rate (44.1 kHz) FLAC, so the fallback forces a 44.1 → 48 kHz resample
   inside the per-track decode. Before the passthrough existed, a second
   ffmpeg pass was resampling anyway, so this was invisible; now it is the
   only processing in the chain and it directly colours the output. The
   44.1 kHz floor was the default before v3.0.0 — v3.0.0 raised it to 48 kHz,
   a decision worth reopening now that the trade-off has changed.
2. **The per-track decode paces itself with `-re`.** MA's realtime path
   already paces the delivered PCM at native rate. Pacing the per-track
   decode a second time pins it to 1× as well, so it cannot read ahead of
   the player; a CDN hiccup is felt immediately as an underrun instead of
   being absorbed by buffered decoded audio.
3. **The per-track stream log cannot prove rate passthrough.** The
   "Streaming track …" line prints only the output *content type*
   (`pcm_s16le` / `pcm_s24le`) next to the full source `audio_format`. The
   output **sample rate is never logged**, and content type encodes bit
   depth only — so a 44.1 ↔ 48 kHz resample on a mismatched track is
   invisible in the one log line an operator would use to verify it.
   "input matches output" in today's log proves codec/bit-depth
   passthrough, not rate passthrough.

A fourth issue is about cost rather than audible fidelity:

4. **The declared rate ignores the target player's capabilities.** Both the
   no-hint floor and the format hint derive the declared PCM rate from the
   *source* (or explicit config) — never from the player. When the source
   rate is one the player cannot accept — e.g. a 96 kHz Hi-Res track on a
   48 kHz-only Chromecast — MA's `_select_audio_source_pcm_format` snaps the
   rate down to the closest supported value, which means the declared format
   no longer matches the consumer format and the passthrough fast path
   misses. MA then spins up its **own** resampling ffmpeg
   (`get_media_stream`) on top of the per-track decode: two ffmpeg processes
   run for one track, and 96 kHz / 24-bit PCM crosses the localhost boundary
   only to be halved immediately. The per-track decode is already running and
   already resamples on seek, so folding the player-snap into it costs
   nothing extra and keeps MA on the zero-ffmpeg fast path. This does not
   change *which* resample happens (same source→player-rate conversion, same
   resampler) — it just removes the redundant second process and the wasted
   localhost bandwidth.

## Solution Summary

Lower the no-hint lossless PCM floor back to 44.1 kHz so a missing format
hint preserves CD-rate lossless instead of resampling it, and stop pacing the
per-track decode with `-re` so MA's realtime pacer is the single pacing
authority and a small read-ahead buffer can absorb CDN jitter. Explicit
`output_sample_rate` / `output_bit_depth` overrides and the hint-driven auto
path are unchanged — only the *no-hint* fallback rate and the *internal*
pacing flag move. Additionally, when the target player is resolvable, snap
the declared PCM sample rate down to the closest rate the player actually
supports (mirroring MA's `_select_audio_source_pcm_format`) before freezing
the session format, so the per-track decode performs the one necessary
source→player resample and MA stays on the zero-ffmpeg passthrough fast path
instead of spawning a second resampling ffmpeg. The snap is best-effort: when
no target player can be resolved at format-decision time, behaviour is
unchanged. Explicit `output_sample_rate` always wins over the snap. Separately,
enrich the per-track stream log so it carries the output sample rate and bit
depth alongside the source format, making rate passthrough (or a resample)
directly observable instead of inferred.

## Acceptance Criteria

1. With no format hint available and a lossless-quality linked provider, the
   plugin declares a **44.1 kHz / 24-bit** PCM format (was 48 kHz / 24-bit);
   the lossy no-hint profile (44.1 kHz / 16-bit) is unchanged.
2. A real format hint still wins over the floor: a 96 kHz / 24-bit Hi-Res
   hint yields a 96 kHz / 24-bit declared format, and a 48 kHz hint yields
   48 kHz — the floor only applies when the hint is absent.
3. Explicit `output_sample_rate` / `output_bit_depth` values still override
   both the hint and the floor exactly as before.
4. The per-track decode is invoked **without** `-re`; the realtime pacer
   remains the only component pacing delivery, and back-pressure through the
   generator chain still bounds memory (no unbounded read-ahead).
5. A before/after measurement under simulated CDN jitter (e.g. throttled or
   stalled source reads) is recorded in the PR: read-ahead buffer depth
   and/or underrun count, demonstrating the `-re` removal does not regress
   steady-state playback and ideally improves jitter tolerance.
6. The per-track stream log line includes the **output sample rate and bit
   depth** (e.g. `→ pcm_s24le/44100Hz/24bit`) next to the source
   `audio_format`, so an operator can read input-vs-output rate directly
   from one line. No private symbols / internal paths are added to the
   message text beyond what is already logged.
7. The `CLAUDE.local.md` "Auto-detection (no hint)" line and the doc-pinning
   test introduced by spec 0002 are updated in the same PR so the documented
   lossless profile matches the new 44.1 kHz floor (no stale `24-bit/48kHz`
   assertion left behind).
8. `CHANGELOG.md` gains a single new version block describing the
   user-observable changes (CD-rate lossless preserved on the no-hint path;
   smoother playback under network jitter; fewer resamples / lower CPU and
   local bandwidth when the source rate exceeds what the player supports),
   and `VERSION` is bumped.
9. When a target player is resolvable and the otherwise-chosen rate
   (hint, floor, or source) is **not** in that player's supported sample
   rates, the declared PCM sample rate is snapped to the highest supported
   rate `<= chosen` (or the lowest supported rate when none is `<= chosen`),
   matching MA's `_select_audio_source_pcm_format` so the AudioSource fast
   path is hit and **no `get_media_stream` ffmpeg runs** for that session.
   Bit depth and channel count are not changed by the snap.
10. The snap is best-effort and never blocks setup: when no target player can
    be resolved at format-decision time, or the chosen rate is already
    supported, the declared rate is left exactly as the hint/floor/source
    logic produced it (current behaviour). A resolution failure logs at debug
    and falls through — it does not raise.
11. An explicit `output_sample_rate` override is **not** subject to the snap:
    it wins over the player's supported set exactly as it wins over the hint
    and floor (precedence: explicit override > player-snap > hint > floor).
    A user who forces a rate the player cannot accept keeps that rate and
    accepts MA's resample, preserving the "explicit always wins" contract.

## Test Plan

- Unit: a test pinning the no-hint lossless profile asserts the declared
  format is 44.1 kHz / 24-bit when the linked provider reports a
  lossless quality and no hint is supplied (red on the current 48 kHz
  constant, green after the change).
- Unit: a hint-precedence test feeds a 96 kHz / 24-bit source
  `audio_format` and asserts the declared format lifts to 96 kHz / 24-bit,
  guarding that the floor change did not break hint promotion.
- Unit: an override-precedence test sets an explicit
  `output_sample_rate` and asserts it wins over both hint and floor.
- Unit: assert the per-track decode's extra input args no longer contain
  `-re` (and that the realtime delivery path is unaffected).
- Unit: capture the per-track stream log (e.g. `caplog`) and assert the
  emitted message contains the output sample rate and bit depth, not just
  the content type — red against the current format string, green after.
- Unit: with a stub target player whose supported rates are `{44100, 48000}`
  and a 96 kHz source hint, assert the declared rate snaps to 48 kHz (highest
  supported `<= 96000`) and that no MA `get_media_stream` ffmpeg is required
  (declared format equals the format MA's `_select_audio_source_pcm_format`
  would pick).
- Unit: with the same stub player and a 48 kHz source, assert the declared
  rate is left at 48 kHz untouched (already supported → no snap, no churn).
- Unit: with no resolvable target player, assert the declared rate equals the
  hint/floor/source result (snap is skipped) and setup does not raise.
- Unit: with an explicit `output_sample_rate=96000` and a player supporting
  only `{44100, 48000}`, assert the declared rate stays 96 kHz (override beats
  the snap).
- Doc: update spec 0002's `test_docs.py` assertion to the new
  `24-bit/44.1kHz` (or constant-derived) substring; full `uv run pytest`
  green.
- Manual: play a CD-rate lossless track with the format pre-fetch disabled
  / forced to time out and confirm the source is delivered without
  resampling (passthrough fast path active — no `media_stream` ffmpeg in
  `/proc` beyond the player bridge). Then play across a deliberately
  throttled network link and confirm no audible underruns versus the
  current `-re` build.

## Sequence Diagram

```mermaid
sequenceDiagram
    participant CDN as Yandex CDN
    participant YM as yandex_music provider
    participant IFF as per-track ffmpeg (decode→PCM)
    participant GEN as plugin get_audio_stream()
    participant PACER as MA realtime_pcm_pacer
    participant PL as Player

    Note over IFF: today: -re pins decode to 1×<br/>proposed: no -re, pull-paced only
    CDN->>YM: compressed FLAC/MP3/AAC
    YM->>IFF: source bytes
    Note over IFF: decode resamples source→declared rate;<br/>declared rate pre-snapped to a player-supported value
    IFF->>GEN: fixed PCM (44.1/48/96k · 16/24-bit)
    GEN->>PACER: PCM chunks (pull)
    Note over PACER: declared format == player-supported<br/>→ passthrough, no MA outer ffmpeg
    PACER->>PL: paced PCM at native rate
    Note over PACER,PL: pacer back-pressures GEN→IFF→YM,<br/>bounding read-ahead even without -re
```

## Data Model

No new persisted state and no schema change. The declared PCM format
(`content_type`, `sample_rate`, `bit_depth`, `channels`) remains a derived,
in-memory value frozen per streaming session. This spec only widens the
inputs to its derivation:

| Input | Source | Precedence |
|-------|--------|-----------|
| Explicit `output_sample_rate` / `output_bit_depth` | provider config | highest (unchanged) |
| Target player supported sample rates | `Player.get_supported_sample_rates()`, read at format-decision time via the already-resolved target player | applied as a downward snap to the chosen rate; below explicit override |
| Format hint | `stream_details.audio_format` from the pre-play pre-fetch | below the player-snap (the snap may lower a hinted rate the player can't accept) |
| No-hint floor | quality-tier constant (lossless → 44.1 kHz / 24-bit, lossy → 44.1 kHz / 16-bit) | lowest |

The player-supported rate set is read transiently each time the format is
(re)derived; nothing is cached or written back, so a player capability change
is picked up on the next session without invalidation logic. Bit depth and
channel count are outside the snap — only the sample rate is adjusted to land
on the passthrough fast path.
