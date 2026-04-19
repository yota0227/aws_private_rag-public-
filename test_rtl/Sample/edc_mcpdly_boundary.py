"""
EDC MCPDLY Boundary Test
Covers: H05

MCPDLY (Multi-Cycle Path Delay) controls the toggle CDC synchronization
in the EDC ring. Default is MCPDLY=7 (derived from clock ratio).
This test configures MCPDLY to minimum (1) and maximum (15) values
and verifies the ring initializes without fatal errors.

New hole: No test configures MCPDLY != default value.
TB capability: APB direct write to BIU config register for MCPDLY field.
The MCPDLY field is at BIU_CTRL_REG[6:3] (4-bit field per EDC spec).
"""

from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from cocotb.triggers import Timer, ClockCycles, with_timeout
import cocotb

# MCPDLY field encoding in BIU_CTRL_REG
MCPDLY_SHIFT  = 3        # bits [6:3]
MCPDLY_MASK   = 0xF      # 4-bit field
MCPDLY_DEFAULT = 7

# BIU_STAT_REG error bits
FATAL_ERR_BIT = 0x80
UNC_ERR_BIT   = 0x20

# Ring re-initialization settle time (in noc_clk cycles)
RING_REINIT_CYCLES = 200

# Test values: minimum, default, near-max, maximum
MCPDLY_TEST_VALUES = [1, MCPDLY_DEFAULT, 14, 15]


async def edc_mcpdly_boundary(dut):
    """
    Sweep MCPDLY field in BIU_CTRL_REG across boundary values and verify
    the EDC ring remains healthy (no FATAL_ERR, no UNC_ERR) after each
    re-initialization.

    Test values: 1 (min), 7 (default), 14 (near-max), 15 (max)
    """

    tb = demoTB(dut)
    await tb.init_and_reset()
    await tb.release_dm_core_reset()

    noc2axi_coords = (
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)
    )

    if len(noc2axi_coords) == 0:
        assert False, "No noc2axi coordinates found"

    # Use APB master 0 throughout
    apb_master = 0

    # --- Clear initial state ---
    status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
    if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
        await edc_clear_biu_interrupts(
            tb, apb_master, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS)
        )
        await ClockCycles(tb.dut.noc_clk, 2)

    if await edc_check_fatal_errors(tb, apb_master, status):
        assert False, "Fatal error in initial BIU_STAT"

    tb.log.info(
        f"EDC MCPDLY boundary test — "
        f"testing values {MCPDLY_TEST_VALUES}, field at BIU_CTRL_REG[6:3]"
    )

    results = []  # list of (mcpdly_val, status, pass_flag)

    for mcpdly_val in MCPDLY_TEST_VALUES:
        tb.log.info("=" * 60)
        tb.log.info(f"Testing MCPDLY={mcpdly_val}")

        # --- Step a: Read current BIU_CTRL_REG ---
        ctrl = await tb.read_edc_apb_register(apb_master, BIU_CTRL_REG)
        tb.log.info(f"  Current BIU_CTRL_REG=0x{ctrl:08x}")

        # --- Step b: Construct new CTRL value with MCPDLY field ---
        new_ctrl = (ctrl & ~(MCPDLY_MASK << MCPDLY_SHIFT)) | (mcpdly_val << MCPDLY_SHIFT)
        tb.log.info(f"  Writing BIU_CTRL_REG=0x{new_ctrl:08x} (MCPDLY={mcpdly_val})")

        # --- Step c: Write new value ---
        await tb.write_edc_apb_register(apb_master, BIU_CTRL_REG, new_ctrl)

        # --- Step d: Read back and verify MCPDLY field ---
        ctrl_rb = await tb.read_edc_apb_register(apb_master, BIU_CTRL_REG)
        mcpdly_rb = (ctrl_rb >> MCPDLY_SHIFT) & MCPDLY_MASK
        tb.log.info(
            f"  BIU_CTRL_REG readback=0x{ctrl_rb:08x}, "
            f"MCPDLY field={mcpdly_rb}"
        )
        assert mcpdly_rb == mcpdly_val, (
            f"MCPDLY readback mismatch: wrote {mcpdly_val}, read {mcpdly_rb}"
        )

        # --- Step e: Wait for ring to re-initialize ---
        tb.log.info(f"  Waiting {RING_REINIT_CYCLES} noc_clk cycles for ring re-init...")
        await ClockCycles(tb.dut.noc_clk, RING_REINIT_CYCLES)

        # --- Step f/g: Read BIU_STAT and check error bits ---
        status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        no_fatal = (status & FATAL_ERR_BIT) == 0
        no_unc   = (status & UNC_ERR_BIT) == 0
        pass_flag = no_fatal and no_unc

        # --- Step h: Log result ---
        tb.log.info(
            f"  MCPDLY={mcpdly_val}: STAT=0x{status:08x} "
            f"FATAL_ERR={not no_fatal} UNC_ERR={not no_unc} "
            f"— {'PASS' if pass_flag else 'FAIL'}"
        )
        results.append((mcpdly_val, status, pass_flag))

        # --- Assertions ---
        assert no_fatal, (
            f"MCPDLY={mcpdly_val}: FATAL_ERR bit set (BIU_STAT=0x{status:08x})"
        )
        assert no_unc, (
            f"MCPDLY={mcpdly_val}: UNC_ERR bit set (BIU_STAT=0x{status:08x})"
        )

        # --- Step i: Clear any error bits before next iteration ---
        if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
            await edc_clear_biu_interrupts(
                tb, apb_master, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS)
            )
            await ClockCycles(tb.dut.noc_clk, 2)

    # --- Restore MCPDLY to default ---
    tb.log.info("=" * 60)
    tb.log.info(f"Restoring MCPDLY={MCPDLY_DEFAULT} (default)")
    ctrl = await tb.read_edc_apb_register(apb_master, BIU_CTRL_REG)
    new_ctrl = (ctrl & ~(MCPDLY_MASK << MCPDLY_SHIFT)) | (MCPDLY_DEFAULT << MCPDLY_SHIFT)
    await tb.write_edc_apb_register(apb_master, BIU_CTRL_REG, new_ctrl)

    await ClockCycles(tb.dut.noc_clk, RING_REINIT_CYCLES)

    # Verify clean state after restore
    status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
    assert not (status & FATAL_ERR_BIT), (
        f"FATAL_ERR set after restoring MCPDLY={MCPDLY_DEFAULT} "
        f"(BIU_STAT=0x{status:08x})"
    )
    assert not (status & UNC_ERR_BIT), (
        f"UNC_ERR set after restoring MCPDLY={MCPDLY_DEFAULT} "
        f"(BIU_STAT=0x{status:08x})"
    )
    tb.log.info(f"Restored — BIU_STAT=0x{status:08x} — clean")

    # --- Summary ---
    tb.log.info("=" * 60)
    tb.log.info("MCPDLY boundary test summary:")
    for val, stat, ok in results:
        tb.log.info(
            f"  MCPDLY={val:2d}: BIU_STAT=0x{stat:08x} — {'PASS' if ok else 'FAIL'}"
        )
    tb.log.info("=" * 60)
    tb.log.info("edc_mcpdly_boundary PASSED")
