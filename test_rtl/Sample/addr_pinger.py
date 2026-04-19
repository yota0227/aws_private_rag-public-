import os
import logging
import random
from typing import Tuple, List, Dict, Optional, Callable, Awaitable
import cocotb
from cocotb.triggers import ClockCycles, Timer
from tests.utils.test_utils import load_binary_data
from tests.utils.addr_pinger_handler import PingerInterface, PingerError
from tests.utils.coco_tensix_api import demoTB, TileType

# Constants
CACHE_LINE_SIZE = 64
TRANSFER_SIZE = 128
TOTAL_SIZE = 1 * 1024

def allocate_memory_for_multi_host_pinger(
    host_coords: List[Tuple[int, int]],
    dest_coords: List[Tuple[int, int]],
    cores_per_host: int,
    transfer_size: int,
    total_size: int,
    start_address: int,
    tb_log: logging.Logger
) -> Dict[Tuple[int, int], Dict[str, int]]:
    """
    Allocates non-overlapping memory regions for multi-host pinger test.

    Args:
        host_coords: List of (x,y) coordinates for host tiles
        dest_coords: List of (x,y) coordinates for destination tiles
        cores_per_host: Number of cores per host tile (typically 8)
        transfer_size: Size of each data transfer chunk
        total_size: Total size of data to be distributed across all cores per host
        start_address: Global start address for allocation
        tb_log: Logger instance

    Returns:
        Memory map with allocated regions for each tile
    """
    tb_log.info(f"Multi-host pinger memory allocation starting at 0x{start_address:X}")
    
    # Identify all unique tiles involved in the test
    all_tiles = sorted(list(set(host_coords + dest_coords)))
    memory_map = {}
    
    # Current global address pointer for allocation
    current_address = start_address
    
    # Calculate and allocate memory for each tile
    for tile_coord in all_tiles:
        is_host = tile_coord in host_coords
        is_dest = tile_coord in dest_coords
        memory_map[tile_coord] = {}
        
        # Calculate host-local space (if this tile is a host)
        if is_host:
            # Each core on this host needs pattern + readback space for each destination
            # Total data is distributed across all cores, so each core gets total_size/cores_per_host per destination
            num_destinations = len(dest_coords) or 1  # Use 1 if empty (self-ping case)
            bytes_per_core = total_size // cores_per_host

            host_local_size = cores_per_host * num_destinations * 2 * bytes_per_core
            host_local_size = (host_local_size + CACHE_LINE_SIZE - 1) & ~(CACHE_LINE_SIZE - 1)  # Align
            memory_map[tile_coord]['host_local_base'] = current_address
            memory_map[tile_coord]['host_local_size'] = host_local_size
            current_address += host_local_size
            tb_log.info(f"Tile {tile_coord} (Host): Pattern/Readback area @0x{memory_map[tile_coord]['host_local_base']:X}, Size 0x{host_local_size:X} ({bytes_per_core}B per core)")
        
        # Calculate destination space (if this tile can be targeted)
        if is_dest:
            # Each destination needs space for pings from all hosts
            # Each host sends total_size bytes to this destination, distributed across all its cores
            total_hosts = len(host_coords)
            dest_size = total_hosts * total_size
            dest_size = (dest_size + CACHE_LINE_SIZE - 1) & ~(CACHE_LINE_SIZE - 1)  # Align
            memory_map[tile_coord]['dest_base'] = current_address
            memory_map[tile_coord]['dest_size'] = dest_size
            current_address += dest_size
            tb_log.info(f"Tile {tile_coord} (Dest): Target area @0x{memory_map[tile_coord]['dest_base']:X}, Size 0x{dest_size:X} ({total_size}B per host)")
        
        # Align the next allocation to cache line boundary
        current_address = (current_address + CACHE_LINE_SIZE - 1) & ~(CACHE_LINE_SIZE - 1)
    
    return memory_map


