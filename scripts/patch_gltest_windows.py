"""Windows fix for gltest direct mode.

gltest 0.29.2 calls os.unlink() on a temp file that is still open, which fails on
Windows with PermissionError [WinError 32]. This wraps that call in try/except.

Run once:  py -3.13 scripts\\patch_gltest_windows.py
Re-run after upgrading genlayer-test.
"""
import pathlib
import re

import gltest.direct.loader as m

MARKER = "WINDOWS_UNLINK_PATCH"
target = pathlib.Path(m.__file__)
src = target.read_text(encoding="utf-8")
original = src

# Repair an earlier bad patch that left raw \x01 control chars as indentation.
if "\x01" in src:
    src = src.replace("\x01", " " * 8)

if MARKER not in src:
    repl = r"\1try:  # " + MARKER + r"\n\1    os.unlink(path)\n\1except OSError:\n\1    pass"
    src, n = re.subn(r"(?m)^([ \t]*)os\.unlink\(path\)[ \t]*$", repl, src)
    if n == 0:
        raise SystemExit("pattern not found - genlayer-test version changed?")

if src == original:
    print("already patched:", target)
else:
    target.write_text(src, encoding="utf-8")
    print("patched:", target)