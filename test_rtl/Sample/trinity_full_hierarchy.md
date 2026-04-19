# Trinity SoC — Full Path Hierarchy Diagram with Memory Inventory

**Date:** 2026-03-18
**RTL (Trinity baseline):** `/secure_data_from_tt/20260221/`
**RTL (N1B0):** `/secure_data_from_tt/20250301/used_in_n1/`
**Hierarchy CSV:** `trinity_hierarchy.csv`

---

## Legend

| Symbol | Meaning |
|--------|---------|
| `[ai]` | Clock source = `i_ai_clk` |
| `[noc]` | Clock source = `i_noc_clk` |
| `[dm]` | Clock source = `i_dm_clk` (core_clk or uncore_clk) |
| `[ref]` | Clock source = `i_ref_clk` |
| `★` | Contains SRAM macro(s) |
| `◆` | Contains latch-array register file |
| `[×N]` | Instance count |
| `(NxM)` | SRAM size: N rows × M bits |

---

## 1. Grid Overview

### Trinity Baseline (20260221)

```
      X=0            X=1               X=2            X=3
Y=4  NIU NE_OPT     NIU N_OPT         NIU N_OPT      NIU NW_OPT    ← DRAM AXI bridges
Y=3  DISPATCH_E     ROUTER(empty*)    ROUTER(empty*)  DISPATCH_W    ← Dispatch + Router
Y=2  TENSIX(2)      TENSIX(7)         TENSIX(12)      TENSIX(17)    ← Compute row C
Y=1  TENSIX(1)      TENSIX(6)         TENSIX(11)      TENSIX(16)    ← Compute row B
Y=0  TENSIX(0)      TENSIX(5)         TENSIX(10)      TENSIX(15)    ← Compute row A

*Router in Trinity baseline IS instantiated as trinity_router inside gen_router[*][3]
```

### N1B0 Grid (20250301/used_in_n1)

```
      X=0               X=1                        X=2                       X=3
Y=4  NOC2AXI_NE_OPT   NOC2AXI_ROUTER_NE_OPT     NOC2AXI_ROUTER_NW_OPT    NOC2AXI_NW_OPT
Y=3  DISPATCH_E        ▲ (ROUTER placeholder,      ▲ (same, no module       DISPATCH_W
                          no module instantiated)    instantiated)
Y=2  TENSIX(2)         TENSIX(7)                  TENSIX(12)               TENSIX(17)
Y=1  TENSIX(1)         TENSIX(6)                  TENSIX(11)               TENSIX(16)
Y=0  TENSIX(0)         TENSIX(5)                  TENSIX(10)               TENSIX(15)

▲ NOC2AXI_ROUTER_NE/NW_OPT each span TWO rows (Y=4 + Y=3).
  Y=3 router logic is embedded inside the combined tile — gen_router[1/2][3] is empty.
```

**EndpointIndex = x × SizeY + y = x×5 + y** (same formula for both)

---

## 2. Tree Overview

```
trinity  [ai/noc/dm/ref]  ── 4×5 NoC mesh SoC
│
├─[×2] gen_dispatch_{e/w}  ── Dispatch Tile (X=0,3 / Y=3)
│   └── tt_dispatch_engine  [dm/noc/ai]
│       ├── disp_eng_l1_partition_inst  [noc]
│       │   └── ★ tt_t6_l1_dispatch  [noc]  ── Dispatch L1 SRAM
│       └── overlay_noc_wrap_inst → disp_eng_overlay_noc_niu_router  [dm/noc/ref]
│           ├── disp_eng_overlay_wrapper → overlay_wrapper  [dm/noc/ref]
│           │   └── ★★ (same as Tensix overlay_wrapper, DISPATCH_INST=1, HAS_SMN=0)
│           └── trin_disp_eng_noc_niu_router_{e/w}_inst  [noc]
│               └── ★ disp_eng_noc_niu_router_inst  [noc]  ── ATT SRAMs (1024x12 + 32x1024)
│
├─[×2] gen_router[1..2][3]  ── NoC Router Tile (Trinity baseline only; N1B0: EMPTY)
│   └── trinity_router  [noc/ai/dm]
│       └── tt_noc2axi (tt_router)  [noc]
│           ├── ★ mem_wrap_*_router_input_north  [noc]  ── Router N VC FIFO (256×2048b)
│           ├── ★ mem_wrap_*_router_input_east   [noc]  ── Router E VC FIFO (256×2048b)
│           ├── ★ mem_wrap_*_router_input_south  [noc]  ── Router S VC FIFO (256×2048b)
│           └── ★ mem_wrap_*_router_input_west   [noc]  ── Router W VC FIFO (256×2048b)
│
├─[×2] gen_noc2axi_router_{ne/nw}_opt  ── N1B0 ONLY: Combined NIU+Router (Y=4+Y=3)
│   └── trinity_noc2axi_router_{ne/nw}_opt  [ai/noc/dm per-column]
│       └── tt_noc2axi (router section)
│           ├── ★ mem_wrap_256x2048_router_input_north  [noc]  ── Router N VC FIFO
│           ├── ★ mem_wrap_256x2048_router_input_east   [noc]  ── Router E VC FIFO
│           ├── ★ mem_wrap_256x2048_router_input_south  [noc]  ── Router S VC FIFO
│           └── ★ mem_wrap_256x2048_router_input_west   [noc]  ── Router W VC FIFO
│
└─[×12] gen_tensix_neo[0..3][0..2]  ── Tensix Compute Tile
    └── tt_tensix_with_l1  [ai/noc/dm]
        │
        ├── overlay_noc_wrap → overlay_noc_niu_router  [dm/noc/ai/ref]
        │   ├── neo_overlay_wrapper → overlay_wrapper  [dm/noc/ref]  ── Overlay CPU cluster
        │   │   └── memory_wrapper  ← all Overlay SRAMs (70/tile)
        │   │       ├── ★ gen_l1_dcache_data[×16]    [dm]  ── Overlay L1 D-Cache Data
        │   │       ├── ★ gen_l1_dcache_tag[×8]      [dm]  ── Overlay L1 D-Cache Tag
        │   │       ├── ★ gen_l1_icache_data[×16]    [dm]  ── Overlay L1 I-Cache Data
        │   │       ├── ★ gen_l1_icache_tag[×8]      [dm]  ── Overlay L1 I-Cache Tag
        │   │       ├── ★ gen_l2_dir[×4]             [dm]  ── Overlay L2 Directory
        │   │       ├── ★ gen_l2_banks[×16]          [dm]  ── Overlay L2 Data Banks
        │   │       ├── ★ gen_cs_32x1024.mem_wrap    [dm]  ── Context Switch SRAM (32-entry)
        │   │       └── ★ gen_cs_8x1024.mem_wrap     [dm]  ── Context Switch SRAM (8-entry)
        │   └── tt_trinity_noc_niu_router_inst → noc_niu_router_inst  [ai/noc]
        │       ├── ★ mem_wrap_*_router_input_north  [noc]  ── Tensix NIU N VC FIFO (64×2048b)
        │       ├── ★ mem_wrap_*_router_input_east   [noc]  ── Tensix NIU E VC FIFO
        │       ├── ★ mem_wrap_*_router_input_south  [noc]  ── Tensix NIU S VC FIFO
        │       ├── ★ mem_wrap_*_router_input_west   [noc]  ── Tensix NIU W VC FIFO
        │       └── ★ mem_wrap_*_router_input_niu    [noc]  ── Tensix NIU→NIU VC FIFO
        │
        ├─[×4] t6[0..3].neo.u_t6  (tt_tensix)  [ai]  ── T6 Tensix Core
        │   ├─[×2] gen_gtile[0..1].u_fpu_gtile  [ai]  ── FPU G-Tile
        │   │   └─[×16] gen_fp_cols[0..15].mtile_and_dest  [ai]
        │   │       ├── u_fpu_mtile → ◆ u_srca_reg_slice  [ai]  ── SRCA Latch-Array (48×16×19b)
        │   │       └── dest_slice  → ◆ dest_reg_bank[2][4]  [ai]  ── DEST Double-Buffer Regfile (latch)
        │   └── instrn_engine_wrapper → instrn_engine  [ai]
        │       ├── sfpu_wrapper.gen_sfpu[*].u_sfpu.u_sfpu_lregs[*]  (FF only, not SRAM)
        │       └── u_ie_mwrap  [ai]  ── All TRISC memory macros
        │           ├── ★ gen_trisc_icache[0].u_trisc_icache  [ai]  ── TRISC0 I-Cache (512×72b)
        │           ├── ★ gen_trisc_icache[1].u_trisc_icache  [ai]  ── TRISC1 I-Cache (256×72b)
        │           ├── ★ gen_trisc_icache[2].u_trisc_icache  [ai]  ── TRISC2 I-Cache (256×72b)
        │           ├── ★ gen_trisc_icache[3].u_trisc_icache  [ai]  ── BRISC I-Cache (512×72b)
        │           ├── ★ gen_trisc_local_mem[0].u_local_mem  [ai]  ── TRISC0 Local Mem (512×52b)
        │           ├── ★ gen_trisc_local_mem[1].u_local_mem  [ai]  ── TRISC1 Local Mem (512×52b)
        │           ├── ★ gen_trisc_local_mem[2].u_local_mem  [ai]  ── TRISC2/BRISC Local Mem (1024×52b)
        │           ├── ★ gen_trisc_local_vec_mem[0].u_vec_mem  [ai]  ── TRISC Vec Local Mem (256×104b)
        │           └── ★ gen_trisc_local_vec_mem[1].u_vec_mem  [ai]  ── TRISC Vec Local Mem (256×104b)
        │
        └── u_l1part → u_l1w2 → u_l1_mem_wrap  [ai]  ── T6 L1 SRAM bank
            └─[×4] gen_sbank[0..3]
                └─[×4] gen_bank[0..3]
                    └─[×4] gen_sub_bank[0..3]
                        └── ★ u_sub_mwrap  [ai]  ── T6 L1 Data SRAM (1024×128b = 16KB × 64 = 1MB/tile)
```

