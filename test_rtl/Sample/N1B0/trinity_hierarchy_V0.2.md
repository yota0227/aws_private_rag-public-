# Trinity SoC — Module Hierarchy & Memory Inventory V0.2

**Date:** 2026-03-18
**RTL source:** `/secure_data_from_tt/20260221/` (Trinity, Mimir L1 config)
**N1B0 reference:** `/secure_data_from_tt/20250301/used_in_n1/` (Trinity N1B0, trin L1 config)
**Hierarchy CSV:** `trinity_hierarchy.csv` (411 rows, TAB-separated)

---

## 1. Grid Overview

| Dimension | Value |
|-----------|-------|
| Grid size | 4×5 (X=0..3, Y=0..4) |
| Tensix compute tiles | 12 (`gen_tensix_neo[0..3][0..2]`) |
| Dispatch tiles | 2 (E: X=0,Y=3 / W: X=3,Y=3) |
| Router tiles | 2 (`gen_router[1..2][3]`) |
| NIU tiles | 4 (Y=4, all X) |

**Top-level clock ports:**
- `i_ai_clk` — FPU, TRISC, SFPU, L1 SRAM, T6 logic
- `i_noc_clk` — NoC router, NIU, VC FIFOs
- `i_dm_clk` — Overlay CPU (core_clk + uncore_clk), SMN, EDC
- `i_ref_clk` — PLL reference

---

## 2. Instance Multiplicity Reference

| Symbol | Expansion | Count |
|--------|-----------|-------|
| `gen_tensix_neo[x][y]` | x=0..3, y=0..2 | 12 tiles |
| `t6[n]` | n=0..3 per tile | 4 per tile |
| `gen_gtile[g]` | g=0..1 per t6 | 2 per t6 |
| `gen_fp_cols[c]` | c=0..15 per gtile | 16 per gtile |
| `dest_reg_bank[b][col]` | b=0..1 (NUM_BANKS), col=0..3 (NUM_COLS) | 8 per fp_col |
| `gen_router[x][3]` | x=1..2 | 2 tiles |
| `gen_dispatch_e/w` | 2 instances | 2 tiles |

---

## 3. Memory Inventory by Subsystem

### 3.1 Tensix L1 SRAM — `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1`

**Config (tt_mimir_l1_cfg.svh):**

| Parameter | Value |
|-----------|-------|
| SBANK_CNT | 4 |
| BANK_IN_SBANK | 4 |
| SUB_BANK_CNT | 4 |
| Total macros per tile | **64** (4×4×4) |
| Macro size | 1024×128b = 16 KB |
| Total L1 capacity per tile | 1.0 MB (64 × 16 KB) |

**Hierarchy path (per tile):**
```
gen_tensix_neo[x][y].tt_tensix_with_l1.u_l1part.u_l1w2.u_l1_mem_wrap
  .gen_sbank[0..3].gen_bank[0..3].gen_sub_bank[0..3].u_sub_mwrap
```

| Scope | Clock | Count |
|-------|-------|-------|
| Per tile | i_ai_clk | 64 |
| **Total (×12 tiles)** | i_ai_clk | **768** |

---

### 3.2 DEST Register File — `tt_reg_bank` (Latch Array)

**Config (tt_gtile_dest.sv):**

| Parameter | Value |
|-----------|-------|
| NUM_BANKS | 2 (double-buffer ping/pong) |
| NUM_COLS | 4 |
| SETS (BANK_ROWS_32B) | 256 |
| Instance name | `dest_reg_bank[b][col]` — b=0..1, col=0..3 |
| Type | `tt_reg_bank` latch array (LATCH_ARRAY, NOT SRAM) |

**Hierarchy path (per fp_col):**
```
gen_tensix_neo[x][y].tt_tensix_with_l1
  .t6[n].neo.u_t6.gen_gtile[g].u_fpu_gtile.gen_fp_cols[c].mtile_and_dest
  .dest_slice.dest_reg_bank[b][col]
```

| Scope | Clock | Multiplier | Count |
|-------|-------|-----------|-------|
| Per fp_col | i_ai_clk | 2×4 = 8 | 8 |
| Per gtile (×16 fp_cols) | i_ai_clk | — | 128 |
| Per t6 (×2 gtiles) | i_ai_clk | — | 256 |
| Per tile (×4 t6) | i_ai_clk | — | 1,024 |
| **Total (×12 tiles)** | i_ai_clk | — | **12,288** |

