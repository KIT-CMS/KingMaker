############################################################################################
#         This script sets up all dependencies necessary for running KingMaker             #
############################################################################################

_addpy() {
    [ ! -z "${1}" ] && export PYTHONPATH="${1}:${PYTHONPATH}"
}

_addbin() {
    [ ! -z "${1}" ] && export PATH="${1}:${PATH}"
}

action() {

    # Determine the directory of this file
    if [ ! -z "${ZSH_VERSION}" ]; then
        local THIS_FILE="${(%):-%x}"
    else
        local THIS_FILE="${BASH_SOURCE[0]}"
    fi

    BASE_DIR="$( cd "$( dirname "${THIS_FILE}" )" && pwd )"
    export ANA_NAME="KingMaker"
    source /opt/conda/bin/activate env

    # Check for voms proxy
    voms-proxy-info -exists &>/dev/null
    if [[ "$?" -eq "1" ]]; then
        echo "No valid voms proxy found, remote storage might be inaccessible."
        echo "Please ensure that it exists and that 'X509_USER_PROXY' is properly set."
    else
        echo "Voms proxy found at ${X509_USER_PROXY}"
    fi

    echo "Setting up Luigi/Law ..."
    export LAW_HOME="${BASE_DIR}/.law/${ANA_NAME}"
    export LAW_CONFIG_FILE="${BASE_DIR}/lawluigi_configs/${ANA_NAME}_law.cfg"
    export LUIGI_CONFIG_PATH="${BASE_DIR}/lawluigi_configs/${ANA_NAME}_luigi.cfg"
    export ANALYSIS_PATH="${BASE_DIR}"
    export ANALYSIS_DATA_PATH="${ANALYSIS_PATH}/data"

    # law
    _addpy "${BASE_DIR}/law"
    _addbin "${BASE_DIR}/law/bin"

    # tasks
    _addpy "${BASE_DIR}/processor"
    _addpy "${BASE_DIR}/processor/tasks"
    echo "KingMaker setup was successful"
}
action "$@"
