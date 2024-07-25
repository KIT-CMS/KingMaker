############################################################################################
#         This script sets up all dependencies necessary for running KingMaker             #
############################################################################################


_addpy() {
    [ ! -z "$1" ] && export PYTHONPATH="$1:${PYTHONPATH}"
}

_addbin() {
    [ ! -z "$1" ] && export PATH="$1:${PATH}"
}

action() {

    # Check if law was already set up in this shell
    if ( [[ ! -z ${LAW_IS_SET_UP} ]] && [[ ! "$@" =~ "-f" ]] ); then
        echo "KingMaker was already set up in this shell. Please, use a new one."
        return 1
    fi

    # Check if law already tried to set up in this shell
    if ( [[ ! -z ${LAW_TRIED_TO_SET_UP} ]] && [[ ! "$@" =~ "-f" ]] ); then
        echo "Kingmaker already tried to set up in this shell. This might lead to unintended behaviour."
    fi

    export LAW_TRIED_TO_SET_UP="True"

    # Determine the directory of this file
    if [ ! -z "${ZSH_VERSION}" ]; then
        local THIS_FILE="${(%):-%x}"
    else
        local THIS_FILE="${BASH_SOURCE[0]}"
    fi

    local BASE_DIR="$( cd "$( dirname "${THIS_FILE}" )" && pwd )"

    # Check if current OS is supported
    source scripts/os-version.sh
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

    # Parse the necessary environments from the luigi config files.
    PARSED_ENVS=$(python3 scripts/ParseNeededEnv.py ${BASE_DIR}/lawluigi_configs/${ANA_NAME}_luigi.cfg)
    PARSED_ENVS_STATUS=$?
    if [[ "${PARSED_ENVS_STATUS}" -eq "1" ]]; then
        IFS='@' read -ra ADDR <<< "${PARSED_ENVS}"
        for i in "${ADDR[@]}"; do
            echo $i
        done
        echo "Parsing of required envs failed with the above error."
        return 1
    fi

    # Ensure that submodule with KingMaker env files is present
    if [ -z "$(ls -A kingmaker-images)" ]; then
        git submodule update --init --recursive -- kingmaker-images
    fi
    # Get kingmaker-images submodule hash to find the correct image during job submission
    export IMAGE_HASH=$(cd kingmaker-images/; git rev-parse --short HEAD)

    # First listed is env of DEFAULT and will be used as the starting env
    # Remaining envs should be sourced via provided docker images
    export STARTING_ENV=$(echo ${PARSED_ENVS} | head -n1 | awk '{print $1;}')
    # echo "The following envs will be set up: ${PARSED_ENVS}"
    echo "${STARTING_ENV}_${IMAGE_HASH} will be sourced as the starting env."
    # Check if necessary environment is present in cvmfs
    # Try to install and export env via miniforge if not
    # NOTE: miniforge is based on conda and uses the same syntax. Switched due to licensing concerns.
    # NOTE2: HTCondor jobs that rely on exported miniforge envs might need additional scratch space
    if [[ -d "/cvmfs/etp.kit.edu/LAW_envs/miniforge/envs/${STARTING_ENV}_${IMAGE_HASH}" ]]; then
        echo "${STARTING_ENV}_${IMAGE_HASH} environment found in cvmfs."
        echo "Activating starting-env ${STARTING_ENV}_${IMAGE_HASH} from cvmfs."
        source /cvmfs/etp.kit.edu/LAW_envs/miniforge/bin/activate ${STARTING_ENV}_${IMAGE_HASH}
    else
        echo "${STARTING_ENV}_${IMAGE_HASH} environment not found in cvmfs. Using miniforge."
        # Install miniforge if necessary
        if [ ! -f "miniforge/bin/activate" ]; then
            # Miniforge version used for all environments
            MAMBAFORGE_VERSION="24.3.0-0"
            MAMBAFORGE_INSTALLER="Mambaforge-${MAMBAFORGE_VERSION}-$(uname)-$(uname -m).sh"
            echo "Miniforge could not be found, installing miniforge version ${MAMBAFORGE_INSTALLER}"
            echo "More information can be found in"
            echo "https://github.com/conda-forge/miniforge"
            curl -L -O https://github.com/conda-forge/miniforge/releases/download/${MAMBAFORGE_VERSION}/${MAMBAFORGE_INSTALLER}
            bash ${MAMBAFORGE_INSTALLER} -b -s -p miniforge
            rm -f ${MAMBAFORGE_INSTALLER}
        fi
        # Source base env of miniforge
        source miniforge/bin/activate ''

        # Check if correct miniforge env is running
        if [ -d "miniforge/envs/${STARTING_ENV}_${IMAGE_HASH}" ]; then
            echo  "${STARTING_ENV}_${IMAGE_HASH} env found using miniforge."
        else
            # Create miniforge env from yaml file if necessary
            echo "Creating ${STARTING_ENV}_${IMAGE_HASH} env from kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml..."
            if [[ ! -f "kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml" ]]; then
                echo "kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml not found. Unable to create environment."
                return 1
            fi
            conda env create -f kingmaker-images/KingMaker_envs/${STARTING_ENV}_env.yml -n ${STARTING_ENV}_${IMAGE_HASH}
            echo  "${STARTING_ENV}_${IMAGE_HASH} env built using miniforge."
        fi
        echo "Activating starting-env ${STARTING_ENV}_${IMAGE_HASH} from miniforge."
        conda activate ${STARTING_ENV}_${IMAGE_HASH}
    fi

    # Set up other dependencies based on workflow
    ############################################
    case ${ANA_NAME} in
        KingMaker)
            echo "Setting up CROWN ..."
             # Due to frequent updates CROWN is not set up as a submodule
            if [ ! -d CROWN ]; then
                git clone --recursive --depth 1 --shallow-submodules git@github.com:KIT-CMS/CROWN
            fi
            if [ -z "$(ls -A sample_database)" ]; then
                git submodule update --init --recursive -- sample_database
            fi
            ;;
        ML_train)
            echo "Setting up ML-scripts ..."
            if [ -z "$(ls -A sm-htt-analysis)" ]; then
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
    if [ -z "$(ls -A law)" ]; then
        git submodule update --init --recursive -- law
    fi

    # Check for voms proxy
    voms-proxy-info -exists &>/dev/null
    if [[ "$?" -eq "1" ]]; then
        echo "No valid voms proxy found, remote storage might be inaccessible."
        echo "Please ensure that it exists and that 'X509_USER_PROXY' is properly set."
    fi
    

    # First check if the user already has a luigid scheduler running
    # Start a luidigd scheduler if there is one already running
    if [ -z "$(pgrep -u ${USER} -f luigid)" ]; then
        echo "Starting Luigi scheduler... using a random port"
        while
            export LUIGIPORT=$(shuf -n 1 -i 49152-65535)
            netstat -atun | grep -q "$LUIGIPORT"
        do
            continue
        done
        luigid --background --logdir logs --state-path luigid_state.pickle --port=$LUIGIPORT
        echo "Luigi scheduler started on port $LUIGIPORT, setting LUIGIPORT to $LUIGIPORT"
    else
        # first get the (first) PID
        export LUIGIPID=$(pgrep -u ${USER} -f luigid | head -n 1)
        # now get the luigid port that the scheduler is using and set the LUIGIPORT variable
        export LUIGIPORT=$(cat /proc/${LUIGIPID}/cmdline | sed -e "s/\x00/ /g" | cut -d "=" -f2)
        echo "Luigi scheduler already running on port ${LUIGIPORT}, setting LUIGIPORT to ${LUIGIPORT}"
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

    # Set the alias
    function sample_manager () {
        # Determine the directory of this file
        if [ ! -z "${ZSH_VERSION}" ]; then
            local THIS_FILE="${(%):-%x}"
        else
            local THIS_FILE="${BASH_SOURCE[0]}"
        fi

        local BASE_DIR="$( cd "$( dirname "${THIS_FILE}" )" && pwd )"
        (
            echo "Starting Samplemanager"
            python3 ${BASE_DIR}/sample_database/samplemanager/main.py --database-folder ${BASE_DIR}/sample_database
        )
    }

    function monitor_production () {
        # Parse all user arguments and pass them to the python script
        python3 scripts/ProductionStatus.py $@
    }

    export LAW_IS_SET_UP="True"
}
action "$@"
