# This is to allow for passing additional arguments to the test system.
# For example: make test ci.tests
# These extra arguments need to be ignored by make.
ifeq ($(firstword $(MAKECMDGOALS)),$(filter $(firstword $(MAKECMDGOALS)), test coverage))
  # use the rest as arguments
  TEST_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  # ...and turn them into do-nothing targets
  $(eval $(TEST_ARGS):;@:)
endif

CIVET_TEST_JOBS ?= 12

ifeq ($(SELENIUM_TEST),1)
	MAX_MISSING_LINES := 74
else
	MAX_MISSING_LINES := 76
endif

py_files := $(shell git ls-files '*.py')

all: coverage check

.PHONY: test
test: 
	python -Werror ./manage.py test --parallel=$(CIVET_TEST_JOBS) $(TEST_ARGS)

.coverage: $(py_files)
	@export COVERAGE_PROCESS_START="./.coveragerc"
	@printf "import coverage\ncoverage.process_startup()\n" > sitecustomize.py
	@export PYTHONWARNINGS="error"
	coverage erase
	coverage run --parallel-mode --source "." ./manage.py test --parallel=$(CIVET_TEST_JOBS) $(TEST_ARGS)
	coverage combine
	@rm -f sitecustomize.py

.PHONY: coverage
coverage: .coverage
	coverage report -m

htmlcov/index.html: .coverage
	coverage html --title='CIVET Coverage' --fail-under=99

.PHONY: htmlcov
htmlcov: htmlcov/index.html

.PHONY: check
check: .coverage
	@missing_lines=`coverage report |tail -1 |awk '{printf $$3; }'`; \
	if [ $(MAX_MISSING_LINES) -ge $$missing_lines ]; then \
		echo "PASSED: Missing lines ($$missing_lines) <= than max $(MAX_MISSING_LINES)"; \
	else \
		echo "FAILED: More missing lines ($$missing_lines) than the max $(MAX_MISSING_LINES)"; \
		exit 1; \
	fi

.PHONY: clean
clean:
	rm -f .coverage
	find . -name '*.pyc' -delete
	rm -rf htmlcov
