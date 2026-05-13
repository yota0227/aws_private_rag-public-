"""Unit tests for Package Function/Task Extractor (task 14.1).

Tests _extract_functions(), _extract_tasks(), and helper functions
added to package_extractor.py for v7 Phase 7.
"""

import unittest
from package_extractor import (
    extract_package_constants,
    _extract_functions,
    _extract_tasks,
    _parse_function_args,
    _parse_task_args,
    _extract_function_body,
    _summarize_body,
)


class TestExtractFunctions(unittest.TestCase):
    """Test _extract_functions() with various SystemVerilog patterns."""

    def test_basic_function(self):
        """Simple function with typed arguments and return type."""
        sv = """
package test_pkg;
    function int getTensixIndex(int x, int y);
        return y * SizeX + x;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertIn("getTensixIndex", claim["claim_text"])
        self.assertIn("int x", claim["claim_text"])
        self.assertIn("int y", claim["claim_text"])
        self.assertIn("→ int", claim["claim_text"])
        self.assertEqual(claim["parser_source"], "package_function_extractor")
        self.assertEqual(claim["analysis_type"], "claim")
        self.assertEqual(claim["topic"], "PackageFunction")

    def test_void_return_type(self):
        """Function with void return type."""
        sv = """
package test_pkg;
    function void initConfig(int addr);
        config[addr] = 0;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("→ void", claims[0]["claim_text"])

    def test_automatic_qualifier(self):
        """Function with automatic qualifier."""
        sv = """
package test_pkg;
    automatic function int compute(int a, int b);
        return a + b;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("[automatic]", claims[0]["claim_text"])

    def test_static_qualifier(self):
        """Function with static qualifier."""
        sv = """
package test_pkg;
    static function logic isValid(logic [7:0] data);
        return data != 0;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("[static]", claims[0]["claim_text"])

    def test_no_arguments(self):
        """Function with no arguments."""
        sv = """
package test_pkg;
    function int getDefaultSize();
        return 4;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("getDefaultSize()", claims[0]["claim_text"])
        self.assertIn("→ int", claims[0]["claim_text"])

    def test_multiple_functions(self):
        """Multiple functions in one package."""
        sv = """
package noc_pkg;
    function int getX(int idx);
        return idx % SizeX;
    endfunction

    function int getY(int idx);
        return idx / SizeX;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "noc_pkg", "noc_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 2)
        names = [c["claim_text"] for c in claims]
        self.assertTrue(any("getX" in n for n in names))
        self.assertTrue(any("getY" in n for n in names))

    def test_body_summary_short_function(self):
        """Short function body gets a summary."""
        sv = """
package test_pkg;
    function int calcIndex(int x, int y);
        return y * SizeX + x;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("Summary:", claims[0]["claim_text"])
        self.assertIn("returns", claims[0]["claim_text"])

    def test_body_summary_with_loop(self):
        """Function with loop gets loop count in summary."""
        sv = """
package test_pkg;
    function int sumArray(int arr);
        int total;
        total = 0;
        for (int i = 0; i < 10; i++) begin
            total = total + i;
        end
        return total;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("Summary:", claims[0]["claim_text"])
        self.assertIn("loop", claims[0]["claim_text"])

    def test_body_summary_with_conditional(self):
        """Function with conditional gets conditional count in summary."""
        sv = """
package test_pkg;
    function int maxVal(int a, int b);
        if (a > b)
            return a;
        else
            return b;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("Summary:", claims[0]["claim_text"])
        self.assertIn("conditional", claims[0]["claim_text"])

    def test_skip_function_inside_module(self):
        """Functions inside module bodies should be skipped."""
        sv = """
package test_pkg;
    function int pkgFunc(int x);
        return x;
    endfunction
endpackage

module my_module;
    function int moduleFunc(int y);
        return y;
    endfunction
