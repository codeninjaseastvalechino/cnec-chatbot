"""Tests for core/date_utils.py — date/time resolution and conflict detection."""
import pytest
from datetime import date, datetime
from unittest.mock import patch

from core.date_utils import resolve_date, resolve_time, resolve_datetime

TODAY = date(2026, 6, 4)   # Thursday
FIXED_NOW = datetime(2026, 6, 4, 12, 0, 0)


def _resolve(date_str, today=TODAY):
    with patch("core.date_utils.date") as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        return resolve_date(date_str)


# ---------------------------------------------------------------------------
# resolve_date — relative words
# ---------------------------------------------------------------------------

class TestResolveDateRelative:
    def test_today(self):
        result = _resolve("today")
        assert result.date() == TODAY

    def test_tomorrow(self):
        result = _resolve("tomorrow")
        assert result.date() == date(2026, 6, 5)

    def test_case_insensitive(self):
        assert _resolve("TODAY").date() == TODAY
        assert _resolve("Tomorrow").date() == date(2026, 6, 5)


# ---------------------------------------------------------------------------
# resolve_date — day names
# ---------------------------------------------------------------------------

class TestResolveDateDayName:
    def test_next_friday(self):
        # Today is Thursday June 4 → Friday = June 5
        result = _resolve("Friday")
        assert result.date() == date(2026, 6, 5)

    def test_next_monday(self):
        # Today is Thursday → Monday = June 8
        result = _resolve("Monday")
        assert result.date() == date(2026, 6, 8)

    def test_same_day_goes_to_next_week(self):
        # Today is Thursday → "Thursday" = next Thursday (June 11)
        result = _resolve("Thursday")
        assert result.date() == date(2026, 6, 11)

    def test_day_name_case_insensitive(self):
        assert _resolve("friday").date() == date(2026, 6, 5)
        assert _resolve("FRIDAY").date() == date(2026, 6, 5)


# ---------------------------------------------------------------------------
# resolve_date — explicit month + day
# ---------------------------------------------------------------------------

class TestResolveDateExplicit:
    def test_june_9th(self):
        result = _resolve("June 9th")
        assert result.date() == date(2026, 6, 9)

    def test_june_9_no_suffix(self):
        result = _resolve("June 9")
        assert result.date() == date(2026, 6, 9)

    def test_month_case_insensitive(self):
        assert _resolve("JUNE 9th").date() == date(2026, 6, 9)

    def test_past_month_rolls_to_next_year(self):
        # January is in the past relative to June 4 → rolls to 2027
        result = _resolve("January 15")
        assert result.date() == date(2027, 1, 15)


# ---------------------------------------------------------------------------
# resolve_date — day name + explicit date (conflict detection)
# ---------------------------------------------------------------------------

class TestResolveDateConflict:
    def test_friday_june_6_is_saturday(self):
        with pytest.raises(ValueError) as exc:
            _resolve("Friday June 6th")
        msg = str(exc.value)
        assert "Saturday" in msg
        assert "Friday" in msg
        assert "June 5" in msg   # nearest Friday suggested

    def test_monday_june_9_is_tuesday(self):
        with pytest.raises(ValueError) as exc:
            _resolve("Monday June 9th")
        msg = str(exc.value)
        assert "Tuesday" in msg
        assert "Monday" in msg
        assert "June 8" in msg   # nearest Monday suggested

    def test_no_conflict_friday_june_5(self):
        result = _resolve("Friday June 5th")
        assert result.date() == date(2026, 6, 5)

    def test_no_conflict_tuesday_june_9(self):
        result = _resolve("Tuesday June 9th")
        assert result.date() == date(2026, 6, 9)


# ---------------------------------------------------------------------------
# resolve_date — invalid input
# ---------------------------------------------------------------------------

class TestResolveDateOrdinalOnly:
    def test_8th_current_month(self):
        # Today is June 4 — "8th" = June 8
        result = _resolve("8th")
        assert result.date() == date(2026, 6, 8)

    def test_the_8th(self):
        result = _resolve("the 8th")
        assert result.date() == date(2026, 6, 8)

    def test_1st_past_rolls_to_next_month(self):
        # Today is June 4 — June 1 is past → rolls to July 1
        result = _resolve("1st")
        assert result.date() == date(2026, 7, 1)

    def test_past_day_rolls_to_next_month(self):
        # Today is June 4 — "2nd" is past → July 2
        result = _resolve("2nd")
        assert result.date() == date(2026, 7, 2)

    def test_11th_future_same_month(self):
        result = _resolve("11th")
        assert result.date() == date(2026, 6, 11)

    def test_ordinal_without_suffix(self):
        # "8" with no suffix — matched by the regex since suffix is optional
        result = _resolve("8")
        assert result.date() == date(2026, 6, 8)


class TestResolveDateInvalid:
    def test_gibberish_raises(self):
        with pytest.raises(ValueError) as exc:
            _resolve("blahblah")
        assert "Could not understand" in str(exc.value)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _resolve("")


# ---------------------------------------------------------------------------
# resolve_time
# ---------------------------------------------------------------------------

class TestResolveTime:
    def test_10am(self):
        assert resolve_time("10am") == (10, 0)

    def test_2pm(self):
        assert resolve_time("2pm") == (14, 0)

    def test_12pm_noon(self):
        assert resolve_time("12pm") == (12, 0)

    def test_12am_midnight(self):
        assert resolve_time("12am") == (0, 0)

    def test_colon_format(self):
        assert resolve_time("2:30 PM") == (14, 30)

    def test_24_hour(self):
        assert resolve_time("14:00") == (14, 0)

    def test_no_meridiem_treated_as_is(self):
        assert resolve_time("9") == (9, 0)

    def test_case_insensitive(self):
        assert resolve_time("10AM") == (10, 0)
        assert resolve_time("10Am") == (10, 0)

    def test_gibberish_raises(self):
        with pytest.raises(ValueError) as exc:
            resolve_time("noon")
        assert "Could not understand" in str(exc.value)


# ---------------------------------------------------------------------------
# resolve_datetime — integration
# ---------------------------------------------------------------------------

class TestResolveDatetime:
    def test_friday_10am(self):
        with patch("core.date_utils.date") as mock_date:
            mock_date.today.return_value = TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            result = resolve_datetime("Friday", "10am")
        assert result.date() == date(2026, 6, 5)
        assert result.hour == 10
        assert result.minute == 0

    def test_conflict_propagates(self):
        with patch("core.date_utils.date") as mock_date:
            mock_date.today.return_value = TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            with pytest.raises(ValueError) as exc:
                resolve_datetime("Friday June 6th", "10am")
        assert "Saturday" in str(exc.value)

    def test_bad_time_propagates(self):
        with patch("core.date_utils.date") as mock_date:
            mock_date.today.return_value = TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            with pytest.raises(ValueError) as exc:
                resolve_datetime("Friday", "noon")
        assert "Could not understand" in str(exc.value)
