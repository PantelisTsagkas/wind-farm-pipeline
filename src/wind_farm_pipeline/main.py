"""Run the whole pipeline: load, clean, summarise, flag, save."""

import argparse
import json
import logging
from pathlib import Path

from wind_farm_pipeline.anomalies import DDOF, SD_THRESHOLD, flag_anomalies
from wind_farm_pipeline.clean import clean
from wind_farm_pipeline.load import load_raw
from wind_farm_pipeline.summarise import daily_summary

logger = logging.getLogger("wind_farm_pipeline")


def run(input_dir: Path, output_dir: Path, sd_threshold: float, ddof: int) -> None:
    raw = load_raw(input_dir)
    cleaned, report = clean(raw)
    summary = flag_anomalies(daily_summary(cleaned), sd_threshold=sd_threshold, ddof=ddof)
    anomalies = summary[summary["is_anomaly"]]
    report["anomalies_flagged"] = len(anomalies)

    output_dir.mkdir(parents=True, exist_ok=True)
    # Parquet keeps the column types. CSV is there so anyone can open it in a spreadsheet.
    cleaned.to_parquet(output_dir / "cleaned_readings.parquet", index=False)
    cleaned.to_csv(output_dir / "cleaned_readings.csv", index=False)
    summary.to_parquet(output_dir / "daily_summary.parquet", index=False)
    summary.to_csv(output_dir / "daily_summary.csv", index=False)
    anomalies.to_csv(output_dir / "anomalies.csv", index=False)
    (output_dir / "data_quality_report.json").write_text(json.dumps(report, indent=2) + "\n")

    for key, value in report.items():
        logger.info("%s: %s", key, value)
    for row in anomalies.itertuples():
        logger.info(
            "Anomaly: %s turbine %d avg %.3f MW (z = %+.2f)",
            row.date,
            row.turbine_id,
            row.avg_power_mw,
            row.z_score,
        )
    logger.info("Wrote outputs to %s", output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--sd-threshold", type=float, default=SD_THRESHOLD)
    parser.add_argument("--ddof", type=int, default=DDOF, choices=[0, 1])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run(args.input_dir, args.output_dir, args.sd_threshold, args.ddof)


if __name__ == "__main__":
    main()
