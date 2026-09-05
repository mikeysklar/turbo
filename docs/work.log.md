# turbo work log

Goal: enable CircuitPython's native emitter (`CIRCUITPY_ENABLE_MPY_NATIVE=1`,
Thumb only) on a farm board, measure the speedup on `misc_mandel.py` as
bytecode / `@micropython.native` / `@micropython.viper`, then ship py + native
mpy + firmware as one UF2 with `folder2uf2 --combine`.

First board: Metro RP2350, `3-3.3.4.2`, armv7emsp.

## Baseline, 2026-08-27, all boards on 10.3.0-alpha.4-79-gc78aa30226

From `resume-2026-08-27.md`. Score is `bm_pidigits.py`, 8-trial average,
higher is better. Run with `~/farm-tools/burn.sh` on bravo.

| Board | MCU | Core | USB path | MHz | Heap kB | Burn | score | 08-25 | delta |
|---|---|---|---|---|---|---|---|---|---|
| Metro M0 Express | SAMD21G18 | Cortex-M0+ | `3-3.3.2` | 48 | 15 | 40/40 | 228.93 | 228.9 | +0.0% |
| Metro RP2040 | RP2040 | Cortex-M0+ | `3-3.2` | 125 | 143 | 40/40 | 352.05 | 341.7 | +3.0% |
| Metro M4 AirLift | SAMD51J19 | Cortex-M4 | `3-3.3.1` | 120 | 135 | 40/40 | 405.09 | 407.2 | -0.5% |
| Feather nRF52840 | nRF52840 | Cortex-M4 | `3-3.3.3` | 64 | 119 | 40/40 | 420.16 | 418.7 | +0.3% |
| Metro ESP32-S2 | ESP32-S2 | Xtensa LX7 | `3-3.3.4.1` | 240 | 2023 | 40/40 | 507.93 | 512.5 | -0.9% |
| Metro RP2350 | RP2350B | Cortex-M33 | `3-3.3.4.2` | 150 | 399 | 40/40 | 641.17 | 649.8 | -1.3% |
| Metro ESP32-S3 | ESP32-S3 | Xtensa LX7 | `3-3.3.4.3` | 240 | 8071 | 40/40 | 865.06 | 884.4 | -2.2% |
| Feather STM32F405 | STM32F405RG | Cortex-M4 | `3-3.3.4.4` | 168 | 95 | 40/40 | 1010.46 | 1011.3 | -0.1% |


Full perf pass (`bench-run.sh`, `run-perfbench.py`) results in
`bravo:~/bench-results/perf-*.log`. RP2350 rows that matter:

```
misc_mandel.py    77312 us   score 5173.80
misc_raytrace.py 103221 us   score  484.40
misc_aes.py       57689 us   score  554.69
viper_call0..2b   SKIP        <- native disabled
```

## Progress

- [x] 1. fresh baseline on RP2350, 2026-09-04 17:58 (below)
- [x] 2. built stock + native metro_rp2350 from the 10.3.0 tag, 2026-09-04 18:07 (below)
- [x] 3. backed up (113 files), flashed native, gate passed 2026-09-04 18:12 (below)
- [x] 4. perf pass on native: viper_call0..2b all run (below). Bytecode tests swung +-10-25%, needs repeats
- [x] 5. mandelbrot float / int / native / viper on RP2350, 2026-09-04 18:31-18:45 (below). viper 24.4x over float bytecode, 17.4x over int
- [x] 6. `turbo-demo.uf2` built, flashed, demo ran from one drag, 2026-09-04 18:55 (below)
- [x] 7. RP2040 run, native build, four variants, 2026-09-04 19:10 (below). viper 36.3x over float bytecode, not 100x
- [x] 8. rest of the farm, 2026-09-04 19:50-20:40 (below). nRF52840 + STM32F405 flashed over SWD; M0 + M4 native builds overflow flash; ESP32 bytecode only

## 1. RP2350 baseline, 2026-09-04, stock 10.3.0 (2026-08-31 build)

`boot_out.txt`: `Adafruit CircuitPython 10.3.0 on 2026-08-31; Adafruit Metro RP2350 with rp2350b`
Script `bravo:~/turbo/baseline-rp2350.sh`, results `bravo:~/turbo/baseline-rp2350/`.
Whole run 33 s; each perf test is ~100 ms x 8 averages.

