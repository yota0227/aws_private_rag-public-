import os
import random
import asyncio
from typing import Tuple, List, Dict
from cocotb.triggers import ClockCycles
from tests.utils.test_utils import load_binary_data, find_largest_rectangle
from tests.utils.coco_tensix_api import demoTB
from tests.utils.tensix_config import TileType
from tests.utils.addr_pinger import (
    L1_COMMAND_ADDR, L1_STATUS_ADDR,
    create_write_command, create_read_command,
    StatusStruct
)


async def check_command_status(tb: demoTB, master: int, coord: Tuple[int, int], status_addr: int) -> bool:
    """
    Check if a command has completed without waiting.
    Returns True if the command is complete, False otherwise.
    """
    read = await tb.noc_read(master, coord[0], coord[1], status_addr, StatusStruct.SIZE)
    status = StatusStruct.from_bytes(read.data)
    tb.log.info(f"Status at {coord}: {status}")
    return status.command_complete


async def wait_for_command_completion(tb: demoTB, master: int, coord: Tuple[int, int], clk, status_addr: int, timeout_cycles: int = 8192) -> None:
    """
    Wait for a command to complete by polling the status register.
    Raises a TimeoutError if the command does not complete within the given cycles.
    """
    remaining_cycles = timeout_cycles
    while remaining_cycles > 0:
        await ClockCycles(clk, 512)
        is_complete = await check_command_status(tb, master, coord, status_addr)
        if is_complete:
            return
        remaining_cycles -= 512
    raise TimeoutError(f"Timeout waiting for command completion at coordinate {coord}.")


def is_valid_endpoint(coord: Tuple[int, int], tensix_coords: List[Tuple[int, int]], dram_coords: List[Tuple[int, int]]) -> bool:
    """
    Determine if a coordinate is a valid endpoint (contains a Tensix or DRAM).
    """
    return coord in tensix_coords or coord in dram_coords


def get_memory_allocation(tensix_coords: List[Tuple[int, int]], dram_coords: List[Tuple[int, int]], dispatch_coords: List[Tuple[int, int]]) -> Dict[Tuple[int, int], int]:
    """
    Allocate memory regions for each Tensix/DRAM coordinate to avoid collisions.
    Each coordinate gets a 1MB region starting from base_addr.
    """
    base_addr = 1 * 1024 * 1024  # Start at 1MB
    region_size = 16 * 1024  # 16kB per region
    
    memory_map = {}
    all_coords = tensix_coords + dram_coords + dispatch_coords
    
    for i, coord in enumerate(all_coords):
        memory_map[coord] = base_addr + (i * region_size)
        
    return memory_map


