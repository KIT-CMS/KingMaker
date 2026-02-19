Containers for KingMaker and CROWN

This directory contains the Dockerfile and Conda environment YAML files used to build container images for running KingMaker and CROWN workflows.

Contents

- `Dockerfile` --- primary Dockerfile for the default image, based on Redhat9.
- `Base_env.yml`, `KingMaker_env.yml`, `KingMakerStandalone_env.yml`, `KingMakerStandaloneMinimal_env.yml` --- Conda environment specs.

Docker Build

This repository includes a number of Conda env files that can be utilized via build arguments.

To build a single image:

```bash
cd containers
docker build --build-arg ENV_FILE_NAME=<name> -t <container-name> .
```

The build will fail if no ENV_FILE_NAME build argument is provided.

Example for build, tag and push:

```bash
docker build --build-arg ENV_FILE_NAME=KingMaker_env.yml -t testing_abc
docker tag testing_abc kingmakerimages/kingmaker:V0.3
docker push kingmakerimages/kingmaker:V0.3
```

Usage with KingMaker

Container images built this way can be utilized for both local sandboxing and for use in the batch system.
KingMaker relies on apptainer-style addresses (i.e. ``docker://kingmakerimages/kingmaker:V0.3``)
The built container can also be added to [CERN CVMFS unpacked](https://gitlab.cern.ch/unpacked/sync/) once it is considered stable.
The default container (``/cvmfs/unpacked.cern.ch/registry.hub.docker.com/tvoigtlaender/kingmaker_standalone:V1.3/``) is one such example.
