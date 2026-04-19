# N1B0 NOC2AXI Performance Monitor HDD v0.1

**Module:** `noc2axi_perf_monitor`
**RTL file:** `used_in_n1/rtl/noc2axi_perf_monitor.sv`
**Lines:** 533
**Synthesizable:** NO — simulation-only. Contains `output real`, `$time`, `$value$plusargs`, `$display`.
**Used in:** Instantiated inside `trinity_noc2axi_n_opt` (or `trinity_noc2axi_ne/nw_opt` corner NIUs) as a passive monitoring probe. Not present in gate-level netlists.

---

## 1. Purpose

`noc2axi_perf_monitor` measures AXI transaction latency at the NOC2AXI bridge. It:
1. Tracks **first-beat read data latency**: time from AR channel handshake to first R-channel valid
2. Tracks **write response latency**: time from AW channel handshake to B-channel valid
3. Optionally tracks **round-trip latency** by AXI ID (when `+MONITOR_ROUND_TRIP_LATENCY=1`)
4. Reports statistics via `$display` and continuously drives output ports of type `real`

The monitor is passive: it observes AXI signals without driving them.

---

## 2. Module Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AXI_ID_WIDTH` | 8 | Width of AXI ID bus. Determines ID space size = 2^AXI_ID_WIDTH |
| `MAX_OUTSTANDING_TXN` | 256 | Depth of per-ID tracking queues |
| `INTERFACE_ID` | 0 | Identifies which AXI interface this monitor watches (printed in log messages) |

---

## 3. Ports

### 3.1 Clock / Reset
| Port | Dir | Description |
|------|-----|-------------|
| `i_clk` | input | AXI clock domain clock |
| `i_reset_n` | input | Active-low reset |

### 3.2 AXI Observation Inputs (read channels)
| Port | Dir | Description |
|------|-----|-------------|
| `i_axi_arid[AXI_ID_WIDTH-1:0]` | input | AR channel: read ID |
| `i_axi_arvalid` | input | AR channel: valid |
| `i_axi_arready` | input | AR channel: ready |
| `i_axi_rid[AXI_ID_WIDTH-1:0]` | input | R channel: response ID |
| `i_axi_rvalid` | input | R channel: valid |
| `i_axi_rready` | input | R channel: ready |
| `i_axi_rlast` | input | R channel: last beat flag |

### 3.3 AXI Observation Inputs (write channels)
| Port | Dir | Description |
|------|-----|-------------|
| `i_axi_awid[AXI_ID_WIDTH-1:0]` | input | AW channel: write ID |
| `i_axi_awvalid` | input | AW channel: valid |
| `i_axi_awready` | input | AW channel: ready |
| `i_axi_bid[AXI_ID_WIDTH-1:0]` | input | B channel: response ID |
| `i_axi_bvalid` | input | B channel: valid |
| `i_axi_bready` | input | B channel: ready |

### 3.4 Output Metrics (type: `real`, non-synthesizable)
| Port | Dir | Description |
|------|-----|-------------|
| `o_avg_rd_latency` | output real | Running average of read first-beat latency (cycles) |
| `o_avg_wr_latency` | output real | Running average of write B-response latency (cycles) |
| `o_max_rd_latency` | output real | Maximum read latency observed |
| `o_max_wr_latency` | output real | Maximum write latency observed |
| `o_min_rd_latency` | output real | Minimum read latency observed |
| `o_min_wr_latency` | output real | Minimum write latency observed |
| `o_total_rd_txn` | output real | Total completed read transactions count |
| `o_total_wr_txn` | output real | Total completed write transactions count |

---

## 4. Monitoring Modes

### Mode 1: Timestamp-based latency (always active)

Every cycle the monitor checks for AXI handshakes:
- **AR handshake** (`arvalid & arready`): record `$time` for that `arid` in an associative array
- **R handshake** (`rvalid & rready`): on first beat (or every beat), compute latency = `$time - ar_timestamp[rid]`; update min/max/avg outputs

- **AW handshake** (`awvalid & awready`): record `$time` for that `awid`
- **B handshake** (`bvalid & bready`): compute latency = `$time - aw_timestamp[bid]`; update write stats

