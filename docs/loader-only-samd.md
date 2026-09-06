# Loader-only native `.mpy` on the SAMD boards, then the whole farm

Tracking the experiment to run host-compiled native `.mpy` on the two SAMD
farm boards without carrying the on-board emitter, so the firmware fits in
flash. Started 2026-09-05. On 2026-09-06 it became the model for every board
(see "All eight farm boards" at the end).

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

## All eight farm boards, 2026-09-06

Decision from Phil and Limor (2026-09-06): drop the on-board emitter, keep the
loader, keep viper. Turbo compiles on the host with `mpy-cross`; the board
only ever loads `.mpy`. Viper is a typing mode inside the same code generator
as `@native`, not the inline assembler, and it is where the 20 to 72x comes
from. All three front ends (`@native`, `@viper`, `@micropython.asm_thumb`)
leave the image in a loader-only build; the loader and `mp_fun_table` stay.

### The flag

`CIRCUITPY_LOAD_NATIVE ?= 0` in `py/circuitpy_mpconfig.mk`, emitted as
`-DMICROPY_LOAD_NATIVE=...`, same pattern as `CIRCUITPY_ENABLE_MPY_NATIVE`.
A board turns it on with `CIRCUITPY_LOAD_NATIVE = 1` in `mpconfigboard.mk`
(the M0 and M4 moved from the header define to this; the M0 links to the same
253,048 bytes either way). Commit `1fae66ee3f` on `loader-only-native`.

### ARM: same core patch, no new coupling

| Board | Stock | Loader-only | Full emitter | Shim (viper, ms) |
|---|---|---|---|---|
| Metro RP2040 | 982,576 | +3,036 (+0.3%) | +48,296 (+4.9%) | 422 |
| Metro RP2350 | 917,704 | +2,876 (+0.3%) | +45,548 (+5.0%) | 281 |
| Feather nRF52840 | 659,856 | +2,432 (+0.4%) | +28,352 (+4.3%) | 844 |
| Feather STM32F405 | 671,800 | +2,444 (+0.4%) | +28,352 (+4.2%) | 437 |

`firmware.bin` bytes, same tree and GCC 14.2.1 per board. Loader-only images
have `mp_native_relocate` and no `emit_native_thumb` / `asm_thumb_` symbols
(the RP2 emitter is bigger because that port builds without LTO). All four
flashed and run: RP2350 by 1200-baud touch and UF2, nRF52840 and STM32F405
over SWD (`bravo:~/turbo/loader-run.sh`). Board flags committed as
`11b6fe3cde`. The `@native` (non-viper) `pixels.native.mpy` also runs on all
six ARM boards (`native-mpy-check.sh`): RP2040 4777, RP2350 2378, nRF52840
7465, STM32F405 2832, M4 3567, M0 23570 ms, checksum 407644, matching the
farm table's `@native` column.

### Xtensa: three more couplings (`esp32-native` branch)

Cherry-picked the two core commits (without the SAMD board hunks) onto
`esp32-native`, then commit `75a3403038`:

- `py/persistentcode.h`: the `xtensa`, `xtensawin` and `rv32` branches of the
  `MPY_FEATURE_ARCH` chain now also fire for `MICROPY_LOAD_NATIVE` on the
  matching compiler target (`__xtensa__`, `__XTENSA_WINDOWED_ABI__`,
  `__riscv && __riscv_xlen == 32`), as the thumb branch already did.
- `ports/espressif/mpconfigport.h` and `supervisor/port.c`: the
  executable-RAM commit hook (`MP_PLAT_COMMIT_EXEC` ->
  `esp_native_code_commit`) and its VM-teardown free were gated on
  `CIRCUITPY_ENABLE_MPY_NATIVE`. The loader path calls it too (relocated code
  first lands in the GC heap or PSRAM, neither executable). Without it the
  S3 link fails on `persistentcode.o`.
- `ports/espressif/Makefile` and `tools/check-sdkconfig.py`: the
  `sdkconfig-native.defaults` (`CONFIG_ESP_SYSTEM_MEMPROT=n`) and its guard
  now apply for either flag.
- `py/mpconfig.h` (`8c69e71fa9`, also `a80fa21afb` on `loader-only-native`):
  `MICROPY_EMIT_NATIVE_PRELUDE_SEPARATE_FROM_MACHINE_CODE` was
  `(MICROPY_EMIT_XTENSAWIN)` with no `#ifndef`, so the loader-only build got 0
  and `persistentcode.c` read the prelude of every loaded `@native` `.mpy`
  byte-wise out of IRAM. Windowed Xtensa cannot: the first call of a native
  (non-viper) function took a LoadStoreError and the board reset, which the
  gate saw as the tty vanishing during `mandel_nat`. Viper functions carry no
  prelude, so the viper shim had passed on both boards and hidden it. Now
  keyed on `MICROPY_EMIT_XTENSAWIN || (MICROPY_LOAD_NATIVE &&
  defined(__XTENSA_WINDOWED_ABI__))`. Lesson for the ESP32-C5 and any other
  port: the shim exercises viper only; run a `@native` `.mpy` too.

