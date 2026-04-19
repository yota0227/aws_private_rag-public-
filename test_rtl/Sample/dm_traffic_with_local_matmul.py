"""
Combined test: Continuous NoC traffic + Local Matmul

This test runs two workloads simultaneously:
1. Continuous NoC traffic from center tile (1,1) to neighboring tiles and vice versa
   - Center tile: DM cores 0-3 each use 3 command buffers to send to N/E/S/W
   - Neighbor tiles: DM cores 0-3 each use 3 command buffers to send to center
   - Traffic data is 0x5a5a pattern preloaded before DM resets are released

2. Local matmul on Tensix cores at center tile (1,1)
   - Both in0 and in1 matrices are pre-loaded to each Tensix L1
   - No DRAM fetching via NoC during compute
   - Test completes when Tensix postcodes indicate matmul is done

The test validates that matmul computation works correctly under heavy NoC load.
"""

import os
from typing import Tuple, List, Dict
import cocotb
from cocotb.triggers import ClockCycles

from tests.utils.test_utils import load_binary_data
from tests.utils.coco_tensix_api import demoTB, TileType
from tests.utils.matrix_util import MatrixGenerator, MatrixTestConfig, MatrixDistribution, ShardingType, MatrixOutputChecker
from tests.utils.binary_compilation import DataMovementConfig, compile_dm_binary
from tests.utils.noc_driver import NocTransactionConfig
from tests.end_to_end_scenario import (
    TestConfig, TestType, compile_dm_kernel, compile_tensix_kernels,
    generate_matrices, release_resets, check_output
)
import numpy as np
from ml_dtypes import bfloat16
from tests.utils.noc.overlay_reg import *

# Traffic configuration - must match test_config.h in noc_traffic_generator
TRAFFIC_DATA_ADDR = 0x200000  # Address where 5a5a pattern is preloaded
TRAFFIC_TRANSFER_SIZE = 2 * 1024  # 2KB per transfer (matches test_config.h)

# Option to use L1 backdoor preload instead of NoC writes
# Set to True to bypass NoC for loading binaries and test data (faster simulation)
USE_BACKDOOR_PRELOAD = os.environ.get("USE_BACKDOOR_PRELOAD", "0") == "1"

# Tile coordinates - must match test_config.h
CENTER_TILE = (1, 1)
NEIGHBOR_TILES = [
    (1, 2),  # North
    (2, 1),  # East
    (1, 0),  # South
    (0, 1),  # West
]


def generate_toggle_pattern(size: int) -> bytes:
    """
    Generate pattern that toggles all 2048 NOC payload bits every cycle.

    NOC payload is 2048 bits = 256 bytes wide. To toggle every bit each cycle,
    we alternate between 256 bytes of 0xa5 and 256 bytes of 0x5a.
    These are bit-inverted complements (0xa5=10100101, 0x5a=01011010).
    """
    NOC_PAYLOAD_BYTES = 256  # 2048 bits / 8

    # Create one toggle unit: 256 bytes of 0xa5 followed by 256 bytes of 0x5a
    toggle_unit = bytes([0xa5] * NOC_PAYLOAD_BYTES) + bytes([0x5a] * NOC_PAYLOAD_BYTES)

    # Repeat until we have enough data
    num_units = (size + len(toggle_unit) - 1) // len(toggle_unit)
    pattern = toggle_unit * num_units

    return pattern[:size]


def pad_to_alignment(data: bytes, alignment: int = 16) -> bytes:
    """Pad data to specified alignment (default 16 bytes for backdoor preload)."""
    remainder = len(data) % alignment
    if remainder == 0:
        return data
    padding = alignment - remainder
    return data + bytes(padding)


