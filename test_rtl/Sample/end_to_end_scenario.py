import os
from typing import Tuple, List, Dict, Optional, Callable, Awaitable
import cocotb
# from api.aether_tb import AetherTB
from tests.utils.coco_tensix_api import demoTB, TileType
from tests.utils.test_utils import load_binary_data, find_largest_rectangle, get_tensix_kernels_with_addresses
from tests.utils.binary_compilation import DataMovementConfig, TensixConfig, compile_dm_binary, compile_tensix_binary
from tests.utils.matrix_util import MatrixGenerator, MatrixTestConfig, MatrixDistribution, ShardingType, MatrixOutputChecker
from tests.utils.tensix_config import TileType
import asyncio
import numpy as np
from ml_dtypes import bfloat16
from dataclasses import dataclass, field
from enum import Enum, auto

class TestType(Enum):
    DATACOPY = auto()
    MATMUL = auto()

# TODO: infer dm_test_name?
@dataclass
class TestConfig:
    test_type: TestType
    test_name: str = "?"
    dm_test_name: str = "aether_sanity"
    dm_only: bool = False
    emulation: bool = False
    num_cores_r_dim: int = 1
    num_cores_c_dim: int = 1
    num_clusters_r_dim: int = 1
    num_clusters_c_dim: int = 1
    active_triscs: tuple[bool, bool, bool, bool] = (True, True, True, False)
    in0_config: MatrixTestConfig = field(default_factory=MatrixTestConfig)
    in1_config: MatrixTestConfig = field(default_factory=MatrixTestConfig)
    upk_fmt_in: type = np.dtype(np.int8)
    input_format: type = np.dtype(np.float16)
    # dest_format: type = np.dtype(np.float16) # Use this to set the pack_out format
    output_format: type = np.dtype(np.float16)
    in0_l1_address: Optional[int] = None
    in1_l1_address: Optional[int] = None
    out_l1_address: Optional[int] = None
    l1_shard_addr: Optional[int] = None
    perf_l1_hash: bool = False

    # Coordinate overrides for DataMovementConfig
    worker_core_coord: Optional[Tuple[int, int]] = None  # (x, y) worker core coordinate
    dram_coords: Optional[List[Tuple[int, int]]] = None  # [(x0, y0), (x1, y1), ...] DRAM bank coordinates

    def __post_init__(self):
        assert type(self.output_format) is type
        assert type(self.in0_config.dtype) is type
        assert type(self.in1_config.dtype) is type
        if self.test_type == TestType.MATMUL:
            assert self.in0_config.cols == self.in1_config.rows
            assert self.in0_config.subblock_c_dim == self.in1_config.subblock_r_dim
            assert not self.in1_config.is_sharded # TODO: is this true?
        # assert self.in0_config.rows == 32*self.num_tiles_r_dim
        # assert self.in0_config.cols == 32*self.num_tiles_k_dim
        # assert self.in1_config.rows == 32*self.num_tiles_k_dim
        # assert self.in1_config.cols == 32*self.num_tiles_c_dim
        if self.in0_l1_address is None:
            self.in0_l1_address = 0x52000
        if self.in1_l1_address is None:
            self.in1_l1_address = self.in0_l1_address + self.in0_size
        if self.out_l1_address is None:
            if self.test_type == TestType.DATACOPY:
                self.out_l1_address = self.in1_l1_address
            else:
                self.out_l1_address = self.in1_l1_address + self.in1_size



        print(f"[TestConfig] final in0_l1_address = {hex(self.in0_l1_address)}")
        print(f"[TestConfig] final in1_l1_address = {hex(self.in1_l1_address)}")
        print(f"[TestConfig] final out_l1_address = {hex(self.out_l1_address)}")

    # @property
    # def input_format(self):
    #     return self.input_format

    @property
    def num_cores(self):
        return self.num_cores_c_dim * self.num_cores_r_dim

    @property
    def rows(self):
        return self.in0_config.rows

    @property
    def cols(self):
        if self.test_type == TestType.MATMUL:
            return self.in1_config.cols
        return self.in0_config.cols

    @property
    def subblock_r_dim(self):
        if self.test_type != TestType.MATMUL:
            return None
        return self.in0_config.subblock_r_dim

    @property
    def subblock_c_dim(self):
        if self.test_type != TestType.MATMUL:
            return None
        return self.in1_config.subblock_c_dim

    @property
    def subblock_k_dim(self):
        if self.test_type != TestType.MATMUL:
            return None
        return self.in0_config.subblock_c_dim

    @property
    def num_subblocks_r_dim(self):
        if self.test_type != TestType.MATMUL:
            return None
        return self.in0_config.num_subblocks_r_dim

    @property
    def num_subblocks_c_dim(self):
        if self.test_type != TestType.MATMUL:
            return None
        return self.in1_config.num_subblocks_c_dim

    @property
    def num_subblocks_k_dim(self):
        if self.test_type != TestType.MATMUL:
            return None
        return self.in0_config.num_subblocks_c_dim

    @property
    def in0_size(self):
        return self.in0_config.rows * self.in0_config.cols * np.dtype(self.input_format).itemsize

    @property
    def in1_size(self):
        return self.in1_config.rows * self.in1_config.cols * np.dtype(self.input_format).itemsize

    @property
    def out_size(self):
        return self.rows * self.cols * np.dtype(self.output_format).itemsize

    @property
    def num_tiles_r_dim(self):
        return self.in0_config.num_subblocks_r_dim * self.in0_config.subblock_r_dim

    @property
    def num_tiles_c_dim(self):
        return self.in1_config.num_subblocks_c_dim * self.in1_config.subblock_c_dim

    @property
    def num_tiles_k_dim(self):
        return self.in0_config.num_subblocks_c_dim * self.in0_config.subblock_c_dim

    @property
    def num_tiles_r_dim_per_core(self):
        return self.num_tiles_r_dim // self.num_cores_r_dim

    @property
    def num_clusters(self):
        return self.num_clusters_r_dim * self.num_clusters_c_dim

    @property
    def num_output_tiles(self):
        return self.num_tiles_r_dim * self.num_tiles_c_dim

    @property
    def in0_offset_ids(self):
        if self.test_type == TestType.DATACOPY:
            return [0, 0, 0, 0]
        elif self.num_cores == 1:
            return [0]
        total_num_tiles_in_r_dim = self.subblock_r_dim * self.subblock_k_dim * self.num_subblocks_r_dim
        total_num_tiles_in_r_dim_per_cluster = total_num_tiles_in_r_dim // self.num_clusters_r_dim
        total_num_tiles_in_r_dim_per_core = total_num_tiles_in_r_dim_per_cluster // self.num_cores_r_dim
        assert total_num_tiles_in_r_dim_per_core % self.subblock_r_dim == 0
        if self.num_cores_r_dim == 4:
            ## THIS IS FOR 1D MATMUL WIDTH SHARDED
            return [i for i in range(0, total_num_tiles_in_r_dim, total_num_tiles_in_r_dim_per_core)]
        elif self.num_cores_c_dim == 4:
            raise NotImplementedError
        elif self.num_cores_r_dim == 2:
            ## THIS IS FOR 2D MATMUL
            return [0, 0, total_num_tiles_in_r_dim_per_core, total_num_tiles_in_r_dim_per_core]

    @property
    def in1_offset_ids(self):
        if self.test_type == TestType.DATACOPY:
            return None
        elif self.num_cores == 1:
            return [0]
        total_num_tiles_in_c_dim = self.subblock_c_dim * self.subblock_k_dim * self.num_subblocks_c_dim
        total_num_tiles_in_c_dim_per_cluster = total_num_tiles_in_c_dim // self.num_clusters_c_dim
        total_num_tiles_in_c_dim_per_core = total_num_tiles_in_c_dim_per_cluster // self.num_cores_c_dim
        assert total_num_tiles_in_c_dim_per_core % self.subblock_c_dim == 0
        if self.num_cores_r_dim == 4:
            return [0, 0, 0, 0]
        elif self.num_cores_c_dim == 4:
            raise NotImplementedError
        elif self.num_cores_c_dim == 2:
            return [0, total_num_tiles_in_c_dim_per_core, 0, total_num_tiles_in_c_dim_per_core]

    @property
    def out_offset_ids(self):
        if self.test_type == TestType.DATACOPY:
            return [0, 0, 0, 0]
        num_output_tiles_per_cluster = self.num_output_tiles // self.num_clusters 
        num_output_per_core = num_output_tiles_per_cluster // self.num_cores
        return [i for i in range(0, num_output_tiles_per_cluster, num_output_per_core)]

    @classmethod
    def test_config_from_params(cls, NCR, NCC, ncr, ncc, sk, sr, sc, k, r, c):
        # Ensure num_subblocks_* will never be 0
        assert r >= sr and r // sr > 0, f"num_subblocks_r_dim (r//sr = {r}//{sr}) must be > 0"
        assert k >= sk and k // sk > 0, f"num_subblocks_k_dim (k//sk = {k}//{sk}) must be > 0"
        assert c >= sc and c // sc > 0, f"num_subblocks_c_dim (c//sc = {c}//{sc}) must be > 0"
        return cls(
            test_type           = TestType.MATMUL,
            dm_test_name        = "2cluster-1d_matmul",
            num_cores_r_dim     = ncr,
            num_cores_c_dim     = ncc,
            num_clusters_r_dim  = NCR,
            num_clusters_c_dim  = NCC,
            in0_config          = MatrixTestConfig(
                                    rows                = 32*r,
                                    cols                = 32*k,
                                    dtype               = bfloat16,
                                    matrix_distribution = MatrixDistribution.UNIFORM.value,
                                    is_sharded          = True,
                                    sharding_type       = ShardingType.WIDTH,
                                    width_shards        = NCC,
                                    num_subblocks_r_dim = r//sr,
                                    num_subblocks_c_dim = k//sk,
                                    subblock_r_dim      = sr,
                                    subblock_c_dim      = sk,
                            ),
            in1_config          = MatrixTestConfig(
                                    rows                = 32*k,
                                    cols                = 32*c,
                                    dtype               = bfloat16,
                                    matrix_distribution = MatrixDistribution.UNIFORM.value,
                                    is_sharded          = False,
                                    chunk_size          = 1024,
                                    num_subblocks_r_dim = k//sk,
                                    num_subblocks_c_dim = c//sc,
                                    subblock_r_dim      = sk,
                                    subblock_c_dim      = sc,
                            ),
            output_format       = bfloat16,
        )

    @classmethod
    def get_test_scenario(cls, scenario_name: str) -> 'TestConfig':
        """Factory method to create TestConfig instances for predefined scenarios.
        
        Args:
            scenario_name: Name of the test scenario (e.g., "TEST0", "TEST2", etc.)
            
        Returns:
            TestConfig instance configured for the specified scenario
            
        Raises:
            ValueError: If scenario_name is not found in predefined configurations
        """
        test_configs = {
            ## int8 -> int8_2x => int32 tests
            "TEST0": TestConfig(
                test_type           = TestType.MATMUL,
                dm_test_name        = "1d_matmul_single_neo_4tensix",
                num_cores_r_dim     = 1,
                num_cores_c_dim     = 1,
                in0_config          = MatrixTestConfig(
                                        rows                = 32,
                                        cols                = 32,
                                        dtype               = np.int8,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 127},
                                        is_sharded          = True,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 1,
                                        num_subblocks_c_dim = 1,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 1,
                                    ),
                in1_config          = MatrixTestConfig(
                                        rows                = 32,
                                        cols                = 32,
                                        dtype               = np.int8,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 127},
                                        is_sharded          = False,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 1,
                                        num_subblocks_c_dim = 1,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 1,
                                    ),
                upk_fmt_in          = np.int8,
                input_format        = np.uint64,
                output_format       = np.int32,
            ),
            "TEST1": cls(
                test_type           = TestType.MATMUL,
                dm_test_name        = "1d_matmul_single_neo_4tensix",
                num_cores_r_dim     = 4,
                num_cores_c_dim     = 1,
                in0_config          = MatrixTestConfig(
                                        rows                = 128,
                                        cols                = 128,
                                        dtype               = np.int8,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 127},
                                        is_sharded          = True,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 4,
                                        num_subblocks_c_dim = 4,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 1,
                                    ),
                in1_config          = MatrixTestConfig(
                                        rows                = 128,
                                        cols                = 256,
                                        dtype               = np.int8,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 127},
                                        is_sharded          = False,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 4,
                                        num_subblocks_c_dim = 2,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 4,
                                    ),
                upk_fmt_in          = np.int8,
                input_format        = np.uint64,
                output_format       = np.int32,
            ),
            ## bfloat16 -> bfloat16 => float32 tests
            "TEST2": TestConfig(
                test_type           = TestType.MATMUL,
                dm_test_name        = "1d_matmul_single_neo_4tensix",
                num_cores_r_dim     = 1,
                num_cores_c_dim     = 1,
                in0_config          = MatrixTestConfig(
                                        rows                = 32,
                                        cols                = 32,
                                        dtype               = bfloat16,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 1},
                                        is_sharded          = True,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 1,
                                        num_subblocks_c_dim = 1,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 1,
                                    ),
                in1_config          = MatrixTestConfig(
                                        rows                = 32,
                                        cols                = 32,
                                        dtype               = bfloat16,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 1},
                                        is_sharded          = False,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 1,
                                        num_subblocks_c_dim = 1,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 1,
                                    ),
                upk_fmt_in          = bfloat16,
                input_format        = bfloat16,
                output_format       = np.float32,
            ),
            "TEST3": cls(
                test_type           = TestType.MATMUL,
                dm_test_name        = "1d_matmul_single_neo_4tensix",
                num_cores_r_dim     = 4,
                num_cores_c_dim     = 1,
                in0_config          = MatrixTestConfig(
                                        rows                = 128,
                                        cols                = 128,
                                        dtype               = bfloat16,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 1},
                                        is_sharded          = True,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 4,
                                        num_subblocks_c_dim = 4,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 1,
                                    ),
                in1_config          = MatrixTestConfig(
                                        rows                = 128,
                                        cols                = 256,
                                        dtype               = bfloat16,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 1},
                                        is_sharded          = False,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 4,
                                        num_subblocks_c_dim = 2,
                                        subblock_r_dim      = 1,
                                        subblock_c_dim      = 4,
                                    ),
                upk_fmt_in          = bfloat16,
                input_format        = bfloat16,
                output_format       = np.float32,
            ),
            ## power vector
            "TEST4": cls(
                test_type           = TestType.MATMUL,
                dm_test_name        = "1d_matmul_single_neo_4tensix",
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
                                        cols                = 512,
                                        dtype               = np.int8,
                                        matrix_distribution = MatrixDistribution.NORMAL.value,
                                        matrix_params       = {'loc': 0, 'scale': 127},
                                        is_sharded          = False,
                                        sharding_type       = ShardingType.WIDTH,
                                        width_shards        = 1,
                                        num_subblocks_r_dim = 4,
                                        num_subblocks_c_dim = 4,
                                        subblock_r_dim      = 4,
                                        subblock_c_dim      = 4,
                                    ),
                upk_fmt_in          = np.int8,
                input_format        = np.uint64,
                output_format       = np.int32,
            ),
        }

        for sk in [1, 2]:
            for sr in [1, 2]:
                for sc in [1, 2, 4]:
                    test_configs[f"TEST_SWEEP_{sk}{sr}{sc}"] = cls.test_config_from_params(NCR=1, NCC=2, ncr=4, ncc=1, sk=sk, sr=sr, sc=sc, k=2, r=4, c=4)
        
        if scenario_name not in test_configs:
            available = list(test_configs.keys())
            raise ValueError(f"Unknown test scenario '{scenario_name}'. Available scenarios: {available}")
            
        # Get the base configuration
        test_config = test_configs[scenario_name]
        
        # Apply environment variable overrides
        test_config.test_name = scenario_name
        test_config.dm_only = os.getenv("DM_ONLY", "0") == "1"
        test_config.emulation = os.getenv("EMULATION", "0") == "1"
        test_config.l1_shard_addr = os.getenv("L1_DATA_START", 0x52000)
        test_config.perf_l1_hash = os.getenv("PERF_L1_HASH", "0") == "1"
        
        return test_config

    def override_coordinates(self, worker_core_coord: Tuple[int, int], dram_coords: List[Tuple[int, int]]) -> None:
        """
        Override the coordinate settings for DataMovementConfig.
        
        Args:
            worker_core_coord: Single (x, y) tuple for the worker core coordinate
            dram_coords: List of (x, y) tuples for DRAM bank coordinates
        """
        self.worker_core_coord = worker_core_coord
        self.dram_coords = dram_coords

    @classmethod
    def get_available_scenarios(cls) -> List[str]:
        """Return list of available test scenario names."""
        return ["TEST0", "TEST1", "TEST2", "TEST3", "TEST4", "TEST5", "TEST6", "TEST7", "TEST8", "TEST_DM_ONLY"]

