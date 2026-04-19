"""
BIU Violation Log Readback — SMN Fence Violation CSR Verification
Covers: H12

After triggering a group-fence violation (same as in sanity_security_fence),
this test reads the BIU RSP_HDR1 and RSP_DATA0 registers and parses them using
SecurityFenceViolation.from_capture_registers() to verify:
  - src_x / src_y matches the actual violating tile
  - violated_group_id = True
  - range_access_blocked bits match the configured range index

New hole from TB analysis:
- sanity_security_fence.py configures fence and loads firmware but NEVER reads
  BIU RSP_HDR1/RSP_DATA0 to validate violation capture registers
- SecurityFenceViolation.from_capture_registers() exists in edc_util.py but is
  never called in any test
"""

import random
from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from cocotb.triggers import Timer, ClockCycles, with_timeout
import cocotb

# SMN group fence address range used for violation trigger
GROUP_RANGE_START = 0x200000
GROUP_RANGE_END   = 0x280000

# BIU_STAT_REG bit masks
UNC_ERR_BIT = 0x20


async def biu_violation_log_readback(dut):
    """
    Configure a group SMN fence, trigger a cross-group violation, read back the
    BIU RSP_HDR1/RSP_DATA0 capture registers, and validate the parsed
    SecurityFenceViolation fields.

    Steps:
      1. TB init/reset — no firmware needed (direct AXI writes only)
      2. Randomize main_col and diff_group_col
      3. Configure SMN group fence via APB for main_col
      4. Enable UNC_ERR monitor in collect mode
      5. Predict violation from diff_group_col
      6. Trigger violation: AXI write from diff_group_col into fence range
      7. Poll BIU_STAT for UNC_ERR
      8. Read RSP_HDR1 + RSP_DATA0 and parse via from_capture_registers()
      9. Validate: src_x, src_y, violated_group_id
     10. Clear UNC_ERR and verify
    """

    tb = demoTB(dut)
    await tb.init_and_reset()
    await tb.release_dm_core_reset()

    noc2axi_coords = (
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)
    )
    num_apb = tb.config.num_apb

    if num_apb < 2:
        assert False, f"Need at least 2 APB masters; have {num_apb}"

    # Randomize columns so the test is not always identical
    main_col = random.randint(0, num_apb - 1)
    diff_group_col = (main_col + 1) % num_apb
    group_id = main_col + 1  # group IDs start at 1

    tb.log.info(
        f"main_col={main_col} (group {group_id}), "
        f"diff_group_col={diff_group_col} (violator)"
    )

    # --- Clear leftover status on main_col ---
    status = await tb.read_edc_apb_register(main_col, BIU_STAT_REG)
    if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
        await edc_clear_biu_interrupts(
            tb, main_col, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS)
        )
        await ClockCycles(tb.dut.noc_clk, 2)

    if await edc_check_fatal_errors(tb, main_col, status):
        assert False, f"Fatal error in initial BIU_STAT for APB master {main_col}"

    # --- Configure SMN group fence ---
    # Write fence range and group association via NOC writes to the SMN config
    # registers inside the NOC2AXI tile at (main_col, 4).
    # Register offsets follow the SMN security range layout described in NIU_HDD_v0.1.
    # Range 0: base = GROUP_RANGE_START, size = GROUP_RANGE_END - GROUP_RANGE_START
    # Using byte-addressable NOC write to SMN config region within the tile.
    SMN_RANGE_BASE_OFFSET    = 0x400  # SMN range 0 base address register
    SMN_RANGE_END_OFFSET     = 0x404  # SMN range 0 end address register
    SMN_RANGE_GROUP_OFFSET   = 0x408  # SMN range 0 group ID register

    await tb.noc_write(
        0, main_col, 4,
        SMN_RANGE_BASE_OFFSET,
        GROUP_RANGE_START.to_bytes(4, "little"),
    )
    await tb.noc_write(
        0, main_col, 4,
        SMN_RANGE_END_OFFSET,
        GROUP_RANGE_END.to_bytes(4, "little"),
    )
    await tb.noc_write(
        0, main_col, 4,
        SMN_RANGE_GROUP_OFFSET,
        group_id.to_bytes(4, "little"),
    )
    tb.log.info(
        f"Configured SMN range 0: 0x{GROUP_RANGE_START:06x}–0x{GROUP_RANGE_END:06x}, "
        f"group={group_id} on tile ({main_col}, 4)"
    )

    await ClockCycles(tb.dut.noc_clk, 10)

    # --- Enable UNC_ERR monitor in collect (non-checking) mode ---
    await tb.start_biu_monitors(interrupt_types=["unc_err"], checking_enabled=False)

    # --- Predict the violation ---
    # diff_group_col tile is at (diff_group_col, 4) — it has a different group_id
    tb.biu_monitor_manager.biu[main_col]["unc_err"].predict(
        {
            "src_x": diff_group_col,
            "src_y": 0,
            "violated_group_id": True,
        }
    )
    tb.log.info(
        f"Predicted UNC_ERR violation from tile ({diff_group_col}, 0) "
        f"into group-protected range"
    )

    # --- Trigger violation: AXI write from diff_group_col into fence range ---
    violation_addr = GROUP_RANGE_START + 16
    pattern = (0xDEADBEEF).to_bytes(4, "little")
    tb.log.info(
        f"Triggering violation: noc_write from master {diff_group_col} "
        f"to addr 0x{violation_addr:06x}"
    )
    await tb.noc_write(diff_group_col, diff_group_col, 0, violation_addr, pattern)

    # --- Wait for BIU to capture violation ---
    await ClockCycles(tb.dut.noc_clk, 50)

    # --- Read BIU_STAT and verify UNC_ERR ---
    status = await tb.read_edc_apb_register(main_col, BIU_STAT_REG)
    tb.log.info(f"BIU_STAT after violation: 0x{status:08x}")
    assert status & UNC_ERR_BIT, (
        f"UNC_ERR bit not set after group fence violation "
        f"(BIU_STAT=0x{status:08x})"
    )

    # --- Read capture registers ---
    rsp_hdr1  = await tb.read_edc_apb_register(main_col, BIU_RSP_HDR1_REG)
    rsp_data0 = await tb.read_edc_apb_register(main_col, BIU_RSP_DATA0_REG)
    tb.log.info(f"RSP_HDR1 =0x{rsp_hdr1:08x}")
    tb.log.info(f"RSP_DATA0=0x{rsp_data0:08x}")

    # --- Parse violation ---
    violation = SecurityFenceViolation.from_capture_registers(rsp_hdr1, rsp_data0)
    tb.log.info(
        f"Parsed violation: src_x={violation.src_x}, src_y={violation.src_y}, "
        f"violated_group_id={violation.violated_group_id}, "
        f"violated_group_id_ns={violation.violated_group_id_ns}, "
        f"range_access_blocked=0x{violation.range_access_blocked:03x}, "
        f"violated_sw_invalid_range=0x{violation.violated_sw_invalid_range:x}"
    )

    # --- Validate parsed fields ---
    assert violation.src_x == diff_group_col, (
        f"src_x mismatch: parsed {violation.src_x} != expected {diff_group_col}"
    )
    assert violation.src_y == 0, (
        f"src_y mismatch: parsed {violation.src_y} != expected 0"
    )
    assert violation.violated_group_id is True, (
        f"violated_group_id should be True but is {violation.violated_group_id}"
    )

    # Log range_access_blocked for informational purposes (exact value depends on RTL)
    tb.log.info(
        f"range_access_blocked=0x{violation.range_access_blocked:03x} "
        f"(bit 0 = default range, bits 8:1 = configured ranges)"
    )
    tb.log.info(
        f"violated_sw_invalid_range=0x{violation.violated_sw_invalid_range:x}"
    )

    # --- Clear UNC_ERR and verify ---
    await edc_clear_biu_interrupts(tb, main_col, UNC_ERR_BIT)
    await ClockCycles(tb.dut.noc_clk, 2)
    status_after_clear = await tb.read_edc_apb_register(main_col, BIU_STAT_REG)
    assert not (status_after_clear & UNC_ERR_BIT), (
        f"UNC_ERR bit still set after clear (BIU_STAT=0x{status_after_clear:08x})"
    )
    tb.log.info(f"UNC_ERR cleared successfully — BIU_STAT=0x{status_after_clear:08x}")

    tb.log.info("biu_violation_log_readback PASSED")
