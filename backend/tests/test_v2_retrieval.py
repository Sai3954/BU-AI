from app.conflicts import find_conflicts
from app.retrieval import Doc, detect_level


def d(n, text, url=None, title="Page"):
    return Doc(n, url or f"https://www.belhaven.edu/p{n}", title, "x", ["all"], text, "current site")


def test_detect_level():
    assert detect_level("When is my DBA residency?") == "doctoral"
    assert detect_level("MBA tuition per credit hour") == "graduate"
    assert detect_level("Is there an undergraduate honors college?") == "undergraduate"
    assert detect_level("When is graduation?") == ""
    assert detect_level("When is graduation?", "doctoral") == "doctoral"
    assert detect_level("library hours", "international") == ""


def test_conflict_found_between_two_pages():
    c = find_conflicts([d(1, "Tuition is $650 per credit hour."), d(2, "Tuition is $695 per credit hour.")])
    assert c and c[0]["fact"] == "Tuition per credit hour"


def test_no_conflict_same_value_or_one_table_or_catalog_years():
    assert not find_conflicts([d(1, "$650 per credit hour"), d(2, "Cost: $650 per credit hour")])
    assert not find_conflicts([d(1, "MBA $650 per credit hour; DBA $795 per credit hour")])
    assert not find_conflicts([
        d(1, "$600 per credit hour", "https://www.belhaven.edu/catalog/2024-2025/fees"),
        d(2, "$650 per credit hour", "https://www.belhaven.edu/catalog/2025-2026/fees")])
