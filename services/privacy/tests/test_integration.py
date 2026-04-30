"""Integration tests for the privacy service.

Requires a running Postgres instance with the 'privacy' database.
Run with:
    DATABASE_URL=postgresql+asyncpg://platform:platform@localhost:5432/privacy \
    PSEUDONYMIZE_SECRET=test-secret \
    uv run pytest tests/test_integration.py -v
"""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ,
    reason="DATABASE_URL not set — skipping integration tests",
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://platform:platform@localhost:5432/privacy"
)


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(DATABASE_URL)

    # SQLAlchemy's create_all cannot emit PARTITION BY RANGE DDL, so we create
    # the schema directly. audit_log gets a catch-all partition covering all dates
    # so every test INSERT lands somewhere valid without needing partition management.
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS consent (
                user_pseudo_id  VARCHAR      PRIMARY KEY,
                consent_granted BOOLEAN      NOT NULL DEFAULT false,
                updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id              INTEGER      GENERATED ALWAYS AS IDENTITY,
                user_pseudo_id  VARCHAR      NOT NULL,
                action          VARCHAR(10)  NOT NULL,
                timestamp       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                reason          VARCHAR(255),
                PRIMARY KEY (id, timestamp)
            ) PARTITION BY RANGE (timestamp)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log_test
            PARTITION OF audit_log
            FOR VALUES FROM ('2000-01-01') TO ('2100-01-01')
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS audit_log_user_idx ON audit_log (user_pseudo_id)"
        ))

    yield engine

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS audit_log_test"))
        await conn.execute(text("DROP TABLE IF EXISTS audit_log CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS consent"))
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_engine):
    from app.database import get_session
    from app.main import app

    test_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── consent PATCH ──────────────────────────────────────────────────────────────

async def test_grant_consent_returns_200(client):
    resp = await client.patch(
        "/privacy/consent/user1",
        json={"consent_granted": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consent_granted"] is True
    assert "user_pseudo_id" in data
    assert "updated_at" in data


async def test_revoke_consent_returns_200(client):
    await client.patch("/privacy/consent/user1", json={"consent_granted": True})
    resp = await client.patch("/privacy/consent/user1", json={"consent_granted": False})
    assert resp.status_code == 200
    assert resp.json()["consent_granted"] is False


async def test_grant_creates_audit_log_entry(client):
    await client.patch(
        "/privacy/consent/user2",
        json={"consent_granted": True, "reason": "onboarding"},
    )
    audit = await client.get("/privacy/audit/user2")
    assert audit.status_code == 200
    entries = audit.json()
    assert len(entries) == 1
    assert entries[0]["action"] == "GRANT"
    assert entries[0]["reason"] == "onboarding"


async def test_revoke_appends_audit_log_entry(client):
    await client.patch("/privacy/consent/user3", json={"consent_granted": True})
    await client.patch("/privacy/consent/user3", json={"consent_granted": False, "reason": "user request"})
    entries = (await client.get("/privacy/audit/user3")).json()
    assert len(entries) == 2
    # Most recent entry first
    assert entries[0]["action"] == "REVOKE"
    assert entries[1]["action"] == "GRANT"


# ── audit GET ─────────────────────────────────────────────────────────────────

async def test_audit_returns_empty_list_for_unknown_user(client):
    resp = await client.get("/privacy/audit/nobody")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_audit_ordered_newest_first(client):
    await client.patch("/privacy/consent/user4", json={"consent_granted": True})
    await client.patch("/privacy/consent/user4", json={"consent_granted": False})
    await client.patch("/privacy/consent/user4", json={"consent_granted": True})
    entries = (await client.get("/privacy/audit/user4")).json()
    actions = [e["action"] for e in entries]
    assert actions == ["GRANT", "REVOKE", "GRANT"]


# ── internal consent check ────────────────────────────────────────────────────

async def test_internal_check_unknown_user_returns_false(client):
    from app.pseudonymize import pseudonymize
    import os
    secret = os.environ.get("PSEUDONYMIZE_SECRET", "test-secret")
    pseudo = pseudonymize("ghost-user", secret)
    resp = await client.get(f"/internal/consent/check/{pseudo}")
    assert resp.status_code == 200
    assert resp.json()["consent_granted"] is False


async def test_internal_check_returns_true_after_grant(client):
    grant_resp = await client.patch("/privacy/consent/user5", json={"consent_granted": True})
    pseudo_id = grant_resp.json()["user_pseudo_id"]
    check = await client.get(f"/internal/consent/check/{pseudo_id}")
    assert check.json()["consent_granted"] is True


async def test_revocation_takes_effect_immediately(client):
    grant = await client.patch("/privacy/consent/user6", json={"consent_granted": True})
    pseudo_id = grant.json()["user_pseudo_id"]

    await client.patch("/privacy/consent/user6", json={"consent_granted": False})

    check = await client.get(f"/internal/consent/check/{pseudo_id}")
    assert check.json()["consent_granted"] is False


# ── pseudonymization consistency ──────────────────────────────────────────────

async def test_public_and_internal_use_same_pseudo_id(client):
    # Grant via public endpoint (raw user_id) → check via internal (pseudo_id)
    grant = await client.patch("/privacy/consent/user7", json={"consent_granted": True})
    pseudo_id = grant.json()["user_pseudo_id"]

    check = await client.get(f"/internal/consent/check/{pseudo_id}")
    assert check.json()["consent_granted"] is True

    audit = await client.get("/privacy/audit/user7")
    assert audit.json()[0]["action"] == "GRANT"
