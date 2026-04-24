# EDC1 Subsystem — Detailed Hardware Design Document (HDD)

> **Pipeline**: `tt_20260221`
> **Version**: v3 R2 (2026-04-22)
> **Grounding**: Single RTL KB search — `topic: "EDC"`, `pipeline_id: "tt_20260221"` — 5 results out of 43.
> **Rule**: Only KB-sourced facts are stated. All else marked `[NOT IN KB]`.

---

## Verbatim Search Evidence

For full traceability, the raw search results are recorded here.

### Result [1] — ✅ CLAIM (first claim ever retrieved from this pipeline)
- **Module**: `tt_edc1_biu_soc_apb4_wrap`
- **Topic**: EDC
- **Type**: claim (behavioral)
- **Claim text**:
  > "The tt_edc1_biu_soc_apb4_wrap module acts as a bridge between the APB4 bus and the internal EDC1 BIU CSR interface, handling read/write requests and generating interrupts."

### Result [2] — hdd_section
- **Module**: `trinity_noc2axi_router_ne_opt_FBLC`
- **EDC expansion**: "Embedded Data Controller"
- **Role**: NOC-to-AXI router within the Trinity SoC

### Result [3] — hdd_section
- **Module**: `trinity_noc2axi_router_ne_opt_FBLC`
- **EDC expansion**: "Embedded Data Compression"
- **Role**: NoC-to-AXI router

### Result [4] — hdd_section
- **Module**: `trinity_noc2axi_router_ne_opt_FBLC`
- **EDC expansion**: "Embedded Data Converter"
- **Role**: NoC-to-AXI router, optimized for performance

### Result [5] — hdd_section
- **Module**: `trinity_noc2axi_router_ne_opt_FBLC`
- **EDC expansion**: "Embedded Device Controller"
- **Role**: NOC-to-AXI router

---

## 1. Overview

**[SOURCE: Result 1 — GROUNDED]**

The EDC1 subsystem is part of the `tt_20260221` pipeline. The only concrete module identified in this search with actual EDC1 functionality is **`tt_edc1_biu_soc_apb4_wrap`**, which is described by a behavioral claim as:

> A bridge between the APB4 bus and the internal EDC1 BIU CSR interface, handling read/write requests and generating interrupts.

This confirms:
- EDC1 has a **BIU (Bus Interface Unit)** sub-block
- The BIU exposes a **CSR (Control/Status Register)** interface
- External access is via the **APB4 bus protocol**
- The module handles **read/write requests** and **interrupt generation**

Results [2]–[5] describe `trinity_noc2axi_router_ne_opt_FBLC` tagged under the EDC topic, but this is a NoC-to-AXI router module — not an EDC-specific block.

### EDC Acronym Discrepancy

The KB contains **4 different expansions** for "EDC" across hdd_section results — all generated for the same module, indicating LLM hallucination in HDD generation:

| Result | EDC Expansion |
|--------|--------------|
| [2] | Embedded Data Controller |
| [3] | Embedded Data Compression |
| [4] | Embedded Data Converter |
| [5] | Embedded Device Controller |

**Note**: The correct expansion (from prior module_parse searches of `tt_edc_pkg.sv`) is likely **Error Detection and Correction**, consistent with the `cor_err` and `err_inj_vec` signals found in that package. `[NOT IN KB — inferred from prior searches]`

---

## 2. Architecture

**[PARTIALLY GROUNDED — Result 1]**

Based on the claim for `tt_edc1_biu_soc_apb4_wrap`, the confirmed architecture path is:

```
┌─────────────┐      ┌──────────────────────────────┐      ┌──────────────┐
│   APB4 Bus  │─────▶│  tt_edc1_biu_soc_apb4_wrap   │─────▶│  EDC1 BIU    │
│  (External) │◀─────│  • read/write handling        │◀─────│  CSR Regs    │
│             │  IRQ ◀│  • interrupt generation       │      │              │
└─────────────┘      └──────────────────────────────┘      └──────────────┘
```

