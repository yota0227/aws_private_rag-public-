# N1B0 NPU — Full Hardware Design Document

> **Pipeline ID:** tt_20260221
> **Version:** v8
> **RAG:** v7 pipeline + max_results=50
> **Method:** 5-round topic search → per-topic files → merge
> **Sources:** v8_chip_no_grounding, v8_chip_grounded, v8_edc, v8_noc, v8_overlay
> **Generated:** 2026-04-29

---

## 1. Overview

N1B0 is the Trinity NPU integrated into the N1 SoC. Top module `trinity` implements a **4×5 tile mesh** (SizeX=4, SizeY=5, 20 tiles, 106 top-level ports).

| Tile Type | Count | RTL Module | Position |
|-----------|-------|------------|----------|
| TENSIX | 12 | `tt_tensix_with_l1` | Y=0..2, X=0..3 |
| NOC2AXI_NE_OPT | 1 | `trinity_noc2axi_ne_opt` | (X=0, Y=4) |
| NOC2AXI_ROUTER_NE_OPT | 1 | `trinity_noc2axi_router_ne_opt` | (X=1, Y=4+3) |
| NOC2AXI_ROUTER_NW_OPT | 1 | `trinity_noc2axi_router_nw_opt` | (X=2, Y=4+3) |
| NOC2AXI_NW_OPT | 1 | `trinity_noc2axi_nw_opt` | (X=3, Y=4) |
| DISPATCH_E | 1 | `tt_dispatch_top_east` | (X=0, Y=3) |
| DISPATCH_W | 1 | `tt_dispatch_top_west` | (X=3, Y=3) |
| ROUTER | 2 | (empty) | (X=1,2, Y=3) |

EnableDynamicRouting=1, DMCoresPerCluster=8, ROUTER placeholder empty by design.

---

## 2. Package Constants and Grid

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`

### 2.1 Constants (13 localparams)

| Constant | Value |
|----------|-------|
| SizeX | 4 |
| SizeY | 5 |
| NumNodes | 20 |
| NumTensix | 12 |
| NumNoc2Axi | 4 |
| NumDispatch | 2 |
| NumApbNodes | 4 |
| NumDmComplexes | 14 |
| DMCoresPerCluster | 8 |
| TensixPerCluster | 4 |
| EnableDynamicRouting | 1'b1 |
| NumAxes | 2 |
| NumDirections | 2 |

### 2.2 tile_t enum (3-bit, 8 members)

| Value | Name | Position |
|-------|------|----------|
| 3'd0 | TENSIX | Y=0..2, X=0..3 |
| 3'd1 | NOC2AXI_NE_OPT | (X=0, Y=4) |
| 3'd2 | NOC2AXI_ROUTER_NE_OPT | (X=1, Y=4+3) |
| 3'd3 | NOC2AXI_ROUTER_NW_OPT | (X=2, Y=4+3) |
| 3'd4 | NOC2AXI_NW_OPT | (X=3, Y=4) |
| 3'd5 | DISPATCH_E | (X=0, Y=3) |
| 3'd6 | DISPATCH_W | (X=3, Y=3) |
| 3'd7 | ROUTER | (X=1,2, Y=3) — empty |

### 2.3 Endpoint Index (EP = x*5+y)

| X | Y | Tile | EP |
|---|---|------|----|
| 0 | 0 | TENSIX | 0 |
| 0 | 1 | TENSIX | 1 |
| 0 | 2 | TENSIX | 2 |
| 0 | 3 | DISPATCH_E | 3 |
| 0 | 4 | NOC2AXI_NE_OPT | 4 |
| 1 | 0 | TENSIX | 5 |
| 1 | 1 | TENSIX | 6 |
| 1 | 2 | TENSIX | 7 |
| 1 | 3 | ROUTER | 8 |
| 1 | 4 | NOC2AXI_ROUTER_NE_OPT | 9 |
| 2 | 0 | TENSIX | 10 |
| 2 | 1 | TENSIX | 11 |
| 2 | 2 | TENSIX | 12 |
| 2 | 3 | ROUTER | 13 |
| 2 | 4 | NOC2AXI_ROUTER_NW_OPT | 14 |
| 3 | 0 | TENSIX | 15 |
| 3 | 1 | TENSIX | 16 |
| 3 | 2 | TENSIX | 17 |
| 3 | 3 | DISPATCH_W | 18 |
| 3 | 4 | NOC2AXI_NW_OPT | 19 |

### 2.4 Enums and Structs

- noc_axis_t: Y_AXIS=1'b0, X_AXIS=1'b1
- noc_direction_t: POSITIVE=1'b0, NEGATIVE=1'b1
- trinity_clock_routing_t: ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, dm_uncore_clk_reset_n, tensix_reset_n, power_good

### 2.5 Grid

```
         X=0              X=1                   X=2                  X=3
