# v8 Chip-Level Search (Grounded)

> **Pipeline ID:** tt_20260221
> **RAG:** v7 (max_results=50)
> **Search:** `Overlay SFPU TDMA SMN DFX iJTAG dispatch FDS`, max_results=30
> **Date:** 2026-04-29

## DFX iJTAG Chain (enhanced from v7)

### Full Chain Topology

```
tt_instrn_engine_wrapper_dfx (11in/9out)
  ← receives from: tt_t6_l1_partition, tt_fpu_gtile_0, tt_fpu_gtile_1
  → sends to: dfd

tt_disp_eng_noc_niu_router_dfx (10in/7out)
  ← receives from: tt_disp_eng_overlay_wrapper_dfx, tt_disp_eng_l1_partition_dfx
  → sends to: dfd

tt_disp_eng_l1_partition_dfx (7in/3out)
  ← receives from: tt_disp_eng_noc_niu_router_dfx
  → sends to: dfd

tt_disp_eng_overlay_wrapper_dfx (7in/3out)  ← v8 NEW
  ← receives from: tt_disp_eng_noc_niu_router_dfx
  → sends to: dfd
```

### v8 NEW DFX Findings

- **tt_disp_eng_overlay_wrapper_dfx** — new iJTAG chain node discovered (7in/3out)
- **tt_instrn_engine_wrapper_dfx** upstream sources identified: tt_t6_l1_partition + tt_fpu_gtile_0/1
- Full bidirectional chain: noc_niu_router_dfx ↔ overlay_wrapper_dfx / l1_partition_dfx

## TDMA (unchanged from v7)

3 sub-modules: tt_tdma_xy_address_controller, tt_tdma_thread_context, tt_tdma_rts_rtr_pipe_stage

## SFPU (unchanged from v7)

tt_sfpu_lregs, tt_sfpu_instrn_resources_used

## SMN

tt_smn_clkdiv(5in/3out), tt_smn_repeater_struct(16in/8out)

## FDS Registers

tt_fds_tensixneo_reg(106in/41out), tt_fds_dispatch_reg(68in/41out), tt_cluster_ctrl_t6_l1_csr_reg(38in/97out)

## SRAM Macros

RF_2P_HSC_LVT_32X136M1FB1WM0DR0 — multiple instances across DFX, NoC, EDC subsystems
