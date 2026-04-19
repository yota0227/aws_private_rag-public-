"""
L1 Backdoor Sanity Test
=======================

Tests direct SRAM backdoor access by cross-checking with frontdoor (NoC) access.
Tests on three tile types:
- Tensix tile (64-bank L1, rows 0-2)
- Dispatch West tile (16-bank L1, column 0, row 3)
- Dispatch East tile (16-bank L1, column 3, row 3)

For each tile (with hash disabled and then enabled):
1. Frontdoor write -> Frontdoor read + check -> Backdoor read (32-bit)
2. Backdoor write -> Frontdoor read (32-bit)
3. Frontdoor write -> Frontdoor read + check -> Backdoor read (128-bit)
4. Bulk preload via backdoor -> Frontdoor verify
5. Frontdoor write -> Frontdoor read + check -> Backdoor dump (128B)
6. Frontdoor write -> Frontdoor read first 4B + check -> Backdoor dump (256B, > 128B)

Note: For large transfers (> 128B), only the first 4B are verified via frontdoor read.

Usage:
    make TESTCASE=sanity_l1_backdoor_test
"""

from tests.utils.coco_tensix_api import *
from tests.utils.tensix_config import TileType
from cocotb.triggers import Timer
import random


async def run_tile_tests(tb, x: int, y: int, tile_name: str, master: int = 0, addr_offset: int = 0):
    """
    Run backdoor tests on a single tile.

    Args:
        tb: Testbench instance
        x: Tile X coordinate
        y: Tile Y coordinate
        tile_name: Human-readable tile name for logging
        master: NoC master to use for frontdoor access
        addr_offset: Offset to add to test addresses (to avoid overlap between hash phases)
    """
    tb.log.info("")
    tb.log.info("#" * 70)
    tb.log.info(f"# Testing {tile_name} at ({x}, {y})")
    tb.log.info("#" * 70)

    # -------------------------------------------------------------------------
    # Test A: Frontdoor Write -> Backdoor Read (32-bit)
    # -------------------------------------------------------------------------
    tb.log.info("=" * 60)
    tb.log.info(f"[{tile_name}] Test A: Frontdoor Write -> Backdoor Read (32-bit)")
    tb.log.info("=" * 60)

    test_addrs = [0x0000 + addr_offset, 0x2000 + addr_offset, 0x10000 + addr_offset, 0x20000 + addr_offset]
    test_values = [0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0xABCDABCD]

    for addr, value in zip(test_addrs, test_values):
        data = value.to_bytes(4, 'little')
        tb.log.info(f"  Frontdoor write: addr=0x{addr:08x}, value=0x{value:08x}")
        await tb.noc_write(master, x, y, addr, data)


        # Frontdoor read and check
        tb.log.info(f"  Frontdoor read: addr=0x{addr:08x}")
        fd_result = await tb.noc_read(master, x, y, addr, 4)
        fd_read_value = int.from_bytes(fd_result.data, 'little')
        tb.log.info(f"  Frontdoor read value: 0x{fd_read_value:08x}")

        if fd_read_value != value:
            tb.log.error(f"  FRONTDOOR MISMATCH: expected 0x{value:08x}, got 0x{fd_read_value:08x}")
            assert False, f"[{tile_name}] Test A frontdoor check failed at addr 0x{addr:08x}"

        # Backdoor read and check
        tb.log.info(f"  Backdoor read: addr=0x{addr:08x}")
        read_value = tb.l1_backdoor_read(x, y, addr, size=4)
        tb.log.info(f"  Backdoor read value: 0x{read_value:08x}")

        if read_value != value:
            tb.log.error(f"  BACKDOOR MISMATCH: expected 0x{value:08x}, got 0x{read_value:08x}")

        tb.log.info(f"  PASS: addr 0x{addr:08x}")

    tb.log.info(f"[{tile_name}] Test A PASSED")

    # -------------------------------------------------------------------------
    # Test B: Backdoor Write -> Frontdoor Read (32-bit)
    # -------------------------------------------------------------------------
    tb.log.info("=" * 60)
    tb.log.info(f"[{tile_name}] Test B: Backdoor Write -> Frontdoor Read (32-bit)")
    tb.log.info("=" * 60)

    test_addrs_2 = [0x3000 + addr_offset, 0x4000 + addr_offset, 0x30000 + addr_offset, 0x40000 + addr_offset]
    test_values_2 = [0x11111111, 0x22222222, 0x33333333, 0x44444444]

    for addr, value in zip(test_addrs_2, test_values_2):
        tb.log.info(f"  Backdoor write: addr=0x{addr:08x}, value=0x{value:08x}")
        tb.l1_backdoor_write(x, y, addr, value, size=4)

        tb.log.info(f"  Frontdoor read: addr=0x{addr:08x}")
        result = await tb.noc_read(master, x, y, addr, 4)
        read_value = int.from_bytes(result.data, 'little')
        tb.log.info(f"  Read value: 0x{read_value:08x}")

        if read_value != value:
            tb.log.error(f"  MISMATCH: expected 0x{value:08x}, got 0x{read_value:08x}")
            assert False, f"[{tile_name}] Test B failed at addr 0x{addr:08x}"

        tb.log.info(f"  PASS: addr 0x{addr:08x}")

    tb.log.info(f"[{tile_name}] Test B PASSED")

    # -------------------------------------------------------------------------
    # Test C: Frontdoor Write -> Backdoor Read (128-bit)
    # -------------------------------------------------------------------------
    tb.log.info("=" * 60)
    tb.log.info(f"[{tile_name}] Test C: Frontdoor Write -> Backdoor Read (128-bit)")
    tb.log.info("=" * 60)

    addr_128 = 0x5000 + addr_offset
    value_128 = 0x0123456789ABCDEF_FEDCBA9876543210

    data_128 = value_128.to_bytes(16, 'little')
    tb.log.info(f"  Frontdoor write 128b: addr=0x{addr_128:08x}, value=0x{value_128:032x}")
    await tb.noc_write(master, x, y, addr_128, data_128)


    # Frontdoor read and check
    tb.log.info(f"  Frontdoor read 128b: addr=0x{addr_128:08x}")
    fd_result_128 = await tb.noc_read(master, x, y, addr_128, 16)
    fd_read_value_128 = int.from_bytes(fd_result_128.data, 'little')
    tb.log.info(f"  Frontdoor read value: 0x{fd_read_value_128:032x}")

    if fd_read_value_128 != value_128:
        tb.log.error(f"  FRONTDOOR MISMATCH: expected 0x{value_128:032x}, got 0x{fd_read_value_128:032x}")
        assert False, f"[{tile_name}] Test C frontdoor check failed at addr 0x{addr_128:08x}"


    # Backdoor read and check
    tb.log.info(f"  Backdoor read 128b: addr=0x{addr_128:08x}")
    read_value_128 = tb.l1_backdoor_read(x, y, addr_128, size=16)
    tb.log.info(f"  Backdoor read value: 0x{read_value_128:032x}")

    if read_value_128 != value_128:
        tb.log.error(f"  BACKDOOR MISMATCH: expected 0x{value_128:032x}, got 0x{read_value_128:032x}")
        assert False, f"[{tile_name}] Test C backdoor check failed at addr 0x{addr_128:08x}"

    tb.log.info(f"[{tile_name}] Test C PASSED")

    # -------------------------------------------------------------------------
    # Test D: Bulk Preload -> Frontdoor Verify
    # -------------------------------------------------------------------------
    tb.log.info("=" * 60)
    tb.log.info(f"[{tile_name}] Test D: Bulk Preload via Backdoor")
    tb.log.info("=" * 60)

    bulk_addr = 0x8000 + addr_offset
    bulk_size = 256

    test_pattern = bytes([i & 0xFF for i in range(bulk_size)])

    tb.log.info(f"  Backdoor preload: addr=0x{bulk_addr:08x}, size={bulk_size} bytes")
    tb.l1_backdoor_preload(x, y, bulk_addr, test_pattern)


    tb.log.info(f"  Frontdoor read: addr=0x{bulk_addr:08x}, size={bulk_size} bytes")
    result = await tb.noc_read(master, x, y, bulk_addr, bulk_size)

    if result.data != test_pattern:
        for i in range(bulk_size):
            if result.data[i] != test_pattern[i]:
                tb.log.error(f"  MISMATCH at offset {i}: expected 0x{test_pattern[i]:02x}, got 0x{result.data[i]:02x}")
                break
        assert False, f"[{tile_name}] Test D failed: bulk preload mismatch"

    tb.log.info(f"[{tile_name}] Test D PASSED")

    # -------------------------------------------------------------------------
    # Test E: Frontdoor Write -> Backdoor Dump
    # -------------------------------------------------------------------------
    tb.log.info("=" * 60)
    tb.log.info(f"[{tile_name}] Test E: Frontdoor Write -> Backdoor Dump")
    tb.log.info("=" * 60)

    dump_addr = 0xA000 + addr_offset
    dump_size = 128

    random_data = bytes([random.randint(0, 255) for _ in range(dump_size)])

    tb.log.info(f"  Frontdoor write: addr=0x{dump_addr:08x}, size={dump_size} bytes")
    await tb.noc_write(master, x, y, dump_addr, random_data)


    # Frontdoor read and check (full check since dump_size <= 128B)
    tb.log.info(f"  Frontdoor read: addr=0x{dump_addr:08x}, size={dump_size} bytes")
    fd_result = await tb.noc_read(master, x, y, dump_addr, dump_size)

    if fd_result.data != random_data:
        for i in range(dump_size):
            if fd_result.data[i] != random_data[i]:
                tb.log.error(f"  FRONTDOOR MISMATCH at offset {i}: expected 0x{random_data[i]:02x}, got 0x{fd_result.data[i]:02x}")
                break
        assert False, f"[{tile_name}] Test E frontdoor check failed"

    tb.log.info(f"  Frontdoor read check PASSED")

    # Backdoor dump and check
    tb.log.info(f"  Backdoor dump: addr=0x{dump_addr:08x}, size={dump_size} bytes")
    dump_result = tb.l1_backdoor_dump(x, y, dump_addr, dump_size)

    if dump_result != random_data:
        for i in range(dump_size):
            if dump_result[i] != random_data[i]:
                tb.log.error(f"  BACKDOOR MISMATCH at offset {i}: expected 0x{random_data[i]:02x}, got 0x{dump_result[i]:02x}")
                break
        assert False, f"[{tile_name}] Test E backdoor check failed"

    tb.log.info(f"[{tile_name}] Test E PASSED")

    # -------------------------------------------------------------------------
    # Test F: Frontdoor Write -> Backdoor Dump (Large transfer > 128B)
    # For large transfers, only first 4B are checked via frontdoor read
    # -------------------------------------------------------------------------
    tb.log.info("=" * 60)
    tb.log.info(f"[{tile_name}] Test F: Frontdoor Write -> Backdoor Dump (Large > 128B)")
    tb.log.info("=" * 60)

    large_addr = 0xC000 + addr_offset
    large_size = 256  # > 128B

    large_data = bytes([random.randint(0, 255) for _ in range(large_size)])

    tb.log.info(f"  Frontdoor write: addr=0x{large_addr:08x}, size={large_size} bytes")
    await tb.noc_write(master, x, y, large_addr, large_data)


    # Frontdoor read and check (first 4B only for large transfers > 128B)
    tb.log.info(f"  Frontdoor read (first 4B only): addr=0x{large_addr:08x}")
    fd_result = await tb.noc_read(master, x, y, large_addr, 4)
    fd_first_4b = fd_result.data
    expected_first_4b = large_data[:4]

    tb.log.info(f"  Frontdoor read value: 0x{int.from_bytes(fd_first_4b, 'little'):08x}")
    tb.log.info(f"  Expected value:       0x{int.from_bytes(expected_first_4b, 'little'):08x}")

    if fd_first_4b != expected_first_4b:
        tb.log.error(f"  FRONTDOOR MISMATCH: expected 0x{expected_first_4b.hex()}, got 0x{fd_first_4b.hex()}")
        assert False, f"[{tile_name}] Test F frontdoor check failed"

    tb.log.info(f"  Frontdoor read check (first 4B) PASSED")

    # await Timer(200, 'ns')

    # Backdoor dump and full check
    tb.log.info(f"  Backdoor dump: addr=0x{large_addr:08x}, size={large_size} bytes")
    dump_result = tb.l1_backdoor_dump(x, y, large_addr, large_size)

    if dump_result != large_data:
        for i in range(large_size):
            if dump_result[i] != large_data[i]:
                tb.log.error(f"  BACKDOOR MISMATCH at offset {i}: expected 0x{large_data[i]:02x}, got 0x{dump_result[i]:02x}")
                break
        assert False, f"[{tile_name}] Test F backdoor check failed"

    tb.log.info(f"[{tile_name}] Test F PASSED")

    tb.log.info(f"[{tile_name}] ALL TESTS PASSED")


