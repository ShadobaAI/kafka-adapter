#!/usr/bin/env bash
set -euo pipefail

status() {
    echo "$*"
}

assets_dir="${ASSETS_DIR:-assets}"
ui_dir="/work/${assets_dir}/ui"
base_dir="${ui_dir}/base-ui"
exit_code_path="${ui_dir}/exit-code.txt"
client_log_path="${ui_dir}/1cv8c.log"
onecv8_root="$(find /opt/1cv8/x86_64 -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -V | tail -n 1 || true)"

if [ -z "$onecv8_root" ] || [ ! -x "$onecv8_root/ibsrv" ] || [ ! -x "$onecv8_root/1cv8c" ]; then
    echo "Не найден каталог платформы 1С в /opt/1cv8/x86_64" >&2
    exit 1
fi

mkdir -p "$ui_dir"

status "Запуск ibsrv для ${base_dir}"
"$onecv8_root/ibsrv" \
    --db-path="$base_dir" \
    >/dev/null 2>&1 &
ibsrv_pid=$!
ibsrv_ready=0

for _ in $(seq 1 120); do
    if (echo > /dev/tcp/127.0.0.1/8314) >/dev/null 2>&1; then
        ibsrv_ready=1
        break
    fi

    if ! kill -0 "$ibsrv_pid" 2>/dev/null; then
        wait "$ibsrv_pid"
    fi

    sleep 0.5
done

if [ "$ibsrv_ready" -ne 1 ] || ! kill -0 "$ibsrv_pid" 2>/dev/null; then
    echo "ibsrv не запустился на порту 8314" >&2
    exit 1
fi

status "ibsrv готов на порту 8314"

xvfb_display_number="${XVFB_DISPLAY_NUMBER:-99}"
xvfb_display=":${xvfb_display_number}"

status "Запуск Xvfb на дисплее ${xvfb_display}"
Xvfb "$xvfb_display" \
    -screen 0 1920x1080x24 \
    >/dev/null 2>&1 &
xvfb_pid=$!
openbox_pid=""
tail_pid=""

cleanup() {
    if [ -n "$tail_pid" ]; then
        kill "$tail_pid" 2>/dev/null || true
    fi

    if [ -n "$openbox_pid" ]; then
        kill "$openbox_pid" 2>/dev/null || true
    fi

    kill "$xvfb_pid" "$ibsrv_pid" 2>/dev/null || true
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
status "Запуск openbox"
DISPLAY="$xvfb_display" openbox >/dev/null 2>&1 &
openbox_pid=$!

status "Вывод лога 1cv8c: ${client_log_path}"
: > "$client_log_path"
tail -n +1 -f "$client_log_path" &
tail_pid=$!

status "Запуск менеджера тестирования 1cv8c"
set +e
DISPLAY="$xvfb_display" \
    "$onecv8_root/1cv8c" ENTERPRISE \
        /WS http://localhost:8314/ /N"Администратор" \
        /DisableStartupMessages /DisableStartupDialogs /UseHwLicenses- /TESTMANAGER \
        /Execute"${ui_dir}/vanessa-automation-single.epf" \
        /C"WorkspaceRoot=${ui_dir};VAParams=${ui_dir}/VAParams.json;StartFeaturePlayer;QuietInstallVanessaExt;exitCodePath=${exit_code_path}" \
        /out"$client_log_path" \
        >/dev/null 2>&1
set -e

sleep 0.2
kill "$tail_pid" 2>/dev/null || true
wait "$tail_pid" 2>/dev/null || true
tail_pid=""

if [ ! -f "$exit_code_path" ]; then
    echo "Файл кода завершения тестов не был создан: ${exit_code_path}" >&2
    exit 2
fi

status "Чтение статуса тестов: ${exit_code_path}"
test_rc="$(tr -d '[:space:]' < "$exit_code_path")"
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
        echo "Некорректный код завершения тестов: ${test_rc}" >&2
        exit 2
        ;;
esac
