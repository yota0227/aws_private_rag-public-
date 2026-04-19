import os
import logging
import random
import itertools
from typing import Tuple, List, Dict, Optional, Callable, Awaitable
import cocotb
from cocotb.triggers import ClockCycles, Timer
from cocotb.handle import Deposit, Release, Force
from cocotbext.axi import AxiRam, AxiBus
from cocotb_bus.bus import Bus
from tests.utils.test_utils import load_binary_data
from tests.utils.addr_pinger_handler import PingerInterface, PingerError
from tests.utils.coco_tensix_api import demoTB, TileType
from tests.addr_pinger import *

# Constants
CACHE_LINE_SIZE = 64
TRANSFER_SIZE = 4 * 1024  # 4KB per transfer


async def verify_data_transfer(
    tb,
    default_master,
    host_tiles,
    original_base_addr,
    readback_base_addr,
    total_data_size,
    transfer_size,
):
    """
    Verify data transfer by comparing original written data with read-back data.

    Args:
        tb: Testbench instance
        default_master: NOC master for memory operations
        host_tiles: List of host tile coordinates
        original_base_addr: Base address where original data was written
        readback_base_addr: Base address where read-back data was written
        total_data_size: Total size of data to verify per tile
        transfer_size: Size of each transfer chunk

    Returns:
        bool: True if all data matches, False otherwise
    """
    tb.log.info("Starting data verification...")

    all_tiles_pass = True

    for host_x, host_y in host_tiles:
        tb.log.info(f"Verifying data for tile ({host_x}, {host_y})")

        try:
            # Read original data section
            tb.log.info(f"Reading original data from 0x{original_base_addr:08x}, size {total_data_size}")
            original_data = await tb.noc_read(
                default_master, host_x, host_y, original_base_addr, total_data_size
            )

            # Read read-back data section
            tb.log.info(f"Reading read-back data from 0x{readback_base_addr:08x}, size {total_data_size}")
            readback_data = await tb.noc_read(
                default_master, host_x, host_y, readback_base_addr, total_data_size
            )

            # Convert to byte arrays for comparison
            original_bytes = original_data.data if hasattr(original_data, 'data') else original_data
            readback_bytes = readback_data.data if hasattr(readback_data, 'data') else readback_data

            if len(original_bytes) != len(readback_bytes):
                tb.log.error(f"Tile ({host_x}, {host_y}): Size mismatch - original: {len(original_bytes)}, readback: {len(readback_bytes)}")
                all_tiles_pass = False
                continue

            # Compare data in chunks for better error reporting
            chunk_size = transfer_size
            total_chunks = (total_data_size + chunk_size - 1) // chunk_size
            mismatches = 0

            for chunk_idx in range(total_chunks):
                start_offset = chunk_idx * chunk_size
                end_offset = min(start_offset + chunk_size, total_data_size)

                orig_chunk = original_bytes[start_offset:end_offset]
                read_chunk = readback_bytes[start_offset:end_offset]

                if orig_chunk != read_chunk:
                    mismatches += 1
                    tb.log.error(f"Tile ({host_x}, {host_y}): Data mismatch in chunk {chunk_idx} (offset 0x{start_offset:08x})")

                    # Show first few bytes of mismatch for debugging
                    for byte_idx in range(min(16, len(orig_chunk))):
                        if byte_idx < len(read_chunk) and orig_chunk[byte_idx] != read_chunk[byte_idx]:
                            tb.log.error(f"  Byte {byte_idx}: expected 0x{orig_chunk[byte_idx]:02x}, got 0x{read_chunk[byte_idx]:02x}")

                    # Don't spam too many error messages
                    if mismatches >= 5:
                        tb.log.error(f"Tile ({host_x}, {host_y}): Too many mismatches, stopping detailed comparison")
                        break

            if mismatches == 0:
                tb.log.info(f"Tile ({host_x}, {host_y}): Data verification PASSED - all {total_chunks} chunks match")
            else:
                tb.log.error(f"Tile ({host_x}, {host_y}): Data verification FAILED - {mismatches}/{total_chunks} chunks have mismatches")
                all_tiles_pass = False

        except Exception as e:
            tb.log.error(f"Tile ({host_x}, {host_y}): Exception during data verification: {e}")
            all_tiles_pass = False

    if all_tiles_pass:
        tb.log.info("=== DATA VERIFICATION PASSED ===")
        tb.log.info("All tiles have matching original and read-back data")
    else:
        tb.log.error("=== DATA VERIFICATION FAILED ===")
        tb.log.error("One or more tiles have data mismatches")

    return all_tiles_pass


