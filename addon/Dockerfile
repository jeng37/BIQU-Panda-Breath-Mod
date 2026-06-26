ARG BUILD_FROM
FROM ${BUILD_FROM}

# HA base images are Alpine-based and ship bashio + s6-overlay.
RUN apk add --no-cache \
        python3 \
        py3-pip \
        openssl \
    && pip3 install --no-cache-dir --break-system-packages \
        websockets \
        requests \
        paho-mqtt

WORKDIR /app

# Single source of truth: pull Panda.py from the repo at build time. The HA add-on
# build context is the add-on folder, so we cannot COPY ../Panda.py. SOURCE_REF can
# be overridden to pin a tag/branch.
ARG SOURCE_REF=main
ADD "https://raw.githubusercontent.com/jeng37/BIQU-Panda-Breath-Mod/${SOURCE_REF}/Panda.py" /app/Panda.py

COPY run.sh /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
