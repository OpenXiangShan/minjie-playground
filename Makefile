SHELL := /bin/bash

.DEFAULT_GOAL := help

ROOT_DIR := $(abspath .)
BUILD_DIR := $(ROOT_DIR)/build
BUILD_LOG_DIR ?= $(BUILD_DIR)/build-log
LOG_STAMP := $(shell date +%Y%m%d-%H%M%S)
TIME_STAMP := $(shell date +%H%M%S)

DESIGN_GOAL := $(firstword $(filter xiangshan nutshell xs nut,$(MAKECMDGOALS)))
DESIGN ?= $(DESIGN_GOAL)
ifeq ($(DESIGN),xs)
override DESIGN := xiangshan
endif
ifeq ($(DESIGN),nut)
override DESIGN := nutshell
endif
JOBS ?= 16

XS_HOME := $(ROOT_DIR)/XiangShan
NUT_HOME := $(ROOT_DIR)/NutShell
WORKLOAD_HOME := $(ROOT_DIR)/workload-builder
BIN2DDR_HOME := $(ROOT_DIR)/Bin2ddr
DIFFTEST_HOME := $(ROOT_DIR)/difftest
NEMU_HOME := $(ROOT_DIR)/NEMU

DIFFTEST_CONFIG ?= ESBIFDU
DIFFTEST_EXCLUDE ?= Vec

XS_CONFIG ?= FpgaDiffDefaultConfig
XS_DEBUG_ARGS ?= --difftest-config $(DIFFTEST_CONFIG) --difftest-exclude $(DIFFTEST_EXCLUDE)

NUT_BOARD ?= fpgadiff
NUT_MILL_ARGS ?= --difftest-config $(DIFFTEST_CONFIG)

DESIGN_HOME = $(if $(filter $(DESIGN),nutshell),$(NUT_HOME),$(XS_HOME))
FPGA_HOST_HOME ?=
FPGA_HOST_ARGS ?= RELEASE=1 FPGA=1 DIFFTEST_PERFCNT=1
RELEASE_DIR ?= $(BUILD_DIR)/release
RELEASE_SUFFIX ?= $(TIME_STAMP)
RELEASE_LOG ?= $(BUILD_LOG_DIR)/release-$(DESIGN)-$(LOG_STAMP).log
RELEASE_LATEST_PATH ?= $(RELEASE_DIR)/latest-$(DESIGN).path
RELEASE_LATEST_NAME ?= $(RELEASE_DIR)/latest-$(DESIGN).name
VERILOG_LOG ?= $(BUILD_LOG_DIR)/verilog-$(DESIGN)-$(LOG_STAMP).log
HOST_LOG ?= $(BUILD_LOG_DIR)/host-$(DESIGN)-$(LOG_STAMP).log
WORKLOAD_LOG ?= $(BUILD_LOG_DIR)/workload-$(WORKLOAD_TAG)-$(LOG_STAMP).log

NEMU_CONFIG ?= riscv64-xs-ref-novec-nopmppma_defconfig
NEMU_SO_NAME ?= riscv64-nemu-interpreter-so
READY_TO_RUN_DIR ?= $(ROOT_DIR)/ready-to-run
NEMU_OUT_DIR ?= $(READY_TO_RUN_DIR)/$(NEMU_CONFIG)
NEMU_OUT_SO ?= $(NEMU_OUT_DIR)/$(NEMU_SO_NAME)
NEMU_SRC_SO ?= $(NEMU_HOME)/build/$(NEMU_SO_NAME)
NEMU_LOG ?= $(BUILD_LOG_DIR)/nemu-$(NEMU_CONFIG)-$(LOG_STAMP).log

# Only Vivado/FPGA run-side commands use REMOTE. Other build targets run locally.
REMOTE ?=
REMOTE_DIR ?= $(ROOT_DIR)
REMOTE_ENV ?= source ~/.bash_profile &&
SSH ?= ssh

FPGA_ROOT := $(if $(strip $(REMOTE)),$(REMOTE_DIR),$(ROOT_DIR))
FPGA_DIFF_HOME := $(FPGA_ROOT)/env-scripts/fpga_diff
FPGA_BUILD_LOG_DIR ?= $(FPGA_ROOT)/build/build-log

