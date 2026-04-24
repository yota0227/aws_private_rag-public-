# NoC Routing & Packet Structure — Detailed HDD (R2)

- **Pipeline**: `tt_20260221`
- **Search**: `topic: "NoC"`, `query: "NoC routing flit VC"` — 5 results / 50 total
- **Grounding Rule**: Only KB-sourced content included. Missing = `[NOT IN KB]`.
- **Generated**: 2026-04-22

---

## Search Results Summary

All 5 results are `hdd_section` type for the same module:

| # | Module | Type | Key Statements |
|---|--------|------|----------------|
| [1] | `trinity_noc2axi_router_ne_opt_FBLC` | hdd_section | "serves as a router in the NoC, responsible for managing the communication between different modules" |
| [2] | `trinity_noc2axi_router_ne_opt_FBLC` | hdd_section | "implementing the router functionality… specifically for the **northeast (NE) direction**" |
| [3] | `trinity_noc2axi_router_ne_opt_FBLC` | hdd_section | "handles the communication between the NoC and the AXI bus interface… optimized for performance… routing data packets" |
| [4] | `trinity_noc2axi_router_ne_opt_FBLC` | hdd_section | "facilitating the communication between the NoC and the AXI (Advanced eXtensible Interface) interfaces… optimized for performance" |
| [5] | `trinity_noc2axi_router_ne_opt_FBLC` | hdd_section | "handling the routing and protocol conversion between the NoC and AXI interfaces" / "does not have any sub-modules" (leaf) |

---

## 1. Overview

**Source**: Results [1]–[5]

The NoC (Network-on-Chip) subsystem in the `tt_20260221` pipeline provides on-chip communication infrastructure. The only module surfaced by the KB is `trinity_noc2axi_router_ne_opt_FBLC`, which:

- Serves as a **router** in the NoC mesh
- Manages **communication between different modules** connected to the network [1]
- Implements router functionality **specifically for the northeast (NE) direction** [2]
- Handles **routing and protocol conversion between NoC and AXI interfaces** [5]
- Is **optimized for performance** [3][4]
- Routes **data packets** between NoC fabric and AXI bus endpoints [3]

### Module Name Decoding

```
trinity_noc2axi_router_ne_opt_FBLC
│       │       │      │  │   └── FBLC: variant/config identifier
│       │       │      │  └── opt: optimized version
│       │       │      └── ne: northeast corner placement
│       │       └── router: routing function
│       └── noc2axi: NoC-to-AXI protocol bridge
└── trinity: top-level SoC
```

---

## 2. Routing Algorithms

**Status**: `[NOT IN KB]`

No information on DIM_ORDER, TENDRIL, or DYNAMIC routing algorithms was returned in this search. The KB only confirms that the module performs "routing data packets" [3] without specifying the algorithm.

| Algorithm | Description | Use Case |
|-----------|-------------|----------|
| DIM_ORDER | `[NOT IN KB]` | `[NOT IN KB]` |
| TENDRIL | `[NOT IN KB]` | `[NOT IN KB]` |
| DYNAMIC | `[NOT IN KB]` | `[NOT IN KB]` |

---

## 3. Flit Structure

**Status**: `[NOT IN KB]`

The search confirms the module handles "data packets" [3] but no details on:
- `noc_header_address_t` fields
- `x_dest`, `y_dest`, `endpoint_id`, `flit_type`
- Flit width or encoding

---

## 4. AXI Address Gasket

**Status**: Partially Grounded

**Confirmed from KB**:
- The module performs **protocol conversion between NoC and AXI** [5]
- AXI = **Advanced eXtensible Interface** [4]
- The conversion is **bidirectional** (NoC ↔ AXI) [3][4][5]

**Not in KB**:
- 56-bit address structure
- `target_index`, `endpoint_id`, `tlb_index`, `address` field breakdown

---

## 5. Virtual Channel

**Status**: `[NOT IN KB]`

No VC buffer structure, depth, or arbitration scheme information was returned.

---

## 6. Security Fence

**Status**: `[NOT IN KB]`

No information on `tt_noc_sec_fence_edc_wrapper` or SMN group-based access control was returned.

---

## 7. Router Module Hierarchy

**Source**: Result [5]

