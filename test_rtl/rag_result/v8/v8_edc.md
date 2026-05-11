# v8 EDC Topic Search

> **Pipeline ID:** tt_20260221
> **Search:** `EDC serial bus BIU topology ring`, topic=EDC, max_results=30
> **Date:** 2026-04-29

## EDC Modules (8 results)

1. **tt_edc1_biu_soc_apb4_wrap** — APB4 bridge with full signal list:
   - In: i_clk, i_reset_n, s_apb_psel, s_apb_penable, s_apb_pwrite, s_apb_pprot, s_apb_paddr, s_apb_pwdata, s_apb_pstrb
   - Out: s_apb_pready, s_apb_prdata, s_apb_pslverr, fatal_err_irq, crit_err_irq, cor_err_irq, pkt_sent_irq, pkt_rcvd_irq
   - Instantiates: edc1_biu_soc_apb4_inner

2. **tt_edc1_noc_sec_block_reg** — NoC security register block:
   - In: i_clk, i_reset_n, i_reg_cs, i_reg_wr_en, i_reg_addr, i_reg_wr_data + noc security config ports
   - Instantiates: edc1_noc_sec_block_reg_inner

3. **tt_edc1_serial_bus_repeater** — Serial bus repeater:
   - In: i_clk, i_reset_n; Contains property assert

4. **tt_edc1_intf_connector** — Portless interface connector

## EDC Interface (from tt_edc_pkg.sv)

4 modports: ingress / egress / edc_node / sram. Toggle-handshake: req_tgl / ack_tgl

## Ring Topology / Harvest Bypass / CDC

[NOT IN KB] — requires trinity.sv generate block analysis or Spec RAG

## v8 vs v7: No new EDC claims. Coverage unchanged.