---

## 3. Dispatch Tiles (×2)

| Full Hierarchy Path | Module | Clock Source | # Instances | Description | Memory Instance(s) |
|---------------------|--------|-------------|-------------|-------------|-------------------|
| `trinity.gen_dispatch_{e/w}` | — | — | ×2 | Dispatch tile generate | — |
| `.tt_dispatch_top_inst_{east/west}` | `tt_dispatch_top_{east/west}` | i_ai_clk / i_noc_clk / i_dm_clk | ×2 | Dispatch Tile Top | — |
| `.tt_dispatch_engine` | `tt_dispatch_engine` | i_dm_clk / i_noc_clk / i_ai_clk | ×2 | Dispatch Engine | — |
| `.disp_eng_l1_partition_inst` | `tt_disp_eng_l1_partition` | i_noc_clk / i_ref_clk | ×2 | Dispatch L1 Partition | — |
| `.disp_eng_l1_partition_inst.de_refclk_dft_vdd_sys` | `tt_refclk_dft_mux` | i_ref_clk | ×2 | DFT ref clock mux | — |
| `.disp_eng_l1_partition_inst.tt_t6_l1_dispatch` ★ | `tt_disp_eng_l1_wrap2` | **i_noc_clk** | ×2 | **Dispatch L1 SRAM Wrapper** | `[dispatch L1 SRAMs]` |
| `.disp_eng_l1_partition_inst.u_edc_biu` | `tt_edc_biu_soc_apb4_wrap` | i_noc_clk | ×2 | EDC APB Bridge | — |
| `.overlay_noc_wrap_inst` | `tt_disp_eng_overlay_noc_wrap` | i_dm_clk / i_noc_clk / i_ref_clk | ×2 | Dispatch Overlay+NoC wrap | — |
| `.disp_eng_overlay_noc_niu_router` | `tt_disp_eng_overlay_noc_niu_router` | i_dm_clk / i_noc_clk / i_ref_clk | ×2 | Dispatch NoC NIU Router | — |
| `.disp_eng_overlay_wrapper` | `tt_disp_eng_overlay_wrapper` | i_dm_clk / i_noc_clk / i_ref_clk | ×2 | Dispatch Overlay shell | — |
| `.disp_eng_overlay_wrapper.edc_muxing_when_harvested` | `tt_edc1_serial_bus_mux` | i_noc_clk | ×2 | EDC harvest mux | — |
| `.disp_eng_overlay_wrapper.overlay_wrapper` | `tt_overlay_wrapper` | i_dm_clk / i_noc_clk / i_ref_clk | ×2 | **Dispatch Overlay CPU Cluster** (DISPATCH_INST=1, HAS_SMN=0) | *(same structure as Tensix overlay but reduced)* |
| `.trin_disp_eng_noc_niu_router_{e/w}_inst` | `tt_trin_disp_eng_noc_niu_router_{east/west}` | i_noc_clk / i_dm_clk | ×2 | Dispatch NIU Router shell | — |
| `.trin_disp_eng_noc_niu_router_{e/w}_inst.disp_eng_noc_niu_router_inst` ★ | `tt_disp_eng_noc_niu_router` | **i_noc_clk** | ×2 | **ATT Endpoint + Routing Tables** | `mem_wrap_1024x12_*_noc_endpoint_translation` / `mem_wrap_32x1024_*_noc_routing_translation` / `noc2axi_slv_rddata FIFOs` |
| `.trin_disp_eng_noc_niu_router_{e/w}_inst.edc_demuxing_when_harvested` | `tt_edc1_serial_bus_demux` | i_noc_clk | ×2 | EDC harvest demux | — |
| `.trin_disp_eng_noc_niu_router_{e/w}_inst.overlay_noc_sec_conf` | `tt_edc1_noc_sec_controller` | i_noc_clk | ×2 | NoC Security Controller | — |

---

## 4. Router Tiles (×2 — Trinity Baseline) / NOC2AXI_ROUTER (N1B0)

### 4-A Trinity Baseline — Standalone Router Tiles (gen_router[1..2][3])

| Full Hierarchy Path | Module | Clock Source | # Instances | Description | Memory Instance(s) |
|---------------------|--------|-------------|-------------|-------------|-------------------|
| `trinity.gen_router[1..2][3]` | — | — | ×2 | Router tile generate | — |
| `.trinity_router` | `trinity_router` | i_noc_clk / i_ai_clk / i_dm_clk | ×2 | Router Tile Top | — |
| `.trinity_router.router_edc1_apb4_bridge` | `tt_edc1_apb4_bridge` | i_noc_clk | ×2 | EDC APB bridge | — |
| `.trinity_router.tt_router` | `tt_noc2axi` | **i_noc_clk** | ×2 | Router NIU core | `mem_wrap_*_router_input_{N/E/S/W}` |
| `.tt_router.mem_wrap_*_router_input_north` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router North VC Input FIFO** | `mem_wrap_*_router_input_north` |
| `.tt_router.mem_wrap_*_router_input_east` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router East VC Input FIFO** | `mem_wrap_*_router_input_east` |
| `.tt_router.mem_wrap_*_router_input_south` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router South VC Input FIFO** | `mem_wrap_*_router_input_south` |
| `.tt_router.mem_wrap_*_router_input_west` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router West VC Input FIFO** | `mem_wrap_*_router_input_west` |
| `.tt_router.router` | `tt_router` | i_noc_clk (postdfx) | ×2 | Router switch fabric | — |
| `.router.gen_input_port[*].tt_router_input_if` | `tt_router_input_if` | i_noc_clk | ×(2×5) | Router Input Port | — |
| `.tt_router_input_if.vc_buf` | `tt_noc_vc_buf` | i_noc_clk (gated) | ×(2×5) | VC Buffer | — |
| `.tt_router_input_if.out_port_arb` | `tt_noc_rr_arb` | i_noc_clk | ×(2×5) | Output port round-robin arbiter | — |
| `.router.gen_output_port[*].tt_router_output_if` | `tt_router_output_if` | i_noc_clk (gated) | ×(2×5) | Router Output Port | — |
| `.tt_router_output_if.vc_allocator` | `tt_router_vc_allocator` | i_noc_clk (gated) | ×(2×5) | VC Allocator | — |
| `.router.tt_router_port_allocator` | `tt_router_port_allocator` | i_noc_clk (gated) | ×2 | Port Allocator | — |
| `.router.tt_noc_repeaters_cardinal` | `tt_noc_repeaters_cardinal` | i_noc_clk | ×2 | Cardinal direction repeaters | — |
| `.tt_router.sync_noc_reset_async_fifo` | `tt_sync_reset_powergood` | i_noc_clk | ×2 | NoC reset synchronizer | — |

