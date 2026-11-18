# Local osmium-tool for clipping map extracts when osmium isn't installed on the host.
# Built automatically by the pipeline as `within-reach-osmium:1`. CI installs osmium natively.
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends osmium-tool \
 && rm -rf /var/lib/apt/lists/*
