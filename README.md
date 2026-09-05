# turbo

Making CircuitPython fast with the native and viper machine-code emitters,
across boards that shipped with bytecode only.

CircuitPython already carries `@micropython.native` and `@micropython.viper`,
but the build flag that turns them on (`CIRCUITPY_ENABLE_MPY_NATIVE=1`) is wired
for ARM Thumb only. This repo pursues two tracks:

- **ARM, no patches.** The Thumb emitter is in every tree. Building a stock
  release tag with the flag on is enough.
- **Non-ARM, via a fork.** Xtensa and RISC-V need real firmware changes. Those
  live on the `esp32-native` branch of the CircuitPython fork.

One workflow, `.github/workflows/firmware.yml`, builds both tracks and
publishes a GitHub release per CircuitPython tag with a `.uf2` for every board.
ARM boards come from the stock tag, ESP32 boards from the fork branch, and the
release notes say which is which.

## Get the firmware

Grab the `.uf2` for your board from the latest `cp-<version>` release, or from
the command line:

```sh
gh release download cp-10.3.0 -R mikeysklar/turbo -p '*metro_esp32s3*.uf2'
```

Every release also ships a matching `mpy-cross` for Linux and a `BUILD.txt`
per board recording the exact source commit, toolchain and flags.
[docs/build.md](docs/build.md) has the commands to build a new tag.

## Status

**ESP32-S2 and ESP32-S3 (Xtensa): working, verified on hardware.** Viper is
about 36x faster than float bytecode on a Mandelbrot inner loop.

**ESP32-C3 / C6 / P4 / C5 (RISC-V): compiled in, not yet run on hardware.**

| Board | Arch | Native / viper | Source | In release |
|---|---|---|---|---|
| Metro RP2040 | Thumb (armv6m) | in-tree | stock tag | yes |
| Metro RP2350 | Thumb (armv7em) | in-tree | stock tag | yes |
| Feather nRF52840 | Thumb (armv7em) | in-tree | stock tag | yes |
| Feather STM32F405 | Thumb (armv7em) | in-tree | stock tag | yes |
| Metro ESP32-S2 | Xtensa LX7 | works | fork branch | yes |
| Metro ESP32-S3 | Xtensa LX7 | works | fork branch | yes |
| ESP32-C3/C6/P4/C5 | RISC-V | untested | fork branch | not yet |

## Mandelbrot, median of 8 runs (Metro ESP32-S2)

| Variant | Time | vs float bytecode |
|---|---|---|
| float bytecode | 7.44 s | 1x |
| `@micropython.native` | 2.11 s | 3.5x |
| `@micropython.viper` | 0.206 s | 36x |

Float bytecode speed is unchanged with the emitter enabled (under 0.1%).

## The ESP32 firmware changes

Five commits on the `esp32-native` branch of the CircuitPython fork:

1. Select the native emitter by architecture, not just Thumb.
2. Commit native machine code into executable RAM (the GC heap is not executable).
3. Turn memory protection off when native code is enabled.
4. Make the Xtensa assembler compile under CircuitPython's warning flags.
5. Do not set the ARM Thumb interworking bit on non-ARM pointers.

The fifth was the actual bug: `MICROPY_MAKE_POINTER_CALLABLE` OR-ed the ARM
Thumb bit into every code pointer, which on Xtensa jumps to an odd address and
hard-faults on the first native call. It stayed latent because no non-ARM port
had ever enabled the native emitter.

## Layout

- `shim/turbo.py` — the on-board `@turbo` decorator (identity fallback on stock firmware).
- `cli/turbo_cli.py` — host tool: `analyze` a project before you start,
  `build` the `.mpy` per arch, `bench` the variants on a board and install the
  winner, `check` the manifest is fresh, `pack` firmware and project into one UF2.
- `examples/mandelbrot/` — the benchmark used for the numbers above.
- `docs/` — conversion procedure, farm notes, applications, work log,
  `analyze.md`, the verdicts and what they cannot see, and `build.md`, the
  commands to run the workflow.
- `.github/workflows/firmware.yml` — builds all six boards and publishes the
  release. Two jobs: `board` (ARM, stock tag) and `esp32` (fork branch). The
  ESP32 job also checks the emitter and the executable-RAM allocator are linked
  and that memory protection is off in the built sdkconfig.

See [ROADMAP.md](ROADMAP.md) for what is left.
