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
- `py/persistentcode.h`: the advertised arch. `MPY_FEATURE_ARCH` was picked by
  `#elif MICROPY_EMIT_THUMB`, so a loader-only build fell through to
  `MP_NATIVE_ARCH_NONE`, reported arch 0 in `sys.implementation._mpy`, and the
  loader raised `native code in .mpy unsupported` before relocating anything.
  The thumb branch now also fires for `MICROPY_LOAD_NATIVE && defined(__thumb__)`,
  and the existing `__thumb2__` / `__ARM_FP` tests resolve it to `armv7emsp`.
  This was the second coupling layer, found only by running the `.mpy`.

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

## Result: it runs (Metro M4 AirLift, 2026-09-05)

Flashed over SWD (CMSIS-DAP `E6647C740349682C`, 500 kHz, app base `0x4000`).
Host-compiled `armv7emsp` `.mpy` files copied to CIRCUITPY, run over the raw
REPL. `sys.implementation._mpy` now reports arch 7 (armv7emsp).

| Variant | checksum | ms (median) | vs int bytecode | vs float bytecode |
|---|---|---|---|---|
| int bytecode (source) | 581 | 6 623 | 1.0x | 1.7x |
| `native .mpy` (host-compiled) | 581 | 3 536 | 1.9x | 3.2x |
| `viper .mpy` (host-compiled) | 581 | **431** | **15.4x** | **26.0x** |
| `@micropython.viper` from source | SyntaxError | | | emitter correctly absent |

Float baseline 11,221 ms is the stock-firmware figure from the farm table. 431 ms
at 120 MHz is about 127 cycles per inner iteration, in line with the other
Cortex-M4 boards (nRF52840 123, RP2040 118).

The last row is the proof of the split: the board runs pre-compiled viper at
full speed but cannot compile `@viper` from source, because the emitter is not
in the image.

## Result: it fits (Metro M0 Express, 2026-09-05)

Same patch, `MICROPY_LOAD_NATIVE (1)` in the M0 board header, nothing else.

| Build | Flash used | vs 253,696 B region |
|---|---|---|
| stock, no native | 251,956 B | fits, 1,740 B free |
| full emitter (`CIRCUITPY_ENABLE_MPY_NATIVE=1`) | | overflow 19,948 |
| loader-only, nothing dropped | 253,824 B | **overflow 128** |
| **loader-only + `CIRCUITPY_SAFEMODE_PY = 0`** | **253,048 B** | **fits, 648 B free** |

The armv6m loader costs 1,868 B over stock, 1,000 B less than on the M4 (smaller
`mp_fun_table` call thunks, no async so no coro wrap). The SAMD21 default config
already turns `MICROPY_PY_ASYNC_AWAIT` off and drops a long list of modules to
fit 256 KB, so there was only 1,740 B of headroom to start with and the loader
missed by 128 B. `safemode.py` support (776 B) is the least-used thing of that
size and is already off on the internal-flash SAMD21 boards, so it went.

One gotcha: after changing a `CIRCUITPY_*` flag in `mpconfigboard.mk` the
incremental build linked stale objects and failed with an undefined
`supervisor_safe_mode_reason_type`. The guards in `shared-bindings/supervisor`
are correct; `rm -rf build-metro_m0_express` and a clean build fixed it.

## Result: it runs (Metro M0 Express, 2026-09-05)

Flashed over SWD (CMSIS-DAP `E6647C74039F6B2D`, `reset halt`, 2000 kHz, app base
`0x2000`). Host-compiled `armv6m` `.mpy` files copied to CIRCUITPY.
`sys.implementation._mpy` = 4870, arch 4 (armv6m).

| Variant | checksum | ms (median) | vs int bytecode | vs float bytecode |
|---|---|---|---|---|
| int bytecode (source) | 581 | 43 281 | 1.0x | 1.7x |
| `native .mpy` (host-compiled) | 581 | 23 408 | 1.8x | 3.1x |
| `viper .mpy` (host-compiled) | 581 | **1 014** | **42.7x** | **71.7x** |
| `@micropython.viper` from source | SyntaxError | | | emitter correctly absent |

