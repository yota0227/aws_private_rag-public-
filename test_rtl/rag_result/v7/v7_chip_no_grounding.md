# Chip-Level HDD (Round 1: 20 results)

> **v7** | tt_20260221

## Package (13 localparams)
SizeX=4, SizeY=5, NumNodes=20, NumTensix=12, NumNoc2Axi=4, NumDispatch=2, NumApbNodes=4, NumDmComplexes=14, EnableDynamicRouting=1'b1, TensixPerCluster=4, DMCoresPerCluster=8, NumAxes=2, NumDirections=2

## tile_t (8 members)
TENSIX=3'd0, NOC2AXI_NE_OPT=3'd1, NOC2AXI_ROUTER_NE_OPT=3'd2, NOC2AXI_ROUTER_NW_OPT=3'd3, NOC2AXI_NW_OPT=3'd4, DISPATCH_E=3'd5, DISPATCH_W=3'd6, ROUTER=3'd7

## Top Ports (800자 확대)
i_axi_clk, i_noc_clk, i_noc_reset_n, i_ai_clk[SizeX-1:0], i_ai_reset_n[SizeX-1:0], i_tensix_reset_n[NumTensix-1:0], i_edc_reset_n, i_dm_clk[SizeX-1:0], i_dm_core_reset_n[NumDmComplexes-1:0][DMCoresPerCluster-1:0], i_dm_uncore_reset_n[NumDmComplexes-1:0], i_reg_psel, i_reg_paddr[31:0], i_reg_penable, i_reg_pwrite, i_reg_pwdata[31:0], o_reg_pready, o_reg_prdata[31:0], o_reg_pslverr, i_edc_apb_psel, i_edc_apb_penable, i_edc_apb_pwrite, i_edc_apb_pprot[2:0], i_edc_apb_paddr[5:0], i_edc_apb_pwdata[31:0], i_edc_apb_pstrb[3:0], o_edc_apb_pready, o_edc_apb_prdata[31:0]

## Port Claims (v7 classifier)
- AI_Clock_Reset(2): i_ai_clk, i_ai_reset_n
- Tensix_Reset(1): i_tensix_reset_n
- DM_Clock_Reset(3): i_dm_clk, i_dm_core_reset_n, i_dm_uncore_reset_n

## Instances
tt_tensix_with_l1, tt_dispatch_top_east, tt_dispatch_top_west, edc_direct/loopback_conn_nodes

## Files
trinity_pkg.sv, trinity.sv (3 variants)