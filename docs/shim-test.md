# Shim test, eight-board farm, 2026-09-05

Same three files on every board: `lib/turbo.py` (the shim), `src/pixels.py`
(the source, `@turbo.viper` on `mandel_row`), and `lib/turbo/<arch>/pixels.mpy`
for `armv6m` and `armv7emsp`, built by `turbo_cli.py build`. `code.py` imports
`turbo`, then `pixels`, runs `_turbo_bench()` (mandelbrot 160x120x64) and prints
which file was imported. Driven over the raw REPL by `tools/farm/deploy-test.sh`.

Expected: a native-firmware ARM board imports from `lib/turbo/<its arch>/`; a
stock board, or one whose arch has no compiled directory, imports `/src/pixels.py`.
Every path must produce checksum 407644.

| Board | Firmware | `turbo.arch` | Imported from | Checksum | ms |
|---|---|---|---|---|---|
| Metro RP2040 | 10.3.0 + flag | `armv6m` | `/lib/turbo/armv6m/pixels.mpy` | 407644 | 422 |
| Metro RP2350 | 10.3.0 + flag | `armv7emsp` | `/lib/turbo/armv7emsp/pixels.mpy` | 407644 | 281 |
| Feather nRF52840 | 10.3.0 + flag | `armv7emsp` | `/lib/turbo/armv7emsp/pixels.mpy` | 407644 | 848 |
| Feather STM32F405 | 10.3.0 + flag | `armv7emsp` | `/lib/turbo/armv7emsp/pixels.mpy` | 407644 | 437 |
| Metro M0 Express | 10.3.0 stock | `None` | `/src/pixels.py` | 407644 | 44282 |
| Metro M4 AirLift | 10.3.0 stock | `None` | `/src/pixels.py` | 407644 | 6789 |
| Metro ESP32-S2 | 10.3.0 stock | `None` | `/src/pixels.py` | 407644 | 4346 |
| Metro ESP32-S2 | esp32-native branch | `xtensawin` | `/src/pixels.py` (no dir for arch) | 407644 | 4347 |
| Metro ESP32-S3 | esp32-native branch (fixed) | `xtensawin` | `/lib/turbo/xtensawin/pixels.mpy` | 407644 | 186 |

All three shim branches are covered: arch dir present (ARM and xtensawin), no
arch reported, and arch reported but no directory (S2 on the branch firmware). Speedups match the farm report within a few percent
(the shim adds one `os.stat` and a `sys.path` insert at import).

`turbo_cli.py bench` on the two RP2 boards, 5 trials, all variants checksum
407644, winner installed:

| Board | arch | bytecode ms | native ms | viper ms | installed |
|---|---|---|---|---|---|
| Metro RP2040 | `armv6m` | 8334.5 | 4777.5 | 422.4 | viper, 19.7x |
| Metro RP2350 | `armv7emsp` | 4602.7 | 2401.2 | 282.0 | viper, 16.3x |

Raw output: `bravo:~/turbo/shim/results/`. Manifest: `bravo:~/turbo/shim/lib/turbo/turbo.json`.

## `pack` end to end, Metro RP2350, 2026-09-05

Firmware from release `cp-10.3.0` on this repo (CI build, GCC 15.2.1), project
= `examples/mandelbrot` plus the built `lib/turbo/` tree from the bench above.

```
turbo_cli.py pack packproj --board adafruit_metro_rp2350 \
    --firmware adafruit-circuitpython-adafruit_metro_rp2350-turbo-10.3.0.uf2 -o rp2350-shim.uf2
combined: 3781 firmware blocks + 224 filesystem blocks
packed rp2350-shim.uf2 (2050560 bytes), 4 candidate files dropped, 1 compiled modules
```

1200-baud touch, copy to the `RP2350` bootloader volume, CIRCUITPY back in 9 s.
`boot_out.txt`: `Adafruit CircuitPython 10.3.0 on 2026-09-05; Adafruit Metro RP2350 with rp2350b`.
Filesystem held exactly `code.py`, `lib/turbo.py`, `lib/turbo/turbo.json`,
`lib/turbo/{armv6m,armv7emsp}/pixels.mpy`, `src/pixels.py`; the `.native.mpy`
and `.viper.mpy` candidates were dropped as intended.

```
sys.implementation._mpy = 7942, arch id 7 (armv7emsp)
arch=armv7emsp path=/lib/turbo/armv7emsp file=/lib/turbo/armv7emsp/pixels.mpy checksum=407644 ms=280
```

Same checksum and time as the bravo-built firmware (281 ms). `--self-extract`
also produced a 6822-byte `code.py` for boards without a UF2 bootloader; not
run on hardware yet. A stale source (edited after `build`) makes `pack` exit 1.

Board state after: RP2350 on the CI turbo firmware with this project, not the
farm idle sketch. Backup: `bravo:~/turbo/backup-rp2350-20260904-181024/`.

## ESP32-S3 recovery and compiled run, 2026-09-05

The farm S3 had been left wedged by the first ESP32 native build (commit
`4f51255`, before the pointer-bit fix), which hard-faulted on the first native
call and left the board presenting only its USB-Serial-JTAG device, silent, not
reachable by REPL or by esptool's auto download-mode entry.

Recovery: power cycle with `-r 80 -w 300`, then a physical BOOT-button press to
force ROM download mode. Once esptool connected, the fixed build's `firmware.uf2`
(commit `4484b98`, the `MICROPY_MAKE_POINTER_CALLABLE` fix) was installed the
correct way for this board, dragged onto the TinyUF2 `METROS3BOOT` volume, not
flashed at `0x0`. CircuitPython came back, formatted CIRCUITPY on first boot,
and the fix verified on-board:

```
sys.implementation._mpy = 11014  (arch id 10, xtensawin)
@micropython.viper  f(7)   -> 22     (hard-faulted before the fix)
@micropython.native g(100) -> 4950
```

xtensawin `pixels.mpy` built with `turbo_cli.py build --arch xtensawin` using
the branch's mpy-cross, deployed with the shim, and run:

```
arch=xtensawin path=/lib/turbo/xtensawin file=/lib/turbo/xtensawin/pixels.mpy checksum=407644 ms=186
```

186 ms is the fastest cell on the farm, ahead of the RP2350's 281 ms, about 26x
over the S3's 4873 ms float bytecode. Board state after: S3 on the fixed native
build with the shim project on CIRCUITPY.

Full S3 tier sweep, 2026-09-05, same module three ways, 8 trials each, spread
under 2 ms, checksum 407644 on all three:

| Tier | S3 median | vs float bytecode |
|---|---|---|
| float bytecode (`mandel_flt`) | 4873 ms | 1.0x |
| `@micropython.native` (`pixels.native.mpy`) | 1708 ms | 2.85x |
| `@micropython.viper` (`pixels.mpy`) | 186 ms | 26.2x |

Native turns the loop into machine code while values stay Python objects;
viper makes the values machine words. The 2.85x / 26.2x split matches every
ARM board on the farm.
