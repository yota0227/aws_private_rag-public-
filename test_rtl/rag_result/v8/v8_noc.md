# v8 NoC Topic Search

> **Pipeline ID:** tt_20260221
> **Search:** `NoC routing arbiter repeater flit noc2axi`, topic=NoC, max_results=30
> **Date:** 2026-04-29

## NoC Modules (14 results)

| Module | Role | Key Facts |
|--------|------|-----------|
| noc_arbiter_tree | Arbitration | Priority-based multi-requestor grant |
| tt_noc_repeaters_cardinal | Repeater | Connects input/output NoC packages |
| tt_upf_async_fifo | CDC FIFO | Write/read clocks at different frequencies |
| tt_niu_mst_timeout | Timeout | Configurable timeout → interrupt + timeout signal |
| tt_noc_sync3_pulse | CDC Sync | Pulse synchronization between clock domains |
| tt_noc_async_fifo_wr_side_reset | Reset Sync | Write/read side reset generation for async FIFO |
| tt_skid_buffer_new_assertion_off | Skid Buffer | Input/output decoupling |
| tt_noc_secded_chk_corr_116_10 | ECC | SECDED on 116-bit data with 10-bit check bits |
| tt_harvest_robust_sync | Harvest Sync | Robust synchronization with multiple replications |

## SRAM Macros in NoC

RF_2P_HSC_LVT_32X136M1FB1WM0DR0 — 32x136 dual-port, HSC LVT (x2+ instances)
tt_mem_wrap_32x1024_2p_nomask — ATT SRAM + noc_routing_translation_selftest (BIST)

## Routing Algorithms / Flit Structure / AXI Gasket / Security Fence

[NOT IN KB] — requires tt_noc_pkg.sv struct extraction or Spec RAG

## v8 vs v7: No new NoC claims from parser. Coverage unchanged.
