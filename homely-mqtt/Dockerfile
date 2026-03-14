ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /opt

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    requests \
    "paho-mqtt>=2.0" \
    "python-socketio[client]"

COPY homely2mqtt.py /opt/
COPY run.sh /

RUN chmod a+x /run.sh

CMD ["/run.sh"]
