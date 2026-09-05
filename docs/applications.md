# Where turbo helps

Measured on Metro RP2350, 2026-09-04, see `work.log.md`: `@micropython.native`
gave 1.9x over int bytecode and 2.7x over float bytecode; `@micropython.viper`
gave 17.4x and 24.4x. Native compiles the control flow but keeps every value as
a Python object and calls the runtime for each `*`, `>>`, `+`. Viper turns
`int` locals into machine words and `ptr8/16/32` into raw pointers, so the
arithmetic becomes single instructions. The speedup lives where that
representation change applies: integer and bit math over memory buffers.

| Workload | Viper fit | Why |
|---|---|---|
| Fractals, plasma, cellular automata, particles | good, if written fixed-point | pure int loops over a buffer, exactly the mandelbrot case |
| Image scaling, rotation, dithering, convolution | good | byte/pixel math via `ptr8`/`ptr16`, integer indices |
| LED mapping, color math, gamma, HSV to RGB | good | small ints, lookup tables, bit packing |
| CRC, checksums, packet parsing, FEC, bit-unpacking | good | shifts, masks, XOR over `ptr8`. Though `binascii.crc32` is already C |
| Compression / codecs (RLE, LZ-ish) | good | byte loops |
| Tiny ML inference | int8-quantized yes, float no | viper has no float type at all |
| FFT, FIR, biquad, mixing | only in fixed-point (Q15/Q31) | float versions can't be viper; `ulab` already does float vectors in C |
| Sensor fusion, Kalman, inverse kinematics | no | float-heavy, small matrices. Native's ~2x is the ceiling, or hand-convert to fixed-point |
| Crypto, hashes | good in principle | but `hashlib`, `aesio` are already C, so little left to win |
| Anything on I2C/SPI/UART/USB/WiFi/`sleep` | none | waiting isn't CPU. Same for `displayio`, `audiocore`, `neopixel_write`: already C |
| String, dict, list, object work, allocation | none | those are Python objects; viper hands them back to the runtime |

## Two nuances

**`@micropython.native` is the general win, viper is the targeted one.** Native
works on any Python, floats included, for roughly 2x. Viper is 10-25x but only
on code already rewritten into ints and pointers, which is a real porting
effort and changes the numerics: 32-bit wrap, fixed-point rounding (the
mandelbrot checksum moved from 581 to 576 going float to fixed-point).

**The flag also turns on inline assembly.** `CIRCUITPY_ENABLE_MPY_NATIVE=1`
sets `MICROPY_EMIT_INLINE_THUMB` too (`py/circuitpy_mpconfig.h:73`), so
`@micropython.asm_thumb` functions work. That is the escape hatch for viper's
remaining overhead: the emitter keeps only one local in a register and spills
the rest to the stack, which is why the viper mandelbrot loop is 96 cycles per
iteration instead of ~20. A hand-written inner loop keeps its values in
registers. Nobody wants to write it, but for one hot kernel it is the only way
past the emitter.

## Framing for the thread

A big win for the graphics, LED, codec and protocol half of the list. A modest
one for float DSP and sensor math. Nothing for I/O. ARM only until someone
wires up `MICROPY_EMIT_XTENSAWIN` for the ESP32 boards.
