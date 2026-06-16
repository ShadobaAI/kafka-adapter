#!/usr/bin/env bash
set -euo pipefail

status() {
    echo "$*"
}

base_dir="/work/base-unit"
unit_log_path="/work/unit.log"
exit_code_path="/work/exit-code.txt"

xvfb_display_number="${XVFB_DISPLAY_NUMBER:-99}"
xvfb_display=":${xvfb_display_number}"

status "Запуск Xvfb на дисплее ${xvfb_display}"
Xvfb "$xvfb_display" \
    -screen 0 1920x1080x24 \
    >/dev/null 2>&1 &
xvfb_pid=$!
openbox_pid=""
xdotool_pid=""
tail_pid=""

cleanup() {
    if [ -n "$tail_pid" ]; then
        kill "$tail_pid" 2>/dev/null || true
    fi

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

mkdir -p /work
status "Вывод лога unit-тестов: ${unit_log_path}"
: > "$unit_log_path"
tail -n +1 -f "$unit_log_path" &
tail_pid=$!

status "Запуск unit-тестов"
set +e
{
    /opt/oscript/bin/vrunner run \
        --command "RunUnitTests=/work/YaxParams.json;workspacePath=/work" \
        --exitCodePath "$exit_code_path" \
        --ibsrv --ibconnection "/F${base_dir}" \
        --db-user "Администратор"
}
test_rc=$?
set -e

sleep 0.2
kill "$tail_pid" 2>/dev/null || true
wait "$tail_pid" 2>/dev/null || true
tail_pid=""

if [ -f "$exit_code_path" ]; then
    status "Файл кода завершения unit-тестов: ${exit_code_path}"
    cat "$exit_code_path"
else
    echo "Файл кода завершения unit-тестов не был создан: ${exit_code_path}" >&2
    exit 2
fi

exit "$test_rc"
