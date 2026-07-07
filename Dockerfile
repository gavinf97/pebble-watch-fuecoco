FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/root/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pil \
    inotify-tools \
    libsdl2-dev \
    libfdt1 \
    libpixman-1-0 \
    qemu-system-arm \
    gcc-arm-none-eabi \
    x11-apps \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN uv tool install pebble-tool --python 3.12

# Accept analytics prompt automatically
RUN yes | pebble sdk install latest

WORKDIR /workspace