### 4-B N1B0 — Combined NIU+Router Tile (gen_noc2axi_router_{ne/nw}_opt, covers Y=4+Y=3)

| Full Hierarchy Path | Module | Clock Source | # Instances | Description | Memory Instance(s) |
|---------------------|--------|-------------|-------------|-------------|-------------------|
| `trinity.gen_noc2axi_router_{ne/nw}_opt` | — | — | ×2 | N1B0 combined NIU+Router tile | — |
| `.trinity_noc2axi_router_{ne/nw}_opt` | `trinity_noc2axi_router_{ne/nw}_opt` | i_ai_clk[x] / i_noc_clk / i_dm_clk[x] | ×2 | **Combined AXI bridge + Router (dual-row Y=4+Y=3)** | — |
| *(Y=4 section) tt_noc2axi AXI bridge* | `tt_noc2axi` | i_ai_clk / i_noc_clk | ×2 | NIU core (NOC→AXI bridge) | `mem_wrap_*` (same as baseline NIU) |
| *(Y=3 section) router*  | `tt_router` inside `tt_noc2axi` | **i_noc_clk** | ×2 | Router fabric embedded in combined tile | same sub-hierarchy as baseline router |
| `.mem_wrap_256x2048_router_input_north` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router North VC FIFO (N1B0)** | `mem_wrap_256x2048_router_input_north` |
| `.mem_wrap_256x2048_router_input_east` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router East VC FIFO (N1B0)** | `mem_wrap_256x2048_router_input_east` |
| `.mem_wrap_256x2048_router_input_south` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router South VC FIFO (N1B0)** | `mem_wrap_256x2048_router_input_south` |
| `.mem_wrap_256x2048_router_input_west` ★ | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | **i_noc_clk** | **×2** | **Router West VC FIFO (N1B0)** | `mem_wrap_256x2048_router_input_west` |

> **N1B0 Clock note:** `router_o_ai_clk` and `router_o_dm_clk` are output ports that feed Y=3 downstream — clock is per-column `i_ai_clk[x]` / `i_dm_clk[x]` arrays in N1B0, not a single shared clock.
> **N1B0 Repeaters:** `tt_noc_repeaters(NUM=4)×2` at Y=4 and `tt_noc_repeaters(NUM=6)×2` at Y=3 bridge X=1↔X=2.

---

## 5. Tensix Compute Tiles (×12: X=0..3, Y=0..2)

### 5-A Tile Top

| Full Hierarchy Path | Module | Clock Source | # Instances | Description | Memory Instance(s) |
|---------------------|--------|-------------|-------------|-------------|-------------------|
| `trinity.gen_tensix_neo[0..3][0..2]` | — | — | **×12** | Tensix tile generate (4×3 grid) | — |
| `.tt_tensix_with_l1` | `tt_tensix_with_l1` | i_ai_clk / i_noc_clk / i_dm_clk | ×12 | **Tensix Tile Top with L1** | — |
| `.tt_tensix_with_l1.overlay_noc_wrap` | `tt_overlay_noc_wrap` | i_dm_clk / i_noc_clk / i_ai_clk | ×12 | Overlay + NIU/Router cluster | — |
| `.tt_tensix_with_l1.tensix_neo_pll_pvt_wrapper` | `tt_tensix_neo_pll_pvt_wrapper` | i_ref_clk | ×12 | PLL/PVT sensor wrapper | — |
| `.tt_tensix_with_l1.edc_conn_*` | `tt_edc1_intf_connector` | — | ×12 | EDC ring connectors | — |

### 5-B Tensix NIU + NoC Router (per tile)

| Full Hierarchy Path | Module | Clock Source | # Inst/tile | Total | Description | Memory Instance(s) |
|---------------------|--------|-------------|------------|-------|-------------|-------------------|
| `.overlay_noc_wrap.overlay_noc_niu_router` | `tt_overlay_noc_niu_router` | i_dm_clk / i_noc_clk / i_ai_clk / i_ref_clk | 1 | 12 | Overlay NoC NIU Router | — |
| `.overlay_noc_niu_router.tt_trinity_noc_niu_router_inst` | `tt_trin_noc_niu_router_wrap` | i_ai_clk / i_noc_clk | 1 | 12 | Tensix NIU Router shell | — |
| `.tt_trinity_noc_niu_router_inst.noc_niu_router_inst` | `tt_noc_niu_router` | i_ai_clk / i_noc_clk | 1 | 12 | Tensix NIU core | 5 VC FIFOs + flex_port_cfg_cdc |
| `.noc_niu_router_inst.mem_wrap_*_router_input_north` ★ | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | **i_noc_clk** | 1 | **12** | **Tensix NIU North VC FIFO** | `mem_wrap_*_router_input_north` |
| `.noc_niu_router_inst.mem_wrap_*_router_input_east` ★ | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | **i_noc_clk** | 1 | **12** | **Tensix NIU East VC FIFO** | `mem_wrap_*_router_input_east` |
| `.noc_niu_router_inst.mem_wrap_*_router_input_south` ★ | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | **i_noc_clk** | 1 | **12** | **Tensix NIU South VC FIFO** | `mem_wrap_*_router_input_south` |
| `.noc_niu_router_inst.mem_wrap_*_router_input_west` ★ | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | **i_noc_clk** | 1 | **12** | **Tensix NIU West VC FIFO** | `mem_wrap_*_router_input_west` |
| `.noc_niu_router_inst.mem_wrap_*_router_input_niu` ★ | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | **i_noc_clk** | 1 | **12** | **Tensix NIU→NIU VC FIFO** | `mem_wrap_*_router_input_niu` |
| `.noc_niu_router_inst.flex_port_cfg_cdc` | `tt_upf_async_fifo` | i_noc_clk(wr) / i_ai_clk(rd) | 1 | 12 | Flex Port Config CDC FIFO | — |
| `.noc_niu_router_inst.router` | `tt_router` | i_noc_clk (postdfx_aon) | 1 | 12 | NIU Router switch fabric | — |
| `.router.gen_input_port[*].tt_router_input_if` | `tt_router_input_if` | i_noc_clk | ×6 | 72 | Router Input Port | — |
| `.router.gen_output_port[*].tt_router_output_if` | `tt_router_output_if` | i_noc_clk (gated) | ×6 | 72 | Router Output Port | — |
| `.router.tt_router_port_allocator` | `tt_router_port_allocator` | i_noc_clk (gated) | 1 | 12 | Port Allocator | — |
| `.router.tt_noc_repeaters_cardinal` | `tt_noc_repeaters_cardinal` | i_noc_clk | 1 | 12 | Cardinal direction repeaters | — |
| `.tt_trinity_noc_niu_router_inst.overlay_noc_sec_conf` | `tt_edc1_noc_sec_controller` | i_noc_clk | 1 | 12 | NoC Security Controller | — |

### 5-C Overlay CPU Cluster (per Tensix tile)