async def prepare_test_patterns(
    tb: demoTB,
    host_coord: Tuple[int, int],
    core_id: int,
    core_local_base: int,
    dest_tiles: List[Tuple[int, int]],
    memory_map: Dict,
    transfer_size: int,
    total_size: int,
    cores_per_host: int,
    default_master: int,
    noc_toggle: bool = False
) -> Dict[Tuple[int, int], Dict]:
    """
    Prepare test patterns for a specific core on a host tile.
    Now supports multiple transfers per destination based on total_size distribution.

    Args:
        noc_toggle: If True, generate alternating 0x5a5a5a5a and 0xa5a5a5a5 patterns
                    to toggle all NoC lines. If False, generate random data.
    """
    host_x, host_y = host_coord
    core_data = {}
    current_offset = 0

    # Calculate per-core allocation
    bytes_per_core = total_size // cores_per_host
    transfers_per_dest = bytes_per_core // transfer_size

    # Setup transfers for each destination, excluding self
    for dest_coord in dest_tiles:
        # Skip self-ping (same tile)
        if dest_coord == host_coord:
            continue

        # Create multiple transfers for this destination
        transfers = []

        for transfer_idx in range(transfers_per_dest):
            # Pattern and readback addresses on this host
            pattern_addr = core_local_base + current_offset
            readback_addr = pattern_addr + transfer_size
            current_offset += (2 * transfer_size)

            # Target address on destination tile
            # Each host gets a section of total_size bytes in the destination
            host_idx = list(memory_map.keys()).index(host_coord) if host_coord in memory_map else 0
            dest_base = memory_map[dest_coord]['dest_base']

            # Calculate destination offset: host_section + core_portion + transfer_offset
            host_section_offset = host_idx * total_size
            core_portion_offset = core_id * bytes_per_core
            transfer_offset = transfer_idx * transfer_size
            dest_offset = host_section_offset + core_portion_offset + transfer_offset
            dest_addr = dest_base + dest_offset

            # Debug logging for memory addresses
            tb.log.debug(f"Core {core_id} Transfer {transfer_idx} to {dest_coord}: "
                        f"dest_addr=0x{dest_addr:X} (base=0x{dest_base:X}, offset=0x{dest_offset:X})")

            # Generate test pattern
            if noc_toggle:
                # NoC data lane width is 256 bytes. Generate patterns that flip all lines every clock cycle.
                # Pattern A (256 bytes): 0x5555aaaa repeating -> [0x55, 0x55, 0xaa, 0xaa] * 64
                # Pattern B (256 bytes): 0xaaaa5555 repeating -> [0xaa, 0xaa, 0x55, 0x55] * 64
                # All bits toggle between consecutive 256-byte chunks
                NOC_DATA_WIDTH = 256
                pattern_a_unit = bytes([0x55, 0x55, 0xaa, 0xaa])  # 0x5555aaaa
                pattern_b_unit = bytes([0xaa, 0xaa, 0x55, 0x55])  # 0xaaaa5555
                pattern_a = pattern_a_unit * (NOC_DATA_WIDTH // 4)  # 256 bytes
                pattern_b = pattern_b_unit * (NOC_DATA_WIDTH // 4)  # 256 bytes
                pattern_unit = pattern_a + pattern_b  # 512 bytes total
                num_repeats = (transfer_size + len(pattern_unit) - 1) // len(pattern_unit)
                pattern = (pattern_unit * num_repeats)[:transfer_size]
            else:
                pattern = os.urandom(transfer_size)

            transfer_info = {
                'pattern': pattern,
                'pattern_addr': pattern_addr,
                'readback_addr': readback_addr,
                'dest_addr': dest_addr,
                'transfer_idx': transfer_idx
            }

            transfers.append(transfer_info)

            # Write pattern to host memory
            tb.noc_write_nonblocking(default_master, host_x, host_y, pattern_addr, pattern)

        core_data[dest_coord] = transfers

    return core_data


async def verify_transfers(
    tb: demoTB,
    host_coord: Tuple[int, int],
    core_id: int,
    transfer_data: Dict[Tuple[int, int], List[Dict]],
    transfer_size: int,
    default_master: int
) -> bool:
    """
    Verify data transfers for a specific core.
    Now handles multiple transfers per destination.

    Args:
        tb: Testbench instance
        host_coord: Host tile coordinates (x, y)
        core_id: Core ID on the host tile
        transfer_data: Test data info for this core (dest_coord -> list of transfer_info)
        transfer_size: Size of each data transfer
        default_master: Default NOC master index

    Returns:
        True if all transfers verified successfully, False otherwise
    """
    host_x, host_y = host_coord
    success = True

    tb.log.info(f"Host {host_coord} Core {core_id}: Verifying data...")

    for dest_coord, transfers_list in transfer_data.items():
        for transfer_info in transfers_list:
            original_pattern = transfer_info['pattern']
            readback_addr = transfer_info['readback_addr']
            transfer_idx = transfer_info['transfer_idx']

            # Read back the data
            readback_result = await tb.noc_read(default_master, host_x, host_y, readback_addr, transfer_size)
            readback_data = readback_result.data

            # Verify data matches
            if readback_data != original_pattern:
                # Find first mismatch for debugging
                mismatch_idx = next((i for i, (a, b) in enumerate(zip(original_pattern, readback_data)) if a != b), -1)

                tb.log.error(f"Host {host_coord} Core {core_id}: DATA MISMATCH for transfer {transfer_idx} to {dest_coord}!")
                tb.log.error(f"First mismatch at byte {mismatch_idx}")

                # Show snippet around the mismatch
                start = max(0, mismatch_idx - 8)
                end = min(len(original_pattern), mismatch_idx + 8)
                tb.log.error(f"Expected: ...{original_pattern[start:end].hex()}...")
                tb.log.error(f"Actual:   ...{readback_data[start:end].hex()}...")

                success = False

    if success:
        tb.log.info(f"Host {host_coord} Core {core_id}: All data transfers verified successfully.")

    return success


async def prepare_host_core(tb, host_coord, core_id, cores_per_host, memory_map, dest_tiles, transfer_size, total_size, default_master, read_memory, write_memory, noc_toggle=False):
    """
    Prepare a single core on a host tile fully in parallel.
    Returns a tuple of (host_coord, core_id, pinger, test_data, command_ids)

    Args:
        noc_toggle: If True, use alternating 0xaa/0x55 patterns instead of random data.
    """
    host_x, host_y = host_coord
    
    # Initialize pinger interface
    pinger = PingerInterface(
        read_memory=read_memory,
        write_memory=write_memory,
        core_id=core_id,
        core_noc_x=host_x,
        core_noc_y=host_y,
        instance_name_prefix=f"pinger_H{host_x}{host_y}_C{core_id}",
        debug=True,
    )
    
    # Initialize pinger
    await pinger.init()
    
    # Calculate memory offsets
    host_local_base = memory_map[host_coord]['host_local_base']
    space_per_core = memory_map[host_coord]['host_local_size'] // cores_per_host
    core_local_base = host_local_base + (core_id * space_per_core)

    tb.log.info(f"Number of cores per host: {cores_per_host}")
    tb.log.info(f"Host {host_coord} Core {core_id}: Preparing test patterns at local base 0x{core_local_base:X}, space per core 0x{space_per_core:X}")
    
    # Prepare test patterns (skipping self)
    test_data = await prepare_test_patterns(
        tb, host_coord, core_id, core_local_base, dest_tiles,
        memory_map, transfer_size, total_size, cores_per_host, default_master,
        noc_toggle=noc_toggle
    )
    
    # Collect all valid destination coordinates (excluding self)
    valid_dest_coords = [coord for coord in dest_tiles if coord != host_coord and coord in test_data]
    
    if not valid_dest_coords:
        tb.log.info(f"Host {host_coord} Core {core_id}: No valid destinations to ping")
        return (host_coord, core_id, pinger, test_data, [])
    
    # Randomize the order of destinations
    random.shuffle(valid_dest_coords)
    
    # Create separate lists for write and read operations
    write_operations = []
    read_operations = []
    
    # Generate all write and read operations for multiple transfers per destination
    for dest_coord in valid_dest_coords:
        dest_x, dest_y = dest_coord
        transfers_list = test_data[dest_coord]

        # Create operations for each transfer to this destination
        for transfer_info in transfers_list:
            pattern_addr = transfer_info['pattern_addr']
            readback_addr = transfer_info['readback_addr']
            dest_addr = transfer_info['dest_addr']

            # Write operation: host → destination
            write_operations.append({
                'type': 'write',
                'src_x': host_x, 'src_y': host_y, 'src_addr': pattern_addr,
                'dest_x': dest_x, 'dest_y': dest_y, 'dest_addr': dest_addr,
                'length': transfer_size
            })

            # write_operations.append({'type': 'writes_ack'})

            # Read operation: destination → host readback
            read_operations.append({
                'type': 'read',
                'src_x': dest_x, 'src_y': dest_y, 'src_addr': dest_addr,
                'dest_x': host_x, 'dest_y': host_y, 'dest_addr': readback_addr,
                'length': transfer_size
            })
    
    # Combine operations: all writes followed by all reads
    operations = []
    
    # random.shuffle(write_operations)
    # random.shuffle(read_operations)
    write_operations.append({'type': 'writes_ack'})
    operations = write_operations + read_operations
    
    # Add finish operation
    operations.append({'type': 'finish'})
    
    # Submit all operations in batch
    command_ids = await pinger.batch_memory_operations(operations)
    
    tb.log.info(f"Host {host_coord} Core {core_id}: Queued {len(operations)} operations with {len(command_ids)} command IDs")
    
    return (host_coord, core_id, pinger, test_data, command_ids)


async def addr_pinger(dut, pinger_bin_path: str = None, cores_per_host: int = PingerInterface.NUM_CORES, transfer_size: int = TRANSFER_SIZE, total_size: int = TOTAL_SIZE, noc_toggle: bool = False):
    """
    Multi-host address pinger test using optimized batched operations.
    Each host tile uses 8 cores to ping other tiles and verify data transfers.

    Args:
        noc_toggle: If True, use alternating 0xaaaaaaaa/0x55555555 patterns instead of
                    random data to toggle all NoC lines for power/signal integrity testing.
    """
    
    tb = demoTB(dut)
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
    host_tiles = tb.config.get_coordinates_for_tile_type(TileType.TENSIX) + \
                 tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) + \
                 tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    dram_tiles = tb.config.get_coordinates_for_tile_type(TileType.DRAM)

    # Choose randomly a set of 4 tiles for hosts and destinations
    host_tiles = random.sample(host_tiles, 2)
    # dram_tiles = []

    tb.log.info(f"Found {len(host_tiles)} host tiles: {host_tiles}")
    
    # All potential destinations (including hosts themselves)
    dest_tiles = sorted(list(set(host_tiles + dram_tiles)))
    
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
                        transfer_size, total_size, default_master, read_memory, write_memory,
                        noc_toggle=noc_toggle
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


async def process_core_completion(
    tb: demoTB,
    host_coord: Tuple[int, int],
    core_id: int,
    pinger: PingerInterface,
    command_ids: List[int],
    test_data: Dict,
    transfer_size: int
) -> bool:
    success = True
    
    tb.log.info(f"Host {host_coord} Core {core_id}: Waiting for {len(command_ids)} commands...")
    
    try:
        # Increase timeout and add debug flags
        statuses = await pinger.wait_for_multiple_statuses(command_ids, timeout_ms=20000)
        
        # Check for errors
        for cmd_id, status in statuses.items():
            if status.error != PingerError.NONE:
                cmd_type = pinger._command_history.get(cmd_id)
                cmd_type_str = cmd_type.command.name if cmd_type else "UNKNOWN"
                
                tb.log.error(f"Host {host_coord} Core {core_id}: Command {cmd_id} ({cmd_type_str}) FAILED with {status.error.name}")
                success = False
        
        # Verify data if commands succeeded
        if success:
            tb.log.info(f"Host {host_coord} Core {core_id}: All commands completed successfully.")
            success = await verify_transfers(tb, host_coord, core_id, test_data, transfer_size, tb.default_master)
            print(f"verify_transfers returned: {success}")
    
    except TimeoutError:
        # Add more debug info on timeout
        tb.log.error(f"Host {host_coord} Core {core_id}: Timeout waiting for commands to complete")
        
        # Print which command IDs weren't received
        received_cmd_ids = set(statuses.keys() if 'statuses' in locals() else [])
        missing_cmd_ids = set(command_ids) - received_cmd_ids
        tb.log.error(f"Host {host_coord} Core {core_id}: Missing status for commands: {missing_cmd_ids}")
        
        # Dump status queue state
        await pinger.dump_buffer_state()
        
        success = False
    
    except Exception as e:
        tb.log.error(f"Host {host_coord} Core {core_id}: Exception during command processing: {str(e)}")
        success = False
    
    if success:
        tb.log.info(f"Host {host_coord} Core {core_id}: All operations completed successfully.")
    else:
        tb.log.error(f"Host {host_coord} Core {core_id}: Operations FAILED.")
    
    return success