"""
Power virus test: center node (1,1) and neighbors hit each other simultaneously.
- Center (1,1) uses 4 cores, one per neighbor direction (N, E, S, W)
- Each neighbor uses 1 core targeting center
- Uses toggling 0x5555aaaa/0xaaaa5555 patterns to flip all NoC data lines
"""

import os
from typing import Tuple, List, Dict
import cocotb
from cocotb.triggers import ClockCycles
from tests.utils.test_utils import load_binary_data
from tests.utils.addr_pinger_handler import PingerInterface, PingerError
from tests.utils.coco_tensix_api import demoTB

# Constants
CACHE_LINE_SIZE = 64
NOC_DATA_WIDTH = 256
TRANSFER_SIZE = 2 * 1024
TOTAL_SIZE = 32 * 1024

# Fixed topology
CENTER = (1, 1)
NEIGHBORS = [(1, 2), (2, 1), (1, 0), (0, 1)]  # N, E, S, W


def generate_toggle_pattern(size: int) -> bytes:
    """Generate pattern that toggles all 256 NoC data lines every clock cycle."""
    pattern_a = bytes([0x55, 0x55, 0xaa, 0xaa]) * (NOC_DATA_WIDTH // 4)
    pattern_b = bytes([0xaa, 0xaa, 0x55, 0x55]) * (NOC_DATA_WIDTH // 4)
    unit = pattern_a + pattern_b
    return (unit * ((size + len(unit) - 1) // len(unit)))[:size]


def allocate_memory(
    host_configs: Dict[Tuple[int, int], Dict],
    start_address: int,
    tb_log
) -> Dict[Tuple[int, int], Dict[str, int]]:
    """
    Allocate memory for power virus test.
    host_configs: {tile_coord: {'cores': num_cores, 'destinations': [dest_coords]}}
    """
    memory_map = {}
    current_addr = start_address

    for tile_coord, config in host_configs.items():
        num_cores = config['cores']
        destinations = config['destinations']

        # Pattern + readback space per core
        bytes_per_core = TOTAL_SIZE // num_cores
        host_local_size = num_cores * len(destinations) * 2 * bytes_per_core
        host_local_size = (host_local_size + CACHE_LINE_SIZE - 1) & ~(CACHE_LINE_SIZE - 1)

        memory_map[tile_coord] = {
            'host_local_base': current_addr,
            'host_local_size': host_local_size,
            'cores': num_cores,
            'destinations': destinations,
            'bytes_per_core': bytes_per_core
        }
        current_addr += host_local_size

        # Destination area (for receiving from others)
        dest_size = TOTAL_SIZE * 4  # Max 4 senders
        dest_size = (dest_size + CACHE_LINE_SIZE - 1) & ~(CACHE_LINE_SIZE - 1)
        memory_map[tile_coord]['dest_base'] = current_addr
        memory_map[tile_coord]['dest_size'] = dest_size
        current_addr += dest_size

        current_addr = (current_addr + CACHE_LINE_SIZE - 1) & ~(CACHE_LINE_SIZE - 1)

        tb_log.info(f"Tile {tile_coord}: {num_cores} cores, local@0x{memory_map[tile_coord]['host_local_base']:X}, dest@0x{memory_map[tile_coord]['dest_base']:X}")

    return memory_map


async def prepare_host_core(
    tb, host_coord, core_id, memory_map, transfer_size, default_master, read_memory, write_memory
):
    """Prepare a single core on a host tile."""
    host_x, host_y = host_coord
    config = memory_map[host_coord]
    num_cores = config['cores']
    destinations = config['destinations']
    bytes_per_core = config['bytes_per_core']

    # Initialize pinger
    pinger = PingerInterface(
        read_memory=read_memory,
        write_memory=write_memory,
        core_id=core_id,
        core_noc_x=host_x,
        core_noc_y=host_y,
        instance_name_prefix=f"pinger_H{host_x}{host_y}_C{core_id}",
        debug=True,
    )
    await pinger.init()

    # Calculate memory offsets
    host_local_base = config['host_local_base']
    space_per_core = config['host_local_size'] // num_cores
    core_local_base = host_local_base + (core_id * space_per_core)

    # For center: each core targets one specific neighbor, sends bytes_per_core in ONE transaction
    # For neighbors: single core targets center, uses transfer_size chunks
    is_center = len(destinations) > 1

    if is_center:
        # Center tile - each core gets one destination, sends all data in one transaction
        dest_coord = destinations[core_id % len(destinations)]
        dest_list = [dest_coord]
        # Center sends bytes_per_core in ONE transaction
        center_transfer_size = bytes_per_core
    else:
        # Neighbor tile - single destination (center)
        dest_list = destinations
        center_transfer_size = None  # Use normal transfer_size

    # Prepare patterns and operations
    test_data = {}
    write_operations = []
    current_offset = 0

    for dest_coord in dest_list:
        dest_x, dest_y = dest_coord
        transfers = []

        # Get destination's dest_base
        dest_base = memory_map[dest_coord]['dest_base']
        # Calculate offset based on sender
        sender_idx = list(memory_map.keys()).index(host_coord)

        if is_center:
            # Center: ONE transaction of bytes_per_core size
            pattern_addr = core_local_base
            dest_offset = core_id * bytes_per_core
            dest_addr = dest_base + dest_offset

            # Generate toggle pattern for full size
            pattern = generate_toggle_pattern(center_transfer_size)

            transfers.append({
                'pattern': pattern,
                'pattern_addr': pattern_addr,
                'dest_addr': dest_addr,
                'transfer_idx': 0
            })

            # Write pattern to memory
            tb.noc_write_nonblocking(default_master, host_x, host_y, pattern_addr, pattern)

            # Add single write operation
            write_operations.append({
                'type': 'write',
                'src_x': host_x, 'src_y': host_y, 'src_addr': pattern_addr,
                'dest_x': dest_x, 'dest_y': dest_y, 'dest_addr': dest_addr,
                'length': center_transfer_size
            })
        else:
            # Neighbors: multiple transfers of transfer_size
            transfers_per_dest = bytes_per_core // transfer_size

            for transfer_idx in range(transfers_per_dest):
                pattern_addr = core_local_base + current_offset
                current_offset += transfer_size

                dest_offset = sender_idx * TOTAL_SIZE + core_id * bytes_per_core + transfer_idx * transfer_size
                dest_addr = dest_base + dest_offset

                # Generate toggle pattern
                pattern = generate_toggle_pattern(transfer_size)

                transfers.append({
                    'pattern': pattern,
                    'pattern_addr': pattern_addr,
                    'dest_addr': dest_addr,
                    'transfer_idx': transfer_idx
                })

                # Write pattern to memory
                tb.noc_write_nonblocking(default_master, host_x, host_y, pattern_addr, pattern)

                # Add write operation
                write_operations.append({
                    'type': 'write',
                    'src_x': host_x, 'src_y': host_y, 'src_addr': pattern_addr,
                    'dest_x': dest_x, 'dest_y': dest_y, 'dest_addr': dest_addr,
                    'length': transfer_size
                })

        test_data[dest_coord] = transfers

    # Build final operations: writes + ack + finish (no reads)
    operations = write_operations + [{'type': 'writes_ack'}, {'type': 'finish'}]

    # Submit operations
    command_ids = await pinger.batch_memory_operations(operations)

    tb.log.info(f"Host {host_coord} Core {core_id}: Queued {len(write_operations)} writes to {dest_list}")

    return (host_coord, core_id, pinger, test_data, command_ids)


async def dm_power_virus(dut, pinger_bin_path: str, transfer_size: int = TRANSFER_SIZE, total_size: int = TOTAL_SIZE):
    """
    Power virus test:
    - Center (1,1) uses 4 cores, each hitting one neighbor
    - Each neighbor uses 1 core hitting center
    - All fire simultaneously
    """
    global TOTAL_SIZE
    TOTAL_SIZE = total_size

    tb = demoTB(dut)
    await tb.init_and_reset()

    # Load binary
    binary_data = load_binary_data(bin_path=pinger_bin_path)
    tb.log.info(f"Loaded pinger binary ({len(binary_data)} bytes)")

    # Define host configurations
    # Center: 4 cores, each targets one neighbor
    # Neighbors: 1 core each, targets center
    host_configs = {
        CENTER: {'cores': 4, 'destinations': NEIGHBORS},
    }
    for nbr in NEIGHBORS:
        host_configs[nbr] = {'cores': 1, 'destinations': [CENTER]}

    all_tiles = [CENTER] + NEIGHBORS
    tb.log.info(f"Power virus: center={CENTER}, neighbors={NEIGHBORS}")

    # Load binary to all tiles
    default_master = tb.default_master
    for x, y in all_tiles:
        tb.noc_write_nonblocking(default_master, x, y, 0x0, binary_data)
    await tb.noc_wait_writes(default_master)
    tb.log.info("Binary loaded to all tiles")

    # Allocate memory
    memory_map = allocate_memory(host_configs, PingerInterface.PINGER_TEST_DATA_GLOBAL_START_ADDRESS, tb.log)

    # Memory helpers
    async def read_memory(address: int, length: int, x: int, y: int) -> bytes:
        return (await tb.noc_read(default_master, x, y, address, length)).data

    async def write_memory(address: int, data: bytes, x: int, y: int) -> None:
        await tb.noc_write(default_master, x, y, address, data)

    # Setup all pingers in parallel
    tb.log.info("Setting up pingers...")
    setup_tasks = []

    for tile_coord, config in host_configs.items():
        for core_id in range(config['cores']):
            setup_tasks.append(
                cocotb.start_soon(
                    prepare_host_core(
                        tb, tile_coord, core_id, memory_map, transfer_size,
                        default_master, read_memory, write_memory
                    )
                )
            )

    # Collect results
    pinger_interfaces = {}
    all_command_ids = {}
    host_test_data = {}

    for task in setup_tasks:
        result = await task
        host_coord, core_id, pinger, test_data, command_ids = result

        if host_coord not in pinger_interfaces:
            pinger_interfaces[host_coord] = {}
            host_test_data[host_coord] = {}
            all_command_ids[host_coord] = {}

        pinger_interfaces[host_coord][core_id] = pinger
        host_test_data[host_coord][core_id] = test_data
        all_command_ids[host_coord][core_id] = command_ids

    # Wait for pattern writes
    await tb.noc_wait_writes(default_master)
    tb.log.info("All patterns written")

    # Start monitoring
    for x, y in all_tiles:
        cocotb.start_soon(tb.monitor_dm_scratch(x, y))

    # Release DM cores
    await tb.release_dm_core_reset()
    tb.log.info("DM cores released - power virus running!")

    # Wait for completion
    success = True
    for host_coord in pinger_interfaces:
        for core_id in pinger_interfaces[host_coord]:
            pinger = pinger_interfaces[host_coord][core_id]
            command_ids = all_command_ids[host_coord][core_id]

            try:
                statuses = await pinger.wait_for_multiple_statuses(command_ids, timeout_ms=30000)
                for cmd_id, status in statuses.items():
                    if status.error != PingerError.NONE:
                        tb.log.error(f"{host_coord} Core {core_id}: cmd {cmd_id} failed with {status.error.name}")
                        success = False
                tb.log.info(f"{host_coord} Core {core_id}: completed")
            except TimeoutError:
                tb.log.error(f"{host_coord} Core {core_id}: timeout")
                success = False

    await ClockCycles(dut.ai_clk, 8)

    if success:
        tb.log.info("Power virus test PASSED!")
    else:
        tb.log.error("Power virus test FAILED!")
        raise RuntimeError("Power virus test failed")
