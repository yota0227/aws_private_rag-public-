# N1B0 NOC2AXI_ROUTER_OPT HDD v0.1

**Module:** `trinity_noc2axi_router_ne_opt` / `trinity_noc2axi_router_nw_opt`
**RTL file (NE):** `used_in_n1/rtl/trinity_noc2axi_router_ne_opt.sv`
**RTL file (NW):** `used_in_n1/rtl/trinity_noc2axi_router_nw_opt.sv`
**Physical placement:** (X=1,Y=4+Y=3) for NE_OPT; (X=2,Y=4+Y=3) for NW_OPT
**EndpointIndex (NOC2AXI level, Y=4):** NE=9, NW=14
**EndpointIndex (Router level, Y=3):** NE=8, NW=13

---

## 1. Overview

`trinity_noc2axi_router_ne_opt` and `trinity_noc2axi_router_nw_opt` are **dual-row composite tiles** introduced in N1B0. Each module spans two physical rows:

- **Y=4 (north):** NOC2AXI bridge — AXI master/slave ports, DRAM connectivity, EDC node at Y=4
- **Y=3 (south):** NoC router — 5-port mesh router, dispatch feedthroughs, EDC node at Y=3

In the baseline Trinity, these rows were handled by two separate modules (`trinity_noc2axi_n_opt` at Y=4, `trinity_router` at Y=3). N1B0 combines them because the inter-row south↔north NoC connections and clock routing would otherwise require external top-level wiring.

The `_ne_opt` variant faces **east** (connects east to X=0 NOC2AXI corner) and the `_nw_opt` variant faces **west** (connects west to X=3 NOC2AXI corner). NE=north-east corner side; NW=north-west corner side. Both variants are structurally identical except for port orientation naming and directionality.

---

## 2. Port Prefix Conventions

Ports are prefixed to indicate which physical row they belong to:

| Prefix | Physical row | Sub-module driven |
|--------|-------------|-------------------|
| `noc2axi_i_*` / `noc2axi_o_*` | Y=4 | `trinity_noc2axi_n_opt` clocks, resets, flits, config |
| `i_noc_*`, `i_local_nodeid_*`, `i_noc_endpoint_id` | Y=4 | NoC config shared to both sub-modules |
| `i/o_noc2axi_*` | Y=4 | AXI master (outbound to DRAM) |
| `i/o_axi2noc_*` | Y=4 | AXI slave (inbound from fabric) |
| `router_i_*` / `router_o_*` | Y=3 | `trinity_router` clocks, flits |
| `router_o_ai_clk`, `router_o_dm_clk`, `router_o_nocclk` | Y=3 | Clock outputs driving `clock_routing_out[x][y-1]` at trinity top |
| `router_o_*_reset_n` | Y=3 | Reset outputs into Y=3 clock_routing |
| `router_i/o_flit_*_{east,west,south}` | Y=3 | Horizontal + south NoC flits |
| `i/o_de_to_t6_*`, `i_t6_to_de_*` | Y=3 | Dispatch feedthrough signals |
| `edc_egress_intf`, `loopback_edc_ingress_intf` | Y=3 | EDC ring at Y=3 level |
| `i_edc_apb_*`, `o_edc_apb_*` | Y=4 | EDC APB CSR access |

**Note:** The module does **not** expose `noc2axi_o_*_south` or any Y=4 clock output directly at Y=4. The clock outputs (`o_ai_clk`, `o_nocclk`, `o_dm_clk`) emerge from the embedded `trinity_router` at port `router_o_*` and are mapped to `clock_routing_out[x][y-1]` (Y=3) at the trinity top level.

---

## 3. Internal Sub-Module Hierarchy

```
trinity_noc2axi_router_ne_opt / _nw_opt
├── trinity_noc2axi_n_opt          (Y=4 NOC2AXI bridge)
│   ├── tt_noc2axi                 (NoC→AXI master path)
│   ├── tt_axi2noc                 (AXI slave→NoC path)
│   ├── edc_node (node_id=9/14)    (EDC at Y=4)
│   └── SFR register block         (APB CSR: SMN security, ATT, mesh config)
└── trinity_router                 (Y=3 Router)
    ├── tt_router                  (5-port mesh router)
    │   ├── gen_input_port[*].tt_router_input_if
    │   ├── gen_output_port[*].tt_router_output_if
    │   ├── tt_router_niu_input_if / tt_router_niu_output_if
    │   └── tt_noc_repeaters_cardinal (N/S/E/W inbound+outbound)
    ├── mem_wrap_*_router_input_[N/E/S/W]  (VC input FIFOs, 72×2048 in N1B0)
    └── edc_node (node_id=8/13)    (EDC at Y=3)
```

