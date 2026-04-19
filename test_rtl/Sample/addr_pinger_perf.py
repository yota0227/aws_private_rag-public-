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
TRANSFER_SIZE = 1024  # 1KB per transfer
TOTAL_SIZE = 128 * 1024  # 128KB total

async def addr_pinger_perf(dut, pinger_bin_path: str = None, cores_per_host: int = PingerInterface.NUM_CORES, transfer_size: int = TRANSFER_SIZE, total_size: int = TOTAL_SIZE, axi_read_data_latency: int = 1, axi_write_response_latency: int = 1):
    """
    Multi-host address pinger test using optimized batched operations.
    Each host tile uses cores_per_host cores to ping other tiles and verify data transfers.

    Args:
        dut: Device under test
        pinger_bin_path: Path to pinger binary
        cores_per_host: Number of cores per host tile
        transfer_size: Size of each transfer chunk in bytes
        total_size: Total size of data to be distributed across all cores per host
        axi_read_data_latency: Latency cycles for AXI R (read data) channel
        axi_write_response_latency: Latency cycles for AXI B (write response) channel
    """

    tb = demoTB(dut)

    # Calculate per-core data allocation
    bytes_per_core = total_size // cores_per_host
    transfers_per_core_per_dest = bytes_per_core // transfer_size

    tb.log.info(f"Starting multi-host addr_pinger_perf test with {cores_per_host} cores per host")
    tb.log.info(f"Total size: {total_size} bytes, distributed as {bytes_per_core} bytes per core")
    tb.log.info(f"Transfer size: {transfer_size} bytes, {transfers_per_core_per_dest} transfers per core per destination")

    await tb.init_and_reset()
    tb.log.info("Testbench initialized and DUT reset.")

    # Load pinger binary
    try:
        binary_data = load_binary_data(bin_path=pinger_bin_path)
        tb.log.info(f"Loaded pinger binary from {pinger_bin_path} ({len(binary_data)} bytes)")
    except FileNotFoundError:
        tb.log.error(f"Pinger binary not found at {pinger_bin_path}.")
        raise

    # Identify available tiles
    host_tiles = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W) + tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    dram_tiles = tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)


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
    
    # Allocate memory for the test
    memory_map = allocate_memory_for_multi_host_pinger(
        host_tiles,
        dest_tiles,
        cores_per_host,
        transfer_size,
        total_size,
        PingerInterface.PINGER_TEST_DATA_GLOBAL_START_ADDRESS,
        tb.log
    )
    
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
    
    # Create test patterns and prepare batched operations for each host/core
    host_test_data = {}  # host_coord -> core_id -> dest_coord -> pattern info
    pinger_interfaces = {}  # host_coord -> core_id -> pinger interface
    all_command_ids = {}   # host_coord -> core_id -> list of command ids

    tb.log.info("Preparing test patterns and operations...")
    setup_tasks = []
    for host_coord in host_tiles:
        for core_id in range(cores_per_host):
            setup_tasks.append(
                cocotb.start_soon(
                    prepare_host_core(
                        tb, host_coord, core_id, cores_per_host, memory_map, dest_tiles,
                        transfer_size, total_size, default_master, read_memory, write_memory
                    )
                )
            )

    setup_results = []
    for task in setup_tasks:
        result = await task
        if result:  # If it returns something (from prepare_host_core)
            setup_results.append(result)
    setup_tasks.clear()  # Clear the list to free up memory

    # Process results and populate dictionaries
    for result in setup_results:
        host_coord, core_id, pinger, test_data, command_ids = result
        
        # Initialize nested dictionaries if needed
        if host_coord not in pinger_interfaces:
            pinger_interfaces[host_coord] = {}
        if host_coord not in host_test_data:
            host_test_data[host_coord] = {}
        if host_coord not in all_command_ids:
            all_command_ids[host_coord] = {}
        
        # Populate the dictionaries    
        pinger_interfaces[host_coord][core_id] = pinger
        host_test_data[host_coord][core_id] = test_data
        all_command_ids[host_coord][core_id] = command_ids

    # Wait for all pattern data writes to complete
    await tb.noc_wait_writes(default_master)
    tb.log.info("All test patterns written. Starting pinger execution.")

    # Start monitoring each host tile
    for host_coord in host_tiles:
        host_x, host_y = host_coord  # Unpack the coordinate tuple
        cocotb.start_soon(tb.monitor_dm_scratch(host_x, host_y))

    # Add debug logging to see available host/core pairs
    tb.log.info(f"Available host coordinates: {list(pinger_interfaces.keys())}")
    for host_coord, cores in pinger_interfaces.items():
        tb.log.info(f"Host {host_coord} has cores: {list(cores.keys())}")

    # Release reset for all DM cores on all host tiles
    await tb.release_dm_core_reset()
    tb.log.info("DM core reset released for all host tiles.")

    # Wait and verify for each host/core
    all_hosts_successful = True

    # Process tiles in parallel for better efficiency
    verification_tasks = []

    # Only iterate over host/core pairs that we actually prepared
    for host_coord in pinger_interfaces:
        for core_id in pinger_interfaces[host_coord]:
            verification_tasks.append(
                cocotb.start_soon(
                    process_core_completion(
                        tb, host_coord, core_id, 
                        pinger_interfaces[host_coord][core_id],
                        all_command_ids[host_coord][core_id],
                        host_test_data[host_coord][core_id],
                        transfer_size
                    )
                )
            )
    
    # Wait for all cores to complete and gather results
    while verification_tasks:
        core_result = await verification_tasks.pop(0)
        if not core_result:
            all_hosts_successful = False
    
    # Final clock cycles and test result
    await ClockCycles(dut.ai_clk, 8)

    if all_hosts_successful:
        tb.log.info("Multi-host pinger test PASSED on all tiles!")
    else:
        tb.log.error("Multi-host pinger test FAILED.")
        raise RuntimeError("Multi-host pinger test failed on one or more host tiles.")

    # Calculate and display throughput
    tb.log.info("Write timing measurement ready, calculating write throughput...")

    # Read write timestamp values directly as signals
    first_write_data_time = tb.dut.noc2axi_perf_monitor_0.first_write_data_timestamp.value
    last_write_data_time = tb.dut.noc2axi_perf_monitor_0.last_write_data_timestamp.value
    minimum_write_round_trip_latency = tb.dut.noc2axi_perf_monitor_0.write_min_latency.value
    maximum_write_round_trip_latency = tb.dut.noc2axi_perf_monitor_0.write_max_latency.value

    tb.log.info(f"First write request timestamp: {first_write_data_time} ns")
    tb.log.info(f"Last write response timestamp: {last_write_data_time} ns")
    tb.log.info(f"Minimum write rount trip latency: {minimum_write_round_trip_latency} ns")
    tb.log.info(f"Maximum write rount trip latency: {maximum_write_round_trip_latency} ns")

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

    tb.log.info(f"First read request timestamp: {first_read_data_time} ns")
    tb.log.info(f"Last read data timestamp: {last_read_data_time} ns")
    tb.log.info(f"Minimum read rount trip latency: {minimum_read_round_trip_latency} ns")
    tb.log.info(f"Maximum read rount trip latency: {maximum_read_round_trip_latency} ns")

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
        results_file = f"perf_res_{total_size}_{transfer_size}_{cores_per_host}_{axi_read_data_latency}_{axi_write_response_latency}.txt"

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


