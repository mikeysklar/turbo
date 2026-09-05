#!/usr/bin/env python3
"""turbo_cli: compile @turbo-decorated CircuitPython modules to native .mpy,
bench the candidates on a board, install the winner, keep a manifest.

    turbo_cli.py build  SRC_DIR [--out lib/turbo] [--mpy-cross PATH] [--arch a,b]
    turbo_cli.py bench  MODULE --port TTY --mount CIRCUITPY [--out lib/turbo] [--trials N]
    turbo_cli.py check  SRC_DIR [--out lib/turbo]
    turbo_cli.py pack   PROJECT --board B --firmware FW.uf2 [-o out.uf2]
    turbo_cli.py pack   PROJECT --self-extract [-o code.py]

Conventions: a module opts in with `from turbo import turbo` and `@turbo`,
`@turbo.native` or `@turbo.viper` on functions. It may define `_turbo_bench()`
returning a comparable value; bench times it and rejects variants whose value
differs from bytecode. The shim (lib/turbo.py) picks the arch dir at runtime.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ARCHES = ["armv6m", "armv7emsp"]
ARCH_ID = {"armv6m": 4, "armv7m": 5, "armv7em": 6, "armv7emsp": 7, "armv7emdp": 8,
           "xtensa": 9, "xtensawin": 10, "rv32imc": 11}
DECO = re.compile(r"^(\s*)@turbo(\.native|\.viper)?\s*$")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def rewrite(src_text, tier):
    """Return source with @turbo lines rewritten for `tier` ('native'|'viper'),
    or None if the module has no @turbo decorators.

    viper tier: @turbo.viper -> @micropython.viper, everything else -> native.
    native tier: every @turbo* -> @micropython.native.
    """
    out, n = [], 0
    for line in src_text.splitlines(keepends=True):
        m = DECO.match(line)
        if m:
            n += 1
            want = "viper" if (tier == "viper" and m.group(2) == ".viper") else "native"
            line = "%s@micropython.%s\n" % (m.group(1), want)
        out.append(line)
    return "".join(out) if n else None


def compile_variant(mpy_cross, text, name, arch, dest):
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, name + ".py")
        with open(src, "w") as f:
            f.write(text)
        r = subprocess.run([mpy_cross, "-march=" + arch, src, "-o", dest],
                           capture_output=True, text=True)
    if r.returncode:
        return r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "mpy-cross failed"
    return None


def load_manifest(out):
    p = os.path.join(out, "turbo.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}


def save_manifest(out, m):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "turbo.json"), "w") as f:
        json.dump(m, f, indent=2, sort_keys=True)
        f.write("\n")


def cmd_build(a):
    manifest = load_manifest(a.out)
    for fn in sorted(os.listdir(a.src)):
        if not fn.endswith(".py"):
            continue
        name = fn[:-3]
        path = os.path.join(a.src, fn)
        text = open(path).read()
        if rewrite(text, "native") is None:
            print("%-14s no @turbo, skipped" % name)
            continue
        entry = manifest.setdefault(name, {})
        entry["src"] = os.path.relpath(path)
        entry["sha256"] = sha256(path)
        for arch in a.arch.split(","):
            d = os.path.join(a.out, arch)
            os.makedirs(d, exist_ok=True)
            built = {}
            for tier in ("viper", "native"):
                dest = os.path.join(d, "%s.%s.mpy" % (name, tier))
                err = compile_variant(a.mpy_cross, rewrite(text, tier), name, arch, dest)
                if err:
                    built[tier] = "failed: " + err
                    if os.path.exists(dest):
                        os.remove(dest)
                else:
                    built[tier] = os.path.getsize(dest)
            # install a default until bench picks: viper if it compiled, else native
            pick = "viper" if isinstance(built.get("viper"), int) else \
                   "native" if isinstance(built.get("native"), int) else None
            arch_entry = entry.setdefault(arch, {})
            arch_entry["candidates"] = built
            if pick:
                shutil.copyfile(os.path.join(d, "%s.%s.mpy" % (name, pick)),
                                os.path.join(d, name + ".mpy"))
                arch_entry["installed"] = pick
                arch_entry["measured"] = arch_entry.get("measured", False)
            print("%-14s %-10s %s -> installed %s" % (name, arch, built, pick))
    save_manifest(a.out, manifest)


def board_exec(pyb, code, timeout=600):
    return pyb.exec_(code, timeout=timeout).decode().strip()


def cmd_bench(a):
    sys.path.insert(0, a.pyboard_tools)
    import pyboard  # from a CircuitPython/MicroPython tree

    manifest = load_manifest(a.out)
    entry = manifest.get(a.module)
    if not entry:
        sys.exit("no manifest entry for %s; run build first" % a.module)

    pyb = pyboard.Pyboard(a.port, 115200)
    pyb.enter_raw_repl()
    mpy = int(board_exec(pyb, "import sys; print(sys.implementation._mpy)"))
    arch = {v: k for k, v in ARCH_ID.items()}.get(mpy >> 10)
    print("board: mpy v%d.%d arch %s" % (mpy & 0xff, (mpy >> 8) & 3, arch))
    if not arch:
        sys.exit("stock firmware, nothing to bench")
    board_dir = os.path.join(a.mount, "lib", "turbo", arch)
    os.makedirs(board_dir, exist_ok=True)
    installed = os.path.join(board_dir, a.module + ".mpy")

    variants = {"bytecode": ("py", entry["src"])}
    for tier, val in entry.get(arch, {}).get("candidates", {}).items():
        if isinstance(val, int):
            variants[tier] = ("mpy", os.path.join(a.out, arch, "%s.%s.mpy" % (a.module, tier)))

    results = {}
    for tier, (kind, src) in variants.items():
        # place exactly one candidate under the arch dir, as the name the shim imports
        for f in os.listdir(board_dir):
            if f.startswith(a.module + "."):
                os.remove(os.path.join(board_dir, f))
        shutil.copyfile(src, os.path.join(board_dir, a.module + (".py" if kind == "py" else ".mpy")))
        os.sync()
        time.sleep(2)
        pyb.exit_raw_repl()
        pyb.enter_raw_repl()  # soft reset clears the module cache
        board_exec(pyb, "import gc, time, turbo, %s" % a.module)
        vals, times = set(), []
        for _ in range(a.trials):
            board_exec(pyb, "gc.collect()")
            out = board_exec(pyb, "t0=time.monotonic_ns(); v=%s._turbo_bench(); "
                                  "print((time.monotonic_ns()-t0)//1000, v)" % a.module).split()
            times.append(int(out[0]))
            vals.add(out[1])
        times.sort()
        results[tier] = {"us_median": times[len(times) // 2], "us_min": times[0],
                         "value": sorted(vals)[0] if len(vals) == 1 else list(vals)}
        print("%-9s median %9.1f ms  value %s" % (tier, times[len(times) // 2] / 1000, results[tier]["value"]))
    pyb.exit_raw_repl()
    pyb.close()

    ref = results["bytecode"]["value"]
    ok = {t: r for t, r in results.items() if t != "bytecode" and r["value"] == ref}
    bad = [t for t in results if t != "bytecode" and t not in ok]
    if bad:
        print("rejected (output differs from bytecode):", ", ".join(bad))
    winner = min(ok, key=lambda t: ok[t]["us_median"]) if ok else None

    for f in os.listdir(board_dir):
        if f.startswith(a.module + "."):
            os.remove(os.path.join(board_dir, f))
    if winner:
        shutil.copyfile(os.path.join(a.out, arch, "%s.%s.mpy" % (a.module, winner)), installed)
        shutil.copyfile(installed, os.path.join(a.out, arch, a.module + ".mpy"))
    os.sync()

    # reload before writing: another bench (other board, other arch) may have saved meanwhile
    manifest = load_manifest(a.out)
    entry = manifest.setdefault(a.module, entry)
    ae = entry.setdefault(arch, {})
    ae.update({"installed": winner, "measured": True, "mpy_abi": "%d.%d" % (mpy & 0xff, (mpy >> 8) & 3),
               "bench": results, "rejected": bad, "trials": a.trials,
               "speedup_vs_bytecode": round(results["bytecode"]["us_median"] / ok[winner]["us_median"], 1) if winner else None})
    save_manifest(a.out, manifest)
    print("installed %s for %s (%.1fx over bytecode)" % (winner, arch, ae["speedup_vs_bytecode"] or 0))


def cmd_check(a):
    manifest = load_manifest(a.out)
    rc = 0
    for name, entry in sorted(manifest.items()):
        path = os.path.join(a.src, name + ".py")
        if not os.path.exists(path):
            print("%-14s source missing" % name)
            rc = 1
            continue
        fresh = sha256(path) == entry.get("sha256")
        archs = ", ".join("%s=%s%s" % (k, v.get("installed"), "" if v.get("measured") else "?")
                          for k, v in entry.items() if isinstance(v, dict))
        print("%-14s %s  %s" % (name, "fresh" if fresh else "STALE, rebuild", archs))
        rc |= not fresh
    return rc


def cmd_pack(a):
    """Stage the project, drop unpicked candidates, hand to folder2uf2."""
    if shutil.which(a.folder2uf2) is None:
        sys.exit("%s not found; pip install folder2uf2" % a.folder2uf2)
    lib_turbo = os.path.join(a.project, "lib", "turbo")
    if not os.path.isfile(os.path.join(a.project, "lib", "turbo.py")):
        print("warning: no lib/turbo.py in project; the shim will not be on the board")
    manifest = load_manifest(lib_turbo)
    stale = []
    for name, entry in manifest.items():
        src = os.path.join(a.project, entry.get("src", ""))
        if not os.path.isfile(src) or sha256(src) != entry.get("sha256"):
            stale.append(name)
    if stale and not a.force:
        sys.exit("stale compiled modules (source changed since build): %s\n"
                 "run `turbo build` again, or pass --force" % ", ".join(stale))

    with tempfile.TemporaryDirectory() as td:
        stage = os.path.join(td, "stage")
        shutil.copytree(a.project, stage, ignore=shutil.ignore_patterns(
            ".git", ".DS_Store", "__pycache__", "*.uf2"))
        dropped = 0
        st = os.path.join(stage, "lib", "turbo")
        if os.path.isdir(st):
            for arch in os.listdir(st):
                d = os.path.join(st, arch)
                if not os.path.isdir(d):
                    continue
                for f in os.listdir(d):
                    if f.endswith(".native.mpy") or f.endswith(".viper.mpy"):
                        os.remove(os.path.join(d, f))
                        dropped += 1
        if a.self_extract:
            out = a.output or "turbo-code.py"
            cmd = [a.folder2uf2, "--self-extract", "-o", out, stage]
        else:
            if not a.board or not a.firmware:
                sys.exit("pack needs --board and --firmware, or --self-extract")
            out = a.output or "%s-turbo.uf2" % a.board
            cmd = [a.folder2uf2, "--board", a.board, "--combine", a.firmware, "-o", out, stage]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.stdout.strip():
            print(r.stdout.strip())
        if r.returncode:
            sys.exit(r.stderr.strip() or "folder2uf2 failed")
    print("packed %s (%d bytes), %d candidate files dropped, %d compiled modules"
          % (out, os.path.getsize(out), dropped, len(manifest)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("src")
    b.add_argument("--out", default="lib/turbo")
    b.add_argument("--mpy-cross", default="mpy-cross")
    b.add_argument("--arch", default=",".join(ARCHES))
    b.set_defaults(fn=cmd_build)
    n = sub.add_parser("bench")
    n.add_argument("module")
    n.add_argument("--port", required=True)
    n.add_argument("--mount", required=True)
    n.add_argument("--out", default="lib/turbo")
    n.add_argument("--trials", type=int, default=5)
    n.add_argument("--pyboard-tools", default=os.path.expanduser("~/cp-1030/tools"))
    n.set_defaults(fn=cmd_bench)
    c = sub.add_parser("check")
    c.add_argument("src")
    c.add_argument("--out", default="lib/turbo")
    c.set_defaults(fn=cmd_check)
    k = sub.add_parser("pack", help="one UF2: turbo firmware + project files (or a self-extracting code.py)")
    k.add_argument("project", help="folder with code.py, lib/, src/")
    k.add_argument("--board", help="folder2uf2 board name, e.g. adafruit_metro_rp2350")
    k.add_argument("--firmware", help="turbo firmware .uf2 to combine with")
    k.add_argument("-o", "--output")
    k.add_argument("--self-extract", action="store_true",
                   help="emit a self-extracting code.py instead; works on any port, no firmware included")
    k.add_argument("--force", action="store_true", help="pack even if a compiled module is stale")
    k.add_argument("--folder2uf2", default="folder2uf2")
    k.set_defaults(fn=cmd_pack)
    a = p.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
