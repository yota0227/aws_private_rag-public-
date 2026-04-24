# Trinity N1B0 — Integrated Hardware Design Document (HDD)

> **Pipeline:** `tt_20260221`
> **Generated:** 2026-04-22
> **Grounding:** RTL search `query="HDD"`, `pipeline_id="tt_20260221"`, 5 results returned out of 109 total
> **Rule:** Only KB-sourced content included. Anything absent is marked **[NOT IN KB]**.

---

## Document Index

| # | Section | KB Source (Topic / Type) |
|---|---------|--------------------------|
| 1 | Overview | Overlay hdd_section, DFX hdd_section, EDC hdd_section, Dispatch hdd_section |
| 2 | Package Constants & Grid | [NOT IN KB] |
| 3 | Top-Level Ports | [NOT IN KB] |
| 4 | Module Hierarchy | Overlay, DFX, EDC, Dispatch hdd_sections |
| 5 | Overlay | Overlay hdd_section |
| 6 | Dispatch Engine | Dispatch hdd_section |
| 7 | NoC Fabric & Routing | [NOT IN KB] |
| 8 | NIU / AXI Bridge | Derived from root module name |
| 9 | Clock & Reset Architecture | [NOT IN KB] |
| 10 | EDC | EDC hdd_section |
| 11 | SRAM Inventory | [NOT IN KB] |
| 12 | DFX | DFX hdd_section (×2 results) |
| 13 | RTL File Reference | Inferred from search metadata |

---

## 1. Overview

All five returned HDD sections reference the same root module:

```
trinity_noc2axi_router_ne_opt_FBLC
```

This module is part of the `tt_20260221` pipeline. Per the KB results, it serves as the anchor block for multiple functional topics — **Overlay**, **DFX**, **EDC**, and **Dispatch** — indicating it is a **NoC-to-AXI router** variant (`noc2axi`) with NE-optimized, FBLC-configured routing. Each topic-specific HDD describes a different functional facet of the same physical block.

> **Note:** `trinity_router` is **not** instantiated in N1B0 (EMPTY by design) and is excluded from all hierarchy descriptions below.

### Key Observations from KB

- The block integrates **Overlay**, **DFX**, **EDC**, and **Dispatch** functions within a single `noc2axi_router` frame.
- The naming convention `ne_opt_FBLC` suggests a **northeast-optimized** placement with **FBLC** (Flit-Based Link Configuration).
- All results are `hdd_section` type, confirming auto-generated block-level design documents from the RTL analysis pipeline.

---

## 2. Package Constants & Grid

**[NOT IN KB]**

The following items were not returned in the search results:

| Item | Status |
|------|--------|
| `SizeX`, `SizeY` | [NOT IN KB] |
| `NumTensix` | [NOT IN KB] |
| `tile_t` enum | [NOT IN KB] |
| Grid dimensions (4×5) | [NOT IN KB] |
| Tile type counts | [NOT IN KB] |

---

## 3. Top-Level Ports

**[NOT IN KB]**

No port table was returned for the top-level `trinity` module or `trinity_noc2axi_router_ne_opt_FBLC` in this search.

---

## 4. Module Hierarchy

Based on the KB results, the following hierarchy is confirmed:

```
tt_20260221 (pipeline)
└── trinity_noc2axi_router_ne_opt_FBLC    ← root block for all 5 HDD results
    ├── [Overlay sub-modules]              ← referenced in Overlay HDD
    ├── [Dispatch sub-modules]             ← referenced in Dispatch HDD
    ├── [EDC sub-modules]                  ← referenced in EDC HDD
    └── [DFX sub-modules]                  ← referenced in DFX HDD (×2)
```

> Specific sub-module names within each topic were truncated in search results. Full sub-module trees require per-topic deep queries.

---

## 5. Overlay

**Source:** KB Result [1] — Topic: `Overlay`, Type: `hdd_section`

### 5.1 Overview (from KB)

> The `trinity_noc2axi_router_ne_opt_FBLC` module is a part of the `tt_20260221` pipeline and is responsible for the **Overlay** functionality. This block-level HDD provides a detailed overview of the module's design and implementation.

### 5.2 Sub-module Hierarchy

