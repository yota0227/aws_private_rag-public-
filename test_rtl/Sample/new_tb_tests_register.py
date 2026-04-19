"""
new_tb_tests_register.py
========================

Registration snippet for new TB-side DV tests.

Copy the import block and test function definitions below into test_trinity.py
to register the 10 new tests in the cocotb test suite.

These tests cover holes not addressable by firmware tests alone and exploit
TB-specific capabilities: APB register access, BIU interrupt monitors,
SecurityFenceViolation parsing, L1Backdoor VPI, AXI master writes,
and perf/delay buffer register readback.
"""

# ============================================================
# NEW TB-SIDE DV TESTS — Add to test_trinity.py
# These tests cover holes not addressable by firmware alone.
# ============================================================

# Add these imports to test_trinity.py:
# from tests.edc_selftest_all_nodes import edc_selftest_all_nodes
# from tests.edc_ring_continuity_harvest import edc_ring_continuity_harvest
# from tests.biu_violation_log_readback import biu_violation_log_readback
# from tests.biu_unc_err_vs_lat_err import biu_unc_err_vs_lat_err
# from tests.l1_backdoor_frontdoor_cross_check import l1_backdoor_frontdoor_cross_check
# from tests.edc_mcpdly_boundary import edc_mcpdly_boundary
# from tests.smn_overlap_priority import smn_overlap_priority
# from tests.harvest_security_fence_crossing import harvest_security_fence_crossing
# from tests.perf_monitor_metrics import perf_monitor_metrics
# from tests.axi_dynamic_delay_inject import axi_dynamic_delay_inject

# Add these test functions to test_trinity.py:
# (paste after existing @cocotb.test entries)

import cocotb
from cocotb.triggers import ClockCycles

# Lazy imports — resolved at runtime to avoid circular dependencies
from tests.edc_selftest_all_nodes import edc_selftest_all_nodes
from tests.edc_ring_continuity_harvest import edc_ring_continuity_harvest
from tests.biu_violation_log_readback import biu_violation_log_readback
from tests.biu_unc_err_vs_lat_err import biu_unc_err_vs_lat_err
from tests.l1_backdoor_frontdoor_cross_check import l1_backdoor_frontdoor_cross_check
from tests.edc_mcpdly_boundary import edc_mcpdly_boundary
from tests.smn_overlap_priority import smn_overlap_priority
from tests.harvest_security_fence_crossing import harvest_security_fence_crossing
from tests.perf_monitor_metrics import perf_monitor_metrics
from tests.axi_dynamic_delay_inject import axi_dynamic_delay_inject


@cocotb.test(skip=False)
async def edc_selftest_all_nodes_test(dut):
    """
    H01/H02: EDC selftest for ALL BIU nodes (not just node 0).
    Existing sanity_edc_selftest.py hardcodes apb_master=0; this test
    iterates all num_apb masters and verifies each returns a valid GEN_EVENT.
    """
    await edc_selftest_all_nodes(dut)


@cocotb.test(skip=False)
async def edc_ring_continuity_harvest_test(dut):
    """
    H04: Verify EDC BIU_STAT is clean (no FATAL/UNC) after configuring
    row/column harvest via NOC_CONFIG_BROADCAST_*_DISABLE registers.
    Firmware tests T05/T06 never read EDC APB registers after harvest config.
    """
    await edc_ring_continuity_harvest(dut)


@cocotb.test(skip=False)
async def biu_violation_log_readback_test(dut):
    """
    H12: Trigger a group-fence violation and validate BIU RSP_HDR1/RSP_DATA0
    capture registers using SecurityFenceViolation.from_capture_registers().
    This call path has never been exercised in any existing test.
    """
    await biu_violation_log_readback(dut)


@cocotb.test(skip=False)
async def biu_unc_err_vs_lat_err_test(dut):
    """
    New hole: CRIT_ERR_IRQ wire covers both LAT_ERR (bit 4) and UNC_ERR (bit 5).
    This test independently triggers each error type and verifies they are
    distinguishable by BIU_STAT_REG bit position.
    """
    await biu_unc_err_vs_lat_err(dut)


@cocotb.test(skip=False)
async def l1_backdoor_frontdoor_cross_check_test(dut):
    """
    H33: Cross-check L1Backdoor (VPI direct SRAM) vs NoC frontdoor for tile (0,0)
    and the first 4 Tensix tiles. Also tests 768KB N1B0 L1 boundary for aliasing.
    sanity_l1_backdoor.py is marked skip=True and has never run in CI.
    """
    await l1_backdoor_frontdoor_cross_check(dut)


@cocotb.test(skip=False)
async def edc_mcpdly_boundary_test(dut):
    """
    H05: Program MCPDLY field (BIU_CTRL_REG[6:3]) to boundary values
    (1, 7, 14, 15) and verify the EDC ring re-initializes without fatal errors.
    No existing test changes MCPDLY from its default value of 7.
    """
    await edc_mcpdly_boundary(dut)


@cocotb.test(skip=False)
async def smn_overlap_priority_test(dut):
    """
    H14: Configure two overlapping SMN address ranges (group fence + level fence)
    and verify that the stricter check wins for four transaction categories
    spanning same/diff group × high/low security level.
    No existing test configures more than 1 SMN range at a time.
    """
    await smn_overlap_priority(dut)


@cocotb.test(skip=False)
async def harvest_security_fence_crossing_test(dut):
    """
    H09: Combine harvest (col 1 disabled via NOC_CONFIG_BROADCAST_COL_DISABLE)
    with a group security fence and verify that:
    - Active same-group writes pass
    - Active diff-group writes are blocked
    - Harvested col writes do not generate UNC_ERR on the protected tile
    No existing test combines harvest state with security fence.
    """
    await harvest_security_fence_crossing(dut)


@cocotb.test(skip=True)  # skip=True: requires PERF_MONITOR_VERBOSITY plusarg
async def perf_monitor_metrics_test(dut):
    """
    H36: Exercise noc2axi_perf_monitor — read all 8 metric registers after
    generating synthetic NOC traffic. Also handles round-trip latency mode
    when MONITOR_ROUND_TRIP_LATENCY=1 plusarg is present.
    The perf_monitor has never been exercised in any CI test.

    To enable:
      make TESTCASE=perf_monitor_metrics_test PLUSARGS="+PERF_MONITOR_VERBOSITY=1"
    For round-trip latency mode:
      make TESTCASE=perf_monitor_metrics_test \\
           PLUSARGS="+PERF_MONITOR_VERBOSITY=1+MONITOR_ROUND_TRIP_LATENCY=1"
    """
    await perf_monitor_metrics(dut)


@cocotb.test(skip=True)  # skip=True: requires axi_dynamic_delay_buffer instantiation
async def axi_dynamic_delay_inject_test(dut):
    """
    H37: Write delay_cycles register of axi_dynamic_delay_buffer to values
    [0, 50, 100, 200, 250] and verify register write-readback plus
    write-transaction completion (no deadlock). Also tests FIFO
    no-change-when-busy behavior.

    NOTE: DELAY_CYCLES_ADDR (0x019800) is a placeholder — verify from
    N1B0_AXI_Dynamic_Delay_HDD_v0.1.md before enabling in production runs.
    """
    await axi_dynamic_delay_inject(dut)