CPU ?= $(if $(filter $(DESIGN),nutshell),nutshell,kmh)
SUFFIX ?=
PRJ_NAME = fpga_$(CPU)$(if $(strip $(SUFFIX)),-$(strip $(SUFFIX)),)
BIT_SRC_DIR ?= $(shell cat "$(RELEASE_LATEST_PATH)" 2>/dev/null)
CORE_DIR ?= $(BIT_SRC_DIR)/build
CHI_DIR ?=
BIT_ROOT ?= $(FPGA_ROOT)/bitstream
BIT_TAG ?= $(DESIGN)-$(LOG_STAMP)
BIT_OUT_DIR ?= $(BIT_ROOT)/$(BIT_TAG)
BIT_LOG ?= $(FPGA_BUILD_LOG_DIR)/bit-$(CPU)-$(LOG_STAMP).log
FPGA_BIT_HOME ?=
WORKLOAD ?=

define abs_path
$(if $(strip $(1)),$$(realpath -m "$(1)"))
endef

define remote
$(if $(strip $(REMOTE)),$(SSH) $(REMOTE) 'cd $(REMOTE_DIR) && $(REMOTE_ENV) $(1)',$(1))
endef

define require_var
	@test -n "$($(1))" || { echo "ERROR: please set $(1)=..."; exit 1; }
endef

define require_design
	@test "$(DESIGN)" = "xiangshan" -o "$(DESIGN)" = "nutshell" || { \
		echo "ERROR: pass design as DESIGN=xiangshan/nutshell or make $@ xiangshan/nutshell"; \
		exit 1; \
	}
endef

define link_one_difftest
	dst="$(1)/difftest"; repo="$(1)"; rel="../difftest"; \
	if [ -L "$$dst" ]; then \
		current=$$(readlink "$$dst"); \
		if [ "$$current" != "$$rel" ]; then unlink "$$dst"; ln -s "$$rel" "$$dst"; fi; \
		echo "$$dst -> $$rel"; \
	elif [ ! -e "$$dst" ]; then \
		ln -s "$$rel" "$$dst"; echo "$$dst -> $$rel"; \
	elif [ -d "$$dst" ] && [ -z "$$(find "$$dst" -mindepth 1 -maxdepth 1 -print -quit)" ]; then \
		rmdir "$$dst"; ln -s "$$rel" "$$dst"; echo "$$dst -> $$rel"; \
	elif [ -d "$$dst" ] && git -C "$$dst" rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		if [ -n "$$(git -C "$$dst" status --short)" ]; then \
			echo "ERROR: $$dst has local changes; refusing to replace it with top-level difftest"; exit 1; \
		fi; \
		git -C "$$repo" submodule deinit -f difftest; \
		if [ -d "$$dst" ] && [ -z "$$(find "$$dst" -mindepth 1 -maxdepth 1 -print -quit)" ]; then rmdir "$$dst"; fi; \
		test ! -e "$$dst" || { echo "ERROR: $$dst still exists after submodule deinit"; exit 1; }; \
		ln -s "$$rel" "$$dst"; echo "$$dst -> $$rel"; \
	else \
		echo "ERROR: $$dst is not empty and is not a clean git submodule; refusing to replace it"; exit 1; \
	fi
endef

TARGET ?= linux/hello
WORKLOAD_TYPE ?= $(firstword $(subst /, ,$(TARGET)))
WORKLOAD_NAME ?= $(if $(findstring /,$(TARGET)),$(word 2,$(subst /, ,$(TARGET))),$(TARGET))
WORKLOAD_TAG ?= $(DESIGN)-$(subst /,-,$(TARGET))
WORKLOAD_BIN ?=
WORKLOAD_LINUX_BIN := $(WORKLOAD_HOME)/build/linux-workloads/$(WORKLOAD_NAME)/fw_payload.bin
WORKLOAD_AM_BIN_DIR := $(WORKLOAD_HOME)/build/am-workloads/$(WORKLOAD_NAME)/package/bin
WORKLOAD_OUT_DIR ?= $(READY_TO_RUN_DIR)/$(WORKLOAD_TAG)
WORKLOAD_OUT_BIN ?= $(WORKLOAD_OUT_DIR)/$(WORKLOAD_TAG).bin
WORKLOAD_OUT_TXT ?= $(WORKLOAD_OUT_DIR)/$(WORKLOAD_TAG).txt
BIN2DDR_ARGS ?=

