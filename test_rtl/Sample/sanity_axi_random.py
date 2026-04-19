from tests.utils.coco_tensix_api import demoTB
from tests.utils.noc_driver import NocTransactionConfig
from tests.utils.tensix_config import TileType
from cocotbext.axi import AxiBurstType
from cocotb.triggers import with_timeout, Event
import cocotb

import os
import random
from collections import defaultdict

# Constants for alignment and timeouts
TIMEOUT_NS = 5000

def generate_non_overlapping_transactions(tb,valid_coords, num_transactions_per_tile=4, mem_size_mb=1):
    """
    Generate a list of non-overlapping memory transactions.
    
    Args:
        valid_coords: List of valid (x,y) memory tile coordinates
        num_transactions_per_tile: Number of transactions to generate per tile
        mem_size_mb: Memory size in MB per tile
        
    Returns:
        List of transaction configurations with no overlapping memory regions
    """
    transactions = []
    # Track used memory regions per tile to avoid overlaps
    used_regions = defaultdict(list)
    
    for x, y in valid_coords:
        tile_key = (x, y)
        for _ in range(num_transactions_per_tile):
            # Random transaction parameters
            transaction_length = random.randrange(0, 16)
            transaction_size = random.randrange(0, 6)
            burst_type = AxiBurstType.INCR
            
            # Calculate total bytes for this transaction
            transaction_size_bytes = (transaction_length + 1) * (2**transaction_size)
            
            # Find a non-overlapping address
            max_addr = mem_size_mb * 1024 * 1024 - transaction_size_bytes
            
            # Try to find a valid address that doesn't overlap with used regions
            max_attempts = 100
            for _ in range(max_attempts):
                # Generate a random address and align to 16 bytes
                addr = random.randint(0, max_addr)
                
                # Calculate end address of this transaction
                end_addr = addr + transaction_size_bytes
                
                # Check if this range overlaps with any existing region
                overlaps = False
                for used_start, used_end in used_regions[tile_key]:
                    if (addr <= used_end and end_addr >= used_start):
                        overlaps = True
                        break
                
                if not overlaps:
                    # No overlap found, use this address
                    base_address = (y << 46) | (x << 40) | addr
                    used_regions[tile_key].append((addr, end_addr))
                    
                    # Create transaction config
                    transaction = {
                        "x": x,
                        "y": y,
                        "length": transaction_length,
                        "size": transaction_size,
                        "size_bytes": transaction_size_bytes,
                        "address": addr,
                        "base_address": base_address,
                        "burst_type": burst_type
                    }
                    
                    transactions.append(transaction)
                    break
            else:
                # If we couldn't find a non-overlapping region after max attempts
                print(f"Warning: Could not find non-overlapping region for tile ({x},{y}) after {max_attempts} attempts")
    
    return transactions

async def execute_transaction(tb, master_idx, transaction):
    """Execute a single memory transaction on the specified master."""
    # Extract transaction parameters
    x = transaction["x"]
    y = transaction["y"]
    transaction_length = transaction["length"]
    transaction_size = transaction["size"]
    transaction_size_bytes = transaction["size_bytes"]
    base_address = transaction["base_address"]
    burst_type = transaction["burst_type"]
    
    # Generate test data
    data = bytearray(os.urandom(transaction_size_bytes))
    
    # Create transaction config with non-posted write
    noc_config = NocTransactionConfig(non_posted=True)
    user_bits = noc_config.get_user_bits()
    
    # Log transaction details
    tb.log.info(f"Master {master_idx} executing transaction at tile ({x},{y}):")
    tb.log.info(f"  Transaction length: {transaction_length} transfers")
    tb.log.info(f"  Transaction size: {2**transaction_size} bytes")
    tb.log.info(f"  Total bytes: {transaction_size_bytes}")
    tb.log.info(f"  Address: 0x{base_address:X}")
    
    try:
        # Write data to memory
        await with_timeout(
            tb.masters[master_idx].write(
                base_address, 
                data, 
                burst=burst_type, 
                size=transaction_size,
                user=user_bits
            ), 
            TIMEOUT_NS, 
            "ns"
        )
        
        # Read data back from memory
        read_result = await with_timeout(
            tb.masters[master_idx].read(
                address=base_address, 
                length=transaction_size_bytes, 
                burst=burst_type, 
                size=transaction_size, 
                user=user_bits
            ), 
            TIMEOUT_NS, 
            "ns"
        )
        
        # Verify data integrity
        if data != read_result.data:
            log_data_mismatch(tb, data, read_result.data)
            return False
        
        tb.log.info(f"  Master {master_idx}: Transaction verified successfully")
        return True
    
    except Exception as e:
        tb.log.error(f"Master {master_idx} transaction failed: {str(e)}")
        return False

