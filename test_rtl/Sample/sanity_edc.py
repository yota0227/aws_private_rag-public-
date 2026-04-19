from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from cocotb.triggers import Timer

async def sanity_edc(dut):
    """
    Test EDC APB communication to BIU (Bus Interface Unit) in noc2axi tiles.
    
    This test demonstrates how to use cocotb EDC APB extension to send APB traffic to 
    the BIU interface for EDC (Error Detection and Correction) communication.
    
    The BIU acts as the EDC ring master and can issue read/write messages to EDC nodes
    through its EDC APB register interface.
    """
    tb = demoTB(dut)

    await tb.init_and_reset()
    await tb.release_dm_core_reset()

    # Get noc2axi coordinates - these have BIU interfaces
    noc2axi_coords = (tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT) + 
                      tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT) + 
                      tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT))
    
    tb.log.info(f"noc2axi_coords: {noc2axi_coords}")
    tb.log.info(f"Number of EDC APB interfaces: {tb.config.num_apb}")
    
    if len(noc2axi_coords) == 0:
        assert False, f"No noc2axi coordinates found"

    # Always test APB master 0 for deterministic behavior
    apb_master = 0
    if apb_master >= min(tb.config.num_apb, len(noc2axi_coords)):
        assert False, f"APB master {apb_master} not available (num_apb={tb.config.num_apb}, noc2axi_coords={len(noc2axi_coords)})"

    tb.log.info(f"Testing EDC APB master {apb_master} - noc2axi at {noc2axi_coords[apb_master] if apb_master < len(noc2axi_coords) else 'N/A'}")
    
    # Read BIU ID register to verify communication
    try:
        biu_id = await tb.read_edc_apb_register(apb_master, BIU_ID_REG)
        tb.log.info(f"EDC APB Master {apb_master} - BIU ID: 0x{biu_id:08x}")
        
        # Extract version and BIU ID fields
        edc_biu_id = biu_id & 0xFF
        edc_version_super = (biu_id >> 28) & 0xF
        edc_version_major = (biu_id >> 24) & 0x0F
        edc_version_minor = (biu_id >> 16) & 0x00FF
        tb.log.info(f"  EDC BIU ID: 0x{edc_biu_id:02x}")
        tb.log.info(f"  EDC Version: {edc_version_super:1d}.{edc_version_major:1d}.{edc_version_minor:1d}")
        
    except Exception as e:
        assert False, f"Failed to read BIU ID from EDC APB master {apb_master}: {e}"
        
    # Read initial status register
    status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
    tb.log.info(f"EDC APB Master {apb_master} - Initial Status: 0x{status:08x}")
    
    # Clear any leftover status bits from previous tests (error packets, etc.)
    if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
        tb.log.info(f"  Clearing leftover status bits: 0x{status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):08x}")
        await edc_clear_biu_interrupts(tb, apb_master, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS))
        # Wait a cycle for clear to take effect
        await ClockCycles(tb.dut.noc_clk, 1)
        # Re-read status after clear
        status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        tb.log.info(f"EDC APB Master {apb_master} - Status after clear: 0x{status:08x}")
    
    # Check for fatal errors in initial status (after clearing leftovers)
    if await edc_check_fatal_errors(tb, apb_master, status):
        assert False, f"Fatal error detected in initial status - APB master {apb_master}"

    # Enable all interrupts
    await tb.write_edc_apb_register(apb_master, BIU_IRQ_EN_REG, 0xBB)

    # Read back interrupt enable register to verify
    irq_en_readback = await tb.read_edc_apb_register(apb_master, BIU_IRQ_EN_REG)
    tb.log.info(f"EDC APB Master {apb_master} - IRQ Enable readback: 0x{irq_en_readback:08x}")

    # Test control register read/write
    # await tb.write_edc_apb_register(apb_master, BIU_CTRL_REG, 0x1)  # Set INIT bit
    ctrl_readback = await tb.read_edc_apb_register(apb_master, BIU_CTRL_REG)
    tb.log.info(f"EDC APB Master {apb_master} - Control register: 0x{ctrl_readback:08x}")

    # Test write-then-read verification for EDC transactions
    tb.log.info(f"EDC APB Master {apb_master} - Testing write-then-read verification")
    
    # Store write transactions for later verification
    write_transactions = []
    
    # Perform additional write transactions for read-back veriReading from noc sec regfication
    num_verify_transactions = 1
    for i in range(num_verify_transactions):
        try:
            # Writing to the bottom Tensix tile NOC Security EDC node
            verify_target_node = (0x1E << 11) | (0 << 8) | 0xC0 #NOC Security EDC node in bottom tensix tile in overlay section
            verify_test_data = bytearray(REG_OFFSET_SLV_TILE_HARVEST.to_bytes(4, byteorder='little')) + bytearray([0x04])
            verify_test_data_len = len(verify_test_data)-1
            verify_reg_addr_offset = 0x0 # Configuration registers offset from address 0x80

            tb.log.info(f"  Write-Verify Transaction {i+1}:")
            tb.log.info(f"    Target Node ID: 0x{verify_target_node:04x}")
            tb.log.info(f"    Verify Data: {len(verify_test_data)} bytes: {[hex(b) for b in verify_test_data]}")
            tb.log.info(f"    Register Address: 0x{verify_reg_addr_offset:02x}")

            # Send write transaction using helper function
            success = await edc_write_noc_sec_regs(tb, apb_master, verify_target_node, verify_reg_addr_offset, verify_test_data, verify_test_data_len)
            if success:
                # Store for later read verification
                write_transactions.append({
                    'node_id': verify_target_node,
                    'data': verify_test_data,  # Exclude first 4 bytes (header)
                    'payload_len': verify_test_data_len,
                    'reg_addr_offset': verify_reg_addr_offset
                })
                tb.log.info(f"    Write verification data stored")
            else:
                assert False, f"Failed transaction {i+1} - APB master {apb_master}"

        except Exception as e:
            assert False, f"Failed transaction {i+1} - APB master {apb_master}"
    
    # Now read back the written data for verification
    tb.log.info(f"EDC APB Master {apb_master} - Reading back written data for verification")

    for i, write_txn in enumerate(write_transactions):
        try:
            target_node = write_txn['node_id']
            expected_data = write_txn['data'][4:]
            reg_addr_offset = write_txn['data'][:4]  # Convert to byte array
            expected_read_len = write_txn['payload_len']-4

            tb.log.info(f"  Read-back {i+1}: Node 0x{target_node:04x}, Reg 0x{reg_addr_offset.hex()}")
            tb.log.info(f"    Expected data: {len(expected_data)} bytes: {[hex(b) for b in expected_data]}")
            
            # Send read command using helper function
            success, read_back_data = await edc_read_noc_sec_regs(tb, apb_master, target_node, reg_addr_offset, expected_read_len)

            if success and read_back_data is not None:
                # Compare written vs read data (both are now byte arrays)
                if read_back_data == expected_data:
                    tb.log.info(f"DATA MATCH: Write/Read verification successful!")
                else:
                    tb.log.error(f"DATA MISMATCH:")
                    tb.log.error(f"      Expected: {len(expected_data)} bytes: {[hex(b) for b in expected_data]}")
                    tb.log.error(f"      Got:      {len(read_back_data)} bytes: {[hex(b) for b in read_back_data]}")
                    assert False, f"Read-back data mismatch on transaction {i+1} - APB master {apb_master}"
            else:
                assert False, f"Read-back failed transaction {i+1} - APB master {apb_master}"
                
        except Exception as e:
            assert False, f"Read-back failed {i+1} - APB master {apb_master}"

    tb.log.info("EDC APB BIU communication test completed successfully")