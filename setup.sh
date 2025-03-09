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
ANA_LIST=("KingMaker" "GPU_example" "ML_train")

_addpy() {
    [ ! -z "${1}" ] && export PYTHONPATH="${1}:${PYTHONPATH}"
}

_addbin() {
    [ ! -z "${1}" ] && export PATH="${1}:${PATH}"
}

parse_arguments() {
    # Default values
    DEFAULT_ANALYSIS="KingMaker"
    DEFAULT_ENV_PATH=""
    DEFAULT_CROWN_ANALYSIS=""
    ANALYSIS=${DEFAULT_ANALYSIS}
    ENV_PATH=${DEFAULT_ENV_PATH}
    CROWN_ANALYSIS=${DEFAULT_CROWN_ANALYSIS}

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -a|--analysis)
                ANALYSIS="$2"
                shift 2
                ;;
            -e|--env-path)
                ENV_PATH="$2"
                shift 2
                ;;
            -c|--crown-analysis)
                CROWN_ANALYSIS="$2"
                shift 2
                ;;
            -l|--list)
                echo "Available workflows:"
                echo "-------------------"
                for workflow in "${ANA_LIST[@]}"; do
                    if [[ "${workflow}" == "${DEFAULT_ANALYSIS}" ]]; then
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
                echo "  -a, --analysis ANALYSIS    Specify the analysis workflow to use"
                echo "                            [default: ${DEFAULT_ANALYSIS}]"
                echo "  -e, --env-path PATH       Specify custom environment path"
                echo "                            [default: auto-detected]"
                echo "  -c, --crown-analysis NAME  Specify CROWN analysis to check out"
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
    export PARSED_ANALYSIS="${ANALYSIS}"
    export PARSED_ENV_PATH="${ENV_PATH}"
    export CROWN_ANALYSIS="${CROWN_ANALYSIS}"
}