The KB result references a "Sub-module" section (Section 2 in the original HDD), but the content was truncated in the search result.

| Item | Status |
|------|--------|
| CPU Cluster | [NOT IN KB — truncated] |
| L1 Cache | [NOT IN KB — truncated] |
| APB Slave | [NOT IN KB — truncated] |

---

## 6. Dispatch Engine

**Source:** KB Result [5] — Topic: `Dispatch`, Type: `hdd_section`

### 6.1 Overview (from KB)

> The `trinity_noc2axi_router_ne_opt_FBLC` module is a part of the `tt_20260221` pipeline, specifically in the **Dispatch** topic. This block-level Hardware Design Document (HDD) provides details about the module's **sub-module hierarchy**, **functional details**, **control path**, **clock/reset structure**...

### 6.2 Confirmed Content Areas

The Dispatch HDD explicitly mentions coverage of:

| Area | Mentioned in KB |
|------|-----------------|
| Sub-module hierarchy | ✅ Yes |
| Functional details | ✅ Yes |
| Control path | ✅ Yes |
| Clock/reset structure | ✅ Yes |

### 6.3 Dispatch-Specific Details

| Item | Status |
|------|--------|
| East/West dispatch paths | [NOT IN KB — truncated] |
| Command distribution structure | [NOT IN KB — truncated] |
| `de_to_t6` / `t6_to_de` signals | [NOT IN KB — truncated] |

---

## 7. NoC Fabric & Routing

**[NOT IN KB]**

| Item | Status |
|------|--------|
| Routing algorithms (DOR / Tendril / Dynamic) | [NOT IN KB] |
| Flit structure | [NOT IN KB] |
| VC buffer organization | [NOT IN KB] |

> The root module name `noc2axi_router` confirms NoC-to-AXI bridging exists, but no protocol-level details were returned.

---

## 8. NIU / AXI Bridge

**Partially inferred from module name only.**

The module `trinity_noc2axi_router_ne_opt_FBLC` contains `noc2axi` in its name, confirming:

- A **NoC-to-AXI bridge** (NIU) function exists within this block.
- The `ne_opt` suffix suggests **northeast-optimized** placement variant.
- `FBLC` likely denotes a flit/link configuration parameter.

| Item | Status |
|------|--------|
| ATT (Address Translation Table) | [NOT IN KB] |
| SMN Security | [NOT IN KB] |
| AXI port width / protocol version | [NOT IN KB] |

---

## 9. Clock & Reset Architecture

**[NOT IN KB]**

| Item | Status |
|------|--------|
| `ai_clk` domain | [NOT IN KB] |
| `noc_clk` domain | [NOT IN KB] |
| `dm_clk` domain | [NOT IN KB] |
| `ref_clk` domain | [NOT IN KB] |
| Reset chain / power partition | [NOT IN KB] |

> The **Dispatch HDD** (Result [5]) mentions "clock/reset structure" as a covered topic, but details were truncated.

---

## 10. EDC

**Source:** KB Result [3] — Topic: `EDC`, Type: `hdd_section`

### 10.1 Overview (from KB)

> The `trinity_noc2axi_router_ne_opt_FBLC` block is a part of the `tt_20260221` pipeline and belongs to the **EDC** (Embedded Design Compiler) topic. This block-level HDD provides a detailed description of the module's **design**, **functionality**, and **verification**...

### 10.2 Confirmed Content Areas

| Area | Mentioned in KB |
|------|-----------------|
| Design description | ✅ Yes |
| Functionality | ✅ Yes |
| Verification | ✅ Yes |

### 10.3 EDC Topology Details

| Item | Status |
|------|--------|
| Ring topology | [NOT IN KB — truncated] |
| Serial bus structure | [NOT IN KB — truncated] |
| Harvest bypass | [NOT IN KB — truncated] |
| `req_tgl` / `ack_tgl` signals | Not in this search (found in prior `tt_edc_pkg.sv` module_parse searches) |

---

## 11. SRAM Inventory

**[NOT IN KB]**

| Item | Status |
|------|--------|
| Memory type/count table | [NOT IN KB] |
| L1 SRAM instances | [NOT IN KB] |
| NoC VC buffer SRAM | [NOT IN KB] |

---

## 12. DFX

