# EDC Node Instance Path Reference

## Overview

| Subsystem | Tile Count | Patterns per Tile | EDC Ring Architecture |
|-----------|-----------|-------------------|-----------------------|
| Tensix tile | 5172 | 47 | Single ring: NOC segment → T0→T1→L1→T3→T2 feedthrough → Overlay segment |
| Dispatch engine (west) | 159 | 27 | Single ring: NOC segment → Dispatch L1 SRAM → Overlay segment |
| Dispatch engine (east) | 159 | 27 | Single ring: NOC segment → Dispatch L1 SRAM → Overlay segment |
| NoC2AXI n opt | 36 | 18 | Single ring: sec_conf → router nodes → AXI buffer nodes |
| NoC2AXI ne opt | 15 | 15 | Single ring: sec_conf → router nodes → AXI buffer nodes |
| NoC2AXI nw opt | 15 | 15 | Single ring: sec_conf → router nodes → AXI buffer nodes |
| Router (standalone) | 30 | 15 | Single ring: APB bridge (BIU) → router nodes → sec_conf |

**Path prefix convention:** `gen_x[*].gen_y[*].<subsystem_prefix>.<...>`

**Parallel notation:** When the same node type is instantiated as an array (`[*]`), the second and subsequent entries are marked **`(parallel to #N)`** referencing the first instance's sequence number. These are still separate serial nodes in the ring — "parallel" means same type replicated for different resource instances.

**Sub-core replication:** T0/T1/T2/T3 each instantiate the same node types. T1/T3/T2 entries are marked **`(same type as T0 #N)`**.

---

## 1. Tensix Tiles

Top-level prefix: `gen_x[*].gen_y[*].gen_tensix.tt_tensix_with_l1.`

**Ring entry:** top-level `edc_ingress_intf` → `overlay_noc_wrap.noc_edc_ingress_intf`
**Ring exit:** `overlay_noc_wrap.overlay_edc_egress_intf` → top-level `edc_egress_intf`

### Segment A — NOC Ring

Sub-prefix: `overlay_noc_wrap.overlay_noc_niu_router.tt_trinity_noc_niu_router_inst.`

