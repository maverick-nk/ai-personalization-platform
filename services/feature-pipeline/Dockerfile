FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# default-jdk-headless resolves to Java 17 on Bookworm, Java 21 on Trixie —
# both are supported by Flink 1.20.3. gcc + libc6-dev are required to build
# pemja's C extension (PyFlink's Python-Java bridge). procps provides pgrep
# for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    gcc \
    libc6-dev \
    procps \
    && rm -rf /var/lib/apt/lists/*

# default-java is the arch- and distro-version-independent symlink.
ENV JAVA_HOME=/usr/lib/jvm/default-java

# Prepend the venv so bare `python` (used by the Flink JVM when discovering
# the pyflink bin path) resolves to the venv Python where pyflink is installed.
# PYFLINK_PYTHON is set for explicit UDF worker spawning as a belt-and-suspenders.
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYFLINK_PYTHON=/app/.venv/bin/python

WORKDIR /app

# ── Dependency layer (cached) ───────────────────────────────────────────────
# Install dependencies without the project itself so this slow layer
# (pemja C compile + apache-flink-libraries source build) is only invalidated
# when pyproject.toml / uv.lock changes, not on every app/ code change.
COPY pyproject.toml uv.lock ./
RUN uv sync --extra pipeline --frozen --no-dev --no-install-project

# ── Application layer ───────────────────────────────────────────────────────
COPY connectors/ connectors/
COPY app/ app/

# Install the project itself (fast: editable install + script creation only).
# Creates .venv/bin/feature-pipeline pointing to app.pipeline:main.
RUN uv sync --extra pipeline --frozen --no-dev

# Run via the venv Python directly — avoids uv re-syncing at container start
# (uv run without --extra pipeline would silently drop PyFlink from the env).
CMD ["/app/.venv/bin/python", "-m", "app.pipeline"]
