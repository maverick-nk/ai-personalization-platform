import pytest
from app.catalog import build_catalog, build_trending
from app.config import Settings


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def catalog(settings):
    return build_catalog(settings)


def test_build_catalog_length(settings, catalog):
    assert len(catalog) == len(settings.content_catalog)


def test_build_catalog_fields(catalog):
    for item in catalog:
        assert item.content_id
        assert item.genre
        assert item.title


def test_build_trending_order(settings, catalog):
    trending = build_trending(settings, catalog)
    ids = [item.content_id for item in trending]
    assert ids == settings.trending_content_ids


def test_build_trending_skips_unknown_id(catalog, caplog):
    settings = Settings(trending_content_ids=["nonexistent", "c001"])
    trending = build_trending(settings, catalog)
    assert len(trending) == 1
    assert trending[0].content_id == "c001"
    assert "nonexistent" in caplog.text


def test_build_trending_all_missing_returns_empty(catalog, caplog):
    settings = Settings(trending_content_ids=["x999", "x998"])
    trending = build_trending(settings, catalog)
    assert trending == []
    assert "x999" in caplog.text
    assert "x998" in caplog.text


def test_build_trending_empty_config(catalog):
    settings = Settings(trending_content_ids=[])
    assert build_trending(settings, catalog) == []
