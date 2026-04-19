# New TB-Side DV Tests — Summary

This document describes the 10 new cocotb Python DV tests added to
`tests/` that exploit TB-specific capabilities to cover holes that
firmware-only tests cannot reach.

---

## Why Firmware Tests Cannot Cover These Holes

Firmware tests (addr_pinger, FDS, LLK, etc.) run code on the DM tiles and
observe results via postcodes or memory writes. They cannot:

- Read **APB/BIU registers directly** — firmware has no path to the EDC APB
  bus; that bus is wired only to the TB cocotb APB master.
- Parse **BIU capture registers** (RSP_HDR1, RSP_DATA0) — the violation log
  is only accessible from the APB side, not from RISC-V MMIO.
- Exercise **L1 backdoor** (zero-simtime VPI SRAM access) — this is a
  simulation-only capability with no RTL equivalent.
- Drive **security level** fields in NoC flits independently of firmware
  security context.
- **Iterate over all APB masters** in a parameterized loop — firmware runs
  on fixed tiles and cannot enumerate the TB's APB master array.
- Read **perf_monitor output ports** (real-typed cocotb signals) — these are
  simulation-only outputs with no AXI register path.
- Program and observe **axi_dynamic_delay_buffer** register behavior with
  cycle-accurate latency measurement via `cocotb.utils.get_sim_time`.

---

## Test Files

### 1. `edc_selftest_all_nodes.py` — H01/H02

| Item | Detail |
|------|--------|
| Hole | `sanity_edc_selftest.py` hardcodes `apb_master=0`; BIU nodes 1–3 never tested |
| TB capability | APB master per-node loop, BIU interrupt prediction/monitoring |
| What it does | Iterates all `num_apb` APB masters; for each: reads BIU_ID, clears status, writes/reads BIU_IRQ_EN, sends selftest write + pulse to node `(0x1E<<11)|(0x4<<8)|apb_master`, waits for RSP_PKT_RCVD, decodes CMD and asserts GEN_EVENT (0x8) |
| Why FW can't | Firmware has no APB master; can only observe its own tile's EDC status |

---

### 2. `edc_ring_continuity_harvest.py` — H04

| Item | Detail |
|------|--------|
| Hole | T05/T06 firmware harvest tests never read EDC APB registers after harvest config |
| TB capability | AXI master NOC_CONFIG writes + APB BIU_STAT polling |
| What it does | Configures row-1 and col-1 harvest via `NOC_CONFIG_BROADCAST_*_DISABLE` registers, then reads BIU_STAT for all APB masters and asserts no FATAL_ERR or UNC_ERR; restores and re-checks |
| Why FW can't | Firmware cannot read the EDC BIU_STAT register (APB-only path) |

---

### 3. `biu_violation_log_readback.py` — H12

| Item | Detail |
|------|--------|
| Hole | `sanity_security_fence.py` never reads BIU RSP_HDR1/RSP_DATA0 capture registers; `SecurityFenceViolation.from_capture_registers()` is never called in any test |
| TB capability | `SecurityFenceViolation.from_capture_registers()`, APB register readback |
| What it does | Configures group SMN fence on randomized main_col, triggers violation from diff_group_col, reads RSP_HDR1+RSP_DATA0, parses via `from_capture_registers()`, validates src_x, src_y, violated_group_id |
| Why FW can't | BIU capture registers are on the APB bus; firmware cannot read them |

---

### 4. `biu_unc_err_vs_lat_err.py` — New hole

| Item | Detail |
|------|--------|
| Hole | CRIT_ERR_IRQ wire covers both LAT_ERR (bit 4) and UNC_ERR (bit 5); LAT_ERR has never been independently triggered or validated |
| TB capability | APB BIU_STAT bit-level observation, EDC diagnostic selftest path |
| What it does | Phase A: triggers LAT_ERR via EDC diagnostic selftest (pattern 0x01); Phase B: triggers UNC_ERR via group fence violation; asserts Phase B sets UNC_ERR (bit 5) but NOT LAT_ERR (bit 4) |
| Why FW can't | BIU_STAT is APB-only; firmware cannot distinguish LAT_ERR vs UNC_ERR bits |

---

### 5. `l1_backdoor_frontdoor_cross_check.py` — H33

| Item | Detail |
|------|--------|
| Hole | `sanity_l1_backdoor.py` is `skip=True` — never runs in CI; L1Backdoor class never exercised; N1B0 768KB L1 boundary never tested |
| TB capability | `L1Backdoor.direct.write_32b/read_32b` (VPI zero-simtime), `tb.noc_write/noc_read` |
| What it does | Phase 1: backdoor write → NoC frontdoor read; Phase 2: NoC frontdoor write → backdoor read; Phase 3: 768KB boundary alias test; Phase 4: multi-tile sweep (first 4 Tensix tiles) |
| Why FW can't | L1Backdoor is a cocotb VPI mechanism — not available from RISC-V firmware |

---

### 6. `edc_mcpdly_boundary.py` — H05

