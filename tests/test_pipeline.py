"""End to end on the real data shipped in data/raw."""

import json
from pathlib import Path

import pandas as pd
import pytest

from wind_farm_pipeline.load import load_raw
from wind_farm_pipeline.main import run

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


def test_load_combines_all_three_files():
    raw = load_raw(RAW_DIR)
    assert len(raw) == 3 * 31 * 24 * 5
    assert sorted(raw["source_file"].unique()) == [
        "data_group_1.csv",
        "data_group_2.csv",
        "data_group_3.csv",
    ]


def test_load_rejects_file_with_missing_column(tmp_path):
    (tmp_path / "data_group_1.csv").write_text("timestamp,turbine_id\n2022-03-01 00:00:00,1\n")
    with pytest.raises(ValueError, match="missing columns"):
        load_raw(tmp_path)


def test_full_run_writes_every_output(tmp_path):
    run(RAW_DIR, tmp_path, sd_threshold=2.0, ddof=0)

    summary = pd.read_parquet(tmp_path / "daily_summary.parquet")
    assert len(summary) == 31 * 15
    assert summary["complete_day"].all()

    report = json.loads((tmp_path / "data_quality_report.json").read_text())
    assert report["rows_loaded"] == report["rows_cleaned"] == 11160
    assert report["anomalies_flagged"] == 20

    for name in ["cleaned_readings.csv", "daily_summary.csv", "anomalies.csv"]:
        assert (tmp_path / name).exists()
