# RandSoC: A 10,000-Design Synthetic FPGA Benchmark Suite

*Anonymized dataset for blind review.*

This directory provides the 10,000-design benchmark suite described in the
paper **"RandSoC: Generating Large, Diverse Synthetic FPGA Benchmark Suites for ML
Tooling Research,"** together with everything needed to rebuild any design from
scratch. The generator tool that produced these designs is in
[`../randsoc/`](../randsoc/).

## What is RandSoC?

Applying machine learning to FPGA CAD requires large, diverse, labeled circuit
datasets, yet established benchmark suites contain only tens of designs. RandSoC
generates arbitrarily large sets of random, *synthesizable* SoC designs from
configurable Xilinx IP connected through randomized interconnect topology. Each
design is a single, self-contained Tcl script that instantiates and configures a
random selection of IP cores (2--30 per design, plus automatically inserted
infrastructure IP), connects them into a legal design, and runs the full Vivado
flow to a bitstream. Every random decision is seeded, so a given configuration,
seed, and target part reproduces an identical design.

This suite of 10,000 designs targets the Xilinx Artix-7
`xc7a200tlffv1156-2L` (the largest Artix-7 device) using **Vivado 2024.2**, with a
120 MHz target clock. It was distilled from a larger pool of randomized designs,
keeping only those that implement successfully.

## What's in this directory

To keep the suite small and reproducible, **only the clean build inputs are
shipped** -- not the multi-gigabyte compiled outputs. You can rebuild any design's
netlists, reports, and bitstream with the included `Makefile` (see below).

```
README.md               this file
Makefile                build any single design end-to-end
dataset_stats.csv       per-design metrics for all 10,000 designs
dataset_ip_sizes.csv    per-IP-instance resource sizes
images/                 figures (regenerated from the two CSVs; see below)
scripts/
  impl.tcl              implementation Tcl driven by the Makefile
  vivado_ioparse.py     turns report_io.txt into pin constraints (design.xdc)
  collect_stats.py      turns a built design's reports into its dataset_stats.csv /
                        dataset_ip_sizes.csv rows (`make stats`; stdlib only)
  figures/              plotting scripts behind `make figures` (numpy + matplotlib)
designs/
  design_0000/          design.tcl, impl_constraints.tcl, clock_constraint.xdc
  ...
  design_9999/
```

## Building a design

Requirements: **Xilinx Vivado 2024.2** on your `PATH` (the designs use
version-specific IP, and `design.tcl` checks the version), and `python3`.

```sh
make DESIGN=0042          # synthesize + implement + bitstream for design_0042
make synth DESIGN=0042    # synthesis only
make stats DESIGN=0042    # extract its CSV rows from the reports
make clean DESIGN=0042    # remove that design's build directory
make list                 # count available designs
```

Build products land in `build/design_0042/`, in the same two-directory layout
the dataset was generated with: `vivado_synth/` holds `viv_synth.edf`,
`synth.dcp`, `report_io.txt`, `design.xdc`, and the synthesis `vivado.log`;
`vivado_impl/` holds `impl.dcp`, `design.bit`, `viv_impl.v`, the implementation
`vivado.log`, and the `utilization*.txt`, `timing_summary.txt`,
`congestion.txt`, `logic_levels.txt`, and `power.txt` reports.

The build flow is: `design.tcl` (self-contained synthesis) -> `vivado_ioparse.py`
(pin constraints) -> `scripts/impl.tcl` (place, route, report, bitgen).

## Dataset statistics

`dataset_stats.csv` has one row per design (`design_name`, `design_id`,
`num_ips`, and utilization / timing / congestion / runtime metrics).
`dataset_ip_sizes.csv` has one row per IP instance with its post-implementation
resource usage.

### Regenerating the CSVs

Each CSV row is extracted from the Vivado reports and logs of one built design
by `scripts/collect_stats.py` (Python standard library only). After rebuilding
a design, extract its rows with:

```sh
make DESIGN=0042          # rebuild (Vivado 2024.2)
make stats DESIGN=0042    # add its rows to build/dataset_stats.csv and
                          #   build/dataset_ip_sizes.csv
```

