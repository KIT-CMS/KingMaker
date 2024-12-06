############################################################################################
#         This script sets up all dependencies necessary for running KingMaker             #
############################################################################################
# First argument chooses from the available setups
# Second argument sets alternative conda environment directory

_addpy() {
    [ ! -z "$1" ] && export PYTHONPATH="$1:${PYTHONPATH}"
}

_addbin() {
    [ ! -z "$1" ] && export PATH="$1:${PATH}"
}

action() {

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
    if [[ "$distro" == "CentOS" ]]; then
        if [[ ${os_version:0:1} == "7" ]]; then
            VALID_OS="True"
        fi
    elif [[ "$distro" == "RedHatEnterprise" || "$distro" == "Alma" || "$distro" == "Rocky" ]]; then
        if [[ ${os_version:0:1} == "9" ]]; then
            VALID_OS="True"
        fi
    elif [[ "$distro" == "Ubuntu" ]]; then
        if [[ ${os_version:0:2} == "22" ]]; then
            VALID_OS="True"
        fi
    fi
    if [[ "${VALID_OS}" == "False" ]]; then
        echo "Kingmaker not support on ${distro} ${os_version}"
        return 1
    else
        echo "Running Kingmaker on $distro Version $os_version on $(hostname) from dir ${BASE_DIR}"
    fi

    # Workflow to be set up
    ANA_NAME_GIVEN=$1

    # List of available workflows
    ANA_LIST=("KingMaker" "GPU_example" "ML_train")
    if [[ "$@" =~ "-l" ]]; then
        echo "Available workflows:"
        printf '%s\n' "${ANA_LIST[@]}"
        return 0
    fi

    # Determine workflow to be used. Default is first in list.
    if [[ -z "${ANA_NAME_GIVEN}" ]]; then
        echo "No workflow chosen. Please choose from:"
        printf '%s\n' "${ANA_LIST[@]}"
        return 1
    else
        # Check if given workflow is in list
        if [[ ! " ${ANA_LIST[*]} " =~ " ${ANA_NAME_GIVEN} " ]] ; then
            echo "Not a valid name. Allowed choices are:"
            printf '%s\n' "${ANA_LIST[@]}"
            return 1
        else
            echo "Using ${ANA_NAME_GIVEN} workflow."
            export ANA_NAME="${ANA_NAME_GIVEN}"
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
    PARSED_ENVS=$(python3 ${BASE_DIR}/scripts/ParseNeededEnv.py ${BASE_DIR}/lawluigi_configs/${ANA_NAME}_luigi.cfg)
    PARSED_ENVS_STATUS=$?
    if [[ "${PARSED_ENVS_STATUS}" -eq "1" ]]; then
        IFS='@' read -ra ADDR <<< "${PARSED_ENVS}"
        for i in "${ADDR[@]}"; do
            echo $i
        done
        echo "Parsing of required envs failed with the above error."
        return 1
    fi
    # First listed is env of DEFAULT and will be used as the starting env
    # Remaining envs should be sourced via provided docker images
    export STARTING_ENV=$(echo ${PARSED_ENVS} | head -n1 | awk '{print $1;}')
    echo "${STARTING_ENV}_${IMAGE_HASH} will be sourced as the starting env."

    # Order of environment locations
    # 1. Use provided directory in second argument if provided
    # 2. Use dir from file if none provided
    # 3. Use local /cvmfs installation if available
    # 4. Use dir of setup script if neither provided
    if [[ ! -z $2 ]]; then
        ENV_PATH="$2"
    elif [[ -f "${BASE_DIR}/environment.location" ]]; then
        ENV_PATH="$(tail -n 1 ${BASE_DIR}/environment.location)"
    elif [[ -d "/cvmfs/etp.kit.edu/LAW_envs/miniforge/envs/${STARTING_ENV}_${IMAGE_HASH}" ]]; then
        ENV_PATH="/cvmfs/etp.kit.edu/LAW_envs"
    else
        ENV_PATH="${BASE_DIR}"
    fi
    echo "Using environments from ${ENV_PATH}/miniforge."
    
    # Save env location to file if provided
    if [[ ! -z $2 ]]; then
        echo saving environment path to file for future setups.
        echo "### This file contains the environment location that was provided when the setup was last run ###" > ${BASE_DIR}/environment.location
        echo "${ENV_PATH}" >> ${BASE_DIR}/environment.location
    fi
    
    # Remember the current value of VOMS_USERCONF to overwrite after conda source.
    # This is necessary as conda installs a seperate voms version without the relevant configs.
    # Use primary default. Secondary default at $HOME/.voms/vomses has to be manually set.
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
                git clone git@github.com:KIT-CMS/CROWN ${BASE_DIR}/CROWN
            fi
            if [ -z "$(ls -A ${BASE_DIR}/sample_database)" ]; then
                git submodule update --init --recursive -- sample_database
            fi
            # Set the alias
            function sample_manager () {
                (
                    # Switch to KingMaker dir in subprocess and run from there
                    echo "Starting Samplemanager"
                    cd "${BASE_DIR}"
                    python3 ${BASE_DIR}/sample_database/samplemanager/main.py --database-folder ${BASE_DIR}/sample_database
                )
            }
            function monitor_production () {
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
