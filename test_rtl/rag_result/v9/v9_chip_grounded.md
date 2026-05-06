# Trinity N1B0 NPU — Hardware Design Document (Hybrid Grounding)

**Pipeline ID:** tt_20260221
**RAG Version:** v9
**Generated:** 2026-05-06
**Grounding Mode:** Hybrid (KB-first + LLM supplement)

---

## Grounding Legend

| Tag | Meaning |
|-----|---------|
| (no tag) | Confirmed from KB (module, port, claim data) |
| `[FROM LLM]` | Supplemented from LLM domain knowledge |
| `[NOT IN KB]` | Not in KB, cannot be inferred |
| `[TBC]` | Needs verification |

---

## 1. Overview

Trinity N1B0 is a Neural Processing Unit (NPU) SoC organized as a 4×5 2D mesh grid of heterogeneous tiles. The top-level module `trinity` has 106 ports in the N1B0 variant.

---

## 2. Package Constants and Grid

Source: `trinity_pkg.sv` (targets/4x5/)

| Parameter | Value | Source |
|-----------|-------|--------|
| SizeX | 4 | KB |
| SizeY | 5 | KB |
| NumNodes | 20 | KB |
| NumTensix | 12 | KB |
| NumNoc2Axi | 4 | KB |
| NumDispatch | 2 | KB |
| NumApbNodes | 4 | KB |
| NumDmComplexes | 14 | KB |
| EnableDynamicRouting | 1'b1 | KB |
| TensixPerCluster | 4 | KB |
| DMCoresPerCluster | 8 | KB |
| NumAxes | 2 | KB |
| NumDirections | 2 | KB |

### tile_t Enum

[FROM LLM] Based on architecture knowledge, tile_t enum defines 8 tile types:
- TENSIX, NOC2AXI_NE_OPT, NOC2AXI_ROUTER_NE_OPT, NOC2AXI_ROUTER_NW_OPT, NOC2AXI_NW_OPT, DISPATCH_E, DISPATCH_W, ROUTER

### Endpoint Index Table

[FROM LLM] EP = x * SizeY + y, yielding 20 endpoints (0..19) across the 4×5 grid.

---

## 3. Top-Level Ports

Module `trinity` — **106 total ports** (N1B0 variant):

| Category | Count | Key Signals | Source |
|----------|-------|-------------|--------|
| AXI_Interface | 39 | AXI bus | KB |
| NoC_Clock_Reset | 2 | i_noc_clk, i_noc_reset_n | KB |
| AI_Clock_Reset | 2 | i_ai_clk[SizeX-1:0], i_ai_reset_n[SizeX-1:0] | KB |
| Tensix_Reset | 1 | i_tensix_reset_n[NumTensix-1:0] | KB |
| EDC_APB | 16 | APB + 5 IRQs | KB |
| DM_Clock_Reset | 3 | i_dm_clk, i_dm_core_reset_n, i_dm_uncore_reset_n | KB |
| APB_Register | 8 | psel/paddr/penable/pwrite/pwdata/pready/prdata/pslverr | KB |
| SFR_Memory_Config | 17 | SRAM config | KB |
| PRTN_Power | 14 | Power partition chain | KB |
| Other | 4 | Misc | KB |

---

## 4. Module Hierarchy

```
trinity (top)
├── tt_tensix_with_l1 [×12]          — KB
├── tt_dispatch_top_inst_east         — KB (tt_dispatch_top_east)
├── tt_dispatch_top_inst_west         — KB (tt_dispatch_top_west)
├── edc_direct_conn_nodes             — KB (tt_edc1_intf_connector)
├── edc_loopback_conn_nodes           — KB (tt_edc1_intf_connector)
├── [NoC routers]                     — KB (tt_noc_repeaters_cardinal, noc_arbiter_tree, etc.)
└── [NIU bridges]                     — KB (tt_niu_mst_timeout)
```

Note: `trinity_router` is NOT instantiated in N1B0 (EMPTY by design).

---

## 5. Compute Tile (Tensix)

- FPU: `tt_fp_max_array`, `tt_dual_align`, `tt_fpu_gtile_SDUMP_INTF` — KB
- SFPU: `tt_sfpu_lregs` (register file), `tt_sfpu_instrn_resources_used` (hazard detection) — KB
- TDMA: `tt_tdma_xy_address_controller`, `tt_tdma_thread_context`, `tt_tdma_rts_rtr_pipe_stage` — KB
- [FROM LLM] L1 Cache with ECC protection
- [FROM LLM] DEST/SRCB register files for operand staging

---

## 6. Dispatch Engine

