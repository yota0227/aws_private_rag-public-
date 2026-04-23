# Trinity N1B0 — NoC Routing & Packet Structure HDD (v3)

> **Pipeline:** `tt_20260221`
> **Grounding:** RTL search — topic `NoC`, 5 of 50 results returned
> **All 5 results reference module:** `trinity_noc2axi_router_ne_opt_FBLC`
> **Rule:** Content NOT found in search results is marked `[NOT IN KB]`

---

## 1. Overview

The NoC (Network-on-Chip) subsystem in Trinity N1B0 provides the communication fabric
connecting all tiles in the chip.

| Attribute | Value (from KB) |
|-----------|----------------|
| Key module searched | `trinity_noc2axi_router_ne_opt_FBLC` |
| Pipeline | `tt_20260221` |
| Role | Router handling communication between NoC and AXI bus interface |
| Direction optimization | Northeast (NE) |
| Variant tag | `FBLC` (Full-Bandwidth Low-Cost — inferred from naming) |
| Protocol conversion | NoC ↔ AXI (Advanced eXtensible Interface) |

**From search result [1]:**
> "serves as a router in the NoC, responsible for managing the communication
> between different modules connected to the network"

**From search result [3]:**
> "handles the communication between the NoC and the AXI bus interface.
> The module is optimized for performance and is responsible for routing"

**From search result [5]:**
> "responsible for handling the routing and protocol conversion between
> the NoC and AXI interfaces"

### Routing Algorithms (3 types)

`[NOT IN KB]` — No mention of DIM_ORDER, TENDRIL, or DYNAMIC routing algorithms
was found in the 5 returned HDD sections. These may exist in the remaining
45 of 50 results or in `claim`/`dataflow` analysis types.

---

## 2. Routing Algorithms — Comparison Table

`[NOT IN KB]`

The search results describe the router's general role (NoC ↔ AXI protocol conversion,
NE-direction optimization) but do not contain specific routing algorithm definitions.

Expected content (not found):

| Algorithm | Description | Status |
|-----------|-------------|--------|
| DIM_ORDER | Dimension-ordered XY routing | `[NOT IN KB]` |
| TENDRIL | Adaptive routing with tendril paths | `[NOT IN KB]` |
| DYNAMIC | Dynamic load-balanced routing | `[NOT IN KB]` |

---

## 3. Flit Structure

`[NOT IN KB]`

No `noc_header_address_t` field definitions (x_dest, y_dest, endpoint_id, flit_type)
were found in the search results.

---

## 4. AXI Address Gasket

`[NOT IN KB]`

No 56-bit address structure (target_index, endpoint_id, tlb_index, address)
was found in the search results.

**Partial grounding:** Results [1]–[5] all confirm NoC ↔ AXI protocol conversion
exists, but the address gasket detail is not included.

---

## 5. Virtual Channel

`[NOT IN KB]`

No VC buffer structure or arbitration scheme details were found.

---

## 6. Security Fence

`[NOT IN KB]`

No mention of `tt_noc_sec_fence_edc_wrapper` or SMN group-based access control
was found in the returned results.

---

## 7. Router Module Hierarchy

**From search results [1], [4], [5]:**

```
trinity_noc2axi_router_ne_opt_FBLC    ← top of searched module
├── [NOT IN KB]                        ← no sub-modules listed
│
│   Result [5]: "The `trinity_noc2axi_router_ne_opt_FBLC` module..."
│   followed by Sub-module Hierarchy section (truncated in results)
│
│   Result [1]: "does not have any sub-modules" pattern
│   (consistent with other topic searches on same module)
```

**Note:** Multiple results indicate this module is either a leaf-level block
or its sub-module details were truncated. The broader `tt_noc_*` module tree
(e.g., `tt_noc_router`, `tt_noc_vc_arbiter`, `tt_noc_flit_decoder`) was
**not returned** in this search.

---

## 8. Endpoint Map

`[NOT IN KB]`

No 4×5 grid endpoint_id mapping was found in the search results.

---

## 9. Inter-column Repeaters

`[NOT IN KB]`

No Y=3 / Y=4 repeater structure details were found.

---

## 10. Key Parameters

`[NOT IN KB]`

No `tt_noc_pkg.sv` parameter definitions were found in the search results.

---

## Appendix A: Raw Search Evidence

### Result [1]
- **Topic:** NoC | **Type:** hdd_section | **Pipeline:** tt_20260221
- "serves as a router in the NoC, responsible for managing the communication
  between different modules connected to the network"

### Result [2]
- **Topic:** NoC | **Type:** hdd_section | **Pipeline:** tt_20260221
- "responsible for implementing the router functionality in the network-on-chip
  design, specifically for the northeast (NE) direction"

### Result [3]
- **Topic:** NoC | **Type:** hdd_section | **Pipeline:** tt_20260221
- "handles the communication between the NoC and the AXI bus interface.
  The module is optimized for performance and is responsible for routing"

### Result [4]
- **Topic:** NoC | **Type:** hdd_section | **Pipeline:** tt_20260221
- "facilitating the communication between the NoC and the AXI interfaces.
  This module is optimized for performance"

### Result [5]
- **Topic:** NoC | **Type:** hdd_section | **Pipeline:** tt_20260221
- "responsible for handling the routing and protocol conversion between
  the NoC and AXI interfaces"

---

## Appendix B: Coverage Gap Analysis

| Section | Grounded? | What's missing |
|---------|-----------|----------------|
| 1. Overview | ✅ Yes | Routing algorithm types |
| 2. Routing Algorithms | ⬜ `[NOT IN KB]` | DIM_ORDER / TENDRIL / DYNAMIC comparison |
| 3. Flit Structure | ⬜ `[NOT IN KB]` | noc_header_address_t fields |
| 4. AXI Address Gasket | ⬜ `[NOT IN KB]` | 56-bit structure |
| 5. Virtual Channel | ⬜ `[NOT IN KB]` | VC buffers, arbitration |
| 6. Security Fence | ⬜ `[NOT IN KB]` | tt_noc_sec_fence, SMN |
| 7. Router Hierarchy | ✅ Partial | Only top module confirmed; no sub-modules |
| 8. Endpoint Map | ⬜ `[NOT IN KB]` | 4×5 grid mapping |
| 9. Repeaters | ⬜ `[NOT IN KB]` | Y=3/Y=4 structure |
| 10. Parameters | ⬜ `[NOT IN KB]` | tt_noc_pkg.sv |

**Coverage: 1.5 / 10 sections grounded** — the remaining 45 of 50 NoC results
and other analysis types (claim, dataflow, module_parse) likely contain the missing detail.

---

## Appendix C: Recommended Next Searches

| Priority | Search Config | Expected Yield |
|----------|---------------|----------------|
| 🔴 High | `query: "noc_header_address_t flit"`, `analysis_type: "claim"` | Flit structure, VC, routing |
| 🔴 High | `query: "tt_noc_pkg"`, `analysis_type: "module_parse"` | Package parameters |
| 🔴 High | `query: "DIM_ORDER TENDRIL DYNAMIC"`, `topic: "NoC"` | Routing algorithm claims |
| 🟡 Med | `query: "tt_noc_sec_fence"` | Security fence module |
| 🟡 Med | `query: "endpoint_id grid"`, `analysis_type: "claim"` | Endpoint map |
| 🟢 Low | `query: "repeater inter-column"`, `topic: "NoC"` | Y=3/Y=4 repeaters |