# AM workload: select ARCH and CPPFLAGS based on DESIGN
AM_ARCH ?= $(if $(filter nutshell,$(DESIGN)),riscv64-nutshell,riscv64-xs)
AM_CPPFLAGS  ?= -DUART16550=1

HOST_BIN ?= $(if $(FPGA_HOST_HOME),$(FPGA_HOST_HOME)/build/fpga-host,)
HOST_ARGS ?=
RUN_LOG ?= $(BUILD_DIR)/run-log/run-$$(date +%Y%m%d-%H%M%S).log

.PHONY: help init link_difftest clean verilog release host bit write_bitstream \
	write_jtag_ddr reset_cpu workload nemu run_host \
	xiangshan nutshell xs nut

help:
	@printf '%s\n' 'FpgaDiff playground targets:'
	@printf '%s\n' '  make init                         init top submodules; run submodule init where available'
	@printf '%s\n' '  make verilog xiangshan            build XiangShan FPGA DiffTest Verilog'
	@printf '%s\n' '  make verilog nutshell             build NutShell FPGA DiffTest Verilog'
	@printf '%s\n' '  make release xiangshan            package RTL/difftest release'
	@printf '%s\n' '  make host xiangshan FPGA_HOST_HOME=...'
	@printf '%s\n' '  make bit xiangshan                build bitstream bundle under bitstream/<design>-<time>/'
	@printf '%s\n' '  make workload xiangshan TARGET=am/hello  build workload and generate ready-to-run/<design>-<target>'
	@printf '%s\n' '  make nemu                         build NEMU ref so into ready-to-run/<NEMU_CONFIG>/'
	@printf '%s\n' '  make write_bitstream FPGA_BIT_HOME=...'
	@printf '%s\n' '  make write_jtag_ddr FPGA_BIT_HOME=... WORKLOAD=...'
	@printf '%s\n' '  make reset_cpu FPGA_BIT_HOME=...'
	@printf '%s\n' ''
	@printf '%s\n' 'Remote Vivado/FPGA: add REMOTE=user@host REMOTE_DIR=/path/to/FpgaDiff-playground.'

# Keep XS/Nut difftest as symlinks to the top-level difftest; otherwise
# their submodule init checks out the shared difftest to their gitlink commits.
init:
	git submodule update --init
	git -C $(XS_HOME) config submodule.difftest.update none
	git -C $(NUT_HOME) config submodule.difftest.update none
	$(MAKE) -C $(XS_HOME) init
	$(MAKE) -C $(NUT_HOME) init
	$(MAKE) -C $(WORKLOAD_HOME) init
	$(MAKE) -C $(BIN2DDR_HOME) FPGA=1
	$(MAKE) link_difftest

link_difftest:
	@set -e; \
	test -d "$(DIFFTEST_HOME)" || { echo "ERROR: missing top-level difftest at $(DIFFTEST_HOME)"; exit 1; }; \
	$(call link_one_difftest,$(XS_HOME)); \
	$(call link_one_difftest,$(NUT_HOME))

clean:
	$(call require_design)
	$(MAKE) -C $(DESIGN_HOME) clean

verilog:
	$(call require_design)
	$(MAKE) link_difftest
	mkdir -p $(BUILD_LOG_DIR)
ifeq ($(DESIGN),nutshell)
	set -o pipefail; \
	NOOP_HOME=$(NUT_HOME) \
	$(MAKE) -C $(NUT_HOME) verilog BOARD=$(NUT_BOARD) \
		MILL_ARGS="$(NUT_MILL_ARGS)" -j$(JOBS) 2>&1 | tee $(VERILOG_LOG)
else
	set -o pipefail; \
	NOOP_HOME=$(XS_HOME) \
	$(MAKE) -C $(XS_HOME) verilog FPGA=1 CONFIG=$(XS_CONFIG) \
		DEBUG_ARGS="$(XS_DEBUG_ARGS)" -j$(JOBS) 2>&1 | tee $(VERILOG_LOG)
