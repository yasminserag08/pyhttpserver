#!/bin/bash

# benchmark_multi.sh — runs benchmark.sh N times, saving each run separately
# Usage: ./benchmark_multi.sh [N]   (default: 5 runs)
# All 4 servers must already be running.

RUNS=${1:-5}
THREADS=4
DURATION=10s
LUA_SCRIPT="./latency.lua"
RUN_DIR="./benchmark_runs"

declare -A SERVERS=(
  ["BLOCKING"]=8888
  ["THREADED"]=8889
  ["EVENTLOOP_V1"]=8890
  ["EVENTLOOP_V2"]=8891
)

CONCURRENCY_LEVELS=(10 25 50 100)
ROUTES=("/" "/slow")
SERVER_ORDER=("BLOCKING" "THREADED" "EVENTLOOP_V1" "EVENTLOOP_V2")

# ---- helpers ----

check_dependencies() {
  if ! command -v wrk &>/dev/null; then
    echo "ERROR: wrk is not installed. Install it with: sudo apt install wrk"
    exit 1
  fi
  if [ ! -f "$LUA_SCRIPT" ]; then
    echo "ERROR: $LUA_SCRIPT not found."
    exit 1
  fi
}

wait_for_server() {
  local port=$1
  local retries=10
  while ! nc -z 127.0.0.1 "$port" 2>/dev/null; do
    retries=$((retries - 1))
    [ $retries -eq 0 ] && return 1
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

run_once() {
  local run_num=$1
  local output_file="$RUN_DIR/results_run${run_num}.txt"

  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "  RUN $run_num / $RUNS  —  $(date)"
  echo "╚══════════════════════════════════════════════════════╝"

  echo "BENCHMARK RUN $run_num — $(date)" > "$output_file"
  echo "wrk -t${THREADS} -d${DURATION} -s ${LUA_SCRIPT}" >> "$output_file"

  for SERVER in "${SERVER_ORDER[@]}"; do
    PORT=${SERVERS[$SERVER]}

    print_header "$SERVER (port $PORT)" | tee -a "$output_file"

    if ! wait_for_server "$PORT"; then
      echo "  SKIPPED — nothing listening on port $PORT" | tee -a "$output_file"
      continue
    fi

    for ROUTE in "${ROUTES[@]}"; do
      echo "" | tee -a "$output_file"
      echo "  Route: $ROUTE" | tee -a "$output_file"
      echo "  $(printf -- '-%.0s' $(seq 1 40))" | tee -a "$output_file"

      for C in "${CONCURRENCY_LEVELS[@]}"; do
        echo "" | tee -a "$output_file"
        echo "  [-t${THREADS} -c${C} -d${DURATION}]" | tee -a "$output_file"

        wrk -t"$THREADS" -c"$C" -d"$DURATION" \
          -s "$LUA_SCRIPT" \
          "http://127.0.0.1:${PORT}${ROUTE}" 2>&1 | \
          sed 's/^/    /' | tee -a "$output_file"

        sleep 2
      done
    done
  done

  echo ""
  echo "Run $run_num saved to $output_file"
}

# ---- main ----

check_dependencies
mkdir -p "$RUN_DIR"

COOLDOWN=15

for i in $(seq 1 "$RUNS"); do
  run_once "$i"

  if [ "$i" -lt "$RUNS" ]; then
    echo ""
    echo "  Cooling down for ${COOLDOWN}s before next run..."
    sleep "$COOLDOWN"
  fi
done

echo ""
echo "All $RUNS runs complete. Results saved in $RUN_DIR/"
echo "Now run:  python3 analyze.py  to aggregate and visualize."