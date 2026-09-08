# Turbo, explained plainly

Written 2026-09-06 to give a forwards-and-backwards picture of the project
and to answer two questions that keep coming up. Everything here is
measured on the farm or read from the source; where something is a plan, not a
fact, it says so.

## The one-paragraph version

CircuitPython carries MicroPython's machine-code compiler, but every Adafruit
board ships with it switched off, so all Python runs as bytecode. Turbo is a
way to get the speed of that compiler without putting the compiler on the
board. You mark one hot function, a tool on your computer compiles it to
machine code for the board's CPU, and the board just loads and runs the
result. On an integer loop over a buffer that is 20x to 70x faster than the
Python people write today. Everything else is untouched.

## Four words

- **Bytecode.** What CircuitPython does today. Python source is compiled to
  a compact instruction stream and interpreted. Every board, every function.
- **Native** (`@micropython.native`). The same function turned into machine
  code, but values stay Python objects. About 3x faster, on any Python code,
  floats included. Small win, no rewrite.
- **Viper** (`@micropython.viper`). Same compiler, stricter mode: you declare
  ints and pointers, and the loop becomes real machine arithmetic. 20x to 70x
  on the right code. Only for code already written in ints over buffers.
- **Inline assembler** (`@micropython.asm_thumb`). Hand-written ARM assembly
  inside a Python file. Not part of turbo; mentioned because the existing
  build flag drags it along.

The `.mpy` file is the container for any of these. `mpy-cross` on the host can
write bytecode `.mpy` (what the Bundle ships) or machine-code `.mpy` for a
named CPU. The board's loader refuses a machine-code `.mpy` built for the
wrong CPU with a `ValueError`; it never faults.

## MicroPython vs CircuitPython vs CircuitPython + turbo

| | MicroPython | CircuitPython today | CircuitPython + turbo |
|---|---|---|---|
| `@native` / `@viper` in `code.py`, compiled on the board | yes on most ports (rp2, stm32, esp32) | no, `SyntaxError` | no, `SyntaxError` (same as today) |
| load a machine-code `.mpy` from `mpy-cross` | yes | no, "native code in .mpy unsupported" | **yes** |
| `mpy-cross` can produce machine-code `.mpy` | yes | yes already, nothing loads it | yes, turbo's tool drives it |
| flash cost of the feature | 28 to 48 KB (compiler in) | 0 | **2 to 3 KB** (loader only) |
| fits SAMD21 / SAMD51 | not relevant | n/a | yes, both |
| same project runs on a board without the feature | n/a | n/a | yes, from source, via the shim |

"CircuitPython + turbo" here is the loader-only direction chosen for the
project on 2026-09-06. The middle column has three exceptions in the tree, all
third-party boards that set the flag themselves: Winterbloom Sol, and the two
Makerdiary nRF52840 boards. No Adafruit board does.

## The three switches, separately

These are three independent things. Today CircuitPython has one flag that
turns on two of them together; turbo adds a flag for the third on its own.

| Switch | Build flag | What a user gets | Flash | Fits where |
|---|---|---|---|---|
| **1. Loader** | `CIRCUITPY_LOAD_NATIVE=1` (new, turbo branch) | machine-code `.mpy` built on the host loads and runs. Nothing changes in `code.py`. | +2 to 3 KB | every board tried, including SAMD21 (648 bytes to spare, `safemode.py` dropped) and SAMD51 (7 KB to spare) |
| **2. On-board compiler** | `CIRCUITPY_ENABLE_MPY_NATIVE=1` (exists today, off everywhere) | `@micropython.native` and `@micropython.viper` work in `code.py`, compiled on the board at import. Includes switch 1. | +28 to 48 KB | RP2040, RP2350, nRF52840, STM32F405, ESP32-S2/S3/C5, nRF54L, RA8D1 all ran it on the farm. Does not fit SAMD21 (20 KB over) or SAMD51 (13 KB over) |
| **3. Inline assembler** | `MICROPY_EMIT_INLINE_THUMB` (today tied to switch 2) | `@micropython.asm_thumb` in `code.py` | small, not measured | ARM only. Out of a loader-only image. Not measured, not part of turbo |

Two facts about switch 2 worth knowing:

- Switch 2 has a latent bug on Cortex-M0+ (RP2040, SAMD21). The compiler
  defaults to Thumb-2 instructions and nothing in CircuitPython turns that off
  for a Thumb-1 core, so a `@viper` function compiled **on** an M0+ board can
  emit instructions the chip does not have. Host-compiled `.mpy` is unaffected;
  `mpy-cross -march=armv6m` gets it right. Found by reading, not by crashing a
  board.
- Speed is identical either way. The same machine code comes out whether the
  compiler ran on the board or on the host. The farm numbers below were
  reproduced on the loader-only images within a few percent.

## Two questions

