from tests.utils.coco_tensix_api import *
from tests.utils.test_utils import *
from tests.utils.noc.att_loader import *
import os

async def att_translation_config(dut):
    tb = demoTB(dut)

    await tb.init_and_reset()

    master = tb.config.get_coordinates_for_tile_type(TileType.NOC2AXI_NW_OPT)[0]

    att = AddressTranslationTables.from_yaml(
        f"{os.environ['TENSIX_ROOT']}/tb/att_user_configs.yaml", config_name="trinity",
        self_x=master[0], self_y=master[1],
        grid_x_size=tb.config.size_x, grid_y_size=tb.config.size_y,
        en_address_translation=True,
        en_dynamic_routing=False,
        clk_gating_enable=False,
        clk_gating_hysteresis=6,
        remap_base=0x200_0000 + 0x1_0000
    )
    
    writes = att.get_register_writes()

    tb.log.info(f"Writing ATT")
    for reg_addr, data in writes:
        await tb.write_apb_register(0, reg_addr, data)

    datas = {}
    for idx, (x, y) in enumerate(tb.config.get_coordinates_for_tile_type(TileType.TENSIX)):
        addr = idx << 22
        rand_data = bytearray(os.urandom(16))
        tb.log.info(f"Writing data to {x}, {y} using address {hex(addr)}")
        await tb.masters[0].write(addr, rand_data)
        datas[(x,y)] = rand_data
    
    for idx, (x, y) in enumerate(tb.config.get_coordinates_for_tile_type(TileType.TENSIX)):
        addr = idx << 22
        tb.log.info(f"Reading data from {x}, {y} using address {hex(addr)}")
        read = await tb.masters[0].read(addr, length=16)
        expected_data = datas[(x,y)]
        assert read.data == expected_data, "Data read back does not match data written"

    return
