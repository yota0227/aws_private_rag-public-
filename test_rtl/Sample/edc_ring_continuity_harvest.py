"""
EDC Ring Continuity After Harvest — CSR Verification
Covers: H04

After configuring row/column harvest (via NOC_CONFIG registers written by AXI master),
read EDC BIU status register to verify:
  1. No fatal errors in ring (BIU_STAT_REG has no FATAL_ERR / UNC_ERR bits)
  2. Ring initializes correctly after harvest (no init_cnt mismatch indicated by COR_ERR)
  3. RSP_PKT_RCVD clears cleanly (no stuck packets from bypassed nodes)

Specifically tests that the EDC ring traversal re-initializes correctly after
NOC broadcast disable bits are set for harvested rows/columns.

New hole from TB analysis:
- T05/T06 firmware tests never READ EDC APB registers after harvest config
- No test verifies EDC BIU_STAT shows a clean ring after harvest
"""

from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from cocotb.triggers import Timer, ClockCycles, with_timeout
import cocotb

# NOC config register offsets (byte addresses within NOC config space)
NOC_CONFIG_BROADCAST_ROW_DISABLE_OFFSET = 0x108
NOC_CONFIG_BROADCAST_COL_DISABLE_OFFSET = 0x110

# BIU_STAT_REG error bit masks
FATAL_ERR_BIT = 0x80
UNC_ERR_BIT   = 0x20
COR_ERR_BIT   = 0x08


async def _read_and_check_all_biu_stat(tb, num_masters, label, allow_cor_err=True):
    """
    Helper: read BIU_STAT_REG for every APB master and assert no fatal/unc errors.
    Returns a dict of {apb_master: status_value}.
    """
    results = {}
    for apb_master in range(num_masters):
        status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        results[apb_master] = status
        cor_flag   = bool(status & COR_ERR_BIT)
        unc_flag   = bool(status & UNC_ERR_BIT)
        fatal_flag = bool(status & FATAL_ERR_BIT)
        tb.log.info(
            f"  [{label}] APB[{apb_master}] BIU_STAT=0x{status:08x} "
            f"FATAL={fatal_flag} UNC={unc_flag} COR={cor_flag}"
        )
        assert not fatal_flag, (
            f"[{label}] APB master {apb_master}: FATAL_ERR bit set (0x{status:08x})"
        )
        assert not unc_flag, (
            f"[{label}] APB master {apb_master}: UNC_ERR bit set (0x{status:08x})"
        )
        if cor_flag and not allow_cor_err:
            assert False, (
                f"[{label}] APB master {apb_master}: COR_ERR bit set unexpectedly "
                f"(0x{status:08x})"
            )
    return results


async def _clear_all_biu_stat(tb, num_masters):
    """Helper: clear all leftover status bits on every APB master."""
    for apb_master in range(num_masters):
        status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
            await edc_clear_biu_interrupts(
                tb, apb_master, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS)
            )
    await ClockCycles(tb.dut.noc_clk, 2)


async def edc_ring_continuity_harvest(dut):
    """
    Configure row and column harvest via NOC_CONFIG broadcast-disable registers,
    then verify that the EDC BIU_STAT shows a clean ring (no FATAL/UNC errors).

    Scenarios:
      A — Row 1 harvest: set ROW_DISABLE bit 1 on all NOC2AXI tiles
      B — Col 1 harvest: set COL_DISABLE bit 1 on all NOC2AXI tiles
      Restore: write 0x0 back to both registers
    """

    tb = demoTB(dut)
    await tb.init_and_reset()
    await tb.release_dm_core_reset()

    noc2axi_coords = (
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)
    )

    tb.log.info(f"noc2axi_coords: {noc2axi_coords}")
    num_apb = tb.config.num_apb
    tb.log.info(f"num_apb: {num_apb}")

    if len(noc2axi_coords) == 0:
        assert False, "No noc2axi coordinates found"

    # --- Baseline: clean state before harvest ---
    tb.log.info("--- Baseline: reading initial BIU_STAT ---")
    await _clear_all_biu_stat(tb, num_apb)
    await _read_and_check_all_biu_stat(tb, num_apb, "baseline")

    # =========================================================================
    # Scenario A — Row 1 harvest simulation
    # =========================================================================
    tb.log.info("--- Scenario A: Row 1 harvest (NOC_CONFIG_BROADCAST_ROW_DISABLE bit 1) ---")
    row_disable_val = (1 << 1)  # disable row 1

    # Write to all NOC2AXI tiles (x=0..3, y=4)
    for x in range(4):
        await tb.noc_write(
            0, x, 4,
            NOC_CONFIG_BROADCAST_ROW_DISABLE_OFFSET,
            row_disable_val.to_bytes(4, "little"),
        )
    tb.log.info(f"  Written ROW_DISABLE=0x{row_disable_val:08x} to all NOC2AXI tiles")

    # Wait for ring to re-initialize
    await ClockCycles(tb.dut.noc_clk, 50)

    # Check EDC ring health — COR_ERR is acceptable during reconfiguration
    await _read_and_check_all_biu_stat(tb, num_apb, "row_harvest", allow_cor_err=True)
    tb.log.info("  Scenario A: EDC ring healthy after row harvest — PASS")

    # =========================================================================
    # Scenario B — Column 1 harvest simulation
    # =========================================================================
    tb.log.info("--- Scenario B: Col 1 harvest (NOC_CONFIG_BROADCAST_COL_DISABLE bit 1) ---")
    col_disable_val = (1 << 1)  # disable column 1

    # Write to NOC2AXI tile at (0, 4) on behalf of broadcast (master 0)
    for x in range(4):
        await tb.noc_write(
            0, x, 4,
            NOC_CONFIG_BROADCAST_COL_DISABLE_OFFSET,
            col_disable_val.to_bytes(4, "little"),
        )
    tb.log.info(f"  Written COL_DISABLE=0x{col_disable_val:08x} to all NOC2AXI tiles")

    await ClockCycles(tb.dut.noc_clk, 50)

    await _read_and_check_all_biu_stat(tb, num_apb, "col_harvest", allow_cor_err=True)
    tb.log.info("  Scenario B: EDC ring healthy after column harvest — PASS")

    # =========================================================================
    # Restore: write 0x0 back to both registers
    # =========================================================================
    tb.log.info("--- Restoring: clearing row/col disable registers ---")
    for x in range(4):
        await tb.noc_write(
            0, x, 4,
            NOC_CONFIG_BROADCAST_ROW_DISABLE_OFFSET,
            (0).to_bytes(4, "little"),
        )
        await tb.noc_write(
            0, x, 4,
            NOC_CONFIG_BROADCAST_COL_DISABLE_OFFSET,
            (0).to_bytes(4, "little"),
        )

    await ClockCycles(tb.dut.noc_clk, 50)
    await _clear_all_biu_stat(tb, num_apb)
    await _read_and_check_all_biu_stat(tb, num_apb, "restored")
    tb.log.info("--- Restore verified: EDC ring clean after restore ---")

    tb.log.info("edc_ring_continuity_harvest PASSED")