async def program_l1_hash(tb, test_config):
    if test_config.perf_l1_hash:
        for tx, ty in tb.config.get_coordinates_for_tile_type(TileType.TENSIX):
            await tb.program_performant_l1_hash(tx, ty)

async def compile_dm_kernel(test_config):

    dm_config = DataMovementConfig(
        test_name           = test_config.test_name,
        dm_test_name        = test_config.dm_test_name,
        dataformat          = test_config.upk_fmt_in,
        subblock_r_dim      = test_config.subblock_r_dim,
        subblock_c_dim      = test_config.subblock_c_dim,
        subblock_k_dim      = test_config.subblock_k_dim,
        num_subblocks_r_dim = test_config.num_subblocks_r_dim,
        num_subblocks_c_dim = test_config.num_subblocks_c_dim,
        num_subblocks_k_dim = test_config.num_subblocks_k_dim,
        num_cores_r_dim     = test_config.num_cores_r_dim,
        l1_input_address    = test_config.in0_l1_address,
        dram_input_address  = 0x0,
        t6_output_address   = test_config.out_l1_address,
        cb0_write_addr      = test_config.in0_l1_address,
        cb1_write_addr      = test_config.in1_l1_address,
        cb8_write_addr      = test_config.out_l1_address,
        worker_core_coord   = test_config.worker_core_coord,
        dram_bank_coords    = test_config.dram_coords,
    )

    dm_project_path = os.getenv("DM_PROJECT_PATH")
    if dm_project_path is None:
        test_file_dir = os.path.dirname(os.path.abspath(__file__))
        dm_project_path = os.path.join(test_file_dir, "..", "..", "firmware", "datamover_cmake")

    dm_kernel_path = await compile_dm_binary(dm_config, dm_project_path)#f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/1d_matmul_single_neo_4tensix/out/1d_matmul_single_neo_4tensix.bin"

    try:
        dm_kernel = load_binary_data(
            bin_path = dm_kernel_path,
            hex_env  = "DM_HEX",
            bin_env  = "DM_BIN",
        )
    except Exception as e:
        dm_kernel = None

    return dm_kernel

