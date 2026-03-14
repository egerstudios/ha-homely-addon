#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Homely MQTT Bridge..."
exec python3 /opt/homely2mqtt.py
