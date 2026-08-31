from datetime import datetime, timedelta, timezone

from date_utils import filter_recent_items, is_recent, parse_published_at


def test_parse_published_at_handles_rfc822_format():
    dt = parse_published_at("Thu, 20 Aug 2026 10:00:00 GMT")
    assert dt == datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_published_at_handles_iso_date_only():
    dt = parse_published_at("2026-08-20")
    assert dt.year == 2026 and dt.month == 8 and dt.day == 20


def test_parse_published_at_handles_iso_datetime_with_z_suffix():
    dt = parse_published_at("2026-08-20T10:00:00Z")
    assert dt == datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_published_at_returns_none_for_garbage():
    assert parse_published_at("isso não é uma data") is None
    assert parse_published_at("") is None
    assert parse_published_at(None) is None


def test_is_recent_true_for_unknown_date():
    assert is_recent(None, max_age_days=30) is True
    assert is_recent("lixo", max_age_days=30) is True


def test_is_recent_true_for_date_within_window():
    recent = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
    assert is_recent(recent, max_age_days=30) is True


def test_is_recent_false_for_old_date():
    old = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%Y-%m-%d")
    assert is_recent(old, max_age_days=30) is False


def test_filter_recent_items_keeps_recent_and_unknown_drops_old():
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    old = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")

    items = [
        {"title": "Recente", "published_at": recent},
        {"title": "Antiga", "published_at": old},
        {"title": "Sem data", "published_at": None},
    ]

    filtered = filter_recent_items(items, max_age_days=30)
    titles = {item["title"] for item in filtered}
    assert titles == {"Recente", "Sem data"}
