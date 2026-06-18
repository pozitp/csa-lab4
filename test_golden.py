from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from machine import read_schedule, run_program
from translator import translate, write_image

ROOT = Path(__file__).resolve().parent
GOLDEN = ROOT / "golden"


def read_golden(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"bad golden YAML: {path}")
    return data


def get_field(case: dict[str, object], path: Path, key: str, expected_type: type) -> object:
    value = case.get(key)
    if not isinstance(value, expected_type):
        raise ValueError(f"bad {key} in {path}")
    return value


def format_stdout(output: str, ticks: int) -> str:
    return f"{output}\nticks: {ticks}\n"


class GoldenTest(unittest.TestCase):
    def test_unsupported_input_schedule_extension_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.txt"
            input_path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "input schedule must be YAML"):
                read_schedule(input_path)

    def test_bad_input_schedule_yaml_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.yaml"
            input_path.write_text("tick: 1\nvalue: A\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bad input schedule"):
                read_schedule(input_path)

    def test_text_section_is_code_segment(self) -> None:
        source = """
.data
one: .word 1

.text
.entry main
main:
    halt
"""
        self.assertEqual("0000 - 01000000 - halt\n", translate(source).listing)

    def test_scalar_instruction_timing_is_not_flat(self) -> None:
        source = """
.data
x: .word 5
ptr: .word 0

.text
.entry main
main:
    ldi 10
    add x
    muli 2
    st x
    ldx ptr
    halt
"""
        self.assertEqual(17, self.run_source_ticks(source))

    def test_vector_instruction_timing_counts_lane_memory(self) -> None:
        source = """
.data
a: .words 1 2 3 4
b: .words 5 6 7 8

.text
.entry main
main:
    vld v0, a
    vld v1, b
    vadd v0, v1
    vst v0, a
    halt
"""
        self.assertEqual(23, self.run_source_ticks(source))

    def test_golden_cases(self) -> None:
        self.assertTrue(GOLDEN.exists(), "golden directory is missing")
        case_paths = sorted(GOLDEN.glob("*.yml"))
        self.assertTrue(case_paths, "golden/*.yml files are missing")
        for case_path in case_paths:
            with self.subTest(case=case_path.name):
                self.check_case(case_path)

    def run_source_ticks(self, source: str) -> int:
        image = translate(source)
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "program.bin"
            write_image(image, image_path)
            _, _, ticks = run_program(image_path)
        return ticks

    def check_case(self, case_path: Path) -> None:
        case = read_golden(case_path)
        source = get_field(case, case_path, "in_source", str)
        input_schedule = get_field(case, case_path, "in_stdin", str)
        expected_binary = get_field(case, case_path, "out_code", bytes)
        expected_listing = get_field(case, case_path, "out_code_hex", str)
        expected_stdout = get_field(case, case_path, "out_stdout", str)
        expected_trace = get_field(case, case_path, "out_log", str)
        trace_limit = int(case.get("in_trace_limit", 2000))
        max_ticks = int(case.get("in_max_ticks", 1_000_000))

        image = translate(source)
        self.assertEqual(expected_listing, image.listing)

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "program.bin"
            input_path = Path(tmp) / "input.yaml"
            input_path.write_text(input_schedule, encoding="utf-8")
            write_image(image, image_path)
            self.assertEqual(expected_binary, image_path.read_bytes())
            output, trace, ticks = run_program(
                image_path,
                input_path,
                trace_limit=trace_limit,
                max_ticks=max_ticks,
            )

        self.assertEqual(expected_stdout, format_stdout(output, ticks))
        self.assertEqual(expected_trace, trace + f"ticks={ticks}\n")


if __name__ == "__main__":
    unittest.main()
