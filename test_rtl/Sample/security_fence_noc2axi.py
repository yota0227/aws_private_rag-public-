from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from tests.utils.noc.noc_fence_reg import *
from tests.utils.noc_driver import NocTransactionConfig
import cocotb
from cocotb.triggers import Timer, with_timeout, ClockCycles
import random

# Security fence test constants
L1_BASE_ADDR = 0x0
CONFIG_ADDR = 0x100000  # 1MB - Firmware reads test config from here

# Address ranges for testing on NOC2AXI (AXI SRAM)
# Range 1: 2MB-2.5MB - Group-based fencing only (no EDC level requirement)
GROUP_RANGE_START = 0x200000  # 2MB
GROUP_RANGE_END = 0x280000    # 2.5MB

# Range 2: 2.5MB-3MB - Security level-based fencing (level >= 5 via EDC)
SECURE_RANGE_START = 0x280000  # 2.5MB
SECURE_RANGE_END = 0x300000    # 3MB

# Offsets for blocked scenarios
OFFSET_GROUP_BLOCKED = 16
OFFSET_LEVEL_BLOCKED = 64

# Specific test addresses for verification on NOC2AXI
# Scenario 1: Same group, high privilege -> GROUP_RANGE (should PASS)
SRAM_ADDR_GROUP_PASS = GROUP_RANGE_START  # 0x200000

# Scenario 2: Different group -> GROUP_RANGE (should BLOCK)
SRAM_ADDR_GROUP_BLOCKED = GROUP_RANGE_START + OFFSET_GROUP_BLOCKED  # 0x200010

# Scenario 3: Same group, high privilege -> SECURE_RANGE (should PASS)
SRAM_ADDR_LEVEL_PASS = SECURE_RANGE_START  # 0x280000

# Scenario 4: Same group, low privilege -> SECURE_RANGE (should BLOCK)
SRAM_ADDR_LEVEL_BLOCKED = SECURE_RANGE_START + OFFSET_LEVEL_BLOCKED  # 0x280040

# Test patterns
PATTERN_SUCCESS = 0x11223344
PATTERN_BLOCKED = 0x12345678
PATTERN_L1_PRELOAD = 0xCAFEBABE  # Pre-initialize L1 read-back addresses to detect if read never arrived

# L1 addresses for read-back verification (on source tiles)
# Using 0x20100 range to avoid overlap with staging addresses (0x20000-0x20040)
L1_READBACK_GROUP_PASS = 0x20100   # Tile (main_col, 2) - read-back from GROUP_RANGE
L1_READBACK_LEVEL_PASS = 0x20110   # Tile (main_col, 2) - read-back from SECURE_RANGE
L1_READBACK_GROUP_BLOCKED = 0x20100  # Tile (diff_group_col, 2) - should have BLOCKED pattern
L1_READBACK_LEVEL_BLOCKED = 0x20100  # Tile (main_col, blocked_level_row) - should have BLOCKED pattern


