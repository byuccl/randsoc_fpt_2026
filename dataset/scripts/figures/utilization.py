"""Resource-utilization figures from dataset_stats.csv.

Writes one histogram per resource (LUT, FF, slice, BRAM, DSP, IO) with a
log-scaled design-count axis: ``utilization_<res>_log.png``.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from matplotlib.ticker import ScalarFormatter

sys.path.insert(0, str(Path(__file__).parent))
import plot_utils  # pylint: disable=wrong-import-position
from dataset_csv import read_dataset_csv  # pylint: disable=wrong-import-position
from plot_utils import add_common_args, figure  # pylint: disable=wrong-import-position

RESOURCES = ["LUT", "FF", "SLICE", "BRAM", "DSP", "IO"]
COLORS = {
    "LUT": "#4e79a7",
    "FF": "#f28e2b",
    "SLICE": "#b07aa1",
    "BRAM": "#59a14f",
    "DSP": "#e15759",
    "IO": "#76b7b2",
}


def load_csv(rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Build (labels, data) from dataset rows, skipping rows without util data."""
    designs, data = [], []
    for r in rows:
        vals = {
            "LUT": r["lut_util_pct"], "FF": r["ff_util_pct"], "SLICE": r["slice_util_pct"],
            "BRAM": r["bram_util_pct"], "DSP": r["dsp_util_pct"], "IO": r["io_util_pct"],
        }
        if any(v is None for v in vals.values()):
            continue
        designs.append(r["design_name"])
        data.append(vals)
    return designs, data


def print_summary(data: list[dict]) -> None:
    header = f"{'Resource':<8} {'Min':>7} {'Median':>8} {'Mean':>7} {'Max':>7} {'Std':>7}"
    print(header)
    print("-" * len(header))
    for key in RESOURCES:
        vals = np.array([d[key] for d in data])
        print(
            f"{key:<8} {vals.min():>6.1f}% {np.median(vals):>7.1f}% "
            f"{vals.mean():>6.1f}% {vals.max():>6.1f}% {vals.std():>6.1f}%"
        )


def plot_histograms(data: list[dict], out_dir: Path) -> None:
    """One histogram, in its own file, per resource type.

    The y-axis (design count) is log-scaled so sparse, heavy tails stay visible.
    """
    for key in RESOURCES:
        with figure(out_dir / f"utilization_{key.lower()}_log") as (_fig, ax):
            vals = [d[key] for d in data]
            ax.hist(vals, bins=30, color=COLORS[key], edgecolor="white", linewidth=0.5)
            ax.set_yscale("log")
            # Label the decade ticks as plain integers (1, 10, 100, ...) rather
            # than matplotlib's default 10^x scientific notation.
            ax.yaxis.set_major_formatter(ScalarFormatter())
            ax.set_xlabel("Utilization (%)")
            ax.set_ylabel("Number of designs")
            ax.set_xlim(0, 100)



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(parser, "Per-design dataset_stats.csv")
    args = parser.parse_args()
    plot_utils.FORMATS = plot_utils.parse_formats(args.formats)

    _designs, data = load_csv(read_dataset_csv(args.csv))
    if not data:
        print(f"No utilization data found in {args.csv}", file=sys.stderr)
        sys.exit(1)

    print(f"Read {len(data)} designs from {args.csv}\n")
    print_summary(data)
    print()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    plot_histograms(data, args.out_dir)


if __name__ == "__main__":
    main()