---

## 4. Internal Wire Connections (Y=4 ↔ Y=3)

The south port of `trinity_noc2axi_n_opt` connects to the north port of `trinity_router`. These are internal wires declared at lines 291–337 of `trinity_noc2axi_router_ne_opt.sv`.

### 4.1 NoC Flit Cross-Wires

```
// NOC2AXI south → Router north (outbound from NOC2AXI going south into Router)
router_i_flit_in_req_north       = noc2axi_o_flit_out_req_south;
noc2axi_i_flit_out_resp_south    = router_o_flit_in_resp_north;

// Router north → NOC2AXI south (flit from Router going north into NOC2AXI)
noc2axi_i_flit_in_req_south      = router_o_flit_out_req_north;
router_i_flit_out_resp_north     = noc2axi_o_flit_in_resp_south;
```

All four handshake signals (req_in, resp_in, req_out, resp_out) are wired. Types:
- `noc_req_t`: flit request (data + valid)
- `noc_resp_t`: flit response (credit/ready)

### 4.2 Clock Routing Chain

`trinity_noc2axi_n_opt` generates buffered clock and reset outputs. These feed into `trinity_router` via an intermediate struct wire `noc2axi_clock_routing_out` → `router_clock_routing_in`:

| `noc2axi_clock_routing_out` field | → `router_clock_routing_in` field |
|----------------------------------|----------------------------------|
| `.ai_clk` | `.ai_clk` |
| `.noc_clk` | `.noc_clk` |
| `.dm_clk` | `.dm_clk` |
| `.ai_clk_reset_n` | `.ai_clk_reset_n` |
| `.noc_clk_reset_n` | `.noc_clk_reset_n` |
| `.dm_core_clk_reset_n` | `.dm_core_clk_reset_n` |
| `.dm_uncore_clk_reset_n` | `.dm_uncore_clk_reset_n` |
| `.tensix_reset_n` | `.tensix_reset_n` |
| `.power_good` | `.power_good` |

All 9 fields of `trinity_clock_routing_t` are passed. The router then outputs the buffered versions (`router_o_ai_clk`, `router_o_dm_clk`, etc.) which drive `clock_routing_out[x][y-1]` at the trinity top level for Y=3.

### 4.3 EDC Ring Chain

Two EDC interfaces cross between the sub-modules:

**Forward path (NOC2AXI→Router in ring order):**
```
router_edc_ingress_intf.req_tgl      = noc2axi_edc_egress_intf.req_tgl;
router_edc_ingress_intf.data         = noc2axi_edc_egress_intf.data;
router_edc_ingress_intf.data_p       = noc2axi_edc_egress_intf.data_p;
router_edc_ingress_intf.async_init   = noc2axi_edc_egress_intf.async_init;
router_edc_ingress_intf.err          = noc2axi_edc_egress_intf.err;
noc2axi_edc_egress_intf.ack_tgl      = router_edc_ingress_intf.ack_tgl;  // ack back
```

**Loopback path (Router loopback→NOC2AXI loopback ingress):**
```
noc2axi_loopback_edc_ingress_intf.req_tgl     = router_loopback_edc_egress_intf.req_tgl;
noc2axi_loopback_edc_ingress_intf.data        = router_loopback_edc_egress_intf.data;
noc2axi_loopback_edc_ingress_intf.data_p      = router_loopback_edc_egress_intf.data_p;
noc2axi_loopback_edc_ingress_intf.async_init  = router_loopback_edc_egress_intf.async_init;
noc2axi_loopback_edc_ingress_intf.err         = router_loopback_edc_egress_intf.err;
router_loopback_edc_egress_intf.ack_tgl       = noc2axi_loopback_edc_ingress_intf.ack_tgl;
```

The **outer-facing** EDC ports (exposed at the composite module boundary) are:
- `edc_egress_intf` → from `trinity_router` (Y=3 level, ring exits south)
- `loopback_edc_ingress_intf` → into `trinity_router` (Y=3 loopback return)
- `i_edc_apb_*` / `o_edc_apb_*` → APB config for `trinity_noc2axi_n_opt` EDC node (Y=4)

