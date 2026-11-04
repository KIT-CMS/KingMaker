#!/bin/bash
# Evaluate the UHH bbtautau classifier (python friend config uhh_classifier_friend of the
# bbtautau analysis, 5 folds) on the ntuples of production Test_30_10_26_NOM.
#
# Usage: ./run_uhh_classifier.sh [test|submit-test|full|sensitivity] [sample list] [law args...]
#   test         local test on the first 1000 events of every sample of the reduced list
#                sm_2018_test.txt (one sample per process type), nothing is submitted
#   submit-test  submit only the first two branches (jobs) of every sample
#   full         submit everything
#   sensitivity  sensitivity test of the model on random inputs, no ntuples needed
# Further arguments are passed to law, e.g. --force-repack-tarball after code changes.
# The scopes can be set with SCOPES, e.g. SCOPES=mt,et,tt ./run_uhh_classifier.sh full
# Run "source setup.sh -w KingMaker" in this directory first.
set -e

MODE=${1:-test}
# the local test only needs one sample per process type (sm_2018_test.txt)
DEFAULT_LIST=sm_2018_binned_embedding.txt
[[ "${MODE}" == "test" ]] && DEFAULT_LIST=sm_2018_test.txt
SAMPLE_LIST=${2:-${DEFAULT_LIST}}
shift $(($# < 2 ? $# : 2))

if [[ "${WF_NAME}" != "KingMaker" ]] || ! command -v law &>/dev/null; then
    echo "KingMaker environment not set up, run 'source setup.sh -w KingMaker' first."
    exit 1
fi

ARGS=(
    --analysis bbtautau
    --config sm_config
    --sample-list "${SAMPLE_LIST}"
    --python-friend-config uhh_classifier_friend
    --friend-tag uhh_classifier
    --scopes "${SCOPES:-mt}"
    --shifts None
    --nanoAOD-version nanoAOD_v15
    --production-tag Test_30_10_26_NOM
    # HHbtag and fatjets are not in the ntuples, see the config
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
