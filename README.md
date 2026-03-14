# ha-homely-addon

Home Assistant addon repository for integrating the [Homely](https://www.homely.no)
alarm system via MQTT.

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fegerstudios%2Fha-homely-addon)

## Addons

### [Homely MQTT](homely-mqtt/)

Bridges the Homely alarm system to MQTT with full Home Assistant auto-discovery.

- Real-time updates via Socket.IO WebSocket
- Polling fallback every 2 minutes (configurable)
- Auto-discovers alarm state, temperature sensors, motion detectors,
  door/window sensors, smoke detectors, and more
- MQTT authentication support
- Runs on amd64, aarch64, armv7, armhf, i386

See [DOCS.md](homely-mqtt/DOCS.md) for full configuration options.

## Installation

1. Click the button above, or add this URL manually in
   **Settings → Add-ons → Add-on Store → ⋮ → Repositories**:
   ```
   https://github.com/egerstudios/ha-homely-addon
   ```
2. Install the **Homely MQTT** addon.
3. Configure your Homely credentials in the addon options.
4. Start the addon.

## Requirements

- A Homely alarm subscription with API access (request from Homely support)
- An MQTT broker (the [Mosquitto](https://github.com/home-assistant/addons/tree/master/mosquitto) addon works out of the box)

## License & attribution

This project is licensed under the [GNU Affero General Public License v3](LICENSE) (AGPL-3.0).

It is a Home Assistant addon reimplementation based on the concepts and API knowledge from
[homely-tools](https://github.com/hansrune/homely-tools) by
[hansrune](https://github.com/hansrune), which is also licensed under AGPL-3.0.
