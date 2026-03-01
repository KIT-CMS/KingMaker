#! /bin/bash

# Arguments passed by Law/KingMaker
CROWNFOLDER=${1}
INSTALLDIR=${2}
BUILDDIR=${3}
ANALYSIS=${4}

echo "--- CROWN Library Compilation ---"
echo "Crown folder: ${CROWNFOLDER}"
echo "Install dir:  ${INSTALLDIR}"
echo "Build dir:    ${BUILDDIR}"
echo "Analysis:     ${ANALYSIS}"

# Exit on any error or pipe failure
set -o pipefail
set -e

# --- Resource Calculation ---
# Use 1/4 of available cores for compilation to avoid overloading the node (min=1)
THREADS_AVAILABLE=$(grep -c ^processor /proc/cpuinfo)
THREADS=$((THREADS_AVAILABLE / 4))
[ "$THREADS" -lt 1 ] && THREADS=1

echo "Using ${THREADS} threads for compilation."
echo "Active Python: $(which python)"
echo "Active CMake:  $(which cmake)"

# Ensure Build Directory exists
mkdir -p "${BUILDDIR}"

# --- CMake Configuration ---
# We use the compilers and libraries provided by the container's Conda 'env'
if cmake "${CROWNFOLDER}" \
    -DBUILD_CROWNLIB_ONLY=ON \
    -DINSTALLDIR="${INSTALLDIR}" \
    -DANALYSIS="${ANALYSIS}" \
    -B"${BUILDDIR}" 2>&1 | tee "${BUILDDIR}/cmake.log"; then
    echo "CMake finished successful."
else
	echo "-------------------------------------------------------------------------"
	echo "CMake failed, check the log file ${BUILDDIR}/cmake.log for more information"
	echo "-------------------------------------------------------------------------"
	sleep 0.1 # wait for the log file to be written
    exit 1
fi

# --- Build and Install ---
cd "${BUILDDIR}"
echo "Starting 'make install'..."

if make install -j "${THREADS}" 2>&1 | tee "${BUILDDIR}/build.log"; then
    echo "CROWN library build and installation successful."
else
    echo "ERROR: Build failed. See ${BUILDDIR}/build.log"
    exit 1
fi