Float baseline 72,741 ms and the farm-table int figure 44,130 ms are the stock
firmware numbers (today's int bytecode ran 2% faster, 2 trials). 1,014 ms at
48 MHz is about 119 cycles per inner iteration, the same core as the RP2040's
118, so the loaded armv6m code runs exactly as the emitter's would. This is the
slowest board on the farm and the one that gains the most: a 73 s float loop
becomes 1 s.

## Complete change list (for the PR)

Twelve files, 43 insertions, 17 deletions, against the `10.3.0` tag (ten for
the core patch plus the two SAMD board files). The exact
diff is saved beside this file as `loader-only-samd.patch`. Everything is
gated behind one new macro so it is a no-op for every existing build.

**The macro**

- `py/mpconfig.h`: define `MICROPY_LOAD_NATIVE` (default 0) and fold it into
  `MICROPY_EMIT_MACHINE_CODE (MICROPY_EMIT_NATIVE || MICROPY_EMIT_INLINE_ASM || MICROPY_LOAD_NATIVE)`.
  Widening `MACHINE_CODE` alone turns on the `.mpy` load path in
  `persistentcode.c`, `mp_emit_glue_assign_native`, `mp_native_to_obj`, the
  `mp_raw_code_t` native fields in `emitglue.h`, and `asmbase.c` (unused, the
  linker drops it), with no per-site edits to those.

**Runtime sites gated on `MICROPY_EMIT_NATIVE`, each changed to `|| MICROPY_LOAD_NATIVE`**

These are needed to make a loaded native function callable and to let its
machine code call back into the runtime. `compile.c` is deliberately left on
the real `MICROPY_EMIT_NATIVE`, so the compile-from-source path and the
emitter selection stay out.

- `py/nativeglue.c` lines 46, 120, 362: `mp_native_type_from_qstr`,
  `mp_native_from_obj`, and the `mp_fun_table` block (the table of runtime
  entry points native code jumps through).
- `py/nativeglue.h` lines 187, 189: the `extern mp_fun_table` declaration.
- `py/emitglue.c` line 228: the `MP_CODE_NATIVE_PY` / `MP_CODE_NATIVE_VIPER`
  cases in `mp_make_function_from_proto_fun` (turns a loaded raw code into a
  callable object).
- `py/objfun.c` lines 142, 451, 486: native prelude lookup, `mp_type_fun_native`
  + `fun_native_call`, `mp_type_fun_viper` + `fun_viper_call`.
- `py/objfun.h` line 56: the inline `mp_obj_new_fun_native` / `mp_obj_new_fun_viper`.
- `py/objgenerator.c` lines 117, 240, 262, 300: `mp_type_native_gen_wrap`,
  `mp_type_native_coro_wrap`, and the native generator resume paths.
- `py/bc.c` line 339: `mp_setup_code_state_native` (referenced by `mp_fun_table`).

**The advertised arch (the second coupling layer)**

- `py/persistentcode.h` line 60: `#elif MICROPY_EMIT_THUMB` becomes
  `#elif MICROPY_EMIT_THUMB || (MICROPY_LOAD_NATIVE && defined(__thumb__))`.
  Without this the build linked and fit but still reported arch 0 and raised
  `native code in .mpy unsupported` from the `MPY_FEATURE_ARCH_TEST` check,
  before the loader ran. The existing `__thumb2__` / `__ARM_FP` tests then
  pick `armv7emsp` for the M4. Only found by actually running a `.mpy`.

**The board**

- `ports/atmel-samd/boards/metro_m4_airlift_lite/mpconfigboard.h`: add
  `#define MICROPY_LOAD_NATIVE (1)`. Build with `CIRCUITPY_ENABLE_MPY_NATIVE`
  left off, so `MICROPY_EMIT_THUMB` is 0 and `emitnthumb.c` (which includes
  `emitnative.c`), `asmthumb.c` and `emitinlinethumb.c` compile to nothing.
- `ports/atmel-samd/boards/metro_m0_express/mpconfigboard.h`: same
  `#define MICROPY_LOAD_NATIVE (1)`.
- `ports/atmel-samd/boards/metro_m0_express/mpconfigboard.mk`: add
  `CIRCUITPY_SAFEMODE_PY = 0` to recover the last 128 B. Needs a clean build.

**What was deliberately not changed**

- `py/compile.c`: stays on `MICROPY_EMIT_NATIVE`. Widening that macro breaks
  it: it selects `NATIVE_EMITTER` from the arch macro and would reference an
  emitter that is not compiled.
- `py/persistentcode.c` lines 597 and 673: the `.mpy` save path, mpy-cross only,
  off in firmware.
- `py/runtime.c` line 116: `default_emit_opt`, compiler-emitter state, not needed.
- `py/asmbase.c`: compiles under the widened `MACHINE_CODE` but is unreferenced,
  so `--gc-sections` drops it.

**One caveat for the PR**

The `emitglue.c` hunk in `loader-only-samd.patch` also carries six lines of an
earlier, separate change (`MP_HAL_INVALIDATE_ICACHE`, the Zephyr I-cache
portability fix) that happened to live in the same tree. The loader-only PR
needs only the one `#if MICROPY_EMIT_NATIVE || MICROPY_LOAD_NATIVE` line from
that file; split the I-cache lines out.

## Procedure

```
# build (no CIRCUITPY_ENABLE_MPY_NATIVE on the make line)
make -C ports/atmel-samd BOARD=metro_m4_airlift_lite -j4
# flash over SWD, keeping the UF2 bootloader at 0x0
openocd -c "source [find interface/cmsis-dap.cfg]" -c "adapter serial E6647C740349682C" \
  -c "transport select swd" -c "source [find target/atsame5x.cfg]" -c "adapter speed 500" \
  -c init -c "reset halt" -c "program firmware.bin 0x4000 verify reset" -c exit
# test: copy armv7emsp mandel_vip.mpy / mandel_nat.mpy to CIRCUITPY, run over raw REPL

# M0 Express: clean build after the .mk change, app base 0x2000
rm -rf ports/atmel-samd/build-metro_m0_express
make -C ports/atmel-samd BOARD=metro_m0_express -j8
openocd -f interface/cmsis-dap.cfg -c "adapter serial E6647C74039F6B2D" -c "transport select swd" \
  -f target/at91samdXX.cfg -c init -c "adapter speed 2000" -c "reset halt" \
  -c "flash write_image erase firmware.bin 0x2000 bin" -c "reset run" -c shutdown
# test: armv6m mandel_vip.mpy / mandel_nat.mpy (bravo:~/turbo/armv6m/)
```

The UF2 route (1200-baud touch) reported "no medium" over SSH on this board;
SWD is the reliable path here.

## Status

- [x] Patch written (10 files), on the `cp-1030` (10.3.0) tree
- [x] M4 links and fits flash (7,000 B free)
- [x] M4 loads and runs host-compiled native and viper `.mpy` (checksum 581, viper 431 ms)
- [x] Source `@viper` rejected, confirming the emitter is out
- [x] Committed to `mikeysklar/circuitpython` branch `loader-only-native` (`af32cbcb36` core, `6fdfdcc7ca` M0 board)
- [x] M0 Express fits (648 B free, safemode.py dropped) and runs host-compiled armv6m viper at 1,014 ms
- [ ] Split the I-cache lines out of `emitglue.c` before an upstream PR
- [ ] Decide upstreamability (clean single macro; a candidate for Adafruit)

Board state after: both the M4 AirLift and the M0 Express are running the
loader-only firmware with the test `.mpy` files on CIRCUITPY, not the farm idle
sketch. Backups: `bravo:~/backup-m4-loaderonly-20260905-194241/`,
`bravo:~/backup-m0-loaderonly-20260905-201331/`.
