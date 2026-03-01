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
QUANTITIESMAP=${11}

echo "--- CROWN Friends Compilation ---"
echo "Crown folder: ${CROWNFOLDER}"
echo "Install dir:  ${INSTALLDIR}"
echo "Build dir:    ${BUILDDIR}"
echo "Analysis:     ${ANALYSIS}"

# Exit on any error or pipe failure
set -o pipefail
set -e

# Use 2 threads for Friends compilation to avoid OOM during linking
THREADS=2

echo "Using ${THREADS} threads for compilation"
echo "Active Python: $(which python)"
echo "Active CMake:  $(which cmake)"

# Ensure Build Directory exists
mkdir -p "${BUILDDIR}"

# --- CMake Configuration ---
# We use the compilers and libraries provided by the container's Conda 'env'
if cmake "${CROWNFOLDER}" \
    -DANALYSIS="${ANALYSIS}" \
    -DCONFIG="${CONFIG}" \
    -DSAMPLES="${SAMPLES}" \
    -DERAS="${ERAS}" \
    -DSCOPES="${SCOPE}" \
    -DSHIFTS="${SHIFTS}" \
    -DINSTALLDIR="${INSTALLDIR}" \
    -DPRODUCTION=True \
    -DFRIENDS=true \
    -DQUANTITIESMAP="${QUANTITIESMAP}" \
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
    echo "CROWN Friends build and installation successful."
else
    echo "ERROR: Build failed. See ${BUILDDIR}/build.log"
    exit 1
fi

# --- Post-Processing (Tarball) ---
echo "Finished the compilation and starting to make the *.tar.gz archive"
cd "${INSTALLDIR}"
# Ensure the tarball isn't trying to archive itself if it already exists
touch "${TARBALLNAME}"
tar -czvf "${TARBALLNAME}" --exclude="${TARBALLNAME}" .
