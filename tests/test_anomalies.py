import pandas as pd

from wind_farm_pipeline.anomalies import flag_anomalies


def one_day(averages: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2022-03-01"] * len(averages),
            "turbine_id": range(1, len(averages) + 1),
            "avg_power_mw": averages,
        }
    )


def test_outlier_turbine_is_flagged():
    # 14 turbines at 3.0 MW and one at 1.0 MW: mean 2.867, population SD 0.499.
    # The low turbine is 3.7 SDs below the mean; the others are 0.27 SDs above.
    result = flag_anomalies(one_day([3.0] * 14 + [1.0]))
    assert result["is_anomaly"].tolist() == [False] * 14 + [True]
    assert round(result["z_score"].iloc[-1], 2) == -3.74


def test_threshold_is_configurable():
    # Same day as above: the low turbine is 3.74 SDs out, so a 4 SD threshold skips it.
    result = flag_anomalies(one_day([3.0] * 14 + [1.0]), sd_threshold=4.0)
    assert not result["is_anomaly"].any()


def test_identical_turbines_flag_nothing():
    result = flag_anomalies(one_day([3.0] * 15))
    assert not result["is_anomaly"].any()
    assert result["z_score"].isna().all()


def test_too_few_turbines_flag_nothing():
    result = flag_anomalies(one_day([3.0, 1.0]))
    assert not result["is_anomaly"].any()


def test_turbine_with_no_readings_is_left_out_of_the_farm_stats():
    result = flag_anomalies(one_day([3.0, 3.0, 3.0, float("nan")]))
    assert result["turbines_reporting"].iloc[0] == 3
    assert result["farm_mean_mw"].iloc[0] == 3.0
    assert not result["is_anomaly"].any()


def test_each_day_is_compared_only_with_itself():
    day1 = one_day([3.0] * 14 + [1.0])
    day2 = one_day([1.0] * 15).assign(date="2022-03-02")
    result = flag_anomalies(pd.concat([day1, day2], ignore_index=True))
    assert result["is_anomaly"].sum() == 1
