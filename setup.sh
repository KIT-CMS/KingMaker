############################################################################################
# This script setups all dependencies necessary for making law executable                  #
############################################################################################


# Run alternative modes if asked for
# Available modes: l
alt_modes() {
    #list of available analyses
    ANA_LIST=("KingMaker" "GPU_example" "ML_train")
    if [[ "$@" =~ "-l" ]]; then
        echo "Available analyses:"
        printf '%s\n' "${ANA_LIST[@]}"
        exit_script
    fi
}

# Basic checks before setup is attempted
#   - Filter by hostname
check_basics() {
    # Check if current machine is an etp portal machine.
    PORTAL_LIST=(
        "bms1.etp.kit.edu" \
        "bms2.etp.kit.edu" \
        "bms3.etp.kit.edu" \
        "portal1.etp.kit.edu" \
        "bms1-centos7.etp.kit.edu" \
        "bms2-centos7.etp.kit.edu" \
        "bms3-centos7.etp.kit.edu" \
        "portal1-centos7.etp.kit.edu"\
    )
    CURRENT_HOST=$(hostname --long)
    if [[ ! " ${PORTAL_LIST[*]} " =~ " ${CURRENT_HOST} " ]]; then  
        echo "Current host (${CURRENT_HOST}) not in list of allowed machines:"
        printf '%s\n' "${PORTAL_LIST[@]}"
        exit_script
    else
        echo "Running on ${CURRENT_HOST}."
    fi
}