async def compile_tensix_kernels(test_config):

    if test_config.dm_only:
        return None

    tensix_project_path = os.getenv("TENSIX_PROJECT_PATH")
    if tensix_project_path is None:
        test_file_dir = os.path.dirname(os.path.abspath(__file__))
        # tensix_project_path = os.path.join(test_file_dir, "..", "..", "tb", "tensix_tests")
        tensix_project_path = os.path.join(test_file_dir, "..", "..", "firmware", "tensix_tests")

    tensix_config = TensixConfig(
        test_name           = test_config.test_name,
        test_type           = test_config.test_type.name,
        rows                = test_config.rows,
        cols                = test_config.cols,
        upk_fmt_in          = test_config.upk_fmt_in,
        input_format        = test_config.input_format,
        output_format       = test_config.output_format,
        cb0_l1_input_addr   = test_config.in0_l1_address,
        cb8_l1_output_addr  = test_config.out_l1_address,
        cb1_l1_input_addr   = test_config.in1_l1_address,
        subblock_r_dim      = test_config.subblock_r_dim,
        subblock_c_dim      = test_config.subblock_c_dim,
        subblock_k_dim      = test_config.subblock_k_dim,
        num_subblocks_r_dim = test_config.num_subblocks_r_dim,
        num_subblocks_c_dim = test_config.num_subblocks_c_dim,
        num_subblocks_k_dim = test_config.num_subblocks_k_dim,
        in0_offset_ids      = test_config.in0_offset_ids,
        in1_offset_ids      = test_config.in1_offset_ids,
        out_offset_ids      = test_config.out_offset_ids,
        num_cores_r_dim     = test_config.num_cores_r_dim,
        num_cores_c_dim     = test_config.num_cores_c_dim,
        num_clusters_r_dim  = test_config.num_clusters_r_dim,
        num_clusters_c_dim  = test_config.num_clusters_c_dim,
    )
    print(f"TENSIX CONFIG: tensix_config.out_l1_address = {tensix_config.cb8_l1_output_addr}")

    tensix_cores = [i for i in range(test_config.num_cores)]
    trisc_ids = [i for i, active in enumerate(test_config.active_triscs) if active]

    tensix_kernel_path = await compile_tensix_binary(
        tensix_config,
        tensix_project_path,
        trisc_ids,
        tensix_cores,
    )

    tensix_kernels = get_tensix_kernels_with_addresses(tensix_kernel_path)

    return tensix_kernels

