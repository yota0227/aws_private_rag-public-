from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from tests.utils.noc.noc_fence_reg import *
from tests.utils.noc_driver import NocTransactionConfig
import cocotb
from cocotb.triggers import Timer, with_timeout
import random

# Security fence test constants
L1_BASE_ADDR = 0x0
CONFIG_ADDR = 0x100000  # 1MB - Firmware reads test config from here

# Address ranges for testing
# Range 1: 2MB-2.5MB - Group-based fencing only (no EDC level requirement)
GROUP_RANGE_START = 0x200000  # 2MB
GROUP_RANGE_END = 0x280000    # 2.5MB

# Range 2: 2.5MB-3MB - Security level-based fencing (level >= 5 via EDC)
SECURE_RANGE_START = 0x280000  # 2.5MB
SECURE_RANGE_END = 0x300000    # 3MB

# Specific test addresses for verification (all on tile 0,0)
# Test 1a: Group-based fencing - same group writes (should PASS)
GROUP_FENCE_ADDR_PASSED = GROUP_RANGE_START  # 0x200000 - tile (0,1) writes here

# Test 1b: Group-based fencing - different group tries to write (should BLOCK)
GROUP_FENCE_ADDR_BLOCKED = GROUP_RANGE_START + 16  # 0x200010 - tile (1,0) writes here

# Test 2: Level-based fencing - high privilege (level 8) tries to write
LEVEL_HIGH_ACCESS_ADDR = SECURE_RANGE_START  # 0x280000

# Test 3: Level-based fencing - low privilege (level 3) tries to write
LEVEL_LOW_ACCESS_ADDR = SECURE_RANGE_START + 64  # 0x280040

# Test patterns
PATTERN_SUCCESS = 0x11223344
PATTERN_BLOCKED = 0x12345678