The two files under `build/` have the same layout as the shipped CSVs and
grow as more designs are rebuilt; running `make stats` again for a design
replaces its rows. `make stats-all` rewrites them from scratch from every
design present under `build/`. Rebuilding all 10,000 designs takes about
1,200 hours of Vivado time (the sum of the `total_elapsed_s` column, roughly
50 machine-days on one build machine), so the shipped CSVs are the aggregate
of the original build; the per-design path above lets any row be checked
independently against the shipped one.

Where each column comes from:

| Columns | Source in `build/design_NNNN/` |
|---|---|
| `num_ips` | `designs/design_NNNN/design.tcl` (randomly selected IP cores, excluding the auto-inserted infrastructure and glue IP) |
| `lut/ff/slice/bram/dsp/io_util_pct` | `vivado_impl/utilization.txt` (`report_utilization`) |
| `synth_*_util_pct` | `vivado_synth/synth_utilization.txt` (post-synthesis `report_utilization`). Not written by this flow and **empty in the shipped CSV**; the columns are kept for schema compatibility. |
| `wns_ns`, `tns_ns`, `failing_endpoints`, `total_endpoints`, `logic_levels`, `data_path_delay_ns`, `clk_period_ns` | `vivado_impl/timing_summary.txt` (`report_timing_summary`); `logic_levels` is the depth of the worst-slack path |
| `max_logic_levels` | `vivado_impl/logic_levels.txt` (`report_design_analysis -logic_level_distribution`); deepest path in the design |
| `congestion_*_pct`, `has_congestion_hotspot` | `vivado_impl/vivado.log`: the placer's per-direction `Max Cong = ..%` estimates. Vivado prints these only for larger designs, so they are empty for about a third of the suite. |
| `synth/opt/place/route_elapsed_s`, `impl_elapsed_s`, `total_elapsed_s` | `vivado_synth/vivado.log` and `vivado_impl/vivado.log`: the `Time (s): ... elapsed` line of each `*_design` command |
| `dataset_ip_sizes.csv` | `vivado_impl/utilization_hier.txt` (`report_utilization -hierarchical`): the row of each top-level `ip_<index>_<type>` wrapper |

What to expect from a rebuild. We verified the extraction step two ways.
First, running `collect_stats.py` over the original build output of all
10,000 designs (the same reports and logs the suite was assembled from, which
the script also reads) reproduces the shipped `dataset_stats.csv` and
`dataset_ip_sizes.csv` byte for byte. Second, rebuilding designs from this
artifact with `make DESIGN=NNNN` on a different machine from the one that
built the suite reproduces every column exactly, including LUT counts, slack,
and congestion, except the `*_elapsed_s` columns, which are wall-clock times
and depend on the machine.

Provenance: the suite was built on several machines with the same parsers,
which ran on each machine and produced small per-machine CSVs that were then
concatenated and renumbered `design_0000 ... design_9999` (see
`designs/`). `collect_stats.py` is that extraction step repackaged to read the
flat `build/design_NNNN/` layout the `Makefile` produces.

| Metric | Min | Median | Max |
|---|---|---|---|
| IP cores per design | 2 | 12 | 30 |
| Slice utilization | 0.1% | 20.9% | 99.8% |
| LUT utilization | 0.0% | 13.4% | 87.5% |
| Total runtime | 22 s | 276 s | 26855 s |

Designs meeting the 120 MHz target timing (WNS >= 0):
**3,187 / 10,000** (32%).

## Figures

### Regenerating the figures

Every figure in `images/` (other than the block-diagram screenshot) is produced
from `dataset_stats.csv` and `dataset_ip_sizes.csv` by the scripts in
`scripts/figures/`. No Vivado run or build products are needed (the CSVs
themselves are regenerated from build products with `make stats`, above).
Regenerate the figures with:

```sh
make figures-env      # optional: create .venv with numpy + matplotlib
make figures          # rewrite images/*.png from the two CSVs
```

`make figures` uses `.venv/bin/python` if `make figures-env` was run, otherwise
`python3` (which must have `numpy` and `matplotlib` installed). Set
`FIG_FORMATS=png,pdf` to also write PDFs, or `IMAGES_DIR=...` to write
elsewhere. Individual groups can be run with `make figures-utilization`,
`figures-timing`, `figures-congestion`, `figures-runtime`, or
`figures-ip-sizes`; each script also prints the summary statistics quoted in
the paper and the number of outliers clipped from each plot.