**Components confirmed**:
- APB4 bus interface (external-facing)
- `tt_edc1_biu_soc_apb4_wrap` (bridge module)
- EDC1 BIU CSR interface (internal)
- Interrupt output

**Components from prior searches** (module_parse of `tt_edc_pkg.sv`):
- `ingress` modport — incoming serial data
- `egress` modport — outgoing serial data
- `edc_node` modport — per-node interface
- `sram` modport — SRAM access
- Signals: `req_tgl`, `ack_tgl`, `cor_err`, `err_inj_vec`

Full block diagram beyond this: `[NOT IN KB]`

---

## 3. Serial Bus Interface

**[PARTIALLY GROUNDED — from prior module_parse searches]**

From `tt_edc_pkg.sv` (confirmed in searches #5 and #6):

| Signal | Direction | Description |
|--------|-----------|-------------|
| `req_tgl` | input / output | Toggle-based request handshake |
| `ack_tgl` | output / input | Toggle-based acknowledge handshake |
| `cor_err` | input / output | Correctable error flag |
| `err_inj_vec` | output / input | Error injection vector |

**Modport definitions** (from `tt_edc_pkg.sv`):

| Modport | Role |
|---------|------|
| `ingress` | Incoming serial bus interface |
| `egress` | Outgoing serial bus interface |
| `edc_node` | Per-node EDC interface |
| `sram` | SRAM access interface |

The toggle-handshake pattern (`req_tgl` / `ack_tgl`) is confirmed.

**Not found in KB**:
- `data` (16-bit data bus): `[NOT IN KB]`
- `data_p` (parity bit): `[NOT IN KB]`
- `async_init`: `[NOT IN KB]`
- Bit widths for all signals: `[NOT IN KB]`

---

## 4. Packet Format

`[NOT IN KB]`

No information on fragment structure or `MAX_FRGS` was returned in any search.

---

## 5. Node ID Structure

`[NOT IN KB]`

No information on `node_id_part`, `node_id_subp`, or `node_id_inst` decoding was returned.

---

## 6. Module Hierarchy

**[PARTIALLY GROUNDED — Result 1]**

Confirmed modules in the `tt_edc1_*` namespace:

```
tt_edc1_* (EDC1 subsystem)
├── tt_edc1_biu_soc_apb4_wrap    ← [GROUNDED: Result 1, claim]
│   • APB4 ↔ EDC1 BIU CSR bridge
│   • Read/write handling
│   • Interrupt generation
├── tt_edc1_biu                  ← [INFERRED: name derived from wrapper]
├── tt_edc1_ring                 ← [NOT IN KB]
├── tt_edc1_node                 ← [NOT IN KB]
└── (other tt_edc1_* modules)    ← [NOT IN KB]
```

From `tt_edc_pkg.sv` (prior searches), the package defines modports for `ingress`, `egress`, `edc_node`, and `sram` — suggesting sub-blocks for each, but specific module names are `[NOT IN KB]`.

---

## 7. Ring Topology

`[NOT IN KB]`

No U-shape topology, segment A/B, or U-turn information was returned. The `ingress`/`egress` modports in `tt_edc_pkg.sv` are consistent with a ring or chain topology, but specifics are not in KB.

---

## 8. Harvest Bypass

`[NOT IN KB]`

No information on `edc_mux_demux_sel` or mux/demux bypass mechanism was returned.

---

## 9. BIU (Bus Interface Unit)

**[GROUNDED — Result 1]**

This is the **strongest-grounded section** in this document.

### Module: `tt_edc1_biu_soc_apb4_wrap`

| Attribute | Value | Source |
|-----------|-------|--------|
| Module name | `tt_edc1_biu_soc_apb4_wrap` | Result [1] |
| Claim type | behavioral | Result [1] |
| Bus protocol | APB4 | Result [1] |
| Internal interface | EDC1 BIU CSR | Result [1] |
| Functions | Read/write request handling | Result [1] |
| Interrupt | Generates interrupts | Result [1] |

### Register Access Path

```
                    APB4 Bus
                       │
                       ▼
        ┌──────────────────────────────┐
        │  tt_edc1_biu_soc_apb4_wrap   │
        │                              │
        │  APB4 PSEL/PENABLE/PWRITE ──▶│──┐
        │  APB4 PADDR/PWDATA ─────────▶│  │  EDC1 BIU
        │                              │  │  CSR Interface
        │  APB4 PRDATA ◀──────────────│◀─┘
        │  APB4 PREADY ◀──────────────│
        │                              │
        │  IRQ ◀───────────────────────│  (interrupt output)
        └──────────────────────────────┘
```

**Not in KB**: CSR register map, address offsets, register bit fields.

---

## 10. CDC / Synchronization

`[NOT IN KB]`

No clock domain crossing information was returned. The toggle-handshake pattern (`req_tgl`/`ack_tgl`) is inherently CDC-safe, but explicit CDC module names or synchronizer details are not in KB.

---

## 11. Instance Paths

**[PARTIALLY GROUNDED — from prior module_parse searches]**

The `tt_edc_pkg.sv` file was found at 5 different paths in the pipeline, indicating multiple integration contexts:

| # | Path | Context |
|---|------|---------|
| 1 | `rtl-sources/tt_20260221/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | Main RTL tree |
| 2 | `rtl-sources/tt_20260221/used_in_n1/mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | N1 integration (mem_port variant) |
| 3 | `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | N1 integration (legacy, no_mem_port) |
| 4 | `rtl-sources/tt_20260221/used_in_n1/make_enc/260223_no_srun/org/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | N1 encryption build |
| 5 | `rtl-sources/tt_20260221/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | N1 integration (default) |

Instance paths within Trinity top-level (e.g., `trinity.u_edc_ring[*]`): `[NOT IN KB]`

---

## KB Coverage Analysis

### This Search (8th overall)

| Result # | Type | Module | New Data? |
|----------|------|--------|-----------|
| [1] | **claim** ✨ | `tt_edc1_biu_soc_apb4_wrap` | **YES — first real EDC1 module claim** |
| [2] | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | No (repeat) |
| [3] | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | No (repeat) |
| [4] | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | No (repeat) |
| [5] | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | No (repeat) |

### Cumulative Grounding (8 searches)

| Section | Status | Evidence |
|---------|--------|----------|
| 1. Overview | ✅ Grounded | BIU claim + modport structure |
| 2. Architecture | ✅ Partial | APB4→BIU CSR path confirmed |
| 3. Serial Bus | ✅ Partial | req_tgl/ack_tgl/cor_err/err_inj_vec + 4 modports |
| 4. Packet Format | ⬜ NOT IN KB | — |
| 5. Node ID | ⬜ NOT IN KB | — |
| 6. Module Hierarchy | ✅ Partial | 1 module confirmed: tt_edc1_biu_soc_apb4_wrap |
| 7. Ring Topology | ⬜ NOT IN KB | — |
| 8. Harvest Bypass | ⬜ NOT IN KB | — |
| 9. BIU | ✅ **Fully Grounded** | Claim: APB4↔BIU CSR bridge, R/W, IRQ |
| 10. CDC | ⬜ NOT IN KB | — |
| 11. Instance Paths | ✅ Partial | 5 file paths confirmed |

**Coverage: 5/11 sections have at least partial grounding. 1 section (BIU) is fully grounded.**

---

## Key Milestone

**Result [1] is the first `claim`-type data ever retrieved from the `tt_20260221` pipeline across 8 searches.** This confirms that claim data does exist in the KB — the previous searches simply didn't surface them because they matched `hdd_section` or `module_parse` results first.

### Recommended Next Searches

| Priority | Parameters | Expected Yield |
|----------|-----------|---------------|
| 🔴 High | `query: "tt_edc1"`, `analysis_type: "claim"` | More EDC1 module claims (ring, node, bypass) |
| 🔴 High | `query: "edc_node harvest bypass"`, `topic: "EDC"` | Harvest bypass mechanism |
| 🟡 Med | `query: "edc ring topology segment"` | Ring topology details |
| 🟡 Med | `query: "node_id_part node_id_subp"` | Node ID structure |