async def sanity_security_fence(dut, bin_path):
    """
    Test security fence feature with both group security and security level filtering.

    Test Configuration (Randomized):
      - main_column: Random column (target tile at row 0)
      - diff_group_column: Random column different from main_column
      - negative_axi_master: Random NOC2AXI master different from main_column

      Target Tile (main_column, 0):
        * Group ID = main_column + 1
        * Range 0 (2MB-2.5MB): Group-based fencing only
        * Range 1 (2.5MB-3MB): Requires security level >= 5 via EDC

      Other Tiles:
        * Each column X has Group ID = X + 1
        * Tile (main_column, 1): master_level = 3 (low privilege)
        * Tile (main_column, 2): master_level = 8 (high privilege)
        * Tile (diff_group_column, 0): Different group from main_column

    Test Stages:
      Stage 1: Group Security (2MB-2.5MB range)
        - Tile (diff_group_column, 0) -> Target: Should FAIL (different group)
        - Tile (main_column, 1) -> Target: Should SUCCEED (same group)

      Stage 2: Security Level (2.5MB-3MB range, requires level >= 5)
        - Tile (main_column, 1) with level 3 -> Target: Should FAIL (level 3 < 5)
        - Tile (main_column, 2) with level 8 -> Target: Should SUCCEED (level 8 >= 5)

      Stage 3: Negative NOC2AXI Scenario
        - NOC2AXI (negative_axi_master, 4) -> Target: Should FAIL (different group)

    Interrupt Validation:
      - All security fence violations generate UNC_ERR interrupts via edc_crit_err_irq
      - Capture registers in RSP_HDR1[15:0] and RSP_DATA0[31:16] contain violation details
      - Test validates source coordinates, violation types, and range information
    """

    # -----------------------------------------------------------------------------------------
    #  Initialize testbench
    # -----------------------------------------------------------------------------------------

    tb = demoTB(dut)
    await tb.init_and_reset()
    tb.log.info("Testbench initialized and DUT reset.")

    if tb.config.num_apb == 0:
        tb.log.error("No EDC APB interfaces available")
        assert False, "EDC APB interface required for security fence configuration"

    apb_master = 0  # Use first EDC APB master
    default_master = tb.default_master

    # -----------------------------------------------------------------------------------------
    #  Randomize test configuration
    # -----------------------------------------------------------------------------------------

    # Get number of available columns
    num_columns = tb.config.num_apb
    if num_columns < 2:
        tb.log.error(f"Need at least 2 columns for this test, got {num_columns}")
        assert False, "Insufficient columns for security fence test"

    # Randomize main column (target tile column)
    main_column = random.randint(0, num_columns - 1)

    # Randomize diff_group_column (different from main_column)
    available_diff_columns = [c for c in range(num_columns) if c != main_column]
    diff_group_column = random.choice(available_diff_columns)

    # Randomize negative_axi_master (different from main_column for BLOCKED access)
    available_axi_masters = [c for c in range(num_columns) if c != main_column]
    negative_axi_master = random.choice(available_axi_masters)

    tb.log.info("=" * 80)
    tb.log.info("RANDOMIZED TEST CONFIGURATION")
    tb.log.info("=" * 80)
    tb.log.info(f"  Main column (target): {main_column}")
    tb.log.info(f"  Diff group column (cross-group source): {diff_group_column}")
    tb.log.info(f"  Negative AXI master (verification): {negative_axi_master}")
    tb.log.info(f"  Total columns available: {num_columns}")
    tb.log.info("=" * 80)

    # -----------------------------------------------------------------------------------------
    #  Enable BIU interrupts for ALL columns
    # -----------------------------------------------------------------------------------------
    tb.log.info("=" * 80)
    tb.log.info(f"Enabling BIU interrupts for all {tb.config.num_apb} APB masters")
    tb.log.info("=" * 80)

    for apb_idx in range(tb.config.num_apb):
        tb.log.info(f"\n[APB Master {apb_idx}] Initializing BIU interrupts")

        # Read initial status register
        status = await tb.read_edc_apb_register(apb_idx, BIU_STAT_REG)
        tb.log.info(f"[APB Master {apb_idx}] Initial Status: 0x{status:08x}")

        # Clear any leftover status bits from previous tests (error packets, etc.)
        if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
            tb.log.info(f"[APB Master {apb_idx}] Clearing leftover status bits: 0x{status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):08x}")
            await edc_clear_biu_interrupts(tb, apb_idx, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS))
            # Wait a cycle for clear to take effect
            await ClockCycles(tb.dut.noc_clk, 1)
            # Re-read status after clear
            status = await tb.read_edc_apb_register(apb_idx, BIU_STAT_REG)
            tb.log.info(f"[APB Master {apb_idx}] Status after clear: 0x{status:08x}")

        # Check for fatal errors in initial status (after clearing leftovers)
        if await edc_check_fatal_errors(tb, apb_idx, status):
            assert False, f"Fatal error detected in initial status - APB master {apb_idx}"

        # Enable all interrupts
        await tb.write_edc_apb_register(apb_idx, BIU_IRQ_EN_REG, 0xBB)

        # Read back interrupt enable register to verify
        irq_en_readback = await tb.read_edc_apb_register(apb_idx, BIU_IRQ_EN_REG)
        tb.log.info(f"[APB Master {apb_idx}] IRQ Enable readback: 0x{irq_en_readback:08x}")

        # Test control register read/write
        # await tb.write_edc_apb_register(apb_idx, BIU_CTRL_REG, 0x1)  # Set INIT bit
        ctrl_readback = await tb.read_edc_apb_register(apb_idx, BIU_CTRL_REG)
        tb.log.info(f"[APB Master {apb_idx}] Control register: 0x{ctrl_readback:08x}")

    tb.log.info("\n" + "=" * 80)
    tb.log.info(f"BIU interrupts enabled for all {tb.config.num_apb} APB masters")
    tb.log.info("=" * 80)
    
    # -----------------------------------------------------------------------------------------
    #  Load binary
    # -----------------------------------------------------------------------------------------

    try:
        binary_data = load_binary_data(bin_path=bin_path)
        tb.log.info(f"Loaded binary from {bin_path} ({len(binary_data)} bytes)")
    except FileNotFoundError:
        tb.log.error(f"Binary not found at {bin_path}.")
        raise

    # Get tile coordinates for all active tiles
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    dispatch_coords = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) + tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    all_active_coords = tensix_coords + dispatch_coords

    # Verify we have the required test tiles (based on randomized columns)
    required_test_tiles = [
        (main_column, 0),  # Target tile
        (main_column, 1),  # Same-group source (low privilege)
        (main_column, 2),  # Same-group source (high privilege)
        (diff_group_column, 0),  # Diff-group source
    ]
    for tile in required_test_tiles:
        if tile not in tensix_coords:
            tb.log.error(f"Required test tile {tile} not found in configuration")
            assert False, f"Missing required test tile {tile}"

    tb.log.info(f"Test tiles: {required_test_tiles}")
    tb.log.info(f"All active tiles (TENSIX + DISPATCH): {len(all_active_coords)}")
    tb.log.info(f"EDC APB interfaces available: {tb.config.num_apb}")

    # -----------------------------------------------------------------------------------------
    #  Write binary to all active tiles
    # -----------------------------------------------------------------------------------------

    tb.log.info(f"Loading binary to all active tiles ({len(all_active_coords)} tiles)...")
    load_binary_tasks = []
    for tile_x, tile_y in all_active_coords:
        tb.log.info(f"Loading binary to tile ({tile_x},{tile_y}) at address 0x{L1_BASE_ADDR:X}")
        load_binary_tasks.append(
            tb.noc_write(default_master, tile_x, tile_y, L1_BASE_ADDR, binary_data)
        )

    # Wait for all binary loading to complete before proceeding
    tb.log.info("Waiting for binary loading to complete...")
    for task in load_binary_tasks:
        await task
    tb.log.info("Binary loading completed for all active tiles.")

    # -----------------------------------------------------------------------------------------
    #  Write test configuration to firmware (all tiles)
    # -----------------------------------------------------------------------------------------

    tb.log.info(f"Writing test configuration to all active tiles at address 0x{CONFIG_ADDR:X}")

    # Prepare config data: [main_column, diff_group_column]
    config_data = bytearray()
    config_data.extend(main_column.to_bytes(4, byteorder='little'))
    config_data.extend(diff_group_column.to_bytes(4, byteorder='little'))

    tb.log.info(f"  Config: main_column={main_column}, diff_group_column={diff_group_column}")

    # Write config to ALL active tiles (each tile needs to know if it should participate)
    config_write_tasks = []
    for tile_x, tile_y in all_active_coords:
        config_write_tasks.append(
            tb.noc_write(default_master, tile_x, tile_y, CONFIG_ADDR, config_data)
        )

    # Wait for all config writes to complete
    tb.log.info("Waiting for config writes to complete...")
    for task in config_write_tasks:
        await task
    tb.log.info(f"Config written to all {len(all_active_coords)} active tiles")

    # -----------------------------------------------------------------------------------------
    #  Configure security fence via EDC
    # -----------------------------------------------------------------------------------------

    # Initialize test memory on tile ({main_column},0) with blocked pattern BEFORE any EDC configuration
    tb.log.info(f"Initializing test memory on tile ({main_column},0) with BLOCKED pattern")

    data = PATTERN_BLOCKED.to_bytes(4, byteorder='little')

    # Test 1a: Group-based fencing - same group writes here (should become SUCCESS)
    await tb.noc_write(default_master, main_column, 0, GROUP_FENCE_ADDR_PASSED, data)

    # Test 1b: Group-based fencing - different group tries to write here (should stay BLOCKED)
    await tb.noc_write(default_master, main_column, 0, GROUP_FENCE_ADDR_BLOCKED, data)

    # Test 2: Level-based fencing - high privilege access address
    await tb.noc_write(default_master, main_column, 0, LEVEL_HIGH_ACCESS_ADDR, data)

    # Test 3: Level-based fencing - low privilege access address
    await tb.noc_write(default_master, main_column, 0, LEVEL_LOW_ACCESS_ADDR, data)

    await ClockCycles(tb.dut.noc_clk, 500)  # Allow writes to complete
    tb.log.info(f"Test memory initialized on tile ({main_column},0)")

    # Enable EDC MUXes before configuration (boot time setup)
    tb.log.info("Enabling EDC MUXes for boot time configuration in parallel")
    enable_tasks = [
        cocotb.start_soon(edc_enable_all_edc_muxes(tb, apb_master)),
        cocotb.start_soon(edc_enable_all_edc_muxes(tb, apb_master + 1)),
        cocotb.start_soon(edc_enable_all_edc_muxes(tb, apb_master + 2)),
        cocotb.start_soon(edc_enable_all_edc_muxes(tb, apb_master + 3))
    ]
    for task in enable_tasks:
        await task

    # -----------------------------------------------------------------------------------------
    # Configure security fence for all tiles, grouped by columns
    # -----------------------------------------------------------------------------------------
    # Each column = one security group
    # Columns are configured in parallel (using different APB masters)
    # Within each column, tiles are configured sequentially (share same APB)
    # -----------------------------------------------------------------------------------------

    tb.log.info("=" * 80)
    tb.log.info("Configuring security fence: 4 columns in parallel")
    tb.log.info("  Column 0 -> Group 1, Column 1 -> Group 2, Column 2 -> Group 3, Column 3 -> Group 4")
    tb.log.info("=" * 80)

    # Define address range for row 0 tiles only (bottom row in each column)
    # Configure SECURE_RANGE (2.5MB-3MB) to require level >= 5
    # GROUP_RANGE (2MB-2.5MB) is NOT configured, uses default group-based fencing
    secure_level_range_config = [
        {'start': SECURE_RANGE_START, 'end': SECURE_RANGE_END, 'wr_level': 5, 'rd_level': 5}
    ]

    # Get all active tiles
    all_tensix = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    all_dispatch_e = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E)
    all_dispatch_w = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    all_active = all_tensix + all_dispatch_e + all_dispatch_w

    # Group tiles by column and sort by y-coordinate
    column_tiles = {}
    for x, y in all_active:
        if x not in column_tiles:
            column_tiles[x] = []
        column_tiles[x].append((x, y))

    # Sort tiles within each column by y-coordinate
    for col_x in column_tiles:
        column_tiles[col_x].sort(key=lambda coord: coord[1])

    tb.log.info(f"Tile distribution across columns:")
    for col_x in sorted(column_tiles.keys()):
        tb.log.info(f"  Column {col_x}: {len(column_tiles[col_x])} tiles "
                   f"-> {column_tiles[col_x]}")

    # -----------------------------------------------------------------------------------------
    # Define async tasks for each column (to be run in parallel)
    # Each column configures its tiles sequentially
    # -----------------------------------------------------------------------------------------

    async def configure_column_0():
        """Configure all tiles in column 0 - Group 1"""
        col_x = 0
        group_id = 1
        apb = apb_master + 0

        tb.log.info(f"[Column {col_x}] Starting configuration (Group {group_id})")

        if col_x not in column_tiles:
            tb.log.warning(f"[Column {col_x}] No tiles to configure")
            return True

        # Configure each tile in column 0 sequentially
        # Tile at row 0 gets ranges, others get different master_levels
        for idx, (tile_x, tile_y) in enumerate(column_tiles[col_x]):
            tb.log.info(f"[Column {col_x}] Configuring tile ({tile_x},{tile_y})")

            # Row 0 (bottom): Configure with secure level range
            if tile_y == 0:
                tb.log.info(f"[Column {col_x}]   -> Row 0: secure range (2.5MB-3MB) enabled, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=secure_level_range_config,  # Only SECURE_RANGE configured
                    enable_fence=True
                )
            # First upper tile: Low privilege (cannot access range)
            elif idx == 1:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=3 (cannot access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=3,  # < 5, cannot access range on row 0
                    ranges_config=None,
                    enable_fence=True
                )
            # Second upper tile: High privilege (can access range)
            elif idx == 2:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8 (can access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,  # >= 5, can access range on row 0
                    ranges_config=None,
                    enable_fence=True
                )
            # Remaining tiles: Medium privilege
            else:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=None,
                    enable_fence=True
                )

            if not success:
                tb.log.error(f"[Column {col_x}] Failed tile ({tile_x},{tile_y})")
                return False
            await ClockCycles(tb.dut.noc_clk, 200)

        tb.log.info(f"[Column {col_x}] All tiles configured successfully")
        return True

    async def configure_column_1():
        """Configure all tiles in column 1 - Group 2"""
        col_x = 1
        group_id = 2
        apb = apb_master + 1

        tb.log.info(f"[Column {col_x}] Starting configuration (Group {group_id})")

        if col_x not in column_tiles:
            tb.log.warning(f"[Column {col_x}] No tiles to configure")
            return True

        # Configure each tile in column 1 sequentially
        for idx, (tile_x, tile_y) in enumerate(column_tiles[col_x]):
            tb.log.info(f"[Column {col_x}] Configuring tile ({tile_x},{tile_y})")

            # Row 0 (bottom): Configure with secure level range
            if tile_y == 0:
                tb.log.info(f"[Column {col_x}]   -> Row 0: secure range (2.5MB-3MB) enabled, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=secure_level_range_config,
                    enable_fence=True
                )
            # First upper tile: Low privilege (cannot access range)
            elif idx == 1:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=3 (cannot access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=3,
                    ranges_config=None,
                    enable_fence=True
                )
            # Second upper tile: High privilege (can access range)
            elif idx == 2:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8 (can access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=None,
                    enable_fence=True
                )
            # Remaining tiles: Medium privilege
            else:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=None,
                    enable_fence=True
                )

            if not success:
                tb.log.error(f"[Column {col_x}] Failed tile ({tile_x},{tile_y})")
                return False
            await ClockCycles(tb.dut.noc_clk, 200)

        tb.log.info(f"[Column {col_x}] All tiles configured successfully")
        return True

    async def configure_column_2():
        """Configure all tiles in column 2 - Group 3"""
        col_x = 2
        group_id = 3
        apb = apb_master + 2

        tb.log.info(f"[Column {col_x}] Starting configuration (Group {group_id})")

        if col_x not in column_tiles:
            tb.log.warning(f"[Column {col_x}] No tiles to configure")
            return True

        # Configure each tile in column 2 sequentially
        for idx, (tile_x, tile_y) in enumerate(column_tiles[col_x]):
            tb.log.info(f"[Column {col_x}] Configuring tile ({tile_x},{tile_y})")

            # Row 0 (bottom): Configure with secure level range
            if tile_y == 0:
                tb.log.info(f"[Column {col_x}]   -> Row 0: secure range (2.5MB-3MB) enabled, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=secure_level_range_config,
                    enable_fence=True
                )
            # First upper tile: Low privilege (cannot access range)
            elif idx == 1:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=3 (cannot access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=3,
                    ranges_config=None,
                    enable_fence=True
                )
            # Second upper tile: High privilege (can access range)
            elif idx == 2:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8 (can access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=None,
                    enable_fence=True
                )
            # Remaining tiles: Medium privilege
            else:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=None,
                    enable_fence=True
                )

            if not success:
                tb.log.error(f"[Column {col_x}] Failed tile ({tile_x},{tile_y})")
                return False
            await ClockCycles(tb.dut.noc_clk, 200)

        tb.log.info(f"[Column {col_x}] All tiles configured successfully")
        return True

    async def configure_column_3():
        """Configure all tiles in column 3 - Group 4"""
        col_x = 3
        group_id = 4
        apb = apb_master + 3

        tb.log.info(f"[Column {col_x}] Starting configuration (Group {group_id})")

        if col_x not in column_tiles:
            tb.log.warning(f"[Column {col_x}] No tiles to configure")
            return True

        # Configure each tile in column 3 sequentially
        for idx, (tile_x, tile_y) in enumerate(column_tiles[col_x]):
            tb.log.info(f"[Column {col_x}] Configuring tile ({tile_x},{tile_y})")

            # Row 0 (bottom): Configure with secure level range
            if tile_y == 0:
                tb.log.info(f"[Column {col_x}]   -> Row 0: secure range (2.5MB-3MB) enabled, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=secure_level_range_config,
                    enable_fence=True
                )
            # First upper tile: Low privilege (cannot access range)
            elif idx == 1:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=3 (cannot access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=3,
                    ranges_config=None,
                    enable_fence=True
                )
            # Second upper tile: High privilege (can access range)
            elif idx == 2:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8 (can access range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=None,
                    enable_fence=True
                )
            # Remaining tiles: Medium privilege
            else:
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=None,
                    enable_fence=True
                )

            if not success:
                tb.log.error(f"[Column {col_x}] Failed tile ({tile_x},{tile_y})")
                return False
            await ClockCycles(tb.dut.noc_clk, 200)

        tb.log.info(f"[Column {col_x}] All tiles configured successfully")
        return True

    # -----------------------------------------------------------------------------------------
    # Start all 4 column configurations in parallel
    # -----------------------------------------------------------------------------------------

    column_config_tasks = [
        cocotb.start_soon(configure_column_0()),
        cocotb.start_soon(configure_column_1()),
        cocotb.start_soon(configure_column_2()),
        cocotb.start_soon(configure_column_3())
    ]

    tb.log.info("Waiting for all column configurations to complete...")

    # Wait for all columns to complete
    column_results = []
    for task in column_config_tasks:
        result = await task
        column_results.append(result)

    # Check if any column failed
    for col_idx, success in enumerate(column_results):
        if not success:
            tb.log.error(f"Column {col_idx} configuration failed!")
            assert False, f"Security fence configuration failed for column {col_idx}"

    tb.log.info("=" * 80)
    tb.log.info("All columns configured successfully!")
    tb.log.info("=" * 80)
    await ClockCycles(tb.dut.noc_clk, 1000)  # Allow configuration to settle

    # Disable EDC MUXes after configuration (return to normal operation)
    tb.log.info("Disabling EDC MUXes after security fence configuration in parallel")
    disable_tasks = [
        cocotb.start_soon(edc_disable_edc_muxes(tb, apb_master,
                                                 harvested_rows=[],
                                                 harvested_columns=[])),
        cocotb.start_soon(edc_disable_edc_muxes(tb, apb_master + 1,
                                                 harvested_rows=[],
                                                 harvested_columns=[])),
        cocotb.start_soon(edc_disable_edc_muxes(tb, apb_master + 2,
                                                 harvested_rows=[],
                                                 harvested_columns=[])),
        cocotb.start_soon(edc_disable_edc_muxes(tb, apb_master + 3,
                                                 harvested_rows=[],
                                                 harvested_columns=[]))
    ]
    for task in disable_tasks:
        await task

    await ClockCycles(tb.dut.noc_clk, 1000)  # Allow MUX disable to settle

    # -----------------------------------------------------------------------------------------
    #  Predict security fence violation interrupts (BEFORE releasing DM core resets)
    # -----------------------------------------------------------------------------------------
    #  Each security violation triggers 2 interrupt types:
    #    1. RSP_PKT_RCVD - response packet received (CMD=0x8)
    #    2. UNC_ERR - uncorrectable error (CMD=0x9)
    #
    #  We have 3 violations, so 6 total predictions needed (3 RSP_PKT_RCVD + 3 UNC_ERR).
    #  SRC_ID is fixed to 0xF010 for this test (targets at bottom row Y=0).
    # -----------------------------------------------------------------------------------------

    tb.log.info("=" * 80)
    tb.log.info("PREDICTING SECURITY FENCE VIOLATION INTERRUPTS")
    tb.log.info("=" * 80)

    # Fixed SRC_ID for security fence violations at the bottom row (Y=0)
    SEC_FENCE_SRC_ID = 0xF010

    # Define expected violations using SecurityFenceViolation dataclass
    # This allows direct comparison between expected and received violations
    expected_violations = [
        SecurityFenceViolation(
            src_x=diff_group_column,
            src_y=0,
            violated_group_id=True,
            name='Checker 1b: Different group access (Tensix)',
            description=f'Tile ({diff_group_column},0) Group {diff_group_column + 1} -> Tile ({main_column},0) Group {main_column + 1}'
        ),
        SecurityFenceViolation(
            src_x=main_column,
            src_y=1,
            range_access_blocked=0x001,  # Expect range 0 (secure range) to be blocked
            name='Checker 3: Low privilege level access',
            description=f'Tile ({main_column},1) Level 3 -> Tile ({main_column},0) SECURE_RANGE (requires Level >= 5)'
        ),
        SecurityFenceViolation(
            src_x=negative_axi_master,
            src_y=4,
            violated_group_id=True,
            name='Negative scenario: Cross-group NOC2AXI access',
            description=f'NOC2AXI ({negative_axi_master},4) Group {negative_axi_master + 1} -> Tile ({main_column},0) Group {main_column + 1}'
        )
    ]

    tb.log.info(f"Target BIU: BIU[{main_column}]")
    tb.log.info(f"SRC_ID: 0x{SEC_FENCE_SRC_ID:04X}")
    tb.log.info(f"Expected {len(expected_violations)} violations x 2 interrupt types = {len(expected_violations) * 2} predictions total")
    for i, v in enumerate(expected_violations):
        tb.log.info(f"  {i+1}. {v.name}: {v}")
        tb.log.info(f"      src_x={v.src_x}, src_y={v.src_y}, group_id={v.violated_group_id}, " +
                    f"range=0x{v.range_access_blocked:03x}, sw_invalid_range=0x{v.violated_sw_invalid_range:01x}")

    # Get monitors for RSP_PKT_RCVD and UNC_ERR
    rsp_pkt_rcvd_monitor = tb.biu_monitor_manager.biu[main_column]['rsp_pkt_rcvd']
    unc_err_monitor = tb.biu_monitor_manager.biu[main_column]['unc_err']

    # Make predictions for each expected violation
    for i, v in enumerate(expected_violations):
        # RSP_PKT_RCVD prediction (CMD=0x8)
        # IMPORTANT: auto_clear=False so user can read capture registers before clearing
        rsp_pkt_rcvd_monitor.predict(
            InterruptType.RSP_PKT_RCVD,
            {
                'expected_cmd': 0x9,  # BIU sets CMD to 0x8 for response packets
                'expected_src_id': SEC_FENCE_SRC_ID,
                'expected_violation': v,  # Include the expected violation object for matching
                'description': f'{v.name} RSP_PKT_RCVD',
            },
            auto_clear=False  # Manual clear - capture registers contain violation data
        )
        # UNC_ERR prediction (CMD=0x9)
        unc_err_monitor.predict(
            InterruptType.UNC_ERR,
            {
                'expected_cmd': 0x9,  # UNC_EVENT
                'expected_src_id': SEC_FENCE_SRC_ID,
                'expected_violation': v,  # Include the expected violation object for matching
                'description': f'{v.name} UNC_ERR',
            }
        )
    tb.log.info(f"Predicted {len(expected_violations)}x RSP_PKT_RCVD + {len(expected_violations)}x UNC_ERR interrupts")

    tb.log.info("=" * 80)
    tb.log.info(f"All {len(expected_violations) * 2} interrupt predictions added to BIU monitor")
    tb.log.info("=" * 80)

    # -----------------------------------------------------------------------------------------
    #  Define parallel tasks for firmware monitoring and interrupt handling
    # -----------------------------------------------------------------------------------------

    # Shared state for violation tracking (accessible from both tasks)
    violation_results = {
        'received': [],           # List of received violations
        'matched': set(),         # Set of matched expected violation indices
        'mismatches': [],         # List of mismatch error messages
        'timeouts': 0,            # Count of timeout errors
    }

    async def wait_for_firmware_and_negative_scenario():
        """
        Wait for firmware execution, then run the negative NOC2AXI scenario.

        This is one parallel thread that:
        1. Waits for firmware to complete on all tiles (generates 2 violations)
        2. Then runs negative NOC2AXI scenario (generates 3rd violation)

        The interrupt handling task runs in parallel and catches all 3 violations.
        """
        # Step 1: Wait for firmware to complete on all active tiles
        waiters = []
        for x, y in all_active_coords:
            waiters.append(cocotb.start_soon(tb.monitor_dm_scratch(x, y)))

        # Wait for all tiles to complete
        while waiters:
            await with_timeout(waiters.pop(0), 10_000, "ns")

        tb.log.info("[FIRMWARE] Execution completed on all tiles")

        # Step 2: Run negative NOC2AXI scenario (generates 3rd interrupt)
        tb.log.info("\n" + "=" * 80)
        tb.log.info("NEGATIVE SCENARIO: Cross-Group NOC2AXI Access (generates 3rd interrupt)")
        tb.log.info("=" * 80)
        tb.log.info(f"Testing that a different group cannot access tile ({main_column},0)")
        tb.log.info("")

        # Use randomized NOC2AXI master from different column (!= main_column)
        # Configure with group_id matching the AXI master's column and high privilege level=9
        cross_group_master = negative_axi_master
        cross_group_group_id = negative_axi_master + 1  # Column X -> Group X+1
        cross_group_config = NocTransactionConfig(sec_level=9, group_id=cross_group_group_id)

        main_column_group_id = main_column + 1  # Column X -> Group X+1

        tb.log.info(f"Using NOC2AXI master {cross_group_master} (Column {cross_group_master})")
        tb.log.info(f"  AXI user bits = 0x{cross_group_config.get_user_bits():02x} "
                    f"(group_id={cross_group_group_id}, sec_level=9)")
        tb.log.info(f"  Attempting to read from tile ({main_column},0) which is in Group {main_column_group_id}")
        tb.log.info(f"  Expected: Access BLOCKED, read data = 0xDEADBEEF")
        tb.log.info("")

        # Try to read from tile (main_column,0) - should be blocked by group fence
        # Reading from GROUP_RANGE address (2MB-2.5MB) - try the PASSED address
        try:
            read_data = await tb.noc_read(cross_group_master, main_column, 0, GROUP_FENCE_ADDR_PASSED, 4,
                                           config=cross_group_config)
            result = int.from_bytes(read_data, byteorder='little')

            if result == 0xDEADBEEF:
                tb.log.info(f"PASS: Cross-group access blocked correctly")
                tb.log.info(f"      Read data = 0x{result:08x} (error response as expected)")
            else:
                tb.log.error(f"FAIL: Cross-group access returned 0x{result:08x}, expected 0xDEADBEEF")
                tb.log.error(f"      Group {cross_group_group_id} should not be able to read from Group {main_column_group_id}'s tile")
        except Exception as e:
            tb.log.info(f"PASS: Cross-group access raised exception (also acceptable): {e}")

        tb.log.info("")
        tb.log.info("[NEGATIVE SCENARIO] Completed - 3rd interrupt generated")
        return True

    async def wait_for_interrupts_and_validate():
        """
        Wait for 3 security fence violation interrupts and validate each immediately.

        Security fence violations trigger UNC_ERR (uncorrectable errors) that:
        - Use the edc_crit_err_irq signal
        - Set UNC_ERR bit (0x20, bit 5) in BIU_STAT_REG
        - We use edc_wait_for_unc_err() which monitors edc_crit_err_irq signal
        - We clear UNC_ERR_BIT (0x20) to acknowledge the interrupt

        Capture register format:
          capture_reg_0[15:0] = RSP_DATA0[15:0]:
            [8:0]  = range_access_blocked
            [14:9] = SRC_X (6 bits)
          capture_reg_1[15:0] = RSP_DATA0[31:16]:
            [5:0]  = SRC_Y (6 bits)
            [9:6]  = VIOLATED_SW_INVALID_RANGE (4 bits)
            [10]   = VIOLATED_GROUP_ID
            [11]   = VIOLATED_GROUP_ID_NS
        """
        tb.log.info("[INTERRUPT] Waiting for 3 security fence violations...")

        for i in range(len(expected_violations)):
            tb.log.info(f"[INTERRUPT] Waiting for security fence violation #{i+1} (via edc_crit_err_irq)...")

            success, interrupt = await edc_wait_for_unc_err(
                tb, main_column, timeout_cycles=10_000
            )

            if not success:
                tb.log.error(f"[INTERRUPT] TIMEOUT waiting for violation #{i+1}")
                tb.log.error("[INTERRUPT] Breaking simulation - first timeout is fatal")
                assert False, f"Timeout waiting for security fence violation #{i+1} - expected {len(expected_violations)} violations"

            tb.log.info(f"[INTERRUPT] Security fence violation #{i+1} interrupt received!")

            # Read capture registers
            rsp_hdr0 = await tb.read_edc_apb_register(
                main_column, BIU_RSP_HDR0_REG)
            rsp_hdr1 = await tb.read_edc_apb_register(
                main_column, BIU_RSP_HDR1_REG)
            rsp_data0 = await tb.read_edc_apb_register(
                main_column, BIU_RSP_DATA0_REG)
            rsp_data1 = await tb.read_edc_apb_register(
                main_column, BIU_RSP_DATA1_REG)

            tb.log.info(f"  RSP_HDR0:  0x{rsp_hdr0:08x}")
            tb.log.info(f"  RSP_HDR1:  0x{rsp_hdr1:08x} (SRC_ID=0x{rsp_hdr1 >> 16:04x}, capture_reg_0=0x{rsp_hdr1 & 0xFFFF:04x})")
            tb.log.info(f"  RSP_DATA0: 0x{rsp_data0:08x} (capture_reg_1=0x{rsp_data0 >> 16:04x})")
            tb.log.info(f"  RSP_DATA1: 0x{rsp_data1:08x}")

            # Parse violation from capture registers
            # capture_reg_0 is in RSP_HDR1[15:0], capture_reg_1 is in RSP_DATA0[31:16]
            received = SecurityFenceViolation.from_capture_registers(
                rsp_hdr1, rsp_data0
            )
            tb.log.info(f"  Parsed: {received}")
            tb.log.info(received.print())

            violation_results['received'].append(received)

            # Immediately try to match against expected violations
            matched = False
            for exp_idx, expected in enumerate(expected_violations):
                if exp_idx in violation_results['matched']:
                    continue  # Already matched

                if expected.matches(received, check_source=True):
                    tb.log.info(f"  [MATCH] {expected.name}")
                    violation_results['matched'].add(exp_idx)
                    matched = True
                    break

            if not matched:
                msg = f"Received violation not matched: {received}"
                tb.log.warning(f"  [NO MATCH] {msg}")
                violation_results['mismatches'].append(msg)

            # Clear both UNC_ERR and RSP_PKT_RCVD (security fence violations trigger both)
            # UNC_ERR uses edc_crit_err_irq signal and sets bit 5 (0x20)
            # RSP_PKT_RCVD sets bit 1 (0x02) - contains capture register data
            await edc_clear_biu_interrupts(tb, main_column, UNC_ERR_BIT | RSP_PKT_RCVD_BIT)
            tb.log.info("  Cleared UNC_ERR and RSP_PKT_RCVD interrupts")

            await ClockCycles(tb.dut.noc_clk, 100)

        tb.log.info(f"[INTERRUPT] Done - received {len(violation_results['received'])} violations")
        return True

    # -----------------------------------------------------------------------------------------
    #  Release DM core reset and start parallel tasks
    # -----------------------------------------------------------------------------------------

    tb.log.info("=" * 80)
    tb.log.info("Starting firmware and interrupt monitoring in PARALLEL")
    tb.log.info("=" * 80)

    # Release DM core reset
    await tb.release_dm_core_reset()
    tb.log.info("DM core reset released for all tiles.")

    # Launch both tasks concurrently:
    # - Thread 1: Firmware monitoring + negative NOC2AXI scenario (sequential)
    # - Thread 2: Interrupt handling (collects all 3 violations)
    firmware_and_negative_task = cocotb.start_soon(wait_for_firmware_and_negative_scenario())
    interrupt_task = cocotb.start_soon(wait_for_interrupts_and_validate())

    # Wait for both tasks to complete
    await firmware_and_negative_task
    tb.log.info("Firmware and negative scenario completed.")

    await interrupt_task
    tb.log.info("Interrupt handling completed.")

    # -----------------------------------------------------------------------------------------
    #  Report violation validation results
    # -----------------------------------------------------------------------------------------

    tb.log.info("=" * 80)
    tb.log.info("VIOLATION VALIDATION SUMMARY")
    tb.log.info("=" * 80)

    num_expected = len(expected_violations)
    num_matched = len(violation_results['matched'])
    num_received = len(violation_results['received'])
    num_timeouts = violation_results['timeouts']

    tb.log.info(f"Expected violations: {num_expected}")
    tb.log.info(f"Received violations: {num_received}")
    tb.log.info(f"Matched violations:  {num_matched}/{num_expected}")
    tb.log.info(f"Timeouts:            {num_timeouts}")

    # Report which expected violations were matched
    for exp_idx, expected in enumerate(expected_violations):
        status = "MATCHED" if exp_idx in violation_results['matched'] else "MISSING"
        tb.log.info(f"  [{status}] {expected.name}")

    # Report any mismatches
    if violation_results['mismatches']:
        tb.log.error("Unmatched received violations:")
        for msg in violation_results['mismatches']:
            tb.log.error(f"  {msg}")

    violations_valid = (num_matched == num_expected and num_timeouts == 0 and len(violation_results['mismatches']) == 0)
    if violations_valid:
        tb.log.info("ALL VIOLATIONS VALIDATED SUCCESSFULLY")
    else:
        tb.log.error("VIOLATION VALIDATION FAILED")
        tb.log.error(f"  Expected {num_expected} violations, matched {num_matched}, timeouts {num_timeouts}, mismatches {len(violation_results['mismatches'])}")
        assert False, f"Violation validation failed: {num_matched}/{num_expected} matched, {num_timeouts} timeouts, {len(violation_results['mismatches'])} mismatches"

    tb.log.info("=" * 80)

    # -----------------------------------------------------------------------------------------
    #  Verify results
    # -----------------------------------------------------------------------------------------

    tb.log.info("=" * 80)
    tb.log.info("VERIFYING TEST RESULTS")
    tb.log.info("=" * 80)

    # Configure AXI user bits for verification reads
    # Use group_id matching main_column's group, sec_level=9 to ensure high privilege access
    # Column X has group X+1
    verify_group_id = main_column + 1
    verify_config = NocTransactionConfig(sec_level=9, group_id=verify_group_id)
    tb.log.info(f"Verification: Using AXI user bits = 0x{verify_config.get_user_bits():02x} "
                f"(group_id={verify_group_id}, sec_level=9) - Reading from tile ({main_column},0)\n")

    all_checkers_passed = True

    # -------------------------------------------------------------------------
    # Checker 1: Group-based Fencing (2 sub-checkers)
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("Checker 1: Group-Based Fencing (2MB-2.5MB range)")
    tb.log.info("-" * 80)

    # Checker 1a: Same group access (tile (main_column,1) writing to tile (main_column,0))
    tb.log.info(f"Checker 1a: Same group (Group {verify_group_id}) access - Should PASS")
    read_data = await tb.noc_read(default_master, main_column, 0, GROUP_FENCE_ADDR_PASSED, 4,
                                   config=verify_config)
    result = int.from_bytes(read_data, byteorder='little')
    expected = PATTERN_SUCCESS  # Should be SUCCESS (same group can write)

    if result == expected:
        tb.log.info(f"  PASS: Same group access: 0x{result:08x} (SUCCESS as expected)")
        tb.log.info(f"        Tile ({main_column},1) Group {verify_group_id} correctly wrote to tile ({main_column},0) Group {verify_group_id}")
    else:
        tb.log.error(f"  FAIL: Same group access: 0x{result:08x}, expected 0x{expected:08x}")
        tb.log.error(f"        Tile ({main_column},1) Group {verify_group_id} should be able to write to tile ({main_column},0) Group {verify_group_id}")
        all_checkers_passed = False

    # Checker 1b: Different group access (tile (diff_group_column,0) writing to tile (main_column,0))
    diff_group_id = diff_group_column + 1
    tb.log.info(f"Checker 1b: Different group (Group {diff_group_id} -> Group {verify_group_id}) access - Should BLOCK")
    read_data = await tb.noc_read(default_master, main_column, 0, GROUP_FENCE_ADDR_BLOCKED, 4,
                                   config=verify_config)
    result = int.from_bytes(read_data, byteorder='little')
    expected = PATTERN_BLOCKED  # Should stay BLOCKED (different group cannot write)

    if result == expected:
        tb.log.info(f"  PASS: Different group access: 0x{result:08x} (BLOCKED as expected)")
        tb.log.info(f"        Tile ({diff_group_column},0) Group {diff_group_id} correctly blocked from tile ({main_column},0) Group {verify_group_id}")
    else:
        tb.log.error(f"  FAIL: Different group access: 0x{result:08x}, expected 0x{expected:08x}")
        tb.log.error(f"        Tile ({diff_group_column},0) Group {diff_group_id} should not be able to write to tile ({main_column},0) Group {verify_group_id}")
        all_checkers_passed = False

    # -------------------------------------------------------------------------
    # Checker 2: Level-Based Fencing - High Privilege Access
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("Checker 2: Level-Based Fencing - High Privilege (2.5MB-3MB range)")
    tb.log.info(f"  Tile ({main_column},2) with Level 8 writes to tile ({main_column},0) SECURE_RANGE - Should PASS")
    tb.log.info("-" * 80)

    # Tile (main_column,2) from same group with high privilege (level 8 >= 5) tried to write here
    # Should SUCCEED because level 8 >= 5 (secure range requirement)
    read_data = await tb.noc_read(default_master, main_column, 0, LEVEL_HIGH_ACCESS_ADDR, 4,
                                   config=verify_config)
    result = int.from_bytes(read_data, byteorder='little')
    expected = PATTERN_SUCCESS  # Should be SUCCESS (level 8 >= 5)

    if result == expected:
        tb.log.info(f"  PASS: High privilege access: 0x{result:08x} (SUCCESS as expected)")
        tb.log.info(f"        Tile ({main_column},2) Level 8 correctly accessed secure range (level >= 5)")
    else:
        tb.log.error(f"  FAIL: High privilege access: 0x{result:08x}, expected 0x{expected:08x}")
        tb.log.error(f"        Tile ({main_column},2) Level 8 should be able to access secure range")
        all_checkers_passed = False

    # -------------------------------------------------------------------------
    # Checker 3: Level-Based Fencing - Low Privilege Access
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("Checker 3: Level-Based Fencing - Low Privilege (2.5MB-3MB range)")
    tb.log.info(f"  Tile ({main_column},1) with Level 3 writes to tile ({main_column},0) SECURE_RANGE - Should BLOCK")
    tb.log.info("-" * 80)

    # Tile (main_column,1) from same group with low privilege (level 3 < 5) tried to write here
    # Should be BLOCKED because level 3 < 5 (secure range requirement)
    read_data = await tb.noc_read(default_master, main_column, 0, LEVEL_LOW_ACCESS_ADDR, 4,
                                   config=verify_config)
    result = int.from_bytes(read_data, byteorder='little')
    expected = PATTERN_BLOCKED  # Should stay BLOCKED (level 3 < 5)

    if result == expected:
        tb.log.info(f"  PASS: Low privilege access: 0x{result:08x} (BLOCKED as expected)")
        tb.log.info(f"        Tile ({main_column},1) Level 3 correctly blocked from secure range (level < 5)")
    else:
        tb.log.error(f"  FAIL: Low privilege access: 0x{result:08x}, expected 0x{expected:08x}")
        tb.log.error(f"        Tile ({main_column},1) Level 3 should not be able to access secure range")
        all_checkers_passed = False

    # -------------------------------------------------------------------------
    # Final Check: Verify All Checkers Passed
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("FINAL VALIDATION: CHECKER RESULTS")
    tb.log.info("=" * 80)

    if all_checkers_passed:
        tb.log.info("ALL CHECKERS PASSED")
    else:
        tb.log.error("SOME CHECKERS FAILED")
        tb.log.error("Review the checker results above for details")
        assert False, "Security fence checker failures detected"

    tb.log.info("=" * 80)
    tb.log.info("Security Fence Sanity Test Completed Successfully.")
