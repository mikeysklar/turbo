# Turbo on the Farm

CircuitPython 10.3.0, native emitter, HIL farm, 2026-09-04 to 09-05.

"Turbo" is CircuitPython's dormant native emitter turned on. A function marked
`@micropython.viper` is compiled by `mpy-cross` into machine code for the
board's CPU and shipped as a `.mpy`, with the `.py` beside it. Same source, no
new firmware feature, one build flag. We measured what it actually buys on real
hardware.

| Headline | |
|---|---|
| **19 to 36x** | viper over the float Python people write, on six ARM boards |
| **1.8 to 2.9x** | `@micropython.native` on unchanged code, any Python |
| **±1%** | change to ordinary bytecode speed with the flag on. It costs nothing until you use it |

## Results

Mandelbrot 160x120, 64 iterations, 407,644 inner iterations. Milliseconds,
median of 8 trials per cell, trial-to-trial spread under 0.02% everywhere. All
four variants produced the same output checksum.

| Board | Core | MHz | float bytecode | int bytecode | @native | @viper | viper / float | viper / int | Native build |
|---|---|---|---|---|---|---|---|---|---|
| Metro M0 Express | Cortex-M0+ | 48 | 72 741 | 44 130 | | | | | overflows flash by 19.9 KB |
| Metro RP2040 | Cortex-M0+ | 125 | 13 942 | 8 296 | 4 739 | 384 | **36.3x** | 21.6x | flashed, UF2 |
| Metro M4 AirLift | Cortex-M4F | 120 | 11 221 | 6 623 | 3 536 | 431 | **26.0x** | 15.4x | loader-only, no emitter, 7 KB free |
| Feather nRF52840 | Cortex-M4F | 64 | 20 788 | 14 697 | 7 445 | 781 | **26.6x** | 18.8x | flashed, SWD |
| Metro ESP32-S2 | Xtensa LX7 | 240 | 7 438 | 4 328 | 2 110 | 206 | **36.1x** | 21.0x | esp32-native branch |
| Metro RP2350 | Cortex-M33 | 150 | 6 371 | 4 547 | 2 380 | 261 | **24.4x** | 17.4x | flashed, UF2 |
| Metro ESP32-S3 | Xtensa LX7 | 240 | 4 873 | 3 411 | 1 708 | 186 | **26.2x** | 18.3x | esp32-native branch |
| Feather STM32F405 | Cortex-M4F | 168 | 8 121 | 5 204 | 2 779 | 416 | **19.5x** | 12.5x | flashed, SWD |
| ESP32-C5 DevKitC | RISC-V rv32imc | 240 | 7 591 | 3 582 | 1 809 | 172 | **44.0x** | 20.8x | esp32-native-c5 branch |
| nRF54L15 DK | Cortex-M33 | 128 | 10 233 | 5 328 | 2 836 | 349 | **29.3x** | 15.3x | verify/nrf54l-all branch, Zephyr |
| nRF54LM20 DK | Cortex-M33 | 128 | 10 288 | 5 400 | 2 840 | 351 | **29.3x** | 15.4x | verify/nrf54l-all branch, Zephyr |

Bytecode columns come from the native-enabled firmware where one exists, else
from the stock 10.3.0 release; the two differ by under 1% on every board except
a 5% float swing on the nRF52840 that also appears between two stock Adafruit
builds.

Viper cost per inner-loop iteration, CPU cycles (measured time x clock / 407,644):

| Board | cycles / iteration |
|---|---|
| Metro RP2350 | 96 |
| ESP32-C5 DevKitC | 101 |
| Metro ESP32-S3 | 110 |
| nRF54L15 DK | 110 |
| nRF54LM20 DK | 110 |
| Metro RP2040 | 118 |
| Metro ESP32-S2 | 121 |
| Feather nRF52840 | 123 |
| Metro M4 AirLift | 127 |
| Feather STM32F405 | 171 |

The two Xtensa rows were measured on the `esp32-native` branch, which wires up
`MICROPY_EMIT_XTENSAWIN` and an executable-RAM allocator. The S3 native and
viper cells are this farm's own 2026-09-05 run, 8 trials, spread under 2 ms,
checksum 407644; the S2 cells come from the branch bring-up.

The two nRF54L rows are the Zephyr port (`zephyr-cp`), same Cortex-M33 core at
128 MHz, both this farm's own 2026-09-05 run, 8 trials, spread under 2 ms,
fixed-point checksum 581. They land at 110 cycles per iteration, in the same
band as the ESP32-S3, so the emitter behaves identically on the Zephyr M33 once
it is allowed to run. What it took to get there is in "what's in the way" below.

