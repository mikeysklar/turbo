import time
import turbo
import pixels

t0 = time.monotonic_ns()
v = pixels._turbo_bench()
ms = (time.monotonic_ns() - t0) // 1_000_000
print("arch=%s path=%s file=%s checksum=%d ms=%d" % (
    turbo.arch, turbo.path, getattr(pixels, "__file__", "?"), v, ms))
print("TURBO-SHIM-DONE")