The paper's data figures map to the following files and scripts:

| Paper figure | File in `images/` | Script | Input CSV |
|---|---|---|---|
| Fig. 2 (per-IP size) | `ip_sizes_luts_ffs_subset.png` | `ip_sizes.py` | `dataset_ip_sizes.csv` |
| Fig. 3a (size vs. runtime) | `runtime_size_vs_runtime_loglog.png` | `runtime.py` | `dataset_stats.csv` |
| Fig. 3b (phase mix) | `runtime_phase_mix.png` | `runtime.py` | `dataset_stats.csv` |
| Fig. 4a (Fmax) | `timing_fmax.png` | `timing.py` | `dataset_stats.csv` |
| Fig. 4b (logic levels) | `timing_logic_levels.png` | `timing.py` | `dataset_stats.csv` |
| Fig. 5a (slice utilization) | `utilization_slice_log.png` | `utilization.py` | `dataset_stats.csv` |
| Fig. 5b (congestion) | `congestion_max.png` | `congestion.py` | `dataset_stats.csv` |

`utilization.py` also writes the per-resource LUT/FF/BRAM/DSP/IO histograms
shown at the end of this README. Fig. 1 (`system_block_diagram.png`) is a
Vivado block-design screenshot of one generated design and is not produced by
a script.

### Notes on the figures below

The figures below are regenerated directly from this released dataset, so they
differ slightly from the corresponding figures in the paper. The paper's figures
included runs collected across several different machines; once more runs had
completed, we elected to keep only seeds built on the same computer, giving a
consistent basis for runtime comparison. This final dataset therefore uses a
different set of seeds, producing minor differences in the distributions.

**Example generated design.** *An example SoC design generated by RandSoC.*

![Example generated design](images/system_block_diagram.png)

**Per-IP size diversity.** *Post-implementation size distribution (LUTs + FFs) for a subset of IP types. A single IP type spans orders of magnitude depending on its randomized configuration.*

![Per-IP size diversity](images/ip_sizes_luts_ffs_subset.png)

**Slice utilization.** *Slice utilization distribution across the suite (log-scaled design counts).*

![Slice utilization](images/utilization_slice_log.png)

**Routing congestion.** *Peak routing-segment utilization distribution -- most designs are routing-constrained.*

![Routing congestion](images/congestion_max.png)

**Maximum frequency.** *Achievable maximum frequency (Fmax) across the suite.*

![Maximum frequency](images/timing_fmax.png)

**Logic-level depth.** *Maximum combinational logic-level depth per design.*

![Logic-level depth](images/timing_logic_levels.png)

**Size vs. runtime.** *Design size vs. total implementation runtime (log-log).*

![Size vs. runtime](images/runtime_size_vs_runtime_loglog.png)

**Phase mix.** *Per-design implementation phase mix (opt / place / route), colored by total runtime.*

![Phase mix](images/runtime_phase_mix.png)


### Resource utilization by type

The short paper reports slice utilization only (above). For completeness, the
per-resource (per-BEL) utilization distributions across all 10,000 designs
are shown below -- LUTs, flip-flops, block RAM, DSPs, and I/O. Per-design values
for every resource (and post-synthesis variants) are in `dataset_stats.csv`, and a
per-IP-instance breakdown is in `dataset_ip_sizes.csv`.

**LUT utilization.** *Distribution of LUT utilization across the suite (log-scaled design counts).*

![LUT utilization](images/utilization_lut_log.png)

**Flip-flop utilization.** *Distribution of flip-flop (FF) utilization across the suite.*

![Flip-flop utilization](images/utilization_ff_log.png)

**Block-RAM utilization.** *Distribution of block-RAM (BRAM) utilization; many designs use no BRAM.*

![Block-RAM utilization](images/utilization_bram_log.png)

**DSP utilization.** *Distribution of DSP-block utilization across the suite.*

![DSP utilization](images/utilization_dsp_log.png)

**I/O utilization.** *Distribution of bonded-IOB (I/O) utilization across the suite.*

![I/O utilization](images/utilization_io_log.png)


## License / attribution

Author and affiliation details are withheld for blind review.
