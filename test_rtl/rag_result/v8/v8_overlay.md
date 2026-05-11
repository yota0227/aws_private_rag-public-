# v8 Overlay Topic Search

> **Pipeline ID:** tt_20260221
> **Search:** combined from chip_grounded + overlay-specific results
> **Date:** 2026-04-29

## SFPU

- **tt_sfpu_lregs:** Register file with transpose/shift, read/write data/parity, parity error reporting
- **tt_sfpu_instrn_resources_used:** Instruction resource analysis — R/W hazards, SFPU status, stall conditions

## TDMA (3 sub-modules)

- **tt_tdma_xy_address_controller:** DMA address generation from input instructions
- **tt_tdma_thread_context:** Thread context management, multi-channel DMA address/control
- **tt_tdma_rts_rtr_pipe_stage:** Pipelined RTS/RTR arbitration with configurable width

## FDS Registers

| Module | Input Ports | Output Ports |
|--------|-------------|--------------|
| tt_fds_tensixneo_reg | 106 | 41 |
| tt_fds_dispatch_reg | 68 | 41 |
| tt_cluster_ctrl_t6_l1_csr_reg | 38 | 97 |

## SMN

- tt_smn_clkdiv (5in/3out) — generates multiple clock domains from noc_clk
- tt_smn_repeater_struct (16in/8out) — repeats/forwards SMN data and control signals

## Clock Distribution

- tt_clkdiv2 — clock divide-by-2
- tt_clkbuf — clock buffer
- tt_clkgater / tt_clk_gater — clock gating with hysteresis and test mode

## v8 vs v7: No new overlay claims from parser. Coverage unchanged.
