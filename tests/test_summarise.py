import pandas as pd

from wind_farm_pipeline.summarise import daily_summary


def test_daily_stats_ignore_missing_power():
    cleaned = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2022-03-01 00:00", "2022-03-01 01:00", "2022-03-01 02:00", "2022-03-02 00:00"]
            ),
            "turbine_id": [1, 1, 1, 1],
            "power_output": [2.0, 4.0, float("nan"), 3.0],
        }
    )
    summary = daily_summary(cleaned)

    day1 = summary.iloc[0]
    assert day1["min_power_mw"] == 2.0
    assert day1["max_power_mw"] == 4.0
    assert day1["avg_power_mw"] == 3.0
    assert day1["n_readings"] == 2
    assert not day1["complete_day"]
    assert len(summary) == 2
