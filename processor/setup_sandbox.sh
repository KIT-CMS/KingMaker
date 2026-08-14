############################################################################################
#     This script sets up all dependencies necessary for running KingMaker sandboxing      #
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
    export USER_FIRST_LETTER=${USER:0:1}

    # Keep the sourced path alias (e.g. /eos/user/...) instead of canonicalizing to /eos/home-...
    BASE_DIR="$(dirname "${THIS_FILE}")"
    BASE_DIR="$(dirname "${BASE_DIR}")"
    if [[ "${BASE_DIR}" != /* ]]; then
        BASE_DIR="${PWD}/${BASE_DIR}"
    fi
    BASE_DIR="${BASE_DIR%/}"

    # Local (non-HTCondor) sandboxed tasks (e.g. BuildCROWNLib) run in a fresh container
    # context where this script is sourced independently of setup.sh, so BASE_DIR must be
    # re-derived here too. On CERN hosts, /eos/home-<letter>/<user>/... and the equivalent
    # /eos/user/<letter>/<user>/... alias are the same location, but only the /eos/user/
    # form has reliably worked for read/write access from inside containers/workers in this
    # setup - translate to it here as well, mirroring the same fix in setup.sh.
    if [[ "$(hostname -f 2>/dev/null)" == *.cern.ch ]] && \
            [[ "${BASE_DIR}" =~ ^/eos/home-([a-z0-9])/([^/]+)(/.*)?$ ]]; then
        _eos_letter="${BASH_REMATCH[1]}"
        _eos_user="${BASH_REMATCH[2]}"
        _eos_rest="${BASH_REMATCH[3]}"
        if [[ -d "/eos/user/${_eos_letter}/${_eos_user}" ]]; then
            BASE_DIR="/eos/user/${_eos_letter}/${_eos_user}${_eos_rest}"
        fi
        unset _eos_letter _eos_user _eos_rest
    fi

    # Check for voms proxy
    voms-proxy-info -exists &>/dev/null
    if [[ "$?" -eq "1" ]]; then
        echo "No valid voms proxy found, remote storage might be inaccessible."
        echo "Please ensure that it exists and that 'X509_USER_PROXY' is properly set."
    else
        echo "Voms proxy found at ${X509_USER_PROXY}"
    fi

    echo "Setting up Luigi/Law ..."
    export LAW_HOME="${BASE_DIR}/.law/${WF_NAME}"
    export LAW_CONFIG_FILE="${BASE_DIR}/lawluigi_configs/${WF_NAME}_law.cfg"
    export LUIGI_CONFIG_PATH="${BASE_DIR}/lawluigi_configs/${WF_NAME}_luigi.cfg"
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
