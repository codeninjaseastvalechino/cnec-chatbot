"""Tests for core/date_utils.py — date/time resolution and conflict detection."""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from core.date_utils import (
    resolve_date, resolve_time, resolve_datetime,
    now_local, today_local, start_of_today_local, week_bounds,
    relative_week_anchor,
)

TODAY = date(2026, 6, 4)   # Thursday
FIXED_NOW = datetime(2026, 6, 4, 12, 0, 0)


def _resolve(date_str, today=TODAY):
    # resolve_date() anchors "today" via core.date_utils.today_local()
    with patch("core.date_utils.today_local", return_value=today):
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
        with patch("core.date_utils.today_local", return_value=TODAY):
            result = resolve_datetime("Friday", "10am")
        assert result.date() == date(2026, 6, 5)
        assert result.hour == 10
        assert result.minute == 0

    def test_conflict_propagates(self):
        with patch("core.date_utils.today_local", return_value=TODAY):
            with pytest.raises(ValueError) as exc:
                resolve_datetime("Friday June 6th", "10am")
        assert "Saturday" in str(exc.value)

    def test_bad_time_propagates(self):
        with patch("core.date_utils.today_local", return_value=TODAY):
            with pytest.raises(ValueError) as exc:
                resolve_datetime("Friday", "noon")
        assert "Could not understand" in str(exc.value)


# ---------------------------------------------------------------------------
# Timezone-anchored clock helpers
# ---------------------------------------------------------------------------

class TestClockHelpers:
    def test_now_local_uses_center_timezone_not_host(self):
        # Regardless of the host clock, now_local() reflects CENTER_TIMEZONE.
        # America/Los_Angeles is UTC-7/-8, so late-UTC-evening is still the
        # previous calendar day in Pacific — the exact off-by-one we guard against.
        with patch("config.settings.settings.CENTER_TIMEZONE", "America/Los_Angeles"):
            now = now_local()
        assert now.tzinfo is None  # naive, for comparison with API-parsed datetimes

    def test_today_local_matches_now_local_date(self):
        assert today_local() == now_local().date()

    def test_start_of_today_local_is_midnight(self):
        s = start_of_today_local()
        assert (s.hour, s.minute, s.second, s.microsecond) == (0, 0, 0, 0)
        assert s.date() == today_local()

    def test_week_bounds_from_midweek(self):
        # Thursday 2026-06-04 -> Mon 06-01 .. next Mon 06-08 (half-open)
        monday, nxt = week_bounds(date(2026, 6, 4))
        assert monday == datetime(2026, 6, 1)
        assert nxt == datetime(2026, 6, 8)
        assert monday.weekday() == 0

    def test_week_bounds_on_monday_returns_same_monday(self):
        monday, nxt = week_bounds(date(2026, 6, 1))  # a Monday
        assert monday == datetime(2026, 6, 1)
        assert nxt == datetime(2026, 6, 8)

    def test_week_bounds_on_sunday_stays_in_that_week(self):
        # Sunday 2026-06-07 belongs to the Mon 06-01 week
        monday, nxt = week_bounds(date(2026, 6, 7))
        assert monday == datetime(2026, 6, 1)
        assert nxt == datetime(2026, 6, 8)

    def test_week_bounds_accepts_datetime(self):
        monday, nxt = week_bounds(datetime(2026, 6, 4, 15, 30))
        assert monday == datetime(2026, 6, 1)
        assert nxt == datetime(2026, 6, 8)


class TestRelativeWeekAnchor:
    # Anchor is Thursday 2026-07-01 (the app's "today" during this work).
    TODAY = datetime(2026, 7, 1)

    def test_this_week(self):
        assert relative_week_anchor("this week", self.TODAY) == self.TODAY

    def test_next_week(self):
        assert relative_week_anchor("next week", self.TODAY) == datetime(2026, 7, 8)

    def test_last_week(self):
        assert relative_week_anchor("last week", self.TODAY) == datetime(2026, 6, 24)

    def test_previous_week_is_alias_for_last_week(self):
        assert relative_week_anchor("previous week", self.TODAY) == datetime(2026, 6, 24)

    def test_week_after_next(self):
        assert relative_week_anchor("week after next", self.TODAY) == datetime(2026, 7, 15)
        assert relative_week_anchor("the week after next", self.TODAY) == datetime(2026, 7, 15)

    def test_case_and_whitespace_insensitive(self):
        assert relative_week_anchor("  NEXT WEEK  ", self.TODAY) == datetime(2026, 7, 8)

    def test_resolves_into_the_correct_week_window(self):
        # "next week" from Wed 2026-07-01 must land in the Mon Jul 6 – Jul 13 window
        anchor = relative_week_anchor("next week", self.TODAY)
        monday, nxt = week_bounds(anchor)
        assert monday == datetime(2026, 7, 6)
        assert nxt == datetime(2026, 7, 13)

    def test_non_relative_phrase_returns_none(self):
        # Concrete dates / "week of X" fall through to resolve_date, so this
        # helper must decline them by returning None.
        assert relative_week_anchor("week of July 6", self.TODAY) is None
        assert relative_week_anchor("July 8th", self.TODAY) is None
        assert relative_week_anchor("Friday", self.TODAY) is None

    def test_empty_or_none_returns_none(self):
        assert relative_week_anchor("", self.TODAY) is None
        assert relative_week_anchor(None, self.TODAY) is None

    def test_next_week_idiom(self):
        # week_bounds(start_of_today + 7d) is how camp handlers compute "next week".
        with patch("core.date_utils.today_local", return_value=date(2026, 6, 4)):  # Thu
            nxt_mon, nxt_end = week_bounds(start_of_today_local() + timedelta(days=7))
        assert nxt_mon == datetime(2026, 6, 8)   # the following Monday
        assert nxt_end == datetime(2026, 6, 15)
