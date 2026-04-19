# Trinity / N1B0 — Full Chip SRAM Memory List

**Date:** 2026-03-18
**Chip:** Trinity N1B0 (4×5 mesh, 20 tiles)
**RTL:** `/secure_data_from_tt/20250301/used_in_n1/`  ← N1B0 specific
**Baseline ref:** `/secure_data_from_tt/20260221/` ← Trinity 20260221 (Mimir L1 config, differs in L1 only)

> **Note on L1 count (Trinity baseline vs N1B0):**
> - N1B0: `tt_trin_l1_cfg.svh` → BANK_IN_SBANK=16 → 4×16×4=256 wrappers × 2 physical = **512 macros/tile**
> - Trinity 20260221: `tt_mimir_l1_cfg.svh` → BANK_IN_SBANK=4 → 4×4×4=64 wrappers × 2 physical = **128 macros/tile**
> All other entries below are common to both unless noted.

---

## Section A — Tensix Compute Tile (gen_tensix_neo[0..3][0..2], ×12 tiles)

| No | Root clock | Category | Count /tile | Size [KB] /tile | SRAM module (RTL wrapper → physical cell) | Instance name | Clock Path Brief |
|----|-----------|---------|------------|----------------|------------------------------------------|--------------|-----------------|
| 1 | i_ai_clk | **T6 L1 SRAM** (N1B0) | **512** | **3,312** | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` → `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_{high,low}` | `u_l1part/u_l1w2/u_l1_mem_wrap/sbank_mem[0..3].bank_mem[0..15].sub_bank_mem[0..3].msel768.u_sub_mwrap/{high,low}` | i_ai_clk → SMN → ai_clk_gated → DFX → postdfx_clk → u_l1_mem_wrap.i_clk |
| 1' | i_ai_clk | **T6 L1 SRAM** (baseline) | *(128)* | *(828)* | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` → `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_{high,low}` | `u_l1part/u_l1w2/u_l1_mem_wrap/sbank_mem[0..3].bank_mem[0..3].sub_bank_mem[0..3].msel768.u_sub_mwrap/{high,low}` | *(same)* |
| 2 | i_ai_clk | **TRISC I-Cache** | **16** | **72** | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` (thread 0,3 full) / `tt_mem_wrap_256x72_sp_wmask_trisc_icache` (thread 1,2 half) → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_512x72m2b1c1_wrapper` | `t6[0..3].neo.u_t6/instrn_engine_wrapper/u_ie_mwrap/icache[0..3].{full,half}.trisc_icache/...` | i_ai_clk → DFX → postdfx_clk → u_ie_mwrap.i_clk |
| 3 | i_ai_clk | **TRISC Local Memory** | **12** | **48** | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` (×2) / `tt_mem_wrap_1024x52_sp_wmask_trisc_local_memory` (×1) → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_512x52m2b1c1` / `1024x52...` | `t6[0..3].neo.u_t6/instrn_engine_wrapper/u_ie_mwrap/local_mem[0..2].u_local_mem/...` | i_ai_clk → DFX → postdfx_clk → u_ie_mwrap.i_clk |
| 4 | i_ai_clk | **TRISC Vec Local Memory** | **8** | **26** | `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory` (×2 per t6) → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x104m2b1c1` | `t6[0..3].neo.u_t6/instrn_engine_wrapper/u_ie_mwrap/local_mem_256x104[0..1].u_vec_mem/...` | i_ai_clk → DFX → postdfx_clk → u_ie_mwrap.i_clk |
| 5 | i_dm_clk | **Overlay L1 D-Cache Data** | **16** | **36** | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_128x144m2b1c1` | `overlay_noc_wrap/.../memory_wrapper/gen_l1_dcache_data[0..15].l1_dcache_data/mem_wrapper_parity_0/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 6 | i_dm_clk | **Overlay L1 D-Cache Tag** | **8** | **3** | `TTOverlayConfig_rockettile_dcache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_32x100m2b1c1` | `overlay_noc_wrap/.../memory_wrapper/gen_l1_dcache_tag[0..7].l1_dcache_tag/mem_wrapper_parity_0/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 7 | i_dm_clk | **Overlay L1 I-Cache Data** | **16** | **34** | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `overlay_noc_wrap/.../memory_wrapper/gen_l1_icache_data[0..15].l1_icache_data/mem_wrapper_parity_0/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 8 | i_dm_clk | **Overlay L1 I-Cache Tag** | **8** | **17** | `TTOverlayConfig_rockettile_icache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `overlay_noc_wrap/.../memory_wrapper/gen_l1_icache_tag[0..7].l1_icache_tag/mem_wrapper_parity_0/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 9 | i_dm_clk | **Overlay L2 Banks** | **32** | **136** | `TTOverlayConfig_cc_banks_0_ext` (16 RTL wrappers × 2 physical 128b-half) → `u_ln05lpe_a00_mc_rf1r_hsr_lvt_256x136m2b1c1` | `overlay_noc_wrap/.../memory_wrapper/gen_l2_banks[0..15].l2_banks/mem_wrapper_parity_0/.../_wrapper_0` | i_dm_clk → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 10 | i_dm_clk | **Overlay L2 Directory** | **4** | **5** | `TTOverlayConfig_cc_dir_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_64x160m2b1c1` | `overlay_noc_wrap/.../memory_wrapper/gen_l2_dir[0..3].l2_dir/mem_wrapper_parity_0/...` | i_dm_clk → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 11 | i_noc_clk | **NOC Router VC Buffers** (N/E/S/W ×4 ports, 17 cells/port) | **68** | **153** | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` → `u_rf_wp_hsc_lvt_64x128m1fb1wm0_{0..16}` | `overlay_noc_wrap/.../noc_niu_router_inst/has_{east,north,south,west}_router_vc_buf.router_vc_buf.router_vc_bu` | i_noc_clk → postdfx_aon_clk → router.i_clk |
| 12 | i_noc_clk | **NOC NIU VC Buffer** (1 NIU port, 17 cells) | **17** | **38** | `tt_mem_wrap_72x2048_2p_nomask_router_input_port` → `u_rf_wp_hsc_lvt_72x128m2fb2wm0_{0..16}` | `f_64.mem_wrap_64x2048_2p_.../...` | i_noc_clk → postdfx_aon_clk → noc_niu_router.i_clk |
| 13 | i_noc_clk | **NOC Tables** (EP/ROCC/Routing) | **13** | **29** | `mem_wrap_1024x12_2p_noc_endpoint_translation` + `mem_wrap_32x1024_2p_noc_routing_translation` + ROCC buf → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `overlay_noc_wrap/.../noc_niu_router_inst/has_ep_table_mem/.../has_rocc_mem/.../` | i_noc_clk → postdfx_aon_clk → noc_niu_router.i_clk |
| — | — | **SUM / Tensix tile** | **730** | **~3,729** | | | |

