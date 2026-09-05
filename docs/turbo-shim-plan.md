# Turbo shim plan, 2026-09-05

Principle: everything lives outside the core. CP already has the emitter behind
`CIRCUITPY_ENABLE_MPY_NATIVE=1`. Our repo builds it, our tool compiles for it,
our shim picks the file on the board, our tracker takes the bugs.

## Three layers

- adafruit/circuitpython (maintainers): nothing required. Optional: one-block
  Cortex-M0+ bug fix now; one line per board to flip the flag, later, with data.
  ESP32 goes to an issue, not a PR.
- adafruit/turbo (us): Actions workflow builds CP at each release tag with the
  flag for supported boards, publishes UF2s. Shim `lib/turbo.py`. CLI
  `adafruit-turbo` (build / bench / check / pack). Examples, docs, issues.
  Triage rule: reproduce on stock before filing upstream.
- Users: drag turbo UF2, `@turbo.viper` on the hot function, `turbo build`,
  copy `lib/` + `src/`. Or one combined UF2 via `turbo pack`. Same project runs
  on stock firmware as bytecode.

## Answers to the thread's concerns

- Arch clarity: `lib/turbo/<arch>/`, shim picks by `sys.implementation._mpy`,
  loader refuses wrong arch, manifest records arch + mpy ABI.
- Fragile linking: not used. mpy-cross emitter output only, no native C
  modules, no mpy_ld.
- Source: always in `/src`, sha256 in manifest. Delete `.mpy`, source runs.
- `.py` beats `.mpy`: solved by layout (src off the path), no loader change.
- Bug load: turbo firmware self-identifies (`_mpy >> 10` nonzero); issue
  template asks for it.

## Status

- Done: 4-board native firmware at 10.3.0, measurements (viper 19-36x),
  shim, CLI build/bench/check, one-UF2 demo.
- Not started: repo + Actions, `turbo pack`, pip package, docs.
- Waiting: M0+ fix PR (needs hardware repro), ESP32 branch (other session).

## Plan

- Weeks 1-2: repo, CI for 4 boards at 10.3.0, finish 8-board shim test,
  restore farm, README.
- Weeks 3-4: `turbo pack`, pip package, 3 more examples (LED colour math,
  CRC/packet, dither), M0+ fix PR, Learn guide draft.
- After: ESP32 issue with farm numbers, ask core to flip flag on boards with
  headroom once used, Community Bundle entry.

## Decisions for boss

1. Repo home: recommend adafruit/turbo.
2. Day-one boards: RP2040, RP2350, nRF52840, STM32F405 families. Skip SAMD.
3. M0+ fix PR now: recommend yes after hardware repro.
4. ESP32 public: after farm numbers; issue not PR.

## Risks

- Flash: 15-91 KB; SAMD out for now.
- Per-release rebuild and mpy ABI match: CI matrix + manifest check.
- Support load is ours by design.
- Expectation gap: 20-36x on int loops over buffers, nothing on I/O/float/str.
