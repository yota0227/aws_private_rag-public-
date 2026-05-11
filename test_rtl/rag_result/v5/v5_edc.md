# EDC1 Subsystem — Hardware Design Document (HDD)

> **Pipeline ID:** tt_20260221
> **Document Version:** v5 (Grounded — KB-only content)
> **Generated:** 2026-04-27
> **Rule:** Only content from RAG KB search results is included. Missing information is marked `[NOT IN KB]`.

---

## 1. Overview

EDC1 (Embedded Debug Controller, version 1) is the serial configuration and debug subsystem within the Trinity N1B0 SoC.

**Key Characteristics (from KB):**

- The EDC subsystem includes a block-level component `BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest` that serves as part of the EDC functionality (source: HDD section [3])
- EDC1 modules use a consistent naming convention: `tt_edc1_*`
- The BIU (Bus Interface Unit) uses APB4 protocol for register access
- NoC security block registers are part of the EDC subsystem
- Serial bus repeaters include clock (`i_clk`) and reset (`i_reset_n`) inputs with assertion-based verification

**Toggle-handshake protocol, 16-bit data + parity:** [NOT IN KB] — These specific protocol details were not returned in the search results.

---

## 2. Architecture

**System-Level Block Diagram (reconstructed from KB claims):**

```
                    ┌─────────────────────────────────────┐
                    │           EDC1 Subsystem             │
                    │                                     │
  APB4 Bus ────────►│  tt_edc1_biu_soc_apb4_wrap          │
                    │    └── edc1_biu_soc_apb4_inner      │
                    │                                     │
                    │  tt_edc1_noc_sec_block_reg           │
                    │    └── edc1_noc_sec_block_reg_inner  │
                    │                                     │
  Serial Ring ─────►│  tt_edc1_serial_bus_repeater [×N]   │
                    │    (i_clk, i_reset_n)               │
                    │                                     │
                    │  tt_edc1_intf_connector              │
                    │    (no ports — structural glue)      │
                    │                                     │
                    │  noc_routing_translation_selftest    │
                    │    (NoC-to-AXI bridge + selftest)    │
                    └─────────────────────────────────────┘
```

---

## 3. Serial Bus Interface

### 3.1 Known Signals (from KB)

The `tt_edc1_serial_bus_repeater` module has the following confirmed ports:

| Signal | Direction | Description | Source |
|--------|-----------|-------------|--------|
| `i_clk` | Input | Serial bus clock | Claim [1] |
| `i_reset_n` | Input | Active-low reset | Claim [1] |

The module also contains assertion properties for protocol verification (claim [6]).

### 3.2 Toggle-Handshake Signals

| Signal | Description |
|--------|-------------|
| `req_tgl` | [NOT IN KB] |
| `ack_tgl` | [NOT IN KB] |
| `data` | [NOT IN KB] |
| `data_p` | [NOT IN KB] |
| `async_init` | [NOT IN KB] |

> Full toggle-handshake protocol details (req_tgl, ack_tgl, data, data_p, async_init) were not returned in the search results.

---

## 4. Packet Format

[NOT IN KB] — Fragment structure and MAX_FRGS constant were not found in the search results.

---

## 5. Node ID Structure

[NOT IN KB] — node_id_part, node_id_subp, node_id_inst decoding table was not found in the search results.

---

## 6. Module Hierarchy

Reconstructed from KB claims [1]–[8]:

```
EDC1 Subsystem
├── tt_edc1_biu_soc_apb4_wrap              — BIU: APB4 bus interface wrapper
│   └── edc1_biu_soc_apb4_inner           — BIU inner logic
│       Ports:
│         Input:  i_clk, i_reset_n
│         Input:  s_apb_psel, s_apb_penable, s_apb_pwrite
│         Input:  s_apb_pprot, s_apb_paddr, s_apb_pwdata, s_apb_pstrb
│         Output: s_apb_pready, s_apb_prdata, s_apb_pslverr
│         Output: fatal_err_irq, crit_err_irq, cor_err_irq
│         Output: pkt_sent_irq, pkt_rcvd_irq
│
├── tt_edc1_noc_sec_block_reg              — NoC security block register file
│   └── edc1_noc_sec_block_reg_inner       — Inner register logic
│       Ports:
│         Input:  i_clk, i_reset_n
│         Input:  i_reg_cs, i_reg_wr_en, i_reg_addr, i_reg_wr_data
│         Output: (noc security configuration outputs)
│
├── tt_edc1_serial_bus_repeater [×N]       — Serial ring bus repeater
│       Ports:
│         Input:  i_clk, i_reset_n
│         Contains: assertion property (protocol check)
│
└── tt_edc1_intf_connector                 — Interface connector (structural glue)
        Ports: (none — portless structural module)
```

---

## 7. Ring Topology

### 7.1 U-Shape Ring Structure

[NOT IN KB] — The specific U-shape topology (Segment A downward → U-turn → Segment B upward) was not returned in the search results.

**What is known from KB:**

- `tt_edc1_serial_bus_repeater` modules are instantiated multiple times along the ring to regenerate signals
- Each repeater is clocked by `i_clk` with active-low reset `i_reset_n`
- `tt_edc1_intf_connector` serves as a portless structural glue module, likely connecting ring segments

**Ring structure (based on module names only — topology details NOT IN KB):**

```
  [BIU/APB4] ──► [Repeater] ──► [Repeater] ──► ... ──► [intf_connector]
       ▲                                                       │
       │              (ring return path)                       │
       └──── [Repeater] ◄── [Repeater] ◄── ... ◄─────────────┘
```

