import random
import traceback

import cocotb
from cocotb.triggers import ClockCycles, with_timeout

from tests.utils.coco_tensix_api import demoTB
from tests.utils.edc_util import (
    BIU_CTRL_REG,
    BIU_ID_REG,
    BIU_IRQ_EN_REG,
    BIU_STAT_REG,
    edc_check_fatal_errors,
    edc_disable_edc_muxes,
    edc_enable_all_edc_muxes,
    edc_harvest_columns,
    edc_reconfigure_coordinates_after_column_harvest,
)
from tests.utils.tensix_config import TileType
from tests.utils.test_utils import load_binary_data


async def simple_edc_col_harvesting(dut, bin_path):
    """
    Test EDC APB communication for column harvesting in noc2axi tiles.

    This test demonstrates column harvesting where a complete column (all rows in that column)
    is harvested instead of a row. This uses cocotb EDC APB extension to configure
    the BIU interface for EDC (Error Detection and Correction) column harvesting.

    The BIU acts as the EDC ring master and can issue read/write messages to EDC nodes
    through its EDC APB register interface.
    """

    # -----------------------------------------------------------------------------------------
    #  Initialize testbench
    # -----------------------------------------------------------------------------------------

    tb = demoTB(dut)

    await tb.init_and_reset()
    tb.log.info("Testbench initialized and DUT reset.")

    # -----------------------------------------------------------------------------------------
    #  Load binary, get tile coordinates
    # -----------------------------------------------------------------------------------------

    # Load binary
    try:
        binary_data = load_binary_data(bin_path=bin_path)
        tb.log.info(f"Loaded binary from {bin_path} ({len(binary_data)} bytes)")
    except FileNotFoundError:
        tb.log.error(f"Binary not found at {bin_path}.")
        raise

    # Get coordinates for different tile types
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    dispatch_coords = (
        tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) +
        tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    )
    noc2axi_coords = (
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT) +
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT) +
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)
    )

    all_active_coords = tensix_coords + dispatch_coords

    # Define test parameters
    default_master = tb.default_master

    # Identify available tiles
    for host_x, host_y in noc2axi_coords:
        tb.log.info(f"NOC2AXI coordinates: {host_x}, {host_y}")
    for host_x, host_y in dispatch_coords:
        tb.log.info(f"DISPATCH_W coordinates: {host_x}, {host_y}")
    for host_x, host_y in tensix_coords:
        tb.log.info(f"TENSIX coordinates: {host_x}, {host_y}")
    for host_x, host_y in all_active_coords:
        tb.log.info(f"All active coordinates: {host_x}, {host_y}")

    # -----------------------------------------------------------------------------------------
    #  Harvest column
    # -----------------------------------------------------------------------------------------

    tb.log.info(f"noc2axi_coords: {noc2axi_coords}")
    tb.log.info(f"Number of EDC APB interfaces: {tb.config.num_apb}")

    if len(noc2axi_coords) == 0:
        assert False, "No noc2axi coordinates found"

    # Generate a random integer for selecting harvest target column (0-3)
    harvest_target_column = random.randint(0, 3)
    # harvest_target_column = 1
    tb.log.info(f"Selected column to be harvested: {harvest_target_column}")

    if harvest_target_column == 0:
        default_master = default_master + 1

    # Test each available EDC APB interface (one per noc2axi)
    for apb_master in range(min(tb.config.num_apb, len(noc2axi_coords))):

        tb.log.info(f"Testing EDC APB master {apb_master} - noc2axi at {noc2axi_coords[apb_master] if apb_master < len(noc2axi_coords) else 'N/A'}")

        # Read BIU ID register to verify communication
        try:
            biu_id = await tb.read_edc_apb_register(apb_master, BIU_ID_REG)
            tb.log.info(f"EDC APB Master {apb_master} - BIU ID: 0x{biu_id:08x}")

            # Extract version and BIU ID fields
            edc_biu_id = biu_id & 0xFF
            edc_version_super = (biu_id >> 28) & 0xF
            edc_version_major = (biu_id >> 24) & 0x0F
            edc_version_minor = (biu_id >> 16) & 0x00FF
            tb.log.info(f"  EDC BIU ID: 0x{edc_biu_id:02x}")
            tb.log.info(f"  EDC Version: {edc_version_super:1d}.{edc_version_major:1d}.{edc_version_minor:1d}")

        except Exception as e:
            assert False, f"Failed to read BIU ID from EDC APB master {apb_master}: {e}"

        # Read initial status register
        status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        tb.log.info(f"EDC APB Master {apb_master} - Initial Status: 0x{status:08x}")

        # Check for fatal errors in initial status
        if await edc_check_fatal_errors(tb, apb_master, status):
            assert False, (f"Fatal error detected in initial status - APB master {apb_master}")

        # Enable all interrupts
        await tb.write_edc_apb_register(apb_master, BIU_IRQ_EN_REG, 0xBB)

        # Read back interrupt enable register to verify
        irq_en_readback = await tb.read_edc_apb_register(apb_master, BIU_IRQ_EN_REG)
        tb.log.info(f"EDC APB Master {apb_master} - IRQ Enable readback: 0x{irq_en_readback:08x}")

        # Test control register read/write
        # await tb.write_edc_apb_register(apb_master, BIU_CTRL_REG, 0x1)  # Set INIT bit
        ctrl_readback = await tb.read_edc_apb_register(apb_master, BIU_CTRL_REG)
        tb.log.info(f"EDC APB Master {apb_master} - Control register: 0x{ctrl_readback:08x}")

    # Enable EDC muxes for all noc2axi tiles in parallel before starting harvest operations
    enable_muxes_task = []
    for apb_master in range(min(tb.config.num_apb, len(noc2axi_coords))):
        tb.log.info(f"Enabling EDC muxes via APB master {apb_master}")

        enable_mux_task = cocotb.start_soon(edc_enable_all_edc_muxes(tb, apb_master))
        enable_muxes_task.append((apb_master, enable_mux_task))

    # Process each enable mux task with timeout
    tb.log.info("Waiting for EDC mux enabling to complete...")
    for apb_master, enable_mux_task in enable_muxes_task:
        try:
            # Apply timeout similar to waiters pattern - using 10 seconds (10_000_000 ns) for enable mux operations
            enable_mux_success = await with_timeout(enable_mux_task, 10_000_000, "ns")
            if not enable_mux_success:
                tb.log.error(f"EDC mux enabling failed for APB master {apb_master}")
                raise RuntimeError(
                    f"EDC mux enabling failed for APB master {apb_master}"
                )
            else:
                tb.log.info(
                    f"EDC mux enabling completed successfully for APB master {apb_master}"
                )
        except cocotb.result.SimTimeoutError:
            tb.log.error(
                f"EDC mux enabling operation timed out for APB master {apb_master} (30 seconds timeout)"
            )
            raise
        except Exception as e:
            tb.log.error(
                f"Exception in EDC mux enabling for APB master {apb_master}: {e}"
            )
            raise

    #  Run harvest operations in parallel for column on all noc2axi tiles
    await edc_harvest_columns(tb, noc2axi_coords, harvest_target_column)

    # Disable EDC muxes for all noc2axi tiles in parallel after harvest operations to re-enable normal access to harvested column
    disable_muxes_task = []
    for apb_master in range(min(tb.config.num_apb, len(noc2axi_coords))):
        tb.log.info(f"Disabling EDC muxes via APB master {apb_master}")

        disable_mux_task = cocotb.start_soon(
            edc_disable_edc_muxes(
                tb, apb_master, harvested_columns=harvest_target_column
            )
        )
        disable_muxes_task.append((apb_master, disable_mux_task))
    # Process each disable mux task with timeout
    tb.log.info("Waiting for EDC mux disabling to complete...")
    for apb_master, disable_mux_task in disable_muxes_task:
        try:
            # Apply timeout similar to waiters pattern - using 10 seconds (10_000_000 ns) for disable mux operations
            disable_mux_success = await with_timeout(disable_mux_task, 10_000_000, "ns")
            if not disable_mux_success:
                tb.log.error(f"EDC mux disabling failed for APB master {apb_master}")
                raise RuntimeError(
                    f"EDC mux disabling failed for APB master {apb_master}"
                )
            else:
                tb.log.info(
                    f"EDC mux disabling completed successfully for APB master {apb_master}"
                )
        except cocotb.result.SimTimeoutError:
            tb.log.error(
                f"EDC mux disabling operation timed out for APB master {apb_master} (30 seconds timeout)"
            )
            raise
        except Exception as e:
            tb.log.error(
                f"Exception in EDC mux disabling for APB master {apb_master}: {e}"
            )
            raise

    await ClockCycles(tb.dut.axi_clk, 1000)

    tb.log.info("EDC Column Harvesting completed successfully")

    # -----------------------------------------------------------------------------------------
    #  Load binary to non-harvested tiles
    # -----------------------------------------------------------------------------------------

    # Get coordinates for different tile types after column harvest
    tensix_coords_harvested = edc_reconfigure_coordinates_after_column_harvest(tensix_coords, harvest_target_column)
    dispatch_coords_harvested = edc_reconfigure_coordinates_after_column_harvest(dispatch_coords, harvest_target_column)
    noc2axi_coords_harvested = edc_reconfigure_coordinates_after_column_harvest(noc2axi_coords, harvest_target_column)

    all_active_coords_harvested = tensix_coords_harvested + dispatch_coords_harvested

    # Identify available tiles
    for host_x, host_y in noc2axi_coords_harvested:
        tb.log.info(f"NOC2AXI post-harvest coordinates: {host_x}, {host_y}")
    for host_x, host_y in dispatch_coords_harvested:
        tb.log.info(f"DISPATCH_W post-harvest coordinates: {host_x}, {host_y}")
    for host_x, host_y in tensix_coords_harvested:
        tb.log.info(f"TENSIX post-harvest coordinates: {host_x}, {host_y}")
    for host_x, host_y in all_active_coords_harvested:
        tb.log.info(f"All active coordinates: {host_x}, {host_y}")

    # Load binary to all host tiles
    tb.log.info("Loading binary to all host tiles...")
    load_binary_tasks = []
    for host_x, host_y in all_active_coords_harvested:
        tb.log.info(f"Loading binary to Host Tile ({host_x},{host_y}) at address 0x0")
        load_binary_tasks.append(
            tb.noc_write(default_master, host_x, host_y, 0x0, binary_data)
        )

    # Wait for all binary loading to complete before proceeding
    tb.log.info("Waiting for binary loading to complete...")
    for task in load_binary_tasks:
        await task
    tb.log.info("Binary loading completed for all host tiles.")

    # -----------------------------------------------------------------------------------------
    # Write configuration values to memory for firmware to read
    # -----------------------------------------------------------------------------------------

    # Write configuration values to memory for firmware to read
    config_base_addr = 0x100000  # 1MB first address for test configurations

    # Generate 2 random values between 0 and 3
    row_selection_column_0 = random.randint(0, 2)
    row_selection_column_2 = random.randint(0, 2)
    dim_order_sel = random.randint(0, 1)
    tb.log.info(f"Generated random values: Column 0 row selection = {row_selection_column_0}, Column 2 row selection = {row_selection_column_2}, DIM order selection = {dim_order_sel}")

    config_values = [
        row_selection_column_0,  # Row 0 column selection
        row_selection_column_2,  # Row 1 column selection
        dim_order_sel            # DIM order selection
    ]

    tb.log.info("Writing configuration values to memory...")
    write_tasks = []
    for host_x, host_y in all_active_coords_harvested:
        for i, value in enumerate(config_values):
            addr = config_base_addr + (i * 4)  # 4 bytes per uint32_t
            data = value.to_bytes(
                4, byteorder="little"
            )  # Convert to little-endian bytes
            tb.log.info(
                f"Writing config[{i}] = {value} to address 0x{addr:08x} on tile ({host_x},{host_y})"
            )
            write_tasks.append(
                tb.noc_write_nonblocking(default_master, host_x, host_y, addr, data)
            )

    # Wait for all config writes to complete
    tb.log.info("Waiting for configuration writes to complete...")
    for task in write_tasks:
        await task
    tb.log.info("Configuration values written to memory.")

    # -----------------------------------------------------------------------------------------
    # Binary execution
    # -----------------------------------------------------------------------------------------

    waiters = []
    # Only monitor scratches on active Tensix/DM cores (skip harvested column)
    for x, y in all_active_coords:
        if x == harvest_target_column:
            continue  # Skip harvested column tiles
        waiters.append(cocotb.start_soon(tb.monitor_dm_scratch(x, y)))

    await tb.release_dm_core_reset()
    tb.log.info("DM core reset released for all host tiles.")

    while waiters:
        await with_timeout(waiters.pop(0), 10_000, "ns")

    tb.log.info("Simple EDC Column Harvesting Binary Finished!")

    # -----------------------------------------------------------------------------------------
    # STEP 1: Verify columns on different sides of harvested column are accessible
    # -----------------------------------------------------------------------------------------

    # Test columns on both sides of harvested column (similar to sanity test)
    tb.log.info("Starting L1 memory write/read test on columns beside harvested column")

    # Determine which columns are on left and right of harvest
    left_columns = [x for x in range(4) if x < harvest_target_column]
    right_columns = [x for x in range(4) if x > harvest_target_column]

    test_tiles = []
    if left_columns:
        test_tiles.append((left_columns[0], 0))  # Leftmost column, bottom tile
        test_tiles.append((left_columns[0], 1))  # Leftmost column, middle tile
        test_tiles.append((left_columns[0], 2))  # Leftmost column, top tile
    if right_columns:
        test_tiles.append((right_columns[-1], 0))  # Rightmost column, bottom tile
        test_tiles.append((right_columns[-1], 1))  # Rightmost column, middle tile
        test_tiles.append((right_columns[-1], 2))  # Rightmost column, top tile

    if not test_tiles:
        tb.log.warning("Cannot perform cross-column test - no columns on both sides of harvest")
    else:
        tb.log.info(f"Testing L1 memory on tiles from different sides: {test_tiles}")

        # Prepare test data
        test_values = [0xAA, 0x55, 0xCC]
        l1_test_base_addr = 0x140000  # 1MB + 256KB offset

        l1_test_tasks = []

        for tile_x_physical, tile_y in test_tiles:
            # AXI master uses physical column ID
            axi_master = tile_x_physical

            # Calculate logical coordinate
            num_harvested_left = sum(1 for col in [harvest_target_column] if col < tile_x_physical)
            tile_x_logical = tile_x_physical - num_harvested_left

            # Only test if this tile exists
            if (tile_x_physical, tile_y) in tensix_coords:
                tb.log.info(f"Testing physical tile ({tile_x_physical}, {tile_y}) -> logical ({tile_x_logical}, {tile_y}) using AXI master {axi_master}")

                async def test_tile_l1_memory(x_phys, x_log, y, values, base_addr, master):
                    tb.log.info(f"AXI master {master}: STARTING L1 test for physical tile ({x_phys}, {y}), logical ({x_log}, {y})")
                    try:
                        # Write test values using LOGICAL coordinates
                        write_tasks = []
                        for i, value in enumerate(values):
                            addr = base_addr + (i * 4)
                            data = value.to_bytes(4, byteorder="little")
                            write_task = tb.noc_write(master, x_log, y, addr, data)
                            write_tasks.append(write_task)

                        for task in write_tasks:
                            await task

                        # Read back and verify using LOGICAL coordinates
                        all_passed = True
                        for i, expected_value in enumerate(values):
                            addr = base_addr + (i * 4)
                            read_data = await tb.noc_read(master, x_log, y, addr, 4)

                            if isinstance(read_data, (bytes, bytearray)):
                                read_value = int.from_bytes(read_data, byteorder="little")
                            elif isinstance(read_data, tuple):
                                read_value = int.from_bytes(bytes(read_data), byteorder="little")
                            else:
                                tb.log.error(f"AXI master {master}: Unexpected read data type")
                                all_passed = False
                                continue

                            if read_value != expected_value:
                                tb.log.error(f"AXI master {master}: Value {i} FAILED - expected {expected_value}, got {read_value}")
                                all_passed = False

                        if all_passed:
                            tb.log.info(f"AXI master {master}: L1 memory test PASSED for physical tile ({x_phys}, {y})")
                            return True
                        else:
                            tb.log.error(f"AXI master {master}: L1 memory test FAILED for physical tile ({x_phys}, {y})")
                            return False

                    except Exception as e:
                        tb.log.error(f"AXI master {master}: L1 memory test FAILED with exception: {e}")
                        return False

                task = cocotb.start_soon(
                    test_tile_l1_memory(tile_x_physical, tile_x_logical, tile_y, test_values, l1_test_base_addr, axi_master)
                )
                l1_test_tasks.append((tile_x_physical, tile_y, axi_master, task))

        # Wait for all tests
        all_tests_passed = True
        for tile_x, tile_y, axi_master, test_task in l1_test_tasks:
            try:
                test_result = await with_timeout(test_task, 2_000, "ns")
                if not test_result:
                    all_tests_passed = False
                    tb.log.error(f"L1 memory test failed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
                else:
                    tb.log.info(f"L1 memory test passed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
            except Exception as e:
                all_tests_passed = False
                tb.log.error(f"L1 memory test exception for tile ({tile_x}, {tile_y}): {e}")

        if all_tests_passed:
            tb.log.info("All L1 memory write/read tests PASSED on columns beside harvest")
        else:
            tb.log.error("Some L1 memory write/read tests FAILED on columns beside harvest")
            assert False, "L1 memory test failures detected"

    # -----------------------------------------------------------------------------------------
    # STEP 2: Read 128KB from logical columns 0 and 2, test all 3 tensix tiles (y=0,1,2)
    # -----------------------------------------------------------------------------------------

    # Always test logical columns 0 and 2
    logical_columns_to_test = [0, 2]

    tb.log.info(f"Starting 128KB L1 memory read and data matching test on logical columns: {logical_columns_to_test}")

    # Define test parameters
    test_size_kb = 128  # 128KB total
    chunk_size_kb = 64  # Each chunk is 64KB
    bytes_per_kb = 1024
    test_size_bytes = test_size_kb * bytes_per_kb  # 131072 bytes
    chunk_size_bytes = chunk_size_kb * bytes_per_kb  # 65536 bytes

    # L1 memory base address for the 128KB test
    l1_read_test_base_addr = 0x200000  # 2MB offset into L1 memory (different from previous test)

    # Define test function for a single tile
    async def test_128kb_l1_read_single_tile(x_log, y, x_phys, base_addr, master, test_bytes, chunk_bytes):
        """Test function to read 128KB from L1 memory and verify first 64KB matches second 64KB"""
        tb.log.info(f"AXI master {master}: STARTING 128KB L1 read test for logical tile ({x_log}, {y}) [physical: ({x_phys}, {y})]")
        try:
            # Read the full 128KB of data using LOGICAL coordinates
            tb.log.info(f"AXI master {master}: Reading {test_bytes} bytes from address 0x{base_addr:08x}")
            read_data = await tb.noc_read(master, x_log, y, base_addr, test_bytes)

            # Convert to bytes if needed
            if isinstance(read_data, tuple):
                read_bytes = bytes(read_data)
            elif isinstance(read_data, (bytes, bytearray)):
                read_bytes = read_data
            else:
                tb.log.error(f"AXI master {master}: Unexpected read data type: {type(read_data)}")
                return False

            # Verify we got the expected amount of data
            if len(read_bytes) != test_bytes:
                tb.log.error(f"AXI master {master}: Expected {test_bytes} bytes, got {len(read_bytes)} bytes")
                return False

            tb.log.info(f"AXI master {master}: Successfully read {len(read_bytes)} bytes from logical tile ({x_log}, {y})")

            # Split into first 64KB and second 64KB chunks
            first_64kb = read_bytes[:chunk_bytes]
            second_64kb = read_bytes[chunk_bytes:chunk_bytes*2]

            tb.log.info(f"AXI master {master}: Comparing first 64KB with second 64KB")
            tb.log.info(f"AXI master {master}: First chunk size: {len(first_64kb)} bytes")
            tb.log.info(f"AXI master {master}: Second chunk size: {len(second_64kb)} bytes")

            # Compare the two 64KB chunks
            if first_64kb == second_64kb:
                tb.log.info(f"AXI master {master}: DATA MATCH SUCCESS - First 64KB matches second 64KB on logical tile ({x_log}, {y})")
                return True
            else:
                # Find first mismatch for debugging
                mismatch_offset = None
                for i in range(min(len(first_64kb), len(second_64kb))):
                    if first_64kb[i] != second_64kb[i]:
                        mismatch_offset = i
                        break

                if mismatch_offset is not None:
                    tb.log.error(f"AXI master {master}: DATA MATCH FAILED - First mismatch at byte offset {mismatch_offset}")
                    tb.log.error(f"AXI master {master}: First chunk byte {mismatch_offset}: 0x{first_64kb[mismatch_offset]:02x}")
                    tb.log.error(f"AXI master {master}: Second chunk byte {mismatch_offset}: 0x{second_64kb[mismatch_offset]:02x}")
                else:
                    tb.log.error(f"AXI master {master}: DATA MATCH FAILED - Chunk sizes differ")

                return False

        except Exception as e:
            tb.log.error(f"AXI master {master}: 128KB L1 read test FAILED for logical tile ({x_log}, {y}) with exception: {e}")
            tb.log.error(f"AXI master {master}: Exception traceback: {traceback.format_exc()}")
            return False

    # Define function to test all 3 tiles in a column SEQUENTIALLY (one AXI master at a time)
    async def test_column_sequential(logical_col_x, physical_col_x, axi_master):
        """Test all 3 tiles in a column sequentially using the same AXI master"""
        tb.log.info(f"AXI master {axi_master}: Starting SEQUENTIAL 128KB tests for logical column {logical_col_x}")
        results = []

        # Test all 3 tiles sequentially (y = 0, 1, 2)
        for tile_y in [0, 1, 2]:
            # Verify this physical tile exists
            if (physical_col_x, tile_y) not in tensix_coords:
                tb.log.warning(f"Physical tile ({physical_col_x}, {tile_y}) not available, skipping")
                continue

            tb.log.info(f"AXI master {axi_master}: Testing tile {tile_y} in logical column {logical_col_x}")

            # Test this tile (sequential - wait for result before continuing)
            result = await test_128kb_l1_read_single_tile(
                logical_col_x, tile_y, physical_col_x, l1_read_test_base_addr, axi_master,
                test_size_bytes, chunk_size_bytes
            )
            results.append((logical_col_x, tile_y, physical_col_x, result))

        tb.log.info(f"AXI master {axi_master}: Completed all sequential tests for logical column {logical_col_x}")
        return results

    # Start ALL column tasks in parallel (each column processes its tiles sequentially internally)
    column_tasks = []

    for logical_col_x in logical_columns_to_test:
        # Calculate physical column ID from logical column ID
        if logical_col_x < harvest_target_column:
            physical_col_x = logical_col_x
        else:
            physical_col_x = logical_col_x + 1

        # AXI master uses physical column ID
        axi_master = physical_col_x

        tb.log.info(f"Logical column {logical_col_x} -> Physical column {physical_col_x}, using AXI master {axi_master}")

        # Ensure we don't exceed available AXI masters
        if axi_master >= min(tb.config.num_noc2axi, len(noc2axi_coords)):
            tb.log.warning(f"Skipping logical column {logical_col_x} - AXI master {axi_master} not available")
            continue

        # Start column task (will process all 3 tiles sequentially)
        task = cocotb.start_soon(test_column_sequential(logical_col_x, physical_col_x, axi_master))
        column_tasks.append((logical_col_x, physical_col_x, axi_master, task))

    # Wait for ALL column tasks to complete (columns run in parallel)
    tb.log.info(f"Waiting for {len(column_tasks)} parallel column tasks (each with 3 sequential tile tests) to complete...")
    all_column_tests_passed = True

    for logical_col_x, physical_col_x, axi_master, column_task in column_tasks:
        try:
            # Get results from this column (list of tuples)
            column_results = await with_timeout(column_task, 15_000, "ns")  # 15 second timeout for 3 tiles

            # Check each tile result
            for logical_x, tile_y, physical_x, test_result in column_results:
                if not test_result:
                    all_column_tests_passed = False
                    tb.log.error(f"128KB L1 read test failed for logical tile ({logical_x}, {tile_y}) [physical: ({physical_x}, {tile_y})] using AXI master {axi_master}")
                else:
                    tb.log.info(f"128KB L1 read test passed for logical tile ({logical_x}, {tile_y}) [physical: ({physical_x}, {tile_y})] using AXI master {axi_master}")

        except cocotb.result.SimTimeoutError:
            all_column_tests_passed = False
            tb.log.error(f"128KB L1 read tests timed out for logical column {logical_col_x} [physical: {physical_col_x}] using AXI master {axi_master}")
        except Exception as e:
            all_column_tests_passed = False
            tb.log.error(f"128KB L1 read tests exception for logical column {logical_col_x} [physical: {physical_col_x}] using AXI master {axi_master}: {e}")

    # Final result for all tested columns
    if all_column_tests_passed:
        tb.log.info(f"All 128KB L1 memory read and data matching tests PASSED on all tested logical columns: {logical_columns_to_test}")
    else:
        tb.log.error(f"Some 128KB L1 memory read and data matching tests FAILED on tested logical columns: {logical_columns_to_test}")
        assert False, "128KB L1 memory read test failures detected on tested logical columns"

    # -----------------------------------------------------------------------------------------
    # STEP 3: Read 256KB from logical columns 0 and 2 on selected tiles and verify one-to-many data matching
    # -----------------------------------------------------------------------------------------

    tb.log.info("Starting 256KB one-to-many L1 memory read and data matching test on logical columns 0 and 2")

    # Define test parameters
    one_to_many_test_size_kb = 256  # 256KB total (4 * 64KB) - writes to 3 locations = 4 chunks
    one_to_many_chunk_size_kb = 64  # Each chunk is 64KB
    one_to_many_test_size_bytes = one_to_many_test_size_kb * bytes_per_kb  # 262144 bytes
    one_to_many_chunk_size_bytes = one_to_many_chunk_size_kb * bytes_per_kb  # 65536 bytes

    # L1 memory base address for the 256KB test (1.5MB as per firmware)
    one_to_many_base_addr = 0x180000  # 1.5MB (1536 * 1024)

    # Test tiles based on randomized row selection for logical columns 0 and 2
    # Logical column 0 uses row_selection_column_0
    # Logical column 2 uses row_selection_column_2
    test_tile_configs = [
        (0, row_selection_column_0),  # Logical column 0, selected row
        (2, row_selection_column_2)   # Logical column 2, selected row
    ]

    tb.log.info(f"Testing one-to-many data on logical tiles: {test_tile_configs}")

    # Define test function for 256KB one-to-many read
    async def test_256kb_one_to_many_read(x_log, y, x_phys, base_addr, master, test_bytes, chunk_bytes):
        """Test function to read 256KB and verify all 4 chunks of 64KB match"""
        tb.log.info(f"AXI master {master}: STARTING 256KB one-to-many read test for logical tile ({x_log}, {y}) [physical: ({x_phys}, {y})]")
        try:
            # Read the full 256KB of data using LOGICAL coordinates
            tb.log.info(f"AXI master {master}: Reading {test_bytes} bytes from address 0x{base_addr:08x}")
            read_data = await tb.noc_read(master, x_log, y, base_addr, test_bytes)

            # Convert to bytes if needed
            if isinstance(read_data, tuple):
                read_bytes = bytes(read_data)
            elif isinstance(read_data, (bytes, bytearray)):
                read_bytes = read_data
            else:
                tb.log.error(f"AXI master {master}: Unexpected read data type: {type(read_data)}")
                return False

            # Verify we got the expected amount of data
            if len(read_bytes) != test_bytes:
                tb.log.error(f"AXI master {master}: Expected {test_bytes} bytes, got {len(read_bytes)} bytes")
                return False

            tb.log.info(f"AXI master {master}: Successfully read {len(read_bytes)} bytes from logical tile ({x_log}, {y})")

            # Split into 4 chunks of 64KB each
            chunks = []
            for i in range(4):
                chunk_start = i * chunk_bytes
                chunk_end = chunk_start + chunk_bytes
                chunks.append(read_bytes[chunk_start:chunk_end])
                tb.log.info(f"AXI master {master}: Chunk {i} size: {len(chunks[i])} bytes")

            # Compare all chunks against the first chunk
            tb.log.info(f"AXI master {master}: Comparing all 4 chunks for data matching")
            first_chunk = chunks[0]
            all_match = True

            for i in range(1, 4):
                if chunks[i] == first_chunk:
                    tb.log.info(f"AXI master {master}: Chunk {i} MATCHES chunk 0 on logical tile ({x_log}, {y})")
                else:
                    # Find first mismatch for debugging
                    mismatch_offset = None
                    for j in range(min(len(first_chunk), len(chunks[i]))):
                        if first_chunk[j] != chunks[i][j]:
                            mismatch_offset = j
                            break

                    if mismatch_offset is not None:
                        tb.log.error(f"AXI master {master}: Chunk {i} MISMATCH - First difference at byte offset {mismatch_offset}")
                        tb.log.error(f"AXI master {master}: Chunk 0 byte {mismatch_offset}: 0x{first_chunk[mismatch_offset]:02x}")
                        tb.log.error(f"AXI master {master}: Chunk {i} byte {mismatch_offset}: 0x{chunks[i][mismatch_offset]:02x}")
                    else:
                        tb.log.error(f"AXI master {master}: Chunk {i} MISMATCH - Chunk sizes differ")

                    all_match = False

            if all_match:
                tb.log.info(f"AXI master {master}: DATA MATCH SUCCESS - All 4 chunks match on logical tile ({x_log}, {y})")
                return True
            else:
                tb.log.error(f"AXI master {master}: DATA MATCH FAILED - Not all chunks match on logical tile ({x_log}, {y})")
                return False

        except Exception as e:
            tb.log.error(f"AXI master {master}: 256KB one-to-many read test FAILED for logical tile ({x_log}, {y}) with exception: {e}")
            tb.log.error(f"AXI master {master}: Exception traceback: {traceback.format_exc()}")
            return False

    # Start BOTH tasks in parallel (2 different AXI masters, can run simultaneously)
    one_to_many_test_tasks = []

    for logical_col_x, tile_y in test_tile_configs:
        # Calculate physical column ID from logical column ID
        if logical_col_x < harvest_target_column:
            physical_col_x = logical_col_x
        else:
            physical_col_x = logical_col_x + 1

        # AXI master uses physical column ID
        axi_master = physical_col_x

        tb.log.info(f"Logical tile ({logical_col_x}, {tile_y}) -> Physical tile ({physical_col_x}, {tile_y}), using AXI master {axi_master}")

        # Ensure we don't exceed available AXI masters
        if axi_master >= min(tb.config.num_noc2axi, len(noc2axi_coords)):
            tb.log.warning(f"Skipping logical tile ({logical_col_x}, {tile_y}) - AXI master {axi_master} not available")
            continue

        # Verify physical tile exists
        if (physical_col_x, tile_y) not in tensix_coords:
            tb.log.warning(f"Skipping logical tile ({logical_col_x}, {tile_y}) [physical: ({physical_col_x}, {tile_y})] - not in tensix coordinates")
            continue

        # Verify tile is in harvested coordinates (logical)
        if (logical_col_x, tile_y) not in tensix_coords_harvested:
            tb.log.warning(f"Skipping logical tile ({logical_col_x}, {tile_y}) - not in harvested coordinates")
            continue

        tb.log.info(f"Starting 256KB one-to-many read test for logical tile ({logical_col_x}, {tile_y}) [physical: ({physical_col_x}, {tile_y})] using AXI master {axi_master}")

        # Start the test task for this tile (different AXI masters run in parallel)
        task = cocotb.start_soon(
            test_256kb_one_to_many_read(
                logical_col_x, tile_y, physical_col_x, one_to_many_base_addr, axi_master,
                one_to_many_test_size_bytes, one_to_many_chunk_size_bytes
            )
        )
        one_to_many_test_tasks.append((logical_col_x, tile_y, physical_col_x, axi_master, task))

    # Wait for BOTH 256KB one-to-many tests to complete (running in parallel with different AXI masters)
    tb.log.info(f"Waiting for {len(one_to_many_test_tasks)} parallel 256KB one-to-many tests to complete (different AXI masters)...")
    all_one_to_many_tests_passed = True

    for logical_x, tile_y, physical_x, axi_master, test_task in one_to_many_test_tasks:
        try:
            test_result = await with_timeout(test_task, 20_000, "ns")  # 20 second timeout
            if not test_result:
                all_one_to_many_tests_passed = False
                tb.log.error(f"256KB one-to-many test failed for logical tile ({logical_x}, {tile_y}) [physical: ({physical_x}, {tile_y})] using AXI master {axi_master}")
            else:
                tb.log.info(f"256KB one-to-many test passed for logical tile ({logical_x}, {tile_y}) [physical: ({physical_x}, {tile_y})] using AXI master {axi_master}")
        except cocotb.result.SimTimeoutError:
            all_one_to_many_tests_passed = False
            tb.log.error(f"256KB one-to-many test timed out for logical tile ({logical_x}, {tile_y}) [physical: ({physical_x}, {tile_y})] using AXI master {axi_master}")
        except Exception as e:
            all_one_to_many_tests_passed = False
            tb.log.error(f"256KB one-to-many test exception for logical tile ({logical_x}, {tile_y}) [physical: ({physical_x}, {tile_y})] using AXI master {axi_master}: {e}")

    # Final result
    if all_one_to_many_tests_passed:
        tb.log.info("All 256KB one-to-many L1 memory read and data matching tests PASSED on logical columns 0 and 2")
    else:
        tb.log.error("Some 256KB one-to-many L1 memory read and data matching tests FAILED on logical columns 0 and 2")
        assert False, "256KB one-to-many test failures detected on logical columns 0 and 2"

    tb.log.info("EDC Column Harvesting Simple Test Completed Successfully.")
