from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import find_largest_rectangle
from tests.utils.tensix_config import TileType
from tests.utils.noc_driver import NocTransactionConfig
from cocotb.triggers import ClockCycles, with_timeout
import os, random

async def strided_multicast_discovery(dut):
    tb = demoTB(dut)
    await tb.init_and_reset()

    for ii in range(5):  # Run the test multiple times
        x_keep = random.randint(0, 3)
        y_keep = random.randint(0, 3)
        x_skip = random.randint(0, 3)
        y_skip = random.randint(0, 3)

        # Log the strided multicast configuration
        tb.log.info(f"Strided config: x_keep={x_keep}, x_skip={x_skip}, y_keep={y_keep}, y_skip={y_skip}")
        
        # Send unique data to the strided pattern of Tensix cores
        transaction_size_bytes = 64
        bcst_data = bytearray(os.urandom(transaction_size_bytes))
        
        tensix_coords = tb.config.get_coordinates_for_tile_type(TileType.TENSIX)
        start_x, start_y, offset_x, offset_y = find_largest_rectangle(tensix_coords)
        
        tb.log.info(f"Multicast rectangle: start=({start_x},{start_y}), size=({offset_x},{offset_y})")

        multicast_config = NocTransactionConfig(
            non_posted = False,
            strided = [x_keep, y_keep, x_skip, y_skip],
            multicast = [offset_x, offset_y],
        )

        # master = ii % tb.config.num_noc2axi
        master = random.choice(range(tb.config.num_noc2axi))
        await with_timeout(tb.noc_write(master, start_x, start_y, 0x0, bcst_data, config=multicast_config), 1000, "ns")
        tb.log.info(f"Data sent to strided pattern of Tensix cores")

        await ClockCycles(dut.ai_clk, 128)

        # Create a grid to visualize the pattern
        grid = []
        for y in range(start_y, start_y + offset_y + 1):
            row = []
            for x in range(start_x, start_x + offset_x + 1):
                # Calculate if this node is in a "keep" position for both X and Y
                # For X direction: if either keep or skip is 0, all positions are kept
                if x_keep == 0 or x_skip == 0:
                    is_x_kept = True
                else:
                    x_position = x - start_x
                    x_cycle_length = x_keep + x_skip
                    x_position_in_cycle = x_position % x_cycle_length
                    is_x_kept = x_position_in_cycle < x_keep
                
                # For Y direction: if either keep or skip is 0, all positions are kept
                if y_keep == 0 or y_skip == 0:
                    is_y_kept = True
                else:
                    y_position = y - start_y
                    y_cycle_length = y_keep + y_skip
                    y_position_in_cycle = y_position % y_cycle_length
                    is_y_kept = y_position_in_cycle < y_keep
                
                # Only nodes that are kept in both X and Y directions receive the data
                should_receive = is_x_kept and is_y_kept
                
                # Mark the position in the grid
                row.append("X" if should_receive else ".")
            grid.append(row)
            
        # Display the grid for debugging
        tb.log.info("Broadcast pattern grid:")
        for row in grid:
            tb.log.info(" ".join(row))


        # Check if each Tensix core should have received the data
        for tensix_coord in tensix_coords:
            x, y = tensix_coord
            # Check if this coordinate is within our multicast rectangle
            if start_x <= x <= start_x + offset_x and start_y <= y <= start_y + offset_y:
                # Calculate if this coordinate should receive data based on strided pattern
                # For X direction: if either keep or skip is 0, all positions are kept
                if x_keep == 0 or x_skip == 0:
                    is_x_kept = True
                else:
                    x_position = x - start_x
                    x_cycle_length = x_keep + x_skip
                    x_position_in_cycle = x_position % x_cycle_length
                    is_x_kept = x_position_in_cycle < x_keep
                
                # For Y direction: if either keep or skip is 0, all positions are kept
                if y_keep == 0 or y_skip == 0:
                    is_y_kept = True
                else:
                    y_position = y - start_y
                    y_cycle_length = y_keep + y_skip
                    y_position_in_cycle = y_position % y_cycle_length
                    is_y_kept = y_position_in_cycle < y_keep
                
                should_receive = is_x_kept and is_y_kept
                
                # Now read the data and verify
                read = await with_timeout(tb.noc_read(0, x, y, 0x0, transaction_size_bytes), 5000, "ns")
                match_status = "MATCH" if read.data == bcst_data else "MISMATCH"
                tb.log.info(f"Core [x, y] = [{x},{y}]: Should receive={should_receive}, Status={match_status}")
                
                if should_receive:
                    assert read.data == bcst_data, f"Core at ({x},{y}) should have received the data but didn't match"
                else:
                    assert read.data != bcst_data, f"Core at ({x},{y}) shouldn't have received the data but did"

        tb.log.info(f"Test iteration completed successfully")