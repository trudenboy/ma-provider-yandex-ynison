# Reverse-sync: upstream PR #6595

## Provenance

- Upstream: https://github.com/music-assistant/server/pull/6595
- Provider: https://github.com/trudenboy/ma-provider-yandex-ynison/pull/172
- Test baseline: Music Assistant `f99b36215310f3e09052ff2f1df37576e849405d`
  and models `1.1.214`.

## Problem and contract

Music Assistant replaced throttler bypass with request priorities. Track playback
must request stream details at HIGH priority while continuing to count toward the
request budget. Format prefetch retains its caller's NORMAL priority. The scoped
priority must restore the previous value after success or an exception.

Keep the provider's narrow MusicAssistantError recovery: an unexpected
RuntimeError must propagate rather than silently ending playback.

## Compatibility

Refresh the test lock to the matching server and models. The setup-session test
double accepts the current Mapping of strings or SetupFlowError objects. Include
the server's pinned hass-client in test dependencies because importing the server
now imports that client; runtime provider requirements do not change.

## Verification

- Removing the HIGH scope reproduces the failing playback-priority regression.
- Tests cover playback HIGH, prefetch NORMAL, and restoration after RuntimeError.
- Full unit suite: 398 tests; Ruff lint/format and mypy pass.
- Local unit environment omits torch and torchaudio because their download host
  is unavailable. The suite stubs the audio-analysis dependencies. GitHub CI
  remains the gate for a complete dependency installation.
