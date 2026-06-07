from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

MAGIC = b"CSA4"
HEADER = struct.Struct(">4sIIII")
WORD = struct.Struct(">I")
DATA_WORD = struct.Struct(">i")

WORD_MASK = 0xFFFFFFFF
ARG_MASK = 0x00FFFFFF
SIGN24 = 0x00800000
SIGN32 = 0x80000000

INPUT_PORT = 0x00FF00
OUTPUT_PORT = 0x00FF01
READY_PORT = 0x00FF02
NO_INTERRUPT = 0xFFFFFFFF

VECTOR_WIDTH = 4


class Op(IntEnum):
    NOP = 0
    HALT = 1
    LDI = 2
    LD = 3
    ST = 4
    ADD = 5
    SUB = 6
    MUL = 7
    DIV = 8
    MOD = 9
    ADDI = 10
    SUBI = 11
    MULI = 12
    DIVI = 13
    MODI = 14
    CMP = 15
    CMPI = 16
    JMP = 17
    JZ = 18
    JNZ = 19
    JN = 20
    JP = 21
    JLE = 22
    JL = 23
    JGE = 24
    JG = 25
    CALL = 26
    RET = 27
    IRET = 28
    EI = 29
    DI = 30
    LEA = 31
    LDX = 32
    STX = 33
    VLD = 40
    VST = 41
    VADD = 42
    VSUB = 43
    VMUL = 44
    VDIV = 45
    VCMPGT = 46


@dataclass(frozen=True)
class Instruction:
    op: Op
    arg: int = 0


def signed24(value: int) -> int:
    value &= ARG_MASK
    return value - (1 << 24) if value & SIGN24 else value


def signed32(value: int) -> int:
    value &= WORD_MASK
    return value - (1 << 32) if value & SIGN32 else value


def to_word(value: int) -> int:
    return signed32(value)


def encode_arg(value: int) -> int:
    if not -(1 << 23) <= value < (1 << 24):
        raise ValueError(f"argument does not fit into 24 bits: {value}")
    return value & ARG_MASK


def encode_word(op: Op, arg: int = 0) -> int:
    return ((op.value & 0xFF) << 24) | encode_arg(arg)


def decode_word(word: int) -> Instruction:
    return Instruction(Op((word >> 24) & 0xFF), word & ARG_MASK)


def pack_v_mem(reg: int, addr: int) -> int:
    if not 0 <= reg < 16:
        raise ValueError(f"bad vector register: v{reg}")
    if not 0 <= addr < (1 << 20):
        raise ValueError(f"vector memory address does not fit into 20 bits: {addr}")
    return (reg << 20) | addr


def unpack_v_mem(arg: int) -> tuple[int, int]:
    return (arg >> 20) & 0xF, arg & 0xFFFFF


def pack_vv(dst: int, src: int) -> int:
    if not 0 <= dst < 16 or not 0 <= src < 16:
        raise ValueError(f"bad vector registers: v{dst}, v{src}")
    return (dst << 20) | (src << 16)


def unpack_vv(arg: int) -> tuple[int, int]:
    return (arg >> 20) & 0xF, (arg >> 16) & 0xF
