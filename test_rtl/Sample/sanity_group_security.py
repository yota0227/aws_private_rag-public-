from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.noc.noc_fence_reg import *
from cocotb.triggers import with_timeout
import os


# The test will associate tensix 0,0 with Group id= 1, and tensix 0,1 with Group id=2
# then it will try to write and read from both using group id=1 

def set_group_security_setting(sec_reg,group,ns):
        for i in range(8):
            sec_reg.sec_fence_range_start_lo[i].ADDRESS= 0
            sec_reg.sec_fence_range_start_hi[i].ADDRESS=0
            sec_reg.sec_fence_range_end_lo[i].ADDRESS=0
            sec_reg.sec_fence_range_end_hi[i].ADDRESS=0
            sec_reg.sec_fence_attribute[i].RANGE_ENABLE=0
            sec_reg.sec_fence_attribute[i].WR_SEC_LEVEL=0
            sec_reg.sec_fence_attribute[i].RD_SEC_LEVEL=0
      
        # Single registers
        sec_reg.sec_fence_master_level.MASTER_LEVEL=0
        sec_reg.sec_fence_master_level.TAG_GROUP_ID=group
        sec_reg.sec_fence_master_level.CHECK_GROUP_ID=group
        sec_reg.sec_fence_master_level.TAG_NS=ns
        sec_reg.sec_fence_master_level.CHECK_NS=ns
        sec_reg.sec_fence_default_range_start_lo.ADDRESS= 0
        sec_reg.sec_fence_default_range_start_hi.ADDRESS= 0
        sec_reg.sec_fence_default_range_end_lo.ADDRESS=0
        sec_reg.sec_fence_default_range_end_hi.ADDRESS=0

async def sanity_group_security(dut):
    tb = demoTB(dut)
    # Initialize the DUT and reset
    await tb.init_and_reset()
    # Create an instance of the ATT register
    # and program it for dynamic routing 
    SecReg_0=SecureFenceReg()
    SecReg_1=SecureFenceReg()
    set_group_security_setting(SecReg_0,1,1)
    set_group_security_setting(SecReg_1,2,1)
    #use Master 0 to configure the security registers of Tensix 0,0 
    tb.log.info(f' *** Setting Group Security for Tensix 0,0 ***')
    await tb.write_noc_sec_reg(0,0,0,SecReg_0)
    #use Master 0 to configure the security registers of Tensix  0,1
    tb.log.info(f' *** Setting Group Security for Tensix 0,1 ***')
    await tb.write_noc_sec_reg(0,0,1,SecReg_1)

    
    ## initiating Traffic on the AXI Bus
    transaction_size_bytes = 64
    data = bytearray(os.urandom(transaction_size_bytes))
    for x in range(2):
        addr = (0 << 46) | (x << 40) | 0
        # Mark transaction as non-posted
        tlb = TLBParams()
        tlb.cmd_resp_marked = 1
        tlb.cmd_static_vc,tlb.cmd_resp_static_vc=get_random_req_resp_vcs(0)
        tlb.cmd_force_user_bits_vc=1 # force the VC to come from user bits
        tlb.sec_group_id=1
        user_bits = tlb.get_full_value()
        tb.log.info(f' *** Writing to Tensix 0,{x} with Group ID=1 ***')
        # Perform the write
        ##  PRIVILEGED  = 0b001
        ##  NONSECURE   = 0b010
        ##  INSTRUCTION = 0b100
        await with_timeout(tb.masters[0].write(addr, data, user=user_bits,prot=0b000), 5000, "ns")

        tb.log.info(f' *** Reading from Tensix 0,{x} with Group ID=1 ***')
        read = await with_timeout(tb.masters[1].read(addr, length=transaction_size_bytes,user=user_bits,prot=0b000), 5000, "ns")
        expected_data = data
        if read.data != expected_data:
            for i in range(0, len(expected_data), 16):
                expected_chunk = expected_data[i:i+16]
                read_chunk = read.data[i:i+16]

                if expected_chunk == read_chunk:
                    tb.log.info(f"Word {i}: 0x{expected_chunk.hex()}")
                else:
                    tb.log.error(f"Word {i}: 0x{expected_chunk.hex()} != 0x{read_chunk.hex()}")

            # Raise an assertion error if data does not match
            assert False, "Data read back does not match data written"
        else:
            tb.log.info(f' *** Check passed ***')
