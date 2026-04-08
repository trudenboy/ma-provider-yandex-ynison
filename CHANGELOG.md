# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-04-08

### Added
- Ynison WebSocket client with two-step connection (redirector + state service)
- Plugin provider with `PluginSource` and `AUDIO_SOURCE` feature
- Audio streaming via linked Yandex Music provider with ffmpeg PCM conversion
- Continuous stream with automatic track change detection
- QR code authentication (shared with Yandex Music provider)
- Playback control: play/pause, next/previous, seek, volume
- Auto and manual MA player selection
- Player switch protection option
- Device registration with persistent device ID
- Reconnection with exponential backoff
- Cover art display from Ynison state
- Docker Compose dev environment for local testing

## [Unreleased]
