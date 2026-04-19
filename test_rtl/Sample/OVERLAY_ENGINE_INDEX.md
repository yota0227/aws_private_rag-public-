# Overlay Engine Extraction — Document Index

## Overview

This index provides quick navigation to the comprehensive overlay engine extraction materials created for N1B0_NPU_HDD_v0.99.md §3 chapter development.

---

## Primary Deliverables

### 1. Main Extraction Document
**File**: `/secure_data_from_tt/overlay_engine_extraction_findings.md` (26 KB, 709 lines)

Contains 15 detailed sections covering:
- Architecture overview
- Hardware components (stream controller, TDMA, MOP, context switch)
- Data paths and NoC integration
- Stream programming model
- Context switching architecture
- Performance characteristics
- Integration with other components
- Power management and DFX
- RTL file locations and parameters
- Alternative DRAM access paths
- Constraints and limitations
- Recommended §3 chapter outline
- Key facts summary
- References and cross-links
- Notes for HDD author

**Use this document for**: Comprehensive technical detail, RTL references, parameter tables, architectural rationale

---

### 2. Summary Report
**File**: `/secure_data_from_tt/EXTRACTION_SUMMARY.txt` (15 KB)

Contains:
- Executive overview of all findings
- Key findings organized by category
- Critical findings (MUST INCLUDE in §3)
- Recommended §3 chapter outline
- Cross-references to existing HDD sections
- Verification coverage
- Notes for HDD author
- Deliverable checklist

**Use this document for**: Quick reference, executive overview, critical constraints, chapter planning

---

## Document Structure Map

### Section-by-Section Navigation

| Section | Topic | Use For | Key Content |
|---------|-------|---------|-------------|
| 1 | Overview | Architecture concept | Role, purpose, tt_neo_overlay_wrapper module |
| 2 | Hardware Components | Design understanding | Stream controller, TDMA, MOP, stream status, context switch |
| 3 | Data Paths | Integration points | DRAM access path, ports, CDC FIFOs, L1 integration |
| 4 | Stream Programming | Firmware development | CSR interface, burst calculation, status polling, limits |
| 5 | Context Switching | Power/performance | SRAM, partition control, L1/L2 orchestration |
| 6 | Performance | Benchmarking | Data rates, latency, stream capacity |
| 7 | Integration | System design | TRISC, FPU, NoC, NIU, SMN, EDC connections |
| 8 | Power/DFX | Verification | Clock gating, reset, DFX wrappers |
| 9 | RTL Locations | Implementation | File paths, parameters, memory config |
| 10 | Alternative Paths | Algorithm design | iDMA vs overlay streams, Dispatch integration |
| 11 | Constraints | Design boundaries | DRAM, burst size, outstanding requests, addressing |
| 12 | Chapter Outline | Authoring | Proposed §3 structure (3.1–3.9 subsections) |
| 13 | Key Facts | Reference | Essential numbers, clock domains, RTL modules |
| 14 | References | Traceability | Links to existing HDD sections |
| 15 | Author Notes | Implementation | Diagram suggestions, RTL snippets, verification facts |

---

## Key Content By Use Case

### For HDD Chapter Creation

**Start with**: Section 12 (Recommended §3 Chapter Outline)

**Then consult**:
- Sections 1–11 for detailed technical content to populate each subsection
- Section 13 for key numbers/facts to include
- Section 15 for diagram and code snippet ideas

**Cross-reference**: Section 14 to avoid duplication with existing sections

---

### For Understanding Overlay Architecture

**Read in order**:
1. Section 1: Overview (big picture)
2. Section 2: Hardware Components (building blocks)
3. Section 3: Data Paths (how they connect)
4. Section 7: Integration (how overlay fits in)

**Time estimate**: 30–45 minutes for complete understanding

---

### For Firmware Development

**Priority sections**:
- Section 4: Stream Programming Model (CSR interface, polling pattern)
- Section 11: Constraints (outstanding limits, max burst size)
- Section 6: Performance (latency expectations)
- Section 13: Key Facts (essential numbers)

