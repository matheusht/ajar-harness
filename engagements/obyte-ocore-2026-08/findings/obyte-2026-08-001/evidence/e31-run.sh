#!/bin/bash
# e31-run.sh — ONE-COMMAND maximum-impact PoC for obyte-2026-08-001 (Medium)
# Runs the full chain on the real two-node local Obyte network, BOTH scenarios:
#   ATTACK : a withdrawal-gated AA (only merkle-tree members may withdraw) is triggered with the
#            VACUOUS is_valid_merkle_proof proof by a non-member -> the AA's funds move.
#   CONTROL: the identical trigger with a wrong-root proof -> bounce, no withdrawal.
# Prints a single combined verdict. Real code path end-to-end (composer -> validation -> writer ->
# stabilization -> aa_triggers -> aa_composer -> formula engine -> response commit).
#
# Usage: bash e31-run.sh   (from anywhere; uses the lab dir)
set -u
LAB="$(cd "$(dirname "$0")" && pwd)"
cd "$LAB"
GENESIS_TS=1700000000
OVERALL=0

for SCENARIO in attack control; do
  echo "=============================="
  echo "=== SCENARIO: $SCENARIO ==="
  echo "=============================="
  rm -rf ".e31-$SCENARIO-node" ".e31-$SCENARIO-hub"
  LAB_GENESIS_TS=$GENESIS_TS SCENARIO=$SCENARIO ROLE=node PORT=6612 node e31-aa-demo.js > "e31-$SCENARIO-node.log" 2>&1 &
  NODE_PID=$!
  sleep 2
  LAB_GENESIS_TS=$GENESIS_TS SCENARIO=$SCENARIO ROLE=hub PORT=6611 node e31-aa-demo.js > "e31-$SCENARIO-hub.log" 2>&1 &
  HUB_PID=$!
  # wait for the node verdict (up to 240s)
  RC=99
  for i in $(seq 1 240); do
    if ! kill -0 $NODE_PID 2>/dev/null; then
      wait $NODE_PID; RC=$?
      break
    fi
    sleep 1
  done
  if [ $RC -eq 99 ]; then
    echo "[$SCENARIO] TIMEOUT waiting for the node process"; kill $NODE_PID $HUB_PID 2>/dev/null
    OVERALL=1
  else
    echo "[$SCENARIO] node exit code: $RC"
    grep "SCENARIO-RESULT" "e31-$SCENARIO-node.log" | tail -1
    if [ "$SCENARIO" = "attack" ]; then
      if [ $RC -eq 0 ] && grep -q "BYPASS-CONFIRMED" "e31-$SCENARIO-node.log"; then
        echo "[attack] PASS — the AA's funds moved via the vacuous proof"
      else
        echo "[attack] FAIL"; OVERALL=1
      fi
    else
      # control anchors: (a) the node saw the trigger and confirmed no withdrawal, or
      # (b) the node missed the trigger via the known relay race, and the HUB (a full node that
      #     stabilized the trigger itself) shows the gate bounce — both prove the wrong-root
      #     proof was rejected.
      if grep -q "CONTROL-CONFIRMED" "e31-$SCENARIO-node.log"; then
        echo "[control] PASS — node-side: wrong-root proof correctly rejected (no withdrawal)"
      elif grep -q "neither case is true" "e31-$SCENARIO-hub.log"; then
        echo "[control] PASS — hub-side bounce anchor: gate evaluated, wrong-root proof rejected ('neither case is true'), no response (node-side relay race known lab flakiness)"
      else
        echo "[control] FAIL — neither the node CONTROL-CONFIRMED line nor the hub bounce line was found"; OVERALL=1
      fi
    fi
  fi
  # cleanup processes
  kill $HUB_PID 2>/dev/null
  sleep 1
  pkill -f "e31-aa-demo.js" 2>/dev/null
  sleep 1
done

echo "=============================="
if [ $OVERALL -eq 0 ]; then
  echo "OVERALL-VERDICT: PASS — attack moves funds, control does not (full chain, real code path)"
else
  echo "OVERALL-VERDICT: PARTIAL — see the per-scenario lines and the raw logs"
fi
echo "Logs: $LAB/e31-attack-node.log, $LAB/e31-control-node.log (+ -hub.log)"
exit $OVERALL