async def security_fence_noc2axi(dut, bin_path):
    """
    Test security fence feature on NOC2AXI with both group security and security level filtering.

    Test Configuration:
      - NOC2AXI tiles (row 4): Each column has a NOC2AXI tile with security fence configured
        * Main column NOC2AXI: Group ID = main_column+1, with secure range configured
      - Tensix tiles: Source tiles that attempt to access NOC2AXI
        * Tile (main_col,2): Same group, high privilege (level 8)
        * Tile (main_col,blocked_level_row): Same group, low privilege (level 3)
        * Tile (diff_col,2): Different group, high privilege

    Test Scenarios (all done in firmware with write + read-back):
      Scenario 1: Tile (main_col,2) -> NOC2AXI GROUP_RANGE: Should SUCCEED (same group)
      Scenario 2: Tile (diff_col,2) -> NOC2AXI GROUP_RANGE: Should BLOCK (different group)
      Scenario 3: Tile (main_col,2) -> NOC2AXI SECURE_RANGE: Should SUCCEED (level 8 >= 5)
      Scenario 4: Tile (main_col,blocked_level_row) -> NOC2AXI SECURE_RANGE: Should BLOCK (level 3 < 5)

    Verification:
      - SRAM backdoor: Check what was actually written to SRAM
      - L1 NOC read: Check what each tile read back from SRAM
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
    #  Get NOC2AXI coordinates
    # -----------------------------------------------------------------------------------------

    noc2axi_coords = (tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT) +
                      tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT) +
                      tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT))

    if len(noc2axi_coords) == 0:
        tb.log.error("No NOC2AXI tiles found in configuration")
        assert False, "NOC2AXI tiles required for this test"

    # Sort by X coordinate to get columns
    noc2axi_coords.sort(key=lambda c: c[0])
    tb.log.info(f"NOC2AXI coordinates: {noc2axi_coords}")

    # -----------------------------------------------------------------------------------------
    #  Randomize test configuration
    # -----------------------------------------------------------------------------------------

    # Get number of available columns
    num_columns = tb.config.num_apb
    if num_columns < 2:
        tb.log.error(f"Need at least 2 columns for this test, got {num_columns}")
        assert False, "Insufficient columns for security fence test"

    # Randomize main column (target NOC2AXI tile column)
    main_column = random.randint(0, num_columns - 1)

    # Randomize diff_group_column (different from main_column)
    available_diff_columns = [c for c in range(num_columns) if c != main_column]
    diff_group_column = random.choice(available_diff_columns)

    # Randomize blocked_level_tile row (row 1 - low privilege in same column)
    blocked_level_row = 1

    # Get the NOC2AXI tile for the main column
    target_noc2axi = None
    for x, y in noc2axi_coords:
        if x == main_column:
            target_noc2axi = (x, y)
            break

    if target_noc2axi is None:
        tb.log.error(f"No NOC2AXI tile found in column {main_column}")
        assert False, f"NOC2AXI tile required in column {main_column}"

    target_noc2axi_x, target_noc2axi_y = target_noc2axi

    tb.log.info("=" * 80)
    tb.log.info("RANDOMIZED TEST CONFIGURATION")
    tb.log.info("=" * 80)
    tb.log.info(f"  Main column (target NOC2AXI): {main_column}")
    tb.log.info(f"  Target NOC2AXI tile: ({target_noc2axi_x}, {target_noc2axi_y})")
    tb.log.info(f"  Diff group column (cross-group source): {diff_group_column}")
    tb.log.info(f"  Blocked level row (low privilege): {blocked_level_row}")
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
    # Source tiles at row 2 (high privilege) and row 1 (low privilege)
    required_test_tiles = [
        (main_column, blocked_level_row),  # Same-group source (low privilege)
        (main_column, 2),  # Same-group source (high privilege)
        (diff_group_column, 2),  # Diff-group source (high privilege)
    ]
    for tile in required_test_tiles:
        if tile not in tensix_coords:
            tb.log.error(f"Required test tile {tile} not found in configuration")
            assert False, f"Missing required test tile {tile}"

    tb.log.info(f"Test tiles (sources): {required_test_tiles}")
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

    # Prepare config data: [main_column, diff_group_column, target_noc2axi_x, target_noc2axi_y, blocked_level_row]
    config_data = bytearray()
    config_data.extend(main_column.to_bytes(4, byteorder='little'))
    config_data.extend(diff_group_column.to_bytes(4, byteorder='little'))
    config_data.extend(target_noc2axi_x.to_bytes(4, byteorder='little'))
    config_data.extend(target_noc2axi_y.to_bytes(4, byteorder='little'))
    config_data.extend(blocked_level_row.to_bytes(4, byteorder='little'))

    tb.log.info(f"  Config: main_column={main_column}, diff_group_column={diff_group_column}")
    tb.log.info(f"          target_noc2axi=({target_noc2axi_x},{target_noc2axi_y}), blocked_level_row={blocked_level_row}")

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

    # Initialize test memory on SRAM (via backdoor) with blocked pattern BEFORE any EDC configuration
    # Using backdoor access via tb.rams[] (cocotbext-axi AxiRam) for direct memory initialization
    tb.log.info(f"Initializing SRAM memory via backdoor (tb.rams[{main_column}]) with BLOCKED pattern")

    data = PATTERN_BLOCKED.to_bytes(4, byteorder='little')

    # Scenario 1: Same group write (should become SUCCESS)
    tb.rams[main_column].write(SRAM_ADDR_GROUP_PASS, data)

    # Scenario 2: Different group write (should stay BLOCKED)
    tb.rams[main_column].write(SRAM_ADDR_GROUP_BLOCKED, data)

    # Scenario 3: High privilege level write (should become SUCCESS)
    tb.rams[main_column].write(SRAM_ADDR_LEVEL_PASS, data)

    # Scenario 4: Low privilege level write (should stay BLOCKED)
    tb.rams[main_column].write(SRAM_ADDR_LEVEL_BLOCKED, data)

    tb.log.info(f"  SRAM_ADDR_GROUP_PASS    = 0x{SRAM_ADDR_GROUP_PASS:08x}")
    tb.log.info(f"  SRAM_ADDR_GROUP_BLOCKED = 0x{SRAM_ADDR_GROUP_BLOCKED:08x}")
    tb.log.info(f"  SRAM_ADDR_LEVEL_PASS    = 0x{SRAM_ADDR_LEVEL_PASS:08x}")
    tb.log.info(f"  SRAM_ADDR_LEVEL_BLOCKED = 0x{SRAM_ADDR_LEVEL_BLOCKED:08x}")
    tb.log.info(f"All SRAM locations initialized to PATTERN_BLOCKED = 0x{PATTERN_BLOCKED:08x}")

    # -----------------------------------------------------------------------------------------
    #  Pre-initialize L1 read-back addresses on source tiles
    #  This allows us to detect if firmware NOC read never wrote data to L1
    # -----------------------------------------------------------------------------------------
    tb.log.info(f"Pre-initializing L1 read-back addresses with PATTERN_L1_PRELOAD = 0x{PATTERN_L1_PRELOAD:08x}")

    l1_preload_data = PATTERN_L1_PRELOAD.to_bytes(4, byteorder='little')

    l1_preload_tasks = []
    # Tile (main_col, 2) - GROUP_PASS and LEVEL_PASS read-backs
    tb.log.info(f"  Tile ({main_column},2) @ 0x{L1_READBACK_GROUP_PASS:05x} (GROUP_PASS)")
    l1_preload_tasks.append(
        tb.noc_write(default_master, main_column, 2, L1_READBACK_GROUP_PASS, l1_preload_data)
    )
    tb.log.info(f"  Tile ({main_column},2) @ 0x{L1_READBACK_LEVEL_PASS:05x} (LEVEL_PASS)")
    l1_preload_tasks.append(
        tb.noc_write(default_master, main_column, 2, L1_READBACK_LEVEL_PASS, l1_preload_data)
    )
    # Tile (diff_group_col, 2) - GROUP_BLOCKED read-back
    tb.log.info(f"  Tile ({diff_group_column},2) @ 0x{L1_READBACK_GROUP_BLOCKED:05x} (GROUP_BLOCKED)")
    l1_preload_tasks.append(
        tb.noc_write(default_master, diff_group_column, 2, L1_READBACK_GROUP_BLOCKED, l1_preload_data)
    )
    # Tile (main_col, blocked_level_row) - LEVEL_BLOCKED read-back
    tb.log.info(f"  Tile ({main_column},{blocked_level_row}) @ 0x{L1_READBACK_LEVEL_BLOCKED:05x} (LEVEL_BLOCKED)")
    l1_preload_tasks.append(
        tb.noc_write(default_master, main_column, blocked_level_row, L1_READBACK_LEVEL_BLOCKED, l1_preload_data)
    )

    # Wait for all L1 preload writes to complete
    for task in l1_preload_tasks:
        await task
    tb.log.info("L1 read-back addresses pre-initialized")

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
    # Each column = one security group
    # NOC2AXI tiles get secure range configured
    # Tensix tiles get different master_levels
    # -----------------------------------------------------------------------------------------

    tb.log.info("=" * 80)
    tb.log.info("Configuring security fence: 4 columns in parallel")
    tb.log.info("  Column 0 -> Group 1, Column 1 -> Group 2, Column 2 -> Group 3, Column 3 -> Group 4")
    tb.log.info("  NOC2AXI tiles get secure range (2.5MB-3MB, level >= 5)")
    tb.log.info("=" * 80)

    # Define address range for NOC2AXI tiles (security level fencing)
    # Configure SECURE_RANGE (2.5MB-3MB) to require level >= 5
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

    # Add NOC2AXI tiles to column_tiles
    for x, y in noc2axi_coords:
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
    # Define async task for configuring a column
    # -----------------------------------------------------------------------------------------

    async def configure_column(col_x, group_id, apb):
        """Configure all tiles in a column - including NOC2AXI"""
        tb.log.info(f"[Column {col_x}] Starting configuration (Group {group_id})")

        if col_x not in column_tiles:
            tb.log.warning(f"[Column {col_x}] No tiles to configure")
            return True

        # Configure each tile in column sequentially
        for idx, (tile_x, tile_y) in enumerate(column_tiles[col_x]):
            tb.log.info(f"[Column {col_x}] Configuring tile ({tile_x},{tile_y})")

            # Check if this is a NOC2AXI tile
            is_noc2axi = (tile_x, tile_y) in noc2axi_coords

            if is_noc2axi:
                # NOC2AXI tile: Configure with secure level range
                tb.log.info(f"[Column {col_x}]   -> NOC2AXI: secure range (2.5MB-3MB) enabled, level=8")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,
                    ranges_config=secure_level_range_config,
                    enable_fence=True
                )
            elif tile_y == blocked_level_row:
                # Row 1 (low privilege): Cannot access secure range on NOC2AXI
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=3 (cannot access secure range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=3,  # < 5, cannot access secure range on NOC2AXI
                    ranges_config=None,
                    enable_fence=True
                )
            elif tile_y == 2:
                # Row 2 (high privilege): Can access secure range on NOC2AXI
                tb.log.info(f"[Column {col_x}]   -> Row {tile_y}: no ranges, level=8 (can access secure range)")
                success = await edc_configure_security_fence(
                    tb, apb, tile_x, tile_y,
                    group_id=group_id,
                    master_level=8,  # >= 5, can access secure range on NOC2AXI
                    ranges_config=None,
                    enable_fence=True
                )
            else:
                # Other rows: Default privilege
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
        cocotb.start_soon(configure_column(0, 1, apb_master + 0)),
        cocotb.start_soon(configure_column(1, 2, apb_master + 1)),
        cocotb.start_soon(configure_column(2, 3, apb_master + 2)),
        cocotb.start_soon(configure_column(3, 4, apb_master + 3))
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
    #  Define expected violations and predict UNC_ERR interrupts
    # -----------------------------------------------------------------------------------------
    #
    # For NOC2AXI test, each blocked scenario does WRITE + READ, generating 2 violations each:
    #   Scenario 1: Different group access -> WRITE blocked + READ blocked = 2 violations
    #   Scenario 2: Low privilege access -> WRITE blocked + READ blocked = 2 violations
    #
    # Total: 4 violations expected, each triggers UNC_ERR via edc_crit_err_irq
    # -----------------------------------------------------------------------------------------

    tb.log.info("=" * 80)
    tb.log.info("PREDICTING SECURITY FENCE VIOLATION INTERRUPTS")
    tb.log.info("=" * 80)

    # SRC_ID for security fence violations from NOC2AXI (updated: was 192, now 19)
    SEC_FENCE_SRC_ID = 0xF413

    # Define expected violations using SecurityFenceViolation dataclass
    expected_violations = [
        # Scenario 2: Different group WRITE violation
        SecurityFenceViolation(
            src_x=diff_group_column,
            src_y=2,
            violated_group_id=True,
            name='Scenario 2a: Different group WRITE',
            description=f'Tile ({diff_group_column},2) Group {diff_group_column + 1} WRITE -> NOC2AXI Group {main_column + 1}'
        ),
        # Scenario 2: Different group READ violation
        SecurityFenceViolation(
            src_x=diff_group_column,
            src_y=2,
            violated_group_id=True,
            name='Scenario 2b: Different group READ',
            description=f'Tile ({diff_group_column},2) Group {diff_group_column + 1} READ -> NOC2AXI Group {main_column + 1}'
        ),
        # Scenario 4: Low privilege WRITE violation
        SecurityFenceViolation(
            src_x=main_column,
            src_y=blocked_level_row,
            range_access_blocked=0x001,  # Range 0 (secure range) blocked
            name='Scenario 4a: Low privilege WRITE',
            description=f'Tile ({main_column},{blocked_level_row}) Level 3 WRITE -> NOC2AXI SECURE_RANGE'
        ),
        # Scenario 4: Low privilege READ violation
        SecurityFenceViolation(
            src_x=main_column,
            src_y=blocked_level_row,
            range_access_blocked=0x001,  # Range 0 (secure range) blocked
            name='Scenario 4b: Low privilege READ',
            description=f'Tile ({main_column},{blocked_level_row}) Level 3 READ -> NOC2AXI SECURE_RANGE'
        ),
    ]

    tb.log.info(f"Target BIU: BIU[{main_column}]")
    tb.log.info(f"SRC_ID: {SEC_FENCE_SRC_ID}")
    tb.log.info(f"Expected {len(expected_violations)} violations, each triggers UNC_ERR")
    for i, v in enumerate(expected_violations):
        tb.log.info(f"  {i+1}. {v.name}: src=({v.src_x},{v.src_y}), group_id={v.violated_group_id}, range=0x{v.range_access_blocked:03x}")

    # Get monitors for RSP_PKT_RCVD and UNC_ERR
    rsp_pkt_rcvd_monitor = tb.biu_monitor_manager.biu[main_column]['rsp_pkt_rcvd']
    unc_err_monitor = tb.biu_monitor_manager.biu[main_column]['unc_err']

    # Make predictions for each expected violation
    # Each violation triggers BOTH RSP_PKT_RCVD and UNC_ERR simultaneously
    for i, v in enumerate(expected_violations):
        # RSP_PKT_RCVD prediction
        # IMPORTANT: auto_clear=False so user can read capture registers before clearing
        rsp_pkt_rcvd_monitor.predict(
            InterruptType.RSP_PKT_RCVD,
            {
                'expected_cmd': 0x9,  # UNC_EVENT (security fence violation)
                'expected_src_id': SEC_FENCE_SRC_ID,
                'expected_violation': v,
                'description': f'{v.name} RSP_PKT_RCVD',
            },
            auto_clear=False  # Manual clear - capture registers contain violation data
        )
        # UNC_ERR prediction
        unc_err_monitor.predict(
            InterruptType.UNC_ERR,
            {
                'expected_cmd': 0x9,  # UNC_EVENT
                'expected_src_id': SEC_FENCE_SRC_ID,
                'expected_violation': v,
                'description': f'{v.name} UNC_ERR',
            }
        )

    tb.log.info(f"Predicted {len(expected_violations)}x RSP_PKT_RCVD + {len(expected_violations)}x UNC_ERR interrupts")
    tb.log.info("=" * 80)

    # -----------------------------------------------------------------------------------------
    #  Release DM core reset and start firmware + interrupt monitoring in parallel
    # -----------------------------------------------------------------------------------------

    # Define async function to wait for firmware completion
    async def wait_for_firmware():
        """Wait for firmware execution to complete on all active tiles."""
        waiters = []
        for x, y in all_active_coords:
            waiters.append(cocotb.start_soon(tb.monitor_dm_scratch(x, y)))

        # Wait for all tiles to complete
        while waiters:
            await with_timeout(waiters.pop(0), 50_000, "ns")

        tb.log.info("[DONE] Firmware execution completed on all tiles")
        return True

    # Shared state for violation tracking (accessible from wait_for_interrupts_and_validate)
    violation_results = {
        'received': [],           # List of received violations
        'matched': set(),         # Set of matched expected violation indices
        'mismatches': [],         # List of mismatch error messages
    }

    # Define async function to wait for security fence interrupts and validate each
    async def wait_for_interrupts_and_validate():
        """
        Wait for 4 security fence violation interrupts and validate each immediately.

        Security fence violations trigger UNC_ERR (via edc_crit_err_irq) that:
        - Set UNC_ERR bit (0x20, bit 5) in BIU_STAT_REG
        - We use edc_wait_for_unc_err() which monitors edc_crit_err_irq signal
        - We clear UNC_ERR_BIT (0x20) to acknowledge the interrupt

        Capture register format:
          capture_reg_0[15:0] = RSP_HDR1[15:0]:
            [8:0]  = range_access_blocked
            [14:9] = SRC_X (6 bits)
          capture_reg_1[15:0] = RSP_DATA0[31:16]:
            [5:0]  = SRC_Y (6 bits)
            [9:6]  = VIOLATED_SW_INVALID_RANGE (4 bits)
            [10]   = VIOLATED_GROUP_ID
            [11]   = VIOLATED_GROUP_ID_NS
        """
        tb.log.info(f"[INTERRUPT] Waiting for {len(expected_violations)} security fence violations...")

        for i in range(len(expected_violations)):
            tb.log.info(f"[INTERRUPT] Waiting for violation #{i+1}/{len(expected_violations)} (via edc_crit_err_irq)...")

            success, interrupt = await edc_wait_for_unc_err(
                tb, main_column, timeout_cycles=10_000
            )

            if not success:
                tb.log.error(f"[INTERRUPT] TIMEOUT waiting for violation #{i+1}")
                tb.log.error("[INTERRUPT] Breaking simulation - first timeout is fatal")
                assert False, f"Timeout waiting for security fence violation #{i+1} - expected {len(expected_violations)} violations"

            tb.log.info(f"[INTERRUPT] Security fence violation #{i+1} received!")

            # Read capture registers
            rsp_hdr0 = await tb.read_edc_apb_register(main_column, BIU_RSP_HDR0_REG)
            rsp_hdr1 = await tb.read_edc_apb_register(main_column, BIU_RSP_HDR1_REG)
            rsp_data0 = await tb.read_edc_apb_register(main_column, BIU_RSP_DATA0_REG)
            rsp_data1 = await tb.read_edc_apb_register(main_column, BIU_RSP_DATA1_REG)

            tb.log.info(f"  RSP_HDR0:  0x{rsp_hdr0:08x}")
            tb.log.info(f"  RSP_HDR1:  0x{rsp_hdr1:08x} (SRC_ID=0x{rsp_hdr1 >> 16:04x}, capture_reg_0=0x{rsp_hdr1 & 0xFFFF:04x})")
            tb.log.info(f"  RSP_DATA0: 0x{rsp_data0:08x} (capture_reg_1=0x{rsp_data0 >> 16:04x})")
            tb.log.info(f"  RSP_DATA1: 0x{rsp_data1:08x}")

            # Parse violation from capture registers
            received = SecurityFenceViolation.from_capture_registers(rsp_hdr1, rsp_data0)
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

            # Clear UNC_ERR (security fence violations trigger UNC_ERR)
            await edc_clear_biu_interrupts(tb, main_column, UNC_ERR_BIT)
            tb.log.info("  Cleared UNC_ERR interrupt")

            await ClockCycles(tb.dut.noc_clk, 100)

        tb.log.info(f"[INTERRUPT] Done - received {len(violation_results['received'])} violations")
        return True

    # Start both tasks concurrently
    tb.log.info("=" * 80)
    tb.log.info("Starting firmware execution and interrupt monitoring in PARALLEL")
    tb.log.info("=" * 80)

    # Release DM core reset to start firmware
    await tb.release_dm_core_reset()
    tb.log.info("DM core reset released - firmware running on all tiles")
    tb.log.info("Scenarios 1, 2, 3 run immediately. Scenario 4 waits for GO signal.")

    # Launch firmware monitoring task
    firmware_task = cocotb.start_soon(wait_for_firmware())

    # Synchronization flag address in L1 (from test_config.h: SYNC_FLAG_BASE = 0x20200)
    SYNC_FLAG_L1_ADDR = 0x20200

    # -----------------------------------------------------------------------------------------
    #  Phase 1: Wait for Scenario 2 violations (2 violations: WRITE + READ)
    # -----------------------------------------------------------------------------------------
    tb.log.info("=" * 80)
    tb.log.info("PHASE 1: Waiting for Scenario 2 violations (2 expected)")
    tb.log.info("=" * 80)

    for i in range(2):
        tb.log.info(f"[INTERRUPT] Waiting for Scenario 2 violation #{i+1}/2...")

        success, interrupt = await edc_wait_for_unc_err(tb, main_column, timeout_cycles=10_000)

        if not success:
            tb.log.error(f"[INTERRUPT] TIMEOUT waiting for Scenario 2 violation #{i+1}")
            assert False, f"Timeout waiting for Scenario 2 violation #{i+1}"

        tb.log.info(f"[INTERRUPT] Scenario 2 violation #{i+1} received!")

        # Read and parse violation
        rsp_hdr1 = await tb.read_edc_apb_register(main_column, BIU_RSP_HDR1_REG)
        rsp_data0 = await tb.read_edc_apb_register(main_column, BIU_RSP_DATA0_REG)
        received = SecurityFenceViolation.from_capture_registers(rsp_hdr1, rsp_data0)
        tb.log.info(f"  Parsed: {received}")
        tb.log.info(received.print())
        violation_results['received'].append(received)

        # Match against expected violations
        matched = False
        for exp_idx, expected in enumerate(expected_violations):
            if exp_idx in violation_results['matched']:
                continue
            if expected.matches(received, check_source=True):
                tb.log.info(f"  [MATCH] {expected.name}")
                violation_results['matched'].add(exp_idx)
                matched = True
                break

        if not matched:
            msg = f"Unmatched violation: {received}"
            tb.log.warning(f"  [NO MATCH] {msg}")
            violation_results['mismatches'].append(msg)

        # Clear both UNC_ERR and RSP_PKT_RCVD (security fence violations trigger both)
        # RSP_PKT_RCVD contains capture register data, must be cleared after reading
        await edc_clear_biu_interrupts(tb, main_column, UNC_ERR_BIT | RSP_PKT_RCVD_BIT)
        await ClockCycles(tb.dut.noc_clk, 100)

    tb.log.info("Scenario 2 violations complete!")

    # -----------------------------------------------------------------------------------------
    #  Signal Scenario 4 to start (write GO signal to its L1)
    # -----------------------------------------------------------------------------------------
    tb.log.info("=" * 80)
    tb.log.info("PHASE 2: Signaling Scenario 4 to start")
    tb.log.info("=" * 80)

    # Write GO signal (0xDEAD0004) to tile (main_col, blocked_level_row) L1 address 0x20200
    # IMPORTANT: Must use correct group_id to avoid triggering security fence violation
    go_signal_group_id = main_column + 1  # Tile in column X has group X+1
    go_signal_config = NocTransactionConfig(sec_level=9, group_id=go_signal_group_id)
    tb.log.info(f"Writing GO signal (0xDEAD0004) to tile ({main_column},{blocked_level_row}) L1 @ 0x{SYNC_FLAG_L1_ADDR:08x}")
    tb.log.info(f"  Using AXI user bits = 0x{go_signal_config.get_user_bits():02x} (group_id={go_signal_group_id}, sec_level=9)")
    await tb.noc_write(default_master, main_column, blocked_level_row, SYNC_FLAG_L1_ADDR,
                      bytearray([0x04, 0x00, 0xAD, 0xDE]),  # 0xDEAD0004 in little-endian
                      config=go_signal_config)

    # -----------------------------------------------------------------------------------------
    #  Phase 2: Wait for Scenario 4 violations (2 violations: WRITE + READ)
    # -----------------------------------------------------------------------------------------
    tb.log.info("=" * 80)
    tb.log.info("PHASE 3: Waiting for Scenario 4 violations (2 expected)")
    tb.log.info("=" * 80)

    for i in range(2):
        tb.log.info(f"[INTERRUPT] Waiting for Scenario 4 violation #{i+1}/2...")

        success, interrupt = await edc_wait_for_unc_err(tb, main_column, timeout_cycles=10_000)

        if not success:
            tb.log.error(f"[INTERRUPT] TIMEOUT waiting for Scenario 4 violation #{i+1}")
            assert False, f"Timeout waiting for Scenario 4 violation #{i+1}"

        tb.log.info(f"[INTERRUPT] Scenario 4 violation #{i+1} received!")

        # Read and parse violation
        rsp_hdr1 = await tb.read_edc_apb_register(main_column, BIU_RSP_HDR1_REG)
        rsp_data0 = await tb.read_edc_apb_register(main_column, BIU_RSP_DATA0_REG)
        received = SecurityFenceViolation.from_capture_registers(rsp_hdr1, rsp_data0)
        tb.log.info(f"  Parsed: {received}")
        tb.log.info(received.print())
        violation_results['received'].append(received)

        # Match against expected violations
        matched = False
        for exp_idx, expected in enumerate(expected_violations):
            if exp_idx in violation_results['matched']:
                continue
            if expected.matches(received, check_source=True):
                tb.log.info(f"  [MATCH] {expected.name}")
                violation_results['matched'].add(exp_idx)
                matched = True
                break

        if not matched:
            msg = f"Unmatched violation: {received}"
            tb.log.warning(f"  [NO MATCH] {msg}")
            violation_results['mismatches'].append(msg)

        # Clear both UNC_ERR and RSP_PKT_RCVD (security fence violations trigger both)
        # RSP_PKT_RCVD contains capture register data, must be cleared after reading
        await edc_clear_biu_interrupts(tb, main_column, UNC_ERR_BIT | RSP_PKT_RCVD_BIT)
        await ClockCycles(tb.dut.noc_clk, 100)

    tb.log.info("Scenario 4 violations complete!")

    tb.log.info("=" * 80)
    tb.log.info("All violations received! Proceeding to wait for firmware completion")
    tb.log.info("=" * 80)

    # -----------------------------------------------------------------------------------------
    #  Report violation validation results
    # -----------------------------------------------------------------------------------------
    tb.log.info("=" * 80)
    tb.log.info("VIOLATION VALIDATION SUMMARY")
    tb.log.info("=" * 80)

    num_expected = len(expected_violations)
    num_matched = len(violation_results['matched'])
    num_received = len(violation_results['received'])

    tb.log.info(f"Expected violations: {num_expected}")
    tb.log.info(f"Received violations: {num_received}")
    tb.log.info(f"Matched violations:  {num_matched}/{num_expected}")

    # Report which expected violations were matched
    for exp_idx, expected in enumerate(expected_violations):
        status = "MATCHED" if exp_idx in violation_results['matched'] else "MISSING"
        tb.log.info(f"  [{status}] {expected.name}")

    # Report any mismatches
    if violation_results['mismatches']:
        tb.log.error("Unmatched received violations:")
        for msg in violation_results['mismatches']:
            tb.log.error(f"  {msg}")

    violations_valid = (num_matched == num_expected and len(violation_results['mismatches']) == 0)
    if violations_valid:
        tb.log.info("ALL VIOLATIONS VALIDATED SUCCESSFULLY")
    else:
        tb.log.error("VIOLATION VALIDATION FAILED")
        tb.log.error(f"  Expected {num_expected} violations, matched {num_matched}, mismatches {len(violation_results['mismatches'])}")
        assert False, f"Violation validation failed: {num_matched}/{num_expected} matched, {len(violation_results['mismatches'])} mismatches"

    tb.log.info("=" * 80)

    # -----------------------------------------------------------------------------------------
    #  Wait for firmware completion (gate for result verification)
    # -----------------------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("PHASE 2: Waiting for firmware execution to complete...")
    tb.log.info("(Violations validated, now waiting for all tiles to finish)")
    tb.log.info("=" * 80)

    # Wait for firmware completion - this is the gate for verification
    firmware_complete = await firmware_task

    tb.log.info("=" * 80)
    tb.log.info("[DONE] Both conditions met: Violations validated AND Firmware complete")
    tb.log.info("  Now safe to verify test results")
    tb.log.info("=" * 80)

    # -----------------------------------------------------------------------------------------
    #  Verify results - Check both SRAM (backdoor) and L1 (NOC read)
    # -----------------------------------------------------------------------------------------

    tb.log.info("\n" + "=" * 80)
    tb.log.info("VERIFYING TEST RESULTS (AFTER FIFO READING AND FIRMWARE COMPLETION)")
    tb.log.info("=" * 80)

    # Configure AXI user bits for verification reads from different tiles
    # Each tile has its own group (column X -> group X+1), so we need matching configs
    # Use high sec_level=9 to ensure verification access is allowed

    # Config for reading from tiles in main_column (group = main_column + 1)
    main_group_id = main_column + 1
    main_column_verify_config = NocTransactionConfig(sec_level=9, group_id=main_group_id)
    tb.log.info(f"Main column verification: AXI user bits = 0x{main_column_verify_config.get_user_bits():02x} "
                f"(group_id={main_group_id}, sec_level=9)")

    # Config for reading from tiles in diff_group_column (group = diff_group_column + 1)
    diff_group_id = diff_group_column + 1
    diff_column_verify_config = NocTransactionConfig(sec_level=9, group_id=diff_group_id)
    tb.log.info(f"Diff column verification: AXI user bits = 0x{diff_column_verify_config.get_user_bits():02x} "
                f"(group_id={diff_group_id}, sec_level=9)")

    all_checkers_passed = True

    # -------------------------------------------------------------------------
    # Checker 1: Same group access to GROUP_RANGE (should PASS)
    # Tile (main_col, 2) -> NOC2AXI GROUP_RANGE
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("Checker 1: Same Group Access to GROUP_RANGE - Should PASS")
    tb.log.info(f"  Tile ({main_column},2) writes to NOC2AXI ({target_noc2axi_x},{target_noc2axi_y})")
    tb.log.info("-" * 80)

    # Check SRAM (backdoor) - should have SUCCESS pattern
    sram_data = tb.rams[main_column].read(SRAM_ADDR_GROUP_PASS, 4)
    sram_result = int.from_bytes(sram_data, byteorder='little')

    # Check L1 read-back (via NOC) - should have SUCCESS pattern
    # Use main_column_verify_config to access tile in main_column with correct group/level
    l1_data = await tb.noc_read(default_master, main_column, 2, L1_READBACK_GROUP_PASS, 4,
                                 config=main_column_verify_config)
    l1_result = int.from_bytes(l1_data, byteorder='little')

    # Diagnostic: Read memory window around the success address
    tb.log.info("  === DIAGNOSTIC: Reading memory window around L1 address ===")
    diag_m8 = await tb.noc_read(default_master, main_column, 2, L1_READBACK_GROUP_PASS - 8, 4, config=main_column_verify_config)
    diag_m8_val = int.from_bytes(diag_m8, byteorder='little')
    tb.log.info(f"    addr-8:  0x{diag_m8_val:08x}")

    diag_m4 = await tb.noc_read(default_master, main_column, 2, L1_READBACK_GROUP_PASS - 4, 4, config=main_column_verify_config)
    diag_m4_val = int.from_bytes(diag_m4, byteorder='little')
    tb.log.info(f"    addr-4:  0x{diag_m4_val:08x}")

    tb.log.info(f"    addr+0:  0x{l1_result:08x} <-- TARGET")

    diag_p4 = await tb.noc_read(default_master, main_column, 2, L1_READBACK_GROUP_PASS + 4, 4, config=main_column_verify_config)
    diag_p4_val = int.from_bytes(diag_p4, byteorder='little')
    tb.log.info(f"    addr+4:  0x{diag_p4_val:08x}")

    diag_p8 = await tb.noc_read(default_master, main_column, 2, L1_READBACK_GROUP_PASS + 8, 4, config=main_column_verify_config)
    diag_p8_val = int.from_bytes(diag_p8, byteorder='little')
    tb.log.info(f"    addr+8:  0x{diag_p8_val:08x}")

    tb.log.info(f"  SRAM (backdoor): 0x{sram_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")
    tb.log.info(f"  L1 read-back:    0x{l1_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")

    if sram_result != PATTERN_SUCCESS:
        tb.log.error(f"  FAIL: SRAM value is 0x{sram_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")
        all_checkers_passed = False
    elif l1_result != PATTERN_SUCCESS:
        tb.log.error(f"  FAIL: L1 read-back value is 0x{l1_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")
        if l1_result == PATTERN_L1_PRELOAD:
            tb.log.error(f"    -> Still has preload value - read never wrote to L1")
        all_checkers_passed = False
    else:
        tb.log.info("  PASS: Write succeeded, read-back matches")

    # -------------------------------------------------------------------------
    # Checker 2: Different group access to GROUP_RANGE (should BLOCK)
    # Tile (diff_group_col, 2) -> NOC2AXI GROUP_RANGE
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("Checker 2: Different Group Access to GROUP_RANGE - Should BLOCK")
    tb.log.info(f"  Tile ({diff_group_column},2) writes to NOC2AXI ({target_noc2axi_x},{target_noc2axi_y})")
    tb.log.info("-" * 80)

    # Check SRAM (backdoor) - should still have BLOCKED pattern (write was blocked)
    sram_data = tb.rams[main_column].read(SRAM_ADDR_GROUP_BLOCKED, 4)
    sram_result = int.from_bytes(sram_data, byteorder='little')

    # Check L1 read-back (via NOC) - should have BLOCKED pattern or error response
    # Use diff_column_verify_config to access tile in diff_group_column with correct group/level
    l1_data = await tb.noc_read(default_master, diff_group_column, 2, L1_READBACK_GROUP_BLOCKED, 4,
                                 config=diff_column_verify_config)
    l1_result = int.from_bytes(l1_data, byteorder='little')

    # Diagnostic: Read memory window around the blocked address
    tb.log.info("  === DIAGNOSTIC: Reading memory window around L1 address ===")
    diag_m8 = await tb.noc_read(default_master, diff_group_column, 2, L1_READBACK_GROUP_BLOCKED - 8, 4, config=diff_column_verify_config)
    diag_m8_val = int.from_bytes(diag_m8, byteorder='little')
    tb.log.info(f"    addr-8:  0x{diag_m8_val:08x}")

    diag_m4 = await tb.noc_read(default_master, diff_group_column, 2, L1_READBACK_GROUP_BLOCKED - 4, 4, config=diff_column_verify_config)
    diag_m4_val = int.from_bytes(diag_m4, byteorder='little')
    tb.log.info(f"    addr-4:  0x{diag_m4_val:08x}")

    tb.log.info(f"    addr+0:  0x{l1_result:08x} <-- TARGET")

    diag_p4 = await tb.noc_read(default_master, diff_group_column, 2, L1_READBACK_GROUP_BLOCKED + 4, 4, config=diff_column_verify_config)
    diag_p4_val = int.from_bytes(diag_p4, byteorder='little')
    tb.log.info(f"    addr+4:  0x{diag_p4_val:08x}")

    diag_p8 = await tb.noc_read(default_master, diff_group_column, 2, L1_READBACK_GROUP_BLOCKED + 8, 4, config=diff_column_verify_config)
    diag_p8_val = int.from_bytes(diag_p8, byteorder='little')
    tb.log.info(f"    addr+8:  0x{diag_p8_val:08x}")

    tb.log.info(f"  SRAM (backdoor): 0x{sram_result:08x}, expected 0x{PATTERN_BLOCKED:08x}")
    tb.log.info(f"  L1 read-back:    0x{l1_result:08x}, expected 0x{PATTERN_BLOCKED:08x} or 0xDEAD0011")

    if sram_result != PATTERN_BLOCKED:
        tb.log.error(f"  FAIL: SRAM was modified to 0x{sram_result:08x} - write should have been blocked!")
        all_checkers_passed = False
    else:
        tb.log.info("  PASS: SRAM unchanged (write was blocked)")

    # Check L1 read-back value - should be BLOCKED or DEADBEEF
    if l1_result == PATTERN_BLOCKED:
        tb.log.info("  PASS: L1 read-back shows BLOCKED pattern (read returned blocked SRAM value)")
    elif l1_result == 0xDEAD0011:
        tb.log.info("  PASS: L1 read-back shows 0xDEAD0011 (security fence blocked read)")
    elif l1_result == PATTERN_L1_PRELOAD:
        tb.log.error(f"  FAIL: L1 still has preload value - read never wrote to L1")
        all_checkers_passed = False
    else:
        tb.log.error(f"  FAIL: L1 read-back has unexpected value 0x{l1_result:08x}")
        tb.log.error(f"    Expected: 0x{PATTERN_BLOCKED:08x} (read SRAM) or 0xDEAD0011 (security fence blocked)")
        all_checkers_passed = False

    # -------------------------------------------------------------------------
    # Checker 3: Same group, high privilege access to SECURE_RANGE (should PASS)
    # Tile (main_col, 2) -> NOC2AXI SECURE_RANGE
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("Checker 3: High Privilege Access to SECURE_RANGE - Should PASS")
    tb.log.info(f"  Tile ({main_column},2) with level 8 writes to NOC2AXI SECURE_RANGE")
    tb.log.info("-" * 80)

    # Check SRAM (backdoor) - should have SUCCESS pattern
    sram_data = tb.rams[main_column].read(SRAM_ADDR_LEVEL_PASS, 4)
    sram_result = int.from_bytes(sram_data, byteorder='little')

    # Check L1 read-back (via NOC) - should have SUCCESS pattern
    # Use main_column_verify_config to access tile in main_column with correct group/level
    l1_data = await tb.noc_read(default_master, main_column, 2, L1_READBACK_LEVEL_PASS, 4,
                                 config=main_column_verify_config)
    l1_result = int.from_bytes(l1_data, byteorder='little')

    tb.log.info(f"  SRAM (backdoor): 0x{sram_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")
    tb.log.info(f"  L1 read-back:    0x{l1_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")

    if sram_result != PATTERN_SUCCESS:
        tb.log.error(f"  FAIL: SRAM value is 0x{sram_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")
        all_checkers_passed = False
    elif l1_result != PATTERN_SUCCESS:
        tb.log.error(f"  FAIL: L1 read-back value is 0x{l1_result:08x}, expected 0x{PATTERN_SUCCESS:08x}")
        if l1_result == PATTERN_L1_PRELOAD:
            tb.log.error(f"    -> Still has preload value - read never wrote to L1")
        all_checkers_passed = False
    else:
        tb.log.info("  PASS: Write succeeded, read-back matches")

    # -------------------------------------------------------------------------
    # Checker 4: Same group, low privilege access to SECURE_RANGE (should BLOCK)
    # Tile (main_col, blocked_level_row) -> NOC2AXI SECURE_RANGE
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    tb.log.info("Checker 4: Low Privilege Access to SECURE_RANGE - Should BLOCK")
    tb.log.info(f"  Tile ({main_column},{blocked_level_row}) with level 3 writes to NOC2AXI SECURE_RANGE")
    tb.log.info("-" * 80)

    # Check SRAM (backdoor) - should still have BLOCKED pattern (write was blocked)
    sram_data = tb.rams[main_column].read(SRAM_ADDR_LEVEL_BLOCKED, 4)
    sram_result = int.from_bytes(sram_data, byteorder='little')

    # Check L1 read-back (via NOC) - should have BLOCKED pattern or error response
    # Use main_column_verify_config to access tile in main_column with correct group/level
    l1_data = await tb.noc_read(default_master, main_column, blocked_level_row, L1_READBACK_LEVEL_BLOCKED, 4,
                                 config=main_column_verify_config)
    l1_result = int.from_bytes(l1_data, byteorder='little')

    # Diagnostic: Read memory window around the blocked address
    tb.log.info("  === DIAGNOSTIC: Reading memory window around L1 address ===")
    diag_m8 = await tb.noc_read(default_master, main_column, blocked_level_row, L1_READBACK_LEVEL_BLOCKED - 8, 4, config=main_column_verify_config)
    diag_m8_val = int.from_bytes(diag_m8, byteorder='little')
    tb.log.info(f"    addr-8:  0x{diag_m8_val:08x}")

    diag_m4 = await tb.noc_read(default_master, main_column, blocked_level_row, L1_READBACK_LEVEL_BLOCKED - 4, 4, config=main_column_verify_config)
    diag_m4_val = int.from_bytes(diag_m4, byteorder='little')
    tb.log.info(f"    addr-4:  0x{diag_m4_val:08x}")

    tb.log.info(f"    addr+0:  0x{l1_result:08x} <-- TARGET")

    diag_p4 = await tb.noc_read(default_master, main_column, blocked_level_row, L1_READBACK_LEVEL_BLOCKED + 4, 4, config=main_column_verify_config)
    diag_p4_val = int.from_bytes(diag_p4, byteorder='little')
    tb.log.info(f"    addr+4:  0x{diag_p4_val:08x}")

    diag_p8 = await tb.noc_read(default_master, main_column, blocked_level_row, L1_READBACK_LEVEL_BLOCKED + 8, 4, config=main_column_verify_config)
    diag_p8_val = int.from_bytes(diag_p8, byteorder='little')
    tb.log.info(f"    addr+8:  0x{diag_p8_val:08x}")

    tb.log.info(f"  SRAM (backdoor): 0x{sram_result:08x}, expected 0x{PATTERN_BLOCKED:08x}")
    tb.log.info(f"  L1 read-back:    0x{l1_result:08x}, expected 0x{PATTERN_BLOCKED:08x} or 0xDEAD0011")

    if sram_result != PATTERN_BLOCKED:
        tb.log.error(f"  FAIL: SRAM was modified to 0x{sram_result:08x} - write should have been blocked!")
        all_checkers_passed = False
    else:
        tb.log.info("  PASS: SRAM unchanged (write was blocked)")

    # Check L1 read-back value - should be BLOCKED or DEADBEEF
    if l1_result == PATTERN_BLOCKED:
        tb.log.info("  PASS: L1 read-back shows BLOCKED pattern (read returned blocked SRAM value)")
    elif l1_result == 0xDEAD0011:
        tb.log.info("  PASS: L1 read-back shows 0xDEAD0011 (security fence blocked read)")
    elif l1_result == PATTERN_L1_PRELOAD:
        tb.log.error(f"  FAIL: L1 still has preload value - read never wrote to L1")
        all_checkers_passed = False
    else:
        tb.log.error(f"  FAIL: L1 read-back has unexpected value 0x{l1_result:08x}")
        tb.log.error(f"    Expected: 0x{PATTERN_BLOCKED:08x} (read SRAM) or 0xDEAD0011 (security fence blocked)")
        all_checkers_passed = False

    # -------------------------------------------------------------------------
    # Final Summary
    # -------------------------------------------------------------------------
    tb.log.info("\n" + "=" * 80)
    if all_checkers_passed:
        tb.log.info("ALL CHECKERS PASSED")
    else:
        tb.log.error("SOME CHECKERS FAILED")
        assert False, "Security fence checker failures detected"

    tb.log.info("=" * 80)
    tb.log.info("Security Fence NOC2AXI Sanity Test Completed Successfully.")