**Source:** KB Results [2] and [4] — Topic: `DFX`, Type: `hdd_section`

### 12.1 Overview — Result [2] (from KB)

> The `trinity_noc2axi_router_ne_opt_FBLC` block is a part of the `tt_20260221` pipeline and is responsible for the **DFX (Design for Extensibility)** functionality. This block-level HDD provides details on the sub-module hierarchy, functional details, control...

### 12.2 Overview — Result [4] (from KB)

> The `trinity_noc2axi_router_ne_opt_FBLC` block is a part of the `tt_20260221` pipeline and is responsible for the **DFX (Dynamic Functional eXchange)** functionality. This block-level Hardware Design Document (HDD) provides a detailed overview of the sub-module hierarchy, functional details...

### 12.3 Observations

Two distinct DFX HDD sections were returned with **different expansions** of the DFX acronym:
- Result [2]: **Design for Extensibility**
- Result [4]: **Dynamic Functional eXchange**

This may indicate two separate DFX sub-functions within the same block, or an inconsistency in the auto-generated HDD descriptions.

### 12.4 Confirmed Content Areas (both results)

| Area | Result [2] | Result [4] |
|------|-----------|-----------|
| Sub-module hierarchy | ✅ | ✅ |
| Functional details | ✅ | ✅ |
| Control path | ✅ (truncated) | ✅ |

### 12.5 DFX-Specific Details

| Item | Status |
|------|--------|
| iJTAG | [NOT IN KB — truncated] |
| Scan chains | [NOT IN KB — truncated] |
| MBIST | [NOT IN KB — truncated] |

---

## 13. RTL File Reference

**Inferred from search metadata (pipeline `tt_20260221`).**

All five results reference the same module `trinity_noc2axi_router_ne_opt_FBLC`. No explicit file paths were returned in this `hdd_section` search. From prior `module_parse` searches on the same pipeline, the following paths are known:

| File | Content |
|------|---------|
| `rtl-sources/tt_20260221/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package — modports: `ingress`, `egress`, `edc_node`, `sram` |
| `rtl-sources/tt_20260221/used_in_n1/mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package (N1 mem_port variant) |
| `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package (legacy no_mem_port) |
| `rtl-sources/tt_20260221/used_in_n1/make_enc/260223_no_srun/org/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package (enc build variant) |
| `rtl-sources/tt_20260221/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package (N1 main) |

> File paths for Overlay, Dispatch, DFX HDD source RTL: **[NOT IN KB]**

---

## Appendix A: Search Metadata

| Parameter | Value |
|-----------|-------|
| Query | `HDD` |
| Pipeline ID | `tt_20260221` |
| Results returned | 5 of 109 |
| Result types | All `hdd_section` |
| Topics covered | Overlay, DFX (×2), EDC, Dispatch |
| Root module | `trinity_noc2axi_router_ne_opt_FBLC` (all 5 results) |

## Appendix B: Coverage Gap Analysis

| Section | Grounded? | Action Needed |
|---------|-----------|---------------|
| Overview | ✅ Partial | — |
| Package Constants & Grid | ❌ | Search `analysis_type="module_parse"` or `topic="Package"` |
| Top-Level Ports | ❌ | Search `query="trinity"` with `analysis_type="module_parse"` |
| Module Hierarchy | ✅ Partial | Deep query per topic for sub-modules |
| Overlay | ✅ Partial (truncated) | Search `topic="Overlay"` for full content |
| Dispatch Engine | ✅ Partial (truncated) | Search `topic="Dispatch"` for full content |
| NoC Fabric | ❌ | Search `topic="NoC"` |
| NIU / AXI Bridge | ⚠️ Name only | Search `query="noc2axi"` |
| Clock & Reset | ❌ | Search `analysis_type="clock_domain"` |
| EDC | ✅ Partial (truncated) | Search `topic="EDC"` for full content |
| SRAM Inventory | ❌ | Search `query="SRAM"` or `analysis_type="module_parse"` |
| DFX | ✅ Partial (truncated) | Search `topic="DFX"` for full content |
| RTL File Reference | ✅ EDC paths only | Expand with per-topic searches |

---

*End of document — generated from a single RTL KB search (5/109 results). Sections marked [NOT IN KB] require additional targeted searches for completion.*
