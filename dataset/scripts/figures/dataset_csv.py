"""Reader for the per-design ``dataset_stats.csv`` shipped with the suite."""

import csv
from pathlib import Path

COLUMNS = [
    "design_name", "design_id", "num_ips",
    "lut_util_pct", "ff_util_pct", "slice_util_pct", "bram_util_pct", "dsp_util_pct", "io_util_pct",
    "synth_lut_util_pct", "synth_ff_util_pct", "synth_bram_util_pct", "synth_dsp_util_pct",
    "wns_ns", "tns_ns", "failing_endpoints", "total_endpoints",
    "logic_levels", "max_logic_levels", "data_path_delay_ns", "clk_period_ns",
    "congestion_north_pct", "congestion_south_pct", "congestion_east_pct",
    "congestion_west_pct", "congestion_max_pct", "has_congestion_hotspot",
    "synth_elapsed_s", "opt_elapsed_s", "place_elapsed_s",
    "route_elapsed_s", "impl_elapsed_s", "total_elapsed_s",
]

_INT_COLUMNS = {"design_id", "num_ips", "failing_endpoints", "total_endpoints",
                "logic_levels", "max_logic_levels"}
_BOOL_COLUMNS = {"has_congestion_hotspot"}
_STR_COLUMNS = {"design_name"}


def _convert(column: str, value: str):
    """Convert one CSV cell to its typed value (empty -> None)."""
    if column in _STR_COLUMNS:
        return value
    if value == "":
        return None
    if column in _BOOL_COLUMNS:
        return value.strip().lower() in ("true", "1", "yes")
    if column in _INT_COLUMNS:
        return int(float(value))
    return float(value)


def read_dataset_csv(path: Path) -> list[dict]:
    """Read dataset_stats.csv into a list of typed row dicts (one per design)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns {missing}")
        return [{col: _convert(col, row.get(col, "")) for col in COLUMNS} for row in reader]