**Critical constraint**: Cannot load DRAM directly to LDM (must go through L1)

---

### For RTL Implementation

**Priority sections**:
- Section 9: RTL File Locations and Parameters
- Section 2: Hardware Components (what to implement)
- Section 3: Data Paths (interfaces between components)
- Section 8: Power Management (clock gating, reset)

**Key files to review**:
- `/secure_data_from_tt/20260221/tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv`
- `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv`

---

### For Performance Analysis

**Priority sections**:
- Section 6: Performance Characteristics
- Section 3: Data Paths (port specifications)
- Section 13: Key Facts (numbers)

**Key metrics**:
- Per-NIU bandwidth: 512 GB/s @ 1 GHz (409.6 GB/s @ 800 MHz)
- Total latency: 100–150+ cycles
- Stream capacity: 8 simultaneous streams
- Max AXI burst: 16 KB per command

---

### For Power Management

**Priority sections**:
- Section 5: Context Switching
- Section 8: Power Management and DFX
- Section 7: Integration (SMN security pre-filters)

**Key concepts**:
- Clock gating via overlay_wrapper_dfx
- L1 remains accessible for DMA when instruction engines gated
- Context switch SRAM saves/restores L1/L2 state

---

### For Constraint Analysis

**Must read**: Section 11 (Constraints and Limitations)

**Critical constraints**:
1. No direct TRISC-to-DRAM load (must go through L1)
2. Max AXI burst is 16 KB (split larger transfers)
3. Max outstanding reads is 4 (check status before issuing 5th)
4. Composite vs standalone NIU have different Y coordinates (X=1,2 are Y=3, not Y=4)

---

## Quick Reference Tables

### Essential Numbers
```
8 overlay streams per cluster
512-bit flit width (64 bytes per beat)
16 KB max AXI burst (256 beats × 64 bytes)
4 outstanding read requests max (8 in large mode)
3 MB L1 capacity per cluster
512 SRAM macros per L1 partition
32 KB RDATA FIFO in NIU (512 entries)
4 TRISC threads (TRISC0=pack, TRISC1=unpack, TRISC2=math, TRISC3=mgmt)
256 FP-Lanes per Tensix (2 G-Tiles × 128 each)
```

### Clock Domains
```
ai_clk   — TRISC, FPU, instruction engines
dm_clk   — Overlay data-move, L1/L2 SRAM, pack/unpack engines
noc_clk  — NoC router, flit FIFOs, overlay stream injection
```

### Core RTL Modules
```
tt_neo_overlay_wrapper        — Container for all overlay logic
tt_instrn_engine              — MOP sequencer, TDMA coordination
tt_trisc                      — TRISC0/1/2 cores
tt_risc_wrapper               — TRISC3 RV32I core
tt_noc2axi                    — NIU (in composite tile)
tt_t6_l1_partition            — L1 cache hierarchy
```

### NIU Addressing (CRITICAL)
```
X=0 (standalone):  NOC_XY_ADDR(0, 4, ...)  ← Y=4
X=1 (composite):   NOC_XY_ADDR(1, 3, ...)  ← Y=3 (router row)
X=2 (composite):   NOC_XY_ADDR(2, 3, ...)  ← Y=3 (router row)
X=3 (standalone):  NOC_XY_ADDR(3, 4, ...)  ← Y=4

Note: Using Y=4 for composite (X=1,2) causes packet drop/misroute
```

---

## Integration Points Checklist

Use this to verify complete coverage in §3 chapter:

- [ ] TRISC interface (CSR writes, status polling)
- [ ] FPU integration (MOP sequencer, SRCA/SRCB feeding)
- [ ] NoC integration (flit injection, routing)
- [ ] NIU interface (ATT lookup, AXI burst parameters)
- [ ] SMN security (pre-ATT range filtering)
- [ ] EDC ring (OVL node per cluster, error escalation)
- [ ] L1 partition (128-bit TRISC port, 512-bit side-channel)
- [ ] Context switch (SRAM state save/restore)
- [ ] Power management (clock gating, reset hierarchy)
- [ ] DFX integration (overlay_wrapper_dfx, instrn_engine_wrapper_dfx)

