#!/bin/sh
action(){

    _addpy() {
        [ ! -z "$1" ] && export PYTHONPATH="$1:${PYTHONPATH}" && echo "Add $1 to PYTHONPATH"
    }
    _addbin() {
        [ ! -z "$1" ] && export PATH="$1:${PATH}" && echo "Add $1 to PATH"
    }

    SPAWNPOINT=$(pwd)
    export HOME=${SPAWNPOINT}

    # Set USER as local USER
    export USER={{USER}}
    export LUIGIPORT={{LUIGIPORT}}
    echo "------------------------------------------"
    echo " | USER = ${USER}"
    echo " | HOSTNAME = $(hostname)"
    echo " | ANA_NAME = {{ANA_NAME}}"
    echo " | ENV_NAME = {{ENV_NAME}}"
    echo " | TAG = {{TAG}}"
    echo " | USE_CVMFS = {{USE_CVMFS}}"
    echo " | TARBALL_PATH = {{TARBALL_PATH}}"

    if [[ "{{USE_CVMFS}}" == "True" ]]; then
        ENV_PATH=/cvmfs/etp.kit.edu/LAW_envs/conda_envs/miniconda/bin/activate
        echo " | ENV_PATH = ${ENV_PATH}"
    else
        ENV_PATH=${SPAWNPOINT}/miniconda/envs/{{ENV_NAME}}
        echo " | ENV_PATH = $ENV_PATH"
        echo " | TARBALL_ENV_PATH = {{TARBALL_ENV_PATH}}"
    fi
    echo "------------------------------------------"

    # copy and untar process (and environment if necessary)
    if [[ "{{USE_CVMFS}}" == "True" ]]; then
        # Activate environment from cvmfs
        source ${ENV_PATH} {{ENV_NAME}}
        echo "gfal-copy {{TARBALL_PATH}} ${SPAWNPOINT}"
        gfal-copy {{TARBALL_PATH}} ${SPAWNPOINT}
    else
        # Copy tarballs (only works for Centos/RHEL 7/8/9)
        (
            export X509_CERT_DIR=/cvmfs/grid.cern.ch/etc/grid-security/certificates
            export X509_VOMS_DIR=/cvmfs/grid.cern.ch/etc/grid-security/vomsdir
            MAJOR_RELEASE="$(. /etc/os-release; echo "${VERSION_ID%.*}")"
            source /cvmfs/sft.cern.ch/lcg/views/LCG_102/x86_64-centos${MAJOR_RELEASE}-gcc11-opt/setup.sh
            xrdcp {{TARBALL_PATH}} ${SPAWNPOINT}
            xrdcp {{TARBALL_ENV_PATH}} ${SPAWNPOINT}
        )
        mkdir -p ${ENV_PATH}
        tar -xzf {{ENV_NAME}}.tar.gz -C ${ENV_PATH} && rm {{ENV_NAME}}.tar.gz
        # Activate environment from tarball
        source ${ENV_PATH}/bin/activate
        conda-unpack
    fi

    tar -xzf processor.tar.gz && rm processor.tar.gz

    # # add law to path
    # # law
    _addpy "${SPAWNPOINT}/law"
    _addbin "${SPAWNPOINT}/law/bin"

    # tasks
    _addpy "${SPAWNPOINT}/processor"
    _addpy "${SPAWNPOINT}/processor/tasks"

    # Analysis specific modules
    MODULE_PYTHONPATH="{{MODULE_PYTHONPATH}}"
    if [[ ! -z ${MODULE_PYTHONPATH} ]]; then
        _addpy ${MODULE_PYTHONPATH}
    fi

    # setup law variables
    export LAW_HOME="${SPAWNPOINT}/.law"
    export LAW_CONFIG_FILE="${SPAWNPOINT}/lawluigi_configs/{{ANA_NAME}}_law.cfg"
    export LUIGI_CONFIG_PATH="${SPAWNPOINT}/lawluigi_configs/{{ANA_NAME}}_luigi.cfg"

    # Variables set by local LAW instance and used by batch job LAW instance
    export LOCAL_TIMESTAMP="{{LOCAL_TIMESTAMP}}"
    export LOCAL_PWD="{{LOCAL_PWD}}"

    export ANALYSIS_DATA_PATH=$(pwd)

    # start a luigid scheduler using $LUIGIPORT
    echo "Starting luigid scheduler on port $LUIGIPORT"
    luigid --background --logdir logs --state-path luigid_state.pickle --port=$LUIGIPORT
}

action
