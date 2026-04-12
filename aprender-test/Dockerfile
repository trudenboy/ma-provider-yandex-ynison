FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils \
    libasound2 \
    kmod \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/aprender

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 7779

ENTRYPOINT ["/entrypoint.sh"]