```
burn            40/40 (1629 testcases)
bm_pidigits     99022 us  score  656.45  (08-27 table 641.17, +2.4%)
misc_mandel     77912 us  score 5134.03
misc_raytrace   87555 us  score  571.07
misc_aes        58548 us  score  546.56
misc_pystone   118107 us  score 2540.07
viper_call0..2b SKIP x6            <- native disabled
bm_fft, core_import_mpy_*  CRASH   <- no cmath / no vfs, known, same on tip
```

## 2. Builds, 2026-09-04, `bravo:~/cp-1030` at tag `10.3.0` (`d897c15f24`)

GCC 14.2.1 (`~/arm-toolchain`). Script `bravo:~/turbo/build-rp2350.sh`, logs
`bravo:~/turbo/build-logs/`. Flag on the make line, no repo edit.

```
submodules            120 s
mpy-cross              10 s   ~/cp-1030/mpy-cross/build/mpy-cross  (mpy 6.3)
stock                  72 s   1835520 bytes   build-adafruit_metro_rp2350-stock/firmware.uf2
native                 74 s   1926656 bytes   build-adafruit_metro_rp2350-native/firmware.uf2
```

Proof the flag took: `py/emitnthumb.o` is 0 bytes in stock, 30019 bytes in
native; `nm firmware.elf | grep -c emit_native_thumb|asm_thumb_|mp_native_relocate|emit_inline_thumb`
is 0 vs 33. The 91 KB delta is the emitter.

## 3-4. Native build flashed, gate passed, 2026-09-04 18:12

Backup `bravo:~/turbo/backup-rp2350-20260904-*/` (113 files, md5 list). Flash
via 1200-baud touch, bootloader volume up in 5 s. After flash the filesystem
matched the backup except `boot_out.txt` (new build date).

`boot_out.txt`: `Adafruit CircuitPython 10.3.0 on 2026-09-04; Adafruit Metro RP2350 with rp2350b`
Results `bravo:~/turbo/native-rp2350/`.

```
                 baseline   native    delta
burn              40/40    40/40
bm_pidigits      656.45   644.78    -1.8%   control, inside 3% band
misc_mandel     5134.03  5115.53    -0.4%   no decorator yet, expected flat
misc_aes         546.56   554.51    +1.5%
misc_pystone    2540.07  2516.10    -0.9%
viper_call0        SKIP   631.17            <- emitter live
viper_call1a       SKIP   613.96
viper_call1b       SKIP   483.27
viper_call1c       SKIP   489.62
viper_call2a       SKIP   601.98
viper_call2b       SKIP   427.83

open question: bytecode-only tests that moved more than the control
bm_chaos         539.70   470.94   -12.7%
bm_float        8858.58  7955.36   -10.2%
core_locals       69.62    52.57   -24.5%
misc_raytrace    571.07   504.94   -11.6%
bm_nqueens      3761.63  4619.61   +22.8%
```

Theory, unproven: +91 KB of flash code moves hot loops relative to the 16 KB
XIP cache. Both-direction swings fit layout better than a real regression.
Needs repeat runs on native, then the stock local build as the control that
separates "local toolchain / layout" from "the flag".

## 5. Mandelbrot, four variants, native firmware, 2026-09-04

Sources `bravo:~/turbo/mandel_{flt,bc,nat,vip}.py`, compiled with
`~/cp-1030/mpy-cross/build/mpy-cross` (`-march=armv7emsp` for nat/vip), copied
to `CIRCUITPY/lib/` over the mounted drive, timed through `pyboard.py` raw REPL.
160x120, 64 max iterations, 407,644 inner iterations (counted on the host with
the same fixed-point math). 8 trials each, spread under 0.01%. Same last-row
checksum (581) on bc/nat/vip; flt gives 576, float vs fixed-point rounding.
`.mpy` header byte 2: `00` for bc/flt, `1f` (armv7emsp, sub 3) for nat/vip.

```
variant                        ms     vs flt   vs bc   ns/iter  cycles/iter @150MHz
bytecode float (mandel_flt)  6370.6    1.0x    0.7x    15628     2344
bytecode int   (mandel_bc)   4546.5    1.4x    1.0x    11153     1673
@native int    (mandel_nat)  2380.1    2.7x    1.9x     5839      876
@viper int     (mandel_vip)   260.9   24.4x   17.4x      640       96
```

