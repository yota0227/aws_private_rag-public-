from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
import random
import cocotb
from cocotb.triggers import Timer
from cocotb.triggers import with_timeout


async def sanity_edc_harvesting(dut, bin_path):
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
    #  Harvest row 1
    # -----------------------------------------------------------------------------------------

    tb.log.info(f"noc2axi_coords: {noc2axi_coords}")
    tb.log.info(f"Number of EDC APB interfaces: {tb.config.num_apb}")

    if len(noc2axi_coords) == 0:
        assert False, f"No noc2axi coordinates found"

    # Generate a random integer for selecting harvest target row
    harvest_target = random.randint(0, 2)
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
    tb.log.info("Start harvesting proccess for row {harvest_target} on all noc2axi tiles")
    harvest_tasks = []
    for apb_master in range(min(tb.config.num_apb, len(noc2axi_coords))):

        tb.log.info(f"Starting parallel harvest operation for APB master {apb_master}")

        # Start harvest task using cocotb.start_soon()
        harvest_task = cocotb.start_soon(
            edc_harvest_rows_single_column(
                tb=tb,
                apb_master=apb_master,
                column_target=apb_master,
                harvest_target_rows=[harvest_target],
            )
        )
        harvest_tasks.append((apb_master, harvest_task))

    # Wait for all harvest operations to complete with timeout (similar to waiters pattern)
    tb.log.info(f"Waiting for {len(harvest_tasks)} parallel harvest operations to complete...")

    # Process each harvest task with timeout
    for apb_master, harvest_task in harvest_tasks:
        try:
            # Apply timeout similar to waiters pattern - using 30 seconds (30_000_000 ns) for harvest operations
            harvest_success = await with_timeout(harvest_task, 30_000_000, "ns")
            if not harvest_success:
                tb.log.error(f"Harvest failed for APB master {apb_master}")
                raise RuntimeError(f"Harvest failed for APB master {apb_master}")  # ← This will be caught by except
            else:
                tb.log.info(f"Harvest completed successfully for APB master {apb_master}")
        except cocotb.triggers.TimeoutError:
            tb.log.error(f"Harvest operation timed out for APB master {apb_master} (30 seconds timeout)")
            raise
        except Exception as e:
            tb.log.error(f"Exception in harvest for APB master {apb_master}: {e}")
            raise

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
        l1_test_base_addr = 0x10000  # 64KB offset into L1 memory

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

    tb.log.info("EDC Harvesting Sanity Test Completed Successfully.")