# Homely MQTT

Bridges the [Homely](https://www.homely.no) alarm system to MQTT with Home
Assistant auto-discovery. Devices appear automatically in Home Assistant once
the addon is running.

> **Note:** The Homely API is available to subscribers upon request from
> Homely support.

## How it works

- On startup, the addon logs into the Homely cloud API, discovers all devices
  in your home, and publishes MQTT auto-discovery configs for each one.
- Real-time state changes are delivered via a Socket.IO WebSocket connection.
- A configurable polling loop (default every 120 s) refreshes all states and
  keeps the access token alive.
- If the WebSocket drops the addon exits cleanly so the HA supervisor can
  restart it.

## Entities created

### Gateway (aggregate across all devices)

| Entity | Type | Description |
|---|---|---|
| Alarm state | `sensor` | Current alarm state (Disarmed / Armed stay / Armed night / Armed away / Alarmed) |
| Link quality | `sensor` | Minimum Zigbee link strength across all devices (%) |
| Connectivity | `binary_sensor` | OFF if any device is offline |
| Battery | `binary_sensor` | ON if any device has a low battery |
| Tamper | `binary_sensor` | ON if any device has a tamper alert |

### Per device

| Sensor type | HA component | Trigger |
|---|---|---|
| Temperature | `sensor` | Device has a `temperature` feature |
| Motion | `binary_sensor` | Model name contains "motion" |
| Door / window | `binary_sensor` | Model name contains "door", "window", or unknown alarm sensor |
| Smoke | `binary_sensor` | Model name contains "smoke" |
| Moisture / flood | `binary_sensor` | Model name contains "water", "flood", or "moisture" |
| Vibration / glass-break | `binary_sensor` | Model name contains "glass" |

## Configuration

| Option | Required | Default | Description |
|---|---|---|---|
| `homely_username` | yes | — | Homely account email |
| `homely_password` | yes | — | Homely account password |
| `homely_home` | no | first home | Home name (if you have multiple locations) |
| `mqtt_host` | no | `core-mosquitto` | MQTT broker hostname |
| `mqtt_port` | no | `1883` | MQTT broker port |
| `mqtt_username` | no | — | MQTT username (if your broker requires auth) |
| `mqtt_password` | no | — | MQTT password |
| `mqtt_discovery_prefix` | no | `homeassistant` | HA MQTT discovery prefix |
| `mqtt_state_prefix` | no | `homely` | Prefix for state topics |
| `poll_interval` | no | `120` | Seconds between full status polls (30–3600) |
| `log_level` | no | `info` | Log verbosity: trace / debug / info / warning / error / fatal |

## MQTT topic layout

```
{state_prefix}/{site}_{device}_{model}/{feature}/state
```

Discovery configs are published with `retain=true` to:

```
{discovery_prefix}/{component}/{site}_{device}_{model}/{feature}/config
```
