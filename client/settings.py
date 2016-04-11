"""
This file will be sourced by the INL client.
Separated out for easier upgrades of the client.
Besides the required settings, you can do any valid ptyhon
to setup the required environment.
REQUIRED:
  SERVERS: a list of servers
  CONFIG_MODULES: A dict of build targets
"""

"""
A list of servers to poll.
Each server is tuple:
  url: URL to the server, eg https://localhost
  build_key: Build key assigned by the CIVET server for a user
  certificate: Path to the certificate of the server. If False
              then SSL cert verification is not done.
"""
SERVERS = [('server0', 'build_key', False), ]

"""
dict of build conigs this client polls for.
Each entry conforms to the following:
  key: name of build config. This is assigned to the recipe on the CIVET server.
  value: list of modules to load before running the job.
"""
CONFIG_MODULES = {'linux-gnu': ['moose-dev-gcc'],
#    'linux-clang': ['moose-dev-clang'],
#    'linux-valgrind': ['moose-dev-gcc'],
#    'linux-gnu-coverage': ['moose-dev-gcc'],
#    'linux-intel': ['moose-dev-intel'],
#    'linux-gnu-timing': ['moose-dev-gcc'],
    }

ENVIRONMENT = {
    "MAKE_JOBS": "16",
    "MAX_MAKE_LOAD": "16",
    "TEST_JOBS": "16",
    "MAX_TEST_LOAD": "16",
    "NUM_JOBS": "8",
    }
