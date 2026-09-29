#!/usr/bin/env python3
"""Extract dataset_stats.csv / dataset_ip_sizes.csv rows from built designs.

This is the report-to-CSV step behind the two CSVs shipped in ``dataset/``.
Given one or more ``build/design_NNNN`` directories produced by ``make
DESIGN=NNNN``, it parses the Vivado reports and logs written there and emits:

  * one ``dataset_stats.csv`` row per design (utilization, timing, congestion,
    runtime), and
  * one ``dataset_ip_sizes.csv`` row per top-level IP instance (from the
    hierarchical utilization report).

The parsers are those used to produce the shipped CSVs, and the ``Makefile``
here produces the same per-design layout the original build machines did:
``build/design_NNNN/vivado_synth/`` and ``build/design_NNNN/vivado_impl/``, each
with its own ``vivado.log``. (A flat directory with ``synth.log`` / ``impl.log``
is also accepted.) Run over the original build output, the script reproduces
the shipped CSVs exactly. Only the Python standard library is required.

Inputs read from each build directory:

  vivado_impl/utilization.txt        report_utilization       -> *_util_pct
  vivado_impl/utilization_hier.txt   report_utilization -hierarchical
                                                              -> dataset_ip_sizes rows
  vivado_impl/timing_summary.txt     report_timing_summary    -> wns/tns/endpoints/
                                                           logic_levels/delay/period
  vivado_impl/logic_levels.txt       report_design_analysis -logic_level_distribution
                                                              -> max_logic_levels
  vivado_impl/vivado.log             log of scripts/impl.tcl  -> congestion_* (the
                          placer's "Max Cong" estimates) and opt/place/route runtimes
  vivado_synth/vivado.log            log of design.tcl        -> synth runtime
  vivado_synth/synth_utilization.txt (optional) post-synthesis report_utilization
                                                              -> synth_*_util_pct

``num_ips`` (the number of randomly selected IP cores, excluding the
automatically inserted infrastructure and glue IP) is counted from the design's
``design.tcl``.

Usage (normally via the Makefile):

  # one design: add/replace its rows in the suite-level CSVs under build/
  make stats DESIGN=0042
  python3 scripts/collect_stats.py build/design_0042 --update \
      --stats-csv build/dataset_stats.csv --ip-sizes-csv build/dataset_ip_sizes.csv

  # every built design: rewrite the suite-level CSVs from scratch
  make stats-all
  python3 scripts/collect_stats.py build/design_* \
      --stats-csv build/dataset_stats.csv --ip-sizes-csv build/dataset_ip_sizes.csv

With ``--update``, rows for the given designs replace any existing rows for the
same design in the output CSVs and all other rows are kept; without it the
output CSVs are overwritten. Rows are always written in design_id order, so the
files have the same layout as the shipped ``dataset_stats.csv`` and
``dataset_ip_sizes.csv``.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Output schema (identical to the shipped CSVs)
# --------------------------------------------------------------------------- #

STATS_COLUMNS = [
    "design_name",
    "design_id",
    "num_ips",
    "lut_util_pct",
    "ff_util_pct",
    "slice_util_pct",
    "bram_util_pct",
    "dsp_util_pct",
    "io_util_pct",
    "synth_lut_util_pct",
    "synth_ff_util_pct",
    "synth_bram_util_pct",
    "synth_dsp_util_pct",
    "wns_ns",
    "tns_ns",
    "failing_endpoints",
    "total_endpoints",
    "logic_levels",
    "max_logic_levels",
    "data_path_delay_ns",
    "clk_period_ns",
    "congestion_north_pct",
    "congestion_south_pct",
    "congestion_east_pct",
    "congestion_west_pct",
    "congestion_max_pct",
    "has_congestion_hotspot",
    "synth_elapsed_s",
    "opt_elapsed_s",
    "place_elapsed_s",
    "route_elapsed_s",
    "impl_elapsed_s",
    "total_elapsed_s",
]

# Columns in `report_utilization -hierarchical`, in order after the Instance and
# Module columns.
HIER_RESOURCE_COLUMNS = [
    "total_luts",
    "logic_luts",
    "lutrams",
    "srls",
    "ffs",
    "ramb36",
    "ramb18",
    "dsp",
]

IP_SIZE_COLUMNS = ["design_name", "design_id", "ip_index", "ip_type"] + HIER_RESOURCE_COLUMNS

# --------------------------------------------------------------------------- #
# num_ips from design.tcl
# --------------------------------------------------------------------------- #

# Every IP the generator places is wrapped in a `ip_<index>_<type>` hierarchy.
# The randomly selected cores come first; these are the automatically inserted
# SoC infrastructure and connectivity glue that follow them.
INFRA_IP_TYPES = {"intc", "reset", "clk_wiz", "axi", "axi_legacy", "jtag_axi"}
GLUE_IP_TYPES = {
    "slice_and_concat",
    "axis_dwidth_converter",
    "axis_broadcaster",
    "axis_combiner",
    "reduce",
}

_HIER_CELL_RE = re.compile(r"^create_bd_cell -type hier ip_(\d+)_([A-Za-z0-9_]+)\s*$", re.M)


def count_ips(design_tcl: Path) -> int | None:
    """Number of randomly selected IP cores in a design.tcl (None if unreadable)."""
    try:
        text = design_tcl.read_text()
    except OSError:
        return None
    return sum(
        1
        for _idx, ip_type in _HIER_CELL_RE.findall(text)
        if ip_type not in INFRA_IP_TYPES and ip_type not in GLUE_IP_TYPES
    )


# --------------------------------------------------------------------------- #
# Utilization
# --------------------------------------------------------------------------- #

# short name -> (table row label, section header used as a zero-usage fallback)
RESOURCES = {
    "LUT": ("Slice LUTs", None),
    "FF": ("Slice Registers", None),
    "SLICE": ("Slice", None),
    "BRAM": ("Block RAM Tile", "3. Memory"),
    "DSP": ("DSPs", "4. DSP"),
    "IO": ("Bonded IOB", None),
}

# Post-synthesis reports have no placement, so no SLICE / IO occupancy rows.
SYNTH_RESOURCES = ("LUT", "FF", "BRAM", "DSP")


def parse_utilization(path: Path, keys=None) -> dict[str, float] | None:
    """Utilization % per resource from a report_utilization file, or None on failure."""
    text = path.read_text()
    result = {}
    for key in keys if keys is not None else RESOURCES:
        label, zero_section = RESOURCES[key]
        pattern = (
            rf"\|\s*{re.escape(label)}\s*\|\s*[\d,]+\s*\|[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)\s*\|"
        )
        m = re.search(pattern, text)
        if m:
            result[key] = float(m.group(1))
        elif zero_section and zero_section in text:
            # Section exists but its table is empty: the resource count is zero.
            result[key] = 0.0
        else:
            return None
    return result


_HIER_IP_RE = re.compile(r"^ip_(\d+)_([a-zA-Z0-9_]+)$")


def parse_utilization_hier(path: Path) -> list[dict]:
    """One dict per top-level ``ip_<n>_<type>`` wrapper in a hierarchical report.

    Only the wrapper rows are kept (not their sub-instances), so each row is that
    IP instance's post-implementation size.
    """
    ips = []
    for line in path.read_text().splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 + len(HIER_RESOURCE_COLUMNS):
            continue
        m = _HIER_IP_RE.match(cells[0])
        if not m:
            continue
        try:
            vals = [int(c) for c in cells[2 : 2 + len(HIER_RESOURCE_COLUMNS)]]
        except ValueError:
            continue
        ip = {"ip_index": int(m.group(1)), "ip_type": m.group(2)}
        ip.update(dict(zip(HIER_RESOURCE_COLUMNS, vals)))
        ips.append(ip)
    return ips


# --------------------------------------------------------------------------- #
# Timing
# --------------------------------------------------------------------------- #


def parse_timing(path: Path) -> dict | None:
    """Timing metrics from timing_summary.txt, or None if the design is unconstrained."""
    text = path.read_text()

    if "There are no user specified timing constraints" in text:
        return None

    # Intra Clock Table row:  clk_out1_<name>  WNS  TNS  TNS_fail  TNS_total ...
    clock_row = re.search(
        r"^\s+clk_out1_\S+\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)",
        text,
        re.MULTILINE,
    )
    if not clock_row:
        return None

    # Clock Summary row:  clk_out1_<name>   {0.000 4.167}   8.333   120.005
    period_row = re.search(
        r"^\s+clk_out1_\S+\s+\{[^}]*\}\s+([\d.]+)\s+([\d.]+)",
        text,
        re.MULTILINE,
    )
    clk_period = float(period_row.group(1)) if period_row else None

    # Logic levels and data path delay of the worst constrained max-delay path
    # (the first path whose slack is not "inf").
    logic_levels = None
    data_path_delay = None
    for m in re.finditer(r"Slack\s*(?:\(VIOLATED\)|\(MET\))\s*:\s*([-\d.]+)ns", text):
        tail = text[m.start() :]
        ll_m = re.search(r"Logic Levels:\s+(\d+)", tail)
        dp_m = re.search(r"Data Path Delay:\s+([\d.]+)ns", tail)
        if ll_m and dp_m:
            logic_levels = int(ll_m.group(1))
            data_path_delay = float(dp_m.group(1))
        break

    return {
        "wns": float(clock_row.group(1)),
        "tns": float(clock_row.group(2)),
        "failing_endpoints": int(clock_row.group(3)),
        "total_endpoints": int(clock_row.group(4)),
        "logic_levels": logic_levels,
        "data_path_delay": data_path_delay,
        "clk_period": clk_period,
    }


def parse_logic_levels(path: Path) -> int | None:
    """Max combinational depth from a logic-level distribution report.

    The highest logic-level column with a non-zero path count over all endpoint
    clocks, or None if the report has no distribution table.
    """
    levels = None
    max_level = None
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells:
            continue
        if cells[0] == "End Point Clock":
            levels = [int(c) for c in cells[2:] if c.isdigit()]
            continue
        if not levels:
            continue
        try:
            counts = [int(c) for c in cells[2 : 2 + len(levels)]]
        except ValueError:
            continue
        for lvl, cnt in zip(levels, counts):
            if cnt > 0 and (max_level is None or lvl > max_level):
                max_level = lvl
    return max_level


# --------------------------------------------------------------------------- #
# Congestion (from the placer's messages in the implementation log)
# --------------------------------------------------------------------------- #

DIRECTIONS = ["North", "South", "East", "West"]


def parse_congestion(log_path: Path) -> dict | None:
    """Peak routing-segment utilization (%) per direction from the impl log.

    Lines look like:
      North Dir 2x2 Area, Max Cong = 87.6126%, Congestion bounded by tiles ...
      East Dir 1x1 Area, Max Cong = 83.8235%, No Congested Regions.
    Vivado only prints these for designs large enough for the placer to run its
    congestion estimate, so None (empty CSV cells) is common for small designs.
    """
    text = log_path.read_text(errors="replace")
    result = {}
    for direction in DIRECTIONS:
        m = re.search(rf"{direction} Dir \S+ Area, Max Cong = ([\d.]+)%", text)
        if m:
            result[direction] = float(m.group(1))
    if len(result) != len(DIRECTIONS):
        return None
    result["max"] = max(result[d] for d in DIRECTIONS)
    result["has_congested_region"] = "Congestion bounded by tiles" in text
    return result


# --------------------------------------------------------------------------- #
# Runtime (from the Vivado logs)
# --------------------------------------------------------------------------- #


def _parse_elapsed(hms: str) -> float:
    """HH:MM:SS(.ss) -> seconds."""
    parts = hms.split(":")
    return sum(float(p) * 60 ** (len(parts) - 1 - i) for i, p in enumerate(parts))


def _phase_elapsed(text: str, phase: str) -> float | None:
    """Elapsed wall-clock seconds of a Vivado command (e.g. 'place_design').

    Normally the summary is a prefixed line ('place_design: Time (s): ... elapsed
    = ...'). For some fast phases Vivado emits a bare 'Time (s): ... elapsed = ...'
    line instead, so fall back to the last such line before '<phase> completed
    successfully'.
    """
    m = re.search(rf"^{phase}: Time.*?elapsed = ([\d:]+)", text, re.MULTILINE)
    if m:
        return _parse_elapsed(m.group(1))
    end = text.find(f"{phase} completed successfully")
    if end == -1:
        return None
    times = re.findall(r"Time \(s\):[^\n]*elapsed = ([\d:]+)", text[:end])
    return _parse_elapsed(times[-1]) if times else None


def parse_runtime(synth_logs: list[Path], impl_log: Path | None) -> dict | None:
    """Elapsed seconds per Vivado phase. synth_logs are tried in order."""
    result = {}
    for log in synth_logs:
        if log.exists():
            elapsed = _phase_elapsed(log.read_text(errors="replace"), "synth_design")
            if elapsed is not None:
                result["synth"] = elapsed
                break
    if impl_log is not None and impl_log.exists():
        text = impl_log.read_text(errors="replace")
        for phase in ["opt_design", "place_design", "route_design"]:
            elapsed = _phase_elapsed(text, phase)
            if elapsed is not None:
                result[phase.replace("_design", "")] = elapsed
    if not result:
        return None
    result["impl"] = sum(result.get(p, 0) for p in ["opt", "place", "route"])
    result["total"] = result.get("synth", 0) + result["impl"]
    return result


# --------------------------------------------------------------------------- #
# Per-design collection
# --------------------------------------------------------------------------- #


def _first_existing(*paths: Path) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


class Layout:
    """Where a design's synthesis and implementation outputs live.

    Two-directory (this artifact's Makefile and the original bfasst build):
    design_<n>/vivado_synth/ and design_<n>/vivado_impl/, each with its own
    vivado.log. The original build also kept design.tcl in design_<n>/ itself;
    the artifact keeps it under designs/. Flat: everything in one directory,
    logs named synth.log / impl.log.
    """

    def __init__(self, build_dir: Path):
        self.build_dir = build_dir
        self.original = (build_dir / "vivado_impl").is_dir()
        if self.original:
            self.synth_dir = build_dir / "vivado_synth"
            self.impl_dir = build_dir / "vivado_impl"
            self.synth_logs = [
                self.synth_dir / "vivado.log",
                # design.tcl synthesizes through launch_runs; if the parent log
                # lacks synth_design's summary, the run's own log has it.
                self.synth_dir / "test" / "test.runs" / "synth_1" / "runme.log",
            ]
            self.impl_log = _first_existing(self.impl_dir / "vivado.log")
            tcl = build_dir / "design.tcl"
            self.default_design_tcl = tcl if tcl.exists() else None
        else:
            self.synth_dir = build_dir
            self.impl_dir = build_dir
            self.synth_logs = [
                build_dir / "synth.log",
                # design.tcl synthesizes through launch_runs; if the parent log
                # lacks synth_design's summary, the run's own log has it.
                build_dir / "test" / "test.runs" / "synth_1" / "runme.log",
            ]
            # vivado.log is accepted for builds made with the default log name.
            self.impl_log = _first_existing(build_dir / "impl.log", build_dir / "vivado.log")
            self.default_design_tcl = None

    def is_complete(self) -> bool:
        """A build counts as complete once implementation has written its checkpoint."""
        return (self.impl_dir / "impl.dcp").exists() or (self.impl_dir / "design.bit").exists()


def collect_design(build_dir: Path, design_tcl: Path | None) -> tuple[dict, list[dict]]:
    """Parse one build directory into (stats row, [ip size rows])."""
    name = build_dir.name
    try:
        design_id = int(name.split("_", 1)[1])
    except (IndexError, ValueError):
        sys.exit(f"{build_dir}: expected a directory named design_<id>")
    layout = Layout(build_dir)

    row = {col: None for col in STATS_COLUMNS}
    row["design_name"] = name
    row["design_id"] = design_id
    row["num_ips"] = count_ips(design_tcl) if design_tcl is not None else None

    # Post-implementation utilization.
    util_path = layout.impl_dir / "utilization.txt"
    util = parse_utilization(util_path) if util_path.exists() else None
    if util:
        for key, col in (
            ("LUT", "lut_util_pct"),
            ("FF", "ff_util_pct"),
            ("SLICE", "slice_util_pct"),
            ("BRAM", "bram_util_pct"),
            ("DSP", "dsp_util_pct"),
            ("IO", "io_util_pct"),
        ):
            row[col] = util.get(key)

    # Post-synthesis utilization (optional report; the Makefile flow does not
    # write it, and the shipped CSV leaves these columns empty).
    synth_util_path = layout.synth_dir / "synth_utilization.txt"
    synth_util = (
        parse_utilization(synth_util_path, keys=SYNTH_RESOURCES)
        if synth_util_path.exists()
        else None
    )
    if synth_util:
        for key, col in (
            ("LUT", "synth_lut_util_pct"),
            ("FF", "synth_ff_util_pct"),
            ("BRAM", "synth_bram_util_pct"),
            ("DSP", "synth_dsp_util_pct"),
        ):
            row[col] = synth_util.get(key)

    # Timing.
    timing_path = layout.impl_dir / "timing_summary.txt"
    timing = parse_timing(timing_path) if timing_path.exists() else None
    if timing:
        row["wns_ns"] = timing["wns"]
        row["tns_ns"] = timing["tns"]
        row["failing_endpoints"] = timing["failing_endpoints"]
        row["total_endpoints"] = timing["total_endpoints"]
        row["logic_levels"] = timing["logic_levels"]
        row["data_path_delay_ns"] = timing["data_path_delay"]
        row["clk_period_ns"] = timing["clk_period"]

    ll_path = layout.impl_dir / "logic_levels.txt"
    row["max_logic_levels"] = parse_logic_levels(ll_path) if ll_path.exists() else None

    # Congestion + runtime come from the Vivado logs.
    impl_log = layout.impl_log
    congestion = parse_congestion(impl_log) if impl_log else None
    if congestion:
        row["congestion_north_pct"] = congestion["North"]
        row["congestion_south_pct"] = congestion["South"]
        row["congestion_east_pct"] = congestion["East"]
        row["congestion_west_pct"] = congestion["West"]
        row["congestion_max_pct"] = congestion["max"]
        row["has_congestion_hotspot"] = congestion["has_congested_region"]

    runtime = parse_runtime(layout.synth_logs, impl_log)
    if runtime:
        row["synth_elapsed_s"] = runtime.get("synth")
        row["opt_elapsed_s"] = runtime.get("opt")
        row["place_elapsed_s"] = runtime.get("place")
        row["route_elapsed_s"] = runtime.get("route")
        row["impl_elapsed_s"] = runtime.get("impl")
        row["total_elapsed_s"] = runtime.get("total")

    # Per-IP sizes.
    hier_path = layout.impl_dir / "utilization_hier.txt"
    ip_rows = []
    if hier_path.exists():
        for ip in parse_utilization_hier(hier_path):
            ip_rows.append({"design_name": name, "design_id": design_id, **ip})

    return row, ip_rows


def read_csv(path: Path, columns: list[str]) -> list[dict]:
    """Read an existing output CSV (as strings), checking it has the expected header."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != columns:
            sys.exit(f"{path}: unexpected columns {reader.fieldnames}; expected {columns}")
        return list(reader)


def write_csv(
    rows: list[dict], columns: list[str], out_path: Path, update: bool = False
) -> int:
    """Write rows to out_path in design_id order; with update, merge into the existing file.

    Returns the number of rows written. Existing rows for the same design_name
    are replaced; all other existing rows are kept.
    """
    if update and out_path.exists():
        new_names = {r["design_name"] for r in rows}
        rows = [r for r in read_csv(out_path, columns) if r["design_name"] not in new_names] + rows
    rows.sort(key=lambda r: (int(r["design_id"]), int(r.get("ip_index", 0))))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "build_dirs", nargs="+", type=Path, help="build/design_NNNN directories to parse"
    )
    parser.add_argument(
        "--design-dir",
        type=Path,
        help="designs/design_NNNN source directory (single build dir only); "
        "its design.tcl gives num_ips",
    )
    parser.add_argument(
        "--designs-root",
        type=Path,
        help="directory holding designs/design_NNNN source directories "
        "(default: <build_dir>/../../designs)",
    )
    parser.add_argument(
        "--stats-csv", type=Path, required=True, help="output per-design CSV"
    )
    parser.add_argument(
        "--ip-sizes-csv", type=Path, required=True, help="output per-IP-instance CSV"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="merge into existing output CSVs: replace rows for these designs, keep "
        "the rest (default: overwrite the CSVs)",
    )
    parser.add_argument(
        "--include-incomplete",
        action="store_true",
        help="also emit rows for build dirs without impl.dcp/design.bit",
    )
    args = parser.parse_args()

    if args.design_dir and len(args.build_dirs) != 1:
        parser.error("--design-dir applies to exactly one build directory")

    rows, ip_rows = [], []
    skipped = 0
    for build_dir in sorted(args.build_dirs):
        if not build_dir.is_dir():
            sys.exit(f"{build_dir}: not a directory (run `make DESIGN=NNNN` first)")
        layout = Layout(build_dir)
        if not layout.is_complete() and not args.include_incomplete:
            skipped += 1
            continue
        if args.design_dir:
            design_tcl = args.design_dir / "design.tcl"
        elif layout.default_design_tcl is not None and not args.designs_root:
            design_tcl = layout.default_design_tcl
        else:
            root = args.designs_root or (build_dir.resolve().parent.parent / "designs")
            design_tcl = root / build_dir.name / "design.tcl"
        if not design_tcl.exists():
            print(f"warning: {design_tcl} not found; num_ips left empty", file=sys.stderr)
            design_tcl = None
        row, ips = collect_design(build_dir, design_tcl)
        rows.append(row)
        ip_rows.extend(ips)

    if skipped:
        print(f"Skipped {skipped} incomplete build dir(s) (no impl.dcp / design.bit)")
    if not rows:
        sys.exit("No completed designs found.")

    n = write_csv(rows, STATS_COLUMNS, args.stats_csv, update=args.update)
    print(f"Wrote {args.stats_csv}  ({n} design(s), {len(STATS_COLUMNS)} columns)")
    n = write_csv(ip_rows, IP_SIZE_COLUMNS, args.ip_sizes_csv, update=args.update)
    print(f"Wrote {args.ip_sizes_csv}  ({n} IP instance(s))")

if __name__ == "__main__":
    main()
