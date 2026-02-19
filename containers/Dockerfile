FROM cern/alma9-base:latest

LABEL author="Tim Voigtländer <tim.voigtlaender@kit.edu>"

# ------------------------------------------------------------------------------
# Environment
# ------------------------------------------------------------------------------
ENV CONDA_DIR=/opt/conda

# ------------------------------------------------------------------------------
# Prepare filesystem
# ------------------------------------------------------------------------------
RUN mkdir -p /srv

# ------------------------------------------------------------------------------
# System packages
# ------------------------------------------------------------------------------
RUN dnf -y update && \
    dnf -y install epel-release && \
    dnf -y install \
        wget \
        python3 \
        python3-pip \
        tini \
        which \
        zlib-devel \
        gcc \
        glibc-devel \
        kernel-headers \
        pcre2-utf16 \
        libSM \
        strace \
        perf \
        openssh \
        crypto-policies-scripts && \
    dnf clean all

# ------------------------------------------------------------------------------
# Allow self-signed certificates (ROOT / grid compatibility)
# ------------------------------------------------------------------------------
RUN update-crypto-policies --set DEFAULT:SHA1

# ------------------------------------------------------------------------------
# Python tooling
# ------------------------------------------------------------------------------
RUN python3 -m pip install --upgrade pip

# ------------------------------------------------------------------------------
# Install Miniforge (Conda)
# ------------------------------------------------------------------------------
ARG MINIFORGE_NAME=Miniforge3
ARG MINIFORGE_VERSION=23.11.0-0
RUN wget -q https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/${MINIFORGE_NAME}-${MINIFORGE_VERSION}-Linux-$(uname -m).sh -O /tmp/miniforge.sh && \
    bash /tmp/miniforge.sh -b -p ${CONDA_DIR} && \
    rm -f /tmp/miniforge.sh

# ------------------------------------------------------------------------------
# Conda environment specification
# Fails for default value
# ------------------------------------------------------------------------------
ARG ENV_NAME=env
ARG ENV_FILE_NAME=None
RUN if [ "$ENV_FILE_NAME" = "None" ]; then \
        echo "ERROR: You must pass --build-arg ENV_FILE_NAME=<name>"; \
        exit 1; \
    fi
COPY ${ENV_FILE_NAME} /srv/conda_env.yml

# ------------------------------------------------------------------------------
# Create conda environment (build-time only)
# ------------------------------------------------------------------------------

RUN (source ${CONDA_DIR}/bin/activate "" && conda env create -f /srv/conda_env.yml -n ${ENV_NAME})

# ------------------------------------------------------------------------------
# Runtime
# ------------------------------------------------------------------------------
ENTRYPOINT ["tini", "--"]
CMD ["/bin/bash"]
