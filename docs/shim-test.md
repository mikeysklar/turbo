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
| Metro ESP32-S3 | | | not run: board held by the ESP32 branch work | | |

All three shim branches are covered: arch dir present, no arch reported, arch
reported but no directory. Speedups match the farm report within a few percent
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
