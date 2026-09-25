# RandSoC FPT-2026 dataset -- build any single design from its design.tcl.
#
# Requirements:
#   * Xilinx Vivado 2024.2 on your PATH. The designs instantiate
#     version-specific IP (VLNVs), so design.tcl checks the Vivado version and
#     errors out on a mismatch.
#   * python3 (only for the tiny vivado_ioparse.py helper).
#
# Usage:
#   make DESIGN=0042            # synth + impl + bitstream for design_0042
#   make synth DESIGN=0042      # synthesis only
#   make clean DESIGN=0042      # remove that design's build directory
#   make list                   # how many designs are available
#   make figures                # regenerate images/ from the two CSVs
#   make figures-env            # (optional) venv with numpy + matplotlib
#
# All build products land in build/design_<DESIGN>/ and mirror the artifacts
# shipped in the original dataset:
#   synthesis:      viv_synth.edf, synth.dcp, synth.v, report_io.txt, design.xdc
#   implementation: impl.dcp, viv_impl.v, viv_impl.edf, design.bit,
#                   utilization.txt, utilization_hier.txt, timing_summary.txt,
#                   congestion.txt, logic_levels.txt, power.txt

VIVADO  ?= vivado
PYTHON  ?= python3
DESIGN  ?= 0000
PART    ?= xc7a200tlffv1156-2L

# Absolute path to this Makefile's directory, so builds work from anywhere.
ROOT       := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
DESIGN_DIR := $(ROOT)/designs/design_$(DESIGN)
WORK       := $(ROOT)/build/design_$(DESIGN)

SYNTH_EDF  := $(WORK)/viv_synth.edf
BITSTREAM  := $(WORK)/design.bit

.PHONY: all synth impl clean list check figures figures-env \
        figures-utilization figures-timing figures-congestion figures-runtime \
        figures-ip-sizes

all: impl
synth: $(SYNTH_EDF)
impl: $(BITSTREAM)

check:
	@test -f $(DESIGN_DIR)/design.tcl || \
		{ echo "No such design: $(DESIGN_DIR) (try DESIGN=0000)"; exit 1; }

# --- Synthesis -----------------------------------------------------------
# design.tcl is self-contained: it builds the project + block design, runs
# synth_1, and writes viv_synth.edf / synth.dcp / report_io.txt into $(WORK).
# vivado_ioparse.py then turns report_io.txt into the pin constraints (design.xdc).
$(SYNTH_EDF): $(DESIGN_DIR)/design.tcl | check
	mkdir -p $(WORK)
	cd $(WORK) && $(VIVADO) -mode batch -source $(DESIGN_DIR)/design.tcl
	cd $(WORK) && $(PYTHON) $(ROOT)/scripts/vivado_ioparse.py \
		< report_io.txt > design.xdc

# --- Implementation ------------------------------------------------------
# Read the synthesized netlist + constraints, opt/place/route, write reports
# and the bitstream. DESIGN_DIR and PART are passed to impl.tcl via the env.
$(BITSTREAM): $(SYNTH_EDF)
	cd $(WORK) && DESIGN_DIR=$(DESIGN_DIR) PART=$(PART) \
		$(VIVADO) -mode batch -source $(ROOT)/scripts/impl.tcl

clean:
	rm -rf $(WORK)

list:
	@echo "$(words $(wildcard $(ROOT)/designs/design_*)) designs available (design_0000 .. design_9999)"

# --- Figures -------------------------------------------------------------
# Regenerate every figure in images/ purely from the two shipped CSVs; no
# Vivado or build products are needed. Requires numpy + matplotlib, either on
# $(PYTHON) or in a local venv created with `make figures-env`.
FIG_DIR     := $(ROOT)/scripts/figures
IMAGES_DIR  ?= $(ROOT)/images
STATS_CSV   ?= $(ROOT)/dataset_stats.csv
IP_CSV      ?= $(ROOT)/dataset_ip_sizes.csv
FIG_FORMATS ?= png
# IP types shown in the reduced per-IP size plot (ip_sizes_luts_ffs_subset).
IP_TYPES    ?= microblaze,fft,axi_dma,emc,complex_multiplier,cordic,axi_cdma,quad_spi,axi_iic,floating_point
# Prefer the local venv when it exists, otherwise fall back to $(PYTHON).
FIG_PYTHON  ?= $(if $(wildcard $(ROOT)/.venv/bin/python),$(ROOT)/.venv/bin/python,$(PYTHON))
FIG_ARGS     = --out-dir $(IMAGES_DIR) --formats $(FIG_FORMATS)

figures: figures-utilization figures-timing figures-congestion figures-runtime figures-ip-sizes

figures-utilization:
	$(FIG_PYTHON) $(FIG_DIR)/utilization.py --csv $(STATS_CSV) $(FIG_ARGS)

figures-timing:
	$(FIG_PYTHON) $(FIG_DIR)/timing.py --csv $(STATS_CSV) $(FIG_ARGS)

figures-congestion:
	$(FIG_PYTHON) $(FIG_DIR)/congestion.py --csv $(STATS_CSV) $(FIG_ARGS)

figures-runtime:
	$(FIG_PYTHON) $(FIG_DIR)/runtime.py --csv $(STATS_CSV) $(FIG_ARGS)

figures-ip-sizes:
	$(FIG_PYTHON) $(FIG_DIR)/ip_sizes.py --csv $(IP_CSV) $(FIG_ARGS) --types $(IP_TYPES)

figures-env: $(ROOT)/.venv/.installed

# Stamp file rather than .venv/bin/python: that is a symlink to the system
# interpreter, so its timestamp can't be used (or touched) to track installs.
$(ROOT)/.venv/.installed: $(FIG_DIR)/requirements.txt
	python3 -m venv $(ROOT)/.venv
	$(ROOT)/.venv/bin/pip install -r $(FIG_DIR)/requirements.txt
	touch $@