Y=4:    | NIU_NE EP=4 | NIU_ROUTER_NE EP=9   NIU_ROUTER_NW EP=14| NIU_NW EP=19|
Y=3:    | DISP_E EP=3 | [ROUTER EP=8]        [ROUTER EP=13]      | DISP_W EP=18|
Y=2:    | T6[0][2]    | T6[1][2]             T6[2][2]             | T6[3][2]    |
Y=1:    | T6[0][1]    | T6[1][1]             T6[2][1]             | T6[3][1]    |
Y=0:    | T6[0][0]    | T6[1][0]             T6[2][0]             | T6[3][0]    |
```


---

## 3. Top-Level Ports (106 total)

### 3.1 AXI Interface (39 ports) *(v8 NEW — was 0% in v7)*

| Port | Direction | Description |
|------|-----------|-------------|
| i_axi_clk | input | AXI clock |
| npu_out_awvalid | output | AW channel valid |
| npu_out_awready | input | AW channel ready |
| npu_out_id_t | output | AXI transaction ID |
| npu_out_addr_t | output | AXI address |
| npu_out_awlock | output | AW lock |
| npu_out_user_t | output | AW user signal |
| npu_out_wvalid | output | W channel valid |
| npu_out_wlast | output | W channel last beat |
| npu_out_wready | input | W channel ready |
| npu_out_bvalid | input | B channel valid |
| npu_out_bready | output | B channel ready |
| npu_out_arvalid | output | AR channel valid |
| npu_out_arlock | output | AR lock |
| npu_out_arready | input | AR channel ready |
| npu_out_rvalid | input | R channel valid |
| npu_out_rlast | input | R channel last beat |
| npu_out_rready | output | R channel ready |
| *(+ npu_in_* slave ports, axi_pkg typed signals — 39 total)* | | |

### 3.2 SFR Memory Config (17 ports) *(v8 NEW — was 0% in v7)*

| Port | Width | Direction |
|------|-------|-----------|
| SFR_RF_2P_HSC_QNAPA | 1 | input |
| SFR_RF_2P_HSC_QNAPB | 1 | input |
| SFR_RF_2P_HSC_EMAA[2:0] | 3 | input |
| SFR_RF_2P_HSC_EMAB[2:0] | 3 | input |
| SFR_RF_2P_HSC_EMASA | 1 | input |
| SFR_RF_2P_HSC_RAWL | 1 | input |
| SFR_RF_2P_HSC_RAWLM[1:0] | 2 | input |
| SFR_RA1_HS_MCS[1:0] | 2 | input |
| SFR_RA1_HS_MCSW | 1 | input |
| SFR_RA1_HS_ADME[2:0] | 3 | input |
| SFR_RF1_HS_MCS[1:0] | 2 | input |
| SFR_RF1_HS_MCSW | 1 | input |
| SFR_RF1_HS_ADME[2:0] | 3 | input |
| SFR_RF1_HD_MCS[1:0] | 2 | input |
| SFR_RF1_HD_MCSW | 1 | input |
| SFR_RF1_HD_ADME[2:0] | 3 | input |

### 3.3 EDC APB + IRQ (16 ports) *(v8: +5 IRQ outputs)*

| Port | Width | Direction |
|------|-------|-----------|
| i_edc_reset_n | 1 | input |
| i_edc_apb_psel | 1 | input |
| i_edc_apb_penable | 1 | input |
| i_edc_apb_pwrite | 1 | input |
| i_edc_apb_pprot[2:0] | 3 | input |
| i_edc_apb_paddr[5:0] | 6 | input |
| i_edc_apb_pwdata[31:0] | 32 | input |
| i_edc_apb_pstrb[3:0] | 4 | input |
| o_edc_apb_pready | 1 | output |
| o_edc_apb_prdata[31:0] | 32 | output |
| o_edc_apb_pslverr | 1 | output |
| o_edc_fatal_err_irq | 1 | output |
| o_edc_crit_err_irq | 1 | output |
| o_edc_cor_err_irq | 1 | output |
| o_edc_pkt_sent_irq | 1 | output |
| o_edc_pkt_rcvd_irq | 1 | output |

### 3.4 PRTN Power (14 ports) *(v8 NEW — was 0% in v7)*

| Port | Width | Direction | Description |
|------|-------|-----------|-------------|
| TIEL_DFT_MODESCAN | 1 | input | DFT scan mode tie-low |
| PRTNUN_FC2UN_DATA_IN | 1 | input | PRTN FC→UN data input |
| PRTNUN_FC2UN_READY_IN | 1 | input | PRTN FC→UN ready input |
| PRTNUN_FC2UN_CLK_IN | 1 | input | PRTN FC→UN clock input |
| PRTNUN_FC2UN_RSTN_IN | 1 | input | PRTN FC→UN reset input |
| PRTNUN_UN2FC_DATA_OUT[3:0] | 4 | output | PRTN UN→FC data (4 columns) |
| PRTNUN_UN2FC_INTR_OUT[3:0] | 4 | output | PRTN UN→FC interrupt (4 columns) |
| PRTNUN_FC2UN_DATA_OUT[3:0] | 4 | output | PRTN FC→UN data daisy-chain |
| PRTNUN_FC2UN_READY_OUT[3:0] | 4 | output | PRTN FC→UN ready daisy-chain |
| PRTNUN_FC2UN_CLK_OUT[3:0] | 4 | output | PRTN FC→UN clock daisy-chain |
| PRTNUN_FC2UN_RSTN_OUT[3:0] | 4 | output | PRTN FC→UN reset daisy-chain |
| PRTNUN_UN2FC_DATA_IN[3:0] | 4 | input | PRTN UN→FC data input (4 columns) |
| PRTNUN_UN2FC_INTR_IN[3:0] | 4 | input | PRTN UN→FC interrupt input (4 columns) |
| ISO_EN[11:0] | 12 | input | Power island isolation enable (per-Tensix) |

**PRTN Daisy-Chain:** Single FC2UN input → 4-column daisy chain (OUT[3:0]) → per-column UN2FC return. ISO_EN[11:0] = per-Tensix power island isolation.

### 3.5 APB Register (8), Clock/Reset (8+), Tensix Reset (1)

*(unchanged from v7 — see Section 9/10 for details)*

### 3.6 Port Summary

| Category | Count | v7 | v8 | Delta |
|----------|-------|----|----|-------|
| AXI_Interface | 39 | ❌ | ✅ | **+39** |
| SFR_Memory_Config | 17 | ❌ | ✅ | **+17** |
| EDC_APB | 16 | partial | ✅ | **+5 IRQs** |
| PRTN_Power | 14 | ❌ | ✅ | **+14** |
| APB_Register | 8 | ✅ | ✅ | — |
| DM_Clock_Reset | 3 | ✅ | ✅ | — |
| AI_Clock_Reset | 2 | ✅ | ✅ | — |
| NoC_Clock_Reset | 2 | ✅ | ✅ | — |
| Tensix_Reset | 1 | ✅ | ✅ | — |
| Other | 4 | — | — | — |
| **Total** | **106** | **~31** | **106** | **+75** |

---

## 4. Module Hierarchy

```
trinity (top)
├── tt_tensix_with_l1 [×12] — Y=0..2
│   ├── tt_sfpu_lregs
│   ├── tt_sfpu_instrn_resources_used
│   ├── tt_tdma_xy_address_controller
│   ├── tt_tdma_thread_context
│   ├── tt_tdma_rts_rtr_pipe_stage
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (SRAM macro)
├── tt_dispatch_top_east EP=3
├── tt_dispatch_top_west EP=18
├── trinity_noc2axi_ne_opt EP=4
├── trinity_noc2axi_router_ne_opt EP=9/8
├── trinity_noc2axi_router_nw_opt EP=14/13
├── trinity_noc2axi_nw_opt EP=19
├── ROUTER placeholder [×2] — EMPTY
├── EDC:
│   ├── tt_edc1_intf_connector (portless)
│   ├── tt_edc1_serial_bus_repeater (assertion-based)
│   ├── tt_edc1_biu_soc_apb4_wrap → edc1_biu_soc_apb4_inner (APB4 + 5 IRQs)
│   ├── tt_edc1_noc_sec_block_reg → edc1_noc_sec_block_reg_inner
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 [×2]
├── NoC:
│   ├── noc_arbiter_tree (priority arbitration)
│   ├── tt_noc_repeaters_cardinal (NoC package connection)
│   ├── tt_upf_async_fifo (CDC FIFO)
│   ├── tt_noc_async_fifo_wr_side_reset (reset sync)
│   ├── tt_noc_sync3_pulse (pulse CDC)
│   ├── tt_skid_buffer_new_assertion_off (decoupling)
│   ├── tt_noc_secded_chk_corr_116_10 (SECDED 116b/10b)
│   ├── tt_harvest_robust_sync (robust sync)
│   ├── tt_niu_mst_timeout (configurable timeout)
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 [×2+]
├── DFX:
│   ├── tt_instrn_engine_wrapper_dfx (11in/9out, iJTAG)
│   │   ← from: tt_t6_l1_partition, tt_fpu_gtile_0/1
│   ├── tt_disp_eng_noc_niu_router_dfx (10in/7out, iJTAG)
│   │   ← from: tt_disp_eng_overlay_wrapper_dfx, tt_disp_eng_l1_partition_dfx
│   ├── tt_disp_eng_l1_partition_dfx (7in/3out, iJTAG)
│   ├── tt_disp_eng_overlay_wrapper_dfx (7in/3out, iJTAG) ← v8 NEW
│   ├── noc_routing_translation_selftest (ATT BIST)
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 [×3+]
├── Clock: tt_clkdiv2, tt_clkbuf, tt_clkgater, tt_clk_gater
└── SMN: tt_smn_clkdiv(5/3), tt_smn_repeater_struct(16/8)
```

---

## 5. Compute Tile — Tensix

### 5.1 SFPU
- **tt_sfpu_lregs:** register file, transpose/shift, parity
- **tt_sfpu_instrn_resources_used:** R/W hazards, stalls

### 5.2 TDMA (3 sub-modules)
- **tt_tdma_xy_address_controller:** DMA address generation
- **tt_tdma_thread_context:** thread context, multi-channel DMA
- **tt_tdma_rts_rtr_pipe_stage:** pipelined RTS/RTR arbitration

### 5.3 L1
- **tt_t6_l1_partition:** 16-bank SRAM, EDC sram modport

### 5.4 FDS Registers
- tt_fds_tensixneo_reg(106/41), tt_fds_dispatch_reg(68/41), tt_cluster_ctrl_t6_l1_csr_reg(38/97)

---

## 6. Dispatch Engine

tt_dispatch_top_east (X=0, Y=3, EP=3), tt_dispatch_top_west (X=3, Y=3, EP=18)

---

## 7. NoC Fabric

Config: EnableDynamicRouting=1, NumAxes=2, NumDirections=2

| Module | Role |
|--------|------|
| noc_arbiter_tree | Priority-based multi-requestor arbitration |
| tt_noc_repeaters_cardinal | NoC package connection/repeater |
| tt_upf_async_fifo | CDC FIFO (different freq write/read clocks) |
| tt_noc_async_fifo_wr_side_reset | Write/read side reset generation |
| tt_noc_sync3_pulse | Pulse synchronization between clock domains |
| tt_skid_buffer_new_assertion_off | Input/output decoupling |
| tt_noc_secded_chk_corr_116_10 | SECDED on 116-bit data + 10-bit check |
| tt_harvest_robust_sync | Robust harvest synchronization |
| tt_niu_mst_timeout | Configurable timeout → interrupt |

Bridge: noc2axi_router_nw_opt + tt_mem_wrap_32x1024_2p_nomask(ATT) + selftest(BIST)

---

## 8. NIU — AXI Bridge Tiles

| Tile | Position | EP |
|------|----------|----|
| trinity_noc2axi_ne_opt | (X=0, Y=4) | 4 |
| trinity_noc2axi_router_ne_opt | (X=1, Y=4+3) | 9/8 |
| trinity_noc2axi_router_nw_opt | (X=2, Y=4+3) | 14/13 |
| trinity_noc2axi_nw_opt | (X=3, Y=4) | 19 |

---

## 9. Clock Architecture

**trinity_clock_routing_t struct:** ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, dm_uncore_clk_reset_n, tensix_reset_n, power_good

| Domain | Signal | Width | Scope |
|--------|--------|-------|-------|
| AXI | i_axi_clk | 1 | Global |
| NoC | i_noc_clk | 1 | Global |
| AI | i_ai_clk[SizeX-1:0] | 4 | Per-column |
| DM | i_dm_clk[SizeX-1:0] | 4 | Per-column |

Modules: tt_clkdiv2 (÷2), tt_clkbuf (buffer), tt_clkgater/tt_clk_gater (gating with hysteresis + test mode), tt_smn_clkdiv (SMN multi-domain from noc_clk)

---

## 10. Reset Architecture

| Reset | Width | Scope |
|-------|-------|-------|
| i_noc_reset_n | 1 | Global NoC |
| i_ai_reset_n[3:0] | 4 | Per-column AI |
| i_tensix_reset_n[11:0] | 12 | Per-Tensix |
| i_edc_reset_n | 1 | EDC |
| i_dm_core_reset_n[13:0][7:0] | 14×8 | Per-DM-core |
| i_dm_uncore_reset_n[13:0] | 14 | Per-DM-complex uncore |

---

## 11. Power Management *(v8 NEW section)*

### 11.1 PRTN Daisy-Chain

Single input (PRTNUN_FC2UN_DATA/READY/CLK/RSTN_IN) → 4-column daisy chain → per-column output (PRTNUN_FC2UN_*_OUT[3:0]). Return path: PRTNUN_UN2FC_DATA/INTR_IN[3:0] → PRTNUN_UN2FC_DATA/INTR_OUT[3:0].

### 11.2 Power Island Isolation

ISO_EN[11:0] — 12-bit isolation enable, one per Tensix tile. Controls power island boundaries for per-tile power gating.

### 11.3 DFT

TIEL_DFT_MODESCAN — scan mode tie-low input for DFT.

---

## 12. EDC

### 12.1 Interface (tt_edc_pkg.sv)
4 modports: ingress / egress / edc_node / sram. Toggle-handshake: req_tgl / ack_tgl.

### 12.2 Modules
- **tt_edc1_intf_connector:** portless connector
- **tt_edc1_serial_bus_repeater:** i_clk, i_reset_n; assertion-based verification
- **tt_edc1_biu_soc_apb4_wrap → inner:** APB4 bridge + 5 IRQs (fatal/crit/cor/pkt_sent/pkt_rcvd)
- **tt_edc1_noc_sec_block_reg → inner:** NoC security register block

### 12.3 SRAM Macros
RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (×2) — 32×136 dual-port, HSC LVT

---

## 13. SRAM Inventory

| SRAM Macro | Geometry | Type | Instances | Subsystem |
|------------|----------|------|-----------|-----------|
| tt_mem_wrap_32x1024_2p_nomask | 32b×1024 | 2P | ATT | NoC/NIU |
| RF_2P_HSC_LVT_32X136M1FB1WM0DR0 | 32×136 | Dual-port HSC LVT | ×2 EDC + ×2+ NoC + ×3+ DFX + ×12 Tensix | All |

### Memory Config SFR Ports *(v8 NEW)*

17 SFR ports control SRAM timing margins across 4 memory families:
- **SFR_RF_2P_HSC_*:** 2-port HSC SRAM (QNAP, EMA, RAWL)
- **SFR_RA1_HS_*:** 1-port HS SRAM (MCS, MCSW, ADME)
- **SFR_RF1_HS_*:** 1-port HS register file (MCS, MCSW, ADME)
- **SFR_RF1_HD_*:** 1-port HD register file (MCS, MCSW, ADME)

---

## 14. DFX

### 14.1 iJTAG Chain Topology *(v8 enhanced)*

```
tt_instrn_engine_wrapper_dfx (11in/9out)
  ← from: tt_t6_l1_partition, tt_fpu_gtile_0, tt_fpu_gtile_1
  → to: dfd

