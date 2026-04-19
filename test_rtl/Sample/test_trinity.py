import sys
import os
import functools
# appending a path
# sys.path.append('/proj_soc/user_dev/ldobric/bos_trinity_b0/staging/tb')
sys.path.insert(0, f"{os.environ['TENSIX_ROOT']}/tb")

print(f"sys.path: {sys.path}")


# import logging
try:
    import tests
    print("Successfully imported 'tests' module from:")
    print(tests.__file__)
except ImportError as e:
    print(f"Failed to import 'tests': {e}")

#----------------------------
# BIU Interrupt Checking Control
#----------------------------
# Global flag to disable BIU checking for specific tests
# Set to True in test wrapper to disable checking for that test
_disable_biu_checking_for_current_test = False

def set_biu_checking_disabled(disabled=True):
    """
    Control BIU checking for the current test.

    Call this at the start of a test wrapper to disable BIU checking,
    even when BIU_CHECKING=1 is set globally.

    Example:
        @cocotb.test(skip=False)
        async def my_problematic_test(dut):
            set_biu_checking_disabled(True)  # Disable for this test
            await my_test_impl(dut)
    """
    global _disable_biu_checking_for_current_test
    _disable_biu_checking_for_current_test = disabled

def is_biu_checking_disabled():
    """Check if BIU checking is disabled for current test."""
    global _disable_biu_checking_for_current_test
    return _disable_biu_checking_for_current_test

from tests.utils.coco_tensix_api import *
from tests.sanity_noc2axi_unicast_all import *
from tests.sanity_noc2axi_multicast import *
from tests.addr_pinger import *
from tests.addr_pinger_perf import *
from tests.dm_power_virus import *
from tests.sanity_axi_random import *
from tests.att_translation_config import *
from tests.att_routing_config import *
from tests.strided_multicast import *
from tests.strided_multicast_discovery import *
from tests.sanity_group_security import *
from tests.sanity_security_fence import *
from tests.security_fence_noc2axi import *
from tests.trinity_binary_loader import *
from tests.sanity_edc import *
from tests.trinity_performance import *
from tests.sanity_edc_harvesting import *
from tests.simple_edc_harvesting import *
from tests.sanity_edc_col_harvesting import *
from tests.simple_edc_col_harvesting import *
from tests.sanity_edc_selftest import *
from tests.sanity_fds import *
from tests.end_to_end_scenario import *
from tests.sanity_l1_backdoor import *
from tests.dm_traffic_with_local_matmul import *

#----------------------------
# BIU Check Decorator
#----------------------------
def with_biu_check(test_func):
    """
    Decorator to add automatic BIU checking to test functions.

    This decorator ensures BIU monitors are checked at test end for both
    TTem and Makefile TESTCASE invocations, without modifying test implementations.

    Usage:
        @cocotb.test(skip=False)
        @with_biu_check
        async def my_test(dut):
            await my_test_implementation(dut)

    The decorator preserves the function name so tests can still be called via:
        make TESTCASE=my_test
        ttem trinity_vcs.yaml -t my_test

    Benefits:
    - No code duplication across tests
    - BIU checking guaranteed via try/finally
    - Works even if test raises an exception
    - Tests remain unchanged
    """
    @functools.wraps(test_func)  # Preserve original function name for TESTCASE lookup
    async def wrapper(dut):
        global _disable_biu_checking_for_current_test
        try:
            await test_func(dut)
        finally:
            # Check all registered TB instances (unless disabled)
            if not is_biu_checking_disabled():
                check_all_biu_monitors()
            # Reset the flag for next test
            _disable_biu_checking_for_current_test = False
    return wrapper

# ----------------------------
# Test Functions
# ----------------------------
@cocotb.test(skip=False)
@with_biu_check
async def sanity_noc2axi_unicast_all_test(dut):
    await sanity_noc2axi_unicast_all(dut)

@cocotb.test(skip=False)
@with_biu_check
async def sanity_noc2axi_multicast_test(dut):
    await sanity_noc2axi_multicast(dut)

@cocotb.test(skip=False)
@with_biu_check
async def sanity_axi_random_test(dut):
    await sanity_axi_random(dut)

