# Changelog

## [1.0.1] - 2026-03-14

### Fixed
- Correct alarm state key names to match API documentation (`ARMED_PARTLY`, `ALARM_PENDING`, `ALARM_STAY_PENDING`, `ARMED_NIGHT_PENDING`, `ARMED_AWAY_PENDING`). Previous keys caused unknown states when system was armed or in pre-alarm grace period.
- Handle flood sensor state name (`flood`) in addition to `alarm` — flood events were silently ignored in both WebSocket and polling paths.
- Publish alarm state with MQTT retain flag so Home Assistant shows the correct state immediately after restart instead of "unavailable".
- Guard against publishing alarm state when state string is empty.

## [1.0.0] - 2026-03-14

### Added
- Initial release
- Real-time alarm state updates via Socket.IO WebSocket
- Periodic polling fallback (configurable interval)
- MQTT auto-discovery for Home Assistant
- Gateway aggregate entities: alarm state, link quality, connectivity, battery, tamper
- Per-device entities: temperature, motion, door/window, smoke, moisture, vibration
- MQTT broker authentication support
- Flexible device detection by model name pattern (not hardcoded strings)
- Runs on amd64, aarch64, armv7, armhf, i386
