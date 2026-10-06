# What does this implement/fix?

Updates Yandex Music Connect (Ynison) from v3.4.2 to v4.3.7. It uses a linked
Yandex Music account and Music Assistant's player-owned AudioSource lifecycle,
adds repeat/shuffle and logical queue navigation, and fixes heartbeat and
connection recovery. Playback uses one fixed PCM format per session; dynamic
format restarts are excluded from this change.

Existing own-credential or automatic-player configurations require reconfiguration
to select a Yandex Music account and a concrete player. The device name follows
the selected player's name. Credentials are not transferred between providers.

**Related issue (if applicable):** [provider #125](https://github.com/trudenboy/ma-provider-yandex-ynison/issues/125)

## Types of changes

- [x] Bugfix (non-breaking change which fixes an issue) — `bugfix`
- [ ] New feature (non-breaking change which adds functionality) — `new-feature`
- [x] Enhancement to an existing feature — `enhancement`
- [ ] New music/player/metadata/plugin provider — `new-provider`
- [x] Breaking change (fix or feature that would cause existing functionality to not work as expected) — `breaking-change`
- [ ] Refactor (no behaviour change) — `refactor`
- [ ] Documentation only — `documentation`
- [ ] Maintenance / chore — `maintenance`
- [ ] CI / workflow change — `ci`
- [x] Dependencies bump — `dependencies`

## Checklist

- [ ] The code change is tested and works locally.
- [ ] `pre-commit run --all-files` passes.
- [ ] `pytest` passes, and tests have been added/updated under `tests/` where applicable.
- [ ] For changes to shared models, the companion PR in `music-assistant/models` is linked.
- [ ] For changes affecting the UI, the companion PR in `music-assistant/frontend` is linked.
- [ ] I have read and complied with the project's [AI Policy](https://github.com/music-assistant/.github/blob/main/AI_POLICY.md) for any AI-assisted contributions.