endif

release:
	$(call require_design)
	$(MAKE) link_difftest
	mkdir -p $(RELEASE_DIR) $(BUILD_LOG_DIR)
	set -o pipefail; \
	NOOP_HOME=$(DESIGN_HOME) \
	$(MAKE) -C $(DESIGN_HOME)/difftest \
		fpga-release RELEASE_DIR=$(RELEASE_DIR) RELEASE_SUFFIX=$(RELEASE_SUFFIX) 2>&1 | tee $(RELEASE_LOG); \
	release_home=$$(sed -n 's/^Release FpgaDiff to \(.*\) done\.$$/\1/p' $(RELEASE_LOG) | tail -n 1); \
	test -n "$$release_home" || { echo "ERROR: failed to parse release path from $(RELEASE_LOG)"; exit 1; }; \
	release_name=$$(basename "$$release_home"); \
	release_pkg="$(RELEASE_DIR)/$$release_name.tar.gz"; \
	test -f "$$release_pkg" || { echo "ERROR: release package not found: $$release_pkg"; exit 1; }; \
	rm -rf "$(RELEASE_DIR)/$$release_name"; \
	tar -xzf "$$release_pkg" -C "$(RELEASE_DIR)"; \
	printf '%s\n' "$(RELEASE_DIR)/$$release_name" > "$(RELEASE_LATEST_PATH)"; \
	printf '%s\n' "$$release_name" > "$(RELEASE_LATEST_NAME)"; \
	echo "Release extracted to $(RELEASE_DIR)/$$release_name"; \
	echo "Release name written to $(RELEASE_LATEST_NAME)"

host:
	$(call require_design)
	$(call require_var,FPGA_HOST_HOME)
	$(MAKE) link_difftest
	mkdir -p $(BUILD_LOG_DIR)
	set -o pipefail; \
	NOOP_HOME=$(FPGA_HOST_HOME) \
	$(MAKE) -C $(FPGA_HOST_HOME)/difftest fpga-host $(FPGA_HOST_ARGS) \
		2>&1 | tee $(HOST_LOG)

bit:
	$(call require_design)
	$(call remote,set -e; \
		release_src="$(BIT_SRC_DIR)"; \
		test -n "$$release_src" || { \
			echo "ERROR: missing latest release path: $(RELEASE_LATEST_PATH)"; \
			echo "Run make release $(DESIGN) first or set BIT_SRC_DIR=..."; \
			exit 1; \
		}; \
		test -d "$$release_src" || { \
			echo "ERROR: bit release directory not found: $$release_src"; \
			exit 1; \
		}; \
		test -n "$(BIT_OUT_DIR)" && test "$(BIT_OUT_DIR)" != "/" || { \
			echo "ERROR: refusing unsafe BIT_OUT_DIR=$(BIT_OUT_DIR)"; \
			exit 1; \
		}; \
		rm -rf "$(BIT_OUT_DIR)"; \
		mkdir -p "$(FPGA_BUILD_LOG_DIR)" "$(BIT_OUT_DIR)")
	$(call remote,set -o pipefail; \
		$(MAKE) -C $(FPGA_DIFF_HOME) all CPU=$(CPU) SUFFIX="$(SUFFIX)" CORE_DIR=$(CORE_DIR) CHI_DIR=$(CHI_DIR) \
			2>&1 | tee $(BIT_LOG))
	$(call remote,set -o pipefail; \
		$(MAKE) -C $(FPGA_DIFF_HOME) bitstream CPU=$(CPU) SUFFIX="$(SUFFIX)" 2>&1 | tee -a $(BIT_LOG))
	$(call remote,set -o pipefail; \
		release_src="$(BIT_SRC_DIR)"; \
		find $(FPGA_DIFF_HOME)/$(PRJ_NAME) -type f \( -name "*.bit" -o -name "*.ltx" \) \
			-exec cp -f {} "$(BIT_OUT_DIR)/" \; && \
		cp -a "$$release_src" "$(BIT_OUT_DIR)/" && \
		find "$(BIT_OUT_DIR)" -maxdepth 1 -mindepth 1 | sort | tee -a $(BIT_LOG))