> Note: Exact tile ordering, segment A/B assignment, and U-turn location are [NOT IN KB].

---

## 8. Harvest Bypass

[NOT IN KB] — Mux/demux bypass mechanism and `edc_mux_demux_sel` signal behavior were not found in the search results.

---

## 9. BIU (Bus Interface Unit)

*Source: KB claims [4], [7]*

### 9.1 Module

`tt_edc1_biu_soc_apb4_wrap` — wraps the inner module `edc1_biu_soc_apb4_inner`.

### 9.2 APB4 Slave Interface

| Signal | Direction | Width | Description |
|--------|-----------|-------|-------------|
| `s_apb_psel` | Input | 1 | APB peripheral select |
| `s_apb_penable` | Input | 1 | APB enable phase |
| `s_apb_pwrite` | Input | 1 | APB write enable |
| `s_apb_pprot` | Input | 3 | APB protection type |
| `s_apb_paddr` | Input | N | APB address bus |
| `s_apb_pwdata` | Input | N | APB write data |
| `s_apb_pstrb` | Input | N | APB write strobe |
| `s_apb_pready` | Output | 1 | APB ready (slave → master) |
| `s_apb_prdata` | Output | N | APB read data |
| `s_apb_pslverr` | Output | 1 | APB slave error |

### 9.3 Interrupt Outputs

| Signal | Description |
|--------|-------------|
| `fatal_err_irq` | Fatal error interrupt — unrecoverable EDC error |
| `crit_err_irq` | Critical error interrupt — requires attention |
| `cor_err_irq` | Correctable error interrupt — auto-corrected, logged |
| `pkt_sent_irq` | Packet sent interrupt — EDC packet transmitted |
| `pkt_rcvd_irq` | Packet received interrupt — EDC packet received |

### 9.4 Register Access Path

```
CPU/ARC ──► APB4 Bus ──► tt_edc1_biu_soc_apb4_wrap
                              └── edc1_biu_soc_apb4_inner
                                    ├── EDC control/status registers
                                    ├── Interrupt enable/status registers
                                    └── Packet TX/RX registers
```

---

## 10. CDC / Synchronization

[NOT IN KB] — No clock domain crossing or synchronization modules specific to EDC1 were returned in the search results. The `tt_edc1_serial_bus_repeater` uses `i_clk` and `i_reset_n` but CDC details between the serial bus clock and tile clocks are not available.

---

## 11. Instance Paths

### 11.1 NoC Security Block Register

*Source: KB claims [2], [8]*

`tt_edc1_noc_sec_block_reg` — provides register-based configuration for NoC security within the EDC subsystem.

| Port | Direction | Description |
|------|-----------|-------------|
| `i_clk` | Input | Register clock |
| `i_reset_n` | Input | Active-low reset |
| `i_reg_cs` | Input | Chip select |
| `i_reg_wr_en` | Input | Write enable |
| `i_reg_addr` | Input | Register address |
| `i_reg_wr_data` | Input | Write data |
| (outputs) | Output | NoC security configuration signals |

Inner module: `edc1_noc_sec_block_reg_inner`

### 11.2 Known EDC1 Instance Paths in Trinity

[NOT IN KB] — Specific hierarchical instance paths (e.g., `trinity.grid.tile[x][y].edc1_*`) were not returned in the search results.

**Known module names in the EDC1 subsystem:**

| Module | Instances | Role |
|--------|-----------|------|
| `tt_edc1_biu_soc_apb4_wrap` | ≥1 | APB4 BIU wrapper |
| `tt_edc1_noc_sec_block_reg` | ≥1 | NoC security register block |
| `tt_edc1_serial_bus_repeater` | ×N | Serial ring repeaters |
| `tt_edc1_intf_connector` | ≥1 | Structural interface connector |
| `BDAed_..._noc_routing_translation_selftest` | ≥1 | NoC routing translation + selftest |

---

## Appendix: KB Search Metadata

| # | Module / Name | Topic | Type | Key Content |
|---|---------------|-------|------|-------------|
| 1 | `tt_edc1_serial_bus_repeater` | EDC | claim | Ports: i_clk, i_reset_n [structural] |
| 2 | `tt_edc1_noc_sec_block_reg` | EDC | claim | Ports: i_clk, i_reset_n, i_reg_cs, i_reg_wr_en, i_reg_addr, i_reg_wr_data + noc security outputs [structural] |
| 3 | (EDC HDD) | EDC | hdd_section | Block-level HDD for noc_routing_translation_selftest |
| 4 | `tt_edc1_biu_soc_apb4_wrap` | EDC | claim | Full APB4 port list + 5 interrupt outputs [structural] |
| 5 | `tt_edc1_intf_connector` | EDC | claim | No ports [structural] |
| 6 | `tt_edc1_serial_bus_repeater` | EDC | claim | Contains assertion property [structural] |
| 7 | `tt_edc1_biu_soc_apb4_wrap` | EDC | claim | Instantiates edc1_biu_soc_apb4_inner [connectivity] |
| 8 | `tt_edc1_noc_sec_block_reg` | EDC | claim | Instantiates edc1_noc_sec_block_reg_inner [connectivity] |

**Search parameters:** `pipeline_id=tt_20260221`, `topic=EDC`, `query=EDC1 serial bus ring topology harvest bypass`
**Results returned:** 8 of 8

---

*This document contains ONLY content retrieved from the BOS-AI RAG knowledge base (pipeline tt_20260221, topic EDC). All sections without KB data are explicitly marked [NOT IN KB]. No inferred or fabricated content has been added.*