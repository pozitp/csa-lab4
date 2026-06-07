from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from machine import read_schedule, run_program
from translator import translate, write_image

ROOT = Path(__file__).resolve().parent
GOLDEN = ROOT / "golden"


def read_meta(path: Path) -> dict[str, int | str]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_output_yaml(path: Path) -> str:
    output = yaml.safe_load(path.read_text(encoding="utf-8")).get("output")
    if not isinstance(output, str):
        raise ValueError(f"bad output YAML: {path}")
    return output


def read_trace_yaml(path: Path) -> str:
    trace = yaml.safe_load(path.read_text(encoding="utf-8")).get("trace")
    if not isinstance(trace, str):
        raise ValueError(f"bad trace YAML: {path}")
    return trace


def read_listing_yaml(path: Path) -> str:
    listing = yaml.safe_load(path.read_text(encoding="utf-8")).get("listing")
    if not isinstance(listing, str):
        raise ValueError(f"bad listing YAML: {path}")
    return listing


def read_machine_code_yaml(path: Path) -> bytes:
    machine_code = yaml.safe_load(path.read_text(encoding="utf-8")).get("machine_code")
    if not isinstance(machine_code, bytes):
        raise ValueError(f"bad machine code YAML: {path}")
    return machine_code


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
        for case_dir in sorted(path for path in GOLDEN.iterdir() if path.is_dir()):
            with self.subTest(case=case_dir.name):
                self.check_case(case_dir)

    def run_source_ticks(self, source: str) -> int:
        image = translate(source)
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "program.bin"
            write_image(image, image_path)
            _, _, ticks = run_program(image_path)
        return ticks

    def check_case(self, case_dir: Path) -> None:
        source = (case_dir / "source.asm").read_text(encoding="utf-8")
        expected_listing = (case_dir / "program.lst").read_text(encoding="utf-8")
        expected_binary = (case_dir / "program.bin").read_bytes()
        expected_output = (case_dir / "output.txt").read_text(encoding="utf-8")
        expected_output_yaml = read_output_yaml(case_dir / "output.yaml")
        expected_listing_yaml = read_listing_yaml(case_dir / "output.yaml")
        expected_trace = (case_dir / "trace.txt").read_text(encoding="utf-8")
        expected_trace_yaml = read_trace_yaml(case_dir / "output.yaml")
        expected_binary_yaml = read_machine_code_yaml(case_dir / "output.yaml")
        meta = read_meta(case_dir / "meta.yaml")

        image = translate(source)
        self.assertEqual(expected_listing, image.listing)
        self.assertEqual(expected_listing, expected_listing_yaml)

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "program.bin"
            write_image(image, image_path)
            self.assertEqual(expected_binary, image_path.read_bytes())
            output, trace, ticks = run_program(
                image_path,
                case_dir / "input.yaml",
                trace_limit=meta["trace_limit"],
                max_ticks=meta["max_ticks"],
            )

        self.assertEqual(meta["ticks"], ticks)
        self.assertEqual(expected_output, expected_output_yaml)
        self.assertEqual(expected_output, output)
        self.assertEqual(expected_trace, expected_trace_yaml)
        self.assertEqual(expected_binary, expected_binary_yaml)
        self.assertEqual(expected_trace, trace + f"ticks={ticks}\n")


if __name__ == "__main__":
    unittest.main()
