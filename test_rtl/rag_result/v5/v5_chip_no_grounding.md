# Trinity N1B0 — Hardware Design Document (HDD)

> **Pipeline ID:** tt_20260221
> **Document Version:** v5 (No Grounding)
> **Generated:** 2026-04-27

---

## 1. Overview

Trinity N1B0 is a domain-specific AI accelerator SoC designed by Tenstorrent for high-throughput tensor computation workloads. The chip targets inference and training acceleration through a tiled architecture of heterogeneous compute elements interconnected by a packet-switched Network-on-Chip (NoC) fabric.

**Key Features:**

- 4×5 grid topology with 12 Tensix compute tiles, plus specialized ARC, DRAM, ETH, PCI, and Router tiles
- Dual-issue SFPU (Scalar Floating-Point Unit) per Tensix tile with dedicated register files (`tt_sfpu_lregs`)
- 2D mesh NoC with DOR/Tendril/Dynamic routing, SECDED ECC protection, and asynchronous clock-domain crossing FIFOs
- NIU (Network Interface Unit) providing AXI bridge with master timeout watchdog (`tt_niu_mst_timeout`)
- Multi-domain clock architecture: `ai_clk`, `noc_clk`, `dm_clk`, `ref_clk` with dividers, buffers, and gating cells
- Harvest-aware design with robust synchronization (`tt_harvest_robust_sync`) for defective-tile bypass
- EDC serial ring bus for configuration and debug

---

## 2. Package Constants and Grid

| Parameter | Value | Description |
|-----------|-------|-------------|
| **GridSizeX** | 5 | Columns in the tile grid |
| **GridSizeY** | 4 | Rows in the tile grid |
| **Total Grid Slots** | 20 | 5 × 4 physical positions |
| **NumTensix** | 12 | Active Tensix compute tiles |
| **NumDRAM** | 2 | HBM/GDDR controller tiles |
| **NumETH** | 2 | Ethernet/SerDes tiles |
| **NumPCI** | 1 | PCIe endpoint tile |
| **NumARC** | 1 | ARC management processor tile |
| **NumRouter** | 2 | Dedicated NoC router tiles |

**Grid Layout (4 rows × 5 columns):**

```
Col:    0        1        2        3        4
     ┌────────┬────────┬────────┬────────┬────────┐
R3   │  ETH   │ TENSIX │ TENSIX │ TENSIX │  ETH   │
     ├────────┼────────┼────────┼────────┼────────┤
R2   │ ROUTER │ TENSIX │ TENSIX │ TENSIX │  DRAM  │
     ├────────┼────────┼────────┼────────┼────────┤
R1   │  ARC   │ TENSIX │ TENSIX │ TENSIX │  DRAM  │
     ├────────┼────────┼────────┼────────┼────────┤
R0   │  PCI   │ TENSIX │ TENSIX │ TENSIX │ ROUTER │
     └────────┴────────┴────────┴────────┴────────┘
```

---

## 3. Top-Level Ports

| Port Name | Direction | Width | Clock Domain | Description |
|-----------|-----------|-------|--------------|-------------|
| `pci_rx_p/n` | Input | SerDes | `ref_clk` | PCIe Gen4/5 receive differential pairs |
| `pci_tx_p/n` | Output | SerDes | `ref_clk` | PCIe Gen4/5 transmit differential pairs |
| `pci_refclk_p/n` | Input | 1 | — | PCIe reference clock |
| `pci_perst_n` | Input | 1 | async | PCIe fundamental reset |
| `dram_dq` | Bidir | per-channel | `dm_clk` | DRAM data bus |
| `dram_addr` | Output | per-channel | `dm_clk` | DRAM address/command |
| `dram_ck_p/n` | Output | per-channel | `dm_clk` | DRAM differential clock |
| `eth_rx_p/n` | Input | SerDes | `ref_clk` | Ethernet receive lanes |
| `eth_tx_p/n` | Output | SerDes | `ref_clk` | Ethernet transmit lanes |
| `ai_clk` | Input | 1 | — | Primary AI compute clock |
| `noc_clk` | Input | 1 | — | NoC fabric clock |
| `ref_clk` | Input | 1 | — | Reference clock for PLLs |
| `reset_n` | Input | 1 | async | Chip-level active-low reset |
| `jtag_tck` | Input | 1 | — | JTAG test clock |
| `jtag_tms` | Input | 1 | `jtag_tck` | JTAG test mode select |
| `jtag_tdi` | Input | 1 | `jtag_tck` | JTAG test data in |
| `jtag_tdo` | Output | 1 | `jtag_tck` | JTAG test data out |
| `harvest_fuses` | Input | 20 | async | Tile harvest/disable fuse inputs |
| `edc_sdi` | Input | 1 | `ref_clk` | EDC serial data in |
| `edc_sdo` | Output | 1 | `ref_clk` | EDC serial data out |

---

## 4. Module Hierarchy

```
trinity (top)
├── tt_grid_4x5                          — Tile grid instantiation wrapper
│   ├── tt_tensix_tile [×12]             — Tensix compute tile
│   │   ├── tt_fpu                       — Fused multiply-add FPU
│   │   ├── tt_sfpu                      — Scalar FPU
│   │   │   ├── tt_sfpu_lregs           — SFPU local register file
│   │   │   └── tt_sfpu_instrn_resources_used — Instruction resource tracker
│   │   ├── tt_tdma                      — Tile DMA engine
│   │   ├── tt_l1_cache                  — L1 SRAM (1 MB per tile)
│   │   ├── tt_dispatch_east             — East dispatch engine
│   │   ├── tt_dispatch_west             — West dispatch engine
│   │   └── tt_noc_router_tile           — Per-tile NoC router
│   ├── tt_dram_tile [×2]                — DRAM controller tile
│   ├── tt_eth_tile [×2]                 — Ethernet SerDes tile
│   ├── tt_pci_tile [×1]                 — PCIe endpoint tile
│   ├── tt_arc_tile [×1]                 — ARC management processor
│   └── tt_router_tile [×2]              — Dedicated router-only tile
├── tt_noc_fabric                        — NoC interconnect top
│   ├── tt_noc_repeaters_cardinal [×N]   — Cardinal-direction repeaters
│   ├── noc_arbiter_tree [×N]            — Priority-based arbitration trees
│   ├── tt_skid_buffer_new_assertion_off — Skid buffers for decoupling
│   ├── tt_noc_secded_chk_corr_116_10   — SECDED ECC (116-bit data, 10-bit check)
│   ├── tt_noc_async_fifo_wr_side_reset  — Async FIFO reset synchronizer
│   ├── tt_upf_async_fifo               — Async FIFO for CDC
│   └── tt_noc_sync3_pulse              — 3-stage pulse synchronizer
├── tt_niu_top [×N]                      — Network Interface Unit
│   ├── tt_noc2axi_local_reg [×3]       — NoC-to-AXI register bridge
│   └── tt_niu_mst_timeout [×5]         — AXI master timeout watchdog
├── tt_clock_top                         — Clock generation & distribution
│   ├── tt_pll [×M]                     — Phase-locked loops
│   ├── tt_clkdiv2 [×N]                 — Divide-by-2 clock dividers
│   ├── tt_clkbuf [×N]                  — Clock buffers
│   └── tt_clkgater / tt_clk_gater [×N] — Clock gating cells
├── tt_reset_top                         — Reset tree & sequencing
│   └── tt_harvest_robust_sync          — Harvest signal synchronizer
├── tt_edc_ring                          — EDC serial configuration ring
└── tt_dfx_top                           — DFX/JTAG/scan wrapper
```
