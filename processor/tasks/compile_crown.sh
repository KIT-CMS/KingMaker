#! /bin/bash
source $ANALYSIS_PATH/CROWN/init.sh

CROWNFOLDER=$1
ANALYSIS=$2
SAMPLES=$3
ERAS=$4
CHANNEL=$5
SHIFTS=$6
INSTALLDIR=$7
BUILDDIR=$8
TARBALLNAME=$9

which cmake

cmake $CROWNFOLDER \
 -DANALYSIS=$ANALYSIS \
 -DSAMPLES=$SAMPLES \
 -DERAS=$ERAS \
 -DCHANNELS=$CHANNEL \
 -DSHIFTS=$SHIFTS \
 -DINSTALLDIR=$INSTALLDIR \
 -B$BUILDDIR

cd $BUILDDIR
make install
cd $INSTALLDIR
touch $TARBALLNAME
tar -czvf $TARBALLNAME --exclude=$TARBALLNAME .