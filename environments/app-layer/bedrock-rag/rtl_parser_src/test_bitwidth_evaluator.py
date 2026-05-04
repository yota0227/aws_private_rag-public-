"""Unit tests for Bitwidth Evaluator (task 17.1).

Tests SafeIntEvaluator class and evaluate_bitwidth() function for
safe integer arithmetic parsing of SystemVerilog bitwidth expressions.

Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6
"""

import unittest
from bitwidth_evaluator import (
    SafeIntEvaluator,
    evaluate_bitwidth,
    _clog2,
    _preprocess_expr,
    _validate_input,
)


class TestClog2(unittest.TestCase):
    """Test the _clog2 helper function."""

    def test_power_of_two(self):
        self.assertEqual(_clog2(1), 0)
        self.assertEqual(_clog2(2), 1)
        self.assertEqual(_clog2(4), 2)
        self.assertEqual(_clog2(8), 3)
        self.assertEqual(_clog2(16), 4)
        self.assertEqual(_clog2(1024), 10)

    def test_non_power_of_two(self):
        self.assertEqual(_clog2(3), 2)
        self.assertEqual(_clog2(5), 3)
        self.assertEqual(_clog2(12), 4)
        self.assertEqual(_clog2(100), 7)

    def test_zero_raises(self):
        with self.assertRaises(ValueError):
            _clog2(0)

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            _clog2(-1)


class TestPreprocessExpr(unittest.TestCase):
    """Test _preprocess_expr helper."""

    def test_clog2_replacement(self):
        self.assertEqual(_preprocess_expr("$clog2(SizeX)"), "clog2(SizeX)")

    def test_whitespace_strip(self):
        self.assertEqual(_preprocess_expr("  SizeX - 1  "), "SizeX - 1")

    def test_no_change_needed(self):
        self.assertEqual(_preprocess_expr("A+B"), "A+B")

    def test_nested_clog2(self):
        self.assertEqual(
            _preprocess_expr("$clog2($clog2(N))"),
            "clog2(clog2(N))",
        )


class TestValidateInput(unittest.TestCase):
    """Test _validate_input rejects dangerous patterns."""

    def test_import_rejected(self):
        with self.assertRaises(ValueError):
            _validate_input("__import__('os')")

    def test_exec_rejected(self):
        with self.assertRaises(ValueError):
            _validate_input("exec('print(1)')")

    def test_eval_rejected(self):
        with self.assertRaises(ValueError):
            _validate_input("eval('1+1')")

    def test_os_system_rejected(self):
        with self.assertRaises(ValueError):
            _validate_input("os.system('rm -rf /')")

    def test_safe_input_passes(self):
        # Should not raise
        _validate_input("SizeX - 1")
        _validate_input("$clog2(NumTensix)")
        _validate_input("A * B + C")


class TestEvaluateBitwidthSimpleArithmetic(unittest.TestCase):
    """Test evaluate_bitwidth with simple arithmetic expressions."""

    def test_integer_literal(self):
        self.assertEqual(evaluate_bitwidth("42", {}), 42)

    def test_addition(self):
        self.assertEqual(evaluate_bitwidth("3+4", {}), 7)

    def test_subtraction(self):
        self.assertEqual(evaluate_bitwidth("10-3", {}), 7)

    def test_multiplication(self):
        self.assertEqual(evaluate_bitwidth("6*7", {}), 42)

    def test_integer_division(self):
        self.assertEqual(evaluate_bitwidth("10/3", {}), 3)

    def test_complex_arithmetic(self):
        self.assertEqual(evaluate_bitwidth("2+3*4", {}), 14)

    def test_unary_minus(self):
        self.assertEqual(evaluate_bitwidth("-5", {}), -5)

    def test_parenthesized(self):
        self.assertEqual(evaluate_bitwidth("(2+3)*4", {}), 20)


class TestEvaluateBitwidthWithParameters(unittest.TestCase):
    """Test evaluate_bitwidth with parameter resolution."""

    def test_single_param_subtraction(self):
        # evaluate_bitwidth("SizeX-1", {"SizeX": 4}) → 3
        self.assertEqual(evaluate_bitwidth("SizeX-1", {"SizeX": 4}), 3)

    def test_two_param_multiplication(self):
        # evaluate_bitwidth("SizeX*SizeY", {"SizeX": 4, "SizeY": 5}) → 20
        self.assertEqual(
            evaluate_bitwidth("SizeX*SizeY", {"SizeX": 4, "SizeY": 5}), 20
        )

    def test_complex_expression(self):
        # evaluate_bitwidth("SizeX*SizeY-1", {"SizeX": 4, "SizeY": 5}) → 19
        self.assertEqual(
            evaluate_bitwidth("SizeX*SizeY-1", {"SizeX": 4, "SizeY": 5}), 19
        )

    def test_param_with_clog2(self):
        # evaluate_bitwidth("$clog2(SizeX)", {"SizeX": 4}) → 2
        self.assertEqual(evaluate_bitwidth("$clog2(SizeX)", {"SizeX": 4}), 2)

    def test_clog2_non_power_of_two(self):
        # evaluate_bitwidth("$clog2(NumTensix)", {"NumTensix": 12}) → 4
        self.assertEqual(
            evaluate_bitwidth("$clog2(NumTensix)", {"NumTensix": 12}), 4
        )

    def test_clog2_of_one(self):
        self.assertEqual(evaluate_bitwidth("$clog2(N)", {"N": 1}), 0)

    def test_param_addition(self):
        self.assertEqual(
            evaluate_bitwidth("A+B", {"A": 10, "B": 20}), 30
        )

    def test_string_param_value(self):
        """String param values that look like integers should be converted."""
        self.assertEqual(evaluate_bitwidth("X-1", {"X": "8"}), 7)