Ring flow: `noc_edc_ingress_intf` → **sec_conf bridge** → `noc_niu_router_inst` (inst 0→15→0xC0) → **NOC BIST** → demux (`i_edc_mux_demux_sel`) → `noc_edc_egress_intf`

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| A-1 | `overlay_noc_sec_conf.u_bridge.u_edc1_node_inst` | NOC Sec Conf | — | `postdfx_aon_clk` | NOC security configuration bridge — ring controller node; provides secure-group policy CSRs for the NOC |
| A-2 | `noc_niu_router_inst.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC North Router | 0x00 | `postdfx_aon_clk` | North router VC buffer parity — monitors flit VC buffer SRAM read parity |
| A-3 | `noc_niu_router_inst.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_header_ecc.g_edc_inst.g_cor_err_no_bit_pos.edc_node_inst` | NOC North Router | 0x01 | `postdfx_aon_clk` | North router header ECC — COR and UNC ECC on flit header SRAM |
| A-4 | `noc_niu_router_inst.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC North Router | 0x02 | `postdfx_aon_clk` | North router data parity — flit data path parity |
| A-5 | `noc_niu_router_inst.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC East Router | 0x03 | `postdfx_aon_clk` | East router VC buffer parity |
| A-6 | `noc_niu_router_inst.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_header_ecc.g_edc_inst.g_cor_err_no_bit_pos.edc_node_inst` | NOC East Router | 0x04 | `postdfx_aon_clk` | East router header ECC — COR and UNC |
| A-7 | `noc_niu_router_inst.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC East Router | 0x05 | `postdfx_aon_clk` | East router data parity |
| A-8 | `noc_niu_router_inst.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC South Router | 0x06 | `postdfx_aon_clk` | South router VC buffer parity |
| A-9 | `noc_niu_router_inst.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_header_ecc.g_edc_inst.g_cor_err_no_bit_pos.edc_node_inst` | NOC South Router | 0x07 | `postdfx_aon_clk` | South router header ECC — COR and UNC |
| A-10 | `noc_niu_router_inst.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC South Router | 0x08 | `postdfx_aon_clk` | South router data parity |
| A-11 | `noc_niu_router_inst.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC West Router | 0x09 | `postdfx_aon_clk` | West router VC buffer parity |
| A-12 | `noc_niu_router_inst.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_header_ecc.g_edc_inst.g_cor_err_no_bit_pos.edc_node_inst` | NOC West Router | 0x0A | `postdfx_aon_clk` | West router header ECC — COR and UNC |
| A-13 | `noc_niu_router_inst.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_data_parity.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC West Router | 0x0B | `postdfx_aon_clk` | West router data parity |
| A-14 | `noc_niu_router_inst.has_niu_vc_buf.noc_overlay_edc_wrapper_niu_vc_buf.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC NIU | 0x0C | `postdfx_aon_clk` | NIU (Network Interface Unit) VC buffer parity |
| A-15 | `noc_niu_router_inst.has_rocc_mem.noc_overlay_edc_wrapper_rocc_intf.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC ROCC | 0x0D | `postdfx_aon_clk` | ROCC interface buffer parity; bypassed when `OVERLAY_INF_EN==0` |
| A-16 | `noc_niu_router_inst.has_ep_table_mem.noc_overlay_edc_wrapper_ep_table.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC Addr Trans | 0x0E | `postdfx_aon_clk` | Endpoint address translation table SRAM parity |
| A-17 | `noc_niu_router_inst.has_routing_table_mem.noc_overlay_edc_wrapper_routing_table.g_edc_inst.g_no_cor_err_events.edc_node_inst` | NOC Addr Trans | 0x0F | `postdfx_aon_clk` | Routing table SRAM parity |
| A-18 | `noc_niu_router_inst.has_sec_fence_edc.noc_sec_fence_edc_wrapper.g_edc_inst.edc_node_inst` | NOC Security | 0xC0 | `postdfx_aon_clk` | Security fence violation detector — unauthorized address range access |
| A-19 | `noc_niu_router_inst.u_edc_flex_client_bist.g_edc_inst.u_edc_flex_client_node` | NOC BIST | — | `postdfx_aon_clk` | NOC-side BIST flex client — in-situ SRAM test result node |

> **After A-19:** `noc_edc_egress_intf` → `edc_conn_ovl_to_L1` feedthrough → L1 partition `edc_ingress_feedthrough_ovl_to_t0` → **T0 sub-core entry**

---

### Segment B — T0 Sub-Core Nodes

Sub-prefix: `t6[0].neo.u_t6.`

Ring flow (confirmed from `tt_tensix.sv` L222, L225): feedthrough from NOC → **Gtile[0]** → `instrn_engine_wrapper` nodes → **Gtile[1]** → feedthrough to T1

> RTL source: `tt_tensix.sv`:
> - L222: `edc_gtile_egress_intf[0]` → `edc_instrn_ingress_intf` (Gtile[0] output feeds instrn_engine_wrapper input)
> - L225: `edc_instrn_egress_intf` → `edc_gtile_ingress_intf[1]` (instrn_engine_wrapper output feeds Gtile[1] input)

> Gtile internal order confirmed from `tt_fpu_gtile.sv` L991→L1032→L1061 (ingress/egress chain):
> `general_error`(inst+0) → `src_parity`(inst+1) → `dest_parity`(inst+2)
> inst offsets from `tt_tensix_edc_pkg.sv`: GTILE_SRCA_PARITY_EDC_OFFSET=0x01, GTILE_DEST_PARITY_EDC_OFFSET=0x02
> base inst IDs: Gtile[0]=0x20, Gtile[1]=0x23 (from GTILE_LOCAL_INST_ID[0/1])

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| B-1 | `gen_gtile[0].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[0] | 0x20 | `aiclk` | Gtile[0] general error aggregator — FPU lane-pair fault, diagnostic mode fault |
| B-2 | `gen_gtile[0].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[0] | 0x21 | `aiclk` | Gtile[0] source operand (SRCA) parity |
| B-3 | `gen_gtile[0].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[0] | 0x22 | `aiclk` | Gtile[0] destination result parity |
| B-4 | `instrn_engine_wrapper.ie_parity_edc_node` | IE | 0x03 | `aiclk` | Instruction engine (IE) overall parity — instruction FIFO/pipeline parity |
| B-5 | `instrn_engine_wrapper.srcb_edc_node` | SRCB | 0x04 | `aiclk` | Source B register file parity |
| B-6 | `instrn_engine_wrapper.u_edc_node_unpack` | Unpack | 0x05 | `aiclk` | Unpack engine register/buffer parity |
| B-7 | `instrn_engine_wrapper.u_edc_node_pack` | Pack | 0x06 | `aiclk` | Pack engine register/buffer parity |
| B-8 | `instrn_engine_wrapper.u_edc_node_sfpu` | SFPU | 0x07 | `aiclk` | Special Function Unit register parity |
| B-9 | `instrn_engine_wrapper.u_edc_node_gpr_p0` | GPR P0 | 0x08 | `aiclk` | General Purpose Register file partition 0 parity |
| B-10 | `instrn_engine_wrapper.u_edc_node_gpr_p1` | GPR P1 | 0x09 | `aiclk` | General Purpose Register file partition 1 parity |
| B-11 | `instrn_engine_wrapper.u_edc_node_cfg_exu_0` | CFG EXU 0 | 0x0A | `aiclk` | Configuration register file (execution unit 0) parity |
| B-12 | `instrn_engine_wrapper.u_edc_node_cfg_exu_1` | CFG EXU 1 | 0x0B | `aiclk` | Configuration register file (execution unit 1) parity |
| B-13 | `instrn_engine_wrapper.u_edc_node_cfg_global` | CFG Global | 0x0C | `aiclk` | Global configuration register file parity |
| B-14 | `instrn_engine_wrapper.u_edc_node_thcon_0` | THCON 0 | 0x0D | `aiclk` | Thread controller 0 state/register parity |
| B-15 | `instrn_engine_wrapper.u_edc_node_thcon_1` | THCON 1 | 0x0E | `aiclk` | Thread controller 1 state/register parity |
| B-16 | `instrn_engine_wrapper.instrn_engine.u_l1_flex_client_edc` | L1 Client | 0x10 | `aiclk` | L1 SRAM client — L1 BIST result and CSR parity for this sub-core |
| B-17 | `gen_gtile[1].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[1] | 0x23 | `aiclk` | Gtile[1] general error aggregator **(same type as B-1, Gtile[1])** |
| B-18 | `gen_gtile[1].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[1] | 0x24 | `aiclk` | Gtile[1] source operand parity **(same type as B-2)** |
| B-19 | `gen_gtile[1].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[1] | 0x25 | `aiclk` | Gtile[1] destination result parity **(same type as B-3)** |

> **After B-19:** feedthrough `edc_egress_feedthrough_t0_to_t1` → **T1 sub-core entry**

---

### Segment C — T1 Sub-Core Nodes

Sub-prefix: `t6[1].neo.u_t6.`  (same node types as T0; same ring order: Gtile[0] → instrn_engine → Gtile[1])

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| C-1 | `gen_gtile[0].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[0] | 0x20 | `aiclk` | **(same type as B-1, T1 instance)** |
| C-2 | `gen_gtile[0].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[0] | 0x21 | `aiclk` | **(same type as B-2)** |
| C-3 | `gen_gtile[0].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[0] | 0x22 | `aiclk` | **(same type as B-3)** |
| C-4 | `instrn_engine_wrapper.ie_parity_edc_node` | IE | 0x03 | `aiclk` | **(same type as B-4)** |
| C-5 | `instrn_engine_wrapper.srcb_edc_node` | SRCB | 0x04 | `aiclk` | **(same type as B-5)** |
| C-6 | `instrn_engine_wrapper.u_edc_node_unpack` | Unpack | 0x05 | `aiclk` | **(same type as B-6)** |
| C-7 | `instrn_engine_wrapper.u_edc_node_pack` | Pack | 0x06 | `aiclk` | **(same type as B-7)** |
| C-8 | `instrn_engine_wrapper.u_edc_node_sfpu` | SFPU | 0x07 | `aiclk` | **(same type as B-8)** |
| C-9 | `instrn_engine_wrapper.u_edc_node_gpr_p0` | GPR P0 | 0x08 | `aiclk` | **(same type as B-9)** |
| C-10 | `instrn_engine_wrapper.u_edc_node_gpr_p1` | GPR P1 | 0x09 | `aiclk` | **(same type as B-10)** |
| C-11 | `instrn_engine_wrapper.u_edc_node_cfg_exu_0` | CFG EXU 0 | 0x0A | `aiclk` | **(same type as B-11)** |
| C-12 | `instrn_engine_wrapper.u_edc_node_cfg_exu_1` | CFG EXU 1 | 0x0B | `aiclk` | **(same type as B-12)** |
| C-13 | `instrn_engine_wrapper.u_edc_node_cfg_global` | CFG Global | 0x0C | `aiclk` | **(same type as B-13)** |
| C-14 | `instrn_engine_wrapper.u_edc_node_thcon_0` | THCON 0 | 0x0D | `aiclk` | **(same type as B-14)** |
| C-15 | `instrn_engine_wrapper.u_edc_node_thcon_1` | THCON 1 | 0x0E | `aiclk` | **(same type as B-15)** |
| C-16 | `instrn_engine_wrapper.instrn_engine.u_l1_flex_client_edc` | L1 Client | 0x10 | `aiclk` | **(same type as B-16)** |
| C-17 | `gen_gtile[1].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[1] | 0x23 | `aiclk` | **(same type as B-17)** |
| C-18 | `gen_gtile[1].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[1] | 0x24 | `aiclk` | **(same type as B-18)** |
| C-19 | `gen_gtile[1].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[1] | 0x25 | `aiclk` | **(same type as B-19)** |

> **After C-19:** `edc_conn_T1_to_L1` → `edc_l1_ingress_intf` → **L1 partition main path entry**

---

### Segment D — L1 Partition (T6_MISC + L1W2 SRAM)

Sub-prefix: `u_l1part.`

Ring flow: `edc_l1_ingress_intf` → T6_MISC repeater → **T6_MISC node** → L1W2 repeater → **L1W2 SRAM sub-bank nodes [0..N]** → `edc_l1_egress_intf`

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| D-1 | `t6_misc.u_edc1_node_misc` | T6 MISC | 0x00 | `aiclk` | T6 tile miscellaneous — misc reg parity, skid buffers, semaphores, GSRS, TC remap; part=`NODE_ID_PART_TENSIX_BASE` (0x10) |
| D-2 | `u_l1w2.u_l1_mem_wrap.sbank_mem[0].bank_mem[0].sub_bank_mem[0].gen_first_last_sync.u_edc_node` | L1W2 SRAM | — | `aiclk` | L1W2 SRAM ECC — **first** sub-bank; uses sync-enabled EDC config (`EDC_CFG_SYNC_EN`) for CDC crossing |
| D-3 | `u_l1w2.u_l1_mem_wrap.sbank_mem[*].bank_mem[*].sub_bank_mem[*].genblk2.u_edc_node` | L1W2 SRAM | — | `aiclk` | L1W2 SRAM ECC — **middle** sub-banks (×N middle instances, one per sub-bank); standard `EDC_CFG` **(parallel to D-2, sub-bank indices 1..N-1)** |
| D-4 | `u_l1w2.u_l1_mem_wrap.sbank_mem[*].bank_mem[*].sub_bank_mem[last].gen_first_last_sync.u_edc_node` | L1W2 SRAM | — | `aiclk` | L1W2 SRAM ECC — **last** sub-bank; uses sync-enabled EDC config **(parallel to D-2, last index)** |

> **After D-4:** `edc_l1_egress_intf` → `edc_conn_L1_to_T3` → **T3 sub-core entry**

---

### Segment E — T3 Sub-Core Nodes

Sub-prefix: `t6[3].neo.u_t6.`  (same node types as T0; ring order: T1→L1→**T3**→T2; same order: Gtile[0] → instrn_engine → Gtile[1])

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| E-1 | `gen_gtile[0].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[0] | 0x20 | `aiclk` | **(same type as B-1, T3 instance)** |
| E-2 | `gen_gtile[0].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[0] | 0x21 | `aiclk` | **(same type as B-2)** |
| E-3 | `gen_gtile[0].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[0] | 0x22 | `aiclk` | **(same type as B-3)** |
| E-4 | `instrn_engine_wrapper.ie_parity_edc_node` | IE | 0x03 | `aiclk` | **(same type as B-4)** |
| E-5 | `instrn_engine_wrapper.srcb_edc_node` | SRCB | 0x04 | `aiclk` | **(same type as B-5)** |
| E-6 | `instrn_engine_wrapper.u_edc_node_unpack` | Unpack | 0x05 | `aiclk` | **(same type as B-6)** |
| E-7 | `instrn_engine_wrapper.u_edc_node_pack` | Pack | 0x06 | `aiclk` | **(same type as B-7)** |
| E-8 | `instrn_engine_wrapper.u_edc_node_sfpu` | SFPU | 0x07 | `aiclk` | **(same type as B-8)** |
| E-9 | `instrn_engine_wrapper.u_edc_node_gpr_p0` | GPR P0 | 0x08 | `aiclk` | **(same type as B-9)** |
| E-10 | `instrn_engine_wrapper.u_edc_node_gpr_p1` | GPR P1 | 0x09 | `aiclk` | **(same type as B-10)** |
| E-11 | `instrn_engine_wrapper.u_edc_node_cfg_exu_0` | CFG EXU 0 | 0x0A | `aiclk` | **(same type as B-11)** |
| E-12 | `instrn_engine_wrapper.u_edc_node_cfg_exu_1` | CFG EXU 1 | 0x0B | `aiclk` | **(same type as B-12)** |
| E-13 | `instrn_engine_wrapper.u_edc_node_cfg_global` | CFG Global | 0x0C | `aiclk` | **(same type as B-13)** |
| E-14 | `instrn_engine_wrapper.u_edc_node_thcon_0` | THCON 0 | 0x0D | `aiclk` | **(same type as B-14)** |
| E-15 | `instrn_engine_wrapper.u_edc_node_thcon_1` | THCON 1 | 0x0E | `aiclk` | **(same type as B-15)** |
| E-16 | `instrn_engine_wrapper.instrn_engine.u_l1_flex_client_edc` | L1 Client | 0x10 | `aiclk` | **(same type as B-16)** |
| E-17 | `gen_gtile[1].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[1] | 0x23 | `aiclk` | **(same type as B-17)** |
| E-18 | `gen_gtile[1].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[1] | 0x24 | `aiclk` | **(same type as B-18)** |
| E-19 | `gen_gtile[1].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[1] | 0x25 | `aiclk` | **(same type as B-19)** |

> **After E-19:** feedthrough `edc_egress_feedthrough_t3_to_t2` → **T2 sub-core entry**

---

### Segment F — T2 Sub-Core Nodes

Sub-prefix: `t6[2].neo.u_t6.`  (same node types as T0; same ring order: Gtile[0] → instrn_engine → Gtile[1])

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| F-1 | `gen_gtile[0].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[0] | 0x20 | `aiclk` | **(same type as B-1, T2 instance)** |
| F-2 | `gen_gtile[0].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[0] | 0x21 | `aiclk` | **(same type as B-2)** |
| F-3 | `gen_gtile[0].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[0] | 0x22 | `aiclk` | **(same type as B-3)** |
| F-4 | `instrn_engine_wrapper.ie_parity_edc_node` | IE | 0x03 | `aiclk` | **(same type as B-4)** |
| F-5 | `instrn_engine_wrapper.srcb_edc_node` | SRCB | 0x04 | `aiclk` | **(same type as B-5)** |
| F-6 | `instrn_engine_wrapper.u_edc_node_unpack` | Unpack | 0x05 | `aiclk` | **(same type as B-6)** |
| F-7 | `instrn_engine_wrapper.u_edc_node_pack` | Pack | 0x06 | `aiclk` | **(same type as B-7)** |
| F-8 | `instrn_engine_wrapper.u_edc_node_sfpu` | SFPU | 0x07 | `aiclk` | **(same type as B-8)** |
| F-9 | `instrn_engine_wrapper.u_edc_node_gpr_p0` | GPR P0 | 0x08 | `aiclk` | **(same type as B-9)** |
| F-10 | `instrn_engine_wrapper.u_edc_node_gpr_p1` | GPR P1 | 0x09 | `aiclk` | **(same type as B-10)** |
| F-11 | `instrn_engine_wrapper.u_edc_node_cfg_exu_0` | CFG EXU 0 | 0x0A | `aiclk` | **(same type as B-11)** |
| F-12 | `instrn_engine_wrapper.u_edc_node_cfg_exu_1` | CFG EXU 1 | 0x0B | `aiclk` | **(same type as B-12)** |
| F-13 | `instrn_engine_wrapper.u_edc_node_cfg_global` | CFG Global | 0x0C | `aiclk` | **(same type as B-13)** |
| F-14 | `instrn_engine_wrapper.u_edc_node_thcon_0` | THCON 0 | 0x0D | `aiclk` | **(same type as B-14)** |
| F-15 | `instrn_engine_wrapper.u_edc_node_thcon_1` | THCON 1 | 0x0E | `aiclk` | **(same type as B-15)** |
| F-16 | `instrn_engine_wrapper.instrn_engine.u_l1_flex_client_edc` | L1 Client | 0x10 | `aiclk` | **(same type as B-16)** |
| F-17 | `gen_gtile[1].u_fpu_gtile.gtile_general_error_edc_node` | FPU Gtile[1] | 0x23 | `aiclk` | **(same type as B-17)** |
| F-18 | `gen_gtile[1].u_fpu_gtile.gtile_src_parity_edc_node` | FPU Gtile[1] | 0x24 | `aiclk` | **(same type as B-18)** |
| F-19 | `gen_gtile[1].u_fpu_gtile.gtile_dest_parity_edc_node` | FPU Gtile[1] | 0x25 | `aiclk` | **(same type as B-19)** |

