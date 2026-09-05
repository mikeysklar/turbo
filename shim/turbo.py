# turbo: run compiled .mpy where the firmware can, source everywhere else.
# Pure Python. Puts one directory at the front of sys.path based on the
# native arch the firmware reports in sys.implementation._mpy.
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
    if arch:
        d = "/lib/turbo/" + arch
        try:
            os.stat(d)
            return d
        except OSError:
            pass
    return "/src"


path = _pick()
if sys.path[0] != path:
    sys.path.insert(0, path)