| Full Hierarchy Path | Module | Clock Source | # Inst/tile | Total | Description | Memory Instance(s) |
|---------------------|--------|-------------|------------|-------|-------------|-------------------|
| `.overlay_noc_niu_router.neo_overlay_wrapper` | `tt_neo_overlay_wrapper` | i_dm_clk / i_noc_clk / i_ai_clk | 1 | 12 | Overlay wrapper shell (harvest mux) | — |
| `.neo_overlay_wrapper.overlay_loopback_repeater` | `tt_noc_overlay_edc_repeater` | i_noc_clk | 1 | 12 | EDC ring loopback repeater | — |
| `.neo_overlay_wrapper.overlay_wrapper` | `tt_overlay_wrapper` | i_dm_clk / i_noc_clk / i_ref_clk | 1 | 12 | **Overlay CPU Cluster Top** | — |
| `.overlay_wrapper.clock_reset_ctrl` | `tt_overlay_clock_reset_ctrl` | i_dm_clk / i_ref_clk / i_noc_clk | 1 | 12 | Overlay Clock/Reset Controller | — |
| `.clock_reset_ctrl.core_clk_gate` | `tt_clkgater` | i_dm_clk | 1 | 12 | Core clock gate | — |
| `.clock_reset_ctrl.uncore_clk_gate` | `tt_clkgater` | i_dm_clk | 1 | 12 | Uncore clock gate | — |
| `.overlay_wrapper.cpu_cluster_wrapper` | `tt_overlay_cpu_wrapper` | i_dm_clk (core/uncore/debug) | 1 | 12 | CPU Cluster Wrapper | — |
| `.cpu_cluster_wrapper.cpu_cluster` | `TTTrinityConfig_DigitalTop` | i_dm_clk (uncore + core×N) | 1 | 12 | Rocket Chip Top | — |
| `.cpu_cluster.RocketTile[*]` | `TTTrinityConfig_RocketTile` | i_dm_clk (core/uncore) | ×N | — | RISC-V Rocket Tile | — |
| `.RocketTile[*].*.ALU[*]` | `TTTrinityConfig_ALU` | i_dm_clk (core) | ×N | — | Rocket ALU | — |
| `.RocketTile[*].*.AMOALU[*]` | `TTTrinityConfig_AMOALU` | i_dm_clk (core) | ×N | — | Rocket AMO ALU | — |
| `.RocketTile[*].BankedStore[*]` | `TTTrinityConfig_BankedStore` | i_dm_clk (uncore) | ×N | — | L2 Banked Store | — |
| `.overlay_wrapper.memory_wrapper` ★ | `tt_overlay_memory_wrapper` | i_dm_clk (core/uncore) | 1 | **12** | **Overlay Memory Wrapper — 70 SRAMs/tile** | (see below) |
| `.memory_wrapper.gen_l1_dcache_data[0..15].l1_dcache_data` ★ | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` | **i_dm_clk (core)** | **16** | **192** | **Overlay CPU L1 D-Cache Data** | `l1_dcache_data` |
| `.memory_wrapper.gen_l1_dcache_tag[0..7].l1_dcache_tag` ★ | `TTOverlayConfig_rockettile_dcache_tag_array_ext` | **i_dm_clk (core)** | **8** | **96** | **Overlay CPU L1 D-Cache Tag** | `l1_dcache_tag` |
| `.memory_wrapper.gen_l1_icache_data[0..15].l1_icache_data` ★ | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` | **i_dm_clk (core)** | **16** | **192** | **Overlay CPU L1 I-Cache Data** | `l1_icache_data` |
| `.memory_wrapper.gen_l1_icache_tag[0..7].l1_icache_tag` ★ | `TTOverlayConfig_rockettile_icache_tag_array_ext` | **i_dm_clk (core)** | **8** | **96** | **Overlay CPU L1 I-Cache Tag** | `l1_icache_tag` |
| `.memory_wrapper.gen_l2_dir[0..3].l2_dir` ★ | `TTOverlayConfig_cc_dir_ext` | **i_dm_clk (uncore)** | **4** | **48** | **Overlay CPU L2 Directory** | `l2_dir` |
| `.memory_wrapper.gen_l2_banks[0..15].l2_banks` ★ | `TTOverlayConfig_cc_banks_0_ext` | **i_dm_clk (uncore)** | **16** | **192** | **Overlay CPU L2 Data Banks** | `l2_banks` |
| `.memory_wrapper.gen_context_switch_mem.gen_cs_32x1024.mem_wrap_32x1024_sp_nomask_overlay_context_switch` ★ | `tt_mem_wrap_32x1024_sp_nomask_overlay_context_switch` | **i_dm_clk (core)** | **1** | **12** | **Context Switch SRAM (32-entry ×1024b)** | `mem_wrap_32x1024_sp_nomask_overlay_context_switch` |
| `.memory_wrapper.gen_context_switch_mem.gen_cs_8x1024.mem_wrap_8x1024_sp_nomask_overlay_context_switch` ★ | `tt_mem_wrap_8x1024_sp_nomask_overlay_context_switch` | **i_dm_clk (core)** | **1** | **12** | **Context Switch SRAM (8-entry ×1024b)** | `mem_wrap_8x1024_sp_nomask_overlay_context_switch` |
| `.overlay_wrapper.smn_wrapper` | `tt_overlay_smn_wrapper` | i_dm_clk (uncore/smn) / i_noc_clk | 1 | 12 | SMN Security Monitor Node | — |
| `.smn_wrapper.smn_inst` | `tt_smn_node_full` | i_dm_clk / i_noc_clk | 1 | 12 | SMN Node (8-range security) | — |
| `.smn_wrapper.overlay_smn_wrapper_cdc` | `tt_overlay_smn_wrapper_cdc` | i_dm_clk / i_noc_clk | 1 | 12 | SMN CDC Bridge | — |
| `.smn_wrapper_cdc.smn_reg_common_input_cdc` | `tt_sync3` | i_dm_clk (smn) | 1 | 12 | SMN common reg input sync | — |
| `.smn_wrapper_cdc.smn_reg_common_output_cdc` | `tt_sync3` | i_dm_clk (uncore) | 1 | 12 | SMN common reg output sync | — |
| `.smn_wrapper_cdc.smn_reg_noc_sec_input_cdc` | `tt_sync_data_autohs` | i_noc_clk(src) / i_dm_clk(dst) | 1 | 12 | SMN NoC security reg CDC | — |
| `.smn_wrapper_cdc.smn_reg_noc_sec_outputput_cdc` | `tt_sync_data_autohs` | i_dm_clk(src) / i_noc_clk(dst) | 1 | 12 | SMN NoC security reg CDC | — |
| `.overlay_wrapper.edc_wrapper` | `tt_overlay_edc_wrapper` | i_dm_clk (aon_uncore) | 1 | 12 | EDC Ring Wrapper | — |
| `.edc_wrapper.wdt_reset_edc_node_inst` | `tt_edc1_node` | i_dm_clk | 1 | 12 | WDT EDC node | — |
| `.overlay_wrapper.overlay_ext_reg_cdc` | `tt_overlay_ext_reg_cdc` | i_dm_clk / i_ai_clk | 1 | 12 | Overlay ↔ T6 Register CDC | `overlay_req_fifo` / `ext_resp_fifo` / `ext_req_fifo` / `overlay_resp_fifo` |
| `.overlay_ext_reg_cdc.ext_req_fifo` | `tt_async_fifo_wrapper` | i_ai_clk(wr) / i_dm_clk(rd) | 1 | 12 | T6→Overlay ext req CDC FIFO | — |
| `.overlay_ext_reg_cdc.ext_resp_fifo` | `tt_async_fifo_wrapper` | i_ai_clk(wr) / i_dm_clk(rd) | 1 | 12 | T6→Overlay ext resp CDC FIFO | — |
| `.overlay_ext_reg_cdc.overlay_req_fifo` | `tt_async_fifo_wrapper` | i_dm_clk(wr) / i_ai_clk(rd) | 1 | 12 | Overlay→T6 req CDC FIFO | — |
| `.overlay_ext_reg_cdc.overlay_resp_fifo` | `tt_async_fifo_wrapper` | i_dm_clk(wr) / i_ai_clk(rd) | 1 | 12 | Overlay→T6 resp CDC FIFO | — |
| `.overlay_wrapper.overlay_niu_reg_cdc` | `tt_overlay_niu_reg_cdc` | i_dm_clk / i_noc_clk | 1 | 12 | Overlay ↔ NIU Register CDC | `overlay_req_fifo` / `niu_resp_fifo` / `niu_req_fifo` / `overlay_resp_fifo` |
| `.overlay_niu_reg_cdc.niu_req_fifo` | `tt_async_fifo_wrapper` | i_noc_clk(wr) / i_dm_clk(rd) | 1 | 12 | NIU→Overlay req CDC FIFO | — |
| `.overlay_niu_reg_cdc.niu_resp_fifo` | `tt_async_fifo_wrapper` | i_noc_clk(wr) / i_dm_clk(rd) | 1 | 12 | NIU→Overlay resp CDC FIFO | — |
| `.overlay_niu_reg_cdc.overlay_req_fifo` | `tt_async_fifo_wrapper` | i_dm_clk(wr) / i_noc_clk(rd) | 1 | 12 | Overlay→NIU req CDC FIFO | — |
| `.overlay_niu_reg_cdc.overlay_resp_fifo` | `tt_async_fifo_wrapper` | i_dm_clk(wr) / i_noc_clk(rd) | 1 | 12 | Overlay→NIU resp CDC FIFO | — |
| `.overlay_wrapper.gen_overlay_context_switch[*].overlay_context_switch` | `tt_overlay_context_switch` | i_dm_clk (core) | ×N | — | Context Switch Logic | — |
| `.overlay_context_switch.cs_clk_gater` | `tt_clk_gater` | i_dm_clk | ×N | — | Context switch clock gate | — |
| `.overlay_wrapper.overlay_wrapper_reg_logic` | `tt_overlay_wrapper_reg_logic` | i_dm_clk (uncore/core) | 1 | 12 | Overlay Register Crossbar | `rocc_reg_intf_cdc_to_core_clk` / `rocc_reg_intf_cdc_to_uncore_clk` |
| `.overlay_wrapper_reg_logic.rocc_reg_intf_cdc_to_core_clk` | `tt_async_fifo_wrapper` | i_dm_clk(uncore→core) | 1 | 12 | RoCC reg uncore→core CDC FIFO | — |
| `.overlay_wrapper_reg_logic.rocc_reg_intf_cdc_to_uncore_clk` | `tt_async_fifo_wrapper` | i_dm_clk(core→uncore) | 1 | 12 | RoCC reg core→uncore CDC FIFO | — |
| `.overlay_wrapper.gen_l1_ports[*].l1_req_async_cdc_to_aiclk` | `tt_async_fifo_wrapper` | i_dm_clk(wr) / i_ai_clk(rd) | ×N | — | L1 Req CDC FIFO (uncore→ai) | — |
| `.overlay_wrapper.gen_l1_ports[*].l1_resp_async_cdc_to_overlayclk` | `tt_async_fifo_wrapper` | i_ai_clk(wr) / i_dm_clk(rd) | ×N | — | L1 Resp CDC FIFO (ai→uncore) | — |
| `.overlay_wrapper.flex_client_port` | `tt_t6_l1_flex_client_port` | i_ai_clk | 1 | 12 | L1 Flex Client Port (AI domain) | — |
| `.overlay_wrapper.gen_flex_rd_ports[*]` | `tt_t6_l1_flex_client_rd_port` | i_ai_clk | ×N | — | L1 Flex Read Port | — |
| `.overlay_wrapper.gen_flex_wr_ports[*]` | `tt_t6_l1_flex_client_wr_port` | i_ai_clk | ×N | — | L1 Flex Write Port | — |
| `.overlay_wrapper.noc_snoop_tl_master` | `tt_overlay_noc_snoop_tl_master` | i_dm_clk / i_ai_clk | 1 | 12 | NoC Snoop TileLink Master | — |
| `.overlay_wrapper.overlay_pvt_pll_sync` | `tt_overlay_pvt_pll_sync` | i_dm_clk / i_ref_clk | 1 | 12 | PLL/PVT sync | — |
| `.overlay_wrapper.overlay_tile_counters_with_comparators` | `tt_overlay_tile_counters_with_comparators` | i_dm_clk (core) | 1 | 12 | Tile performance counters | — |
| `.overlay_wrapper.risc_to_noc_arb` | `tt_overlay_flit_vc_arb` | i_dm_clk (core) | 1 | 12 | RISC→NoC VC arbiter | — |
| `.overlay_wrapper.overlay_flex_client_regs` | `tt_overlay_flex_client_csr_wrapper` | i_ai_clk / i_dm_clk | 1 | 12 | Flex Client CSR Wrapper | — |
| `.overlay_wrapper.u_edc_flex_bist` | `tt_overlay_edc_flex_client_bist` | i_ai_clk (aon) | 1 | 12 | EDC Flex Client BIST | — |
| `.overlay_wrapper.tt_overlay_wrapper_dfx_inst` | `tt_overlay_wrapper_dfx` | i_dm_clk / i_ai_clk / i_noc_clk / i_ref_clk | 1 | 12 | DFT/DFX mux | — |

