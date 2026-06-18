from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import yaml

from isa import (
    DATA_WORD,
    HEADER,
    INPUT_PORT,
    MAGIC,
    NO_INTERRUPT,
    OUTPUT_PORT,
    READY_PORT,
    VECTOR_WIDTH,
    WORD,
    Instruction,
    Op,
    decode_word,
    signed24,
    to_word,
    unpack_v_mem,
    unpack_vv,
)


@dataclass
class Program:
    entry: int
    interrupt: int
    code: list[int]
    data: list[int]


def load_program(path: Path) -> Program:
    content = path.read_bytes()
    magic, entry, interrupt, code_len, data_len = HEADER.unpack_from(content, 0)
    if magic != MAGIC:
        raise ValueError("bad binary magic")
    offset = HEADER.size
    code = []
    for _ in range(code_len):
        code.append(WORD.unpack_from(content, offset)[0])
        offset += WORD.size
    data = []
    for _ in range(data_len):
        data.append(DATA_WORD.unpack_from(content, offset)[0])
        offset += DATA_WORD.size
    return Program(entry, interrupt, code, data)


def read_schedule(path: Path | None) -> list[tuple[int, int]]:
    if path is None:
        return []
    if path.suffix not in {".yaml", ".yml"}:
        raise ValueError(f"input schedule must be YAML: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"bad input schedule: {path}")
    schedule = []
    for item in raw:
        if not isinstance(item, dict) or "tick" not in item or "value" not in item:
            raise ValueError(f"bad input schedule: {path}")
        tick = item["tick"]
        value = item["value"]
        if isinstance(value, str):
            if len(value) != 1:
                raise ValueError(f"input token must be one char: {value!r}")
            token = ord(value)
        else:
            token = int(value)
        schedule.append((int(tick), token))
    return sorted(schedule)


class Machine:
    def __init__(self, program: Program, schedule: list[tuple[int, int]] | None = None, trace_limit: int = 2000):
        self.code = program.code
        self.data = program.data[:]
        self.pc = program.entry
        self.interrupt_vector = program.interrupt
        self.acc = 0
        self.zero = False
        self.negative = False
        self.running = True
        self.ticks = 0
        self.interrupts_enabled = False
        self.in_interrupt = False
        self.call_stack: list[int] = []
        self.interrupt_stack: list[int] = []
        self.vector = [[0] * VECTOR_WIDTH for _ in range(16)]
        self.output: list[str] = []
        self.trace: list[str] = []
        self.trace_limit = trace_limit
        self._trace_truncated = False
        self.schedule = list(schedule or [])
        self.input_port: int | None = None
        self.pending_interrupt = False

    def run(self, max_ticks: int = 1_000_000) -> str:
        while self.running and self.ticks < max_ticks:
            self.enter_interrupt_if_needed()
            self.step()
        if self.ticks >= max_ticks:
            raise RuntimeError(f"tick limit exceeded: {max_ticks}")
        return "".join(self.output)

    def tick(self, stage: str, message: str) -> None:
        self.ticks += 1
        self.load_input_events()
        if len(self.trace) < self.trace_limit:
            self.trace.append(
                f"{self.ticks:06d} | {stage:<5} | pc={self.pc:04d} acc={self.acc:<11d} "
                f"z={int(self.zero)} n={int(self.negative)} irq={int(self.in_interrupt)} | {message}"
            )
        elif not self._trace_truncated:
            self.trace.append("... trace truncated ...")
            self._trace_truncated = True

    def load_input_events(self) -> None:
        while self.schedule and self.schedule[0][0] <= self.ticks and self.input_port is None:
            _, token = self.schedule.pop(0)
            self.input_port = token
            self.pending_interrupt = True

    def enter_interrupt_if_needed(self) -> None:
        if (
            self.pending_interrupt
            and self.interrupts_enabled
            and not self.in_interrupt
            and self.interrupt_vector != NO_INTERRUPT
        ):
            self.interrupt_stack.append(self.pc)
            self.pc = self.interrupt_vector
            self.in_interrupt = True
            self.interrupts_enabled = False
            self.tick("irq", f"enter interrupt -> {self.interrupt_vector}")

    def step(self) -> None:
        if not 0 <= self.pc < len(self.code):
            raise RuntimeError(f"pc out of code memory: {self.pc}")
        word = self.code[self.pc]
        instruction = decode_word(word)
        old_pc = self.pc
        self.pc += 1
        self.tick("fetch", f"{old_pc:04d}: {instruction.op.name.lower()} {instruction.arg}")
        self.execute(instruction)

    def execute(self, instruction: Instruction) -> None:
        op = instruction.op
        arg = instruction.arg
        signed_arg = signed24(arg)

        if op == Op.NOP:
            self.tick("exec", "nop")
        elif op == Op.HALT:
            self.tick("exec", "halt")
            self.running = False
        elif op == Op.LDI:
            self.set_acc(signed_arg)
            self.tick("exec", f"acc <- {self.acc}")
        elif op == Op.LD:
            self.tick("addr", f"data address <- {arg}")
            self.set_acc(self.read_mem(arg))
            self.tick("mem", f"acc <- mem[{arg}]")
        elif op == Op.ST:
            self.tick("addr", f"data address <- {arg}")
            self.write_mem(arg, self.acc)
            self.tick("mem", f"mem[{arg}] <- acc")
        elif op == Op.ADD:
            self.tick("mem", f"operand <- mem[{arg}]")
            self.set_acc(self.acc + self.read_mem(arg))
            self.tick("exec", f"acc += mem[{arg}]")
        elif op == Op.SUB:
            self.tick("mem", f"operand <- mem[{arg}]")
            self.set_acc(self.acc - self.read_mem(arg))
            self.tick("exec", f"acc -= mem[{arg}]")
        elif op == Op.MUL:
            self.tick("mem", f"operand <- mem[{arg}]")
            value = self.read_mem(arg)
            self.set_acc(self.acc * value)
            self.tick("exec", f"acc *= mem[{arg}]")
        elif op == Op.DIV:
            self.tick("mem", f"operand <- mem[{arg}]")
            value = self.read_mem(arg)
            self.set_acc(self.div(self.acc, value))
            self.tick("exec", f"acc /= mem[{arg}]")
        elif op == Op.MOD:
            self.tick("mem", f"operand <- mem[{arg}]")
            value = self.read_mem(arg)
            self.set_acc(self.acc - self.div(self.acc, value) * value)
            self.tick("exec", f"acc %= mem[{arg}]")
        elif op == Op.ADDI:
            self.set_acc(self.acc + signed_arg)
            self.tick("exec", f"acc += {signed_arg}")
        elif op == Op.SUBI:
            self.set_acc(self.acc - signed_arg)
            self.tick("exec", f"acc -= {signed_arg}")
        elif op == Op.MULI:
            self.set_acc(self.acc * signed_arg)
            self.tick("exec", f"acc *= {signed_arg}")
        elif op == Op.DIVI:
            self.set_acc(self.div(self.acc, signed_arg))
            self.tick("exec", f"acc /= {signed_arg}")
        elif op == Op.MODI:
            self.set_acc(self.acc - self.div(self.acc, signed_arg) * signed_arg)
            self.tick("exec", f"acc %= {signed_arg}")
        elif op == Op.CMP:
            self.tick("mem", f"operand <- mem[{arg}]")
            self.set_flags(self.acc - self.read_mem(arg))
            self.tick("exec", f"cmp acc, mem[{arg}]")
        elif op == Op.CMPI:
            self.set_flags(self.acc - signed_arg)
            self.tick("exec", f"cmp acc, {signed_arg}")
        elif op == Op.JMP:
            self.pc = arg
            self.tick("exec", f"pc <- {arg}")
        elif op == Op.JZ:
            self.jump_if(self.zero, arg, "jz")
        elif op == Op.JNZ:
            self.jump_if(not self.zero, arg, "jnz")
        elif op == Op.JN:
            self.jump_if(self.negative, arg, "jn")
        elif op == Op.JP:
            self.jump_if(not self.negative and not self.zero, arg, "jp")
        elif op == Op.JLE:
            self.jump_if(self.negative or self.zero, arg, "jle")
        elif op == Op.JL:
            self.jump_if(self.negative, arg, "jl")
        elif op == Op.JGE:
            self.jump_if(not self.negative, arg, "jge")
        elif op == Op.JG:
            self.jump_if(not self.negative and not self.zero, arg, "jg")
        elif op == Op.CALL:
            self.call_stack.append(self.pc)
            self.pc = arg
            self.tick("exec", f"call {arg}")
        elif op == Op.RET:
            self.pc = self.call_stack.pop()
            self.tick("exec", "ret")
        elif op == Op.IRET:
            self.pc = self.interrupt_stack.pop()
            self.in_interrupt = False
            self.interrupts_enabled = True
            self.tick("exec", "iret")
        elif op == Op.EI:
            self.interrupts_enabled = True
            self.tick("exec", "interrupts enabled")
        elif op == Op.DI:
            self.interrupts_enabled = False
            self.tick("exec", "interrupts disabled")
        elif op == Op.LEA:
            self.set_acc(arg)
            self.tick("exec", f"acc <- address {arg}")
        elif op == Op.LDX:
            self.tick("addr", f"ptr address <- {arg}")
            address = self.read_mem(arg)
            self.tick("mem", f"address <- mem[{arg}]")
            self.set_acc(self.read_mem(address))
            self.tick("mem", f"acc <- mem[{address}]")
        elif op == Op.STX:
            self.tick("addr", f"ptr address <- {arg}")
            address = self.read_mem(arg)
            self.tick("mem", f"address <- mem[{arg}]")
            self.write_mem(address, self.acc)
            self.tick("mem", f"mem[{address}] <- acc")
        elif op in {Op.VLD, Op.VST}:
            self.execute_vector_mem(op, arg)
        elif op in {Op.VADD, Op.VSUB, Op.VMUL, Op.VDIV, Op.VCMPGT}:
            self.execute_vector_alu(op, arg)
        else:
            raise RuntimeError(f"unsupported opcode: {op}")

    def execute_vector_mem(self, op: Op, arg: int) -> None:
        reg, address = unpack_v_mem(arg)
        if op == Op.VLD:
            values = []
            for lane in range(VECTOR_WIDTH):
                lane_address = address + lane
                values.append(self.read_mem(lane_address))
                self.tick("mem", f"v{reg}[{lane}] <- mem[{lane_address}]")
            self.vector[reg] = values
            self.tick("vexec", f"v{reg} <- mem[{address}..{address + VECTOR_WIDTH - 1}]")
        else:
            for lane, value in enumerate(self.vector[reg]):
                lane_address = address + lane
                self.write_mem(lane_address, value)
                self.tick("mem", f"mem[{lane_address}] <- v{reg}[{lane}]")
            self.tick("vexec", f"mem[{address}..{address + VECTOR_WIDTH - 1}] <- v{reg}")

    def execute_vector_alu(self, op: Op, arg: int) -> None:
        dst, src = unpack_vv(arg)
        left = self.vector[dst]
        right = self.vector[src]
        if op == Op.VADD:
            self.vector[dst] = [to_word(a + b) for a, b in zip(left, right, strict=True)]
            text = f"v{dst} += v{src}"
        elif op == Op.VSUB:
            self.vector[dst] = [to_word(a - b) for a, b in zip(left, right, strict=True)]
            text = f"v{dst} -= v{src}"
        elif op == Op.VMUL:
            self.vector[dst] = [to_word(a * b) for a, b in zip(left, right, strict=True)]
            text = f"v{dst} *= v{src}"
        elif op == Op.VDIV:
            self.vector[dst] = [self.div(a, b) for a, b in zip(left, right, strict=True)]
            text = f"v{dst} /= v{src}"
        else:
            self.vector[dst] = [1 if a > b else 0 for a, b in zip(left, right, strict=True)]
            text = f"v{dst} = v{dst} > v{src}"
        self.tick("exec", f"vector operands v{dst}, v{src}")
        self.tick("vexec", text)

    def jump_if(self, condition: bool, target: int, name: str) -> None:
        if condition:
            self.pc = target
        self.tick("exec", f"{name} {'taken' if condition else 'skip'}")

    def read_mem(self, address: int) -> int:
        if address == INPUT_PORT:
            value = self.input_port or 0
            self.input_port = None
            self.pending_interrupt = False
            return value
        if address == READY_PORT:
            return 1 if self.input_port is not None else 0
        if not 0 <= address < len(self.data):
            raise RuntimeError(f"data address out of range: {address}")
        return self.data[address]

    def write_mem(self, address: int, value: int) -> None:
        value = to_word(value)
        if address == OUTPUT_PORT:
            self.output.append(chr(value & 0xFF))
            return
        if address in {INPUT_PORT, READY_PORT}:
            return
        if not 0 <= address < len(self.data):
            raise RuntimeError(f"data address out of range: {address}")
        self.data[address] = value

    def set_acc(self, value: int) -> None:
        self.acc = to_word(value)
        self.set_flags(self.acc)

    def set_flags(self, value: int) -> None:
        value = to_word(value)
        self.zero = value == 0
        self.negative = value < 0

    @staticmethod
    def div(left: int, right: int) -> int:
        if right == 0:
            raise ZeroDivisionError("division by zero in simulated program")
        return to_word(int(left / right))


def run_program(
    image_path: Path,
    input_path: Path | None = None,
    trace_limit: int = 2000,
    max_ticks: int = 1_000_000,
) -> tuple[str, str, int]:
    program = load_program(image_path)
    machine = Machine(program, read_schedule(input_path), trace_limit)
    output = machine.run(max_ticks=max_ticks)
    return output, "\n".join(machine.trace) + "\n", machine.ticks


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CSA lab4 binary image.")
    parser.add_argument("image", type=Path)
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--trace-limit", type=int, default=2000)
    parser.add_argument("--max-ticks", type=int, default=1_000_000)
    args = parser.parse_args()

    output, trace, ticks = run_program(args.image, args.input, args.trace_limit, args.max_ticks)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.trace:
        args.trace.write_text(trace + f"ticks={ticks}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
