"""Step 1: load every raw CSV into one DataFrame."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = ["timestamp", "turbine_id", "wind_speed", "wind_direction", "power_output"]


def load_raw(input_dir: Path, pattern: str = "data_group_*.csv") -> pd.DataFrame:
    """Read all matching CSVs and stack them into one DataFrame.

    Every column is read as text on purpose. If a sensor writes "abc" or leaves a
    cell blank, the read still succeeds and the cleaning step decides what to do
    with it, instead of pandas guessing or crashing here.
    """
    files = sorted(input_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matching {pattern!r} in {input_dir}")

    frames = []
    for path in files:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)

        missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
        if missing:
            raise ValueError(f"{path.name} is missing columns: {missing}")

        df = df[EXPECTED_COLUMNS].copy()
        # Keep lineage so any bad row can be traced back to its file.
        df["source_file"] = path.name
        frames.append(df)
        logger.info("Loaded %s: %d rows", path.name, len(df))

    combined = pd.concat(frames, ignore_index=True)
    logger.info("Loaded %d rows from %d files", len(combined), len(files))
    return combined
