# N1B0 — Full Chip SRAM Memory List

**Date:** 2026-03-18
**Chip:** N1B0 (4×5 mesh, 20 tiles)
**RTL:** `/secure_data_from_tt/20250301/used_in_n1/`

> **N1B0 grid (vs Trinity baseline):**
> - No standalone Router tiles — `gen_router[1..2][3]` blocks are EMPTY in N1B0
> - Middle Y=4 columns (X=1,2) use combined `trinity_noc2axi_router_ne/nw_opt` spanning Y=4+Y=3
> - L1 config: `tt_trin_l1_cfg.svh` → BANK_IN_SBANK=16 → 4×16×4×2 = **512 physical macros/Tensix tile**
> - Clock: per-column `i_ai_clk[4]`, `i_dm_clk[4]` arrays (vs single shared in baseline)

---

## Section A — Tensix Compute Tile (`tt_tensix_with_l1`, ×12 tiles, X=0..3, Y=0..2)

| No | Root clock | Category | Count /tile | Size [KB] /tile | SRAM module (RTL wrapper → physical cell) | Instance name | Clock Path Brief |
|----|-----------|---------|------------|----------------|------------------------------------------|--------------|-----------------|
| 1 | i_ai_clk[x] | **T6 L1 SRAM** | **512** | **3,312** | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` → `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_{high,low}` | `u_l1part/u_l1w2/u_l1_mem_wrap/sbank_mem[0..3].bank_mem[0..15].sub_bank_mem[0..3].msel768.u_sub_mwrap/{high,low}` | i_ai_clk[x] → clock_routing → SMN → ai_clk_gated → DFX → postdfx_clk → u_l1_mem_wrap.i_clk |
| 2 | i_ai_clk[x] | **TRISC I-Cache** (4 T6, 4 threads each) | **16** | **72** | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` (thread 0,3) / `tt_mem_wrap_256x72_sp_wmask_trisc_icache` (thread 1,2) → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_512x72m2b1c1_wrapper` | `t6[0..3].neo.u_t6/instrn_engine_wrapper/u_ie_mwrap/icache[0..3].{full,half}.trisc_icache/...` | i_ai_clk[x] → clock_routing → DFX → postdfx_clk → u_ie_mwrap.i_clk |
| 3 | i_ai_clk[x] | **TRISC Local Memory** (3 banks/T6 × 4 T6) | **12** | **48** | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` (×2) / `tt_mem_wrap_1024x52_sp_wmask_trisc_local_memory` (×1) → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_512x52m2b1c1` / `1024x52...` | `t6[0..3].neo.u_t6/instrn_engine_wrapper/u_ie_mwrap/local_mem[0..2].u_local_mem/...` | i_ai_clk[x] → clock_routing → DFX → postdfx_clk → u_ie_mwrap.i_clk |
| 4 | i_ai_clk[x] | **TRISC Vec Local Memory** (2 banks/T6 × 4 T6) | **8** | **26** | `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory` (×2 per t6) → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x104m2b1c1` | `t6[0..3].neo.u_t6/instrn_engine_wrapper/u_ie_mwrap/local_mem_256x104[0..1].u_vec_mem/...` | i_ai_clk[x] → clock_routing → DFX → postdfx_clk → u_ie_mwrap.i_clk |
| 5 | i_dm_clk[x] | **Overlay L1 D-Cache Data** | **16** | **36** | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_128x144m2b1c1` | `overlay_noc_wrap/.../memory_wrapper/gen_l1_dcache_data[0..15].l1_dcache_data/mem_wrapper_parity_0/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 6 | i_dm_clk[x] | **Overlay L1 D-Cache Tag** | **8** | **3** | `TTOverlayConfig_rockettile_dcache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_32x100m2b1c1` | `.../memory_wrapper/gen_l1_dcache_tag[0..7].l1_dcache_tag/mem_wrapper_parity_0/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 7 | i_dm_clk[x] | **Overlay L1 I-Cache Data** | **16** | **34** | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `.../memory_wrapper/gen_l1_icache_data[0..15].l1_icache_data/mem_wrapper_parity_0/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 8 | i_dm_clk[x] | **Overlay L1 I-Cache Tag** | **8** | **17** | `TTOverlayConfig_rockettile_icache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `.../memory_wrapper/gen_l1_icache_tag[0..7].l1_icache_tag/mem_wrapper_parity_0/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 9 | i_dm_clk[x] | **Overlay L2 Banks** (16 RTL wrappers × 2 physical) | **32** | **136** | `TTOverlayConfig_cc_banks_0_ext` → `u_ln05lpe_a00_mc_rf1r_hsr_lvt_256x136m2b1c1` | `.../memory_wrapper/gen_l2_banks[0..15].l2_banks/mem_wrapper_parity_0/.../_wrapper_0` | i_dm_clk[x] → clock_routing → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 10 | i_dm_clk[x] | **Overlay L2 Directory** | **4** | **5** | `TTOverlayConfig_cc_dir_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_64x160m2b1c1` | `.../memory_wrapper/gen_l2_dir[0..3].l2_dir/mem_wrapper_parity_0/...` | i_dm_clk[x] → clock_routing → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 11 | i_noc_clk | **NOC Router VC Buffers** (N/E/S/W × 4 ports, 17 cells/port) | **68** | **153** | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` → `u_rf_wp_hsc_lvt_64x128m1fb1wm0_{0..16}` | `overlay_noc_wrap/.../noc_niu_router_inst/has_{north,east,south,west}_router_vc_buf.router_vc_buf/...` | i_noc_clk → postdfx_aon_clk → noc_niu_router.i_clk |
| 12 | i_noc_clk | **NOC NIU VC Buffer** (1 NIU port, 17 cells) | **17** | **38** | `tt_mem_wrap_72x2048_2p_nomask_router_input_port` → `u_rf_wp_hsc_lvt_72x128m2fb2wm0_{0..16}` | `overlay_noc_wrap/.../noc_niu_router_inst/niu_vc_buf/...` | i_noc_clk → postdfx_aon_clk → noc_niu_router.i_clk |
| 13 | i_noc_clk | **NOC Tables** (EP + Routing + ROCC) | **13** | **29** | `mem_wrap_1024x12_2p_noc_endpoint_translation` + `mem_wrap_32x1024_2p_noc_routing_translation` + ROCC buf → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `overlay_noc_wrap/.../noc_niu_router_inst/has_ep_table_mem/.../has_rocc_mem/.../` | i_noc_clk → postdfx_aon_clk → noc_niu_router.i_clk |
| — | — | **SUM / Tensix tile** | **730** | **~3,909** | | | |

> Row 1: N1B0 L1 = 4 sbank × 16 bank × 4 sub-bank × 2 physical = **512** (vs 128 in Trinity baseline with BANK_IN_SBANK=4).
> Rows 11+12+13 = 68+17+13 = 98 NoC macros.
> Rows 2+3+4 = 16+12+8 = 36 TRISC macros per tile.

---

## Section B — Dispatch Tiles (`tt_dispatch_top_east/west`, ×2 tiles, X=0/3, Y=3)

> No T6 cores → no TRISC memories. Has Overlay CPU (DISPATCH_INST=1).
> Dispatch-specific L1: `tt_disp_eng_l1_cfg.svh` → SBANK_CNT=4, BANK_IN_SBANK=4, SUB_BANK_CNT=4 = 64 wrappers × 2 physical = 128 macros.

| No | Root clock | Category | Count /tile | Size [KB] /tile | SRAM module (RTL wrapper → physical cell) | Instance name | Clock Path Brief |
|----|-----------|---------|------------|----------------|------------------------------------------|--------------|-----------------|
| 1 | i_noc_clk | **Dispatch L1 SRAM** (64 wrappers × 2 physical) | **128** | **828** | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` (dispatch cfg) → `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_{high,low}` | `disp_eng_l1_partition_inst/tt_t6_l1_dispatch/u_l1w2/u_l1_mem_wrap/sbank_mem[0..3].bank_mem[0..3].sub_bank_mem[0..3].u_sub_mwrap/{high,low}` | i_noc_clk → postdfx_nocclk → tt_t6_l1_dispatch.i_clk (noc_clk domain) |
| 2 | i_dm_clk[x] | **Overlay L1 D-Cache Data** | **16** | **36** | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_128x144m2b1c1` | `overlay_noc_wrap_inst/.../disp_eng_overlay_wrapper/overlay_wrapper/memory_wrapper/gen_l1_dcache_data[0..15].l1_dcache_data/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 3 | i_dm_clk[x] | **Overlay L1 D-Cache Tag** | **8** | **3** | `TTOverlayConfig_rockettile_dcache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_32x100m2b1c1` | `.../memory_wrapper/gen_l1_dcache_tag[0..7].l1_dcache_tag/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 4 | i_dm_clk[x] | **Overlay L1 I-Cache Data** | **16** | **34** | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `.../memory_wrapper/gen_l1_icache_data[0..15].l1_icache_data/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 5 | i_dm_clk[x] | **Overlay L1 I-Cache Tag** | **8** | **17** | `TTOverlayConfig_rockettile_icache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `.../memory_wrapper/gen_l1_icache_tag[0..7].l1_icache_tag/...` | i_dm_clk[x] → clock_routing → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 6 | i_dm_clk[x] | **Overlay L2 Banks** (16 RTL × 2 physical) | **32** | **136** | `TTOverlayConfig_cc_banks_0_ext` → `u_ln05lpe_a00_mc_rf1r_hsr_lvt_256x136m2b1c1` | `.../memory_wrapper/gen_l2_banks[0..15].l2_banks/.../_wrapper_0` | i_dm_clk[x] → clock_routing → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 7 | i_dm_clk[x] | **Overlay L2 Directory** | **4** | **5** | `TTOverlayConfig_cc_dir_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_64x160m2b1c1` | `.../memory_wrapper/gen_l2_dir[0..3].l2_dir/...` | i_dm_clk[x] → clock_routing → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 8 | i_noc_clk | **Dispatch ATT EP Table** | **4** | **6** | `tt_mem_wrap_1024x12_2p_nomask_noc_endpoint_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `overlay_noc_wrap_inst/.../disp_eng_noc_niu_router_inst/has_ep_table_mem/...` | i_noc_clk → disp_eng_noc_niu_router.i_clk |
| 9 | i_noc_clk | **Dispatch ATT Routing Table** | **8** | **32** | `tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `overlay_noc_wrap_inst/.../disp_eng_noc_niu_router_inst/has_rocc_mem/...` | i_noc_clk → disp_eng_noc_niu_router.i_clk |
| 10 | i_dm_clk[x] | **Context Switch SRAMs** | **2** | **4** | `tt_mem_wrap_32x1024_sp_nomask_overlay_context_switch` + `tt_mem_wrap_8x1024_sp_nomask_overlay_context_switch` | `.../overlay_wrapper/memory_wrapper/gen_cs_32x1024.mem_wrap_32x1024_*` / `gen_cs_8x1024.mem_wrap_8x1024_*` | i_dm_clk[x] → core_clk_gate → aon_core_clk → cs_mem_intf.clk |
| — | — | **SUM / Dispatch tile** | **226** | **~1,101** | | | |

---

## Section C — NOC2AXI Router (Middle) (`trinity_noc2axi_router_ne/nw_opt`, ×2 tiles, X=1/2, spanning Y=4+Y=3)

> N1B0 exclusive. Combines AXI bridge (Y=4) + embedded router (Y=3) in one module.
> Has 4 cardinal router VC ports (N/E/S/W) plus AXI FIFOs.

| No | Root clock | Category | Count /tile | Size [KB] /tile | SRAM module (RTL wrapper → physical cell) | Instance name | Clock Path Brief |
|----|-----------|---------|------------|----------------|------------------------------------------|--------------|-----------------|
| 1 | i_noc_clk | **Router VC North** (64-deep, 17 cells) | **17** | **17** | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` → `u_rf_wp_hsc_lvt_64x128m1fb1wm0_{0..16}` | `trinity_noc2axi_router_{ne,nw}_opt/.../tt_noc2axi/router/has_north_router_vc_buf.router_vc_buf/...` | i_noc_clk → postdfx_nocclk → tt_router.i_clk |
| 2 | i_noc_clk | **Router VC East** (64-deep, 17 cells) | **17** | **17** | same | `.../has_east_router_vc_buf.router_vc_buf/...` | i_noc_clk → postdfx_nocclk → tt_router.i_clk |
| 3 | i_noc_clk | **Router VC South** (64-deep, 17 cells) | **17** | **17** | same | `.../has_south_router_vc_buf.router_vc_buf/...` | i_noc_clk → postdfx_nocclk → tt_router.i_clk |
| 4 | i_noc_clk | **Router VC West** (64-deep, 17 cells) | **17** | **17** | same | `.../has_west_router_vc_buf.router_vc_buf/...` | i_noc_clk → postdfx_nocclk → tt_router.i_clk |
| 5 | i_noc_clk | **Router ATT EP Table** | **4** | **6** | `mem_wrap_1024x12_2p_nomask_noc_endpoint_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `.../tt_noc2axi/router/has_ep_table_mem/...` | i_noc_clk → tt_noc2axi.i_clk |
| 6 | i_noc_clk | **Router ATT Routing Table + ROCC** | **9** | **23** | `mem_wrap_32x1024_2p_nomask_noc_routing_translation` + ROCC cmd buf → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `.../tt_noc2axi/router/has_rocc_mem/.../has_rocc_cmd_buf/...` | i_noc_clk → tt_noc2axi.i_clk |
| 7 | i_noc_clk / i_axi_clk | **AXI Data FIFOs** (rd/wr data, rd/wr cmd) | **~26** | **~104** | Various `tt_mem_wrap_*_noc2axi_*` / `tt_mem_wrap_*_axi2noc_*` → `u_rf_wp_hsc_lvt_*` | `.../tt_noc2axi/noc2axi_slv_rddata_fifo/...` / `.../noc2axi_slv_wrdata_fifo/...` | i_noc_clk / i_axi_clk → respective FIFOs |
| — | — | **SUM / tile** | **~107** | **~201** | | | |

---

## Section D — NOC2AXI Corner (`trinity_noc2axi_ne/nw_opt`, ×2 tiles, X=0/3, Y=4)

> Corner tiles: AXI bridge only, no embedded router. Fewer VC ports (E+S for NE_OPT; S+W for NW_OPT).
> AXI FIFOs are larger here (no router resource sharing).

| No | Root clock | Category | Count /tile | Size [KB] /tile | SRAM module (RTL wrapper → physical cell) | Instance name | Clock Path Brief |
|----|-----------|---------|------------|----------------|------------------------------------------|--------------|-----------------|
| 1 | i_noc_clk | **NIU VC East** (64-deep, 17 cells) | **17** | **17** | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` → `u_rf_wp_hsc_lvt_64x128m1fb1wm0_{0..16}` | `trinity_noc2axi_{ne,nw}_opt/.../tt_noc2axi/has_east_vc_buf.vc_buf/...` | i_noc_clk → postdfx_nocclk → tt_noc2axi.i_clk |
| 2 | i_noc_clk | **NIU VC South** (64-deep, 17 cells) | **17** | **17** | same | `.../tt_noc2axi/has_south_vc_buf.vc_buf/...` | i_noc_clk → postdfx_nocclk → tt_noc2axi.i_clk |
| 3 | i_noc_clk | **NOC EP Table** | **4** | **6** | `mem_wrap_1024x12_2p_nomask_noc_endpoint_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `.../tt_noc2axi/has_ep_table_mem/...` | i_noc_clk → tt_noc2axi.i_clk |
| 4 | i_noc_clk | **NOC Routing Table + ROCC** | **9** | **23** | `mem_wrap_32x1024_2p_nomask_noc_routing_translation` + ROCC → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `.../tt_noc2axi/has_rocc_mem/.../has_rocc_cmd_buf/...` | i_noc_clk → tt_noc2axi.i_clk |
| 5 | i_noc_clk / i_axi_clk | **AXI Data FIFOs** (rd/wr data, rd/wr cmd) | **~43** | **~172** | Various `tt_mem_wrap_*_noc2axi_*` / `tt_mem_wrap_*_axi2noc_*` → `u_rf_wp_hsc_lvt_*` | `.../tt_noc2axi/noc2axi_slv_rddata_fifo/...` / `.../noc2axi_slv_wrdata_fifo/...` | i_noc_clk / i_axi_clk → respective FIFOs |
| — | — | **SUM / tile** | **~90** | **~235** | | | |

---

## Section E — N1B0 Chip Summary

### E-1: Per-Tile SRAM Count

| Tile Type | Module | # Tiles | Grid positions | SRAM Macros /tile | Total Macros | Note |
|-----------|--------|---------|---------------|------------------|-------------|------|
| **Tensix** | `tt_tensix_with_l1` | **12** | X=0..3, Y=0..2 | **730** | **8,760** | L1=512 (N1B0 `tt_trin_l1_cfg`); NoC=98 |
| **Dispatch** | `tt_dispatch_top_{east,west}` | **2** | X=0/3, Y=3 | **226** | **452** | Dispatch L1=128 (noc_clk); Overlay=84 |
| **NOC2AXI Router** (middle) | `trinity_noc2axi_router_{ne,nw}_opt` | **2** | X=1/2, Y=3+4 | **~107** | **~214** | Spans 2 rows; embedded router VC×4 |
| **NOC2AXI Corner** | `trinity_noc2axi_{ne,nw}_opt` | **2** | X=0/3, Y=4 | **~90** | **~180** | 2 VC ports; larger AXI FIFOs |
| **Router** (standalone) | `trinity_router` | **0** | — | — | **0** | N1B0: `gen_router[1..2][3]` is EMPTY |
| **Total / chip (N1B0)** | — | **18** (+2 empty) | — | — | **≈ 9,606** | |

### E-2: SRAM by Clock Domain (N1B0 chip-wide)

| Clock domain | Root port | Macros/Tensix | ×12 Tensix | ×2 Dispatch | ×2 NOC2AXI-R | ×2 NOC2AXI-C | **Chip total** |
|-------------|-----------|--------------|-----------|------------|-------------|-------------|--------------|
| **i_ai_clk[x]** | per-column | 548 | 6,576 | — | — | — | **6,576** |
| **i_dm_clk[x]** | per-column | 84 | 1,008 | 168 | — | — | **1,176** |
| **i_noc_clk** | single | 98 | 1,176 | 58 (L1=128 noc) | ~107 | ~90 | **≈ 1,559** |
| **i_axi_clk** | single | — | — | — | (included above) | (included above) | *in NOC2AXI* |
| **Total** | | **730** | **8,760** | **~226** | **~107** | **~90** | **≈ 9,606** |

> Note: Dispatch L1 (128 macros, row 1 in Section B) runs on `i_noc_clk` — counted under i_noc_clk above.

### E-3: SRAM by Category (N1B0 chip-wide)

| Category | Clock | Physical cell | /tile | × tiles | **Total** |
|---------|-------|--------------|-------|---------|-----------|
| T6 L1 SRAM | i_ai_clk[x] | `u_ln05lpe_*_768x69m4b1c1_{high,low}` | 512 | ×12 Tensix | **6,144** |
| TRISC I-Cache | i_ai_clk[x] | `u_ln05lpe_*_512x72m2b1c1` | 16 | ×12 | **192** |
| TRISC Local Memory | i_ai_clk[x] | `u_ln05lpe_*_512/1024x52m2b1c1` | 12 | ×12 | **144** |
| TRISC Vec Memory | i_ai_clk[x] | `u_ln05lpe_*_256x104m2b1c1` | 8 | ×12 | **96** |
| Overlay L1 D$ Data | i_dm_clk[x] | `u_ln05lpe_*_128x144m2b1c1` | 16 | ×14 (Tensix+Disp) | **224** |
| Overlay L1 D$ Tag | i_dm_clk[x] | `u_ln05lpe_*_32x100m2b1c1` | 8 | ×14 | **112** |
| Overlay L1 I$ Data | i_dm_clk[x] | `u_ln05lpe_*_256x68m2b1c1` | 16 | ×14 | **224** |
| Overlay L1 I$ Tag | i_dm_clk[x] | `u_ln05lpe_*_256x68m2b1c1` | 8 | ×14 | **112** |
| Overlay L2 Banks | i_dm_clk[x] | `u_ln05lpe_*_256x136m2b1c1` | 32 | ×14 | **448** |
| Overlay L2 Dir | i_dm_clk[x] | `u_ln05lpe_*_64x160m2b1c1` | 4 | ×14 | **56** |
| Dispatch L1 SRAM | i_noc_clk | `u_ln05lpe_*_768x69m4b1c1_{high,low}` | 128 | ×2 Dispatch | **256** |
| Router VC (64-row, Tensix) | i_noc_clk | `u_rf_wp_hsc_lvt_64x128m1fb1wm0` | 68 | ×12 | **816** |
| NIU VC (72-row, Tensix) | i_noc_clk | `u_rf_wp_hsc_lvt_72x128m2fb2wm0` | 17 | ×12 | **204** |
| NOC Tables (Tensix) | i_noc_clk | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | 13 | ×12 | **156** |
| Router VC×4 (NOC2AXI-R) | i_noc_clk | `u_rf_wp_hsc_lvt_64x128m1fb1wm0` | 68 | ×2 | **136** |
| NOC Tables (NOC2AXI-R) | i_noc_clk | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | 13 | ×2 | **26** |
| AXI FIFOs (NOC2AXI-R) | i_noc_clk/i_axi_clk | `u_rf_wp_hsc_lvt_*` | ~26 | ×2 | **~52** |
| NIU VC×2 (NOC2AXI-C) | i_noc_clk | `u_rf_wp_hsc_lvt_64x128m1fb1wm0` | 34 | ×2 | **68** |
| NOC Tables (NOC2AXI-C) | i_noc_clk | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | 13 | ×2 | **26** |
| AXI FIFOs (NOC2AXI-C) | i_noc_clk/i_axi_clk | `u_rf_wp_hsc_lvt_*` | ~43 | ×2 | **~86** |
| **TOTAL** | | | | | **≈ 9,582** |

---

## Verification Notes

| Item | Status | Notes |
|------|--------|-------|
| N1B0 L1 = 512/Tensix | ✅ | `tt_trin_l1_cfg.svh`: BANK_IN_SBANK=16 → 4×16×4×2=512 |
| TRISC ICache = 16/Tensix | ✅ | 4 T6 × 4 threads = 16 |
| Overlay caches = 84/tile | ✅ | 16+8+16+8+32+4 = 84 (same for Tensix and Dispatch) |
| NoC VCs = 98/Tensix | ✅ | 68+17+13 = 98 (4 cardinal + 1 NIU + tables) |
| Tensix total = 730/tile | ✅ | 512+16+12+8+84+98 = 730 |
| Dispatch L1 on i_noc_clk | ✅ | Dispatch L1 (`tt_t6_l1_dispatch`) runs in noc_clk domain (not ai_clk) |
| Standalone Router tiles | ✅ | N1B0: `gen_router[1..2][3]` → empty; router embedded in `trinity_noc2axi_router_*_opt` |
| N1B0 clock per-column | ✅ | `i_ai_clk[SizeX]`, `i_dm_clk[SizeX]` arrays at trinity top; propagate via `clock_routing_in[x][4]` south |
| Chip total ≈ 9,606 | ⚠️ approx | Rows 7 (C) and 5 (D) are estimated from FIFO depth/width analysis; exact counts require RTL elaboration |

---

*2026-03-18 — N1B0 SRAM inventory (N1B0-specific table; no standalone Router section)*
