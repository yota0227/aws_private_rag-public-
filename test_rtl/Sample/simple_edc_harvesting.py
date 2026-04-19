from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
import random
import cocotb
from cocotb.triggers import Timer
from cocotb.triggers import with_timeout


async def simple_edc_harvesting(dut, bin_path):
    """
    Test EDC APB communication to BIU (Bus Interface Unit) in noc2axi tiles.

    This test demonstrates how to use cocotb EDC APB extension to send APB traffic to
    the BIU interface for EDC (Error Detection and Correction) communication.

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
    dispatch_coords = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) + tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    noc2axi_coords = tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT) + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT) + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)

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
    #  Harvest row between 0-2
    # -----------------------------------------------------------------------------------------

    tb.log.info(f"noc2axi_coords: {noc2axi_coords}")
    tb.log.info(f"Number of EDC APB interfaces: {tb.config.num_apb}")

    if len(noc2axi_coords) == 0:
        assert False, f"No noc2axi coordinates found"

    # Generate a random integer for selecting harvest target row
    harvest_target = random.randint(0, 2)
    # harvest_target = 1
    tb.log.info(f"Selceted row to be harvested: {harvest_target}")

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

    #  Run harvest operations in parallel for row 1 on all noc2axi tiles
    await edc_harvest_rows(tb, noc2axi_coords, harvest_target)

    await ClockCycles(tb.dut.axi_clk, 1000)
    
    tb.log.info("EDC Harvesting completed successfully")

    # -----------------------------------------------------------------------------------------
    #  Load binary to non-harvested tiles
    # -----------------------------------------------------------------------------------------

    # Get coordinates for different tile types
    tensix_coords_harvested = edc_reconfigure_coordinates_after_harvest(tensix_coords, harvest_target)
    dispatch_coords_harvested = edc_reconfigure_coordinates_after_harvest(dispatch_coords, harvest_target)
    noc2axi_coords_harvested = edc_reconfigure_coordinates_after_harvest(noc2axi_coords, harvest_target)

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
    tb.log.info(f"Loading binary to all host tiles...")
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
    column_selection_row_0 = random.randint(0, 3)
    column_selection_row_1 = random.randint(0, 3)
    dim_order_sel = random.randint(0, 1)
    tb.log.info(f"Generated random values: Row 0 column selection = {column_selection_row_0}, Row 1 column selection = {column_selection_row_1}, DIM order selection = {dim_order_sel}")

    config_values = [
        column_selection_row_0,  # Row 0 column selection
        column_selection_row_1,  # Row 1 column selection
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
    # Only monitor scratches on active Tensix/DM cores
    for x, y in all_active_coords:
        if y == harvest_target:
            continue  # Skip harvested row tiles
        waiters.append(cocotb.start_soon(tb.monitor_dm_scratch(x, y)))

    await tb.release_dm_core_reset()
    tb.log.info("DM core reset released for all host tiles.")

    while waiters:
        await with_timeout(waiters.pop(0), 10_000, "ns")

    tb.log.info("Sanity EDC Harvesting Binary Finished!")

    # -----------------------------------------------------------------------------------------
    # Verify that row bellow harvested row is still accessible
    # -----------------------------------------------------------------------------------------

    # Final check to ensure bottom row is accessible after harvesting
    tb.log.info("Starting L1 memory write/read test on bottom tiles for all 4 columns in parallel")

    # Get all tensix coordinates to verify which bottom tiles exist
    # tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    if not tensix_coords_harvested:
        tb.log.error("No Tensix tiles found for L1 memory test")
    else:
        # Bottom tiles are at y=0 for each column (x=0,y=0), (x=1,y=0), (x=2,y=0), (x=3,y=0)
        bottom_tiles = [(x, 0) for x in range(4) if (x, 0) in tensix_coords]

        tb.log.info(f"Testing L1 memory on bottom tiles: {bottom_tiles}")

        # Prepare test data - 3 integer values, each < 256
        test_values = [0xAA, 0x55, 0xCC]  # 3 test values for 3 transactions

        # L1 memory test base address - using a safe region in L1
        l1_test_base_addr = 0x140000  # 1MB + 256KB offset into L1 memory

        # Perform write/read test using each noc2axi master for its corresponding column
        l1_test_tasks = []

        for axi_master in range(min(tb.config.num_noc2axi, len(noc2axi_coords))):
            # Only test AXI master 0 for debugging
            # Bottom tile for this column (axi_master corresponds to column)
            tile_x, tile_y = axi_master, 0

            # Only test if this bottom tile exists as a tensix tile
            if (tile_x, tile_y) in tensix_coords:
                tb.log.info(f"Starting L1 write/read test for bottom tile ({tile_x}, {tile_y}) using AXI master {axi_master}")

                # Create test task for this tile
                async def test_tile_l1_memory(x, y, values, base_addr, master):
                    tb.log.info(f"AXI master {master}: STARTING L1 test for tile ({x}, {y})")
                    try:
                        tb.log.info(f"AXI master {master}: About to create write tasks for {len(values)} values")

                        # Write test values to L1 memory (similar to config writing pattern)
                        write_tasks = []
                        for i, value in enumerate(values):
                            addr = base_addr + (i * 4)  # 4 bytes per uint32_t
                            data = value.to_bytes(
                                4, byteorder="little"
                            )  # Convert to little-endian bytes
                            tb.log.info(f"AXI master {master}: Creating write task {i}: value {value} (0x{value:02x}) to address 0x{addr:08x} on tile ({x},{y})")
                            write_task = tb.noc_write(master, x, y, addr, data)
                            write_tasks.append(write_task)
                            tb.log.info(f"AXI master {master}: Write task {i} created successfully")

                        tb.log.info(f"AXI master {master}: All {len(write_tasks)} write tasks created, now waiting for completion")

                        # Wait for all writes to complete
                        for i, task in enumerate(write_tasks):
                            tb.log.info(f"AXI master {master}: Waiting for write task {i} to complete")
                            await task
                            tb.log.info(f"AXI master {master}: Write task {i} completed")

                        tb.log.info(f"AXI master {master}: All writes completed for tile ({x}, {y})")

                        # Read back and verify each value
                        tb.log.info(f"AXI master {master}: Starting read-back verification")
                        all_passed = True

                        for i, expected_value in enumerate(values):
                            addr = base_addr + (i * 4)  # 4 bytes per uint32_t
                            tb.log.info(f"AXI master {master}: About to read value {i} from address 0x{addr:08x}" )

                            read_data = await tb.noc_read(master, x, y, addr, 4)
                            tb.log.info(f"AXI master {master}: Read operation {i} completed, data type: {type(read_data)}")

                            # Convert read data back to integer
                            if isinstance(read_data, (bytes, bytearray)):
                                tb.log.info(f"AXI master {master}: Converting bytes/bytearray to int")
                                read_value = int.from_bytes(
                                    read_data, byteorder="little"
                                )
                            elif isinstance(read_data, tuple):
                                tb.log.info(f"AXI master {master}: Converting tuple to int")
                                read_bytes = bytes(read_data)
                                read_value = int.from_bytes(
                                    read_bytes, byteorder="little"
                                )
                            else:
                                tb.log.error(f"AXI master {master}: Unexpected read data type: {type(read_data)}")
                                all_passed = False
                                continue

                            tb.log.info(f"AXI master {master}: Read value {read_value} (0x{read_value:02x}) from address 0x{addr:08x} on tile ({x},{y})")

                            if read_value == expected_value:
                                tb.log.info(f"AXI master {master}: Value {i} PASSED - expected {expected_value} (0x{expected_value:02x}), got {read_value} (0x{read_value:02x})")
                            else:
                                tb.log.error(f"AXI master {master}: Value {i} FAILED - expected {expected_value} (0x{expected_value:02x}), got {read_value} (0x{read_value:02x})")
                                all_passed = False

                        tb.log.info(f"AXI master {master}: Finished all read-back verifications")

                        if all_passed:
                            tb.log.info(f"AXI master {master}: L1 memory test PASSED for tile ({x}, {y}) - all values verified")
                            return True
                        else:
                            tb.log.error(f"AXI master {master}: L1 memory test FAILED for tile ({x}, {y}) - some values mismatched")
                            return False

                    except Exception as e:
                        tb.log.error(f"AXI master {master}: L1 memory test FAILED for tile ({x}, {y}) with exception: {e}")
                        import traceback

                        tb.log.error(f"AXI master {master}: Exception traceback: {traceback.format_exc()}")
                        return False

                # Start the test task for this tile with its corresponding master
                task = cocotb.start_soon(
                    test_tile_l1_memory(
                        tile_x, tile_y, test_values, l1_test_base_addr, axi_master
                    )
                )
                l1_test_tasks.append((tile_x, tile_y, axi_master, task))

        # Wait for all L1 memory tests to complete
        tb.log.info(f"Waiting for {len(l1_test_tasks)} parallel L1 memory tests to complete...")
        all_tests_passed = True

        for tile_x, tile_y, axi_master, test_task in l1_test_tasks:
            try:
                test_result = await with_timeout(test_task, 2_000, "ns")  # 10 second timeout
                if not test_result:
                    all_tests_passed = False
                    tb.log.error(f"L1 memory test failed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
                else:
                    tb.log.info(f"L1 memory test passed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
            except cocotb.triggers.TimeoutError:
                all_tests_passed = False
                tb.log.error(f"L1 memory test timed out for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
            except Exception as e:
                all_tests_passed = False
                tb.log.error(f"L1 memory test exception for tile ({tile_x}, {tile_y}) using AXI master {axi_master}: {e}")

        if all_tests_passed:
            tb.log.info("All L1 memory write/read tests PASSED on bottom tiles")
        else:
            tb.log.error("Some L1 memory write/read tests FAILED on bottom tiles")
            assert False, "L1 memory test failures detected on bottom tiles"

    # -----------------------------------------------------------------------------------------
    # Read 128KB from L1 memory on specified row tiles and verify data matching
    # -----------------------------------------------------------------------------------------

    # Define rows to test (extensible for future use - currently only row 0)
    # TODO: In the future, this can be expanded to test multiple rows like [0, 2]
    rows_to_test = [0, 1]  # Currently testing only row 0

    tb.log.info(f"Starting 128KB L1 memory read and data matching test on rows: {rows_to_test}")

    # Define test parameters
    test_size_kb = 128  # 128KB total
    chunk_size_kb = 64  # Each chunk is 64KB
    bytes_per_kb = 1024
    test_size_bytes = test_size_kb * bytes_per_kb  # 131072 bytes
    chunk_size_bytes = chunk_size_kb * bytes_per_kb  # 65536 bytes

    # L1 memory base address for the 128KB test
    l1_read_test_base_addr = 0x200000  # 2MB offset into L1 memory (different from previous test)

    # Test each specified row
    all_row_tests_passed = True

    for row_y in rows_to_test:
        tb.log.info(f"Testing row {row_y} tiles for 128KB L1 memory read and data matching")

        # Get tiles in this row that are still active (not harvested)
        row_tiles = [(x, row_y) for x in range(4) if (x, row_y) in tensix_coords_harvested]

        if not row_tiles:
            tb.log.warning(f"No tiles in row {row_y} available for 128KB L1 memory test")
            continue

        tb.log.info(f"Testing 128KB L1 memory read on row {row_y} tiles: {row_tiles}")

        # Test each tile in this row
        read_test_tasks = []

        for tile_x, tile_y in row_tiles:
            # Use corresponding AXI master for each column
            axi_master = tile_x

            # Ensure we don't exceed available AXI masters
            if axi_master >= min(tb.config.num_noc2axi, len(noc2axi_coords)):
                tb.log.warning(f"Skipping tile ({tile_x}, {tile_y}) - AXI master {axi_master} not available")
                continue

            tb.log.info(f"Starting 128KB L1 read test for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")

            async def test_128kb_l1_read(x, y, base_addr, master, test_bytes, chunk_bytes):
                """Test function to read 128KB from L1 memory and verify first 64KB matches second 64KB"""
                tb.log.info(f"AXI master {master}: STARTING 128KB L1 read test for tile ({x}, {y})")
                try:
                    # Read the full 128KB of data
                    tb.log.info(f"AXI master {master}: Reading {test_bytes} bytes from address 0x{base_addr:08x}")
                    read_data = await tb.noc_read(master, x, y, base_addr, test_bytes)

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

                    tb.log.info(f"AXI master {master}: Successfully read {len(read_bytes)} bytes from tile ({x}, {y})")

                    # Split into first 64KB and second 64KB chunks
                    first_64kb = read_bytes[:chunk_bytes]
                    second_64kb = read_bytes[chunk_bytes:chunk_bytes*2]

                    tb.log.info(f"AXI master {master}: Comparing first 64KB with second 64KB")
                    tb.log.info(f"AXI master {master}: First chunk size: {len(first_64kb)} bytes")
                    tb.log.info(f"AXI master {master}: Second chunk size: {len(second_64kb)} bytes")

                    # Compare the two 64KB chunks
                    if first_64kb == second_64kb:
                        tb.log.info(f"AXI master {master}: DATA MATCH SUCCESS - First 64KB matches second 64KB on tile ({x}, {y})")
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
                    tb.log.error(f"AXI master {master}: 128KB L1 read test FAILED for tile ({x}, {y}) with exception: {e}")
                    import traceback
                    tb.log.error(f"AXI master {master}: Exception traceback: {traceback.format_exc()}")
                    return False

            # Start the test task for this tile
            task = cocotb.start_soon(
                test_128kb_l1_read(
                    tile_x, tile_y, l1_read_test_base_addr, axi_master,
                    test_size_bytes, chunk_size_bytes
                )
            )
            read_test_tasks.append((tile_x, tile_y, axi_master, task))

        # Wait for all 128KB read tests to complete for this row
        tb.log.info(f"Waiting for {len(read_test_tasks)} parallel 128KB L1 read tests to complete on row {row_y}...")
        row_tests_passed = True

        for tile_x, tile_y, axi_master, test_task in read_test_tasks:
            try:
                test_result = await with_timeout(test_task, 5_000, "ns")  # 5 second timeout for larger reads
                if not test_result:
                    row_tests_passed = False
                    all_row_tests_passed = False
                    tb.log.error(f"128KB L1 read test failed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
                else:
                    tb.log.info(f"128KB L1 read test passed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
            except cocotb.triggers.TimeoutError:
                row_tests_passed = False
                all_row_tests_passed = False
                tb.log.error(f"128KB L1 read test timed out for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
            except Exception as e:
                row_tests_passed = False
                all_row_tests_passed = False
                tb.log.error(f"128KB L1 read test exception for tile ({tile_x}, {tile_y}) using AXI master {axi_master}: {e}")

        if row_tests_passed:
            tb.log.info(f"All 128KB L1 memory read and data matching tests PASSED on row {row_y}")
        else:
            tb.log.error(f"Some 128KB L1 memory read and data matching tests FAILED on row {row_y}")

    # Final result for all tested rows
    if all_row_tests_passed:
        tb.log.info(f"All 128KB L1 memory read and data matching tests PASSED on all tested rows: {rows_to_test}")
    else:
        tb.log.error(f"Some 128KB L1 memory read and data matching tests FAILED on tested rows: {rows_to_test}")
        assert False, "128KB L1 memory read test failures detected on tested rows"

    # -----------------------------------------------------------------------------------------
    # Read 320KB from selected tiles and verify one-to-many data matching
    # -----------------------------------------------------------------------------------------

    tb.log.info("Starting 320KB one-to-many L1 memory read and data matching test")

    # Define test parameters
    one_to_many_test_size_kb = 320  # 320KB total (5 * 64KB)
    one_to_many_chunk_size_kb = 64  # Each chunk is 64KB
    one_to_many_test_size_bytes = one_to_many_test_size_kb * bytes_per_kb  # 327680 bytes
    one_to_many_chunk_size_bytes = one_to_many_chunk_size_kb * bytes_per_kb  # 65536 bytes

    # L1 memory base address for the 320KB test (1.5MB as per firmware)
    one_to_many_base_addr = 0x180000  # 1.5MB (1536 * 1024)

    # Test tiles based on randomized column selection
    test_tiles = [
        (column_selection_row_0, 0),  # Selected tile in row 0
        (column_selection_row_1, 1)   # Selected tile in row 1
    ]

    tb.log.info(f"Testing one-to-many data on tiles: {test_tiles}")

    # Test each selected tile
    one_to_many_test_tasks = []
    all_one_to_many_tests_passed = True

    for tile_x, tile_y in test_tiles:
        # Use corresponding AXI master for each column
        axi_master = tile_x

        # Ensure we don't exceed available AXI masters
        if axi_master >= min(tb.config.num_noc2axi, len(noc2axi_coords)):
            tb.log.warning(f"Skipping tile ({tile_x}, {tile_y}) - AXI master {axi_master} not available")
            continue

        # Verify tile is in harvested coordinates
        if (tile_x, tile_y) not in tensix_coords_harvested:
            tb.log.warning(f"Skipping tile ({tile_x}, {tile_y}) - not in harvested coordinates")
            continue

        tb.log.info(f"Starting 320KB one-to-many read test for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")

        async def test_320kb_one_to_many_read(x, y, base_addr, master, test_bytes, chunk_bytes):
            """Test function to read 320KB and verify all 5 chunks of 64KB match"""
            tb.log.info(f"AXI master {master}: STARTING 320KB one-to-many read test for tile ({x}, {y})")
            try:
                # Read the full 320KB of data
                tb.log.info(f"AXI master {master}: Reading {test_bytes} bytes from address 0x{base_addr:08x}")
                read_data = await tb.noc_read(master, x, y, base_addr, test_bytes)

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

                tb.log.info(f"AXI master {master}: Successfully read {len(read_bytes)} bytes from tile ({x}, {y})")

                # Split into 5 chunks of 64KB each
                chunks = []
                for i in range(5):
                    chunk_start = i * chunk_bytes
                    chunk_end = chunk_start + chunk_bytes
                    chunks.append(read_bytes[chunk_start:chunk_end])
                    tb.log.info(f"AXI master {master}: Chunk {i} size: {len(chunks[i])} bytes")

                # Compare all chunks against the first chunk
                tb.log.info(f"AXI master {master}: Comparing all 5 chunks for data matching")
                first_chunk = chunks[0]
                all_match = True

                for i in range(1, 5):
                    if chunks[i] == first_chunk:
                        tb.log.info(f"AXI master {master}: Chunk {i} MATCHES chunk 0 on tile ({x}, {y})")
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
                    tb.log.info(f"AXI master {master}: DATA MATCH SUCCESS - All 5 chunks match on tile ({x}, {y})")
                    return True
                else:
                    tb.log.error(f"AXI master {master}: DATA MATCH FAILED - Not all chunks match on tile ({x}, {y})")
                    return False

            except Exception as e:
                tb.log.error(f"AXI master {master}: 320KB one-to-many read test FAILED for tile ({x}, {y}) with exception: {e}")
                import traceback
                tb.log.error(f"AXI master {master}: Exception traceback: {traceback.format_exc()}")
                return False

        # Start the test task for this tile
        task = cocotb.start_soon(
            test_320kb_one_to_many_read(
                tile_x, tile_y, one_to_many_base_addr, axi_master,
                one_to_many_test_size_bytes, one_to_many_chunk_size_bytes
            )
        )
        one_to_many_test_tasks.append((tile_x, tile_y, axi_master, task))

    # Wait for all 320KB one-to-many tests to complete
    tb.log.info(f"Waiting for {len(one_to_many_test_tasks)} parallel 320KB one-to-many tests to complete...")

    for tile_x, tile_y, axi_master, test_task in one_to_many_test_tasks:
        try:
            test_result = await with_timeout(test_task, 20_000, "ns")  # 20 second timeout
            if not test_result:
                all_one_to_many_tests_passed = False
                tb.log.error(f"320KB one-to-many test failed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
            else:
                tb.log.info(f"320KB one-to-many test passed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
        except cocotb.triggers.TimeoutError:
            all_one_to_many_tests_passed = False
            tb.log.error(f"320KB one-to-many test timed out for tile ({tile_x}, {tile_y}) using AXI master {axi_master}")
        except Exception as e:
            all_one_to_many_tests_passed = False
            tb.log.error(f"320KB one-to-many test exception for tile ({tile_x}, {tile_y}) using AXI master {axi_master}: {e}")

    # Final result
    if all_one_to_many_tests_passed:
        tb.log.info("All 320KB one-to-many L1 memory read and data matching tests PASSED")
    else:
        tb.log.error("Some 320KB one-to-many L1 memory read and data matching tests FAILED")
        assert False, "320KB one-to-many test failures detected"

    tb.log.info("EDC Harvesting Sanity Test Completed Successfully.")