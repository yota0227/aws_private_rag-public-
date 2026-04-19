from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
import os

TT_CLUSTER_CTRL_SCRATCH_0__REG_ADDR = 0x03000048
MAX_ATTEMPTS = 1000
WAIT_CYCLES = 2048

async def wait_for_test_status(tb, master, x, y):
    attempts = MAX_ATTEMPTS
    
    while attempts > 0:
        read = await tb.noc_read_dword(master, x, y, TT_CLUSTER_CTRL_SCRATCH_0__REG_ADDR)
        tb.log.info(f"Test status on tile {x}, {y}: {hex(read)}")
        
        if read == POSTCODE_FAIL:
            assert False, f"Test failed on tile {x}, {y}"
        
        if read == POSTCODE_PASS:
            tb.log.info(f"Test passed on tile {x}, {y}")
            return
            
        await ClockCycles(tb.dut.ai_clk, WAIT_CYCLES)
        attempts -= 1
        assert attempts > 0, f"Test timed out on tile {x}, {y}"

async def trinity_binary_loader(dut, test=None, tensix_neos_phys=((0,0),)):
    tb = demoTB(dut)
    
    # Load the binary file
    hex_file = f"{os.environ['TENSIX_ROOT']}/firmware/overlay/software/unit_tests/{test}/out/{test}128.hex"
    assert hex_file is not None, "HEX_PATH variable not set"
    assert os.path.exists(hex_file), f"Hex file not found at {hex_file}"
    
    binary_data = load_binary_from_hex(hex_file)
    assert len(binary_data) > 0, "Binary is empty"
    
    # Initialize the DUT and reset
    await tb.init_and_reset()
    if (os.environ.get("TRINITY_PRELOAD_T6_L1") != "1"):
        # Load binary to all memory nodes
        master = 0
        tb.log.info(f'Using master {master} to load DM binaries...')
        
        for tensix_phys_x, tensix_phys_y in tensix_neos_phys:
            if (tensix_phys_x, tensix_phys_y) not in tb.config.get_tiles_with_memory() :
                continue
            tb.noc_write_nonblocking(master, tensix_phys_x, tensix_phys_y, 0x0, binary_data) # Perform the write
        
        await tb.noc_wait_writes(master)
        tb.log.info('Binary load complete.')
        
    # Release cores from reset and monitor test status
    await tb.release_dm_core_reset()
    
    for tensix_phys_x, tensix_phys_y in tensix_neos_phys:
        tb.log.info(f"Monitoring for test status on tile {tensix_phys_x}, {tensix_phys_y}")
        await wait_for_test_status(tb, master, tensix_phys_x, tensix_phys_y)

def load_binary_from_hex(hex_file):
    binary_data = bytearray()
    with open(hex_file, "r") as f:
        for line in f:
            hex_value = line.strip()
            # Reverse the byte order
            binary_data.extend(bytes.fromhex(hex_value)[::-1])
    return binary_data
