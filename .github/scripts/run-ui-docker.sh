#!/usr/bin/env bash
set -euo pipefail

status() {
    echo "$*"
}

base_dir="/work/base-ui"
exit_code_path="/work/exit-code.txt"
client_log_path="/work/1cv8c.log"
client_command_log_path="/work/1cv8c-command.log"
ibsrv_log_path="/work/ibsrv.log"

coverage_debug_port="1550"
coverage_debug_url="http://127.0.0.1:${coverage_debug_port}"
coverage_output_path="/work/genericCoverage.xml"
coverage_log_path="/work/coverage41c.log"
dbgs_log_path="/work/dbgs.log"

ibsrv_pid=""
xvfb_pid=""
openbox_pid=""
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

    for _ in $(seq 1 120); do
        if timeout 1 bash -c ":</dev/tcp/${host}/${port}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
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

    if [ -n "$openbox_pid" ]; then
        kill "$openbox_pid" 2>/dev/null || true
    fi

    if [ -n "$dbgs_pid" ]; then
        kill "$dbgs_pid" 2>/dev/null || true
    fi

    if [ -n "$xvfb_pid" ]; then
        kill "$xvfb_pid" 2>/dev/null || true
    fi

    if [ -n "$ibsrv_pid" ]; then
        kill "$ibsrv_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT

onecv8_root="$(find /opt/1cv8/x86_64 -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -V | tail -n 1 || true)"
if [ -z "$onecv8_root" ] || [ ! -x "$onecv8_root/ibsrv" ] || [ ! -x "$onecv8_root/1cv8c" ]; then
    echo "Не найден каталог платформы 1С в /opt/1cv8/x86_64" >&2
    exit 1
fi

mkdir -p /work

status "Запуск ibsrv для $base_dir"
"$onecv8_root/ibsrv" \
    --db-path="$base_dir" \
    >"$ibsrv_log_path" 2>&1 &
ibsrv_pid=$!

if ! wait_for_tcp 127.0.0.1 8314 || ! kill -0 "$ibsrv_pid" 2>/dev/null; then
    echo "ibsrv не запустился на порту 8314" >&2
    cat "$ibsrv_log_path" >&2 || true
    exit 1
fi

status "ibsrv готов на порту 8314"

xvfb_display_number="${XVFB_DISPLAY_NUMBER:-99}"
xvfb_display=":${xvfb_display_number}"

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
status "Запуск openbox"
DISPLAY="$xvfb_display" openbox >/dev/null 2>&1 &
openbox_pid=$!

status "Вывод лога 1cv8c: $client_log_path"
: >"$client_log_path"
tail -n +1 -f "$client_log_path" &
tail_pid=$!

start_coverage

status "Запуск менеджера тестирования 1cv8c"
set +e
DISPLAY="$xvfb_display" \
    "$onecv8_root/1cv8c" ENTERPRISE \
        /WS http://localhost:8314/ /N"Администратор" \
        /DisableStartupMessages /DisableStartupDialogs /UseHwLicenses- /TESTMANAGER \
        /Execute"/work/vanessa-automation-single.epf" \
        /C"WorkspaceRoot=/work;VAParams=/work/VAParams.json;StartFeaturePlayer;QuietInstallVanessaExt;exitCodePath=${exit_code_path}" \
        /out"$client_log_path" \
        >"$client_command_log_path" 2>&1
set -e

stop_coverage

sleep 0.2
kill "$tail_pid" 2>/dev/null || true
wait "$tail_pid" 2>/dev/null || true
tail_pid=""

if [ ! -f "$exit_code_path" ]; then
    echo "Файл кода завершения тестов не был создан: $exit_code_path" >&2
    exit 2
fi

status "Чтение статуса тестов: $exit_code_path"
test_rc="$(tr -d '[:space:]' <"$exit_code_path")"
test_rc="${test_rc#$'\xef\xbb\xbf'}"

case "$test_rc" in
    0)
        echo "Код завершения тестов 0: ошибок при выполнении сценариев не было."
        exit 0
        ;;
    1)
        echo "Код завершения тестов 1: были ошибки выполнения сценариев." >&2
        exit 1
        ;;
    2)
        echo "Код завершения тестов 2: возникла ошибка в шаге контекста, подключения клиента тестирования или сетевого взаимодействия." >&2
        exit 2
        ;;
    3)
        echo "Код завершения тестов 3: не найден ни один сценарий для выполнения." >&2
        exit 3
        ;;
    4)
        echo "Код завершения тестов 4: не удалось выполнить тихую установку внешней компоненты." >&2
        exit "$test_rc"
        ;;
    *)
        echo "Некорректный код завершения тестов: $test_rc" >&2
        exit 2
        ;;
esac
