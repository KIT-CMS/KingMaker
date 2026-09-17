#! /bin/bash

CROWNFOLDER=${1}
ANALYSIS=${2}
CONFIG=${3}
SAMPLES=${4}
ERAS=${5}
SCOPE=${6}
SHIFTS=${7}
INSTALLDIR=${8}
BUILDDIR=${9}
TARBALLNAME=${10}
EXECUTABLE_THREADS=${11}

echo "--- CROWN Production Compilation ---"
echo "Crown folder: ${CROWNFOLDER}"
echo "Install dir:  ${INSTALLDIR}"
echo "Build dir:    ${BUILDDIR}"
echo "Analysis:     ${ANALYSIS}"

# Exit on any error or pipe failure
set -o pipefail
set -e

# Use a fourth of the machine for compiling, capped so several builds can
# run concurrently on the same node without blowing past its memory limit
THREADS_AVAILABLE=$(grep -c ^processor /proc/cpuinfo)
THREADS=$((THREADS_AVAILABLE / 4))
[ "$THREADS" -lt 1 ] && THREADS=1
[ "$THREADS" -gt 6 ] && THREADS=6

echo "Using ${THREADS} threads for compilation"
echo "Active Python: $(which python)"
echo "Active CMake:  $(which cmake)"

# Ensure Build Directory exists
mkdir -p "${BUILDDIR}"

# --- CMake Configuration ---
# We use the compilers and libraries provided by the container's Conda 'env'
CONDA_CC="$(find "${CONDA_PREFIX}/bin" -maxdepth 1 -name '*-cc' | head -n1)"
CONDA_CXX="$(find "${CONDA_PREFIX}/bin" -maxdepth 1 -name '*-c++' | head -n1)"
if [[ -z "${CONDA_CC}" || -z "${CONDA_CXX}" ]]; then
    echo "ERROR: Could not locate conda env compilers in ${CONDA_PREFIX}/bin"
    exit 1
fi
echo "Using CC:  ${CONDA_CC}"
echo "Using CXX: ${CONDA_CXX}"

if cmake "${CROWNFOLDER}" \
    -DANALYSIS="${ANALYSIS}" \
    -DCONFIG="${CONFIG}" \
    -DSAMPLES="${SAMPLES}" \
    -DERAS="${ERAS}" \
    -DSCOPES="${SCOPE}" \
    -DSHIFTS="${SHIFTS}" \
    -DTHREADS="${EXECUTABLE_THREADS}" \
    -DINSTALLDIR="${INSTALLDIR}" \
    -DPRODUCTION=True \
    -DCMAKE_PREFIX_PATH="$(root-config --prefix)" \
    -DCMAKE_C_COMPILER="${CONDA_CC}" \
    -DCMAKE_CXX_COMPILER="${CONDA_CXX}" \
    -B"${BUILDDIR}" 2>&1 | tee "${BUILDDIR}/cmake.log"; then
    echo "CMake finished successfully"
else
    echo "-------------------------------------------------------------------------"
    echo "CMake failed, check the log file ${BUILDDIR}/cmake.log"
    echo "-------------------------------------------------------------------------"
    sleep 0.1 # wait for the log file to be written
    exit 1
fi

cd "${BUILDDIR}"
echo "Starting compilation..."

if make install -j "${THREADS}" 2>&1 | tee "${BUILDDIR}/build.log"; then
    echo "CROWN library build and installation successful."
else
    echo "ERROR: Build failed. See ${BUILDDIR}/build.log"
    exit 1
fi
