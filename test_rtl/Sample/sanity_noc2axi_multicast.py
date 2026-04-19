from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
import os

async def sanity_noc2axi_multicast(dut):
    tb = demoTB(dut)

    # Initialize the DUT and reset
    await tb.init_and_reset()

    transaction_size_bytes = 256

    tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
    dram_coords = tb.config.get_coordinates_for_tile_type(TileType.DRAM)
    dispatch_coords = tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_E) + tb.config.get_coordinates_for_tile_type(TileType.DISPATCH_W)

    tb.log.info(f"tensix_coords: {tensix_coords}")
    tb.log.info(f"dram_coords: {dram_coords}")
    tb.log.info(f"dispatch_coords: {dispatch_coords}")

    valid_coords = tensix_coords + dispatch_coords

    start_x, start_y, offset_x, offset_y = find_largest_rectangle(valid_coords)
    end_x = start_x + offset_x - 1
    end_y = start_y + offset_y - 1

    multicast_addr = 0x0
    for m in range(tb.config.num_noc2axi):
        rand_data = bytearray(os.urandom(transaction_size_bytes))
        tb.log.info(f"Writing {transaction_size_bytes} bytes to rectangle at x={start_x}, y={start_y} to x={end_x}, y={end_y}")
        await tb.noc_multicast(m, start_x, start_y, offset_x, offset_y, multicast_addr, rand_data)

        await ClockCycles(dut.noc_clk, 512)

        # Check the data written to the rectangle
        for x in range(start_x, end_x + 1):
            for y in range(start_y, end_y + 1):
                read = await tb.noc_read(m, x, y, multicast_addr, transaction_size_bytes)
                assert read.data == rand_data, f"Data read back does not match data written at x={x}, y={y} with master {m}"

        tb.log.info(f"Readback check passed for rectangle at x={start_x}, y={start_y} to x={end_x}, y={end_y} with master {m}")
        multicast_addr += transaction_size_bytes