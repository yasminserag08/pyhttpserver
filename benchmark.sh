#!/bin/bash

# benchmark.sh — wrk benchmark runner for all 3 server types
# Usage: ./benchmark.sh
# Make sure all 4 servers are already running before executing.
#
# Start them like this (each in a separate terminal):
#   python3 -m blocking.server apps.flaskapp:app --port 8888
#   python3 -m threaded.server apps.flaskapp:app --port 8889
#   python3 -m eventloop.server_v1 apps.flaskapp:app --port 8890
#   python3 -m eventloop.server_v2 apps.flaskapp:app --port 8891

THREADS=4
DURATION=10s
LUA_SCRIPT="./latency.lua"
OUTPUT_FILE="results.txt"

declare -A SERVERS=(
  ["BLOCKING"]=8888
  ["THREADED"]=8889
  ["EVENTLOOP_V1"]=8890
  ["EVENTLOOP_V2"]=8891
)

CONCURRENCY_LEVELS=(10 25 50 100)
ROUTES=("/" "/slow")

# ---- helpers ----

check_dependencies() {
  if ! command -v wrk &>/dev/null; then
    echo "ERROR: wrk is not installed. Install it with: sudo apt install wrk"
    exit 1
  fi
  if [ ! -f "$LUA_SCRIPT" ]; then
    echo "ERROR: $LUA_SCRIPT not found. Make sure latency.lua is in the same directory as this script."
    exit 1
  fi
}

wait_for_server() {
  local port=$1
  local retries=10
  while ! nc -z 127.0.0.1 "$port" 2>/dev/null; do
    retries=$((retries - 1))
    if [ $retries -eq 0 ]; then
      return 1
    fi
    sleep 0.5
  done
  return 0
}

print_header() {
  local text="$1"
  local line
  line=$(printf '=%.0s' $(seq 1 60))
  echo ""
  echo "$line"
  echo "  $text"
  echo "$line"
}

# ---- main ----

check_dependencies

# Clear and init output file
echo "BENCHMARK RESULTS — $(date)" > "$OUTPUT_FILE"
echo "wrk -t${THREADS} -d${DURATION} --latency -s ${LUA_SCRIPT}" >> "$OUTPUT_FILE"

# Ordered server list for consistent output
SERVER_ORDER=("BLOCKING" "THREADED" "EVENTLOOP_V1" "EVENTLOOP_V2")

for SERVER in "${SERVER_ORDER[@]}"; do
  PORT=${SERVERS[$SERVER]}

  print_header "$SERVER (port $PORT)" | tee -a "$OUTPUT_FILE"

  # Check server is up
  if ! wait_for_server "$PORT"; then
    echo "  SKIPPED — nothing listening on port $PORT" | tee -a "$OUTPUT_FILE"
    continue
  fi

  for ROUTE in "${ROUTES[@]}"; do
    echo "" | tee -a "$OUTPUT_FILE"
    echo "  Route: $ROUTE" | tee -a "$OUTPUT_FILE"
    echo "  $(printf -- '-%.0s' $(seq 1 40))" | tee -a "$OUTPUT_FILE"

    for C in "${CONCURRENCY_LEVELS[@]}"; do
      echo "" | tee -a "$OUTPUT_FILE"
      echo "  [-t${THREADS} -c${C} -d${DURATION}]" | tee -a "$OUTPUT_FILE"

      wrk -t"$THREADS" -c"$C" -d"$DURATION" --latency \
        -s "$LUA_SCRIPT" \
        "http://127.0.0.1:${PORT}${ROUTE}" 2>&1 | \
        sed 's/^/    /' | tee -a "$OUTPUT_FILE"

      # Small pause between runs so the server can drain connections
      sleep 2
    done
  done
done

echo "" | tee -a "$OUTPUT_FILE"
echo "Done. Results saved to $OUTPUT_FILE"