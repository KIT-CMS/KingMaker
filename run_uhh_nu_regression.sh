#!/bin/bash
# Evaluate the UHH neutrino regression (python friend config uhh_nu_regression_friend of
# the bbtautau analysis) on the ntuples of production 22_09_26_NOM.
#
# Usage: ./run_uhh_nu_regression.sh [test|submit-test|full] [sample list] [law args...]
#   test         local test on the first 1000 events of every sample, nothing is submitted
#   submit-test  submit only the first two branches (jobs) of every sample
#   full         submit everything
#   sensitivity  sensitivity test of the model on random inputs, no ntuples needed
# Further arguments are passed to law, e.g. --force-repack-tarball after code changes.
# Run "source setup.sh -w KingMaker" in this directory first.
set -e

MODE=${1:-test}
SAMPLE_LIST=${2:-2018.txt}
shift $(($# < 2 ? $# : 2))

if [[ "${WF_NAME}" != "KingMaker" ]] || ! command -v law &>/dev/null; then
    echo "KingMaker environment not set up, run 'source setup.sh -w KingMaker' first."
    exit 1
fi

ARGS=(
    --analysis bbtautau
    --config sm_config
    --sample-list "${SAMPLE_LIST}"
    --python-friend-config uhh_nu_regression_friend
    --friend-tag nu_regression
    --scopes mt
    --shifts None
    --nanoAOD-version nanoAOD_v15
    --production-tag 22_09_26_NOM
    # HHbtag, CvsB/CvsL and fatjets are not in the ntuples, see the config
    --allow-empty-values
    "$@"
)

case ${MODE} in
    test) law run ProducePythonFriends "${ARGS[@]}" --local-test --workers 1 ;;
    submit-test) law run ProducePythonFriends "${ARGS[@]}" --PythonFriend-branches 0,1 ;;
    full) law run ProducePythonFriends "${ARGS[@]}" ;;
    sensitivity) law run ProducePythonFriends "${ARGS[@]}" --sensitivity-test ;;
    *) echo "Unknown mode ${MODE}, use test, submit-test, full or sensitivity." && exit 1 ;;
esac