> **Note:** `tt_reg_bank` is a latch-array-based register file — **not counted as SRAM macro**.

---

### 3.3 SRCA Register Slice — `tt_srca_reg_slice` (Latch Array)

**Hierarchy path:**
```
...gen_fp_cols[c].mtile_and_dest.u_fpu_mtile.u_srca_reg_slice
```

| Scope | Clock | Count |
|-------|-------|-------|
| Per fp_col | i_ai_clk | 1 |
| Per tile (4 t6 × 2 gtile × 16 cols) | i_ai_clk | 128 |
| **Total (×12 tiles)** | i_ai_clk | **1,536** |

> **Note:** SRCA slice holds 48 rows × 16 cols × 19b. Latch-array, **not SRAM**.

---

### 3.4 TRISC Instruction Cache — `tt_mem_wrap_*x72_sp_wmask_trisc_icache`

**Config (tt_instrn_engine_mem_wrappers.sv):** THREAD_COUNT = 4

| Thread | Instance | Module | Size |
|--------|----------|--------|------|
| thread 0 | `gen_trisc_icache[0].u_trisc_icache` | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` | 512×72b |
| thread 1 | `gen_trisc_icache[1].u_trisc_icache` | `tt_mem_wrap_256x72_sp_wmask_trisc_icache` | 256×72b |
| thread 2 | `gen_trisc_icache[2].u_trisc_icache` | `tt_mem_wrap_256x72_sp_wmask_trisc_icache` | 256×72b |
| thread 3 | `gen_trisc_icache[3].u_trisc_icache` | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` | 512×72b |

**Hierarchy path:**
```
gen_tensix_neo[x][y].tt_tensix_with_l1
  .t6[n].neo.u_t6.instrn_engine_wrapper.u_ie_mwrap.gen_trisc_icache[t].u_trisc_icache
```

| Scope | Clock | Count |
|-------|-------|-------|
| Per t6 | i_ai_clk | 4 (2×512, 2×256) |
| Per tile (×4 t6) | i_ai_clk | 16 |
| **Total (×12 tiles)** | i_ai_clk | **192** |

---

### 3.5 TRISC Local Memory — `tt_mem_wrap_*x52_sp_wmask_trisc_local_memory`

| Index | Instance | Module | Size |
|-------|----------|--------|------|
| 0 | `gen_trisc_local_mem[0].u_local_mem` | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` | 512×52b |
| 1 | `gen_trisc_local_mem[1].u_local_mem` | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` | 512×52b |
| 2 | `gen_trisc_local_mem[2].u_local_mem` | `tt_mem_wrap_1024x52_sp_wmask_trisc_local_memory` | 1024×52b |

**Hierarchy path:**
```
...instrn_engine_wrapper.u_ie_mwrap.gen_trisc_local_mem[i].u_local_mem
```

| Scope | Clock | Count |
|-------|-------|-------|
| Per t6 | i_ai_clk | 3 |
| Per tile (×4 t6) | i_ai_clk | 12 |
| **Total (×12 tiles)** | i_ai_clk | **144** |

---

### 3.6 TRISC Local Vector Memory — `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory`

| Index | Instance |
|-------|----------|
| 0 | `gen_trisc_local_vec_mem[0].u_vec_mem` |
| 1 | `gen_trisc_local_vec_mem[1].u_vec_mem` |

**Hierarchy path:**
```
...instrn_engine_wrapper.u_ie_mwrap.gen_trisc_local_vec_mem[i].u_vec_mem
```

| Scope | Clock | Count |
|-------|-------|-------|
| Per t6 | i_ai_clk | 2 |
| Per tile (×4 t6) | i_ai_clk | 8 |
| **Total (×12 tiles)** | i_ai_clk | **96** |

---

### 3.7 Overlay CPU Memories (per Tensix tile)

**Config (tt_overlay_pkg.sv):**

