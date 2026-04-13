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
# setup with analysis clone if needed
set -o pipefail
set -e
source ${ANALYSIS_PATH}/CROWN/init.sh ${ANALYSIS}
# remove conda prefix from $PATH so cmakes uses the LCG stack python and not the conda one
if [[ ! -z "${CONDA_PREFIX}" ]]; then
	PATH=$(echo ${PATH} | sed "s@${CONDA_PREFIX}@@g")
	# PATH=$(echo ${PATH} | sed 's%/cvmfs/etp.kit.edu/[^:]*:%%g')
	CONDA_PYTHON_EXE=""
	CONDA_EXE=""
	CONDA_PREFIX=""
fi
# use a fourth of the machine for compiling
THREADS_AVAILABLE=$(grep -c ^processor /proc/cpuinfo)
THREADS=$((THREADS_AVAILABLE / 4))
echo "Using ${THREADS} threads for the compilation"
which cmake

if cmake ${CROWNFOLDER} \
	-DANALYSIS=${ANALYSIS} \
	-DCONFIG=${CONFIG} \
	-DSAMPLES=${SAMPLES} \
	-DERAS=${ERAS} \
	-DSCOPES=${SCOPE} \
	-DSHIFTS=${SHIFTS} \
	-DTHREADS=${EXECUTABLE_THREADS} \
	-DINSTALLDIR=${INSTALLDIR} \
	-DPRODUCTION=True \
	-B${BUILDDIR} 2>&1 | tee ${BUILDDIR}/cmake.log; then
	echo "CMake finished successfully"
else
	echo "-------------------------------------------------------------------------"
	echo "CMake failed, check the log file ${BUILDDIR}/cmake.log for more information"
	echo "-------------------------------------------------------------------------"
	sleep 0.1 # wait for the log file to be written
	exit 1
fi
cd ${BUILDDIR}
echo "Finished preparing the compilation and starting to compile"
make install -j ${THREADS} 2>&1 | tee ${BUILDDIR}/build.log
echo "Finished the compilation"