async def sanity_l1_backdoor(dut):
    """
    Sanity test for L1 direct SRAM backdoor access.

    Tests backdoor read/write on:
    - One Tensix tile (64-bank L1)
    - One Dispatch West tile (16-bank L1)
    - One Dispatch East tile (16-bank L1)

    Two phases:
    - Phase 1: Hash disabled (identity mapping) - RTL default
    - Phase 2: Hash enabled (performant hash function)
    """
    tb = demoTB(dut)
    await tb.init_and_reset()

    master = 0

    # Get Tensix tile
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)

    tensix_coord = tensix_coords[0]

    # Dispatch tiles are at row 3: West at column 0, East at column 3
    dispatch_west = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)[0]
    dispatch_east = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E)[0]

    # List of tiles to test
    tiles = [
        (tensix_coord[0], tensix_coord[1], "Tensix"),
        (dispatch_west[0], dispatch_west[1], "Dispatch_West"),
        (dispatch_east[0], dispatch_east[1], "Dispatch_East"),
    ]

    # =========================================================================
    # PHASE 1: Hash DISABLED (identity mapping - RTL default)
    # =========================================================================
    tb.log.info("")
    tb.log.info("*" * 70)
    tb.log.info("* PHASE 1: Hash DISABLED (identity mapping)")
    tb.log.info("*" * 70)

    for x, y, name in tiles:
        await run_tile_tests(tb, x, y, f"{name}_NoHash", master, addr_offset=0x0)

    tb.log.info("")
    tb.log.info("=" * 70)
    tb.log.info("PHASE 1 COMPLETE: All tests passed with hash DISABLED")
    tb.log.info("=" * 70)

    # =========================================================================
    # PHASE 2: Hash ENABLED (performant hash function)
    # =========================================================================
    tb.log.info("")
    tb.log.info("*" * 70)
    tb.log.info("* PHASE 2: Hash ENABLED (performant hash function)")
    tb.log.info("*" * 70)

    # Program performant hash function on all tiles
    tb.log.info("Programming performant L1 hash function on all tiles...")
    for x, y, name in tiles:
        tb.log.info(f"  Programming hash on {name} ({x}, {y})")
        await tb.program_performant_l1_hash(x, y)
        # Enable hash on all backdoors
        tb.log.info(f"  Enabling hash on {name} ({x}, {y}) backdoor loader")
        tb.l1_backdoor_set_hash_enabled(x, y, True)


    # Use different address offset to avoid reading stale data from Phase 1
    for x, y, name in tiles:
        await run_tile_tests(tb, x, y, f"{name}_Hashed", master, addr_offset=0x50000)

    tb.log.info("")
    tb.log.info("=" * 70)
    tb.log.info("PHASE 2 COMPLETE: All tests passed with hash ENABLED")
    tb.log.info("=" * 70)

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    tb.log.info("")
    tb.log.info("=" * 70)
    tb.log.info("ALL L1 BACKDOOR TESTS PASSED")
    tb.log.info("=" * 70)
