# Changelog

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
