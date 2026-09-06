# Roadmap

## Done

- [x] ARM boards build with the flag, no patches (firmware workflow).
- [x] Xtensa windowed-ABI native + viper on ESP32-S2 / S3, verified on hardware.
- [x] Executable-RAM allocator for the espressif port.
- [x] Clean failure modes: wrong-arch `.mpy` -> `ValueError`, oversized native
      code -> `MemoryError`, neither faults.
- [x] Regression gate: 40/40 burn-set, pidigits unchanged.
- [x] Loader-only firmware on every farm board (2026-09-06): emitter out,
      2 to 3 KB loader in, same viper speed. `CIRCUITPY_LOAD_NATIVE=1` on
      `loader-only-native` (ARM) and `esp32-native` (Xtensa, RISC-V line in).
- [x] `analyze`: static triage of a project on the host, verdicts keyed to the
      farm numbers, no board needed (docs/analyze.md).
- [x] CI: one workflow builds all six boards and publishes a `cp-<tag>` release
      with a `.uf2` per board. ARM from the stock tag, ESP32-S2/S3 from the fork
      branch. Notes split by track and name both source commits.

## Next

- [x] RISC-V on hardware: ESP32-C5 runs native and viper (172 ms, 44x) on
      `esp32-native-c5`.
- [ ] RISC-V (C3 / C6 / P4): run the RV32 path on hardware.
- [ ] Add the RISC-V boards to the workflow once the RV32 path is verified.
- [ ] Loader-only on the Zephyr boards (nRF54L, EK-RA8D1) and the C5 branch.
- [ ] Switch the firmware workflow to loader-only builds.
- [ ] Cortex-M0+ bug: board-compiled viper emits Thumb-2 on a Thumb-1 core.
- [ ] Upstream PR to adafruit/circuitpython (run the tandan checklist first).
- [ ] Restore farm boards to stock 10.3.0 when done.

## Open questions

- Memory protection off lowers a security boundary. Per-chip decision, stated
  plainly in the PR rather than made by default.
- S2 IRAM budget (no PSRAM): how large a native module fits before `MemoryError`.
