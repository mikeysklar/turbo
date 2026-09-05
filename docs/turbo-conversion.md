# Turbo: CircuitPython source to machine code, and onto the board

"Turbo" is the native emitter that ships inside MicroPython and CircuitPython.
You mark a function, `mpy-cross` compiles that function to machine code for the
target CPU, and the board runs it directly instead of interpreting bytecode.
Nothing changes in your source language, and the `.py` stays readable.

Verified against the `10.3.0` tag (`d897c15f24`), 2026-09-04.

## What has to be true first

| Requirement | Why | How you know it is missing |
|---|---|---|
| Firmware built with `CIRCUITPY_ENABLE_MPY_NATIVE=1` | Default is `0` (`py/circuitpy_mpconfig.mk:321`). Only winterbloom_sol, swan_r5 and two makerdiary boards ship with it on | `@micropython.native` in a `.py` gives `SyntaxError: invalid micropython decorator`; importing a native `.mpy` gives `ValueError: native code in .mpy unsupported` |
| ARM Cortex-M board | The flag only wires up Thumb (`py/circuitpy_mpconfig.h:73-74`). No Xtensa or RISC-V wiring exists in CircuitPython today | ESP32-S2/S3 are out until someone adds `MICROPY_EMIT_XTENSAWIN` |
| `mpy-cross` from the **same CircuitPython tree** | `.mpy` format is 6.3 and CircuitPython's differs from MicroPython's | `ValueError: incompatible .mpy file` |
| Right `-march=` for the chip | Machine code is per-architecture | `ValueError: incompatible .mpy arch` |

Farm boards and their arch:

| Board | Core | `-march=` |
|---|---|---|
| Metro M0 Express, Metro RP2040 | Cortex-M0+ | `armv6m` |
| Metro M4 AirLift, Feather nRF52840, Feather STM32F405 | Cortex-M4F | `armv7emsp` |
| Metro RP2350 (ARM mode) | Cortex-M33 | `armv7emsp` |
| Metro ESP32-S2 / S3 | Xtensa LX7 | not supported in CircuitPython |

## Step 1: build the firmware

No source edit. The flag rides on the make line.

```sh
cd ~/cp-1030                                  # worktree at the 10.3.0 tag
export PATH=$HOME/arm-toolchain/bin:$HOME/.local/bin:$PATH
make -C ports/raspberrypi fetch-port-submodules
make -C mpy-cross -j4                         # this tree's mpy-cross, step 3 needs it
make -C ports/raspberrypi BOARD=adafruit_metro_rp2350 \
     CIRCUITPY_ENABLE_MPY_NATIVE=1 -j4
```

Output: `ports/raspberrypi/build-adafruit_metro_rp2350/firmware.uf2`.

Flash it the normal RP2 way: 1200-baud touch on the board's tty, wait for the
`RP2350` bootloader volume, copy the UF2. Back up `CIRCUITPY` first.

## Step 2: mark the hot function

Two decorators, pick per function.

`@micropython.native` compiles ordinary Python. Everything still works, objects
are still Python objects. Expect roughly 2 to 3x.

`@micropython.viper` is where the big numbers come from. Integers only, no
floats, arguments typed as `int`, buffers reached through `ptr8` / `ptr16` /
`ptr32`. Expect 10 to 100x on tight integer loops, because the loop becomes
real machine instructions on real registers.

```python
# turbo_mandel.py

@micropython.viper
def mandel_row(out: ptr8, width: int, cy: int, max_iter: int):
    # fixed point, 12 fractional bits, so no floats reach viper
    for px in range(width):
        cx = ((px * 3) << 12) // width - (2 << 12)
        x = 0
        y = 0
        i = 0
        while i < max_iter:
            x2 = (x * x) >> 12
            y2 = (y * y) >> 12
            if x2 + y2 > (4 << 12):
                break
            y = ((x * y) >> 11) + cy
            x = x2 - y2 + cx
            i += 1
        out[px] = i
```

The same file runs unchanged as plain bytecode on a stock build if you delete
the decorator line. That is the whole "source is the fallback" story.

## Step 3: compile it

```sh
~/cp-1030/mpy-cross/build/mpy-cross -march=armv7emsp turbo_mandel.py
# writes turbo_mandel.mpy next to it
```

Only decorated functions become machine code. The rest of the module is normal
bytecode inside the same `.mpy`.

## Step 4: put it on the board

The import search tries `name.py` **before** `name.mpy`
(`py/builtinimport.c:80`, `stat_file_py_or_mpy`). A `turbo_mandel.py` sitting
next to `turbo_mandel.mpy` shadows the native code and you silently get the
slow path. So the source has to live somewhere off `sys.path`:

```
CIRCUITPY/
  code.py
  lib/turbo_mandel.mpy      <- what runs
  src/turbo_mandel.py       <- what you read, edit, and recompile from
```

Two ways to get it there:

**Drag and drop.** Copy `lib/` and `src/` onto `CIRCUITPY`.

**One UF2, firmware included.** `folder2uf2 --combine` lays the filesystem
image over the native firmware so the whole thing is a single drag onto the
`RP2350` bootloader volume:

```sh
folder2uf2 --board adafruit_metro_rp2350 \
           --combine ports/raspberrypi/build-adafruit_metro_rp2350/firmware.uf2 \
           -o turbo-demo.uf2 myproject/
```

`--self-extract -o code.py` also works on a board already running the native
firmware, if you would rather not touch the bootloader.

## Step 5: prove it

```python
import time
import turbo_mandel

row = bytearray(320)
t0 = time.monotonic_ns()
for cy in range(240):
    turbo_mandel.mandel_row(row, 320, ((cy * 2) << 12) // 240 - (1 << 12), 64)
print((time.monotonic_ns() - t0) // 1_000_000, "ms")
```

Run it three ways on the same board, 8 or more trials each: bytecode (no
decorator), `@micropython.native`, `@micropython.viper`. Two trials is not a
measurement. Numbers for the Metro RP2350 land in `work.log.md` as they come
in.

## What it will not do

- Speed up anything waiting on I2C, SPI, USB, WiFi or `time.sleep`. Only CPU
  loops get faster.
- Run on ESP32 boards, yet.
- Load if the `.mpy` was made by MicroPython's `mpy-cross` or for the wrong
  `-march`. The error names the problem in both cases, see the table above.