Why 96 cycles and not ~20: disassembly of the 364-byte viper blob
(`arm-none-eabi-objdump -D -b binary -marm -Mforce-thumb bravo:~/turbo/vip.bin`).
Inner loop 0x98-0x132, ~65 instructions. Only `out` got a register (r4); every
other local is an `[sp, #N]` slot, and each op is ldr/mov/ldr/op/mov/str
through a scratch slot at `[sp, #8]`. Comparisons materialise 0/1 via
`cmp; ite; movgt; movle` then `cmp; beq` again. ~25 memory ops x 2 cycles +
~40 ALU/branch = ~96. This is `py/emitnative.c` behaviour, same on every port;
not caused by the flag, not fixable from the Python side beyond fewer locals.

Phillip'"'"'s 100x was RP2040 (M0+, no FPU, soft-float on heap float objects), a
much slower denominator. Direct comparison needs the same files with
`-march=armv6m` on the farm RP2040 (`3-3.2`). Not run yet.

Board state: native firmware still flashed; `lib/mandel_*.mpy` (4 files) still
on the board, needed for step 6. Backup at `bravo:~/turbo/last-backup`.

## 6. One UF2, 2026-09-04 18:55

`folder2uf2` is not on bravo, so the pack ran on the Mac:

```
folder2uf2 --board adafruit_metro_rp2350 --combine firmware-native.uf2 -o turbo-demo.uf2 turbo-demo/
combined: 3763 firmware blocks + 224 filesystem blocks
FAT16, 4 sectors/cluster, 7664 clusters, 56KB used of 15360KB
3987 blocks, flash 0x10000000..0x1010e000, family 0xe48bff59
2041344 bytes, md5 c641ed3aba35f5768bde22d9e224eb46 (matched after scp)
```

Project layout: `code.py`, `lib/mandel_{flt,bc,nat,vip}.mpy`, `src/mandel_*.py`.
Source in `/src` on purpose: `.py` beats `.mpy` in the import search, so the
source must sit off `sys.path` or it shadows the native code.

Flash: 1200-baud touch, bootloader in 5 s, CIRCUITPY back 13 s after the copy.
`boot_out.txt`: `Adafruit CircuitPython 10.3.0 on 2026-09-04; Adafruit Metro RP2350 with rp2350b`.
Console after Ctrl-D, captured over the tty:

```
mandelbrot 160x120, 64 iterations, Metro RP2350
bytecode float            6321 ms     1.0x
bytecode int              4494 ms     1.4x
@micropython.native       2379 ms     2.7x
@micropython.viper         260 ms    24.3x
```

Within 1% of the pyboard-timed step 5 numbers.

Deliverables copied beside this log: `turbo-demo.uf2`, `turbo-demo/`.

Board state: RP2350 now runs the demo firmware + filesystem, NOT farm standard.
Restore = flash the 10.3.0 release UF2 and untar `bravo:~/turbo/backup-rp2350-*/circuitpy.tar`
onto CIRCUITPY, verify against `md5.txt`.

## 7. RP2040, 2026-09-04

Board `3-3.2`, stock `10.3.0 on 2026-08-31`, backup `bravo:~/turbo/backup-rp2040-20260904-185924/` (37 files).
Build `build-adafruit_metro_rp2040-native`, 71 s, 2061824 bytes, `emitnthumb.o` 31687 B.
`.mpy` via `mpy-cross -march=armv6m`, header byte 2 = `13` (ARMV6M, sub 3).
Flash: touch, `RPI-RP2` in 5 s, back in 13 s, `boot_out.txt` = `10.3.0 on 2026-09-04`.
Harness `bravo:~/turbo/time-mandel.py`, 160x120x64, 8 trials, spread <0.02%.

```
variant           stock fw ms   native fw ms   vs flt   vs bc   cycles/iter @125MHz   RP2350 native ms
bytecode float      14027.4       13941.6       1.0x    0.6x      4275                 6370.6
bytecode int         8292.4        8295.7       1.7x    1.0x      2544                 4546.5
@native int             -          4738.6       2.9x    1.8x      1453                 2380.1
@viper int              -           383.9      36.3x   21.6x       118                  260.9
```

Stock vs native firmware, bytecode: +0.04% / -0.6%. No layout effect on RP2040.
Phillip'"'"'s 108x (5.2 s -> 48 ms) not reproduced: 36x here with a float baseline.
His source is unknown, so the gap is unexplained, not refuted.