> **N1B0 row 1:** 512 macros (4 sbank × 16 bank × 4 sub × 2 physical). Trinity baseline row 1': 128 macros (4×4×4×2).
> **Rows 3+4** (TRISC Local/Vec Mem) counted separately from screenshot's combined row 9 (20 total = 12+8).
> **Rows 11+12+13** = 68+17+13 = 98 NoC macros matching screenshot row 10-12 totals.

---

## Section B — Dispatch Tiles (gen_dispatch_{e/w}, ×2 tiles)

> Dispatch has no T6 cores → no TRISC memories. Overlay CPU present (DISPATCH_INST=1). Dispatch-specific L1 (`tt_disp_eng_l1_cfg.svh`: SBANK_CNT=4, BANK_IN_SBANK=4, SUB_BANK_CNT=4 = 64 wrappers × 2 physical).

| No | Root clock | Category | Count /tile | Size [KB] /tile | SRAM module (RTL wrapper → physical cell) | Instance name | Clock Path Brief |
|----|-----------|---------|------------|----------------|------------------------------------------|--------------|-----------------|
| 1 | i_ai_clk | **Dispatch L1 SRAM** | **128** | **828** | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` (dispatch variant) → `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_{high,low}` | `disp_eng_l1_partition_inst/tt_t6_l1_dispatch/u_l1w2/u_l1_mem_wrap/sbank_mem[0..3].bank_mem[0..3].sub_bank_mem[0..3].u_sub_mwrap/{high,low}` | i_noc_clk → postdfx_nocclk → tt_t6_l1_dispatch.i_clk (note: dispatch L1 on noc_clk domain) |
| 2 | i_dm_clk | **Overlay L1 D-Cache Data** | **16** | **36** | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_128x144m2b1c1` | `overlay_noc_wrap_inst/.../disp_eng_overlay_wrapper/overlay_wrapper/memory_wrapper/gen_l1_dcache_data[0..15].l1_dcache_data/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 3 | i_dm_clk | **Overlay L1 D-Cache Tag** | **8** | **3** | `TTOverlayConfig_rockettile_dcache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_32x100m2b1c1` | `…/memory_wrapper/gen_l1_dcache_tag[0..7].l1_dcache_tag/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 4 | i_dm_clk | **Overlay L1 I-Cache Data** | **16** | **34** | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `…/memory_wrapper/gen_l1_icache_data[0..15].l1_icache_data/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 5 | i_dm_clk | **Overlay L1 I-Cache Tag** | **8** | **17** | `TTOverlayConfig_rockettile_icache_tag_array_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1` | `…/memory_wrapper/gen_l1_icache_tag[0..7].l1_icache_tag/...` | i_dm_clk → core_clk_gate → aon_core_clk → memory_wrapper.RW0_clk |
| 6 | i_dm_clk | **Overlay L2 Banks** | **32** | **136** | `TTOverlayConfig_cc_banks_0_ext` (16 × 2 physical) → `u_ln05lpe_a00_mc_rf1r_hsr_lvt_256x136m2b1c1` | `…/memory_wrapper/gen_l2_banks[0..15].l2_banks/.../_wrapper_0` | i_dm_clk → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 7 | i_dm_clk | **Overlay L2 Directory** | **4** | **5** | `TTOverlayConfig_cc_dir_ext` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_64x160m2b1c1` | `…/memory_wrapper/gen_l2_dir[0..3].l2_dir/...` | i_dm_clk → uncore_clk_gate → aon_uncore_clk → memory_wrapper.RW0_clk |
| 8 | i_noc_clk | **Dispatch ATT EP Table** | **4** | **6** | `tt_mem_wrap_1024x12_2p_nomask_noc_endpoint_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `overlay_noc_wrap_inst/.../disp_eng_noc_niu_router_inst/has_ep_table_mem/...` | i_noc_clk → disp_eng_noc_niu_router.i_clk |
| 9 | i_noc_clk | **Dispatch ATT Routing Table** | **8** | **32** | `tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `overlay_noc_wrap_inst/.../disp_eng_noc_niu_router_inst/has_rocc_mem/...` | i_noc_clk → disp_eng_noc_niu_router.i_clk |
| 10 | i_noc_clk | **Context Switch SRAMs** | **2** | **4** | `tt_mem_wrap_32x1024_sp_nomask_overlay_context_switch` + `tt_mem_wrap_8x1024_sp_nomask_overlay_context_switch` | `…/overlay_wrapper/memory_wrapper/gen_cs_32x1024.mem_wrap_32x1024_*` / `gen_cs_8x1024.mem_wrap_8x1024_*` | i_dm_clk → core_clk_gate → aon_core_clk → cs_mem_intf.clk |
| — | — | **SUM / Dispatch tile** | **226** | **~1,101** | | | |