async def load_kernels(tb, test_config):

    tensix_coords = [(0,0)]#tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    start_x, start_y, size_x, size_y = find_largest_rectangle(tensix_coords)

    assert len(tensix_coords) == test_config.num_clusters

    dm_kernel_addr = os.getenv("DM_ADDR", 0x0)
    dm_kernel = await compile_dm_kernel(test_config)

    print ("SALJI DM KERNEL")

    if dm_kernel is not None:
        await tb.noc_multicast(
            tb.default_master,
            start_x,
            start_y,
            size_x,
            size_y,
            dm_kernel_addr,
            dm_kernel,
        )

    print ("SALJI TENSIX KERNELS")

    tensix_kernels = await compile_tensix_kernels(test_config)

    if tensix_kernels is not None:
        print("SALJI TENSIX BINARY")
        for addr, (trisc_bin, file_path) in tensix_kernels.items():
            tb.noc_multicast_nonblocking(
                tb.default_master,
                start_x,
                start_y,
                size_x,
                size_y,
                addr,
                trisc_bin,
            )

def generate_matrices(test_config):

    generator = MatrixGenerator(
        dtype = test_config.in0_config.dtype,
        seed  = test_config.in0_config.seed,
    )

    if test_config.test_type == TestType.MATMUL:
        # assert test_config.in0_config.is_sharded     # TODO: is this true?
        assert not test_config.in1_config.is_sharded # TODO: is this true?
        matrices = generator.prepare_matmul_matrices_for_test(
            test_config.in0_config,
            test_config.in1_config,
            num_cores = test_config.num_clusters,
        )
    elif test_config.test_type == TestType.DATACOPY:
        assert test_config.in0_config.is_sharded # TODO: is this true?
        matrices = generator.prepare_unary_matrix_for_test(
            test_config.in0_config,
            num_cores = test_config.num_clusters,
        )

    return matrices