Averages are computed as running means:
```
avg = (avg * (count-1) + new_latency) / count
```

### Mode 2: Per-ID round-trip latency (opt-in via plusarg)

When `+MONITOR_ROUND_TRIP_LATENCY=1`, the monitor tracks each transaction from AR/AW to final R-last/B per AXI ID using FIFO queues (depth = `MAX_OUTSTANDING_TXN`). This enables:
- Per-ID latency histograms
- Detection of ID-specific bottlenecks
- Round-trip rather than first-beat measurement for reads

Verbosity of output is controlled by `+PERF_MONITOR_VERBOSITY=N`:
| Level | Output |
|-------|--------|
| 0 | No per-transaction output; final summary only |
| 1 | Print on every 1000th transaction |
| 2 | Print on every transaction completion |
| 3 | Print on every AXI beat (very verbose) |

---

## 5. SW Guide — Simulation Usage

### 5.1 Enabling the Monitor

The monitor is always instantiated in simulation. No RTL control is needed.

Enable round-trip latency tracking:
```
+MONITOR_ROUND_TRIP_LATENCY=1
```

Set verbosity level (0-3, default=0):
```
+PERF_MONITOR_VERBOSITY=2
```

Example simulation invocation:
```bash
vcs +PERF_MONITOR_VERBOSITY=1 +MONITOR_ROUND_TRIP_LATENCY=1 <other_args>
```

### 5.2 Reading Output Metrics

The `output real` ports are available in simulation waveform viewers. In SystemVerilog testbenches:

```systemverilog
// Hierarchical path to monitor instance (example NE NIU, X=1)
real avg_rd, max_rd;
assign avg_rd = dut.gen_noc2axi_router_ne_opt.trinity_noc2axi_n_opt.perf_monitor.o_avg_rd_latency;
assign max_rd = dut.gen_noc2axi_router_ne_opt.trinity_noc2axi_n_opt.perf_monitor.o_max_rd_latency;
```

### 5.3 Sampling in Testbench

At end-of-test, read metrics:
```systemverilog
$display("NOC2AXI[%0d] Avg RD latency = %0.2f cycles, Max = %0.2f, TotalTxn=%0.0f",
         INTERFACE_ID, o_avg_rd_latency, o_max_rd_latency, o_total_rd_txn);
```

### 5.4 Multi-Interface Monitoring

Each NOC2AXI tile instance has a separate monitor with its own `INTERFACE_ID`:
- NE corner (X=0,Y=4): INTERFACE_ID=0
- NE router tile (X=1,Y=4): INTERFACE_ID=1
- NW router tile (X=2,Y=4): INTERFACE_ID=2
- NW corner (X=3,Y=4): INTERFACE_ID=3

The `INTERFACE_ID` is printed in `$display` messages to disambiguate.

---

## 6. Latency Definitions

| Metric | Start event | End event |
|--------|------------|-----------|
| Read latency | AR handshake (`arvalid & arready`) | First R beat (`rvalid & rready`) |
| Read round-trip | AR handshake | R last beat (`rlast & rvalid & rready`) |
| Write latency | AW handshake (`awvalid & awready`) | B handshake (`bvalid & bready`) |

All times measured in simulation clock cycles (integer `$time` units divided by clock period, depending on timescale).

---

## 7. Limitations

1. **Not synthesizable.** Will cause synthesis errors if included in synthesis flow. Guarded by `` `ifndef SYNTHESIS `` pragmas in the instantiating module.
2. **No persistance.** Statistics reset on `i_reset_n` assertion.
3. **Shared-ID collision.** If the same AXI ID is reused before the previous transaction completes, latency measurement for that ID may be incorrect (FIFO overflow or timestamp overwrite). Set `MAX_OUTSTANDING_TXN` appropriately.
4. **Time resolution.** `$time` granularity is the simulation timescale. For sub-cycle precision, use the `real`-valued version of `$time`.

---

*RTL source: `used_in_n1/rtl/noc2axi_perf_monitor.sv` (533 lines)*
*Author: N1B0 HDD project, 2026-03-18*