class TestEvaluateBitwidthUnresolvable(unittest.TestCase):
    """Test evaluate_bitwidth with unresolvable parameters."""

    def test_unknown_param_returns_original(self):
        # evaluate_bitwidth("UNKNOWN-1", {}) → "UNKNOWN-1"
        result = evaluate_bitwidth("UNKNOWN-1", {})
        self.assertEqual(result, "UNKNOWN-1")
        self.assertIsInstance(result, str)

    def test_partial_resolution_returns_original(self):
        result = evaluate_bitwidth("SizeX+UNKNOWN", {"SizeX": 4})
        self.assertEqual(result, "SizeX+UNKNOWN")
        self.assertIsInstance(result, str)

    def test_empty_context_returns_original(self):
        result = evaluate_bitwidth("WIDTH", {})
        self.assertEqual(result, "WIDTH")

    def test_none_context_returns_original(self):
        result = evaluate_bitwidth("WIDTH", None)
        self.assertEqual(result, "WIDTH")


class TestEvaluateBitwidthMalicious(unittest.TestCase):
    """Test evaluate_bitwidth rejects malicious inputs (Req 22.6)."""

    def test_import_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("__import__('os').system('rm -rf /')", {})

    def test_exec_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("exec('print(1)')", {})

    def test_eval_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("eval('1+1')", {})

    def test_lambda_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("lambda x: x", {})

    def test_attribute_access_raises(self):
        """Attribute access like os.path should be rejected at AST level."""
        with self.assertRaises(ValueError):
            evaluate_bitwidth("os.system", {})

    def test_list_comprehension_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("[x for x in range(10)]", {})

    def test_string_literal_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("'hello'", {})

    def test_float_literal_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("3.14", {})

    def test_subprocess_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("subprocess.run('ls')", {})


class TestEvaluateBitwidthEdgeCases(unittest.TestCase):
    """Test edge cases for evaluate_bitwidth."""

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("", {})

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("   ", {})

    def test_non_string_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth(123, {})

    def test_division_by_zero_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("10/0", {})

    def test_clog2_zero_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("$clog2(0)", {})

    def test_clog2_negative_raises(self):
        with self.assertRaises(ValueError):
            evaluate_bitwidth("$clog2(N)", {"N": -1})

    def test_whitespace_preserved_in_original(self):
        """Whitespace is stripped from the returned original expression."""
        result = evaluate_bitwidth("  UNKNOWN - 1  ", {})
        self.assertEqual(result, "UNKNOWN - 1")

    def test_large_numbers(self):
        self.assertEqual(evaluate_bitwidth("1024*1024", {}), 1048576)

    def test_nested_clog2(self):
        # $clog2($clog2(256)) = $clog2(8) = 3
        self.assertEqual(evaluate_bitwidth("$clog2($clog2(N))", {"N": 256}), 3)

    def test_clog2_with_arithmetic(self):
        # $clog2(SizeX) - 1 where SizeX=8 → clog2(8)-1 = 3-1 = 2
        self.assertEqual(
            evaluate_bitwidth("$clog2(SizeX)-1", {"SizeX": 8}), 2
        )


class TestSafeIntEvaluatorDirectly(unittest.TestCase):
    """Test SafeIntEvaluator class directly for coverage."""

    def test_unsupported_binary_op(self):
        """Modulo and other ops should be rejected."""
        import ast as ast_mod
        evaluator = SafeIntEvaluator({})
        tree = ast_mod.parse("5 % 3", mode="eval")
        with self.assertRaises(ValueError):
            evaluator.visit(tree)

    def test_unsupported_unary_op(self):
        """Bitwise NOT should be rejected."""
        import ast as ast_mod
        evaluator = SafeIntEvaluator({})
        tree = ast_mod.parse("~5", mode="eval")
        with self.assertRaises(ValueError):
            evaluator.visit(tree)

    def test_unsupported_function(self):
        """Functions other than clog2 should be rejected."""
        import ast as ast_mod
        evaluator = SafeIntEvaluator({})
        tree = ast_mod.parse("print(1)", mode="eval")
        with self.assertRaises(ValueError):
            evaluator.visit(tree)

    def test_clog2_wrong_arg_count(self):
        """$clog2 with wrong number of args should be rejected."""
        import ast as ast_mod
        evaluator = SafeIntEvaluator({})
        tree = ast_mod.parse("clog2(1, 2)", mode="eval")
        with self.assertRaises(ValueError):
            evaluator.visit(tree)


if __name__ == "__main__":
    unittest.main()