action() {

    # Parse arguments first
    parse_arguments "$@"
    if [[ $? -eq "1" ]]; then 
        return 1 
    fi
    
    # Check if law was already set up in this shell
    if [[ ! -z ${LAW_IS_SET_UP} ]]; then
        echo "KingMaker was already set up in this shell. Please, use a new one."
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

    BASE_DIR="$( cd "$( dirname "${THIS_FILE}" )" && pwd )"

    # Check if current OS is supported
    source ${BASE_DIR}/scripts/os-version.sh
    local VALID_OS="False"
    if [[ "${distro}" == "CentOS" ]]; then
        if [[ ${os_version:0:1} == "7" ]]; then
            VALID_OS="True"
        fi
    elif [[ "${distro}" == "RedHatEnterprise" || "${distro}" == "Alma" || "${distro}" == "Rocky" ]]; then
        if [[ ${os_version:0:1} == "9" ]]; then
            VALID_OS="True"
        fi
    elif [[ "${distro}" == "Ubuntu" ]]; then
        if [[ ${os_version:0:2} == "22" ]]; then
            VALID_OS="True"
        fi
    fi
    if [[ "${VALID_OS}" == "False" ]]; then
        echo "Kingmaker not support on ${distro} ${os_version}"
        return 1
    else
        echo "Running Kingmaker on ${distro} Version ${os_version} on $(hostname) from dir ${BASE_DIR}"
    fi

    # Handle analysis selection
    if [[ -z "${PARSED_ANALYSIS}" ]]; then
        echo "No workflow chosen. Please choose from:"
        printf '%s\n' "${ANA_LIST[@]}"
        return 1
    else
        # Check if given workflow is in list
        if [[ ! " ${ANA_LIST[*]} " =~ " ${PARSED_ANALYSIS} " ]] ; then
            echo "Not a valid name. Allowed choices are:"
            printf '%s\n' "${ANA_LIST[@]}"
            return 1
        else
            echo "Using ${PARSED_ANALYSIS} workflow."
            export ANA_NAME="${PARSED_ANALYSIS}"
        fi
    fi

    # Needed for EOS directory parsing
    export USER_FIRST_LETTER=${USER:0:1}

    # Ensure that submodule with KingMaker env files is present
    if [ -z "$(ls -A ${BASE_DIR}/kingmaker-images)" ]; then
        git submodule update --init --recursive -- kingmaker-images
    fi
    # Get kingmaker-images submodule hash to find the correct image during job submission
    export IMAGE_HASH=$(cd ${BASE_DIR}/kingmaker-images/; git rev-parse --short HEAD)

    # Parse the necessary environments from the luigi config files.
    PARSED_ENVS=$(python3 ${BASE_DIR}/scripts/ParseNeededVar.py ${BASE_DIR}/lawluigi_configs/${ANA_NAME}_luigi.cfg "ENV_NAME")
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
    # Remaining envs should be sourced via provided docker images
    export STARTING_ENV=$(echo ${PARSED_ENVS} | head -n1 | awk '{print $1;}')
    echo "${STARTING_ENV}_${IMAGE_HASH} will be sourced as the starting env."

    # Order of environment locations
    # 1. Use realpath of provided directory in second argument
    # 2. Use dir from file if none provided
    # 3. Use local /cvmfs installation if available
    # 4. Use dir of setup script if neither provided
    if [[ ! -z ${PARSED_ENV_PATH} ]]; then
        ENV_PATH="$(realpath ${PARSED_ENV_PATH})"
    elif [[ -f "${BASE_DIR}/environment.location" ]]; then
        ENV_PATH="$(tail -n 1 ${BASE_DIR}/environment.location)"
    elif [[ -d "/cvmfs/etp.kit.edu/LAW_envs/miniforge/envs/${STARTING_ENV}_${IMAGE_HASH}" ]]; then
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

    # Try to install env via miniforge
    # NOTE: miniforge is based on conda and uses the same syntax. Switched due to licensing concerns.
    # Install miniforge if necessary
    if [ ! -f "${ENV_PATH}/miniforge/bin/activate" ]; then
        # Miniforge version used for all environments
        MAMBAFORGE_VERSION="24.3.0-0"
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
    if [ -d "${ENV_PATH}/miniforge/envs/${STARTING_ENV}_${IMAGE_HASH}" ]; then
        echo  "${STARTING_ENV}_${IMAGE_HASH} env found using miniforge."
    else
        # Create miniforge env from yaml file if necessary
        echo "Creating ${STARTING_ENV}_${IMAGE_HASH} env from kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml..."
        if [[ ! -f "${BASE_DIR}/kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml" ]]; then
            echo "${BASE_DIR}/kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml not found. Unable to create environment."
            return 1
        fi
        conda env create -f ${BASE_DIR}/kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml -n ${STARTING_ENV}_${IMAGE_HASH}
        echo  "${STARTING_ENV}_${IMAGE_HASH} env built using miniforge."
    fi
    echo "Activating starting-env ${STARTING_ENV}_${IMAGE_HASH} from miniforge."
    conda activate ${STARTING_ENV}_${IMAGE_HASH}

    # Set up other dependencies based on workflow
    ############################################
    case ${ANA_NAME} in
        KingMaker)
            echo "Setting up CROWN ..."
            # Due to frequent updates CROWN is not set up as a submodule
            if [ ! -d "${BASE_DIR}/CROWN" ]; then
                git clone --recurse-submodules git@github.com:KIT-CMS/CROWN ${BASE_DIR}/CROWN
            fi
            # Add CROWN analysis checkout option using init.sh
            if [ ! -z "${CROWN_ANALYSIS}" ]; then
                (
                    # Run in subprocess to prevent environment changes
                    cd "${BASE_DIR}/CROWN"
                    if [ -f "init.sh" ]; then
                        echo "Checking out CROWN analysis: ${CROWN_ANALYSIS}"
                        source init.sh "${CROWN_ANALYSIS}"
                    else
                        echo "Error: CROWN init.sh not found"
                        return 1
                    fi
                )
            fi
            if [ -z "$(ls -A ${BASE_DIR}/sample_database)" ]; then
                git submodule update --init --recursive -- sample_database
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
            ;;
        ML_train)
            echo "Setting up ML-scripts ..."
            if [ -z "$(ls -A ${BASE_DIR}/sm-htt-analysis)" ]; then
                git submodule update --init --recursive -- sm-htt-analysis
            fi
            export MODULE_PYTHONPATH=sm-htt-analysis
            ;;
        *)
            ;;
    esac
    ############################################

    if [[ ! -z ${MODULE_PYTHONPATH} ]]; then
        export PYTHONPATH=${MODULE_PYTHONPATH}:${PYTHONPATH}
    fi

    # Check is law was set up, and do so if not
    if [ -z "$(ls -A ${BASE_DIR}/law)" ]; then
        git submodule update --init --recursive -- law
    fi

    # Remember the previous value of VOMS_USERCONF to overwrite after conda source
    export VOMS_USERCONF=${INITIAL_VOMS_USERCONF}

    # Check for voms proxy
    voms-proxy-info -exists &>/dev/null
    if [[ "$?" -eq "1" ]]; then
        echo "No valid voms proxy found, remote storage might be inaccessible."
        echo "Please ensure that it exists and that 'X509_USER_PROXY' is properly set."
    fi
    
    # Parse the necessary environments from the luigi config files.
    LOCAL_SCHEDULER=$(python3 ${BASE_DIR}/scripts/ParseNeededVar.py ${BASE_DIR}/lawluigi_configs/${ANA_NAME}_luigi.cfg "local_scheduler")
    LOCAL_SCHEDULER_STATUS=$?
    if [[ "${LOCAL_SCHEDULER_STATUS}" -eq "1" ]]; then
        IFS='@' read -ra ADDR <<< "${LOCAL_SCHEDULER}"
        for i in "${ADDR[@]}"; do
            echo ${i}
        done
        echo "Parsing of required scheduler setting failed with the above error."
        return 1
    fi
    export LOCAL_SCHEDULER
    if [[ "${LOCAL_SCHEDULER}" == "False" ]]; then
        echo "Using central scheduler."
        if  [[ ! -z $(hostname --long | grep -E '^lxplus.*\.cern\.ch$') ]]; then
            printf "\nWARNING: LXPLUS DOES NOT SUPPORT THE CENTRAL SCHEDULER BY DEFAULT!\n"
            printf "It is reccomended to change this setting in the configs and rerun the setup.\n"
            printf "'local_scheduler' should be set to false and the 'scheduler_port' schould be removed.\n\n"
	fi
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
    else
        echo "Using local scheduler."
        export LUIGIPORT=""
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

    export LAW_IS_SET_UP="True"
    echo "KingMaker setup was successful"
}
action "$@"
