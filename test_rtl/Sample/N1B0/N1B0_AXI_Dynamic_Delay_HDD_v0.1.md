# N1B0 AXI Dynamic Delay Buffer HDD v0.1

**Module:** `axi_dynamic_delay_buffer`
**RTL file:** `used_in_n1/rtl/axi_dynamic_delay_buffer.sv`
**Lines:** 160
**Synthesizable:** YES
**Purpose:** Injects a runtime-programmable cycle delay into a data stream (AXI channel) for testing or timing emulation.

---

## 1. Overview

`axi_dynamic_delay_buffer` is a synthesizable FIFO that introduces a programmable latency between its input and output. The delay is specified in clock cycles and can be changed at runtime, subject to the constraint that the pipeline must be empty when the delay changes.

It is used in N1B0 testbench/emulation infrastructure to inject artificial latency on AXI channels (e.g., DRAM read-data path) to simulate memory subsystem timing.

---

## 2. Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DATA_WIDTH` | 32 | Width of data payload in bits |
| `MAX_DELAY` | 256 | Maximum programmable delay in cycles |
| `HEADROOM` | 256 | Extra FIFO depth beyond MAX_DELAY to prevent overflow during draining |

FIFO depth = `MAX_DELAY + HEADROOM`. Total storage = `(MAX_DELAY + HEADROOM)` entries × `DATA_WIDTH + log2(MAX_DELAY)` bits (data + timestamp).

---

## 3. Ports

| Port | Dir | Width | Description |
|------|-----|-------|-------------|
| `i_clk` | input | 1 | Clock |
| `i_reset_n` | input | 1 | Active-low synchronous reset |
| `delay_cycles` | input | log2(MAX_DELAY) | Programmed delay in clock cycles (runtime-changeable when empty) |
| `i_data` | input | DATA_WIDTH | Input data |
| `i_valid` | input | 1 | Input valid (handshake) |
| `o_ready` | output | 1 | Input ready (backpressure) |
| `o_data` | output | DATA_WIDTH | Output data (delayed) |
| `o_valid` | output | 1 | Output valid |
| `i_ready` | input | 1 | Output ready (downstream backpressure) |

---

## 4. Functional Description

### 4.1 Timestamp FIFO

On each input handshake (`i_valid & o_ready`):
1. The data and current cycle counter (`$time` / cycle count) are pushed into the internal FIFO.
2. The FIFO holds `{timestamp, data}` pairs.

### 4.2 Output Gate

The output is released when:
```
current_cycle >= (entry_timestamp + delay_cycles)
```

Until this condition is met, `o_valid` remains 0 even if the FIFO is non-empty.

### 4.3 Zero-Delay Pass-Through

When `delay_cycles == 0`, the module becomes a pure pass-through:
- `o_data = i_data`
- `o_valid = i_valid`
- `o_ready = i_ready`

No FIFO latency is added. This allows bypassing the delay without changing structural connectivity.

### 4.4 Delay Change Constraint

`delay_cycles` may only be updated when the pipeline is empty (no entries in FIFO). The RTL enforces this with a concurrent assertion:

```systemverilog
assert_no_delay_change_when_busy:
  assert property (@(posedge i_clk) disable iff (!i_reset_n)
    (fifo_count != 0) |-> (delay_cycles == $past(delay_cycles)))
  else $error("delay_cycles changed while pipeline not empty");
```

If `delay_cycles` changes while entries are in flight, the assertion fires (simulation error). In hardware, the result is undefined — mismatched timestamps cause premature or delayed output release.

### 4.5 Backpressure

The module fully supports backpressure:
- `o_ready` goes low when FIFO is full (capacity = `MAX_DELAY + HEADROOM`)
- Input is stalled by deasserting `o_ready`
- Output is stalled by downstream deasserting `i_ready`

A FIFO full condition should not occur in normal operation if `MAX_DELAY + HEADROOM` > maximum burst + delay.

---

## 5. Timing Behavior

```
Cycle 0: i_valid=1, i_data=X, delay_cycles=5  → entry pushed {timestamp=0, data=X}
Cycle 1: i_valid=0                              → FIFO has 1 entry
...
Cycle 5: current >= timestamp+delay            → o_valid=1, o_data=X (released)
Cycle 6: downstream accepts (i_ready=1)        → entry popped, FIFO empty
```

Total latency from input handshake to output = `delay_cycles` cycles (plus 1 cycle pipeline for FIFO read).

---

## 6. SW / TB Programming Guide

### 6.1 Setting Delay

```systemverilog
// Set a 32-cycle delay
delay_buffer.delay_cycles = 32;

// Ensure pipeline is empty before changing:
wait(delay_buffer.fifo_count == 0);
delay_buffer.delay_cycles = 64;
```

### 6.2 Using as Pass-Through (debug / baseline)

```systemverilog
delay_buffer.delay_cycles = 0;  // no added latency
```

### 6.3 Connecting to AXI R Channel

```systemverilog
axi_dynamic_delay_buffer #(
  .DATA_WIDTH(512),   // AXI data width
  .MAX_DELAY(128),
  .HEADROOM(128)
) rdata_delay (
  .i_clk(axi_clk),
  .i_reset_n(axi_reset_n),
  .delay_cycles(tb_delay_cycles),
  .i_data({rdata, rid, rlast, rresp}),
  .i_valid(rvalid),
  .o_ready(rready),
  .o_data({rdata_dly, rid_dly, rlast_dly, rresp_dly}),
  .o_valid(rvalid_dly),
  .i_ready(rready_dly)
);
```

### 6.4 Changing Delay Mid-Simulation

```systemverilog
// Phase 1: 10-cycle delay
@(posedge clk);
delay_cycles = 10;
// ... run some transactions ...

// Phase 2: change to 50-cycle delay
// Must wait for pipeline to drain first
wait(fifo_count == 0);
@(posedge clk);
delay_cycles = 50;
```

---

## 7. Resource Usage (Estimates)

For `DATA_WIDTH=32`, `MAX_DELAY=256`, `HEADROOM=256`:
- FIFO depth: 512 entries
- Entry width: 32 + 8 (timestamp bits for 256 cycles) = 40 bits
- Total FIFO storage: 512 × 40 = 20,480 bits ≈ 20K bits (~2.5KB)
- Implemented as flip-flop FIFO or SRAM depending on synthesis tool

For `DATA_WIDTH=512` (AXI 512-bit):
- FIFO depth: 512 entries × 520 bits ≈ 265K bits (~33KB) — SRAM macro recommended

---

## 8. Assertion Summary

| Assertion name | Condition checked |
|----------------|-----------------|
| `assert_no_delay_change_when_busy` | `delay_cycles` stable when FIFO non-empty |

---

*RTL source: `used_in_n1/rtl/axi_dynamic_delay_buffer.sv` (160 lines)*
*Author: N1B0 HDD project, 2026-03-18*