EDC node_id assignment:
- `trinity_noc2axi_n_opt` gets Y=4: `i_noc_endpoint_id` = 9 (NE) or 14 (NW)
- `trinity_router` gets Y=3: `i_noc_endpoint_id - 1` = 8 (NE) or 13 (NW)

---

## 5. NoC Config ID Offsets

`trinity_router` receives the following adjusted IDs:

```systemverilog
.i_local_nodeid_y   (i_local_nodeid_y - 1),   // Y=4→Y=3 physical row
.i_noc_endpoint_id  (i_noc_endpoint_id - 1),  // EP=9→8 (NE), EP=14→13 (NW)
```

`i_local_nodeid_x` and `i_noc_x_size`, `i_noc_y_size` are passed unchanged to both sub-modules.

---

## 6. trinity_router Parameters (N1B0-specific)

These are hard-coded in `trinity_noc2axi_router_ne_opt.sv` lines 519–531:

| Parameter | Value (decimal) | RTL literal | Description |
|-----------|----------------|-------------|-------------|
| REP_DEPTH_LOOPBACK | 6 | `6` | Loopback reg-slice depth (added N1B0 2026-03-04) |
| REP_DEPTH_OUTPUT | 4 | `4` | Output reg-slice depth |
| NUM_REPEATERS_INBOUND_WEST | 4 | `32'b100` | Inbound repeater stages from west |
| NUM_REPEATERS_OUTBOUND_WEST | 4 | `32'b100` | Outbound repeater stages to west |
| NUM_REPEATERS_INBOUND_EAST | 1 | `32'b1` | Inbound from east |
| NUM_REPEATERS_OUTBOUND_EAST | 1 | `32'b1` | Outbound to east |
| NUM_REPEATERS_INBOUND_NORTH | 1 | `32'b1` | Inbound from north (internal NOC2AXI) |
| NUM_REPEATERS_OUTBOUND_NORTH | 1 | `32'b1` | Outbound to north (internal NOC2AXI) |
| NUM_REPEATERS_INBOUND_SOUTH | 5 | `32'b101` | Inbound from south (to Tensix rows) |
| NUM_REPEATERS_OUTBOUND_SOUTH | 5 | `32'b101` | Outbound to south (to Tensix rows) |

**Design rationale:** West repeater count=4 matches the inter-column 4-stage repeater at Y=4. South repeater count=5 handles the distance to Y=2 Tensix tiles. REP_DEPTH_LOOPBACK=6 and REP_DEPTH_OUTPUT=4 are register-slice additions for N1B0 timing closure (comment: `Jungyu Im 20260304`).

---

## 7. AXI Parameters (Configurable)

Passed from trinity top as parameters, stored in `trinity_noc2axi_router_ne_opt` and forwarded to `trinity_noc2axi_n_opt`:

| Parameter | Description |
|-----------|-------------|
| `AXI_SLV_OUTSTANDING_READS` | Max outstanding read transactions on AXI slave port |
| `AXI_SLV_OUTSTANDING_WRITES` | Max outstanding write transactions on AXI slave port |
| `AXI_SLV_RD_RDATA_FIFO_DEPTH` | RDATA FIFO depth — selectable via `define in N1B0 |

`AXI_SLV_RD_RDATA_FIFO_DEPTH` can be set to 32/64/128/256/512/1024 depending on compile-time `define. Corresponding SRAM wrapper instances exist in `used_in_n1/rtl/` for each depth.

---

## 8. SFR Memory Config Ports

At the end of both sub-module instantiations, SRAM macro control ports are passed through unchanged from the top-level:

| Port | Width | Description |
|------|-------|-------------|
| `SFR_RF_2P_HSC_QNAPA` | 1 | SRAM margin adjust A |
| `SFR_RF_2P_HSC_QNAPB` | 1 | SRAM margin adjust B |
| `SFR_RF_2P_HSC_EMAA` | 3 | Extra margin adjust A |
| `SFR_RF_2P_HSC_EMAB` | 3 | Extra margin adjust B |
| `SFR_RF_2P_HSC_EMASA` | 1 | Extra margin adjust self-time A |
| `SFR_RF_2P_HSC_RAWL` | 1 | Read-after-write latency |
| `SFR_RF_2P_HSC_RAWLM` | 2 | Read-after-write latency mode |

