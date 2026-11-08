#!/usr/bin/env bash
# Start the local web app: http://localhost:8000
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
( sleep 2 && open "http://localhost:$PORT" ) >/dev/null 2>&1 &
exec conda run --no-capture-output -n ca-copilot uvicorn server:app --port "$PORT"