### 5-D T6 Tensix Cores (×4 per tile → ×48 total)

| Full Hierarchy Path | Module | Clock Source | # Inst/tile | Total | Description | Memory Instance(s) |
|---------------------|--------|-------------|------------|-------|-------------|-------------------|
| `.t6[0..3].neo.u_t6` | `tt_tensix` | **i_ai_clk** (gated per t6) | **4** | **48** | **T6 Tensix Compute Core** | — |
| `.u_t6.edc_input_conn_second_gtile` | `tt_edc1_intf_connector` | — | 4 | 48 | EDC G-Tile connector | — |
| `.u_t6.gen_gtile[0..1].u_fpu_gtile` | `tt_fpu_gtile` | **i_ai_clk** (gated/gtile) | **8** | **96** | **FPU G-Tile** | `gen_fp_cols[16].mtile_and_dest` |
| `.u_fpu_gtile.gen_fp_cols[0..15].mtile_and_dest` | `tt_mtile_and_dest_together_at_last` | **i_ai_clk** | **128** | **1,536** | **FP Column (M-Tile + DEST)** | `u_srca_reg_slice` + `dest_reg_bank[2][4]` |
| `.mtile_and_dest.u_fpu_mtile` | `tt_fpu_mtile` | **i_ai_clk** | 128 | 1,536 | M-Tile (256 MACs/cycle) | `u_srca_reg_slice` |
| `.u_fpu_mtile.u_srca_reg_slice` ◆ | `tt_srca_reg_slice` | **i_ai_clk** | **128** | **1,536** | **SRCA Register Slice (latch_array, 48×16×19b)** | `u_srca_reg_slice` |
| `.u_fpu_mtile.fp_row[*].u_tile` | `tt_fpu_tile` | **i_ai_clk** (gated) | ×(128×N) | — | FP Lane (multiplier/adder pipeline) | — |
| `.u_fpu_mtile.fp_row[*].fp_tile_clk_gater` | `tt_clk_gater` | i_ai_clk | ×(128×N) | — | FP tile clock gate | — |
| `.u_fpu_mtile.fpu_mtile_clk_gater` | `tt_clk_gater` | i_ai_clk | 128 | 1,536 | M-Tile clock gate | — |
| `.mtile_and_dest.dest_slice` | `tt_gtile_dest` | **i_ai_clk** | 128 | 1,536 | DEST Slice (double-buffer) | `dest_reg_bank[2][4]` |
| `.dest_slice.dest_reg_bank[0..1][0..3]` ◆ | `tt_reg_bank` | **i_ai_clk** | **1,024** | **12,288** | **DEST Double-Buffer Regfile (latch_array, SETS=256)** | `dest_reg_bank[b][col]` |
| `.dest_slice.fpu_parity_check[*]` | `tt_parity_check_with_tfd` | i_ai_clk | ×(128×N) | — | DEST parity check | — |
| `.dest_slice.strided_mux_tree_data` | `tt_gtile_dest_stride_mux_tree` | — | 128 | 1,536 | DEST stride mux (data) | — |
| `.u_fpu_gtile.gen_compare_fault_check.u_tt_fpu_safety_ctrl` | `tt_fpu_safety_ctrl` | i_ai_clk | 8 | 96 | FPU Safety Controller | — |
| `.u_fpu_gtile.u_srca_columnize` | `tt_srca_columnize` | i_ai_clk | 8 | 96 | SRCA column reformat | — |
| `.u_fpu_gtile.u_srcb_rows_ff` | `tt_srcb_pipe_stage` | i_ai_clk | 8 | 96 | SRCB pipeline stage | — |
| `.u_fpu_gtile.edc_*_repeater` | `tt_edc1_serial_bus_repeater` | i_ai_clk | ×(8×N) | — | EDC serial bus repeaters | — |
| `.u_t6.instrn_engine_wrapper` | `tt_instrn_engine_wrapper` | **i_ai_clk** (postdfx) | 4 | 48 | Instruction Engine Wrapper | `u_ie_mwrap` memories |
| `.instrn_engine_wrapper.instrn_engine` | `tt_instrn_engine` | **i_ai_clk** (postdfx) | 4 | 48 | Instruction Engine | — |
| `.instrn_engine.fpu` | `tt_fpu_v2` | **i_ai_clk** (fpu gated) | 4 | 48 | FPU Controller (decodes MVMUL etc.) | — |
| `.instrn_engine.fpu.srcb_regs` | `tt_srcb_registers` | i_ai_clk | 4 | 48 | SRCB registers | — |
| `.instrn_engine.fpu.srcb_metadata` | `tt_srcb_metadata` | i_ai_clk | 4 | 48 | SRCB metadata | — |
| `.instrn_engine.u_trisc[0..2]` | `tt_trisc` | **i_ai_clk** | **12** | **144** | TRISC Thread (3 per core: TRISC0/1/2) | — |
| `.u_trisc[*].u_trisc_control` | `tt_risc_wrapper` | **i_ai_clk** (trisc gated) | 12 | 144 | TRISC RISC-V wrapper | — |
| `.u_trisc_control.u_risc_core` | `tt_riscv_core` | **i_ai_clk** | 12 | 144 | TRISC RISC-V Core | — |
| `.u_risc_core.u_risc_mailbox` | `tt_risc_mailbox` | i_ai_clk (aon) | 12 | 144 | TRISC mailbox | — |
| `.u_trisc[*].u_trisc_mop_buf` | `tt_multi_write_fifo` | i_ai_clk | 12 | 144 | MOP instruction buffer | — |
| `.instrn_engine.sfpu_wrapper` | `tt_sfpu_wrapper` | **i_ai_clk** | 4 | 48 | SFPU Wrapper | — |
| `.sfpu_wrapper.gen_sfpu[*].u_sfpu` | `tt_sfpu` | **i_ai_clk** (gated) | ×(4×N) | — | SFPU Instance | `u_sfpu_lregs[*]` (FF, not SRAM) |
| `.u_sfpu.u_sfpu_lregs[*]` | `tt_sfpu_lregs` | **i_ai_clk** | — | — | **SFPU Local Registers (flip-flop, NOT SRAM)** | — |
| `.u_sfpu.u_mad` | `tt_t6_com_sfpu_mad` | i_ai_clk | ×N | — | SFPU FMA (MAD stage) | — |
| `.u_sfpu.u_prng` | `tt_t6_com_prng` | i_ai_clk | ×N | — | SFPU PRNG | — |
| `.instrn_engine.u_ie_mwrap` ★ | `tt_instrn_engine_mem_wrappers` | **i_ai_clk** (postdfx) | 4 | 48 | **TRISC Memory Wrapper (9 SRAMs/t6)** | 9 types below |
| `.u_ie_mwrap.gen_trisc_icache[0].u_trisc_icache` ★ | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` | **i_ai_clk** | **4** | **48** | **TRISC0 Instruction Cache (512×72b)** | `gen_trisc_icache[0].u_trisc_icache` |
| `.u_ie_mwrap.gen_trisc_icache[1].u_trisc_icache` ★ | `tt_mem_wrap_256x72_sp_wmask_trisc_icache` | **i_ai_clk** | **4** | **48** | **TRISC1 Instruction Cache (256×72b)** | `gen_trisc_icache[1].u_trisc_icache` |
| `.u_ie_mwrap.gen_trisc_icache[2].u_trisc_icache` ★ | `tt_mem_wrap_256x72_sp_wmask_trisc_icache` | **i_ai_clk** | **4** | **48** | **TRISC2 Instruction Cache (256×72b)** | `gen_trisc_icache[2].u_trisc_icache` |
| `.u_ie_mwrap.gen_trisc_icache[3].u_trisc_icache` ★ | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` | **i_ai_clk** | **4** | **48** | **BRISC Instruction Cache (512×72b)** | `gen_trisc_icache[3].u_trisc_icache` |
| `.u_ie_mwrap.gen_trisc_local_mem[0].u_local_mem` ★ | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` | **i_ai_clk** | **4** | **48** | **TRISC0 Local Memory (512×52b)** | `gen_trisc_local_mem[0].u_local_mem` |
| `.u_ie_mwrap.gen_trisc_local_mem[1].u_local_mem` ★ | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` | **i_ai_clk** | **4** | **48** | **TRISC1 Local Memory (512×52b)** | `gen_trisc_local_mem[1].u_local_mem` |
| `.u_ie_mwrap.gen_trisc_local_mem[2].u_local_mem` ★ | `tt_mem_wrap_1024x52_sp_wmask_trisc_local_memory` | **i_ai_clk** | **4** | **48** | **TRISC2/BRISC Local Memory (1024×52b)** | `gen_trisc_local_mem[2].u_local_mem` |
| `.u_ie_mwrap.gen_trisc_local_vec_mem[0].u_vec_mem` ★ | `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory` | **i_ai_clk** | **4** | **48** | **TRISC Vector Local Memory 0 (256×104b)** | `gen_trisc_local_vec_mem[0].u_vec_mem` |
| `.u_ie_mwrap.gen_trisc_local_vec_mem[1].u_vec_mem` ★ | `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory` | **i_ai_clk** | **4** | **48** | **TRISC Vector Local Memory 1 (256×104b)** | `gen_trisc_local_vec_mem[1].u_vec_mem` |

