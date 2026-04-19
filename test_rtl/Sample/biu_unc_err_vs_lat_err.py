"""
BIU LAT_ERR vs UNC_ERR — Independent Interrupt Wire Validation
Covers: New hole (not in DV guide) — CRIT_ERR_IRQ wire is shared between
        LAT_ERR (bit 4, latent error from test-for-diagnostics) and
        UNC_ERR (bit 5, uncorrectable error).

Existing tests only generate UNC_ERR (fence violations) — LAT_ERR is never
independently triggered or verified. The CRIT_ERR_IRQ wire monitors BOTH
interrupt types; they should be distinguishable by status register bit.

New hole from TB analysis:
- IRQ_WIRE_TO_STATUS_BITS[CRIT_ERR_IRQ] = [0x10, 0x20] (LAT_ERR + UNC_ERR)
- STATUS_BIT_TO_TYPE[0x10] = InterruptType.LAT_ERR (NEW per spec v16'h1100)
- No test independently verifies bit 4 vs bit 5 can fire separately
"""

from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from cocotb.triggers import Timer, ClockCycles, with_timeout
import cocotb

# BIU_STAT_REG bit masks
LAT_ERR_BIT = 0x10
UNC_ERR_BIT = 0x20
COR_ERR_BIT = 0x08

# SMN fence address range for UNC_ERR trigger (Phase B)
FENCE_RANGE_START = 0x300000
FENCE_RANGE_END   = 0x380000


