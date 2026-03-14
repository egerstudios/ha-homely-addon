# Homely MQTT

Bridges the [Homely](https://www.homely.no) alarm system to MQTT with Home
Assistant auto-discovery. Devices appear automatically in Home Assistant once
the addon is running.

> **Note:** The Homely API is available to subscribers upon request from
> Homely support.

## Prerequisites

Before starting this addon you need:

1. **Mosquitto broker addon** — Install it from the addon store
   (*Settings → Add-ons → Add-on Store → Mosquitto broker*) and start it.

2. **A dedicated MQTT user** — The Mosquitto addon uses Home Assistant user
   accounts for authentication. Create a service account for this addon:
   - Go to *Settings → People → Users*
     (enable **Advanced mode** in your profile if the Users tab is hidden)
   - Click **Add User**
   - Set a username (e.g. `homely`) and a strong password
   - Uncheck **Can login** — this restricts it to service use only
   - Click **Create**
   - Enter this username and password in the addon's `mqtt_username` /
     `mqtt_password` config options below

3. **MQTT integration in Home Assistant** — Go to
   *Settings → Devices & Services → + Add Integration → MQTT*
   and follow the prompts. If you are using the Mosquitto addon,
   Home Assistant will likely offer to configure it automatically.

That's it. No extra YAML, no `configuration.yaml` entries needed.

## Quick start

1. Install and configure this addon (see **Configuration** below).
2. Start the addon.
3. Go to *Settings → Devices & Services → MQTT* — your Homely devices
   will appear there automatically within a few seconds.
4. Entities are immediately available for dashboards, automations, and scripts.

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

## Using the data in Home Assistant

### Finding your entities

After the addon starts, open *Settings → Devices & Services → MQTT*.
You will find:

- A **Gateway** device with alarm state, link quality, connectivity,
  battery and tamper entities.
- One **device card** per Homely sensor (door sensors, motion detectors,
  temperature probes, etc.).

All entities are also searchable from the HA search bar and can be added to
any dashboard via the normal UI.

> **Read-only:** The Homely API does not support changing the alarm state
> remotely, so there is no arm/disarm control. The integration is
> monitoring only.

### Example automations

#### Notify when the alarm is triggered

```yaml
automation:
  - alias: "Homely alarm triggered"
    trigger:
      - platform: state
        entity_id: sensor.gateway_alarm_alarmstate
        to: "Alarmed"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "Alarm has been triggered!"
          title: "Homely Alert"
```

#### Notify when a door is opened while armed

```yaml
automation:
  - alias: "Front door opened while armed"
    trigger:
      - platform: state
        entity_id: binary_sensor.frontdoor_windowsensor_alarm
        to: "on"
    condition:
      - condition: not
        conditions:
          - condition: state
            entity_id: sensor.gateway_alarm_alarmstate
            state: "Disarmed"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "Front door opened while alarm is active"
```

#### Low battery alert

```yaml
automation:
  - alias: "Homely low battery"
    trigger:
      - platform: state
        entity_id: binary_sensor.gateway_devices_battery
        to: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "One or more Homely sensors have a low battery"
```

> **Tip:** The exact entity IDs depend on your home name and device names
> in Homely. Check *Settings → Devices & Services → MQTT* or use the HA
> developer tools (*Developer Tools → States*) to find the correct IDs.

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
