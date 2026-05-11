# v8 Chip-Level Search (No Grounding)

> **Pipeline ID:** tt_20260221
> **RAG:** v7 (max_results=50)
> **Search:** `trinity chip package tile_t claim HDD`, max_results=50
> **Date:** 2026-04-29

## Key Findings (vs v7)

### Port Classifier — Full 106 Ports Now Visible

| Category | Count | Key Ports |
|----------|-------|-----------|
| AXI_Interface | 39 | npu_out_awvalid, npu_out_id_t, npu_out_addr_t, npu_out_awlock, npu_out_wvalid, npu_out_wlast, npu_out_arvalid, npu_out_arlock, npu_out_rvalid, npu_out_rlast, npu_out_bvalid, npu_out_rready, npu_out_bready, i_axi_clk |
| SFR_Memory_Config | 17 | SFR_RF_2P_HSC_QNAPA, SFR_RF_2P_HSC_QNAPB, SFR_RF_2P_HSC_EMAA[2:0], SFR_RF_2P_HSC_EMAB[2:0], SFR_RF_2P_HSC_EMASA, SFR_RF_2P_HSC_RAWL, SFR_RF_2P_HSC_RAWLM[1:0], SFR_RA1_HS_MCS[1:0], SFR_RA1_HS_MCSW, SFR_RA1_HS_ADME[2:0], SFR_RF1_HS_MCS[1:0], SFR_RF1_HS_MCSW, SFR_RF1_HS_ADME[2:0], SFR_RF1_HD_MCS[1:0], SFR_RF1_HD_MCSW, SFR_RF1_HD_ADME[2:0] |
| EDC_APB | 16 | i_edc_reset_n, i_edc_apb_psel/penable/pwrite/pprot[2:0]/paddr[5:0]/pwdata[31:0]/pstrb[3:0], o_edc_apb_pready/prdata[31:0]/pslverr, o_edc_fatal_err_irq, o_edc_crit_err_irq, o_edc_cor_err_irq, o_edc_pkt_sent_irq, o_edc_pkt_rcvd_irq |
| **PRTN_Power** | **14** | **TIEL_DFT_MODESCAN, PRTNUN_FC2UN_DATA_IN, PRTNUN_FC2UN_READY_IN, PRTNUN_FC2UN_CLK_IN, PRTNUN_FC2UN_RSTN_IN, PRTNUN_UN2FC_DATA_OUT[3:0], PRTNUN_UN2FC_INTR_OUT[3:0], PRTNUN_FC2UN_DATA_OUT[3:0], PRTNUN_FC2UN_READY_OUT[3:0], PRTNUN_FC2UN_CLK_OUT[3:0], PRTNUN_FC2UN_RSTN_OUT[3:0], PRTNUN_UN2FC_DATA_IN[3:0], PRTNUN_UN2FC_INTR_IN[3:0], ISO_EN[11:0]** |
| APB_Register | 8 | i_reg_psel, i_reg_paddr[31:0], i_reg_penable, i_reg_pwrite, i_reg_pwdata[31:0], o_reg_pready, o_reg_prdata[31:0], o_reg_pslverr |
| DM_Clock_Reset | 3 | i_dm_clk[SizeX-1:0], i_dm_core_reset_n[NumDmComplexes-1:0][DMCoresPerCluster-1:0], i_dm_uncore_reset_n[NumDmComplexes-1:0] |
| AI_Clock_Reset | 2 | i_ai_clk[SizeX-1:0], i_ai_reset_n[SizeX-1:0] |
| NoC_Clock_Reset | 2 | i_noc_clk, i_noc_reset_n |
| Tensix_Reset | 1 | i_tensix_reset_n[NumTensix-1:0] |
| Other | 4 | (uncategorized) |

### v8 NEW — Previously Missing P0 Items

1. **PRTN_Power (14 ports)** — PRTNUN_FC2UN_* daisy chain input/output, PRTNUN_UN2FC_* interrupt/data, ISO_EN[11:0]
2. **AXI_Interface (39 ports)** — npu_out_* / npu_in_* full AXI master interface
3. **SFR_Memory_Config (17 ports)** — SFR_RF_2P_HSC_*, SFR_RA1_HS_*, SFR_RF1_HS_*, SFR_RF1_HD_* SRAM configuration
4. **EDC IRQ outputs (5)** — o_edc_fatal_err_irq, o_edc_crit_err_irq, o_edc_cor_err_irq, o_edc_pkt_sent_irq, o_edc_pkt_rcvd_irq

### Package Constants (unchanged from v7)

13 localparams: SizeX=4, SizeY=5, NumNodes=20, NumTensix=12, NumNoc2Axi=4, NumDispatch=2, NumApbNodes=4, NumDmComplexes=14, DMCoresPerCluster=8, TensixPerCluster=4, EnableDynamicRouting=1'b1, NumAxes=2, NumDirections=2

tile_t enum (8 members), noc_axis_t, noc_direction_t, trinity_clock_routing_t struct (8 fields)
