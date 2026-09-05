# `turbo analyze`, 2026-09-05

Static triage. Reads a `.py` file or a project folder on the host, grades each
function by shape, and says whether turbo is worth the trouble. No board, no
serial, no mpy-cross.

```
turbo_cli.py analyze SRC [--arch A | --board B] [--json]
```

It answers "is this the kind of code viper is good at". It does **not** answer
"is this where the time goes". A perfect-looking function that runs once at
boot is 0x. `bench` is still the only thing that measures.

## Verdicts

| Verdict | What it means | What to do |
|---|---|---|
| `viper` | Loop, integer math, buffer indexing, nothing that forces objects | `@turbo.viper`, add `ptr8`/`int` annotations, `build` |
| `fixed-point` | Same shape but float math, and the floats are only `+ - * /` and comparisons | Rewrite to scaled integers first, then `@turbo.viper` |
| `native` | Loop-heavy but touches objects, calls Python functions, or allocates | `@turbo.native`, expect single digits |
| `skip` | No loop, I/O bound, or no arithmetic | Nothing. Turbo will not help |

The `fixed-point` bucket exists because the farm's 26.2x came from a rewrite,
not from viper eating float code. `examples/mandelbrot/src/pixels.py` is
integer-only with 12 fractional bits; the 4873 ms baseline it beat was
`mandel_flt`, the float form of the same loop. A tool that greps for floats and
says "skip" gives backwards advice on exactly that shape. Analyze flags it, and
says plainly that it will not do the rewrite for you.

## Where the numbers come from

`MEASURED` in `cli/turbo_cli.py`, sourced from `docs/shim-test.md`:

| arch | viper | native | measured on |
|---|---|---|---|
| `armv6m` | 19.7x | - | Metro RP2040 |
| `armv7emsp` | 16.3x | - | Metro RP2350 |
| `xtensawin` | 26.2x | 2.85x | Metro ESP32-S3 |

No entry, no number. An arch we have not run prints the verdict and "no
measurement for <arch> yet". Nothing is interpolated between architectures.
Numbers are always phrased as "similar loops ran Nx on <board>", never as a
prediction for your code.

`--board` accepts the five farm board ids and resolves to an arch. Anything
else, use `--arch`.

## Signals it reads

Per function, over the AST: loop nesting depth; integer ops (`+ - * // %`,
shifts, bitwise); float ops (float literals, true `/`, `math.*`, `float()`);
indexing into a parameter or a name bound to `bytearray`/`array`/`memoryview`;
and the things that rule viper out - calls to other Python functions, method
calls and attribute access on objects, container growth in the loop, string
work, f-strings, `try`, `yield`, `**`, comprehensions and literals that
allocate inside the loop.

Anything it cannot see through lands in a lower bucket, never a higher one.

## What it cannot see

- **Hotness.** The only proxy is whether a function is called from inside a
  loop somewhere in the same file. Cross-module call sites are invisible, so
  a viper candidate may be annotated "never called in this file" when it is in
  fact the hot one.
- **I/O placement.** Any `print`, `time.sleep`, or `board`/`busio`/`digitalio`
  use anywhere in the function sends it to `skip`, even when the I/O sits
  outside the hot loop. Move the I/O out and run it again.
- **Whether the viper rewrite will compile.** `viper` means the shape fits, not
  that the annotations are written. That part is still yours.

## Example

```
$ turbo_cli.py analyze examples/mandelbrot/src/pixels.py --arch armv7emsp
turbo analyze reads shape only. It cannot see where time is actually
spent: a perfect-looking function that runs once is 0x. Measure with bench.
target: armv7emsp (Metro RP2350)

examples/mandelbrot/src/pixels.py
  mandel_row       viper        loop x2, integer math, buffer indexing
                                similar loops ran 16.3x on Metro RP2350
                                already marked @turbo.viper
  _turbo_bench     native       loop x1, calls mandel_row(); calls sum()
                                no measurement for armv7emsp yet
```

`--json` emits the same records, one per function, with `file`, `arch`,
`function`, `line`, `verdict`, `reason`, `notes`, `decorated`. Exit status is 0
unless the board or arch is unknown (2); the verdicts are advice, not a gate.