> **After F-19:** feedthrough `edc_egress_feedthrough_t2_to_ovl` → `edc_L1_to_ovl_egress_intf` → `edc_conn_L1_to_overlay` → `overlay_edc_ingress_intf` → **Overlay wrapper entry**

---

### Segment G — Overlay Wrapper Ring

Sub-prefix: `overlay_noc_wrap.overlay_noc_niu_router.neo_overlay_wrapper.overlay_wrapper.`

Ring flow (from `tt_overlay_wrapper.sv`):
`overlay_edc_ingress_intf` → **memory nodes** → WDT → **APB Bridge (BIU)** → **overlay BIST** → `overlay_edc_egress_intf`

| Seq # | Instance Suffix | Block | Clock | Description |
|-------|----------------|-------|-------|-------------|
| G-1 | `memory_wrapper.gen_l1_dcache_data_edc[0].noc_overlay_edc_wrapper_l1_dcache_data.g_edc_inst.g_cor_err_with_bit_pos.edc_node_inst` | L1 DCache Data | `postdfx_aon_clk` | L1 data cache data[0] ECC — COR with bit position + UNC |
| G-2 | `memory_wrapper.gen_l1_dcache_data_edc[1..N].noc_overlay_edc_wrapper_l1_dcache_data.g_edc_inst.g_cor_err_with_bit_pos.edc_node_inst` | L1 DCache Data | `postdfx_aon_clk` | L1 data cache data[1..N] ECC **(parallel to G-1, per way/bank)** |
| G-3 | `memory_wrapper.gen_l1_dcache_tag_edc[0].noc_overlay_edc_wrapper_l1_dcache_tag.g_edc_inst.g_cor_err_with_bit_pos.edc_node_inst` | L1 DCache Tag | `postdfx_aon_clk` | L1 data cache tag[0] ECC — COR with bit position + UNC |
| G-4 | `memory_wrapper.gen_l1_dcache_tag_edc[1..N].noc_overlay_edc_wrapper_l1_dcache_tag.g_edc_inst.g_cor_err_with_bit_pos.edc_node_inst` | L1 DCache Tag | `postdfx_aon_clk` | L1 data cache tag[1..N] ECC **(parallel to G-3)** |
| G-5 | `memory_wrapper.gen_l1_icache_data_edc[0].noc_overlay_edc_wrapper_l1_icache_data.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L1 ICache Data | `postdfx_aon_clk` | L1 instruction cache data[0] parity — UNC only |
| G-6 | `memory_wrapper.gen_l1_icache_data_edc[1..N].noc_overlay_edc_wrapper_l1_icache_data.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L1 ICache Data | `postdfx_aon_clk` | L1 instruction cache data[1..N] parity **(parallel to G-5)** |
| G-7 | `memory_wrapper.gen_l1_icache_tag_edc[0].noc_overlay_edc_wrapper_l1_icache_tag.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L1 ICache Tag | `postdfx_aon_clk` | L1 instruction cache tag[0] parity — UNC only |
| G-8 | `memory_wrapper.gen_l1_icache_tag_edc[1..N].noc_overlay_edc_wrapper_l1_icache_tag.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L1 ICache Tag | `postdfx_aon_clk` | L1 instruction cache tag[1..N] parity **(parallel to G-7)** |
| G-9 | `memory_wrapper.gen_l2_dir[0].noc_overlay_edc_wrapper_l2_dir.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L2 Directory | `postdfx_aon_clk` | L2 cache directory[0] SRAM parity — UNC only |
| G-10 | `memory_wrapper.gen_l2_dir[1..N].noc_overlay_edc_wrapper_l2_dir.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L2 Directory | `postdfx_aon_clk` | L2 cache directory[1..N] SRAM parity **(parallel to G-9)** |
| G-11 | `memory_wrapper.gen_l2_banks[0].noc_overlay_edc_wrapper_l2_banks.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L2 Banks | `postdfx_aon_clk` | L2 cache data bank[0] SRAM parity — UNC only |
| G-12 | `memory_wrapper.gen_l2_banks[1..N].noc_overlay_edc_wrapper_l2_banks.g_edc_inst.g_no_cor_err_events.edc_node_inst` | L2 Banks | `postdfx_aon_clk` | L2 cache data bank[1..N] SRAM parity **(parallel to G-11)** |
| G-13 | `edc_wrapper.g_edc_inst.wdt_reset_edc_node_inst` | WDT | `postdfx_aon_clk` | Watchdog timer reset event node |
| G-14 | `edc_apb_bridge.g_edc_inst.u_edc1_apb4_bridge.u_edc1_node` | EDC BIU | `postdfx_aon_clk` | **EDC1 APB4 bridge (BIU)** — ring controller; sends EDC packets to SMN via APB; last node before ring return |
| G-15 | `u_edc_flex_bist.g_edc_inst.u_edc_flex_client_node` | Overlay BIST | `postdfx_aon_clk` | Overlay-side BIST flex client — in-situ SRAM test result node |

**Ring return:** `overlay_edc_egress_intf` → top-level `edc_egress_intf`

---

### Tensix Tile Ring Summary

```
External edc_ingress_intf
  ↓
