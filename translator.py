from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

from isa import (
    DATA_WORD,
    HEADER,
    INPUT_PORT,
    MAGIC,
    NO_INTERRUPT,
    OUTPUT_PORT,
    READY_PORT,
    WORD,
    Op,
    encode_word,
    pack_v_mem,
    pack_vv,
)

LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
CONSTANTS = {"%in": INPUT_PORT, "%out": OUTPUT_PORT, "%ready": READY_PORT}


@dataclass
class DataItem:
    directive: str
    values: list[str] | str | int


@dataclass
class CodeLine:
    address: int
    text: str
    line_no: int


@dataclass
class ProgramImage:
    code: list[int]
    data: list[int]
    listing: str
    entry: int
    interrupt: int


def strip_comment(line: str) -> str:
    quoted = False
    escaped = False
    result = []
    for char in line:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and quoted:
            result.append(char)
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
        if char == ";" and not quoted:
            break
        result.append(char)
    return "".join(result).strip()


def split_args(text: str) -> list[str]:
    return [part for part in re.split(r"[\s,]+", text.strip()) if part]


def parse_string(text: str) -> str:
    value = ast.literal_eval(text.strip())
    if not isinstance(value, str):
        raise ValueError("expected string literal")
    return value


def parse_char(text: str) -> int:
    value = ast.literal_eval(text)
    if not isinstance(value, str) or len(value) != 1:
        raise ValueError(f"bad char literal: {text}")
    return ord(value)


def resolve_value(token: str, data_symbols: dict[str, int], code_symbols: dict[str, int]) -> int:
    token = token.strip()
    lower = token.lower()
    if lower in CONSTANTS:
        return CONSTANTS[lower]
    if token in data_symbols:
        return data_symbols[token]
    if token in code_symbols:
        return code_symbols[token]
    if token.startswith("'") and token.endswith("'"):
        return parse_char(token)
    return int(token, 0)


def parse_vreg(token: str) -> int:
    token = token.lower()
    if not re.fullmatch(r"v\d+", token):
        raise ValueError(f"expected vector register, got {token}")
    return int(token[1:])


def parse_source(
    source: str,
) -> tuple[list[DataItem], list[CodeLine], dict[str, int], dict[str, int], str | None, str | None]:
    section = None
    data_items: list[DataItem] = []
    code_lines: list[CodeLine] = []
    data_symbols: dict[str, int] = {}
    code_symbols: dict[str, int] = {}
    data_address = 0
    code_address = 0
    entry_label: str | None = None
    interrupt_label: str | None = None

    for line_no, raw_line in enumerate(source.splitlines(), start=1):
        line = strip_comment(raw_line)
        if not line:
            continue

        lower = line.lower()
        if lower == ".data":
            section = "data"
            continue
        if lower == ".text":
            section = "text"
            continue

        match = LABEL_RE.match(line)
        if match:
            label = match.group(1)
            if section == "data":
                if label in data_symbols:
                    raise ValueError(f"line {line_no}: duplicate data label {label}")
                data_symbols[label] = data_address
            elif section == "text":
                if label in code_symbols:
                    raise ValueError(f"line {line_no}: duplicate text label {label}")
                code_symbols[label] = code_address
            else:
                raise ValueError(f"line {line_no}: label outside section")
            line = line[match.end() :].strip()
            if not line:
                continue
            lower = line.lower()

        if section == "data":
            directive, _, rest = line.partition(" ")
            directive = directive.lower()
            rest = rest.strip()
            if directive == ".word":
                data_items.append(DataItem(directive, [rest]))
                data_address += 1
            elif directive == ".words":
                values = split_args(rest)
                data_items.append(DataItem(directive, values))
                data_address += len(values)
            elif directive == ".zero":
                count = int(rest, 0)
                data_items.append(DataItem(directive, count))
                data_address += count
            elif directive == ".pstr":
                text = parse_string(rest)
                data_items.append(DataItem(directive, text))
                data_address += len(text) + 1
            else:
                raise ValueError(f"line {line_no}: unknown data directive {directive}")
        elif section == "text":
            if lower.startswith(".entry"):
                entry_label = split_args(line)[1]
                continue
            if lower.startswith(".interrupt"):
                interrupt_label = split_args(line)[1]
                continue
            code_lines.append(CodeLine(code_address, line, line_no))
            code_address += 1
        else:
            raise ValueError(f"line {line_no}: text outside .data/.text section")

    return data_items, code_lines, data_symbols, code_symbols, entry_label, interrupt_label