### 5-E T6 L1 SRAM (per tile)

| Full Hierarchy Path | Module | Clock Source | # Inst/tile | Total | Description | Memory Instance(s) |
|---------------------|--------|-------------|------------|-------|-------------|-------------------|
| `.u_l1part` | `tt_t6_l1_partition` | **i_ai_clk** / i_noc_clk | 1 | 12 | **T6 L1 Partition (shared by 4 t6 cores)** | — |
| `.u_l1part.t6_misc` | `tt_t6_misc` | **i_ai_clk** / i_noc_clk | 1 | 12 | T6 Misc (DFT, power, EDC misc) | — |
| `.u_l1part.u_l1w2` | `tt_t6_l1_wrap2` | **i_ai_clk** (postdfx) | 1 | 12 | L1 Wrap Level 2 | `u_l1_mem_wrap` |
| `.u_l1w2.u_l1_mem_wrap` ★ | `tt_t6_l1_mem_wrap` | **i_ai_clk** (postdfx) | 1 | 12 | **T6 L1 SRAM Bank Wrapper (64 macros/tile)** | `gen_sbank[4].gen_bank[4].gen_sub_bank[4].u_sub_mwrap` |
| `.u_l1_mem_wrap.gen_sbank[0..3].gen_bank[0..3].gen_sub_bank[0..3].u_sub_mwrap` ★ | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` | **i_ai_clk** | **64** (4×4×4) | **768** | **T6 L1 Data SRAM (1024×128b = 16 KB)** | `u_sub_mwrap` |
| `.u_l1w2.u_l1w` | `tt_t6_l1_wrap` | **i_ai_clk** | 1 | 12 | L1 Wrap Level 1 (arbiter + port interfaces) | — |
| `.u_l1w.u_l1` | `tt_t6_l1` | **i_ai_clk** | 1 | 12 | L1 Logic (ECC SECDED, superarb, addr decode) | — |
| `.u_l1w.u_l1_sarb[*]` | `tt_t6_l1_superarb` | **i_ai_clk** | ×N | — | L1 Super-Arbiter (multi-client) | — |
| `.u_l1w2.u_l1w.u_*_adp[*]` | `tt_t6_l1_sbank_intf_*` | — | ×N | — | L1 bank interface adapters (rd/wr/rw) | — |
| `.u_l1part.edc_misc_bus_repeater` | `tt_edc1_serial_bus_repeater` | i_ai_clk (postdfx) | 1 | 12 | EDC misc bus repeater | — |
| `.u_l1part.edc_serial_bus_repeater` | `tt_edc1_serial_bus_repeater` | i_ai_clk (postdfx) | 1 | 12 | EDC serial bus repeater | — |

---

## 6. Complete SRAM Count Table

| # | Full Hierarchy Path (template) | Module | Size | Clock | Per Tile | Tile Count | **Total** | Description |
|---|-------------------------------|--------|------|-------|----------|------------|-----------|-------------|
| 1 | `…u_l1_mem_wrap.gen_sbank[4].gen_bank[4].gen_sub_bank[4].u_sub_mwrap` | `tt_mem_wrap_1024x128_sp_nomask_selftest_t6_l1` | 1024×128b (16KB) | **i_ai_clk** | 64 | 12 | **768** | T6 L1 Data SRAM |
| 2 | `…u_ie_mwrap.gen_trisc_icache[0].u_trisc_icache` | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` | 512×72b | **i_ai_clk** | 4 | 12 | **48** | TRISC0 I-Cache |
| 3 | `…u_ie_mwrap.gen_trisc_icache[1].u_trisc_icache` | `tt_mem_wrap_256x72_sp_wmask_trisc_icache` | 256×72b | **i_ai_clk** | 4 | 12 | **48** | TRISC1 I-Cache |
| 4 | `…u_ie_mwrap.gen_trisc_icache[2].u_trisc_icache` | `tt_mem_wrap_256x72_sp_wmask_trisc_icache` | 256×72b | **i_ai_clk** | 4 | 12 | **48** | TRISC2 I-Cache |
| 5 | `…u_ie_mwrap.gen_trisc_icache[3].u_trisc_icache` | `tt_mem_wrap_512x72_sp_wmask_trisc_icache` | 512×72b | **i_ai_clk** | 4 | 12 | **48** | BRISC I-Cache |
| 6 | `…u_ie_mwrap.gen_trisc_local_mem[0].u_local_mem` | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` | 512×52b | **i_ai_clk** | 4 | 12 | **48** | TRISC0 Local Memory |
| 7 | `…u_ie_mwrap.gen_trisc_local_mem[1].u_local_mem` | `tt_mem_wrap_512x52_sp_wmask_trisc_local_memory` | 512×52b | **i_ai_clk** | 4 | 12 | **48** | TRISC1 Local Memory |
| 8 | `…u_ie_mwrap.gen_trisc_local_mem[2].u_local_mem` | `tt_mem_wrap_1024x52_sp_wmask_trisc_local_memory` | 1024×52b | **i_ai_clk** | 4 | 12 | **48** | TRISC2/BRISC Local Memory |
| 9 | `…u_ie_mwrap.gen_trisc_local_vec_mem[0].u_vec_mem` | `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory` | 256×104b | **i_ai_clk** | 4 | 12 | **48** | TRISC Vector Local Memory 0 |
| 10 | `…u_ie_mwrap.gen_trisc_local_vec_mem[1].u_vec_mem` | `tt_mem_wrap_256x104_sp_wmask_trisc_local_memory` | 256×104b | **i_ai_clk** | 4 | 12 | **48** | TRISC Vector Local Memory 1 |
| 11 | `…memory_wrapper.gen_l1_dcache_data[0..15].l1_dcache_data` | `TTOverlayConfig_rockettile_dcache_data_arrays_0_ext` | — | **i_dm_clk** | 16 | 12 | **192** | Overlay CPU L1 D-Cache Data |
| 12 | `…memory_wrapper.gen_l1_dcache_tag[0..7].l1_dcache_tag` | `TTOverlayConfig_rockettile_dcache_tag_array_ext` | — | **i_dm_clk** | 8 | 12 | **96** | Overlay CPU L1 D-Cache Tag |
| 13 | `…memory_wrapper.gen_l1_icache_data[0..15].l1_icache_data` | `TTOverlayConfig_rockettile_icache_data_arrays_0_ext` | — | **i_dm_clk** | 16 | 12 | **192** | Overlay CPU L1 I-Cache Data |
| 14 | `…memory_wrapper.gen_l1_icache_tag[0..7].l1_icache_tag` | `TTOverlayConfig_rockettile_icache_tag_array_ext` | — | **i_dm_clk** | 8 | 12 | **96** | Overlay CPU L1 I-Cache Tag |
| 15 | `…memory_wrapper.gen_l2_dir[0..3].l2_dir` | `TTOverlayConfig_cc_dir_ext` | — | **i_dm_clk** | 4 | 12 | **48** | Overlay CPU L2 Directory |
| 16 | `…memory_wrapper.gen_l2_banks[0..15].l2_banks` | `TTOverlayConfig_cc_banks_0_ext` | — | **i_dm_clk** | 16 | 12 | **192** | Overlay CPU L2 Data Banks |
| 17 | `…memory_wrapper.gen_cs_32x1024.mem_wrap_32x1024_sp_nomask_overlay_context_switch` | `tt_mem_wrap_32x1024_sp_nomask_overlay_context_switch` | 32×1024b | **i_dm_clk** | 1 | 12 | **12** | Context Switch SRAM (32-entry) |
| 18 | `…memory_wrapper.gen_cs_8x1024.mem_wrap_8x1024_sp_nomask_overlay_context_switch` | `tt_mem_wrap_8x1024_sp_nomask_overlay_context_switch` | 8×1024b | **i_dm_clk** | 1 | 12 | **12** | Context Switch SRAM (8-entry) |
| 19 | `gen_router[1..2][3].trinity_router.tt_router.mem_wrap_*_router_input_north` | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | 256×2048b | **i_noc_clk** | 1 | 2 | **2** | Router North VC Input FIFO |
| 20 | `gen_router[1..2][3].trinity_router.tt_router.mem_wrap_*_router_input_east` | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | 256×2048b | **i_noc_clk** | 1 | 2 | **2** | Router East VC Input FIFO |
| 21 | `gen_router[1..2][3].trinity_router.tt_router.mem_wrap_*_router_input_south` | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | 256×2048b | **i_noc_clk** | 1 | 2 | **2** | Router South VC Input FIFO |
| 22 | `gen_router[1..2][3].trinity_router.tt_router.mem_wrap_*_router_input_west` | `tt_mem_wrap_256x2048_2p_nomask_d2d_router_input_port_selftest` | 256×2048b | **i_noc_clk** | 1 | 2 | **2** | Router West VC Input FIFO |
| 23 | `gen_tensix_neo[x][y].…noc_niu_router_inst.mem_wrap_*_router_input_north` | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | 64×2048b | **i_noc_clk** | 1 | 12 | **12** | Tensix NIU North VC FIFO |
| 24 | `gen_tensix_neo[x][y].…noc_niu_router_inst.mem_wrap_*_router_input_east` | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | 64×2048b | **i_noc_clk** | 1 | 12 | **12** | Tensix NIU East VC FIFO |
| 25 | `gen_tensix_neo[x][y].…noc_niu_router_inst.mem_wrap_*_router_input_south` | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | 64×2048b | **i_noc_clk** | 1 | 12 | **12** | Tensix NIU South VC FIFO |
| 26 | `gen_tensix_neo[x][y].…noc_niu_router_inst.mem_wrap_*_router_input_west` | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | 64×2048b | **i_noc_clk** | 1 | 12 | **12** | Tensix NIU West VC FIFO |
| 27 | `gen_tensix_neo[x][y].…noc_niu_router_inst.mem_wrap_*_router_input_niu` | `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest` | 64×2048b | **i_noc_clk** | 1 | 12 | **12** | Tensix NIU→NIU VC FIFO |
| 28 | `gen_dispatch_{e/w}.…disp_eng_noc_niu_router_inst.mem_wrap_1024x12_*_noc_endpoint_translation` | `tt_mem_wrap_1024x12_*` | 1024×12b | **i_noc_clk** | ~1 | 2 | **~2** | Dispatch ATT Endpoint Table |
| 29 | `gen_dispatch_{e/w}.…disp_eng_noc_niu_router_inst.mem_wrap_32x1024_*_noc_routing_translation` | `tt_mem_wrap_32x1024_*` | 32×1024b | **i_noc_clk** | ~1 | 2 | **~2** | Dispatch ATT Routing Table |

### Summary by Clock Domain

| Clock | SRAM Count | Key Blocks |
|-------|-----------|------------|
| **i_ai_clk** | **1,212** | T6 L1 (768) + TRISC I-Cache (192) + TRISC Local Mem (144) + TRISC Vec Mem (96) |
| **i_dm_clk** | **840** | Overlay L1 D/I Cache (576) + L2 Dir/Banks (240) + Context Switch (24) |
| **i_noc_clk** | **≥62** | Router VC FIFOs (8) + NIU VC FIFOs (60) + ATT (~4+) |
| **Total SRAM** | **≈ 2,114** | |

### Register Files (non-SRAM)

| # | Full Hierarchy Path | Module | Type | # Inst/tile | Total | Description |
|---|---------------------|--------|------|------------|-------|-------------|
| A | `…gen_fp_cols[16].mtile_and_dest.dest_slice.dest_reg_bank[2][4]` | `tt_reg_bank` | Latch array | 1,024 | **12,288** | DEST Double-Buffer Regfile (SETS=256×32b) |
| B | `…gen_fp_cols[16].mtile_and_dest.u_fpu_mtile.u_srca_reg_slice` | `tt_srca_reg_slice` | Latch array | 128 | **1,536** | SRCA Register Slice (48×16×19b) |
| C | `…sfpu_wrapper.gen_sfpu[*].u_sfpu.u_sfpu_lregs[*]` | `tt_sfpu_lregs` | Flip-flop | — | — | SFPU Local Registers (4×32b, NOT SRAM) |

---

## 7. N1B0 vs Trinity Baseline Delta

### 7-A Grid-Level Differences

| Aspect | Trinity Baseline (20260221) | N1B0 (20250301/used_in_n1) |
|--------|----------------------------|---------------------------|
| Middle column NIU (X=1,2 Y=4) | `trinity_noc2axi_n_opt` (NIU only) | `trinity_noc2axi_router_ne/nw_opt` (combined NIU+Router) |
| Router tiles Y=3 | `gen_router[1..2][3]` → `trinity_router` | `gen_router[1..2][3]` → **EMPTY** (no module) |
| Router location | Separate tile at Y=3 | Embedded in `noc2axi_router_*_opt` spanning Y=4+Y=3 |
| AI/DM clock inputs | Single `i_ai_clk`, `i_dm_clk` | Per-column `i_ai_clk[SizeX]`, `i_dm_clk[SizeX]` |
| Clock distribution | Direct wiring | `trinity_clock_routing_t` struct propagating south Y=4→Y=0 |
| X-axis NoC connections | Generate loop | Manual assigns (allows repeater insertion) |
| Inter-column repeaters | None | `tt_noc_repeaters(NUM=4)×2` @ Y=4, `tt_noc_repeaters(NUM=6)×2` @ Y=3 |
| PRTN chain | Absent | 4-column per-column daisy chain Y=2→Y=1→Y=0 |
| ISO_EN port | Absent | `[11:0]` (3 bits × 4 cols = 12 power isolation enables) |
| `i_edc_reset_n` | EDC reset | Repurposed as `power_good` in clock_routing |
| tile_t enum | `NOC2AXI_N_OPT` | `NOC2AXI_ROUTER_NE/NW_OPT` (replaces N_OPT) |
| **T6/Dispatch/Overlay** | — | **Same module structure** (tt_tensix_with_l1, tt_overlay_wrapper, etc.) |

### 7-B L1 SRAM Differences (Mimir vs Trinity L1 Config)

| Parameter | Trinity 20260221 (tt_mimir_l1_cfg.svh) | N1B0 20250301 (tt_trin_l1_cfg.svh) |
|-----------|----------------------------------------|-------------------------------------|
| SBANK_CNT | 4 | 4 |
| BANK_IN_SBANK | 4 | **16** (4×) |
| SUB_BANK_CNT | 4 | 4 |
| **Total macros/tile** | **64** | **256** (4×) |
| SRAM macro type | `MWRAP2X2048X128` (dual 2048×128) | `MWRAP768X128` (768×128, shallower) |
| NOC_RD_PORT_CNT | 2 | **4** |
| NOC_WR_PORT_CNT | 2 | **4** |
| **Total L1 SRAM (×12 tiles)** | **768** | **3,072** |

### 7-C N1B0 NOC2AXI_ROUTER Clock Routing

```
N1B0 clock entry at Y=4:
  i_ai_clk[x] ─→ clock_routing_in[x][4].ai_clk
  i_dm_clk[x] ─→ clock_routing_in[x][4].dm_clk
  i_noc_clk   ─→ direct to all tiles (not in routing struct)
  i_axi_clk   ─→ direct to all NIU tiles

