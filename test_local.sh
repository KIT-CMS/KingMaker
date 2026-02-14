#!/bin/bash

# Input Validation
if [[ $# -lt 3 ]]; then
    echo "Usage: $0 <executable> <outfile> <input1> [input2 ...]"
    exit 1
fi

# Check for Analysis Environment Variables
if [[ -z "${ANALYSIS_PATH}" ]]; then
    echo "Error: Environment variable ANALYSIS_PATH is not set."
    echo "This script must be run after 'source setup.sh'."
    exit 1
fi

if [[ -z "${ANA_NAME}" ]]; then
    echo "Error: Environment variable ANA_NAME is not set."
    echo "This script must be run after 'source setup.sh'."
    exit 1
fi

EXECUTABLE="$1"
FURTHER_ARGS="${@:2}"

# Check for VOMS Proxy
if ! voms-proxy-info -exists -file "$X509_USER_PROXY" >/dev/null 2>&1; then
    echo "Error: Valid VOMS proxy not found at $X509_USER_PROXY."
    exit 1
fi

# Path Validations
if [[ ! -f "$EXECUTABLE" ]]; then
    echo "Error: Executable '$EXECUTABLE' not found."
    exit 1
fi

FULL_EXECUTABLE="$(realpath "$EXECUTABLE")"
EXECUTABLE_DIR="$(dirname "${FULL_EXECUTABLE}")"
EXECUTABLE_NAME="$(basename "${FULL_EXECUTABLE}")"

# Sandbox Parsing
CONFIG_PATH="${ANALYSIS_PATH}/lawluigi_configs/${ANA_NAME}_luigi.cfg"
if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "Error: Config file not found at $CONFIG_PATH"
    exit 1
fi
PARSED_SANDBOX=$(python3 "${ANALYSIS_PATH}/scripts/ParseNeededVar.py" "$CONFIG_PATH" sandbox)
PARSED_SANDBOX_STATUS=$?
if [[ "${PARSED_SANDBOX_STATUS}" -ne 0 ]]; then
    IFS='@' read -ra ADDR <<< "${PARSED_SANDBOX}"
    for i in "${ADDR[@]}"; do
        echo "ERROR: ${i}" >&2
    done
    echo "Parsing of required envs failed with the above error." >&2
    exit 1
fi

# Strip to singularity callable address (e.g., docker://...)
PARSED_SANDBOX_CONTAINER="${PARSED_SANDBOX#*::}"

# Execution
echo "--- Launching ${PARSED_SANDBOX_CONTAINER} Singularity Container ---"
singularity exec -e \
    -B /etc/grid-security/certificates \
    "${PARSED_SANDBOX_CONTAINER}" \
    bash -l -c "
        export X509_USER_PROXY=${X509_USER_PROXY};
        source ${ANALYSIS_PATH}/setup_sandbox.sh;
        cd ${EXECUTABLE_DIR};
        ./${EXECUTABLE_NAME} ${FURTHER_ARGS}
    "