Hand-written C would be about 20 cycles for this loop. The gap is the emitter,
not the chips: it keeps one local in a register and spills the rest to the
stack. The STM32F405 outlier is unexplained; its code is byte-identical to the
RP2350's.

## What the four columns are

The same mandelbrot, four ways, from the same 10.3.0 tree.

| Variant | What it is |
|---|---|
| float bytecode | The version anyone would write: `x*x + y*y > 4.0`. Normal CircuitPython. This is the honest baseline |
| int bytecode | Same loop rewritten in 12-bit fixed point, no decorator. Still interpreted. Shows how much of the win is just "avoid floats" |
| `@micropython.native` | The fixed-point file with one decorator, compiled by `mpy-cross -march=...`. Control flow becomes machine code; every value is still a Python object |
| `@micropython.viper` | Same file, `int` and `ptr8` types. Values become raw machine words; `x*x` becomes one `muls` |

## Why viper and not native gets the speedup

We disassembled both blobs. The native one contains no multiply instruction.
Every `*`, `>>`, `+` and `<` is a call back into the runtime:

```
144:  ldr  r1, [sp, #24]      ; operand, still a Python object
146:  movs r0, #14            ; which binary op
148:  ldr  r3, [r7, #72]      ; mp_binary_op, from the runtime table
14a:  blx  r3                 ; type-check, unbox, multiply, overflow-check, re-box
14c:  str  r0, [sp, #24]      ; result, a Python object
```

Native removed bytecode fetch and dispatch, worth about 2x. Viper changed the
data representation, so the same statement is `ldr, muls, asrs, str`. That is
the other 9x, and it is also why viper only takes ints and pointers: the
restrictions are the price of the representation.

Viper is still far from C. Its 96 to 171 cycles per iteration against ~20 for
compiled C come from MicroPython's emitter keeping only one local in a register
and shuttling every other value through the stack. That is a property of
`py/emitnative.c` on every port, not of the flag or the chips.

## Where this pays

Good fit, 20 to 35x:

- Fractals, plasma, cellular automata, particles
- Pixel ops: scaling, rotation, dithering, convolution
- LED mapping, colour math, gamma, HSV to RGB
- CRCs, checksums, packet parsing, FEC, bit unpacking
- Byte-level codecs and compression
- Fixed-point DSP, int8 ML inference

Little or nothing:

- Float-heavy math that can't go fixed-point: sensor fusion, Kalman. Native's 2 to 3x is the ceiling
- Anything already in C: `displayio`, `ulab`, `hashlib`, `aesio`, `neopixel_write`
- Anything waiting on I2C, SPI, USB, WiFi or `sleep`
- Strings, dicts, lists, object work, allocation

## What it costs and what is in the way

