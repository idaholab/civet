#!/bin/bash
#
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# The recipes used internally at INL
# may depend on these environment
# variables being set.
# Primarily used for testing since our client_launcher
# takes care of all this normally.
NUM_PROCS=$(nproc --all)
NUM_JOBS=$(expr $NUM_PROCS / 4)
echo "Using $NUM_JOBS/$NUM_PROCS processors"
export BUILD_ROOT=${BUILD_ROOT:=$HOME/build_root}
export MOOSE_JOBS=${MOOSE_JOBS:=$NUM_JOBS}
export JOBS=${JOBS:=$NUM_JOBS}
export RUNJOBS=${RUNJOBS:=$NUM_JOBS}
export LOAD=${LOAD:=$NUM_JOBS}
export OPTIMIZED_BUILD=${OPTIMIZED_BUILD:=0}

# Load the required module for the config
module purge
module load moose-dev-gcc

CLIENT_NAME=client_name
# CONFIG options are:
# linux-gnu linux-gnu-coverage linux-valgrind linux-gnu-timing: requires moose-dev-gcc
# linux-intel : requires moose-dev-intel
# linux-clang : requires moose-dev-clang
CONFIG=linux-gnu
BUILD_KEY="123"
URL="server"
SCRIPT_DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
"$SCRIPT_DIR"/client.py --url "$URL" --name "$CLIENT_NAME" --config "$CONFIG" --build-key "$BUILD_KEY" --insecure
