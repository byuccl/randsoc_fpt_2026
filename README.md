# RandSoC

*Anonymized repository for blind review.*

This repository accompanies the paper **"RandSoC: Generating Large, Diverse
Synthetic FPGA Benchmark Suites for ML Tooling Research."** It contains two parts:

- **[`randsoc/`](randsoc/)** — the RandSoC generator tool: a Python tool that
  generates random, synthesizable Xilinx SoC designs from configurable IP with
  randomized interconnect topology. See [`randsoc/README.md`](randsoc/README.md)
  to install it and generate your own designs.
- **[`dataset/`](dataset/)** — the generated **10,000-design** benchmark
  suite described in the paper, targeting the Xilinx Artix-7 `xc7a200tlffv1156-2L` with
  Vivado 2024.2. It ships the build inputs for every design plus a
  Makefile to rebuild any of them, per-design and per-IP statistics CSVs, the
  script that extracts those CSV rows from a rebuilt design's Vivado reports,
  the paper's figures, and the scripts that regenerate those figures from the CSVs.
  See [`dataset/README.md`](dataset/README.md).

The `dataset/` designs were generated with `randsoc/`, using the
`fpt_2026.yaml` configuration included under
[`randsoc/configs/`](randsoc/configs/).

## Quick start

Generate a new random design with the tool:

```sh
cd randsoc
make env                                            # create .venv, install deps
make run CONFIG=configs/fpt_2026.yaml SEED=0        # writes ./temp/design.tcl
```

Rebuild one of the suite's designs to a bitstream, then regenerate its rows of
the statistics CSVs from the resulting reports:

```sh
cd dataset
make DESIGN=0042                                    # needs Vivado 2024.2
make stats DESIGN=0042                              # reports -> CSV rows
```

Regenerate the paper's figures from the shipped CSVs (no Vivado needed):

```sh
cd dataset
make figures-env                                    # optional venv: numpy + matplotlib
make figures                                        # rewrites dataset/images/*.png
```

## License / attribution

Author and affiliation details are withheld for blind review.