**"On tight platforms like SAMD51 and SAMD21 we will not be able to use the
decorators in `code.py`, only in `.mpy`?"**

Yes. On those boards only switch 1 fits. `@micropython.viper` in `code.py`
raises `SyntaxError`, exactly as it does on stock firmware. The compiled
`.mpy` runs at full speed: SAMD51 431 ms on the benchmark that takes 11.2 s
in float bytecode, SAMD21 1.0 s against 73 s.

One nuance that makes this feel less awkward: turbo's own decorator,
`@turbo.viper`, does nothing on the board. It is a marker for the host tool.
So the source file keeps the decorator, stays readable, runs as plain Python
on any firmware, and the tool compiles the marked function on your computer.
The user never writes a `.mpy` by hand.

**"On platforms with lots of space, like Espressif, RP2040 and RP2350, could
we still have the viper and native decorators active in `code.py`?"**

Technically yes. Switch 2 built, ran and was measured on all of those. It is
one line per board in `mpconfigboard.mk`, so it can be flipped later for a
family with headroom.

The 09-06 decision was loader-only everywhere, and the reasons hold even
where the compiler fits:

- One story for every board. A project behaves the same on a Metro M0 and a
  Metro RP2350: source runs everywhere, the compiled `.mpy` runs where the
  CPU matches.
- The M0+ bug above goes away, since nothing compiles on the board.
- Smaller support surface. The loader runs the same output `mpy-cross` has
  produced for MicroPython for years. The on-board compiler adds 28 to 48 KB
  of code paths, compile-time RAM use at import, and its own bug class.
- It can be added later with data. Turning switch 2 on is additive; nothing
  in turbo depends on it being off.

## What the user actually does

1. Flash a turbo build of CircuitPython (a stock release tag plus the flag,
   built by the repo's CI; a `.uf2` per board).
2. Put `@turbo.viper` on the hot function, in the same `.py` file.
3. Run `turbo build` on the computer. It compiles the function for each
   supported CPU into `lib/turbo/<arch>/`, and copies `lib/` and `src/` to
   CIRCUITPY. Or `turbo pack` makes one `.uf2` with firmware and project.

On the board, a 40-line pure-Python shim (`lib/turbo.py`) reads which CPU the
firmware reports, puts the matching `lib/turbo/<arch>/` ahead of `/src` on the
import path, and the normal `import` does the rest. No loader change, no
custom importer. If the directory or the file is missing, or the firmware is
stock, the same `import` finds the source.

## What it buys

Mandelbrot 160x120, 64 iterations, median of 8 runs, milliseconds. "vs float"
is against the float bytecode a person would write first.

```
Board                 native ms   vs float   viper ms   vs float
--------------------  ---------   --------   --------   --------
EK-RA8D1 (M85)              488       3.7x         47      38.3x
ESP32-C5                  1 809       4.2x        172      44.0x
Metro ESP32-S3            1 708       2.9x        186      26.2x
Metro ESP32-S2            2 110       3.5x        206      36.1x
Metro RP2350              2 380       2.7x        261      24.4x
nRF54L15 DK               2 836       3.6x        349      29.3x
nRF54LM20 DK              2 840       3.6x        351      29.3x
Metro RP2040              4 739       2.9x        384      36.3x
Feather STM32F405         2 779       2.9x        416      19.5x
Metro M4 AirLift          3 536       3.2x        431      26.0x
Feather nRF52840          7 445       2.8x        781      26.6x
Metro M0 Express         23 408       3.1x      1 014      71.7x
```

## What it does not do

- Nothing for I/O. Waiting on I2C, SPI, UART, USB, WiFi or `sleep` is not
  CPU time. `displayio`, `audiocore`, `neopixel_write` are already C.
- Nothing for strings, dicts, lists, objects or allocation. Viper hands those
  back to the runtime.
- Native's roughly 3x is the ceiling for float-heavy code unless someone
  rewrites it in fixed-point ints, which is real porting work and changes the
  numerics.
- Bytecode speed is unchanged. Float bytecode measured the same with and
  without the loader on every board (under 1%).

## Where the code is

Everything is on Mikey's GitHub, nothing has gone to `adafruit/`:

- `mikeysklar/turbo`: shim, CLI, CI workflow, examples, all the docs and
  measurements. `docs/turbo-on-the-farm.md` is the full results table,
  `docs/loader-only-samd.md` the loader-only record with the complete change
  list for a future PR.
- `mikeysklar/circuitpython` branches: `loader-only-native` (ARM: the
  `CIRCUITPY_LOAD_NATIVE` patch, 12 files, plus board flags),
  `esp32-native` (Xtensa: the same plus the ESP32 executable-memory work),
  `esp32-native-c5` (RISC-V), `verify/nrf54l-all` and `ra8d1-turbo` (Zephyr
  boards, on-board compiler, not yet converted to loader-only).