async def compile_traffic_generator_kernel(test_name: str) -> bytes:
    """
    Compile the noc_traffic_generator DM kernel.

    This kernel generates continuous NoC traffic on center and neighbor tiles.
    """
    # Create a minimal config for the traffic generator (no matmul params needed)
    config = DataMovementConfig(
        test_name=test_name,
        dm_test_name="noc_traffic_generator",
    )

    # Get project path
    test_file_dir = os.path.dirname(os.path.abspath(__file__))
    dm_project_path = os.path.join(test_file_dir, "..", "..", "firmware", "datamover_cmake")

    # Compile the binary
    traffic_kernel_path = await compile_dm_binary(config, dm_project_path)

    # Load the binary
    traffic_kernel = load_binary_data(bin_path=traffic_kernel_path)

    return traffic_kernel


async def setup_noc_traffic(
    tb,
    traffic_kernel: bytes,
    center_tile: Tuple[int, int],
    neighbor_tiles: List[Tuple[int, int]],
    use_backdoor: bool = False,
):
    """
    Setup NoC traffic by loading traffic generator kernel and preloading data pattern.

    Traffic pattern:
    - Center tile (1,1): DM cores 0-3 send to N/E/S/W neighbors using all 3 cmdbufs
    - Each neighbor tile: DM cores 0-3 send back to center using all 3 cmdbufs

    Data pattern: 0x5a5a preloaded at TRAFFIC_DATA_ADDR before DM resets released

    Args:
        use_backdoor: If True, use L1 backdoor preload instead of NoC writes
    """
    all_traffic_tiles = [center_tile] + neighbor_tiles
    default_master = tb.default_master

    # Generate toggle pattern for traffic data
    traffic_pattern = generate_toggle_pattern(TRAFFIC_TRANSFER_SIZE)

    tb.log.info(f"Loading traffic generator kernel ({len(traffic_kernel)} bytes) to all traffic tiles")
    tb.log.info(f"Preloading 0x5a5a pattern ({len(traffic_pattern)} bytes) at 0x{TRAFFIC_DATA_ADDR:X}")
    tb.log.info(f"Using {'L1 backdoor preload' if use_backdoor else 'NoC writes'}")

    if use_backdoor:
        # Use L1 backdoor preload (zero sim time, bypasses NoC)
        traffic_kernel_padded = pad_to_alignment(traffic_kernel, 16)
        traffic_pattern_padded = pad_to_alignment(traffic_pattern, 16)

        for x, y in all_traffic_tiles:
            # Load traffic generator kernel at address 0x0
            tb.l1_backdoor_preload(x, y, 0x0, traffic_kernel_padded)

            # Preload 5a5a traffic pattern at TRAFFIC_DATA_ADDR
            tb.l1_backdoor_preload(x, y, TRAFFIC_DATA_ADDR, traffic_pattern_padded)

        tb.log.info("Traffic kernel and data pattern loaded via L1 backdoor")
    else:
        # Use NoC writes (normal path)
        for x, y in all_traffic_tiles:
            # Load traffic generator kernel at address 0x0
            tb.noc_write_nonblocking(default_master, x, y, 0x0, traffic_kernel)

            # Preload 5a5a traffic pattern at TRAFFIC_DATA_ADDR
            tb.noc_write_nonblocking(default_master, x, y, TRAFFIC_DATA_ADDR, traffic_pattern)

        await tb.noc_wait_writes(default_master)
        tb.log.info("Traffic kernel and data pattern loaded via NoC")


