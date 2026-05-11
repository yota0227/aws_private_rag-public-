# EDC1 HDD (Round 2: 8 results, topic=EDC)

> **v7** | tt_20260221

## Modules
- tt_edc1_biu_soc_apb4_wrap → inner (APB4 + 5 IRQs)
- tt_edc1_noc_sec_block_reg → inner (NoC security)
- tt_edc1_serial_bus_repeater (i_clk, i_reset_n; assertion)
- tt_edc1_intf_connector (portless)

## BIU APB4
In: s_apb_{psel,penable,pwrite,pprot,paddr,pwdata,pstrb}
Out: s_apb_{pready,prdata,pslverr} + 5 IRQs

## EDC HDD Sub-modules (v7 신규)
- RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (×2)

## Interface (tt_edc_pkg.sv)
ingress/egress/edc_node/sram modports

## [NOT IN KB]
Toggle-handshake, packet format, node ID, ring topology, harvest bypass