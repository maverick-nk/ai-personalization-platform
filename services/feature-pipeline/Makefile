.PHONY: install install-pipeline download-connectors test test-unit test-integration run clean

# ── Environment ───────────────────────────────────────────────────────────────

# PyFlink requires Java 11/17/21. Java 26 (default on this machine) is not supported.
# Override JAVA_HOME if openjdk@21 is installed at a different path.
JAVA_HOME ?= $(shell brew --prefix openjdk@21 2>/dev/null)/libexec/openjdk.jdk/Contents/Home

# apache-flink-libraries (JARs) are installed into the root venv, not the
# feature-pipeline venv, because uv build isolation prevents setuptools pinning
# in nested venvs. FLINK_HOME tells PyFlink where to find lib/ and opt/ JARs.
# We resolve it from the repo root venv (two levels up from this Makefile).
# Override if you have a standalone Flink installation.
ROOT_VENV_PYTHON := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))/../../.venv/bin/python
FLINK_HOME ?= $(shell $(ROOT_VENV_PYTHON) -c "import pyflink, os; print(os.path.dirname(pyflink.__file__))" 2>/dev/null)

# ── Install ───────────────────────────────────────────────────────────────────

install:
	uv sync --dev

# apache-beam 2.48.0 has no ARM64 wheel — must be built from source.
# Building it requires:
#   - setuptools<67: pkg_resources is a top-level module in this range;
#     newer versions moved it, breaking apache-beam's setup.py (line 28).
#   - wheel: provides the bdist_wheel command apache-beam's build calls.
#   - --no-build-isolation: uses the venv's packages so the pinned
#     setuptools above is visible during the build instead of a fresh env.
install-pipeline: install download-connectors
	uv pip install "setuptools==65.5.1" wheel --reinstall
	uv pip install apache-flink==1.20.3 --no-build-isolation

# Download the Kafka connector JAR (not bundled with apache-flink-libraries).
# Version 3.3.0-1.20 is the latest connector release for Flink 1.20.x.
download-connectors:
	mkdir -p connectors
	@test -f connectors/flink-sql-connector-kafka-3.3.0-1.20.jar || \
		curl -fL -o connectors/flink-sql-connector-kafka-3.3.0-1.20.jar \
		https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar

# ── Test ──────────────────────────────────────────────────────────────────────

test-unit:
	uv run pytest tests/test_features.py -v

# Requires: make install-pipeline + docker-compose up kafka redis + Java 21
test-integration:
	@if [ -z "$(shell brew --prefix openjdk@21 2>/dev/null)" ]; then \
		echo "Error: openjdk@21 not found. Run: brew install openjdk@21"; exit 1; \
	fi
	JAVA_HOME="$(JAVA_HOME)" FLINK_HOME="$(FLINK_HOME)" uv run pytest tests/test_integration.py -v -s

test: test-unit test-integration

# ── Run ───────────────────────────────────────────────────────────────────────

run:
	@if [ -z "$(shell brew --prefix openjdk@21 2>/dev/null)" ]; then \
		echo "Error: openjdk@21 not found. Run: brew install openjdk@21"; exit 1; \
	fi
	JAVA_HOME="$(JAVA_HOME)" FLINK_HOME="$(FLINK_HOME)" uv run feature-pipeline

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	rm -rf .venv uv.lock __pycache__ .pytest_cache
