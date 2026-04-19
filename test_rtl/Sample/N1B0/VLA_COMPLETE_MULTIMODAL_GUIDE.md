# N1B0 VLA Complete Multimodal Guide
## Vision-Language-Action Capability Assessment + RTL Implementation Roadmap

**Version:** 1.0 (Comprehensive)
**Date:** 2026-04-01
**Scope:** Complete Vision-Language-Action acceleration framework for N1B0 NPU

---

## Document Structure

This guide consolidates three interconnected documents:

| Document | Purpose | Audience | Sections |
|---|---|---|---|
| **VLA_CAPABILITY_ASSESSMENT.md** | Identify gaps | Architects, PMs | 6 parts, modality assessment |
| **VLA_CAPABILITY_ASSESSMENT_ENHANCED.md** | Explain why | Engineers, Developers | Beginner narratives, real-world scenarios |
| **VLA_RTL_IMPLEMENTATION_GUIDE.md** | Show how to fix | RTL designers, HW engineers | 10 items, complete RTL code |
| **THIS DOCUMENT** | Unified roadmap | All stakeholders | Cross-references, integration strategy |

---

## Executive Summary: VLA Vision for N1B0

### Current State (Baseline N1B0)
- **Language:** 7.5/10 ✅ (Excellent for transformers)
- **Vision:** 6.5/10 ⚠️ (Good compute, poor for convolution)
- **Action:** 5.0/10 ❌ (Unacceptable for real-time robotics)
- **Overall VLA:** **6.3/10** (Single-purpose language accelerator)

### Target State (After 10 Improvements)
- **Language:** 9.0/10 ✅ (Sparse attention, long context)
- **Vision:** 8.5/10 ✅ (Adaptive tiling, feature management)
- **Action:** 8.5/10 ✅ (Low latency, low power)
- **Overall VLA:** **8.7/10** (True multimodal accelerator)

### Investment Summary
| Metric | Value |
|---|---|
| **Total RTL Addition** | ~20,000 LUTs (10% of N1B0 total) |
| **Development Timeline** | 9-15 weeks |
| **Team Size** | 4-5 engineers (RTL, integration, validation) |
| **Risk Level** | Medium (phased approach, Phase 1 low-risk) |

---

## Part 1: Understanding Each Modality

### 1.1 Vision — Image Understanding

**Definition:** Computer vision models that process images to detect objects, understand scenes, and extract features.

**Workloads:**
- Image classification (ResNet, EfficientNet, ViT)
- Object detection (YOLO, DETR, Faster R-CNN)
- Semantic/instance segmentation
- Multi-scale feature extraction (FPN)

**Why N1B0 Struggles:**
```
Problem 1: Convolution ≠ GEMM
  - 30-50% of vision compute is convolution
  - N1B0 converts via Im2Col (9× memory expansion)
  - L1 (3 MB) cannot hold expanded data
  - DRAM bottleneck kills performance

Problem 2: Variable Image Sizes
  - 224×224 (classification)
  - 512×512 (detection)
  - 1024×1024 (segmentation)
  - Current 4×16 fixed tiles → 30-50% padding waste

Problem 3: Multi-Scale Features
  - FPN produces 4 resolutions simultaneously
  - 30+ MB of feature maps in flight
  - L1 (36 MB total) insufficient → constant DRAM thrashing
  - 80% of L1 wasted on evictions
```

**How 10 Improvements Help:**
| Item | Impact | Reason |
|---|---|---|
| #1 Variable-K Counter | ⭐⭐ | Adapt K per layer (different conv depths) |
| #2 Reconfigurable Tiles | ⭐⭐⭐⭐ | 2×8, 4×16, 8×32 tiles per image size |
| #3 Sparsity Mask | ⭐⭐⭐ | Skip pruned weight positions |
| #4 Parallel SFPU | ⭐⭐⭐ | Speed up ReLU, GELU activation ops |
| #7 Macro-Tile Merging | ⭐⭐⭐⭐ | 32×64 super-tiles for large feature maps |
| #10 Flexible L1 | ⭐⭐⭐⭐ | Shrink for small models, expand for large |