def load_interleaved_chunks_to_dram(tb, chunks):
    dram_coords = [(0,1)]#tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)
    num_dram = 1#tb.config.num_dram
    dram_addrs = [0 for _ in range(num_dram)]
    for i, chunk_bytes in enumerate(chunks):
        dram_idx = i % num_dram
        x, y = dram_coords[dram_idx]
        tb.log.info(f"Loading interleaved chunk {i} to DRAM at x={x}, y={y}")
        tb.noc_write_nonblocking(tb.default_master, x, y, dram_addrs[dram_idx], chunk_bytes)
        dram_addrs[dram_idx] += len(chunk_bytes)

def load_matrices_for_matmul(tb, test_config, matrices):

    tensix_coords = [(0,0)]#tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    sharding_type = test_config.in0_config.sharding_type
    
    # Organize coordinates based on sharding type
    if sharding_type == ShardingType.WIDTH:
        # Width sharding: iterate over x dimension (columns), keep y fixed
        # Group coordinates by y, then sort by x within each group
        coords_by_y = {}
        for x, y in tensix_coords:
            if y not in coords_by_y:
                coords_by_y[y] = []
            coords_by_y[y].append((x, y))
        
        # Sort by y first, then by x within each y
        sorted_coords = []
        for y in sorted(coords_by_y.keys()):
            sorted_coords.extend(sorted(coords_by_y[y], key=lambda coord: coord[0]))
        
        # For width sharding, we want to iterate x within the same y
        # Take only the first row of coordinates (same y value)
        if sorted_coords:
            first_y = sorted_coords[0][1]
            width_coords = [coord for coord in sorted_coords if coord[1] == first_y]
            width_coords = sorted(width_coords, key=lambda coord: coord[0])
            
            # Load shards to width coordinates
            for i, shard_bytes in enumerate(matrices['shards']):
                if i >= len(width_coords):
                    tb.log.info(f"Warning: Not enough Tensix cores for shard {i} in width sharding")
                    break
                x, y = width_coords[i]
                tb.log.info(f"Loading shard {i} to Tensix at x={x}, y={y} (WIDTH sharding)")
                tb.noc_write_nonblocking(
                    tb.default_master,
                    x,
                    y,
                    test_config.l1_shard_addr,
                    shard_bytes,
                )
    
    elif sharding_type == ShardingType.HEIGHT:
        # Height sharding: iterate over y dimension (rows), keep x fixed
        # Group coordinates by x, then sort by y within each group
        coords_by_x = {}
        for x, y in tensix_coords:
            if x not in coords_by_x:
                coords_by_x[x] = []
            coords_by_x[x].append((x, y))
        
        # For height sharding, we want to iterate y within the same x
        # Take only the first column of coordinates (same x value)
        if coords_by_x:
            first_x = min(coords_by_x.keys())
            height_coords = sorted(coords_by_x[first_x], key=lambda coord: coord[1])
            
            # Load shards to height coordinates
            for i, shard_bytes in enumerate(matrices['shards']):
                if i >= len(height_coords):
                    tb.log.info(f"Warning: Not enough Tensix cores for shard {i} in height sharding")
                    break
                x, y = height_coords[i]
                tb.log.info(f"Loading shard {i} to Tensix at x={x}, y={y} (HEIGHT sharding)")
                tb.noc_write_nonblocking(
                    tb.default_master,
                    x,
                    y,
                    test_config.l1_shard_addr,
                    shard_bytes,
                )
    
    elif sharding_type == ShardingType.BLOCK:
        # Block sharding: iterate in row-major order (y outer loop, x inner loop)
        # This matches the block sharding algorithm which does:
        # for block_row in range(...):
        #     for block_col in range(...):
        
        # Sort coordinates in row-major order (by y first, then by x)
        block_coords = sorted(tensix_coords, key=lambda coord: (coord[1], coord[0]))
        
        # Load shards to coordinates in row-major order
        for i, shard_bytes in enumerate(matrices['shards']):
            if i >= len(block_coords):
                tb.log.info(f"Warning: Not enough Tensix cores for shard {i} in block sharding")
                break
            x, y = block_coords[i]
            tb.log.info(f"Loading shard {i} to Tensix at x={x}, y={y} (BLOCK sharding)")
            tb.noc_write_nonblocking(
                tb.default_master,
                x,
                y,
                test_config.l1_shard_addr,
                shard_bytes,
            )
    
    else:
        raise ValueError(f"Unsupported sharding type: {sharding_type}")

    # Ping-pong interleaved chunks into DRAM
    load_interleaved_chunks_to_dram(tb, matrices['chunks'])

