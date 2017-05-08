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
# init.d style control of civet clients
CIVET_DIR=/home/moosetest/civet/civet/client
EXE=${CIVET_DIR}/inl_client.py
export MAKE_JOBS=16
export TEST_JOBS=16
# MOOSE run_tests has the option to set the max system load.
# This is used so that when there are multiple CIVET clients
# running, run_tests doesn't overload the machine. However,
# if one client is idle, this allows the other to use all
# the CPUs
export MAX_TEST_LOAD=16

# Similar to run_tests. Use the whole machine when available
# but avoid overloading the machine.
export MAX_MAKE_LOAD=17

# Default number of jobs.
NUM_JOBS=8
# Number of CIVET clients to start
NUM_CLIENTS=2

module purge
module load moose-dev-gcc

function control()
{
  local cmd=${1-:"stop"}
  for i in $(seq 0 $((NUM_CLIENTS-1)) ); do
    echo "Client $i"
    $EXE --num-jobs $NUM_JOBS --client $i --daemon $cmd
  done
}


function get_pid()
{
  local client_num=${1:?"Need a client number"}
  local pid_file="$HOME/civet_client_${HOSTNAME}_${client_num}.pid"
  if [ -e "$pid_file" ]; then
    cat "$pid_file"
  fi
}

function send_sig()
{
  local sig=${1:?"Need a signal to send"}
  for i in $(seq 0 $(($NUM_CLIENTS-1)) ); do
    echo "Client $i"
    local pid=$(get_pid $i)
    if [ -z "$pid" ]; then
      echo "No pid found"
    else
      echo "Sending $sig to $pid"
      kill "$sig" "$pid"
    fi
  done
}

function graceful_restart()
{
  while true; do
    send_sig "-USR2"
    local finished=0
    for i in $(seq 0 $((NUM_CLIENTS-1)) ); do
      local pid=$(get_pid $i)
      if [ -z "$pid" ]; then
        finished=$((finished+1))
      fi
    done
    if [ "$finished" == "$NUM_CLIENTS" ]; then
      break
    fi
    sleep 5
  done
}

case "$1" in
  start)
    control start
    ;;
  stop)
    control stop
    ;;
  restart)
    control graceful_restart
    ;;
  cancel)
    send_sig "-USR1"
    ;;
  graceful)
    send_sig "-USR2"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|cancel|graceful}"
    exit 2
esac
exit $?