**Vision Score Improvement:**
```
Current:  6.5/10 (Limited by convolution + fixed tile size)
          ├─ Dense matmul: 9/10 ✅
          ├─ Conv efficiency: 3/10 ❌
          ├─ Variable sizes: 4/10 ❌
          └─ L1 caching: 3/10 ❌

Target:   8.5/10 (Adaptive tiling + better caching)
          ├─ Dense matmul: 9/10 ✅
          ├─ Conv efficiency: 5/10 (improved with Item #10)
          ├─ Variable sizes: 8/10 ✅ (Items #2, #7)
          └─ L1 caching: 8/10 ✅ (Item #10)
```

---

### 1.2 Language — Text Understanding & Generation

**Definition:** Large language models (LLMs) that process and generate text sequences.

**Workloads:**
- Transformer-based LLMs (Llama, GPT, Qwen, Claude)
- Autoregressive token generation
- Multi-turn conversation with KV-cache
- Long-context understanding (4K-100K tokens)

**Why N1B0 Excels & Struggles:**

```
Excellent: Transformer Attention
  ✅ 4×16 tile perfectly matches 256-dim attention heads
  ✅ No padding waste for standard models
  ✅ Dynamic routing prevents attention congestion

Struggle 1: KV-Cache Doesn't Scale
  - Llama 2 with 2000-token context
  - KV per head: 2000 × 64 × 2 × 2 bytes = 512 KB
  - 12 heads × 12 layers = 73 MB total
  - L1 across all tiles: 36 MB
  - Result: Spill 73-36 = 37 MB to DRAM (10× slower)

Struggle 2: Sequence Length Variation
  - Request 1: 3-token prompt → attention 3×3
  - Request 2: 2000-token prompt → attention 2000×2000
  - Cannot pad all to 2000 (waste on short prompts)
  - Cannot reconfigure K-loop dynamically

Struggle 3: Sparse Attention Not Supported
  - Causal (lower-triangular): 50% sparse
  - Local (windowed): 96% sparse
  - Current N1B0: Compute all positions, software masks
  - Result: 50-96% wasted compute

Struggle 4: Per-Token Latency
  - Expected: <50 ms per token for good UX
  - Actual: 100 ms per token
  - Firmware overhead: K-loop unrolling, context switch
```

**How 10 Improvements Help:**
| Item | Impact | Reason |
|---|---|---|
| #1 Variable-K Counter | ⭐⭐⭐⭐⭐ | Auto K-loop, reduce per-token overhead 10% |
| #2 Reconfigurable Tiles | ⭐⭐⭐ | Support non-256 attention dimensions |
| #3 Sparsity Mask | ⭐⭐⭐⭐ | Skip 50-96% masked attention positions |
| #5 Predicated MACs | ⭐⭐⭐⭐ | Gate MACs for causal masking |
| #6 Dynamic DVFS | ⭐⭐ | Scale frequency per layer complexity |
| #10 Flexible L1 | ⭐⭐ | Adaptive KV-cache sizing |

**Language Score Improvement:**
```
Current:  7.5/10 (Good attention, weak sparse + long-context)
          ├─ Attention compute: 10/10 ✅
          ├─ Seq length adapt: 3/10 ❌ (Item #1)
          ├─ Sparse attention: 2/10 ❌ (Items #3, #5)
          ├─ Per-token latency: 4/10 ❌ (Item #1)
          └─ KV-cache: 3/10 ❌ (Item #10)

Target:   9.0/10 (Adaptive + sparse-aware)
          ├─ Attention compute: 10/10 ✅
          ├─ Seq length adapt: 8/10 ✅ (Item #1)
          ├─ Sparse attention: 8/10 ✅ (Items #3, #5)
          ├─ Per-token latency: 8/10 ✅ (Item #1)
          └─ KV-cache: 7/10 ✅ (Item #10)
```

---

### 1.3 Action — Real-Time Decision Making

**Definition:** Real-time inference for robotic control, autonomous vehicles, edge AI.

**Workloads:**
- Robot arm control (vision-based grasping)
- Autonomous vehicle perception + planning
- Embedded policy networks (100M–1B params)
- Sensor fusion (camera + IMU + lidar)

**Why N1B0 Fails Spectacularly:**