def load_matrices_for_datacopy(tb, test_config, matrices):

    mem_blocks = matrices['mem_blocks']
    tb.log.info(f"Generated {len(mem_blocks)} mem_blocks ")

    if not test_config.in0_config.is_sharded:
        # Ping-pong interleaved chunks into DRAM
        load_interleaved_chunks_to_dram(tb, mem_blocks)
        return

    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    sharding_type = test_config.in0_config.sharding_type

    shard_per_cluster = len(mem_blocks) == len(tensix_coords)
    if not shard_per_cluster:
        tb.log.info(f"Number of shards {len(mem_blocks)} does not match number of Neo clusters {len(tensix_coords)}. Loading same shard to every cluster.")
        # If not one shard per cluster, just load to all cores in arbitrary order
        for i, (x, y) in enumerate(tensix_coords):
            idx = 0  # Use the same shard for all
            tb.log.info(f"Loading shard {idx} to Tensix at x={x}, y={y}")
            tb.noc_write_nonblocking(
                tb.default_master,
                x,
                y,
                test_config.l1_shard_addr,
                mem_blocks[idx],
            )
        return
    
    # Organize coordinates based on sharding type (same logic as matmul)
    if sharding_type == ShardingType.WIDTH:
        # Width sharding: iterate over x dimension (columns), keep y fixed
        coords_by_y = {}
        for x, y in tensix_coords:
            if y not in coords_by_y:
                coords_by_y[y] = []
            coords_by_y[y].append((x, y))
        
        # Take only the first row of coordinates (same y value)
        sorted_coords = []
        for y in sorted(coords_by_y.keys()):
            sorted_coords.extend(sorted(coords_by_y[y], key=lambda coord: coord[0]))
        
        if sorted_coords:
            first_y = sorted_coords[0][1]
            width_coords = [coord for coord in sorted_coords if coord[1] == first_y]
            width_coords = sorted(width_coords, key=lambda coord: coord[0])
            
            for i, mem_block in enumerate(mem_blocks):
                if i >= len(width_coords):
                    tb.log.info(f"Warning: Not enough Tensix cores for mem_block {i} in width sharding")
                    break
                x, y = width_coords[i]
                tb.log.info(f"Loading mem_block {i} to Tensix at x={x}, y={y} (WIDTH sharding)")
                tb.noc_write_nonblocking(
                    tb.default_master,
                    x,
                    y,
                    test_config.l1_shard_addr,
                    mem_block,
                )
    
    elif sharding_type == ShardingType.HEIGHT:
        # Height sharding: iterate over y dimension (rows), keep x fixed
        coords_by_x = {}
        for x, y in tensix_coords:
            if x not in coords_by_x:
                coords_by_x[x] = []
            coords_by_x[x].append((x, y))
        
        # Take only the first column of coordinates (same x value)
        if coords_by_x:
            first_x = min(coords_by_x.keys())
            height_coords = sorted(coords_by_x[first_x], key=lambda coord: coord[1])
            
            for i, mem_block in enumerate(mem_blocks):
                if i >= len(height_coords):
                    tb.log.info(f"Warning: Not enough Tensix cores for mem_block {i} in height sharding")
                    break
                x, y = height_coords[i]
                tb.log.info(f"Loading mem_block {i} to Tensix at x={x}, y={y} (HEIGHT sharding)")
                tb.noc_write_nonblocking(
                    tb.default_master,
                    x,
                    y,
                    test_config.l1_shard_addr,
                    mem_block,
                )
    
    elif sharding_type == ShardingType.BLOCK:
        # Block sharding: iterate in row-major order (y outer loop, x inner loop)
        block_coords = sorted(tensix_coords, key=lambda coord: (coord[1], coord[0]))
        
        for i, mem_block in enumerate(mem_blocks):
            if i >= len(block_coords):
                tb.log.info(f"Warning: Not enough Tensix cores for mem_block {i} in block sharding")
                break
            x, y = block_coords[i]
            tb.log.info(f"Loading mem_block {i} to Tensix at x={x}, y={y} (BLOCK sharding)")
            tb.noc_write_nonblocking(
                tb.default_master,
                x,
                y,
                test_config.l1_shard_addr,
                mem_block,
            )
    
    else:
        raise ValueError(f"Unsupported sharding type: {sharding_type}")