# Set up environments for analysis
env_setup() {
    ANA_NAME_GIVEN=$1

    #Determine analysis to be used. Default is first in list.
    if [[ -z "${ANA_NAME_GIVEN}" ]]; then
        echo "No analysis chosen. Please choose from:"
        printf '%s\n' "${ANA_LIST[@]}"
        exit_script
    fi
    #Check if given analysis is in list 
    if [[ ! " ${ANA_LIST[*]} " =~ " ${ANA_NAME_GIVEN} " ]] ; then 
        echo "Not a valid name. Allowed choices are:"
        printf '%s\n' "${ANA_LIST[@]}"
        exit_script
    fi
    echo "Using ${ANA_NAME_GIVEN} analysis." 
    export ANA_NAME="${ANA_NAME_GIVEN}"

    # Parse the necessary environments from the luigi config files.
    PARSED_ENVS=$(python3 scripts/ParseNeededEnv.py lawluigi_configs/${ANA_NAME}_luigi.cfg)
    PARSED_ENVS_STATUS=$?
    if [[ "${PARSED_ENVS_STATUS}" -eq "1" ]]; then
        IFS='@' read -ra ADDR <<< "${PARSED_ENVS}"
        for i in "${ADDR[@]}"; do
            echo $i
        done    
        echo "Parsing of required envs failed with the above error."
        exit_script
    fi

    # First listed is env of DEFAULT and will be used as the starting env
    export STARTING_ENV=$(echo ${PARSED_ENVS} | head -n1 | awk '{print $1;}')
    echo "The following envs will be set up:"
    printf '%s\n' "${PARSED_ENVS[@]}"
    echo "${STARTING_ENV} will be sourced as the starting env."
    export ENV_NAMES_LIST=""
    for ENV_NAME in ${PARSED_ENVS}; do
        # Check if necessary environment is present in cvmfs
        # Try to install and export env via miniforge if not
        # NOTE: HTCondor jobs that rely on exported miniforge envs might need additional scratch space
        if [[ -d "/cvmfs/etp.kit.edu/LAW_envs/forge_envs/miniforge/envs/${ENV_NAME}" ]]; then
            echo "${ENV_NAME} environment found in cvmfs."
            CVMFS_ENV_PRESENT="True"
        else
            echo "${ENV_NAME} environment not found in cvmfs. Using miniforge."
            # Install miniforge if necessary
            if [ ! -f "miniforge/bin/activate" ]; then
                # Miniforge version used for all environments
                MAMBAFORGE_VERSION="23.3.1-1"
                MAMBAFORGE_INSTALLER="Mambaforge-${MAMBAFORGE_VERSION}-$(uname)-$(uname -m).sh"
                echo "Miniforge could not be found, installing miniforge ..."
                echo "More information can be found in"
                echo "https://github.com/conda-forge/miniforge"
                curl -L -O https://github.com/conda-forge/miniforge/releases/download/${MAMBAFORGE_VERSION}/${MAMBAFORGE_INSTALLER}
                bash ${MAMBAFORGE_INSTALLER} -b -s -p miniforge
                rm -f ${MAMBAFORGE_INSTALLER}
            fi
            # source base env of miniforge
            source miniforge/bin/activate ''

            # check if correct miniforge env is running
            if [ "${CONDA_DEFAULT_ENV}" != "${ENV_NAME}" ]; then
                if [ -d "miniforge/envs/${ENV_NAME}" ]; then
                    echo  "${ENV_NAME} env found using miniforge."
                else
                    # Create miniforge env from yaml file if necessary
                    echo "Creating ${ENV_NAME} env from forge_environments/${ENV_NAME}_env.yml..."
                    if [[ ! -f "forge_environments/${ENV_NAME}_env.yml" ]]; then
                        echo "forge_environments/${ENV_NAME}_env.yml not found. Unable to create environment."
                        exit_script
                    fi
                    conda env create -f forge_environments/${ENV_NAME}_env.yml -n ${ENV_NAME}
                    echo  "${ENV_NAME} env built using miniforge."
                fi
            fi

            # create miniforge tarball if env not in cvmfs and it if it doesn't already exist
            if [ ! -f "tarballs/forge_envs/${ENV_NAME}.tar.gz" ]; then
                # IMPORTANT: environments have to be named differently with each change
                #            as chaching prevents a clean overwrite of existing files
                echo "Creating ${ENV_NAME}.tar.gz"
                mkdir -p "tarballs/forge_envs"
                conda activate ${ENV_NAME}
                conda pack -n ${ENV_NAME} --output tarballs/forge_envs/${ENV_NAME}.tar.gz
                if [[ "$?" -eq "1" ]]; then
                    echo "Conda pack failed. Does the env contain conda-pack?"
                    exit_script
                fi
                conda deactivate
            fi
            CVMFS_ENV_PRESENT="False"
        fi

        # Remember status of starting-env
        if [[ "${ENV_NAME}" == "${STARTING_ENV}" ]]; then
            CVMFS_ENV_PRESENT_START=${CVMFS_ENV_PRESENT}
        fi
        # Create list of envs and their status to be later parsed by python
        #   Example: 'env1;True,env2;False,env3;False'
        # ENV_NAMES_LIST is used by the processor/framework.py to determine whether the environments are present in cvmfs
        ENV_NAMES_LIST+="${ENV_NAME},${CVMFS_ENV_PRESENT};"
    done
    # Actvate starting-env
    if [[ "${CVMFS_ENV_PRESENT_START}" == "True" ]]; then
        echo "Activating starting-env ${STARTING_ENV} from cvmfs."
        source /cvmfs/etp.kit.edu/LAW_envs/forge_envs/miniforge/bin/activate ${STARTING_ENV}
    else
        echo "Activating starting-env ${STARTING_ENV} from miniforge."
        conda activate ${STARTING_ENV}
    fi
}

# Set up additional things for the relevant analysis
env_specific_setup() {
    #Set up other dependencies based on analysis
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
            # set an alias for the sample manager
            alias sample_manager="python3 sample_database/manager.py"
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
        _addpy ${MODULE_PYTHONPATH}
    fi
}

