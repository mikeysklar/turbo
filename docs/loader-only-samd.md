# Loader-only native `.mpy` on the SAMD boards

Tracking the experiment to run host-compiled native `.mpy` on the two SAMD
farm boards without carrying the on-board emitter, so the firmware fits in
flash. Started 2026-09-05.

## The problem

With `CIRCUITPY_ENABLE_MPY_NATIVE=1` the two SAMD farm boards overflow flash:

| Board | Chip | Overflow |
|---|---|---|
| Metro M0 Express | SAMD21, Cortex-M0+ | 19,948 bytes |
| Metro M4 AirLift | SAMD51, Cortex-M4F | 12,804 bytes |

On the M4 the emitter plus the native `.mpy` loader together cost about
22.6 KB of flash under LTO (native build used 512,516 B of the 488 KB
`FLASH_FIRMWARE` region; stock is about 489,936 B in flash).

## The idea

The turbo shim ships `.mpy` files that `mpy-cross` already compiled on the
host. The board only needs to **load and run** native `.mpy`, not **compile**
`@native` / `@viper` from source. The on-board emitter (`emitnative.c`,
`asmthumb.c`, `emitinlinethumb.c`) is the bulk of that 22.6 KB; the load path
(`persistentcode.c`, `mp_native_relocate`, `nativeglue.c` `mp_fun_table`) is
the small remainder. Drop the emitter, keep the loader, and the M4 should fit
without giving up any modules.

## The coupling

`CIRCUITPY_ENABLE_MPY_NATIVE` sets `MICROPY_EMIT_THUMB` (py/circuitpy_mpconfig.h).
`MICROPY_EMIT_NATIVE` is derived from the per-arch emit macros, and
`MICROPY_EMIT_MACHINE_CODE = MICROPY_EMIT_NATIVE || MICROPY_EMIT_INLINE_ASM`.
The native `.mpy` load path in `py/persistentcode.c` is gated on
`MICROPY_EMIT_MACHINE_CODE`, so today loading is coupled to emitting: turn the
emitter off and the loader goes with it. There is no stock flag for
loader-only.

## The patch (proposed)

- New macro `MICROPY_LOAD_NATIVE`, default 0, in `py/mpconfig.h`.
- In `py/persistentcode.c` (and the `mp_fun_table` / relocate glue), change the
  native-load `#if MICROPY_EMIT_MACHINE_CODE` guards to
  `#if MICROPY_EMIT_MACHINE_CODE || MICROPY_LOAD_NATIVE`.
- On the M4 board, set `MICROPY_LOAD_NATIVE=1` with `CIRCUITPY_ENABLE_MPY_NATIVE`
  off, so the emitter files empty out (`#if MICROPY_EMIT_THUMB`) while the load
  path stays.

## The patch (as built)

New macro `MICROPY_LOAD_NATIVE` in `py/mpconfig.h`, folded into
`MICROPY_EMIT_MACHINE_CODE`. Then `|| MICROPY_LOAD_NATIVE` added to the
native-runtime guards (not `compile.c`, which stays on the real emitter macro,
so the from-source path and the emitter files stay out):

- `py/persistentcode.c` load path (via the widened `MICROPY_EMIT_MACHINE_CODE`)
- `py/nativeglue.c` / `py/nativeglue.h` (`mp_fun_table`, type conversions)
- `py/emitglue.c` (`assign_native`, make-callable switch)
- `py/objfun.c` / `py/objfun.h` (`mp_type_fun_native`/`viper`, call thunks)
- `py/objgenerator.c`, `py/bc.c` (native gen/coro types, `mp_setup_code_state_native`)

Board turns it on with `MICROPY_LOAD_NATIVE (1)` in `mpconfigboard.h` and leaves
`CIRCUITPY_ENABLE_MPY_NATIVE` off, so `MICROPY_EMIT_THUMB` is 0 and the emitter
source files (`emitnative.c`, `asmthumb.c`, `emitinlinethumb.c`) compile to
nothing.

## Result: it fits (Metro M4 AirLift, 2026-09-05)

| Build | Flash used | vs 499,712 B region |
|---|---|---|
| stock, no native | ~489,936 B | fits |
| full emitter (`CIRCUITPY_ENABLE_MPY_NATIVE=1`) | 512,516 B | overflow 12,804 |
| **loader-only** | **492,708 B** | **fits, 7,004 B free** |

Loader-only costs about 2.8 KB over stock (the load path + glue + fun table) and
drops the ~22.6 KB emitter, clearing the overflow with 7 KB to spare, no modules
dropped.

## Status

- [x] Patch written (7 core files + board define), on `cp-1030` tree
- [x] M4 links and fits flash (7,004 B free)
- [ ] M4 loads and runs a host-compiled native/viper `.mpy` (checksum 407644)
- [ ] M0 (armv6m) tried
- [ ] Decide upstreamability / where it lives (clean macro, could go to Adafruit)

Notes and numbers land here as the experiment runs.
