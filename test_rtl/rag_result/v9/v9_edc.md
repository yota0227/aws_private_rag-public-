# EDC1 Subsystem — Hardware Design Document

**Pipeline ID:** tt_20260221
**RAG Version:** v9
**Generated:** 2026-05-06

---

## 1. Overview

The EDC1 (Error Detection and Correction, version 1) subsystem provides chip-level error management through a serial bus ring topology. It implements toggle-handshake protocol with 16-bit data + parity for reliable inter-node communication.

Key modules:
- `tt_edc1_intf_connector` — Interface connector (ring node)
- `tt_edc1_serial_bus_repeater` — Serial bus signal repeater
- `tt_edc1_biu_soc_apb4_wrap` — Bus Interface Unit (APB4 wrapper)
- `tt_edc1_noc_sec_block_reg` — NoC security block registers

---

## 2. Module Hierarchy

```
tt_edc1_biu_soc_apb4_wrap
└── edc1_biu_soc_apb4_inner

tt_edc1_noc_sec_block_reg
└── edc1_noc_sec_block_reg_inner

tt_edc1_serial_bus_repeater
tt_edc1_intf_connector
```

---

## 3. Serial Bus Interface

The `tt_edc1_serial_bus_repeater` module:
- Inputs: `i_clk`, `i_reset_n`
- Contains property assertions for protocol verification
- Repeats serial bus signals along the ring

---

## 4. BIU (Bus Interface Unit)

`tt_edc1_biu_soc_apb4_wrap` provides the APB4 register access path:

| Port | Direction | Description |
|------|-----------|-------------|
| i_clk | input | Clock |
| i_reset_n | input | Active-low reset |
| s_apb_psel | input | APB select |
| s_apb_penable | input | APB enable |
| s_apb_pwrite | input | APB write |
| s_apb_pprot | input | APB protection |
| s_apb_paddr | input | APB address |
| s_apb_pwdata | input | APB write data |
| s_apb_pstrb | input | APB strobe |
| s_apb_pready | output | APB ready |
| s_apb_prdata | output | APB read data |
| s_apb_pslverr | output | APB slave error |
| fatal_err_irq | output | Fatal error interrupt |
| crit_err_irq | output | Critical error interrupt |
| cor_err_irq | output | Correctable error interrupt |
| pkt_sent_irq | output | Packet sent interrupt |
| pkt_rcvd_irq | output | Packet received interrupt |

---

## 5. NoC Security Block

`tt_edc1_noc_sec_block_reg` manages NoC security configuration:
- Inputs: `i_clk`, `i_reset_n`, `i_reg_cs`, `i_reg_wr_en`, `i_reg_addr`, `i_reg_wr_data`
- Various security configuration input/output ports
- Instantiates `edc1_noc_sec_block_reg_inner`

---

## 6. Ring Topology

Trinity instantiates EDC nodes in two configurations:
- `edc_direct_conn_nodes` — Direct connection (tt_edc1_intf_connector)
- `edc_loopback_conn_nodes` — Loopback connection (tt_edc1_intf_connector)

The ring forms a U-shape topology:
- Segment A: downward path
- U-turn at bottom
- Segment B: upward return path

---

## 7. Harvest Bypass

Harvest bypass allows non-functional tiles to be bypassed in the EDC ring using mux/demux selection (`edc_mux_demux_sel`).

---

## 8. Top-Level EDC Ports (from trinity.sv)

16 EDC_APB ports exposed at chip level:
- 5 EDC IRQ outputs: fatal, critical, correctable, packet sent, packet received
- Full APB4 slave interface (psel, penable, pwrite, pprot, paddr, pwdata, pstrb, pready, prdata, pslverr)
- Dedicated `i_edc_reset_n`

---

*Generated from RAG v9 pipeline (tt_20260221).*
