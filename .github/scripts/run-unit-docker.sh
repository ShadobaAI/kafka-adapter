#!/usr/bin/env bash
set -euo pipefail

status() {
    echo "$*"
}

base_dir="/work/base-unit"
unit_log_path="/work/unit.log"
vrunner_log_path="/work/vrunner.log"
exit_code_path="/work/exit-code.txt"

xvfb_display_number="${XVFB_DISPLAY_NUMBER:-99}"
xvfb_display=":${xvfb_display_number}"

coverage_debug_port="1550"
coverage_debug_url="http://127.0.0.1:${coverage_debug_port}"
coverage_output_path="/work/genericCoverage.xml"
coverage_log_path="/work/coverage41c.log"
dbgs_log_path="/work/dbgs.log"

xvfb_pid=""
openbox_pid=""
xdotool_pid=""
tail_pid=""
dbgs_pid=""
coverage_pid=""
coverage_started=""

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Не найдена команда $1. Пересоберите client-образ с поддержкой Coverage41C." >&2
        exit 1
    fi
}

require_edt_jar() {
    local pattern="$1"

    if [ -z "${EDT_LOCATION:-}" ] || [ ! -d "$EDT_LOCATION" ]; then
        echo "EDT_LOCATION не задан или каталог не существует: ${EDT_LOCATION:-<empty>}" >&2
        exit 1
    fi

    if ! find "$EDT_LOCATION" -maxdepth 1 -type f -name "$pattern" -print -quit | grep -q .; then
        echo "В EDT_LOCATION не найден $pattern: $EDT_LOCATION" >&2
        exit 1
    fi
}

wait_for_tcp() {
    local host="$1"
    local port="$2"

    for _ in $(seq 1 100); do
        if timeout 1 bash -c ":</dev/tcp/${host}/${port}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.2
    done

    return 1
}

stop_coverage() {
    if [ "$coverage_started" != "1" ]; then
        return 0
    fi

    status "Остановка замера покрытия"
    Coverage41C stop -i DefAlias -u "$coverage_debug_url" >>"$coverage_log_path" 2>&1 || true

    if [ -n "$coverage_pid" ] && kill -0 "$coverage_pid" 2>/dev/null; then
        kill -INT "$coverage_pid" 2>/dev/null || true
        wait "$coverage_pid" 2>/dev/null || true
    fi

    coverage_started=""

    if [ -f "$coverage_output_path" ]; then
        status "Файл покрытия: $coverage_output_path"
    else
        echo "Файл покрытия не был создан: $coverage_output_path. Лог: $coverage_log_path" >&2
    fi
}

start_coverage() {
    require_command java
    require_command dbgs
    require_command Coverage41C
    require_edt_jar "com._1c.g5.v8.dt.debug.core_*.jar"
    require_edt_jar "com._1c.g5.v8.dt.debug.model_*.jar"

    : >"$coverage_log_path"
    : >"$dbgs_log_path"

    status "Запуск сервера отладки dbgs на $coverage_debug_url"
    dbgs --addr=127.0.0.1 --port="$coverage_debug_port" >"$dbgs_log_path" 2>&1 &
    dbgs_pid=$!

    if ! wait_for_tcp 127.0.0.1 "$coverage_debug_port"; then
        echo "dbgs не запустился на $coverage_debug_url. Лог: $dbgs_log_path" >&2
        cat "$dbgs_log_path" >&2 || true
        exit 1
    fi

    local coverage_start_args=(
        start
        -i DefAlias
        -u "$coverage_debug_url"
        -o "$coverage_output_path"
    )

    if [ -n "${COVERAGE_PROJECT_DIR:-}" ]; then
        coverage_start_args+=(-P "$COVERAGE_PROJECT_DIR")
    elif [ -n "${COVERAGE_SOURCE_DIR:-}" ]; then
        coverage_start_args+=(-s "$COVERAGE_SOURCE_DIR")
    else
        echo "Не заданы исходники для покрытия. Задайте COVERAGE_PROJECT_DIR или COVERAGE_SOURCE_DIR." >&2
        exit 1
    fi

    if [ -n "${COVERAGE_EXTENSION_NAME:-}" ]; then
        coverage_start_args+=(-e "$COVERAGE_EXTENSION_NAME")
    fi

    for target in ${COVERAGE_AUTOCONNECT_TARGETS:-Client ManagedClient Server ServerEmulation}; do
        coverage_start_args+=(-a "$target")
    done

    status "Запуск замера покрытия Coverage41C"
    Coverage41C "${coverage_start_args[@]}" >>"$coverage_log_path" 2>&1 &
    coverage_pid=$!
    coverage_started="1"

    sleep 2
    if ! kill -0 "$coverage_pid" 2>/dev/null; then
        echo "Coverage41C завершился до запуска тестов. Лог: $coverage_log_path" >&2
        cat "$coverage_log_path" >&2 || true
        exit 1
    fi
}

cleanup() {
    stop_coverage

    if [ -n "$tail_pid" ]; then
        kill "$tail_pid" 2>/dev/null || true
    fi

    if [ -n "$xdotool_pid" ]; then
        kill "$xdotool_pid" 2>/dev/null || true
    fi

    if [ -n "$openbox_pid" ]; then
        kill "$openbox_pid" 2>/dev/null || true
    fi

    if [ -n "$dbgs_pid" ]; then
        kill "$dbgs_pid" 2>/dev/null || true
    fi

    if [ -n "$xvfb_pid" ]; then
        kill "$xvfb_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT

status "Запуск Xvfb на дисплее $xvfb_display"
Xvfb "$xvfb_display" \
    -screen 0 1920x1080x24 \
    >/dev/null 2>&1 &
xvfb_pid=$!

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
    echo "Xvfb не запустился на дисплее $xvfb_display" >&2
    exit 1
fi

status "Xvfb готов на дисплее $xvfb_display"
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
status "Вывод лога unit-тестов: $unit_log_path"
: >"$unit_log_path"
tail -n +1 -f "$unit_log_path" &
tail_pid=$!

start_coverage

status "Запуск unit-тестов"
vrunner_args=(
    run
    --command "RunUnitTests=/work/YaxParams.json;workspacePath=/work"
    --exitCodePath "$exit_code_path"
    --ibsrv
    --ibconnection "/F${base_dir}"
    --db-user "Администратор"
    --additional "/debug -http -attach /debuggerURL $coverage_debug_url"
)

set +e
{
    /opt/oscript/bin/vrunner "${vrunner_args[@]}"
} >"$vrunner_log_path" 2>&1
test_rc=$?
set -e

stop_coverage

sleep 0.2
kill "$tail_pid" 2>/dev/null || true
wait "$tail_pid" 2>/dev/null || true
tail_pid=""

if [ -f "$exit_code_path" ]; then
    status "Файл кода завершения unit-тестов: $exit_code_path"
    cat "$exit_code_path"
else
    echo "Файл кода завершения unit-тестов не был создан: $exit_code_path" >&2
    exit 2
fi

exit "$test_rc"