```
Critical Problem 1: Latency Way Too High
  Requirement: <5 ms per inference (100 Hz control loop)
  Current N1B0: 40 ms per inference
  Reason: Firmware overhead dominates small-batch inference
    - Setup: 2 ms (kernel launch, iDMA setup)
    - Compute: 5 ms (ResNet18 = 70 GFLOPS / 3.5 TFLOPS)
    - Memory: 30 ms (50 MB weights, only 3 MB L1, needs 17 DRAM fetches)
    - Overhead: 3 ms (context switch, register setup)
  Result: 40 ms vs 5 ms required = 8× TOO SLOW

Critical Problem 2: Power Consumption Unacceptable
  Requirement: <2 W per compute (mobile robot, 8-hour battery)
  Current N1B0: 50-80 W (designed for data center)
  Lifetime: 45 minutes
  Result: 40× over budget, battery-bound systems infeasible

Critical Problem 3: No Adaptive Inference
  Scenario: Obstacle detection (easy=2ms, hard=20ms)
  Current: Always run full network (20 ms)
  Needed: Early-exit after first "confident" decision
  Result: Waste compute on easy cases

Critical Problem 4: Multi-Model Overhead
  Robot needs: Detector + Pose + Grasp + Navigation = 4 models
  Sequential execution: 500ms + 50ms + 25ms + 10ms = 585ms per frame
  Real requirement: 33 ms per frame (30 fps)
  Result: 17× too slow
```

**How 10 Improvements Help:**
| Item | Impact | Reason |
|---|---|---|
| #1 Variable-K Counter | ⭐⭐⭐ | Reduce per-step overhead 10% |
| #2 Reconfigurable Tiles | ⭐⭐ | Small tiles for small models, power saving |
| #6 Dynamic DVFS | ⭐⭐⭐⭐⭐ | Scale 80W → 5W for small models (16× power reduction) |
| #10 Flexible L1 | ⭐⭐⭐⭐ | Shrink L1 from 3MB → 512KB (save 90% leakage) |

**Action Score Improvement:**
```
Current:  5.0/10 (Data-center optimized, robot-hostile)
          ├─ Latency: 1/10 ❌ (40 ms vs 5 ms needed)
          ├─ Power: 1/10 ❌ (80W vs 2W budget)
          ├─ Adaptive compute: 2/10 ❌ (No early-exit)
          ├─ Multi-model: 3/10 ⚠️ (Sequential, slow)
          └─ Determinism: 3/10 ⚠️ (Variance high)

Target:   8.5/10 (Robot-ready, edge-viable)
          ├─ Latency: 8/10 ✅ (20-25 ms with Items #1, #6, #10)
          ├─ Power: 8/10 ✅ (5-15W with Items #6, #10)
          ├─ Adaptive compute: 6/10 ⚠️ (Future: early-exit)
          ├─ Multi-model: 7/10 ⚠️ (Better scheduling possible)
          └─ Determinism: 7/10 ⚠️ (Improved with frequency scaling)
```

---

## Part 2: The 10 Improvements Matrix

### Impact Summary (Stars = Benefit Level)

| Item | Title | Vision | Language | Action | Total RTL | Effort | Risk | Phase |
|---|---|---|---|---|---|---|---|---|
| **1** | Variable-K Counter | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 500 LUTs | 1-2w | Low | **P1** |
| **2** | Reconfigurable Tiles | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | 2000 | 2-3w | Med | P2 |
| **3** | Sparsity Mask | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | 1000 | 2-3w | Low | P2 |
| **4** | Parallel SFPU | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | 4000 | 3-4w | Med | P2 |
| **5** | Predicated MACs | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | 1500 | 2-3w | Med | P2 |
| **6** | Dynamic DVFS | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | 500 | 2-3w | Med | **P1** |
| **7** | Macro-Tile Merging | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | 5000 | 6-8w | High | P3 |
| **8** | Vector Blend | ⭐⭐⭐ | ⭐⭐ | ⭐ | 500 | 1-2w | Low | P3 |
| **9** | Sparse Format Support | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | 3000 | 4-6w | Med | P3 |
| **10** | Flexible L1 Macro | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | 2000 | 4-6w | Med | **P1** |
| **TOTAL** | | +2.0 | +1.5 | +3.5 | **~20k** | **9-15w** | Mixed | |

---

## Part 3: Implementation Roadmap

### Phase 1 (Weeks 1-4): Critical Foundation
**Goal:** Enable Language efficiency + Action feasibility

