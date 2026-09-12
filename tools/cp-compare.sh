#!/bin/bash
# Deterministic A/B firmware compare: clean-build one board in two existing trees with the version string and build
# date pinned (jepler's SOURCE_DATE_EPOCH + CP_VERSION), then report size, sha256, differing bytes, and per-symbol
# size changes. No git work: point it at trees you already have checked out (e.g. ~/cp-1030 and ~/wt-arm-pr).
# Extra make args go to both builds. ESP-IDF stamps its own app descriptor, so espressif may never come out identical.
# usage: cp-compare.sh <board> <port> <tree-a> <tree-b> [make args...]   e.g. TRANSLATION=ja CIRCUITPY_LOAD_NATIVE=1
# exit: 0 identical, 1 differ, 2 build failed
export PATH=$HOME/arm-toolchain/bin:$HOME/.local/bin:$PATH
set -u
[ $# -ge 4 ] || { sed -n 2,7p "$0"; exit 2; }
B=$1 P=$2 A=$(realpath "$3") Z=$(realpath "$4"); shift 4
PIN="SOURCE_DATE_EPOCH=0 CP_VERSION=10.99.99-i-love-determinism"
NM=${NM:-arm-none-eabi-nm}
BD=build-$B-cpc; LOG=~/turbo/logs/cp-compare; mkdir -p $LOG
echo "board $B  port $P  gcc $(arm-none-eabi-gcc -dumpversion)  args: ${*:-none}"
build() { # tag tree
  local t=$1 d=$2 L=$LOG/$B-$1.log; shift 2
  echo "$t $d  $(git -C $d rev-parse --short=10 HEAD) dirty=$(git -C $d status --short --untracked-files=no | wc -l)"
  [ -x $d/mpy-cross/build/mpy-cross ] || make -C $d/mpy-cross -j$(nproc) > $LOG/$B-$t-mpy-cross.log 2>&1 \
    || { echo "$t mpy-cross FAILED, see $LOG/$B-$t-mpy-cross.log"; exit 2; }
  rm -rf $d/ports/$P/$BD
  make -C $d/ports/$P BOARD=$B BUILD=$BD $PIN "$@" -j$(nproc) > $L 2>&1 \
    || { echo "$t build FAILED, see $L"; tail -3 $L; exit 2; }
  grep -q "10.99.99-i-love-determinism" $d/ports/$P/$BD/firmware.bin \
    || { echo "$t pinned version string not in firmware.bin, flags did not take"; exit 2; }
}
build A $A "$@"; build B $Z "$@"
FA=$A/ports/$P/$BD/firmware.bin FB=$Z/ports/$P/$BD/firmware.bin
printf "A %8d B  %s\nB %8d B  %s\n" $(stat -c%s $FA) $(sha256sum $FA | cut -c1-16) $(stat -c%s $FB) $(sha256sum $FB | cut -c1-16)
if cmp -s $FA $FB; then echo "IDENTICAL"; exit 0; fi
echo "DIFFER: $(cmp -l $FA $FB 2>/dev/null | wc -l) bytes differ in the common length"
echo "symbol size changes (B - A), largest first:"
python3 - <($NM -S --defined-only ${FA%.bin}.elf) <($NM -S --defined-only ${FB%.bin}.elf) <<'EOF'
import sys, collections
def load(p):
    s = collections.Counter()
    for line in open(p):
        f = line.split()
        if len(f) == 4:
            s[f[3]] += int(f[1], 16)
    return s
a, b = load(sys.argv[1]), load(sys.argv[2])
d = [(b[k] - a[k], k) for k in set(a) | set(b) if a[k] != b[k]]
for delta, k in sorted(d, key=lambda x: -abs(x[0]))[:40]:
    tag = " (new)" if k not in a else " (gone)" if k not in b else ""
    print("  %+6d  %s%s" % (delta, k, tag))
print("  %d symbols changed, net %+d bytes" % (len(d), sum(x[0] for x in d)))
EOF
exit 1