@cocotb.test(skip=False)
@with_biu_check
async def strided_multicast_test(dut):
    await strided_multicast(dut)

@cocotb.test(skip=False)
@with_biu_check
async def att_translation_config_test(dut):
    await att_translation_config(dut)

@cocotb.test(skip=False)
@with_biu_check
async def att_routing_config_test(dut):
    await att_routing_config(dut)

@cocotb.test(skip=False)
@with_biu_check
async def addr_pinger_test(dut):
    # To disable BIU checking for this test (even when BIU_CHECKING=1):
    #   set_biu_checking_disabled(True)
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/addr_pinger/out/addr_pinger.bin"
    await addr_pinger(dut, bin_path, 8)

@cocotb.test(skip=False)
@with_biu_check
async def dm_power_virus_test(dut):
    """Power virus: neighbors hit center (1,2) while center sends to all neighbors."""
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/addr_pinger/out/addr_pinger.bin"
    await dm_power_virus(dut, bin_path, transfer_size=8*1024, total_size=8*1024)

@cocotb.test(skip=True)
@with_biu_check
async def addr_pinger_perf_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/addr_pinger/out/addr_pinger.bin"
    # Get command line arguments with defaults
    overlay_cores= int(cocotb.plusargs.get("OVERLAY_CORES", "8"))
    transfer_size = int(cocotb.plusargs.get("TRANSFER_SIZE", "1024"))
    total_size = int(cocotb.plusargs.get("TOTAL_SIZE", str(128*1024)))
    axi_read_latency = int(cocotb.plusargs.get("AXI_READ_LATENCY", "0"))
    axi_write_latency = int(cocotb.plusargs.get("AXI_WRITE_LATENCY", "0"))

    # Debug prints
    print(f"DEBUG: overlay_cores={overlay_cores}")
    print(f"DEBUG: transfer_size={transfer_size}")
    print(f"DEBUG: total_size={total_size}")
    print(f"DEBUG: axi_read_latency={axi_read_latency}")
    print(f"DEBUG: axi_write_latency={axi_write_latency}")
    print(f"DEBUG: All plusargs: {dict(cocotb.plusargs)}")

    await addr_pinger_perf(dut, bin_path,
                          cores_per_host=overlay_cores,
                          transfer_size=transfer_size,
                          total_size=total_size,
                          axi_read_data_latency=axi_read_latency,
                          axi_write_response_latency=axi_write_latency)

@cocotb.test(skip=True)
@with_biu_check
async def trinity_performance_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/trinity_performance/out/trinity_performance.bin"
    # Get command line arguments with defaults
    overlay_cores = int(cocotb.plusargs.get("OVERLAY_CORES", "8"))
    num_of_cmd_bufers = int(cocotb.plusargs.get("NUMBER_OF_CMD_BUFFERS", "3"))
    transfer_size = int(cocotb.plusargs.get("TRANSFER_SIZE", "1024"))
    num_of_transfers = int(cocotb.plusargs.get("NUMBER_OF_TRANSFERS", "20"))
    total_size = overlay_cores * num_of_cmd_bufers * transfer_size * num_of_transfers
    axi_read_latency = int(cocotb.plusargs.get("AXI_READ_LATENCY", "0"))
    axi_write_latency = int(cocotb.plusargs.get("AXI_WRITE_LATENCY", "0"))
    multi_channel = int(cocotb.plusargs.get("MULTI_CHANNEL", "0"))
    target_memory_start_addr = int(cocotb.plusargs.get("TARGET_MEMORY_START_ADDR", "0"))

    # Debug prints
    print(f"DEBUG: overlay_cores={overlay_cores}")
    print(f"DEBUG: num_of_cmd_bufers={num_of_cmd_bufers}")
    print(f"DEBUG: transfer_size={transfer_size}")
    print(f"DEBUG: num_of_transfers={num_of_transfers}")
    print(f"DEBUG: total_size={total_size}")
    print(f"DEBUG: axi_read_latency={axi_read_latency}")
    print(f"DEBUG: axi_write_latency={axi_write_latency}")
    print(f"DEBUG: multi_channel={multi_channel}")
    print(f"DEBUG: target_memory_start_addr={target_memory_start_addr}")
    print(f"DEBUG: All plusargs: {dict(cocotb.plusargs)}")

    await trinity_performance(dut=dut,
                              bin_path=bin_path,
                              cores_per_host=overlay_cores,
                              number_of_cmd_buffers=num_of_cmd_bufers,
                              transfer_size=transfer_size,
                              number_of_transfers=num_of_transfers,
                              total_size=total_size,
                              target_memory_start_addr=target_memory_start_addr,
                              axi_read_data_latency=axi_read_latency,
                              axi_write_response_latency=axi_write_latency,
                              multi_channel=multi_channel)