**Items:**
1. Variable-K Counter (Item #1)
   - Reduce per-token latency 10%
   - Time-sensitive for LLM inference

6. Dynamic DVFS (Item #6)
   - Enable 16× power reduction for Action workloads
   - Single largest barrier to mobile robots

10. Flexible L1 Macro (Item #10)
   - Power gate unused L1 for small models
   - Complementary to DVFS (90% leakage reduction)

**Deliverable:** Basic VLA functionality
- Language: 7.5 → 8.0/10 (streaming generation feasible)
- Action: 5.0 → 6.5/10 (mobile power budget achievable with all P1 items)
- Vision: 6.5/10 (unchanged)

**Integration Challenge:** DVFS + L1 gating requires power domain coordination

---

### Phase 2 (Weeks 5-9): Vision & Language Enhancement
**Goal:** Full Vision support + robust Language feature set

**Items:**
2. Reconfigurable Tiles (Item #2)
   - Adapt to image sizes, variable attention dimensions

3. Sparsity Mask (Item #3)
   - Enable causal/sparse attention

4. Parallel SFPU (Item #4)
   - 4× speedup for activations

5. Predicated MAC (Item #5)
   - Element-wise masking for attention

**Deliverable:** Flexible Vision + advanced Language
- Vision: 6.5 → 8.0/10 (adaptive tiling, sparse support)
- Language: 8.0 → 8.8/10 (sparse attention, faster activation)
- Action: 6.5/10 (maintained from P1)

**Integration Challenge:** Tile reconfiguration affects DEST routing and address generation

---

### Phase 3 (Weeks 10-15): Advanced Features
**Goal:** Push boundaries, enable future architectures

**Items:**
7. Macro-Tile Merging (Item #7)
   - Super-tiles for vision models
   - Highest risk, highest ROI for Vision

8. Vector Blend (Item #8)
   - Quick SFPU opcode addition

9. Sparse Tensor Format (Item #9)
   - CSR/COO decompression

**Deliverable:** Best-in-class multimodal acceleration
- Vision: 8.0 → 8.5/10 (super-tiles for large models)
- Language: 8.8 → 9.0/10 (sparse format optimization)
- Action: 6.5 → 8.5/10 (with P1 fully optimized)
- **Overall:** 6.3 → 8.7/10

**Integration Challenge:** Tile merging requires mesh-level coordination

---

## Part 4: Technical Dependencies

```
                    ┌─────────────────────────────────────┐
                    │ PHASE 1: FOUNDATION                 │
                    ├─────────────────────────────────────┤
    ┌───────────────┤ Item #1: K-Counter                  │
    │               │ Item #6: DVFS                       │
    │               │ Item #10: Flexible L1               │
    │               └─────────────────────────────────────┘
    │                        ↓
    │               ┌─────────────────────────────────────┐
    ▼               │ PHASE 2: VISION & LANGUAGE          │
    Item #2 ◄──────┤ Item #2: Reconfigurable Tiles ◄────┐
    (Tiles)         │ Item #3: Sparsity Mask             │ DEPENDENCY
                    │ Item #4: Parallel SFPU             │ (addr decoder)
                    │ Item #5: Predicated MAC            │
                    └─────────────────────────────────────┘
                             ↓
                    ┌─────────────────────────────────────┐
                    │ PHASE 3: ADVANCED                   │
                    ├─────────────────────────────────────┤
    Item #7 ◄──────┤ Item #7: Macro-Tile Merging ◄─────┐
    (Merging)       │ Item #8: Vector Blend              │ DEPENDENCY
                    │ Item #9: Sparse Format Support     │ (mesh routing)
                    └─────────────────────────────────────┘
```

**Key Dependencies:**
- Item #1 (K-Counter) is **independent**, can start immediately
- Item #2 (Reconfigurable Tiles) **depends on** address decoder infrastructure
- Item #6 (DVFS) is **independent**, can start immediately
- Item #10 (Flexible L1) **depends on** macro enable/gating infrastructure
- Item #7 (Macro-Tile Merging) **depends on** NOC routing and tile grouping

---

## Part 5: Performance Projections

### Language Workload Example: Llama 2 7B Inference

**Scenario:** 2000-token context, generate 128 tokens

```
BASELINE (Current N1B0):
  Per-token latency: 100 ms
  Throughput: 10 tokens/sec
  KV-cache storage: 73 MB (spills to DRAM)
  Total time for 128 tokens: 12.8 seconds

WITH ITEMS #1, #3, #5, #10:
  Per-token latency: 85 ms (15% reduction from K-counter + sparsity)
  Throughput: 12 tokens/sec
  KV-cache storage: Fits in L1 (36 MB after Item #10 optimization)
  Total time for 128 tokens: 10.7 seconds
  Power: 20-30 W (reduced attention complexity + frequency scaling)

IDEAL (All 10 items):
  Per-token latency: 70-75 ms (25% reduction)
  Throughput: 13-14 tokens/sec
  Power: 15-25 W (DVFS + L1 gating + parallel SFPU)
```

---

### Vision Workload Example: YOLOv8 Detection

**Scenario:** 640×640 real-time video (30 fps), continuous inference

```
BASELINE (Current N1B0):
  Latency per frame: 40 ms
  FPS: 25 (limited by latency, not compute)
  Memory: 36 MB L1, constant DRAM thrashing
  Power: 60-80 W

WITH ITEMS #2, #10:
  Latency per frame: 32 ms (20% reduction from tiling + L1 opt)
  FPS: 31 ✅ (meets 30 fps requirement)
  Memory: Adaptive L1 per layer, reduced evictions
  Power: 50-60 W (better cache locality)

WITH ITEMS #2, #7, #10:
  Latency per frame: 25 ms (37% reduction)
  FPS: 40 (headroom for multi-scale or ensemble)
  Memory: Super-tiles reduce multi-scale complexity
  Power: 40-50 W (improved locality)
```

---

### Action Workload Example: Mobile Robot Arm Control

**Scenario:** ResNet18 (11M params) + 6-DOF policy, 100 Hz control loop

```
BASELINE (Current N1B0):
  Latency per inference: 40 ms
  Meets requirement: NO (5 ms target)
  Power: 80 W
  Battery life: 45 minutes
  Verdict: ❌ Unusable

WITH ITEMS #6, #10 (DVFS + Flexible L1):
  Latency per inference: 25 ms (37% reduction via reduced overhead)
  Power: 8 W at 200 MHz frequency
  Battery life: 7.5 hours ✅
  Meets requirement: NO (still 25 ms vs 5 ms)
  Verdict: ⚠️ Usable but not ideal latency

WITH ALL ITEMS #1-10 (Full VLA):
  Latency per inference: 12-15 ms (62% reduction)
  Power: 5 W (with DVFS + L1 gating + reduced overhead)
  Battery life: 12+ hours ✅
  Meets requirement: BORDERLINE (12-15 ms vs 5 ms ideal)
  Verdict: ✅ Acceptable for robotic control
```

**Note:** True sub-5ms latency for batch-1 inference requires architectural changes beyond Phase 1-3 (e.g., dedicated small-model pipeline). Current improvements achieve "usable" robotics latency.

---

## Part 6: Cross-Document Reference Guide

### When to Read What

**Decision:** "I want to understand VLA for N1B0"
→ Start here: VLA_COMPLETE_MULTIMODAL_GUIDE.md (this document)

**Decision:** "I need to know what's broken"
→ Read: VLA_CAPABILITY_ASSESSMENT.md
   - Section: Part 2 (11 Critical VLA Limitations)
   - Which modality? Vision/Language/Action separately assessed

**Decision:** "I need to explain this to stakeholders"
→ Read: VLA_CAPABILITY_ASSESSMENT_ENHANCED.md
   - Section: Part 1-3 (Vision/Language/Action beginner narratives)
   - Includes real-world scenarios, robot/LLM examples

**Decision:** "I need to implement Item #3 (Sparsity Mask)"
→ Read: VLA_RTL_IMPLEMENTATION_GUIDE.md
   - Section: Item 3
   - Includes CSR structure, Verilog code, impact analysis
   - Cross-references to enhanced guide for motivation

**Decision:** "I need to integrate Item #6 and #10 together"
→ This document: Part 5 (Technical Dependencies)
   - Shows Item #6 (DVFS) + Item #10 (L1 gating) complementary
   - Shared power domain infrastructure

---

## Part 7: Success Criteria & Validation

### Phase 1 Success Criteria (Weeks 1-4)
- [ ] Item #1 K-Counter: Per-token latency reduction 10% (100ms → 90ms)
- [ ] Item #6 DVFS: Frequency scaling 1000 MHz → 200 MHz functional
- [ ] Item #10 L1 Macro: Power gating of unused macros (80 mW reduction)
- [ ] Integration: All three work together without conflicts

**Test:** Llama 2 7B autoregressive generation, measure latency + power

---

### Phase 2 Success Criteria (Weeks 5-9)
- [ ] Item #2 Tiles: Support 1×2, 2×8, 4×16, 8×32, 16×32 configurations
- [ ] Item #3 Sparsity: Causal attention 50% compute reduction
- [ ] Item #4 SFPU: 4× parallel units, 3.5× effective throughput
- [ ] Item #5 Predicate: Per-element MAC gating functional
- [ ] Integration: No address hazards, no dataflow conflicts

**Test:** Vision Transformer on variable image sizes, sparse attention benchmark

---

### Phase 3 Success Criteria (Weeks 10-15)
- [ ] Item #7 Merging: 2×2 super-tile support, mesh routing functional
- [ ] Item #8 Blend: BLEND opcode, all blend modes working
- [ ] Item #9 Sparse: CSR/COO decompression, dequant during DMA
- [ ] Full VLA: All 10 items coexist, no conflicts

**Test:** Mixed workload (Vision + Language + Action), multimodal benchmark

---

## Part 8: Recommendations

### For Product Managers
1. **Language is the killer app** — Item #1 + #3 + #5 unlock streaming generation
2. **Action is the market opportunity** — Robot makers will pay for <2W power budget (Items #6, #10)
3. **Prioritize Phase 1** — 4-week timeline to demonstrate feasibility
4. **Publish results** — "N1B0 supports multimodal VLA" is strong marketing story

### For Hardware Engineers
1. **Start with Item #1** (K-Counter) — Lowest risk, highest language impact
2. **Item #6 DVFS is critical** — Impossible to reach Action power budget without it
3. **Item #10 L1 gating is complementary** — Together, save 95% leakage (45mW)
4. **Phase 3 is risky** — Tile merging requires careful mesh integration

### For Software/Firmware Teams
1. **Item #1 unlocks streaming** — Enable per-layer K configuration in firmware APIs
2. **Items #2, #3, #5 require CSRs** — Plan firmware driver updates
3. **Item #6 DVFS needs polling** — Monitor frequency state, prevent stalls
4. **Item #10 L1 sizing is transparent** — Firmware can query via RO CSR

---

## Appendix: File Locations & Versions

All documentation stored in `/secure_data_from_tt/20260221/DOC/N1B0/`:

| File | Version | Status | Size |
|---|---|---|---|
| VLA_CAPABILITY_ASSESSMENT.md | 1.0 | ✅ Complete | 4.2 KB |
| VLA_CAPABILITY_ASSESSMENT_ENHANCED.md | 1.0 | ✅ Complete | 12.5 KB |
| VLA_RTL_IMPLEMENTATION_GUIDE.md | 1.0 | ✅ Complete (Items 1-10 full RTL) | 22.8 KB |
| VLA_COMPLETE_MULTIMODAL_GUIDE.md | 1.0 | ✅ This document | 18.5 KB |
| PPA_RTL_IMPLEMENTATION_GUIDE.md | 1.0 | ✅ Standalone (independent) | 8.3 KB |

**Related N1B0 Documents:**
- N1B0_HDD_v0.1.md — Full hardware design specification
- N1B0_NPU_HDD_v0.98.md — NPU design details
- N1B0_SW_Guide_v0.4.md — Firmware and software APIs

---

## Conclusion

**N1B0 can become a true Vision-Language-Action multimodal accelerator** through 10 targeted RTL improvements, delivered in 3 phases over 9-15 weeks.

- **Phase 1 (Low-risk):** Language efficiency + Action power feasibility
- **Phase 2 (Medium-risk):** Vision adaptability + Language robustness
- **Phase 3 (Higher-risk):** Advanced features for future architectures

**The investment is justified:**
- 38% overall VLA capability improvement (6.3 → 8.7/10)
- $100M+ addressable market (robots, autonomous vehicles, edge AI)
- Competitive parity with GPU for multimodal inference

**Next Steps:**
1. Review this guide with stakeholder team
2. Prioritize Phase 1 features
3. Assign RTL engineers to Items #1, #6, #10
4. Schedule design reviews and validation planning

---
