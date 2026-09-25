"""Routing-congestion figures from dataset_stats.csv.

Writes ``congestion_max.png``: a histogram of each design's peak
routing-segment utilization.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import plot_utils  # pylint: disable=wrong-import-position
from dataset_csv import read_dataset_csv  # pylint: disable=wrong-import-position
from plot_utils import add_common_args, figure  # pylint: disable=wrong-import-position

DIRECTIONS = ["North", "South", "East", "West"]


def load_csv(rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Build (labels, data) from dataset rows, skipping rows without congestion data."""
    designs, data = [], []
    for r in rows:
        if r["congestion_max_pct"] is None:
            continue
        designs.append(r["design_name"])
        data.append({
            "North": r["congestion_north_pct"],
            "South": r["congestion_south_pct"],
            "East": r["congestion_east_pct"],
            "West": r["congestion_west_pct"],
            "max": r["congestion_max_pct"],
            "has_congested_region": bool(r["has_congestion_hotspot"]),
        })
    return designs, data


def print_summary(data: list[dict]) -> None:
    hotspot = sum(1 for d in data if d["has_congested_region"])
    print(f"Designs with congestion hotspots: {hotspot}/{len(data)}\n")

    header = f"{'Direction':<10} {'Min':>7} {'Median':>8} {'Mean':>7} {'Max':>7}"
    print(header)
    print("-" * len(header))
    for key in DIRECTIONS + ["max"]:
        vals = np.array([d[key] for d in data if d[key] is not None])
        label = key if key != "max" else "Overall max"
        print(
            f"{label:<10} {vals.min():>6.1f}% {np.median(vals):>7.1f}%"
            f" {vals.mean():>6.1f}% {vals.max():>6.1f}%"
        )


def plot_congestion(data: list[dict], out_dir: Path) -> None:
    """Histogram of each design's overall peak routing-segment utilization."""
    with figure(out_dir / "congestion_max") as (_fig, ax):
        max_vals = [d["max"] for d in data]
        # Congestion can exceed 100% (Vivado reports routing overuse that way), so
        # the upper bin edge tracks the actual max rather than being capped at 100.
        bins = np.linspace(min(max_vals) - 1, max(max(max_vals), 100) + 1, 25)
        ax.hist(max_vals, bins=bins, color="#4e79a7", alpha=0.8)
        ax.set_xlabel("Peak routing segment utilization (%)")
        ax.set_ylabel("Number of designs")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(parser, "Per-design dataset_stats.csv")
    args = parser.parse_args()
    plot_utils.FORMATS = plot_utils.parse_formats(args.formats)

    _designs, data = load_csv(read_dataset_csv(args.csv))
    if not data:
        print(f"No congestion data found in {args.csv}", file=sys.stderr)
        sys.exit(1)

    print(f"Read {len(data)} designs from {args.csv}\n")
    print_summary(data)
    print()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    plot_congestion(data, args.out_dir)


if __name__ == "__main__":
    main()
