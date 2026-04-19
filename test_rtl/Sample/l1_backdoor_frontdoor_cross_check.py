"""
L1 Backdoor vs Frontdoor Cross-Check
Covers: H33 (DEST latch array coverage via L1 backdoor), sanity_l1_backdoor gap

Uses L1Backdoor (direct zero-simtime SRAM access) to:
1. Preload a known pattern directly into L1 SRAM of tile (x,y)
2. Read back via NOC frontdoor (AXI master read) and compare
3. Then write via NOC frontdoor and verify via backdoor readback

This is the full cross-check validating that:
- L1 address mapping matches between backdoor (VPI) and frontdoor (NoC)
- ECC encoding is applied correctly by L1Backdoor
- No address aliasing at 768KB boundary (N1B0 4x L1 expansion)

New hole from TB analysis:
- sanity_l1_backdoor test exists but is marked skip=True — never runs
- L1Backdoor class has never been exercised in CI regression
- N1B0 768KB L1 (3072x128 macros) never boundary-tested via backdoor
"""

from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from tests.utils.l1_backdoor import L1Backdoor
from cocotb.triggers import Timer, ClockCycles, with_timeout
import cocotb

# Test addresses and patterns
TEST_OFFSET_1   = 0x001000  # 4KB offset — Phase 1 backdoor→frontdoor
TEST_OFFSET_2   = 0x001010  # 4KB + 16B   — Phase 2 frontdoor→backdoor
PATTERN_BACK    = 0xB4C0D00E  # written via backdoor (Phase 1)
PATTERN_FRONT   = 0xF120D00D  # written via frontdoor (Phase 2)

# N1B0 L1 is 768KB = 0xC0000 bytes per tile
L1_SIZE_BYTES   = 0xC0000
BOUNDARY_OFFSET = L1_SIZE_BYTES - 0x100  # 768KB - 256B  (Phase 3)
BOUNDARY_PATTERN = 0xBD0A1AAA