@cocotb.test(skip=False)
@with_biu_check
async def dm_cpu_muldiv_sanity_test(dut):
     tensix_neos_phys = ((0,0), (1,2), (3,2)) # Testing tensixNeo at (1,1), (1,2), (3,2)
     await trinity_binary_loader(dut, test="dm_cpu_muldiv_sanity_test", tensix_neos_phys=tensix_neos_phys)

@cocotb.test(skip=False)
@with_biu_check
async def dm_noc_sanity_test(dut):
    tensix_neos_phys = (((1,1),)) # Needs to be (1,1)
    await trinity_binary_loader(dut, test="dm_noc_sanity_test", tensix_neos_phys=tensix_neos_phys)

@cocotb.test(skip=False)
@with_biu_check
async def dm_fds_test(dut):
    # Full 4x3 Tensix grid (x=0-3, y=0-2) plus 2 Dispatch tiles (y=3)
    # Tensix: 12 tiles, Dispatch: 2 tiles
    tensix_neos_phys = (
        # Tensix tiles (y=0,1,2)
        (0,0), (0,1), (0,2),
        (1,0), (1,1), (1,2),
        (2,0), (2,1), (2,2),
        (3,0), (3,1), (3,2),
        # Dispatch tiles (y=3)
        (0,3),  # Dispatch 1 (DISPATCH_W) - West/Left
        (3,3),  # Dispatch 0 (DISPATCH_E) - East/Right
    )
    await trinity_binary_loader(dut, test="dm_fds_test", tensix_neos_phys=tensix_neos_phys)

@cocotb.test(skip=False)
async def sanity_edc_test(dut):
    await sanity_edc(dut)

@cocotb.test(skip=True)
@with_biu_check
async def sanity_edc_selftest_test(dut):
    await sanity_edc_selftest(dut)

@cocotb.test(skip=True)
@with_biu_check
async def sanity_edc_harvesting_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/sanity_edc_harvesting/out/sanity_edc_harvesting.bin"
    await sanity_edc_harvesting(
        dut=dut,
        bin_path=bin_path
    )

@cocotb.test(skip=True)
@with_biu_check
async def simple_edc_harvesting_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/simple_edc_harvesting/out/simple_edc_harvesting.bin"
    await simple_edc_harvesting(
        dut=dut,
        bin_path=bin_path
    )

@cocotb.test(skip=False)
@with_biu_check
async def sanity_edc_col_harvesting_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/sanity_edc_col_harvesting/out/sanity_edc_col_harvesting.bin"
    await sanity_edc_col_harvesting(
        dut=dut,
        bin_path=bin_path
    )

@cocotb.test(skip=False)
@with_biu_check
async def simple_edc_col_harvesting_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/simple_edc_col_harvesting/out/simple_edc_col_harvesting.bin"
    await simple_edc_col_harvesting(
        dut=dut,
        bin_path=bin_path
    )

@cocotb.test(skip=False)
async def sanity_fds_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/fds_sanity/out/fds_sanity.bin"
    await sanity_fds(
        dut=dut,
        bin_path=bin_path
    )

@cocotb.test(skip=False)
async def matmul_int8_int82x_int32_32x32_32x32_test(dut):
    os.environ["TEST_SCENARIO"] = "TEST0"
    os.environ["TEST_TYPE"] = "MATMUL"
    os.environ["USE_COMPILED_MATH_DM_BINARIES"] = "1"

    await test_end_to_end_scenario(dut)