async def embedded_addr_pinger(dut):
    binary_data = load_binary_data(bin_path="tests/embedded_src/addr_pinger/out/addr_pinger.bin", pad_to=16)

    tb = demoTB(dut)
    await tb.init_and_reset()

    # Get all Tensix, Dispatch and DRAM coordinates
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    noc2axi_coords = tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT) + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT) + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)
    dispatch_coords = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) + tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    
    tb.log.info(f"Tensix coordinates: {tensix_coords}")
    tb.log.info(f"NOC2AXI coordinates: {noc2axi_coords}")
    tb.log.info(f"Dispatch coordinates: {dispatch_coords}")
    
    # Allocate memory regions for each coordinate
    memory_map = get_memory_allocation(tensix_coords, noc2axi_coords, dispatch_coords)
    
    # Calculate all valid endpoints (Tensix, Dispatch or DRAM)
    valid_endpoints = tensix_coords + noc2axi_coords + dispatch_coords

    # Transfer size for each test
    transfer_size = 1024  # 1KB

    master = 0

    # Distribute the binary to all Tensix coordinates and clear command/status buffers
    rect = find_largest_rectangle(tensix_coords)
    tb.log.info(f"Loading binary ({hex(len(binary_data))} bytes) to Tensix rectangle: {rect}")
    await tb.noc_multicast(master, rect[0], rect[1], rect[2], rect[3], 0x0, binary_data)
    await tb.noc_multicast(master, rect[0], rect[1], rect[2], rect[3], L1_COMMAND_ADDR, bytearray(256))
    await tb.noc_multicast(master, rect[0], rect[1], rect[2], rect[3], L1_STATUS_ADDR, bytearray(256))

    # Load binary to Dispatch coordinates
    for coord in dispatch_coords:
        x, y = coord
        tb.log.info(f"Loading binary ({hex(len(binary_data))} bytes) to Dispatch at [x, y] = [{x}, {y}]")
        tb.noc_write_nonblocking(master, x, y, 0x0, binary_data)
        tb.noc_write_nonblocking(master, x, y, L1_COMMAND_ADDR, bytearray(256))
        tb.noc_write_nonblocking(master, x, y, L1_STATUS_ADDR, bytearray(256))
    await tb.noc_wait_writes(master)
    
    tb.log.info(f"Finished waiting for writes")
    
    # Generate test patterns for each source-destination pair
    test_patterns = {}
    for src_coord in tensix_coords:
        patterns = {}
        for dest_coord in valid_endpoints:
            # Skip testing a coordinate with itself
            if src_coord == dest_coord:
                continue
                
            # Generate a unique pattern for this src-dest pair
            pattern = os.urandom(transfer_size)
            patterns[dest_coord] = pattern
        
        test_patterns[src_coord] = patterns
    
    # Release the core reset to start processing commands
    await tb.release_dm_core_reset()
    
    # Prepare test configurations for all tests
    all_tests = []
    for src_coord in tensix_coords:
        src_x, src_y = src_coord
        
        for dest_coord in valid_endpoints:
            if src_coord == dest_coord:
                continue  # Skip testing a coordinate with itself
                
            dest_x, dest_y = dest_coord
            
            # Get source and destination memory addresses
            src_mem_addr = memory_map[src_coord]
            dest_mem_addr = memory_map[dest_coord]
            readback_addr = src_mem_addr + transfer_size  # Use a different address for readback
            
            # Get the test pattern for this src-dest pair
            test_data = test_patterns[src_coord][dest_coord]
            
            all_tests.append({
                'src_coord': src_coord,
                'dest_coord': dest_coord,
                'src_mem_addr': src_mem_addr,
                'dest_mem_addr': dest_mem_addr,
                'readback_addr': readback_addr,
                'test_data': test_data
            })
    
    # === PHASE 1: Issue all write commands ===
    tb.log.info("PHASE 1: Issuing all write commands...")
    
    for test in all_tests:
        src_x, src_y = test['src_coord']
        dest_x, dest_y = test['dest_coord']
        src_mem_addr = test['src_mem_addr']
        dest_mem_addr = test['dest_mem_addr']
        test_data = test['test_data']
        
        tb.log.info(f"Setting up write from ({src_x},{src_y}) to ({dest_x},{dest_y})")
        
        # Write test data to source memory
        tb.noc_write_nonblocking(master, src_x, src_y, src_mem_addr, test_data)
        
        # Clear status before issuing command
        tb.noc_write_nonblocking(master, src_x, src_y, L1_STATUS_ADDR, bytearray(256))
        
        # Issue WRITE command from source to destination
        write_cmd = create_write_command(
            command_id=0x0,
            src=(src_x, src_y, src_mem_addr),
            dest=(dest_x, dest_y, dest_mem_addr),
            length=transfer_size
        )
        tb.noc_write_nonblocking(master, src_x, src_y, L1_COMMAND_ADDR, write_cmd)
    
    # Wait for all nonblocking writes to complete
    await tb.noc_wait_writes(master)
    tb.log.info("All write commands issued")
    
    # === PHASE 2: Check writes and issue reads as they complete ===
    tb.log.info("PHASE 2: Checking write completions and issuing reads...")
    
    # Keep track of tests that need to be checked for write completion
    pending_writes = all_tests.copy()
    # Keep track of tests with reads issued
    reads_issued = []
    
    # Poll and issue reads until all writes are complete
    while pending_writes:
        # Make a copy to avoid modifying the list while iterating
        for test in pending_writes.copy():
            src_coord = test['src_coord']
            src_x, src_y = src_coord
            dest_x, dest_y = test['dest_coord']
            
            # Check if write command is complete
            is_complete = await check_command_status(tb, master, src_coord, L1_STATUS_ADDR)
            
            if is_complete:
                tb.log.info(f"Write complete from ({src_x},{src_y}) to ({dest_x},{dest_y}), issuing read command")
                
                # Issue READ command to verify data transfer
                read_cmd = create_read_command(
                    command_id=0x1,
                    src=(dest_x, dest_y, test['dest_mem_addr']),
                    dest=(src_x, src_y, test['readback_addr']),
                    length=transfer_size
                )
                
                # Clear status before issuing the next command
                tb.noc_write_nonblocking(master, src_x, src_y, L1_STATUS_ADDR, bytearray(256))
                tb.noc_write_nonblocking(master, src_x, src_y, L1_COMMAND_ADDR, read_cmd)
                
                # Move this test from pending_writes to reads_issued
                pending_writes.remove(test)
                reads_issued.append(test)
        
        # Wait for nonblocking writes to complete
        await tb.noc_wait_writes(master)
        
        # If there are still pending writes, wait a bit before checking again
        if pending_writes:
            await ClockCycles(dut.ai_clk, 128)
    
    # === PHASE 3: Wait for all reads to complete and verify data ===
    tb.log.info("PHASE 3: Checking read completions and verifying data...")
    
    # Keep track of tests that need to be checked for read completion
    pending_reads = reads_issued.copy()
    
    # Poll until all reads are complete
    while pending_reads:
        # Make a copy to avoid modifying the list while iterating
        for test in pending_reads.copy():
            src_coord = test['src_coord']
            src_x, src_y = src_coord
            dest_x, dest_y = test['dest_coord']
            
            # Check if read command is complete
            is_complete = await check_command_status(tb, master, src_coord, L1_STATUS_ADDR)
            
            if is_complete:
                tb.log.info(f"Read complete from ({dest_x},{dest_y}) to ({src_x},{src_y}), verifying data")
                
                # Verify that the read back data matches the originally written test data
                readback = await tb.noc_read(master, src_x, src_y, test['readback_addr'], transfer_size)
                test_data = test['test_data']
                
                if readback.data == test_data:
                    tb.log.info(f"✓ Data transfer verified from ({src_x},{src_y}) to ({dest_x},{dest_y})")
                else:
                    tb.log.error(f"✗ Data mismatch in transfer from ({src_x},{src_y}) to ({dest_x},{dest_y})")
                    # Provide more detailed error information
                    mismatch_count = sum(1 for a, b in zip(readback.data, test_data) if a != b)
                    tb.log.error(f"  {mismatch_count}/{transfer_size} bytes mismatched")
                    # Show the first few mismatches for debugging
                    for i in range(min(16, len(readback.data))):
                        if readback.data[i] != test_data[i]:
                            tb.log.error(f"  Byte {i}: expected {test_data[i]}, got {readback.data[i]}")
                    
                    assert False, f"Data transfer failed from ({src_x},{src_y}) to ({dest_x},{dest_y})"
                
                # Remove from pending reads
                pending_reads.remove(test)
        
        # If there are still pending reads, wait a bit before checking again
        if pending_reads:
            await ClockCycles(dut.ai_clk, 128)
    
    tb.log.info("All address pinger tests completed successfully!")