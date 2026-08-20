# KingMaker Containers
[← Back to KingMaker Main Project](../README.md)

This directory contains the Dockerfile and Conda environment YAML files used to build container images for running KingMaker and CROWN workflows.

Contents

- `Dockerfile`:  primary Dockerfile for the default image, based on Redhat9.
- `container_package_baseline.yml`: file that includes all relevant packages necessary for the container environment.
- `container_env.yml`: full Conda environment for the container where CROWN is run in. 
- `KingMaker_env.yml`: Conda environment for KingMaker itself with the law setup.

Docker Build

Conda env files can be utilized via build arguments to build the container.

To build a single image:

```bash
cd containers
docker build --build-arg ENV_FILE_NAME=<env-name> -t <container-name> .
```

The build will fail if no `ENV_FILE_NAME` build argument is provided.

Example for build, tag and push:

```bash
docker build --build-arg ENV_FILE_NAME=container_env.yml -t testing_abc .
docker tag testing_abc kingmakerimages/crown:V0.1
# 'docker login' might be needed
docker push kingmakerimages/crown:V0.1
```

Usage with KingMaker

Container images built this way can be utilized for both local sandboxing (`sandbox`) and for use in the batch system (`htcondor_container_image`).
Both can be set in the `*_luigi.cfg` files in the `lawluigi_configs` directory.

KingMaker relies on apptainer-style addresses (i.e. ``kingmakerimages/crown:V0.1``)
The built container can also be added to [CERN CVMFS unpacked](https://gitlab.cern.ch/unpacked/sync/) once it is considered stable.
The default container (``/cvmfs/unpacked.cern.ch/registry.hub.docker.com/kingmakerimages/crown:V0.1/``) is one such example.
