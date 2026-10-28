"""Step 2: clean the raw readings.

Each rule below handles one kind of sensor problem. The README explains why
each problem is removed, flagged, or left alone. Counts for every rule go into
a data quality report, so a rule that found nothing still shows up as a zero.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

NUMERIC_COLUMNS = ["wind_speed", "wind_direction", "power_output"]
VALID_TURBINE_IDS = set(range(1, 16))

# Physical limits. Anything outside these is treated as a sensor error.
# The brief gives no turbine model, so POWER_MAX_MW is an assumed nameplate
# capacity: above the highest value seen (4.5 MW), small enough to catch spikes.
POWER_MIN_MW = 0.0
POWER_MAX_MW = 5.0
WIND_SPEED_MIN_MS = 0.0
WIND_SPEED_MAX_MS = 50.0
DIRECTION_MIN_DEG = 0.0
DIRECTION_MAX_DEG = 360.0

# A turbine should not produce power below cut-in or above cut-out wind speed.
# Typical values for utility-scale turbines.
CUT_IN_MS = 3.0
CUT_OUT_MS = 25.0

FLAG_COLUMNS = [
    "flag_missing_value",
    "flag_out_of_range",
    "flag_duplicate_conflict",
    "flag_power_wind_mismatch",
]


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return (cleaned readings, data quality report)."""
    report: dict = {"rows_loaded": len(raw)}
    df = raw.copy()

    df = _parse_keys(df, report)
    df = _parse_numbers(df, report)
    # Range check runs before de-duplication, so the duplicate step can tell a
    # good copy of a reading from a broken one.
    df = _null_out_of_range(df, report)
    df = _drop_exact_duplicates(df, report)
    df = _resolve_conflicting_duplicates(df, report)
    df = _flag_power_wind_mismatch(df, report)

    df = df.sort_values(["turbine_id", "timestamp"]).reset_index(drop=True)
    report["rows_cleaned"] = len(df)
    report["rows_with_any_flag"] = int(df[FLAG_COLUMNS].any(axis=1).sum())
    report.update(_coverage(df))
    report["wind_power_correlation"] = round(float(df["wind_speed"].corr(df["power_output"])), 4)
    return df, report


def _parse_keys(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Drop rows that cannot be placed in time or tied to a turbine.

    Without a valid timestamp and turbine_id a reading is unusable for every
    downstream step, so these rows are removed rather than flagged.
    """
    df["timestamp"] = pd.to_datetime(df["timestamp"].str.strip(), errors="coerce")
    df["turbine_id"] = pd.to_numeric(df["turbine_id"].str.strip(), errors="coerce")

    bad_timestamp = df["timestamp"].isna()
    bad_turbine = ~df["turbine_id"].isin(VALID_TURBINE_IDS)
    report["dropped_bad_timestamp"] = int(bad_timestamp.sum())
    report["dropped_unknown_turbine"] = int((bad_turbine & ~bad_timestamp).sum())

    df = df[~bad_timestamp & ~bad_turbine].copy()
    df["turbine_id"] = df["turbine_id"].astype(int)
    return df


def _parse_numbers(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Turn the three measurement columns into numbers.

    Blank cells and text such as "abc" both become NaN. The row is kept and
    flagged, because its other measurements may still be valid.
    """
    df["flag_missing_value"] = False
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")
        missing = df[col].isna()
        report[f"missing_{col}"] = int(missing.sum())
        df["flag_missing_value"] |= missing
    return df


def _drop_exact_duplicates(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Remove rows that repeat another row exactly. They carry no new information."""
    columns = ["timestamp", "turbine_id", *NUMERIC_COLUMNS]
    duplicated = df.duplicated(subset=columns, keep="first")
    report["dropped_exact_duplicates"] = int(duplicated.sum())
    return df[~duplicated].copy()


def _resolve_conflicting_duplicates(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Keep one reading per turbine per hour when two readings disagree.

    The copy with the most usable measurements wins, so a missing or impossible
    value never beats a real one. Between equally complete copies there is no
    way to know which is true, so the first in file order is kept and flagged.
    Averaging would invent a value no sensor recorded.
    """
    # A stable sort keeps file order among copies with the same valid count.
    valid_count = df[NUMERIC_COLUMNS].notna().sum(axis=1)
    df = df.loc[valid_count.sort_values(ascending=False, kind="stable").index]

    key = ["timestamp", "turbine_id"]
    has_conflict = df.duplicated(subset=key, keep=False)
    is_extra = df.duplicated(subset=key, keep="first")

    df["flag_duplicate_conflict"] = has_conflict
    report["dropped_conflicting_duplicates"] = int(is_extra.sum())
    return df[~is_extra].copy()


def _null_out_of_range(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Blank out physically impossible values and flag the row.

    The value is set to NaN instead of deleting the row, so a bad power reading
    does not also throw away a good wind reading from the same hour.
    """
    # 360 degrees is the same direction as 0, so normalise it rather than flag it.
    df.loc[df["wind_direction"] == DIRECTION_MAX_DEG, "wind_direction"] = 0.0

    limits = {
        "power_output": (POWER_MIN_MW, POWER_MAX_MW),
        "wind_speed": (WIND_SPEED_MIN_MS, WIND_SPEED_MAX_MS),
        "wind_direction": (DIRECTION_MIN_DEG, DIRECTION_MAX_DEG),
    }
    df["flag_out_of_range"] = False
    for col, (low, high) in limits.items():
        out_of_range = (df[col] < low) | (df[col] > high)
        report[f"out_of_range_{col}"] = int(out_of_range.sum())
        df.loc[out_of_range, col] = float("nan")
        df["flag_out_of_range"] |= out_of_range
    return df


def _flag_power_wind_mismatch(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    """Flag power produced when the wind is outside the turbine's operating range.

    Both values are individually possible, so nothing is removed. The pair is
    suspicious and worth an engineer looking at.
    """
    too_calm = df["wind_speed"] < CUT_IN_MS
    too_windy = df["wind_speed"] > CUT_OUT_MS
    mismatch = (df["power_output"] > 0) & (too_calm | too_windy)
    df["flag_power_wind_mismatch"] = mismatch
    report["flagged_power_wind_mismatch"] = int(mismatch.sum())
    return df


def _coverage(df: pd.DataFrame) -> dict:
    """Count hourly slots with no reading. Gaps are reported, never filled."""
    first_day = df["timestamp"].min().floor("D")
    last_hour = df["timestamp"].max().floor("D") + pd.Timedelta(hours=23)
    hours = pd.date_range(first_day, last_hour, freq="h")
    expected = len(hours) * len(VALID_TURBINE_IDS)
    present = df[["timestamp", "turbine_id"]].drop_duplicates().shape[0]
    return {
        "expected_hourly_readings": expected,
        "missing_hourly_readings": expected - present,
    }
