# Wind Farm Pipeline

**Status: ACTIVE**

A small Python pipeline that turns one month of raw hourly readings from 15 wind turbines into data the operations team can trust. It loads the three sensor files, cleans them, summarises each turbine per day, flags turbines whose daily average is unusual compared with the rest of the farm, and saves the results as Parquet and CSV.

## How to run

You need [uv](https://docs.astral.sh/uv/). It installs the right Python and the dependencies for you.

```bash
uv sync              # install pandas, pyarrow, pytest, ruff
uv run wind-farm     # run the pipeline: reads data/raw, writes output/
uv run pytest        # run the tests
```

Options:

```bash
uv run wind-farm --sd-threshold 3     # flag at 3 standard deviations instead of 2
uv run wind-farm --ddof 1             # use the sample standard deviation
uv run wind-farm --input-dir path/to/csvs --output-dir path/to/results
```

The run logs every data quality count and every flagged turbine to the console.

## Outputs

All outputs are in `output/` and committed, so you can read the results without running anything.

| File | Contents |
| --- | --- |
| `cleaned_readings.parquet` / `.csv` | Every reading after cleaning, with the source file and four `flag_*` columns |
| `daily_summary.parquet` / `.csv` | One row per turbine per day: min, max and average power, how many hours it is based on, the farm mean and SD for that day, the z-score, and `is_anomaly` |
| `anomalies.csv` | Only the flagged rows from the daily summary |
| `data_quality_report.json` | A count for every cleaning rule |

## How it works

There's one module per step in the brief, in `src/wind_farm_pipeline/`:

| Step | Module | What it does |
| --- | --- | --- |
| 1. Load | `load.py` | Reads every `data_group_*.csv` as text, checks the columns, adds `source_file`, and stacks them |
| 2. Clean | `clean.py` | Applies the rules in the next section and builds the data quality report |
| 3. Summarise | `summarise.py` | Groups by date and turbine for min, max, mean and reading count |
| 4. Flag | `anomalies.py` | For each day, compares each turbine's average with the mean and SD of all 15 averages |
| 5. Save | `main.py` | Runs the steps in order and writes the outputs |

The raw files are read as text on purpose. A blank cell or a value like `"abc"` then reaches the cleaning step, where a rule decides what happens to it, instead of crashing the load or being silently converted by pandas.

## Data problems and how each one is handled

The brief says the data contains missing, duplicated and physically impossible readings. **I checked for every one of those and found none in these files.** All 15 turbines have a reading for all 744 hours of March 2022. There are no blank or non-numeric values, no duplicate rows, and every value is within physical limits.

I didn't assume the files would stay that clean. The pipeline has a rule for each problem the brief describes, each rule has a test with a planted bad row (`tests/test_clean.py`), and `data_quality_report.json` records a count for every rule. On this data every count is zero. If tomorrow's files arrive dirty, the same code handles them.

| Problem | Decision | Why |
| --- | --- | --- |
| Timestamp can't be parsed | **Remove** the row | The reading can't be placed in time, so it can't be used in any daily figure |
| Turbine ID not in 1 to 15 | **Remove** the row | The reading can't be attributed to a turbine |
| Blank or non-numeric measurement | **Keep** the row, set the value to empty, flag `flag_missing_value` | The other measurements in the row may still be good. Aggregations skip empty values |
| Exact duplicate row | **Remove** the extra copy | It adds no information and would double-count in averages |
| Same turbine and hour with different values | **Keep the first**, remove the rest, flag `flag_duplicate_conflict` | There's no way to tell which reading is true. Averaging them would create a value no sensor recorded. The flag lets ops find these hours |
| Impossible value: power below 0 or above 5 MW, wind speed below 0 or above 50 m/s, direction outside 0 to 360° | **Keep** the row, set that value to empty, flag `flag_out_of_range` | One broken sensor shouldn't throw away the other readings from the same hour |
| Direction of exactly 360° | **Fix**: set it to 0° | 360° and 0° are the same direction |
| Power produced with wind below cut-in (3 m/s) or above cut-out (25 m/s) | **Leave** the values, flag `flag_power_wind_mismatch` | Each value is possible on its own, but the pair is suspicious. That's for an engineer to judge, not for the pipeline to delete |
| Missing hours | **Leave** them missing. They're counted in the report, and each daily row has `n_readings` and `complete_day` | Filling gaps would invent power output. A daily average based on 20 hours is labelled as such |

### One real finding: power doesn't depend on wind speed

Power output has no relationship with wind speed in this data. The correlation is -0.0025. A turbine produces anywhere from 1.5 to 4.5 MW whether the wind is at 9 m/s or at 15 m/s. Wind speed never drops below 9 m/s all month.

Real turbines follow a power curve: below rated wind speed, more wind means more power. I've left these values alone, because nothing in a single reading is impossible. But I'd raise it with the operations team before anyone trusts the power figures. It could point to a mislabelled column, an anemometer reporting the wrong unit or location, or data that has been resampled or anonymised before reaching us. The correlation is recorded in the data quality report so it's checked on every run.

## Flagged turbines

The method follows the brief. For each day, take the 15 daily averages, compute their mean and standard deviation, and flag any turbine whose average is more than 2 SD from the mean.

**20 turbine-days were flagged** (from `output/anomalies.csv`):

| Date | Turbine | Daily avg (MW) | Farm mean (MW) | z-score |
| --- | --- | --- | --- | --- |
| 2022-03-01 | 15 | 3.371 | 2.998 | +2.27 |
| 2022-03-02 | 2 | 2.467 | 3.024 | -2.57 |
| 2022-03-03 | 12 | 2.671 | 3.027 | -2.44 |
| 2022-03-04 | 8 | 2.529 | 2.965 | -2.72 |
| 2022-03-06 | 3 | 3.300 | 3.007 | +2.24 |
| 2022-03-07 | 1 | 3.283 | 2.996 | +2.08 |
| 2022-03-08 | 11 | 2.579 | 3.073 | -2.31 |
| 2022-03-11 | 4 | 2.479 | 2.974 | -2.47 |
| 2022-03-12 | 12 | 2.637 | 2.986 | -2.50 |
| 2022-03-13 | 7 | 2.725 | 2.984 | -2.18 |
| 2022-03-15 | 9 | 3.471 | 3.077 | +2.45 |
| 2022-03-18 | 2 | 2.738 | 3.005 | -2.06 |
| 2022-03-18 | 15 | 3.296 | 3.005 | +2.25 |
| 2022-03-20 | 4 | 2.504 | 2.977 | -2.09 |
| 2022-03-22 | 11 | 2.554 | 2.955 | -2.32 |
| 2022-03-24 | 13 | 2.663 | 3.040 | -2.03 |
| 2022-03-25 | 2 | 2.725 | 3.065 | -2.02 |
| 2022-03-26 | 4 | 2.471 | 2.978 | -2.44 |
| 2022-03-28 | 3 | 2.688 | 2.975 | -2.21 |
| 2022-03-29 | 9 | 2.575 | 2.971 | -2.08 |

Turbines 2 and 4 were flagged on three separate days each. Turbines 3, 9, 11, 12 and 15 were flagged twice. No turbine was flagged on two days in a row.

**How I'd read this:** 20 flags out of 465 turbine-days is about 4.3%. That's close to the roughly 4.5% a 2 SD rule flags in normally distributed data even when nothing is wrong. Over the whole month every turbine averages between 2.946 MW (turbine 4) and 3.051 MW (turbine 12). So I don't see a turbine that's consistently underperforming. Most of these flags are likely normal day-to-day variation. Turbines 2 and 4, each flagged low on three days, are the ones I'd ask the operations team to look at first.

## Assumptions

- **Population standard deviation (`ddof=0`).** The 15 turbines are the whole farm, not a sample of it. With the sample SD (`--ddof 1`) the SD is slightly larger and 17 turbine-days are flagged instead of 20.
- **"More than 2 SD" is strict:** exactly 2.00 SD isn't flagged.
- **A day is a calendar day, midnight to midnight, in the timestamps' own timezone.** 27 March 2022, when UK and EU clocks went forward, has all 24 hours for every turbine. So the timestamps appear to be in a single timezone such as UTC, and no adjustment was made.
- **Valid turbine IDs are 1 to 15,** as described in the brief.
- **Rated capacity of 5 MW.** The brief doesn't name the turbine model. The highest reading is 4.5 MW, so 5 MW is the assumed upper limit. Change `POWER_MAX_MW` in `clean.py` if the real nameplate figure is known.
- **Cut-in 3 m/s and cut-out 25 m/s.** These are typical values for utility-scale turbines, used only to flag suspicious readings.
- **A day's anomaly check needs at least 3 turbines with data and an SD above zero.** Otherwise nothing is flagged that day.
- **Turbines with partial days are still compared.** Their row has `complete_day = False`, so a reader can discount them.

## What I'd do next with more time

1. **Check against a power curve, not just the rest of the farm.** Compare each turbine's output with what its wind speed should produce. That catches a turbine that underperforms on a windy day even when the whole farm is average. Comparing turbines with each other on the same day can't do that. It depends on resolving the wind/power finding above first.
2. **Flag persistence, not single days.** Alert when a turbine is low on, say, 3 of the last 7 days. A single 2 SD day happens by chance, as the results above show.
3. **Use robust statistics.** One very bad turbine pulls up both the mean and the SD, which makes it look less extreme. With 15 turbines and population SD, the z-score can never exceed √14 ≈ 3.74, however bad a turbine gets. A median and median absolute deviation (MAD) version wouldn't have that ceiling.
4. **Productionise the run.** Load each new day incrementally, write partitioned Parquet or Delta by date, schedule it with an orchestrator such as Airflow, and alert when a data quality count rises above zero.
5. **Formal schema validation** with a library such as pandera, so the contract with the sensor team is written down as code.

## Project layout

```
data/raw/                    the three source CSVs, unchanged
output/                      pipeline results (committed)
src/wind_farm_pipeline/
    load.py                  step 1
    clean.py                 step 2, with all thresholds as named constants
    summarise.py             step 3
    anomalies.py             step 4
    main.py                  command-line entry point, step 5
tests/                       pytest: clean, summarise, anomalies, plus load and end-to-end in test_pipeline.py
```