| Board | Loader-only | Full emitter | Shim (viper, ms) |
|---|---|---|---|
| Metro ESP32-S3 | 2,007,920 (4,672 under stock: memprot code out) | 2,028,320 | 186 |
| Metro ESP32-S2 | 1,649,744 | 1,664,768 | 225 |

Both flashed app-only with esptool at `0x10000` (`esp-flash-app-any.sh S2|S3`;
`on_next_reset(BOOTLOADER)` lands both in ROM download mode, `303a:0002` /
`303a:0009`, not TinyUF2). Filesystems intact. Board flags committed as `b33b3e726b`. The C5 branch
(`esp32-native-c5`) still needs a rebase onto this; the RISC-V arch line is
in but not built.

### ESP regression gate, loader-only, 2026-09-06

`esp-run.sh` on both boards after the prelude fix (`8c69e71fa9`):

| | ESP32-S3 | ESP32-S2 |
|---|---|---|
| mandel float / int bytecode, us | 4,873,718 / 3,410,034 | 7,506,958 / 4,328,735 |
| mandel `@native` / `@viper` .mpy, us | 1,692,321 / 171,783 | 2,106,689 / 205,780 |
| on-board `@viper` compile | SyntaxError (expected) | SyntaxError (expected) |
| wrong-arch .mpy / 920 KB viper | ValueError / MemoryError, alive | ValueError / MemoryError, alive |
| burn set | 40/40 | 40/40 |
| pidigits score, loader-only | 932 to 940 (3 runs) | 450 (3 runs, spread 0.2%) |
| pidigits score, stock 10.3.0 | 870 to 887 | 486 to 487 |
| pidigits score, emitter build | not measured | 546 to 548 |

Before the prelude fix the gate had caught the native fault (tty vanished
during `mandel_nat` on both boards). Viper is 8% faster on the S3 than on
the emitter build (172 vs 186 ms); the S2 is unchanged (206 ms).

**Open: S2 pidigits.** Four S2 images whose bytecode mandelbrot agrees to
0.1% give pidigits 481 (first loader image, `be5c582bff`), 450 (current
loader image), 486 (stock, `CIRCUITPY_LOAD_NATIVE=0` on this tree) and 547
(emitter image, 09-05). So the current loader-only S2 is 7.5% below stock
on this one bignum-heavy benchmark, and the previous loader image was 1%
below it. The S2 has no PSRAM and runs code from flash through an 8 KB
instruction cache, so code placement moves cache-sensitive workloads by
this much between otherwise equivalent images; that is the likely
mechanism and it is not proven. The S3 (PSRAM, larger cache) shows the
opposite sign: loader-only is 6% above stock. Worth a linker-map
comparison of the `mpz_*` hot functions before any upstream claim about
S2 bytecode speed.

### Not yet converted

The two Zephyr boards (nRF54L15/LM20 on `verify/nrf54l-all`, EK-RA8D1 on
`ra8d1-turbo`) and the ESP32-C5. Same core patch; the `emitglue.c` I-cache
hunk is needed by the loader path there too, so it stays and gets attributed
rather than split out.

## Status

- [x] Patch written (10 files), on the `cp-1030` (10.3.0) tree
- [x] M4 links and fits flash (7,000 B free)
- [x] M4 loads and runs host-compiled native and viper `.mpy` (checksum 581, viper 431 ms)
- [x] Source `@viper` rejected, confirming the emitter is out
- [x] Committed to `mikeysklar/circuitpython` branch `loader-only-native` (`af32cbcb36` core, `6fdfdcc7ca` M0 board)
- [x] M0 Express fits (648 B free, safemode.py dropped) and runs host-compiled armv6m viper at 1,014 ms
- [x] `CIRCUITPY_LOAD_NATIVE` make flag (`1fae66ee3f`)
- [x] RP2040, RP2350, nRF52840, STM32F405 built, flashed, shim verified, flags committed (`11b6fe3cde`)
- [x] ESP32-S2 and S3 on `esp32-native`: arch selection, commit-exec hook and memprot gates on the flag (`75a3403038`), flags committed (`b33b3e726b`), shim verified
- [x] ESP regression gate on loader-only (`bravo:~/turbo/esp-results/{S3,S2}-loader2`): see below
- [ ] Zephyr boards and the C5 branch
- [ ] Split the I-cache lines out of `emitglue.c` before an upstream PR (or keep and attribute: the loader needs them on Zephyr)
- [ ] Decide upstreamability (clean single macro; a candidate for Adafruit)

Board state after: all eight farm boards run loader-only firmware with the
shim files on CIRCUITPY, not the farm idle sketch. Backups:
`bravo:~/backup-m4-loaderonly-20260905-194241/`,
`bravo:~/backup-m0-loaderonly-20260905-201331/`,
`bravo:~/turbo/backup-rp2040-loader-20260906-102936/`,
`bravo:~/turbo/backup-{rp2350,nrf52840,stm32f405}-loader-20260906-*/`;
the ESP boards kept their filesystems (app-only flash).
