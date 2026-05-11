# Overlay + SFPU/TDMA/SMN HDD (Round 4: 20 results)

> **v7** | tt_20260221

## SFPU HDD (v7 신규)
- tt_sfpu_lregs: register file, transpose/shift, parity
- tt_sfpu_instrn_resources_used: R/W hazards, stalls

## TDMA HDD (v7 신규 — 3개 sub-module!)
- tt_tdma_xy_address_controller: DMA address gen
- tt_tdma_thread_context: thread context, multi-channel
- tt_tdma_rts_rtr_pipe_stage: pipelined RTS/RTR

## SMN HDD
noc2axi bridge, RF_2P_HSC_LVT SRAM macros

## Overlay Registers
tt_fds_tensixneo_reg(106/41), tt_fds_dispatch_reg(68/41)

## [NOT IN KB]
CPU cluster, L1 internals, iDMA, ROCC, LLK, APB map