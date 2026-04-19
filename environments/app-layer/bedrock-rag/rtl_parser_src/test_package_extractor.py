"""
Tests for package_extractor.py — localparam, parameter, typedef enum extraction.
"""

import pytest
from package_extractor import (
    extract_package_params,
    identify_chip_config,
    extract_enum_mapping,
)


# ---------------------------------------------------------------------------
# extract_package_params tests
# ---------------------------------------------------------------------------

class TestExtractPackageParams:
    def test_empty_input(self):
        result = extract_package_params("")
        assert result == {"localparams": {}, "parameters": {}, "enums": {}}

    def test_none_input(self):
        result = extract_package_params(None)
        assert result == {"localparams": {}, "parameters": {}, "enums": {}}

    def test_single_localparam(self):
        content = "localparam SizeX = 4;"
        result = extract_package_params(content)
        assert result["localparams"]["SizeX"] == "4"

    def test_localparam_with_logic_type(self):
        content = "localparam logic [3:0] NumTensix = 12;"
        result = extract_package_params(content)
        assert result["localparams"]["NumTensix"] == "12"

    def test_multiple_localparams(self):
        content = """
        localparam SizeX = 4;
        localparam SizeY = 5;
        localparam NumTensix = 12;
        """
        result = extract_package_params(content)
        assert len(result["localparams"]) == 3
        assert result["localparams"]["SizeX"] == "4"
        assert result["localparams"]["SizeY"] == "5"

    def test_single_parameter(self):
        content = "parameter integer Width = 64"
        result = extract_package_params(content)
        assert result["parameters"]["Width"] == "64"

    def test_parameter_without_type(self):
        content = "parameter Depth = 256"
        result = extract_package_params(content)
        assert result["parameters"]["Depth"] == "256"

    def test_typedef_enum_simple(self):
        content = """
        typedef enum logic [2:0] {
            TENSIX,
            NOC2AXI,
            DISPATCH
        } tile_type_t;
        """
        result = extract_package_params(content)
        assert "tile_type_t" in result["enums"]
        assert "TENSIX" in result["enums"]["tile_type_t"]
        assert "NOC2AXI" in result["enums"]["tile_type_t"]
        assert "DISPATCH" in result["enums"]["tile_type_t"]

    def test_typedef_enum_with_assignments(self):
        content = """
        typedef enum {
            IDLE = 0,
            ACTIVE = 1,
            DONE = 2
        } state_t;
        """
        result = extract_package_params(content)
        assert "state_t" in result["enums"]
        assert "IDLE" in result["enums"]["state_t"]

    def test_mixed_declarations(self):
        content = """
        localparam SizeX = 4;
        parameter NumNoc2Axi = 8;
        typedef enum { A, B, C } my_enum_t;
        """
        result = extract_package_params(content)
        assert "SizeX" in result["localparams"]
        assert "NumNoc2Axi" in result["parameters"]
        assert "my_enum_t" in result["enums"]

    def test_expression_value(self):
        content = "localparam Total = SizeX * SizeY;"
        result = extract_package_params(content)
        assert result["localparams"]["Total"] == "SizeX * SizeY"


# ---------------------------------------------------------------------------
# identify_chip_config tests
# ---------------------------------------------------------------------------

class TestIdentifyChipConfig:
    def test_empty_input(self):
        result = identify_chip_config({})
        assert result == {"chip_params": {}, "grid_size": {}}

    def test_none_input(self):
        result = identify_chip_config(None)
        assert result == {"chip_params": {}, "grid_size": {}}

    def test_identifies_sizex_sizey(self):
        params = {
            "localparams": {"SizeX": "4", "SizeY": "5"},
            "parameters": {},
            "enums": {},
        }
        result = identify_chip_config(params)
        assert "SizeX" in result["chip_params"]
        assert "SizeY" in result["chip_params"]
        assert result["grid_size"]["x"] == "4"
        assert result["grid_size"]["y"] == "5"

    def test_identifies_numtensix(self):
        params = {
            "localparams": {"NumTensix": "12"},
            "parameters": {},
            "enums": {},
        }
        result = identify_chip_config(params)
        assert "NumTensix" in result["chip_params"]
        assert result["chip_params"]["NumTensix"]["value"] == "12"
        assert result["chip_params"]["NumTensix"]["type"] == "localparam"

    def test_ignores_non_chip_params(self):
        params = {
            "localparams": {"RandomParam": "42"},
            "parameters": {},
            "enums": {},
        }
        result = identify_chip_config(params)
        assert len(result["chip_params"]) == 0


# ---------------------------------------------------------------------------
# extract_enum_mapping tests
# ---------------------------------------------------------------------------

class TestExtractEnumMapping:
    def test_empty_input(self):
        result = extract_enum_mapping("")
        assert result == {}

    def test_none_input(self):
        result = extract_enum_mapping(None)
        assert result == {}

    def test_simple_enum_with_values(self):
        content = """
        typedef enum logic [2:0] {
            TENSIX = 0,
            NOC2AXI = 1,
            DISPATCH = 2
        } tile_type_t;
        """
        result = extract_enum_mapping(content)
        assert "tile_type_t" in result
        assert result["tile_type_t"]["TENSIX"] == "0"
        assert result["tile_type_t"]["NOC2AXI"] == "1"

    def test_enum_auto_increment(self):
        content = """
        typedef enum {
            IDLE,
            ACTIVE,
            DONE
        } state_t;
        """
        result = extract_enum_mapping(content)
        assert "state_t" in result
        assert result["state_t"]["IDLE"] == 0
        assert result["state_t"]["ACTIVE"] == 1
        assert result["state_t"]["DONE"] == 2

    def test_enum_mixed_assignment(self):
        content = """
        typedef enum {
            A = 5,
            B,
            C = 10
        } mixed_t;
        """
        result = extract_enum_mapping(content)
        assert result["mixed_t"]["A"] == "5"
        assert result["mixed_t"]["B"] == 6
        assert result["mixed_t"]["C"] == "10"

    def test_multiple_enums(self):
        content = """
        typedef enum { X, Y } coord_t;
        typedef enum { R, G, B } color_t;
        """
        result = extract_enum_mapping(content)
        assert "coord_t" in result
        assert "color_t" in result
