#!/bin/bash
# The recipes used internally at INL
# may depend on these environment
# variables being set.
# Primarily used for testing since our client_launcher
# takes care of all this normally.
NUM_PROCS=$(nproc --all)
NUM_JOBS=$(expr $NUM_PROCS / 2)
echo "Using $NUM_JOBS/$NUM_PROCS processors"
export BUILD_ROOT=${BUILD_ROOT:=$HOME/build_root}
export MOOSE_JOBS=${MOOSE_JOBS:=$NUM_JOBS}
export JOBS=${JOBS:=$NUM_JOBS}
export RUNJOBS=${RUNJOBS:=$NUM_JOBS}
export LOAD=${LOAD:=$NUM_JOBS}
export OPTIMIZED_BUILD=${OPTIMIZED_BUILD:=0}
SCRIPT_DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
"$SCRIPT_DIR"/client.py $*