NOC2AXI_ROUTER_NE/NW_OPT drives Y=3 via:
  router_o_ai_clk → clock_routing[x][3].ai_clk  (= clock_routing_in[x][4] propagated)
  router_o_dm_clk → clock_routing[x][3].dm_clk

Tensix tiles Y=0..2 receive:
  clock_routing_in[x][y].ai_clk = i_ai_clk[x]  (same column clock)
  clock_routing_in[x][y].dm_clk = i_dm_clk[x]
```

---

## 8. Clock Domain Tree (Memory Focus)

```
i_ai_clk ──────────────────────────────────────────────────────────
  gen_tensix_neo[12 tiles].tt_tensix_with_l1
  └─ t6[4].neo.u_t6  (×48 total)
     ├─ gen_gtile[2].u_fpu_gtile (×96)
     │  └─ gen_fp_cols[16].mtile_and_dest (×1,536)
     │     ├─◆ u_fpu_mtile.u_srca_reg_slice  (latch_array) ...... ×1,536
     │     └─◆ dest_slice.dest_reg_bank[2][4] (latch_array) ..... ×12,288
     └─ instrn_engine_wrapper.u_ie_mwrap  (×48)
        ├─★ gen_trisc_icache[0].u_trisc_icache  (512×72b) ....... ×48
        ├─★ gen_trisc_icache[1].u_trisc_icache  (256×72b) ....... ×48
        ├─★ gen_trisc_icache[2].u_trisc_icache  (256×72b) ....... ×48
        ├─★ gen_trisc_icache[3].u_trisc_icache  (512×72b) ....... ×48   [BRISC]
        ├─★ gen_trisc_local_mem[0].u_local_mem  (512×52b) ....... ×48
        ├─★ gen_trisc_local_mem[1].u_local_mem  (512×52b) ....... ×48
        ├─★ gen_trisc_local_mem[2].u_local_mem  (1024×52b) ...... ×48
        ├─★ gen_trisc_local_vec_mem[0].u_vec_mem (256×104b) ..... ×48
        └─★ gen_trisc_local_vec_mem[1].u_vec_mem (256×104b) ..... ×48
  └─ u_l1part.u_l1w2.u_l1_mem_wrap  (×12)
     └─★ gen_sbank[4].gen_bank[4].gen_sub_bank[4].u_sub_mwrap
           (tt_mem_wrap_1024x128, 16KB each) ..................... ×768