These are forwarded to all embedded SRAMs (router VC input FIFOs, NOC2AXI RDATA FIFOs). They are driven from the trinity top-level SFR APB register interface.

---

## 9. Trinity Top-Level Connections

In `trinity.sv`, the composite module is instantiated as:

**NE_OPT (X=1, Y=4+Y=3, EP_NOC2AXI=9, EP_ROUTER=8):**
```systemverilog
gen_noc2axi_router_ne_opt: trinity_noc2axi_router_ne_opt #(...) (
    // Clock routing in
    .noc2axi_i_ai_clk       (clock_routing_in[1][4].ai_clk),   // per-col clock
    .noc2axi_i_dm_clk       (clock_routing_in[1][4].dm_clk),
    .noc2axi_i_nocclk       (i_noc_clk),                        // single global
    // Clock routing out (goes to Y=3)
    .router_o_ai_clk        (clock_routing_out[1][3].ai_clk),
    .router_o_dm_clk        (clock_routing_out[1][3].dm_clk),
    .router_o_nocclk        (clock_routing_out[1][3].noc_clk),
    // Flit connections: east/west at Y=4, east/west/south at Y=3
    .noc2axi_i_flit_in_req_east   (noc_flit_x[0][4]...),
    .router_i_flit_in_req_east    (noc_flit_x[1][3]...),
    .router_i_flit_in_req_west    (via 6-stage repeater),
    .router_o_flit_out_req_west   (via 6-stage repeater),
    // EDC
    .edc_egress_intf        (edc_chain[col_1][seg_router]...),
    // PRTN not applicable (Y=3 router row has no PRTN)
)
```

---

## 10. Delta vs Baseline

| Feature | Baseline Trinity | N1B0 |
|---------|-----------------|------|
| Y=4 NOC2AXI | `trinity_noc2axi_n_opt` standalone | embedded inside `_router_*_opt` |
| Y=3 Router | `trinity_router` standalone | embedded inside `_router_*_opt` |
| South↔North flit | driven at trinity top level | internal wires in composite module |
| Clock routing Y=3 | driven at trinity top from Y=4 module outputs | driven by `trinity_router` `router_o_*` ports inside composite |
| REP_DEPTH_LOOPBACK | 0 (no loopback reg-slice) | 6 |
| REP_DEPTH_OUTPUT | 0 | 4 |
| West repeaters | 0 | 4 inbound + 4 outbound |
| South repeaters | default | 5 inbound + 5 outbound |
| EDC loopback path | driven externally | internally chained |

---

## 11. SW Programming

The `trinity_noc2axi_router_ne_opt` tile contains two independently addressable APB register banks:

### 11.1 NOC2AXI CSR (Y=4 physical row)
Accessed via `i_reg_psel/paddr/penable/pwrite/pwdata` on the APB bus (one APB per column, `getApbIndex = x`).

Register map inherited from `trinity_noc2axi_n_opt` (see NIU_HDD_v0.1.md Section 10):
- ATT endpoint translation table (1024-entry, 12-bit mask per entry)
- ATT routing translation table (32×1024 routing bits)
- SMN security ranges (8 ranges: base/mask/allow/deny)
- Mesh config override registers (harvest: `noc_x_size`, `noc_y_size`, `disable_endpoints`)
- EDC CSR (via `i_edc_apb_*` APB port, separate from main APB)

### 11.2 Router CSR (Y=3 physical row)
The embedded `trinity_router` does **not** have an independent APB port in this composite. Router configuration (`i_noc_x_size`, `i_noc_y_size`, `i_local_nodeid_*`, `i_noc_endpoint_id`) is passed as static inputs from the trinity top. Dynamic routing table updates go through the NoC2AXI ATT only.

### 11.3 Harvest (Mesh Config)
To disable tiles during harvest:
1. Write to `mesh_config_override` CSR in NOC2AXI bank
2. Set `noc_y_size` to exclude dead rows
3. Set `disable_endpoints` bitmask for harvested tiles
4. The same value is automatically propagated to `trinity_router` via the `trinity_noc2axi_n_opt` mesh-config EDC override mechanism (see M8 NIU HDD, Section 12)

---

*RTL source: `used_in_n1/rtl/trinity_noc2axi_router_ne_opt.sv` lines 1–612 (NE), `trinity_noc2axi_router_nw_opt.sv` (structurally identical, NW orientation)*
*Author: N1B0 HDD project, 2026-03-18*