async def load_matrices(tb, test_config, matrices):
    if test_config.test_type == TestType.MATMUL:
        load_matrices_for_matmul(tb, test_config, matrices)
    elif test_config.test_type == TestType.DATACOPY:
        load_matrices_for_datacopy(tb, test_config, matrices)
    # Wait for all the data to be moved into DRAM/Tensix
    await tb.noc_wait_writes(tb.default_master)

async def release_resets(tb, test_config, tensix_coords=None):

    reset_value = 0
    for active in reversed(test_config.active_triscs):
        reset_value <<= 1
        reset_value |= int(active)
    reset_value = ~reset_value & 0xf

    tb.log.info(f"[END_TO_END_SCENARIO(release_resets)] : reset_value:{reset_value} num_cores:{test_config.num_cores}..")
    await tb.release_dm_core_reset()

    if not test_config.dm_only:
        active_cores = [i for i in range(test_config.num_cores)]
        # Use provided tensix_coords or default to (0,0)
        coords = tensix_coords if tensix_coords is not None else [(0, 0)]
        await tb.set_risc_soft_reset(reset_value, active_cores, tensix_coords=coords)

def get_waiters(tb, test_config):

    # TODO: simplify this
    if test_config.test_name == "TEST_DM_ONLY":
        tensix_postcodes_scratch = [1, 3, 5]

    n = test_config.num_cores_r_dim * test_config.num_cores_c_dim
    tensix_postcodes_scratch = [i for i in range(1, (3*n*2), 2)]

    # Wait for scratch 0 to have non-zero value
    dm_postcodes_scratch = list(range(0, 16, 2))

    if test_config.dm_only:
        postcodes_scratch = dm_postcodes_scratch
    else:
        postcodes_scratch = list(sorted(set(dm_postcodes_scratch + tensix_postcodes_scratch)))

    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    active_tensix_coords = tensix_coords if test_config.num_clusters > 1 else [tensix_coords[0]]

    waiters = []
    for x, y in active_tensix_coords:
        task = tb.monitor_dm_t6_scratch(x, y, indicies=postcodes_scratch)
        waiter = cocotb.start_soon(task)
        waiters.append(waiter)
    return waiters

async def wait_for_test_to_end(tb, test_config, timeout=500_000):

    waiters = get_waiters(tb, test_config)

    if test_config.emulation:
        await tb.wait_all_tasks(waiters)
        await tb.wait_ns(timeout)
    else:
        while waiters:
            from cocotb.triggers import with_timeout
            await with_timeout(waiters.pop(0), timeout, 'ns')

