#!/bin/bash
# v7 production runner: run_v7_production.sh <log-name> <law args...>
# Sources the KingMaker environment in a subshell and runs `law run ProduceNtuples <law args>` from the
# KingMaker root, logging to /ceph/sdaigler/v7_logs/<log-name>.log. Never call git submodule update here
# (it would move the CROWN checkout back to the pinned commit).
set -o pipefail
name="$1"; shift
logdir=/ceph/sdaigler/v7_logs
mkdir -p "$logdir"
log="$logdir/${name}.log"
cd /work/sdaigler/bbtautau/KingMaker || exit 2
export X509_USER_PROXY=/tmp/x509up_u12108
# ~/.local/bin holds a luigid without tornado that would shadow the KingMaker env's one
PATH=$(echo "$PATH" | tr ':' '\n' | grep -v -E '^/home/sdaigler/\.local/bin$|/\.nvm/' | paste -sd:)
export PATH PYTHONNOUSERSITE=1
{
  echo "=== $(date -Is) start: law run ProduceNtuples $*"
  echo "=== CROWN core $(git -C CROWN rev-parse --short HEAD) ($(git -C CROWN branch --show-current)), bbtautau $(git -C CROWN/analysis_configurations/bbtautau rev-parse --short HEAD) ($(git -C CROWN/analysis_configurations/bbtautau branch --show-current)), KingMaker $(git rev-parse --short HEAD) ($(git branch --show-current)), DB $(git -C sample_database rev-parse --short HEAD)"
  # setup.sh must not see this script's arguments (source passes them on)
  law_args=("$@")
  # the CVMFS copy of the KingMaker env (/cvmfs/etp.kit.edu/LAW_envs) gives I/O errors on portal2 (2026-10-17);
  # use the local miniforge env under KingMaker/miniforge instead
  set -- -e /work/sdaigler/bbtautau/KingMaker
  # shellcheck disable=SC1091
  source setup.sh
  law run ProduceNtuples "${law_args[@]}"
  rc=$?
  echo "=== $(date -Is) end rc=$rc"
  exit $rc
} >>"$log" 2>&1