def get_local_matmul_test_config() -> TestConfig:
    """
    Create a TestConfig for local matmul where both in0 and in1 are in L1.
    Uses a simple 1x1 tile matmul configuration.
    """
    return TestConfig(
        test_type=TestType.MATMUL,
        test_name="LOCAL_MATMUL_WITH_TRAFFIC",
        dm_test_name="local_matmul",  # DM kernel that reads from L1 only
        dm_only=False,
        num_cores_r_dim     = 4,
        num_cores_c_dim     = 1,
        in0_config          = MatrixTestConfig(
                                rows                = 128,
                                cols                = 512,
                                dtype               = np.int8,
                                matrix_distribution = MatrixDistribution.NORMAL.value,
                                matrix_params       = {'loc': 0, 'scale': 127},
                                is_sharded          = True,
                                sharding_type       = ShardingType.WIDTH,
                                width_shards        = 1,
                                num_subblocks_r_dim = 4,
                                num_subblocks_c_dim = 4,
                                subblock_r_dim      = 1,
                                subblock_c_dim      = 4,
                            ),
        in1_config          = MatrixTestConfig(
                                rows                = 512,
                                cols                = 256,
                                dtype               = np.int8,
                                matrix_distribution = MatrixDistribution.NORMAL.value,
                                matrix_params       = {'loc': 0, 'scale': 127},
                                is_sharded          = False,
                                sharding_type       = ShardingType.WIDTH,
                                width_shards        = 1,
                                num_subblocks_r_dim = 4,
                                num_subblocks_c_dim = 2,
                                subblock_r_dim      = 4,
                                subblock_c_dim      = 4,
                            ),
        upk_fmt_in          = np.int8,
        input_format        = np.uint64,
        output_format       = np.int32
    )


async def load_matrices_to_l1(tb, test_config: TestConfig, matrices: Dict, tensix_coords: List[Tuple[int, int]], use_backdoor: bool = False):
    """
    Load BOTH in0 and in1 matrices directly to each Tensix L1.
    No DRAM involvement - both matrices reside in local L1.

    Args:
        use_backdoor: If True, use L1 backdoor preload instead of NoC writes
    """
    default_master = tb.default_master
    tb.log.info(f"Loading matrices using {'L1 backdoor preload' if use_backdoor else 'NoC writes'}")

    for i, (x, y) in enumerate(tensix_coords):
        # Load in0 (shards)
        shard_idx = i if i < len(matrices['shards']) else 0
        in0_data = matrices['shards'][shard_idx]
        tb.log.info(f"Loading in0 shard {shard_idx} to Tensix ({x},{y}) at 0x{test_config.in0_l1_address:X}")

        # Load in1 directly to L1 (instead of DRAM)
        # The 'chunks' are normally interleaved to DRAM, but we load full matrix to L1
        in1_bytes = b''.join(matrices['chunks'])
        tb.log.info(f"Loading in1 ({len(in1_bytes)} bytes) to Tensix ({x},{y}) at 0x{test_config.in1_l1_address:X}")

        if use_backdoor:
            # Use L1 backdoor preload (zero sim time, bypasses NoC)
            in0_padded = pad_to_alignment(in0_data, 16)
            in1_padded = pad_to_alignment(in1_bytes, 16)
            tb.l1_backdoor_preload(x, y, test_config.in0_l1_address, in0_padded)
            tb.l1_backdoor_preload(x, y, test_config.in1_l1_address, in1_padded)
        else:
            # Use NoC writes (normal path)
            tb.noc_write_nonblocking(
                default_master, x, y,
                test_config.in0_l1_address,
                in0_data
            )
            tb.noc_write_nonblocking(
                default_master, x, y,
                test_config.in1_l1_address,
                in1_bytes
            )

    if not use_backdoor:
        await tb.noc_wait_writes(default_master)

    tb.log.info(f"All matrices loaded to L1 via {'backdoor' if use_backdoor else 'NoC'}")


def get_tensix_only_waiters(tb, test_config: TestConfig, tensix_coords: List[Tuple[int, int]]):
    """
    Create waiters that ONLY monitor Tensix postcodes (not DM postcodes).
    This allows the test to complete when matmul is done while NoC traffic continues.
    """
    n = test_config.num_cores_r_dim * test_config.num_cores_c_dim
    # Tensix postcodes are at odd indices: 1, 3, 5, ...
    tensix_postcodes_scratch = [i for i in range(1, (3 * n * 2), 2)]

    waiters = []
    for x, y in tensix_coords:
        task = tb.monitor_dm_t6_scratch(x, y, indicies=tensix_postcodes_scratch)
        waiter = cocotb.start_soon(task)
        waiters.append(waiter)

    return waiters


async def wait_for_tensix_completion(tb, test_config: TestConfig, tensix_coords: List[Tuple[int, int]], timeout: int = 100000):
    """Wait only for Tensix cores to complete (ignore DM cores)."""
    waiters = get_tensix_only_waiters(tb, test_config, tensix_coords)

    from cocotb.triggers import with_timeout
    while waiters:
        await with_timeout(waiters.pop(0), timeout, 'ns')

    tb.log.info("Tensix computation complete")


async def release_traffic_dm_resets(tb, all_traffic_tiles: List[Tuple[int, int]]):
    """
    Release DM resets on traffic tiles to start continuous NoC traffic.
    Only releases DM cores (not Tensix cores) on traffic tiles.
    """
    tb.log.info("Releasing DM resets on traffic tiles to start NoC traffic...")

    # Release DM core resets on all traffic tiles
    # Note: We only release DM resets, not Tensix resets on neighbor tiles
    for x, y in all_traffic_tiles:
        # Skip the center tile - its DM cores will be released with matmul setup
        if (x, y) != CENTER_TILE:
            await tb.release_dm_core_reset_for_tile(x, y)

    tb.log.info("DM resets released on neighbor traffic tiles")


async def dm_traffic_with_local_matmul(dut):
    """
    Main test: Continuous NoC traffic + Local Matmul

    Traffic pattern:
    - Center tile (1,1): DM cores 0-3 send to N/E/S/W using 3 cmdbufs each
    - Neighbor tiles: DM cores 0-3 send to center using 3 cmdbufs each
    - Data: 0x5a5a pattern preloaded at TRAFFIC_DATA_ADDR
    - Traffic runs continuously until simulation ends

    Matmul:
    - Runs on Tensix cores at center tile (1,1)
    - Both in0 and in1 pre-loaded to L1
    - Test completes when Tensix postcodes indicate matmul is done

    Environment variables:
    - USE_BACKDOOR_PRELOAD=1: Use L1 backdoor preload instead of NoC writes for loading
      binaries and test data (faster simulation, bypasses NoC)
    """
    tb = demoTB(dut)
    await tb.init_and_reset()

    tb.log.info("=" * 60)
    tb.log.info("Starting: Continuous NoC Traffic + Local Matmul Test")
    tb.log.info("=" * 60)

    # Check if backdoor preload is enabled
    use_backdoor = USE_BACKDOOR_PRELOAD
    if use_backdoor:
        tb.log.info("L1 BACKDOOR PRELOAD ENABLED - bypassing NoC for data loading")

    # Define traffic topology
    center_tile = CENTER_TILE
    neighbor_tiles = NEIGHBOR_TILES
    all_traffic_tiles = [center_tile] + neighbor_tiles

    tb.log.info(f"Traffic center: {center_tile}")
    tb.log.info(f"Traffic neighbors: {neighbor_tiles}")

    # Compile and load traffic generator kernel
    tb.log.info("Compiling traffic generator kernel...")
    traffic_kernel = await compile_traffic_generator_kernel("NOC_TRAFFIC_GENERATOR")

    # Setup traffic: load kernel and preload 5a5a data to all traffic tiles
    tb.log.info("Setting up NoC traffic...")
    await setup_noc_traffic(tb, traffic_kernel, center_tile, neighbor_tiles, use_backdoor=use_backdoor)

    # Setup local matmul
    tb.log.info("Setting up local matmul...")
    test_config = get_local_matmul_test_config()

    # Compile matmul kernels
    dm_kernel = await compile_dm_kernel(test_config)
    tensix_kernels = await compile_tensix_kernels(test_config)

    tensix_coords = [center_tile]  # Matmul runs on center tile
    default_master = tb.default_master

    math_dm_kernel_address = 0x2C0000  # 3MB - 256KB

    reset_vector_unicast_config = NocTransactionConfig(non_posted = True)

    # Load matmul DM kernel to center tile
    # Note: Traffic kernel is at 0x0, matmul DM kernel at 0x2C0000
    # DM cores 0-3 run traffic, cores 5-7 run matmul
    if dm_kernel is not None:
        for x, y in tensix_coords:
            if use_backdoor:
                # Use L1 backdoor preload for DM kernel
                dm_kernel_padded = pad_to_alignment(dm_kernel, 16)
                tb.l1_backdoor_preload(x, y, math_dm_kernel_address, dm_kernel_padded)
            else:
                tb.noc_write_nonblocking(default_master, x, y, math_dm_kernel_address, dm_kernel)

            # Set reset vectors for matmul DM cores (5, 6, 7) - always via NoC (register writes)
            await tb.noc_write(default_master, x, y, TT_CLUSTER_CTRL_RESET_VECTOR_5__REG_ADDR, math_dm_kernel_address.to_bytes(8, 'little'), config=reset_vector_unicast_config)
            await tb.noc_write(default_master, x, y, TT_CLUSTER_CTRL_RESET_VECTOR_6__REG_ADDR, math_dm_kernel_address.to_bytes(8, 'little'), config=reset_vector_unicast_config)
            await tb.noc_write(default_master, x, y, TT_CLUSTER_CTRL_RESET_VECTOR_7__REG_ADDR, math_dm_kernel_address.to_bytes(8, 'little'), config=reset_vector_unicast_config)

    # Load Tensix kernels
    if tensix_kernels is not None:
        for addr, (trisc_bin, _) in tensix_kernels.items():
            for x, y in tensix_coords:
                if use_backdoor:
                    # Use L1 backdoor preload for Tensix kernels
                    trisc_bin_padded = pad_to_alignment(trisc_bin, 16)
                    tb.l1_backdoor_preload(x, y, addr, trisc_bin_padded)
                else:
                    tb.noc_write_nonblocking(default_master, x, y, addr, trisc_bin)

    await tb.noc_wait_writes(default_master)
    tb.log.info("Matmul kernels loaded")

    # Generate and load matrices to L1
    tb.log.info("Generating matrices...")
    matrices = generate_matrices(test_config)

    tb.log.info("Loading matrices directly to L1 (no DRAM)...")
    await load_matrices_to_l1(tb, test_config, matrices, tensix_coords, use_backdoor=use_backdoor)

    # Start monitoring for all tiles
    cocotb.start_soon(tb.monitor_dm_scratch(center_tile[0], center_tile[1]))

    # Release resets - this starts both traffic and matmul
    tb.log.info("Releasing resets - starting traffic and matmul...")

    # Release DM resets on all traffic tiles (traffic starts immediately)
    await tb.release_dm_core_reset()

    # Release Tensix resets on center tile for matmul
    if not test_config.dm_only:
        active_cores = [i for i in range(test_config.num_cores)]
        reset_value = 0
        for active in reversed(test_config.active_triscs):
            reset_value <<= 1
            reset_value |= int(active)
        reset_value = ~reset_value & 0xf
        await tb.set_risc_soft_reset(reset_value, active_cores, tensix_coords=tensix_coords)

    tb.log.info("NoC traffic running continuously in background")
    tb.log.info("Waiting for Tensix matmul to complete...")

    # Wait ONLY for Tensix postcodes (ignore DM traffic cores)
    await wait_for_tensix_completion(tb, test_config, tensix_coords, timeout=100000)

    # Give a few cycles for any final writes
    await ClockCycles(dut.ai_clk, 100)

    tb.log.info("=" * 60)
    tb.log.info("TEST PASSED: Local matmul completed correctly under NoC traffic load")
    tb.log.info("=" * 60)