write_bitstream:
	$(call require_var,FPGA_BIT_HOME)
	$(call remote,$(MAKE) -C $(FPGA_DIFF_HOME) write_bitstream FPGA_BIT_HOME=$(call abs_path,$(FPGA_BIT_HOME)))

write_jtag_ddr:
	$(call require_var,FPGA_BIT_HOME)
	$(call require_var,WORKLOAD)
	$(call remote,$(MAKE) -C $(FPGA_DIFF_HOME) write_jtag_ddr FPGA_BIT_HOME=$(call abs_path,$(FPGA_BIT_HOME)) WORKLOAD=$(call abs_path,$(WORKLOAD)))

reset_cpu:
	$(call require_var,FPGA_BIT_HOME)
	$(call remote,$(MAKE) -C $(FPGA_DIFF_HOME) reset_cpu FPGA_BIT_HOME=$(call abs_path,$(FPGA_BIT_HOME)))

workload:
	$(call require_design)
	mkdir -p $(WORKLOAD_OUT_DIR) $(BUILD_LOG_DIR)
	set -o pipefail; \
	if [ "$(WORKLOAD_TYPE)" = "am" ]; then \
		$(MAKE) -C $(WORKLOAD_HOME) $(TARGET) ARCH=$(AM_ARCH) CPPFLAGS="$(AM_CPPFLAGS)" -j$(JOBS) 2>&1 | tee $(WORKLOAD_LOG); \
	else \
		$(MAKE) -C $(WORKLOAD_HOME) $(TARGET) -j$(JOBS) 2>&1 | tee $(WORKLOAD_LOG); \
	fi
	set -o pipefail; src="$(WORKLOAD_BIN)"; \
	if [ -z "$$src" ] && [ "$(WORKLOAD_TYPE)" = "linux" ]; then src="$(WORKLOAD_LINUX_BIN)"; fi; \
	if [ -z "$$src" ] && [ "$(WORKLOAD_TYPE)" = "am" ]; then \
		src=$$(find "$(WORKLOAD_AM_BIN_DIR)" -maxdepth 1 -type f -name '*.bin' | sort | head -n 1); \
	fi; \
	test -n "$$src" && test -f "$$src" || { echo "ERROR: workload binary not found. Set WORKLOAD_BIN=..."; exit 1; }; \
	cp "$$src" $(WORKLOAD_OUT_BIN) 2>&1 | tee -a $(WORKLOAD_LOG)
	set -o pipefail; $(MAKE) -C $(BIN2DDR_HOME) FPGA=1 2>&1 | tee -a $(WORKLOAD_LOG)
	set -o pipefail; \
	$(BIN2DDR_HOME)/bin2ddr -i $(WORKLOAD_OUT_BIN) -o $(WORKLOAD_OUT_TXT) \
		$(BIN2DDR_ARGS) 2>&1 | tee -a $(WORKLOAD_LOG)

nemu:
	mkdir -p $(NEMU_OUT_DIR) $(BUILD_LOG_DIR)
	set -o pipefail; $(MAKE) -C $(NEMU_HOME) NEMU_HOME=$(NEMU_HOME) $(NEMU_CONFIG) 2>&1 | tee $(NEMU_LOG)
	set -o pipefail; $(MAKE) -C $(NEMU_HOME) NEMU_HOME=$(NEMU_HOME) -j$(JOBS) 2>&1 | tee -a $(NEMU_LOG)
	test -f "$(NEMU_SRC_SO)" || { echo "ERROR: NEMU ref so not found: $(NEMU_SRC_SO)"; exit 1; }
	cp -f "$(NEMU_SRC_SO)" "$(NEMU_OUT_SO)" 2>&1 | tee -a $(NEMU_LOG)
	echo "NEMU ref so copied to $(NEMU_OUT_SO)" | tee -a $(NEMU_LOG)

run_host:
	$(call require_var,HOST_ARGS)
	run_log="$(RUN_LOG)"; mkdir -p "$$(dirname "$$run_log")"
	set -o pipefail; \
	run_log="$(RUN_LOG)"; \
	$(call remote,$(HOST_BIN) $(HOST_ARGS)) 2>&1 | tee "$$run_log"

xiangshan nutshell xs nut:
	@:
