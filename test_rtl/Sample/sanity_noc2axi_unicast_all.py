from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.noc_driver import NocTransactionConfig
import os
import random

async def sanity_noc2axi_unicast_all(dut):
    tb = demoTB(dut)

    await tb.init_and_reset()

    MIN_TRANSACTION_SIZE = 1
    MAX_TRANSACTION_SIZE = 5*1024  # 5k bytes

    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    dram_coords = tb.config.get_coordinates_for_tile_type(TileType.DRAM)
    dispatch_coords = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) + tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    noc2axi_coords = tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT) + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT) + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)

    tb.log.info(f"tensix_coords: {tensix_coords}")
    tb.log.info(f"dram_coords: {dram_coords}")
    tb.log.info(f"dispatch_coords: {dispatch_coords}")
    tb.log.info(f"noc2axi_coords: {noc2axi_coords}")
    tb.log.info(f"L1 size: {tb.config.l1_size_mb} MB")

    l1_size = tb.config.l1_size_mb * 1024 * 1024

    # Process each node type with appropriate address limit
    node_types = [
        (dispatch_coords, l1_size),
        (tensix_coords, l1_size),
    ]

    # Consolidated data structure for each master
    master_transactions = {}

    # Initialize master transactions with randomized address allocation
    used_addresses = set()  # Will store (addr, size) tuples
    for m in range(tb.config.num_noc2axi):
        master_transactions[m] = {}

    # Prepare all transactions with randomized address allocation
    def allocate_random_address(addr_limit, used_addresses, transaction_size, max_attempts=5000):
        """Allocate random available address"""
        for _ in range(max_attempts):
            if addr_limit <= transaction_size:
                break
            base_addr = random.randint(0, addr_limit - transaction_size)
            if not any(base_addr < existing_addr + existing_size and base_addr + transaction_size > existing_addr
                      for existing_addr, existing_size in used_addresses):
                used_addresses.add((base_addr, transaction_size))
                return base_addr

        raise RuntimeError(f"No available address space in limit {addr_limit} for transaction size {transaction_size} after {max_attempts} attempts")

    for m in range(tb.config.num_noc2axi):
        for coords, addr_limit in node_types:
            if len(coords) == 0:
                continue

            for x, y in coords:
                transaction_size = random.randint(MIN_TRANSACTION_SIZE, MAX_TRANSACTION_SIZE)
                addr = allocate_random_address(addr_limit, used_addresses, transaction_size)
                data = bytearray(os.urandom(transaction_size))
                master_transactions[m][(x, y)] = {'addr': addr, 'data': data, 'size': transaction_size}

    # Launch write operations for all masters concurrently
    write_tasks = []
    for m in range(tb.config.num_noc2axi):
        task = cocotb.start_soon(run_master_writes(tb, m, node_types, master_transactions[m]))
        write_tasks.append(task)

    while write_tasks:
        await write_tasks.pop(0)

    # Launch verification operations for all masters concurrently
    verify_tasks = []
    for m in range(tb.config.num_noc2axi):
        task = cocotb.start_soon(run_master_verifies(tb, m, node_types, master_transactions[m]))
        verify_tasks.append(task)

    while verify_tasks:
        await verify_tasks.pop(0)

    tb.log.info("All unicast tests passed")

async def run_master_writes(tb, master_id, node_types, transactions):
    """Run all write operations for a specific master"""
    for coords, _ in node_types:
        if len(coords) == 0:
            continue

        for x, y in coords:
            if (x, y) not in transactions:
                continue

            addr = transactions[(x, y)]['addr']
            data = transactions[(x, y)]['data']
            size = transactions[(x, y)]['size']

            tb.log.info(f"Master {master_id} writing to [x={x}, y={y}] at address {hex(addr)} (size: {size} bytes)")
            write_config = NocTransactionConfig(non_posted=True)
            tb.noc_write_nonblocking(master_id, x, y, addr, data, config=write_config)

    await tb.noc_wait_writes(master_id)
    tb.log.info(f"Master {master_id} completed all writes")

async def run_master_verifies(tb, master_id, node_types, transactions):
    """Run all verification operations for a specific master"""
    # Issue all reads in non-blocking manner first
    read_requests = []
    for coords, _ in node_types:
        if len(coords) == 0:
            continue

        for x, y in coords:
            if (x, y) not in transactions:
                continue

            addr = transactions[(x, y)]['addr']
            expected_data = transactions[(x, y)]['data']
            size = transactions[(x, y)]['size']

            tb.log.info(f"Master {master_id} reading from node [{x}, {y}] at address 0x{addr:x} (size: {size} bytes)")
            tb.noc_read_nonblocking(master_id, x, y, addr, len(expected_data))
            read_requests.append(((x, y), expected_data))

    # Wait for all reads to complete
    if read_requests:
        tb.log.info(f"Master {master_id} waiting for all reads to complete")
        reads = await tb.noc_wait_reads(master_id)

        # Verify content of each read
        tb.log.info(f"Master {master_id} verifying {len(reads)} read results")
        for i, (coord_info, expected_data) in enumerate(read_requests):
            x, y = coord_info
            if i >= len(reads):
                assert False, f"Master {master_id}: Missing read result for node [{x}, {y}]"

            if expected_data != reads[i].data:
                for j in range(0, len(expected_data), 16):
                    expected_chunk = expected_data[j:j+16]
                    read_chunk = reads[i].data[j:j+16] if j+16 <= len(reads[i].data) else reads[i].data[j:]

                    if expected_chunk != read_chunk:
                        tb.log.error(f"Master {master_id}, Node [{x}, {y}], Word {j}: 0x{expected_chunk.hex()} != 0x{read_chunk.hex()}")

                assert False, f"Data mismatch at master {master_id}, node [{x}, {y}]"

    tb.log.info(f"Master {master_id} completed all verifications")
