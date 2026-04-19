from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from cocotb.triggers import Timer


async def sanity_edc_selftest(dut):

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

    # Test gtile0 test for diagnostics
    tb.log.info(f"EDC APB Master {apb_master} - Testing selftest")

    #Tensix gtile0 at coordinates (0,0) - General Error EDC node
    #Partition: NODE_ID_PART_TENSIX = 0x10
    #Y coordinate: 0 (tile at y=0)
    #Instance: 0 (gtile0, general error EDC node)
    target_node_id = 0x8000
    tb.log.info(f"Selftest target ID : 0x{target_node_id:04x} (Tensix gtile0 general error EDC node at (0,0))")
    #config regs address offset
    SEC_REG_CMD_OPT = 0x80
    #Value of the configuration register containing the self-pattern selection
    #Set LSB (bit 0) of config register --> test for diagnostics
    reg_data = bytearray([0x01, 0x00])  #LSB MSB - sets bit 0 only
    payload_len = len(reg_data)-1

    success = await edc_send_write_command(tb, apb_master, target_node_id, reg_data, SEC_REG_CMD_OPT, payload_len=payload_len)
    if not success:
        assert False, f"Failed to write selftest pattern selection on node 0x{target_node_id:04x}"
    await ClockCycles(tb.dut.noc_clk, 10)

    #pulse regs address offset
    SEC_REG_PULSE_CMD_OPT = 0x40 
    #Set LSB (bit 0) of pulse register
    pulse_data = [0x01]  # Sets only bit 0 (LSB)
    success = await edc_send_write_command(tb, apb_master, target_node_id, pulse_data, SEC_REG_PULSE_CMD_OPT, payload_len=0)
    if not success:
        assert False, f"Failed to write selftest start on node 0x{target_node_id:04x}"

    # Wait for response packet by polling STATUS register for RSP_PKT_RCVD_BIT
    rsp_pkt_rcvd = await edc_wait_for_response_packet_received(tb, apb_master, timeout_cycles=10000)

    if rsp_pkt_rcvd:
        rsp_status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        tb.log.info(f"  Response status: 0x{rsp_status:08x}, RSP_PKT_RCVD: 1")
        rsp_hdr0 = await tb.read_edc_apb_register(apb_master, BIU_RSP_HDR0_REG)
        rsp_hdr1 = await tb.read_edc_apb_register(apb_master, BIU_RSP_HDR1_REG)


        tgt_id   = (rsp_hdr0 >> 16) & 0xFFFF
        cmd_raw  = (rsp_hdr0 >> 12) & 0xF
        pyld_len = (rsp_hdr0 >> 8) & 0xF

        src_id = (rsp_hdr1 >> 16) & 0xFFFF

# --- CMD Decoding ---
        cmd_map = {
            0b0010: "RD_RSP_CMD",
            0b1000: "GEN_EVENT",
            0b1001: "UNC_EVENT",
            0b1010: "ADR_EVENT",
            0b1011: "COR_EVENT",
            0b1110: "OVF_EVENT",
            0b1111: "SLF_EVENT"
        }
        cmd_str = cmd_map.get(cmd_raw, f"UNKNOWN(0x{cmd_raw:x})")

        tb.log.info(f"  RSP_HDR0: 0x{rsp_hdr0:08x}")
        tb.log.info(f"    - SRC_ID  : 0x{src_id:04x}")
        tb.log.info(f"    - TGT_ID  : 0x{tgt_id:04x} ({'Broadcast' if tgt_id == 0xFFFF else 'Target'})")
        tb.log.info(f"    - CMD     : {cmd_str} (0x{cmd_raw:x})")
        tb.log.info(f"    - PYLD_LEN: {pyld_len} ({pyld_len + 1} bytes)")

        if cmd_raw in [0b1000, 0b1001, 0b1010, 0b1011, 0b1110, 0b1111]:
            selftest    = (rsp_hdr0 >> 7) & 0x1
            ovf_cmd     = (rsp_hdr0 >> 4) & 0x7
            # Reconstruct EVENT_ID from Bits 3:1 and Bit 0
            event_id    = (rsp_hdr0 & 0xF) 
            
            tb.log.info(f"    - SELFTEST: {selftest}")
            tb.log.info(f"    - OVF_CMD : 0x{ovf_cmd:x}")
            tb.log.info(f"    - EVENT_ID: 0x{event_id:x}")


    else:
        assert False, f"Error: No selftest response received"

    tb.log.info("EDC selftest completed successfully")