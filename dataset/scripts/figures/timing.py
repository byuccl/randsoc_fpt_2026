"""Timing figures from dataset_stats.csv.

Writes ``timing_fmax.png`` (achieved Fmax) and ``timing_logic_levels.png``
(maximum logic-level depth). Heavy tails are clipped; the number of designs
not shown is printed for each figure.
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import plot_utils  # pylint: disable=wrong-import-position
from dataset_csv import read_dataset_csv  # pylint: disable=wrong-import-position
from plot_utils import add_common_args, figure  # pylint: disable=wrong-import-position

# Cap for the max-logic-depth histogram; see plot_timing().
LOGIC_DEPTH_MAX = 50


def fmax_mhz(d: dict) -> float | None:
    """Achieved max frequency (MHz) = 1000 / (target_period - WNS)."""
    period = d.get("clk_period")
    wns = d.get("wns")
    if period is None or wns is None:
        return None
    slack_period = period - wns
    return 1000.0 / slack_period if slack_period > 0 else None


def load_csv(rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Build (labels, data) from dataset rows, skipping unconstrained designs."""
    designs, data = [], []
    for r in rows:
        if r["wns_ns"] is None:
            continue
        designs.append(r["design_name"])
        data.append({
            "wns": r["wns_ns"],
            "tns": r["tns_ns"],
            "failing_endpoints": r["failing_endpoints"],
            "total_endpoints": r["total_endpoints"],
            "logic_levels": r["logic_levels"],
            "max_logic_levels": r["max_logic_levels"],
            "data_path_delay": r["data_path_delay_ns"],
            "clk_period": r["clk_period_ns"],
        })
    return designs, data


def print_summary(data: list[dict]) -> None:
    meeting = sum(1 for d in data if d["wns"] >= 0)
    failing = len(data) - meeting
    print(f"Timing closure: {meeting}/{len(data)} designs meet timing ({failing} failing)\n")

    rows = [
        ("WNS (ns)", lambda d: d["wns"]),
        ("TNS (ns)", lambda d: d["tns"]),
        ("Fmax (MHz)", fmax_mhz),
        ("Failing endpoints", lambda d: d["failing_endpoints"]),
        ("Logic levels (worst path)", lambda d: d["logic_levels"]),
        ("Logic levels (design max)", lambda d: d.get("max_logic_levels")),
        ("Data path delay (ns)", lambda d: d["data_path_delay"]),
    ]
    header = f"{'Metric':<28} {'Min':>8} {'Median':>8} {'Mean':>8} {'Max':>8}"
    print(header)
    print("-" * len(header))
    for label, getter in rows:
        vals = np.array([v for v in (getter(d) for d in data) if v is not None], dtype=float)
        if len(vals):
            print(
                f"{label:<28} {vals.min():>8.3f} {np.median(vals):>8.3f}"
                f" {vals.mean():>8.3f} {vals.max():>8.3f}"
            )


def _clip_range(vals: np.ndarray, clip: str, k: float = 1.5) -> tuple[float, float, int]:
    """Return (lo, hi, n_outliers) trimming the requested tail(s) to a Tukey fence.

    These timing metrics are extremely heavy-tailed/bimodal -- designs that fail
    timing have catastrophic values (logic depth, slack, endpoints) while the
    rest cluster tightly -- so a percentile clip is far too loose. The Tukey fence
    (Q1 - k*IQR, Q3 + k*IQR) tracks the bulk and the figure reports how many
    designs fall outside the shown range.
    """
    q1, q3 = np.percentile(vals, [25, 75])
    iqr = q3 - q1
    lo, hi = float(vals.min()), float(vals.max())
    n_out = 0
    if clip in ("lower", "both"):
        lo = float(q1 - k * iqr)
        n_out += int((vals < lo).sum())
    if clip in ("upper", "both"):
        hi = float(q3 + k * iqr)
        n_out += int((vals > hi).sum())
    return lo, hi, n_out


def _hist(ax, raw, color, title, xlabel, clip="upper", integer=False, hi=None):
    vals = np.array([v for v in raw if v is not None], dtype=float)
    if len(vals) == 0:
        ax.set_visible(False)
        return
    if hi is not None:
        # Explicit upper cap overrides the automatic clip: show [min, hi] and
        # report how many designs fall beyond hi.
        lo, n_out = float(vals.min()), int((vals > hi).sum())
    else:
        lo, hi, n_out = _clip_range(vals, clip)
    if hi <= lo:
        hi = lo + 1
    if integer:
        edges = np.arange(int(np.floor(lo)), int(np.ceil(hi)) + 2) - 0.5
        ax.hist(vals, bins=edges, color=color, edgecolor="white", linewidth=0.5)
        ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    else:
        ax.hist(vals, bins=30, range=(lo, hi), color=color, edgecolor="white", linewidth=0.5)
    ax.set_xlim(lo, hi)
    if n_out:
        print(f"  {title}: {n_out} outliers not shown")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Number of designs")


def plot_timing(data: list[dict], out_dir: Path) -> None:
    """One file each: achieved Fmax and max logic-level depth."""
    # --- Fmax (achieved) ---
    # Clip only the high tail: the low tail is the failing/hard-design population
    # (fmax well below target), which is exactly what we want to keep visible.
    periods = np.array([d["clk_period"] for d in data if d.get("clk_period")], dtype=float)
    with figure(out_dir / "timing_fmax") as (_fig, ax):
        fmax_vals = [fmax_mhz(d) for d in data]
        _hist(ax, fmax_vals, "#af7aa1", "Achieved Fmax", "Fmax (MHz)", clip="upper")
        # Mark the median target frequency for reference.
        if len(periods):
            target_mhz = 1000.0 / float(np.median(periods))
            ax.axvline(target_mhz, color="black", linewidth=1, linestyle="--")
            ax.text(target_mhz, ax.get_ylim()[1] * 0.92,
                    f" target {target_mhz:.0f} MHz", fontsize=8, color="black")
        # Anchor the Fmax axis at 0 so the slow/failing tail reads on an absolute scale.
        ax.set_xlim(left=0)

    # --- Max logic depth across the design ---
    # The deepest combinational path regardless of slack. A handful of pathological
    # designs reach depths in the hundreds. The bulk is very tight, so a Tukey fence
    # would drop several percent of designs; cap at a round LOGIC_DEPTH_MAX instead
    # to show ~99% of the distribution while keeping the median peak readable (the
    # count beyond the cap is reported).
    max_ll = [d.get("max_logic_levels") for d in data if d.get("max_logic_levels") is not None]
    if max_ll:
        with figure(out_dir / "timing_logic_levels") as (_fig, ax):
            _hist(ax, max_ll, "#59a14f", "Max Logic Depth", "Logic levels",
                  integer=True, hi=LOGIC_DEPTH_MAX)
    else:
        print("  No max_logic_levels data; skipping logic-depth plot")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(parser, "Per-design dataset_stats.csv")
    args = parser.parse_args()
    plot_utils.FORMATS = plot_utils.parse_formats(args.formats)

    _designs, data = load_csv(read_dataset_csv(args.csv))
    if not data:
        print(f"No constrained timing data found in {args.csv}", file=sys.stderr)
        sys.exit(1)

    print(f"Read {len(data)} constrained designs from {args.csv}\n")
    print_summary(data)
    print()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    plot_timing(data, args.out_dir)


if __name__ == "__main__":
    main()