def log_data_mismatch(tb, expected_data, actual_data):
    """Log detailed information about data mismatches."""
    for i in range(0, len(expected_data), 16):
        expected_chunk = expected_data[i:i+16]
        actual_chunk = actual_data[i:i+16] if i < len(actual_data) else b""
        
        if expected_chunk == actual_chunk:
            tb.log.info(f"Word {i}: 0x{expected_chunk.hex()}")
        else:
            tb.log.error(f"Word {i}: 0x{expected_chunk.hex()} != 0x{actual_chunk.hex()}")
    
    tb.log.error("  Verification failed")

async def worker(tb, master_idx, transactions, results, done_event):
    """Worker coroutine that processes transactions for a specific master."""
    success_count = 0
    total_count = len(transactions)
    
    for transaction in transactions:
        success = await execute_transaction(tb, master_idx, transaction)
        if success:
            success_count += 1
    
    # Store results and signal completion
    results[master_idx] = {
        "total": total_count,
        "success": success_count,
        "master_idx": master_idx
    }
    done_event.set()

async def sanity_axi_random(dut):
    """Test random AXI transactions in parallel with 16-byte alignment."""
    # Initialize testbench
    tb = demoTB(dut)
    await tb.init_and_reset()
    
    # Get valid memory coordinates
    valid_coords = tb.config.get_tiles_with_memory()
    
    # Generate non-overlapping transactions
    transactions = generate_non_overlapping_transactions(tb,valid_coords)
    tb.log.info(f"Generated {len(transactions)} non-overlapping transactions")
    
    # Distribute transactions across masters
    num_masters = tb.config.num_noc2axi
    master_transactions = [[] for _ in range(num_masters)]
    
    for i, transaction in enumerate(transactions):
        master_idx = i % num_masters
        master_transactions[master_idx].append(transaction)
    
    # Track results and completion
    results = {}
    done_events = [Event() for _ in range(num_masters)]
    
    # Launch parallel workers
    workers = []
    for master_idx in range(num_masters):
        if master_transactions[master_idx]:  # Only launch if there are transactions
            worker_coro = worker(
                tb, 
                master_idx, 
                master_transactions[master_idx], 
                results, 
                done_events[master_idx]
            )
            workers.append(cocotb.start_soon(worker_coro))
            tb.log.info(f"Started worker for master {master_idx} with {len(master_transactions[master_idx])} transactions")
    
    # Wait for all workers to complete
    for event in done_events:
        await event.wait()
    
    # Report overall results
    tb.log.info("All transactions completed")
    total_transactions = 0
    total_success = 0
    
    for master_idx, result in results.items():
        success_rate = (result["success"] / result["total"]) * 100 if result["total"] > 0 else 0
        tb.log.info(f"Master {master_idx}: {result['success']}/{result['total']} transactions succeeded ({success_rate:.2f}%)")
        total_transactions += result["total"]
        total_success += result["success"]
    
    overall_success_rate = (total_success / total_transactions) * 100 if total_transactions > 0 else 0
    tb.log.info(f"Overall: {total_success}/{total_transactions} transactions succeeded ({overall_success_rate:.2f}%)")
    
    # Test passes if all transactions succeeded
    assert total_success == total_transactions, f"Failed {total_transactions - total_success} transactions"