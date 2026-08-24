.PHONY: lint lint-file test test-unit test-direct deploy-hello

# genvm-lint's human-readable output uses Unicode checkmarks that crash under the
# default Windows cp1252 console encoding. See docs/RUNNER.md "Windows note".
export PYTHONIOENCODING = utf-8
export PYTHONUTF8 = 1

CONTRACTS := $(shell find contracts -name '*.py' 2>/dev/null)

lint:
	@for f in $(CONTRACTS); do \
		echo "== $$f =="; \
		genvm-lint check $$f || exit 1; \
	done

lint-file:
	genvm-lint check $(FILE)

test: test-unit test-direct

test-unit:
	pytest tests/unit -v

# On Windows, run this under WSL, not a native shell — see docs/RUNNER.md
# "Direct-mode test setup" for the one-time cache workaround it needs.
test-direct:
	pytest tests/direct -v

deploy-hello:
	genlayer deploy --contract contracts/hello.py --args '"hello from veritas phase 0"'
