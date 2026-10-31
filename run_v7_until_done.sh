#!/bin/bash
# run_v7_until_done.sh <log-name> <max-attempts> <law args...>
# Waits until no other law run with the same --production-tag is active, then calls run_v7_production.sh until it
# returns 0 or max-attempts is reached. CROWNRun jobs that start before their CROWNBuild tarball exists fail after
# their retries; a re-run picks up the finished builds.
name="$1"; max="$2"; shift 2
tag=""
prev=""
for a in "$@"; do [ "$prev" = "--production-tag" ] && tag="$a"; prev="$a"; done
cd /work/sdaigler/bbtautau/KingMaker || exit 2
while pgrep -u "$USER" -f "law run ProduceNtuples .*--production-tag ${tag} " >/dev/null; do sleep 60; done
for i in $(seq 1 "$max"); do
  ./run_v7_production.sh "${name}_a${i}" "$@"
  rc=$?
  echo "$(date -Is) ${name} attempt ${i} rc=${rc}" >> /ceph/sdaigler/v7_logs/attempts.log
  [ $rc -eq 0 ] && exit 0
  sleep 120
done
exit 1
