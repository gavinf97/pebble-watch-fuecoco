# Use Ubuntu 24.04 as the stable base
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/root/.local/bin:${PATH}"

# 1. Install System Dependencies & Graphical Libs for Emulator
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    libsdl2-dev \
    libfdt1 \
    libpixman-1-0 \
    qemu-system-arm \
    gcc-arm-none-eabi \
    x11-apps \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# 2. Install 'uv' (Modern Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install the RePebble Tool via uv
RUN uv tool install pebble-tool --python 3.12

# 4. Install the SDK Core (Flint/Emery support)
# 'yes' accepts the analytics prompts automatically
RUN yes | pebble sdk install latest

WORKDIR /workspaces/fuecoco-face