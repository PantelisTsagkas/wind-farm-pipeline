"""Step 4: flag turbines whose daily average is far from the rest of the farm."""

import pandas as pd

SD_THRESHOLD = 2.0
# ddof=0 is the population standard deviation. The 15 turbines are the whole
# farm, not a sample of a bigger one. Change to 1 for the sample version.
DDOF = 0
# With fewer turbines than this, a standard deviation means very little.
MIN_TURBINES = 3


def flag_anomalies(
    summary: pd.DataFrame,
    sd_threshold: float = SD_THRESHOLD,
    ddof: int = DDOF,
) -> pd.DataFrame:
    """Add farm mean, farm SD, z-score and an is_anomaly flag to the daily summary.

    For each day: take every turbine's average power, compute the mean and SD of
    those averages, and flag any turbine more than sd_threshold SDs away.
    """
    df = summary.copy()
    by_day = df.groupby("date")["avg_power_mw"]

    df["farm_mean_mw"] = by_day.transform("mean")
    df["farm_sd_mw"] = by_day.transform("std", ddof=ddof)
    df["turbines_reporting"] = by_day.transform("count")

    distance = df["avg_power_mw"] - df["farm_mean_mw"]
    usable = (df["turbines_reporting"] >= MIN_TURBINES) & (df["farm_sd_mw"] > 0)

    # z-score is only defined when the SD is above zero.
    df["z_score"] = (distance / df["farm_sd_mw"]).where(usable)
    df["is_anomaly"] = usable & (distance.abs() > sd_threshold * df["farm_sd_mw"])
    return df
