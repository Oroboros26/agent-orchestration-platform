#!/bin/bash
# Start all three environments (DEV / UAT / PROD) locally.
# Each environment gets its own API port and Streamlit port.
#
# Ports:
#   DEV  → API :8000  UI :8501   http://localhost:8501
#   UAT  → API :8001  UI :8502   http://localhost:8502
#   PROD → API :8002  UI :8503   http://localhost:8503
#
# Usage:
#   cd aaop
#   bash tools/start_envs.sh          # start all three
#   bash tools/start_envs.sh dev      # start dev only
#   bash tools/start_envs.sh uat      # start uat only
#   bash tools/start_envs.sh prod     # start prod only
#   bash tools/start_envs.sh stop     # kill all

set -e
TARGET=${1:-all}
LOG_DIR="logs/envs"
mkdir -p "$LOG_DIR"

_start_env() {
    local env=$1
    local api_port=$2
    local ui_port=$3

    echo "▶  Starting $env | API :$api_port | UI :$ui_port"

    AAOP_ENV=$env uvicorn api.app:app \
        --host 0.0.0.0 \
        --port "$api_port" \
        --log-level warning \
        > "$LOG_DIR/${env}_api.log" 2>&1 &
    echo $! > "$LOG_DIR/${env}_api.pid"

    AAOP_ENV=$env streamlit run ui/app.py \
        --server.port "$ui_port" \
        --server.headless true \
        > "$LOG_DIR/${env}_ui.log" 2>&1 &
    echo $! > "$LOG_DIR/${env}_ui.pid"

    echo "   API log : $LOG_DIR/${env}_api.log"
    echo "   UI log  : $LOG_DIR/${env}_ui.log"
    echo "   UI url  : http://localhost:$ui_port"
}

_stop_all() {
    echo "■  Stopping all environments..."
    for pidfile in "$LOG_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" && echo "   Killed PID $pid ($(basename "$pidfile"))"
        fi
        rm -f "$pidfile"
    done
    echo "   Done."
}

case "$TARGET" in
    stop)
        _stop_all
        ;;
    dev)
        _start_env dev  8000 8501
        ;;
    uat)
        _start_env uat  8001 8502
        ;;
    prod)
        _start_env prod 8002 8503
        ;;
    all)
        _start_env dev  8000 8501
        _start_env uat  8001 8502
        _start_env prod 8002 8503
        echo ""
        echo "All environments running:"
        echo "  🔵 DEV  → http://localhost:8501"
        echo "  🟠 UAT  → http://localhost:8502"
        echo "  🟢 PROD → http://localhost:8503"
        echo ""
        echo "Stop with: bash tools/start_envs.sh stop"
        ;;
    *)
        echo "Usage: $0 [dev|uat|prod|all|stop]"
        exit 1
        ;;
esac