- `tt_dispatch_top_east` — East dispatch — KB
- `tt_dispatch_top_west` — West dispatch — KB
- [FROM LLM] Instruction distribution to Tensix tiles via NoC

---

## 7. NoC Fabric

| Component | Module | Source |
|-----------|--------|--------|
| Repeater | tt_noc_repeaters_cardinal | KB |
| Arbiter | noc_arbiter_tree | KB |
| ECC | tt_noc_secded_chk_corr_116_10 (SECDED 116b/10b) | KB |
| CDC Sync | tt_noc_sync3_pulse | KB |
| Async FIFO | tt_upf_async_fifo | KB |
| Skid Buffer | tt_skid_buffer_new_assertion_off | KB |
| Harvest Sync | tt_harvest_robust_sync | KB |
| Timeout | tt_niu_mst_timeout | KB |

Routing: DIM_ORDER / TENDRIL / DYNAMIC (EnableDynamicRouting=1) — KB

---

## 8. EDC

- Ring topology: `tt_edc1_intf_connector` (direct + loopback) — KB
- Serial bus: `tt_edc1_serial_bus_repeater` — KB
- BIU: `tt_edc1_biu_soc_apb4_wrap` → `edc1_biu_soc_apb4_inner` — KB
- Security: `tt_edc1_noc_sec_block_reg` → `edc1_noc_sec_block_reg_inner` — KB
- [FROM LLM] Harvest bypass via edc_mux_demux_sel

---

## 9. Power Management (PRTN)

- 14 PRTN_Power ports — KB
- ISO_EN[11:0] — 12 power island isolation enables — KB
- PRTNUN daisy-chain: FC2UN/UN2FC data/ready/clk/rstn × 4 columns — KB
- [FROM LLM] 4-column daisy-chain topology

---

## 10. Clock Architecture

| Clock | Width | Domain | Source |
|-------|-------|--------|--------|
| i_axi_clk | 1 | AXI | KB |
| i_noc_clk | 1 | NoC | KB |
| i_ai_clk | [SizeX-1:0] | AI (per-column) | KB |
| i_dm_clk | [SizeX-1:0] | DM (per-column) | KB |

- Clock gating: `tt_clkgater`, `tt_clk_gater` — KB
- Clock buffer: `tt_clkbuf` — KB

---

## 11. Reset Architecture

| Reset | Width | Source |
|-------|-------|--------|
| i_noc_reset_n | 1 | KB |
| i_ai_reset_n | [SizeX-1:0] | KB |
| i_tensix_reset_n | [NumTensix-1:0] | KB |
| i_dm_core_reset_n | [14][8] | KB |
| i_dm_uncore_reset_n | [14] | KB |
| i_edc_reset_n | 1 | KB |

---

## 12. SRAM Inventory

[FROM LLM] Memory instances include:
- RF_2P_HSC_LVT_32X136M1FB1WM0DR0 — 2-port register file (32×136-bit)
- Additional SRAM macros for L1 cache, NoC buffers

[NOT IN KB] Exact SRAM instance count and total capacity per tile.

---

## 13. DFX

[FROM LLM] DFX infrastructure includes iJTAG scan chains and BIST controllers.
[NOT IN KB] Specific scan chain topology and DFT mode details.

---

## 14. RTL File Reference

| File | Description | Source |
|------|-------------|--------|
| rtl/trinity.sv | Top-level | KB |
| rtl/targets/4x5/trinity_pkg.sv | Package constants | KB |
| used_in_n1/rtl/trinity.sv | N1B0 variant (106 ports) | KB |
| used_in_n1/mem_port/rtl/trinity.sv | N1B0 + mem_port | KB |

---

## KB Coverage Matrix

| Section | KB | FROM LLM | NOT IN KB |
|---------|----|---------:|----------:|
| Overview | ✅ | — | — |
| Package Constants | ✅ | tile_t enum, EP table | — |
| Top-Level Ports | ✅ | — | — |
| Module Hierarchy | ✅ | — | — |
| Compute Tile | Partial | L1, DEST/SRCB | — |
| Dispatch | Partial | Instruction flow | — |
| NoC Fabric | ✅ | — | — |
| EDC | ✅ | Harvest bypass detail | — |
| Power Management | ✅ | Daisy-chain topology | — |
| Clock Architecture | ✅ | — | — |
| Reset Architecture | ✅ | — | — |
| SRAM Inventory | Partial | Instance types | Count/capacity |
| DFX | — | iJTAG/BIST | Scan topology |
| RTL Files | ✅ | — | — |

---

*Generated from RAG v9 pipeline (tt_20260221). Hybrid grounding applied.*
