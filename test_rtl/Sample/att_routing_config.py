from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.noc.att_loader import *
from tests.utils.noc_driver import NocTransactionConfig
from cocotb.triggers import with_timeout
import os

async def att_routing_config(dut):
    tb = demoTB(dut)

    await tb.init_and_reset()

    tb.log.info(f'Design Config: {tb.config}')

    master = tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)[0]

    att = AddressTranslationTables.from_yaml(
        f"{os.environ['TENSIX_ROOT']}/tb/att_user_configs.yaml", config_name="trinity",
        self_x=master[0], self_y=master[1],
        grid_x_size=tb.config.size_x, grid_y_size=tb.config.size_y,
        en_address_translation=True,
        en_dynamic_routing=True,
        clk_gating_enable=False,
        clk_gating_hysteresis=6,
        remap_base=0x200_0000 + 0x1_0000
    )
    
    writes = att.get_register_writes()
    tb.log.info(f"Writing ATT")
    for reg_addr, data in writes:
        await tb.write_apb_register(0, reg_addr, data)


    data = rand_data = bytearray(os.urandom(16))
    # Write the dynamic route entry
    dynamic_route_entry = 20
    addr = dynamic_route_entry << 22
    write_config = NocTransactionConfig(req_vc=0)
    user_bits = write_config.get_user_bits()
    tb.log.info(f"Writing data to {hex(addr)} using address {hex(addr)}")

    await tb.masters[0].write(addr, rand_data, user=user_bits)

    indexes = {
        (x, y): y * tb.config.size_x + x
        for y in range(tb.config.size_y)
        for x in range(tb.config.size_x)
    }
    tb.log.info(f"Indexes: {indexes}")

    # Define expected NIU destination coordinates
    expected_coords = [(0, 3), (0, 2), (1, 2), (1, 1), (2, 1), (3, 1), (3, 0)]

    # Create list of coordinates that should fail (non-NIU destinations with relevant tile types)
    should_fail_coords = [
        (x, y) for x in range(tb.config.size_x) 
            for y in range(tb.config.size_y)
            if (x, y) not in expected_coords 
            and tb.config.get_tile_type(x, y) in [TileType.TENSIX, TileType.DISPATCH_E, TileType.DISPATCH_W]
    ]

    # Test expected coordinates (should match data)
    reads = []
    for x, y in expected_coords:
        index = indexes[(x, y)]
        addr = index << 22
        tb.log.info(f"Reading from {hex(addr)}, x={x}, y={y}, index={index}")
        read = await tb.masters[0].read(addr, 16)
        assert read.data == data, f"Data read back does not match data written at {x}, {y}"
        tb.log.info(f"Success! Data read back matches data written at {x}, {y}")

    # Test coordinates that should fail (should not match data)
    for x, y in should_fail_coords:
        index = indexes[(x, y)]
        addr = index << 22
        tb.log.info(f"Reading from {hex(addr)}, x={x}, y={y}, index={index}")
        read = await tb.masters[0].read(addr, 16)
        assert read.data != data, f"Data read back matches data written at {x}, {y}"
        tb.log.info(f"Success! Data read back does not match data written at {x}, {y}")