> Note: Total of 226 per tile is close to screenshot estimate of 229; difference of 3 may reflect additional small SRAM instances inside the dispatch L1 or overlay that are not listed individually. Context Switch SRAMs (row 10) are also present in Tensix tile but omitted from Tensix table above.

---

## Section C — NoC Router Tile (gen_router[1..2][3], ×2 tiles — Trinity baseline only)

> Standalone router tile: NoC VC buffers only. No T6, no Overlay CPU, no L1.
> **N1B0:** This tile is EMPTY (`gen_router` block has no sub-module). Router logic is embedded inside `trinity_noc2axi_router_ne/nw_opt`.

| No | Root clock | Category | Count /tile | Size [KB] /tile | SRAM module (RTL wrapper → physical cell) | Instance name | Clock Path Brief |
|----|-----------|---------|------------|----------------|------------------------------------------|--------------|-----------------|
| 1 | i_noc_clk | **Router North VC Input FIFO** (256-deep) | **16** | **64** | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` → `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x128m4b1c1` ×16 | `trinity_router/tt_router/mem_wrap_*_router_input_north/{0..15}` | i_noc_clk → postdfx_nocclk → tt_router.i_wr_clk/i_rd_clk |
| 2 | i_noc_clk | **Router East VC Input FIFO** (256-deep) | **16** | **64** | same | `trinity_router/tt_router/mem_wrap_*_router_input_east/{0..15}` | i_noc_clk → postdfx_nocclk → tt_router |
| 3 | i_noc_clk | **Router South VC Input FIFO** (256-deep) | **16** | **64** | same | `trinity_router/tt_router/mem_wrap_*_router_input_south/{0..15}` | i_noc_clk → postdfx_nocclk → tt_router |
| 4 | i_noc_clk | **Router West VC Input FIFO** (256-deep) | **16** | **64** | same | `trinity_router/tt_router/mem_wrap_*_router_input_west/{0..15}` | i_noc_clk → postdfx_nocclk → tt_router |
| 5 | i_noc_clk | **Router ATT EP Table** | **4** | **6** | `mem_wrap_1024x12_2p_nomask_noc_endpoint_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `trinity_router/tt_router/router.has_ep_table_mem/...` | i_noc_clk → router.i_clk |
| 6 | i_noc_clk | **Router ATT Routing Table** | **8** | **32** | `mem_wrap_32x1024_2p_nomask_noc_routing_translation` → `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `trinity_router/tt_router/router.has_rocc_mem/...` | i_noc_clk → router.i_clk |
| 7 | i_noc_clk | **Router Scheduler / ROCC** | **~8** | **~16** | `tt_mem_wrap_64x512_2p_nomask_noc_rocc_cmd_buf` → `u_rf_2p_hsc_lvt_*` | `trinity_router/tt_router/router.*_cmd_buf/...` | i_noc_clk → router.i_clk |
| — | — | **SUM / Router tile** | **~84** | **~310** | | | |

> Row 1-4: Each 256×2048b VC FIFO → 2048/128 = 16 physical cells wide at 256-row depth.
> Total ~84/tile vs screenshot summary 98/tile — rows 5-7 may include additional scheduler SRAMs to reach 98. Use screenshot's 98 as authoritative.

---

## Section D — NOC2AXI Tiles (N1B0 specific)

### D-1: NOC2AXI Middle Columns (trinity_noc2axi_router_ne/nw_opt, ×2 tiles — spans Y=4+Y=3)

> Covers AXI bridge (Y=4) + embedded router (Y=3). Has 3 NoC input ports (E/S/W for NE; E/S for NW corner cases vary).

| No | Root clock | Category | Count /tile | SRAM module | Instance name | Description |
|----|-----------|---------|------------|-------------|--------------|-------------|
| 1 | i_noc_clk | **Router VC N** | 17 | `u_rf_wp_hsc_lvt_64x128m1fb1wm0_{0..16}` | `.../router_vc_buf.north/...` | Router North VC (64-deep) |
| 2 | i_noc_clk | **Router VC E** | 17 | same | `.../router_vc_buf.east/...` | Router East VC |
| 3 | i_noc_clk | **Router VC S** | 17 | same | `.../router_vc_buf.south/...` | Router South VC |
| 4 | i_noc_clk | **Router VC W** | 17 | same | `.../router_vc_buf.west/...` | Router West VC |
| 5 | i_noc_clk | **NOC Tables** | ~13 | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `.../has_ep_table_mem/.../has_rocc_mem/...` | EP/Routing/ROCC tables |
| 6 | i_noc_clk / i_axi_clk | **AXI FIFOs** | ~26 | Various | `.../noc2axi_slv_rddata/noc2axi_slv_wrdata/...` | AXI rd/wr data FIFOs |
| — | | **SUM / tile** | **~107** | | | |

### D-2: NOC2AXI Corner Columns (trinity_noc2axi_ne/nw_opt, X=0 and X=3 at Y=4, ×2 tiles)

> Has 2 NoC input ports only (E/S for NE_OPT, S/W for NW_OPT). No embedded router.

| No | Root clock | Category | Count /tile | SRAM module | Instance name | Description |
|----|-----------|---------|------------|-------------|--------------|-------------|
| 1 | i_noc_clk | **Router VC E** | 17 | `u_rf_wp_hsc_lvt_64x128m1fb1wm0_{0..16}` | `.../router_vc_buf.east/...` | East VC (NE_OPT) or West VC (NW_OPT) |
| 2 | i_noc_clk | **Router VC S** | 17 | same | `.../router_vc_buf.south/...` | South VC |
| 3 | i_noc_clk | **NOC Tables** | ~13 | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | `.../has_ep_table_mem/.../has_rocc_mem/...` | EP/Routing/ROCC tables |
| 4 | i_noc_clk / i_axi_clk | **AXI FIFOs** | ~43 | Various | `.../noc2axi_slv_rddata/noc2axi_slv_wrdata/...` | AXI rd/wr data FIFOs (larger, no router sharing) |
| — | | **SUM / tile** | **~90** | | | |

---

## Section E — Total Summary

### E-1: Per-Tile SRAM Count

| Tile Type | Module | # of Tiles | SRAM Macros/tile | Total Macros | Note |
|-----------|--------|-----------|-----------------|-------------|------|
| **Tensix** | `tt_tensix_with_l1` | **12** | **730** | **8,760** | N1B0 L1=512; baseline=326 |
| **Dispatch** | `tt_dispatch_top_{east/west}` | **2** | **~229** | **~458** | No T6 cores |
| **NOC2AXI Router** (middle, N1B0) | `trinity_noc2axi_router_ne/nw_opt` | **2** | **~107** | **~214** | N1B0: combined Y=4+Y=3 |
| **NOC2AXI Corner** | `trinity_noc2axi_ne/nw_opt` | **2** | **~90** | **~180** | Corner tiles X=0,3 |
| **Router** (baseline only) | `trinity_router` | **2** | **~98** | **~196** | Trinity baseline: standalone Y=3 |
| **Total / chip (N1B0)** | — | **20** | — | **≈ 9,748** | N1B0: no standalone router (empty) |
| **Total / chip (baseline)** | — | **20** | — | **≈ 6,136** | Baseline: 12×326+2×229+2×98+... |

### E-2: SRAM Count by Clock Domain (Tensix tile × 12)

| Clock domain | Source | Macros/tile | Total (×12) | Key memories |
|-------------|--------|-------------|------------|-------------|
| **i_ai_clk** | `i_ai_clk` | 548 (N1B0) / 164 (baseline) | 6,576 / 1,968 | T6 L1 + TRISC I-Cache + TRISC Local/Vec Mem |
| **i_dm_clk** | `i_dm_clk` | 84 | 1,008 | Overlay L1 D/I Cache + L2 Banks/Dir |
| **i_noc_clk** | `i_noc_clk` | 98 | 1,176 | NIU/Router VC FIFOs + ATT Tables |
| **Total/tile** | — | **730** (N1B0) | **8,760** | |

### E-3: Memory by Type (Chip-wide, N1B0, Tensix tiles only)

| Type | Module | Clock | Physical cell | Total macros |
|------|--------|-------|--------------|-------------|
| T6 L1 SRAM (N1B0) | `tt_mem_wrap_1024x128_*` | i_ai_clk | `u_ln05lpe_*_768x69m4b1c1_{high,low}` | **6,144** |
| TRISC I-Cache | `tt_mem_wrap_512/256x72_sp_wmask_*` | i_ai_clk | `u_ln05lpe_*_512x72m2b1c1` | **192** |
| TRISC Local Memory | `tt_mem_wrap_512/1024x52_sp_wmask_*` | i_ai_clk | `u_ln05lpe_*_512/1024x52m2b1c1` | **144** |
| TRISC Vec Memory | `tt_mem_wrap_256x104_sp_wmask_*` | i_ai_clk | `u_ln05lpe_*_256x104m2b1c1` | **96** |
| Overlay L1 D$ Data | `TTOverlayConfig_*_dcache_data_*` | i_dm_clk | `u_ln05lpe_*_128x144m2b1c1` | **192** |
| Overlay L1 D$ Tag | `TTOverlayConfig_*_dcache_tag_*` | i_dm_clk | `u_ln05lpe_*_32x100m2b1c1` | **96** |
| Overlay L1 I$ Data | `TTOverlayConfig_*_icache_data_*` | i_dm_clk | `u_ln05lpe_*_256x68m2b1c1` | **192** |
| Overlay L1 I$ Tag | `TTOverlayConfig_*_icache_tag_*` | i_dm_clk | `u_ln05lpe_*_256x68m2b1c1` | **96** |
| Overlay L2 Banks | `TTOverlayConfig_cc_banks_0_ext` | i_dm_clk | `u_ln05lpe_*_256x136m2b1c1` | **384** |
| Overlay L2 Dir | `TTOverlayConfig_cc_dir_ext` | i_dm_clk | `u_ln05lpe_*_64x160m2b1c1` | **48** |
| NIU/Router VC (64-row) | `tt_mem_wrap_64x2048_2p_*` | i_noc_clk | `u_rf_wp_hsc_lvt_64x128m1fb1wm0` | **816** |
| NIU VC (72-row) | `tt_mem_wrap_72x2048_2p_*` | i_noc_clk | `u_rf_wp_hsc_lvt_72x128m2fb2wm0` | **204** |
| NOC EP/Routing/ROCC | `mem_wrap_1024x12/32x1024_2p_*` | i_noc_clk | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` | **156** |

