# Overlay (RISC-V) + SFPU/TDMA/SMN HDD

> **Pipeline ID:** tt_20260221 | **Version:** v6c | **Search:** Overlay(7) + SFPU/TDMA/SMN(20)

---

## Overlay Registers

| Module | In | Out | Inner |
|--------|----|-----|-------|
| `tt_fds_tensixneo_reg` | 106 | 41 | `_inner` |
| `tt_fds_dispatch_reg` | 68 | 41 | `_inner` |
| `tt_cluster_ctrl_t6_l1_csr_reg` | 38 | 97 | `_inner` |

## SFPU

- `tt_sfpu_lregs`: Register file (transpose/shift, parity, error injection)
- `tt_sfpu_instrn_resources_used`: R/W hazards, stall conditions

## TDMA

- `tt_tdma_thread_context`: Multi-channel DMA addr/ctrl gen, RTS/RTR
- TDMA HDD: address generation, thread context, RTS/RTR for NoC system

## SMN

- `tt_smn_repeater_struct` (16/8): SMN data/control repeater
- `tt_smn_clkdiv` (5/3): Clock domain generation

## HDD Sections

SFPU HDD, TDMA HDD, SMN HDD, Overlay HDD, Dispatch HDD, DFX HDD

## EDC Interface (`tt_edc_pkg.sv`)

4 modports: ingress/egress/edc_node/sram (5+ file variants)

## [NOT IN KB]

CPU cluster, L1 internals, iDMA, ROCC, LLK, APB map