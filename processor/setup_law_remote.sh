#!/bin/sh
action() {

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
    export X509_CERT_DIR=/cvmfs/grid.cern.ch/etc/grid-security/certificates
    export X509_VOMS_DIR=/cvmfs/grid.cern.ch/etc/grid-security/vomsdir
    echo "------------------------------------------"
    echo " | USER = ${USER}"
    echo " | HOSTNAME = $(hostname)"
    echo " | ANA_NAME = {{ANA_NAME}}"
    echo " | ENV_NAME = {{ENV_NAME}}"
    echo " | TAG = {{TAG}}"
    echo "------------------------------------------"

    source /opt/conda/etc/profile.d/conda.sh
    conda activate env

    if [ "{{OUTPUT_DESTINATION}}" = "local" ]
    then
        echo "cp {{TARBALL_PATH}} ${SPAWNPOINT}"
        cp {{TARBALL_PATH}} ${SPAWNPOINT}
    else
        echo "gfal-copy {{TARBALL_PATH}} ${SPAWNPOINT}"
        gfal-copy {{TARBALL_PATH}} ${SPAWNPOINT}
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
