from app.stats import median, parse_date, summarize, to_float, to_int


def test_median_odd_even_empty():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 3, 2]) == 2.5
    assert median([]) is None


def test_summarize():
    assert summarize([]) == {"count": 0}
    assert summarize([None]) == {"count": 0}
    s = summarize([100, 300, 200, 400])
    assert s == {"count": 4, "median": 250, "average": 250, "low": 100, "high": 400}


def test_to_float_and_int_are_safe():
    assert to_float("1,234.50") == 1234.5
    assert to_float(" $12 ") == 12.0
    assert to_float(".00") == 0.0
    for junk in (None, "", "  ", "N/A", "abc"):
        assert to_float(junk) is None
        assert to_int(junk) is None
    assert to_int("3.0") == 3
    assert to_int(" 2 ") == 2


def test_parse_date():
    assert parse_date("04/12/2006", "%m/%d/%Y") == "2006-04-12"
    assert parse_date("2023-10-16", "%Y-%m-%d") == "2023-10-16"
    assert parse_date("2005-12-29 0:00:00", "%Y-%m-%d") == "2005-12-29"
    assert parse_date("01/01/1900", "%m/%d/%Y") is None
    assert parse_date("", "%m/%d/%Y") is None
    assert parse_date("13/45/2020", "%m/%d/%Y") is None
