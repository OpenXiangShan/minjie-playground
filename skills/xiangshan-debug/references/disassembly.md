# PC, ELF, and Disassembly

Use the matching workload ELF and kernel image when mapping a PC. A checkpoint memory image such as
`_memory_.zstd` is not an ELF. See [environment.md](environment.md) for common input layouts.

Before symbolizing, confirm the benchmark/input, build version, compiler options, PIE status and load
bias, address space, and whether the logged PC is virtual, physical, or sign-extended. If the ELF cannot
be matched, report the instruction encoding and dynamic trace without inventing symbols or source lines.

```bash
ELF=/path/to/matching/workload.elf
PC=0x00000000006e5a8c
riscv64-unknown-linux-gnu-objdump -d -S   --start-address=$((PC - 64)) --stop-address=$((PC + 64)) "$ELF"
riscv64-unknown-linux-gnu-addr2line -e "$ELF" -f -C "$PC"
```

Use the toolchain available in the current environment. For PIE binaries, compute the load bias from the
memory map or boot log. RISC-V compressed instructions may be two bytes; use disassembly boundaries or a
commit trace rather than assuming a four-byte predecessor.

To find the producer, distinguish the committed instruction, reference instruction, and consumer that
reported the difference. Trace register, memory, control-flow, and exception state through the stages that
can produce that state.
