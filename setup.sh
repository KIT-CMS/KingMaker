############################################################################################
#         This script sets up all dependencies necessary for running KingMaker             #
############################################################################################
# Usage: source setup.sh [options]
#
# Script accepts following options:
#   -a, --analysis ANALYSIS    Choose workflow from available options
#   -e, --env-path PATH        Set custom conda environment directory
#   -c, --crown-analysis NAME  Specify CROWN analysis to check out (KingMaker workflow only)
#   -l, --list                 List available workflows
#   -h, --help                 Show detailed help message
#
# Supports CentOS 7, RHEL/Alma/Rocky 9, and Ubuntu 22.


# List of available workflows
WF_LIST=("KingMaker" "GPU_example")

_addpy() {
    [ ! -z "${1}" ] && export PYTHONPATH="${1}:${PYTHONPATH}"
}

_addbin() {
    [ ! -z "${1}" ] && export PATH="${1}:${PATH}"
}

parse_arguments() {
    # Default values
    DEFAULT_WORKFLOW="KingMaker"
    DEFAULT_ENV_PATH=""
    DEFAULT_CROWN_ANALYSIS=""
    WORKFLOW=${DEFAULT_WORKFLOW}
    ENV_PATH=${DEFAULT_ENV_PATH}
    CROWN_ANALYSIS=${DEFAULT_CROWN_ANALYSIS}

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -w|--workflow)
                WORKFLOW="$2"
                shift 2
                ;;
            -e|--env-path)
                ENV_PATH="$2"
                shift 2
                ;;
            -a|--analysis)
                CROWN_ANALYSIS="$2"
                shift 2
                ;;
            -l|--list)
                echo "Available workflows:"
                echo "-------------------"
                for workflow in "${WF_LIST[@]}"; do
                    if [[ "${workflow}" == "${DEFAULT_WORKFLOW}" ]]; then
                        echo "* ${workflow} (default)"
                    else
                        echo "* ${workflow}"
                    fi
                done
                return 1
                ;;
            -h|--help)
                echo "Usage: source setup.sh [options]"
                echo ""
                echo "Options:"
                echo "  -w, --workflow WORKFLOW   Specify the workflow to use"
                echo "                            [default: ${DEFAULT_WORKFLOW}]"
                echo "  -e, --env-path PATH       Specify custom environment path"
                echo "                            [default: auto-detected]"
                echo "  -a, --analysis NAME       Specify CROWN analysis to check out"
                echo "                            (only with KingMaker workflow)"
                echo "                            Available: https://crown.readthedocs.io/en/latest/introduction.html#id1"
                echo "  -l, --list                List available workflows"
                echo "  -h, --help                Show this help message"
                echo ""
                echo "Environment path precedence:"
                echo "1. Command line argument (-e/--env-path)"
                echo "2. Saved location from environment.location file"
                echo "3. CVMFS installation if available"
                echo "4. Current directory"
                return 1
                ;;
            *)
                echo "Error: Unknown option $1"
                echo "Use --help to see available options"
                return 1
                ;;
        esac
    done

    # Export for use in main script
    export PARSED_WORKFLOW="${WORKFLOW}"
    export PARSED_ENV_PATH="${ENV_PATH}"
    export CROWN_ANALYSIS="${CROWN_ANALYSIS}"
}

