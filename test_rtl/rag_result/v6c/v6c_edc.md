# EDC1 Subsystem HDD

> **Pipeline ID:** tt_20260221 | **Version:** v6c | **Search:** topic=EDC (8 results)

---

## Modules

| Module | Function | Ports |
|--------|----------|-------|
| `tt_edc1_biu_soc_apb4_wrap` → inner | APB4 BIU | s_apb_* + 5 IRQs |
| `tt_edc1_noc_sec_block_reg` → inner | NoC security | i_reg_cs/wr_en/addr/wr_data |
| `tt_edc1_serial_bus_repeater` | Ring repeater | i_clk, i_reset_n; assertion |
| `tt_edc1_intf_connector` | Structural glue | No ports |

## Interface (`tt_edc_pkg.sv`)

ingress(in req_tgl, out ack_tgl, in cor_err, out err_inj_vec), egress(reverse), edc_node(bidir), sram(in err_inj_vec, out cor_err)

## [NOT IN KB]

Toggle-handshake details, packet format, node ID, ring topology, harvest bypass, CDC