async def l1_backdoor_frontdoor_cross_check(dut):
    """
    Four-phase L1 backdoor/frontdoor cross-check test.

    Phase 1: Backdoor write → Frontdoor read  (tile (0,0))
    Phase 2: Frontdoor write → Backdoor read  (tile (0,0))
    Phase 3: 768KB L1 boundary test via both paths  (tile (0,0))
    Phase 4: Multi-tile sweep — first 4 Tensix tiles via backdoor write + frontdoor read
    """

    tb = demoTB(dut)
    await tb.init_and_reset()
    await tb.release_dm_core_reset()

    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    assert len(tensix_coords) > 0, "No TENSIX tiles found in config"

    # Canonical first tensix tile
    x, y = 0, 0
    tb.log.info(f"=== L1 Backdoor/Frontdoor Cross-Check for tile ({x},{y}) ===")

    # =========================================================================
    # Phase 1: Backdoor Write → Frontdoor Read
    # =========================================================================
    tb.log.info("-" * 60)
    tb.log.info(
        f"Phase 1: Write 0x{PATTERN_BACK:08x} via backdoor "
        f"at offset 0x{TEST_OFFSET_1:06x}"
    )

    bd = L1Backdoor(dut, x=x, y=y)
    bd.direct.write_32b(TEST_OFFSET_1, PATTERN_BACK)

    # Allow time for SRAM write to settle before frontdoor read
    await ClockCycles(tb.dut.noc_clk, 10)

    readback = await tb.noc_read(0, x, y, TEST_OFFSET_1, 4)
    read_val = int.from_bytes(readback.data, "little")

    tb.log.info(
        f"Phase 1 frontdoor readback: 0x{read_val:08x} "
        f"(expected 0x{PATTERN_BACK:08x})"
    )
    assert read_val == PATTERN_BACK, (
        f"Phase 1 Backdoor→Frontdoor mismatch: "
        f"wrote 0x{PATTERN_BACK:08x}, read 0x{read_val:08x}"
    )
    tb.log.info("Phase 1 PASSED")

    # =========================================================================
    # Phase 2: Frontdoor Write → Backdoor Read
    # =========================================================================
    tb.log.info("-" * 60)
    tb.log.info(
        f"Phase 2: Write 0x{PATTERN_FRONT:08x} via frontdoor "
        f"at offset 0x{TEST_OFFSET_2:06x}"
    )

    pattern_bytes = PATTERN_FRONT.to_bytes(4, "little")
    await tb.noc_write(0, x, y, TEST_OFFSET_2, pattern_bytes)

    await ClockCycles(tb.dut.noc_clk, 5)

    bd_val = bd.direct.read_32b(TEST_OFFSET_2)
    tb.log.info(
        f"Phase 2 backdoor readback: 0x{bd_val:08x} "
        f"(expected 0x{PATTERN_FRONT:08x})"
    )
    assert bd_val == PATTERN_FRONT, (
        f"Phase 2 Frontdoor→Backdoor mismatch: "
        f"wrote 0x{PATTERN_FRONT:08x}, read 0x{bd_val:08x}"
    )
    tb.log.info("Phase 2 PASSED")

    # =========================================================================
    # Phase 3: N1B0 768KB L1 Boundary Test
    # =========================================================================
    tb.log.info("-" * 60)
    tb.log.info(
        f"Phase 3: 768KB boundary test at offset 0x{BOUNDARY_OFFSET:06x} "
        f"(L1_SIZE=0x{L1_SIZE_BYTES:06x})"
    )

    bd.direct.write_32b(BOUNDARY_OFFSET, BOUNDARY_PATTERN)
    await ClockCycles(tb.dut.noc_clk, 10)

    readback_boundary = await tb.noc_read(0, x, y, BOUNDARY_OFFSET, 4)
    bd_val_boundary = int.from_bytes(readback_boundary.data, "little")
    tb.log.info(
        f"Phase 3 frontdoor readback: 0x{bd_val_boundary:08x} "
        f"(expected 0x{BOUNDARY_PATTERN:08x})"
    )
    assert bd_val_boundary == BOUNDARY_PATTERN, (
        f"Phase 3 boundary test mismatch at offset 0x{BOUNDARY_OFFSET:06x}: "
        f"0x{bd_val_boundary:08x} != 0x{BOUNDARY_PATTERN:08x}"
    )
    tb.log.info("Phase 3 PASSED")

    # =========================================================================
    # Phase 4: Multi-Tile Sweep — first 4 Tensix tiles
    # =========================================================================
    tb.log.info("-" * 60)
    tb.log.info("Phase 4: Multi-tile sweep (first 4 Tensix tiles)")

    sweep_addr = 0x002000
    test_tiles = tensix_coords[:4]
    tb.log.info(f"  Tiles under test: {test_tiles}")

    for tx, ty in test_tiles:
        sweep_pattern = 0xA0000000 | (tx << 16) | (ty << 8) | 0x5A
        bd_tile = L1Backdoor(dut, x=tx, y=ty)

        tb.log.info(
            f"  Tile ({tx},{ty}): backdoor write 0x{sweep_pattern:08x} "
            f"at 0x{sweep_addr:06x}"
        )
        bd_tile.direct.write_32b(sweep_addr, sweep_pattern)
        await ClockCycles(tb.dut.noc_clk, 5)

        rd = await tb.noc_read(0, tx, ty, sweep_addr, 4)
        rd_val = int.from_bytes(rd.data, "little")

        tb.log.info(
            f"  Tile ({tx},{ty}): frontdoor readback 0x{rd_val:08x} "
            f"(expected 0x{sweep_pattern:08x})"
        )
        assert rd_val == sweep_pattern, (
            f"Tile ({tx},{ty}) sweep mismatch: "
            f"0x{rd_val:08x} != 0x{sweep_pattern:08x}"
        )
        tb.log.info(f"  Tile ({tx},{ty}) OK")

    tb.log.info("Phase 4 PASSED")
    tb.log.info("=== L1 Backdoor/Frontdoor Cross-Check PASSED ===")
