"""
Trinity FDS Sanity Test

This test validates the Fast Dispatch System (FDS) on Trinity's 4x5 grid.
Ported from Quasar's fds_sanity test.

Test Overview:
- Loads self-contained fds_sanity firmware to all data movement tiles
- Firmware autonomously exercises FDS functionality:
  * Auto-dispatch configuration
  * Interrupt-driven threshold detection
  * Subgrid communication between dispatch and Tensix NEO tiles
- Python test simply monitors postcodes for pass/fail

Requirements:
- Must run with harvesting DISABLED to preserve grid layout
- Trinity grid: 4 columns x 5 rows
- Data movement tiles: Dispatch at (0,3) and (3,3), Tensix NEO at ([0:3], [0:2])

Grid Layout:
  Row 4: [NOC2AXI] [NOC2AXI] [NOC2AXI] [NOC2AXI]
  Row 3: [DISP_0 ] [ROUTER ] [ROUTER ] [DISP_1 ]
  Row 2: [T2/SUB0] [T5/SUB1] [T8/SUB2] [T11/SUB3]
  Row 1: [T1/SUB0] [T4/SUB1] [T7/SUB2] [T10/SUB3]
  Row 0: [T0/SUB0] [T3/SUB1] [T6/SUB2] [T9 /SUB3]
"""

import os
from cocotb.triggers import ClockCycles, with_timeout
from tests.utils.test_utils import load_binary_data, find_largest_rectangle
from tests.utils.coco_tensix_api import demoTB
from tests.utils.tensix_config import TileType


async def sanity_fds(dut, bin_path):
    """
    Trinity FDS Sanity Test

    Self-contained firmware test that validates FDS functionality:
    1. Load firmware to all data movement (DM) tiles
    2. Release DM core reset
    3. Wait for firmware completion via postcodes
    4. Verify pass/fail status

    The firmware handles all test logic internally, including:
    - Interrupt setup and handling (PLIC)
    - Auto-dispatch configuration
    - Subgrid communication and acknowledgment

    Args:
        dut: Device under test
        bin_path: Path to the fds_sanity.bin firmware binary
    """

    # Load firmware binary
    if not os.path.exists(bin_path):
        raise FileNotFoundError(
            f"FDS sanity firmware not found: {bin_path}\n"
            f"Build it first with: cd firmware/data_movement && make TARGET=fds_sanity"
        )

    binary_data = load_binary_data(bin_path=bin_path, pad_to=16)

    # Initialize testbench
    tb = demoTB(dut)
    await tb.init_and_reset()

    # Get all data movement tile coordinates
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    dispatch_coords = (tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) +
                      tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W))

    dm_coords = tensix_coords + dispatch_coords

    tb.log.info("=" * 80)
    tb.log.info("Trinity FDS Sanity Test")
    tb.log.info("=" * 80)
    tb.log.info(f"Tensix NEO tiles: {tensix_coords}")
    tb.log.info(f"Dispatch tiles:   {dispatch_coords}")
    tb.log.info(f"Total DM tiles:   {len(dm_coords)}")
    tb.log.info(f"Firmware size:    {len(binary_data)} bytes")
    tb.log.info("=" * 80)

    # Validate grid configuration
    expected_tensix = 12  # 4 columns x 3 rows
    expected_dispatch = 2  # 2 dispatch engines
    if len(tensix_coords) != expected_tensix:
        tb.log.error(f"ERROR: Expected {expected_tensix} Tensix tiles, found {len(tensix_coords)}")
        tb.log.error("This test requires harvesting to be DISABLED")
        assert False, f"Invalid Tensix count: {len(tensix_coords)} (expected {expected_tensix})"

    if len(dispatch_coords) != expected_dispatch:
        tb.log.error(f"ERROR: Expected {expected_dispatch} Dispatch tiles, found {len(dispatch_coords)}")
        assert False, f"Invalid Dispatch count: {len(dispatch_coords)} (expected {expected_dispatch})"

    # Verify expected dispatch locations
    expected_dispatch_locs = [(0, 3), (3, 3)]
    for expected_loc in expected_dispatch_locs:
        if expected_loc not in dispatch_coords:
            tb.log.error(f"ERROR: Expected dispatch at {expected_loc}, not found")
            assert False, f"Missing expected dispatch location: {expected_loc}"

    tb.log.info("Grid configuration validated successfully")

    # Load firmware to all data movement tiles
    master = 0

    # Load to Tensix tiles (using multicast for efficiency)
    rect = find_largest_rectangle(tensix_coords)
    tb.log.info(f"Loading firmware to Tensix rectangle: {rect}")
    await tb.noc_multicast(master, rect[0], rect[1], rect[2], rect[3], 0x0, binary_data)

    # Load to Dispatch tiles in parallel using nonblocking writes
    tb.log.info("Loading firmware to Dispatch tiles (nonblocking)...")
    for coord in dispatch_coords:
        tb.log.info(f"  Queueing load to Dispatch {coord}")
        tb.noc_write_nonblocking(master, coord[0], coord[1], 0x0, binary_data)

    # Wait for all dispatch tile writes to complete
    tb.log.info("Waiting for all firmware writes to complete...")
    await tb.noc_wait_writes(master)
    tb.log.info("Firmware loaded to all DM tiles")

    # Release data movement core reset to start execution
    tb.log.info("Releasing DM core reset - firmware execution starting...")
    await tb.release_dm_core_reset()

    # Wait a few cycles for execution to begin
    await ClockCycles(tb.dut.noc_clk, 100)

    # Monitor postcodes for completion using common monitoring function
    # This monitors all 8 harts on all DM tiles and checks for pass/fail postcodes
    tb.log.info("=" * 80)
    tb.log.info("Monitoring firmware execution (all harts on all DM tiles)...")
    tb.log.info("=" * 80)

    # monitor_binary_status() will automatically monitor all tiles and return when all pass
    # It will assert if any tile fails
    # Use timeout to prevent hanging - FDS test needs more time due to:
    # - Auto-dispatch cycle count (1500 cycles)
    # - Interrupt handling and PLIC communication
    # - Multiple subgrids with ACK sequences
    timeout_ns = 10_000  # 50 microseconds simulation time
    try:
        await with_timeout(tb.monitor_binary_status(), timeout_ns, "ns")
    except Exception:
        tb.log.error("=" * 80)
        tb.log.error(f"FDS Sanity Test TIMEOUT after {timeout_ns} ns")
        tb.log.error("=" * 80)
        tb.log.error("This could indicate:")
        tb.log.error("  1. FDS communication failure (dispatch <-> tensix)")
        tb.log.error("  2. Interrupt/PLIC configuration issue")
        tb.log.error("  3. Firmware stuck in polling loop")
        tb.log.error("  4. Auto-dispatch not triggering")
        raise

    tb.log.info("=" * 80)
    tb.log.info("Trinity FDS Sanity Test COMPLETED SUCCESSFULLY")
    tb.log.info("=" * 80)
