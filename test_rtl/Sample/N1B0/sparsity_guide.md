# N1B0 Sparsity Function and Programming Guide

**Document Version:** 2.0  
**Date:** 2026-04-03  
**Target Audience:** Firmware developers, model optimization engineers  
**Related HDD Section:** §2.7.9 (Sparsity and Zero Skipping in Unpack Engine)

---

## Part 1: Overview — Understanding N1B0 Sparsity

### What is Sparsity in N1B0?

Sparsity is a hardware feature that allows you to **skip loading zero-valued z-planes** from L1 during tensor unpacking. You provide a 32-bit **z-plane mask** that tells the hardware which depth slices to skip.

**Key Mechanism:**
- One z-plane = one 128-bit L1 read = one unpack cycle
- One 32-bit mask controls 32 z-planes maximum
- Skipped z-planes don't consume L1 bandwidth
- Unpack latency **remains unchanged** (loop still iterates K times)

### Benefits

✅ **What Sparsity Saves:**
- **L1 read traffic:** Proportional to sparsity (50% sparse → 50% fewer reads)
- **Compute energy:** Fewer FPU MACs, less L1 activity
- **Local tile power:** Reduced in the unpack/compute subsystem

✅ **How It Works:**
- No branching (hardware FSM automatic)
- No latency penalty (SKIP takes same time as UNPACK)
- Seamless integration with existing TDMA/double-buffering

### Limitations — What Sparsity DOES NOT Do

❌ **Latency:** Unpack loop **still iterates K times** (e.g., 96 cycles for K=96), regardless of sparsity
```
With 50% sparsity, K=96:
  Cycles 1,3,5,... → UNPACK_A0 (load)
  Cycles 2,4,6,... → SKIP_A (no load)
  Total = 96 cycles (unchanged)
```

❌ **Throughput:** One tensor still takes ~96 cycles (latency unchanged, so no throughput gain)

❌ **DRAM bandwidth:** Zero savings (sparse data already loaded into L1 during load phase)

❌ **System-level power:** Savings only in compute subsystem; other NPU components unaffected

### When to Use Sparsity

✅ **Good candidates:**
- Pruned networks (30–75% weights zero)
- Transformer attention masks (causal, 50%+ masked)
- Sparse activations (after ReLU, 30–70% zeros)
- Block-sparse matrices (structured patterns)

✅ **Optimization goal:**
- Power-constrained systems (battery, thermal budgets)
- Energy-per-inference matters more than latency

❌ **Poor candidates:**
- Dense models (no sparsity)
- Real-time latency-critical inference (latency unchanged)
- Fine-grained random sparsity (hard to encode)

### N1B0 vs NVIDIA Sparsity — Quick Comparison

| Feature | N1B0 Z-Plane | NVIDIA 2:4 |
|---------|-------------|-----------|
| **Granularity** | Entire depth slices (z-planes) | 4 consecutive elements |
| **Max sparsity** | Any ratio (50%, 75%, 90%+) | Up to 50% only |
| **Where applied** | L1 unpack (tile-local) | DRAM load (system-wide) |
| **L1 bandwidth saved** | Yes, proportional | N/A (no L1 optimization) |
| **DRAM bandwidth saved** | No | Yes, significant |
| **Latency impact** | None (loop unchanged) | Reduced (faster load) |
| **Best for** | Structured/block sparse | Fine-grained uniform sparse |

**Pros & Cons:**

**N1B0 Sparsity Pros:**
- ✅ Works with any sparsity ratio (no 50% limit)
- ✅ Reduces L1 bandwidth and compute energy locally
- ✅ Simple to implement (32-bit mask)
- ✅ Works seamlessly with existing hardware

**N1B0 Sparsity Cons:**
- ❌ No latency improvement (loop still runs K cycles)
- ❌ No DRAM bandwidth savings (data pre-loaded)
- ❌ Only helps if compute is bottleneck
- ❌ Requires structured patterns

**NVIDIA 2:4 Sparsity Pros:**
- ✅ Reduces both DRAM and L1 bandwidth
- ✅ Improves latency (fewer bytes to load)
- ✅ System-level optimization (benefits entire chip)

**NVIDIA 2:4 Sparsity Cons:**
- ❌ Limited to 50% max sparsity
- ❌ Requires fine-grained 2-of-4 pattern
- ❌ Not suitable for highly pruned networks (>50%)

**When to choose:**
- **Use N1B0 sparsity:** Energy-constrained, structured sparsity patterns, power-per-inference matters
- **Use NVIDIA 2:4:** Latency-critical, system-wide optimization needed, fine-grained sparsity

---

## Part 2: Hardware Architecture

### The 32-Bit Z-Plane Mask

**What is a z-plane?**

