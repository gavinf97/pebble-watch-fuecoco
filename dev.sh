#!/usr/bin/env bash
set -e

# Detect docker compose command (v2 plugin vs old standalone)
if docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

CMD="${1:-help}"

xsetup() {
  xhost +local: >/dev/null 2>&1 || true
}

case "$CMD" in
  build)
    $DC run --rm pebble bash -c "pebble build"
    ;;

  emu)
    xsetup
    $DC run --rm pebble bash -c "
      pebble build && pebble install --emulator flint
      echo 'Emulator running — close this terminal or press Ctrl+C to stop.'
      sleep infinity
    "
    ;;

  watch)
    xsetup
    $DC run --rm pebble bash -c "
      pebble build && pebble install --emulator flint
      echo 'Watching src/ and resources/ for changes. Press Ctrl+C to stop.'
      while inotifywait -r -e modify,create,delete,move src/ resources/ 2>/dev/null; do
        echo '--- Change detected, rebuilding ---'
        pebble build && pebble install --emulator flint || true
      done
    "
    ;;

  install)
    PHONE_IP="${2:?Usage: ./dev.sh install <phone-ip>}"
    echo "Building and installing to Pebble at ${PHONE_IP}..."
    $DC run --rm pebble bash -c "pebble build && pebble install --phone ${PHONE_IP}"
    ;;

  screenshot)
    OUT="${2:-screenshot.png}"
    $DC exec pebble bash -c "pebble screenshot --no-open --emulator flint /workspace/${OUT}"
    echo "Saved to fuecoco-face/${OUT}"
    ;;

  icons)
    $DC run --rm pebble bash -c "python3 scripts/create_app_icons.py ."
    ;;

  gif)
    $DC run --rm pebble bash -c "python3 scripts/create_preview_gif.py . --frames 8 --delay 400"
    ;;

  shell)
    xsetup
    $DC run --rm pebble bash
    ;;

  help|*)
    cat <<'EOF'
Pebble Watch Face Dev Tool
--------------------------
First time only:
  docker compose build        Build the container (takes a few minutes)

Daily commands (run from this directory):
  ./dev.sh build              Compile the watch face -> build/pebble-app.pbw
  ./dev.sh emu                Build + install + open emulator window (leaves running)
  ./dev.sh watch              Live reload: auto-rebuild on any src/ or resources/ change
  ./dev.sh screenshot [file]  Capture a PNG from the emulator started by `emu`
                              (run in a second terminal while `emu` is still running)
  ./dev.sh install <ip>       Build + install to physical Pebble (enable Developer
                              Connection in the Pebble phone app to get the IP)
  ./dev.sh icons              Generate icon_80x80.png / icon_144x144.png from a screenshot
  ./dev.sh gif                Generate a rollover preview GIF from the emulator
  ./dev.sh shell              Drop into a shell inside the build container

Swap the Fuecoco artwork:
  Replace fuecoco-face/resources/images/fuecoco_body.png and fuecoco_flame.png
  with any pure black/white PNG at the same pixel dimensions (110x80 and 26x30),
  then run ./dev.sh emu (or it auto-reloads in watch mode). Or edit and re-run
  fuecoco-face/scripts/generate_fuecoco_art.py to regenerate them procedurally.
EOF
    ;;
esac