- **Flash.** The emitter does not fit on the two SAMD farm boards: the SAMD21 (M0 Express) overflows by 19,948 bytes, the SAMD51 (M4 AirLift) by 12,804. On the M4 the emitter plus the native `.mpy` loader together cost about 22.6 KB of flash under LTO. Two ways out: drop modules, or split the config so the board only loads and runs host-compiled native `.mpy` and does not carry the on-board emitter (`emitnative.c` + `asmthumb.c`, the bulk of that 22.6 KB). The load path (`persistentcode.c`, `mp_native_relocate`, `nativeglue.c`) is gated on `MICROPY_EMIT_MACHINE_CODE`, which is derived from the emitter, so the loader-only split needed a decoupling patch (new `MICROPY_LOAD_NATIVE` macro, 10 files). Done and proven on the M4: it links at 492,712 B with 7,000 B free, loads and runs host-compiled viper at 431 ms (26.0x over float), and rejects `@viper` from source with a `SyntaxError` because the emitter is not in the image. Full record and the exact patch in `loader-only-samd.md` / `loader-only-samd.patch`. The M0 (armv6m, 19.9 KB over) has not been tried yet.
- **ARM in tree; Xtensa on a branch.** Stock `CIRCUITPY_ENABLE_MPY_NATIVE` wires up Thumb and nothing else. The `esp32-native` branch adds the Xtensa mapping in `py/circuitpy_mpconfig.h`, an executable-RAM allocator for the espressif port, and the non-ARM pointer fix; with it the ESP32-S2 and S3 run native and viper (the two Xtensa rows above). The emitters and `mpy-cross -march=xtensawin / rv32imc` already exist upstream. RISC-V is now proven on hardware too: the ESP32-C5 row above was built from `esp32-native` plus the `esp32c5-board` support and runs viper at 44x. The ESP32-P4 native firmware is built and verified but not yet flashed (its download USB drops with the OTG, so it needs a BOOT-strapped download or a JTAG debug flash).
- **Zephyr's MPU and cache (nRF54L).** The Zephyr M33 needs three things the bare-metal ARM ports do not. The build flag has to be read after the board's `circuitpython.toml` loads, because the zephyr board aliases return no `mpconfigboard` and it otherwise never reaches the compiler. The emitter's D-cache flush and I-cache invalidate, undefined in this port, map to Zephyr's cache API (`sys_cache_data_flush_range` / `sys_cache_instr_invd_all`). And `CONFIG_ARM_MPU` force-selects `SRAM_REGION_PERMISSIONS`, which marks the heap non-executable, so the first native call takes an MPU Instruction Access Violation; `CONFIG_ARM_MPU=n` leaves SRAM executable under the ARMv8-M default map, the analog of the ESP32 memprot-off. A dedicated executable MPU region is the proper fix. All three are on `mikeysklar/circuitpython@verify/nrf54l-all`.
- **The import rule.** CircuitPython tries `name.py` before `name.mpy`. A source file next to its native `.mpy` silently shadows it. "Source beside binary" works only with the source off `sys.path`, e.g. `/src/`, or with a loader change.
- **Per-arch files.** An `armv7emsp` `.mpy` refuses to load on an RP2040 (`incompatible .mpy arch`), which is correct but means one file per architecture family, or a bundle format.
- **Firmware required for both decorators.** On stock firmware `@micropython.native` is a compile-time `SyntaxError` and a native `.mpy` is `ValueError: native code in .mpy unsupported`. The fallback `.py` must have the decorator removed.
- **A latent bug.** `MICROPY_EMIT_THUMB_ARMV7M` defaults to 1 and nothing in CircuitPython clears it for Cortex-M0+, so a `@viper` function compiled on an M0+ board from source would emit Thumb-2. Host-compiled `.mpy` files are unaffected. Found by reading, not by crashing a board.

## Shipping it as one file

On the RP2350 we packed the native firmware, `lib/*.mpy`, `src/*.py` and a
`code.py` into a single 2 MB UF2 with `folder2uf2 --combine`. One drag onto the
bootloader volume; 13 seconds later the board boots and prints the table above
for itself. The source is on the drive for anyone to read, the compiled
acceleration is a file they can delete.

## How it was measured

- Eight boards on the bravo HIL farm, addressed by USB path, identity confirmed from `boot_out.txt` before every write. Every board backed up first.
- Firmware: the `10.3.0` tag, GCC 14.2.1, flag on the `make` line, no source edit. Emitter presence proven from `emitnthumb.o` size (0 to 30 KB) and 33 new symbols in the ELF.
- Regression gate on RP2350 before any speed claim: 40/40 on the farm burn set, `bm_pidigits` within 2% of stock, the six `viper_call` perf tests flipping from SKIP to numbers.
- Timing on-board with `time.monotonic_ns()`, 8 trials per cell after `gc.collect()`, driven over the raw REPL. Output checksums compared across variants.
- The 100x figure from the internal thread was not reproduced. Our best is 36x on the same chip against float Python. The original's baseline code is unknown, so the gap is unexplained rather than refuted.

## Next

- SiWx917 (Zephyr): native compiles, but a first run reported arch 0 and the console routing is unresolved.
- ESP32-P4 (RISC-V): native firmware built and verified, flash blocked (its download USB drops with the OTG, so it needs a BOOT-strapped download or a JTAG debug flash).
- SAMD51 (M4 AirLift) is done via the loader-only split (431 ms viper, 7 KB free). SAMD21 (M0 Express, armv6m, 19,948 B over) is next: same patch, `MICROPY_LOAD_NATIVE` on its board, see whether the armv6m loader fits.
- Find the STM32F405's extra 75 cycles.
- Cortex-M4 boards other than the farm's have not been measured; the range above is a handful of boards, not a law.

Data, scripts and per-step notes: `work.log.md`, `turbo-conversion.md`,
`applications.md`, and `bravo:~/turbo/`. Measured 2026-09-04.