async def generate_golden_tensor_matmul(tb, test_config, output_checker, matrices, tensix_coords=None):

    for i in range(test_config.num_clusters):

        x, y = tensix_coords[i]
        out_size = test_config.out_size // test_config.num_clusters
        await output_checker.read_output_tensor(tb, x, y, out_size)

        in0_sub_matrix = matrices['matrix_a']
        in1_sub_matrix = matrices['matrix_b']

        if test_config.num_clusters_r_dim > 1:
            matrix_a_vsplit = np.vsplit(matrices['matrix_a'], test_config.num_clusters_r_dim)
            in0_sub_matrix = matrix_a_vsplit[i // test_config.num_clusters_r_dim]
        if test_config.num_clusters_c_dim > 1:
            matrix_b_hsplit = np.hsplit(matrices['matrix_b'], test_config.num_clusters_c_dim)
            in1_sub_matrix = matrix_b_hsplit[i % test_config.num_clusters_c_dim]

        output_checker.generate_golden_tensor(in0_sub_matrix, in1_sub_matrix)

async def generate_golden_tensor_datacopy(tb, test_config, output_checker, matrices):
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    for x, y in tensix_coords:
        await output_checker.read_output_tensor(tb, x, y, test_config.out_size)
    output_checker.generate_golden_tensor(matrices['matrix_a'])

async def check_output(tb, test_config, matrices, tensix_coords=None):

    if test_config.dm_only:
        return

    output_checker = MatrixOutputChecker(
        np.dtype(test_config.output_format),
        test_config.test_type.name,
        test_config.out_l1_address,
    )

    if test_config.test_type == TestType.MATMUL:
        await generate_golden_tensor_matmul(tb, test_config, output_checker, matrices, tensix_coords)
    elif test_config.test_type == TestType.DATACOPY:
        await generate_golden_tensor_datacopy(tb, test_config, output_checker, matrices)

    output_checker.check_output_tensor()

async def print_mmio_data(tb, test_config):
    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    active_tensix_coords = tensix_coords if test_config.num_clusters > 1 else [tensix_coords[0]]
    for x, y in active_tensix_coords:
        output_data = await tb.noc_read(tb.default_master, x=x, y=y, addr=0x300000, length=256*4)
        if hasattr(output_data, 'data'):         data = bytearray(output_data.data)
        elif isinstance(output_data, bytearray): data = output_data
        elif isinstance(output_data, bytes):     data = bytearray(output_data)
        else:                                    data = bytearray(output_data)
        s = f"MMIO data for x={x} y={y}:"
        for i, byte in enumerate(data):
            if i % 16 == 0:
                s += "\n"
            s += f"{byte:02x} "
        s += "\n"
        tb.log.info(s)

async def test_end_to_end_scenario(dut):

    test_scenario = os.getenv("TEST_SCENARIO")

    # Use the new classmethod factory (includes environment variable configuration)
    test_config = TestConfig.get_test_scenario(test_scenario)

    assert test_config.test_type.name == os.getenv("TEST_TYPE")

    tb = demoTB(dut)

    tb.log.info("init_and_reset()")
    await tb.init_and_reset()

    tb.log.info("program_l1_hash()")
    await program_l1_hash(tb, test_config)

    tb.log.info("load_kernels()")
    await load_kernels(tb, test_config)

    tb.log.info("generate_matrices()")
    matrices = generate_matrices(test_config)
    # print(f"[END_TO_END_SCENARIO(generate_matrices)][matrix_a] : matrices:{matrices['matrix_a_tilized']}")
    # print(f"[END_TO_END_SCENARIO(generate_matrices)][matrix_b] : matrices:{matrices['matrix_b_tilized']}")

    tb.log.info("load_matrices()")
    await load_matrices(tb, test_config, matrices)

    tb.log.info("release_resets()")
    await release_resets(tb, test_config)

    tb.log.info("wait_for_test_to_end()")
    await wait_for_test_to_end(tb, test_config, 40000)

# ##########
#     dram_checker_bank0 = MatrixOutputChecker(bfloat16, test_config.test_type.name, 0x0)
#     await dram_checker_bank0.read_output_tensor(tb, 0, 0, 32*32*2*4)
#     dram_checker_bank0.print_tiles(dram_checker_bank0.output_tensor, True, "dram_checker_bank0")
# ##########
#     dram_checker_bank1 = MatrixOutputChecker(bfloat16, test_config.test_type.name, 0x0)
#     await dram_checker_bank1.read_output_tensor(tb, 1, 0, 32*32*2*4)
#     dram_checker_bank1.print_tiles(dram_checker_bank1.output_tensor, True, "dram_checker_bank1")
# #########
    # tb.log.info("print_mmio_data()")
    # await print_mmio_data(tb, test_config)

    tb.log.info("check_output()")
    await check_output(tb, test_config, matrices, tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX))
