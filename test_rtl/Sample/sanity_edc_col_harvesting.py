import cocotb
from cocotb.triggers import with_timeout

from tests.utils.coco_tensix_api import demoTB
from tests.utils.edc_util import (
    BIU_CTRL_REG,
    BIU_ID_REG,
    BIU_IRQ_EN_REG,
    BIU_STAT_REG,
    edc_check_fatal_errors,
    edc_disable_edc_muxes,
    edc_do_random_harvesting,
    edc_enable_all_edc_muxes,
)
from tests.utils.tensix_config import TileType
from tests.utils.test_utils import load_binary_data


async def sanity_edc_col_harvesting(dut, bin_path):
    """
    Test EDC APB communication for column harvesting in noc2axi tiles.

    This test demonstrates column harvesting where a complete column (all rows in that column)
    is harvested instead of a row. The key difference from row harvesting:
    - X coordinates are adjusted instead of Y coordinates
    - Grid size_x is reduced instead of size_y
    - Each column's APB master does different configuration based on its position relative to harvested column
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

    # Get noc2axi coordinates
    noc2axi_coords = (
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)
    )

    # Test each available EDC APB interface (one per noc2axi)
    for apb_master in range(min(tb.config.num_apb, len(noc2axi_coords))):
        tb.log.info(
            f"Testing EDC APB master {apb_master} - noc2axi at {noc2axi_coords[apb_master] if apb_master < len(noc2axi_coords) else 'N/A'}"
        )

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
            tb.log.info(
                f"  EDC Version: {edc_version_super:1d}.{edc_version_major:1d}.{edc_version_minor:1d}"
            )

        except Exception as e:
            assert False, f"Failed to read BIU ID from EDC APB master {apb_master}: {e}"

        # Read initial status register
        status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        tb.log.info(f"EDC APB Master {apb_master} - Initial Status: 0x{status:08x}")

        # Check for fatal errors in initial status
        if await edc_check_fatal_errors(tb, apb_master, status):
            assert False, (
                f"Fatal error detected in initial status - APB master {apb_master}"
            )

        # Enable all interrupts
        await tb.write_edc_apb_register(apb_master, BIU_IRQ_EN_REG, 0xBB)

        # Read back interrupt enable register to verify
        irq_en_readback = await tb.read_edc_apb_register(apb_master, BIU_IRQ_EN_REG)
        tb.log.info(
            f"EDC APB Master {apb_master} - IRQ Enable readback: 0x{irq_en_readback:08x}"
        )

        # Test control register read/write
        ctrl_readback = await tb.read_edc_apb_register(apb_master, BIU_CTRL_REG)
        tb.log.info(
            f"EDC APB Master {apb_master} - Control register: 0x{ctrl_readback:08x}"
        )

    enable_muxes_task = []
    for apb_master in range(min(tb.config.num_apb, len(noc2axi_coords))):
        tb.log.info(f"Enabling EDC muxes via APB master {apb_master}")

        enable_mux_task = cocotb.start_soon(edc_enable_all_edc_muxes(tb, apb_master))
        enable_muxes_task.append((apb_master, enable_mux_task))

    tb.log.info("Waiting for EDC mux enabling to complete...")

    # Process each enable mux task with timeout

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
        except TimeoutError:
            tb.log.error(
                f"EDC mux enabling operation timed out for APB master {apb_master} (30 seconds timeout)"
            )
            raise
        except Exception as e:
            tb.log.error(
                f"Exception in EDC mux enabling for APB master {apb_master}: {e}"
            )
            raise

    (
        tensix_coords_harvested,
        dispatch_coords_harvested,
        noc2axi_coords_harvested,
        tensix_coords,
        dispatch_coords,
        noc2axi_coords,
        harvest_target_columns,
    ) = await edc_do_random_harvesting(tb, harvest_dispatch_columns=False)

    disable_muxes_task = []
    for apb_master in range(min(tb.config.num_apb, len(noc2axi_coords))):
        tb.log.info(f"Disabling EDC muxes via APB master {apb_master}")

        disable_mux_task = cocotb.start_soon(
            edc_disable_edc_muxes(
                tb, apb_master, harvested_columns=harvest_target_columns
            )
        )
        disable_muxes_task.append((apb_master, disable_mux_task))

    tb.log.info("Waiting for EDC mux disabling to complete...")

    # Process each disable mux task with timeout

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
        except TimeoutError:
            tb.log.error(
                f"EDC mux disabling operation timed out for APB master {apb_master} (30 seconds timeout)"
            )
            raise
        except Exception as e:
            tb.log.error(
                f"Exception in EDC mux disabling for APB master {apb_master}: {e}"
            )
            raise

    tb.log.info(
        f"TB config size_x after harvest: {tb.config.size_x}, size_y: {tb.config.size_y}"
    )

    # Define test parameters
    default_master = tb.default_master

    # Define all active coordinates (before harvesting)
    all_active_coords = tensix_coords + dispatch_coords

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

    all_active_coords_harvested = tensix_coords_harvested + dispatch_coords_harvested

    # Identify available tiles after harvest
    for host_x, host_y in noc2axi_coords_harvested:
        tb.log.info(f"NOC2AXI post-harvest coordinates: {host_x}, {host_y}")
    for host_x, host_y in dispatch_coords_harvested:
        tb.log.info(f"DISPATCH_W post-harvest coordinates: {host_x}, {host_y}")
    for host_x, host_y in tensix_coords_harvested:
        tb.log.info(f"TENSIX post-harvest coordinates: {host_x}, {host_y}")
    for host_x, host_y in all_active_coords_harvested:
        tb.log.info(f"All active coordinates after harvest: {host_x}, {host_y}")

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

    waiters = []
    # Only monitor scratches on active Tensix/DM cores (skip harvested column)
    for x, y in all_active_coords:
        if x in harvest_target_columns:
            continue  # Skip harvested column tiles
        waiters.append(cocotb.start_soon(tb.monitor_dm_scratch(x, y)))

    await tb.release_dm_core_reset()
    tb.log.info("DM core reset released for all host tiles.")

    while waiters:
        await with_timeout(waiters.pop(0), 10_000, "ns")
        # tb.log.error("A DM core have not finished in time.")

    tb.log.info("Sanity EDC Column Harvesting Binary Finished!")

    # -----------------------------------------------------------------------------------------
    # Verify cross-column traffic across harvested column
    # -----------------------------------------------------------------------------------------

    # Critical test: Verify that traffic can route ACROSS the harvested column
    # Use AXI master from one side to access tiles on the other side of the harvested column
    tb.log.info("Starting cross-column traffic validation across harvested column")

    # If multiple columns harvested, pick the first one for testing
    if not harvest_target_columns:
        tb.log.warning("No columns were harvested, skipping cross-column test")
    else:
        test_harvest_column = harvest_target_columns[0]
        tb.log.info(f"Testing cross-column traffic for harvested column {test_harvest_column}")

        # Determine which columns are on left and right of harvest
        left_columns = [x for x in range(4) if x < test_harvest_column and x not in harvest_target_columns]
        right_columns = [x for x in range(4) if x > test_harvest_column and x not in harvest_target_columns]

        if not left_columns or not right_columns:
            tb.log.warning(
                f"Cannot perform cross-column test - harvested column {test_harvest_column} is at edge (no columns on one side)"
            )
        else:
            # Test from left to right: Use leftmost AXI master to access rightmost tile
            source_axi_master = left_columns[0]  # Leftmost AXI master (physical coordinate)
            target_tile_x_physical = right_columns[
                -1
            ]  # Rightmost column (physical coordinate)
            target_tile_y = 0  # Bottom row

            # Calculate logical coordinate after harvest
            # Tiles to the right of harvested column have their X coordinate decremented
            num_harvested_columns_left = sum(
                1 for col in harvest_target_columns if col < target_tile_x_physical
            )
            target_tile_x_logical = target_tile_x_physical - num_harvested_columns_left

            tb.log.info(
                f"Cross-column test: Physical target tile ({target_tile_x_physical}, {target_tile_y}) -> Logical coordinate ({target_tile_x_logical}, {target_tile_y})"
            )

            # Ensure target tile exists (using physical coordinates for check)
            if (target_tile_x_physical, target_tile_y) in tensix_coords:
                tb.log.info(
                    f"Cross-column test: AXI master {source_axi_master} (column {source_axi_master}) accessing tile at logical ({target_tile_x_logical}, {target_tile_y})"
                )
                tb.log.info(f"  Physical tile: ({target_tile_x_physical}, {target_tile_y})")
                tb.log.info(
                    f"  Traffic must route ACROSS harvested column {test_harvest_column}"
                )

                # Test data
                cross_test_values = [0xDE, 0xAD, 0xBE, 0xEF]
                cross_test_base_addr = 0x200000  # 2MB offset

                async def test_cross_column_traffic(
                    src_master, dst_x, dst_y, values, base_addr
                ):
                    """Test traffic routing across harvested column"""
                    tb.log.info(
                        f"AXI master {src_master}: STARTING cross-column traffic test to tile ({dst_x}, {dst_y})"
                    )
                    try:
                        # Write test values
                        write_tasks = []
                        for i, value in enumerate(values):
                            addr = base_addr + (i * 4)
                            data = value.to_bytes(4, byteorder="little")
                            tb.log.info(
                                f"AXI master {src_master}: Cross-column write {i}: value 0x{value:02x} to tile ({dst_x},{dst_y}) addr 0x{addr:08x}"
                            )
                            write_task = tb.noc_write(src_master, dst_x, dst_y, addr, data)
                            write_tasks.append(write_task)

                        # Wait for all writes
                        for i, task in enumerate(write_tasks):
                            await task
                            tb.log.info(
                                f"AXI master {src_master}: Cross-column write {i} completed"
                            )

                        tb.log.info(
                            f"AXI master {src_master}: All cross-column writes completed"
                        )

                        # Read back and verify
                        all_passed = True
                        for i, expected_value in enumerate(values):
                            addr = base_addr + (i * 4)
                            read_data = await tb.noc_read(src_master, dst_x, dst_y, addr, 4)

                            # Convert to integer
                            if isinstance(read_data, (bytes, bytearray)):
                                read_value = int.from_bytes(read_data, byteorder="little")
                            elif isinstance(read_data, tuple):
                                read_bytes = bytes(read_data)
                                read_value = int.from_bytes(read_bytes, byteorder="little")
                            else:
                                tb.log.error(
                                    f"AXI master {src_master}: Unexpected read data type: {type(read_data)}"
                                )
                                all_passed = False
                                continue

                            if read_value == expected_value:
                                tb.log.info(
                                    f"AXI master {src_master}: Cross-column read {i} PASSED - got 0x{read_value:02x}"
                                )
                            else:
                                tb.log.error(
                                    f"AXI master {src_master}: Cross-column read {i} FAILED - expected 0x{expected_value:02x}, got 0x{read_value:02x}"
                                )
                                all_passed = False

                        if all_passed:
                            tb.log.info(
                                f"AXI master {src_master}: Cross-column traffic test PASSED for tile ({dst_x}, {dst_y})"
                            )
                            return True
                        else:
                            tb.log.error(
                                f"AXI master {src_master}: Cross-column traffic test FAILED for tile ({dst_x}, {dst_y})"
                            )
                            return False

                    except Exception as e:
                        tb.log.error(
                            f"AXI master {src_master}: Cross-column traffic test FAILED with exception: {e}"
                        )
                        import traceback

                        tb.log.error(
                            f"AXI master {src_master}: Exception traceback: {traceback.format_exc()}"
                        )
                        return False

                # Run the cross-column traffic test using LOGICAL coordinates
                try:
                    cross_test_result = await with_timeout(
                        test_cross_column_traffic(
                            source_axi_master,
                            target_tile_x_logical,
                            target_tile_y,
                            cross_test_values,
                            cross_test_base_addr,
                        ),
                        2_000,
                        "ns",
                    )

                    if cross_test_result:
                        tb.log.info(
                            f"Cross-column traffic validation PASSED - Traffic successfully routed across harvested column {test_harvest_column}"
                        )
                    else:
                        tb.log.error("Cross-column traffic validation FAILED")
                        assert False, "Cross-column traffic test failed"

                except TimeoutError:
                    tb.log.error("Cross-column traffic test timed out")
                    assert False, "Cross-column traffic test timed out"
                except Exception as e:
                    tb.log.error(f"Cross-column traffic test exception: {e}")
                    assert False, f"Cross-column traffic test exception: {e}"

            else:
                tb.log.warning(
                    f"Target tile ({target_tile_x_physical}, {target_tile_y}) not available for cross-column test"
                )

    # -----------------------------------------------------------------------------------------
    # Verify that columns beside harvested column are still accessible
    # -----------------------------------------------------------------------------------------

    # Final check to ensure non-harvested columns are accessible after harvesting
    tb.log.info(
        "Starting L1 memory write/read test on non-harvested column tiles in parallel"
    )

    if not tensix_coords_harvested:
        tb.log.error("No Tensix tiles found for L1 memory test")
    else:
        # Test tiles from non-harvested columns (pick one tile per remaining column for verification)
        test_tiles = [
            (x, 0)
            for x in range(4)
            if x not in harvest_target_columns and (x, 0) in tensix_coords
        ]

        tb.log.info(f"Testing L1 memory on tiles: {test_tiles}")

        # Prepare test data - 3 integer values
        test_values = [0xAA, 0x55, 0xCC]

        # L1 memory test base address
        l1_test_base_addr = 0x100000  # 1MB offset into L1 memory

        # Perform write/read test
        l1_test_tasks = []

        for tile_x_physical, tile_y in test_tiles:
            # tile_x_physical is the PHYSICAL column index (0, 1, 3 if column 2 harvested)
            # AXI master selection uses PHYSICAL index
            axi_master = tile_x_physical  # AXI masters are indexed by physical column

            # Calculate LOGICAL coordinate for NOC access
            # Tiles to the right of harvested column have their X coordinate decremented
            num_harvested_left = sum(
                1 for col in harvest_target_columns if col < tile_x_physical
            )
            tile_x_logical = tile_x_physical - num_harvested_left

            tb.log.info(
                f"L1 test: Physical tile ({tile_x_physical}, {tile_y}) -> Logical ({tile_x_logical}, {tile_y}), AXI master {axi_master}"
            )

            # Ensure we don't exceed available AXI masters
            if axi_master >= min(tb.config.num_noc2axi, len(noc2axi_coords)):
                tb.log.warning(
                    f"Skipping tile ({tile_x_physical}, {tile_y}) - AXI master {axi_master} not available"
                )
                continue

            # Only test if this tile exists as a tensix tile (check using physical coordinates)
            if (tile_x_physical, tile_y) in tensix_coords:
                tb.log.info(
                    f"Starting L1 write/read test for physical tile ({tile_x_physical}, {tile_y}), logical ({tile_x_logical}, {tile_y}) using AXI master {axi_master}"
                )

                # Create test task for this tile
                async def test_tile_l1_memory(
                    x_phys, x_log, y, values, base_addr, master
                ):
                    tb.log.info(
                        f"AXI master {master}: STARTING L1 test for physical tile ({x_phys}, {y}), logical ({x_log}, {y})"
                    )
                    try:
                        # Write test values to L1 memory using LOGICAL coordinates
                        write_tasks = []
                        for i, value in enumerate(values):
                            addr = base_addr + (i * 4)
                            data = value.to_bytes(4, byteorder="little")
                            tb.log.info(
                                f"AXI master {master}: Creating write task {i}: value {value} (0x{value:02x}) to logical tile ({x_log},{y}) addr 0x{addr:08x}"
                            )
                            write_task = tb.noc_write(master, x_log, y, addr, data)
                            write_tasks.append(write_task)

                        # Wait for all writes to complete
                        for i, task in enumerate(write_tasks):
                            await task

                        tb.log.info(
                            f"AXI master {master}: All writes completed for logical tile ({x_log}, {y})"
                        )

                        # Read back and verify each value using LOGICAL coordinates
                        all_passed = True

                        for i, expected_value in enumerate(values):
                            addr = base_addr + (i * 4)

                            read_data = await tb.noc_read(master, x_log, y, addr, 4)

                            # Convert read data back to integer
                            if isinstance(read_data, (bytes, bytearray)):
                                read_value = int.from_bytes(
                                    read_data, byteorder="little"
                                )
                            elif isinstance(read_data, tuple):
                                read_bytes = bytes(read_data)
                                read_value = int.from_bytes(
                                    read_bytes, byteorder="little"
                                )
                            else:
                                tb.log.error(
                                    f"AXI master {master}: Unexpected read data type: {type(read_data)}"
                                )
                                all_passed = False
                                continue

                            if read_value == expected_value:
                                tb.log.info(f"AXI master {master}: Value {i} PASSED")
                            else:
                                tb.log.error(
                                    f"AXI master {master}: Value {i} FAILED - expected {expected_value}, got {read_value}"
                                )
                                all_passed = False

                        if all_passed:
                            tb.log.info(
                                f"AXI master {master}: L1 memory test PASSED for physical tile ({x_phys}, {y}), logical ({x_log}, {y})"
                            )
                            return True
                        else:
                            tb.log.error(
                                f"AXI master {master}: L1 memory test FAILED for physical tile ({x_phys}, {y}), logical ({x_log}, {y})"
                            )
                            return False

                    except Exception as e:
                        tb.log.error(
                            f"AXI master {master}: L1 memory test FAILED for physical tile ({x_phys}, {y}) with exception: {e}"
                        )
                        import traceback

                        tb.log.error(
                            f"AXI master {master}: Exception traceback: {traceback.format_exc()}"
                        )
                        return False

                # Start the test task for this tile with its corresponding master
                task = cocotb.start_soon(
                    test_tile_l1_memory(
                        tile_x_physical,
                        tile_x_logical,
                        tile_y,
                        test_values,
                        l1_test_base_addr,
                        axi_master,
                    )
                )
                l1_test_tasks.append((tile_x_physical, tile_y, axi_master, task))

        # Wait for all L1 memory tests to complete
        tb.log.info(
            f"Waiting for {len(l1_test_tasks)} parallel L1 memory tests to complete..."
        )
        all_tests_passed = True

        for tile_x, tile_y, axi_master, test_task in l1_test_tasks:
            try:
                test_result = await with_timeout(test_task, 2_000, "ns")
                if not test_result:
                    all_tests_passed = False
                    tb.log.error(
                        f"L1 memory test failed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}"
                    )
                else:
                    tb.log.info(
                        f"L1 memory test passed for tile ({tile_x}, {tile_y}) using AXI master {axi_master}"
                    )
            except TimeoutError:
                all_tests_passed = False
                tb.log.error(
                    f"L1 memory test timed out for tile ({tile_x}, {tile_y}) using AXI master {axi_master}"
                )
            except Exception as e:
                all_tests_passed = False
                tb.log.error(
                    f"L1 memory test exception for tile ({tile_x}, {tile_y}) using AXI master {axi_master}: {e}"
                )

        if all_tests_passed:
            tb.log.info(
                "All L1 memory write/read tests PASSED on non-harvested columns"
            )
        else:
            tb.log.error(
                "Some L1 memory write/read tests FAILED on non-harvested columns"
            )
            assert False, "L1 memory test failures detected on non-harvested columns"

    tb.log.info("EDC Column Harvesting Sanity Test Completed Successfully.")
