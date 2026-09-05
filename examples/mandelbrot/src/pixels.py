from turbo import turbo


@turbo.viper
def mandel_row(out: ptr8, width: int, dx: int, cy: int, max_iter: int):
    # fixed point, 12 fractional bits, integers only so viper can take it
    for px in range(width):
        cx = px * dx - (2 << 12)
        x = 0
        y = 0
        i = 0
        while i < max_iter:
            x2 = (x * x) >> 12
            y2 = (y * y) >> 12
            if x2 + y2 > (4 << 12):
                break
            y = ((x * y) >> 11) + cy
            x = x2 - y2 + cx
            i += 1
        out[px] = i


def _turbo_bench():
    W, H, IT = 160, 120, 64
    row = bytearray(W)
    dx = (3 << 12) // W
    total = 0
    for r in range(H):
        mandel_row(row, W, dx, ((r * 2) << 12) // H - (1 << 12), IT)
        total += sum(row)
    return total