# Check if specified remote file system is readable and writeable with provided voms certificate 
check_voms() {
    # Check if valid voms exists
    voms-proxy-info -exists &>/dev/null
    if [[ "$?" -eq "1" ]]; then
        echo "No valid voms proxy found, please ensure that it exists and that 'X509_USER_PROXY' is properly set."
        exit_script
    fi
    # Check if remote storage is accessible by creating and deleting a dummy file 
    #   at the location specified in the luigi config file (wlcg_path)
    PARSED_RFS_PATH=$(python3 scripts/ParseRFSPath.py lawluigi_configs/${ANA_NAME}_luigi.cfg)
    RFS_PATH_STATUS=$?
    if [[ "${PARSED_ENVS_STATUS}" -eq "1" ]]; then
        IFS='@' read -ra ADDR <<< "${RFS_PATH}"
        for i in "${ADDR[@]}"; do
            echo $i
        done
        echo "Parsing of required envs failed with the above error."
        exit_script
    fi
    RFS_PATH="${PARSED_RFS_PATH/'${USER}'/"${USER}"}"
    TMPFILE_PATH=$(mktemp)
    TMPFILE_NAME=$(basename "${TMPFILE_PATH}")    
    gfal-copy "${TMPFILE_PATH}" "${RFS_PATH}" 1> /dev/null 
    if [[ "$?" -eq "1" ]]; then
        echo "Dummy copy from ${TMPFILE_PATH} to ${RFS_PATH} failed. Please ensure you have the necessary rights."
        exit_script
    fi
    gfal-rm "${RFS_PATH}/${TMPFILE_NAME}" 1> /dev/null
    if [[ "$?" -eq "1" ]]; then
        echo "Removal of dummy at ${RFS_PATH}/${TMPFILE_NAME} failed. Please ensure you have the necessary rights."
        exit_script
    fi
    # add voms proxy path
    export X509_USER_PROXY=$(voms-proxy-info -path)
    echo "Proxy at ${X509_USER_PROXY} is valid for accesing ${RFS_PATH}."
}

# Set up LAW
law_setup() {
    # Check is law was cloned, and set it up if not
    if [ -z "$(ls -A law)" ]; then
        git submodule update --init --recursive -- law
    fi
    # first check if the user already has a luigid scheduler running
    # start a luidigd scheduler if there is one already running
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

    # determine the directory of this file
    if [ ! -z "${ZSH_VERSION}" ]; then
        local THIS_FILE="${(%):-%x}"
    else
        local THIS_FILE="${BASH_SOURCE[0]}"
    fi

    local BASE_DIR="$( cd "$( dirname "${THIS_FILE}" )" && pwd )"

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
        exit_script
    fi

    # tasks
    _addpy "${BASE_DIR}/processor"
    _addpy "${BASE_DIR}/processor/tasks"

    # Create law index for analysis if not previously done
    if [[ ! -f "${LAW_HOME}/index" ]]; then
        law index --verbose
        if [[ "$?" -eq "1" ]]; then
            echo "Law index failed."
            exit_script
        fi
    fi
}

# Exit source script without killing the shell
exit_script() {
    kill -SIGINT $$
}

# Add path to 'PYTHONPATH'
_addpy() {
    [ ! -z "$1" ] && export PYTHONPATH="$1:${PYTHONPATH}"
}

# Add path to 'PATH'
_addbin() {
    [ ! -z "$1" ] && export PATH="$1:${PATH}"
}


action() {
    # Check if law was already set up in this shell
    if ( [[ ! -z ${LAW_IS_SET_UP} ]] && [[ ! "$@" =~ "-f" ]] ); then
        echo "LAW was already set up in this shell. Please, use a new one."
        exit_script
    fi
    # Check if alternative modes are asked for
    alt_modes "$@"
    # Check if basic setup is present
    check_basics
    # Set up all environments of the requested analysis
    env_setup "$@"
    # Set up analysis specific parts
    env_specific_setup
    # Check if working voms proxy is present
    check_voms
    # Set up law
    law_setup

    # Mark that setup is complete
    export LAW_IS_SET_UP="True"
}


action "$@"