[A] NOC ring (postdfx_aon_clk)
    A-1:  overlay_noc_sec_conf bridge
    A-2:  N_vc_buf → A-3: N_hdr_ecc → A-4: N_data_parity
    A-5:  E_vc_buf → A-6: E_hdr_ecc → A-7: E_data_parity
    A-8:  S_vc_buf → A-9: S_hdr_ecc → A-10: S_data_parity
    A-11: W_vc_buf → A-12: W_hdr_ecc → A-13: W_data_parity
    A-14: NIU_vc_buf → A-15: ROCC → A-16: EP_table → A-17: Routing_table
    A-18: sec_fence → A-19: NOC_BIST
  ↓ feedthrough (ovl→T0)
[B] T0 sub-core (aiclk)
    B-1..B-3:  Gtile[0]: general_error(0x20) / src_parity(0x21) / dest_parity(0x22)
    B-4..B-16: IE(0x03)/SRCB/Unpack/Pack/SFPU/GPR_P0/GPR_P1/CFG_EXU_0/1/Global/THCON_0/1/L1_client(0x10)
    B-17..B-19: Gtile[1]: general_error(0x23) / src_parity(0x24) / dest_parity(0x25)
  ↓ feedthrough (T0→T1)
[C] T1 sub-core (aiclk)  — same structure as T0 (C-1..C-19)
  ↓ edc_conn_T1_to_L1
