"""Step 3: daily min, max and average power per turbine."""

import pandas as pd

HOURS_PER_DAY = 24


def daily_summary(cleaned: pd.DataFrame) -> pd.DataFrame:
    """One row per turbine per day.

    NaN power values (missing or impossible readings) are skipped by pandas
    aggregations, so the stats only use real readings. n_readings shows how
    many hours each average is based on.
    """
    df = cleaned.assign(date=cleaned["timestamp"].dt.date)

    summary = (
        df.groupby(["date", "turbine_id"])["power_output"]
        .agg(
            min_power_mw="min",
            max_power_mw="max",
            avg_power_mw="mean",
            n_readings="count",
        )
        .reset_index()
    )
    summary["complete_day"] = summary["n_readings"] == HOURS_PER_DAY
    return summary