action() {

    # Parse arguments first
    parse_arguments "$@"
    if [[ $? -eq "1" ]]; then
        return 1
    fi

    # Check if law already tried to set up in this shell
    if [[ ! -z ${LAW_TRIED_TO_SET_UP} ]]; then
        echo "Kingmaker already tried to set up in this shell. This might lead to unintended behaviour."
    fi

    export LAW_TRIED_TO_SET_UP="True"

    # Determine the directory of this file
    if [ ! -z "${ZSH_VERSION}" ]; then
        local THIS_FILE="${(%):-%x}"
    else
        local THIS_FILE="${BASH_SOURCE[0]}"
    fi

    # Keep the sourced path alias 
    BASE_DIR="$(dirname "${THIS_FILE}")"
    if [[ "${BASE_DIR}" != /* ]]; then
        BASE_DIR="${PWD}/${BASE_DIR}"
    fi
    BASE_DIR="${BASE_DIR%/}"

    # Detect whether we're running on lxplus, to automatically enable
    # EOS/EosSubmit-specific behavior (path alias preservation, proxy handling, container
    # binds) without requiring a dedicated workflow name
    IS_CERN_HOST=false
    if [[ "$(hostname -f 2>/dev/null)" == *.cern.ch ]]; then
        IS_CERN_HOST=true
    fi

    # HTCondor/EosSubmit worker nodes fetch/write job I/O through the eosuser.cern.ch xrootd
    # door. If this checkout lives under /eos/home-*, translate to the /eos/user/ alias
    # so paths handed to HTCondor (executable, transfer_input_files, output remaps) work.
    if [[ "${IS_CERN_HOST}" == "true" ]] && \
            [[ "${BASE_DIR}" =~ ^/eos/home-([a-z0-9])/([^/]+)(/.*)?$ ]]; then
        _eos_letter="${BASH_REMATCH[1]}"
        _eos_user="${BASH_REMATCH[2]}"
        _eos_rest="${BASH_REMATCH[3]}"
        if [[ -d "/eos/user/${_eos_letter}/${_eos_user}" ]]; then
            BASE_DIR="/eos/user/${_eos_letter}/${_eos_user}${_eos_rest}"
        fi
        unset _eos_letter _eos_user _eos_rest
    fi

    export LOCAL_PWD="${BASE_DIR}"

    # Handle analysis selection
    if [[ -z "${PARSED_WORKFLOW}" ]]; then
        echo "No workflow chosen. Please choose from:"
        printf '%s\n' "${WF_LIST[@]}"
        return 1
    else
        # Check if given workflow is in list
        if [[ ! " ${WF_LIST[*]} " =~ " ${PARSED_WORKFLOW} " ]] ; then
            echo "Not a valid name. Allowed choices are:"
            printf '%s\n' "${WF_LIST[@]}"
            return 1
        else
            echo "Using ${PARSED_WORKFLOW} workflow."
            export WF_NAME="${PARSED_WORKFLOW}"
        fi
    fi

    # Needed for EOS directory parsing
    export USER_FIRST_LETTER=${USER:0:1}

    # Parse the necessary environments from the luigi config files.
    PARSED_ENVS=$(python3 ${BASE_DIR}/scripts/ParseNeededVar.py ${BASE_DIR}/lawluigi_configs/${WF_NAME}_luigi.cfg "ENV_NAME")
    PARSED_ENVS_STATUS=$?
    if [[ "${PARSED_ENVS_STATUS}" -eq "1" ]]; then
        IFS='@' read -ra ADDR <<< "${PARSED_ENVS}"
        for i in "${ADDR[@]}"; do
            echo ${i}
        done
        echo "Parsing of required envs failed with the above error."
        return 1
    fi
    # First listed is env of DEFAULT and will be used as the starting env
    # Remaining envs should be sourced via provided container images
    export STARTING_ENV=$(echo ${PARSED_ENVS} | head -n1 | awk '{print $1;}')
    echo "${STARTING_ENV} will be sourced as the starting env."

    # Order of environment locations
    # 1. Use realpath of provided directory in second argument
    # 2. Use dir from file if none provided
    # 3. Use local /cvmfs installation if available
    # 4. Use dir of setup script if neither provided
    if [[ ! -z ${PARSED_ENV_PATH} ]]; then
        ENV_PATH="$(realpath ${PARSED_ENV_PATH})"
    elif [[ -f "${BASE_DIR}/environment.location" ]]; then
        ENV_PATH="$(tail -n 1 ${BASE_DIR}/environment.location)"
    elif [[ -d "/cvmfs/etp.kit.edu/LAW_envs/miniforge/envs/${STARTING_ENV}" ]]; then
        ENV_PATH="/cvmfs/etp.kit.edu/LAW_envs"
    else
        ENV_PATH="${BASE_DIR}"
    fi
    echo "Using environments from ${ENV_PATH}/miniforge."
    # Save env location to file if provided
    if [[ ! -z ${PARSED_ENV_PATH} ]]; then
        echo saving environment path to file for future setups.
        echo "### This file contains the environment location that was provided when the setup was last run ###" > ${BASE_DIR}/environment.location
        echo "${ENV_PATH}" >> ${BASE_DIR}/environment.location
    fi

    # Remember the current value of VOMS_USERCONF to overwrite after conda source.
    # This is necessary as conda installs a seperate voms version without the relevant configs.
    # Use primary default. Secondary default at ${HOME}/.voms/vomses has to be manually set.
    INITIAL_VOMS_USERCONF=${VOMS_USERCONF:-"/etc/vomses"}

    INITIAL_PROXY_PATH=""
    if voms-proxy-info -exists &>/dev/null 2>&1; then
        INITIAL_PROXY_PATH="$(voms-proxy-info -path 2>/dev/null)"
    fi

    # Try to install env via miniforge
    # NOTE: miniforge is based on conda and uses the same syntax. Switched due to licensing concerns.
    # Install miniforge if necessary
    if [ ! -f "${ENV_PATH}/miniforge/bin/activate" ]; then
        # Miniforge version used for all environments
        MAMBAFORGE_VERSION="26.5.0-0"
        MAMBAFORGE_INSTALLER="Mambaforge-${MAMBAFORGE_VERSION}-$(uname)-$(uname -m).sh"
        echo "Miniforge could not be found, installing miniforge version ${MAMBAFORGE_INSTALLER}"
        echo "More information can be found in"
        echo "https://github.com/conda-forge/miniforge"
        curl -L -O https://github.com/conda-forge/miniforge/releases/download/${MAMBAFORGE_VERSION}/${MAMBAFORGE_INSTALLER}
        bash ${MAMBAFORGE_INSTALLER} -b -s -p ${ENV_PATH}/miniforge
        rm -f ${MAMBAFORGE_INSTALLER}
    fi
    # Source base env of miniforge
    source ${ENV_PATH}/miniforge/bin/activate ''

    # Check if correct miniforge env is running
    if [ -d "${ENV_PATH}/miniforge/envs/${STARTING_ENV}" ]; then
        echo "${STARTING_ENV} env found using miniforge."
    else
        # Create miniforge env from yaml file if necessary
        echo "Creating ${STARTING_ENV} env from containers/${STARTING_ENV}_env.yml..."
        if [[ ! -f "${BASE_DIR}/containers/${STARTING_ENV}_env.yml" ]]; then
            echo "${BASE_DIR}/containers/${STARTING_ENV}_env.yml not found. Unable to create environment."
            return 1
        fi
        conda env create -f ${BASE_DIR}/containers/${STARTING_ENV}_env.yml -n ${STARTING_ENV}
        echo "${STARTING_ENV} env built using miniforge."
    fi
    echo "Activating starting-env ${STARTING_ENV} from miniforge."
    conda activate ${STARTING_ENV}
    export VOMS_USERCONF="${INITIAL_VOMS_USERCONF}"

    # Set up other dependencies based on workflow
    ############################################
    case ${WF_NAME} in
        KingMaker)
            echo "Setting up CROWN ..."
            # Due to frequent updates CROWN is not set up as a submodule
            if [ -z "$(ls -A ${BASE_DIR}/CROWN)" ]; then
                git -C "${BASE_DIR}" submodule update --init --recursive -- CROWN
            fi
            # Add CROWN analysis checkout option using init.sh
            if [ ! -z "${CROWN_ANALYSIS}" ]; then
                (
                    # Run in subprocess to prevent environment changes
                    if [ -f "${BASE_DIR}/CROWN/init.sh" ]; then
                        echo "Checking out CROWN analysis: ${CROWN_ANALYSIS}"
                        source ${BASE_DIR}/CROWN/init.sh -a "${CROWN_ANALYSIS}" --dry-run
                    else
                        echo "Error: CROWN init.sh not found at ${BASE_DIR}/CROWN/init.sh"
                        return 1
                    fi
                )
            fi
            if [ -z "$(ls -A ${BASE_DIR}/sample_database)" ]; then
                git -C "${BASE_DIR}" submodule update --init --recursive -- sample_database
            fi
            # Set the alias
            sample_manager () {
                (
                    # Switch to KingMaker dir in subprocess and run from there
                    echo "Starting Samplemanager"
                    cd "${BASE_DIR}"
                    python3 ${BASE_DIR}/sample_database/samplemanager/main.py --database-folder ${BASE_DIR}/sample_database
                )
            }
            monitor_production () {
                # Parse all user arguments and pass them to the python script
                python3 ${BASE_DIR}/scripts/ProductionStatus.py $@
            }

            # Set up ccache
            export CCACHE_DIR="${BASE_DIR}/CROWN/.cache/ccache";

            # KingMaker_luigi.cfg's htcondor_accounting_group picks this up.
            export LAW_ACCOUNTING_GROUP="cms.higgs"
            if [[ "${IS_CERN_HOST}" == "true" ]]; then
                export APPTAINER_BIND="/eos,/afs,/tmp,/run/user"
                export SINGULARITY_BIND="/eos,/afs,/tmp,/run/user"
                [[ ! -z "${KRB5CCNAME}" ]] && export APPTAINERENV_KRB5CCNAME="${KRB5CCNAME}"
                [[ ! -z "${KRB5CCNAME}" ]] && export SINGULARITYENV_KRB5CCNAME="${KRB5CCNAME}"
                module load lxbatch/eossubmit #for submission from eos
                export LAW_ACCOUNTING_GROUP="group_u_CMS.u_zh.users"
            fi

            ;;
        *)
            ;;
    esac
    ############################################

    # Check is law was set up, and do so if not
    if [ -z "$(ls -A ${BASE_DIR}/law)" ]; then
        git -C "${BASE_DIR}" submodule update --init --recursive -- law
    fi

    # Check for voms proxy - prefer path saved before conda changed the voms tools
    if [[ -n "${INITIAL_PROXY_PATH}" ]] && [[ -f "${INITIAL_PROXY_PATH}" ]]; then
        export X509_USER_PROXY="${INITIAL_PROXY_PATH}"
        echo "Voms proxy found at ${X509_USER_PROXY}"
    elif voms-proxy-info -exists &>/dev/null; then
        export X509_USER_PROXY=$(voms-proxy-info -path)
        echo "Voms proxy found at ${X509_USER_PROXY}"
    fi

    # For lxplus/EosSubmit: copy proxy to EOS so the remote schedd can access it
    # (EosSubmit schedds cannot read /tmp/ on the login node), and so it survives
    # across container restarts and is reusable from any CERN machine
    if [[ "${IS_CERN_HOST}" == "true" ]]; then
        EOS_PROXY_DIR="${BASE_DIR}/.proxy"
        EOS_PROXY="${EOS_PROXY_DIR}/x509up"
        if [[ -n "${X509_USER_PROXY}" ]] && [[ -f "${X509_USER_PROXY}" ]]; then
            # a fresh source proxy is available: refresh the persisted EOS copy
            mkdir -p "${EOS_PROXY_DIR}"
            cp "${X509_USER_PROXY}" "${EOS_PROXY}"
            chmod 600 "${EOS_PROXY}"
            export X509_USER_PROXY="${EOS_PROXY}"
            echo "Proxy copied to EOS for EosSubmit: ${X509_USER_PROXY}"
        elif [[ -f "${EOS_PROXY}" ]] && voms-proxy-info -file "${EOS_PROXY}" -exists &>/dev/null; then
            # no fresh source proxy (e.g. /tmp was wiped by a container restart),
            # but the previously persisted EOS copy is still valid: reuse it
            export X509_USER_PROXY="${EOS_PROXY}"
            echo "No fresh voms proxy found; reusing still-valid persisted proxy at ${X509_USER_PROXY}"
        fi
    fi

    if [[ -z "${X509_USER_PROXY}" ]] || [[ ! -f "${X509_USER_PROXY}" ]]; then
        echo "No valid voms proxy found, remote storage might be inaccessible."
        echo "Please ensure that it exists and that 'X509_USER_PROXY' is properly set."
    fi

    # Parse the necessary environments from the luigi config files.
    LOCAL_SCHEDULER=$(python3 ${BASE_DIR}/scripts/ParseNeededVar.py ${BASE_DIR}/lawluigi_configs/${WF_NAME}_luigi.cfg "local_scheduler")
    LOCAL_SCHEDULER_STATUS=$?
    if [[ "${LOCAL_SCHEDULER_STATUS}" -eq "1" ]]; then
        IFS='@' read -ra ADDR <<< "${LOCAL_SCHEDULER}"
        for i in "${ADDR[@]}"; do
            echo ${i}
        done
        echo "Parsing of required scheduler setting failed with the above error."
        return 1
    fi
    # lxplus doesn't support the central scheduler by default; force the
    # local scheduler there regardless of what the config says, rather than just warning.
    if [[ "${IS_CERN_HOST}" == "true" ]]; then
        LOCAL_SCHEDULER="True"
    fi
    export LOCAL_SCHEDULER
    if [[ "${LOCAL_SCHEDULER}" == "False" ]]; then
        echo "Using central scheduler."
        # Defined as function to allow for re-assignment in shells that persist longer than the port assignment
        set_luigiport () {
            # First check if the user already has a luigid scheduler running
            # Start a luidigd scheduler if there is one already running
            if [ -z "$(pgrep -u ${USER} -f luigid)" ]; then
                echo "Starting Luigi scheduler... using a random port"
                while
                    export LUIGIPORT=$(shuf -n 1 -i 49152-65535)
                    netstat -atun | grep -q "${LUIGIPORT}"
                do
                    continue
                done
                luigid --background --logdir logs --state-path luigid_state.pickle --port=${LUIGIPORT}
                echo "Luigi scheduler started on port ${LUIGIPORT}, setting LUIGIPORT to ${LUIGIPORT}"
            else
                # first get the (first) PID
                export LUIGIPID=$(pgrep -u ${USER} -f luigid | head -n 1)
                # now get the luigid port that the scheduler is using and set the LUIGIPORT variable
                export LUIGIPORT=$(cat /proc/${LUIGIPID}/cmdline | sed -e "s/\x00/ /g" | cut -d "=" -f2)
                echo "Luigi scheduler already running on port ${LUIGIPORT}, setting LUIGIPORT to ${LUIGIPORT}"
            fi
        }
        set_luigiport
    else
        echo "Using local scheduler."
        export LUIGIPORT=""
    fi

    echo "Setting up Luigi/Law ..."
    export LAW_HOME="${BASE_DIR}/.law/${WF_NAME}"
    export LAW_CONFIG_FILE="${BASE_DIR}/lawluigi_configs/${WF_NAME}_law.cfg"
    export LUIGI_CONFIG_PATH="${BASE_DIR}/lawluigi_configs/${WF_NAME}_luigi.cfg"
    export ANALYSIS_PATH="${BASE_DIR}"
    export ANALYSIS_DATA_PATH="${ANALYSIS_PATH}/data"
    mkdir -p "${LAW_HOME}"

    clear_law_cache (){
        echo "Clearing Law file target cache..."
        rm "${LAW_HOME}/target_exists_cache.json"
        rm "${LAW_HOME}/target_exists_cache.json.lock"
    }

    # law
    _addpy "${BASE_DIR}/law"
    _addbin "${BASE_DIR}/law/bin"
    source "$( law completion )"
    if [[ "$?" -eq "1" ]]; then
        echo "Law completion failed."
        return 1
    fi

    # tasks
    _addpy "${BASE_DIR}/processor"
    _addpy "${BASE_DIR}/processor/tasks"

    # Create law index for workflow if not previously done
    if [[ ! -f "${LAW_HOME}/index" ]]; then
        law index --verbose
        if [[ "$?" -eq "1" ]]; then
            echo "Law index failed."
            return 1
        fi
    fi
}
action "$@"
