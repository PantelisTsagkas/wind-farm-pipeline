# Wind Farm Pipeline

**Status: DONE**

Loads one month of hourly readings from 15 turbines, cleans them, summarises power per turbine per day, and flags turbines whose daily average is more than 2 SD from the farm mean. Built with pandas.

## How to run

Needs [uv](https://docs.astral.sh/uv/), which installs Python and the dependencies.

```bash
uv sync            # install dependencies
uv run wind-farm   # reads data/raw, writes output/
uv run pytest      # run the tests
```

Optional flags: `--sd-threshold 3`, `--ddof 1` (sample SD), `--input-dir`, `--output-dir`.

Outputs in `output/` (committed): `cleaned_readings`, `daily_summary` (Parquet and CSV), `anomalies.csv`, and `data_quality_report.json` with a count for every cleaning rule.

## Data problems and how each is handled

I checked the files for missing, duplicated and impossible readings and **found none**: all 15 turbines have all 744 hours of March 2022, with no blanks, duplicates or out-of-range values. The pipeline still has a rule for each problem, each rule is tested with a planted bad row, and the quality report shows every count (all zero here).

| Problem | Action | Why |
| --- | --- | --- |
| Unparseable timestamp or unknown turbine ID | Remove row | Can't be placed in time or tied to a turbine |
| Blank or non-numeric value | Set to empty, flag | The row's other measurements may be good |
| Impossible value (power outside 0-5 MW, wind outside 0-50 m/s, direction outside 0-360°) | Set to empty, flag | One bad sensor shouldn't discard the rest of the row |
| Exact duplicate | Remove extra copy | Would double-count in averages |
| Same turbine and hour, different values | Keep the most complete copy (first if tied), flag | Averaging would invent a value no sensor recorded |
| Power with wind below cut-in (3 m/s) or above cut-out (25 m/s) | Flag only | Each value is possible, the pair is for an engineer to judge |
| Missing hours | Leave missing, count them | Filling would invent output. Each daily row has `n_readings` |

**One real finding:** power output has no relationship with wind speed (correlation -0.0025), and wind never drops below 9 m/s. Real turbines follow a power curve, so I'd raise this with operations before trusting the power figures.

## Flagged turbines

20 of 465 turbine-days were flagged (z = distance from the farm mean in SDs):

| Date | Turbine | z | | Date | Turbine | z |
| --- | --- | --- | --- | --- | --- | --- |
| 03-01 | 15 | +2.27 | | 03-15 | 9 | +2.45 |
| 03-02 | 2 | -2.57 | | 03-18 | 2 | -2.06 |
| 03-03 | 12 | -2.44 | | 03-18 | 15 | +2.25 |
| 03-04 | 8 | -2.72 | | 03-20 | 4 | -2.09 |
| 03-06 | 3 | +2.24 | | 03-22 | 11 | -2.32 |
| 03-07 | 1 | +2.08 | | 03-24 | 13 | -2.03 |
| 03-08 | 11 | -2.31 | | 03-25 | 2 | -2.02 |
| 03-11 | 4 | -2.47 | | 03-26 | 4 | -2.44 |
| 03-12 | 12 | -2.50 | | 03-28 | 3 | -2.21 |
| 03-13 | 7 | -2.18 | | 03-29 | 9 | -2.08 |

All dates are 2022. About 4.3% of turbine-days were flagged, close to the ~4.5% a 2 SD rule flags by chance, and monthly averages only range from 2.946 to 3.051 MW. So most flags look like normal variation. Turbines 2 and 4, each flagged low on three days, are the ones I'd check first.

## Assumptions

- Population SD (`ddof=0`), because the 15 turbines are the whole farm. Sample SD flags 17 instead of 20.
- "More than 2 SD" is strict: exactly 2.00 isn't flagged.
- A day is midnight to midnight in the timestamps' timezone. 27 March (UK/EU clock change) has 24 hours, so timestamps look like UTC.
- Turbine IDs are 1 to 15, rated capacity 5 MW (highest reading is 4.5), cut-in 3 m/s and cut-out 25 m/s. All are named constants in `clean.py`.
- A day needs at least 3 reporting turbines and a non-zero SD to flag anything.

## Next steps

1. Compare each turbine against a power curve, not just the rest of the farm, once the wind/power issue is resolved.
2. Alert on persistence (e.g. low on 3 of the last 7 days) rather than single days.
3. Use median and MAD instead of mean and SD, so one very bad turbine can't hide itself by inflating the SD.
4. Run it daily and incrementally with an orchestrator such as Airflow, write date-partitioned Parquet or Delta, and alert when a quality count is above zero.
