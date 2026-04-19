"""
EDC Selftest — All BIU Nodes
Covers: H01 (sanity_edc_harvesting stub), H02 (sanity_edc_col_harvesting stub)

Existing tests only send selftest to BIU node 0 (NOC2AXI x=0, y=4).
This test iterates over ALL num_apb APB masters and sends the selftest command
to the corresponding BIU node, verifying each responds with a valid GEN_EVENT.

New hole exposed by TB env analysis:
- sanity_edc_selftest.py hardcodes apb_master=0 → BIU nodes 1,2,3 never tested
- BIU_IRQ_EN register write-readback never cross-checked across all nodes
"""

from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.tensix_config import TileType
from tests.utils.edc_util import *
from cocotb.triggers import Timer, ClockCycles, with_timeout
import cocotb


async def edc_selftest_all_nodes(dut):
    """
    EDC Selftest — iterate over ALL APB masters (BIU nodes), not just node 0.

    For each APB master index:
      1. Read BIU_ID_REG and verify non-zero
      2. Clear any leftover status bits
      3. Check for fatal errors
      4. Write and read-back BIU_IRQ_EN_REG
      5. Send selftest command to BIU node (0x1E, y=4, local_id=apb_master)
      6. Predict GEN_EVENT response
      7. Send selftest pulse
      8. Wait for RSP_PKT_RCVD and decode response header
      9. Assert CMD == GEN_EVENT (0x8)
    """

    tb = demoTB(dut)
    await tb.init_and_reset()
    await tb.release_dm_core_reset()

    noc2axi_coords = (
        tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_N_OPT)
        + tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NE_OPT)
    )

    tb.log.info(f"noc2axi_coords: {noc2axi_coords}")
    tb.log.info(f"Number of EDC APB interfaces: {tb.config.num_apb}")

    if len(noc2axi_coords) == 0:
        assert False, "No noc2axi coordinates found"

    num_to_test = min(tb.config.num_apb, len(noc2axi_coords))
    tb.log.info(f"Will test {num_to_test} APB masters")

    # CMD decoding map (matches sanity_edc_selftest.py)
    cmd_map = {
        0b0010: "RD_RSP_CMD",
        0b1000: "GEN_EVENT",
        0b1001: "UNC_EVENT",
        0b1010: "LAT_EVENT",
        0b1011: "COR_EVENT",
        0b1100: "ST_UNC_EVENT",
        0b1101: "ST_LAT_EVENT",
        0b1110: "ST_PASS_EVENT",
        0b1111: "ST_EVENT",
    }

    passed_nodes = []
    failed_nodes = []

    for apb_master in range(num_to_test):
        tb.log.info("=" * 70)
        tb.log.info(f"Testing EDC APB master {apb_master} at {noc2axi_coords[apb_master]}")
        tb.log.info("=" * 70)

        # --- Step a: Read BIU_ID_REG ---
        try:
            biu_id = await tb.read_edc_apb_register(apb_master, BIU_ID_REG)
        except Exception as e:
            assert False, f"APB master {apb_master}: failed to read BIU_ID_REG: {e}"

        assert biu_id != 0, f"APB master {apb_master}: BIU_ID_REG is zero — no response"

        edc_biu_id = biu_id & 0xFF
        edc_version_super = (biu_id >> 28) & 0xF
        edc_version_major = (biu_id >> 24) & 0x0F
        edc_version_minor = (biu_id >> 16) & 0x00FF
        tb.log.info(
            f"  APB[{apb_master}] BIU_ID=0x{edc_biu_id:02x}, "
            f"version={edc_version_super}.{edc_version_major}.{edc_version_minor}"
        )

        # --- Step b: Read and clear leftover status bits ---
        status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
        tb.log.info(f"  APB[{apb_master}] Initial BIU_STAT=0x{status:08x}")

        if status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):
            tb.log.info(
                f"  APB[{apb_master}] Clearing leftover bits "
                f"0x{status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS):08x}"
            )
            await edc_clear_biu_interrupts(
                tb, apb_master, status & (RSP_PKT_RCVD_BIT | ALL_ERROR_BITS)
            )
            await ClockCycles(tb.dut.noc_clk, 1)
            status = await tb.read_edc_apb_register(apb_master, BIU_STAT_REG)
            tb.log.info(f"  APB[{apb_master}] BIU_STAT after clear=0x{status:08x}")

        # --- Step c: Check for fatal errors ---
        if await edc_check_fatal_errors(tb, apb_master, status):
            assert False, f"APB master {apb_master}: fatal error in initial status"

        # --- Step d: Write and read-back BIU_IRQ_EN_REG ---
        await tb.write_edc_apb_register(apb_master, BIU_IRQ_EN_REG, 0xBB)
        irq_en_rb = await tb.read_edc_apb_register(apb_master, BIU_IRQ_EN_REG)
        assert irq_en_rb == 0xBB, (
            f"APB master {apb_master}: BIU_IRQ_EN_REG readback mismatch: "
            f"wrote 0xBB, read 0x{irq_en_rb:08x}"
        )
        tb.log.info(f"  APB[{apb_master}] BIU_IRQ_EN readback: 0x{irq_en_rb:08x} — OK")

        # --- Step e: Start rsp_pkt_rcvd monitor ---
        await tb.start_biu_monitors(interrupt_types=["rsp_pkt_rcvd"], checking_enabled=True)

        # --- Step f: Build target_node_id for this BIU ---
        # NOC2AXI BIU: partition=0x1E, y=4, local_id=apb_master
        target_node_id = (0x1E << 11) | (0x4 << 8) | apb_master
        tb.log.info(f"  APB[{apb_master}] target_node_id=0x{target_node_id:04x}")

        # Write selftest pattern selection register
        SEC_REG_CMD_OPT = 0x81
        reg_data = bytearray([0x03, 0x00])  # LSB MSB
        payload_len = len(reg_data) - 1

        success = await edc_send_write_command(
            tb, apb_master, target_node_id, reg_data, SEC_REG_CMD_OPT, payload_len=payload_len
        )
        if not success:
            assert False, (
                f"APB master {apb_master}: failed to write selftest pattern "
                f"selection to node 0x{target_node_id:04x}"
            )
        await ClockCycles(tb.dut.noc_clk, 10)

        # --- Step g: Predict GEN_EVENT response ---
        tb.biu_monitor_manager.biu[apb_master]["rsp_pkt_rcvd"].predict(
            {
                "expected_cmd": 0x8,  # GEN_EVENT
                "expected_src_id": target_node_id,
            }
        )
        tb.log.info(
            f"  APB[{apb_master}] Predicted GEN_EVENT from SRC_ID=0x{target_node_id:04x}"
        )

        # --- Step h: Send selftest pulse ---
        SEC_REG_PULSE_CMD_OPT = 0x40
        pulse_data = [0x1]
        success = await edc_send_write_command(
            tb, apb_master, target_node_id, pulse_data, SEC_REG_PULSE_CMD_OPT, payload_len=0
        )
        if not success:
            assert False, (
                f"APB master {apb_master}: failed to write selftest pulse "
                f"to node 0x{target_node_id:04x}"
            )

        # --- Step i: Wait for RSP_PKT_RCVD ---
        rsp_pkt_rcvd = await edc_wait_for_response_packet_received(
            tb, apb_master, timeout_cycles=15000
        )

        if not rsp_pkt_rcvd:
            failed_nodes.append(apb_master)
            assert False, f"APB master {apb_master}: no selftest response received (timeout)"

        # --- Steps j/k: Decode and validate response ---
        rsp_hdr0 = await tb.read_edc_apb_register(apb_master, BIU_RSP_HDR0_REG)
        rsp_hdr1 = await tb.read_edc_apb_register(apb_master, BIU_RSP_HDR1_REG)

        tgt_id = (rsp_hdr0 >> 16) & 0xFFFF
        cmd_raw = (rsp_hdr0 >> 12) & 0xF
        pyld_len = (rsp_hdr0 >> 8) & 0xF
        src_id = (rsp_hdr1 >> 16) & 0xFFFF

        cmd_str = cmd_map.get(cmd_raw, f"UNKNOWN(0x{cmd_raw:x})")
        tb.log.info(
            f"  APB[{apb_master}] RSP_HDR0=0x{rsp_hdr0:08x}: "
            f"SRC_ID=0x{src_id:04x}, CMD={cmd_str}, PYLD_LEN={pyld_len}"
        )

        if cmd_raw in [0b1000, 0b1001, 0b1010, 0b1011, 0b1110, 0b1111]:
            selftest_bit = (rsp_hdr0 >> 7) & 0x1
            event_id = rsp_hdr0 & 0xF
            tb.log.info(
                f"  APB[{apb_master}] SELFTEST={selftest_bit}, EVENT_ID=0x{event_id:x}"
            )

        assert cmd_raw == 0x8, (
            f"APB master {apb_master}: expected GEN_EVENT (0x8), "
            f"got {cmd_str} (0x{cmd_raw:x})"
        )

        # --- Step l: Clear RSP_PKT_RCVD before next iteration ---
        await edc_clear_biu_interrupts(tb, apb_master, RSP_PKT_RCVD_BIT)
        await ClockCycles(tb.dut.noc_clk, 2)

        passed_nodes.append(apb_master)
        tb.log.info(f"  APB master {apb_master} selftest PASSED")

    tb.log.info("=" * 70)
    tb.log.info(f"EDC Selftest All Nodes: PASSED={passed_nodes}, FAILED={failed_nodes}")
    tb.log.info("=" * 70)

    assert len(failed_nodes) == 0, (
        f"EDC selftest failed for APB masters: {failed_nodes}"
    )
    tb.log.info("edc_selftest_all_nodes PASSED")