| Item | Detail |
|------|--------|
| Hole | No test configures MCPDLY ≠ default (7); toggle CDC synchronization boundary behavior never validated |
| TB capability | APB write to BIU_CTRL_REG[6:3], BIU_STAT polling after ring re-init |
| What it does | For MCPDLY ∈ {1, 7, 14, 15}: writes field, reads back, waits 200 noc_clk cycles for ring re-init, asserts no FATAL_ERR or UNC_ERR; restores default |
| Why FW can't | BIU_CTRL_REG is APB-only; firmware cannot program MCPDLY |

---

### 7. `smn_overlap_priority.py` — H14

| Item | Detail |
|------|--------|
| Hole | No existing test configures >1 SMN security range; `range_access_blocked` field of `SecurityFenceViolation` never validated |
| TB capability | APB/AXI range config writes, BIU UNC_ERR monitor, `SecurityFenceViolation` parsing |
| What it does | Configures Range 0 (group fence) and Range 1 (level fence) with overlap at 0x240000–0x280000; issues 4 transactions (same-grp+hi-lvl, same-grp+lo-lvl, diff-grp+hi-lvl, diff-grp+lo-lvl); validates correct blocking and violation type per transaction |
| Why FW can't | SMN range configuration and BIU violation readback require APB access |

---

### 8. `harvest_security_fence_crossing.py` — H09

| Item | Detail |
|------|--------|
| Hole | No test combines harvest state with security fence; interaction between ISO_EN and SMN fence never verified |
| TB capability | AXI NOC_CONFIG harvest writes + APB fence config + BIU UNC_ERR monitor |
| What it does | Harvests col 1 via COL_DISABLE; configures group fence on col 0; verifies col 0 passes, col 2 is blocked (UNC_ERR + violation parse), col 1 (harvested) generates no UNC_ERR at col 0 BIU |
| Why FW can't | Harvest config and BIU monitoring both require APB/TB-master access |

---

### 9. `perf_monitor_metrics.py` — H36 (skip=True by default)

| Item | Detail |
|------|--------|
| Hole | `noc2axi_perf_monitor` is a sim-only module that has never been exercised in any Python test; 8 metric output ports never read |
| TB capability | `cocotb.plusargs` (`PERF_MONITOR_VERBOSITY`, `MONITOR_ROUND_TRIP_LATENCY`), AXI master read of perf register space |
| What it does | Checks plusargs, generates synthetic NOC traffic (or loads addr_pinger), reads 8 metric registers from `PERF_BASE_ADDR=0x019600`, verifies at least one is non-zero; in round-trip mode also validates metric[7] is bounded |
| Enable | `make TESTCASE=perf_monitor_metrics_test PLUSARGS="+PERF_MONITOR_VERBOSITY=1"` |
| Why FW can't | Perf monitor output ports are real-typed cocotb signals; no MMIO register path from firmware |

---

### 10. `axi_dynamic_delay_inject.py` — H37 (skip=True by default)

| Item | Detail |
|------|--------|
| Hole | `axi_dynamic_delay_buffer` (synthesizable) has never been exercised; delay_cycles register never written; no test measures AXI latency to validate delay injection |
| TB capability | `tb.noc_write/noc_read` to delay_cycles register, `cocotb.utils.get_sim_time` for latency measurement |
| What it does | Sweeps delay_cycles ∈ {0, 50, 100, 200, 250}; verifies register write-readback; measures round-trip latency at each setting; tests FIFO no-change-when-busy behavior; restores delay_cycles=0 |
| NOTE | `DELAY_CYCLES_ADDR=0x019800` is a **placeholder** — verify from `N1B0_AXI_Dynamic_Delay_HDD_v0.1.md` before enabling |
| Why FW can't | Delay module is outside the firmware-visible address space; latency measurement requires cocotb simulation-time API |

---

## Registration

See `new_tb_tests_register.py` for the import block and `@cocotb.test` decorated
wrapper functions to paste into `test_trinity.py`.

Tests 1–8 have `skip=False` and are suitable for the default regression.
Tests 9–10 have `skip=True` and require specific plusargs or RTL instantiation
confirmation before enabling.

---

## Hole Coverage Summary

| Test | Hole ID | Root Cause |
|------|---------|------------|
| edc_selftest_all_nodes | H01/H02 | apb_master hardcoded to 0 in existing test |
| edc_ring_continuity_harvest | H04 | No EDC APB read after harvest config in FW tests |
| biu_violation_log_readback | H12 | `from_capture_registers()` never called; RSP_HDR1/DATA0 never read |
| biu_unc_err_vs_lat_err | (new) | LAT_ERR (bit 4) never independently triggered |
| l1_backdoor_frontdoor_cross_check | H33 | `sanity_l1_backdoor` marked `skip=True` |
| edc_mcpdly_boundary | H05 | MCPDLY never changed from default |
| smn_overlap_priority | H14 | Only single SMN range ever configured |
| harvest_security_fence_crossing | H09 | Harvest + fence interaction never tested |
| perf_monitor_metrics | H36 | perf_monitor never exercised |
| axi_dynamic_delay_inject | H37 | delay_buffer never exercised |
