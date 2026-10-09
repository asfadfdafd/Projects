#!/usr/bin/env bash
# Demo IoT sensor: posts plausible storage-room readings every N seconds.
#   bash scripts/simulate_sensor.sh            (Ctrl+C to stop)
#   INTERVAL=5 SENSOR=storage-room-2 bash scripts/simulate_sensor.sh
set -u
BASE="${WEBHOOK_BASE:-http://localhost:5678/webhook}"
SENSOR="${SENSOR:-storage-room-1}"
INTERVAL="${INTERVAL:-10}"
echo "Posting $SENSOR readings to $BASE/metrics every ${INTERVAL}s (Ctrl+C to stop)"
T=18.2; H=47.0
while true; do
  # small random walk around archival norms (16-20°C / 40-55%)
  T=$(python3 -c "import random;t=$T+random.uniform(-0.3,0.3);print(round(min(max(t,15.0),22.5),1))")
  H=$(python3 -c "import random;h=$H+random.uniform(-1.2,1.2);print(round(min(max(h,32.0),68.0),1))")
  OUT=$(curl -s -X POST "$BASE/metrics" -H 'Content-Type: application/json' \
    -d "{\"sensor\":\"$SENSOR\",\"metrics\":{\"temperature\":$T,\"humidity\":$H}}")
  echo "$(date +%H:%M:%S)  t=${T}°C h=${H}%  -> $OUT"
  sleep "$INTERVAL"
done
