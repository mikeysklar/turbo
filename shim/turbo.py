# turbo: run compiled .mpy where the firmware can, source everywhere else.
# Pure Python. Puts the native arch directory (from sys.implementation._mpy)
# at the front of sys.path, with /src right behind it, so a module missing
# from the arch directory still imports from source.
import os
import sys

_ARCH = {4: "armv6m", 5: "armv7m", 6: "armv7em", 7: "armv7emsp", 8: "armv7emdp",
         9: "xtensa", 10: "xtensawin", 11: "rv32imc"}

arch = _ARCH.get(getattr(sys.implementation, "_mpy", 0) >> 10)


class _Turbo:
    # identity decorators: @turbo, @turbo.native, @turbo.viper are markers for
    # the host CLI; on the board they change nothing. (Functions cannot take
    # attributes in MicroPython, hence the instance.)
    def __call__(self, f):
        return f

    def native(self, f):
        return f

    def viper(self, f):
        return f


turbo = _Turbo()


def _pick():
    paths = ["/src"]
    if arch:
        d = "/lib/turbo/" + arch
        try:
            os.stat(d)
            paths.insert(0, d)
        except OSError:
            pass
    return paths


paths = _pick()
path = paths[0]  # where a compiled module comes from, if any; kept for callers
for _p in reversed(paths):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
del _p