def build_data(items: list[DataItem], data_symbols: dict[str, int], code_symbols: dict[str, int]) -> list[int]:
    data: list[int] = []
    for item in items:
        if item.directive == ".word":
            assert isinstance(item.values, list)
            data.append(resolve_value(item.values[0], data_symbols, code_symbols))
        elif item.directive == ".words":
            assert isinstance(item.values, list)
            data.extend(resolve_value(value, data_symbols, code_symbols) for value in item.values)
        elif item.directive == ".zero":
            assert isinstance(item.values, int)
            data.extend([0] * int(item.values))
        elif item.directive == ".pstr":
            assert isinstance(item.values, str)
            text = str(item.values)
            data.append(len(text))
            data.extend(ord(char) for char in text)
    return data


def encode_instruction(text: str, data_symbols: dict[str, int], code_symbols: dict[str, int]) -> int:
    parts = split_args(text)
    if not parts:
        raise ValueError("empty instruction")
    mnemonic = parts[0].lower()
    args = parts[1:]

    no_arg = {
        "nop": Op.NOP,
        "halt": Op.HALT,
        "ret": Op.RET,
        "iret": Op.IRET,
        "ei": Op.EI,
        "di": Op.DI,
    }
    one_arg = {
        "ldi": Op.LDI,
        "ld": Op.LD,
        "st": Op.ST,
        "add": Op.ADD,
        "sub": Op.SUB,
        "mul": Op.MUL,
        "div": Op.DIV,
        "mod": Op.MOD,
        "addi": Op.ADDI,
        "subi": Op.SUBI,
        "muli": Op.MULI,
        "divi": Op.DIVI,
        "modi": Op.MODI,
        "cmp": Op.CMP,
        "cmpi": Op.CMPI,
        "jmp": Op.JMP,
        "jz": Op.JZ,
        "jnz": Op.JNZ,
        "jn": Op.JN,
        "jp": Op.JP,
        "jle": Op.JLE,
        "jl": Op.JL,
        "jge": Op.JGE,
        "jg": Op.JG,
        "call": Op.CALL,
        "lea": Op.LEA,
        "ldx": Op.LDX,
        "stx": Op.STX,
    }

    if mnemonic in no_arg:
        if args:
            raise ValueError(f"{mnemonic} takes no arguments")
        return encode_word(no_arg[mnemonic])

    if mnemonic in one_arg:
        if len(args) != 1:
            raise ValueError(f"{mnemonic} takes one argument")
        return encode_word(one_arg[mnemonic], resolve_value(args[0], data_symbols, code_symbols))

    if mnemonic in {"vld", "vst"}:
        if len(args) != 2:
            raise ValueError(f"{mnemonic} takes vreg and address")
        op = Op.VLD if mnemonic == "vld" else Op.VST
        return encode_word(op, pack_v_mem(parse_vreg(args[0]), resolve_value(args[1], data_symbols, code_symbols)))

    if mnemonic in {"vadd", "vsub", "vmul", "vdiv", "vcmpgt"}:
        if len(args) != 2:
            raise ValueError(f"{mnemonic} takes two vector registers")
        op = {
            "vadd": Op.VADD,
            "vsub": Op.VSUB,
            "vmul": Op.VMUL,
            "vdiv": Op.VDIV,
            "vcmpgt": Op.VCMPGT,
        }[mnemonic]
        return encode_word(op, pack_vv(parse_vreg(args[0]), parse_vreg(args[1])))

    raise ValueError(f"unknown instruction: {mnemonic}")


def translate(source: str) -> ProgramImage:
    data_items, code_lines, data_symbols, code_symbols, entry_label, interrupt_label = parse_source(source)
    data = build_data(data_items, data_symbols, code_symbols)
    code = []
    listing_lines = []
    for line in code_lines:
        try:
            word = encode_instruction(line.text, data_symbols, code_symbols)
        except ValueError as exc:
            raise ValueError(f"line {line.line_no}: {exc}") from exc
        code.append(word)
        listing_lines.append(f"{line.address:04d} - {word:08X} - {line.text}")

    if entry_label and entry_label not in code_symbols:
        raise ValueError(f"entry label is not defined: {entry_label}")
    if interrupt_label and interrupt_label not in code_symbols:
        raise ValueError(f"interrupt label is not defined: {interrupt_label}")

    entry = code_symbols[entry_label] if entry_label else 0
    interrupt = code_symbols[interrupt_label] if interrupt_label else NO_INTERRUPT
    return ProgramImage(code, data, "\n".join(listing_lines) + "\n", entry, interrupt)


def write_image(image: ProgramImage, path: Path) -> None:
    with path.open("wb") as file:
        file.write(HEADER.pack(MAGIC, image.entry, image.interrupt, len(image.code), len(image.data)))
        for word in image.code:
            file.write(WORD.pack(word))
        for value in image.data:
            file.write(DATA_WORD.pack(value))


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate CSA lab4 assembly to binary image.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lst", type=Path)
    args = parser.parse_args()

    image = translate(args.source.read_text(encoding="utf-8"))
    write_image(image, args.output)
    if args.lst:
        args.lst.write_text(image.listing, encoding="utf-8")
    else:
        print(image.listing, end="")


if __name__ == "__main__":
    main()
