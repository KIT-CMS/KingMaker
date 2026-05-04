# KingMaker Containers
[← Back to KingMaker Main Project](../README.md)

This directory contains the Dockerfile and Conda environment YAML files used to build container images for running KingMaker and CROWN workflows.

Contents

- `Dockerfile`:  primary Dockerfile for the default image, based on Redhat9.
- `*_env.yml`:  Conda environment specs.

Docker Build

This repository includes a number of Conda env files that can be utilized via build arguments.

To build a single image:

```bash
cd containers
docker build --build-arg ENV_FILE_NAME=<env-name> -t <container-name> .
```

The build will fail if no `ENV_FILE_NAME` build argument is provided.

Example for build, tag and push:

```bash
docker build --build-arg ENV_FILE_NAME=KingMaker_env.yml -t testing_abc
docker tag testing_abc kingmakerimages/kingmaker_standalone:V0.1
docker push kingmakerimages/kingmaker_standalone:V0.1
```

Usage with KingMaker

Container images built this way can be utilized for both local sandboxing (`sandbox`) and for use in the batch system (`htcondor_container_image`).
Both can be set in the `*_luigi.cfg` files in the `lawluigi_configs` directory.

KingMaker relies on apptainer-style addresses (i.e. ``kingmakerimages/kingmaker_standalone:V0.1``)
The built container can also be added to [CERN CVMFS unpacked](https://gitlab.cern.ch/unpacked/sync/) once it is considered stable.
The default container (``/cvmfs/unpacked.cern.ch/registry.hub.docker.com/kingmakerimages/kingmaker_standalone:V1/``) is one such example.