tt_disp_eng_noc_niu_router_dfx (10in/7out)
  ← from: tt_disp_eng_overlay_wrapper_dfx, tt_disp_eng_l1_partition_dfx
  → to: dfd

tt_disp_eng_l1_partition_dfx (7in/3out)
  ← from: tt_disp_eng_noc_niu_router_dfx → to: dfd

tt_disp_eng_overlay_wrapper_dfx (7in/3out) ← v8 NEW
  ← from: tt_disp_eng_noc_niu_router_dfx → to: dfd
```

### 14.2 ATT BIST
noc_routing_translation_selftest — ATT SRAM self-test

### 14.3 DFX SRAM
RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (×3+)

---

## 15. RTL File Reference

| # | File | Content |
|---|------|---------|
| 1 | used_in_n1/rtl/targets/4x5/trinity_pkg.sv | 13 localparams, tile_t, clock struct |
| 2 | used_in_n1/rtl/trinity.sv | Top module (106 ports) |
| 3-4 | mem_port/legacy variants | Top variants |
| 5 | rtl/trinity_router.sv | Router (placeholder) |
| 6-10 | tt_edc_pkg.sv (5 variants) | EDC interface |

---

## Appendix A: Source Traceability

| Section | Primary Source | v8 Enhancements |
|---------|---------------|-----------------|
| 1 Overview | v8_chip_no_grounding | 106 total ports noted |
| 2 Package/Grid | v8_chip_no_grounding | — |
| 3 Top-Level Ports | v8_chip_no_grounding | **AXI(39), SFR(17), PRTN(14), EDC IRQ(5) — all NEW** |
| 4 Hierarchy | all 5 v8 files | tt_disp_eng_overlay_wrapper_dfx NEW |
| 5 Tensix | v8_overlay | — |
| 6 Dispatch | v8_chip_no_grounding | — |
| 7 NoC | v8_noc | — |
| 8 NIU | v8_chip + noc | — |
| 9 Clock | v8_chip + overlay | — |
| 10 Reset | v8_chip | — |
| 11 Power | v8_chip_no_grounding | **NEW section: PRTN daisy-chain + ISO_EN** |
| 12 EDC | v8_edc | — |
| 13 SRAM | v8_noc + edc + chip | **SFR Memory Config ports NEW** |
| 14 DFX | v8_chip_grounded | **overlay_wrapper_dfx + instrn upstream sources** |
| 15 RTL Files | chip + overlay | — |

## Appendix B: v8 Delta Summary (vs v7)

| # | Enhancement | Detail | Impact |
|---|-------------|--------|--------|
| 1 | **PRTN_Power ports** | 14 ports: PRTNUN_FC2UN/UN2FC daisy chain + ISO_EN[11:0] | P0 gap → resolved |
| 2 | **AXI_Interface ports** | 39 ports: npu_out_*/npu_in_* full AXI master/slave | P0 gap → resolved |
| 3 | **SFR_Memory_Config ports** | 17 ports: SFR_RF_2P_HSC/RA1_HS/RF1_HS/RF1_HD families | P0 gap → resolved |
| 4 | **EDC IRQ outputs** | 5 IRQs: fatal/crit/cor/pkt_sent/pkt_rcvd | P0 gap → resolved |
| 5 | **Power Management section** | NEW section 11: PRTN daisy-chain topology + ISO_EN | Section gap → resolved |
| 6 | **DFX overlay_wrapper_dfx** | New iJTAG chain node (7in/3out) | DFX coverage improved |
| 7 | **DFX instrn upstream** | tt_t6_l1_partition + tt_fpu_gtile_0/1 identified | DFX chain completeness |
| 8 | **max_results 20→50** | No parser change — retrieval improvement only | All above enabled by this |

---

*End of Document — N1B0 NPU HDD v8 (Merged)*