[D] L1 partition (aiclk)
    D-1: T6_MISC → D-2: L1W2_subbank[first] → D-3: L1W2_subbank[1..N-1] → D-4: L1W2_subbank[last]
  ↓ edc_conn_L1_to_T3
[E] T3 sub-core (aiclk)  — same structure as T0 (E-1..E-19)
  ↓ feedthrough (T3→T2)
[F] T2 sub-core (aiclk)  — same structure as T0 (F-1..F-19)
  ↓ feedthrough (T2→ovl) → edc_conn_L1_to_overlay
[G] Overlay wrapper ring (postdfx_aon_clk)
    G-1..G-2:  DCache_data[0..N] → G-3..G-4: DCache_tag[0..N]
    G-5..G-6:  ICache_data[0..N] → G-7..G-8: ICache_tag[0..N]
    G-9..G-10: L2_dir[0..N]      → G-11..G-12: L2_banks[0..N]
    G-13: WDT → G-14: APB Bridge (BIU) → G-15: Overlay BIST
  ↓
External edc_egress_intf
```

---

## 2. Dispatch Engine (West)

Top-level prefix: `gen_x[*].gen_y[*].gen_dispatch_w.tt_dispatch_top_inst_west.tt_dispatch_engine.`

**Ring architecture:** Same topology as Tensix tile but without sub-tensix T0–T3 cores. Dispatch L1 SRAM nodes replace the T0–T3 sub-core segments. Only North/East/South router ports present (no West port outward).

### Segment A — NOC Ring (West)

Sub-prefix: `disp_eng_overlay_noc_wrap.disp_eng_overlay_noc_niu_router.gen_disp_noc_west.trin_disp_eng_noc_niu_router_west_inst.`

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| A-1 | `overlay_noc_sec_conf.u_bridge.u_edc1_node_inst` | NOC Sec Conf | — | `postdfx_aon_clk` | NOC security configuration bridge |
| A-2 | `disp_eng_noc_niu_router_inst.noc_niu_router_inst.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_vc_buf...edc_node_inst` | N Router | 0x00 | `postdfx_aon_clk` | North VC buffer parity |
| A-3 | `..noc_overlay_edc_wrapper_north_router_header_ecc...edc_node_inst` | N Router | 0x01 | `postdfx_aon_clk` | North header ECC |
| A-4 | `..noc_overlay_edc_wrapper_north_router_data_parity...edc_node_inst` | N Router | 0x02 | `postdfx_aon_clk` | North data parity |
| A-5 | `..has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_vc_buf...edc_node_inst` | E Router | 0x03 | `postdfx_aon_clk` | East VC buffer parity |
| A-6 | `..noc_overlay_edc_wrapper_east_router_header_ecc...edc_node_inst` | E Router | 0x04 | `postdfx_aon_clk` | East header ECC |
| A-7 | `..noc_overlay_edc_wrapper_east_router_data_parity...edc_node_inst` | E Router | 0x05 | `postdfx_aon_clk` | East data parity |
| A-8 | `..has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf...edc_node_inst` | S Router | 0x06 | `postdfx_aon_clk` | South VC buffer parity |
| A-9 | `..noc_overlay_edc_wrapper_south_router_header_ecc...edc_node_inst` | S Router | 0x07 | `postdfx_aon_clk` | South header ECC |
| A-10 | `..noc_overlay_edc_wrapper_south_router_data_parity...edc_node_inst` | S Router | 0x08 | `postdfx_aon_clk` | South data parity |
| A-11 | `..has_niu_vc_buf.noc_overlay_edc_wrapper_niu_vc_buf...edc_node_inst` | NIU | 0x09 | `postdfx_aon_clk` | NIU VC buffer parity |
| A-12 | `..has_rocc_mem.noc_overlay_edc_wrapper_rocc_intf...edc_node_inst` | ROCC | 0x0A | `postdfx_aon_clk` | ROCC interface buffer parity |
| A-13 | `..has_ep_table_mem.noc_overlay_edc_wrapper_ep_table...edc_node_inst` | Addr Trans | 0x0B | `postdfx_aon_clk` | EP address translation table SRAM parity |
| A-14 | `..has_routing_table_mem.noc_overlay_edc_wrapper_routing_table...edc_node_inst` | Addr Trans | 0x0C | `postdfx_aon_clk` | Routing table SRAM parity |
| A-15 | `..has_sec_fence_edc.noc_sec_fence_edc_wrapper...edc_node_inst` | Security | 0xC0 | `postdfx_aon_clk` | Security fence violation detector |
| A-16 | `..u_edc_flex_client_bist.g_edc_inst.u_edc_flex_client_node` | NOC BIST | — | `postdfx_aon_clk` | NOC-side BIST flex client |

> **After A-16:** feedthrough → **Dispatch L1 SRAM entry**

### Segment B — Dispatch L1 SRAM Nodes

Sub-prefix: `disp_eng_l1_partition_inst.customer_dispatch_top.tt_t6_l1_dispatch.u_l1_mem_wrap.`

| Seq # | Instance Suffix | Block | Clock | Description |
|-------|----------------|-------|-------|-------------|
| B-1 | `sbank_mem[0].bank_mem[0].sub_bank_mem[0].gen_first_last_sync.u_edc_node` | L1 SRAM | `aiclk` | Dispatch L1 SRAM ECC — **first** sub-bank; sync-enabled EDC config |
| B-2 | `sbank_mem[*].bank_mem[*].sub_bank_mem[*].genblk2.u_edc_node` | L1 SRAM | `aiclk` | Dispatch L1 SRAM ECC — **middle** sub-banks **(parallel to B-1, sub-bank indices 1..N-1)** |
| B-3 | `sbank_mem[*].bank_mem[*].sub_bank_mem[last].gen_first_last_sync.u_edc_node` | L1 SRAM | `aiclk` | Dispatch L1 SRAM ECC — **last** sub-bank **(parallel to B-1, last index)** |

> **After B-3:** feedthrough → **Overlay wrapper entry**

### Segment C — Overlay Wrapper Ring (West)

Sub-prefix: `disp_eng_overlay_noc_wrap.disp_eng_overlay_noc_niu_router.disp_eng_overlay_wrapper.overlay_wrapper.`

| Seq # | Instance Suffix | Block | Clock | Description |
|-------|----------------|-------|-------|-------------|
| C-1 | `memory_wrapper.gen_l1_dcache_data_edc[0]...edc_node_inst` | L1 DCache Data | `postdfx_aon_clk` | L1 DCache data[0] ECC — COR + UNC **(same type as Tensix G-1)** |
| C-2 | `memory_wrapper.gen_l1_dcache_data_edc[1..N]...edc_node_inst` | L1 DCache Data | `postdfx_aon_clk` | L1 DCache data[1..N] **(parallel to C-1)** |
| C-3 | `memory_wrapper.gen_l1_dcache_tag_edc[0]...edc_node_inst` | L1 DCache Tag | `postdfx_aon_clk` | L1 DCache tag[0] ECC — COR + UNC |
| C-4 | `memory_wrapper.gen_l1_dcache_tag_edc[1..N]...edc_node_inst` | L1 DCache Tag | `postdfx_aon_clk` | L1 DCache tag[1..N] **(parallel to C-3)** |
| C-5 | `memory_wrapper.gen_l1_icache_data_edc[0]...edc_node_inst` | L1 ICache Data | `postdfx_aon_clk` | L1 ICache data[0] parity — UNC only |
| C-6 | `memory_wrapper.gen_l1_icache_data_edc[1..N]...edc_node_inst` | L1 ICache Data | `postdfx_aon_clk` | L1 ICache data[1..N] **(parallel to C-5)** |
| C-7 | `memory_wrapper.gen_l1_icache_tag_edc[0]...edc_node_inst` | L1 ICache Tag | `postdfx_aon_clk` | L1 ICache tag[0] parity — UNC only |
| C-8 | `memory_wrapper.gen_l1_icache_tag_edc[1..N]...edc_node_inst` | L1 ICache Tag | `postdfx_aon_clk` | L1 ICache tag[1..N] **(parallel to C-7)** |
| C-9 | `memory_wrapper.gen_l2_dir[0]...edc_node_inst` | L2 Directory | `postdfx_aon_clk` | L2 directory[0] SRAM parity — UNC only |
| C-10 | `memory_wrapper.gen_l2_dir[1..N]...edc_node_inst` | L2 Directory | `postdfx_aon_clk` | L2 directory[1..N] **(parallel to C-9)** |
| C-11 | `memory_wrapper.gen_l2_banks[0]...edc_node_inst` | L2 Banks | `postdfx_aon_clk` | L2 data bank[0] SRAM parity — UNC only |
| C-12 | `memory_wrapper.gen_l2_banks[1..N]...edc_node_inst` | L2 Banks | `postdfx_aon_clk` | L2 data bank[1..N] **(parallel to C-11)** |
| C-13 | `edc_wrapper.g_edc_inst.wdt_reset_edc_node_inst` | WDT | `postdfx_aon_clk` | Watchdog timer reset event node |
| C-14 | `edc_apb_bridge.g_edc_inst.u_edc1_apb4_bridge.u_edc1_node` | EDC BIU | `postdfx_aon_clk` | **EDC1 APB4 bridge (BIU)** — ring controller |
| C-15 | `u_edc_flex_bist.g_edc_inst.u_edc_flex_client_node` | Overlay BIST | `postdfx_aon_clk` | Overlay-side BIST flex client |

---

## 3. Dispatch Engine (East)

Top-level prefix: `gen_x[*].gen_y[*].gen_dispatch_e.tt_dispatch_top_inst_east.tt_dispatch_engine.`

Same ring structure as Dispatch West. Difference: East-side router has North/South/West ports (no East port outward).

### Segment A — NOC Ring (East)

Sub-prefix: `disp_eng_overlay_noc_wrap.disp_eng_overlay_noc_niu_router.gen_disp_noc_east.trin_disp_eng_noc_niu_router_east_inst.`

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| A-1 | `overlay_noc_sec_conf.u_bridge.u_edc1_node_inst` | NOC Sec Conf | — | `postdfx_aon_clk` | NOC security configuration bridge |
| A-2 | `..has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_vc_buf...edc_node_inst` | N Router | 0x00 | `postdfx_aon_clk` | North VC buffer parity |
| A-3 | `..noc_overlay_edc_wrapper_north_router_header_ecc...edc_node_inst` | N Router | 0x01 | `postdfx_aon_clk` | North header ECC |
| A-4 | `..noc_overlay_edc_wrapper_north_router_data_parity...edc_node_inst` | N Router | 0x02 | `postdfx_aon_clk` | North data parity |
| A-5 | `..has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf...edc_node_inst` | S Router | 0x06 | `postdfx_aon_clk` | South VC buffer parity |
| A-6 | `..noc_overlay_edc_wrapper_south_router_header_ecc...edc_node_inst` | S Router | 0x07 | `postdfx_aon_clk` | South header ECC |
| A-7 | `..noc_overlay_edc_wrapper_south_router_data_parity...edc_node_inst` | S Router | 0x08 | `postdfx_aon_clk` | South data parity |
| A-8 | `..has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_vc_buf...edc_node_inst` | W Router | 0x09 | `postdfx_aon_clk` | West VC buffer parity |
| A-9 | `..noc_overlay_edc_wrapper_west_router_header_ecc...edc_node_inst` | W Router | 0x0A | `postdfx_aon_clk` | West header ECC |
| A-10 | `..noc_overlay_edc_wrapper_west_router_data_parity...edc_node_inst` | W Router | 0x0B | `postdfx_aon_clk` | West data parity |
| A-11 | `..has_niu_vc_buf.noc_overlay_edc_wrapper_niu_vc_buf...edc_node_inst` | NIU | 0x0C | `postdfx_aon_clk` | NIU VC buffer parity |
| A-12 | `..has_rocc_mem.noc_overlay_edc_wrapper_rocc_intf...edc_node_inst` | ROCC | 0x0D | `postdfx_aon_clk` | ROCC interface buffer parity |
| A-13 | `..has_ep_table_mem.noc_overlay_edc_wrapper_ep_table...edc_node_inst` | Addr Trans | 0x0E | `postdfx_aon_clk` | EP address translation table SRAM parity |
| A-14 | `..has_routing_table_mem.noc_overlay_edc_wrapper_routing_table...edc_node_inst` | Addr Trans | 0x0F | `postdfx_aon_clk` | Routing table SRAM parity |
| A-15 | `..has_sec_fence_edc.noc_sec_fence_edc_wrapper...edc_node_inst` | Security | 0xC0 | `postdfx_aon_clk` | Security fence violation detector |
| A-16 | `..u_edc_flex_client_bist.g_edc_inst.u_edc_flex_client_node` | NOC BIST | — | `postdfx_aon_clk` | NOC-side BIST flex client |

**Segments B and C:** Same as Dispatch West (B-1..B-3 Dispatch L1 SRAM, C-1..C-15 Overlay wrapper).

---

## 4. NoC2AXI (n opt — North)

Top-level prefix: `gen_x[*].gen_y[*].gen_noc2axi_n_opt.trinity_noc2axi_n_opt.`

**Ring architecture:** Single ring: sec_conf bridge → router nodes (E+S+W) → AXI buffer nodes (EP table, routing table, data buffers, slave read)

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| 1 | `noc2axi_noc_sec_conf.u_bridge.u_edc1_node_inst` | Sec Conf | — | `postdfx_aon_clk` | NoC2AXI security configuration bridge — ring start |
| 2 | `tt_noc2axi.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_vc_buf...edc_node_inst` | E Router | 0x03 | `postdfx_aon_clk` | East VC buffer parity |
| 3 | `tt_noc2axi.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_header_ecc...edc_node_inst` | E Router | 0x04 | `postdfx_aon_clk` | East header ECC |
| 4 | `tt_noc2axi.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_data_parity...edc_node_inst` | E Router | 0x05 | `postdfx_aon_clk` | East data parity |
| 5 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf...edc_node_inst` | S Router | 0x06 | `postdfx_aon_clk` | South VC buffer parity |
| 6 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_header_ecc...edc_node_inst` | S Router | 0x07 | `postdfx_aon_clk` | South header ECC |
| 7 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_data_parity...edc_node_inst` | S Router | 0x08 | `postdfx_aon_clk` | South data parity |
| 8 | `tt_noc2axi.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_vc_buf...edc_node_inst` | W Router | 0x09 | `postdfx_aon_clk` | West VC buffer parity |
| 9 | `tt_noc2axi.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_header_ecc...edc_node_inst` | W Router | 0x0A | `postdfx_aon_clk` | West header ECC |
| 10 | `tt_noc2axi.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_data_parity...edc_node_inst` | W Router | 0x0B | `postdfx_aon_clk` | West data parity |
| 11 | `tt_noc2axi.has_ep_table_mem_mst_rd.noc_overlay_edc_wrapper_mst_rd_ep_table...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read EP table SRAM parity |
| 12 | `tt_noc2axi.has_routing_table_mem_mst_rd.noc_overlay_edc_wrapper_mst_rd_routing_table...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read routing table SRAM parity |
| 13 | `tt_noc2axi.has_ep_table_mem_mst_wr.noc_overlay_edc_wrapper_mst_wr_ep_table...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write EP table SRAM parity |
| 14 | `tt_noc2axi.has_routing_table_mem_mst_wr.noc_overlay_edc_wrapper_mst_wr_routing_table...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write routing table SRAM parity |
| 15 | `tt_noc2axi.has_mst_wr_mem.gen_wr_buffer_mem_macro_mst_wr[0].noc_overlay_edc_wrapper_mst_wr...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write data buffer[0] SRAM parity |
| 15+ | `tt_noc2axi.has_mst_wr_mem.gen_wr_buffer_mem_macro_mst_wr[1..N]...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write data buffer[1..N] **(parallel to #15)** |
| 16 | `tt_noc2axi.has_mst_rd_mem.gen_rd_buffer_mem_macro_mst_rd[0].noc_overlay_edc_wrapper_mst_rd...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read data buffer[0] SRAM parity |
| 16+ | `tt_noc2axi.has_mst_rd_mem.gen_rd_buffer_mem_macro_mst_rd[1..N]...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read data buffer[1..N] **(parallel to #16)** |
| 17 | `tt_noc2axi.has_slv_rd_mem.noc_overlay_edc_wrapper_slv_rd...edc_node_inst` | AXI Slv Rd | — | `postdfx_aon_clk` | AXI slave-read data buffer SRAM parity |
| 18 | `tt_noc2axi.has_sec_fence_edc.noc_sec_fence_edc_wrapper...edc_node_inst` | Security | 0xC0 | `postdfx_aon_clk` | Security fence violation detector — **last node before ring exit** |

---

## 5. NoC2AXI (ne opt — Northeast)

Top-level prefix: `gen_x[*].gen_y[*].gen_noc2axi_ne_opt.trinity_noc2axi_ne_opt.`

**Topology difference vs n opt:** No East router port (NE corner has no eastern neighbor). S+W router only.

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| 1 | `noc2axi_noc_sec_conf.u_bridge.u_edc1_node_inst` | Sec Conf | — | `postdfx_aon_clk` | Security configuration bridge |
| 2 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf...edc_node_inst` | S Router | 0x06 | `postdfx_aon_clk` | South VC buffer parity |
| 3 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_header_ecc...edc_node_inst` | S Router | 0x07 | `postdfx_aon_clk` | South header ECC |
| 4 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_data_parity...edc_node_inst` | S Router | 0x08 | `postdfx_aon_clk` | South data parity |
| 5 | `tt_noc2axi.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_vc_buf...edc_node_inst` | W Router | 0x09 | `postdfx_aon_clk` | West VC buffer parity |
| 6 | `tt_noc2axi.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_header_ecc...edc_node_inst` | W Router | 0x0A | `postdfx_aon_clk` | West header ECC |
| 7 | `tt_noc2axi.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_data_parity...edc_node_inst` | W Router | 0x0B | `postdfx_aon_clk` | West data parity |
| 8 | `tt_noc2axi.has_ep_table_mem_mst_rd.noc_overlay_edc_wrapper_mst_rd_ep_table...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read EP table SRAM parity **(same type as n_opt #11)** |
| 9 | `tt_noc2axi.has_routing_table_mem_mst_rd.noc_overlay_edc_wrapper_mst_rd_routing_table...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read routing table SRAM parity |
| 10 | `tt_noc2axi.has_ep_table_mem_mst_wr.noc_overlay_edc_wrapper_mst_wr_ep_table...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write EP table SRAM parity |
| 11 | `tt_noc2axi.has_routing_table_mem_mst_wr.noc_overlay_edc_wrapper_mst_wr_routing_table...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write routing table SRAM parity |
| 12 | `tt_noc2axi.has_mst_wr_mem.gen_wr_buffer_mem_macro_mst_wr[0]...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write data buffer[0] SRAM parity |
| 12+ | `tt_noc2axi.has_mst_wr_mem.gen_wr_buffer_mem_macro_mst_wr[1..N]...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | **(parallel to #12)** |
| 13 | `tt_noc2axi.has_mst_rd_mem.gen_rd_buffer_mem_macro_mst_rd[0]...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read data buffer[0] SRAM parity |
| 13+ | `tt_noc2axi.has_mst_rd_mem.gen_rd_buffer_mem_macro_mst_rd[1..N]...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | **(parallel to #13)** |
| 14 | `tt_noc2axi.has_slv_rd_mem.noc_overlay_edc_wrapper_slv_rd...edc_node_inst` | AXI Slv Rd | — | `postdfx_aon_clk` | AXI slave-read data buffer SRAM parity |
| 15 | `tt_noc2axi.has_sec_fence_edc.noc_sec_fence_edc_wrapper...edc_node_inst` | Security | 0xC0 | `postdfx_aon_clk` | Security fence violation detector — **last node before ring exit** |

---

## 6. NoC2AXI (nw opt — Northwest)

Top-level prefix: `gen_x[*].gen_y[*].gen_noc2axi_nw_opt.trinity_noc2axi_nw_opt.`

**Topology difference vs n opt:** No West router port (NW corner has no western neighbor). E+S router only.

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| 1 | `noc2axi_noc_sec_conf.u_bridge.u_edc1_node_inst` | Sec Conf | — | `postdfx_aon_clk` | Security configuration bridge |
| 2 | `tt_noc2axi.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_vc_buf...edc_node_inst` | E Router | 0x03 | `postdfx_aon_clk` | East VC buffer parity |
| 3 | `tt_noc2axi.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_header_ecc...edc_node_inst` | E Router | 0x04 | `postdfx_aon_clk` | East header ECC |
| 4 | `tt_noc2axi.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_data_parity...edc_node_inst` | E Router | 0x05 | `postdfx_aon_clk` | East data parity |
| 5 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf...edc_node_inst` | S Router | 0x06 | `postdfx_aon_clk` | South VC buffer parity |
| 6 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_header_ecc...edc_node_inst` | S Router | 0x07 | `postdfx_aon_clk` | South header ECC |
| 7 | `tt_noc2axi.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_data_parity...edc_node_inst` | S Router | 0x08 | `postdfx_aon_clk` | South data parity |
| 8 | `tt_noc2axi.has_ep_table_mem_mst_rd.noc_overlay_edc_wrapper_mst_rd_ep_table...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read EP table SRAM parity |
| 9 | `tt_noc2axi.has_routing_table_mem_mst_rd.noc_overlay_edc_wrapper_mst_rd_routing_table...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read routing table SRAM parity |
| 10 | `tt_noc2axi.has_ep_table_mem_mst_wr.noc_overlay_edc_wrapper_mst_wr_ep_table...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write EP table SRAM parity |
| 11 | `tt_noc2axi.has_routing_table_mem_mst_wr.noc_overlay_edc_wrapper_mst_wr_routing_table...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write routing table SRAM parity |
| 12 | `tt_noc2axi.has_mst_wr_mem.gen_wr_buffer_mem_macro_mst_wr[0]...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | AXI master-write data buffer[0] SRAM parity |
| 12+ | `tt_noc2axi.has_mst_wr_mem.gen_wr_buffer_mem_macro_mst_wr[1..N]...edc_node_inst` | AXI Mst Wr | — | `postdfx_aon_clk` | **(parallel to #12)** |
| 13 | `tt_noc2axi.has_mst_rd_mem.gen_rd_buffer_mem_macro_mst_rd[0]...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | AXI master-read data buffer[0] SRAM parity |
| 13+ | `tt_noc2axi.has_mst_rd_mem.gen_rd_buffer_mem_macro_mst_rd[1..N]...edc_node_inst` | AXI Mst Rd | — | `postdfx_aon_clk` | **(parallel to #13)** |
| 14 | `tt_noc2axi.has_slv_rd_mem.noc_overlay_edc_wrapper_slv_rd...edc_node_inst` | AXI Slv Rd | — | `postdfx_aon_clk` | AXI slave-read data buffer SRAM parity |
| 15 | `tt_noc2axi.has_sec_fence_edc.noc_sec_fence_edc_wrapper...edc_node_inst` | Security | 0xC0 | `postdfx_aon_clk` | Security fence violation detector — **last node before ring exit** |

---

## 7. Router (Standalone)

Top-level prefix: `gen_x[*].gen_y[*].gen_router.trinity_router.`

**Ring architecture:** APB bridge (BIU) → router nodes (N+E+S+W) → sec_conf bridge

| Seq # | Instance Suffix | Block | inst | Clock | Description |
|-------|----------------|-------|------|-------|-------------|
| 1 | `router_edc1_apb4_bridge.u_edc1_node` | EDC BIU | — | `postdfx_aon_clk` | **EDC1 APB4 bridge (BIU)** — ring controller; first node in standalone router ring |
| 2 | `tt_router.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_vc_buf...edc_node_inst` | N Router | 0x00 | `postdfx_aon_clk` | North VC buffer parity |
| 3 | `tt_router.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_header_ecc...edc_node_inst` | N Router | 0x01 | `postdfx_aon_clk` | North header ECC |
| 4 | `tt_router.has_north_router_vc_buf.noc_overlay_edc_wrapper_north_router_data_parity...edc_node_inst` | N Router | 0x02 | `postdfx_aon_clk` | North data parity |
| 5 | `tt_router.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_vc_buf...edc_node_inst` | E Router | 0x03 | `postdfx_aon_clk` | East VC buffer parity |
| 6 | `tt_router.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_header_ecc...edc_node_inst` | E Router | 0x04 | `postdfx_aon_clk` | East header ECC |
| 7 | `tt_router.has_east_router_vc_buf.noc_overlay_edc_wrapper_east_router_data_parity...edc_node_inst` | E Router | 0x05 | `postdfx_aon_clk` | East data parity |
| 8 | `tt_router.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_vc_buf...edc_node_inst` | S Router | 0x06 | `postdfx_aon_clk` | South VC buffer parity |
| 9 | `tt_router.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_header_ecc...edc_node_inst` | S Router | 0x07 | `postdfx_aon_clk` | South header ECC |
| 10 | `tt_router.has_south_router_vc_buf.noc_overlay_edc_wrapper_south_router_data_parity...edc_node_inst` | S Router | 0x08 | `postdfx_aon_clk` | South data parity |
| 11 | `tt_router.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_vc_buf...edc_node_inst` | W Router | 0x09 | `postdfx_aon_clk` | West VC buffer parity |
| 12 | `tt_router.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_header_ecc...edc_node_inst` | W Router | 0x0A | `postdfx_aon_clk` | West header ECC |
| 13 | `tt_router.has_west_router_vc_buf.noc_overlay_edc_wrapper_west_router_data_parity...edc_node_inst` | W Router | 0x0B | `postdfx_aon_clk` | West data parity |
| 14 | `tt_router.has_sec_fence_edc.noc_sec_fence_edc_wrapper...edc_node_inst` | Security | 0xC0 | `postdfx_aon_clk` | Security fence violation detector |
| 15 | `router_noc_sec_conf.u_bridge.u_edc1_node_inst` | NOC Sec Conf | — | `postdfx_aon_clk` | Security configuration bridge — last node in standalone router ring |

---

## Appendix A — Node Type Legend

| Wrapper Generate Block | Error Type | Meaning |
|------------------------|-----------|---------|
| `g_cor_err_with_bit_pos` | COR + UNC | ECC with correction and bit-position reporting (DCache data/tag) |
| `g_cor_err_no_bit_pos` | COR + UNC | ECC with correction but no bit-position (router header ECC) |
| `g_no_cor_err_events` | UNC only | Parity-only, no correction (router VC buf, data path, most memories) |
| `edc_node_inst` (bare) | UNC only | Direct instantiation, no generate wrapper (sec fence, sec conf) |
| `u_edc1_node` / `u_edc1_node_inst` | — | BIU or bridge node (ring controller / security CSR) |
| `u_edc_flex_client_node` | — | BIST flex client — in-situ SRAM test result reporting |

## Appendix B — Clock Domain Summary

| Clock | Description | Applicable Nodes |
|-------|-------------|-----------------|
| `postdfx_aon_clk` | Always-on, post-DFX mux | All NOC router, overlay wrapper memory, WDT, BIU, BIST, AXI buffer nodes |
| `aiclk` | AI compute clock (tile-gated) | Sub-tensix compute (IE/SRCB/Unpack/Pack/SFPU/GPR/CFG/THCON/L1 client), Gtile, T6_MISC, L1W2 SRAM, Dispatch L1 SRAM |

## Appendix C — Harvest Bypass

When a tensix sub-core cluster is harvested (`i_harvest_en` asserted):
- `tt_edc1_serial_bus_demux` in `tt_trin_noc_niu_router_wrap` redirects the ring output from NOC (A-19 exit) → `edc_egress_t6_byp_intf` (bypass path) instead of through T0–T3 and L1 partition
- `tt_edc1_serial_bus_mux` in `tt_neo_overlay_wrapper` selects `edc_ingress_t6_byp_intf` as the overlay ring entry instead of the normal T2-exit path
- Segments B–F (T0/T1/L1/T3/T2) are **entirely bypassed**; only Segment A (NOC) and Segment G (Overlay wrapper) remain active
- The bypass loopback path (`loopback_edc_ingress_intf` / `loopback_edc_egress_intf`) is a single repeater stage at `postdfx_aon_clk`
