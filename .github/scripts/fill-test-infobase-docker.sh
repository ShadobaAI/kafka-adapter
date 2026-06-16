#!/usr/bin/env bash
set -euo pipefail

status() {
    echo "$*"
}

base_dir="/work/base-db"

xvfb_display_number="${XVFB_DISPLAY_NUMBER:-99}"
xvfb_display=":${xvfb_display_number}"

status "Запуск Xvfb на дисплее ${xvfb_display}"
Xvfb "$xvfb_display" \
    -screen 0 1920x1080x24 \
    >/dev/null 2>&1 &
xvfb_pid=$!
openbox_pid=""
xdotool_pid=""

cleanup() {
    if [ -n "$xdotool_pid" ]; then
        kill "$xdotool_pid" 2>/dev/null || true
    fi

    if [ -n "$openbox_pid" ]; then
        kill "$openbox_pid" 2>/dev/null || true
    fi

    kill "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 50); do
    if [ -S "/tmp/.X11-unix/X${xvfb_display_number}" ]; then
        break
    fi

    if ! kill -0 "$xvfb_pid" 2>/dev/null; then
        wait "$xvfb_pid"
    fi

    sleep 0.1
done

if ! kill -0 "$xvfb_pid" 2>/dev/null; then
    echo "Xvfb не запустился на дисплее ${xvfb_display}" >&2
    exit 1
fi

status "Xvfb готов на дисплее ${xvfb_display}"
export DISPLAY="$xvfb_display"

status "Запуск openbox"
openbox >/dev/null 2>&1 &
openbox_pid=$!

(
    for _ in $(seq 1 600); do
        xdotool search --class 1cv8c \
            windowmap %@ \
            windowsize %@ 1920 1080 \
            windowmove %@ 0 0 \
            windowraise %@ >/dev/null 2>&1 || true
        sleep 0.2
    done
) &
xdotool_pid=$!

status "Заполнение тестовой информационной базы"
vrunner run \
    --ibsrv \
    --ibconnection "/F${base_dir}" \
    --command "ЗавершитьРаботуСистемы"