| Instance | Module | Type | Clock | Count per tile |
|----------|--------|------|-------|----------------|
| `memory_wrapper.gen_l1_dcache_data[0..15].l1_dcache_data` | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` | L1 D$ data | i_dm_clk | 16 |
| `memory_wrapper.gen_l1_dcache_tag[0..7].l1_dcache_tag` | `TTOverlayConfig_rockettile_dcache_tag_array_ext` | L1 D$ tag | i_dm_clk | 8 |
| `memory_wrapper.gen_l1_icache_data[0..15].l1_icache_data` | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` | L1 I$ data | i_dm_clk | 16 |
| `memory_wrapper.gen_l1_icache_tag[0..7].l1_icache_tag` | `TTOverlayConfig_rockettile_icache_tag_array_ext` | L1 I$ tag | i_dm_clk | 8 |
| `memory_wrapper.gen_l2_dir[0..3].l2_dir` | `TTOverlayConfig_cc_dir_ext` | L2 directory | i_dm_clk | 4 |
| `memory_wrapper.gen_l2_banks[0..15].l2_banks` | `TTOverlayConfig_cc_banks_0_ext` | L2 data banks | i_dm_clk | 16 |
| `memory_wrapper.gen_context_switch_mem.gen_cs_32x1024.mem_wrap_32x1024_sp_nomask_overlay_context_switch` | `tt_mem_wrap_32x1024_sp_nomask_overlay_context_switch` | Context switch | i_dm_clk | 1 |
| `memory_wrapper.gen_context_switch_mem.gen_cs_8x1024.mem_wrap_8x1024_sp_nomask_overlay_context_switch` | `tt_mem_wrap_8x1024_sp_nomask_overlay_context_switch` | Context switch | i_dm_clk | 1 |

**Full path prefix:**
```
gen_tensix_neo[x][y].tt_tensix_with_l1.overlay_noc_wrap.overlay_noc_niu_router
  .neo_overlay_wrapper.overlay_wrapper.memory_wrapper
```

| Scope | Clock | Count per tile | Total (×12) |
|-------|-------|----------------|-------------|
| Overlay memories | i_dm_clk | **70** | **840** |

---

### 3.8 Router VC Buffer SRAMs — `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest`

**In `gen_router[1..2][3].trinity_router.tt_router`:**

| Instance | Direction | Clock |
|----------|-----------|-------|
| `mem_wrap_*_router_input_north` | N | i_noc_clk |
| `mem_wrap_*_router_input_east` | E | i_noc_clk |
| `mem_wrap_*_router_input_south` | S | i_noc_clk |
| `mem_wrap_*_router_input_west` | W | i_noc_clk |

| Scope | Count |
|-------|-------|
| Per router tile | 4 |
| **Total (×2 router tiles)** | **8** |

---

### 3.9 Tensix NIU Router VC SRAMs — `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest`

**In `gen_tensix_neo[x][y].tt_tensix_with_l1.overlay_noc_wrap.overlay_noc_niu_router.tt_trinity_noc_niu_router_inst.noc_niu_router_inst`:**

| Instance | Port | Clock |
|----------|------|-------|
| `mem_wrap_*_router_input_north` | N | i_noc_clk |
| `mem_wrap_*_router_input_east` | E | i_noc_clk |
| `mem_wrap_*_router_input_south` | S | i_noc_clk |
| `mem_wrap_*_router_input_west` | W | i_noc_clk |
| `mem_wrap_*_router_input_niu` | NIU | i_noc_clk |

| Scope | Count |
|-------|-------|
| Per Tensix tile | 5 |
| **Total (×12 tiles)** | **60** |

---

### 3.10 Dispatch ATT SRAMs (2 dispatch tiles)

**In `gen_dispatch_{e/w}.tt_dispatch_top_inst_{east/west}.tt_dispatch_engine.overlay_noc_wrap_inst.disp_eng_overlay_noc_niu_router.trin_disp_eng_noc_niu_router_{east/west}_inst.disp_eng_noc_niu_router_inst`:**

| Instance | Module | Type | Clock |
|----------|--------|------|-------|
| `mem_wrap_1024x12_*_noc_endpoint_translation` | `tt_mem_wrap_1024x12_*` | ATT endpoint table | i_noc_clk |
| `mem_wrap_32x1024_*_noc_routing_translation` | `tt_mem_wrap_32x1024_*` | ATT routing table | i_noc_clk |
| `noc2axi_slv_rddata` FIFOs | — | Read data FIFOs | i_noc_clk |

> Note: ATT SRAM count inside `tt_noc2axi` (dispatch variant) not expanded here.
> **Estimated: ~6 macros per dispatch tile, 12 total.**

---

### 3.11 Dispatch L1 SRAMs

**In `gen_dispatch_{e/w}.tt_dispatch_top_inst.tt_dispatch_engine.disp_eng_l1_partition_inst.tt_t6_l1_dispatch`:**

