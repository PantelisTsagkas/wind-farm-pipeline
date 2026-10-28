"""The real data has none of the problems the brief warns about, so each rule
is proven here with a planted bad row."""

import pandas as pd
import pytest

from wind_farm_pipeline.clean import clean

GOOD = ["2022-03-01 00:00:00", "1", "10.0", "180", "3.0"]


def make_raw(*rows: list[str]) -> pd.DataFrame:
    """Build a raw frame the way load_raw does: every column as text."""
    columns = ["timestamp", "turbine_id", "wind_speed", "wind_direction", "power_output"]
    df = pd.DataFrame([list(r) for r in rows], columns=columns, dtype=str)
    df["source_file"] = "test.csv"
    return df


def hour(h: int, turbine: str = "1") -> list[str]:
    return [f"2022-03-01 {h:02d}:00:00", turbine, "10.0", "180", "3.0"]


def test_clean_row_passes_through_unflagged():
    cleaned, report = clean(make_raw(GOOD))
    assert len(cleaned) == 1
    assert report["rows_with_any_flag"] == 0
    assert cleaned.loc[0, "power_output"] == 3.0


def test_bad_timestamp_is_dropped():
    cleaned, report = clean(make_raw(GOOD, ["not a date", "1", "10", "180", "3"]))
    assert len(cleaned) == 1
    assert report["dropped_bad_timestamp"] == 1


@pytest.mark.parametrize("turbine_id", ["99", "0", "abc", ""])
def test_unknown_turbine_is_dropped(turbine_id):
    row = ["2022-03-01 01:00:00", turbine_id, "10", "180", "3"]
    cleaned, report = clean(make_raw(GOOD, row))
    assert len(cleaned) == 1
    assert report["dropped_unknown_turbine"] == 1


@pytest.mark.parametrize("bad_value", ["", "abc", "  "])
def test_missing_power_is_kept_as_nan_and_flagged(bad_value):
    row = ["2022-03-01 01:00:00", "1", "10", "180", bad_value]
    cleaned, report = clean(make_raw(GOOD, row))
    assert len(cleaned) == 2
    assert pd.isna(cleaned.loc[1, "power_output"])
    assert cleaned.loc[1, "flag_missing_value"]
    assert report["missing_power_output"] == 1


def test_exact_duplicate_is_dropped():
    cleaned, report = clean(make_raw(GOOD, GOOD))
    assert len(cleaned) == 1
    assert report["dropped_exact_duplicates"] == 1
    assert not cleaned.loc[0, "flag_duplicate_conflict"]


def test_conflicting_duplicate_keeps_first_and_flags_it():
    conflicting = ["2022-03-01 00:00:00", "1", "10.0", "180", "4.0"]
    cleaned, report = clean(make_raw(GOOD, conflicting))
    assert len(cleaned) == 1
    assert cleaned.loc[0, "power_output"] == 3.0
    assert cleaned.loc[0, "flag_duplicate_conflict"]
    assert report["dropped_conflicting_duplicates"] == 1


@pytest.mark.parametrize("bad_power", ["-1.0", "99", ""])
def test_conflicting_duplicate_prefers_the_valid_copy(bad_power):
    # The broken copy comes first in file order, but the good one must win.
    broken = ["2022-03-01 00:00:00", "1", "10.0", "180", bad_power]
    cleaned, report = clean(make_raw(broken, GOOD))
    assert len(cleaned) == 1
    assert cleaned.loc[0, "power_output"] == 3.0
    assert cleaned.loc[0, "flag_duplicate_conflict"]
    assert report["dropped_conflicting_duplicates"] == 1


@pytest.mark.parametrize(
    ("column_index", "value", "column"),
    [
        (4, "-1.0", "power_output"),
        (4, "99", "power_output"),
        (2, "-5", "wind_speed"),
        (2, "120", "wind_speed"),
        (3, "400", "wind_direction"),
        (3, "-10", "wind_direction"),
    ],
)
def test_impossible_value_is_nulled_and_flagged(column_index, value, column):
    row = hour(1)
    row[column_index] = value
    cleaned, report = clean(make_raw(GOOD, row))
    assert len(cleaned) == 2, "the row is kept, only the bad value is removed"
    assert pd.isna(cleaned.loc[1, column])
    assert cleaned.loc[1, "flag_out_of_range"]
    assert report[f"out_of_range_{column}"] == 1


def test_direction_360_is_normalised_to_0_not_flagged():
    row = hour(1)
    row[3] = "360"
    cleaned, _ = clean(make_raw(GOOD, row))
    assert cleaned.loc[1, "wind_direction"] == 0.0
    assert not cleaned.loc[1, "flag_out_of_range"]


@pytest.mark.parametrize("wind_speed", ["1.0", "30.0"])
def test_power_outside_operating_wind_is_flagged_not_removed(wind_speed):
    row = hour(1)
    row[2] = wind_speed
    cleaned, report = clean(make_raw(GOOD, row))
    assert cleaned.loc[1, "power_output"] == 3.0
    assert cleaned.loc[1, "flag_power_wind_mismatch"]
    assert report["flagged_power_wind_mismatch"] == 1


def test_missing_hours_are_counted_not_filled():
    # Two readings for turbine 1 on one day: 22 of its 24 hours are missing,
    # plus all 24 hours for each of the other 14 turbines.
    cleaned, report = clean(make_raw(hour(0), hour(5)))
    assert len(cleaned) == 2
    assert report["expected_hourly_readings"] == 24 * 15
    assert report["missing_hourly_readings"] == 24 * 15 - 2