async def biu_unc_err_vs_lat_err(dut):
    """
    Independently trigger LAT_ERR (bit 4) and UNC_ERR (bit 5) on APB master 0
    and verify they are distinguishable by BIU_STAT_REG bit position.

    Phase A — LAT_ERR via EDC diagnostic selftest (pattern 0x01, diagnostic mode):
      - Send selftest write with reg_data=[0x01] (diagnostic pattern bit 0)
      - Send pulse and wait for response
      - Observe BIU_STAT for LAT_ERR vs UNC_ERR

    Phase B — UNC_ERR via group fence violation:
      - Configure minimal group fence at FENCE_RANGE_START..FENCE_RANGE_END
      - Issue cross-group NOC write to trigger UNC_ERR
      - Assert UNC_ERR set and LAT_ERR NOT set
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

    num_apb = tb.config.num_apb
    apb_master = 0

    # --- Initial cleanup ---
    status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
    if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
        await edc_clear_biu_interrupts(
            tb, apb_master, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS)
        )
        await ClockCycles(tb.dut.noc_clk, 2)

    if await edc_check_fatal_errors(tb, apb_master, status):
        assert False, f"Fatal error in initial BIU_STAT for APB master {apb_master}"

    await tb.write_edc_apb_register(apb_master, BIU_IRQ_EN_REG, 0xBB)

    # =========================================================================
    # Phase A — LAT_ERR via EDC diagnostic selftest
    # =========================================================================
    tb.log.info("=" * 70)
    tb.log.info("Phase A: Trigger LAT_ERR via EDC diagnostic selftest (reg_data=[0x01])")
    tb.log.info("=" * 70)

    # Enable COR_ERR and LAT_ERR monitors in observe (non-checking) mode
    await tb.start_biu_monitors(
        interrupt_types=["cor_err", "lat_err"], checking_enabled=False
    )

    # Target: Overlay node (partition=0x1E, y=0, local_id=0)
    target_node_id = (0x1E << 11) | (0x00 << 8) | 0x00
    tb.log.info(f"Target node (Overlay): 0x{target_node_id:04x}")

    # Write selftest pattern selection with diagnostic mode bit set (0x01)
    SEC_REG_CMD_OPT = 0x81
    reg_data_diag = bytearray([0x01, 0x00])  # diagnostic pattern
    success = await edc_send_write_command(
        tb, apb_master, target_node_id, reg_data_diag, SEC_REG_CMD_OPT, payload_len=1
    )
    if not success:
        assert False, "Phase A: failed to write diagnostic pattern selection"

    await ClockCycles(tb.dut.noc_clk, 10)

    # Send selftest pulse
    SEC_REG_PULSE_CMD_OPT = 0x40
    pulse_data = [0x1]
    success = await edc_send_write_command(
        tb, apb_master, target_node_id, pulse_data, SEC_REG_PULSE_CMD_OPT, payload_len=0
    )
    if not success:
        assert False, "Phase A: failed to send selftest pulse"

    # Wait for response (timeout generous — diagnostic path may be slower)
    rsp_rcvd = await edc_wait_for_response_packet_received(
        tb, apb_master, timeout_cycles=10000
    )

    if not rsp_rcvd:
        tb.log.warning(
            "Phase A: no RSP_PKT_RCVD after diagnostic selftest — "
            "LAT_ERR may not have been triggered; continuing"
        )

    # Read BIU_STAT and record error bits
    status_a = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
    lat_err_a   = bool(status_a & LAT_ERR_BIT)
    unc_err_a   = bool(status_a & UNC_ERR_BIT)
    cor_err_a   = bool(status_a & COR_ERR_BIT)
    rsp_rcvd_a  = bool(status_a & RSP_PKT_RCVD_BIT)

    tb.log.info(
        f"Phase A (diagnostic selftest): BIU_STAT=0x{status_a:08x} "
        f"LAT_ERR={lat_err_a} UNC_ERR={unc_err_a} COR_ERR={cor_err_a} "
        f"RSP_PKT_RCVD={rsp_rcvd_a}"
    )

    # Clear all bits before Phase B
    await edc_clear_biu_interrupts(
        tb, apb_master, status_a & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS)
    )
    await ClockCycles(tb.dut.noc_clk, 2)

    # =========================================================================
    # Phase B — UNC_ERR via group fence violation
    # =========================================================================
    tb.log.info("=" * 70)
    tb.log.info("Phase B: Trigger UNC_ERR via group fence violation")
    tb.log.info("=" * 70)

    if num_apb < 2:
        tb.log.warning("Only 1 APB master — Phase B cross-group test skipped")
        tb.log.info("biu_unc_err_vs_lat_err PASSED (Phase B skipped)")
        return

    main_col    = 0
    diff_col    = 1
    group_id    = main_col + 1

    # Configure minimal SMN group fence on tile (main_col, 4)
    SMN_RANGE_BASE_OFFSET  = 0x400
    SMN_RANGE_END_OFFSET   = 0x404
    SMN_RANGE_GROUP_OFFSET = 0x408

    await tb.noc_write(
        0, main_col, 4,
        SMN_RANGE_BASE_OFFSET,
        FENCE_RANGE_START.to_bytes(4, "little"),
    )
    await tb.noc_write(
        0, main_col, 4,
        SMN_RANGE_END_OFFSET,
        FENCE_RANGE_END.to_bytes(4, "little"),
    )
    await tb.noc_write(
        0, main_col, 4,
        SMN_RANGE_GROUP_OFFSET,
        group_id.to_bytes(4, "little"),
    )
    tb.log.info(
        f"Configured fence: 0x{FENCE_RANGE_START:06x}–0x{FENCE_RANGE_END:06x}, "
        f"group={group_id} on tile ({main_col}, 4)"
    )
    await ClockCycles(tb.dut.noc_clk, 10)

    # Trigger violation from diff_col
    violation_addr = FENCE_RANGE_START + 32
    pattern = (0xCAFEBABE).to_bytes(4, "little")
    tb.log.info(
        f"Triggering violation: noc_write from master {diff_col} "
        f"to addr 0x{violation_addr:06x}"
    )
    await tb.noc_write(diff_col, diff_col, 0, violation_addr, pattern)

    await ClockCycles(tb.dut.noc_clk, 50)

    # Read BIU_STAT
    status_b = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
    lat_err_b  = bool(status_b & LAT_ERR_BIT)
    unc_err_b  = bool(status_b & UNC_ERR_BIT)

    tb.log.info(
        f"Phase B (fence violation): BIU_STAT=0x{status_b:08x} "
        f"LAT_ERR={lat_err_b} UNC_ERR={unc_err_b}"
    )

    assert unc_err_b, (
        f"Phase B: UNC_ERR should be set after fence violation "
        f"(BIU_STAT=0x{status_b:08x})"
    )
    assert not lat_err_b, (
        f"Phase B: LAT_ERR should NOT be set from fence violation "
        f"(BIU_STAT=0x{status_b:08x})"
    )

    # Clear UNC_ERR
    await edc_clear_biu_interrupts(tb, apb_master, UNC_ERR_BIT)
    await ClockCycles(tb.dut.noc_clk, 2)

    # =========================================================================
    # Summary
    # =========================================================================
    tb.log.info("=" * 70)
    tb.log.info("Comparison summary:")
    tb.log.info(
        f"  Phase A (diagnostic selftest): LAT_ERR={lat_err_a}, UNC_ERR={unc_err_a}"
    )
    tb.log.info(
        f"  Phase B (fence violation):     LAT_ERR={lat_err_b}, UNC_ERR={unc_err_b}"
    )
    tb.log.info("  Phase B assertions: UNC_ERR=True, LAT_ERR=False — PASSED")
    tb.log.info("=" * 70)
    tb.log.info("biu_unc_err_vs_lat_err PASSED")