> Dispatch uses a reduced L1 (`tt_disp_eng_l1_wrap2`). Exact macro count not extracted; expected ~16–32 macros per dispatch tile.

---

## 4. SRAM Macro Count Summary — Trinity (20260221)

| # | Subsystem | Module | Macro Size | Clock | Per Tile | Tiles | **Total** |
|---|-----------|--------|-----------|-------|----------|-------|-----------|
| 1 | T6 L1 data | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` | 1024×128b (16KB) | i_ai_clk | 64 | 12 | **768** |
| 2 | TRISC I-cache (th 0,3) | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` | 512×72b | i_ai_clk | 8 | 12 | **96** |
| 3 | TRISC I-cache (th 1,2) | `tt_mem_wrap_256x72_sp_wmask_trisc_icache` | 256×72b | i_ai_clk | 8 | 12 | **96** |
| 4 | TRISC local mem (x2) | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` | 512×52b | i_ai_clk | 8 | 12 | **96** |
| 5 | TRISC local mem (x1) | `tt_mem_wrap_1024x52_sp_wmask_trisc_local_memory` | 1024×52b | i_ai_clk | 4 | 12 | **48** |
| 6 | TRISC vec mem | `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory` | 256×104b | i_ai_clk | 8 | 12 | **96** |
| 7 | Overlay L1 D$ data | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` | — | i_dm_clk | 16 | 12 | **192** |
| 8 | Overlay L1 D$ tag | `TTOverlayConfig_rockettile_dcache_tag_array_ext` | — | i_dm_clk | 8 | 12 | **96** |
| 9 | Overlay L1 I$ data | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` | — | i_dm_clk | 16 | 12 | **192** |
| 10 | Overlay L1 I$ tag | `TTOverlayConfig_rockettile_icache_tag_array_ext` | — | i_dm_clk | 8 | 12 | **96** |
| 11 | Overlay L2 directory | `TTOverlayConfig_cc_dir_ext` | — | i_dm_clk | 4 | 12 | **48** |
| 12 | Overlay L2 banks | `TTOverlayConfig_cc_banks_0_ext` | — | i_dm_clk | 16 | 12 | **192** |
| 13 | Context switch 32×1024 | `tt_mem_wrap_32x1024_sp_nomask_overlay_context_switch` | 32×1024b | i_dm_clk | 1 | 12 | **12** |
| 14 | Context switch 8×1024 | `tt_mem_wrap_8x1024_sp_nomask_overlay_context_switch` | 8×1024b | i_dm_clk | 1 | 12 | **12** |
| 15 | Router VC FIFO (d2d) | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | 256×2048b | i_noc_clk | 4 | 2 | **8** |
| 16 | Tensix NIU VC FIFO | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | 64×2048b | i_noc_clk | 5 | 12 | **60** |
| 17 | Dispatch ATT SRAMs | `tt_mem_wrap_{1024x12,32x1024}_*` | various | i_noc_clk | ~6 | 2 | **~12** |
| — | **SRAM subtotal** | | | | | | **≈ 2,112** |

### Non-SRAM Register Files

| # | Subsystem | Module | Type | Per Tile | Total |
|---|-----------|--------|------|----------|-------|
| A | DEST regfile | `tt_reg_bank` | Latch array (LATCH_ARRAY) | 1,024 | **12,288** |
| B | SRCA reg slice | `tt_srca_reg_slice` | Latch array | 128 | **1,536** |
| C | SFPU local regs | `tt_sfpu_lregs` | Flip-flop (always_ff) | — | — |

---

## 5. Memory Instances by Clock Domain

| Clock | Total SRAM macros | Key subsystems |
|-------|------------------|----------------|
| **i_ai_clk** | ~1,200 | T6 L1, TRISC I-cache, TRISC local/vec mem |
| **i_dm_clk** | ~840 | Overlay CPU L1/L2 cache, context switch |
| **i_noc_clk** | ~80 | Router VC FIFOs, NIU VC FIFOs, ATT tables |
| **i_ref_clk** | 0 | No SRAM |

---

## 6. N1B0 Differences (20250301 vs 20260221)

Based on `tt_trin_l1_cfg.svh` (N1B0) vs `tt_mimir_l1_cfg.svh` (Trinity 20260221):

| Parameter | Trinity 20260221 (Mimir L1) | N1B0 20250301 | Impact |
|-----------|---------------------------|---------------|--------|
| SBANK_CNT | 4 | 4 | Same |
| BANK_IN_SBANK | 4 | **16** | 4× larger |
| SUB_BANK_CNT | 4 | 4 | Same |
| **Total macros/tile** | **64** | **256** | **4× more** |
| SRAM macro | `MWRAP2X2048X128` (dual 2048×128) | `MWRAP768X128` (768×128) | Shallower/wider |
| Total L1 SRAM (12 tiles) | 768 | **3,072** | — |
| NOC_RD_PORT_CNT | 2 | 4 | 2× more NoC read ports |
| NOC_WR_PORT_CNT | 2 | 4 | 2× more NoC write ports |

> **Key difference:** N1B0 Trinity uses a larger L1 (256 × 768×128 macros = 24.6 MB per tile vs 1.0 MB per tile in 20260221 Mimir config). This is a dramatically different memory subsystem — N1B0 appears to be a much larger compute tile variant. The overlay CPU and NoC memories are unchanged.

---

## 7. Hierarchy Revision Notes (V0.2 changes from V0.1)

1. **DEST register bank dimensions corrected:** `dest_reg_bank[*][*]` → `dest_reg_bank[2][4]` (NUM_BANKS×NUM_COLS from `tt_gtile_dest.sv`)
2. **TRISC memory thread assignment added:** threads 0,3 use 512×72 I-cache; threads 1,2 use 256×72; local mem is 2×512×52 + 1×1024×52; vec mem 2×256×104
3. **L1 SRAM exact count confirmed:** 4×4×4 = 64 macros per tile (from `tt_mimir_l1_cfg.svh`)
4. **Overlay macro counts confirmed:** 16 D$/I$ data, 8 tag, 4 L2 dir, 16 L2 banks, 1+1 context switch per tile (from `tt_overlay_pkg.sv`)
5. **N1B0 comparison section added** — significant L1 macro count difference (64 vs 256 per tile)
6. **Clock domain breakdown table added** for memory macros

---

## 8. Complete Instance Name Index (all unique memory macros in Trinity)

```
SRAM macros (tt_mem_wrap_* and Rocket tile SRAM):
  tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1               [T6 L1 data]
  tt_mem_wrap_512x72_sp_wmask_trisc_icache                     [TRISC icache thread 0,3]
  tt_mem_wrap_256x72_sp_wmask_trisc_icache                     [TRISC icache thread 1,2]
  tt_mem_wrap_512x52_sp_wmask_trisc_local_memory               [TRISC local mem]
  tt_mem_wrap_1024x52_sp_wmask_trisc_local_memory              [TRISC local mem large]
  tt_mem_wrap_256x104_sp_wmask_trisc_local_memory              [TRISC vector local mem]
  TTOverlayConfig_rockettile_dcache_data_arrays_0_ext          [Overlay L1 D$ data]
  TTOverlayConfig_rockettile_dcache_tag_array_ext              [Overlay L1 D$ tag]
  TTOverlayConfig_rockettile_icache_data_arrays_0_ext          [Overlay L1 I$ data]
  TTOverlayConfig_rockettile_icache_tag_array_ext              [Overlay L1 I$ tag]
  TTOverlayConfig_cc_dir_ext                                   [Overlay L2 directory]
  TTOverlayConfig_cc_banks_0_ext                               [Overlay L2 banks]
  tt_mem_wrap_32x1024_sp_nomask_overlay_context_switch         [Context switch 32-entry]
  tt_mem_wrap_8x1024_sp_nomask_overlay_context_switch          [Context switch 8-entry]
  tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest [Router VC FIFO, 2-port]
  tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest     [Tensix NIU VC FIFO]
  tt_mem_wrap_1024x12_*_noc_endpoint_translation               [ATT endpoint table]
  tt_mem_wrap_32x1024_*_noc_routing_translation                [ATT routing table]

Latch-array register files (not SRAM):
  tt_reg_bank                                                  [DEST double-buffer, 12,288 total]
  tt_srca_reg_slice                                            [SRCA buffer, 1,536 total]

Flip-flop register files (not SRAM):
  tt_sfpu_lregs                                                [SFPU local regs 4×32b]
```

---

*Document auto-generated 2026-03-18 from RTL analysis of /secure_data_from_tt/20260221/ and N1B0 comparison with /secure_data_from_tt/20250301/used_in_n1/*