endmodule
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("pkgFunc", claims[0]["claim_text"])

    def test_no_functions(self):
        """Package with no functions returns empty list."""
        sv = """
package test_pkg;
    localparam int SIZE = 4;
endpackage
"""
        claims = _extract_functions(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 0)

    def test_claim_text_roundtrip_format(self):
        """Verify claim_text format allows roundtrip parsing (Req 17.6)."""
        sv = """
package noc_pkg;
    function int getNoc2AxiIndex(int tile_x, int tile_y);
        return tile_y * SizeX + tile_x;
    endfunction
endpackage
"""
        claims = _extract_functions(sv, "noc_pkg", "noc_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        text = claims[0]["claim_text"]
        # Verify format: Package 'X' defines function 'name(args) → type'
        self.assertIn("Package 'noc_pkg' defines function '", text)
        self.assertIn("getNoc2AxiIndex(", text)
        self.assertIn("→ int", text)


class TestExtractTasks(unittest.TestCase):
    """Test _extract_tasks() with various SystemVerilog patterns."""

    def test_basic_task(self):
        """Simple task with input/output arguments."""
        sv = """
package test_pkg;
    task sendPacket(input logic [7:0] data, output logic done);
        // task body
        done = 1;
    endtask
endpackage
"""
        claims = _extract_tasks(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertIn("sendPacket", claim["claim_text"])
        self.assertIn("input", claim["claim_text"])
        self.assertIn("output", claim["claim_text"])
        self.assertEqual(claim["parser_source"], "package_function_extractor")
        self.assertEqual(claim["topic"], "PackageFunction")

    def test_task_no_arguments(self):
        """Task with no arguments."""
        sv = """
package test_pkg;
    task resetAll();
        // reset logic
    endtask
endpackage
"""
        claims = _extract_tasks(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("resetAll()", claims[0]["claim_text"])

    def test_task_automatic_qualifier(self):
        """Task with automatic qualifier."""
        sv = """
package test_pkg;
    automatic task waitCycles(input int count);
        // wait
    endtask
endpackage
"""
        claims = _extract_tasks(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("[automatic]", claims[0]["claim_text"])

    def test_skip_task_inside_module(self):
        """Tasks inside module bodies should be skipped."""
        sv = """
package test_pkg;
    task pkgTask(input int x);
    endtask
endpackage

module my_module;
    task moduleTask(input int y);
    endtask
endmodule
"""
        claims = _extract_tasks(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 1)
        self.assertIn("pkgTask", claims[0]["claim_text"])

    def test_no_tasks(self):
        """Package with no tasks returns empty list."""
        sv = """
package test_pkg;
    localparam int SIZE = 4;
endpackage
"""
        claims = _extract_tasks(sv, "test_pkg", "test_pkg.sv", "pipe1")
        self.assertEqual(len(claims), 0)


class TestParseFunctionArgs(unittest.TestCase):
    """Test _parse_function_args() helper."""

    def test_typed_args(self):
        args = _parse_function_args("int x, int y")
        self.assertEqual(len(args), 2)
        self.assertEqual(args[0], {"name": "x", "type": "int"})
        self.assertEqual(args[1], {"name": "y", "type": "int"})

    def test_mixed_types(self):
        args = _parse_function_args("logic [7:0] data, int count")
        self.assertEqual(len(args), 2)
        self.assertEqual(args[0]["name"], "data")
        self.assertEqual(args[1]["name"], "count")
        self.assertEqual(args[1]["type"], "int")

    def test_empty_args(self):
        args = _parse_function_args("")
        self.assertEqual(args, [])

    def test_single_arg(self):
        args = _parse_function_args("int value")
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0], {"name": "value", "type": "int"})


class TestParseTaskArgs(unittest.TestCase):
    """Test _parse_task_args() helper."""

    def test_directed_args(self):
        args = _parse_task_args("input logic [7:0] data, output logic done")
        self.assertEqual(len(args), 2)
        self.assertEqual(args[0]["direction"], "input")
        self.assertEqual(args[0]["name"], "data")
        self.assertEqual(args[1]["direction"], "output")
        self.assertEqual(args[1]["name"], "done")

    def test_empty_args(self):
        args = _parse_task_args("")
        self.assertEqual(args, [])

    def test_default_direction(self):
        """Without explicit direction, default is input."""
        args = _parse_task_args("int value")
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0]["direction"], "input")


class TestSummarizeBody(unittest.TestCase):
    """Test _summarize_body() helper."""

    def test_return_expression(self):
        summary = _summarize_body("return y * SizeX + x;")
        self.assertIn("returns", summary)

    def test_loop_detection(self):
        summary = _summarize_body("for (int i = 0; i < 10; i++) begin\n  total = total + i;\nend")
        self.assertIn("loop", summary)

    def test_conditional_detection(self):
        summary = _summarize_body("if (a > b) return a;\nelse return b;")
        self.assertIn("conditional", summary)

    def test_empty_body(self):
        summary = _summarize_body("")
        self.assertEqual(summary, "")


class TestIntegration(unittest.TestCase):
    """Integration test: extract_package_constants includes function/task claims."""

    def test_full_package_extraction(self):
        """Verify function/task claims are included in extract_package_constants output."""
        sv = """
package noc_pkg;
    localparam int SizeX = 4;
    localparam int SizeY = 4;

    function int getTensixIndex(int x, int y);
        return y * SizeX + x;
    endfunction

    task sendFlit(input logic [63:0] flit_data, output logic ack);
        // send logic
        ack = 1;
    endtask
endpackage
"""
        claims = extract_package_constants(sv, file_path="noc_pkg.sv", pipeline_id="pipe1")

        # Should have localparam claims + function claim + task claim
        func_claims = [c for c in claims if "defines function" in c.get("claim_text", "")]
        task_claims = [c for c in claims if "defines task" in c.get("claim_text", "")]

        self.assertEqual(len(func_claims), 1)
        self.assertEqual(len(task_claims), 1)

        # Verify parser_source on function/task claims
        for c in func_claims + task_claims:
            self.assertEqual(c["parser_source"], "package_function_extractor")

        # Verify localparam claims still work (backward compatibility)
        param_claims = [c for c in claims if "localparam" in c.get("claim_text", "")]
        self.assertGreater(len(param_claims), 0)

    def test_parser_source_only_on_function_task_claims(self):
        """Existing localparam/enum/struct claims should NOT have parser_source."""
        sv = """
package test_pkg;
    localparam int SIZE = 4;

    typedef enum logic [1:0] {
        IDLE = 0,
        ACTIVE = 1
    } state_t;

    function int getSize();
        return SIZE;
    endfunction
endpackage
"""
        claims = extract_package_constants(sv, file_path="test_pkg.sv", pipeline_id="pipe1")

        for c in claims:
            if "defines function" in c.get("claim_text", ""):
                self.assertEqual(c.get("parser_source"), "package_function_extractor")
            else:
                # Existing claims should not have parser_source set
                # (or it should be empty string)
                self.assertNotEqual(c.get("parser_source", ""), "package_function_extractor")


if __name__ == "__main__":
    unittest.main()