A z-plane is one slice along the K (depth) dimension. For a 4×16×96 tensor, each z-plane is a 4×16 slice, and there are 96 z-planes.

**Mask encoding:**
```
zmask[31:0] — one bit per z-plane

zmask[i] = 0 → LOAD z-plane i from L1 (UNPACK instruction, SRCA++)
zmask[i] = 1 → SKIP z-plane i (SKIP instruction, no load, SRCA unchanged)
```

**Z-Plane Size by Data Type:**

| Data Type | Elements per Z-Plane | Z-Planes for K=96 |
|-----------|----------------------|-------------------|
| INT8 | 16 elements | 6 z-planes |
| INT16 / FP16B | 8 elements | 12 z-planes |
| FP32 | 4 elements | 24 z-planes |

All formats use the same hardware; z-planes are physical units (128-bit L1 reads).

### Unpack Loop FSM (State Machine)

The hardware has a 7-state FSM that automatically selects UNPACK vs SKIP:

```
States: IDLE → UNPACK_A0/A1/A2/A3 → UNPACK_B → SKIP_A → SKIP_B

Per cycle:
  if zmask[current_bit] == 0:  emit UNPACK_A0  (load from L1)
  if zmask[current_bit] == 1:  emit SKIP_A     (don't load)
  
  current_zmask >>= 1  (shift mask right each cycle)
```

**Both UNPACK and SKIP take exactly 1 cycle — sparsity adds zero latency overhead.**

### Mask Format (32-bit MOP Word)

```
MOP instruction word [31:0]:
  [31]      mop_type    0 = unpack_loop
  [30]      done        1 = last MOP in sequence
  [29:23]   loop_count  number of z-planes - 1
  [22:8]    zmask_lo    inner loop count + zmask[14:9]
  [7:0]     opcode      0x01 (OPCODE_MOP)

Optional MOP_CFG word [31:0]:
  [31:8]    zmask_hi24  upper 24 bits of z-plane mask
  [7:0]     opcode      0x03 (OPCODE_MOP_CFG)
```

### Multi-MOP for K_tile > 32

The 32-bit mask covers up to 32 z-planes per MOP. For K_tile > 32, issue multiple MOPs with different masks:

**Practical cases for N1B0:**
- K=96 INT8: 6 z-planes → **1 MOP** (6 < 32)
- K=96 INT16: 12 z-planes → **1 MOP** (12 < 32)
- K=96 FP32: 24 z-planes → **1 MOP** (24 < 32)

**SRCA address continuity:** Hardware automatically maintains SRCA address across multiple MOPs (no firmware reset needed).

---

## Part 3: Software Programming Guide

### 3-Step Implementation

**Step 1: Generate mask** — Determine which z-planes have zeros
```c
uint32_t zmask = 0;
for (int i = 0; i < num_zplanes && i < 32; i++) {
    if (is_sparse[i])  zmask |= (1 << i);  // bit=1 to skip
}
```

**Step 2: Write MOP** — Load mask into unpack sequencer
```c
uint32_t mop = (0 << 31) | (1 << 30) | ((k_tile - 1) << 23) | ((zmask & 0xFF) << 8) | 0x01;
write_mop(mop);

if (k_tile > 32) {
    uint32_t mop_cfg = ((zmask >> 8) << 8) | 0x03;  // Upper 24 bits
    write_mop(mop_cfg);
}
```

**Step 3: Hardware executes** — FSM alternates UNPACK/SKIP based on mask
- Unpack: load z-plane from L1, SRCA++
- Skip: don't load, SRCA unchanged
- Total time: K_tile cycles (unchanged)

### Example: Pruned Network

```c
// 50% structured sparsity (alternating zero z-planes)
uint32_t zmask = 0xAAAAAAAA;  // Binary: 1010...1010

uint32_t mop = (0 << 31) | (1 << 30) | (95 << 23) | (0xAA << 8) | 0x01;
write_mop(mop);

// Hardware: cycles alternate UNPACK_A0 (load) / SKIP_A (no load)
// Result: 50% fewer L1 reads, 50% fewer MACs
```

---

## Quick Reference

**Zmask patterns:**
- 50% alternating: `0xAAAAAAAA` (binary: 1010...1010)
- 75% (skip 3 of 4): `0xEEEEEEEE` (binary: 1110...1110)
- Causal attention: `pattern = [0]*(token+1) + [1]*(max_len-token-1)`

**Common zmask values:**
```
0x00000000 = load all (dense)
0xAAAAAAAA = skip every other (50%)
0xFFFFFFFF = skip all (invalid, don't use)
```

---

**End of Sparsity Guide**

For detailed RTL architecture, see §2.7.9 in N1B0_NPU_HDD_v1.00.md