---

## Cross-References to Existing HDD Sections

When writing §3, reference these existing sections to avoid duplication:

| Topic | Existing Section | How to Cross-Ref |
|-------|------------------|------------------|
| TRISC memory interfaces | §2.2.4 | ICache, LDM, L1, NoC overlay streams |
| TRISC thread roles | §2.3.2 | pack/unpack/math/mgmt role assignment |
| Complete access matrix | §2.3.6 | All 7 data paths through tile |
| DRAM access path detail | §2.3.6.4 | Overlay stream CSR programming |
| Access diagram | §2.3.6.5 | Paths ①–⑦ with bandwidth/latency |
| ATT address translation | §3.2.3 | 64-entry lookup table |
| NIU DMA operation | §3.7 | AXI burst parameters, RDATA FIFO |
| End-to-end DRAM path | §3.7.6 | Complete latency/bandwidth model |
| iDMA engine | §4.X | Alternative DRAM access for weights |
| Harvest integration | §5 | Power domain gating through overlay |
| DFX wrappers | §8.7.4–8.7.6 | Clock gating, reset, test integration |

---

## Common Questions Answered

**Q: What's the difference between overlay streams and iDMA?**
A: See Section 10. Overlay streams = TRISC-initiated residual DMA during kernel. iDMA = Dispatch-controlled bulk weight loading before kernel.

**Q: Why can't TRISC load DRAM directly to LDM?**
A: See Section 11. No direct DRAM port in any TRISC. Data must arrive in L1 first via overlay DMA, then TRISC reads from L1.

**Q: What's the max burst size?**
A: See Section 4. Max AXI burst = 256 beats × 64 bytes = 16 KB. Split larger transfers across multiple overlay stream commands.

**Q: Why is composite tile Y=3 instead of Y=4?**
A: See Section 3.4 and Section 11. Composite module reports nodeid_y = Y−1 (router row). Must use correct Y in NOC_XY_ADDR or packet drops.

**Q: How many overlay streams can run simultaneously?**
A: See Section 13. 8 streams per cluster, but they execute sequentially at the DRAM level due to single NIU port. Practical concurrency = 1–2 without stalls.

**Q: What happens if firmware issues >4 outstanding reads?**
A: See Section 11. NIU RDATA FIFO (512 entries = 32 KB) may overflow. Firmware must check status before issuing 5th concurrent read.

---

## Document Maintenance

**Last updated**: 2026-04-01
**Source HDD**: N1B0_NPU_HDD_v0.99.md
**RTL snapshot**: /secure_data_from_tt/20260221/tt_rtl/
**Status**: COMPLETE — Ready for §3 chapter authoring

**To update this extraction**:
1. Re-read N1B0_NPU_HDD_v0.99.md sections 2.2.4, 2.3.6, 3.7.6, 8.7.4–8.7.5
2. Search RTL files for new parameters or RTL hierarchy changes
3. Update corresponding sections in overlay_engine_extraction_findings.md
4. Regenerate this index

---

## File Locations

```
Primary extraction document:
  /secure_data_from_tt/overlay_engine_extraction_findings.md

Summary report:
  /secure_data_from_tt/EXTRACTION_SUMMARY.txt

This index:
  /secure_data_from_tt/OVERLAY_ENGINE_INDEX.md

HDD being enhanced:
  /secure_data_from_tt/20260221/DOC/N1B0/N1B0_NPU_HDD_v0.99.md

RTL source files:
  /secure_data_from_tt/20260221/tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv
  /secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_instrn_engine.sv
```

---

## Getting Started

1. **For overview**: Read EXTRACTION_SUMMARY.txt (15 min)
2. **For technical depth**: Read overlay_engine_extraction_findings.md (45 min)
3. **For chapter authoring**: Follow Section 12 outline with Sections 1–11 as reference
4. **For verification**: Check Section 15 for diagram/snippet suggestions

---

END OF INDEX