```
trinity_noc2axi_router_ne_opt_FBLC    [CONFIRMED — leaf module, no sub-modules]
├── (no sub-modules per KB)            [5]: "does not have any sub-modules"
│
└── Inferred parent context:
    └── trinity (top)
        └── (instantiation path: [NOT IN KB])
```

**Key fact**: Result [5] explicitly states this module **"does not have any sub-modules"** — it is a leaf-level block.

> **Note**: `trinity_router` is NOT instantiated in N1B0 (EMPTY by design) and is excluded from this hierarchy per design rules.

---

## 8. Endpoint Map

**Status**: `[NOT IN KB]`

No endpoint_id assignment table or 4×5 grid placement was returned. The only placement hint is **"northeast (NE) direction"** [2], suggesting this particular variant is instantiated in the NE corner of the mesh.

---

## 9. Inter-column Repeaters

**Status**: `[NOT IN KB]`

No information on Y=3 or Y=4 repeater structures was returned.

---

## 10. Key Parameters

**Status**: `[NOT IN KB]`

No `tt_noc_pkg.sv` parameters were returned. The module name itself encodes some configuration:

| Inferred Parameter | Value | Source |
|-------------------|-------|--------|
| Direction | NE (northeast) | Module name [2] |
| Optimization | opt (enabled) | Module name |
| Variant | FBLC | Module name |
| Protocol | NoC-to-AXI | Module name + [5] |

---

## Cross-Reference: Previous Searches

From earlier `module_parse` searches (not in this search but in workspace memory):

| Data Point | Source | Value |
|------------|--------|-------|
| `tt_edc_pkg.sv` modports | module_parse search #5/#6 | `ingress`, `egress`, `edc_node`, `sram` |
| EDC serial signals | module_parse search #5/#6 | `req_tgl`, `ack_tgl`, `cor_err`, `err_inj_vec` |

These are EDC-related, not NoC-specific, but confirm the pipeline contains parseable RTL data beyond hdd_sections.

---

## Grounding Scorecard

| # | Section | Status | Evidence |
|---|---------|--------|----------|
| 1 | Overview | ✅ Grounded | [1]–[5] |
| 2 | Routing Algorithms | ⬜ `[NOT IN KB]` | — |
| 3 | Flit Structure | ⬜ `[NOT IN KB]` | — |
| 4 | AXI Address Gasket | 🟡 Partial | Protocol conversion confirmed |
| 5 | Virtual Channel | ⬜ `[NOT IN KB]` | — |
| 6 | Security Fence | ⬜ `[NOT IN KB]` | — |
| 7 | Router Hierarchy | ✅ Grounded | Leaf module confirmed |
| 8 | Endpoint Map | 🟡 Minimal | NE direction only |
| 9 | Repeaters | ⬜ `[NOT IN KB]` | — |
| 10 | Key Parameters | 🟡 Minimal | Module name inference only |

**Overall Coverage: 2 full + 3 partial / 10 = ~35%**

---

## R1 → R2 Comparison

| Aspect | R1 (v3_noc.md) | R2 (this file) |
|--------|----------------|----------------|
| Claim data | 0 claims | 0 claims (NoC topic has no claims in KB) |
| Verbatim evidence | Minimal | Full per-result quotes in summary table |
| Module name analysis | Listed | Decoded (prefix breakdown) |
| Cross-reference | None | Previous search memory included |
| Grounding tags | Present | Expanded with scorecard |

**Key finding for NoC**: Unlike EDC (which yielded `tt_edc1_biu_soc_apb4_wrap` claim) and Overlay (which yielded 3 claims for cluster_ctrl/fds modules), the **NoC topic has zero claims** — only LLM-generated hdd_sections for the same `noc2axi_router` module.

---

## Recommended Next Searches

| Priority | Query | Expected Yield |
|----------|-------|----------------|
| 🔴 | `query: "tt_noc_router"`, no topic filter | Actual NoC router module_parse data |
| 🔴 | `query: "noc_header_address_t flit"` | Flit structure from pkg file |
| 🟡 | `query: "tt_noc_sec_fence"` | Security fence claims |
| 🟡 | `query: "tt_noc_pkg"` | Package parameters |
| 🟢 | `query: "virtual channel vc buffer"` | VC architecture |