i_dm_clk ──────────────────────────────────────────────────────────
  gen_tensix_neo[12 tiles] → overlay_wrapper.memory_wrapper  (×12)
  ├─★ gen_l1_dcache_data[16].l1_dcache_data ..................... ×192
  ├─★ gen_l1_dcache_tag[8].l1_dcache_tag ....................... ×96
  ├─★ gen_l1_icache_data[16].l1_icache_data ..................... ×192
  ├─★ gen_l1_icache_tag[8].l1_icache_tag ....................... ×96
  ├─★ gen_l2_dir[4].l2_dir ..................................... ×48
  ├─★ gen_l2_banks[16].l2_banks ................................ ×192
  ├─★ gen_cs_32x1024.mem_wrap_32x1024_sp_nomask_* .............. ×12
  └─★ gen_cs_8x1024.mem_wrap_8x1024_sp_nomask_* ................ ×12

i_noc_clk ─────────────────────────────────────────────────────────
  gen_router[2].trinity_router.tt_router
  ├─★ mem_wrap_*_router_input_north (256×2048b, 2-port) ......... ×2
  ├─★ mem_wrap_*_router_input_east  (256×2048b, 2-port) ......... ×2
  ├─★ mem_wrap_*_router_input_south (256×2048b, 2-port) ......... ×2
  └─★ mem_wrap_*_router_input_west  (256×2048b, 2-port) ......... ×2
  gen_tensix_neo[12].noc_niu_router_inst
  ├─★ mem_wrap_*_router_input_north (64×2048b, 2-port) .......... ×12
  ├─★ mem_wrap_*_router_input_east  (64×2048b, 2-port) .......... ×12
  ├─★ mem_wrap_*_router_input_south (64×2048b, 2-port) .......... ×12
  ├─★ mem_wrap_*_router_input_west  (64×2048b, 2-port) .......... ×12
  └─★ mem_wrap_*_router_input_niu   (64×2048b, 2-port) .......... ×12
  gen_dispatch[2].disp_eng_noc_niu_router_inst
  ├─★ mem_wrap_1024x12_*_noc_endpoint_translation ............... ×~2
  └─★ mem_wrap_32x1024_*_noc_routing_translation ................ ×~2
```

---

*Generated 2026-03-18 — Trinity 20260221 baseline + N1B0 20250301 delta (M11+M12 memory archive)*