Latent bug, from reading, not run: `MICROPY_EMIT_THUMB_ARMV7M` defaults to 1
(`py/mpconfig.h:477`) and nothing in CircuitPython sets it to 0 for Cortex-M0+
(RP2040, SAMD21). `asm_thumb_allow_armv7m()` (`py/asmthumb.h:83`) returns it,
so a `@native`/`@viper` function compiled ON THE BOARD from `.py` would emit
Thumb-2 on an M0+. Host-compiled `-march=armv6m` `.mpy` is unaffected because
the loader arch comes from `__thumb2__` (`py/persistentcode.h:61-71`). Affects
winterbloom_sol too. Fix is `#define MICROPY_EMIT_THUMB_ARMV7M (0)` gated on
`__ARM_ARCH_6M__`, or per-port. Not tested on hardware (would hard fault).

Board state: RP2040 on native firmware with 4 extra `lib/mandel_*.mpy`, else
farm files intact. RP2350 on demo firmware + demo filesystem. Neither restored.

## 8. Whole farm, 2026-09-04

Stock bytecode timings ran on all six remaining boards in parallel (on-board
`monotonic_ns`, host load irrelevant), backups in `bravo:~/turbo/farm/backup-*`.
Native builds (`bravo:~/turbo/build-farm.sh`):

```
metro_m0_express           FAILED  FLASH_FIRMWARE overflowed by 19948 bytes
metro_m4_airlift_lite      FAILED  FLASH_FIRMWARE overflowed by 12804 bytes
feather_nrf52840_express   ok 63 s  emitnthumb.o 15435 B
feather_stm32f405_express  ok 56 s  emitnthumb.o 15371 B
```

Flashed over SWD with the fastcp-1030.sh recipes (`bravo:~/turbo/flash-farm.sh`):
STM32F405 `stm32f4x.cfg` @1000 kHz, `reset halt`, firmware.bin @0x08000000.
nRF52840 `nrf52.cfg` @4000 kHz, runs from `uf2extract.py` at 0x26000 and 0x27000.
The nRF check hit a stale mount (I/O error on the old CIRCUITPY7) right after
re-enumeration; the fresh mount 5 s later read `10.3.0 on 2026-09-04`. Lesson:
after an SWD flash, wait for the mount to be *re-created*, not merely present.

All boards, median of 8 trials, ms, 160x120x64, 407,644 inner iterations.
Bytecode columns from the native firmware where one exists, else stock.

```
Board      MHz  float bc   int bc   native    viper  vip/flt  vip/int  viper cyc/iter  note
M0          48   72741.0  44129.5        -        -        -        -        -       flash overflow, bytecode only
RP2040     125   13941.6   8295.7   4738.6    383.9    36.3x    21.6x      118
M4         120   11220.9   6768.1        -        -        -        -        -       flash overflow, bytecode only
nRF52840    64   20788.3  14697.4   7444.6    781.0    26.6x    18.8x      123
ESP32-S2   240    7438.0   4327.6        -        -        -        -        -       no Xtensa emitter in CP
RP2350     150    6370.6   4546.5   2380.1    260.9    24.4x    17.4x       96
ESP32-S3   240    4873.0   3410.6        -        -        -        -        -       no Xtensa emitter in CP
STM32F405  168    8120.6   5204.1   2779.2    416.0    19.5x    12.5x      171
```

Stock vs native firmware, bytecode: nRF52840 int -0.8%, float -4.8%; STM32F405
int +0.4%, float +0.8%. Layout noise, same story as the RP2350.

Open observations:
- STM32F405 viper is 171 cycles/iter vs 96-123 elsewhere with the identical
  armv7emsp blob. Memory system, not code. Cause unknown.
- ESP32-S3 has the fastest bytecode on the farm and cannot take turbo. Largest
  untapped gain if MICROPY_EMIT_XTENSAWIN were wired in.
- M0 float bytecode 72.7 s: 5.2x the RP2040. Native would help most here and
  is exactly where it does not fit.

Board state: RP2040, RP2350, nRF52840, STM32F405 on native builds; RP2350 also
on the demo filesystem; every board has mandel_*.mpy in lib/. Nothing restored.
Stale mounts CIRCUITPY8/9/10 on bravo from re-enumerations (P4 and Pico W are
CIRCUITPY8/9 legitimately).
