#!/bin/bash
# Produce the SM HH -> bbtautau ntuples (sm_config of the bbtautau analysis) for 2018.
# The sample list is the binned data + MC list plus the et/mt/tt embedding of the config
# (CROWN/analysis_configurations/bbtautau/sample_list, see its README.md).
#
# Usage: ./prodnTups_2018_sm.sh [production tag] [scopes] [law args...]
# Run "source setup.sh -w KingMaker" in this directory first.
set -e

TAG=${1:-30_10_26_NOM}
SCOPES=${2:-mt}
shift $(($# < 2 ? $# : 2))

LISTS=CROWN/analysis_configurations/bbtautau/sample_list
SAMPLE_LIST=sm_2018_binned_embedding.txt
cat ${LISTS}/sm_2018_binned.txt ${LISTS}/sm_2018_embedding.txt > ${SAMPLE_LIST}

law run ProduceNtuples \
 --analysis bbtautau \
 --config sm_config \
 --production-tag ${TAG} \
 --sample-list ${SAMPLE_LIST} \
 --nanoAOD-version nanoAOD_v15 \
 --scopes ${SCOPES} \
 --shifts None \
 --workers 50 \
 "$@"

# Friends needed by the shapes (fastMTT and fake factors are no longer in the ntuples):
# law run ProduceNtuples --analysis bbtautau --config sm_config --friend-config sm_fastmtt \
#  --friend-tag fastmtt --production-tag ${TAG} --sample-list ${SAMPLE_LIST} \
#  --nanoAOD-version nanoAOD_v15 --scopes ${SCOPES} --shifts None --workers 10
# law run ProduceNtuples --analysis bbtautau --config sm_config --friend-config sm_fake_factors \
#  --friend-tag ff_v7b --production-tag ${TAG} --sample-list ${SAMPLE_LIST} \
#  --nanoAOD-version nanoAOD_v15 --scopes ${SCOPES} --shifts None --workers 10
