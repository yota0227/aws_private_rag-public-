# N1B0 DV Guide — Firmware-Based Test Coverage

**Version:** 0.1
**Date:** 2026-03-20
**Scope:** Trinity / N1B0 SoC — all firmware-driven DV tests derived from
`/secure_data_from_tt/20260221/firmware/`

---

## Table of Contents

1. [Test Inventory](#1-test-inventory)
2. [DV Coverage Hole Analysis](#2-dv-coverage-hole-analysis)
3. [New DV Test Cases — Proposed](#3-new-dv-test-cases--proposed)

---

## 1. Test Inventory

### 1.1 Data Movement Tests (`firmware/data_movement/tests/`)

| # | Test Name | Status | Hardware Blocks Exercised | Key Scenarios |
|---|-----------|--------|--------------------------|---------------|
| T01 | `hello_world` | Implemented | BRISC boot, MMIO scratch | Hart boot sanity — each hart writes POSTCODE_PASS |
| T02 | `addr_pinger` | Implemented | NoC receive cmdbuf, L2 cache, 8-hart dispatch | Host→FW command queue: WRITE, READ, WRITE_INLINE, COMPARE, FINISH, WRITES_ACK, WRITE_REPEAT |
| T03 | `fds_sanity` | Implemented | FDS Dispatch (×2), FDS TensixNEO (×12), auto-dispatch FIFO | GO/DONE polling handshake, GroupID counting, filter threshold, auto-dispatch cycle config |
| T04 | `trinity_performance` | Implemented | All 3 NoC cmdbufs, VC wrapping registers | 3-cmdbuf concurrent write+read, multi-VC (1/2/4 VCs), Tensix→N2A bandwidth |
| T05 | `simple_edc_harvesting` | Implemented | NoC send/receive cmdbuf, NOC_CONFIG_VC_DIM_ORDER | Row-harvest NoC rerouting: cross-row write/read, 1-to-all-column broadcast, XY/YX routing modes |
| T06 | `simple_edc_col_harvesting` | Implemented | NoC send/receive cmdbuf, NOC_CONFIG_VC_DIM_ORDER | Column-harvest NoC rerouting: col-0↔col-2 write/read, 1-to-all-row broadcast, bypass of col-1 |
| T07 | `sanity_edc_harvesting` | **STUB** | None | Empty — only calls `test_pass()` |
| T08 | `sanity_edc_col_harvesting` | **STUB** | None | Empty — only calls `test_pass()` |
| T09 | `sanity_security_fence` | Implemented | SMN group fence, SMN level fence, NoC send cmdbuf | Stage 1: same-group write PASS / diff-group write BLOCK. Stage 2: level-3 write BLOCK (req≥5) / level-8 write PASS |
| T10 | `security_fence_noc2axi` | Implemented | NOC2AXI BIU security fence, L1 cache, sync flag | 4 scenarios: group-PASS, group-BLOCK, level-PASS, level-BLOCK; write+readback to NOC2AXI SRAM; Python-synchronized |

### 1.2 Overlay DM Tests (`firmware/overlay/software/dm_tests/`)

| # | Test Name | Status | Hardware Blocks Exercised | Key Scenarios |
|---|-----------|--------|--------------------------|---------------|
| T11 | `all_to_all_test_vc_inc` | Implemented | ATT (Address Translation Table), NoC receive cmdbuf, ADDRGEN, cycle counter | Per-VC all-to-all read with ATT endpoint mapping; bytes/cycle measurement; VC increment mode |

### 1.3 Tensix LLK Tests (`firmware/tensix_tests/`)

| # | Test Name | Status | Hardware Blocks Exercised | Key Scenarios |
|---|-----------|--------|--------------------------|---------------|
| T12 | `llk_unpack_datacopy` | Implemented | TDMA unpack, SRCA/SRCB | Unpack data copy through TDMA path |
| T13 | `llk_unpack_matmul_block` | Implemented | TDMA unpack, SRCA/SRCB | Unpack for matmul block (B-operand staging) |
| T14 | `llk_math_datacopy` | Implemented | FPU G-Tile/M-Tile, DEST | Math unit data passthrough |
| T15 | `llk_math_matmul_block` | Implemented | FPU G-Tile, DEST, SRCA/SRCB | INT/FP matmul block |
| T16 | `llk_math_matmul_block_trinity` | Implemented | FPU (Trinity/N1B0 config), G-Tile | Trinity-specific matmul configuration |
| T17 | `llk_pack_datacopy` | Implemented | TDMA pack, L1 write, DEST | Pack data copy output path |
| T18 | `llk_pack_l1_acc_block` | Implemented | TDMA pack, L1 accumulate, DEST | L1 accumulation during pack |

---

## 2. DV Coverage Hole Analysis

### 2.1 STUB Tests (Empty Implementations)

| Hole ID | Related Test | Description | New TC Possible? |
|---------|-------------|-------------|-----------------|
| H01 | T07 `sanity_edc_harvesting` | Test body is empty — no actual EDC harvesting scenario is run. The "sanity" checks (EDC ring reconfiguration, bypass CDC, init_cnt, MCPDLY) after row-harvest are never exercised. | **Yes** — see P01 |
| H02 | T08 `sanity_edc_col_harvesting` | Same as H01 but for column harvesting. EDC column bypass topology and ring continuity after column harvest are not checked. | **Yes** — see P02 |

---

### 2.2 EDC Ring Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H03 | **EDC error injection / CRC check not tested.** All existing tests assume clean data; no test injects a bit flip into an EDC-protected flit and verifies that the ring detects+reports the error (EDC_STATUS CSR bit, error interrupt). | **Yes** — see P03 |
| H04 | **EDC ring continuity after harvest not verified.** T05/T06 verify NoC routing correctness but do NOT read EDC ring CSRs to confirm the ring traverses the harvested topology correctly (bypass nodes, MCPDLY re-derivation). | **Yes** — see P04 |
| H05 | **EDC init_cnt / MCPDLY boundary conditions not tested.** No test exercises the edge case where MCPDLY is computed at the minimum or maximum delay value. | **Yes** — see P05 |
| H06 | **N1B0 composite tile (NOC2AXI_ROUTER_NE/NW_OPT) EDC internal chain not directly tested.** The composite tile spans two rows; its internal EDC forward+loopback chain is never independently exercised. | **Partial** — requires DV-side force/probe |

---

### 2.3 Harvest Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H07 | **ISO_EN[11:0] (N1B0 harvest mechanism 6) not exercised.** T05/T06 exercise routing aspects but never toggle ISO_EN bits and verify power-domain isolation of harvested tiles (no leakage, no spurious traffic). | **Yes** — see P06 |
| H08 | **Multi-column harvest combination not tested.** T06 tests a single column bypass. No test exercises harvesting 2+ non-adjacent columns simultaneously, which stresses the DOR/dynamic routing path length. | **Yes** — see P07 |
| H09 | **Harvest + security fence interaction not tested.** No test exercises a security fence access to an address range that spans a harvested column boundary. | **Yes** — see P08 |
| H10 | **Harvest reset isolation (noc_isolation / mesh_start reconfiguration) not verified.** The reset isolation mechanism (mechanism 4) is not validated: harvested tile reset held asserted while neighbors operate. | **Partial** — requires DV-level reset control |

---

### 2.4 Security (SMN) Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H11 | **Only write transactions tested for SMN blocking.** T09/T10 use NOC write to trigger fence violations. NoC reads to a blocked range are never tested (read-blocking behavior may differ from write-blocking). | **Yes** — see P09 |
| H12 | **Violation error status register (BIU error FIFO) not read back.** T10 uses a delay loop to avoid BIU FIFO overflow but never reads the violation log to confirm the correct flit address and master ID were recorded. | **Yes** — see P10 |
| H13 | **All 8 SMN security ranges not fully exercised.** T09/T10 only use GROUP_RANGE and SECURE_RANGE (2 of 8 configurable ranges). Ranges 3–8 are never configured or tested. | **Yes** — see P11 |
| H14 | **SMN security range overlap / priority not tested.** No test configures two overlapping ranges with different group/level requirements to validate priority resolution. | **Yes** — see P12 |
| H15 | **Security fence bypass via NOC2AXI tendril routing not tested.** A flit using tendril (alternative) routing to reach a secured range is never attempted. | **Partial** — requires tendril routing config |
| H16 | **AxUSER field propagation through AXI gasket not verified.** The security level is carried in AxUSER; no test explicitly checks that the AXI master level is correctly propagated from NoC flit to AXI AxUSER to SMN comparator. | **Partial** — requires waveform/CSR check |

---

### 2.5 NoC / Router Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H17 | **DOR (Dimension-Order Routing) vs. Dynamic routing not compared.** T05/T06 set DIM_ORDER_SEL but never run the same traffic pattern under dynamic routing to compare results. | **Yes** — see P13 |
| H18 | **Tendril routing mode not tested.** No firmware test configures and exercises tendril routing (alternative path through mesh). | **Partial** — requires router ATT config |
| H19 | **NoC VC back-pressure / congestion not tested.** T04 uses multi-VC but does not saturate VCs to measure head-of-line blocking or VC starvation. | **Yes** — see P14 |
| H20 | **Path squash flit mechanism not exercised.** The path squash flit type (used to cancel an in-flight flit sequence) is never tested. | **Partial** — complex router internal, may need RTL force |
| H21 | **All-to-all write traffic not tested.** T11 does all-to-all reads; there is no matching all-to-all write test (different stress on NoC mesh congestion). | **Yes** — see P15 |
| H22 | **addr_pinger WRITE_REPEAT (infinite loop) has no proper termination / power measurement.** The WRITE_REPEAT command is included but there is no companion DV test that measures power or detects liveness issues. | **Yes** — see P16 |

---

### 2.6 FDS Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H23 | **FDS interrupt mode not tested.** T03 is explicitly polling-only. The FDS interrupt path (TT_FDS_DISPATCH_INTERRUPT_ENABLE) is never enabled or verified. | **Yes** — see P17 |
| H24 | **FDS with >2 phases (NUM_PHASES > 2) and >4 subgrids not tested.** T03 uses NUM_PHASES=2 and 4 subgrids. Multi-epoch scenarios with higher phase counts are uncovered. | **Yes** — see P18 |
| H25 | **FDS GroupID=0 (reserved) behavior not tested.** T03 uses GroupIDs 1–4. GroupID=0 is reserved; sending it should not trigger any valid dispatch. | **Yes** — see P19 |
| H26 | **FDS auto-dispatch FIFO overflow/underflow not tested.** No test deliberately overfills the auto-dispatch FIFO (TT_FDS_DISPATCH_AUTO_DISPATCH_FIFO_FULL) to verify stall behavior. | **Yes** — see P20 |
| H27 | **FDS filter threshold (de-glitcher) corner cases not tested.** T03 uses FILTER_THRESHOLD=700. Threshold=0 (passthrough) and threshold=max (maximum de-glitch delay) are never tried. | **Yes** — see P21 |

---

### 2.7 ATT (Address Translation Table) Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H28 | **ATT disabled path not tested.** T11 always enables ATT. No test verifies that when ATT is disabled, addresses pass through unchanged. | **Yes** — see P22 |
| H29 | **ATT mask/endpoint table boundary conditions not tested.** Only a full-grid ATT table is used. Tests with partial fills, non-contiguous endpoint assignments, or invalid endpoint IDs are missing. | **Yes** — see P23 |

---

### 2.8 Tensix / LLK Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H30 | **SFPU (Special Function Processing Unit) not tested.** No firmware test exercises the SFPU path (reciprocal, exp, GELU, etc.). | **Yes** — requires SFPU kernel |
| H31 | **Stochastic rounding not tested.** The FPU stochastic rounding mode (LFSR-based) is never enabled in any test. | **Yes** — requires FPU config |
| H32 | **L1 4× expansion (N1B0 3072 macros/tile) correctness not tested.** The LLK tests do not specifically address or probe the 768KB L1 capacity boundary; no test writes the full L1 and reads back to check for address aliasing. | **Yes** — see P24 |
| H33 | **DEST register file (latch array) full coverage not tested.** G-Tile latch direct test path does not exist in current firmware (per GtileLatch_DirectTest_Guide_V0.1.md). Only a small subset of DEST rows is exercised by LLK tests. | **Partial** — requires DFX scan path (per design guide) |
| H34 | **Pack with SRCA accumulation (different from L1 acc) not tested.** `llk_pack_l1_acc_block` tests L1 accumulation, but SRCA-register-level accumulation mode is not exercised. | **Yes** — requires LLK kernel |
| H35 | **Multi-format LLK testing (INT16/INT8/FP16B/FP32) not present.** All LLK tests are single-format. Mixed-format operations and format-conversion paths are uncovered. | **Yes** — see P25 |

---

### 2.9 Performance / Perf Monitor Coverage Holes

| Hole ID | Description | New TC Possible? |
|---------|-------------|-----------------|
| H36 | **noc2axi_perf_monitor (simulation-only) never instantiated in any firmware test.** The perf monitor module (M16 in memory) is documented but no firmware test exercises its 8 metric output ports or round-trip latency measurement mode. | **Yes** — see P26 |
| H37 | **axi_dynamic_delay_buffer (synthesizable delay injection) not exercised.** No test programs delay_cycles to inject AXI latency and verifies that subsequent reads observe the correct delay. | **Yes** — see P27 |

---

## 3. New DV Test Cases — Proposed

### 3.1 EDC Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P01 | `edc_sanity_row_harvest` | H01 | After row harvest, read EDC ring CSRs per node to verify traversal order matches N1B0 ring topology. Write a known pattern, trigger EDC snapshot, check all nodes visited. | **Can be written** — needs EDC CSR read API |
| P02 | `edc_sanity_col_harvest` | H02 | Same as P01 but after column harvest (ISO_EN for col). Verify bypass EDC nodes are skipped and ring init_cnt matches expected count. | **Can be written** |
| P03 | `edc_error_inject` | H03 | Flip a data bit in-flight via test-mode pin or RTL force, verify EDC error status CSR asserts and correct node reports violation. | **Partial** — RTL-level force needed for bit flip injection |
| P04 | `edc_ring_continuity_harvest` | H04 | After harvest, poll EDC ring status register in SW to confirm toggling CDC pattern successfully traverses all active nodes without lockup. | **Can be written** |
| P05 | `edc_mcpdly_boundary` | H05 | Configure MCPDLY to minimum (1) and maximum values; verify ring still initializes successfully and no init_cnt mismatch is flagged. | **Can be written** |

---

### 3.2 Harvest Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P06 | `iso_en_isolation_check` | H07 | Toggle ISO_EN bits for a Tensix column, verify harvested tile does not respond to NoC writes (no ACK, no data corruption at neighbors). | **Can be written** |
| P07 | `multi_col_harvest_routing` | H08 | Harvest columns 1 AND 3 simultaneously; run NoC writes from col-0 to col-2 and verify packets route correctly (DOR must skip 2 harvested columns). | **Can be written** |
| P08 | `harvest_security_fence_crossing` | H09 | Configure security fence range crossing the harvested column boundary address; verify fence behavior is unchanged. | **Can be written** |

---

### 3.3 Security Fence Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P09 | `smn_read_block_test` | H11 | Issue NOC read to a range with higher level requirement from a low-level master; verify read response is blocked / returns error. | **Can be written** |
| P10 | `smn_violation_log_readback` | H12 | After triggering a group-fence violation, read SMN/BIU violation FIFO CSR; verify logged address, master ID, and violation type match the issued flit. | **Can be written** |
| P11 | `smn_all_8_ranges` | H13 | Configure all 8 SMN ranges with distinct group/level settings; fire test transactions to each range (pass + block per range). | **Can be written** |
| P12 | `smn_overlap_priority` | H14 | Configure two overlapping ranges (e.g., range A: group-only, range B: level+group); access the overlap with transactions that satisfy only one constraint; verify priority resolution. | **Can be written** |

---

### 3.4 NoC / Router Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P13 | `noc_dor_vs_dynamic_routing` | H17 | Run identical all-to-all read traffic under DOR (DIM_ORDER_SEL=XY) and then under dynamic routing; compare data integrity and measure latency difference. | **Can be written** |
| P14 | `noc_vc_backpressure` | H19 | Saturate VCs by sending max-rate traffic on all VCs simultaneously from multiple tiles; verify no deadlock, measure throughput degradation. | **Can be written** |
| P15 | `all_to_all_write` | H21 | Mirror of T11 but using writes instead of reads; each tile writes to all others and checks destination memory. | **Can be written** |
| P16 | `write_repeat_power_stress` | H22 | Run WRITE_REPEAT command from addr_pinger for a timed window; verify tile remains live (can receive FINISH command after), measure activity via perf counter. | **Can be written** |

---

### 3.5 FDS Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P17 | `fds_interrupt_mode` | H23 | Enable FDS interrupt (TT_FDS_DISPATCH_INTERRUPT_ENABLE) on both Dispatch and NEO; use interrupt handler instead of polling to receive GO/DONE; verify interrupt fires and clears correctly. | **Can be written** |
| P18 | `fds_multi_epoch` | H24 | Run NUM_PHASES=16 with all 4 subgrids; verify no missed GOs or DONEs across 16 rounds. | **Can be written** |
| P19 | `fds_groupid_zero_reserved` | H25 | Send GroupID=0 from a NEO; verify no Dispatch counter increments, no spurious GO sent. | **Can be written** |
| P20 | `fds_fifo_overflow` | H26 | Fill auto-dispatch FIFO to capacity; verify FIFO_FULL asserts, firmware stalls correctly, and next slot opens after read. | **Can be written** |
| P21 | `fds_filter_threshold_corner` | H27 | Run FDS with FILTER_THRESHOLD=0 (no de-glitch) and FILTER_THRESHOLD=max; verify correct GO/DONE propagation in both cases. | **Can be written** |

---

### 3.6 ATT Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P22 | `att_disabled_passthrough` | H28 | Disable ATT (noc_address_translation_table_en = false); issue reads with raw endpoint addresses; verify data arrives at correct physical coordinates without translation. | **Can be written** |
| P23 | `att_partial_table` | H29 | Fill ATT with only half the grid endpoints; access an untranslated endpoint; verify expected behavior (drop / error / wrap). | **Can be written** |

---

### 3.7 Tensix / LLK Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P24 | `l1_full_capacity` | H32 | Write 768KB (3072×256B) to N1B0 L1, read back in reverse order; verify no aliasing, check all banks. | **Can be written** |
| P25 | `llk_multi_format_matmul` | H35 | Run matmul in INT16, INT8, FP16B, FP32 modes sequentially; verify output correctness for each format and format-conversion intermediates. | **Can be written** |

---

### 3.8 Perf Monitor / AXI Delay Tests

| ID | Test Name | Covers Holes | Description | Feasibility |
|----|-----------|-------------|-------------|-------------|
| P26 | `perf_monitor_latency` | H36 | Instantiate noc2axi_perf_monitor in simulation; run addr_pinger workload; read 8 metric ports (MONITOR_ROUND_TRIP_LATENCY plusarg enabled); verify latency histogram plausibility. | **Can be written** (sim-only) |
| P27 | `axi_dynamic_delay_inject` | H37 | Configure axi_dynamic_delay_buffer with delay_cycles=50; send 10 consecutive AXI reads; verify response timestamps match T_issue + 50 cycles (±tolerance). | **Can be written** |

---

## Summary Table

| Category | Total Holes | New TC Feasible | Partial / Needs RTL | Total Proposed |
|----------|-------------|-----------------|---------------------|----------------|
| EDC Ring | 4 (H01–H06) | 4 (P01–P05 excl P03) | 1 (P03) | 5 |
| Harvest | 4 (H07–H10) | 3 (P06–P08) | 1 (H10) | 3 |
| Security (SMN) | 6 (H11–H16) | 4 (P09–P12) | 2 (H15, H16) | 4 |
| NoC / Router | 6 (H17–H22) | 4 (P13–P16) | 2 (H18, H20) | 4 |
| FDS | 5 (H23–H27) | 5 (P17–P21) | 0 | 5 |
| ATT | 2 (H28–H29) | 2 (P22–P23) | 0 | 2 |
| Tensix / LLK | 6 (H30–H35) | 3 (P24, P25 + H30/H31/H34 if kernels written) | 1 (H33) | 2 |
| Perf / AXI Delay | 2 (H36–H37) | 2 (P26–P27) | 0 | 2 |
| **Total** | **35** | **27** | **7** | **27** |

> **"Partial / Needs RTL"** holes require either RTL-level force/probe (e.g., bit-flip injection, reset control, waveform observation) and cannot be fully addressed by firmware alone. They require SV-level test bench support or DFX infrastructure additions.

---

## Appendix: Firmware Test Architecture Reference

```
RISC-V BRISC harts (mhartid 0–7)
     │
     ├─ cache::mx()/my()      ─ tile coordinates from CSR
     ├─ cache::flush_l2()     ─ writeback L2 cache line
     ├─ cache::invalidate_l2() ─ invalidate L2 cache line
     ├─ mmio::write_dm_scratch() ─ test scratch register (POSTCODE)
     │
     ├─ NoC cmdbufs (3 per tile: receive / send / reg)
     │   ├─ noc_write_prep_*_cmdbuf()   ─ configure cmdbuf for writes
     │   ├─ noc_read_prep_*_cmdbuf()    ─ configure cmdbuf for reads
     │   ├─ noc_*_issue_*_cmdbuf()      ─ issue one transfer
     │   ├─ noc_nonposted_writes_acked_*() ─ poll write completion
     │   └─ noc_reads_acked_*()         ─ poll read completion
     │
     ├─ ATT: noc_address_translation_table_*()
     ├─ ADDRGEN: ADDRGEN_WR_REG(), ADDRGEN_PUSH_BOTH()
     ├─ FDS: FDS_INTF_READ/WRITE() via RoCC custom opcode
     └─ NOC config: WRITE_REG32(NOC_CONFIG_VC_DIM_ORDER_REG_ADDR, ...)
```

---

*End of DV Guide v0.1*
