import tempfile
from pathlib import Path

import pytest

from machine import read_schedule, run_program
from translator import translate, write_image

def format_stdout(output: str, ticks: int) -> str:
    return f"{output}\nticks: {ticks}\n"

def test_unsupported_input_schedule_extension_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "input.txt"
        input_path.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="input schedule must be YAML"):
            read_schedule(input_path)

def test_bad_input_schedule_yaml_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "input.yaml"
        input_path.write_text("tick: 1\nvalue: A\n", encoding="utf-8")
        with pytest.raises(ValueError, match="bad input schedule"):
            read_schedule(input_path)

def test_text_section_is_code_segment() -> None:
    source = """
.data
one: .word 1

.text
.entry main
main:
    halt
"""
    assert translate(source).listing == "0000 - 01000000 - halt\n"

def run_source_ticks(source: str) -> int:
    image = translate(source)
    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "program.bin"
        write_image(image, image_path)
        _, _, ticks = run_program(image_path)
    return ticks

def test_scalar_instruction_timing_is_not_flat() -> None:
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
    assert run_source_ticks(source) == 16

def test_vector_instruction_timing_counts_lane_memory() -> None:
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
    assert run_source_ticks(source) == 23

@pytest.mark.golden_test("golden/*.yml")
def test_golden_cases(golden) -> None:
    source = golden["in_source"]
    input_schedule = str(golden.get("in_stdin", ""))
    trace_limit = int(golden.get("in_trace_limit", 2000))
    max_ticks = int(golden.get("in_max_ticks", 1_000_000))

    image = translate(source)
    assert image.listing == golden.out["out_code_hex"]

    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "program.bin"
        input_path = Path(tmp) / "input.yaml"
        input_path.write_text(input_schedule, encoding="utf-8")
        write_image(image, image_path)
        
        assert image_path.read_bytes() == golden.out["out_code"]
        
        output, trace, ticks = run_program(
            image_path,
            input_path,
            trace_limit=trace_limit,
            max_ticks=max_ticks,
        )

    assert format_stdout(output, ticks) == golden.out["out_stdout"]
    assert trace + f"ticks={ticks}\n" == golden.out["out_log"]