async def trinity_performance(
    dut,
    bin_path,
    cores_per_host,
    number_of_cmd_buffers,
    transfer_size,
    number_of_transfers,
    total_size,
    target_memory_start_addr,
    axi_read_data_latency,
    axi_write_response_latency,
    multi_channel
):
    """
    Multi-host address pinger test using optimized batched operations.
    Each host tile uses cores_per_host cores to ping other tiles and verify data transfers.

    Args:
        dut: Device under test
        bin_path: Path to pinger binary
        cores_per_host: Number of cores per host tile
        transfer_size: Size of each transfer chunk in bytes
        total_size: Total size of data to be distributed across all cores per host
        axi_read_data_latency: Latency cycles for AXI R (read data) channel
        axi_write_response_latency: Latency cycles for AXI B (write response) channel
    """

    tb = demoTB(dut)

    await tb.init_and_reset()
    tb.log.info("Testbench initialized and DUT reset.")

    # Load binary
    try:
        binary_data = load_binary_data(bin_path=bin_path)
        tb.log.info(f"Loaded pinger binary from {bin_path} ({len(binary_data)} bytes)")
    except FileNotFoundError:
        tb.log.error(f"Binary not found at {bin_path}.")
        raise

    # Identify available tiles
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    host_tiles = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    dram_tiles = tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)

    active_tensix_coords = tensix_coords

    tb.log.info(f"Found {len(host_tiles)} host tiles: {host_tiles}")
    
    # All potential destinations (including hosts themselves)
    dest_tiles = sorted(list(set(dram_tiles)))
    
    if not host_tiles:
        tb.log.error("No Tensix or Dispatch tiles found for hosting the pinger.")
        raise RuntimeError("No suitable host tiles available.")
    
    if not dest_tiles:
        tb.log.error("No destination tiles found for pinger test.")
        raise RuntimeError("No suitable destination tiles available.")
    
    # Define test parameters
    default_master = tb.default_master
    
    # Load pinger binary to all host tiles
    load_binary_tasks = []
    for host_x, host_y in host_tiles:
        tb.log.info(f"Loading pinger binary to Host Tile ({host_x},{host_y}) at address 0x0")
        load_binary_tasks.append(
            tb.noc_write_nonblocking(default_master, host_x, host_y, 0x0, binary_data)
        )

    # Wait for all binary loading to complete before proceeding
    tb.log.info("Waiting for binary loading to complete...")
    for task in load_binary_tasks:
        await task
    tb.log.info("Binary loading completed for all host tiles.")
    
    # Memory read/write adapter functions for pinger interface
    async def read_memory(address: int, length: int, x: int, y: int) -> bytes:
        read_result = await tb.noc_read(default_master, x, y, address, length)
        return read_result.data
    
    async def write_memory(address: int, data: bytes, x: int, y: int) -> None:
        await tb.noc_write(default_master, x, y, address, data)

    # Wait for all pattern data writes to complete
    await tb.noc_wait_writes(default_master)
    tb.log.info("All test patterns written. Starting pinger execution.")

    # Write configuration values to memory for firmware to read
    config_base_addr = 0x100000  # 1MB first address for test configurations
    config_values = [
        transfer_size,              # TRANSFER_SIZE
        number_of_transfers,        # NUM_TRANSFERS
        cores_per_host,             # NUM_CPUS
        number_of_cmd_buffers,      # NUM_BUFFERS
        target_memory_start_addr,   # BLOCK_START_ADDRESS
        2 * 1024 * 1024,            # LOCAL_L1_ADDRESS - 2MB
        multi_channel,              # MULTI_CHANNEL_FLAG
        tb.config.size_x,           # CHIP_SIZE_X
        tb.config.size_y            # CHIP_SIZE_Y
    ]

    tb.log.info("Writing configuration values to memory...")
    write_tasks = []
    for host_x, host_y in host_tiles:
        for i, value in enumerate(config_values):
            addr = config_base_addr + (i * 8)  # 8 bytes per uint64_t
            data = value.to_bytes(
                8, byteorder="little"
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

    # total_size = transfer_size * 80 * 8 * 3 / 1024

    # # Start monitoring each host tile
    # for host_coord in host_tiles:
    #     host_x, host_y = host_coord  # Unpack the coordinate tuple
    #     cocotb.start_soon(tb.monitor_dm_scratch(host_x, host_y))

    waiters = []
    # Only monitor scratches on active Tensix/DM cores
    for x, y in active_tensix_coords:
        waiters.append(
            cocotb.start_soon(tb.monitor_dm_scratch(x, y))
        )

    # Release reset for all DM cores on all host tiles
    await tb.release_dm_core_reset()
    tb.log.info("DM core reset released for all host tiles.")

    from cocotb.triggers import with_timeout
    while waiters:
        await with_timeout(waiters.pop(0), 900_000, 'ns')
    
    # Final clock cycles and test result
    await ClockCycles(dut.ai_clk, 8)

    # Verify data transfer integrity
    # You'll need to set these addresses based on your firmware's memory layout
    original_data_addr = 2 * 1024 * 1024  # TEST_LOCAL_L1_ADDRESS from firmware
    readback_data_addr = original_data_addr + (transfer_size * number_of_transfers * cores_per_host * number_of_cmd_buffers)  # Original + total transfer size
    total_transfer_size = transfer_size * number_of_transfers * cores_per_host * number_of_cmd_buffers  # transfer_size * NUM_TRANSFERS * NUM_CPUS * NUM_BUFFERS

    data_verification_passed = await verify_data_transfer(
        tb, default_master, host_tiles,
        original_data_addr, readback_data_addr,
        total_transfer_size, transfer_size
    )

    if data_verification_passed:
        tb.log.info("Trinity performance test PASSED!")
    else:
        tb.log.error("Trinity performance test FAILED. Data mismatch detected.")
        raise RuntimeError("Trinity performance test failed")

    # Calculate and display throughput
    tb.log.info("Write timing measurement ready, calculating write throughput...")

    # Read write timestamp values directly as signals
    first_write_data_time = tb.dut.noc2axi_perf_monitor_0.first_write_data_timestamp.value
    last_write_data_time = tb.dut.noc2axi_perf_monitor_0.last_write_data_timestamp.value
    minimum_write_round_trip_latency = tb.dut.noc2axi_perf_monitor_0.write_min_latency.value
    maximum_write_round_trip_latency = tb.dut.noc2axi_perf_monitor_0.write_max_latency.value
    # average_write_round_trip_latency = tb.dut.write_avg_latency.value

    tb.log.info(f"First write request timestamp: {first_write_data_time} ns")
    tb.log.info(f"Last write response timestamp: {last_write_data_time} ns")
    tb.log.info(f"Minimum write rount trip latency: {minimum_write_round_trip_latency} ns")
    tb.log.info(f"Maximum write rount trip latency: {maximum_write_round_trip_latency} ns")
    # tb.log.info(f"Average write rount trip latency: {average_write_round_trip_latency} ns")

    # Calculate total data transferred
    total_hosts = len(host_tiles)
    total_destinations = len(dest_tiles)
    total_data_bytes = total_hosts * total_destinations * total_size

    round_trip_latency_en = tb.dut.noc2axi_perf_monitor_0.round_trip_latency_monitor_enabled.value

    # Calculate write time difference
    write_time_diff_ns = last_write_data_time - first_write_data_time + 1

    if write_time_diff_ns > 0:
        write_throughput_gbps = total_data_bytes / write_time_diff_ns

        tb.log.info("=== WRITE THROUGHPUT CALCULATION ===")
        tb.log.info(f"Total data written: ({total_data_bytes / (1024):.2f} KB)")
        tb.log.info(f"Write time: ({write_time_diff_ns} ns)")
        tb.log.info(f"Write throughput: {write_throughput_gbps:.4f} B/cycle")
        tb.log.info("======================================")
    else:
        tb.log.warning("Invalid time difference for throughput calculation")

    # Calculate and display read throughput

    tb.log.info("Read timing measurement ready, calculating read throughput...")

    # Read read timestamp values directly as signals
    first_read_data_time = tb.dut.noc2axi_perf_monitor_0.first_rdata_timestamp.value
    last_read_data_time = tb.dut.noc2axi_perf_monitor_0.last_rdata_timestamp.value
    minimum_read_round_trip_latency = tb.dut.noc2axi_perf_monitor_0.read_min_latency.value
    maximum_read_round_trip_latency = tb.dut.noc2axi_perf_monitor_0.read_max_latency.value
    # average_read_round_trip_latency = tb.dut.read_avg_latency.value

    tb.log.info(f"First read request timestamp: {first_read_data_time} ns")
    tb.log.info(f"Last read data timestamp: {last_read_data_time} ns")
    tb.log.info(f"Minimum read rount trip latency: {minimum_read_round_trip_latency} ns")
    tb.log.info(f"Maximum read rount trip latency: {maximum_read_round_trip_latency} ns")
    # tb.log.info(f"Average write rount trip latency: {average_read_round_trip_latency} ns")

    # Calculate total data transferred (assuming same amount of data is read as written)
    total_hosts = len(host_tiles)
    total_destinations = len(dest_tiles)
    total_data_bytes = total_hosts * total_destinations * total_size

    # Calculate read time difference
    read_time_diff_ns = last_read_data_time - first_read_data_time + 1

    if read_time_diff_ns > 0:
        read_throughput_gbps = total_data_bytes / read_time_diff_ns

        tb.log.info("=== READ THROUGHPUT CALCULATION ===")
        tb.log.info(f"Total data read: ({total_data_bytes / (1024):.2f} KB)")
        tb.log.info(f"Read time: ({read_time_diff_ns} ns)")
        tb.log.info(f"Read throughput: {read_throughput_gbps:.4f} B/cycle")
        tb.log.info("===================================")
    else:
        tb.log.warning("Invalid read time difference for throughput calculation")

    # Save results to file
    try:
        channel_usage = "sc" if multi_channel == 0 else f"mc{multi_channel}"
        results_file = f"perf_res_{total_size}_{transfer_size}_{channel_usage}_{axi_read_data_latency}_{axi_write_response_latency}.txt"

        with open(results_file, 'w') as f:
            f.write("=== NOC2AXI Performance Results ===\n")
            f.write(f"Test: Multi-host pinger performance test\n")
            f.write(f"Cores per host: {cores_per_host}\n")
            f.write(f"Host tiles: {len(host_tiles)}\n")
            f.write(f"Destination tiles: {len(dest_tiles)}\n")
            f.write(f"Transfer size per chunk: {transfer_size} bytes\n")
            f.write(f"Total size per host: {total_size} bytes\n")
            f.write(f"Total data transferred: {total_data_bytes} bytes ({total_data_bytes / 1024:.2f} KB)\n")
            f.write("\n")

            # Write results
            f.write("WRITE PERFORMANCE:\n")
            if 'first_write_data_time' in locals() and 'last_write_data_time' in locals():
                f.write(f"  Noc2Axi write buffer latency: {axi_write_response_latency} cycles\n")
                f.write(f"  First write request timestamp: {first_write_data_time} ns\n")
                f.write(f"  Last write response timestamp: {last_write_data_time} ns\n")
                if round_trip_latency_en:
                    f.write(f"  Minimum write round trip latency: {minimum_write_round_trip_latency} ns\n")
                    f.write(f"  Maximum write round trip latency: {maximum_write_round_trip_latency} ns\n")
                if 'write_time_diff_ns' in locals() and write_time_diff_ns > 0:
                    f.write(f"  Write latency: {write_time_diff_ns} ns\n")
                    f.write(f"  Write throughput: {write_throughput_gbps} B/cycle\n")
                else:
                    f.write("  Write latency: N/A (invalid timing)\n")
                    f.write("  Write throughput: N/A\n")
            else:
                f.write("  Write measurements: N/A (no data captured)\n")
            f.write("\n")

            # Read results
            f.write("READ PERFORMANCE:\n")
            if 'first_read_data_time' in locals() and 'last_read_data_time' in locals():
                f.write(f"  Noc2Axi read buffer latency: {axi_read_data_latency} cycles\n")
                f.write(f"  First read request timestamp: {first_read_data_time} ns\n")
                f.write(f"  Last read data timestamp: {last_read_data_time} ns\n")
                if round_trip_latency_en:
                    f.write(f"  Minimum read round trip latency: {minimum_read_round_trip_latency} ns\n")
                    f.write(f"  Maximum read round trip latency: {maximum_read_round_trip_latency} ns\n")
                if 'read_time_diff_ns' in locals() and read_time_diff_ns > 0:
                    f.write(f"  Read latency: {read_time_diff_ns} ns\n")
                    f.write(f"  Read throughput: {read_throughput_gbps} B/cycle\n")
                else:
                    f.write("  Read latency: N/A (invalid timing)\n")
                    f.write("  Read throughput: N/A\n")
            else:
                f.write("  Read measurements: N/A (no data captured)\n")

            f.write("\n")
            f.write("=====================================\n")

        tb.log.info(f"Performance results saved to {os.path.abspath(results_file)}")

    except Exception as e:
        tb.log.warning(f"Could not save results to file: {e}")