@cocotb.test(skip=True)
@with_biu_check
async def matmul_int8_int82x_int32_128x128_128x256_test(dut):
    os.environ["TEST_SCENARIO"] = "TEST1"
    os.environ["TEST_TYPE"] = "MATMUL"
    os.environ["USE_COMPILED_MATH_DM_BINARIES"] = "1"

    await test_end_to_end_scenario(dut)

@cocotb.test(skip=True)
@with_biu_check
async def matmul_bfloat16_bfloat16_float32_32x32_32x32_test(dut):
    os.environ["TEST_SCENARIO"] = "TEST2"
    os.environ["TEST_TYPE"] = "MATMUL"
    os.environ["USE_COMPILED_MATH_DM_BINARIES"] = "1"

    await test_end_to_end_scenario(dut)

@cocotb.test(skip=True)
@with_biu_check
async def matmul_bfloat16_bfloat16_float32_128x128_128x256_test(dut):
    os.environ["TEST_SCENARIO"] = "TEST3"
    os.environ["TEST_TYPE"] = "MATMUL"
    os.environ["USE_COMPILED_MATH_DM_BINARIES"] = "1"

    await test_end_to_end_scenario(dut)

@cocotb.test(skip=True)
@with_biu_check
async def dm_traffic_with_local_matmul_test(dut):
    os.environ["USE_COMPILED_MATH_DM_BINARIES"] = "1"

    await dm_traffic_with_local_matmul(dut)

@cocotb.test(skip=False)
@with_biu_check
async def sanity_security_fence_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/sanity_security_fence/out/sanity_security_fence.bin"
    await sanity_security_fence(
        dut=dut,
        bin_path=bin_path
    )
    
@cocotb.test(skip=True)
@with_biu_check
async def sanity_l1_backdoor_test(dut):
    """Test L1 direct SRAM backdoor access by cross-checking with frontdoor (NoC) access."""
    await sanity_l1_backdoor(dut)

@cocotb.test(skip=False)
@with_biu_check
async def security_fence_noc2axi_test(dut):
    bin_path = f"{os.environ['TENSIX_ROOT']}/firmware/data_movement/tests/security_fence_noc2axi/out/security_fence_noc2axi.bin"
    await security_fence_noc2axi(
        dut=dut,
        bin_path=bin_path
    )

#@cocotb.test(skip=True)
#async def sanity_group_security_test(dut):
#    await sanity_group_security(dut)

#----------------------------
# BIU Interrupt Monitoring - Global Test Hooks
#----------------------------
# Global registry to track TB instances for cleanup
_tb_instances = []

def register_tb_for_biu_check(tb):
    """Register a TB instance for BIU checking at test end."""
    global _tb_instances
    _tb_instances.append(tb)

def check_all_biu_monitors():
    """Check all registered TB instances' BIU monitors."""
    global _tb_instances
    for tb in _tb_instances:
        if hasattr(tb, 'check_biu_monitors'):
            tb.check_biu_monitors()
    _tb_instances.clear()

async def run_test_with_biu_check(test_func, dut):
    """
    Run a test function and check BIU monitors at the end.

    This wrapper is used by ttem_entry_point_to_cocotb to automatically
    check BIU interrupts after each test completes.
    """
    global _disable_biu_checking_for_current_test
    try:
        await test_func(dut)
    finally:
        # Check all registered TB instances
        check_all_biu_monitors()
        # Reset the flag for next test
        _disable_biu_checking_for_current_test = False

#----------------------------
# ttem entry point test
#----------------------------
import logging


@cocotb.test(skip=True)
async def ttem_entry_point_to_cocotb(dut):

    log = logging.getLogger("cocotb.tb")
    log.setLevel(logging.DEBUG)

    cocotb_test_name = cocotb.plusargs.get("COCOTB_TEST")
    if(cocotb_test_name is not None):
        # Check that the module file exists
        # then load it
        log.info(f'Loading test: {cocotb_test_name}')

        test_func = getattr(sys.modules[__name__], cocotb_test_name)
        log.info(f'Running test: {cocotb_test_name}')

        # Run test with automatic BIU checking at end
        await run_test_with_biu_check(test_func, dut)

    else:
        log.info("No COCOTB_TEST plusarg; No test loaded for COCOTB")
