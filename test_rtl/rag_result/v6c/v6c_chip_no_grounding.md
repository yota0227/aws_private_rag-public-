# N1B0 NPU — Chip-Level HDD (No Grounding)

> **Pipeline ID:** tt_20260221 | **Version:** v6c | **RAG:** v4.1 + Package Parser v2
> **Search:** Round 1 — chip-level (20 results)

---

## Package Constants (`trinity_pkg.sv`)

13 localparams: SizeX=4, SizeY=5, NumNodes=20, NumTensix=12, NumNoc2Axi=4, NumDispatch=2, NumApbNodes=4, NumDmComplexes=14, EnableDynamicRouting=1'b1, TensixPerCluster=4, DMCoresPerCluster=8, NumAxes=2, NumDirections=2

## tile_t enum (8 members)

TENSIX=3'd0, NOC2AXI_NE_OPT=3'd1, NOC2AXI_ROUTER_NE_OPT=3'd2, NOC2AXI_ROUTER_NW_OPT=3'd3, NOC2AXI_NW_OPT=3'd4, DISPATCH_E=3'd5, DISPATCH_W=3'd6, ROUTER=3'd7

## trinity_clock_routing_t (8 fields)

ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, dm_uncore_clk_reset_n, tensix_reset_n, power_good

## NoC enums

noc_axis_t: Y_AXIS=1'b0, X_AXIS=1'b1 | noc_direction_t: POSITIVE=1'b0, NEGATIVE=1'b1

## Top module `trinity` (trinity.sv)

Ports: i_axi_clk, i_noc_clk, i_noc_reset_n, i_ai_clk[SizeX-1:0], i_ai_reset_n[SizeX-1:0], i_tensix_reset_n[NumTensix-1:0], i_edc_reset_n, i_edc_apb_*

Instances: tt_tensix_with_l1, tt_dispatch_top_east, tt_dispatch_top_west, edc_direct_conn_nodes(tt_edc1_intf_connector), edc_loopback_conn_nodes(tt_edc1_intf_connector)

## Clock

tt_clkbuf, tt_clkgater/tt_clk_gater (interconnected network), tt_clkdiv2

## DFX

tt_instrn_engine_wrapper_dfx (11in/9out, iJTAG+clock)

## Files

`used_in_n1/rtl/targets/4x5/trinity_pkg.sv`, `used_in_n1/rtl/trinity.sv`