---

## Verification Notes

| Item | Status | Notes |
|------|--------|-------|
| L1 SRAM 512/tile | ✅ Correct (N1B0) | `tt_trin_l1_cfg.svh`: 4×16×4×2=512; Trinity baseline 128/tile |
| TRISC ICache 16/tile | ✅ Correct | 4 t6 × 4 threads = 16 |
| TRISC Local Mem 20/tile | ✅ Correct | 4 t6 × 5 types = 20 (= rows 3+4 above) |
| L1 D/I Cache 16+8/tile | ✅ Correct | From `tt_overlay_pkg.sv` |
| L2 Banks 32/tile | ✅ Correct | 16 RTL wrappers × 2 physical (256b → 2×128b confirmed) |
| L2 Dir 4/tile | ✅ Correct | From `tt_overlay_pkg.sv` |
| NoC VC 68+17+13=98 | ✅ Plausible | 4 cardinal ports × 17 = 68; NIU port = 17; tables = 13 |
| Per-tile total = 730 | ✅ Verified | 512+16+20+16+8+16+8+32+4+68+17+13 = 730 |
| Summary total 9748 | ⚠️ Check | 12×730+2×229+2×107+2×90+2×98 = 9808 ≠ 9748; delta=60; suggest Router/tile = 68 (not 98) or re-verify one tile's count |

---

*2026-03-18 — Trinity N1B0 SRAM inventory from RTL analysis + physical cell mapping*
