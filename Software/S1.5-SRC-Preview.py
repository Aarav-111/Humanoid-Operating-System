import sys
sys.dont_write_bytecode = True

import os

_VENV_PYTHON = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".venv", "bin", "python")
if (__name__ == "__main__" and os.path.exists(_VENV_PYTHON)
        and not os.environ.get("S1_NO_VENV")
        and os.path.realpath(sys.prefix) != os.path.realpath(
            os.path.dirname(os.path.dirname(_VENV_PYTHON)))):
    import importlib.util
    if not all(importlib.util.find_spec(m) for m in
               ("cv2", "numpy", "coremltools", "openai", "PIL")):
        os.execv(_VENV_PYTHON,
                 [_VENV_PYTHON, os.path.abspath(__file__)] + sys.argv[1:])

FASTSAM_BUILD_FLAG = "--build-fastsam"
if FASTSAM_BUILD_FLAG not in sys.argv:
    sys.modules.setdefault("torch", None)

import base64
import colorsys
import copy
import datetime
import io
import json
import math
import multiprocessing
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field, replace as dc_replace
from multiprocessing import shared_memory
from typing import Optional

import cv2
import numpy as np

# The FastSAM worker is this same file re-run by multiprocessing's spawn as
# "__mp_main__". It only outlines, so it skips the window, model-API, audio
# and serial modules -- a second or more off the time before the first
# outlines appear.
_FASTSAM_CHILD = __name__ == "__mp_main__"

try:
    if _FASTSAM_CHILD:
        raise ImportError("not needed in the FastSAM worker")
    from openai import OpenAI
except ImportError:

    OpenAI = None

try:
    if _FASTSAM_CHILD:
        raise ImportError("not needed in the FastSAM worker")
    from AppKit import (NSApplication, NSBundle, NSMenu, NSMenuItem,
                        NSProcessInfo, NSScreen, NSEvent, NSPasteboard,
                        NSPasteboardTypeString, NSObject, NSSpeechSynthesizer,
                        NSImage)
except ImportError:
    NSApplication = NSBundle = NSMenu = NSMenuItem = None
    NSProcessInfo = NSScreen = None
    NSEvent = NSPasteboard = NSPasteboardTypeString = None
    NSImage = None
    NSObject = None
    NSSpeechSynthesizer = None

try:
    if _FASTSAM_CHILD:
        raise ImportError("not needed in the FastSAM worker")
    import objc
    from Foundation import NSDate, NSDefaultRunLoopMode
except ImportError:
    objc = NSDate = NSDefaultRunLoopMode = None

try:
    if _FASTSAM_CHILD:
        raise ImportError("not needed in the FastSAM worker")
    import sounddevice as sd
except Exception:
    sd = None

try:
    if _FASTSAM_CHILD:
        raise ImportError("not needed in the FastSAM worker")
    import serial
    from serial.tools import list_ports as serial_list_ports
except ImportError:
    serial = None
    serial_list_ports = None

DEFAULT_N_COLS = 20
DEFAULT_N_ROWS = 20
MAX_N_COLS = 26
MAX_N_ROWS = 26
MIN_N = 2

ALPHABET = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

DEBUG_INPUT = bool(os.environ.get("S1_DEBUG_INPUT"))

SCRIPT_PATH = os.path.abspath(__file__)
S1_EMBEDDED_STATE_B64 = "eyJzZXR0aW5ncyI6eyJjYW1lcmEiOnsiem9vbSI6MS4xLCJicmlnaHRuZXNzIjowLCJjb250cmFzdCI6MS4wLCJzYXR1cmF0aW9uIjoxLjAsInNoYXJwbmVzcyI6MC4wLCJyb3RhdGlvbiI6MCwibWlycm9yIjpmYWxzZX0sImdyaWQiOnsibl9jb2xzIjoyMCwibl9yb3dzIjoyMCwiYm94IjpbMjEzLjAsNy43NTk5OTk5OTk5OTk5OTEsOTkwLjI0LDc4NS4wXSwic3F1YXJlX2NlbGxzIjp0cnVlLCJmcmFtZV9zaXplIjpbMTQwOSw3OTJdLCJib3hfcmVsIjpbMC4xNTExNzEwNDMyOTMxMTU2OCwwLjAwOTc5Nzk3OTc5Nzk3OTc4NiwwLjcwMjc5NjMwOTQzOTMxODcsMC45OTExNjE2MTYxNjE2MTYxXX0sInRyaWdfb2Zmc2V0Ijp7ImNhbWVyYV9oZWlnaHRfaW4iOjM1LjAsInRhZ19oZWlnaHRfaW4iOjUuNSwiYm9hcmRfaGVpZ2h0X2luIjowLjAsInBpdm90X3giOjAuMCwicGl2b3RfeSI6MC4wLCJncmlwcGVyX3VwX2Rvd24iOi03LCJncmlwcGVyX3JpZ2h0X2xlZnQiOjAsImdyaXBwZXJfdmVydGljYWxfZGlyZWN0aW9uIjoidXAiLCJncmlwcGVyX2hvcml6b250YWxfZGlyZWN0aW9uIjoibGVmdCIsIm51ZGdlX3MiOjAuMiwibnVkZ2VfZGlyZWN0aW9uIjoicmlnaHQiLCJudWRnZV9hY3Rpb25zIjp7InBpY2t1cCI6dHJ1ZSwia2VlcCI6ZmFsc2UsInByZXNzIjpmYWxzZSwicmVsZWFzZSI6dHJ1ZX19LCJ2aXNpb24iOnsiYm9hcmRfd2lkdGhfaW4iOjI0LjAsImNvbmZfdGhyZXMiOjAuMjUsImlvdV90aHJlcyI6MC43LCJtYXhfYXJlYSI6MC41LCJvdXRsaW5lX3B4IjoyLCJtYXJrX3BhcnRzIjp0cnVlLCJzaG93X25hbWVzIjp0cnVlLCJhdXRvX25hbWUiOnRydWUsIm5hbWVyX21vZGVsIjoiZ3B0LTUuNC1taW5pIiwicHJpb3JpdHlfbmFtaW5nIjp0cnVlLCJtYXhfZnBzIjoxMC4wLCJzY2VuZV9oaW50IjoiVGhlIHBob3RvIHNob3dzIHRoZSB3b3JrIGFyZWEgb2YgYSBzbWFsbCBnYW50cnkgcm9ib3QsIHNvIGl0IG1heSBob2xkIHBhcnRzIG9mIHRoZSByb2JvdCBpdHNlbGYgKGFsdW1pbml1bSBmcmFtZSByYWlscywgbGVhZCBzY3Jld3MsIHNtb290aCByb2RzLCBzdGVwcGVyIG1vdG9ycywgYmVsdHMsIHB1bGxleXMsIGEgZ3JpcHBlciwgY2FibGVzKSBhcyB3ZWxsIGFzIGV2ZXJ5ZGF5IG9iamVjdHMuIn0sImJlaGF2aW91ciI6eyJtYW51YWxfZ3JpcHBlcl9zdGVwcyI6ZmFsc2UsImdyaXBwZXJfYWkiOnRydWUsImVycl92ZXJzaW9uIjoiRVJSLTMifX0sImN1c3RvbV90cmFpbmluZyI6W10sImVycm9yX3JlYm91bmRzIjpbeyJ0YXNrIjoic3dhcCBhbGwgdGhlIG9iamVjdHMgb24gdGhlIGJvYXJkIiwidmVyZGljdCI6ImRvbmUgd3JvbmdseSIsInJlYXNvbiI6Ik9iamVjdHMgZGlkIG5vdCBzd2FwIHBvc2l0aW9uczsgc2NyZXdkcml2ZXIgcmVtYWlucyBhdCBIMTQgYW5kIHV0aWxpdHkga25pZmUgcmVtYWlucyBhdCBQMTEuIiwibW9kZWwiOiJncHQtNS40IiwidGltZXN0YW1wIjoiMjAyNi0wOC0zMVQyMDo0NTowNiJ9LHsidGFzayI6IndhdGVyIG15IHBsYW50cyIsInZlcmRpY3QiOiJkb25lIHdyb25nbHkiLCJyZWFzb24iOiJObyB2aXNpYmxlIGV2aWRlbmNlIHRoZSBwbGFudCB3YXMgd2F0ZXJlZDsgY3VwIGFuZCBwbGFudCByZW1haW4gZXNzZW50aWFsbHkgdW5jaGFuZ2VkLiIsIm1vZGVsIjoiZ3B0LTUuNCIsInRpbWVzdGFtcCI6IjIwMjYtMDktMDFUMTU6NDY6MTMifSx7InRhc2siOiJ3YXRlciBteSBwbGFudHMiLCJ2ZXJkaWN0IjoiZG9uZSB3cm9uZ2x5IiwicmVhc29uIjoiTm8gdmlzaWJsZSBldmlkZW5jZSB0aGUgcGxhbnQgd2FzIHdhdGVyZWQ7IHBsYW50IGFuZCBtdWcgb25seSBzaGlmdGVkIHNsaWdodGx5LiIsIm1vZGVsIjoiZ3B0LTUuNCIsInRpbWVzdGFtcCI6IjIwMjYtMDktMDJUMTQ6MzE6NTAifSx7InRhc2siOiJLZWVwIHRoZSBibGFjayBzcG90IGluIHRoZSBib2R5LiIsInZlcmRpY3QiOiJkb25lIGNvcnJlY3RseSIsInJlYXNvbiI6ImJsYWNrIHNvY2sgd2FzIG1vdmVkIGludG8gdGhlIGJvd2wsIHdpdGggdGhlIGJvd2wgc3RpbGwgY29udGFpbmluZyBpdCBpbiB0aGUgZmluYWwgaW1hZ2UiLCJtb2RlbCI6ImdwdC01LjQiLCJ0aW1lc3RhbXAiOiIyMDI2LTA5LTExVDExOjUxOjIyIn0seyJ0YXNrIjoiS2VlcCB0aGUgYmxhY2sgc3BvdCBpbiB0aGUgYm9keS4iLCJ2ZXJkaWN0IjoiZG9uZSB3cm9uZ2x5IiwicmVhc29uIjoiYmxhY2sgc29jayB3YXMgbW92ZWQgbmVhciBLNCBpbnN0ZWFkIG9mIGJlaW5nIGtlcHQgaW4gdGhlIGJvd2wvYm9keSBhdCBRMyIsIm1vZGVsIjoiZ3B0LTUuNCIsInRpbWVzdGFtcCI6IjIwMjYtMDktMTFUMTE6NTE6MzYifSx7InRhc2siOiJzb3J0IHRoZSBzb2NrZXMgYW5kIGtlZXAgdGhlIHdoaXRlcyBpbiB0ZSBib3dsIiwidmVyZGljdCI6ImRvbmUgd3JvbmdseSIsInJlYXNvbiI6IldoaXRlIHNvY2tzIGFyZSBub3QgdmlzaWJsZSBpbiB0aGUgYm93bCBpbiB0aGUgZmluYWwgaW1hZ2U7IG9ubHkgdGhlIGJsYWNrIHNvY2tzIHJlbWFpbiBvbiB0aGUgYm9hcmQuIiwibW9kZWwiOiJncHQtNS40IiwidGltZXN0YW1wIjoiMjAyNi0wOS0xMVQxMjowMzowMCJ9LHsidGFzayI6IktlZXAgdGhlIGJsYWNrIHNvY2tzIHN0YWNrZWQgdG9nZXRoZXIuIiwidmVyZGljdCI6ImRvbmUgd3JvbmdseSIsInJlYXNvbiI6Ik9ubHkgb25lIGJsYWNrIHNvY2sgaXMgdmlzaWJsZSBpbiB0aGUgZmluYWwgaW1hZ2U7IHRoZSB0d28gc29ja3MgYXJlIG5vdCBjb25maXJtZWQgc3RhY2tlZCB0b2dldGhlci4iLCJtb2RlbCI6ImdwdC01LjQiLCJ0aW1lc3RhbXAiOiIyMDI2LTA5LTExVDEyOjA1OjEzIn0seyJ0YXNrIjoiS2VlcCB0aGUgYmxhY2sgc29ja3Mgc3RhY2tlZCB0b2dldGhlci4iLCJ2ZXJkaWN0IjoiZG9uZSBjb3JyZWN0bHkiLCJyZWFzb24iOiJUaGUgdHdvIGJsYWNrIHNvY2tzIGFyZSBzdGFja2VkIHRvZ2V0aGVyIGluIHRoZSBmaW5hbCBpbWFnZS4iLCJtb2RlbCI6ImdwdC01LjQiLCJ0aW1lc3RhbXAiOiIyMDI2LTA5LTExVDEyOjA1OjIzIn0seyJ0YXNrIjoiS2VlcCB0aGUgYmxhY2sgc29jayBpbiB0aGUgYm93bC4iLCJ2ZXJkaWN0IjoiZG9uZSBjb3JyZWN0bHkiLCJyZWFzb24iOiJibGFjayBzb2NrIGlzIHBsYWNlZCBpbiB0aGUgZ3JlZW4gYm93bCBpbiB0aGUgZmluYWwgaW1hZ2UuIiwibW9kZWwiOiJncHQtNS40IiwidGltZXN0YW1wIjoiMjAyNi0wOS0xMVQxMzowMTozNCJ9LHsidGFzayI6IlNvcnQgdGhlIGJsYWNrIGFuZCB3aGl0ZSBzb2NrcywgYW5kIHB1dCBhbGwgdGhlIHdoaXRlcyBpbiB0aGUgYm93bC4iLCJ2ZXJkaWN0IjoiZG9uZSB3cm9uZ2x5IiwicmVhc29uIjoiV2hpdGUgc29jayBpcyBpbiB0aGUgYm93bCwgYnV0IG9uZSB3aGl0ZSBzb2NrIHJlbWFpbnMgb3V0c2lkZSB0aGUgYm93bC4iLCJtb2RlbCI6ImdwdC01LjQiLCJ0aW1lc3RhbXAiOiIyMDI2LTA5LTExVDE2OjI3OjQ4In0seyJ0YXNrIjoiU29ydCBteSBjbG90aGVzIG9yIHNvY2tzIGludG8gYmxhY2sgYW5kIHdoaXRlLiBLZWVwIGFsbCB0aGUgYmxhY2tzIGluIHRoZSBib3dsLiIsInZlcmRpY3QiOiJkb25lIHdyb25nbHkiLCJyZWFzb24iOiJPbmx5IG9uZSBibGFjayBzb2NrIGlzIGluIHRoZSBib3dsOyB0aGUgb3RoZXIgYmxhY2sgc29jayBpcyBub3QgdmVyaWZpZWQgaW4gdGhlIGJvd2wuIiwibW9kZWwiOiJncHQtNS40IiwidGltZXN0YW1wIjoiMjAyNi0wOS0xMVQxNjozOTo0MiJ9LHsidGFzayI6IktlZXAgdGhlIGxlYXZlcyBpbiB0aGUgYm93bC4iLCJ2ZXJkaWN0IjoiZG9uZSB3cm9uZ2x5IiwicmVhc29uIjoiTGVhdmVzIGFyZSBub3QgZnVsbHkgaW4gdGhlIGJvd2w7IHBhcnQgb2YgdGhlIHNwcmlnIHJlbWFpbnMgb3V0c2lkZSBvbiB0aGUgcmltL3RhYmxlLiIsIm1vZGVsIjoiZ3B0LTUuNCIsInRpbWVzdGFtcCI6IjIwMjYtMDktMTFUMTY6NDc6NTIifSx7InRhc2siOiJtb2UgdGhlIGJrb29rIHRvIGl0J3MgbGVmdCIsInZlcnNpb24iOiJFUlItMyIsInZlcmRpY3QiOiJkb25lIHdyb25nbHkiLCJvYmplY3RzIjpbIm5vdGVib29rPXdyb25nIl0sInJlYXNvbiI6IlRoZSBub3RlYm9vayByZW1haW5zIGluIHRoZSBzYW1lIHBvc2l0aW9uIGFzIGluIHRoZSBzdGFydCBpbWFnZXMgYW5kIHdhcyBub3QgbW92ZWQgbGVmdC4iLCJuZXh0IjoiRklYOiBtb3ZlIHRoZSBub3RlYm9vayBsZWZ0IGZyb20gaXRzIGN1cnJlbnQgcG9zaXRpb24gYW5kIHJlbGVhc2UgaXQgdGhlcmUiLCJtb2RlbCI6ImdwdC01LjQiLCJ0aW1lc3RhbXAiOiIyMDI2LTEwLTAyVDE4OjA0OjAwIn0seyJ0YXNrIjoibW9lIHRoZSBia29vayB0byBpdCdzIGxlZnQiLCJ2ZXJzaW9uIjoiRVJSLTMiLCJ2ZXJkaWN0IjoiZG9uZSBjb3JyZWN0bHkiLCJvYmplY3RzIjpbIm5vdGVib29rPW9rIl0sInJlYXNvbiI6IlRoZSBibGFjayBub3RlYm9vayBpcyB2aXNpYmx5IHNoaWZ0ZWQgbGVmdCBmcm9tIGl0cyBzdGFydCBwb3NpdGlvbiAoZnJvbSBhYm91dCBHLUwgY29sdW1ucyB0byBhYm91dCBELUogY29sdW1ucykgYW5kIGlzIHJlc3Rpbmcgb24gdGhlIGJvYXJkIHdpdGggbm8gZ3JpcHBlciBob2xkaW5nIGl0OyBubyBvdGhlciB0YXNrIGNvbnN0cmFpbnRzIGFyZSB2aXNpYmx5IHZpb2xhdGVkLiIsIm5leHQiOiIiLCJtb2RlbCI6ImdwdC01LjQiLCJ0aW1lc3RhbXAiOiIyMDI2LTEwLTAyVDE4OjA0OjIyIn1dfQ=="  # S1_EMBEDDED_STATE
try:
    S1_EMBEDDED_STATE = json.loads(
        base64.b64decode(S1_EMBEDDED_STATE_B64).decode("utf-8"))
except (ValueError, UnicodeDecodeError):
    S1_EMBEDDED_STATE = {
        "settings": {}, "custom_training": [], "error_rebounds": []}
_EMBEDDED_STATE_PATTERN = re.compile(
    r'^S1_EMBEDDED_STATE_B64 = "[A-Za-z0-9+/=]*"'
    r'  # S1_EMBEDDED_STATE$', re.MULTILINE)
_PERSIST_COND = threading.Condition()
_PERSIST_PENDING = None
_PERSIST_THREAD = None
_PERSIST_IDLE = threading.Event()
_PERSIST_IDLE.set()


def _write_embedded_state(encoded: str) -> bool:
    """The slow part: read this ~600KB file, rewrite one line, fsync.

    Runs only on the persist worker thread -- see persist_embedded_state.
    """
    replacement = (
        f'S1_EMBEDDED_STATE_B64 = "{encoded}"  # S1_EMBEDDED_STATE')
    try:
        with open(SCRIPT_PATH, "r+", encoding="utf-8") as fh:
            source = fh.read()
            updated, count = _EMBEDDED_STATE_PATTERN.subn(
                replacement, source, count=1)
            if count != 1:
                raise OSError("embedded state marker is missing")
            fh.seek(0)
            fh.write(updated)
            fh.truncate()
            fh.flush()
            os.fsync(fh.fileno())
        print(f"[state] saved inside {SCRIPT_PATH}")
        return True
    except OSError as e:
        print(f"[state] could not update {SCRIPT_PATH}: {e}")
        return False


def _persist_worker():
    """Write whatever the newest queued snapshot is, forever.

    A snapshot queued while a write is already running replaces the one
    waiting rather than queuing behind it -- only the final state is worth
    putting on disk, and catching up on every intermediate one a fast
    sequence of clicks produced would only fall further behind.
    """
    global _PERSIST_PENDING
    while True:
        with _PERSIST_COND:
            while _PERSIST_PENDING is None:
                _PERSIST_COND.wait()
            encoded = _PERSIST_PENDING
            _PERSIST_PENDING = None
            _PERSIST_IDLE.clear()
        _write_embedded_state(encoded)
        with _PERSIST_COND:
            if _PERSIST_PENDING is None:
                _PERSIST_IDLE.set()


def persist_embedded_state() -> bool:
    """Queue the current embedded state to be written into S1.py.

    Reading and rewriting this whole file, then fsync, used to happen right
    here on whatever thread called this -- the main/render thread for
    every settings change a click makes. On a slow or momentarily busy
    disk that is a stall the operator feels as the window freezing the
    instant they click. The actual write now happens on its own thread;
    this call only has to serialize the (small, fast) in-memory state,
    which is done before it returns.
    """
    global _PERSIST_PENDING, _PERSIST_THREAD
    encoded = base64.b64encode(json.dumps(
        S1_EMBEDDED_STATE, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).decode("ascii")
    with _PERSIST_COND:
        _PERSIST_PENDING = encoded
        _PERSIST_IDLE.clear()
        if _PERSIST_THREAD is None:
            _PERSIST_THREAD = threading.Thread(
                target=_persist_worker, daemon=True)
            _PERSIST_THREAD.start()
        _PERSIST_COND.notify()
    return True


def flush_embedded_state(timeout=2.0):
    """Block until any queued or in-flight save has actually reached disk.

    Called once, on the way out of main(), so quitting right after a
    settings change can no longer race the background write that change
    queued -- the daemon thread would otherwise simply be killed with the
    process, mid-write or never having started at all.
    """
    _PERSIST_IDLE.wait(timeout)


SETTINGS_PATH = SCRIPT_PATH
TRAINING_PATH = SCRIPT_PATH
ERR_HISTORY_PATH = SCRIPT_PATH


class GridConfig:
    """Mutable grid dimensions. Labels are derived, so changing n_cols /
    n_rows at runtime immediately changes the coordinate namespace."""

    def __init__(self, n_cols: int = DEFAULT_N_COLS, n_rows: int = DEFAULT_N_ROWS):
        self.n_cols = n_cols
        self.n_rows = n_rows

    @property
    def columns(self):
        return ALPHABET[:self.n_cols]

    @property
    def rows(self):
        return list(range(1, self.n_rows + 1))

    def col_index(self, letter: str):
        letter = letter.upper()
        cols = self.columns
        return cols.index(letter) if letter in cols else None

    def row_index(self, num: int):
        return num - 1 if 1 <= num <= self.n_rows else None


CONFIG = GridConfig()


def parse_coordinate(text: str):
    """Parse a coordinate like 'G1' or 'K11' into 0-indexed (col_idx, row_idx).

    Returns None if the text isn't a valid, in-range coordinate.
    """
    text = text.strip().upper()
    if len(text) < 2:
        return None
    col_letter = text[0]
    row_part = text[1:]
    col_idx = CONFIG.col_index(col_letter)
    if col_idx is None:
        return None
    if not row_part.isdigit():
        return None
    row_idx = CONFIG.row_index(int(row_part))
    if row_idx is None:
        return None
    return col_idx, row_idx


def coordinate_name(col_idx: int, row_idx: int) -> str:
    """0-indexed (col_idx, row_idx) -> 'G1' style label."""
    return f"{CONFIG.columns[col_idx]}{CONFIG.rows[row_idx]}"


def cell_label(col_idx, row_idx) -> str:
    """coordinate_name, but safe for a cell that is legitimately off the board.

    Once a custom gripper offset is set, the gripper's own cell can hang past
    the rim while the tag is still on it. CONFIG.columns[-1] would happily
    return the LAST column instead of raising, naming a cell on the far side
    of the board -- a wrong answer is worse here than an honest one.
    """
    if col_idx is None or row_idx is None:
        return "--"
    if 0 <= col_idx < CONFIG.n_cols and 0 <= row_idx < CONFIG.n_rows:
        return coordinate_name(col_idx, row_idx)
    return "off board"


def build_path_commands(start_col: int, start_row: int, end_col: int, end_row: int):
    """Return the list of directional commands to walk from start to end,
    one grid cell at a time.

    VERTICAL FIRST, then horizontal, always -- never split across the two,
    never diagonal. The gantry's own hardware only ever runs one axis at a
    time (send_direction sends a single 'u'/'d'/'l'/'r' letter and the
    Arduino keeps running it until told otherwise), so this is not a
    display choice: it is the actual axis order the carriage moves in. All
    of the up/down commands come first, then all of the left/right ones --
    2026-09-26, the user's explicit correction: "do all the up-down first,
    and then right-left ... not half and half."

    Convention: row 0 is the TOP of the grid (row label '1'), so moving to a
    smaller row index is "up" and a larger row index is "down". Column 0 is
    the LEFT of the grid ('A'), so moving to a larger column index is
    "right" and a smaller one is "left".
    """
    commands = []

    col_diff = end_col - start_col
    row_diff = end_row - start_row

    vertical_cmd = "down" if row_diff > 0 else "up"
    for _ in range(abs(row_diff)):
        commands.append(vertical_cmd)

    horizontal_cmd = "right" if col_diff > 0 else "left"
    for _ in range(abs(col_diff)):
        commands.append(horizontal_cmd)

    return commands


def condense_commands(commands):
    """Turn ['right','right','down'] into a readable 'right x2, down x1'."""
    if not commands:
        return "(already there)"
    parts = []
    current = commands[0]
    count = 1
    for cmd in commands[1:]:
        if cmd == current:
            count += 1
        else:
            parts.append(f"{current} x{count}")
            current = cmd
            count = 1
    parts.append(f"{current} x{count}")
    return ", ".join(parts)


def _bgr(hex_colour: str):
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


ANIM_RATE = 0.35


def ease_toward(current: float, target: float, rate: float = ANIM_RATE) -> float:
    """One frame's step of `current` toward `target`.

    Every popover/panel in the app used to just appear and disappear -- a
    hard cut every other part of the UI is glassy and rounded and softly
    shadowed. This is the one shared primitive that makes all of them ease
    in and out instead, called once per frame with nothing to store but the
    current value.
    """
    value = current + (target - current) * rate
    return target if abs(value - target) < 0.002 else value


C_BG        = _bgr("#f4f6fb")
C_CARD      = _bgr("#ffffff")
C_CARD_SOFT = _bgr("#f7f8fc")
C_BORDER    = _bgr("#e2e6f0")
C_TEXT      = _bgr("#1f2430")
C_TEXT_DIM  = _bgr("#6b7280")
C_ACCENT    = _bgr("#8b5cf6")
C_ACCENT_SO = _bgr("#ede9fe")
C_GREEN     = _bgr("#10b981")
C_AMBER     = _bgr("#f59e0b")
C_RED       = _bgr("#ef4444")
C_BLUE      = _bgr("#3b82f6")
C_BTN       = _bgr("#111114")
C_BTN_HOVER = _bgr("#2b2b31")
C_BTN_FG    = _bgr("#ffffff")
C_GHOST     = _bgr("#ffffff")
C_GHOST_HOV = _bgr("#eef0f6")

FONT = cv2.FONT_HERSHEY_SIMPLEX

GLASS_ALPHA = 0.10
GLASS_EDGE = _bgr("#ffffff")


def glass_fill(backdrop=C_BG, alpha=GLASS_ALPHA, tint=C_CARD):
    """The colour a glass card leaves over a flat backdrop.

    Panels that sit on the window wash can be filled with this directly --
    blurring a flat colour returns the same colour, so the expensive part is
    skipped and the result is identical.
    """
    return tuple(int(round(backdrop[i] * (1 - alpha) + tint[i] * alpha))
                 for i in range(3))


def blur_band(frame, a, b, c, d):
    """Gaussian-blur one rectangular region of `frame` in place, (a,b)-(c,d).

    Used to knock the room out of focus around the board so the grid reads
    as the one thing in the shot worth looking at. A no-op on an empty or
    inverted rect; the kernel is capped to the band's own smaller side so a
    sliver strip (the board dragged to the very edge of the frame) never
    hands cv2 a kernel bigger than the pixels it is blurring.

    Downsampled first, the same way glass_card blurs a panel's backdrop --
    at full resolution this ran a 45px-kernel GaussianBlur over up to the
    whole frame, four times, every frame: ~43ms on a 2000x1200 canvas, on
    its own most of a frame's entire budget at 60fps and the single biggest
    thing slowing down how quickly a click's own result reached the screen.
    A blurred-out background band has no fine detail for the downsample to
    lose, so the result looks the same at a fraction of the cost.
    """
    if b >= d or a >= c:
        return
    band = frame[b:d, a:c]
    bh, bw = d - b, c - a
    k = min(45, bh | 1, bw | 1)
    if k < 3:
        return
    sw, sh = max(1, bw // 8), max(1, bh // 8)
    # Shrink from a whole number of 8x8 blocks: INTER_AREA then takes its
    # integer fast path (~7x quicker than the general one on a 525x1013
    # band). The few rows/columns left over at the edge are still covered
    # by the stretch back up -- there is no detail to lose in a blur.
    src = band[:sh * 8, :sw * 8] if bw >= 8 and bh >= 8 else band
    small = cv2.resize(src, (sw, sh), interpolation=cv2.INTER_AREA)
    sk = min(k // 8 | 1, sw | 1, sh | 1)
    if sk >= 3:
        small = cv2.GaussianBlur(small, (sk, sk), 0)
    frame[b:d, a:c] = cv2.resize(small, (bw, bh), interpolation=cv2.INTER_LINEAR)


_CARD_STAMPS = {}


def glass_card(img, rect, radius, alpha=GLASS_ALPHA, blur=True, shadow=True):
    """A floating pane: blurred backdrop, white wash, hairline edge.

    The blur shrinks a whole number of 6x6 blocks (INTER_AREA's fast path --
    the general path was ~5 ms of every frame the Settings card was open),
    and the wash and edge are an AffineStamp per card size.
    """
    if shadow:
        drop_shadow(img, rect, radius, spread=14, strength=0.16)
    rx0, ry0, rx1, ry1 = (int(round(v)) for v in rect)
    h, w = img.shape[:2]
    x0, y0 = max(0, rx0), max(0, ry0)
    x1, y1 = min(w, rx1), min(h, ry1)
    if blur and x1 > x0 and y1 > y0:
        patch = img[y0:y1, x0:x1]
        pw, ph = x1 - x0, y1 - y0
        sw, sh = max(1, pw // 6), max(1, ph // 6)
        src = patch[:sh * 6, :sw * 6] if pw >= 6 and ph >= 6 else patch
        small = cv2.resize(src, (sw, sh), interpolation=cv2.INTER_AREA)
        small = cv2.blur(small, (5, 5))
        img[y0:y1, x0:x1] = cv2.resize(small, (pw, ph),
                                       interpolation=cv2.INTER_LINEAR)
    if rx1 <= rx0 or ry1 <= ry0:
        return
    key = (rx1 - rx0, ry1 - ry0, int(radius), round(float(alpha), 4))
    stamp = _CARD_STAMPS.get(key)
    if stamp is None:
        if len(_CARD_STAMPS) >= 64:
            _CARD_STAMPS.clear()
        cw, ch = rx1 - rx0, ry1 - ry0

        def paint(im):
            local = (3, 3, 3 + cw, 3 + ch)
            rounded_rect(im, local, radius, C_CARD, -1, alpha=alpha)
            rounded_rect(im, local, radius, GLASS_EDGE, 1)

        stamp = _CARD_STAMPS[key] = AffineStamp(cw + 7, ch + 7, paint)
    stamp.apply(img, rx0 - 3, ry0 - 3)


def rounded_rect(img, rect, radius, colour, thickness=-1, alpha=1.0,
                 clip=None):
    """Filled or stroked rounded rectangle, optionally blended.

    A blended shape is composed on a copy of its OWN region, not of the whole
    image: every card, button and shadow ring on this canvas is small, and
    copying the full frame per ring cost more than the rest of the UI put
    together. `clip` narrows that region further, so a caller can commit only
    the part of the shape it will actually leave visible; it applies to
    blended shapes only.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    if x1 <= x0 or y1 <= y0:
        return
    r = int(max(0, min(radius, (x1 - x0) // 2, (y1 - y0) // 2)))
    blend = alpha < 0.999

    if blend:
        h, w = img.shape[:2]
        pad = max(2, int(thickness)) if thickness > 0 else 1
        rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
        rx1, ry1 = min(w, x1 + pad + 1), min(h, y1 + pad + 1)
        if clip is not None:
            cx0, cy0, cx1, cy1 = (int(round(v)) for v in clip)
            rx0, ry0 = max(rx0, cx0), max(ry0, cy0)
            rx1, ry1 = min(rx1, cx1), min(ry1, cy1)
        if rx1 <= rx0 or ry1 <= ry0:
            return
        base = img[ry0:ry1, rx0:rx1].copy()
        layer = base.copy()
        x0, y0, x1, y1 = x0 - rx0, y0 - ry0, x1 - rx0, y1 - ry0
    else:
        layer = img

    if thickness < 0:
        if r:
            cv2.rectangle(layer, (x0 + r, y0), (x1 - r, y1), colour, -1, cv2.LINE_AA)
            cv2.rectangle(layer, (x0, y0 + r), (x1, y1 - r), colour, -1, cv2.LINE_AA)
            for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r),
                           (x0 + r, y1 - r), (x1 - r, y1 - r)):
                cv2.circle(layer, (cx, cy), r, colour, -1, cv2.LINE_AA)
        else:
            cv2.rectangle(layer, (x0, y0), (x1, y1), colour, -1, cv2.LINE_AA)
    else:
        t = thickness
        cv2.line(layer, (x0 + r, y0), (x1 - r, y0), colour, t, cv2.LINE_AA)
        cv2.line(layer, (x0 + r, y1), (x1 - r, y1), colour, t, cv2.LINE_AA)
        cv2.line(layer, (x0, y0 + r), (x0, y1 - r), colour, t, cv2.LINE_AA)
        cv2.line(layer, (x1, y0 + r), (x1, y1 - r), colour, t, cv2.LINE_AA)
        for (cx, cy), ang in (((x0 + r, y0 + r), 180), ((x1 - r, y0 + r), 270),
                              ((x1 - r, y1 - r), 0), ((x0 + r, y1 - r), 90)):
            cv2.ellipse(layer, (cx, cy), (r, r), ang, 0, 90, colour, t, cv2.LINE_AA)

    if blend:
        img[ry0:ry1, rx0:rx1] = cv2.addWeighted(layer, alpha, base, 1 - alpha, 0)


class AffineStamp:
    """A drawing that only ever blends pixels toward fixed colours, recorded
    once and replayed as two whole-region cv2 calls.

    Everything that is "paint this colour over what is there, at this
    coverage" -- shadows, translucent fills, anti-aliased lines and text --
    leaves each pixel as  old * m + b  for an m and b that depend only on the
    pixel's position, never on the picture underneath. Drawing it once onto
    an all-black and once onto an all-white image recovers b and m exactly
    (up to the original's own rounding), and replaying is then one
    cv2.multiply and one cv2.add over the stamp's box instead of re-running
    every ring, blend and glyph. Nothing that reads neighbouring pixels (a
    blur) may be recorded this way.
    """

    __slots__ = ("pieces",)

    def __init__(self, w, h, draw, hole=None):
        """`draw(img)` paints the stamp into a (h, w, 3) uint8 image.

        `hole` (x0, y0, x1, y1), when given, is a part the drawing leaves
        untouched -- a shadow's card -- and is not stored or replayed: only
        the bands around it are.
        """
        w, h = int(w), int(h)
        black = np.zeros((h, w, 3), np.uint8)
        white = np.full((h, w, 3), 255, np.uint8)
        draw(black)
        draw(white)
        m = cv2.subtract(white, black)
        changed = ((m != 255) | (black != 0)).any(axis=2).astype(np.uint8)
        if hole is None:
            areas = [(0, 0, w, h)]
        else:
            hx0, hy0, hx1, hy1 = (max(0, min(lim, int(v))) for v, lim in
                                  zip(hole, (w, h, w, h)))
            areas = [(0, 0, w, hy0), (0, hy1, w, h),
                     (0, hy0, hx0, hy1), (hx1, hy0, w, hy1)]
            changed[hy0:hy1, hx0:hx1] = 0
        self.pieces = []
        for ax0, ay0, ax1, ay1 in areas:
            if ax1 <= ax0 or ay1 <= ay0:
                continue
            touched = cv2.findNonZero(changed[ay0:ay1, ax0:ax1])
            if touched is None:
                continue
            bx, by, bw, bh = cv2.boundingRect(touched)
            bx, by = bx + ax0, by + ay0
            self.pieces.append((
                bx, by, bw, bh,
                np.ascontiguousarray(m[by:by + bh, bx:bx + bw]),
                np.ascontiguousarray(black[by:by + bh, bx:bx + bw])))

    def apply(self, img, x, y):
        """Replay with the stamp's top-left at (x, y), clipped to `img`."""
        ih, iw = img.shape[:2]
        for dx, dy, pw, ph, m, b in self.pieces:
            px, py = x + dx, y + dy
            x0, y0 = max(0, px), max(0, py)
            x1, y1 = min(iw, px + pw), min(ih, py + ph)
            if x1 <= x0 or y1 <= y0:
                continue
            sx0, sy0 = x0 - px, y0 - py
            sx1, sy1 = sx0 + (x1 - x0), sy0 + (y1 - y0)
            region = img[y0:y1, x0:x1]
            out = cv2.multiply(region, m[sy0:sy1, sx0:sx1], scale=1.0 / 255.0)
            cv2.add(out, b[sy0:sy1, sx0:sx1], dst=region)


_SHADOW_STAMPS = {}
_BUTTON_STAMPS = {}
BUTTON_STAMP_CACHE = 512
SHADOW_STAMP_CACHE = 256
SHADOW_STAMP_MAX_PIXELS = 3_000_000


def drop_shadow(img, rect, radius, spread=10, strength=0.16):
    """A few expanding translucent rings under a card -- cheap soft shadow.

    Only the band outside the card is committed: the caller paints the card
    over the rest immediately afterwards, and blending a full card-sized ring
    per step is by far the most expensive thing on this canvas.

    The rings depend only on the card's size, so they are worked out once per
    size (see AffineStamp) and every later shadow of that size is two cv2
    calls: a button's shadow went from 28 small blends to 2.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    if x1 <= x0 or y1 <= y0:
        return
    m = int(spread) + 6
    w, h = x1 - x0, y1 - y0
    if (w + 2 * m) * (h + 2 * m) > SHADOW_STAMP_MAX_PIXELS:
        _draw_shadow_rings(img, (x0, y0, x1, y1), radius, spread, strength)
        return
    key = (w, h, int(radius), int(spread), round(float(strength), 4))
    stamp = _SHADOW_STAMPS.get(key)
    if stamp is None:
        if len(_SHADOW_STAMPS) >= SHADOW_STAMP_CACHE:
            _SHADOW_STAMPS.clear()
        stamp = _remember(_SHADOW_STAMPS, key, AffineStamp(
            w + 2 * m, h + 2 * m,
            lambda im: _draw_shadow_rings(im, (m, m, m + w, m + h), radius,
                                          spread, strength),
            hole=(m, m, m + w, m + h)))
    stamp.apply(img, x0 - m, y0 - m)


def _draw_shadow_rings(img, rect, radius, spread, strength):
    """The rings themselves, as drop_shadow always drew them."""
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    colour = _bgr("#c8cede")
    for i in range(spread, 0, -2):
        a = strength * (1.0 - (i - 1) / float(spread)) ** 1.8
        if a <= 0.004:
            continue
        ring = (x0 - i, y0 - i + 3, x1 + i, y1 + i + 3)
        for clip in ((x0 - i - 2, y0 - i, x1 + i + 2, y0),
                     (x0 - i - 2, y1, x1 + i + 2, y1 + i + 5),
                     (x0 - i - 2, y0, x0, y1),
                     (x1, y0, x1 + i + 2, y1)):
            rounded_rect(img, ring, radius + i, colour, -1, alpha=a, clip=clip)


_WALLPAPER_STOPS = ((0.0, "#f7f8fc"), (0.45, "#f3f0ff"), (1.0, "#eef6ff"))

_WALLPAPER_ORBS = (
    (0.78, 0.42, 0.52, 150, "#ba96ff"),
    (0.62, 0.58, 0.48, 135, "#ff96be"),
    (0.70, 0.32, 0.42, 125, "#ffc382"),
    (0.88, 0.62, 0.38, 115, "#ffaa6e"),
    (0.48, 0.28, 0.32,  90, "#aabeff"),
    (0.55, 0.70, 0.36, 100, "#ff8ca0"),
)


def _wallpaper_gradient(w, h):
    """Diagonal top-left -> bottom-right pastel gradient, S1-SRC's base wash."""
    stops_t = np.array([t for t, _ in _WALLPAPER_STOPS], np.float32)
    colours = np.array([_bgr(c) for _, c in _WALLPAPER_STOPS], np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    diag = (xx / max(w - 1, 1) + yy / max(h - 1, 1)) * 0.5
    out = np.empty((h, w, 3), np.float32)
    for c in range(3):
        out[..., c] = np.interp(diag, stops_t, colours[:, c])
    return out


WALLPAPER_SCALE = 8
WALLPAPER_DRIFT = 0.05
WALLPAPER_MARGIN = 24


def _wallpaper_scale(w, h):
    """The 1:N reduction to build the wash at.

    Fixed at WALLPAPER_SCALE for ordinary windows, then loosened so the
    working canvas stays about the same handful of pixels however big the
    window is -- a 4K window should not cost sixteen times a laptop one to
    paint a gradient nothing can resolve detail in anyway.
    """
    return max(WALLPAPER_SCALE, int(math.ceil(max(int(w), int(h)) / 220.0)))


def _wallpaper_small(w, h):
    """The reduced size the wash is actually computed at."""
    s = _wallpaper_scale(w, h)
    return max(16, int(w) // s), max(16, int(h) // s)


def build_wallpaper_base(w, h):
    """The size-only half of the wallpaper: the gradient plus one blurred
    alpha "sprite" per colour bloom, at reduced resolution.

    Cached once per window size (see main()). Neither the gradient nor the
    blurs depend on the mouse, only on how big the window is; what the mouse
    moves each frame is just where the sprites get pasted, in
    paint_wallpaper() below.
    """
    sw, sh = _wallpaper_small(w, h)
    m = WALLPAPER_MARGIN
    grad = _wallpaper_gradient(sw, sh)
    sprites = []
    for cx_f, cy_f, rf, alpha, hexc in _WALLPAPER_ORBS:
        rad = int(max(sw, sh) * rf)
        if rad <= 0:
            continue
        mask = np.zeros((sh + 2 * m, sw + 2 * m), np.float32)
        cv2.circle(mask, (int(cx_f * sw) + m, int(cy_f * sh) + m), rad, 1.0,
                   -1, cv2.LINE_AA)
        mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, rad * 0.35))
        a = np.clip(mask * (alpha / 255.0) * 0.32, 0.0, 0.22)[..., None]
        colour = np.array(_bgr(hexc), np.float32)
        sprites.append((a, colour))
    return grad, sprites


_THEME_HUES = (0, 230, 160, 70, 300)
_HUE_STAGE_HOLD = 1.6
_HUE_STAGE_FADE = 1.4
_HUE_STAGE = _HUE_STAGE_HOLD + _HUE_STAGE_FADE


def _smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


def theme_hue_shift(t=None):
    """Degrees to rotate the base palette's hue by, right now.

    A pure function of wall-clock time -- the cycle needs no state of its
    own, so nothing has to track "how long has the wallpaper been showing";
    it is simply always in step with the clock, the same way S1-SRC's own
    QTimer-driven _anim_t is in practice (it runs continuously from launch).
    """
    if t is None:
        t = time.time()
    n = len(_THEME_HUES)
    stage, within = divmod(t, _HUE_STAGE)
    cur = _THEME_HUES[int(stage) % n]
    if within <= _HUE_STAGE_HOLD:
        return float(cur)
    nxt = _THEME_HUES[(int(stage) + 1) % n]
    frac = _smoothstep((within - _HUE_STAGE_HOLD) / _HUE_STAGE_FADE)
    d = ((nxt - cur + 180) % 360) - 180
    return cur + d * frac


def _rotate_hue_bgr(bgr, degrees):
    """One BGR triple, hue-rotated by `degrees` -- saturation/value held."""
    b, g, r = (c / 255.0 for c in bgr)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = ((h * 360.0 + degrees) % 360.0) / 360.0
    r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
    return (b2 * 255.0, g2 * 255.0, r2 * 255.0)


def wallpaper_offset(w, h, mouse):
    """The parallax shift for this cursor position, in reduced-size pixels.

    main() keys its cached wash on this, so the wash is only rebuilt when the
    cursor has moved far enough to actually change it.
    """
    mx, my = mouse if mouse else (w * 0.5, h * 0.5)
    k = WALLPAPER_DRIFT / _wallpaper_scale(w, h)
    return int((mx - w * 0.5) * k), int((my - h * 0.5) * k)


def paint_wallpaper(base, sprites, w, h, mouse=None, hue_shift=None):
    """One frame of the background: the cached gradient plus each bloom,
    nudged toward the mouse and hue-rotated by the theme cycle -- the same
    cursor parallax and the same living colour S1-SRC's animated wallpaper
    both have, just driven by wall-clock time the way it always was rather
    than a Qt timer.
    """
    out = base.copy()
    sh, sw = base.shape[:2]
    m = WALLPAPER_MARGIN
    off_x, off_y = wallpaper_offset(w, h, mouse)
    shift = theme_hue_shift() if hue_shift is None else hue_shift
    for i, (a, colour) in enumerate(sprites):
        depth = 1.0 + 0.3 * (i % 3)
        dx = max(-m, min(m, int(off_x * depth)))
        dy = max(-m, min(m, int(off_y * depth)))
        shifted = a[m - dy:m - dy + sh, m - dx:m - dx + sw]
        rotated = np.array(_rotate_hue_bgr(tuple(colour.tolist()), shift),
                           np.float32)
        out *= (1.0 - shifted)
        out += rotated[None, None, :] * shifted
    small = np.clip(out, 0, 255).astype(np.uint8)
    return cv2.resize(small, (int(w), int(h)), interpolation=cv2.INTER_LINEAR)


VIDEO_RADIUS = 22


def _corner_alpha(r):
    """Coverage for one rounded corner block, its curve centred at (r, r)."""
    m = np.zeros((r, r), np.float32)
    cv2.circle(m, (r, r), r, 1.0, -1, cv2.LINE_AA)
    return m[..., None]


_CORNER_A = _corner_alpha(VIDEO_RADIUS)


def round_video_corners(canvas, wash, x, y, w, h, r=VIDEO_RADIUS):
    """Round the corners of a pane already pasted square onto the canvas.

    Only the four r-by-r corner blocks are touched, each blended back toward
    the background that was behind it -- 4 * 22 * 22 pixels instead of the
    whole pane, which is the difference between rounding these corners for
    free and paying a frame-sized float32 composite to do it.
    """
    if w < 2 * r or h < 2 * r:
        return
    for by, bx, a in ((y, x, _CORNER_A),
                      (y, x + w - r, _CORNER_A[:, ::-1]),
                      (y + h - r, x, _CORNER_A[::-1, :]),
                      (y + h - r, x + w - r, _CORNER_A[::-1, ::-1])):
        fg = canvas[by:by + r, bx:bx + r].astype(np.float32)
        bg = wash[by:by + r, bx:bx + r].astype(np.float32)
        canvas[by:by + r, bx:bx + r] = (fg * a + bg * (1.0 - a)).astype(np.uint8)


ASCII_MAP = str.maketrans({
    "\u00b0": " deg", "\u00d7": "x", "\u2013": "-", "\u2014": "--",
    "\u2212": "-", "\u00b7": "-", "\u2022": "-", "\u2026": "...",
    "\u2192": "->", "\u2190": "<-", "\u2191": "^", "\u2193": "v",
    "\u2713": "OK", "\u2018": "'", "\u2019": "'", "\u201c": '"',
    "\u201d": '"', "\u00a0": " ",
})


def ascii_text(label) -> str:
    """Whatever came in, rendered with characters this font actually has."""
    text = str(label).translate(ASCII_MAP)
    if text.isascii():
        return text
    return "".join(ch if ch.isascii() else "?" for ch in text)


_TEXT_CACHE_MAX = 20000
_TEXT_SIZES = {}
_WRAPS = {}
_EDIT_WRAPS = {}
_FITS = {}


def _remember(cache, key, value):
    """Store one memoised layout result, emptying the cache when it gets big.

    Every one of these is a pure function of its arguments (one fixed font),
    so a hit is always right. Emptying instead of evicting one at a time keeps
    the hit path a single dict lookup.
    """
    if len(cache) >= _TEXT_CACHE_MAX:
        cache.clear()
    cache[key] = value
    return value


def text_size(label, scale, thickness=1):
    """Pixel size of `label`, memoised.

    The sidebar alone used to ask cv2 for ~950 text sizes a frame -- every
    word of every message, re-wrapped on every frame -- which by itself was a
    good part of why a click took a visible moment to show.
    """
    key = (label if isinstance(label, str) else str(label), scale, thickness)
    size = _TEXT_SIZES.get(key)
    if size is None:
        size = _remember(_TEXT_SIZES, key, cv2.getTextSize(
            ascii_text(key[0]), FONT, scale, thickness)[0])
    return size


def draw_text(img, label, org, scale=0.5, colour=C_TEXT, thickness=1):
    cv2.putText(img, ascii_text(label), (int(org[0]), int(org[1])), FONT,
                scale, colour, thickness, cv2.LINE_AA)


def wrap_text(text, width, scale):
    """Greedy word wrap, measured with the font actually used to draw.

    Lives at module level because two different cards need it; AISidebar._wrap
    is a thin delegate so the sidebar's call sites read as they always did.
    Memoised: a message wraps the same way every frame it is on screen.
    """
    key = (str(text), width, scale)
    hit = _WRAPS.get(key)
    if hit is None:
        hit = _remember(_WRAPS, key, tuple(_wrap_text(key[0], width, scale)))
    return list(hit)


def _wrap_text(text, width, scale):
    lines = []
    for para in str(text).splitlines() or [""]:
        words, line = para.split(), ""
        if not words:
            lines.append("")
            continue
        for w in words:
            probe = f"{line} {w}".strip()
            if text_size(probe, scale, 1)[0] > width and line:
                lines.append(line)
                line = w
            else:
                line = probe
        lines.append(line)
    return lines or [""]


def wrap_editable(text, width, scale):
    """Word wrap that never loses a character -- for an editable field.

    Returns the visual lines as (start, end) index pairs into `text`, so a
    caret position maps to a line and a column with no guessing. wrap_text
    above cannot be used for this: it re-splits on whitespace and hands back
    strings, which is fine for a read-only paragraph but leaves an editor
    unable to say which character a click or an arrow key landed on.

    Every character belongs to exactly one line except a '\\n', which ends
    its line and belongs to none -- so an empty line between two newlines,
    and the empty line a trailing newline opens, both come back as an empty
    (start, start) pair and the caret can sit on them.

    Memoised: the prompt box is re-wrapped every frame it is drawn.
    """
    key = (str(text), width, scale)
    hit = _EDIT_WRAPS.get(key)
    if hit is None:
        hit = _remember(_EDIT_WRAPS, key,
                        tuple(_wrap_editable(key[0], width, scale)))
    return list(hit)


def _wrap_editable(text, width, scale):
    n = len(text)
    lines = []
    seg_start = 0
    while True:
        nl = text.find("\n", seg_start)
        seg_end = n if nl < 0 else nl
        start = seg_start
        while True:
            end = seg_end
            if text_size(text[start:end], scale, 1)[0] > width:
                end = start
                while (end < seg_end and
                       text_size(text[start:end + 1], scale, 1)[0] <= width):
                    end += 1
                end = max(end, start + 1)
                brk = text.rfind(" ", start, end)
                if brk > start:
                    end = brk + 1
            lines.append((start, end))
            start = end
            if start >= seg_end:
                break
        if nl < 0:
            break
        seg_start = nl + 1
    return lines


def caret_line_col(lines, cursor):
    """Which (line index, column within that line) a caret index sits at.

    A caret exactly on a wrap boundary belongs to the line that ENDS there,
    so it draws at the right-hand edge of the text it just typed rather than
    jumping ahead of a line it has not reached yet.
    """
    if not lines:
        return 0, 0
    for i, (start, end) in enumerate(lines):
        if cursor <= end:
            return i, max(0, cursor - start)
    return len(lines) - 1, max(0, cursor - lines[-1][0])


def fit_text(text, width, scale):
    """One line, truncated with "..." if it would overflow width.

    Lives at module level for the same reason as wrap_text: AISidebar._fit
    is a thin delegate so its call sites keep working unchanged. Memoised,
    and the cut point is found by bisection rather than one character at a
    time -- a long plan step used to cost a getTextSize per character it
    lost, every frame.
    """
    text = str(text)
    key = (text, width, scale)
    hit = _FITS.get(key)
    if hit is not None:
        return hit
    if text_size(text, scale, 1)[0] <= width:
        return _remember(_FITS, key, text)
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_size(text[:mid] + "...", scale, 1)[0] <= width:
            lo = mid
        else:
            hi = mid - 1
    return _remember(_FITS, key, text[:lo] + "...")


def draw_text_centred(img, label, rect, scale=0.5, colour=C_TEXT, thickness=1):
    x0, y0, x1, y1 = rect
    w, h = text_size(label, scale, thickness)
    draw_text(img, label, (x0 + (x1 - x0 - w) / 2, y0 + (y1 - y0 + h) / 2),
              scale, colour, thickness)


def draw_chevron(img, centre, size, colour, thickness=2, up=False):
    cx, cy = centre
    dy = -size if up else size
    pts = [(cx - size, cy - dy // 2), (cx, cy + dy // 2), (cx + size, cy - dy // 2)]
    cv2.polylines(img, [np.array(pts, np.int32)], False, colour, thickness,
                  cv2.LINE_AA)


@dataclass
class CameraSettings:
    """Software image adjustments applied to every grabbed frame."""
    zoom: float = 1.0
    brightness: int = 0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 0.0
    rotation: int = 0
    mirror: bool = False

    def apply(self, frame):
        if self.rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self.rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        if self.mirror:
            frame = cv2.flip(frame, 1)

        if self.zoom > 1.001:
            h, w = frame.shape[:2]
            cw = max(8, int(w / self.zoom))
            ch = max(8, int(h / self.zoom))
            x0 = (w - cw) // 2
            y0 = (h - ch) // 2
            frame = cv2.resize(frame[y0:y0 + ch, x0:x0 + cw], (w, h),
                               interpolation=cv2.INTER_LINEAR)

        if abs(self.contrast - 1.0) > 1e-3 or self.brightness != 0:
            frame = cv2.convertScaleAbs(frame, alpha=self.contrast,
                                        beta=self.brightness)

        if abs(self.saturation - 1.0) > 1e-3:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * self.saturation, 0, 255)
            frame = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        if self.sharpness > 1e-3:
            blur = cv2.GaussianBlur(frame, (0, 0), 2.0)
            frame = cv2.addWeighted(frame, 1.0 + self.sharpness,
                                    blur, -self.sharpness, 0)

        return frame


class CameraManager:
    """Finds connected cameras and lets you cycle through them."""

    RECONNECT_EVERY = 3.0

    def __init__(self, max_index_to_probe: int = 6,
                 settings: Optional[CameraSettings] = None):
        self.available_indices = self._probe_cameras(max_index_to_probe)
        if not self.available_indices:
            raise RuntimeError("No cameras found.")
        self.current_pos = 0
        self.cap = None
        self.settings = settings or CameraSettings()
        self._init_frame_state()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_ok = time.time()
        self._next_reconnect = 0.0
        self._open_current()
        self._thread = threading.Thread(target=self._grab_loop, daemon=True)
        self._thread.start()

    def _init_frame_state(self):
        self._latest = None
        self._seq = 0
        self._newest = (None, 0)

    def _publish(self, frame):
        """Make `frame` the newest one. Each grab is a new array that nothing
        ever draws on, so readers may keep a reference without copying. The
        (frame, number) pair is replaced in one assignment so a reader can
        never pair one frame with another's number."""
        if frame is not None:
            self._seq += 1
        self._latest = frame
        self._newest = (frame, self._seq)

    @staticmethod
    def _probe_cameras(max_index_to_probe: int):
        """Open indices in order, stopping after two consecutive misses.

        Walking the full range unconditionally made macOS print an
        "out device of bound" error for every index past the last real
        camera, which looked like a failure and was only noise.

        isOpened() alone is not proof of a working camera: on macOS, an
        index cv2 has opened but has no camera permission for (or that
        another app already has open) still reports isOpened() == True,
        and every read() from it then fails forever. A few real read
        attempts, not just the one the old check made, are what actually
        tell the two apart from a camera that is merely slow to wake up --
        a printed reason is the only way "camera 0 shows nothing" is
        distinguishable from "camera 0 was never offered" from the
        console, since either looks identical from inside the app itself.
        """
        found, misses = [], 0
        for idx in range(max_index_to_probe):
            cap = cv2.VideoCapture(idx)
            opened = cap is not None and cap.isOpened()
            alive = False
            if opened:
                for attempt in range(5):
                    alive = cap.read()[0]
                    if alive:
                        break
                    time.sleep(0.1)
            if cap is not None:
                cap.release()
            if alive:
                found.append(idx)
                misses = 0
            else:
                if opened:
                    print(f"[camera] index {idx} opened but sent no frame -- "
                         f"check System Settings > Privacy & Security > "
                         f"Camera for this app, and that no other app "
                         f"(Zoom, FaceTime, Photo Booth...) already has it open")
                misses += 1
                if misses >= 2 and found:
                    break
        return found

    def _open_current(self):
        """Open the camera at current_pos. Returns whether it came up alive.

        isOpened() is not enough here either -- see _probe_cameras -- so
        this waits (briefly; this only ever runs from a deliberate camera
        switch, never every frame) for a real frame the same way, rather
        than reporting a switch as successful when the feed is about to
        sit frozen.
        """
        with self._lock:
            if self.cap is not None:
                self.cap.release()
            idx = self.available_indices[self.current_pos]
            self.cap = cv2.VideoCapture(idx)
            ok = self.cap.isOpened()
            frame = None
            if ok:
                for attempt in range(5):
                    got, frame = self.cap.read()
                    if got:
                        break
                    time.sleep(0.1)
                ok = got
            self._publish(frame if ok else None)
        if self.cap.isOpened() and not ok:
            print(f"[camera] index {idx} opened but sent no frame -- "
                 f"check System Settings > Privacy & Security > Camera "
                 f"for this app, and that no other app already has it open")
        return ok

    def _grab_loop(self):
        """Keep the newest frame ready.

        cap.read() blocks until the sensor has a frame -- a third of the
        budget at 30 fps, spent doing nothing. On its own thread the UI loop
        always finds a frame waiting and never waits on the camera.

        A camera that gets unplugged mid-run just starts returning `False`
        forever -- there's no exception to catch, `_latest` simply stops
        updating and the app would sit there showing the last frame it ever
        grabbed. So a read failure that persists past RECONNECT_EVERY
        triggers the same reopen `switch()`/`select()` already do, on this
        thread, at that same cadence -- if the camera comes back (replugged,
        woken up), the feed comes back with it instead of staying frozen.

        A camera whose read() returns instantly (no frame ever coming, e.g.
        permission not yet granted, or another app already has the device)
        used to spin this loop close to CPU-bound: read() returning in
        under a millisecond meant only the 20ms sleep stood between one
        iteration and the next, taking the GIL and this manager's OWN LOCK
        with it every single time. That lock is also what main() blocks on
        at startup (_open_current, read()) and what switch()/select() need
        from the UI thread -- so a camera stuck in this state didn't just
        burn CPU, it starved every other thread of the lock badly enough to
        look exactly like a frozen window with no error at all. The sleep
        now always runs (moved out of the `else` branch), so a read that
        returns instantly is throttled the same as one that legitimately
        fails, and the lock is held only for the instant of the read/reopen
        itself rather than being fought over every native VideoCapture call.
        """
        while not self._stop.is_set():
            with self._lock:
                cap = self.cap
                ok, frame = (cap.read() if cap is not None else (False, None))
            if ok:
                self._publish(frame)
                self._last_ok = time.time()
            else:
                now = time.time()
                if now >= self._next_reconnect:
                    self._next_reconnect = now + self.RECONNECT_EVERY
                    idx = self.available_indices[self.current_pos]
                    with self._lock:
                        if self.cap is not None:
                            self.cap.release()
                        self.cap = cv2.VideoCapture(idx)
            time.sleep(0.02)

    def switch(self):
        """Cycle to the next known camera. Returns whether it came up alive."""
        old_pos = self.current_pos
        self.current_pos = (self.current_pos + 1) % len(self.available_indices)
        if self._open_current():
            print(f"[camera] switched to index {self.available_indices[self.current_pos]}")
            return True
        print(f"[camera] index {self.available_indices[self.current_pos]} failed to open, reverting")
        self.current_pos = old_pos
        self._open_current()
        return False

    def select(self, index: int):
        """Open a camera by its device index. Returns True if it changed."""
        if index not in self.available_indices:
            return False
        pos = self.available_indices.index(index)
        if pos == self.current_pos:
            return False
        old_pos = self.current_pos
        self.current_pos = pos
        if self._open_current():
            print(f"[camera] selected index {index}")
            return True
        print(f"[camera] index {index} failed to open, reverting")
        self.current_pos = old_pos
        self._open_current()
        return False

    def read(self):
        frame = self._latest
        if frame is None:
            return False, None
        out = self.settings.apply(frame)
        return True, out if out is not frame else frame.copy()

    def latest(self):
        """(newest raw frame, its sequence number), without copying or
        adjusting it -- the frame loop does that once per new frame rather
        than once per window redraw. The frame must not be drawn on."""
        return self._newest

    def current_index(self):
        return self.available_indices[self.current_pos]

    def release(self):
        self._stop.set()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            print("[camera] grabber did not stop; leaving the device to exit")
            return
        with self._lock:
            if self.cap is not None:
                self.cap.release()
                self.cap = None


ARDUINO_PORT_HINTS = ("usbmodem", "usbserial", "wchusbserial", "ttyacm", "ttyusb")
ARDUINO_BAUD = 115200
DIRECTION_LETTERS = {"up": "u", "down": "d", "left": "l", "right": "r"}
SLOW_SUFFIX = "q"
HEIGHT_UP_CMD = "hu"
HEIGHT_DOWN_CMD = "hd"
GRIP_CMD_LETTER = "g"
GRIP_MIN_DEG = 0
GRIP_MAX_DEG = 90
GRIP_SEND_INTERVAL_S = 0.05


def grip_command(angle) -> str:
    """The serial token for a jaw angle, clamped to what the servo accepts."""
    deg = int(round(float(angle)))
    deg = max(GRIP_MIN_DEG, min(GRIP_MAX_DEG, deg))
    return f"{GRIP_CMD_LETTER}{deg}"


JOG_PULSE_S = 0.1
SIMPLE_JOG_PULSE_S = 0.2
SLOW_APPROACH_CELLS = 1
TAG_HOLD_SECONDS = 0.35
AUTO_GRIP_COMMAND_DELAY_S = 1.0
AUTO_PULSE_S = 0.1
AUTO_PICKUP_HX_S = 3.0
AUTO_ACTION_GAP_S = 1.0
AUTO_GRIP_DOWN_MAX_S = 25.0
AUTO_PRESS_BACKOFF_S = 0.2
AUTO_RELEASE_DURATION_S = 3.0
AUTO_ACTION_MAX_S = 90.0

GRIPPER_NUDGE_S = 0.2
GRIPPER_NUDGE_DIRECTION = "left"
GRIPPER_NUDGE_ACTIONS = {"pickup": True, "keep": False,
                         "press": False, "release": False}


def load_gripper_nudge(settings):
    global GRIPPER_NUDGE_S, GRIPPER_NUDGE_DIRECTION
    GRIPPER_NUDGE_S = max(0.0, min(2.0, float(
        settings.get("nudge_s", GRIPPER_NUDGE_S))))
    direction = str(settings.get("nudge_direction", GRIPPER_NUDGE_DIRECTION))
    if direction in DIRECTION_LETTERS:
        GRIPPER_NUDGE_DIRECTION = direction
    saved_actions = settings.get("nudge_actions")
    if isinstance(saved_actions, dict):
        for action in GRIPPER_NUDGE_ACTIONS:
            if action in saved_actions:
                GRIPPER_NUDGE_ACTIONS[action] = bool(saved_actions[action])


def has_serial_stop_signal(data) -> bool:
    """Whether a sensor packet is the board saying "contact" -- s/S/stop.

    Matched a token at a time. The old test ended in `"s" in text.lower()`,
    which is true of any line with an s ANYWHERE in it: "sensors ok",
    "pos 40", "status". Every one of those ended the automatic pickup's
    descent early, and an early end means the jaw closes on air and the
    lift is timed from a descent that never finished. A whole token is the
    thing the firmware actually sends, and it still accepts "S\r\n",
    "ok S" and "stop" -- just not a stray letter inside another word.
    """
    text = data.decode("ascii", "ignore") if isinstance(data, bytes) else str(data)
    return any(token.strip(".,;:").lower() in ("s", "stop")
               for token in text.split())

CARET_BLINK_PERIOD = 1.06
CARET_BLINK_ON = 0.53


def caret_visible(state) -> bool:
    """Whether the text-field caret should be drawn on this frame -- blinks
    like a native text field, and resets to solid on every keystroke or
    cursor move so it never looks like it vanished mid-edit."""
    elapsed = time.time() - state.ai_caret_reset_at
    return (elapsed % CARET_BLINK_PERIOD) < CARET_BLINK_ON


class SerialLink:
    """One lowercase letter per move: u/d/l/r start it, s stops it, and the
    same letter with a trailing 'q' (uq/dq/lq/rq) means the same move but
    slower -- sent for the last stretch into a target cell.

    Fails open everywhere: with pyserial missing, no port chosen, or the
    Arduino unplugged, every call here is a no-op and the rest of the app
    runs exactly as it did before this existed.
    """

    RECONNECT_EVERY = 3.0
    BOOT_DELAY = 2.0

    def __init__(self):
        self.port = None
        self.conn = None
        self.last_error = None
        self._last_sent = None
        self._ready_at = 0.0
        self._next_reconnect = 0.0
        self._reconnecting = False
        self._last_logged_error = None
        self.auto_reconnect = True
        self.on_line = None
        self.on_bytes = None
        self.last_received = ""
        self._rx_buf = b""
        self._rx_chunk_at = 0.0
        self._tx_queue = queue.Queue()
        self._tx_thread = threading.Thread(target=self._tx_loop, daemon=True)
        self._tx_thread.start()

    def _tx_loop(self):
        while True:
            letter = self._tx_queue.get()
            conn = self.conn
            if conn is None:
                continue
            try:
                conn.write(letter.encode("ascii"))
                if self.on_line:
                    self.on_line("tx", letter)
            except Exception as e:
                self.last_error = str(e)
                print(f"[serial] write failed, disconnecting: {e}")
                if self.on_line:
                    self.on_line("sys", f"Write failed, disconnecting: {e}")
                self.disconnect()

    def available_ports(self):
        if serial_list_ports is None:
            return []
        try:
            return list(serial_list_ports.comports())
        except Exception as e:
            self.last_error = str(e)
            return []

    def guess_arduino_port(self):
        """Best-effort pick of the port that looks like an Arduino Uno."""
        best = None
        for p in self.available_ports():
            dev = (p.device or "")
            desc = f"{p.description or ''} {p.manufacturer or ''}".lower()
            if "arduino" in desc:
                return p.device
            if best is None and any(h in dev.lower() for h in ARDUINO_PORT_HINTS):
                best = p.device
        return best

    @property
    def connected(self):
        return self.conn is not None and self.conn.is_open

    def connect(self, port: str):
        if serial is None:
            self.last_error = "pyserial is not installed."
            return False
        self.disconnect()
        try:
            self.conn = serial.Serial(port, ARDUINO_BAUD, timeout=0,
                                      write_timeout=0.5)
            self.port = port
            self.last_error = None
            self._last_sent = None
            self._ready_at = time.time() + self.BOOT_DELAY
            self.auto_reconnect = True
            self._last_logged_error = None
            print(f"[serial] connected to {port}")
            if self.on_line:
                self.on_line("sys", f"Connected to {port} @ {ARDUINO_BAUD} "
                                    f"-- waiting {self.BOOT_DELAY:g}s for it to reset.")
            return True
        except Exception as e:
            self.conn = None
            self.port = None
            self.last_error = str(e)
            print(f"[serial] could not open {port}: {e}")
            if self.on_line and self.last_error != self._last_logged_error:
                self._last_logged_error = self.last_error
                self.on_line("sys", f"Could not open {port}: {e}")
            return False

    def disconnect(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            if self.on_line:
                self.on_line("sys", "Disconnected.")
        self.conn = None
        self._last_sent = None

    def _write(self, letter: str) -> bool:
        """Queues the letter for the writer thread and returns True as soon
        as it is queued -- never blocks on the port itself. A caller that
        needs "did this actually reach the board" has no stronger guarantee
        to read here than before: the old synchronous write only confirmed
        the bytes left this process, not that the Arduino received them,
        and a failed write already disconnects (via _tx_loop) exactly as it
        did inline, so a caller's next _write correctly sees `connected`
        turn False rather than silently succeeding into a dead port.
        """
        if not self.connected:
            return False
        if time.time() < self._ready_at:
            return False
        self._tx_queue.put(letter)
        return True

    def send_direction(self, direction, slow=False):
        """direction is 'up'/'down'/'left'/'right'/None (None means stop).

        Only writes on a change: 'u'/'d'/'l'/'r' each start the Arduino
        moving that way on its own until it sees an 's', so repeating the
        same letter every frame would be redundant, not just wasteful. `slow`
        appends a 'q' (see SLOW_SUFFIX) -- a real change in what is sent, not
        a flag on top of it, so easing into a target cell from a fast
        approach re-sends the direction just like a turn would.
        `_last_sent` only updates once the bytes are actually confirmed out,
        so a command dropped by a disconnected port or a still-booting board
        keeps getting retried instead of being silently given up on.
        """
        letter = DIRECTION_LETTERS.get(direction, "s")
        if slow and direction is not None:
            letter += SLOW_SUFFIX
        if letter == self._last_sent:
            return
        if self._write(letter):
            self._last_sent = letter

    def send_command(self, text: str) -> bool:
        """Write a token verbatim -- for one-shot commands like the height
        jogs, which are not directions and must not be de-duplicated.

        `send_direction` skips a write when the letter matches the last one
        sent, because 'u' means "keep going up until told to stop". A height
        jog is the opposite: it is a discrete nudge, and pressing the button
        twice has to send it twice. `_last_sent` is deliberately left alone,
        since this changes nothing about which way the XY axes are running.
        """
        return self._write(text)

    def halt(self) -> bool:
        """Send the stop letter NOW, whatever was last sent.

        `send_direction(None)` skips the write when 's' has already gone out,
        which is right for a de-duplicated stream and wrong for a panic
        button: the operator pressing it can see the carriage still moving
        and does not care what the software believes it already sent. Missed
        bytes and a board that rebooted mid-move both look exactly like this.
        """
        if self._write("s"):
            self._last_sent = "s"
            return True
        return False

    def pump_receive(self):
        """Drain incoming serial bytes and deliver them to the observer."""
        if not self.connected:
            return
        try:
            count = self.conn.in_waiting
            data = self.conn.read(count) if count else b""
        except Exception as e:
            if self.on_line:
                self.on_line("sys", f"Read failed: {e}")
            return
        if data:
            self._rx_buf += data
            self._rx_chunk_at = time.time()
            while b"\n" in self._rx_buf:
                raw, self._rx_buf = self._rx_buf.split(b"\n", 1)
                text = raw.decode("utf-8", "replace").rstrip("\r")
                if text:
                    self.last_received = text
                    if self.on_line:
                        self.on_line("rx", text)
            if self.on_bytes is not None:
                self.on_bytes(data)
        elif self._rx_buf and time.time() - self._rx_chunk_at >= 0.5:
            text = self._rx_buf.decode("utf-8", "replace").rstrip("\r")
            self._rx_buf = b""
            if text:
                self.last_received = text
                if self.on_line:
                    self.on_line("rx", text)

    def maybe_reconnect(self):
        """Called every frame: try to find and open the Arduino again after
        it drops (unplugged, USB hiccup, port grabbed by something else),
        without hammering the OS with open() calls every frame. Does
        nothing after an operator-requested disconnect -- that is a
        deliberate "leave it alone", not a drop to recover from.

        The attempt itself runs on its own thread. Enumerating ports walks
        IOKit and opening one waits on the driver: together they can block
        for the best part of a second, and on the render loop that is a
        second where the window does not redraw and no click is answered.
        """
        if self.connected or serial is None or not self.auto_reconnect:
            return
        if self._reconnecting:
            return
        now = time.time()
        if now < self._next_reconnect:
            return
        self._next_reconnect = now + self.RECONNECT_EVERY
        self._reconnecting = True
        threading.Thread(target=self._reconnect_worker, daemon=True).start()

    def _reconnect_worker(self):
        try:
            port = self.port or self.guess_arduino_port()
            if port:
                self.connect(port)
        except Exception as e:
            self.last_error = str(e)
        finally:
            self._reconnecting = False


ARDUINO = SerialLink()


class AprilTagDetector:
    def __init__(self):
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        params = cv2.aruco.DetectorParameters()
        params.adaptiveThreshWinSizeMin = 3
        params.adaptiveThreshWinSizeMax = 53
        params.adaptiveThreshWinSizeStep = 4
        params.adaptiveThreshConstant = 7
        params.minMarkerPerimeterRate = 0.02
        params.maxMarkerPerimeterRate = 4.0
        params.polygonalApproxAccuracyRate = 0.05
        params.minCornerDistanceRate = 0.03
        params.minOtsuStdDev = 3.0
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.cornerRefinementWinSize = 5
        params.cornerRefinementMaxIterations = 30
        params.cornerRefinementMinAccuracy = 0.05
        params.errorCorrectionRate = 0.8
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, params)

    def detect(self, frame):
        """Returns (corners, ids) exactly as cv2.aruco does. ids is None
        if nothing was found."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        return corners, ids

    @staticmethod
    def tag_center(corner_set) -> tuple:
        """corner_set is one tag's 4 corner points, shape (1,4,2)."""
        pts = corner_set.reshape(4, 2)
        cx = float(np.mean(pts[:, 0]))
        cy = float(np.mean(pts[:, 1]))
        return cx, cy


TAG_CENTER_TOL_FRAC = 0.14
TAG_BOUNDARY_MIN_INSIDE = 0.92


def tag_cell_centering(pts, grid: "Grid", col: int, row: int) -> bool:
    """Is a detected tag both mostly INSIDE one cell and CENTERED on it?

    `pts` is the tag's 4 corners in full-frame pixels. Being "on" a cell by
    its centre point alone (what pixel_to_cell/contains_pixel check, used
    for path-finding) is not enough here -- the whole tag has to sit inside
    the cell's own boundary, hugging its centre, before a step is allowed
    to count as arrived.
    """
    x0, y0, x1, y1 = grid.cell_rect(col, row)
    cell_w, cell_h = x1 - x0, y1 - y0
    if cell_w <= 0 or cell_h <= 0:
        return False
    xs, ys = pts[:, 0], pts[:, 1]
    tx0, ty0, tx1, ty1 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
    tag_area = (tx1 - tx0) * (ty1 - ty0)
    if tag_area <= 0:
        return False
    ix0, iy0 = max(tx0, x0), max(ty0, y0)
    ix1, iy1 = min(tx1, x1), min(ty1, y1)
    inside_frac = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0) / tag_area
    cx, cy = float(xs.mean()), float(ys.mean())
    cell_cx, cell_cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    offset = math.hypot(cx - cell_cx, cy - cell_cy)
    tol = TAG_CENTER_TOL_FRAC * min(cell_w, cell_h)
    return inside_frac >= TAG_BOUNDARY_MIN_INSIDE and offset <= tol


TRIG_CAMERA_HEIGHT_IN = 35.0
TRIG_TAG_HEIGHT_IN = 5.5
TRIG_BOARD_HEIGHT_IN = 0.0


def trig_heights() -> tuple:
    """(h, H) -- tag and camera heights ABOVE THE BOARD, in inches."""
    h = TRIG_TAG_HEIGHT_IN - TRIG_BOARD_HEIGHT_IN
    H = TRIG_CAMERA_HEIGHT_IN - TRIG_BOARD_HEIGHT_IN
    return h, H


def trig_offset_k() -> float:
    """k = (H-h)/H, from the heights above the board.

    Recomputed live so a Trigonometry-menu change takes effect at once. Falls
    back to 1.0 (no correction at all) rather than producing nonsense if the
    numbers are physically impossible -- a camera below the board, or a tag
    at or above the camera.
    """
    h, H = trig_heights()
    if H <= 0 or h < 0 or h >= H:
        return 1.0
    return (H - h) / H


TRIG_PIVOT_X = 0.0
TRIG_PIVOT_Y = 0.0

DEFAULT_GRIPPER_OFFSET_UP_DOWN = -7
DEFAULT_GRIPPER_OFFSET_RIGHT_LEFT = 0
GRIPPER_OFFSET_UP_DOWN = DEFAULT_GRIPPER_OFFSET_UP_DOWN
GRIPPER_OFFSET_RIGHT_LEFT = DEFAULT_GRIPPER_OFFSET_RIGHT_LEFT
GRIPPER_VERTICAL_DIRECTION = "up"
GRIPPER_HORIZONTAL_DIRECTION = "right"
MAX_GRIPPER_OFFSET = 10


def gripper_offset() -> tuple:
    """(dcol, drow) from the tag's cell to the gripper's cell."""
    return GRIPPER_OFFSET_RIGHT_LEFT, GRIPPER_OFFSET_UP_DOWN


def load_gripper_offsets(settings):
    """Load independent axes, migrating the former single-direction setting."""
    global GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT
    vertical, horizontal = DEFAULT_GRIPPER_OFFSET_UP_DOWN, DEFAULT_GRIPPER_OFFSET_RIGHT_LEFT
    if "gripper_cells" in settings:
        count = max(0, min(MAX_GRIPPER_OFFSET, int(settings["gripper_cells"])))
        direction = settings.get("gripper_dir", "up")
        if direction in ("up", "down"):
            vertical, horizontal = count * (-1 if direction == "up" else 1), 0
        elif direction in ("left", "right"):
            vertical, horizontal = 0, count * (-1 if direction == "left" else 1)
    GRIPPER_OFFSET_UP_DOWN = max(-MAX_GRIPPER_OFFSET, min(MAX_GRIPPER_OFFSET,
        int(settings.get("gripper_up_down", vertical))))
    GRIPPER_OFFSET_RIGHT_LEFT = max(-MAX_GRIPPER_OFFSET, min(MAX_GRIPPER_OFFSET,
        int(settings.get("gripper_right_left", horizontal))))

    global GRIPPER_VERTICAL_DIRECTION, GRIPPER_HORIZONTAL_DIRECTION
    GRIPPER_VERTICAL_DIRECTION = ("up" if GRIPPER_OFFSET_UP_DOWN < 0 else
        "down" if GRIPPER_OFFSET_UP_DOWN > 0 else
        "down" if settings.get("gripper_vertical_direction") == "down" else "up")
    GRIPPER_HORIZONTAL_DIRECTION = ("left" if GRIPPER_OFFSET_RIGHT_LEFT < 0 else
        "right" if GRIPPER_OFFSET_RIGHT_LEFT > 0 else
        "left" if settings.get("gripper_horizontal_direction") == "left" else "right")


def offset_axis_label(value, negative, positive):
    return f"{abs(value)} {negative if value < 0 else positive}" if value else "0"


def gripper_cell(col, row) -> tuple:
    """Where the gripper is, given where the tag is.

    Deliberately NOT clamped to the board. The gripper really can hang off
    the edge when the tag is at the rim, and clamping would quietly report
    it as being on the last row -- which is exactly the lie that would make
    an unreachable target look reachable.
    """
    if col is None or row is None:
        return None, None
    dc, dr = gripper_offset()
    return col + dc, row + dr


def tag_cell_for(col, row) -> tuple:
    """The inverse: where the TAG has to stop so the gripper lands on
    (col, row). This is the one the guidance actually drives to."""
    if col is None or row is None:
        return None, None
    dc, dr = gripper_offset()
    return col - dc, row - dr


OPPOSITE_DIR = {"up": "down", "down": "up", "left": "right", "right": "left"}


ACTIVE_GRIPPER_PANEL = None


def automatic_gripper_busy() -> bool:
    """Whether an automatic gripper action owns the serial port right now."""
    panel = ACTIVE_GRIPPER_PANEL
    if panel is None:
        return False
    try:
        return bool(panel.automatic_busy())
    except Exception:
        return False

def unreachable_rows() -> set:
    """Row indices where NO column is reachable, given the gripper offset.

    A target row r is reachable only if the tag's stop row (r - dr) is still
    on the board -- so with the offset in the row axis, either every column
    in a row is unreachable or none are; there is no partial row.
    """
    dc, dr = gripper_offset()
    if dr == 0:
        return set()
    return {r for r in range(CONFIG.n_rows) if not (0 <= r - dr < CONFIG.n_rows)}


def unreachable_cols() -> set:
    """Same as unreachable_rows(), for a left/right offset."""
    dc, dr = gripper_offset()
    if dc == 0:
        return set()
    return {c for c in range(CONFIG.n_cols) if not (0 <= c - dc < CONFIG.n_cols)}


FIXED_UNREACHABLE_ROW_COUNT = 3

BLUE_LABEL_LAST_ROW = 13


def fixed_unreachable_rows() -> set:
    """The last FIXED_UNREACHABLE_ROW_COUNT rows (18-20 on a 20-row board),
    display only."""
    n = min(FIXED_UNREACHABLE_ROW_COUNT, CONFIG.n_rows)
    return set(range(CONFIG.n_rows - n, CONFIG.n_rows))


NO_REACH = ()


def reachable_cells():
    """(c0, r0, c1, r1), the half-open block of cells the gripper can work
    in -- the board minus the red band Grid.draw paints -- or None when no
    cell is reachable at all.

    The red band is whole rows and whole columns, and both of its sources
    sit at the board's edges (the offset-derived limit on one side, the
    fixed band at the bottom), so what is left is always one rectangle.
    """
    bad_rows = unreachable_rows() | fixed_unreachable_rows()
    bad_cols = unreachable_cols()
    rows = [r for r in range(CONFIG.n_rows) if r not in bad_rows]
    cols = [c for c in range(CONFIG.n_cols) if c not in bad_cols]
    if not rows or not cols:
        return None
    return min(cols), min(rows), max(cols) + 1, max(rows) + 1


def reachable_box(box, sx=1.0, sy=1.0):
    """The reachable cells' pixel rectangle inside the grid box `box`,
    scaled by (sx, sy) into another frame's pixels -- what Vision AI is
    allowed to look at. NO_REACH when no cell can be reached."""
    cells = reachable_cells()
    if cells is None:
        return NO_REACH
    c0, r0, c1, r1 = cells
    x0, y0, x1, y1 = box
    cw = (x1 - x0) / float(CONFIG.n_cols)
    ch = (y1 - y0) / float(CONFIG.n_rows)
    return ((x0 + c0 * cw) * sx, (y0 + r0 * ch) * sy,
            (x0 + c1 * cw) * sx, (y0 + r1 * ch) * sy)


def red_zone_hint() -> str:
    """Appended to "not found on the board": Vision AI no longer looks at the
    red band at all, so an object lying there reads as missing -- say so
    rather than leave the operator searching a board that clearly has it."""
    note = unreachable_board_note()
    if not note:
        return ""
    return (f" Vision AI only looks at the reachable part of the board -- "
            f"anything in the red {note} is not seen; move it out of the "
            f"red area first.")


def _index_spans(indices) -> list:
    """Sorted ints -> contiguous [start, end] runs, e.g. {16,17,18,19} ->
    [[16, 19]]. Shared by the row/column phrasing below."""
    spans = []
    for i in sorted(indices):
        if spans and i == spans[-1][1] + 1:
            spans[-1][1] = i
        else:
            spans.append([i, i])
    return spans


def unreachable_board_note() -> str:
    """The red band -- rows/columns the gripper's own geometry keeps it out
    of no matter how the tag is driven -- as a short phrase for a prompt:
    'row 17-20' or 'row 17-20 and column S-T'. Empty when nothing is
    excluded.

    Combines the same two sources Grid.draw paints red: unreachable_rows()/
    unreachable_cols() (the real, offset-derived limit) and
    fixed_unreachable_rows() (the separate always-on cosmetic band). Both
    read the same to a plan: nowhere in the union is a coordinate the robot
    can ever actually reach.
    """
    bad_rows = unreachable_rows() | fixed_unreachable_rows()
    bad_cols = unreachable_cols()
    parts = []
    if bad_rows:
        spans = [f"{CONFIG.rows[a]}-{CONFIG.rows[b]}" if a != b
                else str(CONFIG.rows[a])
                for a, b in _index_spans(bad_rows)]
        parts.append(f"row{'s' if len(bad_rows) > 1 else ''} "
                     + ", ".join(spans))
    if bad_cols:
        spans = [f"{CONFIG.columns[a]}-{CONFIG.columns[b]}" if a != b
                else CONFIG.columns[a]
                for a, b in _index_spans(bad_cols)]
        parts.append(f"column{'s' if len(bad_cols) > 1 else ''} "
                     + ", ".join(spans))
    return " and ".join(parts)


def gripper_offset_label() -> str:
    """Describe both independent axes for the panel and status line."""
    dc, dr = gripper_offset()
    parts = [offset_axis_label(v, neg, pos) for v, neg, pos in
             ((dr, "up", "down"), (dc, "left", "right")) if v]
    return " + ".join(parts) + " cells" if parts else "none"


def correct_tag_position(cx: float, cy: float, grid: "Grid") -> tuple:
    """The one call site everything downstream should use.

    There used to be a second, data-fitted correction here -- a homography
    fitted from measured (raw pixel, true board position) correspondences,
    which would have sat in front of the trig formula whenever it had been
    calibrated. It was never calibrated on this rig, and it is gone now: the
    trig formula is the whole correction, so what the Trigonometry panel says
    is exactly what the board does.
    """
    return apply_trig_offset(cx, cy, grid)


def apply_trig_offset(cx: float, cy: float, grid: "Grid") -> tuple:
    """Raw detected tag pixel -> where a flush marker at the same spot on the
    board would read.

    Pure trigonometry, nothing fitted: a point at height h and horizontal
    offset r from the camera's nadir images at the same angle as a FLUSH
    point at r * H/(H-h), so the true position is the raw reading pulled back
    toward the nadir by exactly k = (H-h)/H.
    """
    k = trig_offset_k()
    x0, y0, x1, y1 = grid.box
    ccx = (x0 + x1) / 2.0 + TRIG_PIVOT_X
    ccy = (y0 + y1) / 2.0 + TRIG_PIVOT_Y
    return (ccx + k * (cx - ccx), ccy + k * (cy - ccy))


class TagTracker:
    """AprilTag detection on its own thread, like the camera's own grabber.

    detectMarkers costs ~20ms on the probe image -- most of a frame's budget
    at 30fps, and by a wide margin the most expensive thing the loop did. It
    is also the least urgent: the answer guides a person pushing a gantry by
    hand, so being one frame old is worth nothing to anybody, while halving
    the frame rate is felt in every click and every menu.

    The loop submits frames and reads whatever the last completed detection
    found. A frame arriving while a detection is still running is dropped
    rather than queued -- the newest position is the only one worth having,
    and a queue would only add latency to it.
    """

    def __init__(self, max_width=None):
        self.max_width = max_width
        self.detector = AprilTagDetector()
        self._pending = None
        self._result = ([], None, None)
        self._busy = False
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, frame):
        """Offer the newest frame. Cheap and non-blocking when busy."""
        if frame is None or self._busy:
            return
        with self._lock:
            if self._pending is not None:
                return
            self._pending = frame.copy()
        self._wake.set()

    def latest(self, shape=None):
        """(corners, ids) in FULL-frame pixels, from the last completed pass.

        A result found at a different frame size -- a resize or a rotation
        mid-flight -- is discarded rather than drawn a few pixels out.
        """
        with self._lock:
            corners, ids, got = self._result
        if shape is not None and got is not None and got != shape:
            return [], None
        return corners, ids

    def _loop(self):
        while not self._stop.is_set():
            self._wake.wait(0.05)
            self._wake.clear()
            with self._lock:
                frame = self._pending
                self._pending = None
            if frame is None:
                continue
            self._busy = True
            try:
                shape = frame.shape[:2]
                h, w = shape
                ds = 1.0
                if self.max_width and w > self.max_width:
                    ds = self.max_width / float(w)
                    frame = cv2.resize(
                        frame, (self.max_width, max(1, int(h * ds))),
                        interpolation=cv2.INTER_AREA)
                corners, ids = self.detector.detect(frame)
                if ds != 1.0 and corners:
                    corners = [c / ds for c in corners]
                with self._lock:
                    self._result = (corners, ids, shape)
            except Exception as e:
                print(f"[tags] detection failed: {e}")
            finally:
                self._busy = False

    def stop(self):
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=1.0)


CORNER_RADIUS = 11
MIN_BOX_SIDE = 40
GRID_STAMP_SETTLE_S = 0.25


class Grid:
    """The grid lives inside an AXIS-ALIGNED BOX the user can reshape by
    dragging its corners.

    The boundary is stored as (x0, y0, x1, y1) rather than four free points,
    which is what keeps it a rectangle: dragging one corner moves the two
    edges it sits on, so the neighbouring corners follow and the shape can
    never become a general quadrilateral. With `square_cells` on (the
    default) the dragged corner is additionally snapped so cell width equals
    cell height -- the box then stays a true square when rows == columns.
    """

    def __init__(self, frame_width: int, frame_height: int, box=None,
                 square_cells: bool = True):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.square_cells = square_cells
        self.box = list(box) if box else self.default_box(frame_width, frame_height)
        self._clamp()


    @staticmethod
    def default_box(frame_width: int, frame_height: int):
        """A centred box with side ratio n_cols:n_rows, so every cell is
        square (and the whole box is a square on a 20x20 grid)."""
        cell = min(frame_width / CONFIG.n_cols, frame_height / CONFIG.n_rows) * 0.94
        w = cell * CONFIG.n_cols
        h = cell * CONFIG.n_rows
        x0 = (frame_width - w) / 2.0
        y0 = (frame_height - h) / 2.0
        return [x0, y0, x0 + w, y0 + h]

    def box_fractions(self):
        """The corners as fractions of the frame, for a size-independent save."""
        x0, y0, x1, y1 = self.box
        w = float(max(1, self.frame_width))
        h = float(max(1, self.frame_height))
        return [x0 / w, y0 / h, x1 / w, y1 / h]

    def reset_box(self):
        self.box = self.default_box(self.frame_width, self.frame_height)

    def config_changed(self):
        """Called after n_cols / n_rows change: re-fit for square cells."""
        self.reset_box()

    def update_size(self, frame_width: int, frame_height: int):
        if (frame_width, frame_height) == (self.frame_width, self.frame_height):
            return
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.reset_box()

    def _clamp(self):
        x0, y0, x1, y1 = self.box
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        x0 = max(0.0, min(float(self.frame_width - MIN_BOX_SIDE), x0))
        y0 = max(0.0, min(float(self.frame_height - MIN_BOX_SIDE), y0))
        x1 = min(float(self.frame_width), max(x0 + MIN_BOX_SIDE, x1))
        y1 = min(float(self.frame_height), max(y0 + MIN_BOX_SIDE, y1))
        self.box = [x0, y0, x1, y1]

    @property
    def cell_w(self):
        return (self.box[2] - self.box[0]) / CONFIG.n_cols

    @property
    def cell_h(self):
        return (self.box[3] - self.box[1]) / CONFIG.n_rows

    def corners(self):
        """TL, TR, BR, BL in pixel coordinates."""
        x0, y0, x1, y1 = self.box
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


    def pixel_to_cell(self, x: float, y: float):
        col = int((x - self.box[0]) // max(1e-6, self.cell_w))
        row = int((y - self.box[1]) // max(1e-6, self.cell_h))
        return (max(0, min(CONFIG.n_cols - 1, col)),
                max(0, min(CONFIG.n_rows - 1, row)))

    def contains_pixel(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.box
        return x0 <= x <= x1 and y0 <= y <= y1

    def cell_to_pixel_center(self, col_idx: int, row_idx: int):
        return (int(self.box[0] + (col_idx + 0.5) * self.cell_w),
                int(self.box[1] + (row_idx + 0.5) * self.cell_h))

    def cell_rect(self, col_idx: int, row_idx: int):
        return (self.box[0] + col_idx * self.cell_w,
                self.box[1] + row_idx * self.cell_h,
                self.box[0] + (col_idx + 1) * self.cell_w,
                self.box[1] + (row_idx + 1) * self.cell_h)

    def grid_to_pixel(self, col_f: float, row_f: float):
        """A continuous (col, row) coordinate -- as vision reports a polygon
        vertex -- to a pixel. col_f=0 is column A's left edge, col_f=1 is
        its right edge / column B's left edge, and so on; same for row_f."""
        return (self.box[0] + col_f * self.cell_w,
                self.box[1] + row_f * self.cell_h)

    def pixel_to_grid(self, x: float, y: float):
        """The inverse of grid_to_pixel: a pixel back to (col, row) units.

        Used to bring a refined outline, traced in the pixels of a crop of
        one object, back into the grid units everything else speaks.
        """
        col_f = (x - self.box[0]) / max(1e-6, self.cell_w)
        row_f = (y - self.box[1]) / max(1e-6, self.cell_h)
        return (max(0.0, min(float(CONFIG.n_cols), col_f)),
                max(0.0, min(float(CONFIG.n_rows), row_f)))


    def nearest_corner(self, x: float, y: float, max_dist: float = 30.0):
        best, best_d = None, max_dist
        for i, (cx, cy) in enumerate(self.corners()):
            d = float(np.hypot(cx - x, cy - y))
            if d < best_d:
                best, best_d = i, d
        return best

    def move_corner(self, index: int, x: float, y: float):
        """Drag one corner. The box stays a rectangle by construction, and
        stays square-celled when that lock is on."""
        x = max(0.0, min(float(self.frame_width), float(x)))
        y = max(0.0, min(float(self.frame_height), float(y)))
        x0, y0, x1, y1 = self.box
        ax, ay = (x1, y1) if index == 0 else \
                 (x0, y1) if index == 1 else \
                 (x0, y0) if index == 2 else (x1, y0)

        if self.square_cells:
            w = abs(x - ax)
            h = abs(y - ay)
            cell = max(w / CONFIG.n_cols, h / CONFIG.n_rows,
                       MIN_BOX_SIDE / float(max(CONFIG.n_cols, CONFIG.n_rows)))
            max_w = (self.frame_width - ax) if x >= ax else ax
            max_h = (self.frame_height - ay) if y >= ay else ay
            cell = min(cell, max(max_w, 1e-6) / CONFIG.n_cols,
                       max(max_h, 1e-6) / CONFIG.n_rows)
            w, h = cell * CONFIG.n_cols, cell * CONFIG.n_rows
            x = ax + (w if x >= ax else -w)
            y = ay + (h if y >= ay else -h)

        nx0, nx1 = sorted((ax, x))
        ny0, ny1 = sorted((ay, y))
        self.box = [nx0, ny0, nx1, ny1]
        self._clamp()


    def draw(self, frame, show_corners: bool = False):
        """Blur the room around the board, then lay the grid over it.

        Everything after the blur -- lines, the red and blue bands, the
        border and every label -- depends only on the box, the grid size and
        the reach, never on the picture, so it is recorded once as an
        AffineStamp and replayed as two cv2 calls. Drawing it from scratch
        every frame was ~15 ms, the single most expensive thing a frame did.
        """
        x0, y0, x1, y1 = self.box
        h, w = frame.shape[:2]
        ix0, iy0 = max(0, int(x0)), max(0, int(y0))
        ix1, iy1 = min(w, int(x1)), min(h, int(y1))

        for a, b, c, d in ((0, 0, w, iy0), (0, iy1, w, h),
                           (0, iy0, ix0, iy1), (ix1, iy0, w, iy1)):
            blur_band(frame, a, b, c, d)

        key = (w, h, tuple(self.box), CONFIG.n_cols, CONFIG.n_rows,
               frozenset(unreachable_rows() | fixed_unreachable_rows()),
               frozenset(unreachable_cols()))
        if getattr(self, "_overlay_key", None) == key:
            self._overlay.apply(frame, 0, 0)
        else:
            # Recording costs two full draws, so it waits until the box has
            # stopped changing: a corner being dragged is drawn directly,
            # exactly as fast as before, and the stamp is made once it rests.
            now = time.monotonic()
            if getattr(self, "_pending_key", None) != key:
                self._pending_key, self._pending_since = key, now
            if now - self._pending_since >= GRID_STAMP_SETTLE_S:
                self._overlay = AffineStamp(w, h, self._draw_overlay)
                self._overlay_key = key
                self._overlay.apply(frame, 0, 0)
            else:
                self._draw_overlay(frame)

        if show_corners:
            for i, (cx, cy) in enumerate(self.corners()):
                cv2.circle(frame, (int(cx), int(cy)), CORNER_RADIUS + 5,
                           _bgr("#ffffff"), -1, cv2.LINE_AA)
                cv2.circle(frame, (int(cx), int(cy)), CORNER_RADIUS,
                           C_ACCENT, -1, cv2.LINE_AA)
                cv2.circle(frame, (int(cx), int(cy)), CORNER_RADIUS,
                           _bgr("#ffffff"), 2, cv2.LINE_AA)

    def _draw_overlay(self, frame):
        """The grid's own marks, as Grid.draw always drew them after the
        blur. Called only to record the stamp."""
        x0, y0, x1, y1 = self.box
        h, w = frame.shape[:2]
        ix0, iy0 = max(0, int(x0)), max(0, int(y0))
        ix1, iy1 = min(w, int(x1)), min(h, int(y1))

        if ix1 > ix0 and iy1 > iy0:
            board = frame[iy0:iy1, ix0:ix1]
            line = board.copy()
            for c in range(CONFIG.n_cols + 1):
                x = int(x0 + c * self.cell_w) - ix0
                cv2.line(line, (x, 0), (x, iy1 - iy0), _bgr("#2f3545"), 1,
                         cv2.LINE_AA)
            for r in range(CONFIG.n_rows + 1):
                y = int(y0 + r * self.cell_h) - iy0
                cv2.line(line, (0, y), (ix1 - ix0, y), _bgr("#2f3545"), 1,
                         cv2.LINE_AA)
            frame[iy0:iy1, ix0:ix1] = cv2.addWeighted(line, 0.45, board, 0.55, 0)

        bad_rows = unreachable_rows() | fixed_unreachable_rows()
        bad_cols = unreachable_cols()
        if bad_rows or bad_cols:
            red = _bgr("#ef4444")
            overlay = frame[iy0:iy1, ix0:ix1].copy()
            for r in bad_rows:
                ry0 = int(y0 + r * self.cell_h) - iy0
                ry1 = int(y0 + (r + 1) * self.cell_h) - iy0
                cv2.rectangle(overlay, (0, max(0, ry0)),
                              (ix1 - ix0, min(iy1 - iy0, ry1)), red, -1)
            for c in bad_cols:
                cx0 = int(x0 + c * self.cell_w) - ix0
                cx1 = int(x0 + (c + 1) * self.cell_w) - ix0
                cv2.rectangle(overlay, (max(0, cx0), 0),
                              (min(ix1 - ix0, cx1), iy1 - iy0), red, -1)
            frame[iy0:iy1, ix0:ix1] = cv2.addWeighted(
                overlay, 0.35, frame[iy0:iy1, ix0:ix1], 0.65, 0)

        last_row_idx = min(BLUE_LABEL_LAST_ROW, CONFIG.n_rows)
        by1 = int(y0 + last_row_idx * self.cell_h) - iy0
        if by1 > 0:
            blue = _bgr("#3b82f6")
            overlay = frame[iy0:iy1, ix0:ix1].copy()
            cv2.rectangle(overlay, (0, 0), (ix1 - ix0, min(iy1 - iy0, by1)),
                         blue, -1)
            frame[iy0:iy1, ix0:ix1] = cv2.addWeighted(
                overlay, 0.18, frame[iy0:iy1, ix0:ix1], 0.82, 0)

        rounded_rect(frame, (x0, y0, x1, y1), 10, _bgr("#ffffff"), 2)

        for c, letter in enumerate(CONFIG.columns):
            w, _ = text_size(letter, 0.44, 1)
            draw_text(frame, letter,
                      (x0 + (c + 0.5) * self.cell_w - w / 2, y0 - 9),
                      0.44, _bgr("#ffffff"), 1)

        for r, num in enumerate(CONFIG.rows):
            label = str(num)
            w, h = text_size(label, 0.44, 1)
            draw_text(frame, label,
                      (x0 - w - 10, y0 + (r + 0.5) * self.cell_h + h / 2),
                      0.44, _bgr("#ffffff"), 1)
            draw_text(frame, label,
                      (x1 + 10, y0 + (r + 0.5) * self.cell_h + h / 2),
                      0.44, _bgr("#ffffff"), 1)

        for c, letter in enumerate(CONFIG.columns):
            w, h = text_size(letter, 0.44, 1)
            draw_text(frame, letter,
                      (x0 + (c + 0.5) * self.cell_w - w / 2, y1 + h + 9),
                      0.44, _bgr("#ffffff"), 1)

    def highlight_cell(self, frame, col_idx: int, row_idx: int, colour, alpha=0.32):
        x0, y0, x1, y1 = self.cell_rect(col_idx, row_idx)
        pad = 2
        rounded_rect(frame, (x0 + pad, y0 + pad, x1 - pad, y1 - pad), 8,
                     colour, -1, alpha=alpha)
        rounded_rect(frame, (x0 + pad, y0 + pad, x1 - pad, y1 - pad), 8,
                     colour, 2)


VISION_CELL_PX = 82
VISION_MIN_LONG_SIDE = 1400
VISION_MAX_LONG_SIDE = 2200
VISION_MAX_SCALE = 3.0
VISION_PAD_FRAC = 0.055


def vision_long_side() -> int:
    """How big to render the board: enough that a cell, and the name printed
    in it, stay legible whether the board is 11 cells across or 20."""
    want = VISION_CELL_PX * max(CONFIG.n_cols, CONFIG.n_rows)
    return int(max(VISION_MIN_LONG_SIDE, min(VISION_MAX_LONG_SIDE, want)))


CROP_DIM_ALPHA = 0.45


def render_board_region(frame_bgr, grid: Grid, c0, r0, c1, r1,
                        long_side=None, overlay_poly=None, labels=True,
                        subject_poly=None):
    """A rectangle of cells, drawn as the model should see it.

    The display frame is the wrong picture to reason over: the board is a
    fraction of it, the rest of the room is in shot, and the only labels are
    at the far edges -- so a vertex four cells in has nothing nearby to check
    itself against, and outlines come back drifted a cell off the object.

    This crops to the cells asked for, upscales them, and prints each cell's
    own name inside it, with the letters and numbers repeated on all four
    sides. The model reads the label under an object instead of counting to
    it. Coordinates stay absolute grid units at any zoom, so a close-up of
    D9-M12 answers in exactly the same numbers the whole board would.
    """
    if frame_bgr is None:
        return None
    h, w = frame_bgr.shape[:2]
    c0 = max(0, min(CONFIG.n_cols - 1, int(c0)))
    r0 = max(0, min(CONFIG.n_rows - 1, int(r0)))
    c1 = max(c0 + 1, min(CONFIG.n_cols, int(c1)))
    r1 = max(r0 + 1, min(CONFIG.n_rows, int(r1)))
    ncols, nrows = c1 - c0, r1 - r0

    x0, y0 = grid.grid_to_pixel(c0, r0)
    x1, y1 = grid.grid_to_pixel(c1, r1)
    ix0, iy0 = max(0, int(round(x0))), max(0, int(round(y0)))
    ix1, iy1 = min(w, int(round(x1))), min(h, int(round(y1)))
    if ix1 - ix0 < 16 or iy1 - iy0 < 16:
        return None

    board = frame_bgr[iy0:iy1, ix0:ix1]
    target = long_side or vision_long_side()
    scale = target / float(max(board.shape[:2]))
    scale = max(1.0, min(VISION_MAX_SCALE, scale))
    if scale > 1.0:
        board = cv2.resize(board, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_CUBIC)
    bh, bw = board.shape[:2]

    if subject_poly is not None and len(subject_poly) >= 3:
        cwf = bw / float(c1 - c0)
        chf = bh / float(r1 - r0)
        pts = np.array([[[int(round((c - c0) * cwf)), int(round((r - r0) * chf))]
                         for c, r in subject_poly]], np.int32)
        mask = np.zeros((bh, bw), np.uint8)
        cv2.fillPoly(mask, pts, 255)
        if mask.any():
            dark = (board.astype(np.float32) * (1.0 - CROP_DIM_ALPHA)).astype(np.uint8)
            board = np.where(mask[:, :, None] > 0, board, dark)

    pad = max(46, int(VISION_PAD_FRAC * max(bw, bh)))
    canvas = np.full((bh + 2 * pad, bw + 2 * pad, 3), 22, np.uint8)
    canvas[pad:pad + bh, pad:pad + bw] = board

    cw = bw / float(ncols)
    ch = bh / float(nrows)

    if not labels:
        return canvas

    lines = canvas[pad:pad + bh, pad:pad + bw].copy()
    for c in range(ncols + 1):
        x = min(int(round(c * cw)), bw - 1)
        cv2.line(lines, (x, 0), (x, bh), (255, 240, 160), 2, cv2.LINE_AA)
    for r in range(nrows + 1):
        y = min(int(round(r * ch)), bh - 1)
        cv2.line(lines, (0, y), (bw, y), (255, 240, 160), 2, cv2.LINE_AA)
    canvas[pad:pad + bh, pad:pad + bw] = cv2.addWeighted(
        lines, 0.55, canvas[pad:pad + bh, pad:pad + bw], 0.45, 0)

    def stamp(text, x, y, fs, thick=1, colour=(255, 255, 255)):
        """Text with a dark halo, so it reads over any photo underneath."""
        cv2.putText(canvas, text, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX,
                    fs, (0, 0, 0), thick + 3, cv2.LINE_AA)
        cv2.putText(canvas, text, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX,
                    fs, colour, thick, cv2.LINE_AA)

    cell_fs = max(0.34, min(0.85, min(cw, ch) / 150.0))
    for i in range(ncols):
        letter = CONFIG.columns[c0 + i]
        for j in range(nrows):
            stamp(f"{letter}{CONFIG.rows[r0 + j]}",
                  pad + i * cw + 5, pad + j * ch + 6 + 13 * cell_fs / 0.4,
                  cell_fs, 1, (170, 255, 255))

    edge_fs = max(0.6, min(1.3, min(cw, ch) / 90.0))
    for i in range(ncols):
        letter = CONFIG.columns[c0 + i]
        (tw, th), _ = cv2.getTextSize(letter, cv2.FONT_HERSHEY_SIMPLEX,
                                      edge_fs, 2)
        cx = pad + (i + 0.5) * cw - tw / 2
        stamp(letter, cx, pad - 12, edge_fs, 2)
        stamp(letter, cx, pad + bh + th + 14, edge_fs, 2)
    for j in range(nrows):
        label = str(CONFIG.rows[r0 + j])
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                                      edge_fs, 2)
        cy = pad + (j + 0.5) * ch + th / 2
        stamp(label, pad - tw - 12, cy, edge_fs, 2)
        stamp(label, pad + bw + 12, cy, edge_fs, 2)

    if overlay_poly and len(overlay_poly) >= 3:
        def at(c, r):
            return (int(round(pad + (c - c0) * cw)),
                    int(round(pad + (r - r0) * ch)))
        pts = np.array([[at(c, r) for c, r in overlay_poly]], np.int32)
        cv2.polylines(canvas, pts, True, (255, 0, 255), 3, cv2.LINE_AA)
        for c, r in overlay_poly:
            cv2.circle(canvas, at(c, r), 5, (255, 0, 255), -1, cv2.LINE_AA)
    return canvas


def render_vision_board(frame_bgr, grid: Grid, labels=True):
    """The whole board, drawn for the model."""
    return render_board_region(frame_bgr, grid, 0, 0,
                               CONFIG.n_cols, CONFIG.n_rows, labels=labels)


@dataclass
class Button:
    """A pill. `style` picks the surface: primary (black), ghost (white),
    accent (violet), or tonal (soft violet)."""
    label: str
    x0: int
    y0: int
    x1: int
    y1: int
    kind: str
    value: object = None
    style: str = "ghost"
    scale: float = 0.5

    def contains(self, x, y):
        pad = 5
        return (self.x0 - pad <= x <= self.x1 + pad
                and self.y0 - pad <= y <= self.y1 + pad)

    def draw(self, img, hover=False, active=False, shadow=True):
        """Paint the pill. Each distinct look (label, size, style, hover,
        active, shadow) is recorded once as an AffineStamp and replayed --
        the Settings card alone draws ~50 of these a frame."""
        x0, y0 = int(round(self.x0)), int(round(self.y0))
        w, h = int(round(self.x1)) - x0, int(round(self.y1)) - y0
        if w <= 0 or h <= 0:
            return
        key = (self.label, w, h, self.style, bool(hover), bool(active),
               bool(shadow), self.scale)
        stamp = _BUTTON_STAMPS.get(key)
        if stamp is None:
            if len(_BUTTON_STAMPS) >= BUTTON_STAMP_CACHE:
                _BUTTON_STAMPS.clear()
            m = 14
            local = dc_replace(self, x0=m, y0=m, x1=m + w, y1=m + h)
            stamp = _BUTTON_STAMPS[key] = AffineStamp(
                w + 2 * m, h + 2 * m,
                lambda im: local._paint(im, hover, active, shadow))
        stamp.apply(img, x0 - 14, y0 - 14)

    def _paint(self, img, hover=False, active=False, shadow=True):
        r = (self.y1 - self.y0) // 2
        rect = (self.x0, self.y0, self.x1, self.y1)
        if shadow:
            drop_shadow(img, rect, r, spread=6, strength=0.13)

        if self.style == "primary":
            bg = C_BTN_HOVER if hover else C_BTN
            fg = C_BTN_FG
            border = None
        elif self.style == "accent":
            bg = _bgr("#7c4ddb") if hover else C_ACCENT
            fg = C_BTN_FG
            border = None
        elif active:
            bg = C_ACCENT_SO
            fg = C_ACCENT
            border = C_ACCENT
        else:
            bg = C_GHOST_HOV if hover else C_GHOST
            fg = C_TEXT
            border = C_BORDER

        rounded_rect(img, rect, r, bg, -1)
        if border is not None:
            rounded_rect(img, rect, r, border, 1)
        draw_text_centred(img, self.label, rect, self.scale, fg,
                          2 if self.style in ("primary", "accent") else 1)


class Dropdown:
    """A pill that opens a rounded card of choices, with per-item hover."""

    ITEM_W = 46
    ITEM_H = 34

    def __init__(self, label: str, x0, y0, x1, y1, kind: str):
        self.label = label
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.kind = kind
        self.items = []
        self.open = False
        self._item_rects = []
        self._list_rect = None
        self.list_columns = None
        self.list_alpha = GLASS_ALPHA
        self.list_text_scale = 0.5

    def set_items(self, items):
        self.items = items
        self.open = False

    def contains(self, x, y):
        pad = 5
        return (self.x0 - pad <= x <= self.x1 + pad
                and self.y0 - pad <= y <= self.y1 + pad)

    def hit_item(self, x, y):
        for ix0, iy0, ix1, iy1, value in self._item_rects:
            if ix0 <= x <= ix1 and iy0 <= y <= iy1:
                return value
        return None

    def list_contains(self, x, y):
        if not self.open or not self._list_rect:
            return False
        lx0, ly0, lx1, ly1 = self._list_rect
        return lx0 <= x <= lx1 and ly0 <= y <= ly1

    def draw(self, img, current, hover=False):
        r = (self.y1 - self.y0) // 2
        rect = (self.x0, self.y0, self.x1, self.y1)
        drop_shadow(img, rect, r, spread=6, strength=0.13)
        rounded_rect(img, rect, r, C_GHOST_HOV if (hover or self.open) else C_GHOST, -1)
        rounded_rect(img, rect, r, C_ACCENT if self.open else C_BORDER, 1)

        draw_text(img, self.label, (self.x0 + 18, (self.y0 + self.y1) / 2 - 8),
                  0.42, C_TEXT_DIM, 1)
        value = str(current) if current is not None else "--"
        draw_text(img, value, (self.x0 + 18, (self.y0 + self.y1) / 2 + 13),
                  0.62, C_TEXT if current is not None else C_TEXT_DIM, 2)
        draw_chevron(img, (self.x1 - 20, (self.y0 + self.y1) // 2), 6,
                     C_TEXT_DIM, 2, up=self.open)

    def draw_list(self, img, current, mouse=(-1, -1)):
        """Painted last, on top of everything else."""
        self._item_rects = []
        self._list_rect = None
        if not self.open or not self.items:
            return

        pad = 10
        span = self.x1 - self.x0
        per_row = max(1, (span - 2 * pad) // self.ITEM_W)
        if self.list_columns is not None:
            per_row = min(self.list_columns,
                          max(1, (img.shape[1] - 16 - 2 * pad) // self.ITEM_W))
        n_rows = (len(self.items) + per_row - 1) // per_row
        lw = per_row * self.ITEM_W + 2 * pad
        lh = n_rows * self.ITEM_H + 2 * pad
        lx0 = self.x0
        ly0 = self.y0 - lh - 10
        if ly0 < 8:
            ly0 = self.y1 + 10

        if self.list_columns is not None:
            lx0 = max(8, min(lx0, img.shape[1] - lw - 8))
            ly0 = max(8, min(ly0, img.shape[0] - lh - 8))
        rect = (lx0, ly0, lx0 + lw, ly0 + lh)
        self._list_rect = rect
        glass_card(img, rect, 20, alpha=self.list_alpha)

        mx, my = mouse
        for i, (value, label) in enumerate(self.items):
            row, col = divmod(i, per_row)
            ix0 = lx0 + pad + col * self.ITEM_W
            iy0 = ly0 + pad + row * self.ITEM_H
            hx0, hy0 = ix0, iy0
            hx1, hy1 = ix0 + self.ITEM_W, iy0 + self.ITEM_H
            ix1, iy1 = hx1 - 2, hy1 - 2
            selected = (value == current)
            hovered = hx0 <= mx <= hx1 and hy0 <= my <= hy1
            if selected:
                rounded_rect(img, (ix0, iy0, ix1, iy1), 12, C_ACCENT, -1)
                fg = C_BTN_FG
            elif hovered:
                rounded_rect(img, (ix0, iy0, ix1, iy1), 12, C_ACCENT_SO, -1)
                fg = C_ACCENT
            else:
                fg = C_TEXT
            draw_text_centred(img, label, (ix0, iy0, ix1, iy1), self.list_text_scale, fg,
                              2 if selected else 1)
            self._item_rects.append((hx0, hy0, hx1, hy1, value))


class Slider:
    """A horizontal track with a draggable knob, for a value that reads
    better as a position than as a number stepped one click at a time.

    Same split as Button: the widget draws itself and answers hit tests, the
    panel owns the value and decides what a hit means. Nothing is stored
    here but the geometry, so a panel can lay one out fresh every frame the
    way the -/+ buttons already are.
    """

    TRACK_H = 6
    KNOB_R = 9

    def __init__(self, label: str, kind: str, lo: float, hi: float,
                 fmt: str = "{:.0f}", unit: str = ""):
        self.label = label
        self.kind = kind
        self.lo = float(lo)
        self.hi = float(hi)
        self.fmt = fmt
        self.unit = unit
        self.x0 = self.y0 = self.x1 = self.y1 = 0

    def set_rect(self, x0, y0, x1, y1):
        self.x0, self.y0 = int(round(x0)), int(round(y0))
        self.x1, self.y1 = int(round(x1)), int(round(y1))

    def contains(self, x, y):
        """Generous vertically on purpose -- the track is 6px tall, and a
        6px-tall click target is one nobody can hit."""
        pad = self.KNOB_R + 5
        return (self.x0 - pad <= x <= self.x1 + pad
                and self.y0 - pad <= y <= self.y1 + pad)

    def value_at(self, x) -> float:
        """The value the knob would take if dragged to pixel `x`, clamped to
        the track -- so a drag that runs off the end pins to lo/hi instead of
        overshooting."""
        span = self.x1 - self.x0
        if span <= 0:
            return self.lo
        t = min(1.0, max(0.0, (x - self.x0) / float(span)))
        return self.lo + t * (self.hi - self.lo)

    def clamp(self, value) -> float:
        return min(self.hi, max(self.lo, float(value)))

    def knob_x(self, value) -> int:
        span = self.hi - self.lo
        t = 0.0 if span == 0 else (self.clamp(value) - self.lo) / span
        return int(round(self.x0 + t * (self.x1 - self.x0)))

    def text(self, value) -> str:
        return self.fmt.format(float(value)) + self.unit

    def draw(self, img, value, hover=False, active=False):
        cy = (self.y0 + self.y1) // 2
        half = max(1, self.TRACK_H // 2)
        rounded_rect(img, (self.x0, cy - half, self.x1, cy + half),
                     half, C_BORDER, -1)
        kx = self.knob_x(value)
        if kx > self.x0:
            rounded_rect(img, (self.x0, cy - half, kx, cy + half),
                         half, C_ACCENT, -1)
        lit = hover or active
        r = self.KNOB_R + (1 if lit else 0)
        drop_shadow(img, (kx - r, cy - r, kx + r, cy + r), r,
                    spread=5, strength=0.15)
        cv2.circle(img, (kx, cy), r, C_CARD, -1, cv2.LINE_AA)
        cv2.circle(img, (kx, cy), r, C_ACCENT if lit else C_BORDER, 2,
                   cv2.LINE_AA)


def draw_switch(img, rect, on: bool, hover=False):
    """A real toggle switch: a pill track with the knob at one end.

    Drawn rather than made of Buttons because the whole point is that the
    control LOOKS like its state -- an on/off setting shown as "-" and "+"
    next to the word "Off" reads as something you step through, not
    something you flip.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    h = y1 - y0
    r = h // 2
    track = C_ACCENT if on else C_BORDER
    if hover:
        track = _bgr("#7c4ddb") if on else _bgr("#ccd2e2")
    rounded_rect(img, (x0, y0, x1, y1), r, track, -1)
    label, lcol = ("ON", C_BTN_FG) if on else ("OFF", C_TEXT_DIM)
    lw, _ = text_size(label, 0.32, 1)
    lx = x0 + (r - lw // 2) if on else x1 - r - lw // 2
    draw_text(img, label, (lx, y0 + h // 2 + 4), 0.32, lcol, 1)
    kx = (x1 - r) if on else (x0 + r)
    kr = r - 3
    drop_shadow(img, (kx - kr, y0 + 3, kx + kr, y1 - 3), kr,
                spread=5, strength=0.18)
    cv2.circle(img, (kx, y0 + h // 2), kr, C_CARD, -1, cv2.LINE_AA)


@dataclass
class SettingRow:
    key: str
    label: str
    read: object
    step: object
    section: str = ""
    toggle: bool = False


class SettingsPanel:
    """A frosted card floating over the video with -/+ controls and
    switches for the on/off settings."""

    ROW_H = 42
    PAD = 22
    WIDTH = 520

    def __init__(self, cam_settings: CameraSettings, grid: Grid,
                 on_grid_size_changed, state=None):
        self.cam = cam_settings
        self.grid = grid
        self.on_grid_size_changed = on_grid_size_changed
        self.state = state
        self.visible = False
        self.edit_corners = False
        self.rows = self._build_rows()
        self.buttons = []
        self._last_rect = None
        self._anim = 0.0
        self.scroll = 0
        self._max_scroll = 0
        self._view = None

    def _build_rows(self):
        def clamp(v, lo, hi):
            return max(lo, min(hi, v))

        def step_zoom(d):
            self.cam.zoom = round(clamp(self.cam.zoom + 0.1 * d, 1.0, 5.0), 2)

        def step_brightness(d):
            self.cam.brightness = int(clamp(self.cam.brightness + 5 * d, -100, 100))

        def step_contrast(d):
            self.cam.contrast = round(clamp(self.cam.contrast + 0.05 * d, 0.5, 2.0), 2)

        def step_saturation(d):
            self.cam.saturation = round(clamp(self.cam.saturation + 0.1 * d, 0.0, 2.0), 2)

        def step_sharpness(d):
            self.cam.sharpness = round(clamp(self.cam.sharpness + 0.1 * d, 0.0, 1.0), 2)

        def step_rotation(d):
            self.cam.rotation = (self.cam.rotation + 90 * d) % 360

        def step_mirror(_d):
            self.cam.mirror = not self.cam.mirror

        def step_cols(d):
            new = int(clamp(CONFIG.n_cols + d, MIN_N, MAX_N_COLS))
            if new != CONFIG.n_cols:
                CONFIG.n_cols = new
                self.on_grid_size_changed()

        def step_rows(d):
            new = int(clamp(CONFIG.n_rows + d, MIN_N, MAX_N_ROWS))
            if new != CONFIG.n_rows:
                CONFIG.n_rows = new
                self.on_grid_size_changed()

        def step_square(_d):
            self.grid.square_cells = not self.grid.square_cells
            if self.grid.square_cells:
                self.grid.reset_box()

        def step_speed(d):
            global SIM_SPEED
            i = SIM_SPEEDS.index(SIM_SPEED) if SIM_SPEED in SIM_SPEEDS else 1
            SIM_SPEED = SIM_SPEEDS[int(clamp(i + d, 0, len(SIM_SPEEDS) - 1))]

        def step_wait_cap(d):
            global WAIT_MAX_PLAYBACK
            i = (WAIT_CAPS.index(WAIT_MAX_PLAYBACK)
                 if WAIT_MAX_PLAYBACK in WAIT_CAPS else 1)
            WAIT_MAX_PLAYBACK = WAIT_CAPS[int(clamp(i + d, 0, len(WAIT_CAPS) - 1))]

        def step_gripper_ai(_d):
            global GRIPPER_AI
            GRIPPER_AI = not GRIPPER_AI

        def step_automatic_gripper(_d):
            global MANUAL_GRIPPER_STEPS
            MANUAL_GRIPPER_STEPS = not MANUAL_GRIPPER_STEPS
            save_settings(self.cam, self.grid)

        def step_dexterity_check(_d):
            global DEXTERITY_CHECK
            DEXTERITY_CHECK = not DEXTERITY_CHECK

        def step_err_auto(d):
            global ERR_AUTO
            keys = [k for k, _ in ERR_AUTO_MODES]
            ERR_AUTO = keys[(keys.index(ERR_AUTO) + d) % len(keys)]

        def step_board_width(d):
            global BOARD_WIDTH_IN
            BOARD_WIDTH_IN = round(clamp(BOARD_WIDTH_IN + d, 2.0, 240.0), 1)

        def step_vision_conf(d):
            global VISION_CONF
            lo, hi, st = VISION_LIMITS["conf_thres"]
            VISION_CONF = round(clamp(VISION_CONF + st * d, lo, hi), 2)

        def step_vision_iou(d):
            global VISION_IOU
            lo, hi, st = VISION_LIMITS["iou_thres"]
            VISION_IOU = round(clamp(VISION_IOU + st * d, lo, hi), 2)

        def step_vision_max_area(d):
            global VISION_MAX_AREA
            lo, hi, st = VISION_LIMITS["max_area"]
            VISION_MAX_AREA = round(clamp(VISION_MAX_AREA + st * d, lo, hi), 2)

        def step_vision_outline(d):
            global VISION_OUTLINE_PX
            lo, hi, st = VISION_LIMITS["outline_px"]
            VISION_OUTLINE_PX = int(clamp(VISION_OUTLINE_PX + st * d, lo, hi))

        def step_vision_parts(_d):
            global VISION_MARK_PARTS
            VISION_MARK_PARTS = not VISION_MARK_PARTS

        def step_vision_names(_d):
            global VISION_SHOW_NAMES
            VISION_SHOW_NAMES = not VISION_SHOW_NAMES

        def step_namer_model(d):
            global NAMER_MODEL
            i = NAMER_MODELS.index(NAMER_MODEL) if NAMER_MODEL in NAMER_MODELS else 0
            NAMER_MODEL = NAMER_MODELS[(i + d) % len(NAMER_MODELS)]

        def step_priority_naming(_d):
            global PRIORITY_NAMING
            PRIORITY_NAMING = not PRIORITY_NAMING
            save_settings(self.cam, self.grid)

        def step_vision_fps(d):
            global VISION_MAX_FPS
            i = (VISION_FPS_CHOICES.index(VISION_MAX_FPS)
                 if VISION_MAX_FPS in VISION_FPS_CHOICES else 3)
            VISION_MAX_FPS = VISION_FPS_CHOICES[
                int(clamp(i + d, 0, len(VISION_FPS_CHOICES) - 1))]

        def step_refresh_rate(d):
            global REFRESH_RATE
            i = (REFRESH_RATES.index(REFRESH_RATE)
                 if REFRESH_RATE in REFRESH_RATES else 2)
            REFRESH_RATE = REFRESH_RATES[int(clamp(i + d, 0, len(REFRESH_RATES) - 1))]

        def step_outlines(_d):
            if self.state is not None:
                self.state.show_objects = not self.state.show_objects

        def step_verbose(_d):
            global DEBUG_INPUT
            DEBUG_INPUT = not DEBUG_INPUT

        rows = [
            SettingRow("zoom", "Camera zoom", lambda: f"{self.cam.zoom:.1f}x",
                       step_zoom, section="CAMERA"),
            SettingRow("brightness", "Brightness", lambda: f"{self.cam.brightness:+d}",
                       step_brightness),
            SettingRow("contrast", "Contrast", lambda: f"{self.cam.contrast:.2f}",
                       step_contrast),
            SettingRow("saturation", "Saturation", lambda: f"{self.cam.saturation:.1f}",
                       step_saturation),
            SettingRow("sharpness", "Sharpness", lambda: f"{self.cam.sharpness:.1f}",
                       step_sharpness),
            SettingRow("rotation", "Rotation", lambda: f"{self.cam.rotation} deg",
                       step_rotation),
            SettingRow("mirror", "Mirror", lambda: "On" if self.cam.mirror else "Off",
                       step_mirror, toggle=True),
            SettingRow("cols", "Columns", lambda: str(CONFIG.n_cols), step_cols,
                       section="GRID"),
            SettingRow("rows", "Rows", lambda: str(CONFIG.n_rows), step_rows),
            SettingRow("square", "Square cells",
                       lambda: "On" if self.grid.square_cells else "Off",
                       step_square, toggle=True),
            SettingRow("speed", "Playback speed", lambda: f"{SIM_SPEED:g}x",
                       step_speed, section="SIMULATION"),
            SettingRow("wait_cap", "Simulated wait cap",
                       lambda: f"{WAIT_MAX_PLAYBACK:g}s", step_wait_cap),
            SettingRow("gripper_ai", "Grip top-right, press centre",
                       lambda: "On" if GRIPPER_AI else "Off", step_gripper_ai,
                       toggle=True),
            SettingRow("automatic_gripper", "Automatic gripper actions",
                       lambda: "On" if not MANUAL_GRIPPER_STEPS else "Off",
                       step_automatic_gripper, toggle=True),
            SettingRow("board_width", "Board width (in)",
                       lambda: f"{BOARD_WIDTH_IN:g} in", step_board_width,
                       section="VISION"),
            SettingRow("vision_conf", "Detection confidence",
                       lambda: f"{VISION_CONF:.2f}", step_vision_conf),
            SettingRow("vision_iou", "Merge overlap above",
                       lambda: f"{VISION_IOU:.2f}", step_vision_iou),
            SettingRow("vision_max_area", "Largest object (of frame)",
                       lambda: f"{VISION_MAX_AREA:.0%}", step_vision_max_area),
            SettingRow("vision_outline", "Outline thickness",
                       lambda: f"{VISION_OUTLINE_PX} px", step_vision_outline),
            SettingRow("vision_parts", "Show parts in red",
                       lambda: "On" if VISION_MARK_PARTS else "Off",
                       step_vision_parts, toggle=True),
            SettingRow("vision_names", "Show names",
                       lambda: "On" if VISION_SHOW_NAMES else "Off",
                       step_vision_names, toggle=True),
            SettingRow("namer_model", "Naming model",
                       lambda: NAMER_MODEL, step_namer_model),
            SettingRow("priority_naming", "Priority naming (faster)",
                       lambda: "On" if PRIORITY_NAMING else "Off",
                       step_priority_naming, toggle=True),
            SettingRow("dexterity_check", "Dexterity check",
                       lambda: "On" if DEXTERITY_CHECK else "Off",
                       step_dexterity_check, toggle=True),
            SettingRow("err_auto", "Automatic check",
                       lambda: dict(ERR_AUTO_MODES)[ERR_AUTO],
                       step_err_auto, section="ERROR REBOUNDS"),
            SettingRow("refresh_rate", "Refresh rate",
                       lambda: ("Uncapped" if REFRESH_RATE == 0
                               else f"{REFRESH_RATE} fps"),
                       step_refresh_rate, section="PERFORMANCE"),
            SettingRow("vision_fps", "Vision updates",
                       lambda: f"{VISION_MAX_FPS:g}/s", step_vision_fps),
        ]
        if self.state is not None:
            rows.append(SettingRow(
                "outlines", "Object outlines",
                lambda: "On" if self.state.show_objects else "Off",
                step_outlines, toggle=True))
        rows.append(SettingRow(
            "verbose", "Verbose console",
            lambda: "On" if DEBUG_INPUT else "Off", step_verbose, toggle=True))
        return rows


    def toggle(self):
        self.visible = not self.visible
        if not self.visible:
            self.edit_corners = False
        else:
            self.scroll = 0

    def scroll_by(self, delta_px: int):
        """Wheel the row list. Only the rows scroll -- the title and the
        SAVE/CLOSE pills stay put, so the way out of the panel is never
        scrolled off the screen."""
        self.scroll = max(0, min(self.scroll + delta_px, self._max_scroll))

    def wants_scroll(self, x, y) -> bool:
        """True when the wheel at (x, y) belongs to this panel's row list."""
        if not self.visible or not self._view or self._max_scroll <= 0:
            return False
        vx0, vy0, vx1, vy1 = self._view
        return vx0 <= x <= vx1 and vy0 <= y <= vy1

    def hit_test(self, x, y):
        """Returns a status string when the click was ours, "" when it was
        swallowed by the card, or None when it wasn't ours at all."""
        if not self.visible:
            return None
        for b in self.buttons:
            if not b.contains(x, y):
                continue
            if b.kind == "step":
                row, delta = b.value
                row.step(delta)
                return f"{row.label}: {row.read()}"
            if b.kind == "corners":
                self.edit_corners = not self.edit_corners
                return ("Drag the four handles to resize the board."
                        if self.edit_corners else "Corner editing off.")
            if b.kind == "reset_corners":
                self.grid.reset_box()
                save_settings(self.cam, self.grid)
                return "Boundary reset."
            if b.kind == "save":
                save_settings(self.cam, self.grid)
                return f"Saved to {os.path.basename(SETTINGS_PATH)}"
            if b.kind == "close":
                self.visible = False
                self.edit_corners = False
                return "Settings closed."
        if self._rect_contains(x, y):
            return ""
        return None

    def dropdown_hit(self, x, y):
        if not self.visible:
            return False
        return False

    def draw_lists(self, frame, mouse=(-1, -1)):
        if not self.visible:
            return

    def _rect_contains(self, x, y):
        if not self._last_rect:
            return False
        px, py, pw, ph = self._last_rect
        return px <= x <= px + pw and py <= y <= py + ph


    def draw(self, frame, mouse=(-1, -1)):
        self._anim = ease_toward(self._anim, 1.0 if self.visible else 0.0,
                                 ANIM_RATE)
        if self._anim < 0.004:
            return
        fh, fw = frame.shape[:2]
        pw = min(self.WIDTH, fw - 2 * self.PAD)
        n_sections = sum(1 for r in self.rows if r.section)
        HEADER_H = 22
        row_h = self.ROW_H

        content_h = row_h * len(self.rows) + HEADER_H * n_sections
        chrome_h = self.PAD * 2 + 34 + row_h * 2
        view_h = max(0, min(content_h, fh - 2 * self.PAD - chrome_h))
        self._max_scroll = max(0, content_h - view_h)
        self.scroll = max(0, min(self.scroll, self._max_scroll))

        ph = chrome_h + view_h
        px, py = max(0, (fw - pw) // 2), max(0, (fh - ph) // 2)
        self._last_rect = (px, py, pw, ph)
        self._dropdown_origin = (px, vy0 if 'vy0' in locals() else py + 54)
        rect = (px, py, px + pw, py + ph)

        margin = 40
        bx0, by0 = max(0, px - margin), max(0, py - margin)
        bx1, by1 = min(fw, px + pw + margin), min(fh, py + ph + margin)
        fading = self._anim < 0.999
        under = frame[by0:by1, bx0:bx1].copy() if fading else None

        glass_card(frame, rect, 28, alpha=0.62)

        draw_text(frame, "Settings", (px + 24, py + 36), 0.72, C_TEXT, 2)

        mx, my = mouse
        self.buttons = []
        close_top = Button("X", px + pw - 52, py + 12,
                           px + pw - 20, py + 44, "close", scale=0.46)
        close_top.draw(frame, hover=close_top.contains(mx, my), shadow=False)
        self.buttons.append(close_top)

        vy0 = py + 54
        vy1 = min(fh, vy0 + view_h)
        self._view = (px, vy0, min(fw, px + pw), vy1)
        vp = frame[vy0:vy1, px:px + pw]
        vmx, vmy = mx - px, my - vy0

        y = -self.scroll
        for row in self.rows if vy1 > vy0 else []:
            if row.section:
                if -HEADER_H < y < view_h:
                    draw_text(vp, row.section, (24, y + 14), 0.36, C_ACCENT, 1)
                y += HEADER_H
            if y + row_h > 0 and y < view_h:
                draw_text(vp, row.label, (24, y + 26), 0.48, C_TEXT, 1)
                if row.toggle:
                    sw = (pw - 96, y + 8, pw - 30, y + row_h - 10)
                    hit = Button("", sw[0], sw[1], sw[2], sw[3],
                                 "step", (row, +1))
                    draw_switch(vp, sw, on=str(row.read()).lower() == "on",
                                hover=hit.contains(vmx, vmy))
                    row_buttons = (hit,)
                else:
                    value = row.read()
                    vw, _ = text_size(value, 0.48, 2)
                    draw_text(vp, value, (pw - 128 - vw, y + 26), 0.48,
                              C_ACCENT, 2)
                    minus = Button("-", pw - 116, y + 4, pw - 78,
                                   y + row_h - 6, "step", (row, -1),
                                   style="ghost", scale=0.62)
                    plus = Button("+", pw - 68, y + 4, pw - 30, y + row_h - 6,
                                  "step", (row, +1), style="ghost", scale=0.62)
                    minus.draw(vp, hover=minus.contains(vmx, vmy), shadow=False)
                    plus.draw(vp, hover=plus.contains(vmx, vmy), shadow=False)
                    row_buttons = (minus, plus)
                if y >= 0 and y + row_h <= view_h:
                    self.buttons.extend(
                        dc_replace(b, x0=b.x0 + px, y0=b.y0 + vy0,
                                   x1=b.x1 + px, y1=b.y1 + vy0)
                        for b in row_buttons)
            y += row_h

        if self._max_scroll:
            self._scrollbar(frame, px + pw - 10, vy0, vy1, view_h, content_h)

        y = py + 54 + view_h
        half = (pw - 60) // 2
        corners = Button("EDIT CORNERS", px + 24, y + 4, px + 24 + half,
                         y + row_h - 6, "corners",
                         style="accent" if self.edit_corners else "ghost", scale=0.42)
        reset = Button("RESET BOX", px + 36 + half, y + 4, px + pw - 24,
                       y + row_h - 6, "reset_corners", scale=0.42)
        corners.draw(frame, hover=corners.contains(mx, my), shadow=False)
        reset.draw(frame, hover=reset.contains(mx, my), shadow=False)
        self.buttons.extend([corners, reset])
        y += row_h

        save = Button("SAVE", px + 24, y + 4, px + 24 + half, y + row_h - 6,
                      "save", style="primary", scale=0.46)
        close = Button("CLOSE", px + 36 + half, y + 4, px + pw - 24,
                       y + row_h - 6, "close", scale=0.46)
        save.draw(frame, hover=save.contains(mx, my), shadow=False)
        close.draw(frame, hover=close.contains(mx, my), shadow=False)
        self.buttons.extend([save, close])

        if fading:
            drawn = frame[by0:by1, bx0:bx1]
            frame[by0:by1, bx0:bx1] = cv2.addWeighted(
                drawn, self._anim, under, 1.0 - self._anim, 0)

    def _scrollbar(self, frame, x, vy0, vy1, view_h, content_h):
        track_h = vy1 - vy0
        bar_h = max(24, int(track_h * view_h / float(content_h)))
        top = vy0 + int((track_h - bar_h)
                        * (self.scroll / float(self._max_scroll)))
        rounded_rect(frame, (x, top, x + 3, top + bar_h), 2, C_BORDER, -1)


class PortPanel:
    """A frosted card for picking and connecting the Arduino's serial port.

    Opened from the File menu's "Port Settings..." item. Lists whatever
    pyserial can see, with the port that looks like an Arduino
    pre-selected, and a Connect/Disconnect pill that drives `arduino`.
    """

    WIDTH = 380
    ROW_H = 40
    PAD = 22
    AUTOSCAN_EVERY = 3.0

    def __init__(self, arduino: SerialLink):
        self.arduino = arduino
        self.visible = False
        self.ports = []
        self.selected_port = None
        self.buttons = []
        self._last_rect = None
        self._anim = 0.0
        self._next_autoscan = 0.0
        self._scanning = False
        self.rescan()

    def rescan(self):
        self.ports = self.arduino.available_ports()
        available = {p.device for p in self.ports}
        if self.selected_port not in available:
            guess = self.arduino.guess_arduino_port()
            self.selected_port = guess or (self.ports[0].device if self.ports else None)
        self._next_autoscan = time.time() + self.AUTOSCAN_EVERY

    def maybe_rescan(self):
        """Called once a frame; re-lists ports on its own every few seconds
        while the panel is open, so a newly plugged-in USB device appears
        without the operator having to press Rescan themselves.

        Off the render thread: listing ports walks IOKit and can take long
        enough to drop frames and delay clicks.
        """
        if not self.visible or self.arduino.connected or self._scanning:
            return
        if time.time() < self._next_autoscan:
            return
        self._next_autoscan = time.time() + self.AUTOSCAN_EVERY
        self._scanning = True
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            self.rescan()
        finally:
            self._scanning = False

    def open(self):
        self.rescan()
        self.visible = True

    def toggle(self):
        if self.visible:
            self.visible = False
        else:
            self.open()


    def hit_test(self, x, y):
        """Same contract as SettingsPanel.hit_test."""
        if not self.visible:
            return None
        for b in self.buttons:
            if not b.contains(x, y):
                continue
            if b.kind == "port":
                self.selected_port = b.value
                return f"{b.value} selected."
            if b.kind == "rescan":
                self.rescan()
                return "Ports rescanned."
            if b.kind == "connect":
                if self.arduino.connected:
                    self.arduino.disconnect()
                    self.arduino.auto_reconnect = False
                    return "Disconnected."
                if not self.selected_port:
                    return "No port to connect to."
                if self.arduino.connect(self.selected_port):
                    return f"Connected to {self.selected_port}."
                return f"Could not connect: {self.arduino.last_error}"
            if b.kind == "close":
                self.visible = False
                return "Port settings closed."
        if self._rect_contains(x, y):
            return ""
        return None

    def _rect_contains(self, x, y):
        if not self._last_rect:
            return False
        px, py, pw, ph = self._last_rect
        return px <= x <= px + pw and py <= y <= py + ph


    def draw(self, frame, mouse=(-1, -1)):
        self._anim = ease_toward(self._anim, 1.0 if self.visible else 0.0,
                                 ANIM_RATE)
        if self._anim < 0.004:
            return
        fh, fw = frame.shape[:2]
        pw = min(self.WIDTH, fw - 2 * self.PAD)
        n_port_rows = max(1, len(self.ports))
        ph = self.PAD * 2 + 60 + n_port_rows * self.ROW_H + 2 * self.ROW_H
        px, py = self.PAD, self.PAD
        self._last_rect = (px, py, pw, ph)
        rect = (px, py, px + pw, py + ph)

        margin = 40
        bx0, by0 = max(0, px - margin), max(0, py - margin)
        bx1, by1 = min(fw, px + pw + margin), min(fh, py + ph + margin)
        fading = self._anim < 0.999
        under = frame[by0:by1, bx0:bx1].copy() if fading else None

        glass_card(frame, rect, 28, alpha=0.62)
        draw_text(frame, "Arduino Port", (px + 24, py + 36), 0.72, C_TEXT, 2)

        if self.arduino.connected:
            status, colour = f"Connected: {self.arduino.port}", C_GREEN
        elif self.arduino.last_error:
            status, colour = f"Not connected ({self.arduino.last_error})", C_RED
        else:
            status, colour = "Not connected", C_TEXT_DIM
        draw_text(frame, status[:60], (px + 24, py + 58), 0.4, colour, 1)

        mx, my = mouse
        self.buttons = []
        close_top = Button("X", px + pw - 52, py + 12,
                           px + pw - 20, py + 44, "close", scale=0.46)
        close_top.draw(frame, hover=close_top.contains(mx, my), shadow=False)
        self.buttons.append(close_top)
        y = py + 74
        if not self.ports:
            draw_text(frame, "No serial ports found.", (px + 24, y + 22), 0.42,
                      C_TEXT_DIM, 1)
            y += self.ROW_H
        for p in self.ports:
            selected = p.device == self.selected_port
            label = f"{p.device}  {p.description or ''}".strip()
            btn = Button(label[:44], px + 16, y, px + pw - 16, y + self.ROW_H - 6,
                        "port", p.device,
                        style="accent" if selected else "ghost", scale=0.38)
            btn.draw(frame, hover=btn.contains(mx, my), shadow=False)
            self.buttons.append(btn)
            y += self.ROW_H

        half = (pw - 60) // 2
        rescan = Button("RESCAN", px + 24, y + 4, px + 24 + half,
                        y + self.ROW_H - 2, "rescan", scale=0.42)
        connect = Button("DISCONNECT" if self.arduino.connected else "CONNECT",
                         px + 36 + half, y + 4, px + pw - 24, y + self.ROW_H - 2,
                         "connect", style="primary", scale=0.42)
        rescan.draw(frame, hover=rescan.contains(mx, my), shadow=False)
        connect.draw(frame, hover=connect.contains(mx, my), shadow=False)
        self.buttons.extend([rescan, connect])
        y += self.ROW_H

        close = Button("CLOSE", px + 24, y + 4, px + pw - 24, y + self.ROW_H - 2,
                       "close", scale=0.46)
        close.draw(frame, hover=close.contains(mx, my), shadow=False)
        self.buttons.append(close)

        if fading:
            drawn = frame[by0:by1, bx0:bx1]
            frame[by0:by1, bx0:bx1] = cv2.addWeighted(
                drawn, self._anim, under, 1.0 - self._anim, 0)


LINE_COLOURS = {"tx": C_ACCENT, "rx": C_TEXT, "sys": C_TEXT_DIM}
LINE_PREFIX = {"tx": ">> ", "rx": "<< ", "sys": "-- "}


class ConsolePanel:
    """The raw serial console: every line in or out, plus a line to type
    into and send straight to the Arduino -- for debugging the link
    itself, independent of whatever the AprilTag guidance is doing.

    Opened from the "Comm" menu, next to File.
    """

    WIDTH = 460
    HEIGHT = 340
    PAD = 22
    LINE_H = 20
    MAX_LINES = 400

    def __init__(self, arduino: SerialLink):
        self.arduino = arduino
        self.visible = False
        self.focused = False
        self.input_text = ""
        self.input_cursor = 0
        self.lines = []
        self._rx_buf = b""
        self.on_rx_bytes = None
        self.buttons = []
        self._field_rect = None
        self._last_rect = None
        self._anim = 0.0

    def log(self, kind, text):
        for line in text.splitlines() or [""]:
            self.lines.append((kind, line))
        if len(self.lines) > self.MAX_LINES:
            self.lines = self.lines[-self.MAX_LINES:]

    def open(self):
        self.visible = True
        self.focused = True

    def toggle(self):
        if self.visible:
            self.visible = False
            self.focused = False
        else:
            self.open()


    def pump(self):
        """Called every frame: drain whatever the Arduino has sent back."""
        self.arduino.on_bytes = self.receive_bytes
        self.arduino.pump_receive()

    def receive_bytes(self, data):
        """Notify raw-byte consumers; SerialLink logs parsed RX lines."""
        if self.on_rx_bytes is not None:
            try:
                self.on_rx_bytes(data)
            except Exception as e:
                print(f"[serial] rx observer failed: {e}")

    def send_line(self):
        text = self.input_text.strip()
        self.input_text, self.input_cursor = "", 0
        if not text:
            return
        if not self.arduino.connected:
            self.log("sys", "Not connected -- nothing sent.")
            return
        try:
            self.arduino.conn.write((text + "\n").encode("utf-8"))
            self.log("tx", text)
        except Exception as e:
            self.log("sys", f"Send failed: {e}")


    def handle_key(self, key):
        """A minimal line editor, the same key codes AISidebar uses for its
        prompt box. Returns True when the key was ours to swallow."""
        if not self.focused:
            return False
        if key in (13, 10):
            self.send_line()
            return True
        if key in (8, 127):
            if self.input_cursor > 0:
                self.input_text = (self.input_text[:self.input_cursor - 1]
                                   + self.input_text[self.input_cursor:])
                self.input_cursor -= 1
            return True
        if key == 27:
            self.focused = False
            return True
        ch = chr(key) if 32 <= key < 127 else None
        if ch and len(self.input_text) < 200:
            self.input_text = (self.input_text[:self.input_cursor] + ch
                               + self.input_text[self.input_cursor:])
            self.input_cursor += 1
        return True

    def hit_test(self, x, y):
        if not self.visible:
            return None
        for b in self.buttons:
            if not b.contains(x, y):
                continue
            if b.kind == "clear":
                self.lines = []
                return "Console cleared."
            if b.kind == "send":
                self.focused = True
                self.send_line()
                return ""
            if b.kind == "close":
                self.visible = False
                self.focused = False
                return "Console closed."
        if self._field_rect:
            fx0, fy0, fx1, fy1 = self._field_rect
            if fx0 <= x <= fx1 and fy0 <= y <= fy1:
                self.focused = True
                return ""
        if self._rect_contains(x, y):
            self.focused = False
            return ""
        return None

    def _rect_contains(self, x, y):
        if not self._last_rect:
            return False
        px, py, pw, ph = self._last_rect
        return px <= x <= px + pw and py <= y <= py + ph


    def draw(self, frame, mouse=(-1, -1)):
        self._anim = ease_toward(self._anim, 1.0 if self.visible else 0.0,
                                 ANIM_RATE)
        if self._anim < 0.004:
            return
        fh, fw = frame.shape[:2]
        pw = min(self.WIDTH, fw - 2 * self.PAD)
        ph = min(self.HEIGHT, fh - 2 * self.PAD)
        px, py = fw - pw - self.PAD, self.PAD
        self._last_rect = (px, py, pw, ph)
        rect = (px, py, px + pw, py + ph)

        margin = 40
        bx0, by0 = max(0, px - margin), max(0, py - margin)
        bx1, by1 = min(fw, px + pw + margin), min(fh, py + ph + margin)
        fading = self._anim < 0.999
        under = frame[by0:by1, bx0:bx1].copy() if fading else None

        glass_card(frame, rect, 28, alpha=0.62)
        draw_text(frame, "Serial Console", (px + 24, py + 36), 0.6, C_TEXT, 2)

        status = (f"{self.arduino.port} @ {ARDUINO_BAUD}" if self.arduino.connected
                  else "Not connected")
        draw_text(frame, status, (px + 24, py + 54),
                  0.36, C_GREEN if self.arduino.connected else C_TEXT_DIM, 1)

        log_top = py + 66
        field_h = 34
        log_bottom = py + ph - field_h - 16
        n_visible = max(1, (log_bottom - log_top) // self.LINE_H)
        shown = self.lines[-n_visible:]
        y = log_top + 14
        for kind, text in shown:
            colour = LINE_COLOURS.get(kind, C_TEXT)
            draw_text(frame, LINE_PREFIX.get(kind, "") + text,
                      (px + 24, y), 0.38, colour, 1)
            y += self.LINE_H

        fx0, fy0 = px + 24, log_bottom + 8
        fx1, fy1 = px + pw - 88, log_bottom + 8 + field_h - 8
        self._field_rect = (fx0, fy0, fx1, fy1)
        rounded_rect(frame, (fx0, fy0, fx1, fy1), 10,
                    C_GHOST_HOV if self.focused else C_GHOST, -1)
        rounded_rect(frame, (fx0, fy0, fx1, fy1), 10,
                    C_ACCENT if self.focused else C_BORDER, 1)
        shown_text = self.input_text or ("Type a command..." if not self.focused else "")
        text_colour = C_TEXT if self.input_text else C_TEXT_DIM
        draw_text(frame, shown_text, (fx0 + 10, fy0 + 22), 0.4, text_colour, 1)
        if self.focused and int(time.time() * 2) % 2 == 0:
            cw, _ = text_size(self.input_text[:self.input_cursor], 0.4, 1)
            cx = fx0 + 12 + cw
            cv2.line(frame, (cx, fy0 + 6), (cx, fy1 - 6), C_ACCENT, 1, cv2.LINE_AA)

        mx, my = mouse
        self.buttons = []
        send = Button("SEND", px + pw - 80, fy0, px + pw - 24, fy1,
                      "send", style="primary", scale=0.4)
        send.draw(frame, hover=send.contains(mx, my), shadow=False)
        self.buttons.append(send)

        clear = Button("CLEAR", px + pw - 176, py + 32, px + pw - 96, py + 58,
                       "clear", scale=0.36)
        close = Button("X", px + pw - 56, py + 12, px + pw - 24, py + 40,
                       "close", scale=0.36)
        clear.draw(frame, hover=clear.contains(mx, my), shadow=False)
        close.draw(frame, hover=close.contains(mx, my), shadow=False)
        self.buttons.extend([clear, close])

        if fading:
            drawn = frame[by0:by1, bx0:bx1]
            frame[by0:by1, bx0:bx1] = cv2.addWeighted(
                drawn, self._anim, under, 1.0 - self._anim, 0)


def save_settings(cam: CameraSettings, grid: Grid):
    data = {
        "camera": {
            "zoom": cam.zoom, "brightness": cam.brightness,
            "contrast": cam.contrast, "saturation": cam.saturation,
            "sharpness": cam.sharpness, "rotation": cam.rotation,
            "mirror": cam.mirror,
        },
        "grid": {
            "n_cols": CONFIG.n_cols, "n_rows": CONFIG.n_rows,
            "box": list(grid.box), "square_cells": grid.square_cells,
            "frame_size": [grid.frame_width, grid.frame_height],
            "box_rel": grid.box_fractions(),
        },
        "trig_offset": {
            "camera_height_in": TRIG_CAMERA_HEIGHT_IN,
            "tag_height_in": TRIG_TAG_HEIGHT_IN,
            "board_height_in": TRIG_BOARD_HEIGHT_IN,
            "pivot_x": TRIG_PIVOT_X,
            "pivot_y": TRIG_PIVOT_Y,
            "gripper_up_down": GRIPPER_OFFSET_UP_DOWN,
            "gripper_right_left": GRIPPER_OFFSET_RIGHT_LEFT,
            "gripper_vertical_direction": GRIPPER_VERTICAL_DIRECTION,
            "gripper_horizontal_direction": GRIPPER_HORIZONTAL_DIRECTION,
            "nudge_s": GRIPPER_NUDGE_S,
            "nudge_direction": GRIPPER_NUDGE_DIRECTION,
            "nudge_actions": dict(GRIPPER_NUDGE_ACTIONS),
        },
        "vision": {
            "board_width_in": BOARD_WIDTH_IN,
            "conf_thres": VISION_CONF,
            "iou_thres": VISION_IOU,
            "max_area": VISION_MAX_AREA,
            "outline_px": VISION_OUTLINE_PX,
            "mark_parts": VISION_MARK_PARTS,
            "show_names": VISION_SHOW_NAMES,
            "namer_model": NAMER_MODEL,
            "priority_naming": PRIORITY_NAMING,
            "max_fps": VISION_MAX_FPS,
            "scene_hint": VISION_SCENE_HINT,
        },
        "behaviour": {
            "manual_gripper_steps": MANUAL_GRIPPER_STEPS,
            "gripper_ai": GRIPPER_AI,
            "err_auto": ERR_AUTO,
        },
    }
    S1_EMBEDDED_STATE["settings"] = data
    if persist_embedded_state():
        print(f"[settings] saved inside {SETTINGS_PATH}")


def load_settings():
    """Returns (CameraSettings, (box, frame_size, square_cells, box_rel) or
    None). Grid dimensions are applied to CONFIG as a side effect."""
    cam = CameraSettings()
    data = copy.deepcopy(S1_EMBEDDED_STATE.get("settings") or {})
    if not isinstance(data, dict):
        print("[settings] ignoring malformed embedded settings")
        data = {}

    c = data.get("camera", {})
    cam.zoom = float(c.get("zoom", cam.zoom))
    cam.brightness = int(c.get("brightness", cam.brightness))
    cam.contrast = float(c.get("contrast", cam.contrast))
    cam.saturation = float(c.get("saturation", cam.saturation))
    cam.sharpness = float(c.get("sharpness", cam.sharpness))
    cam.rotation = int(c.get("rotation", cam.rotation)) % 360
    cam.mirror = bool(c.get("mirror", cam.mirror))

    t = data.get("trig_offset", {})
    global TRIG_CAMERA_HEIGHT_IN, TRIG_TAG_HEIGHT_IN, TRIG_BOARD_HEIGHT_IN
    global TRIG_PIVOT_X, TRIG_PIVOT_Y
    TRIG_CAMERA_HEIGHT_IN = float(t.get("camera_height_in", TRIG_CAMERA_HEIGHT_IN))
    TRIG_TAG_HEIGHT_IN = float(t.get("tag_height_in", TRIG_TAG_HEIGHT_IN))
    TRIG_BOARD_HEIGHT_IN = float(t.get("board_height_in", TRIG_BOARD_HEIGHT_IN))
    TRIG_PIVOT_X = float(t.get("pivot_x", TRIG_PIVOT_X))
    TRIG_PIVOT_Y = float(t.get("pivot_y", TRIG_PIVOT_Y))

    load_gripper_offsets(t)
    load_gripper_nudge(t)


    global BOARD_WIDTH_IN
    BOARD_WIDTH_IN = float(data.get("vision", {}).get("board_width_in",
                                                      BOARD_WIDTH_IN))
    load_vision_settings(data.get("vision", {}))

    global MANUAL_GRIPPER_STEPS, GRIPPER_AI, ERR_AUTO
    behaviour = data.get("behaviour", {})
    MANUAL_GRIPPER_STEPS = bool(behaviour.get(
        "manual_gripper_steps", MANUAL_GRIPPER_STEPS))
    GRIPPER_AI = bool(behaviour.get("gripper_ai", GRIPPER_AI))
    if behaviour.get("err_auto") in dict(ERR_AUTO_MODES):
        ERR_AUTO = behaviour["err_auto"]

    g = data.get("grid", {})
    CONFIG.n_cols = max(MIN_N, min(MAX_N_COLS, int(g.get("n_cols", CONFIG.n_cols))))
    CONFIG.n_rows = max(MIN_N, min(MAX_N_ROWS, int(g.get("n_rows", CONFIG.n_rows))))

    return cam, (g.get("box"), g.get("frame_size"),
                 bool(g.get("square_cells", True)), g.get("box_rel"))


def load_vision_settings(v):
    """Vision AI's saved settings, each checked the way Vision AI checks its
    yolo_settings.json: a value of the wrong kind or out of range keeps the
    default, with a warning, rather than reaching the pipeline."""
    global NAMER_MODEL, VISION_SCENE_HINT
    if not isinstance(v, dict):
        return
    numbers = {"conf_thres": "VISION_CONF", "iou_thres": "VISION_IOU",
               "max_area": "VISION_MAX_AREA", "outline_px": "VISION_OUTLINE_PX"}
    for key, name in numbers.items():
        if key not in v:
            continue
        lo, hi, _ = VISION_LIMITS[key]
        value = v[key]
        if (isinstance(value, (int, float)) and not isinstance(value, bool)
                and lo <= value <= hi):
            globals()[name] = int(value) if key == "outline_px" else float(value)
        else:
            print(f"[settings] vision {key}: {value!r} is not valid - keeping "
                  f"{globals()[name]!r}")
    for key, name in (("mark_parts", "VISION_MARK_PARTS"),
                      ("show_names", "VISION_SHOW_NAMES"),
                      ("priority_naming", "PRIORITY_NAMING")):
        if isinstance(v.get(key), bool):
            globals()[name] = v[key]
    if v.get("max_fps") in VISION_FPS_CHOICES:
        globals()["VISION_MAX_FPS"] = float(v["max_fps"])
    if v.get("namer_model") in NAMER_MODELS:
        NAMER_MODEL = v["namer_model"]
    if isinstance(v.get("scene_hint"), str) and v["scene_hint"].strip():
        VISION_SCENE_HINT = v["scene_hint"]


ARROW_KEYS = {
    0: (0, -1), 63232: (0, -1), 65362: (0, -1), 82: (0, -1),
    1: (0, 1), 63233: (0, 1), 65364: (0, 1), 84: (0, 1),
    2: (-1, 0), 63234: (-1, 0), 65361: (-1, 0), 81: (-1, 0),
    3: (1, 0), 63235: (1, 0), 65363: (1, 0), 83: (1, 0),
}
NUDGE_BUTTONS = {"manual_up": (0, -1), "manual_down": (0, 1),
                 "manual_left": (-1, 0), "manual_right": (1, 0)}
HEIGHT_KEYS = {ord("+"): True, ord("="): True, ord("-"): False,
               ord("_"): False}


class ManualMovePanel:
    """A popup for hand-picking a cell -- column and row, each its own
    dropdown -- and sending the gantry there via the exact same live
    AprilTag guidance the AI-driven runner uses.

    Opened from the "Comm" menu. Setting `state.target_col/row` directly
    (with no PlanRunner involved) is enough: `update_guidance` already
    re-derives directions from wherever the tag actually is every frame,
    whoever set the target.
    """

    WIDTH = 320
    PAD = 22
    ROW_H = 40

    def __init__(self):
        self.visible = False
        self._anim = 0.0
        self.letter_dd = Dropdown("Column", 0, 0, 0, 0, "manual_col")
        self.number_dd = Dropdown("Row", 0, 0, 0, 0, "manual_row")
        self.sel_col = None
        self.sel_row = None
        self.text_value = ""
        self.text_cursor = 0
        self.text_focus = False
        self.buttons = []
        self._field_rect = None
        self._last_rect = None

    def open(self):
        self.letter_dd.set_items([(i, CONFIG.columns[i])
                                  for i in range(CONFIG.n_cols)])
        self.number_dd.set_items([(i, str(CONFIG.rows[i]))
                                  for i in range(CONFIG.n_rows)])
        self.visible = True

    def toggle(self):
        if self.visible:
            self.close()
        else:
            self.open()

    def close(self):
        self.visible = False
        self.letter_dd.open = False
        self.number_dd.open = False
        self.text_focus = False

    def _rect_contains(self, x, y):
        if not self._last_rect:
            return False
        px, py, pw, ph = self._last_rect
        return px <= x <= px + pw and py <= y <= py + ph

    def _go(self, state, runner, sim):
        """Send the gantry to whatever cell is currently selected -- shared
        by the GO button and pressing Enter in the typed-coordinate field."""
        if runner.active or sim.active:
            return "Busy -- stop the current run first."
        if self.sel_col is None or self.sel_row is None:
            return "Pick a column and a row first."
        runner.stop(state, "Manual move started.")
        sim.stop(state, "Manual move started.")
        state.target_col, state.target_row = self.sel_col, self.sel_row
        state.arrived = False
        state.action_label = None
        state.manual_move_active = True
        name = coordinate_name(self.sel_col, self.sel_row)
        stop = tag_cell_for(self.sel_col, self.sel_row)
        off_note = ("" if gripper_offset() == (0, 0)
                    else f"  (tag -> {cell_label(*stop)})")
        chat_say(state, "assistant",
                 f"Manual move: guiding the gripper to {name}.{off_note}")
        self.close()
        return f"Guiding the gripper to {name}.{off_note}"

    def _nudge(self, dcol, drow, state, runner, sim):
        """Move the target one cell, then let the same live guidance drive it.

        The step is taken from the TARGET when a manual move is already under
        way, not from wherever the tag has got to -- so tapping right three
        times means three cells, instead of three races between the keypress
        and the carriage.
        """
        if runner.active or sim.active:
            return "Busy -- stop the current run first."
        if state.manual_move_active and state.target_col is not None:
            col, row = state.target_col, state.target_row
        elif state.last_tag_col is not None:
            col, row = gripper_cell(state.last_tag_col, state.last_tag_row)
        else:
            return ("No AprilTag detected yet -- show the tag to the "
                    "camera first.")
        col += dcol
        row += drow
        if not (0 <= col < CONFIG.n_cols and 0 <= row < CONFIG.n_rows):
            return "That is the edge of the board."
        self.sel_col, self.sel_row = col, row
        state.target_col, state.target_row = col, row
        state.arrived = False
        state.action_label = None
        state.manual_move_active = True
        return f"Jogging one cell to {coordinate_name(col, row)}."

    def _height(self, up, state, runner, sim):
        """A one-shot Z jog -- no camera can see height, so there is nothing
        to guide against and nothing to arrive at. Straight out the port."""
        if runner.active or sim.active:
            return "Busy -- stop the current run first."
        if not ARDUINO.connected:
            return "Not connected -- nothing sent."
        cmd = HEIGHT_UP_CMD if up else HEIGHT_DOWN_CMD
        if ARDUINO.send_command(cmd):
            return f"Sent {cmd} -- height {'up' if up else 'down'}."
        return f"Could not send {cmd} -- the board may still be booting."

    def _halt(self, state, runner, sim):
        """Everything stops: the plan, the sim, the pending manual target,
        and the motors.

        Order matters. The runner is cleared FIRST so that update_guidance
        has no target left to re-derive a direction from on the next frame --
        forcing 's' out first and then leaving a live target behind would put
        the carriage straight back into motion a frame later.
        """
        runner.stop(state, "Stopped.")
        sim.stop(state, "Stopped.")
        state.manual_move_active = False
        state.target_col = state.target_row = None
        state.arrived = False
        if not ARDUINO.connected:
            return "Stopped -- not connected, nothing sent."
        if ARDUINO.halt():
            return "Stopped -- sent s."
        return "Stopped -- could not send s, the board may still be booting."

    def handle_nav_key(self, key, state, runner, sim):
        """Arrow keys jog a cell, +/- jog the height. True when swallowed.

        Only while the card is open and the typed field is not focused: the
        masked arrow codes (0-3) are the sort of value a stray key can also
        produce, so they are never live when the operator cannot see what
        they would move.
        """
        if not self.visible or self.text_focus:
            return False
        step = ARROW_KEYS.get(key)
        if step is not None:
            state.status_message = self._nudge(step[0], step[1], state,
                                               runner, sim)
            return True
        if key in HEIGHT_KEYS:
            state.status_message = self._height(HEIGHT_KEYS[key], state,
                                                runner, sim)
            return True
        if key == 32:
            state.status_message = self._halt(state, runner, sim)
            return True
        return False

    def handle_key(self, key, state, runner, sim):
        """A minimal line editor for the typed-coordinate field, the same
        key codes ConsolePanel/AISidebar use. Returns True when the key was
        ours to swallow (the field is focused), False otherwise."""
        if not self.text_focus:
            return False
        if key in (13, 10):
            hit = parse_coordinate(self.text_value)
            if hit is None:
                return True
            self.sel_col, self.sel_row = hit
            state.status_message = self._go(state, runner, sim)
            return True
        if key in (8, 127):
            if self.text_cursor > 0:
                self.text_value = (self.text_value[:self.text_cursor - 1]
                                   + self.text_value[self.text_cursor:])
                self.text_cursor -= 1
            return True
        if key == 27:
            self.text_focus = False
            return True
        ch = chr(key) if 32 <= key < 127 else None
        if ch and ch.isalnum() and len(self.text_value) < 6:
            self.text_value = (self.text_value[:self.text_cursor] + ch
                               + self.text_value[self.text_cursor:])
            self.text_cursor += 1
        hit = parse_coordinate(self.text_value)
        if hit is not None:
            self.sel_col, self.sel_row = hit
        return True

    def hit_test(self, x, y, state, runner, sim):
        """Same contract as PortPanel.hit_test -- None means "not mine",
        a string (possibly empty) means the click was consumed here."""
        if not self.visible:
            return None
        for b in self.buttons:
            if not b.contains(x, y):
                continue
            if b.kind == "manual_text":
                self.text_focus = True
                self.text_cursor = len(self.text_value)
                return ""
            if b.kind == "manual_go":
                self.text_focus = False
                return self._go(state, runner, sim)
            if b.kind in NUDGE_BUTTONS:
                self.text_focus = False
                dcol, drow = NUDGE_BUTTONS[b.kind]
                return self._nudge(dcol, drow, state, runner, sim)
            if b.kind == "manual_halt":
                self.text_focus = False
                return self._halt(state, runner, sim)
            if b.kind in ("manual_hu", "manual_hd"):
                self.text_focus = False
                return self._height(b.kind == "manual_hu", state, runner, sim)
            if b.kind == "manual_stop":
                self.text_focus = False
                runner.stop(state, "Manual move cancelled.")
                state.manual_move_active = False
                return "Manual move cancelled."
            if b.kind == "close":
                self.close()
                return "Manual move closed."
        if self._rect_contains(x, y):
            self.text_focus = False
            return ""
        return None

    def dropdown_hit(self, x, y):
        """Explicit open/select handling for the two dropdowns, the same
        pattern the camera picker uses -- returns True if the click was the
        dropdowns' business (open, close, or pick an item)."""
        if not self.visible:
            return False
        for dd, target in ((self.letter_dd, "sel_col"),
                           (self.number_dd, "sel_row")):
            if dd.open:
                chosen = dd.hit_item(x, y)
                in_list = dd.list_contains(x, y)
                on_button = dd.contains(x, y)
                dd.open = False
                if chosen is not None:
                    setattr(self, target, chosen)
                    self.text_focus = False
                    return True
                if in_list or on_button:
                    return True
        for dd in (self.letter_dd, self.number_dd):
            if dd.contains(x, y):
                was_open = dd.open
                self.letter_dd.open = False
                self.number_dd.open = False
                dd.open = not was_open
                self.text_focus = False
                return True
        return False

    def draw(self, frame, mouse=(-1, -1)):
        self._anim = ease_toward(self._anim, 1.0 if self.visible else 0.0,
                                 ANIM_RATE)
        if self._anim < 0.004:
            return
        fh, fw = frame.shape[:2]
        pw = min(self.WIDTH, fw - 2 * self.PAD)
        ph = self.PAD * 2 + 60 + 6 * self.ROW_H + 44
        px = (fw - pw) // 2
        py = self.PAD
        self._last_rect = (px, py, pw, ph)
        rect = (px, py, px + pw, py + ph)

        margin = 40
        bx0, by0 = max(0, px - margin), max(0, py - margin)
        bx1, by1 = min(fw, px + pw + margin), min(fh, py + ph + margin)
        fading = self._anim < 0.999
        under = frame[by0:by1, bx0:bx1].copy() if fading else None

        glass_card(frame, rect, 28, alpha=0.62)
        draw_text(frame, "Manual Move", (px + 24, py + 36), 0.72, C_TEXT, 2)
        draw_text(frame, "Send the gantry to a cell via AprilTag guidance.",
                  (px + 24, py + 58), 0.36, C_TEXT_DIM, 1)

        mx, my = mouse
        y = py + 74
        half = (pw - 24 * 2 - 12) // 2
        self.letter_dd.x0, self.letter_dd.y0 = px + 24, y
        self.letter_dd.x1, self.letter_dd.y1 = px + 24 + half, y + self.ROW_H - 4
        self.number_dd.x0, self.number_dd.y0 = px + 36 + half, y
        self.number_dd.x1, self.number_dd.y1 = px + pw - 24, y + self.ROW_H - 4
        letter = CONFIG.columns[self.sel_col] if self.sel_col is not None else None
        number = CONFIG.rows[self.sel_row] if self.sel_row is not None else None
        self.letter_dd.draw(frame, letter, hover=self.letter_dd.contains(mx, my))
        self.number_dd.draw(frame, number, hover=self.number_dd.contains(mx, my))
        y += self.ROW_H

        draw_text(frame, "or type a cell (e.g. f18) and press Enter",
                  (px + 24, y + 10), 0.34, C_TEXT_DIM, 1)
        field_h = 30
        fx0, fy0 = px + 24, y + 16
        fx1, fy1 = px + pw - 24, y + 16 + field_h
        self._field_rect = (fx0, fy0, fx1, fy1)
        rounded_rect(frame, (fx0, fy0, fx1, fy1), 10,
                    C_GHOST_HOV if self.text_focus else C_GHOST, -1)
        rounded_rect(frame, (fx0, fy0, fx1, fy1), 10,
                    C_ACCENT if self.text_focus else C_BORDER, 1)
        shown_text = self.text_value.upper() or ("" if self.text_focus
                                                  else "F18, k11, ...")
        text_colour = C_TEXT if self.text_value else C_TEXT_DIM
        draw_text(frame, shown_text, (fx0 + 10, fy0 + 21), 0.4, text_colour, 1)
        if self.text_focus and int(time.time() * 2) % 2 == 0:
            cw, _ = text_size(shown_text[:self.text_cursor], 0.4, 1)
            cx = fx0 + 12 + cw
            cv2.line(frame, (cx, fy0 + 5), (cx, fy1 - 5), C_ACCENT, 1, cv2.LINE_AA)
        y += self.ROW_H

        self.buttons = []
        close_top = Button("X", px + pw - 52, py + 12,
                           px + pw - 20, py + 44, "close", scale=0.46)
        close_top.draw(frame, hover=close_top.contains(mx, my), shadow=False)
        self.buttons.append(close_top)
        text_field = Button("", fx0, fy0, fx1, fy1, "manual_text")
        self.buttons.append(text_field)
        go = Button("GO", px + 24, y + 8, px + 24 + half, y + self.ROW_H + 2,
                   "manual_go", style="accent", scale=0.46)
        stop = Button("STOP", px + 36 + half, y + 8, px + pw - 24,
                     y + self.ROW_H + 2, "manual_stop", style="primary",
                     scale=0.44)
        go.draw(frame, hover=go.contains(mx, my), shadow=False)
        stop.draw(frame, hover=stop.contains(mx, my), shadow=False)
        self.buttons.extend([go, stop])

        gap = 8
        y += self.ROW_H + 14
        draw_text(frame, "Jog one cell  (arrow keys)", (px + 24, y),
                  0.34, C_TEXT_DIM, 1)
        y += 8
        bw = (pw - 48 - 3 * gap) // 4
        for i, (label, kind) in enumerate((("<", "manual_left"),
                                           ("^", "manual_up"),
                                           ("v", "manual_down"),
                                           (">", "manual_right"))):
            bx = px + 24 + i * (bw + gap)
            b = Button(label, bx, y, bx + bw, y + self.ROW_H - 6, kind,
                       style="primary", scale=0.5)
            b.draw(frame, hover=b.contains(mx, my), shadow=False)
            self.buttons.append(b)
        y += self.ROW_H + 8

        draw_text(frame, "Height  (+ / -)", (px + 24, y), 0.34, C_TEXT_DIM, 1)
        y += 8
        hw = (pw - 48 - gap) // 2
        for i, (label, kind) in enumerate((("HEIGHT -", "manual_hd"),
                                           ("HEIGHT +", "manual_hu"))):
            bx = px + 24 + i * (hw + gap)
            b = Button(label, bx, y, bx + hw, y + self.ROW_H - 6, kind,
                       style="primary", scale=0.42)
            b.draw(frame, hover=b.contains(mx, my), shadow=False)
            self.buttons.append(b)
        y += self.ROW_H + 6

        halt = Button("STOP  -  SEND s", px + 24, y, px + pw - 24,
                      y + self.ROW_H - 6, "manual_halt", style="accent",
                      scale=0.46)
        halt.draw(frame, hover=halt.contains(mx, my), shadow=False)
        self.buttons.append(halt)

        if fading:
            drawn = frame[by0:by1, bx0:bx1]
            frame[by0:by1, bx0:bx1] = cv2.addWeighted(
                drawn, self._anim, under, 1.0 - self._anim, 0)

    def draw_lists(self, frame, mouse=(-1, -1)):
        """Painted last, on top of everything else in the video."""
        if not self.visible:
            return
        self.letter_dd.draw_list(frame, self.sel_col, mouse)
        self.number_dd.draw_list(frame, self.sel_row, mouse)


def dispatch_video_dropdowns(x, y, settings_panel, trig_panel, manual_panel):
    """Match draw_lists order so a lower popup cannot steal an offset click."""
    for panel in (settings_panel, trig_panel, manual_panel):
        if panel.dropdown_hit(x, y):
            return True
    return False


class TrigPanel:
    """A small frosted card, opened from its own "Trigonometry" menu, for
    the two measurements apply_trig_offset() derives its correction from --
    the camera's height above the board and the AprilTag's height above it --
    plus the pivot point the correction radiates from, for a mount that
    isn't perfectly centered over the board.

    Split out from the main Settings card since these are physical
    measurements of the rig, not a display/behavior preference -- they only
    change if the camera or gantry is physically remounted.
    """

    ROW_H = 42
    PAD = 22
    WIDTH = 420

    def __init__(self):
        self.visible = False
        self.buttons = []
        self._last_rect = None
        self._anim = 0.0
        self.vertical_dd = Dropdown("Up/Down cells", 0, 0, 0, 0, "offset_vertical")
        self.vertical_dir_dd = Dropdown("Direction", 0, 0, 0, 0, "offset_vertical_dir")
        self.horizontal_dd = Dropdown("Left/Right cells", 0, 0, 0, 0, "offset_horizontal")
        self.horizontal_dir_dd = Dropdown("Direction", 0, 0, 0, 0, "offset_horizontal_dir")
        self.offset_dropdowns = (self.vertical_dd, self.vertical_dir_dd,
                                 self.horizontal_dd, self.horizontal_dir_dd)
        for dd in self.offset_dropdowns:
            dd.list_columns = 5
            dd.ITEM_W = 56
            dd.ITEM_H = 40
            dd.list_alpha = 1.0
            dd.list_text_scale = 0.62
        for dd in (self.vertical_dd, self.horizontal_dd):
            dd.set_items([(n, str(n)) for n in range(MAX_GRIPPER_OFFSET + 1)])
        for dd, directions in ((self.vertical_dir_dd, ("up", "down")),
                               (self.horizontal_dir_dd, ("left", "right"))):
            dd.list_columns = 2
            dd.ITEM_W = 88
            dd.set_items([(d, d.title()) for d in directions])
        self.nudge_dir_dd = Dropdown("Direction", 0, 0, 0, 0, "nudge_dir")
        self.nudge_dir_dd.list_columns = 4
        self.nudge_dir_dd.ITEM_W = 70
        self.nudge_dir_dd.ITEM_H = 40
        self.nudge_dir_dd.list_alpha = 1.0
        self.nudge_dir_dd.list_text_scale = 0.62
        self.nudge_dir_dd.set_items([(d, d.title()) for d in
                                     ("up", "down", "left", "right")])

    def offset_values(self):
        return (abs(GRIPPER_OFFSET_UP_DOWN),
                GRIPPER_VERTICAL_DIRECTION, abs(GRIPPER_OFFSET_RIGHT_LEFT),
                GRIPPER_HORIZONTAL_DIRECTION)

    def _all_dropdowns(self):
        return self.offset_dropdowns + (self.nudge_dir_dd,)

    def toggle(self):
        self.visible = not self.visible
        if not self.visible:
            for dd in self._all_dropdowns():
                dd.open = False

    def _rect_contains(self, x, y):
        if not self._last_rect:
            return False
        px, py, pw, ph = self._last_rect
        return px <= x <= px + pw and py <= y <= py + ph

    def dropdown_hit(self, x, y):
        if not self.visible:
            return False
        global GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT
        global GRIPPER_VERTICAL_DIRECTION, GRIPPER_HORIZONTAL_DIRECTION
        global GRIPPER_NUDGE_DIRECTION
        for dd in self._all_dropdowns():
            if dd.open:
                chosen = dd.hit_item(x, y)
                consumed = dd.list_contains(x, y) or dd.contains(x, y)
                dd.open = False
                if chosen is not None:
                    if dd is self.vertical_dd:
                        GRIPPER_OFFSET_UP_DOWN = int(chosen) * (
                            -1 if GRIPPER_VERTICAL_DIRECTION == "up" else 1)
                    elif dd is self.horizontal_dd:
                        GRIPPER_OFFSET_RIGHT_LEFT = int(chosen) * (
                            -1 if GRIPPER_HORIZONTAL_DIRECTION == "left" else 1)
                    elif dd is self.vertical_dir_dd:
                        GRIPPER_VERTICAL_DIRECTION = chosen
                        GRIPPER_OFFSET_UP_DOWN = abs(GRIPPER_OFFSET_UP_DOWN) * (
                            -1 if chosen == "up" else 1)
                    elif dd is self.horizontal_dir_dd:
                        GRIPPER_HORIZONTAL_DIRECTION = chosen
                        GRIPPER_OFFSET_RIGHT_LEFT = abs(GRIPPER_OFFSET_RIGHT_LEFT) * (
                            -1 if chosen == "left" else 1)
                    else:
                        GRIPPER_NUDGE_DIRECTION = chosen
                    return True
                if consumed:
                    return True
        for dd in self._all_dropdowns():
            if dd.contains(x, y):
                for other in self._all_dropdowns():
                    other.open = False
                dd.open = True
                return True
        return False

    def draw_lists(self, frame, mouse=(-1, -1)):
        if self.visible:
            for dd, value in zip(self.offset_dropdowns, self.offset_values()):
                dd.draw_list(frame, value, mouse)
            self.nudge_dir_dd.draw_list(frame, GRIPPER_NUDGE_DIRECTION, mouse)

    def hit_test(self, x, y, cam_settings, grid, state, runner=None, sim=None):
        if not self.visible:
            return None
        before = self.offset_values() + (GRIPPER_NUDGE_DIRECTION,)
        if self.dropdown_hit(x, y):
            after = self.offset_values() + (GRIPPER_NUDGE_DIRECTION,)
            if after != before:
                save_settings(cam_settings, grid)
            if after[:4] != before[:4]:
                return f"Gripper offset: {gripper_offset_label()}"
            return f"Nudge direction: {GRIPPER_NUDGE_DIRECTION}"
        for b in self.buttons:
            if not b.contains(x, y):
                continue
            if b.kind == "trig_step":
                axis, delta = b.value
                global TRIG_CAMERA_HEIGHT_IN, TRIG_TAG_HEIGHT_IN
                global TRIG_BOARD_HEIGHT_IN
                if axis == "camera":
                    TRIG_CAMERA_HEIGHT_IN = round(
                        max(1.0, min(240.0, TRIG_CAMERA_HEIGHT_IN + delta)), 1)
                elif axis == "tag":
                    TRIG_TAG_HEIGHT_IN = round(
                        max(0.0, min(239.0, TRIG_TAG_HEIGHT_IN + delta)), 1)
                else:
                    TRIG_BOARD_HEIGHT_IN = round(
                        max(0.0, min(238.0, TRIG_BOARD_HEIGHT_IN + delta)), 1)
                h_in, H_in = trig_heights()
                return (f'Above board: tag {h_in:g}", cam {H_in:g}" '
                        f"-> k={trig_offset_k():.3f}")
            if b.kind == "trig_pivot_step":
                axis, delta = b.value
                global TRIG_PIVOT_X, TRIG_PIVOT_Y
                if axis == "x":
                    TRIG_PIVOT_X = max(-400.0, min(400.0, TRIG_PIVOT_X + delta))
                else:
                    TRIG_PIVOT_Y = max(-400.0, min(400.0, TRIG_PIVOT_Y + delta))
                return f"Pivot {TRIG_PIVOT_X:+.0f}, {TRIG_PIVOT_Y:+.0f}px"
            if b.kind == "nudge_step":
                global GRIPPER_NUDGE_S
                GRIPPER_NUDGE_S = round(max(0.0, min(2.0,
                    GRIPPER_NUDGE_S + b.value)), 2)
                save_settings(cam_settings, grid)
                return f"Nudge: {GRIPPER_NUDGE_S:g}s {GRIPPER_NUDGE_DIRECTION}"
            if b.kind == "nudge_toggle":
                action = b.value
                GRIPPER_NUDGE_ACTIONS[action] = not GRIPPER_NUDGE_ACTIONS[action]
                save_settings(cam_settings, grid)
                state_word = "on" if GRIPPER_NUDGE_ACTIONS[action] else "off"
                return f"Nudge before {action}: {state_word}"
            if b.kind == "save":
                save_settings(cam_settings, grid)
                return f"Saved to {os.path.basename(SETTINGS_PATH)}"
            if b.kind == "close":
                self.toggle()
                return "Trigonometry closed."
        if self._rect_contains(x, y):
            return ""
        return None

    def draw(self, frame, grid=None, mouse=(-1, -1)):
        self._anim = ease_toward(self._anim, 1.0 if self.visible else 0.0,
                                 ANIM_RATE)
        if self._anim < 0.004:
            return
        fh, fw = frame.shape[:2]
        pw = min(self.WIDTH, fw - 2 * self.PAD)
        row_h = max(26, min(self.ROW_H, (fh - 2 * self.PAD - 200) // 8))
        ph = 200 + row_h * 8 + 210
        px, py = self.PAD, self.PAD
        self._last_rect = (px, py, pw, ph)
        rect = (px, py, px + pw, py + ph)

        margin = 40
        bx0, by0 = max(0, px - margin), max(0, py - margin)
        bx1, by1 = min(fw, px + pw + margin), min(fh, py + ph + margin)
        fading = self._anim < 0.999
        under = frame[by0:by1, bx0:bx1].copy() if fading else None

        glass_card(frame, rect, 28, alpha=0.62)
        draw_text(frame, "Trigonometry", (px + 24, py + 36), 0.72, C_TEXT, 2)

        mx, my = mouse
        self.buttons = []
        close_top = Button("X", px + pw - 52, py + 12,
                           px + pw - 20, py + 44, "close", scale=0.46)
        close_top.draw(frame, hover=close_top.contains(mx, my), shadow=False)
        self.buttons.append(close_top)
        y = py + 54
        for axis, label, value in (
                ("camera", "Camera height (in)", TRIG_CAMERA_HEIGHT_IN),
                ("tag", "Tag height (in)", TRIG_TAG_HEIGHT_IN),
                ("board", "Board surface (in)", TRIG_BOARD_HEIGHT_IN)):
            draw_text(frame, label, (px + 24, y + 26), 0.48, C_TEXT, 1)
            vtext = f'{value:g}"'
            vw, _ = text_size(vtext, 0.48, 2)
            draw_text(frame, vtext, (px + pw - 128 - vw, y + 26), 0.48, C_ACCENT, 2)
            minus = Button("-", px + pw - 116, y + 4, px + pw - 78, y + row_h - 6,
                           "trig_step", (axis, -1), style="ghost", scale=0.62)
            plus = Button("+", px + pw - 68, y + 4, px + pw - 30, y + row_h - 6,
                          "trig_step", (axis, +1), style="ghost", scale=0.62)
            minus.draw(frame, hover=minus.contains(mx, my), shadow=False)
            plus.draw(frame, hover=plus.contains(mx, my), shadow=False)
            self.buttons.extend([minus, plus])
            y += row_h

        for axis, label, value in (("x", "Pivot X (px)", TRIG_PIVOT_X),
                                   ("y", "Pivot Y (px)", TRIG_PIVOT_Y)):
            draw_text(frame, label, (px + 24, y + 26), 0.48, C_TEXT, 1)
            vtext = f"{value:+.0f}px"
            vw, _ = text_size(vtext, 0.48, 2)
            draw_text(frame, vtext, (px + pw - 128 - vw, y + 26), 0.48, C_ACCENT, 2)
            pminus = Button("-", px + pw - 116, y + 4, px + pw - 78, y + row_h - 6,
                            "trig_pivot_step", (axis, -5), style="ghost", scale=0.62)
            pplus = Button("+", px + pw - 68, y + 4, px + pw - 30, y + row_h - 6,
                          "trig_pivot_step", (axis, +5), style="ghost", scale=0.62)
            pminus.draw(frame, hover=pminus.contains(mx, my), shadow=False)
            pplus.draw(frame, hover=pplus.contains(mx, my), shadow=False)
            self.buttons.extend([pminus, pplus])
            y += row_h

        half = (pw - 60) // 2

        cv2.line(frame, (px + 24, y + 2), (px + pw - 24, y + 2), C_BORDER, 1)
        draw_text(frame, "Custom offset", (px + 24, y + 24), 0.48, C_TEXT, 1)
        y += 32
        for i, (dd, value) in enumerate(zip(self.offset_dropdowns, self.offset_values())):
            x0 = px + 24 if i % 2 == 0 else px + 36 + half
            x1 = px + 24 + half if i % 2 == 0 else px + pw - 24
            yy = y + (i // 2) * 52
            dd.x0, dd.y0, dd.x1, dd.y1 = x0, yy, x1, yy + 44
            dd.draw(frame, value.title() if isinstance(value, str) else value,
                    hover=dd.contains(mx, my))
        y += 106

        cv2.line(frame, (px + 24, y + 2), (px + pw - 24, y + 2), C_BORDER, 1)
        draw_text(frame, "Pre-action nudge", (px + 24, y + 24), 0.48, C_TEXT, 1)
        y += 32

        draw_text(frame, "Duration (s)", (px + 24, y + 26), 0.48, C_TEXT, 1)
        dtext = f"{GRIPPER_NUDGE_S:g}"
        dw, _ = text_size(dtext, 0.48, 2)
        draw_text(frame, dtext, (px + pw - 128 - dw, y + 26), 0.48, C_ACCENT, 2)
        nminus = Button("-", px + pw - 116, y + 4, px + pw - 78, y + row_h - 6,
                        "nudge_step", -0.05, style="ghost", scale=0.62)
        nplus = Button("+", px + pw - 68, y + 4, px + pw - 30, y + row_h - 6,
                       "nudge_step", +0.05, style="ghost", scale=0.62)
        nminus.draw(frame, hover=nminus.contains(mx, my), shadow=False)
        nplus.draw(frame, hover=nplus.contains(mx, my), shadow=False)
        self.buttons.extend([nminus, nplus])
        y += row_h

        draw_text(frame, "Direction", (px + 24, y + 22), 0.48, C_TEXT, 1)
        self.nudge_dir_dd.x0, self.nudge_dir_dd.y0 = px + 24 + half, y
        self.nudge_dir_dd.x1, self.nudge_dir_dd.y1 = px + pw - 24, y + 44
        self.nudge_dir_dd.draw(frame, GRIPPER_NUDGE_DIRECTION.title(),
                               hover=self.nudge_dir_dd.contains(mx, my))
        y += 52

        draw_text(frame, "Nudge before:", (px + 24, y + 26), 0.42, C_TEXT_DIM, 1)
        y += 30
        toggle_w = (pw - 48 - 3 * 8) // 4
        tx = px + 24
        for action, short in (("pickup", "Pickup"), ("keep", "Keep"),
                              ("press", "Press"), ("release", "Release")):
            on = GRIPPER_NUDGE_ACTIONS[action]
            btn = Button(short, tx, y, tx + toggle_w, y + row_h - 6,
                        "nudge_toggle", action, style="ghost", scale=0.42)
            btn.draw(frame, hover=btn.contains(mx, my), active=on, shadow=False)
            self.buttons.append(btn)
            tx += toggle_w + 8
        y += row_h + 4

        cv2.line(frame, (px + 24, y + 2), (px + pw - 24, y + 2), C_BORDER, 1)
        h_in, H_in = trig_heights()
        k = trig_offset_k()
        if H_in <= 0 or h_in < 0 or h_in >= H_in:
            line, line_c = "Heights are impossible -- correction is OFF", C_AMBER
        else:
            shift = (h_in / (H_in - h_in)) * (CONFIG.n_cols / 2.0)
            line = (f'above board: tag {h_in:g}", cam {H_in:g}"  ->  '
                    f"k={k:.3f}, edge shift {shift:.1f} cells")
            line_c = C_TEXT_DIM
        draw_text(frame, line, (px + 24, y + 26), 0.36, line_c, 1)
        y += 40

        save = Button("SAVE", px + 24, y + 4, px + 24 + half, y + row_h - 6,
                      "save", style="primary", scale=0.46)
        close = Button("CLOSE", px + 36 + half, y + 4, px + pw - 24,
                       y + row_h - 6, "close", scale=0.46)
        save.draw(frame, hover=save.contains(mx, my), shadow=False)
        close.draw(frame, hover=close.contains(mx, my), shadow=False)
        self.buttons.extend([save, close])

        if fading:
            drawn = frame[by0:by1, bx0:bx1]
            frame[by0:by1, bx0:bx1] = cv2.addWeighted(
                drawn, self._anim, under, 1.0 - self._anim, 0)
        self.draw_lists(frame, mouse)


class GripperPanel:
    """The "gripper popup": jaw angle on a slider, a Height Up/Down pair, and
    a mini jog d-pad, opened from its own Gripper menu.

    Three different things are live here, and each speaks a different serial
    token:
      - Grip: a position. Dragging the slider sends "g<degrees>" (see
        grip_command) -- an absolute angle, so nothing needs to stop.
      - Height: a one-shot nudge. Each press sends HEIGHT_UP_CMD/DOWN_CMD
        ("hu"/"hd") once, straight out the port -- no camera can see height,
        so there is nothing to guide against and nothing to hold down.
      - Jog: a timed pulse. Pressing a direction sends that direction's
        letter, holds it for JOG_PULSE_S, then sends 's' -- turning "keep
        going until told to stop" into a small fixed nudge (see _start_jog).
        tick() has to be called every frame for that pulse to end on time.

    Nothing here is persisted; the grip slider starts at its midpoint every
    launch. Each control's sending is confined to one method (_send_grip,
    _height_step, _start_jog) so there is one place to look when the
    hardware does not follow the UI.
    """

    ROW_H = 58
    PAD = 28
    WIDTH = 900

    GRIP_LO, GRIP_HI = float(GRIP_MIN_DEG), float(GRIP_MAX_DEG)

    JOG_BTN = 48
    JOG_GAP = 16
    JOG_LAYOUT = {"up": (0, 1), "left": (1, 0), "right": (1, 2), "down": (2, 1)}
    JOG_ARROWS = {"up": "^", "down": "v", "left": "<", "right": ">"}
    JOG_STOP_ROW_COL = (1, 1)

    AUTO_GRIP_IDLE = "idle"
    AUTO_GRIP_WAIT_DOWN = "wait_down"
    AUTO_GRIP_DOWN = "down"
    AUTO_GRIP_WAIT_GRIP = "wait_grip"
    AUTO_GRIP_WAIT_UP = "wait_up"
    AUTO_GRIP_UP = "up"
    AUTO_GRIP_WAIT_STOP = "wait_stop"
    AUTO_GRIP_WAIT_HX = "wait_hx"
    AUTO_GRIP_HX = "hx"
    AUTO_GRIP_WAIT_G90 = "wait_g90"
    AUTO_GRIP_WAIT_HU = "wait_hu"

    NOTE = "Automatic pickup, keep, press and release are available below."
    NOTE_SCALE = 0.4
    NOTE_LINE_H = 18
    INSTR_SCALE = 0.62
    INSTR_LINE_H = 28

    def __init__(self):
        self.visible = False
        self.buttons = []
        self._last_rect = None
        self._anim = 0.0
        self.grip = 0.0
        self.dragging = None
        self._grip_sent = None
        self._grip_tx_at = 0.0
        self._last_height_cmd = None
        self.jog_dir = None
        self.jog_until = 0.0
        self.auto_grip_phase = self.AUTO_GRIP_IDLE
        self.auto_grip_started_at = 0.0
        self.auto_grip_down_duration = 0.0
        self.auto_grip_up_until = 0.0
        self.auto_pulse_kind = None
        self.auto_pulse_until = 0.0
        self.auto_press_started_at = 0.0
        self.auto_press_duration = 0.0
        self.offset_phase = "idle"
        self.offset_action = ""
        self.offset_until = 0.0
        self.offset_failed = False
        self.offset_deadline = 0.0
        global ACTIVE_GRIPPER_PANEL
        ACTIVE_GRIPPER_PANEL = self
        self.pending_auto_actions = []
        self.last_msg = ""
        self.instruction = ""
        self.awaiting_confirm = False
        self.sliders = (
            Slider("Grip", "grip_grip", self.GRIP_LO, self.GRIP_HI,
                   "{:.0f}", "\u00b0"),
        )

    def toggle(self):
        self.visible = not self.visible
        if not self.visible:
            self.dragging = None

    def open(self):
        self.visible = True

    def close(self):
        self.visible = False
        self.dragging = None

    def show_instruction(self, text: str):
        """A plan step needs doing by hand. Open the card, say what, and
        start waiting for DONE.

        Opening rather than merely updating: the operator's attention is on
        the board, and an instruction on a card they closed ten steps ago
        would never be seen -- the run would just appear to hang.
        """
        self.instruction = str(text or "")
        self.awaiting_confirm = True
        self.last_msg = ""
        self.visible = True

    def confirm(self) -> bool:
        """DONE pressed: the operator says the step is carried out. True if
        that actually ended a wait, so the caller can ignore a stray press."""
        was, self.awaiting_confirm = self.awaiting_confirm, False
        self.instruction = ""
        return was

    def clear_instruction(self):
        """The run stopped or moved on by itself -- drop the manual step so
        a stale instruction cannot keep a later run waiting on it."""
        self.instruction = ""
        self.awaiting_confirm = False

    def waiting_for_confirm(self) -> bool:
        return self.awaiting_confirm

    def automatic_busy(self) -> bool:
        return (self.offset_phase != "idle"
                or self.auto_grip_phase != self.AUTO_GRIP_IDLE
                or bool(self.pending_auto_actions))

    def start_automatic_action(self, action: str, *, immediate=False) -> str:
        self.last_msg = self._start_offset_action(action, immediate=immediate)
        return self.last_msg

    def slider(self, kind):
        for sl in self.sliders:
            if sl.kind == kind:
                return sl
        return None

    def value_of(self, kind) -> float:
        return self.grip

    def set_value(self, kind, value, final=False):
        sl = self.slider(kind)
        v = round(sl.clamp(value)) if sl is not None else value
        self.grip = v
        self._send_grip(final=final)
        return v

    def _send_grip(self, final=False):
        """Push the current jaw angle to the Arduino, throttled.

        Skipped when the angle has not changed since the last confirmed
        write, and -- unless this is the value a drag ended on -- when the
        last write was too recent. A failed write is not recorded, so the
        next move retries it instead of leaving the jaw behind.
        """
        cmd = grip_command(self.grip)
        if cmd == self._grip_sent:
            return False
        now = time.time()
        if not final and now - self._grip_tx_at < GRIP_SEND_INTERVAL_S:
            return False
        if not ARDUINO.send_command(cmd):
            return False
        self._grip_sent = cmd
        self._grip_tx_at = now
        return True

    def _height_step(self, up: bool) -> str:
        """A one-shot Z nudge -- HU or HD, sent once, straight out the port."""
        if not ARDUINO.connected:
            return "Not connected -- nothing sent."
        cmd = HEIGHT_UP_CMD if up else HEIGHT_DOWN_CMD
        return self._send_height_command(cmd, "up" if up else "down")

    def _send_height_command(self, cmd: str, direction: str) -> str:
        """Send a one-shot height command without sensor handling."""
        if not ARDUINO.connected:
            return "Not connected -- nothing sent."
        if not ARDUINO.send_command(cmd):
            return f"Could not send {cmd} -- the board may still be booting."
        self._last_height_cmd = cmd
        return f"Sent {cmd} -- height {direction}."

    def _start_jog(self, direction: str) -> str:
        """A tiny, fixed-length jerk: send the direction letter at SLOW_SUFFIX
        speed ("uq"/"dq"/"lq"/"rq"), hold it for JOG_PULSE_S, then send 's'
        (see tick()).

        Slow because a jog this small is a fine positioning nudge, not a
        traverse -- the same distinction ManualMovePanel/send_direction's
        `slow` makes for easing into a target cell, just always-on here
        rather than conditional on how close the target is.

        If a previous pulse is still running, it is stopped first -- the
        board should never be told to hold two directions across an
        un-halted handoff between them.
        """
        if not ARDUINO.connected:
            return f"Not connected -- {direction} jog not sent."
        if self.jog_dir is not None:
            ARDUINO.halt()
        letter = DIRECTION_LETTERS[direction] + SLOW_SUFFIX
        if not ARDUINO.send_command(letter):
            self.jog_dir = None
            return f"Could not send {letter} -- the board may still be booting."
        self.jog_dir = direction
        self.jog_until = time.time() + JOG_PULSE_S
        return f'Jogging {direction} ("{letter}") for {JOG_PULSE_S:g}s...'

    def tick(self):
        """Called every frame: ends a jog pulse once its time is up.

        Not driven by sleeping -- like PlungeSequence, the pulse has to end
        on schedule regardless of how often the frame loop happens to call
        in, and sleeping here would freeze the whole window for 0.2s.
        """
        if self.jog_dir is not None and time.time() >= self.jog_until:
            ARDUINO.halt()
            self.jog_dir = None
        if self.auto_pulse_kind is not None and time.monotonic() >= self.auto_pulse_until:
            ARDUINO.halt()
            self.last_msg = f"Automatic {self.auto_pulse_kind}: sent s."
            self.auto_pulse_kind = None
        now = time.monotonic()
        if (self.offset_phase != "idle" and self.offset_deadline
                and now >= self.offset_deadline):
            ARDUINO.halt()
            self.auto_grip_phase = self.AUTO_GRIP_IDLE
            self.auto_grip_down_duration = 0.0
            self._abort_offset_action(
                f"Automatic {self.offset_action or 'action'} gave up after "
                f"{AUTO_ACTION_MAX_S:g}s -- sent s.")
            return
        if self.offset_phase == "nudge" and now >= self.offset_until:
            if ARDUINO.halt():
                self.offset_phase = "wait_action"
                self.offset_until = now + AUTO_ACTION_GAP_S
                self.last_msg = f"Nudge complete -- automatic {self.offset_action} in {AUTO_ACTION_GAP_S:.1f}s."
            else:
                self.last_msg = "Nudge duration finished -- retrying lowercase s."
        elif self.offset_phase == "wait_action" and now >= self.offset_until:
            self.offset_phase = "action"
            self._execute_offset_action(self.offset_action)
        elif self.offset_phase == "action":
            self._execute_offset_action(self.offset_action)
        elif self.offset_phase == "wait_pickup" and self.auto_grip_phase == self.AUTO_GRIP_IDLE:
            self._schedule_action_complete(now)
        elif self.offset_phase == "press_down":
            if now - self.auto_press_started_at >= AUTO_GRIP_DOWN_MAX_S:
                ARDUINO.halt()
                self.auto_press_duration = max(
                    0.0, now - self.auto_press_started_at)
                self._abort_offset_action(
                    f"Automatic press failed: no limit-switch signal in "
                    f"{AUTO_GRIP_DOWN_MAX_S:g}s -- sent s.")
                return
        elif self.offset_phase == "press_lift_pending":
            if ARDUINO.send_command(HEIGHT_UP_CMD):
                self.offset_phase = "press_lift"
                self.offset_until = now + AUTO_PRESS_BACKOFF_S
                self.last_msg = (f"Automatic press: hu for "
                                 f"{AUTO_PRESS_BACKOFF_S:.1f}s.")
        elif (self.offset_phase in ("press_lift", "wait_release")
                and now >= self.offset_until):
            if ARDUINO.halt():
                self._schedule_action_complete(now)
            else:
                self.last_msg = "Action duration finished -- retrying lowercase s."
        elif self.offset_phase == "wait_complete" and now >= self.offset_until:
            self._complete_offset_action("Automatic action complete.")
        if (self.auto_grip_phase == self.AUTO_GRIP_DOWN
                and now - self.auto_grip_started_at >= AUTO_GRIP_DOWN_MAX_S):
            ARDUINO.halt()
            self.auto_grip_phase = self.AUTO_GRIP_IDLE
            self.auto_grip_down_duration = 0.0
            self._abort_offset_action(
                f"Automatic pickup failed: no contact signal in "
                f"{AUTO_GRIP_DOWN_MAX_S:g}s -- sent s.")
            return
        if (self.auto_grip_phase == self.AUTO_GRIP_WAIT_DOWN
                and now >= self.auto_grip_up_until):
            if ARDUINO.send_command(HEIGHT_DOWN_CMD):
                self.auto_grip_phase = self.AUTO_GRIP_DOWN
                self.auto_grip_started_at = now
                self.last_msg = "Automatic gripping: sent hd; waiting for s/S."
            return
        if (self.auto_grip_phase == self.AUTO_GRIP_WAIT_GRIP
                and now >= self.auto_grip_up_until):
            if ARDUINO.send_command("hx"):
                self.auto_grip_phase = self.AUTO_GRIP_HX
                self.auto_grip_up_until = now + AUTO_PICKUP_HX_S
                self.last_msg = f"Sensor S received -- hx for {AUTO_PICKUP_HX_S:g}s."
            return
        if (self.auto_grip_phase == self.AUTO_GRIP_HX
                and now >= self.auto_grip_up_until):
            if ARDUINO.halt():
                self.auto_grip_phase = self.AUTO_GRIP_WAIT_G90
                self.auto_grip_up_until = now + AUTO_GRIP_COMMAND_DELAY_S
                self.last_msg = "hx complete -- g90 in 1.0s."
            else:
                self.last_msg = "hx complete -- retrying lowercase s."
            return
        if (self.auto_grip_phase == self.AUTO_GRIP_WAIT_G90
                and now >= self.auto_grip_up_until):
            if ARDUINO.send_command(grip_command(GRIP_MAX_DEG)):
                self.grip = GRIP_MAX_DEG
                self.auto_grip_phase = self.AUTO_GRIP_WAIT_HU
                self.auto_grip_up_until = now + AUTO_GRIP_COMMAND_DELAY_S
                self.last_msg = "Sent g90 -- hu in 1.0s."
            return
        if (self.auto_grip_phase == self.AUTO_GRIP_WAIT_HU
                and now >= self.auto_grip_up_until):
            if ARDUINO.send_command(HEIGHT_UP_CMD):
                self.auto_grip_phase = self.AUTO_GRIP_UP
                self.auto_grip_up_until = now + self.auto_grip_down_duration
                self.last_msg = (f"Automatic gripping: sent hu for "
                                 f"{self.auto_grip_down_duration:.1f}s.")
            return
        if (self.auto_grip_phase == self.AUTO_GRIP_UP
                and now >= self.auto_grip_up_until):
            if ARDUINO.halt():
                self.auto_grip_phase = self.AUTO_GRIP_IDLE
                if self.offset_phase == "wait_pickup":
                    self._schedule_action_complete(now)
                else:
                    self.last_msg = "Automatic gripping complete -- sent s."
            else:
                self.last_msg = "Raise duration finished -- retrying lowercase s."
            return

    def _stop_jog(self) -> str:
        """The d-pad's centre button: send 's' right now, unconditionally.

        Unlike the arrows, this does not check self.jog_dir first -- the
        whole point of a STOP button is that it is trusted even if this
        panel's own idea of what is moving turns out to be wrong (a jog
        started, the pulse's timer got wedged, the operator just wants the
        board stopped NOW). jog_dir is cleared regardless of whether the
        write succeeds, so the UI never shows a pulse "in progress" after
        the operator has explicitly asked for it to stop.
        """
        self.jog_dir = None
        if not ARDUINO.connected:
            return "Not connected -- nothing to stop."
        if ARDUINO.halt():
            return "Stopped -- sent s."
        return "Could not send s -- the board may still be booting."

    def _start_auto_pulse(self, cmd: str, label: str) -> str:
        """Run a lowercase HU/HX pulse for exactly 0.1s, then stop."""
        if not ARDUINO.connected:
            return "Not connected -- nothing sent."
        if self.auto_pulse_kind is not None:
            ARDUINO.halt()
        cmd = cmd.lower()
        if not ARDUINO.send_command(cmd):
            return f"Could not send {cmd} -- the board may still be booting."
        self.auto_pulse_kind = label
        self.auto_pulse_until = time.monotonic() + AUTO_PULSE_S
        return f"Sent {cmd} for {AUTO_PULSE_S:g}s; then s."

    def _start_offset_action(self, action: str, *, immediate=False) -> str:
        """Run horizontal/vertical offsets once, then the gripper action.

        A press is accepted even while the board is reconnecting. The phase
        machine retries the first write, so a short reset or boot interval can
        no longer make an apparently clickable button silently do nothing.

        `immediate` is kept only so existing callers (Simple Gripper's DONE)
        do not need to change; it no longer skips the wait. DONE used to
        fire the first command in this same call, the one gap-free step in
        an otherwise all-one-second sequence -- inconsistent for no reason
        an operator watching the card could tell. Every trigger now waits
        the same AUTO_ACTION_GAP_S before its first command.
        """
        if action not in ("pickup", "keep", "press", "release"):
            return f"Unknown automatic action: {action}."
        if self.offset_phase != "idle":
            self.pending_auto_actions.append(action)
            return (f"Automatic {action} queued -- it will run after the "
                    f"current {self.offset_action} finishes.")
        self.offset_action = action
        self.offset_failed = False
        self.offset_deadline = time.monotonic() + AUTO_ACTION_MAX_S
        if GRIPPER_NUDGE_ACTIONS.get(action) and GRIPPER_NUDGE_S > 0:
            letter = DIRECTION_LETTERS[GRIPPER_NUDGE_DIRECTION] + SLOW_SUFFIX
            if ARDUINO.send_command(letter):
                self.offset_phase = "nudge"
                self.offset_until = time.monotonic() + GRIPPER_NUDGE_S
                return (f"Automatic {action}: nudging "
                        f"{GRIPPER_NUDGE_DIRECTION} for {GRIPPER_NUDGE_S:g}s.")
        self.offset_phase = "wait_action"
        self.offset_until = time.monotonic() + AUTO_ACTION_GAP_S
        return f"Automatic {action} in {AUTO_ACTION_GAP_S:.1f}s."

    def _execute_offset_action(self, action: str):
        now = time.monotonic()
        if action == "pickup":
            self.last_msg = self._start_auto_grip()
            if self.auto_grip_phase != self.AUTO_GRIP_IDLE:
                self.offset_phase = "wait_pickup"
        elif action == "keep":
            if ARDUINO.send_command("g0"):
                self.grip = 0.0
                self._grip_sent = "g0"
                self.last_msg = "Automatic keep: sent g0."
                self._schedule_action_complete(now)
            else:
                self.last_msg = "Automatic keep ready -- waiting to send g0."
        elif action == "press":
            if ARDUINO.send_command("hx"):
                self.auto_press_started_at = now
                self.offset_phase = "press_down"
                self.last_msg = ("Automatic press: sent hx; waiting for the "
                                 "limit switch s/S.")
            else:
                self.last_msg = "Automatic press ready -- waiting to send hx."
        elif action == "release":
            lift = self.auto_press_duration or AUTO_RELEASE_DURATION_S
            if ARDUINO.send_command("hu"):
                self.auto_press_duration = 0.0
                self.offset_phase = "wait_release"
                self.offset_until = now + lift
                self.last_msg = (f"Automatic release: hu for {lift:.1f}s.")
            else:
                self.last_msg = "Automatic release ready -- waiting to send hu."

    def _schedule_action_complete(self, now=None):
        """Hold for one second after the action."""
        self.offset_phase = "wait_complete"
        self.offset_until = (time.monotonic() if now is None else now) + AUTO_ACTION_GAP_S
        self.last_msg = "Action complete -- waiting 1.0s."

    def abort_automatic_action(self, message=None) -> str:
        """Stop an automatic action dead, from outside this card.

        This is what the Simple Gripper card's STOP is wired to. It halts
        first and unwinds second -- whatever phase is running may well have
        an axis moving -- and it clears the queue too, so a stop does not
        merely pause before the next queued action starts on its own.
        """
        if not self.automatic_busy():
            return "No automatic action is running."
        ARDUINO.halt()
        self.auto_grip_phase = self.AUTO_GRIP_IDLE
        self.auto_grip_down_duration = 0.0
        self.pending_auto_actions = []
        action = self.offset_action or "action"
        self._abort_offset_action(
            message or f"Automatic {action} stopped -- sent s.")
        return self.last_msg

    def _abort_offset_action(self, message):
        """End the action without pretending it worked.

        Same teardown as a success -- the phase returns to idle and any
        queued action still runs -- but the card keeps the failure on it
        rather than being overwritten with "complete", which is the one
        thing that would let a pickup that gripped nothing look fine.
        """
        self.offset_failed = True
        self._complete_offset_action(message)

    def _complete_offset_action(self, message="Automatic action complete."):
        self.offset_deadline = 0.0
        self.offset_phase = "idle"
        self.offset_action = ""
        self.last_msg = message
        if self.pending_auto_actions:
            next_action = self.pending_auto_actions.pop(0)
            self.last_msg = self._start_offset_action(next_action)

    def _start_auto_grip(self) -> str:
        """Schedule HD, grip, HU, and stop with one-second command gaps."""
        if self.auto_grip_phase != self.AUTO_GRIP_IDLE:
            return "Automatic gripping is already running."
        if not ARDUINO.send_command(HEIGHT_DOWN_CMD):
            self.auto_grip_phase = self.AUTO_GRIP_WAIT_DOWN
            self.auto_grip_up_until = time.monotonic()
            return "Automatic pickup accepted -- waiting to send hd."
        self.auto_grip_phase = self.AUTO_GRIP_DOWN
        self.auto_grip_started_at = time.monotonic()
        return "Automatic gripping: sent hd; waiting for s/S."

    def note_rx(self, data) -> bool:
        """Handle a contact packet: the IR sensor during an automatic
        pickup's descent, and the limit switch during an automatic press.

        Both are the board reporting that it has ALREADY stopped, so
        neither path sends an s of its own -- an s here would be a stop
        with nothing left to stop.
        """
        if not has_serial_stop_signal(data):
            return False
        if self.offset_phase == "press_down":
            return self._note_press_limit_switch()
        if self.auto_grip_phase != self.AUTO_GRIP_DOWN:
            return False
        now = time.monotonic()
        self.auto_grip_down_duration = max(0.0, now - self.auto_grip_started_at)
        self.auto_grip_phase = self.AUTO_GRIP_WAIT_GRIP
        self.auto_grip_up_until = now + AUTO_GRIP_COMMAND_DELAY_S
        self.last_msg = (f"IR sensor tripped after "
                         f"{self.auto_grip_down_duration:.1f}s -- hx in "
                         f"{AUTO_GRIP_COMMAND_DELAY_S:.1f}s.")
        return True

    def _note_press_limit_switch(self) -> bool:
        """The press's hx reached the switch: back off by AUTO_PRESS_BACKOFF_S.

        What a later release has to undo is the descent MINUS that back-off,
        since the back-off has already given part of it back -- the same
        arithmetic the pickup's lift does, where hu runs for the hd descent
        plus the hx that followed it.
        """
        now = time.monotonic()
        descent = max(0.0, now - self.auto_press_started_at)
        self.auto_press_duration = max(0.0, descent - AUTO_PRESS_BACKOFF_S)
        if ARDUINO.send_command(HEIGHT_UP_CMD):
            self.offset_phase = "press_lift"
            self.offset_until = now + AUTO_PRESS_BACKOFF_S
            self.last_msg = (f"Limit switch after {descent:.1f}s -- hu for "
                             f"{AUTO_PRESS_BACKOFF_S:.1f}s.")
        else:
            self.offset_phase = "press_lift_pending"
            self.last_msg = ("Limit switch tripped -- waiting to send hu.")
        return True

    def status_line(self) -> str:
        sent = grip_command(self.grip)
        if not ARDUINO.connected:
            tail = f"{sent} not sent -- no serial connection"
        else:
            tail = f"sent {sent}"
        height_bit = (f"last height command {self._last_height_cmd}"
                     if self._last_height_cmd else "height not moved yet")
        return f"Gripper: grip {self.grip:.0f} -- {tail}; {height_bit}."

    def automation_status(self) -> str:
        """Live, rendered proof of the current phase and remaining wait."""
        now = time.monotonic()
        remaining = max(0.0, self.offset_until - now)
        grip_remaining = max(0.0, self.auto_grip_up_until - now)
        if self.auto_grip_phase == self.AUTO_GRIP_WAIT_DOWN:
            message = "Pickup: waiting to send hd"
        elif self.auto_grip_phase == self.AUTO_GRIP_DOWN:
            message = "Pickup: hd sent; waiting for sensor s"
        elif self.auto_grip_phase == self.AUTO_GRIP_WAIT_GRIP:
            message = f"Pickup: waiting {grip_remaining:.1f}s before hx"
        elif self.auto_grip_phase == self.AUTO_GRIP_HX:
            message = f"Pickup: hx has {grip_remaining:.1f}s remaining"
        elif self.auto_grip_phase == self.AUTO_GRIP_WAIT_G90:
            message = f"Pickup: waiting {grip_remaining:.1f}s before g90"
        elif self.auto_grip_phase == self.AUTO_GRIP_WAIT_HU:
            message = f"Pickup: waiting {grip_remaining:.1f}s before hu"
        elif self.auto_grip_phase == self.AUTO_GRIP_UP:
            message = f"Pickup: hu has {grip_remaining:.1f}s remaining"
        elif self.offset_phase == "nudge":
            message = (f"Nudging {GRIPPER_NUDGE_DIRECTION} -- "
                      f"{remaining:.1f}s before {self.offset_action}")
        elif self.offset_phase == "action":
            message = self.last_msg
        elif self.offset_phase == "wait_action":
            message = f"Waiting {remaining:.1f}s before {self.offset_action}"
        elif self.offset_phase == "press_down":
            message = "Press: hx sent; waiting for the limit switch s"
        elif self.offset_phase == "press_lift_pending":
            message = "Press: limit switch tripped; waiting to send hu"
        elif self.offset_phase in ("press_lift", "wait_release"):
            message = f"{self.offset_action.title()}: {remaining:.1f}s remaining"
        elif self.offset_phase == "wait_complete":
            message = f"Waiting {remaining:.1f}s after {self.offset_action}"
        else:
            message = self.last_msg or "Ready."
        if self.pending_auto_actions:
            message += f" | queued: {len(self.pending_auto_actions)}"
        return message

    def _rect_contains(self, x, y):
        if not self._last_rect:
            return False
        px, py, pw, ph = self._last_rect
        return px <= x <= px + pw and py <= y <= py + ph

    def press(self, x, y):
        """A click. Returns a status line, "" for a click on the card that
        did nothing, or None when the click was not the card's at all --
        the same three-way contract the other panels' hit_test uses, so the
        dispatcher in on_mouse treats it identically."""
        if not self.visible:
            return None
        for sl in self.sliders:
            if sl.contains(x, y):
                self.dragging = sl.kind
                self.set_value(sl.kind, sl.value_at(x))
                return self.status_line()
        for b in self.buttons:
            if b.contains(x, y):
                if b.kind == "grip_close":
                    self.close()
                    return "Gripper closed."
                if b.kind == "grip_close_top":
                    self.close()
                    return "Gripper closed."
                if b.kind == "grip_height":
                    self.last_msg = self._height_step(up=b.value)
                    return self.last_msg
                if b.kind == "grip_hx":
                    self.last_msg = self._send_height_command("hx", "press")
                    return self.last_msg
                if b.kind == "grip_pulse":
                    self.last_msg = self._start_auto_pulse(b.value, b.value)
                    return self.last_msg
                if b.kind == "grip_auto":
                    self.last_msg = self._start_offset_action("pickup")
                    return self.last_msg
                if b.kind == "grip_auto_keep":
                    self.last_msg = self._start_offset_action("keep")
                    return self.last_msg
                if b.kind == "grip_auto_press":
                    self.last_msg = self._start_offset_action("press")
                    return self.last_msg
                if b.kind == "grip_auto_release":
                    self.last_msg = self._start_offset_action("release")
                    return self.last_msg
                if b.kind == "grip_jog":
                    self.last_msg = self._start_jog(b.value)
                    return self.last_msg
                if b.kind == "grip_stop":
                    self.last_msg = self._stop_jog()
                    return self.last_msg
                if b.kind == "grip_done":
                    self.confirm()
                    self.last_msg = "Step confirmed -- carrying on."
                    return self.last_msg
                return ""
        if self._rect_contains(x, y):
            return ""
        return None

    def drag(self, x, y):
        """Mouse moved with the button down. Tracks the held slider even
        once the pointer has left it -- releasing the moment the cursor
        strays off a 6px track is what makes a slider feel broken."""
        if not self.visible or self.dragging is None:
            return None
        sl = self.slider(self.dragging)
        if sl is None:
            self.dragging = None
            return None
        self.set_value(sl.kind, sl.value_at(x))
        return self.status_line()

    def draw_lists(self, frame, mouse=(-1, -1)):
        if not self.visible:
            return
        return

    def release(self):
        """True when this ended a drag, so the caller knows the mouse-up was
        ours and can stop before the corner-drag handling below it.

        The throttle in _send_grip can swallow the last move of a drag, which
        is the one that matters -- so the final angle is forced out here.
        """
        was, self.dragging = self.dragging, None
        if was == "grip_grip":
            self._send_grip(final=True)
        return was is not None

    MIN_SCALE = 0.55

    def _natural_height(self, pw):
        """The card's height at full size (scale 1), before it is shrunk to
        fit a short video frame. Used only to work out how much to shrink
        by -- see the scale factor `k` in draw()."""
        row_h = self.ROW_H
        note_lines = wrap_text(self.NOTE, pw - 56, self.NOTE_SCALE)
        note_h = len(note_lines) * self.NOTE_LINE_H + 10
        jog_h = 26 + 3 * self.JOG_BTN + 2 * self.JOG_GAP
        instr_lines = (wrap_text(self.instruction, pw - 56, self.INSTR_SCALE)
                      if self.instruction else [])
        instr_h = (len(instr_lines) * self.INSTR_LINE_H + 16
                  if instr_lines else 0)
        done_h = row_h + 10 if self.awaiting_confirm else 0
        return (self.PAD * 2 + 44 + instr_h + 78 + 26 + row_h + row_h + 10
             + jog_h + 30
               + note_h + 26 + done_h + row_h)

    def draw(self, frame, mouse=(-1, -1)):
        self._anim = ease_toward(self._anim, 1.0 if self.visible else 0.0,
                                 ANIM_RATE)
        if self._anim < 0.004:
            return
        fh, fw = frame.shape[:2]
        pw = min(self.WIDTH, fw - 2 * self.PAD)

        natural_ph = self._natural_height(pw)
        avail_h = max(1, fh - 2 * self.PAD)
        k = 1.0 if natural_ph <= avail_h else max(self.MIN_SCALE,
                                                   avail_h / natural_ph)

        def S(v):
            return v * k

        row_h = S(self.ROW_H)
        note_scale = self.NOTE_SCALE * k
        instr_scale = self.INSTR_SCALE * k
        note_lines = wrap_text(self.NOTE, pw - 56, note_scale)
        note_line_h = S(self.NOTE_LINE_H)
        note_h = len(note_lines) * note_line_h + S(10)
        jog_btn = max(1, int(round(S(self.JOG_BTN))))
        jog_gap = max(12, int(round(S(self.JOG_GAP))))
        jog_h = S(26) + 3 * jog_btn + 2 * jog_gap
        instr_lines = (wrap_text(self.instruction, pw - 56, instr_scale)
                      if self.instruction else [])
        instr_line_h = S(self.INSTR_LINE_H)
        instr_h = (len(instr_lines) * instr_line_h + S(16)
                  if instr_lines else 0)
        done_h = row_h + S(10)
        ph = int(round(
            self.PAD * 2 + S(44) + instr_h + S(78) + S(26) + row_h
            + row_h + S(20) + jog_h
            + S(30) + note_h + S(26) + done_h + row_h))
        px = max(0, (fw - pw) // 2)
        py = max(0, (fh - ph) // 2)
        self._last_rect = (px, py, pw, ph)
        rect = (px, py, px + pw, py + ph)

        margin = 40
        bx0, by0 = max(0, px - margin), max(0, py - margin)
        bx1, by1 = min(fw, px + pw + margin), min(fh, py + ph + margin)
        fading = self._anim < 0.999
        under = frame[by0:by1, bx0:bx1].copy() if fading else None

        glass_card(frame, rect, 28, alpha=0.62)
        draw_text(frame, "Gripper", (px + 28, py + int(S(44))), 0.9 * k,
                  C_TEXT, 2)
        mx, my = mouse
        self.buttons = []
        close_top = Button("X", px + pw - int(S(66)), py + int(S(18)),
                           px + pw - int(S(20)), py + int(S(58)),
                           "grip_close_top", style="primary", scale=0.52 * k)
        close_top.draw(frame, hover=close_top.contains(mx, my), shadow=False)
        self.buttons.append(close_top)
        auto_label = "PLAN AUTO: ON" if not MANUAL_GRIPPER_STEPS else "PLAN AUTO: OFF"
        auto_scale = 0.4 * k
        auto_col = C_GREEN if not MANUAL_GRIPPER_STEPS else C_TEXT_DIM
        aw, _ = text_size(auto_label, auto_scale, 1)
        draw_text(frame, auto_label, (px + pw - 28 - aw, py + int(S(40))),
                  auto_scale, auto_col, 1)

        y = py + S(72)

        if instr_lines:
            for line in instr_lines:
                draw_text(frame, line, (px + 28, int(y + S(16))), instr_scale,
                          C_ACCENT, 2)
                y += instr_line_h
            y += S(16)

        for sl in self.sliders:
            value = self.value_of(sl.kind)
            fscale = 0.6 * k
            draw_text(frame, sl.label, (px + 28, int(y + S(18))), fscale,
                      C_TEXT, 1)
            vtext = sl.text(value)
            vw, _ = text_size(vtext, fscale, 2)
            draw_text(frame, vtext, (px + pw - 28 - vw, int(y + S(18))),
                      fscale, C_ACCENT, 2)
            sl.set_rect(px + 28, int(y + S(40)), px + pw - 28, int(y + S(54)))
            sl.draw(frame, value,
                    hover=sl.contains(mx, my),
                    active=self.dragging == sl.kind)
            y += S(78)

        fscale = 0.6 * k
        draw_text(frame, "Height", (px + 28, int(y + S(18))), fscale,
                  C_TEXT, 1)
        hlabel = (self._last_height_cmd if self._last_height_cmd
                 else "not moved")
        hscale = 0.5 * k
        hw, _ = text_size(hlabel, hscale, 2)
        draw_text(frame, hlabel, (px + pw - 28 - hw, int(y + S(18))),
                  hscale, C_ACCENT, 2)
        y += S(26)
        gap = max(12, S(12))
        third = int((pw - 28 - 28 - 2 * gap) // 3)
        y0, y1 = int(y), int(y + row_h - S(8))
        down_btn = Button("DOWN (hd)", px + 28, y0, px + 28 + third, y1,
                          "grip_height", value=False, scale=0.52 * k)
        up_x0 = int(px + 28 + third + gap)
        up_btn = Button("UP (hu)", up_x0, y0, up_x0 + third, y1,
                "grip_height", value=True,
                        scale=0.52 * k)
        hx_x0 = int(up_x0 + third + gap)
        hx_btn = Button("HX", hx_x0, y0, px + pw - 28, y1,
                "grip_hx", style="accent", scale=0.52 * k)
        down_btn.draw(frame, hover=down_btn.contains(mx, my), shadow=False)
        up_btn.draw(frame, hover=up_btn.contains(mx, my), shadow=False)
        hx_btn.draw(frame, hover=hx_btn.contains(mx, my), shadow=False)
        self.buttons.extend([down_btn, up_btn, hx_btn])
        y += row_h + S(10)

        pulse_gap = max(12, S(12))
        half = int((pw - 56 - pulse_gap) // 2)
        hu_pulse = Button("HU 0.1s", px + 28, int(y),
                          px + 28 + half, int(y + row_h - S(8)),
                          "grip_pulse", value="hu", scale=0.5 * k)
        hx_pulse = Button("HX 0.1s", int(px + 28 + half + pulse_gap), int(y),
                          px + pw - 28, int(y + row_h - S(8)),
                          "grip_pulse", value="hx", scale=0.5 * k)
        hu_pulse.draw(frame, hover=hu_pulse.contains(mx, my), shadow=False)
        hx_pulse.draw(frame, hover=hx_pulse.contains(mx, my), shadow=False)
        self.buttons.extend([hu_pulse, hx_pulse])
        y += row_h + S(10)

        auto_gap = max(12, S(12))
        auto_width = int((pw - 56 - 3 * auto_gap) // 4)
        auto_specs = [
            ("PICKUP", "grip_auto", None),
            ("KEEP", "grip_auto_keep", None),
            ("PRESS", "grip_auto_press", None),
            ("RELEASE", "grip_auto_release", None),
        ]
        for i, (label, kind, value) in enumerate(auto_specs):
            x0 = int(px + 28 + i * (auto_width + auto_gap))
            btn = Button(label, x0, int(y), x0 + auto_width,
                         int(y + row_h - S(8)), kind, value=value,
                         style="accent", scale=0.34 * k)
            btn.draw(frame, hover=btn.contains(mx, my), shadow=False)
            self.buttons.append(btn)
        y += row_h + S(10)

        active = self.jog_dir
        jlabel = (f'Jog: sending "{DIRECTION_LETTERS[active]}{SLOW_SUFFIX}", '
                 f"{max(0.0, self.jog_until - time.time()):.1f}s left"
                 if active else "Jog: idle")
        draw_text(frame, jlabel, (px + 28, int(y + S(18))), 0.4 * k,
                  C_TEXT_DIM, 1)
        y += S(26)
        cx = px + pw // 2
        jog_scale = 0.7 * k
        for direction, (row, col) in self.JOG_LAYOUT.items():
            jx0 = int(cx + (col - 1) * (jog_btn + jog_gap) - jog_btn // 2)
            jy0 = int(y + row * (jog_btn + jog_gap))
            btn = Button(self.JOG_ARROWS[direction], jx0, jy0,
                        jx0 + jog_btn, jy0 + jog_btn,
                        "grip_jog", value=direction, scale=jog_scale)
            btn.draw(frame, hover=btn.contains(mx, my),
                    active=active == direction, shadow=False)
            self.buttons.append(btn)
        srow, scol = self.JOG_STOP_ROW_COL
        sx0 = int(cx + (scol - 1) * (jog_btn + jog_gap) - jog_btn // 2)
        sy0 = int(y + srow * (jog_btn + jog_gap))
        stop_btn = Button("X", sx0, sy0, sx0 + jog_btn, sy0 + jog_btn,
                          "grip_stop", style="primary", scale=jog_scale)
        stop_btn.draw(frame, hover=stop_btn.contains(mx, my), shadow=False)
        self.buttons.append(stop_btn)
        y += 3 * jog_btn + 2 * jog_gap + S(12)

        msg_scale = 0.4 * k
        msg_line = fit_text(self.automation_status(), pw - 56, msg_scale)
        draw_text(frame, msg_line, (px + 28, int(y + S(18))), msg_scale,
                  C_TEXT_DIM, 1)
        y += S(28)

        for line in note_lines:
            draw_text(frame, line, (px + 28, int(y + S(14))), note_scale,
                      C_RED, 1)
            y += note_line_h
        y += S(12)

        sending = f'Grip sends "{grip_command(self.grip)}".'
        draw_text(frame, sending, (px + 28, int(y + S(12))), 0.4 * k,
                  C_TEXT_DIM, 1)
        y += S(26)

        y0, y1 = int(y + S(6)), int(y + row_h - S(8))
        done = Button("DONE", px + 28, y0, px + pw - 28, y1,
                      "grip_done", style="accent", scale=0.56 * k)
        done.draw(frame, hover=done.contains(mx, my), shadow=False)
        self.buttons.append(done)
        y += row_h + S(10)

        y0, y1 = int(y + S(6)), int(y + row_h - S(8))
        close = Button("CLOSE", px + 28, y0, px + pw - 28, y1,
                       "grip_close", scale=0.56 * k)
        close.draw(frame, hover=close.contains(mx, my), shadow=False)
        self.buttons.append(close)

        if fading:
            drawn = frame[by0:by1, bx0:bx1]
            frame[by0:by1, bx0:bx1] = cv2.addWeighted(
                drawn, self._anim, under, 1.0 - self._anim, 0)


OPENAI_API_KEY = "ADD YOUR OPENAI API KEY HERE"

NAMER_MODELS = ("gpt-5.4-mini", "gpt-5.4")
NAMER_MODEL = NAMER_MODELS[0]
PLANNER_MODEL = "gpt-5.6-terra"
# Error Rebounds: the cheapest model that reads photos well (gpt-6-luna,
# $0.10 / $0.50 per 1M tokens), thinking as little as still reasons --
# every checked step waits on it. ERR_MAX_TOKENS covers that reasoning too.
ERR_MODEL = "gpt-6-luna"
ERR_REASONING = "low"
ERR_MAX_TOKENS = 2500

STT_MODEL = "gpt-4o-transcribe"
STT_FALLBACK_MODEL = "whisper-1"
STT_SAMPLE_RATE = 16000
STT_TIMEOUT_S = 60.0
STT_MIN_SPEECH_S = 0.35
STT_MAX_SECONDS = 120.0

API_TIMEOUT_S = 90.0
API_RETRIES = 3
API_BACKOFF_S = 1.6

AUTO_EXECUTE_DELAY = 3.0
HOLD_SECONDS = 1.0


def resolve_api_key() -> str:
    """The API key, environment first.

    The environment is checked BEFORE the literal at the top of this file so
    a key can be rotated without editing source -- and, more to the point,
    so the literal can be emptied out without the app losing its key. A key
    written into a file that lives in a git repository is a published key:
    anyone who ever gets a copy of S1.py has it, and it stays valid until
    somebody notices. Export OPENAI_API_KEY and blank the constant.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    if OPENAI_API_KEY.strip():
        return OPENAI_API_KEY.strip()
    return str(S1_EMBEDDED_STATE.get("api_key", "")).strip()


class ModelError(RuntimeError):
    """Carries a message already phrased for the operator."""


def make_client():
    key = resolve_api_key()
    if not key:
        raise ModelError("No API key. Put one in OPENAI_API_KEY at the top of "
                         "S1.py or in the environment.")
    if OpenAI is None:
        raise ModelError("The 'openai' package is not installed "
                         "(pip install openai).")
    return OpenAI(api_key=key, timeout=API_TIMEOUT_S, max_retries=0)


def _wav_bytes(samples, rate: int) -> bytes:
    """A 16-bit mono WAV file, in memory.

    `samples` is float32 in [-1, 1] (what the capture callback delivers) or
    already-int16. Written with the stdlib `wave` module so the recorder
    needs no encoder: soundfile/ffmpeg are not installed here, and the
    transcription endpoint rejects raw PCM and AIFF alike -- it wants a
    container it can sniff, and WAV is the one every speech model accepts.
    """
    arr = np.asarray(samples)
    if arr.dtype != np.int16:
        arr = np.clip(np.asarray(arr, dtype=np.float32), -1.0, 1.0)
        arr = (arr * 32767.0).astype(np.int16)
    arr = arr.reshape(-1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(arr.tobytes())
    return buf.getvalue()


def _resample_linear(samples, src_rate: int, dst_rate: int):
    """Linear resample. Only ever used when the microphone refuses the rate
    we asked for -- no SciPy here, and for speech going DOWN in rate the
    difference between this and a windowed filter is inaudible to a model
    that was trained on telephone audio."""
    src_rate, dst_rate = int(src_rate), int(dst_rate)
    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    if src_rate == dst_rate or arr.size == 0:
        return arr
    n_out = int(round(arr.size * dst_rate / float(src_rate)))
    if n_out <= 1:
        return arr[:1].copy()
    idx = np.linspace(0.0, arr.size - 1, n_out, dtype=np.float32)
    return np.interp(idx, np.arange(arr.size, dtype=np.float32), arr
                     ).astype(np.float32)


def _speech_seconds(samples, rate: int) -> float:
    """Roughly how much of this clip is speech rather than room tone.

    Frames are 30ms; a frame counts as speech when its RMS sits well above
    the clip's own noise floor, so a quiet room and a noisy workshop are
    judged on the same terms instead of against a fixed threshold. This
    exists to catch the two cases that would otherwise reach the user as a
    bad transcript: a tap that recorded nothing, and the confident
    hallucination ("Thank you.", "Bye.") these models emit for silence.
    """
    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return 0.0
    win = max(1, int(rate * 0.03))
    n = arr.size // win
    if n == 0:
        return 0.0
    frames = arr[:n * win].reshape(n, win)
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    floor = float(np.percentile(rms, 20))
    thresh = max(floor * 3.0, 0.006)
    return float(np.count_nonzero(rms > thresh) * win) / float(rate)


class MicRecorder:
    """The microphone behind the voice button: start, stop, get a WAV.

    Capture runs in sounddevice's own callback thread and appends blocks to
    a list under a lock; `stop()` concatenates them. Nothing here touches
    the UI, and the UI never blocks on the device -- `start()` reports a
    string on failure instead of raising, because a missing microphone or a
    denied permission prompt must not take the app down mid-session.

    The device is opened at STT_SAMPLE_RATE when it will accept it. Macs
    generally run the internal microphone at 48 kHz, so CAPTURE_RATE falls
    back to the device default and `stop()` resamples once at the end --
    resampling a finished clip is cheaper and cleaner than doing it per
    block in the callback.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._blocks = []
        self._stream = None
        self.rate = STT_SAMPLE_RATE
        self.started_at = 0.0
        self.level = 0.0
        self.overflows = 0

    @property
    def active(self) -> bool:
        return self._stream is not None

    def elapsed(self) -> float:
        return (time.time() - self.started_at) if self.active else 0.0

    def _callback(self, indata, frames, time_info, status):
        if status and getattr(status, "input_overflow", False):
            self.overflows += 1
        block = np.asarray(indata, dtype=np.float32).reshape(-1).copy()
        peak = float(np.max(np.abs(block))) if block.size else 0.0
        with self._lock:
            self._blocks.append(block)
            self.level = max(peak, self.level * 0.82)

    def start(self) -> str:
        """Open the microphone. Returns "" on success, else why not."""
        if self.active:
            return ""
        if sd is None:
            return ("Voice needs the 'sounddevice' package "
                    "(pip install sounddevice).")
        with self._lock:
            self._blocks = []
            self.level = 0.0
        self.overflows = 0
        for rate in (STT_SAMPLE_RATE, None):
            try:
                if rate is None:
                    dev = sd.query_devices(kind="input")
                    rate = int(dev.get("default_samplerate") or 48000)
                stream = sd.InputStream(samplerate=int(rate), channels=1,
                                        dtype="float32",
                                        callback=self._callback)
                stream.start()
            except Exception as e:
                last = e
                continue
            self._stream = stream
            self.rate = int(rate)
            self.started_at = time.time()
            return ""
        msg = str(last) if "last" in dir() else "unknown error"
        if "permission" in msg.lower() or "denied" in msg.lower():
            return ("The microphone is blocked. Allow it in System Settings "
                    "> Privacy & Security > Microphone.")
        return f"Could not open the microphone: {msg}"

    def stop(self):
        """Close the device and return (float32 samples at STT_SAMPLE_RATE,
        rate). Returns (empty, rate) when nothing was captured."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            blocks, self._blocks = self._blocks, []
            self.level = 0.0
        if not blocks:
            return np.zeros(0, dtype=np.float32), STT_SAMPLE_RATE
        audio = np.concatenate(blocks)
        if self.rate != STT_SAMPLE_RATE:
            audio = _resample_linear(audio, self.rate, STT_SAMPLE_RATE)
        return audio, STT_SAMPLE_RATE

    def cancel(self):
        """Throw the take away without transcribing it."""
        self.stop()


MIC = MicRecorder()


class TranscribeJob:
    """One clip -> one string, on a worker thread.

    Mirrors the other jobs in this file (lock, `stage`, `done`, a daemon
    thread, `snapshot()`) so the sidebar polls it the same way it polls the
    planner. `cancelled` makes a late reply a no-op: the user may have
    started typing, and a transcript must never overwrite what they wrote
    after letting go of the button.

    STT_MODEL is tried first and whisper-1 is the fallback, because a model
    that is unavailable on a given key should degrade to a working one
    rather than to an error message.
    """

    def __init__(self, samples, rate: int):
        self.samples = samples
        self.rate = int(rate)
        self._lock = threading.Lock()
        self.stage = "Transcribing..."
        self.text = ""
        self.error = ""
        self.done = False
        self.cancelled = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def snapshot(self):
        with self._lock:
            return self.stage, self.done

    def cancel(self):
        self.cancelled = True

    def _run(self):
        try:
            speech = _speech_seconds(self.samples, self.rate)
            if speech < STT_MIN_SPEECH_S:
                raise ModelError("I did not hear anything -- hold the "
                                 "microphone button while you speak.")
            wav = _wav_bytes(self.samples, self.rate)
            client = make_client()
            last = None
            for model in (STT_MODEL, STT_FALLBACK_MODEL):
                try:
                    self.text = self._transcribe(client, model, wav)
                    return
                except ModelError:
                    raise
                except Exception as e:
                    last = e
            raise ModelError(f"Transcription failed: {last}")
        except ModelError as e:
            self.error = str(e)
        except Exception as e:
            self.error = f"Transcription failed: {e}"
        finally:
            with self._lock:
                self.done = True

    def _transcribe(self, client, model: str, wav: bytes) -> str:
        fh = ("speech.wav", io.BytesIO(wav), "audio/wav")
        kwargs = dict(model=model, file=fh,
                      timeout=STT_TIMEOUT_S)
        kwargs["prompt"] = STT_PROMPT
        resp = client.audio.transcriptions.create(**kwargs)
        text = (getattr(resp, "text", "") or "").strip()
        return clean_transcript(text)


STT_PROMPT = ("Commands for a robotic gantry over a lettered-and-numbered "
              "board. Cells are written like A1, B3, D7. Vocabulary: gantry, "
              "gripper, AprilTag, cell, column, row, pick up, put down, "
              "sweep, broom, dustpan, fold, mop, tidy, execute, stop.")

_STT_FILLER = re.compile(r"^(?:\s*(?:um+|uh+|er+|hmm+|mm+)\b[,.]?\s*)+",
                         re.IGNORECASE)


def clean_transcript(text: str) -> str:
    """Tidy a raw transcript into something worth putting in the prompt box.

    Leading filler goes, whitespace collapses, and the single trailing full
    stop these models add to every utterance is dropped -- the prompt box is
    a command line, not prose, and "Move to B3." reads as a typo there.
    Question and exclamation marks stay: they carry meaning the planner uses.
    """
    if not text:
        return ""
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = _STT_FILLER.sub("", text)
    if text.endswith(".") and not text.endswith(".."):
        text = text[:-1]
    return text.strip()


def merge_transcript(current: str, text: str, at: int):
    """Splice a transcript into the prompt box at `at`.

    Returns (new_text, new_caret). Insertion rather than replacement so
    dictating into a half-typed sentence does the obvious thing, and so
    anything typed while the model was working survives. A space is added
    on whichever side needs one -- without it, dictation appended to
    existing text welds itself onto the last word ("moveto B3").
    """
    at = max(0, min(int(at), len(current)))
    before, after = current[:at], current[at:]
    if before and not before.endswith((" ", "\n")):
        text = " " + text
    if after and not after.startswith((" ", "\n")):
        text = text + " "
    merged = (before + text + after)[:MAX_CHAT_CHARS]
    return merged, min(len(before) + len(text), len(merged))


def _finish_reason(resp) -> str:
    """The reply's finish_reason, or "" when the shape is unfamiliar.

    Deliberately forgiving: a stub client in the tests, or an SDK that
    names this differently, must not turn into an exception on the one
    path every model call goes through.
    """
    try:
        return str(resp.choices[0].finish_reason or "").lower()
    except (AttributeError, IndexError, TypeError):
        return ""


PRIORITY_NAMING = True
_PRIORITY_REFUSED = set()
_REASONING_REFUSED = set()      # (model, effort) pairs refused this session


def _service_tier_for(model, priority=False):
    """"priority" for a call that asked for it, unless this model has
    already turned the priority tier down once this session."""
    if priority and model not in _PRIORITY_REFUSED:
        return "priority"
    return None


def _log_call(stage, model, resp, seconds, tier, effort=None):
    """One console line per model call: how long it took and what it cost,
    so a slow task shows exactly which call was slow, and whether the
    priority tier was actually used (the reply says which tier served it)."""
    usage = getattr(resp, "usage", None)
    prompt = getattr(usage, "prompt_tokens", None)
    out = getattr(usage, "completion_tokens", None)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None)
    cached = getattr(getattr(usage, "prompt_tokens_details", None),
                     "cached_tokens", None)
    served = getattr(resp, "service_tier", None)
    print(f"[timing] {stage}: {model} took {seconds:.1f} s"
          f" (tokens in {prompt}, cached {cached}, out {out},"
          f" reasoning {reasoning}"
          f"{f' at effort {effort}' if effort else ''};"
          f" tier asked {tier or 'default'}, served {served})", flush=True)


def call_model(client, *, model, messages, max_tokens, stage="request",
               priority=False, reasoning=None):
    """One chat completion with bounded retries and a real error message.

    Same contract as S1-SRC's: a filtered or malformed request fails at
    once, only transport faults are retried. `priority` asks for OpenAI's
    priority processing tier (faster, billed higher); a model that refuses
    it falls back to the standard tier for the rest of the session.
    `reasoning` is the reasoning effort ("none" ... "max"); a model that
    refuses that value is asked again at its own default, and is not sent
    it again this session.
    """
    last = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            kwargs = {}
            tier = _service_tier_for(model, priority)
            if tier:
                kwargs["service_tier"] = tier
            if reasoning and (model, reasoning) not in _REASONING_REFUSED:
                kwargs["reasoning_effort"] = reasoning
            t0 = time.time()
            while True:
                try:
                    resp = client.chat.completions.create(
                        model=model, messages=messages,
                        max_completion_tokens=max_tokens, **kwargs)
                    break
                except TypeError:
                    if not kwargs:
                        raise
                    kwargs, tier = {}, None    # an SDK too old for them
                except Exception as e:
                    low = str(e).lower()
                    if "service_tier" in kwargs and any(w in low for w in (
                            "service_tier", "service tier", "priority")):
                        print(f"[api] priority tier refused for {model} "
                              f"({str(e)[:80]}) - using the standard tier "
                              f"for it from now on")
                        _PRIORITY_REFUSED.add(model)
                        kwargs.pop("service_tier")
                        tier = None
                    elif "reasoning_effort" in kwargs and any(w in low for w in (
                            "reasoning_effort", "reasoning effort",
                            "reasoning.effort")):
                        effort = kwargs.pop("reasoning_effort")
                        print(f"[api] {model} refused reasoning effort "
                              f"{effort!r} ({str(e)[:80]}) - using its default "
                              f"from now on")
                        _REASONING_REFUSED.add((model, effort))
                    else:
                        raise
                    t0 = time.time()
            try:
                _log_call(stage, model, resp, time.time() - t0, tier,
                          kwargs.get("reasoning_effort"))
            except Exception:
                pass
            try:
                text = (resp.choices[0].message.content or "").strip()
            except (AttributeError, IndexError):
                text = ""
            if _finish_reason(resp) == "length":
                raise ModelError(
                    f"{stage}: the model hit its {max_tokens}-token cap "
                    f"before finishing. Raise the cap for this stage.")
            if not text:
                raise ModelError(f"{stage}: the model returned nothing.")
            return text
        except ModelError:
            raise
        except Exception as e:
            last = e
            if attempt < API_RETRIES:
                time.sleep(API_BACKOFF_S * attempt)
                continue
    raise ModelError(f"{stage} failed after {API_RETRIES} attempts "
                     f"({type(last).__name__}: {str(last)[:120]})")


def encode_jpeg_b64(bgr, quality=94):
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return None
    return base64.b64encode(buf.tobytes()).decode()


VISION_AI_DIR = (os.environ.get("S1_VISION_AI_DIR", "").strip()
                 or os.path.join(os.path.dirname(os.path.dirname(SCRIPT_PATH)),
                                 "Vision AI"))
FASTSAM_IMGSZ = 640
FASTSAM_WEIGHTS = os.path.join(VISION_AI_DIR, "FastSAM-s.pt")
FASTSAM_MODEL_PATH = os.path.join(VISION_AI_DIR, ".coreml_cache",
                                  f"FastSAM-s_{FASTSAM_IMGSZ}.mlmodelc")

VISION_CONF = 0.25
VISION_IOU = 0.7
VISION_MAX_AREA = 0.5
VISION_OUTLINE_PX = 2
VISION_MARK_PARTS = True
VISION_SHOW_NAMES = True
VISION_MAX_FPS = 10.0
VISION_FPS_CHOICES = [4.0, 6.0, 8.0, 10.0, 15.0, 30.0]
VISION_SCENE_HINT = (
    "The photo shows the work area of a small gantry robot, so it may hold "
    "parts of the robot itself (aluminium frame rails, lead screws, smooth "
    "rods, stepper motors, belts, pulleys, a gripper, cables) as well as "
    "everyday objects.")
VISION_LIMITS = {"conf_thres": (0.05, 0.95, 0.05),
                 "iou_thres": (0.3, 0.95, 0.05),
                 "max_area": (0.1, 1.0, 0.05),
                 "outline_px": (1, 6, 1)}

REGION_BACKGROUND_SHARE = 0.75
COMPONENT_CONTAINMENT = 0.90
NAMER_MAX_SIDE = 1600
NAMER_MAX_TOKENS = 4000
NAME_FONT = 0.6
TAG_OBJECT_AREA_MULT = 4.0
VISION_READY_WAIT_S = 60.0


def fastsam_letterbox(frame):
    h, w = frame.shape[:2]
    r = min(FASTSAM_IMGSZ / h, FASTSAM_IMGSZ / w)
    nw, nh = round(w * r), round(h * r)
    top = round((FASTSAM_IMGSZ - nh) / 2 - 0.1)
    left = round((FASTSAM_IMGSZ - nw) / 2 - 0.1)
    padded = cv2.copyMakeBorder(
        cv2.resize(frame, (nw, nh)), top, FASTSAM_IMGSZ - nh - top, left,
        FASTSAM_IMGSZ - nw - left, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return cv2.cvtColor(padded, cv2.COLOR_BGR2RGB), r, left, top


def build_fastsam_model():
    """Converts FastSAM to Core ML. Runs once, in its own process
    (`S1.5-SRC.py --build-fastsam`), the first time the model is missing."""
    import ssl

    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    ssl._create_default_https_context = ssl.create_default_context

    import coremltools as ct
    import torch
    from ultralytics import FastSAM

    net = FastSAM(FASTSAM_WEIGHTS).model.eval().float().cpu().fuse()
    for m in net.modules():
        if hasattr(m, "export"):
            m.export = True
        if hasattr(m, "format"):
            m.format = "coreml"

    x = torch.rand(1, 3, FASTSAM_IMGSZ, FASTSAM_IMGSZ)
    with torch.no_grad():
        net(x)
        traced = torch.jit.trace(net, x, strict=False)
    ml = ct.convert(
        traced,
        inputs=[ct.ImageType("image", shape=x.shape, scale=1 / 255, bias=[0, 0, 0])],
        outputs=[ct.TensorType("preds"), ct.TensorType("protos")],
        convert_to="mlprogram",
        compute_precision=ct.precision.FLOAT16,
        minimum_deployment_target=ct.target.macOS13,
        skip_model_load=True,
    )
    os.makedirs(os.path.dirname(FASTSAM_MODEL_PATH), exist_ok=True)
    package = os.path.splitext(FASTSAM_MODEL_PATH)[0] + ".mlpackage"
    ml.save(package)
    ct.utils.compile_model(package, FASTSAM_MODEL_PATH)
    shutil.rmtree(package)
    print(f"Built {FASTSAM_MODEL_PATH}")


class FastSAMSegmenter:
    def __init__(self, conf, iou, max_area):
        import coremltools as ct

        if not os.path.exists(FASTSAM_MODEL_PATH):
            print("Converting FastSAM to Core ML (one time)...")
            subprocess.run([sys.executable, SCRIPT_PATH, FASTSAM_BUILD_FLAG],
                           check=True)
        self.model = ct.models.CompiledMLModel(
            FASTSAM_MODEL_PATH, compute_units=ct.ComputeUnit.CPU_AND_GPU)
        self.conf, self.iou, self.max_area = conf, iou, max_area
        self.outline_letterboxed(np.zeros((FASTSAM_IMGSZ, FASTSAM_IMGSZ, 3), np.uint8),
                                 1.0, 0, 0, FASTSAM_IMGSZ, FASTSAM_IMGSZ)

    def outline_letterboxed(self, rgb, r, left, top, w, h, max_pixels=None,
                            conf=None, iou=None):
        """Returns one list of contours (screen pixels) per object. conf and iou,
        when given, override the starting values (Settings changes them live).
        """
        from PIL import Image

        conf = self.conf if conf is None else conf
        iou = self.iou if iou is None else iou
        out = self.model.predict({"image": Image.fromarray(rgb)})
        preds, protos = out["preds"][0], out["protos"][0]
        keep = preds[4] > conf
        cx, cy, bw, bh = preds[:4, keep]
        xywh = np.stack([cx - bw / 2, cy - bh / 2, bw, bh], 1)
        idx = np.array(cv2.dnn.NMSBoxes(xywh.tolist(), preds[4, keep].tolist(),
                                        conf, iou), dtype=int).flatten()[:300]
        if not len(idx):
            return []

        n_proto, ph, pw = protos.shape
        logits = (preds[5:, keep].T[idx] @ protos.reshape(n_proto, -1)).reshape(
            len(idx), ph, pw).astype(np.float32)
        k = FASTSAM_IMGSZ / pw
        s = r / k
        objects = []
        for m, (x, y, bw_, bh_) in zip(logits, xywh[idx]):
            x1, y1 = max(0, int((x - left) / r)), max(0, int((y - top) / r))
            x2 = min(w, int(np.ceil((x + bw_ - left) / r)))
            y2 = min(h, int(np.ceil((y + bh_ - top) / r)))
            limit = max_pixels if max_pixels is not None else self.max_area * w * h
            if x2 <= x1 or y2 <= y1 or (x2 - x1) * (y2 - y1) > limit:
                continue
            M = np.float32([[s, 0, (x1 + 0.5) * s + left / k - 0.5],
                            [0, s, (y1 + 0.5) * s + top / k - 0.5]])
            patch = cv2.warpAffine(m, M, (x2 - x1, y2 - y1),
                                   flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
            contours, _ = cv2.findContours((patch > 0).astype(np.uint8),
                                           cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = [c + (x1, y1) for c in contours if cv2.contourArea(c) > 4]
            if contours:
                objects.append(contours)
        return objects


def fastsam_segmenter_process(conn, shm_name, conf, iou, max_area):
    try:
        shm = shared_memory.SharedMemory(name=shm_name, track=False)
    except TypeError:
        shm = shared_memory.SharedMemory(name=shm_name)
    rgb = np.ndarray((FASTSAM_IMGSZ, FASTSAM_IMGSZ, 3), np.uint8, buffer=shm.buf)
    try:
        segment = FastSAMSegmenter(conf, iou, max_area)
        conn.send("ready")
        while (msg := conn.recv()) is not None:
            conn.send(segment.outline_letterboxed(rgb, *msg))
    except (EOFError, BrokenPipeError, ConnectionResetError, KeyboardInterrupt):
        pass  # the app went away first: nothing left to outline for


def object_bbox(contours):
    xs = np.concatenate([c[:, 0, 0] for c in contours])
    ys = np.concatenate([c[:, 0, 1] for c in contours])
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def object_area(contours):
    return sum(cv2.contourArea(c) for c in contours)


def find_parents(objects):
    """For each object, the index of the smallest bigger object it sits mostly
    inside (it's a part of that one: a logo, a button, a sticker), or None.
    """
    n = len(objects)
    boxes = [object_bbox(c) for c in objects]
    areas = [object_area(c) for c in objects]
    parents = [None] * n
    for i in range(n):
        xi1, yi1, xi2, yi2 = boxes[i]
        box_area_i = max(1, (xi2 - xi1) * (yi2 - yi1))
        for j in range(n):
            if i == j or areas[i] >= areas[j]:
                continue
            xj1, yj1, xj2, yj2 = boxes[j]
            inter = max(0, min(xi2, xj2) - max(xi1, xj1)) * max(0, min(yi2, yj2) - max(yi1, yj1))
            if inter / box_area_i >= COMPONENT_CONTAINMENT and (parents[i] is None or areas[j] < areas[parents[i]]):
                parents[i] = j
    return parents


def box_iou(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / max(1, union)


def box_center(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def object_rect(contours):
    """(short side, long side, angle) of the object's tightest turned rectangle. The
    angle (degrees, modulo 90) is None when the object is too square or round for it
    to mean anything."""
    (_, _), (w, h), angle = cv2.minAreaRect(np.concatenate(contours))
    short, long = sorted((w, h))
    return short, long, (angle if long > 1.15 * max(short, 1) else None)


def object_centroid(contours):
    """The outline's centre of mass; unlike its box's centre, it turns with the object."""
    moments = [cv2.moments(c) for c in contours]
    a = sum(m["m00"] for m in moments)
    if a <= 0:
        return box_center(object_bbox(contours))
    return sum(m["m10"] for m in moments) / a, sum(m["m01"] for m in moments) / a


def object_color(frame, contours):
    """Mean BGR colour inside the outline, from every 4th pixel (plenty for a mean, and it
    runs on every detection)."""
    x1, y1, x2, y2 = object_bbox(contours)
    crop = np.ascontiguousarray(frame[y1:y2 + 1:4, x1:x2 + 1:4])
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.drawContours(mask, [(c - (x1, y1)) // 4 for c in contours], -1, 255, -1)
    return cv2.mean(crop, mask)[:3]


def similar_color(a, b):
    """Loose on purpose, since an object moving into shadow darkens. What it rules out is
    a dark notebook's ID passing to the white desk left behind where it was (measured:
    brightness 58 vs 172; the notebook's own motion blur: 56)."""
    if a is None or b is None:
        return True
    la, lb = sum(a) / 3 + 1, sum(b) / 3 + 1
    if not 0.55 < la / lb < 1.8:
        return False
    if min(la, lb) < 60:
        return True
    return sum(abs(x / (3 * la) - y / (3 * lb)) for x, y in zip(a, b)) < 0.2


def rotate(v, degrees):
    a = np.radians(degrees)
    return v[0] * np.cos(a) - v[1] * np.sin(a), v[0] * np.sin(a) + v[1] * np.cos(a)


class ObjectTracker:
    """Gives each outlined object a stable ID from one detection to the next, so
    its name stays on it as it moves. Before matching, each object's last box is
    moved to where it should be now: a part (a logo on a notebook) to the same
    spot on its parent (turning with it), anything else onward at its last
    speed. Boxes then match by overlap, or failing that by centre distance. An
    object that drops out is still drawn for HOLD_S, then remembered unseen for
    MEMORY_S in case it comes back in the same place (a part: the same place on
    its parent), when it gets its old ID, and name, back.

    An object picked up and put down somewhere else, or moved further between two
    detections than any guess reaches, is matched by its size and shape instead:
    one lost object and one new object that look the same are taken to be the
    same, but only when neither could be anything else. Its parts then follow it.
    """

    MATCH_IOU = 0.3
    HOLD_S = 0.5
    MEMORY_S = 10.0
    MAX_COAST_S = 0.3
    MIN_RADIUS = 40
    FOUND_MIN_AREA = 2000
    YOUNG_S = 1.0
    SETTLED_HITS = 6

    def __init__(self):
        self.next_id = 1
        self.tracks = {}
        self.now = 0.0

    @staticmethod
    def _same_shape(area, sides, color, t):
        return (t["area"] >= ObjectTracker.FOUND_MIN_AREA and t["hits"] >= ObjectTracker.SETTLED_HITS
                and 0.75 < area / max(t["area"], 1) < 1.33 and similar_color(color, t["color"])
                and all(0.85 < a / max(b, 1) < 1.18 for a, b in zip(sides, t["sides"])))

    def visible(self):
        return {tid: t for tid, t in self.tracks.items() if self.now - t["seen"] <= self.HOLD_S}

    def _score(self, box, center, area, color, t, placed, now):
        """How well a detection fits a track, or None. `placed` holds the centre and
        angle of every track already matched this frame, so a part is looked for
        at its spot on its parent wherever the parent now is. Sizes are compared by
        outline area, which unlike a box's area doesn't grow when the object turns.
        """
        if not similar_color(color, t["color"]):
            return None
        dt = now - t["seen"]
        dormant = dt > self.HOLD_S
        tb, tc = t["box"], t["center"]
        guesses = []
        if t["parent"] in placed and t["rel"] is not None:
            (px, py), angle = placed[t["parent"]]
            rx, ry = rotate(t["rel"], angle)
            guesses.append(((px + rx, py + ry), True))
        if not dormant:
            coast = min(dt, self.MAX_COAST_S)
            guesses += [(tc, False), ((tc[0] + t["vel"][0] * coast, tc[1] + t["vel"][1] * coast), False)]
        elif t["parent"] is None:
            guesses.append((tc, False))
        size = max(tb[2] - tb[0], tb[3] - tb[1], 1)
        area_ratio = (area + 1) / (t["area"] + 1)
        reach = max(0.5 * size, self.MIN_RADIUS)
        best = None
        for (gx, gy), by_parent in guesses:
            dx, dy = gx - tc[0], gy - tc[1]
            iou = box_iou(box, (tb[0] + dx, tb[1] + dy, tb[2] + dx, tb[3] + dy))
            dist = np.hypot(center[0] - gx, center[1] - gy)
            if dormant:
                near = max(0.35 * size, 12)
                score = 2 - dist / near if dist < near and 0.67 < area_ratio < 1.5 else None
            elif by_parent:
                ok = (iou >= self.MATCH_IOU or dist < reach) and 0.5 < area_ratio < 2
                score = 2 + (iou + max(0.0, 1 - dist / reach)) / 2 if ok else None
            elif iou >= self.MATCH_IOU:
                score = 1 + iou
            elif dist < reach and 0.5 < area_ratio < 2:
                score = 1 - dist / reach
            else:
                score = None
            if score is not None and (best is None or score > best):
                best = score
        if best is not None and dormant:
            best -= 1
        if best is not None and t["hits"] >= self.SETTLED_HITS:
            best += 0.5
        return best

    def update(self, objects, parents, now, frame=None):
        """`parents` is find_parents(objects); `frame`, the picture they were found in,
        lets colours be compared too. Returns each object's ID."""
        n = len(objects)
        colors = [object_color(frame, c) if frame is not None else None for c in objects]
        boxes = [object_bbox(c) for c in objects]
        centers = [object_centroid(c) for c in objects]
        self.tracks = {tid: t for tid, t in self.tracks.items() if now - t["seen"] <= self.MEMORY_S}
        depth, root = [0] * n, list(range(n))
        for i in range(n):
            p, d = parents[i], 0
            while p is not None and d < n:
                root[i], p, d = p, parents[p], d + 1
            depth[i] = d
        rects = [object_rect(c) for c in objects]
        areas = [object_area(c) for c in objects]
        ids, angles = [None] * n, [0.0] * n
        taken, placed, found = set(), {}, set()
        for level in sorted(set(depth)):
            members = [i for i in range(n) if depth[i] == level]
            candidates = []
            for i in members:
                for tid, t in self.tracks.items():
                    if tid not in taken:
                        s = self._score(boxes[i], centers[i], areas[i], colors[i], t, placed, now)
                        if s is not None:
                            candidates.append((s, i, tid))
            for _, i, tid in sorted(candidates, reverse=True):
                if ids[i] is None and tid not in taken:
                    ids[i] = tid
                    taken.add(tid)
            pairs = []
            for i in members:
                young = ids[i] is not None and now - self.tracks[ids[i]]["born"] <= self.YOUNG_S
                if parents[i] is not None or (ids[i] is not None and not young):
                    continue
                for tid, t in self.tracks.items():
                    if (tid not in taken and t["parent"] is None and self._same_shape(areas[i], rects[i][:2], colors[i], t)
                            and (not young or t["seen"] < self.tracks[ids[i]]["born"])):
                        pairs.append((i, tid))
            for i, tid in pairs:
                if sum(p[0] == i for p in pairs) == 1 and sum(p[1] == tid for p in pairs) == 1:
                    taken.discard(ids[i])
                    ids[i] = tid
                    taken.add(tid)
                    found.add(i)
            for i in members:
                if ids[i] is None:
                    ids[i], self.next_id = self.next_id, self.next_id + 1
                old = self.tracks.get(ids[i])
                prev = old["angle"] if old else 0.0
                raw = rects[i][2]
                angles[i] = prev if raw is None else prev + ((raw - prev + 45) % 90 - 45)
                placed[ids[i]] = (centers[i], angles[i])
        for i in range(n):
            old = self.tracks.get(ids[i])
            vel = (0.0, 0.0)
            if old and self.HOLD_S >= now - old["seen"] > 0 and i not in found:
                oc, dt = old["center"], now - old["seen"]
                vel = ((centers[i][0] - oc[0]) / dt, (centers[i][1] - oc[1]) / dt)
            p, r = parents[i], root[i]
            if p is not None:
                parent = ids[r]
                rel = rotate((centers[i][0] - centers[r][0], centers[i][1] - centers[r][1]), -angles[r])
            else:
                parent, rel = (old["parent"], old["rel"]) if old else (None, None)
            points = np.concatenate([c[:, 0] for c in objects[i]])
            top = points[points[:, 1].argmin()]
            self.tracks[ids[i]] = {"box": boxes[i], "center": centers[i], "top": (int(top[0]), int(top[1])), "part": p is not None,
                                   "seen": now, "born": old["born"] if old else now, "hits": old["hits"] + 1 if old else 1,
                                   "vel": vel,
                                   "angle": angles[i], "sides": rects[i][:2], "area": areas[i], "color": colors[i],
                                   "parent": parent, "rel": rel}
        self.now = now
        return ids


def board_crop(frame, box):
    """The board's own pixels and where they start in the frame: Vision AI's
    region, which in S1 is the grid box. (None, (0, 0)) for a box too small
    to look at."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = box
    ix0, iy0 = max(0, int(round(x0))), max(0, int(round(y0)))
    ix1, iy1 = min(w, int(round(x1))), min(h, int(round(y1)))
    if ix1 - ix0 < 16 or iy1 - iy0 < 16:
        return None, (0, 0)
    return frame[iy0:iy1, ix0:ix1], (ix0, iy0)


def keep_on_board(objects, box):
    """Drops any object whose centre is off the board, and the board's own
    surface: it comes back as one shape covering most of the box (measured
    93% on the bench), which would otherwise make everything on it look like
    a part."""
    x0, y0, x1, y1 = box
    background = REGION_BACKGROUND_SHARE * max(1.0, (x1 - x0) * (y1 - y0))
    kept = []
    for contours in objects:
        bx1, by1, bx2, by2 = object_bbox(contours)
        cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1 and object_area(contours) < background:
            kept.append(contours)
    return kept


def drop_tag_objects(objects, tag_pts):
    """Drops the AprilTag's own outline and the gripper mount it sits on.

    `tag_pts` is the tag's four corners in the same pixels as the outlines.
    An outline counts as the tag when it runs round the tag's centre and is
    no bigger than TAG_OBJECT_AREA_MULT tags, or when it lies inside the
    tag itself (its printed squares)."""
    if tag_pts is None:
        return objects
    pts = np.asarray(tag_pts, np.float32).reshape(-1, 2)
    if len(pts) < 3:
        return objects
    centre = (float(pts[:, 0].mean()), float(pts[:, 1].mean()))
    tag_area = max(1.0, float(cv2.contourArea(pts)))
    tx0, ty0 = pts.min(0)
    tx1, ty1 = pts.max(0)
    pad_x, pad_y = 0.25 * (tx1 - tx0), 0.25 * (ty1 - ty0)
    kept = []
    for contours in objects:
        x0, y0, x1, y1 = object_bbox(contours)
        inside_tag = (x0 >= tx0 - pad_x and y0 >= ty0 - pad_y
                      and x1 <= tx1 + pad_x and y1 <= ty1 + pad_y)
        around_tag = (object_area(contours) <= TAG_OBJECT_AREA_MULT * tag_area
                      and any(cv2.pointPolygonTest(c, centre, False) >= 0
                              for c in contours))
        if not (inside_tag or around_tag):
            kept.append(contours)
    return kept


def label_points(objects, parents):
    """A spot well inside each object for its number: the point farthest from its
    edge, ignoring the area its own parts cover, so a notebook's number doesn't
    land on its logo.
    """
    points = []
    for i, contours in enumerate(objects):
        x1, y1, x2, y2 = object_bbox(contours)
        mask = np.zeros((y2 - y1 + 1, x2 - x1 + 1), np.uint8)
        cv2.drawContours(mask, [c - (x1, y1) for c in contours], -1, 255, -1)
        for j, p in enumerate(parents):
            if p == i:
                cv2.drawContours(mask, [c - (x1, y1) for c in objects[j]], -1, 0, -1)
        dist = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        y, x = np.unravel_index(int(np.argmax(dist)), dist.shape)
        points.append((x1 + int(x), y1 + int(y)))
    return points


def naming_images(frame, objects, parents, box, is_part=None):
    """Two JPEGs of the same view, cropped to the board: the plain picture, and one
    with the objects to name outlined and numbered 1..n. The plain one matters: the
    outlines and numbers cover small parts, and the model names them better seeing both.
    `is_part` colours an object red even when the thing it's part of isn't being named.
    """
    marked = frame.copy()
    for k, (contours, p) in enumerate(zip(objects, parents)):
        part = is_part[k] if is_part is not None else p is not None
        cv2.drawContours(marked, contours, -1, (0, 0, 255) if part else (0, 255, 0), 2)
    for n, (x, y) in enumerate(label_points(objects, parents), 1):
        (tw, th), _ = cv2.getTextSize(str(n), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(marked, (x - tw // 2 - 4, y - th // 2 - 5), (x + tw // 2 + 4, y + th // 2 + 5), (255, 255, 255), -1)
        cv2.rectangle(marked, (x - tw // 2 - 4, y - th // 2 - 5), (x + tw // 2 + 4, y + th // 2 + 5), (0, 0, 0), 1)
        cv2.putText(marked, str(n), (x - tw // 2, y + th // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    images = []
    for img in (frame, marked):
        if box is not None:
            crop, _ = board_crop(img, box)
            img = crop if crop is not None else img
        scale = min(1.0, NAMER_MAX_SIDE / max(img.shape[:2]))
        if scale < 1:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        images.append(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())
    return images


def naming_prompt(n, part_of, scene_hint):
    """part_of[k] is what object k+1 is a part of (another number, or an object
    already named), or None.

    Vision AI's prompt, word for word, plus what the planner needs beyond a
    name: a colour and a few words of description to match the operator's
    words against, which outlines are the robot itself (never planned with),
    and whether a red outline is really a separate thing lying on the bigger
    one -- a sock in a bowl is picked up on its own; a mug's handle is not.
    """
    parts = "\n".join(f"- {k + 1} is a part of {p}" for k, p in enumerate(part_of) if p)
    return (
        f"These are two photos of the same workbench seen from above. {scene_hint.strip()} The first photo is "
        "the plain view. In the second, each object to name is outlined and has a white label with a number "
        f"from 1 to {n} placed on it. Red outlines are parts of a bigger object:\n"
        f"{parts or '- (none)'}\n\n"
        "Name what each number is with a short, specific everyday name of 1-3 lowercase words, "
        'e.g. "stepper motor", "notebook", "usb cable", "screwdriver". For a part, name the part itself '
        '("logo", "sticker", "button"), not the thing it is on. If a number marks a shadow, bare surface, '
        "a gap, or something you can't identify, use \"unknown\".\n\n"
        "For every number also give:\n"
        '- "color": its main colour in one word ("black", "white", "silver", ...);\n'
        '- "desc": what it looks like in at most 8 words (material, shape, markings);\n'
        '- "robot": true only when it is the robot\'s own machinery (its frame, rails, lead screws, '
        "rods, motors, belts, pulleys, carriage, cables or gripper); false for anything lying on "
        "the board, whatever it looks like - when unsure, false;\n"
        '- "loose": only for a red-outlined part - true when it is really a separate thing lying on '
        "or in the bigger object that could be lifted off on its own (a sock in a bowl, a pen on a "
        "book), false when it is attached to it or printed on it (a handle, a lid, a button, a logo).\n\n"
        'Reply with JSON only: {"objects": [{"n": 1, "name": "...", "color": "...", "desc": "...", '
        '"robot": false, "loose": false}, ...]}, one entry for every number.'
    )


def parse_naming_reply(text, n):
    """{number: {"name", "color", "desc", "robot", "loose"}} for every number
    the reply named; "unknown" and numbers out of range are left out."""
    if "{" not in text:
        raise ValueError(f"no JSON in the reply: {text[:60]!r}")
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    entries = data.get("objects", []) if isinstance(data, dict) else []
    names = {}
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            num = int(item.get("n", 0))
        except (TypeError, ValueError):
            continue
        name = str(item.get("name", "")).strip().lower()
        if 1 <= num <= n and name and name != "unknown":
            names[num] = {"name": name,
                          "color": str(item.get("color") or "").strip().lower(),
                          "desc": str(item.get("desc") or "").strip(),
                          "robot": item.get("robot") is True,
                          "loose": item.get("loose") is True}
    return names


def ask_for_names(model, images, prompt, n):
    """One vision call; returns parse_naming_reply's {number: entry}."""
    client = make_client()
    text = call_model(client, model=model, max_tokens=NAMER_MAX_TOKENS,
                      stage="Naming", priority=PRIORITY_NAMING,
                      messages=[{"role": "user", "content": [
                          {"type": "text", "text": prompt},
                          *({"type": "image_url", "image_url": {
                              "url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(),
                              "detail": "high"}} for jpeg in images),
                      ]}])
    return parse_naming_reply(text, n)


class ObjectNamer:
    """Names the outlined objects with a vision model in a background thread, so
    the video never waits. Every call asks only about objects without a name;
    the named ones are left alone.

    Naming happens only when a task is sent (the planner needs the names)
    or on the N key -- one call each, and then it stops. Nothing is named
    while a task is being typed, and objects that turn up later (put down
    new, or back with a fresh ID after the robot moved them) wait for the
    next task.
    """

    MESSAGE_S = 6

    def __init__(self):
        self.names = {}
        self.info = {}
        self.asked = set()
        self.busy = False
        self.message, self.message_until = "", 0.0
        self._lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()

    def say(self, text):
        self.message, self.message_until = text, time.time() + self.MESSAGE_S

    def current_message(self):
        return self.message if time.time() < self.message_until else ""

    def start(self, frame, objects, ids, box):
        """The N key: names every unnamed object now."""
        if self.busy:
            return
        if not objects:
            self.say("No objects to name")
            return
        pending = [i for i, tid in enumerate(ids) if tid not in self.names]
        if not pending:
            self.say("All objects already named")
            return
        self._launch(frame, objects, ids, pending, box)

    def unanswered(self, ids):
        """The IDs the model has not answered for yet -- neither named nor
        already called "unknown" (a shadow, a gap, bare board)."""
        return [tid for tid in ids
                if tid not in self.names and tid not in self.asked]

    def name_now(self, frame, objects, ids, box):
        """For a task: names every object the model has not answered for
        yet before it returns. Waits for a call already in flight first,
        since that one may be naming the same objects. Returns "" or why
        naming failed.

        An outline the model already called "unknown" is NOT asked about
        again: it never gets a name, so counting it as unnamed made every
        single task pay a full naming round trip for the same shadow."""
        deadline = time.time() + 2 * (API_TIMEOUT_S * API_RETRIES + 30)
        while time.time() < deadline:
            pending = [i for i, tid in enumerate(ids)
                       if tid not in self.names and tid not in self.asked]
            if not pending:
                return ""
            if not self._claim():
                self._idle.wait(timeout=1.0)
                continue
            job = self._prepare(frame, objects, ids, pending, box)
            if job is None:
                self._release()
                return self.current_message() or "Naming could not start."
            return self._run(*job)
        return "Naming did not finish in time."

    def _claim(self):
        with self._lock:
            if self.busy:
                return False
            self.busy = True
            self._idle.clear()
            return True

    def _release(self):
        with self._lock:
            self.busy = False
            self._idle.set()

    def _launch(self, frame, objects, ids, pending, box):
        if not self._claim():
            return
        try:
            job = self._prepare(frame, objects, ids, pending, box)
        except Exception as e:
            self._release()
            self.say(f"Naming failed: {str(e)[:90]}")
            return
        if job is None:
            self._release()
            return
        threading.Thread(target=self._run, args=job, daemon=True).start()

    def _prepare(self, frame, objects, ids, pending, box):
        """(images, prompt, ids, model) for one call, or None without a key."""
        if not resolve_api_key():
            self.say("No OpenAI API key set")
            return None
        full = find_parents(objects)
        part_of = []
        for i in pending:
            p = full[i]
            if p is None:
                part_of.append(None)
            elif p in pending:
                part_of.append(str(pending.index(p) + 1))
            elif ids[p] in self.names:
                part_of.append(f'the "{self.names[ids[p]]}" (already named)')
            else:
                part_of.append("a bigger object")
        sub_parents = [pending.index(full[i]) if full[i] in pending else None for i in pending]
        images = naming_images(frame, [objects[i] for i in pending], sub_parents, box,
                               is_part=[full[i] is not None for i in pending])
        return (images, naming_prompt(len(pending), part_of, VISION_SCENE_HINT),
                [ids[i] for i in pending], NAMER_MODEL)

    def _run(self, images, prompt, ids, model):
        error = ""
        try:
            got = ask_for_names(model, images, prompt, len(ids))
            for n, entry in got.items():
                tid = ids[n - 1]
                self.info[tid] = {k: entry[k] for k in ("color", "desc", "robot", "loose")}
                self.names[tid] = entry["name"]
            self.asked.update(ids)
            self.say(f"Named {len(got)} of {len(ids)} new object{'s' if len(ids) > 1 else ''}")
            named = ", ".join(self.names[ids[n - 1]] for n in sorted(got))
            print(f"[vision] named {len(got)} of {len(ids)}: {named or 'nothing'}")
        except Exception as e:
            error = f"Naming failed: {str(e)[:90]}"
            self.say(error)
            print(f"[vision] {error}")
        finally:
            self._release()
        return error


class LiveVision:
    """Vision AI's camera loop, without its window: FastSAM in its own process,
    the newest board frame handed over the moment each result returns, and
    the tracker and namer run on that feeder thread. The frame loop only
    submits frames and draws the last result; a task takes a snapshot of it.
    """

    def __init__(self):
        self.tracker = ObjectTracker()
        self.namer = ObjectNamer()
        self.ready = False
        self.failed = ""
        self.rate = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._pending, self._pending_id = None, 0
        self._view = None
        self._results = 0
        self._proc = self._conn = self._shm = self._thread = None
        self._started = 0.0

    def start(self):
        if not os.path.exists(FASTSAM_MODEL_PATH) and not os.path.exists(FASTSAM_WEIGHTS):
            self.failed = (f"Vision AI is off: FastSAM was not found in "
                           f"{VISION_AI_DIR} (FastSAM-s.pt or its .coreml_cache).")
            print(f"[vision] {self.failed}")
            return self
        self._started = time.time()
        try:
            self._shm = shared_memory.SharedMemory(create=True, size=FASTSAM_IMGSZ * FASTSAM_IMGSZ * 3)
            ctx = multiprocessing.get_context("spawn")
            self._conn, child_conn = ctx.Pipe()
            self._proc = ctx.Process(target=fastsam_segmenter_process, daemon=True,
                                     args=(child_conn, self._shm.name, VISION_CONF,
                                           VISION_IOU, VISION_MAX_AREA))
            self._proc.start()
            child_conn.close()
        except Exception as e:
            self.failed = f"Vision AI could not start: {e}"
            print(f"[vision] {self.failed}")
            self._close_shm()
            return self
        self._thread = threading.Thread(target=self._feed, daemon=True)
        self._thread.start()
        return self

    def submit(self, frame, box, tag_pts=None, region=None):
        """Offer the newest camera frame, the grid box and the AprilTag's
        corners, all in that frame's pixels. Never blocks: a frame arriving
        while one is being outlined just replaces the one waiting.

        `region` is the part of the board FastSAM may look at -- the
        reachable cells, see reachable_box(). None means the whole box;
        NO_REACH means nothing is reachable, so nothing is outlined."""
        if frame is None or self._thread is None:
            return
        region = (None if region is None else
                  tuple(float(v) for v in region))
        with self._lock:
            self._pending = (frame, tuple(float(v) for v in box), tag_pts,
                             region)
            self._pending_id += 1

    def _feed(self):
        try:
            if self._conn.recv() != "ready":
                return
            print(f"[vision] FastSAM ready in {time.time() - self._started:.1f} s")
            self.ready = True
            sent_id, last, sent_at = 0, None, 0.0
            while not self._stop.is_set():
                with self._lock:
                    pending, pending_id = self._pending, self._pending_id
                if pending is None or pending_id == sent_id:
                    time.sleep(0.002)
                    continue
                # FastSAM flat out (~20-30 outlines a second) kept a core and
                # the GPU busy and this thread's tracking holding the GIL the
                # frame loop needs -- clicks paid for outlines nobody can see
                # change that fast. VISION_MAX_FPS is plenty to follow a
                # moving object.
                wait = sent_at + 1.0 / max(1.0, VISION_MAX_FPS) - time.time()
                if wait > 0:
                    self._stop.wait(wait)
                    continue
                sent_id = pending_id
                sent_at = time.time()
                frame, box, tag_pts, region = pending
                area = box if region is None else region
                if region == NO_REACH:
                    crop = None
                else:
                    crop, (ox, oy) = board_crop(frame, area)
                if crop is None:
                    objects = []
                else:
                    rgb, r, left, top = fastsam_letterbox(crop)
                    np.ndarray(rgb.shape, np.uint8, buffer=self._shm.buf)[:] = rgb
                    self._conn.send((r, left, top, crop.shape[1], crop.shape[0],
                                     VISION_MAX_AREA * frame.shape[0] * frame.shape[1],
                                     VISION_CONF, VISION_IOU))
                    objects = self._conn.recv()
                    objects = [[c + (ox, oy) for c in contours]
                               for contours in objects]
                    objects = drop_tag_objects(keep_on_board(objects, area),
                                               tag_pts)
                parents = find_parents(objects)
                now = time.time()
                ids = self.tracker.update(objects, parents, now, frame)
                labels = [(tid, t["top"], t["part"])
                          for tid, t in self.tracker.visible().items()]
                with self._lock:
                    self._view = {"frame": frame, "box": box, "objects": objects,
                                  "ids": ids, "parents": parents, "labels": labels,
                                  "time": now,
                                  "region": None if region == NO_REACH else area}
                    self._results += 1
                    if last:
                        rate = 1 / max(1e-6, now - last)
                        self.rate = 0.8 * self.rate + 0.2 * rate if self.rate else rate
                last = now
        except (EOFError, OSError):
            if not self._stop.is_set():
                self.failed = "Vision AI's outliner stopped (see the console)."
                print(f"[vision] {self.failed}")
        except Exception as e:
            self.failed = f"Vision AI stopped: {e}"
            print(f"[vision] {self.failed}")

    def view(self):
        """The last result: {"frame", "box", "objects", "ids", "parents",
        "labels", "time"} in camera pixels, or None before the first one."""
        with self._lock:
            return self._view

    def status(self):
        if self.failed:
            return "off"
        if not self.ready:
            return "loading FastSAM..."
        view = self.view()
        count = len(view["objects"]) if view else 0
        return f"{count} objects  {self.rate:.0f} updates/s"

    def name_now(self):
        """The N key: name every unnamed object on the board now."""
        view = self.view()
        if view is None:
            self.namer.say("Wait for the outlines to appear first")
            return
        self.namer.start(view["frame"], view["objects"], view["ids"],
                         view.get("region") or view["box"])

    def snapshot(self, timeout=VISION_READY_WAIT_S, on_wait=None):
        """The last result, for a task -- waiting up to `timeout` for the
        first one while FastSAM loads. Raises ModelError if there is none."""
        deadline = time.time() + timeout
        while True:
            if self.failed:
                raise ModelError(self.failed)
            view = self.view()
            if view is not None:
                return dict(view)
            if time.time() >= deadline:
                raise ModelError("Vision AI has not outlined the board yet - "
                                 "is the camera on and the grid box over the board?")
            if on_wait:
                on_wait()
            time.sleep(0.1)

    def _close_shm(self):
        if self._shm is not None:
            try:
                self._shm.close()
                self._shm.unlink()
            except Exception:
                pass
            self._shm = None

    def stop(self):
        self._stop.set()
        if self._proc is not None and self._proc.pid is not None:
            self._proc.terminate()
            self._proc.join(timeout=2)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._close_shm()


_LIVE_SCALED = [None, None, None]


def draw_live_vision(frame, view, names, info, scale):
    """Vision AI's overlay on the video: green outlines, red for parts, each
    name centred just above its object's highest point. `scale` takes the
    camera pixels the outlines are in to the video's own. Robot parts the
    namer recognised are drawn grey: seen, but never planned with."""
    if not view:
        return frame
    parents = view["parents"]
    cached = _LIVE_SCALED
    if cached[0] is not view or cached[1] != scale:
        # Outlines change only when vision does (~10 times a second); the
        # window redraws up to 60. Scale each result's contours once.
        cached[:] = [view, scale,
                     [[(c * scale).astype(np.int32) for c in contours]
                      for contours in view["objects"]]]
    for scaled, tid, p in zip(cached[2], view["ids"], parents):
        meta = info.get(tid) or {}
        if meta.get("robot"):
            color = (150, 150, 150)
        elif p is not None and VISION_MARK_PARTS and not meta.get("loose"):
            color = (0, 0, 255)
        else:
            color = (0, 255, 0)
        cv2.drawContours(frame, scaled, -1, color, VISION_OUTLINE_PX,
                         cv2.LINE_AA)
    if not VISION_SHOW_NAMES:
        return frame
    h, w = frame.shape[:2]
    placed = []
    for tid, (x, y), part in sorted(view["labels"], key=lambda e: e[1][1]):
        name = names.get(tid)
        if not name:
            continue
        meta = info.get(tid) or {}
        (tw, th), base = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, NAME_FONT, 2)
        x, y = int(x * scale), int(y * scale)
        tx = max(3, min(x - tw // 2, w - tw - 4))
        ty = y - 8 if y - th - 12 > 0 else y + th + 12
        for _ in range(4):
            box = (tx - 3, ty - th - 4, tx + tw + 3, ty + base + 1)
            if not any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
                break
            ty -= th + base + 6
        ty = min(max(ty, th + 5), h - base - 2)
        box = (tx - 3, ty - th - 4, tx + tw + 3, ty + base + 1)
        placed.append(box)
        if meta.get("robot"):
            color = (170, 170, 170)
        elif part and VISION_MARK_PARTS and not meta.get("loose"):
            color = (0, 0, 255)
        else:
            color = (0, 255, 0)
        cv2.rectangle(frame, box[:2], box[2:], (0, 0, 0), -1)
        cv2.putText(frame, name, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, NAME_FONT, color, 2)
    return frame


def colour_word(bgr) -> str:
    """A colour name for a mean BGR value -- the fallback when the naming
    model gave none."""
    if bgr is None:
        return "?"
    px = np.uint8([[[int(max(0, min(255, v))) for v in bgr[:3]]]])
    hue, sat, val = (int(v) for v in cv2.cvtColor(px, cv2.COLOR_BGR2HSV)[0, 0])
    hue *= 2
    if val < 50:
        return "black"
    if sat < 45:
        return "white" if val > 190 else "gray"
    if hue < 15 or hue >= 345:
        return "red" if val > 110 else "brown"
    if hue < 40:
        return "orange" if val > 150 else "brown"
    if hue < 70:
        return "yellow"
    if hue < 165:
        return "green"
    if hue < 260:
        return "blue"
    if hue < 290:
        return "purple"
    return "pink"


def outline_polygon(contours, grid: Grid):
    """An object's outline as S1's polygon: (col, row) points in grid units,
    from its largest contour, simplified to a few dozen vertices -- enough
    to follow the shape, few enough for polygon_to_cells to stay quick."""
    c = max(contours, key=cv2.contourArea)
    if len(c) < 3:
        return None
    eps = max(1.5, 0.005 * cv2.arcLength(c, True))
    approx = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    if len(approx) < 3:
        approx = c.reshape(-1, 2)
    poly = [grid.pixel_to_grid(float(x), float(y)) for x, y in approx]
    return poly if _poly_area(poly) > 1e-6 else None


def planner_objects(snap, namer, grid: Grid):
    """A Vision AI snapshot as the planner's object list.

    Every outline keeps its tracked name. An outline inside a bigger one is
    one of that object's COMPONENTS -- unless the namer said it is a loose
    thing lying on it (a sock in a bowl), which makes it an object of its
    own, described as lying on the other. Robot parts are left out: they are
    equipment, not something on the board to plan with. `grid` is the grid
    box in the snapshot's own camera pixels.
    """
    objects, ids, parents = snap["objects"], snap["ids"], snap["parents"]
    frame = snap.get("frame")
    names, info = namer.names, namer.info
    cw, ch = cell_size_in(grid)

    def meta(i):
        return info.get(ids[i]) or {}

    def owner(i):
        """The object this outline belongs to: itself when it stands alone
        (or lies loose on something), else the nearest such ancestor."""
        seen = 0
        while parents[i] is not None and not meta(i).get("loose") and seen < len(objects):
            i, seen = parents[i], seen + 1
        return i

    entries, components = {}, {}
    for i, contours in enumerate(objects):
        if meta(i).get("robot"):
            continue
        poly = outline_polygon(contours, grid)
        if poly is None:
            continue
        cell, cells, pt = polygon_to_cells(poly)
        if cell is None:
            continue
        o = owner(i)
        name = clean_object_name(names.get(ids[i])) or (
            "part" if o != i else "unidentified object")
        entry = {"name": name, "center": coordinate_name(*cell),
                 "touches": ",".join(coordinate_name(*c) for c in cells),
                 "polygon": poly}
        set_center_pt(entry, pt)
        if o != i:
            components.setdefault(o, []).append(entry)
            continue
        colour = meta(i).get("color") or (
            colour_word(object_color(frame, contours)) if frame is not None else "?")
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        w_in, h_in = (max(xs) - min(xs)) * cw, (max(ys) - min(ys)) * ch
        desc = meta(i).get("desc") or ""
        bits = [desc] if desc else []
        bits.append(f"about {w_in:.1f} x {h_in:.1f} in")
        if parents[i] is not None:
            under = names.get(ids[parents[i]])
            bits.append(f"lying on/in the {under}" if under else "lying on another object")
        entry.update({"color": colour, "size": size_class(max(w_in, h_in)),
                      "desc": ", ".join(bits), "aka": [], "components": [],
                      "track_id": ids[i]})
        if ids[i] not in names:
            entry["name_uncertain"] = True
        entries[i] = entry
    for o, comps in components.items():
        if o in entries:
            parent_poly = entries[o]["polygon"]
            entries[o]["components"] = [c for c in comps
                                        if component_on_parent(c["polygon"], parent_poly)]
    return [entries[i] for i in sorted(entries, key=lambda i: _reading_order(entries[i]))]


def _hint_matches(key: str, name: str) -> bool:
    """Whole-word match, never a raw substring.

    Plain `in` gave a folded "cloth" the parts of a "clothes dryer" -- door,
    drum, lint filter -- because "cloth" sits inside "clothes". A match that
    fires on the wrong object is worse than none: a "clothes dryer" would be
    folded like a towel.
    """
    if key == name:
        return True
    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", name) is not None


BOARD_WIDTH_IN = 24.0


VISION_FRAME_DIR_VAR = "S1_VISION_FRAME_DIR"


def save_vision_frame(raw_frame, grid):
    """Write the raw frame + grid box to S1_VISION_FRAME_DIR, if it is set.

    Returns the image path, or None when the dump is off or fails. Never
    raises: a diagnostic must not be able to break a vision run.
    """
    folder = os.environ.get(VISION_FRAME_DIR_VAR, "").strip()
    if not folder or raw_frame is None or grid is None:
        return None
    try:
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"board_{stamp}.png")
        if not cv2.imwrite(path, raw_frame):
            return None
        h, w = raw_frame.shape[:2]
        with open(os.path.join(folder, f"board_{stamp}.json"), "w") as f:
            json.dump({"box": [float(v) for v in grid.box],
                       "square_cells": bool(grid.square_cells),
                       "n_cols": CONFIG.n_cols, "n_rows": CONFIG.n_rows,
                       "frame": [w, h]}, f)
        print(f"[vision] frame saved to {path}")
        return path
    except Exception as e:
        print(f"[vision] could not save the frame ({e})")
        return None


PLACEHOLDER_NAMES = frozenset((
    "object", "item", "thing", "unknown", "unidentified", "part", "piece",
    "device", "tool", "equipment", "stuff", "something", "n/a", "none",
))


def clean_object_name(raw) -> str:
    """A model's name field -> a usable object name, or "" if it is a refusal."""
    name = re.sub(r"\s+", " ", str(raw or "").strip().lower()).strip(" .,-")
    if not name or name in PLACEHOLDER_NAMES:
        return ""
    return name


def _clean_aka(raw, name: str):
    """Synonym list -> lowercase strings, minus the name itself and junk."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for a in raw:
        a = re.sub(r"\s+", " ", str(a).strip().lower()).strip(" .,-")
        if a and a != name and a not in PLACEHOLDER_NAMES and a not in out:
            out.append(a)
    return out[:4]


QUALIFIER_WORDS = frozenset((
    "big", "large", "small", "little", "tiny", "long", "short", "tall",
    "wide", "narrow", "thick", "thin", "open", "closed", "empty", "full",
    "folded", "unfolded", "upright", "upside", "down", "left", "right",
    "upper", "lower", "top", "bottom", "near", "far", "first", "second",
    "black", "white", "grey", "gray", "red", "blue", "green", "yellow",
    "orange", "purple", "pink", "brown", "silver", "gold", "golden", "clear",
    "transparent", "dark", "light", "pale", "bright", "metal", "metallic",
    "plastic", "wooden", "wood", "glass", "steel", "chrome", "striped",
    "patterned", "plain", "old", "new", "dirty", "clean",
))


def _name_kind(name: str) -> str:
    """What an object IS, with the describing words taken off.

    "black sock", "white sock" and "sock" are all the same kind of thing, and
    an operator who says "the sock" means any of them. Grouping on the exact
    string instead misses that entirely: it only sees a clash when two names
    match character for character, so a board holding "sock", "sock" and
    "black sock" gets the first two renamed and the third left alone -- and
    the rename then falls back to cell numbers, because the colours that
    would have separated them were not all in the same group.
    """
    words = [w for w in re.split(r"[\s/_-]+", clean_object_name(name)) if w]
    kept = [w for w in words if w not in QUALIFIER_WORDS]
    return " ".join(kept) if kept else " ".join(words)


def _attr_values(objects, attr):
    """Each object's value for `attr`, or None if any is missing/useless."""
    vals = []
    for o in objects:
        v = re.sub(r"\s+", " ", str(o.get(attr) or "").strip().lower())
        v = v.strip(" .,-")
        if not v or v in {"?", "n/a", "none", "unknown", "mixed", "various"}:
            return None
        vals.append(v)
    return vals


def _separating_labels(group, kind):
    """Names that tell these same-kind objects apart, and how it was done.

    A describing word does not have to be UNIQUE to be worth using -- it only
    has to divide the group. Two black socks and two white ones is the normal
    case, and "black sock 1 / black sock 2 / white sock 1 / white sock 2" is
    a far better answer than numbering all four, because the operator can say
    "the white one" and cut the field in half. Requiring uniqueness threw
    colour away in exactly the case it helps most.
    """
    own = [clean_object_name(o.get("name")) for o in group]
    if all(own) and all(n != kind for n in own) and len(set(own)) >= 2:
        out = [""] * len(group)
        for val in set(own):
            idxs = [i for i, v in enumerate(own) if v == val]
            if len(idxs) == 1:
                out[idxs[0]] = val
                continue
            for rank, i in enumerate(sorted(idxs,
                                            key=lambda j: _reading_order(group[j])),
                                     start=1):
                out[i] = f"{val} {rank}"
        return out, "their own names then position"
    for attr, tag in (("color", "colour"), ("size", "size")):
        vals = _attr_values(group, attr)
        if not vals or len(set(vals)) < 2:
            continue
        labels = [f"{v} {kind}" for v in vals]
        if len(set(labels)) == len(labels):
            return labels, tag
        out = [""] * len(group)
        for val in set(vals):
            idxs = [i for i, v in enumerate(vals) if v == val]
            if len(idxs) == 1:
                out[idxs[0]] = f"{val} {kind}"
                continue
            for rank, i in enumerate(sorted(idxs,
                                            key=lambda j: _reading_order(group[j])),
                                     start=1):
                out[i] = f"{val} {kind} {rank}"
        return out, f"{tag} then position"

    shared = own[0] if all(own) and len(set(own)) == 1 else kind
    order = sorted(range(len(group)), key=lambda i: _reading_order(group[i]))
    labels = [""] * len(group)
    for rank, idx in enumerate(order, start=1):
        labels[idx] = f"{shared} {rank}"
    return labels, "position"


def disambiguate_names(objects):
    """Give objects of the same KIND something to tell them apart by.

    The planner resolves the operator's words against these names, so two
    entries the operator cannot address separately are two objects it will
    pick between at random -- and half the time it picks the wrong one.

    Three things this has to get right, all of which the exact-string version
    got wrong on a real board of four socks and an iron:

    - Group by KIND, not by string. "sock", "sock" and "black sock" are three
      socks. Matching strings saw only the first two.
    - Prefer a VISIBLE difference. Colour first, then size, then the object's
      own description -- something the operator can see and say. A cell
      reference is the last resort, because "the sock at C4" is not language
      anyone uses; it is the robot's coordinates handed back to the human.
    - Keep the shared word in `aka`, so "the sock" still matches all of them
      and the difference decides between them.
    """
    groups = {}
    for o in objects:
        kind = _name_kind(o.get("name"))
        if kind:
            groups.setdefault(kind, []).append(o)

    for kind, group in groups.items():
        if len(group) < 2:
            continue
        names = [clean_object_name(o.get("name")) for o in group]
        if len(set(names)) == len(names) and all(n != kind for n in names):
            continue

        labels, how = _separating_labels(group, kind)

        for o, label in zip(group, labels):
            aka = _clean_aka(o.get("aka"), label)
            old = clean_object_name(o.get("name"))
            for extra in (kind, old):
                if extra and extra != label and extra not in aka:
                    aka.insert(0, extra)
            o["name"] = label
            o["aka"] = aka[:4]
        print(f"[vision] {len(group)} objects of kind '{kind}' - "
              f"told apart by {how}")
    return objects


def _reading_order(obj):
    """(row, col) of an object's centre, for numbering left-to-right."""
    cell = parse_coordinate(str(obj.get("center") or "").strip())
    if cell is None:
        return (10 ** 6, 10 ** 6)
    return (cell[1], cell[0])


GRIPPER_AI = True


def _poly_span(poly):
    """(width, height) of a polygon's bounding box, in grid units."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return max(xs) - min(xs), max(ys) - min(ys)


GARMENT_FAMILIES = (
    ("sleeved", ("shirt", "t-shirt", "tshirt", "tee", "sweater", "jumper",
                 "sweatshirt", "hoodie", "hoody", "jacket", "coat", "blouse",
                 "cardigan", "polo", "pullover", "fleece", "onesie", "romper",
                 "bodysuit", "top", "jersey", "tunic", "kurta", "kimono",
                 "robe", "bathrobe", "long sleeve", "crop top")),
    ("sleeveless", ("dress", "gown", "skirt", "tank top", "tank", "vest",
                    "camisole", "singlet", "apron", "nightgown", "nightie",
                    "slip", "pinafore", "sundress", "frock")),
    ("bottoms", ("trousers", "pants", "jeans", "shorts", "leggings",
                 "sweatpants", "joggers", "tights", "pajama pants",
                 "pyjama bottoms", "pajama bottoms", "bottoms", "slacks",
                 "chinos", "culottes", "trunks", "swim trunks")),
    ("flat", ("towel", "washcloth", "face cloth", "facecloth", "hand towel",
              "bath towel", "tea towel", "dish towel", "sheet", "bedsheet",
              "bed sheet", "pillowcase", "pillow case", "blanket", "napkin",
              "tablecloth", "table cloth", "cloth", "rag", "duvet cover",
              "flannel", "throw", "wipe", "microfiber cloth", "dishcloth",
              "dish cloth", "duster", "handkerchief", "hanky", "bandana",
              "serviette", "cleaning cloth", "kitchen cloth", "dust cloth")),
    ("simple", ("sock", "socks", "scarf", "necktie", "tie", "underwear",
                "briefs", "boxers", "panties", "knickers", "bra", "glove",
                "gloves", "mitten", "mittens", "beanie", "hat",
                "belt", "headband", "bib", "swimsuit",
                "shawl", "stole", "wrap", "sarong", "bikini", "leg warmer",
                "vest top")),
)

FOLD_ROLES = {
    "top_left": ("shoulder_left", "top_left", "waist_left", "waistband_left",
                 "neck_left", "collar_left"),
    "top_right": ("shoulder_right", "top_right", "waist_right",
                  "waistband_right", "neck_right", "collar_right"),
    "top_mid": ("collar", "neck", "neckline", "waistband", "waist", "top",
                "opening", "cuff", "crown"),
    "bottom_left": ("hem_left", "cuff_left", "bottom_left", "corner_left",
                    "leg_left", "ankle_left"),
    "bottom_right": ("hem_right", "cuff_right", "bottom_right",
                     "corner_right", "leg_right", "ankle_right"),
    "bottom_mid": ("hem", "toe", "bottom", "tip", "end", "heel"),
    "arm_left": ("sleeve_left", "strap_left", "tie_left", "arm_left",
                 "string_left", "sleeve left"),
    "arm_right": ("sleeve_right", "strap_right", "tie_right", "arm_right",
                  "string_right", "sleeve right"),
    "hood": ("hood",),
    "body": ("body", "torso", "panel", "front panel", "front"),
}
FOLD_ROLE_ORDER = ("top_left", "top_right", "top_mid", "bottom_left",
                   "bottom_right", "bottom_mid", "arm_left", "arm_right",
                   "hood", "body")

FOLD_LONG_IN = 14.0
FOLD_TARGET_IN = 12.0
FOLD_NARROW_IN = 5.0
FOLD_MIN_IN = 3.0
FOLD_MAX_LENGTH_FOLDS = 3

FOLD_TASK_RE = re.compile(r"\bfold(?:ing|ed|s)?\b", re.I)


def is_fold_task(task) -> bool:
    return bool(FOLD_TASK_RE.search(task or ""))


def garment_family(obj) -> str:
    """"sleeved" / "sleeveless" / "bottoms" / "flat" / "simple", "unknown"
    for a garment named something this table does not know but carrying
    fold landmarks, or "" for something that is not clothing at all."""
    name = clean_object_name(obj.get("name")) or ""
    best, best_len = "", 0
    for family, words in GARMENT_FAMILIES:
        for word in words:
            if len(word) > best_len and _hint_matches(word, name):
                best, best_len = family, len(word)
    if best:
        return best
    for alias in (str(a) for a in (obj.get("aka") or []) if a):
        low = clean_object_name(alias)
        for family, words in GARMENT_FAMILIES:
            if any(_hint_matches(w, low) for w in words):
                return family
    if fold_landmarks(obj, family="unknown"):
        return "unknown"
    return ""


def is_garment(obj) -> bool:
    return bool(garment_family(obj))


def is_fold_top(obj):
    """Kept for the name: a garment that folds sleeve-onto-sleeve."""
    return garment_family(obj) == "sleeved"


def _fold_aliases(role: str, family: str):
    """The landmark names that fill this role FOR THIS FAMILY, best first.

    Two names mean opposite ends on different garments and are settled
    here: "cuff_left"/"cuff_right" are a pair of pants' leg openings (the
    BOTTOM), a sock's cuff is its TOP, and a shirt's cuffs are its sleeve
    ends (a SIDE handle).
    """
    names = list(FOLD_ROLES[role])
    if family == "bottoms":
        if role == "top_mid":
            names = [n for n in names if n != "cuff"]
    else:
        if role in ("bottom_left", "bottom_right"):
            names = [n for n in names if not n.startswith("cuff")]
        if family == "sleeved":
            if role == "arm_left":
                names.append("cuff_left")
            elif role == "arm_right":
                names.append("cuff_right")
        else:
            if role == "top_left":
                names.append("cuff_left")
            elif role == "top_right":
                names.append("cuff_right")
    return names


def _located_part(part, parent_poly):
    """A part with a real cell ON its parent, as (cell, point) -- or None.

    Names without geometry are not usable folding landmarks: a part's cell
    beats the object's centre when the planner picks up, so a landmark that
    exists only as a word would send the arm to whatever cell it invents.
    """
    if not isinstance(part, dict):
        return None
    cell = parse_coordinate(str(part.get("center") or ""))
    poly = part.get("polygon")
    if cell is None or not poly or not parent_poly:
        return None
    if not component_on_parent(poly, parent_poly):
        return None
    pt = part.get("center_pt")
    if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
        pt = (cell[0] + 0.5, cell[1] + 0.5)
    return cell, (float(pt[0]), float(pt[1]))


def fold_landmarks(obj, family=None):
    """role -> {"name", "cell", "pt"} for every located landmark on this
    object. First located part wins a role (vision lists the best first)."""
    family = garment_family(obj) if family is None else family
    parent_poly = obj.get("polygon")
    located = {}
    for part in obj.get("components") or []:
        if not isinstance(part, dict):
            continue
        key = str(part.get("name") or "").strip().lower()
        if not key or key in located:
            continue
        loc = _located_part(part, parent_poly)
        if loc is not None:
            located[key] = {"name": key, "cell": loc[0], "pt": loc[1]}
    found = {}
    for role in FOLD_ROLE_ORDER:
        for alias in _fold_aliases(role, family or ""):
            if alias in located:
                found[role] = located[alias]
                break
    return found


def _fold_side(marks, end, side):
    """The landmark for one END ("top"/"bottom") on one SIDE ("left"/
    "right"), falling back to that end's middle point."""
    return marks.get(f"{end}_{side}") or marks.get(f"{end}_mid")


def _fold_point_name(pt):
    """A synthetic point (the crease after a fold) as a cell name."""
    c = int(max(0, min(CONFIG.n_cols - 1, math.floor(pt[0]))))
    r = int(max(0, min(CONFIG.n_rows - 1, math.floor(pt[1]))))
    return coordinate_name(c, r)


def _fold_move(what, src, where, dst, why):
    """One pickup/keep pair. src/dst are landmark dicts or synthetic
    {"name", "cell", "pt"} points; cells are what the planner writes."""
    return {"pick": what, "pick_name": src["name"],
            "pick_cell": coordinate_name(*src["cell"]), "pick_pt": src["pt"],
            "place": where, "place_name": dst["name"],
            "place_cell": coordinate_name(*dst["cell"]), "place_pt": dst["pt"],
            "why": why}


def _fold_span_in(obj, marks, grid=None):
    """(length, width) of the garment in inches: length is top end to
    bottom end when both are located, else the outline's larger span."""
    cw, ch = cell_size_in(grid)
    cell_in = (cw + ch) / 2.0
    tops = [m["pt"] for k, m in marks.items() if k.startswith("top_")]
    bots = [m["pt"] for k, m in marks.items() if k.startswith("bottom_")]
    poly = obj.get("polygon") or []
    w_cells = h_cells = 0.0
    if len(poly) >= 3:
        w_cells, h_cells = _poly_span(poly)
    if tops and bots:
        tc = (sum(p[0] for p in tops) / len(tops), sum(p[1] for p in tops) / len(tops))
        bc = (sum(p[0] for p in bots) / len(bots), sum(p[1] for p in bots) / len(bots))
        length = math.hypot(tc[0] - bc[0], tc[1] - bc[1])
        along_rows = abs(tc[1] - bc[1]) >= abs(tc[0] - bc[0])
        width = w_cells if along_rows else h_cells
        return length * cell_in, width * cell_in
    return max(w_cells, h_cells) * cell_in, min(w_cells, h_cells) * cell_in


def _missing_name(role: str, kind: str) -> str:
    """A missing role, named the way vision would have to report it."""
    side = role.rsplit("_", 1)[-1]
    if role.startswith("arm_"):
        return f"sleeve_{side}" if kind in ("sleeved top", "hooded top") \
            else f"strap_{side} or sleeve_{side}"
    if role.startswith("bottom_"):
        return {"legged bottom": f"cuff_{side}",
                "simple item": f"bottom_{side}"}.get(kind, f"hem_{side}")
    if role.startswith("top_"):
        return {"legged bottom": f"waist_{side}",
                "simple item": f"top_{side}"}.get(kind, f"shoulder_{side}")
    return role


CLOTH_CORNER_NAMES = ("top_left", "top_right", "bottom_right", "bottom_left")
CLOTH_GRIP_INSET = 0.3


def _convex_hull(pts):
    """Monotone-chain hull of (x, y) points, counter-clockwise, no repeats."""
    pts = sorted(set((float(x), float(y)) for x, y in pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def cloth_corners(obj):
    """The cloth's four corners, {name: (col, row)} in grid units, or None.

    The four hull points that span the largest quadrilateral are the four
    corners of anything cloth-shaped, however it is turned -- a crease, a
    frayed edge or a rounded corner cannot out-span a real corner. Names
    are by screen position: whichever labelling puts each point nearest
    its own corner of the cloth's bounding box.
    """
    poly = obj.get("polygon") if isinstance(obj, dict) else obj
    if not poly or len(poly) < 3:
        return None
    try:
        hull = _convex_hull([(float(p[0]), float(p[1])) for p in poly])
    except (TypeError, ValueError, IndexError):
        return None
    if len(hull) < 4:
        return None
    if len(hull) > 24:
        arr = np.array(hull, dtype=np.float32).reshape(-1, 1, 2)
        eps = 0.0
        simplified = hull
        for _ in range(20):
            eps += 0.01
            approx = cv2.approxPolyDP(arr, eps, True).reshape(-1, 2)
            if len(approx) <= 24:
                simplified = [(float(x), float(y)) for x, y in approx]
                break
        hull = simplified if len(simplified) >= 4 else hull[::2]
    best, best_area = None, -1.0
    n = len(hull)
    for a in range(n):
        for b in range(a + 1, n):
            for c in range(b + 1, n):
                for d in range(c + 1, n):
                    quad = [hull[a], hull[b], hull[c], hull[d]]
                    area = _poly_area(quad)
                    if area > best_area:
                        best, best_area = quad, area
    if best is None or best_area <= 1e-6:
        return None
    xs = [p[0] for p in best]
    ys = [p[1] for p in best]
    box = {"top_left": (min(xs), min(ys)), "top_right": (max(xs), min(ys)),
           "bottom_right": (max(xs), max(ys)),
           "bottom_left": (min(xs), max(ys))}
    cyc = best
    best_rot, best_cost = None, None
    for r in range(4):
        rot = cyc[r:] + cyc[:r]
        cost = sum((rot[k][0] - box[nm][0]) ** 2 + (rot[k][1] - box[nm][1]) ** 2
                   for k, nm in enumerate(CLOTH_CORNER_NAMES))
        if best_cost is None or cost < best_cost:
            best_rot, best_cost = rot, cost
    return {nm: best_rot[k] for k, nm in enumerate(CLOTH_CORNER_NAMES)}


def _inset(pt, toward, amount):
    """`pt` moved `amount` cells toward `toward`, never past half the gap."""
    dx, dy = toward[0] - pt[0], toward[1] - pt[1]
    dist = math.hypot(dx, dy)
    if dist <= 1e-9:
        return pt
    step = min(amount, dist / 2.0)
    return (pt[0] + dx / dist * step, pt[1] + dy / dist * step)


def cloth_fold_points(obj):
    """The four grip/landing points of the cloth fold, or None.

    {"left_mid", "right_mid", "bottom_right", "top_right", "corners"}: the
    middle of the left side, the middle of the right side and the two right-
    hand corners, each pulled CLOTH_GRIP_INSET in toward the cloth's middle.
    """
    corners = cloth_corners(obj)
    if corners is None:
        return None
    tl, tr = corners["top_left"], corners["top_right"]
    br, bl = corners["bottom_right"], corners["bottom_left"]
    mid = (sum(p[0] for p in corners.values()) / 4.0,
           sum(p[1] for p in corners.values()) / 4.0)
    left_mid = ((tl[0] + bl[0]) / 2.0, (tl[1] + bl[1]) / 2.0)
    right_mid = ((tr[0] + br[0]) / 2.0, (tr[1] + br[1]) / 2.0)
    return {"left_mid": _inset(left_mid, mid, CLOTH_GRIP_INSET),
            "right_mid": _inset(right_mid, mid, CLOTH_GRIP_INSET),
            "bottom_right": _inset(br, mid, CLOTH_GRIP_INSET),
            "top_right": _inset(tr, mid, CLOTH_GRIP_INSET),
            "corners": corners}


CLOTH_FOLD_POINT_NAMES = ("left_mid", "right_mid", "bottom_right", "top_right")
_CLOTH_FOLD_POINT_AKA = {
    "left_mid": ["middle of the left side", "left edge midpoint"],
    "right_mid": ["middle of the right side", "right edge midpoint"],
    "bottom_right": ["bottom right corner"],
    "top_right": ["top right corner"],
}


def cloth_corner_components(obj):
    """The cloth's fold grip points as COMPONENTS: exactly four, never more,
    and never the raw geometric corners the fold does not use.

    A plain cloth is folded in two moves -- left-mid onto right-mid, then
    bottom-right onto top-right (see _flat_recipe) -- so those are the four
    points published here, each a small square at the cell the gripper
    actually closes on, so the overlay shows them and the planner can
    address "the middle of the left side" by a real cell. top_left and
    bottom_left are geometry cloth_fold_points() computes on the way to
    these four points, never grip targets in their own right, and are not
    published.
    """
    pts = cloth_fold_points(obj)
    if pts is None:
        return []
    out = []
    for name in CLOTH_FOLD_POINT_NAMES:
        c = pts[name]
        cell = parse_coordinate(_fold_point_name(c))
        if cell is None:
            continue
        entry = {"name": name,
                 "polygon": [[c[0] - 0.12, c[1] - 0.12], [c[0] + 0.12, c[1] - 0.12],
                             [c[0] + 0.12, c[1] + 0.12], [c[0] - 0.12, c[1] + 0.12]],
                 "center": coordinate_name(*cell),
                 "touches": coordinate_name(*cell),
                 "aka": list(_CLOTH_FOLD_POINT_AKA[name])}
        set_center_pt(entry, c)
        out.append(entry)
    return out


def add_cloth_corners(objects):
    """Give every plain cloth on the board its four corners as components."""
    for o in objects or ():
        if garment_family(o) == "flat" and o.get("polygon"):
            comps = cloth_corner_components(o)
            if comps:
                o["components"] = comps
    return objects


def _flat_recipe(obj, out, kind="flat item", note=""):
    """The cloth fold: left side's middle onto the right side's middle, then
    the bottom-right corner up onto the top-right corner - EXCEPT a very
    elongated outline (a sock- or scarf-shaped item that fell through to
    "flat" for want of landmarks, or simply a long thin towel), which folds
    end-to-end along its length instead: the corner fold's own left_mid and
    right_mid can land in the SAME grid cell on a shape this narrow (found
    by fuzzing _outline_fold_moves' sibling path, 2026-09-27), which is not
    a fold at all - picking up and putting down at the same spot."""
    out["family"] = "flat"
    out["flat"] = True
    out["kind"] = kind
    out["note"] = note
    pts = cloth_fold_points(obj)
    if pts is None:
        out["missing"] = ["the cloth's four corners (its outline is unusable)"]
        return out
    c = pts["corners"]
    cw, ch = cell_size_in()
    width = math.hypot((c["top_right"][0] - c["top_left"][0]) * cw,
                       (c["top_right"][1] - c["top_left"][1]) * ch)
    length = math.hypot((c["bottom_left"][0] - c["top_left"][0]) * cw,
                        (c["bottom_left"][1] - c["top_left"][1]) * ch)
    out["length_in"], out["width_in"] = max(length, width), min(length, width)
    long_span, short_span = max(length, width), min(length, width)
    if long_span < FOLD_MIN_IN:
        out["note"] = ((note + "; ") if note else "") + \
            "already compact - no fold needed"
        return out
    if short_span > 0 and long_span / short_span >= 1.8:
        moves = _outline_fold_moves(obj, {}, "simple item", short_span)
        if moves:
            out["moves"] = moves
            out["note"] = ((note + "; ") if note else "") + \
                "elongated - folded end to end instead of by its corners"
            return out
    def at(name, pt):
        return {"name": name, "cell": parse_coordinate(_fold_point_name(pt)),
                "pt": pt}

    out["moves"] = [
        _fold_move("middle of the left side", at("left side, middle", pts["left_mid"]),
                   "middle of the right side", at("right side, middle", pts["right_mid"]),
                   "side: the left half folded over onto the right half"),
        _fold_move("bottom-right corner", at("bottom_right", pts["bottom_right"]),
                   "top-right corner", at("top_right", pts["top_right"]),
                   "length: the bottom-right corner up onto the top-right corner"),
    ]
    return out


def fold_recipe(obj, grid=None):
    """The fold for one garment, from the landmarks vision located.

    Returns {"family", "kind", "moves", "missing", "note", "flat",
    "length_in", "width_in"}. "moves" is the ordered pickup/keep list with
    real cells; "missing" names what the fold still needs (empty when the
    recipe is complete); "flat" says this is a plain cloth, folded by its
    corners (playbook 5a).
    """
    family = garment_family(obj)
    out = {"family": family, "kind": "", "moves": [], "missing": [],
           "note": "", "flat": False, "length_in": 0.0, "width_in": 0.0}
    if not family:
        return out
    desc = str(obj.get("desc") or "").lower()
    name = str(obj.get("name") or "").lower()
    if ((re.search(r"\b(already|neatly|is|lying) folded\b|\bfolded (up|neatly|into|in half)\b", desc)
         and not re.search(r"\bunfolded\b", desc))
            or (re.search(r"\bfolded\b", name) and not re.search(r"\bunfolded\b", name))):
        out["kind"] = "already folded"
        out["note"] = "already folded - leave it"
        return out
    if family == "flat":
        return _flat_recipe(obj, out)
    marks = fold_landmarks(obj, family)
    length_in, width_in = _fold_span_in(obj, marks, grid)
    out["length_in"], out["width_in"] = length_in, width_in

    shape_marks = {k: v for k, v in marks.items() if k not in ("body",)}
    if not shape_marks and not re.search(
            r"\b(sleeve|strap|hood|collar|waist|cuff|crotch|leg)\b", desc):
        return _flat_recipe(
            obj, out, kind="flat item (no garment shape found)",
            note=("named as a garment but has no sleeve/strap/leg/waist of "
                  "its own - folded as a plain cloth instead"))

    arms = "arm_left" in marks and "arm_right" in marks
    arm_names = tuple((marks.get(k) or {}).get("name", "") for k in ("arm_left", "arm_right"))
    sleeved = arms and not any(n.startswith(("strap", "tie", "string"))
                               for n in arm_names)
    legged = family == "bottoms"
    hooded = "hood" in marks
    if legged:
        kind = "legged bottom"
    elif sleeved:
        kind = "hooded top" if hooded else "sleeved top"
    elif arms:
        kind = "strapped garment"
    elif family == "simple" or (family in ("unknown",) and width_in < FOLD_NARROW_IN):
        kind = "simple item"
    elif family == "sleeved":
        kind = "sleeved top"
    else:
        kind = "sleeveless garment"
    out["kind"] = kind

    def complete(side):
        return _fold_side(marks, "bottom", side) and _fold_side(marks, "top", side)
    give, recv = "left", "right"
    if not complete("right") and complete("left"):
        give, recv = "right", "left"
    missing = []
    moves = []

    if hooded:
        land = marks.get("top_mid")
        if land is None and "top_left" in marks and "top_right" in marks:
            a, b = marks["top_left"]["pt"], marks["top_right"]["pt"]
            pt = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            land = {"name": "between the shoulders",
                    "cell": parse_coordinate(_fold_point_name(pt)), "pt": pt}
        if land is None:
            land = marks.get("body")
        if land is not None:
            moves.append(_fold_move("hood", marks["hood"], "collar", land,
                                    "tuck: hood down onto the collar"))
        else:
            out["note"] = "hood located but no collar/shoulders/body to lay it on - left as is; "

    if kind in ("sleeved top", "hooded top", "strapped garment"):
        if arms:
            moves.append(_fold_move(
                f"arm_{give}", marks[f"arm_{give}"], f"arm_{recv}",
                marks[f"arm_{recv}"],
                "side: one side onto the other by its "
                + ("sleeve" if sleeved else "strap")))
        else:
            missing += [_missing_name(f"arm_{s}", kind) for s in ("left", "right")
                        if f"arm_{s}" not in marks]
        if kind == "strapped garment" and length_in >= FOLD_LONG_IN:
            bl, br = marks.get(f"bottom_{give}"), marks.get(f"bottom_{recv}")
            if bl and br:
                moves.append(_fold_move(
                    f"bottom_{give}", bl, f"bottom_{recv}", br,
                    "side: a long garment's bottom corner over too"))
    elif kind == "legged bottom":
        bl, br = marks.get(f"bottom_{give}"), marks.get(f"bottom_{recv}")
        if bl and br:
            moves.append(_fold_move(f"bottom_{give}", bl, f"bottom_{recv}", br,
                                    "side: one leg laid over the other"))
        else:
            missing += [_missing_name(f"bottom_{s}", kind) for s in ("left", "right")
                        if f"bottom_{s}" not in marks]
        tl, tr = marks.get(f"top_{give}"), marks.get(f"top_{recv}")
        if tl and tr:
            moves.append(_fold_move(f"top_{give}", tl, f"top_{recv}", tr,
                                    "side: the waistband squared over the same side"))
    elif kind == "sleeveless garment":
        bl, br = marks.get(f"bottom_{give}"), marks.get(f"bottom_{recv}")
        if width_in >= FOLD_NARROW_IN:
            if bl and br:
                moves.append(_fold_move(
                    f"bottom_{give}", bl, f"bottom_{recv}", br,
                    "side: one hem corner onto the other"))
            else:
                missing += [_missing_name(f"bottom_{s}", kind) for s in ("left", "right")
                        if f"bottom_{s}" not in marks]
            tl, tr = marks.get(f"top_{give}"), marks.get(f"top_{recv}")
            if length_in >= FOLD_LONG_IN and tl and tr:
                moves.append(_fold_move(
                    f"top_{give}", tl, f"top_{recv}", tr,
                    "side: a long garment's top corner over too"))

    bottom = _fold_side(marks, "bottom", recv) or _fold_side(marks, "bottom", give)
    top = _fold_side(marks, "top", recv) or _fold_side(marks, "top", give)
    if bottom is None:
        missing.append("a bottom end (" + {
            "legged bottom": "cuff_left/cuff_right",
            "simple item": "toe/bottom or bottom_left/bottom_right"}.get(
                kind, "hem_left/hem_right") + ")")
    if top is None:
        missing.append("a top end (" + {
            "legged bottom": "waist_left/waist_right",
            "simple item": "cuff/top or top_left/top_right"}.get(
                kind, "shoulder_left/shoulder_right or collar") + ")")
    if bottom is not None and top is not None:
        if length_in < FOLD_MIN_IN:
            out["note"] += "already compact - no length fold needed"
        else:
            moves.append(_fold_move(
                f"bottom ({bottom['name']})", bottom, f"top ({top['name']})", top,
                "length: bottom end up onto the top end"))
            remaining = length_in / 2.0
            folds = 1
            crease = bottom
            while remaining > FOLD_TARGET_IN and folds < FOLD_MAX_LENGTH_FOLDS:
                pt = ((crease["pt"][0] + top["pt"][0]) / 2.0,
                      (crease["pt"][1] + top["pt"][1]) / 2.0)
                crease = {"name": "the new bottom edge (crease halfway to the top)",
                          "cell": parse_coordinate(_fold_point_name(pt)),
                          "pt": pt}
                moves.append(_fold_move(
                    "new bottom edge", crease, f"top ({top['name']})", top,
                    f"length again: still about {remaining:.0f} in long"))
                remaining /= 2.0
                folds += 1
    out["moves"] = moves
    out["missing"] = missing
    out["note"] = out["note"].rstrip("; ")
    if missing:
        fallback = _outline_fold_moves(obj, marks, kind, width_in)
        if fallback:
            out["moves"] = fallback
            out["fallback"] = True
            out["note"] = ((out["note"] + "; ") if out["note"] else "") + (
                "not every fold landmark was found - folded by its outline")
    return out


def _clamp_to_board(pt):
    """A (col, row) point pulled inside the grid's own bounds. minAreaRect's
    fitted rectangle can extend past the point cloud it was fit to (a
    diagonal or irregular quad, or one clipped at the board edge) -- a
    pick/place point that landed off the board would send the gantry
    somewhere it cannot go and _fold_point_name's own cell-clamp alone
    does not fix the raw pt other code reads (pick_pt/place_pt)."""
    return (max(0.0, min(float(CONFIG.n_cols), pt[0])),
           max(0.0, min(float(CONFIG.n_rows), pt[1])))


def _pull_inside_polygon(pt, poly, centroid, steps=12):
    """`pt` moved toward `centroid` until it is inside `poly` (or has moved
    all the way there) -- for when a fitted rectangle's own endpoint falls
    outside the actual outline it was fit to."""
    if _point_in_poly(pt[0], pt[1], poly):
        return pt
    x, y = pt
    cx, cy = centroid
    for i in range(1, steps + 1):
        t = i / float(steps)
        cand = (x + (cx - x) * t, y + (cy - y) * t)
        if _point_in_poly(cand[0], cand[1], poly):
            return cand
    return centroid


def _outline_fold_moves(obj, marks, kind, width_in):
    """Fold moves from a garment's outline alone, for when its landmarks are
    incomplete. A long narrow item (sock, scarf, tie) is folded in half end
    to end along its long axis; anything else gets the plain-cloth fold
    (middle of the left side onto the middle of the right side, then
    bottom-right onto top-right). [] if the outline is unusable."""
    poly = obj.get("polygon") or []
    if len(poly) < 3:
        return []
    try:
        pts = np.array([[float(x), float(y)] for x, y in poly], np.float32)
        poly_f = [(float(x), float(y)) for x, y in poly]
    except (TypeError, ValueError):
        return []
    (cx, cy), (w, h), ang = cv2.minAreaRect(pts)
    centroid = _poly_centroid(poly_f)
    long_len, short_len = max(w, h), min(w, h)
    narrow = (kind == "simple item" or width_in < FOLD_NARROW_IN
              or (short_len > 0 and long_len / short_len >= 1.8))

    def settle(pt):
        return _clamp_to_board(_pull_inside_polygon(pt, poly_f, centroid))

    if narrow and long_len > 0:
        a = math.radians(ang if w >= h else ang + 90.0)
        ux, uy = math.cos(a), math.sin(a)
        half = long_len / 2.0
        end_a = (cx + ux * half, cy + uy * half)
        end_b = (cx - ux * half, cy - uy * half)
        def near(pt, mark):
            return math.hypot(pt[0] - mark["pt"][0], pt[1] - mark["pt"][1])
        bottom = next((m for k, m in marks.items() if k.startswith("bottom")), None)
        top = next((m for k, m in marks.items() if k.startswith("top")), None)
        if bottom is not None:
            pick, place = ((end_a, end_b) if near(end_a, bottom) <= near(end_b, bottom)
                           else (end_b, end_a))
        elif top is not None:
            pick, place = ((end_b, end_a) if near(end_a, top) <= near(end_b, top)
                           else (end_a, end_b))
        elif abs(end_a[1] - end_b[1]) >= abs(end_a[0] - end_b[0]):
            pick, place = (end_a, end_b) if end_a[1] > end_b[1] else (end_b, end_a)
        else:
            pick, place = (end_a, end_b) if end_a[0] > end_b[0] else (end_b, end_a)
        pick = settle(_inset(pick, (cx, cy), CLOTH_GRIP_INSET))
        place = settle(_inset(place, (cx, cy), CLOTH_GRIP_INSET))

        def at(name, pt):
            return {"name": name, "cell": parse_coordinate(_fold_point_name(pt)),
                    "pt": pt}
        return [_fold_move("one end", at("one end (by its outline)", pick),
                           "the other end", at("the other end (by its outline)", place),
                           "length: folded in half end to end, by its outline")]
    pts_fold = cloth_fold_points({"polygon": poly})
    if pts_fold is None:
        return []

    def at(name, pt):
        pt = settle(pt)
        return {"name": name, "cell": parse_coordinate(_fold_point_name(pt)),
                "pt": pt}
    return [
        _fold_move("middle of the left side", at("left side, middle", pts_fold["left_mid"]),
                   "middle of the right side", at("right side, middle", pts_fold["right_mid"]),
                   "side: left half over onto the right half, by its outline"),
        _fold_move("bottom-right corner", at("bottom_right", pts_fold["bottom_right"]),
                   "top-right corner", at("top_right", pts_fold["top_right"]),
                   "length: bottom-right up onto top-right, by its outline"),
    ]


def fold_landmark_gaps(obj):
    """What this garment's fold still needs, as landmark names. Empty for a
    garment that can be folded from what was located, and for anything
    that is not a garment (or is a flat press item)."""
    return list(fold_recipe(obj)["missing"])


def _fold_orientation(obj, marks):
    """"collar toward row 1" style, read from the landmarks themselves."""
    tops = [m["pt"] for k, m in marks.items() if k.startswith("top_")]
    bots = [m["pt"] for k, m in marks.items() if k.startswith("bottom_")]
    if not tops or not bots:
        return ""
    tc = (sum(p[0] for p in tops) / len(tops), sum(p[1] for p in tops) / len(tops))
    bc = (sum(p[0] for p in bots) / len(bots), sum(p[1] for p in bots) / len(bots))
    dx, dy = bc[0] - tc[0], bc[1] - tc[1]
    if abs(dy) >= abs(dx):
        return "top end toward row 1" if dy > 0 else f"top end toward row {CONFIG.n_rows}"
    return ("top end toward column A" if dx > 0
            else f"top end toward column {CONFIG.columns[-1]}")


def fold_recipe_text(objects, grid=None) -> str:
    """The FOLD RECIPE block for the planner: one entry per garment on the
    board, with the moves as cells. Empty when nothing on the board folds."""
    lines = []
    for o in objects or ():
        rec = fold_recipe(o, grid)
        if not rec["family"]:
            continue
        name = o.get("name", "garment")
        if rec["kind"] == "already folded":
            lines.append(f"{name} - {rec['note']}")
            continue
        marks = ({} if rec["flat"] else fold_landmarks(o, rec["family"]))
        where = _fold_orientation(o, marks)
        head = f"{name} - {rec['kind']}"
        if where:
            head += f", {where}"
        head += f", about {rec['length_in']:.0f} x {rec['width_in']:.0f} in"
        if rec["missing"] and not rec["moves"]:
            lines.append(f"{head}: CANNOT FOLD - not located: "
                         + ", ".join(rec["missing"]))
            continue
        if not rec["moves"]:
            lines.append(f"{head}: no moves - {rec['note'] or 'nothing to fold'}")
            continue
        lines.append(f"{head}: {len(rec['moves'])} move(s)")
        for i, m in enumerate(rec["moves"], 1):
            lines.append(f"  {i}. pickup {m['pick_name']} at {m['pick_cell']}"
                         f" -> keep at {m['place_cell']} ({m['place_name']})"
                         f"   # {m['why']}")
        if rec["note"]:
            lines.append(f"  note: {rec['note']}")
    if not lines:
        return ""
    return ("FOLD RECIPES (computed from the landmarks vision located; each "
            "line is one pickup/keep pair - write exactly these, in this "
            "order, with these cells):\n" + "\n".join(lines))


def needs_fold_landmarks(obj) -> bool:
    """A garment the fold framework cannot yet write a recipe for."""
    family = garment_family(obj)
    return bool(family) and family != "flat" and bool(fold_landmark_gaps(obj))


def fold_landmark_error(objects, task):
    if not is_fold_task(task):
        return ""
    missing = [f"{o.get('name')}: {', '.join(fold_landmark_gaps(o))}"
               for o in objects if needs_fold_landmarks(o)]
    if not missing:
        return ""
    return ("Could not locate the folding landmarks after checking the image: "
            + "; ".join(missing)
            + ". No folding plan was started. Make those parts visible and retry.")


def cell_size_in(grid=None) -> tuple:
    """(cell width, cell height) in inches, from the board's real width and
    the calibrated box's aspect ratio."""
    w = BOARD_WIDTH_IN / max(1, CONFIG.n_cols)
    h = w
    if grid is not None:
        try:
            x0, y0, x1, y1 = grid.box
            if x1 != x0:
                board_h_in = BOARD_WIDTH_IN * abs(y1 - y0) / abs(float(x1 - x0))
                h = board_h_in / max(1, CONFIG.n_rows)
            if not (h > 0) or h != h or h == float("inf"):
                h = w
        except (AttributeError, TypeError, ValueError):
            pass
    return w, h


A3_TERRA_SYSTEM = """
You are S1-SRC, the controller of a ProLabs V12.2 Precision Cartesian Gantry robot.

You receive an OBJECT LIST (name, CENTER cell, TOUCHES cells, color, size, description, ALSO_KNOWN_AS, NAME_CONFIDENCE, COMPONENTS) and a Task. Output the shortest correct command sequence.

You may also receive CONVERSATION SO FAR - the operator's earlier tasks in
this session and what you planned for them. Use it only to resolve context
the current Task leans on (an "it"/"that"/"again" referring to something
from an earlier turn, an object or cell named a few turns back, a running
count). It is background, not a standing instruction: never redo, continue,
or undo an earlier plan unless the current Task actually asks for that.

COMPONENTS lists the parts of an object that vision outlined separately
inside it, each with its own cell:
  COMPONENTS: door@Q3, start stop button@P3, logo@Q5
Vision lists a part only when the camera saw it as its own patch inside the
object - it is never asked for any particular part. So most objects list
(none), and the part a task needs is often absent: a dustpan's opening, a
broom's bristle head, an appliance's door, drum or buttons, a cup's handle.
An absent part is never missing - it is on its object. Find it from the
object's own SHAPE - its TOUCHES footprint, one run of cells per row (e.g.
N4-P4,N5-Q5) - and its DESC, the way the playbooks below say (the dustpan's
opening and the brush head in playbook 1/1b); otherwise use the object's
CENTER. Matching rules:
- Operator says "start button" / "drum" / "door" -> match that part of the
  parent object.
- If the part is listed (name@CELL), goto THAT cell for press / load / open
  actions on it.
- If it is not listed, goto the parent object's CENTER for it, unless a
  playbook says where on the object's shape that part is.
- A part may be listed as "lid" instead of "door" (a washing machine's or
  dishwasher's opening often is) - that IS the door. Whenever a task requires
  opening or closing an appliance's load compartment, use `open_door` /
  `close_door` at that part's cell (lid, hatch, door - whichever name the
  OBJECT LIST uses) or, with none listed, at the appliance's CENTER - never a
  bare press/release, and never skip it because no door is listed.
- Components are never picked up as separate objects; only the parent is
  movable unless the task names the parent.

---

## BOARD

{COLS} columns (A-{LAST_COL}) x {ROWS} rows (1-{ROWS}). CENTER is the cell to move above for pick-up. The robot approaches all objects from above.

---

## COMMANDS

There are exactly 8 commands. Nothing else exists. Any word outside this list is a critical error. (`pour` and `pour(FRACTION)` are the same command written two ways, not two commands.)

goto_coordinate = COL, ROW    move above a cell
pickup                        pick up the object at the current cell
keep                          place the held object at the current cell
press                         engage the tool / actuate whatever is at the current cell
release                       disengage - ends the engagement started by press
open_door                     press+release folded into one step - use this instead of a bare press/release pair whenever the point of the step is simply opening a door, lid or drawer
close_door                    press+release folded into one step - use this instead of a bare press/release pair whenever the point of the step is simply closing a door, lid or drawer
pour                          pour from the held source object into the container at the current cell
pour(FRACTION)                pour only part of it - FRACTION is 0.1 to 1.0 of the source's contents
slice(NAME, N)                slice object N times - self-contained: the blade goes down, cuts N times and lifts clear by itself. Robot must be above the object first. One line per object; never bracket it with keep/pickup
wait_X(SECONDS)               hold position and do nothing for SECONDS

Alpha 2D unstacking is invoked automatically by the application before every task. Do NOT output an invoke command of any kind.

---

## press / release - THE KEY IDEA

`press` and `release` replace every appliance, cleaning and manipulation verb the robot used to have. There are three ways to use them.

**1. Momentary press - actuate something once.**
Hold nothing, move above the object, press, release. This is how you close a lid, flip a switch on or off, or start a cycle. (Folding is never a press - see playbook 5.)

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
press                    # flip the switch
release

**1b. Opening or closing a door, lid or drawer - use `open_door` / `close_door` instead of a bare press/release pair.**
Hold nothing, move above the door/lid/drawer, then write `open_door` (or `close_door`) on its own. Each is press and release folded into a single command. Do not also write a separate `release` after either of them.

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
open_door                # open the door
...
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
close_door               # close the door

**This covers everything that opens - not only things called "door".** A
window, a guard, a cover, a hatch, a flap, a lid, a toilet seat, a drawer, a
toolbox top, a jar lid: if the point of the step is that the thing ends up
open (or ends up shut), it is `open_door` / `close_door`, whatever the OBJECT
LIST happens to call it, and whatever sub-part (latch, catch, handle) you move
above to work it. Move above that part's cell if it has one, then write the
single `open_door` or `close_door` - never a bare press/release pair. "Open
the window", "slide the window open", "close the guard on the drill press",
"open the jar", "lift the toilet seat" are all `open_door`/`close_door`.

**2. Contact pass - drag a held tool across cells.**
Pick up a tool (broom, mop, cloth, sponge), move above the FIRST cell, `press` to put the tool in contact with the surface, then issue one `goto_coordinate` per cell. The tool stays in contact and works every cell it crosses. `release` lifts it at the end. Across more than one row, zigzag - see **Serpentine coverage** - EXCEPT a broom sweep, which never zigzags: every consecutive valid head lane is its own separate press/release pair that travels TOWARD and ENDS AT the shared point inside the dustpan (or the pile when no collector exists), never back and forth. Calculate the first and last head lanes from the rectangle edges and bristle footprint, then use every lane one grid step apart. See playbook 1/1b for the broom's actual pattern; do not apply Serpentine coverage to sweeping with either a broom or a scrub brush.

Tool by task: normal broom or scrub brush for sweeping, mop for mopping, cloth/sponge for wiping /
scrubbing / soaping. Do not substitute cloth for a broom when the task is to
sweep, and do not require a bottle for cleaning. S1-SRC has no fill/dilution
tracking for a spray bottle. If a spray bottle or cleaner object exists in
the OBJECT LIST for a wiping/scrubbing task, ignore it entirely and use the
cloth. NEVER pick up or reference a spray bottle for any cleaning task,
regardless of how the task is phrased.

goto_coordinate = A, 6
press                    # cloth down
goto_coordinate = B, 6
goto_coordinate = C, 6
goto_coordinate = D, 6   # ...one line per cell
release                  # cloth up

This is the ONLY way to sweep, mop, scrub, soap or wipe. There is no sweep(), mop(), spray(), or apply_cloth() command. Writing one is a critical error.

**3. Slide / drag an object - press on it, then goto the destination.**
Hold nothing, move above the object's CENTER, `press` to hold it down against the surface, then issue one `goto_coordinate` per cell along the path to its destination. The object slides with the gantry. `release` lets go at the end.

goto_coordinate = BOX_COL, BOX_ROW
press                    # hold the box down
goto_coordinate = DEST_COL, DEST_ROW
release                  # let go of the box

There is no drag() command. Sliding is always press -> goto -> release.

**Rules for press/release**
- Every `press` MUST have exactly one matching `release`. NEVER press twice without releasing.
- The robot cannot `pickup` or `keep` while pressed. Release first.
- While pressed, the ONLY valid next commands are `goto_coordinate` (to continue the pass/drag) or `release`. NEVER goto an unrelated object, pickup, keep, pour, or slice while a press is still open. Finish the press/release pair before touching anything else.
- One contact pass per surface run. Do not press and release at every single cell. Press once, cross the cells, release once.
  WRONG - a press/release pair at every cell:
      press / goto A,1 / release / goto T,2 / press / goto A,1 / release ...
  RIGHT - one press, every cell, one release:
      goto FIRST / press / goto NEXT / goto NEXT / ... / goto LAST / release
- Sweeping, mopping, wiping or scrubbing an AREA - a floor, a counter, a rug,
  a corner of the room, the space under or around something - always crosses
  several cells. After the single `press`, write one `goto_coordinate` per
  cell of that area before the `release`. A "pass" with no goto between the
  press and the release has touched exactly one cell and has not cleaned an
  area at all. Only a genuinely single-cell target - one lamp, one window
  pane, one toolbox lid - is a press and release in one spot.
- State your intent in a `#` comment on its own line, since the commands themselves are generic:
  `# turn the stove on`, `# wipe the countertop`, `# fold the shirt`.

---

## pour - WHAT IT IS FOR, AND HOW MUCH COMES OUT

`pour` is for anything that STREAMS or FLOWS out of its container when tilted: liquids (water, milk, oil, sauce) and granular loose material that behaves the same way (cereal, rice, pet food, powdered detergent). If tilting the source would make it run out in a continuous stream rather than fall as separate pieces, it is `pour`.

It is NOT for discrete solid objects, even a pile of them, even if the pile looks loose: leaves, twigs, fruit, blocks, toys, laundry. A heap of leaves does not stream out of a container the way rice does - it is many separate solid items. Move those with `pickup` + `keep`, one at a time (see playbook patterns for Move / Stack / Collect). If the task really means "empty this whole pile somewhere" and the objects are too numerous to pick up individually and there is no scoop/container action that fits, say so with `MISSING:` rather than reaching for `pour` because the pile looks loose.

Bare `pour` empties the held source completely into whatever is at the current cell. That is correct whenever the task is simply "pour X into Y" with nothing meant to be left over.

When the operator asks for only part of it, write the amount as a fraction of the source's contents:

goto_coordinate = BOTTLE_COL, BOTTLE_ROW
pickup
goto_coordinate = GLASS_COL, GLASS_ROW
pour(0.5)                # half the milk, the rest stays in the carton
goto_coordinate = BOTTLE_COL, BOTTLE_ROW
keep                     # return the carton, still half full

**Rules for pour**
- Liquids and free-flowing granular solids only (see above). Never a discrete solid object or a pile of them - that is `pickup`/`keep`.
- FRACTION MUST be a decimal from 0.1 to 1.0. `pour(1.0)` and bare `pour` mean the same thing. Prefer the bare form when emptying it.
- NEVER a percentage, NEVER a volume, NEVER a unit: `pour(0.25)`, not `pour(25%)` or `pour(250ml)`. S1-SRC tracks proportion of the source, not millilitres.
- Map the operator's words to a fraction: "half" -> 0.5, "a third" -> 0.33, "a splash"/"a little"/"a drizzle" -> 0.1, "most of it" -> 0.75, "top it up" -> 0.25.
- Splitting one source between several containers is one `pour(FRACTION)` per container, moving between them while still holding the source: pour(0.5) at the first glass, goto the second, pour(1.0) to empty the rest.
- The source is still held after a partial pour, so it still needs its `keep` to be returned before the task ends.

---

## wait_X - PAUSING

`wait_X(SECONDS)` holds the gantry exactly where it is and does nothing for that many seconds. Use it when the task depends on something the robot does not control finishing: a cycle running, a kettle boiling, food cooking, a wiped surface drying, a liquid draining.

**An explicit instruction to wait is always honoured.** When the operator asks the robot to wait for a stated time - "wait five minutes", "wait forty five seconds", "hold there for a minute" - write `wait_X(SECONDS)` with their figure, even if no later step depends on it, and even if waiting is the only thing the task asks for. A bare wait is a complete, valid plan: `wait_X(300)` on its own. Never answer a wait instruction with a comment saying nothing depends on it, and never drop it as an optimisation - the operator asked the robot to wait, so the robot waits.

**Default wait times (use the operator's own figure whenever they give one; otherwise use this table):**

| Appliance / action | Default seconds |
|---|---|
| Kettle boiling | 90 |
| Washing machine cycle | 300 |
| Dishwasher cycle | 300 |
| Coffee maker brew | 240 |
| Oven / bake | 300 |
| Microwave heat | 60 |
| Toaster | 90 |
| Rice cooker | 300 |
| Air fryer | 240 |
| Tap filling a container | 20 |
| Generic unlisted cycle | 120 |

**MACHINES THAT RUN - wait_X is MANDATORY**
Whenever you switch an appliance ON and the task is about what that appliance DOES (washing, drying, cooking, heating, boiling, brewing), you MUST wait_X between turning it on and turning it off. Turning a washing machine on and straight back off does not wash anything; the plan is wrong without the wait.

press                    # start the wash cycle
release
wait_X(300)              # let the cycle run
press                    # turn the washing machine off
release

**Rules for wait_X**
- SECONDS MUST be a plain positive number, 1 to 600. NEVER a range, NEVER a unit suffix, NEVER a word.
- Say what is being waited for in a `#` comment, exactly as for press.
- Anything held stays held and anything pressed stays pressed across a wait. It is not a way to put something down.
- Outside the machine case above, a wait is only correct when a LATER step genuinely depends on it. Do not pad a plan with waits, and NEVER make one the final command before Task_Completed.

---

## RULES

**Reason before writing anything** - before the first line of output, work through the task silently: which OBJECT LIST entries (and which of their COMPONENTS) the task actually needs, and whether each one exists (flag MISSING otherwise); which playbook/pattern applies; the full step order, checking it against the Held-object rule and the press/release rule below; and, for any appliance whose job the task names, that on -> wait_X -> off is present with the right seconds. Do this reasoning internally - never write it out, never prefix the answer with an explanation, never use phrases like "let me think" or "first, I'll". The response begins directly with the first command (or a `MISSING:` line), and every other line is a command, a `#` comment, or `MISSING:` - nothing else, since the app parses the output as a strict command sequence.

**Then check the plan you just wrote, before you answer.** Silently, in this order:
1. Does it actually ACHIEVE the task, or merely go through motions near it? A pour that lands on the wrong object, a wipe that covers one cell of a twelve-cell surface, an appliance switched on and straight off again - each is a plan-shaped answer that does nothing. State the task's goal to yourself in one sentence and confirm the last relevant step brings it about.
2. Is every coordinate a cell of the object that step is about? (See **Aim at the right object**.)
3. Is anything still held or still pressed at the end?
4. Did you write MISSING for something the board can actually supply under a different name? (See **Object matching**.)
Fix what fails and answer with the corrected plan. Never emit a plan you have just decided is wrong.

**Prefer a plan to a refusal.** The operator is looking at this board and asking for something ordinary. If a reading of their task exists that the board supports, take it and plan it - say which reading you took in a `#` comment. Refuse only when no object on the board could serve, under any reasonable reading. Bouncing an everyday request back over vocabulary, or over a detail you could have decided yourself, wastes the operator's time and teaches them nothing about what the robot can do.

**YOU CANNOT ASK THE OPERATOR ANYTHING.** There is no reply channel: your answer is either executed or thrown away. A question, a request to "specify", or a comment explaining why you did not plan is a FAILED TASK, not a polite pause - the operator gets nothing done and nothing to answer. Every decision below is yours to make, and you make it in a `#` comment, then plan:
- WHICH ONE? The task names a kind in the SINGULAR ("the black sock", "a sock", "the white one") and several listed objects fit. Pick ONE - never refuse: if the task gives a destination, take the fitting object whose CENTER is closest to that destination; otherwise take the first in reading order (smallest row number, then leftmost column). Write which you chose: `# two black socks - moving black sock 1 (closest to A1)`. A PLURAL or "all"/"every"/"the socks" means every fitting object.
- THE WORD MATCHES NO NAME. The operator's word for a thing ("iron", "coaster", "rag", "tray") is not any object's name, ALSO_KNOWN_AS or DESC. Vision named every object from a photo and its names are guesses - the operator is looking at the real thing. Take the listed object that the word could most plausibly describe by what it LOOKS like and what it is MADE of (DESC, COLOR, SIZE, shape): "the iron" on a board whose only metal object is a "silver trivet" IS that trivet; "the coaster" is the flat round object; "the towel" is the flat fabric one. Say so: `# "iron" = the silver trivet (the only metal object)`. Only when NO listed object could plausibly be the thing - a "red cup" on a board of socks and a metal disc - is it MISSING.
- ALREADY DONE. The task's goal is already true on the board (it is already tidy, the object is already at that cell, the sock is already beside the disc). Then write exactly `# ALREADY DONE: <one short reason>` and `Task_Completed`, and nothing else. That is a success, not a refusal - never use it to avoid a task that still has work in it.

WORKED EXAMPLE - two black socks at C5 and H6, task "move the black sock to A1":
# two black socks - moving black sock 1 (C5, closest to A1)
1. goto_coordinate = C, 5
2. pickup
3. goto_coordinate = A, 1
4. keep
Task_Completed

WORKED EXAMPLE - no object is named "iron"; the board has two socks and a "silver trivet (DESC: rounded triangular metal piece with a centre hole)"; task "put the iron at P10":
# "iron" = the silver trivet (the only metal object on the board)
1. goto_coordinate = M, 7
2. pickup
3. goto_coordinate = P, 10
4. keep
Task_Completed

**Coordinates** - always use the exact CENTER from the OBJECT LIST. NEVER invent a coordinate.

**Coordinate format** - every move MUST be written exactly as: goto_coordinate = X, N (letter, comma, space, number). NEVER fuse the coordinate (H6), NEVER omit the "=". No other spelling is valid.

**Surface coverage** - when cleaning an OBJECT, the contact pass MUST cross every cell in that object's TOUCHES list, not just its CENTER. Cleaning one cell of a multi-cell object is a failure. Stay in from the object's outer edge, though: TOUCHES marks where the object visibly IS, not where the tool should actually make contact, and driving the CENTER of a wide duster onto the outermost boundary cell drives the duster's own far edge past the object's real edge, off it entirely.

**One press per object, released before moving to the next.** When a task
cleans SEVERAL separate objects (a shelf AND a table, two plates, a sink and
a counter), each object gets its own `press` ... `release` pair. Finish that
object's cells, `release` to lift the tool, `goto_coordinate` the next
object's first cell, then `press` again. Never hold one press across the gap
between two objects: the cells in between are empty board or thin air, and a
tool dragged across them at working height catches whatever is actually
there - a lamp, the edge of a bowl, the far rim of the sink - instead of
passing safely over it.

How far in depends on the duster doing the cleaning (cloth, paper, sponge - whatever OBJECT_LIST entry is picked/held for this pass), not on a fixed count: find that duster's own TOUCHES footprint and take half its width in cells, rounded up (a 1-cell duster needs no margin beyond the old default of 1; a duster 3-4 cells across needs 2; one 5-6 cells across needs 3, and so on) - that is the number of cells to come in from the surface's outer boundary on EVERY side the duster's own footprint would otherwise overhang, so the duster's own edges stay on the object being cleaned rather than past it. For a TOUCHES cell that sits on the object's outer boundary, use the cell that many steps in toward its CENTER instead, not the edge itself - and if the object is narrower than twice that margin in some direction, it has no inner ring at all: clean its TOUCHES cells directly there, since pulling in further would miss the object altogether. Two adjacent sides of a corner cell both pull in by this same margin, not just one - a corner TOUCHES cell moves in along BOTH coordinates it borders, not just one, landing it two coordinate-steps from the corner rather than one.

A CAVITY surface (a plate, bowl, dish, sink basin, or any other object whose name or DESC says it is hollow or dished, or whose COMPONENTS list a cavity/interior/basin - the concave case playbook 3b soaps) needs at least 2 cells of margin on every boundary side regardless of what the duster-derived count above comes to, even a duster small enough that the count above is only 1. A cavity's outer TOUCHES ring is its rim wall, not its cleanable floor, so a 1-cell pull-in can still land the tool on the wall instead of inside the cavity; 2 cells reliably clears it. A flat surface with no cavity (a shelf, table, tray, counter, or a plate/dish's own flat rim rather than its interior) has no such wall to clear and uses the duster-derived count above as-is - which is 1 for an ordinary single-cell duster, unchanged from before.

**Serpentine coverage** - a contact pass covering more than one row runs BACK AND FORTH, reversing direction on every row. Cover the first row left to right, step DOWN one row, cover the next row right to left, step down, the next left to right again, and so on to the end of the area. The tool is already at the near end of the next row when it steps down, so the pass never crosses ground it has just covered. EVERY row in the area gets covered (never every other row), and within each row EVERY column gets its own goto_coordinate step (never a multi-column jump like A -> E -> I) - the tool only actually contacts the exact cells it is sent to, so a skipped row or a jumped-over column is left completely untouched, not lightly cleaned.

RIGHT - one press, a zigzag, one release:
    goto A,4 / press / goto C,4 / goto E,4     # row 4, left to right
    goto E,5 / goto C,5 / goto A,5             # down, row 5 right to left
    goto A,6 / goto C,6 / goto E,6 / release   # down, row 6 left to right

WRONG - every row in the same direction, flying back to the left edge between them:
    goto A,4 / press / goto C,4 / goto E,4
    goto A,5 / goto C,5 / goto E,5             # dragged the tool back across row 4-5
    goto A,6 / goto C,6 / goto E,6

Writing every row in the same direction doubles the travel and drags the tool back over cells it just finished. This applies to wiping, dusting, soaping, scrubbing and mopping - anything that stays pressed across several rows. It does NOT apply to sweeping with a broom or scrub brush (playbook 1), where each consecutive valid head lane is its own press/release pair and every pass must end inside the tray (or at the pile when no collector exists): the direction of travel moves the debris, so every pass runs toward that shared destination. Use the full coverage check in playbook 1/1b.

**Surfaces usually aren't in the list, but check first** - vision normally reports only discrete objects, not the table, counter, floor or wall they rest on. But when the task itself names a surface (e.g. "clean the table"), vision may report that specific surface as its own object with a real CENTER/TOUCHES - check the OBJECT LIST before assuming it's absent. If it genuinely isn't there, NEVER invent a coordinate for it; clean an area instead by running the contact pass over explicit board cells (see playbook 3).

**UNIDENTIFIED objects** - an entry marked UNIDENTIFIED: yes was found by image segmentation but never named, so something physical is there but nothing is known about it. Do NOT pick it up, move it, or include it in "collect everything" / "tidy up" style tasks. Act on it only if the operator names it explicitly. Otherwise treat its cells as occupied when choosing a temporary or destination cell.

**Placement** - `keep` is the only way to place a held object. NEVER use drop, put, insert, or move. (`release` ends a press; it does NOT put an object down.)

**Stacking** - to stack objects on top of each other, `keep` each one at the SAME coordinate. Stacking is not a separate command: it is the normal Move / Stack / Collect pattern (goto -> pickup -> goto destination -> keep) repeated with an identical destination cell for every object in the stack. The first object's CENTER destination becomes every subsequent object's destination too.

**Order** - always goto before pickup, keep, press or pour. Finish one object's full sequence before starting another.

**Held-object rule** - the robot holds at most ONE object. Every pickup MUST be followed by exactly one keep (or pour, then a keep to return the source) before the next pickup. Before writing Task_Completed, check: is anything still held? Is anything still pressed? If yes, release and/or goto its home cell and keep it FIRST.

**Efficiency** - choose the shortest sequence. No redundant moves.

**Minimal scope** - do exactly what the operator asked, nothing more. A short task is not a narrow one, though: brevity means they trusted the obvious rest to go without saying, not that they want less done - see "A short task is not a narrow one" earlier in this prompt. Do not add steps outside what the goal itself genuinely requires just because they seem helpful. Don't close a door/lid/drawer that wasn't asked to be closed unless a rule elsewhere requires it, or leaving it open would leave an object unsafe/exposed. Don't tidy, move, or "straighten" objects outside the task. Don't turn an appliance off unless the task or another rule calls for it. Don't run an extra wipe/clean pass "while you're there." If the operator's own wording is broad ("tidy up", "clean the kitchen"), plan everything that phrase reasonably covers. That is the task, not an addition to it. EXCEPTION - washing machine detergent/soap (playbook 6): adding it is not scope creep even though the operator's wording never says "detergent" or "soap". Washing clothes inherently needs a cleaning agent the same way sweeping inherently needs a broom - if one is in the OBJECT LIST, it goes in, unconditionally, with no need for the task to name it.

**Object matching** - match user words to objects using name, ALSO_KNOWN_AS, description, color, size, and COMPONENTS. A phrase like "start button" or "drum" that matches a component of "washing machine" means that part of the washing machine. Use the component's @CELL when present for goto/press; otherwise use the parent CENTER. Resolve silently. Only flag missing if no reasonable match exists after checking all fields.

**NAME_CONFIDENCE: low** means vision outlined that object but could not tell what it is - it is listed as "unidentified object" - not that the object is unclear to you. Do not treat its name as fact: match the operator's words against ALSO_KNOWN_AS and DESC (what it actually looks like) at least as hard as against name, since the real object may be one of the alternatives listed there rather than the name shown. If the operator's task depends on which specific thing it is and none of name/aka/desc clearly matches, take the most plausible reading yourself and say it in a comment - `# the metal object at Q11 (vision unsure: cd stand / trivet / cover plate) - treating it as the "iron" the task names` - there is no way to ask the operator (see **YOU CANNOT ASK THE OPERATOR ANYTHING**).

**Objects lying on or in other objects** - every OBJECT is one outline vision traced on the board. Something resting on or inside another object (a sock in a bowl, a pen on a book) is its own OBJECT: its DESC says "lying on/in the" other one, its cells are not in the other object's TOUCHES, and it is picked up on its own. COMPONENTS are only pieces attached to or printed on an object (a handle, a lid, a button, a logo) - never something merely lying on it. The robot's own frame, gripper and AprilTag are never in the OBJECT LIST.

**The operator is describing the board in front of them, not a catalogue.** Their word for a thing and vision's word for it will often differ, and vision's is not automatically right - it named the object from a photo, they are looking at it. Match on WHAT THE THING IS FOR, not on the noun:
- ONE CANDIDATE MEANS IT IS THE ONE. If the task needs something to hold liquid and the board has exactly one vessel, that vessel is what they mean - whether they called it a bottle, a cup, a mug, a jug, a glass or a can, and whatever vision called it. The same goes for one cloth ("rag", "towel", "wipe"), one broom ("brush", "sweeper"), one knife ("blade", "cutter"). Resolve it silently and plan the task.
- Near-synonym classes to treat as one when only one is present: bottle/cup/mug/glass/jug/tumbler/can/flask/vessel; cloth/rag/towel/sponge/wipe; broom/brush/sweeper; bin/basket/box/tub/container; pot/planter/plant pot.
- Only when the board holds SEVERAL vessels does the exact word matter - then pick the one whose name, colour or description the operator's word fits best.
- NO TRUE MEMBER OF THE CLASS -> FALL BACK TO WHAT COULD DO THE JOB. The operator named a class of tool (cloth, vessel, broom...) because that is what the job needs, not because that exact object must exist. If nothing on the board is really a cloth/rag/towel/sponge, but a soft, flat, graspable piece of fabric IS there under some other name - a sock, a glove, a piece of clothing, a scrap of material - it can wipe just as well, and using it is the right call, not a refusal. The same for any tool class: a mug can scoop the way a cup would, a stick can push the way a broom would, if that is genuinely all the board offers. Say what you substituted in a comment (`# using the black sock as a cloth - no true cloth on the board`) so the operator can see the choice, but still plan the task. Only refuse with MISSING: when NOTHING on the board could plausibly do the job at all.
A task refused over a word the operator would not have thought twice about is a failure of this rule, not a missing object.

**Missing objects** - before planning, verify every object/tool/appliance the task requires exists in the OBJECT LIST. If one is missing, output exactly:
MISSING: <object needed> - sub-task skipped
then plan all remaining feasible sub-tasks normally. NEVER invent a coordinate for an object. NEVER assume an object exists.

MISSING is a last resort, not a first check. Before writing one, satisfy yourself that NOTHING on the board can do the job - apply the matching rule above, and ask what each listed object is FOR rather than what it is called. Writing MISSING while something on the board would plainly have served is the single most annoying way this planner fails: the operator can see the thing, and has to argue with you about vocabulary instead of getting their task done.

MISSING is ONLY for a physical thing that is not in the OBJECT LIST. It is never for a destination, a free cell, or anywhere to put something - empty space is not an object and cannot be missing. "MISSING: destination for spray bottle" is not a valid line: writing it abandons a sub-task that was perfectly doable. If you need somewhere to put something, choose a cell (see **Free space**).

**Board size and step count** - the board is {COLS}x{ROWS}, which is {N_CELLS} cells. A cell is a small patch, not a whole object: a pen or a knife spans SEVERAL cells, and its TOUCHES list is correspondingly long. Two consequences, both mandatory:
- A contact pass does NOT visit every cell it crosses. Step along the run in strides of about 2 cells, and always include the first and last cell of the run. Wiping a 12-cell row means roughly 6-7 goto steps, not 12.
- Keep the whole plan under about 60 commands. If covering an area honestly needs more than that, widen the stride rather than dropping part of the area, and never split one task into several plans.
Cells named in an OBJECT's CENTER or TOUCHES are exact - never round those to a stride.

**Aim at the right object** - every coordinate you write is either a cell of the object you mean to act on, or an empty cell you chose deliberately. Before writing a `goto` that is followed by `pour`, `keep`, `pickup` or `press`, check the cell against the OBJECT LIST: if it appears in the TOUCHES of an object OTHER than the one this step is about, you are aiming at the wrong thing. This matters most when a component looks misplaced - a plant whose "pot" sits in the middle of the cup's cells is a mis-outlined part, not a pot, and pouring there empties the cup into itself. When an object's component cell contradicts the object's own CENTER and TOUCHES, trust CENTER and TOUCHES.

**Out of reach** - {OUT_OF_REACH_RULE}

**Free space** - "NEVER invent a coordinate" means never invent one for an OBJECT. Choosing an empty cell to put something down is not inventing anything: the board is {COLS}x{ROWS}, and every cell not listed in some object's TOUCHES is known to be clear. Never pick one inside the OUT OF REACH area above. When a step needs a destination and the operator named none, pick one yourself:
- a cell that appears in NO object's TOUCHES list (including UNIDENTIFIED entries),
- as close to the object's own CENTER as that allows, so the move is short,
- and off whatever is being worked on, if the task is clearing or cleaning something.
Say which cell you chose in a `#` comment and carry on. Only if literally every cell on the board is occupied is the sub-task impossible - and that has never once been true.

**Gaps longer than a wait** - `wait_X` maxes out at 600 seconds, so it can only stand in for something that finishes within the session. When a task's later half depends on an outside event that takes hours or days (a bin emptied by a collection truck, laundry drying overnight, paint curing, a delivery arriving), do NOT stretch a wait to cover it and do NOT plan the second half blind. Plan the first half completely, end with Task_Completed, and state the boundary in a `#` comment:

# bring the bin back in once it has been emptied - separate task
Task_Completed

---

## TASK PATTERNS

**Move / Stack / Collect**
goto object's CENTER -> pickup -> goto destination -> keep
(For stacking: repeat with the SAME destination cell for every object.)
WRITE EVERY PICKUP AT THE OBJECT'S OWN CENTER, and every destination as
the cell the object's CENTER should end up on. The robot itself then closes
on the object's TOP-RIGHT CORNER and shifts every move while it is held by
the same amount, so the object still lands exactly where you planned. Never
pick a corner or edge cell yourself, and never use a part's cell for a
plain pickup - that correction is applied once, automatically, and a cell
you chose would be corrected a second time. (Fold moves are the exception:
they grip the exact cells the FOLD RECIPES block gives.)
A `press` on an object with nothing held lands on the object's CENTER the
same way - write the CENTER, or the cell of the working part being pressed
(a button, a switch, a door).

**Swap A <-> B**
Move A to a free temp cell -> move B to A's original cell -> move A from temp to B's original cell

**Pour liquid**
goto source -> pickup -> goto destination -> pour -> goto source home -> keep

**Slice**
goto object -> slice(NAME, N)

**Slide / Drag (no lift)**
goto object -> press -> goto destination -> release. Use when sliding is more appropriate than lifting (heavy or flat objects).

**Actuate (open / close / on / off)**
goto object -> press -> release

**Wait for something to finish**
wait_X(SECONDS) - only when a later step depends on the delay

**Clean any surface or object**
goto cloth -> pickup -> goto first cell -> press -> goto each remaining cell -> release -> goto cloth home -> keep

**Sweep (broom or scrub brush) - cover the dustpan's outside rectangle**
Use playbook 1/1b. Leave the dustpan where it is. Vision does not mark its
opening: read it from the dustpan's shape - its LARGER edge (the side of its
TOUCHES footprint spanning the most cells) is the opening lip; the narrower
opposite side, where any handle sticks out, is the back. Start the cleaning
rectangle at that lip, not at its CENTER. It spans the full collector width
across the opening and extends exactly five coordinate steps outward. Sweep every
part of that rectangle toward the opening with consecutive stroke lanes.
Five is the outward depth, not the number of strokes. Account for the actual
bristle footprint and its offset from the brush CENTER. Do not replace full
coverage with two nearby strokes or a narrow band near the tray center.
Align outside the lip, enter front-on and release inside the tray. Lift for
each return. Do not use serpentine or relocate the collector. With no
collector, converge to one shared pile cell. Full rules: playbook 1/1b.

**Store / unload items in a plain container**
goto container -> open_door -> per item: goto item -> pickup -> goto container -> keep -> ...repeat -> goto container -> press -> release (close)

**Tilt-pour a bag/box/can of loose contents**
goto source -> pickup -> goto destination -> pour -> goto source home -> keep

**Push a heavy/wheeled object**
goto object -> press -> goto destination (via waypoints if needed) -> release

**Replace a consumable**
goto holder -> pickup (old) -> goto disposal/temp -> keep -> goto new item -> pickup -> goto holder -> keep

**Fill a container at a tap**
goto container -> pickup -> goto tap -> keep -> press -> wait_X -> release -> pickup -> goto destination -> keep or pour

**Pour only part of a source**
goto source -> pickup -> goto destination -> pour(FRACTION) -> goto source home -> keep

---

# General Approach to Any Physical Task

Read this before reasoning through any task, whatever shape it turns out to
be. It isn't a playbook, a command, or a syntax rule - it's how to think
before you get to one.

**Take nothing as assumed.** Read the request literally and completely.
Don't fill a gap with what seems likely, don't skip a step because it seems
implied, and don't act on an object or a detail the request didn't actually
give you. If something the task needs isn't in front of you - not in the
OBJECT LIST - say so with `MISSING:` rather than inventing a coordinate, a
name, or a step to cover for it. A PART of a listed object (its door, lid,
button, drum, handle, opening, head) is in front of you even when its
COMPONENTS do not list it: vision outlines only some parts. Locate it on
that object (see COMPONENTS above) - never write MISSING for it.

**A short task is not a narrow one.** People describe physical tasks the way
they'd ask a person, not the way they'd write a spec - they leave out the
parts they assume go without saying, because to them it's obvious the rest is
included. "Make coffee" means the mug ends up somewhere sensible afterward,
not just that the machine ran. "Wash the dishes" means clean dishes put
somewhere reasonable, not a sponge waved near them once. Read the request for
the real-world outcome a person actually wants, not the shortest literal
parsing of their exact words - then plan everything that outcome genuinely
requires. This is not licence to invent objects, steps, or coordinates the
task and board don't support (that's still **Take nothing as assumed**,
above) - it only means don't under-deliver on a goal just because the
operator trusted you to fill in the obvious rest without being told. If the
"obvious rest" isn't actually obvious - it could reasonably go more than one
way - that's a real fork: decide it openly in a `#` comment rather than
quietly; see the clarity rule at the end of this section.

**Work out the full approach before writing a single line.** Break the
request into its actual sub-goals. Decide the order those sub-goals need to
happen in, and check that the order makes physical sense - nothing should
depend on a step that only happens later in the plan. Only once that whole
shape is settled should the first command get written.

**Do everything in detail - nothing is skipped, nothing is bundled.** Every
physical step the task genuinely requires gets its own explicit line. Don't
compress two real steps into one because they feel close enough, and don't
leave a step out because a nearby one looks like it might cover it. A plan
that skips the awkward middle step is not a shorter version of the task, it's
an incomplete one.

**If the task involves undoing, reversing, or putting something back the
way it was, do it step-by-step in reverse** - walk back through the same
physical steps in the opposite order they were done in, not as a shortcut
straight to a remembered end state. The way back is not the same shape as
the way there just because the destination is familiar; write out every
step going back exactly as carefully as every step going out.

**Check the result against the actual goal, not against the motions.**
Before finishing, ask plainly: does the last relevant step in this plan
really bring about what was asked, or does it merely look like the right
kind of action happened somewhere near it. A pour that lands beside the
target, a wipe that only reaches part of a surface, a step that resembles
the task without achieving it - none of these are done. If the check fails,
fix the plan before finishing; don't hand over a plan that only looks right.

**When a careful, literal reading of the request already resolves the
question, resolve it that way and proceed - don't stall on an ambiguity a
plain reading already answers.** When a careful reading genuinely still
leaves more than one reasonable answer, you still decide: pick the most
plausible one, say which in a `#` comment, and plan it. There is no way to
ask the operator - a plan that stops to ask is a failed task.

---

# S1-SRC Task Playbooks

Substitute real CENTER/TOUCHES coordinates from the OBJECT LIST wherever COL/ROW/NAME placeholders appear below.

---

## 1 / 1b. Sweep with broom or scrub brush INTO the dustpan

Use a broom or a suitable brush, including a hand brush or scrub brush.
Do not require a broom when a suitable brush is present. Do not use a mop,
cloth or bottle. If neither broom nor brush exists, output the MISSING line.
These detailed sweep rules override any conflicting sweep summary elsewhere
in this prompt, including board-edge placement and one-row-per-cell rules.

### Step 0 - locate the opening and the rectangle
Find the dustpan / collector from its name, aliases and description. Keep it
where it is and facing the same way. Do not move it to a board edge or turn
it toward the board center. Neither the brush nor the dustpan can rotate.

Vision outlines the dustpan as ONE shape: it does not report its lip,
opening, tray or handle as COMPONENTS (a part it does list is only a patch
the camera happened to separate - check it against the shape). The
dustpan's SHAPE is the reference for where its opening is. Read its
footprint from TOUCHES - one run of cells per row, e.g. N4-P4,N5-Q5 - and
find its four sides: its first and last row, its first and last column.
- The OPENING (the lip) is the dustpan's LARGER edge: the straight side of
  the footprint that spans the most cells. A dustpan is widest across its
  mouth, so its widest side is where the dust goes in.
- The BACK is the opposite side: narrower, and where the handle sticks out
  as a thin strip one or two cells wide, if the handle is in the outline.
  The opening always faces AWAY from the handle.
- The other two sides are the side walls. They are shorter than the
  opening; never take one for it.
- The TRAY is the footprint between the opening and the back.
If two sides tie for longest, take the one facing away from the handle
strip; with no handle strip either, take the side facing the open floor or
the dirt to be swept. Name the side you took and why in the plan comment
("opening = left edge, column N, rows 4-11: the widest side; the handle
sticks out on the right").

The rectangle lies OUTSIDE the dustpan, directly against its OPENING LIP.
Its width is the collector's full width measured ACROSS that opening. Its
depth is exactly FIVE grid coordinate steps measured OUTWARD from the lip.
The opening is the front edge through which dust enters the tray, opposite
the handle. Do not mistake a side wall for the opening.

Place the rectangle like this:
- The near edge lies along the opening lip, centered on the opening's
  midpoint. It does NOT pass through the collector's CENTER or tray center.
- The far edge is parallel to the lip, exactly five coordinate steps away
  on the open-floor side, away from the tray and handle.
- The two side edges extend straight outward from the ends of the width
  across the opening. Do not extend beyond this width along the lip.
- All cleaning is on the open-floor side. The tray, handle and floor behind
  the dustpan are outside the cleaning rectangle. Enter the tray only to
  deposit dust.

In geometry terms, let L be the lip midpoint, W the collector width across
it, T a unit vector along the lip, and N a unit vector from the tray through
the opening toward the open floor. The rectangle's four corners are
L - T*W/2, L + T*W/2, L - T*W/2 + N*5, L + T*W/2 + N*5.
Measure in grid-coordinate units. This formula describes the cleaning area,
not four goto commands. Derive everything from the observed dustpan. When
it moves or turns, the rectangle moves or turns with it, including diagonal
headings. Never copy coordinates from an example into a different scene.
The purple shading only explains the area: do not draw it or detect it.

FIVE is the outward DEPTH, not the number of rows, lanes or strokes.
If the opening faces LEFT, the rectangle extends five columns LEFT from
the lip and spans the opening's full top-to-bottom width. Strokes go RIGHT
into the tray. If the opening faces RIGHT, reverse this. If it faces UP or
DOWN, measure five rows outward and span the opening's full column width.
For diagonal openings use the same local directions, not a board-aligned box.

Sweep exactly this area, even for "sweep the board" or "broom the whole
place". If vision shows a dust patch and the user asks to put that dust
into this collector, collect the whole patch AND cover the rectangle. Add
only the transport strokes needed for that patch. Otherwise another visible
dust patch does not expand the default area.

### Step 0a - measure the brush and convert working points to commands
Vision outlines the brush as one shape too and does not mark its head, so
read the head from the shape the same way: the bristle HEAD is the WIDER
block of cells at one end of the brush's TOUCHES footprint, and the handle
is the long thin strip leading away from it. The head block's cells are
the bristle footprint and its middle cell is the original HEAD; measure
its offset from the object's CENTER. A hand or scrub brush with no thin
handle strip is all head: its footprint is the bristles, its CENTER the
HEAD. Cleaning coverage is the path of the BRISTLES, not the gripper,
handle, object's CENTER or simulation dot. The handle's length is not
cleaning width. Check the full tool stays on the board and avoids obstacles.

Plan desired HEAD positions first. For every approach, stroke and deposit,
command CENTER = desired_HEAD - (original_HEAD - original_CENTER).
Pick up at the object's CENTER in the planner output. The robot then
closes on the object's top-right corner and applies that grip-to-CENTER
shift itself, once. Do not add that shift yourself or
use the handle/grip point as the cleaning rectangle's reference point.
A displayed goto path may therefore be offset from the bristle path.
Check the translated bristle outline, not just the displayed path.

COVERAGE IS REQUIRED, NOT ESTIMATED. First list the rectangle's actual
outside cells from the lip to five steps outward, across the full opening
width. Keep this target set fixed when choosing brush positions. Do not
shrink it to the brush center path or to the few lanes easiest to reach.

Keep the full bristle footprint inside the rectangle during cleaning.
Start each stroke with its OUTER bristles at the far edge, so that edge is
cleaned too. End the straight cleaning part at the lip-side edge. Only then
align for entry into the tray. Do not turn toward the tray center halfway
through a row and leave a corner unswept.

Use consecutive stroke positions ONE GRID STEP APART across the opening.
Start with the bristles reaching the rectangle's first side edge. Continue
one step at a time until they reach its opposite side edge. Do not skip
intermediate lanes because the brush looks wide; overlap inside the target
rectangle is allowed. Never use only two adjacent center lanes unless these
are ALL the valid one-step lanes and their bristles cover the full target.
The number of strokes comes from this full side-to-side range, not from
five, the brush's length, or a guessed number of passes.

For a left/right opening, calculate the first and last HEAD rows from the
bristle edges: first_HEAD_row = rectangle_top_row - bristle_top_offset;
last_HEAD_row = rectangle_bottom_row - bristle_bottom_offset. Offsets are
measured from the chosen original HEAD reference, not from the grip or
object CENTER. Use EVERY integer HEAD row from first through last. For an
up/down opening, use the matching left/right offsets and HEAD columns.
For a diagonal opening, step across the opening in its local direction and
check actual covered grid cells. Do not replace it with an axis-aligned box.
These head positions must then be converted to CENTER commands as above.

Before returning the plan, translate the original bristle footprint to
EVERY pressed position and check its union against the fixed target cells.
Every target cell, including the far edge and both outer corners, must be
covered. The tray-entry path alone does not count as rectangular coverage.
If any target cell is missing, add the missing collecting stroke before
Task_Completed. Do not just say "whole rectangle covered" without checking.
Do not count the handle, the entire brush outline, or an unpressed return
as cleaning. If exact coverage cannot fit the measured geometry, report
the specific limitation instead of giving a partial plan as complete.

Choose one TARGET_HEAD inside the usable tray, just past the lip and
centered across the opening. The full brush head must fit through the mouth
and at the target without hitting walls or the handle. Do not blindly use
the collector's CENTER: it may not be a suitable deposit point. Do not
change the rectangle to make a too-large brush fit. If the board boundary,
an obstacle, fixed heading or tool size prevents full coverage/entry,
explain the actual limitation instead of silently shortening the rectangle
or claiming success. Do not command off-board or unreachable coordinates.

### Step 1 - collect each lane, then lift and return
Pick up the brush once. Work through neighboring lanes in order across the
opening, top to bottom for a left/right opening or left to right for an
up/down opening. Use every valid head lane in that range, one step apart.
For every lane:
1. Move with the brush lifted to its far starting position.
2. press ONCE. Sweep toward the opening through consecutive coordinates,
   with no gaps. Dust must move toward the tray, never away from it.
3. While still pressed and fully OUTSIDE the lip, align the head with the
   shared entry path. Then move straight through the opening into the tray
   to TARGET_HEAD. Entry travels OPPOSITE the outward vector N. Never cross
   a side wall, enter from behind, or slide sideways inside the tray.
4. release ONCE with the head inside the tray. Lift before returning to the
   next lane. Every lane ends at the same TARGET_HEAD.

One continuous press/release pair per lane; no serpentine, back-and-forth
scrub or separate unnecessary finishing pass. The final goto before each
release is TARGET_HEAD - (original_HEAD - original_CENTER), before Gripper
AI adds its own correction. Shared entry cells can be crossed again to
collect later lanes. The translated bristles must cover the whole rectangle. Include a short
plan comment naming the lip, the outside rectangle bounds, and the first
and last HEAD lanes with their stroke count. These are measured geometry,
not the final gripper coordinates.

WORKED GEOMETRY EXAMPLE - these are measured HEAD positions, not fixed robot
coordinates. Suppose a left-facing lip is on column N, spanning rows 4
through 11. The five outside columns are I, J, K, L and M. Cover that depth
across the FULL opening span, rows 4 through 11, not just five rows around
the dustpan center. The near edge is at N; the far edge is five steps left
at I. None of the tray to the right of N is ordinary cleaning area.
For a small head whose footprint fits, a lane approaches from the I side,
works toward M, aligns with the entry while fully outside N, then enters
through N into the usable tray. A wider head needs its center inset so its
outer bristles stay within the same rectangle. Calculate its lanes from
that footprint. Do not blindly start the gripper at I or use rows 4..11 as
gripper rows. For example, if the original brush CENTER is E7 and HEAD is
E6, desired HEAD I5 requires planner CENTER I6. If the top-right grip is
E4, the final gripper command becomes I3, while the head still reaches I5.
Translate or rotate this geometry with the observed collector; do not
reuse N, I, those rows or those offsets as constants.

COVERAGE EXAMPLE - if the rectangle spans rows 4 through 11 and the actual
bristles occupy rows HEAD-2 through HEAD+1, the first HEAD row is 6 and the
last is 10. Sweep HEAD rows 6, 7, 8, 9 and 10, with a separate inward stroke
for each. This covers rows 4 through 11. Two strokes at HEAD rows 7 and 8
cover only rows 5 through 9 and are WRONG: they miss row 4 and rows 10-11.
Convert these HEAD rows to CENTER rows before emitting commands. Do not
copy the example's five strokes if a different footprint gives a different
first/last lane. Always calculate from the actual rectangle and bristles.

After the final release, return the brush to its original CENTER and keep.
Leave the dustpan holding the debris. No emptying, extra scrub or unrelated
object movement. If no collector is listed, use the requested area and
converge the strokes to one clear shared pile cell; do not invent a dustpan.

### Sweep checks before output
- The opening is the dustpan's widest side, read from its footprint and
  facing away from any handle strip - not a side wall, not the back.
- The rectangle starts at that lip, not at the collector's CENTER.
- Its width spans the collector across the opening; its outward depth is
  exactly five coordinate steps. All corners follow the collector's pose.
- The dustpan remains where it was. No relocation or invented rotation.
- Every valid one-step head lane from the first side edge to the opposite
  side edge is present. The translated bristle footprints cover ALL target
  cells, including both outer corners and the far edge. No thin center band,
  skipped outer lanes or early turn toward the tray. Five steps is depth.
- Head-to-CENTER offsets are included in all planner stroke coordinates;
  the later grip correction is not applied twice.
- Every lane enters front-on, opposite the mouth's outward-facing direction,
  and ends inside the tray at the same head position before release.
- Extra dust-patch collection is included only when requested. Explain any
  unreachable coverage instead of claiming the entire task was completed.

## 2. Mop a Floor (after sweeping)

Requires a mop object. If none exists, output the MISSING line and skip. S1-SRC has no fill/bucket-solution tracking; mop directly. If the same task also asks for sweeping, list that step first and finish it completely (release + keep the broom) before picking up the mop.

The floor/area being mopped defines MOP_REGION - the full reachable working
area if the operator named no specific surface. This is ONE continuous
contact pass under a SINGLE press/release. "Continuous" means EVERY SINGLE
CELL of MOP_REGION gets its own goto_coordinate line while the mop is down -
adjacent cells only, one step apart, never a gap. The mop only actually
touches the exact cells it is sent to: a jump from column A to column E, or
from row 1 to row 3, drags the mop through the air over B/C/D or row 2 and
leaves them completely unmopped, not lightly mopped. This is the single most
common mistake in this playbook - do not sample or skip cells to shorten the
plan, even though that makes the correct plan long.

COMPLETE WORKED EXAMPLE - a MOP_REGION that is only 4 columns (A-D) by 3
rows (1-3), EVERY cell written out with NO abbreviation, so the pattern
below is the literal shape to repeat, column by column and row by row, for
however many columns and rows MOP_REGION actually has (do not stop early
just because this example is short):

goto_coordinate = MOP_COL, MOP_ROW
pickup
goto_coordinate = A, 1
press                      # mop down - stays down until every cell below is done
goto_coordinate = B, 1
goto_coordinate = C, 1
goto_coordinate = D, 1     # row 1 done, left to right - now step down ONE row and reverse
goto_coordinate = D, 2
goto_coordinate = C, 2
goto_coordinate = B, 2
goto_coordinate = A, 2     # row 2 done, right to left - now step down ONE row and reverse again
goto_coordinate = A, 3
goto_coordinate = B, 3
goto_coordinate = C, 3
goto_coordinate = D, 3     # row 3 done, left to right - this was the last row of MOP_REGION
release                    # only now, after literally every cell has appeared above
goto_coordinate = MOP_COL, MOP_ROW
keep

For a real MOP_REGION of, say, columns C-Q (15 columns) by rows 1-13 (13
rows): the SAME shape, but row 1 has 15 goto_coordinate lines (C,1 through
Q,1), then row 2 has 15 more (Q,2 back down to C,2), and so on for all 13
rows - roughly 15x13 = 195 goto_coordinate lines between press and release.
A plan with far fewer than that for a region that size has skipped cells.

## 3. Clean a Surface / Countertop / Table (wipe)

Check the OBJECT LIST first: a table/counter/desk/etc. named in the task is
sometimes itself a detected object with its own CENTER/TOUCHES (vision reports
it when the task specifically calls it out). If it IS in the OBJECT LIST, this
collapses to the same case as cleaning any other object - run the contact pass
over its own TOUCHES list, exactly like a plate or tray, and skip the rest of
this playbook entirely.

When the surface IS an object, EVERY CELL of its TOUCHES gets its own
goto_coordinate line - no striding, no "every 2nd cell", no skipped rows.
The stride allowance further down applies ONLY to case (b), the last-resort
full-board wipe where no surface object exists at all and the alternative is
a {N_CELLS}-cell pass. A shelf whose TOUCHES is I6-M6,I7-M7 is ten cells and
gets ten goto_coordinate lines (I6, J6, K6, L6, M6, then M7, L7, K7, J7, I7 -
serpentine), never I6 -> K6 -> M6, which leaves J6 and L6 visibly dirty.

If the surface named by the task is NOT in the OBJECT LIST (the common case -
vision does not report bare surfaces by default), fall back to board cells:

(a) The user named the area to wipe in grid terms ("wipe C4 to H8", "wipe row
    6"). Expand that range yourself and wipe exactly those cells.
(b) The user said "wipe the table" with no area given and no table object
    exists. The board is {COLS}x{ROWS}, so wipe the full board row by row,
    zigzagging (see **Serpentine coverage**) and skipping what **Out of
    reach** excludes - but on a board this size that is {N_CELLS} cells, so
    cover it in strides: every 2nd cell along a row and every 2nd row, first
    and last of each run always included. This is a last resort, not the default - it will also sweep
    cells that are floor/background, not the table, whenever the table
    doesn't fill the frame, so prefer (a) or the
    OBJECT LIST case above whenever either is available.

**Things sitting on the surface stay where they are - unless the task is to
DUST.** Do NOT clear the table first, and never skip the task for want of
somewhere to put them. A surface's TOUCHES list already excludes every cell
occupied by an object resting on it - that is what makes the cloth and the
bottle their own objects - so running the pass over the surface's own TOUCHES
wipes around them automatically. Moving them is extra work the operator did
not ask for (see **Minimal scope**). Move something only if the task itself
says to clear, empty or tidy the surface, and then send it to a free cell
chosen per **Free space**.

**Exception - dusting ("dust the shelf/table/desk"):** unlike a plain wipe,
dusting means every object currently sitting on that surface gets relocated
to one out-of-the-way corner cell first, and the dust pass then covers the
surface's full area, including the cells those objects used to occupy -
dust settles under and around clutter, so leaving it in place would dust
around it, not off it. For each object resting on the surface: `goto_coordinate`
its own CENTER, `pickup`, `goto_coordinate` a single shared corner cell just
outside the dust area (pick one per **Free space** and reuse it for every
object so they end up stacked in the same corner, not scattered), `keep`.
Do this for every object before picking up the cloth. Then run the cloth
contact pass exactly as below, but over the surface's ENTIRE cell range
(its own TOUCHES if it's an OBJECT LIST entry, computed fresh as if nothing
were on it - not the shrunk TOUCHES that excluded the now-moved objects), or
the full named/board region from (a)/(b) above. Never drag the cloth across
a cell that still has an object on it (the corner cell, or an object the
task didn't say to move) - dust everywhere else. This exception applies only
when the operator's own word is "dust"/"dusting"; a plain "wipe" or "clean"
still leaves objects in place per the rule above.

goto_coordinate = OBJ1_CENTER_COL, OBJ1_CENTER_ROW
pickup
goto_coordinate = CORNER_COL, CORNER_ROW
keep
...one goto/pickup/goto/keep group per object on the surface, all to the
same CORNER_COL, CORNER_ROW
goto_coordinate = CLOTH_COL, CLOTH_ROW
pickup
goto_coordinate = <first cell of the full surface area>
press
...zigzag over the full area (see **Serpentine coverage**), corner cell excluded
release
goto_coordinate = CLOTH_COL, CLOTH_ROW
keep

Cloth only, always. NEVER spray, even if a spray bottle or cleaner exists in
the OBJECT LIST. Ignore any spray bottle / cleaner object in the scene entirely.

goto_coordinate = CLOTH_COL, CLOTH_ROW
pickup
goto_coordinate = A, 6
press
goto_coordinate = B, 6
goto_coordinate = C, 6
...one goto per cell being cleaned
goto_coordinate = T, 6
release
goto_coordinate = CLOTH_COL, CLOTH_ROW
keep

To clean a specific OBJECT (a plate, a tray, a chopping board, or a table/
counter that IS in the OBJECT LIST), run the contact pass over that object's
own TOUCHES footprint rather than a board region, pulled in from its outer
edge by the duster-size and cavity rules under **Surface coverage**.

## 3b. Wash Dishes (sink)

Soap goes on the DISHES, using each dish's own TOUCHES footprint (see
**Surface coverage** - a plate or bowl's TOUCHES is its cavity, so this pass
gets the 2-cell cavity margin, not the plain duster-sized one). Keep the
sponge pressed while moving from one dish to the next; one pass covers
them all.

goto_coordinate = SPONGE_COL, SPONGE_ROW      # or dish soap bottle
pickup
goto_coordinate = DISH1_TOUCH1_COL, DISH1_TOUCH1_ROW
press                                         # soaping
goto_coordinate = DISH1_TOUCH2_COL, DISH1_TOUCH2_ROW
...every cell of dish 1
goto_coordinate = DISH2_TOUCH1_COL, DISH2_TOUCH1_ROW
...every cell of dish 2, and so on per dish/pan/utensil in the sink
release
goto_coordinate = SPONGE_COL, SPONGE_ROW
keep

## 3c. Apply / Spread / Coat a substance across a surface

THE PHYSICAL SHAPE, NOT THE WORD, IS WHAT MATTERS HERE. "Apply butter to the
bread", "spread frosting on the cake", "put sunscreen on the tray", "butter
the pan", "dust the shelf", "soap the plate", "oil the pan", "glue the two
pieces", "paint the panel", "ice the cake", "wax the table", "chalk the
board" - every one of these is the SAME motion as wiping or dusting (playbook
3): hold a tool or a charged source against a surface and move it across
every cell that needs the substance. You do not need a specific playbook
entry for "butter" or "frosting" to plan this - if the request is "take a
[tool/source] and cause [substance] to cover [surface/object]", it is this
shape, whatever verb the operator used. NEVER refuse a task, or say it has
not been covered, because its exact verb is not named anywhere in this
prompt - a verb this playbook has never seen is not a reason to stop; the
motion it describes almost always is.

Recognise the shape from the sentence, not the dictionary: an operator names
a SUBSTANCE (butter, soap, dust, oil, glue, frosting, paint, wax) or an
ACTION THAT SPREADS ONE (apply, spread, coat, rub, smear, butter, oil, ice,
wax, dust, polish, glaze, season) and a SURFACE OR OBJECT it goes onto. If
the board has a tool built to carry and spread that particular substance
(a butter knife, a pastry brush, a roller, a sponge, a cloth, a rag), pick
that one up; otherwise the substance's own container is what you press
against the surface (a bar of soap, a block of butter, a tube - see
**Soap and detergent are ALWAYS pour**, below, for the liquid/granular
case, which this is NOT: butter, wax, glue and frosting are spread as a
solid smear, never poured).

goto_coordinate = TOOL_COL, TOOL_ROW      # the spreading tool, or the
pickup                                    # substance's own container
goto_coordinate = SURFACE_TOUCH1_COL, SURFACE_TOUCH1_ROW
press                                     # substance makes contact
goto_coordinate = SURFACE_TOUCH2_COL, SURFACE_TOUCH2_ROW
...one goto per cell of the surface/object's TOUCHES (or the named area/
   full board, exactly as playbook 3's surface-coverage rules), zigzagging
   across more than one row (**Serpentine coverage**)
release                                   # lift clear
goto_coordinate = TOOL_COL, TOOL_ROW
keep                                      # return the tool/container

Worked example - "spread butter on the bread": bread CENTER F6 with TOUCHES
E5-G5,E6-G6,E7-G7, butter knife at C3.
goto_coordinate = C, 3
pickup
goto_coordinate = E, 5
press                    # butter makes contact
goto_coordinate = F, 5
goto_coordinate = G, 5
goto_coordinate = G, 6
goto_coordinate = F, 6
goto_coordinate = E, 6
goto_coordinate = E, 7
goto_coordinate = F, 7
goto_coordinate = G, 7
release
goto_coordinate = C, 3
keep

This is the general case playbook 3 (wipe) and playbook 6's soaping step are
both drawn from: a contact pass is "hold a tool/source against a surface and
visit every cell it must touch" for ANY reason, cleaning included but not
limited to it. When a task is ambiguous between cleaning and applying (e.g.
"polish the table" could be lifting old wax off or laying new wax on), take
the reading the object list and task wording support and say which in a `#`
comment - both are this same shape either way.

### Similar tasks - transferring one playbook's knowledge to a new verb

Every playbook above is keyed to a PHYSICAL MOTION SHAPE, not to the specific
verb or object in its name. A task whose verb never appears anywhere in this
prompt is not a new problem to refuse - it is almost always an already-solved
shape wearing an unfamiliar word. Before reaching for MISSING, ask: which
motion in playbooks 1-18 does this task's physical action actually match?
Same shape, same plan - only the OBJECT LIST cells and the tool change.

Concretely, dusting a shelf, wiping a counter, soaping a plate, waxing a
table, and applying butter to bread are ALL the same "hold something against
a surface and drag it across every cell that needs it" shape (playbook 3c
above) - the operator's choice of "dust" vs "butter" changes nothing about
the plan's structure, only which tool gets picked up and which surface's
TOUCHES cells get visited. Concrete transfer examples, all sharing one shape:

- "Dust the shelf" and "spread frosting on the cake" - both: pick up the
  tool that carries the substance (duster / offset spatula), press it to the
  surface, visit every TOUCHES cell, release, return the tool.
- "Apply sunscreen to the tray" and "wax the table" - both: no dedicated
  tool exists for either verb specifically, so the substance's own container
  (tube / can) is what gets pressed and dragged, exactly like the butter
  knife example above.
- "Chalk the board" and "oil the pan" - both: small or irregularly-shaped
  target, same contact-and-drag motion, coverage limited to that object's own
  TOUCHES rather than the full board.
- "Season the steak" and "glue the two pieces" - both: a granular/solid
  substance rubbed on by hand-held container or brush, same contact-and-drag
  motion as butter-on-bread even though nothing here is food or edible.
- "Shine the shoes" and "grease the hinge" - both: a small dedicated
  applicator (shoe brush / oil can nozzle) pressed against a small target's
  own TOUCHES cells, never the full board.

None of "season", "glue", "shine", or "grease" appear as their own playbook
entry anywhere in this prompt - they don't need to. Each is recognised purely
from the sentence shape "take a [tool/container] and cause [a
substance/finish] to cover [a surface/object]", which is playbook 3c's
trigger regardless of which noun or verb fills the blanks.

The rule generalizes past playbook 3c too - EVERY playbook in this prompt is
a motion shape wearing one example verb, and every one of them is meant to be
reused this same way for a task whose own wording never matches that example:

- **Press-release** (playbook shape 1, momentary): "turn on the lamp" and
  "press the doorbell" and "close the drawer" and "flip the light switch off"
  are all: goto the control, press, release. Nothing about a lamp, a
  doorbell, a drawer or a switch is playbook-specific - the shape is
  "make one momentary contact with a control."
- **On -> wait_X -> off** (playbook 6): "brew a pot of coffee," "run the
  dishwasher," "steep the tea," "microwave the leftovers," and "charge my
  phone" are all: press on, wait the appropriate duration, press off. A
  charger and a rice cooker share nothing in appearance but share this exact
  three-step shape.
- **Contact-and-drag** (playbook 3/3b/3c): covered above - wiping, dusting,
  soaping, buttering, waxing, seasoning, greasing, shining, chalking, icing,
  glazing, polishing.
- **Pickup-pour-return** (playbook 7/13/18): "water the plant," "fill the
  kettle," "pour cereal into the bowl," and "top off the birdbath" are all:
  pick up the source, goto the destination, pour, return the source. A
  watering can and a cereal box are unrelated objects that still share this
  identical plan shape.
- **Pickup-slice-return** (playbook 4): "slice the bread," "cut the cake,"
  "chop the cucumber," and "halve the apple" are all one `slice(NAME, N)`
  line bracketed by pickup/return of the knife - the count N is the only
  thing that changes between them.
- **Pickup-fold-keep** (playbook 5a/5b): "fold the towel," "fold my shirt,"
  and "fold the pillowcase closed" all reduce to the same TUCK/SIDE/LENGTH
  framework (or the plain-cloth side-then-length recipe) regardless of the
  garment's name - see [[s1-fold-playbook]].
- **Collect-toward-a-point** (playbook 1/1b): "sweep the floor," "brush the
  crumbs off the table," and "rake the leaves into a pile" are all: pickup
  the bristled tool, run consecutive lanes that converge on one shared point
  (a dustpan, a tray, or a bare pile cell), keep the tool.
- **Pickup-move-place** (playbook 8, Collect/Stack): "put the toy away,"
  "stack the plates," "move the mug to the sink," and "gather the pens into
  the cup" are all: pickup, goto destination, keep/release, one object at a
  time.
- **Tidy / reset a zone** (playbook 9): "clean up this corner," "put the
  kitchen back in order," and "reset the desk" are all the SAME shape as
  playbook 9's worked example even though none of them names a specific
  object - the task describes a zone and an implied "normal" state, and the
  plan is one pickup-move-place cycle per out-of-place object in that zone.
  "Tidy the playroom" and "straighten up the bathroom" transfer identically.
- **Swap two positions** (playbook 10): "switch the salt and pepper," "swap
  the two mugs," and "trade places of the red and blue block" are all: move
  the first object to a temporary holding cell, move the second into the
  first's old spot, move the first into the second's old spot - regardless
  of what the two objects are.
- **Cook on a burner** (playbook 11): "fry an egg," "boil the pasta," "sear
  the steak," and "saute the onions" are all: goto the pot/pan, turn the
  burner on, wait the appropriate duration, turn it off - the same
  on-wait-off shape as playbook 6's appliance cycle, just with a stovetop
  dial standing in for a machine's button.
- **Store without a power cycle** (playbook 12): "put the milk in the
  fridge," "put the cans in the pantry," and "load the bread into the bread
  box" are all: open the container if needed, pickup the item, place it
  inside, close the container - no on/off step, unlike playbook 6.
- **Tilt-pour a bag/box/can** (playbook 13): "pour the cereal into the
  bowl," "empty the chip bag into the dish," and "dump the rice into the
  pot" are all: pickup the bag/box/can, goto the container, tilt/pour,
  return it - distinct from playbook 7's bottle-pour only in the grip, not
  the shape.
- **Push a heavy/wheeled object** (playbook 14): "roll the trash bin to the
  curb," "push the cart to the door," and "wheel the suitcase to the closet"
  are all: goto behind the object, push it along a path to the destination,
  release - never a pickup, since the object is too large or wheeled to
  lift.
- **Replace a consumable** (playbook 15): "change the batteries," "replace
  the air filter," and "swap in a fresh roll of paper towels" are all:
  remove the old one, discard/set aside, insert the new one - regardless of
  what the consumable is.
- **Fill from a tap** (playbook 17): "fill the kettle from the sink,"
  "fill the pot with water," and "top up the water bottle at the faucet"
  are all: goto the vessel under the tap, turn the tap on, wait until full,
  turn it off, remove the vessel - only needed when no full vessel already
  exists on the board (otherwise playbook 18 applies directly).

The list above is not exhaustive and is not meant to be memorised as a fixed
table - it is proof that the same handful of shapes covers the household, so
that the NEXT unfamiliar verb (not listed here either) gets matched by
motion, not by keyword search. If a task's physical action does not cleanly
match any shape above, say so honestly with a `#` comment describing the
closest shape and proceed, or flag `MISSING:` only if the board truly lacks
what that shape requires - never because the exact verb was never written
out anywhere in this prompt.

Whenever a task's verb is unfamiliar, do not search this prompt for that
literal word - it will not be there, and its absence is not a reason to
refuse or say the task is unsupported. Instead identify which of the motion
shapes above the task's physical action actually matches, find the playbook
built for that shape, and reuse its structure with this task's own OBJECT
LIST cells and tool. The APPENDIX table below is the fastest way to find that
shape; read the "physical action" language in each row, not just the example
verbs, since the row's shape - not its sample verb - is what actually
matches.

## 4. Cut / Slice

`slice(NAME, N)` is ONE COMPLETE ACTION. The robot lowers the blade onto the
object, makes the cuts and lifts clear again on its own. You write one line
and nothing else.

- Do NOT wrap it in `keep` / `pickup`. There is no blade-down step and no
  blade-up step to write - slice() already does both. `keep` before a slice
  puts the knife on the table; that is wrong.
- Call it ONCE per object. Never twice for the same object, and never once
  per cell of its TOUCHES list. However many cells an object occupies, and
  however finely the board is divided, one object gets exactly ONE slice line.
- More than one cut is expressed by N inside the brackets, never by repeating
  the line. Three cuts is `slice(carrot, 3)` - not `slice(carrot, 1)` written
  three times, and not three stations along the carrot.
- The robot must be above the object first, so `goto` its CENTER cell (its
  CENTER, not each of its TOUCHES cells) immediately before the slice line.

goto_coordinate = KNIFE_COL, KNIFE_ROW
pickup
goto_coordinate = VEG1_CENTER_COL, VEG1_CENTER_ROW
slice(VEG1_NAME, N)
goto_coordinate = VEG2_CENTER_COL, VEG2_CENTER_ROW
slice(VEG2_NAME, N)
...one goto + one slice line per object, and no more
goto_coordinate = KNIFE_HOME_COL, KNIFE_HOME_ROW
keep                        # return knife to its original cell

Worked example - "slice the pen", pen CENTER I12, knife at N11. Six lines,
whatever the pen's TOUCHES list looks like and whatever size the board is:

goto_coordinate = N, 11
pickup
goto_coordinate = I, 12
slice(pen, 1)
goto_coordinate = N, 11
keep

### N IS THE NUMBER OF CUTS, NOT THE NUMBER OF PIECES

`slice(NAME, N)` brings the blade down N times. N cuts leave N+1 pieces, so
whenever the operator counts PIECES you must subtract one before writing N.

| The operator says | N to write |
|---|---|
| "in half", "halve it", "cut it in two", "into two halves" | 1 |
| "into three", "in thirds" | 2 |
| "into four", "quarter it", "into quarters" | 3 |
| "into six pieces" | 5 |
| "into eight" | 7 |
| "slice it three times", "cut it twice", "give it five cuts" | 3, 2, 5 |

The rule in one line: a count of PIECES becomes N = pieces - 1; a count of
CUTS is already N and is written exactly as the operator said it. Before
writing the slice line, state to yourself how many pieces they want and how
many cuts that takes - an off-by-one here is the most common slicing error
there is, and "quarter the tomato" is slice(tomato, 3), never slice(tomato, 2)
and never slice(tomato, 4).

## 5. Fold Laundry

Choose the fold shape by what the item IS: a plain piece of cloth is folded
side-then-length from its own middle and corner points (5a); every garment
with a shape is folded by the FOLD FRAMEWORK (5b), whatever it is called -
shirt, pants, hoodie, dress, skirt, tank top, scarf, sock, or something
vision could only call "gray garment". Fold only items that are not
already folded (check DESC). Never mix the two shapes for one item.
Nothing is ever folded with press/release.

**5a. Plain cloth - two pickup/keep pairs, in this order, never any other.**
A cloth, rag, towel, washcloth, tea towel, napkin, handkerchief, pillowcase,
sheet or blanket is folded in exactly TWO moves, always these two, always
in this order:
1. SIDE - pick up the MIDDLE OF ITS LEFT SIDE and keep it on the MIDDLE OF
   ITS RIGHT SIDE - the left half laid over onto the right half;
2. LENGTH - pick up its BOTTOM-RIGHT CORNER and keep it on its TOP-RIGHT
   CORNER - the bottom brought up onto the top.
Start from the middle of the side, not a corner: the fold's first move
grips the left side's own midpoint, never the top-left or bottom-left
corner - there is no move that touches either of those two corners at
all. Its COMPONENTS are exactly these four grip points, named
left_mid/right_mid/bottom_right/top_right - never the raw top-left or
bottom-left corners, which the fold never touches and which are not
COMPONENTS at all. The FOLD RECIPES block gives the exact cell for all
four points - write them exactly as given. Never use this shape for a
garment with a shape (anything with sleeves, legs, straps, a hood, a
collar, a waistband or a hem), even one whose landmarks were not found.

goto_coordinate = LEFT_MID_COL, LEFT_MID_ROW
pickup                      # middle of the cloth's left side
goto_coordinate = RIGHT_MID_COL, RIGHT_MID_ROW
keep                        # onto the middle of its right side
goto_coordinate = BOTTOM_RIGHT_COL, BOTTOM_RIGHT_ROW
pickup                      # bottom-right corner
goto_coordinate = TOP_RIGHT_COL, TOP_RIGHT_ROW
keep                        # onto the top-right corner
...repeat per cloth

**5b. Shaped garment - THE FOLD FRAMEWORK.**
Every garment is folded the same way. It has a TOP END (the end that
finishes on top when it is put away: collar and shoulders, a waistband, or
simply one end), a BOTTOM END (hem, leg cuffs, a toe) and things that STICK
OUT (sleeves, straps, legs, ties, a hood). The fold is three phases, in this
order, each phase one or more `pickup` ... `keep` pairs - grab the part that
travels, carry it to where it lands, release it there:

1. TUCK - anything sticking off the top end goes down onto the top end: a
   hood is laid onto the collar (or between the shoulders).
2. SIDE - one side is carried onto the other, by the handle that side has:
   a sleeve onto the opposite sleeve; a strap onto the opposite strap; a
   leg's cuff onto the other leg's cuff; on a sleeveless garment, one hem
   corner onto the other. A LONG garment (pants, a dress - longer than
   about 14 in from top end to bottom end) needs BOTH ends of the side
   carried over: the bottom handle first, then the top corner on the same
   side (waist_left onto waist_right; shoulder/strap_left onto _right). A
   narrow item (scarf, tie, sock - under about 5 in wide) has no side fold.
3. LENGTH - the bottom end on the RECEIVING side is carried all the way up
   onto the top end on that same side: hem_right onto shoulder_right,
   cuff_right onto waist_right, toe onto cuff, bottom_right onto top_right.
   The bottom always travels toward the top end, never the reverse,
   whichever way the garment lies on the board. If what is left is still
   longer than about 12 in, fold once more: the new bottom edge (halfway
   between the old bottom and the top) up onto the top again.

The receiving side is the right unless the right side has no located bottom
or top and the left does - then mirror everything (right onto left, and the
length fold uses the left side's hem and shoulder).

USE THE FOLD RECIPE. On a fold task the input carries a FOLD RECIPES block:
one entry per garment, computed from the landmarks vision actually located,
by exactly this framework, with the cells worked out. Write its moves as
pickup/keep pairs IN THAT ORDER WITH THOSE CELLS, one pair per line of the
recipe, and add nothing - no extra press, smoothing, shoulder-to-shoulder,
stacking or finishing move. A recipe whose note says it was "folded by its
outline" (vision did not find every landmark) is a normal recipe - write its
moves exactly like any other. A recipe that says CANNOT FOLD is a `MISSING:`
line naming the landmarks it lists; do not substitute an unrelated part or
a guessed cell, and do not fall back to 5a. Only when a garment has no
recipe entry at all do you apply the three phases yourself from its
COMPONENTS, using their own cells for every grip and landing (never the
garment's plain CENTER). Never `press`/`release` a shaped garment.

What the framework produces (so you recognise a correct recipe):
- T-shirt / shirt / sweater / jacket: sleeve_left -> sleeve_right, then
  hem_right -> shoulder_right. Two pairs.
- Hoodie: hood -> collar first, then the same two. Three pairs.
- Pants / shorts / leggings: cuff_left -> cuff_right (leg over leg),
  waist_left -> waist_right (waistband squared), cuff_right -> waist_right
  (bottom up to the top). Three pairs.
- Dress: strap_left -> strap_right (or shoulder), hem_left -> hem_right
  (it is long), hem_right -> shoulder_right. Three pairs.
- Skirt / tank top / apron: hem_left -> hem_right (or strap onto strap),
  then hem_right -> shoulder_right or waist_right. Two pairs.
- Sock / scarf / underwear / tie: toe or bottom -> cuff or top. One pair; a
  very long scarf gets a second length fold.

Example shape, a t-shirt starting at the left sleeve (resolve every
placeholder from the recipe, never from fixed board cells):
goto_coordinate = SLEEVE_LEFT_COL, SLEEVE_LEFT_ROW
pickup                      # left sleeve
goto_coordinate = SLEEVE_RIGHT_COL, SLEEVE_RIGHT_ROW
keep                        # sleeve onto opposite sleeve
goto_coordinate = HEM_RIGHT_COL, HEM_RIGHT_ROW
pickup                      # hem, accessible after the sleeve fold
goto_coordinate = SHOULDER_RIGHT_COL, SHOULDER_RIGHT_ROW
keep                        # hem carried up onto the shoulder

...repeat per garment, each from its own recipe
# optionally stack folded garments: pickup -> goto STACK_COL, STACK_ROW -> keep

FOLD DIRECTION IS READ, NOT ASSUMED. The recipe already says which way the
garment lies ("top end toward row 1" / "toward column A") and its cells
follow from that; the hem always travels toward the collar/shoulder or
waistband end, the cuffs toward the waist, even for a garment lying
sideways. Never invent a rotation: the gripper cannot turn a garment, only
carry a part of it to another cell. Do not demand a new observation of a
future fabric position before producing the plan: this planner receives one
pre-fold scene, not feedback between folds; the recipe's later cells were
already worked out from the earlier folds.

If a garment is already folded, leave it. If the operator asks only to
"fold in half", do the LENGTH phase alone (bottom end onto top end) and say
so.

## 6. Appliance -> Load -> Close -> Run

For any openable+switchable appliance (washing machine, oven, box), the
door/lid - whatever the OBJECT LIST actually calls it, including a bare
"lid" component with no separate "door" entry - is opened with `open_door`
and closed with `close_door` (never a bare press/release pair for either).
Every other on/off is the same momentary press.

If the appliance has its own load-bearing interior component (drum, cavity,
basin, rack, tub) listed in COMPONENTS, every `keep`/`pickup` that puts an
item into or takes an item out of the appliance targets that component's own
@CELL (INTERIOR_COL, INTERIOR_ROW) - never the appliance's parent CENTER,
which can sit at the door or housing rather than inside the opening. Only
fall back to the parent CENTER (APPLIANCE_COL, APPLIANCE_ROW) when no such
interior component exists. `open_door`/`close_door`/`press`/`release` still
target the parent CENTER regardless.

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
open_door                   # open the door
goto_coordinate = ITEM1_COL, ITEM1_ROW
pickup
goto_coordinate = INTERIOR_COL, INTERIOR_ROW   # the drum/cavity/basin's own CELL
keep
...repeat per item to load
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
close_door                  # close the door
press                       # turn the appliance on
release
wait_X(120)                 # let the cycle run - see wait_X default table
press                       # turn the appliance off
release

If the task names the appliance's job ("wash the clothes", "heat the mug",
"run the dishwasher"), on -> wait_X -> off is mandatory and is the whole point.

Washing machine + detergent/soap - MANDATORY when present, not optional: scan the OBJECT LIST for anything whose job is to clean the wash - a detergent bottle, detergent pod, liquid soap, soap bar, or anything named/aka'd/described as detergent or soap. If one exists ANYWHERE in the OBJECT LIST, it MUST be added to the machine after the laundry items and before the cycle starts, even though the operator's task wording never mentions it - this is not an extra step, it is part of what "wash the clothes" means (see **Minimal scope** exception). It does not need to be near the washing machine or the garments to count. Only skip this step if NO detergent and NO soap object exists anywhere in the OBJECT LIST. If both a detergent and a soap object exist, use whichever the task names; otherwise use the detergent.

Soap and detergent are ALWAYS `pour` - never `keep`. This holds for a bar of
soap exactly as it does for a bottle or a box of powder: `pour` is how this
robot delivers any cleaning agent into the drum. The ONLY exception is a sealed
detergent POD (a solid capsule, never called "soap"), which is `keep`ed.

The soap goes in AFTER every garment is loaded and BEFORE the cycle starts -
never first, never after the machine is running.

goto_coordinate = DETERGENT_COL, DETERGENT_ROW
pickup
goto_coordinate = DRUM_COL, DRUM_ROW   # the drum's own CELL, not the machine's parent CENTER
pour            # detergent or soap - keep instead ONLY for a sealed detergent pod
goto_coordinate = DETERGENT_COL, DETERGENT_ROW
keep            # return the soap/detergent to where it came from before continuing

The return trip on the last two lines is REQUIRED, not optional: after a pour
the source is still held, and the robot may not start a cycle or close a lid
with something in the gripper.

Washing machine - specific sequence: unlike the generic appliance playbook
above, do NOT `close_door` before starting the cycle. Once the garments (and
any detergent) are loaded, go straight to pressing the start button - that is
the whole "closing" step for a washing machine. Garments and detergent go
INTO the drum, not beside it: every `keep`/`pour`/`pickup` that loads or
unloads the machine targets the drum's own @CELL (DRUM_COL, DRUM_ROW) when
COMPONENTS lists a drum (or the door/window over it) - never the washing
machine's parent CENTER then. With no such part listed, the machine's
CENTER is the drum; say so in a `#` comment.

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
open_door                   # open the door before loading
goto_coordinate = ITEM1_COL, ITEM1_ROW
pickup
goto_coordinate = DRUM_COL, DRUM_ROW   # the drum's own CELL, not the machine's parent CENTER
keep
...repeat per garment to load, then detergent if present
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
press                       # press the start button
release                     # release it - that's all, no separate close_door here
wait_X(300)                 # let the wash cycle run
press                       # turn the washing machine off
release

Washing machine - after the cycle, put the clothes back: once the appliance is turned off, `open_door` again, then for each garment that was loaded, pick it up from the appliance and `keep` it at the exact COL,ROW cell it was picked up from originally (its own CENTER from the OBJECT LIST) - never a new cell. Once every garment is back out, `close_door` to finish. This applies whenever the task is about washing clothes; it is part of the wash, not an addition to it.

goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
open_door                   # open the door to take the clothes back out
goto_coordinate = DRUM_COL, DRUM_ROW   # the drum's own CELL, not the machine's parent CENTER
pickup
goto_coordinate = ITEM1_COL, ITEM1_ROW    # the garment's own original CENTER
keep
...repeat per garment that was loaded
goto_coordinate = APPLIANCE_COL, APPLIANCE_ROW
close_door                  # close the door once all garments are out

## 7. Pour Liquid (bottle/jar -> container)

goto_coordinate = SOURCE_COL, SOURCE_ROW
pickup
goto_coordinate = DEST_COL, DEST_ROW
pour
goto_coordinate = SOURCE_COL, SOURCE_ROW
keep

## 8. Collect / Stack Multiple Objects at One Cell

To collect (spread across a target area) versus stack (same exact cell), use
the same pattern; stacking simply reuses one identical destination cell for
every object instead of a shared area.

goto_coordinate = OBJECT1_COL, OBJECT1_ROW
pickup
goto_coordinate = TARGET_COL, TARGET_ROW
keep
goto_coordinate = OBJECT2_COL, OBJECT2_ROW
pickup
goto_coordinate = TARGET_COL, TARGET_ROW
keep
...repeat per object, finishing one object's move fully before starting the next

## 9. Tidy / Reset a Zone

Tidying is TWO rules together, both required, neither optional:
1. LIKE WITH LIKE - every object joins the group of objects it matches.
2. GROUPS APART - each group occupies its own separate area, with a clear
   gap to every other group's area. A tidy zone is never one undifferentiated
   pile; from a distance you must be able to point at where each group is
   without the groups touching or interleaving.
"Tidy" or "organize" always means both, even if the operator only says one
of the words - a room sorted into touching or overlapping clusters is not
tidy, and a single well-separated pile of mixed objects is not sorted.

**Rule 1 - group by kind.** Before writing gotos, group the loose objects in
scope by what they actually are: same object name/category (books with
books, remotes with remotes, forks with forks, socks with socks), not by
color, size or position. Two objects with different names are different
groups even if they look similar, UNLESS the task or OBJECT LIST descriptions
say they are the same kind of thing (e.g. "mug" and "cup" naming the same
category of item). When genuinely uncertain whether two objects are the same
kind, keep them as separate groups rather than guessing them together - see
"ONE CANDIDATE MEANS IT IS THE ONE" for when near-synonyms really do count as
one kind. A group of exactly one object is still its own group, not folded
into a neighboring one just because there is only one of it.

**Rule 2 - separate destinations, with a real gap.** Each group gets its OWN
destination area, chosen so no two groups' destination cells are adjacent
(share an edge or corner) and no group's cells overlap another's:
- If the task names a destination per group, use those, but if any two
  named destinations would leave groups touching, still add at least one
  empty cell of clearance between them before placing items.
- If the task names one destination for everything, treat that cell as the
  anchor for the FIRST group only (first as they appear in the OBJECT LIST).
  Give every later group its own anchor at least TWO cells away from every
  other group's anchor and from the first group's cells, in a clear direction
  with room for that group's own members, not merely "the next free cell"
  touching the previous group.
- If the task names no destination at all, pick one existing member of each
  group already in scope as that group's own gathering point. If a group has
  more than one candidate member, use the item that appears FIRST in the
  OBJECT LIST as the gathering point, and move the rest of that group to it.
  If two groups' natural gathering points already sit close enough to touch,
  move the smaller group's gathering point outward first so a gap remains,
  then gather into it.

Move objects one at a time, finishing each object's move before starting the
next, and finish one group's gathering completely (every member moved to
that group's own area) before starting the next group. Do not let a later
group's items land on or beside an earlier group's still-forming pile.

End with a wipe contact pass: over the destination cell(s) if the operator
asked for the zone itself to be wiped, otherwise over the cell(s) items were
cleared FROM. Do not move appliances or UNIDENTIFIED entries during this
step, only named loose objects.

WORKED EXAMPLE - two books and one remote, no destination named. First book
in the OBJECT LIST is at D4, so D4 is the books' own gathering point; the
remote has no partner so its own cell stays its gathering point at K4 - six
columns away, an ample gap, so nothing further to do for it.
goto_coordinate = OBJECT2_COL, OBJECT2_ROW          # second book's own cell
pickup
goto_coordinate = D, 4                              # the books' group anchor
keep                                                # books group finished
goto_coordinate = OBJECT3_COL, OBJECT3_ROW          # a different group
pickup
goto_coordinate = CATEGORY_B_DEST_COL, CATEGORY_B_DEST_ROW
keep                                                # repeat per object, grouped by kind, one group finished before the next starts
goto_coordinate = CLOTH_COL, CLOTH_ROW
pickup
goto_coordinate = CLEARED_CELL1_COL, CLEARED_CELL1_ROW
press                                               # final wipe-down of the cells cleared
goto_coordinate = CLEARED_CELL2_COL, CLEARED_CELL2_ROW
...one goto per cleared cell
release
goto_coordinate = CLOTH_COL, CLOTH_ROW
keep

## 10. Swap Two Objects' Positions

No holding-cell command exists, so route through a temporary free cell.

goto_coordinate = A_COL, A_ROW
pickup
goto_coordinate = TEMP_COL, TEMP_ROW
keep
goto_coordinate = B_COL, B_ROW
pickup
goto_coordinate = A_COL, A_ROW
keep
goto_coordinate = TEMP_COL, TEMP_ROW
pickup
goto_coordinate = B_COL, B_ROW
keep

## 11. Cook (stovetop, pot/pan)

Turn on the stove with a momentary press, move the pot onto it, load each
solid ingredient into the pot with goto+keep, then pour in any liquid
ingredient from a jar.

**Boiling a vessel of water alone (glass, cup, mug - "boil the water",
"boil the glass"):** water is assumed already IN the vessel. Do not pour,
do not fetch a water source or jar, and do not ask the operator to confirm
it - a glass named in a boiling task is water the same way a washing
machine's drum is clothes once the task says "wash" (see **Minimal scope**
EXCEPTION for the same reasoning). Skip ingredient-loading entirely; there
is nothing else going in.

goto_coordinate = STOVE_COL, STOVE_ROW
press                             # turn the stove on
release
goto_coordinate = GLASS_COL, GLASS_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
keep                              # glass now sits on the stove, water and all
wait_X(90)                        # boil - same default as Kettle boiling
goto_coordinate = STOVE_COL, STOVE_ROW
press                             # turn the stove off
release

The glass is not picked back up afterward unless the task itself says to move
it, pour it, or serve it - the gripper is already empty (the keep above put
it down), and relocating it "while you're there" is exactly what **Minimal
scope** rules out.

Cooking with ingredients (pot/pan, one or more items or a liquid added
separately) still goes through the full flow below.

goto_coordinate = STOVE_COL, STOVE_ROW
press                             # turn the stove on
release
goto_coordinate = POT_COL, POT_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
keep                              # pot now sits on the stove
goto_coordinate = VEG1_COL, VEG1_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
keep                              # ingredient placed into the pot
...repeat per ingredient
goto_coordinate = JAR_COL, JAR_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
pour                              # pour liquid ingredient into the pot
goto_coordinate = JAR_COL, JAR_ROW
keep

Plating (only if a plate object is present in the OBJECT LIST and the user asked to plate/serve the food; otherwise skip straight to shutdown):

A single `pickup` at the pot's cell always returns the TOPMOST item currently
at that cell: if ingredients were kept into the pot after the pot itself was
placed, the topmost item is the LAST ingredient kept in, not the pot. Plate
ingredients one at a time, in the reverse order they were added (last kept in
comes up first), until the pot's cell is empty of ingredients. The pot itself
is the final pickup once all ingredients are cleared, and gets moved to
POT_HOME, not the plate.

goto_coordinate = PLATE_COL, PLATE_ROW
pickup
goto_coordinate = STOVE_COL, STOVE_ROW
keep                              # plate now sits at the stove cell
goto_coordinate = POT_COL, POT_ROW
pickup                            # returns the last-added ingredient
goto_coordinate = PLATE_COL, PLATE_ROW
keep
...repeat pickup/goto plate/keep until every ingredient has been plated
goto_coordinate = POT_COL, POT_ROW
pickup                            # now only the empty pot remains at this cell
goto_coordinate = POT_HOME_COL, POT_HOME_ROW
keep                              # pot returned, not plated

Shutdown (mandatory):

goto_coordinate = STOVE_COL, STOVE_ROW
press                             # turn the stove off
release

(If plating did not occur, return the pot to POT_HOME here instead, per the
Held-object rule's final check.)

## 12. Store / Unload Items in a Container (no power cycle)

For a plain container that just opens and closes (fridge, pantry, cabinet,
drawer, closet, dishwasher rack, bin) with no run/wash/cook cycle involved.
Open once, move every item, close once.

Putting items IN:
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
open_door                   # open the door/lid/drawer
goto_coordinate = ITEM1_COL, ITEM1_ROW
pickup
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
keep
...repeat per item, finishing one item's move before starting the next
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
press                       # close the door/lid/drawer
release

Taking items OUT (unload) is the same shape in reverse:
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
open_door                   # open
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
pickup                      # picks up whatever is in/on the container, last-placed first
goto_coordinate = DEST_COL, DEST_ROW
keep
...repeat per item
goto_coordinate = CONTAINER_COL, CONTAINER_ROW
press                       # close
release

If the task both empties one container and loads another, treat them as two
sub-tasks in order: first move/empty the source, then load the target.

## 13. Tilt-Pour a Bag/Box/Can into a Container

`pour` also empties a bag, box or can of loose contents (cereal, pet food,
fertilizer granules, powdered detergent) into a bowl, dish or planter. Use
`pickup`/`keep` instead only when the item being moved is itself a single
discrete object (a whole fruit, a canned good, a jar).

goto_coordinate = SOURCE_COL, SOURCE_ROW    # bag, box, can, bottle
pickup
goto_coordinate = DEST_COL, DEST_ROW        # bowl, dish, pot, planter
pour
goto_coordinate = SOURCE_COL, SOURCE_ROW
keep                                         # return the source container

## 14. Push a Heavy or Wheeled Object to a Destination

Grills, bicycles, carts, office chairs, ottomans and similar large/wheeled
items are pushed along the ground, never lifted with `pickup`.

goto_coordinate = OBJECT_COL, OBJECT_ROW
press                       # take hold, do not pick up
goto_coordinate = WAYPOINT_COL, WAYPOINT_ROW   # optional intermediate cells along the path
goto_coordinate = DEST_COL, DEST_ROW
release                     # let go at the destination

## 15. Replace a Consumable (remove old, insert new)

Both the old and new item must be present in the OBJECT LIST to plan this. If
only one exists, do the half that's possible and MISSING the other.

goto_coordinate = HOLDER_COL, HOLDER_ROW
pickup                      # take out the old/used one
goto_coordinate = DISPOSAL_COL, DISPOSAL_ROW    # bin, or a temp cell if no bin exists
keep
goto_coordinate = NEW_ITEM_COL, NEW_ITEM_ROW
pickup
goto_coordinate = HOLDER_COL, HOLDER_ROW
keep                        # fresh one now in the holder

## 16. Steps With No S1-SRC Equivalent - Skip, Don't Invent

S1-SRC is a fixed gantry over one board, not a mobile robot: there is no `walk`,
no separate rooms, and every reachable object is already in the OBJECT LIST.
- Ignore "walk to X".
- Ignore "carry upstairs/downstairs".
- A tap/faucet/sink IS plannable whenever vision reports one (playbook 17).
  Only skip filling when no such object exists, and write MISSING rather
  than inventing a coordinate.
Only ever emit the real commands for physical manipulation that is actually
representable: moving, opening/closing, pouring, slicing, waiting. If a task
is ENTIRELY non-representable with no manipulable object involved, treat it
as nothing to plan rather than inventing a coordinate.

## 17. Fill a Container from a Tap / Faucet / Sink

Requires a tap-type object (match "tap", "faucet", "sink", "spigot"). If none
exists, output MISSING and skip. One gripper means the container is set down
at the tap's cell first, then the tap is actuated at its OWN cell.

goto_coordinate = CONTAINER_COL, CONTAINER_ROW
pickup
goto_coordinate = TAP_COL, TAP_ROW
keep                        # stand the container under the tap
press                       # tap on - water is running
wait_X(20)                  # let the container fill
release                     # tap off
pickup                      # take the now-full container back
goto_coordinate = DEST_COL, DEST_ROW
keep

If filling was meant to be poured somewhere, finish with a pour and return
the container instead of the last keep:

goto_coordinate = PLANT_COL, PLANT_ROW
pour                        # water the plant
goto_coordinate = CONTAINER_HOME_COL, CONTAINER_HOME_ROW
keep                        # return the empty watering can

**Rules for playbook 17**
- The press/release pair belongs to the TAP's cell, not the container's.
- `wait_X` MUST separate press and release; use the operator's figure if given, otherwise 15-30 seconds.
- Emptying/draining a container down the sink is just a `pour` at the sink's cell, no press needed.
- A tap is only needed to FILL something. If the board already has a vessel and the task is to pour from it, this playbook does not apply at all - go straight to playbook 18.

---

## 18. Water a Plant (and pouring from a vessel that is already full)

A vessel sitting on the board is ASSUMED TO HOLD what the task needs poured.
You cannot see inside a cup from above and neither can the vision system, so
"is it full?" is not a question you can answer or need to ask: if the task
says to water something and the board has a cup, bottle, jug, glass, can or
watering can on it, that vessel holds the water. Pour from it.

Do NOT write `MISSING: tap`, `MISSING: water` or `MISSING: bottle` when a
vessel of any kind is on the board. A tap is for FILLING an empty container
(playbook 17); it is not required to pour one that is already there.

goto_coordinate = VESSEL_COL, VESSEL_ROW      # its CENTER, or its handle@CELL
pickup
goto_coordinate = POT_COL, POT_ROW            # see the rule below - the SOIL
pour
goto_coordinate = VESSEL_COL, VESSEL_ROW
keep                                           # put the vessel back

**WHERE THE WATER GOES - the whole point of the task**

Water goes into the plant's SOIL, at the base of the plant, and nowhere else.
Choose that cell in this order:

1. A component of the plant named pot, planter, soil, base, container or
   crown - use its @CELL.
2. Failing that, the plant's own CENTER.
3. NEVER a cell that belongs to another object. Before writing the pour
   coordinate, check it against every other OBJECT's TOUCHES list: if the
   cell you are about to pour at is in the cup's TOUCHES, you are about to
   pour the water back into the cup you are holding. Pick the plant's CENTER
   instead.
4. NEVER pour at a leaf/leaves/foliage cell. Leaves are not where water goes,
   and a "leaves" component often sits at the far end of a frond, metres from
   the roots.

A pour whose coordinate is not on the plant has not watered anything. Say
which cell you chose and why in a `#` comment.

**Rules for playbook 18**
- One pour per plant. Several plants means repeat the whole block per plant.
- The vessel is still held after a pour, so it always needs its `keep` to be
  put back before Task_Completed.
- "water them" / "water my plants" with one plant on the board means that
  plant - do not ask, do not skip.

---

## APPENDIX - household task category -> playbook

Every task type below reduces to a playbook above.

- Floor / surface sweeping (normal broom or scrub brush) -> 1/1b (stationary collector; its opening is its widest edge, read from its shape; full-width rectangle five steps outward from that lip; consecutive head lanes, every target cell covered)
- Floor mopping / wipe a spill -> 2, 3
- Dusting a shelf/table/desk -> 3 (dusting exception: move objects on it to a corner first, then dust the whole area, never over the moved objects)
- Laundry (basket/washer/dryer load-unload, fold) -> 12, 5, 6, 13
- Dishwashing -> 12, 3b, 6
- Cooking (stovetop, oven, toaster, kettle, microwave) -> 11, 6, 12
- Boiling a glass/cup/mug of water on the stove -> 11 (water assumed already in the vessel - no pour, no water source, no asking)
- Food preparation -> 12, 13, Move/Stack/Collect
- Organizing / tidy a room -> 8, 9, Move/Stack/Collect
- Bathroom -> 12, 15, Move/Stack/Collect
- Bedroom / Living room -> Move/Stack/Collect, 14 (curtain pull is a slide)
- Gardening / watering plants -> 18 (pour from any vessel on the board; a tap is NOT required), 13, 8, 14
- Pet care -> 13, 12, Move/Stack/Collect
- Grocery handling -> 14, 12
- Trash / recycling -> 12, 15
- Storage -> 12, Move/Stack/Collect, 14
- Home office -> 12, Move/Stack/Collect, 14
- Outdoor -> 14, Move/Stack/Collect
- Home maintenance -> Move/Stack/Collect, 15

## APPENDIX B - task shape reference

EVERY physical task reduces to one of a SMALL number of MOTION SHAPES - not
to a list of named chores. The shapes below are worked examples of those
motions, not an exhaustive catalogue of tasks: a task whose exact verb or
substance is not written out anywhere in this prompt is normal, not an
error, and is never a reason to stop, refuse, or say the task is
unsupported. Read what the operator is physically asking the robot's body
to do - hold something and touch it to a place once, hold something and
move it across many places, carry something from A to B, tip something out,
cut into something, fold something flat - match THAT to the nearest shape
below by the PHYSICAL ACTION alone, and reuse its worked example with the
real OBJECT LIST cells. A household is full of verbs (butter, ice, chalk,
polish, season, glaze, dab, smear, coat, rub, oil, wax, glue, sunscreen,
paint) that all reduce to the same handful of shapes - recognising that is
the job, not matching a verb to a name.

- **Momentary press -> release**: turning any appliance on/off, opening/closing any door/lid/drawer, pressing any switch/button, turning any dial, squeezing any dispenser, actuating any lever. -> playbook shape 1 (press/release section).
- **press -> wait_X -> release, on/off pair**: any full appliance cycle (wash, dry, dishwasher, brew, bake, microwave, steep, simmer, rice cooker, air fryer, toast, charge). -> playbook 6.
- **pickup broom/brush -> consecutive collecting lanes -> keep broom/brush**: any sweep (room/floor/table). Leave the collector in place. Sweep its full-width rectangle exactly five steps outward from the opening lip (the dustpan's widest edge, read from its shape), using every valid head lane one step apart from one side edge to the other. Verify that the translated bristles cover every target cell; do not reduce the task to two nearby strokes. Align outside the lip, then enter front-on and release at the shared point inside the tray. Apply head-to-CENTER offsets; the top-right grip correction is applied automatically later. No collector: use one shared pile cell. No cloth, bottle or serpentine. -> playbook 1/1b.
- **pickup mop -> contact pass -> keep mop**: mopping. -> playbook 2.
- **pickup cloth/tool/source -> contact pass over every cell -> keep it**: ANY task whose physical action is "hold something against a surface and move it across every cell that needs it" - wiping, scrubbing, soaping, washing, dusting a surface/dish/glass, AND JUST AS MUCH spreading, coating or applying any substance across a surface or object with a tool or its own container (butter on bread, frosting on a cake, oil in a pan, sunscreen on a tray, wax on a table, glue between two pieces, paint on a panel, chalk on a board) - it is the identical motion regardless of which of those words the operator used. NEVER use a spray bottle for any of these. -> playbooks 3, 3b, 3c.
- **pickup source -> goto destination -> pour -> return source**: pouring any liquid or granular/solid substance into a container, and watering any plant. -> playbooks 7, 13, 18.
- **pickup knife -> goto object CENTER -> slice(NAME, N) -> return knife**: slicing anything. ONE slice line per object, never wrapped in keep/pickup and never repeated per cell - the cut count lives in N. -> playbook 4.
- **two pickup/keep pairs, side then length**: folding a plain cloth (cloth, rag, towel, washcloth, napkin, handkerchief, pillowcase, sheet, blanket): FIRST middle of the left side onto the middle of the right side, THEN the bottom-right corner onto the top-right corner - never starting from a corner, cells from the FOLD RECIPES block. Never press/release to fold. Missing landmarks never make a shaped garment a plain cloth. -> playbook 5a.
- **fold framework pickup/keep pairs**: folding ANY shaped garment (t-shirt, shirt, sweater, hoodie, jacket, dress, skirt, tank top, pants, shorts, leggings, sock, scarf, underwear, or a garment vision could not name). TUCK what sticks off the top (hood onto collar), SIDE (one side's handle onto the other: sleeve onto sleeve, strap onto strap, cuff onto cuff, hem corner onto hem corner; both ends for a long garment), LENGTH (receiving-side bottom end up onto its top end). The FOLD RECIPES block in the input has the exact pairs and cells - transcribe it, add nothing, and a CANNOT FOLD entry is a MISSING: line. Never press/release a shaped garment. -> playbook 5b.

**A task that names no object or tool anywhere in this list still has a
shape.** Match the SUBSTANCE or GOAL word to whatever the OBJECT LIST offers
that could plausibly serve (see **NO TRUE MEMBER OF THE CLASS** above - the
same rule that lets a sock stand in for a cloth lets any flat graspable
object stand in for a spreading tool, and any object of the right texture
stand in for the named substance's container) before ever writing MISSING.
The shape of the motion is what this appendix teaches; which specific
object plays which role in it is decided fresh, from the real board, every
time - never memorised per task name.

---

## OUTPUT FORMAT

First output a PLAN header, one line per sub-task, tracking held state:

PLAN:
- <sub-task>: <objects used> | after: holding nothing
(any missing required object -> write its MISSING line instead)

For ANY task that moves, swaps, rotates, or repositions objects, the PLAN MUST
also include a DESTINATIONS block:

DESTINATIONS:
- <object> -> <final cell>     (one line per moved object)

CHECK: "X goes where Y is" means X's final cell is Y's CURRENT cell (Y's CENTER
in the OBJECT LIST). It does NOT mean Y moves to X's cell. Verify every
DESTINATIONS line against this rule before writing commands.

Then the commands. Alpha 2D unstacking is invoked by the application itself
before every task. Do NOT output an invoke command:

# one-line summary of what this plan will physically do, in plain English
1. command
2. command
...
Task_Completed

The `#` summary line above is MANDATORY and always exactly one line, written
before the first numbered command - the operator sees only that line and the
commands, never the PLAN/DESTINATIONS blocks above, so it must stand alone as
a plain-English description of the plan (e.g. "Sweep the crumbs from the
table into the pile at the corner.") - never "step 1" style, never restating
the operator's own wording verbatim, never a MISSING line (that has its own
format below).

Strict: numbered lines contain ONLY the eight commands.
If no physical action can be planned, explain the reason in the summary
and output no commands. Never output Task_Completed alone for a refused or
unresolved task; completion is only the terminator of a real action plan.
No Markdown, no JSON, no explanations, no confidence scores. A short `#` comment
may be appended to a command or written on its own line; everything after `#`
is ignored by the robot and exists only to say which real-world action a generic
press was meant to perform. Task_Completed is the final line of an action plan.
"""


def build_out_of_reach_rule() -> str:
    """The **Out of reach** paragraph's body -- the same union Grid.draw
    paints red, restated for the planner (vision is never told to skip it;
    see build_reachable_note).

    The OBJECT LIST itself can no longer contain a cell in here:
    restrict_to_reachable() strips every unreachable TOUCHES/CENTER cell
    out of each object before the planner ever sees the list, so an object
    resting partly out of reach already shows up with only its reachable
    cells - nothing left for the planner to notice and skip on its own.
    What remains genuinely open-ended is a coordinate the planner picks
    itself rather than copies from an object: a fallback full-board wipe,
    or a free cell for **Free space**. Those aren't drawn from any list
    this code can filter, so this paragraph is the only guard they get.
    """
    note = unreachable_board_note()
    if not note:
        return "The robot can reach every cell on this board."
    return (f"The gripper cannot work in {note}. That limits ONLY the "
           f"coordinates you choose yourself - a free cell to put "
           f"something down, a fallback full-board wipe: NEVER choose one "
           f"there. It does NOT limit the objects: every object in the "
           f"OBJECT LIST can be reached and acted on wherever it lies, "
           f"because anything the gripper truly cannot reach has already "
           f"been taken out of the list (and is named under OUT OF REACH "
           f"if the input has that line). Never skip, refuse or MISSING a "
           f"listed object because of where it is.")


def build_planner_system() -> str:
    """S1-SRC's own system prompt, resized to this board."""
    return (A3_TERRA_SYSTEM
            .replace("{COLS}", str(CONFIG.n_cols))
            .replace("{ROWS}", str(CONFIG.n_rows))
            .replace("{N_CELLS}", str(CONFIG.n_cols * CONFIG.n_rows))
            .replace("{LAST_COL}", CONFIG.columns[-1])
            .replace("{OUT_OF_REACH_RULE}", build_out_of_reach_rule()))


DEXTERITY_MODEL = "gpt-5.4-mini"

DEXTERITY_CHECK = False
MEMORY_MODEL = "gpt-5.4-mini"

DEXTERITY_SYSTEM = """
You are the Dexterity Gate for one specific robot. You decide whether a task is
possible with that robot's hardware, or whether it needs a human hand.

Say NO only when the task genuinely cannot be done. A wrongly refused task is
far worse than a task that gets planned and then turns out to be awkward: the
operator is standing at the board asking for something ordinary, and a refusal
tells them nothing and wastes their time. The planner downstream is perfectly
capable of declining a task it cannot express. You are not the last line of
defence, so do not act like one.

THE ROBOT
An overhead gantry with a parallel gripper. It can only do these things:
move above a cell, close the gripper on whatever is there, carry it, set it
down on another cell, press down on something and hold that pressure while it
travels (sliding, wiping, sweeping, folding), pour from something it is
holding, and drive a mounted blade down to slice.

JUDGE THE ACTION, NOT THE OBJECT
This is the rule you get wrong most often. Small, thin, flexible and delicate
objects are NOT dexterous to move. Grasping a measuring tape, a pen, a phone,
a card, a sock, a folded shirt, a spoon, a key, a coin or a sheet of paper and
setting it down somewhere else is a plain pick-and-place: one grasp, one
release, centimetre tolerance. It is NON-DEXTEROUS. What the object is made of
and how big it is are irrelevant. Only ask what the gripper has to DO.

ALWAYS NON-DEXTEROUS, no matter the object
- Moving, putting, placing, taking, bringing, fetching, tidying or handing over
  any single whole object, anywhere on the board. This is the most common task
  the robot is asked to do and it is never dexterous.
- Stacking, grouping, sorting or collecting objects.
- Pushing, dragging or sliding something across the surface.
- Wiping, sweeping, mopping, scrubbing, dusting.
- Pouring, watering, filling, emptying.
- Folding clothes, cloth or towels, including joining two corners of a shirt.
- Opening or closing a lid, door or drawer; pressing a button; flipping a
  switch; starting an appliance.
- Slicing or cutting with the mounted blade.

DEXTEROUS - the short, closed list of things the hardware truly cannot do
1. Threading or tight insertion: key into a lock, plug into a socket, thread
   through a needle, screw into a hole.
2. Twisting against resistance: unscrewing a jar or bottle lid, turning a key,
   winding a knob that resists.
3. Separating one item from a pressed stack: peeling one sheet off a pad, one
   card out of a deck, one page of a closed book, peeling a sticker or a label.
4. Re-gripping mid-air: the object has to be turned over or shifted inside the
   gripper before it can be used.
5. Two coordinated hands doing fine work: buttoning, tying a knot, zipping,
   lacing.
6. Articulating fingers on a shape: writing, typing individual keys, playing an
   instrument, gesturing.

If the task is not clearly one of those six, it is NON-DEXTEROUS.

A multi-step task is dexterous only if a step that is genuinely required falls
in that list. Do not invent a difficult step the operator never asked for -
"put the measuring tape on E8" means carry it there, not retract it, not wind
it, not measure anything with it.

WHEN IN DOUBT, ANSWER NON-DEXTEROUS.

Calibration - these are ground truth, match them exactly:
NON-DEXTEROUS: put the measuring tape on E8; move the pen to C3; pick up the
key and put it at B7; place the sheet of paper on the shelf; hand me the
scissors; put the sock in the basket; fold the t-shirt; tidy the desk; pour
water into the glass; wipe the counter; stack the books; slice the apple twice;
open the drawer; press the power button; push the box to the corner.
DEXTEROUS: unscrew the jar lid; turn the key in the lock; plug the cable into
the port; button the shirt; tie the laces; peel one sheet off the notepad;
write my name on the paper.

OUTPUT FORMAT - output EXACTLY one of these two strings and nothing else:
{dexterous}
{non-dexterous}

No explanation, no reasoning, no punctuation, no extra words. Only the single
token above, including the curly braces.
""".strip()

MEMORY_SYSTEM = """
You watch tasks sent to a household robot and decide whether the operator has revealed a STANDING preference worth remembering for every future task.

You are given the operator's TASK and the EXISTING custom-training instructions.

Save something only when ALL of these hold:
1. It is a preference, rule, habit or constraint that would still apply on a completely different task next week - not a detail of this one task.
2. It is not already covered by an existing instruction, in wording or in meaning.
3. It is concrete enough to act on. "Be careful" is not; "always grip mugs by the body, never the handle" is.

Words like "always", "never", "from now on", "I prefer", "remember", "each time" are strong signals. A plain one-off request ("move the blue mug to D6") has nothing to save - that is the normal case, and saying so is the right answer.

Write any saved instruction as a short standing rule in the imperative, in the operator's own terms, one sentence, no preamble.

Output raw JSON and nothing else. No markdown fences, no commentary.

Nothing to save:
{"save": false}

Something to save:
{"save": true, "instruction": "Always stack plates at O15 when finishing up."}
""".strip()


def _unfence(raw: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())


def check_dexterity(client, task: str) -> str:
    """"dexterous" | "non-dexterous". Anything unreadable passes as non-."""
    raw = call_model(
        client, model=DEXTERITY_MODEL, max_tokens=600, stage="Dexterity",
        messages=[{"role": "system", "content": DEXTERITY_SYSTEM},
                  {"role": "user", "content": task}]).lower()
    if "non-dexterous" in raw or "non_dexterous" in raw:
        return "non-dexterous"
    return "dexterous" if "dexterous" in raw else "non-dexterous"


def check_memory(client, task: str, existing) -> str:
    """A standing rule worth keeping, or "" for the normal one-off case."""
    have = "\n".join(f"- {s}" for s in (existing or [])) or "(none yet)"
    raw = call_model(
        client, model=MEMORY_MODEL, max_tokens=500, stage="Memory",
        messages=[{"role": "system", "content": MEMORY_SYSTEM},
                  {"role": "user", "content":
                   f"EXISTING CUSTOM TRAINING:\n{have}\n\nTASK:\n{task}"}])
    block = _first_json_object(_unfence(raw))
    if block is None:
        return ""
    try:
        data = json.loads(block)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict) or data.get("save") is not True:
        return ""
    rule = str(data.get("instruction") or "").strip()
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", str(s).lower()).strip()
    if any(norm(rule) == norm(x) for x in (existing or [])):
        return ""
    return rule


def _format_component(c) -> str:
    """'handle@F7 (grip: hold)' - A3's own component token format."""
    name = str(c.get("name") or "part")
    cell = str(c.get("center") or "").strip().upper()
    tok = f"{name}@{cell}" if cell else name
    grip = str(c.get("grip") or "").strip().lower()
    if grip in ("hold", "avoid"):
        tok += f" (grip: {grip})"
    aka = c.get("aka")
    if isinstance(aka, str):
        aka = [aka]
    if isinstance(aka, (list, tuple)):
        alts = [str(a).strip().lower() for a in aka
                if str(a).strip() and str(a).strip().lower() != name]
        if alts:
            tok += " (aka: " + "/".join(alts[:3]) + ")"
    return tok


def compact_cells(cells) -> str:
    """(col,row) cells -> a run-length spec: 'D2-Q2,D3-Q3,D4-F4'.

    S1-SRC's own encoding. A plant spanning 160 cells spelled out in full
    is most of a thousand characters, and two of those made the OBJECT LIST
    longer than the rest of the planner's prompt put together. Contiguous
    runs within a row collapse; PlanRunner never sees these, since only
    CENTER and the planner's own goto lines are ever driven to.
    """
    by_row = {}
    for cell in cells:
        coord = parse_coordinate(cell) if isinstance(cell, str) else cell
        if coord is None:
            continue
        ci, ri = coord
        by_row.setdefault(ri, set()).add(ci)
    out = []
    for ri in sorted(by_row):
        cols = sorted(by_row[ri])
        start = prev = cols[0]
        for c in cols[1:] + [None]:
            if c is not None and c == prev + 1:
                prev = c
                continue
            if start == prev:
                out.append(coordinate_name(start, ri))
            else:
                out.append(f"{coordinate_name(start, ri)}-"
                           f"{coordinate_name(prev, ri)}")
            if c is not None:
                start = prev = c
    return ",".join(out)


def expand_cell_spec(spec: str):
    """Inverse of compact_cells: 'D2-Q2,F4' -> [(col, row), ...]."""
    cells, seen = [], set()
    for token in str(spec or "").split(","):
        token = token.strip()
        if not token:
            continue
        m = re.match(r"^([A-Za-z]{1,2})\s*(\d{1,2})\s*-\s*"
                     r"([A-Za-z]{1,2})\s*(\d{1,2})$", token)
        if m:
            a = parse_coordinate(f"{m.group(1)}{m.group(2)}")
            b = parse_coordinate(f"{m.group(3)}{m.group(4)}")
            if a is None or b is None:
                continue
            for rr in range(min(a[1], b[1]), max(a[1], b[1]) + 1):
                for cc in range(min(a[0], b[0]), max(a[0], b[0]) + 1):
                    if (cc, rr) not in seen:
                        seen.add((cc, rr)); cells.append((cc, rr))
            continue
        one = parse_coordinate(token)
        if one is not None and one not in seen:
            seen.add(one); cells.append(one)
    return cells


def obj_to_line(o) -> str:
    """One object dict -> the OBJECT: line the planner consumes."""
    aka = o.get("aka", [])
    aka = ", ".join(str(a) for a in aka) if isinstance(aka, list) else str(aka)
    comps = o.get("components") or []
    comps_s = ", ".join(_format_component(c) for c in comps) if comps else "(none)"
    touches = compact_cells(_touch_cells(o)) or o.get("touches", "")
    conf = "low - treat this name as a guess" if o.get("name_uncertain") else "ok"
    return (f"OBJECT: {o.get('name', 'object')}  "
            f"CENTER: {o.get('center', '')}  "
            f"TOUCHES: {touches}  "
            f"COLOR: {o.get('color', '?')}  "
            f"SIZE: {o.get('size', '?')}  "
            f"DESC: {o.get('desc', '')}  "
            f"ALSO_KNOWN_AS: {aka}  "
            f"NAME_CONFIDENCE: {conf}  "
            f"COMPONENTS: {comps_s}")


def object_list_text(objs) -> str:
    return "\n".join(obj_to_line(o) for o in objs)


def vision_report_text(objs) -> str:
    """Everything vision found, for the operator to read before the plan.

    The planner's own OBJECT: lines are too wide for the chat column, so the
    same content is folded into one short line per object: where it is, what
    it spans, and which of its parts were outlined.
    """
    if not objs:
        return "Vision found nothing on the board."
    lines = [f"Vision - {len(objs)} object(s) on the board:"]
    for o in objs:
        cells = [c for c in str(o.get("touches") or "").split(",") if c.strip()]
        span = f" ({len(cells)} cells)" if len(cells) > 1 else ""
        bits = [f"* {o.get('name', 'object')} @ {o.get('center', '?')}{span}"]
        colour = str(o.get("color") or "").strip()
        if colour and colour != "?":
            bits.append(f"  {colour}")
        if o.get("name_uncertain"):
            bits.append("  [unnamed - the naming model could not tell what it is]")
        comps = o.get("components") or []
        if comps:
            named = []
            for c in comps:
                cname = c.get("name", "part") if isinstance(c, dict) else str(c)
                ccell = c.get("center") if isinstance(c, dict) else None
                named.append(f"{cname}@{ccell}" if ccell else str(cname))
            bits.append("  parts: " + ", ".join(named))
        lines.append("".join(bits))
    return "\n".join(lines)


POLY_SAMPLES = 8
POLY_TOUCH_THRESHOLD = 0.28
POLY_RELATIVE_CUT = 0.34
POLY_MIN_COVER = 0.04


def _poly_area(poly):
    n = len(poly)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def _poly_centroid(poly):
    n = len(poly)
    if n == 0:
        return (0.0, 0.0)
    if n < 3:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    return (cx / (6.0 * a), cy / (6.0 * a))


def _point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    x0, y0 = poly[-1]
    for i in range(n):
        x1, y1 = poly[i]
        if ((y1 > y) != (y0 > y)) and \
           (x < (x0 - x1) * (y - y1) / ((y0 - y1) or 1e-9) + x1):
            inside = not inside
        x0, y0 = x1, y1
    return inside


MAX_TOUCH_CELLS_SLACK = 1.6
MAX_TOUCH_CELLS_PAD = 6


CENTROID_AGREE_CELLS = 0.25


def _cell_enclosed(cov, c, r) -> bool:
    """Does the object wrap around this cell on all four sides?

    Distinguishes a genuine hole -- the inside of a cup's rim, where the
    centre belongs -- from the open mouth of a crescent or a horseshoe,
    where it does not. Cheap and deliberately coarse: four axis scans over
    cells already known to be covered, no geometry.
    """
    return (any((cc, r) in cov for cc in range(c))
            and any((cc, r) in cov for cc in range(c + 1, CONFIG.n_cols))
            and any((c, rr) in cov for rr in range(r))
            and any((c, rr) in cov for rr in range(r + 1, CONFIG.n_rows)))


def set_center_pt(entry, pt):
    """Record (or clear) an object's unrounded centre on its dict.

    Clearing matters as much as setting: a stale center_pt outlives the
    outline it came from, and the overlay trusts it over the cell, so a
    refinement that cannot produce a new one must drop the old one rather
    than leave the dot behind on the object's previous position.
    """
    if pt is None:
        entry.pop("center_pt", None)
    else:
        entry["center_pt"] = [float(pt[0]), float(pt[1])]


def polygon_to_cells(poly, cap=None):
    """A (col, row) polygon in grid units -> (center_cell, touches, center_pt).

    `center_pt` is the same centre BEFORE it is snapped to a cell -- the
    continuous (col, row) position, for drawing. The robot can only be sent
    to a whole cell, but a dot drawn at that cell's midpoint sits up to 0.7
    cells from where the object's centre really is, which on a big bowl is
    an eighth of its width and reads as plainly off. The overlay draws the
    honest point; only the robot rounds.

    Coverage is measured by sampling points inside each candidate cell, so a
    thin or diagonal object only claims the cells it actually crosses rather
    than its whole bounding box -- the same rule S1-SRC's polygon_to_cells
    uses in its own ruler space.

    The number of cells is then capped against the outline's own area. A
    plant traced with long slack diagonals used to come back holding every
    cell on the board, which is not a location: it overlapped every other
    object, made the planner's OBJECT line thousands of characters long, and
    made any cell on the board look like part of the plant.
    """
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    if x1 <= x0 or y1 <= y0:
        return None, [], None

    ci_lo = max(0, int(x0)); ci_hi = min(CONFIG.n_cols - 1, int(x1))
    ri_lo = max(0, int(y0)); ri_hi = min(CONFIG.n_rows - 1, int(y1))

    cov = {}
    sum_x = sum_y = 0.0
    n_in = 0
    for ci in range(ci_lo, ci_hi + 1):
        for ri in range(ri_lo, ri_hi + 1):
            hits = 0
            for si in range(POLY_SAMPLES):
                sx = ci + (si + 0.5) / POLY_SAMPLES
                for sj in range(POLY_SAMPLES):
                    sy = ri + (sj + 0.5) / POLY_SAMPLES
                    if _point_in_poly(sx, sy, poly):
                        hits += 1
                        sum_x += sx
                        sum_y += sy
            n_in += hits
            if hits:
                cov[(ci, ri)] = hits / float(POLY_SAMPLES * POLY_SAMPLES)

    if not cov:
        return None, [], None
    best = max(cov.values())
    cut = min(POLY_TOUCH_THRESHOLD, max(POLY_MIN_COVER, best * POLY_RELATIVE_CUT))
    touches = [c for c, f in cov.items() if f >= cut]
    if not touches:
        return None, [], None

    if cap is None:
        cap = max(8, int(math.ceil(MAX_TOUCH_CELLS_SLACK * _poly_area(poly)
                                   + MAX_TOUCH_CELLS_PAD)))
    if len(touches) > cap:
        claimed = len(touches)
        touches = sorted(touches, key=lambda c: -cov[c])[:cap]
        print(f"[cells] outline claimed {claimed} cells for "
              f"{_poly_area(poly):.1f} cells of area - kept the {cap} "
              f"best-covered")

    wx = sum_x / n_in
    wy = sum_y / n_in
    gx, gy = _poly_centroid(poly)
    if abs(gx - wx) <= CENTROID_AGREE_CELLS and abs(gy - wy) <= CENTROID_AGREE_CELLS:
        wx, wy = gx, gy
    wc = min(CONFIG.n_cols - 1, max(0, int(round(wx, 9))))
    wr = min(CONFIG.n_rows - 1, max(0, int(round(wy, 9))))
    if (wc, wr) in cov or _cell_enclosed(cov, wc, wr):
        centre = (wc, wr)
    else:
        centre = min(cov.keys(),
                     key=lambda cr: ((cr[0] + 0.5 - wx) ** 2
                                     + (cr[1] + 0.5 - wy) ** 2, -cov[cr]))
    if centre not in touches:
        touches.append(centre)
    touches.sort(key=lambda c: (c[1], c[0]))
    return centre, touches, (wx, wy)


COMPONENT_ON_PARENT_MIN = 0.5

COMPONENT_MAX_AREA_RATIO = 1.15


def component_on_parent(poly, parent_poly) -> bool:
    """Is this component's outline actually ON the object it belongs to?

    Nothing downstream re-checks a part against its parent, and a part's cell
    BEATS the object's own CENTER when the planner picks up, pours or presses.
    So a part the close-up placed badly publishes a perfectly well-formed
    `pot@S17`, the arm drives to S17, and it pours into whatever is really
    sitting there while the outline on screen still looks right. That is not
    hypothetical: it is how "water the plant" ended up pouring into the cup.

    Accepted when the part's centroid lies inside the parent outline, or when
    at least half of the part does. Anything less is the close-up having
    wandered onto a neighbour, and the part keeps its name but loses its
    geometry.
    """
    if not isinstance(parent_poly, (list, tuple)) or len(parent_poly) < 3:
        return True
    if not isinstance(poly, (list, tuple)) or len(poly) < 3:
        return False
    try:
        parent = [(float(x), float(y)) for x, y in parent_poly]
        poly = [(float(x), float(y)) for x, y in poly]
    except (TypeError, ValueError):
        return False
    parent_area = _poly_area(parent)
    part_area = _poly_area(poly)
    if parent_area > 0 and part_area > parent_area * COMPONENT_MAX_AREA_RATIO:
        return False
    cx, cy = _poly_centroid(poly)
    if _point_in_poly(cx, cy, parent):
        return True
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    inside = total = 0
    for i in range(POLY_SAMPLES):
        sx = x0 + (i + 0.5) * (x1 - x0) / POLY_SAMPLES
        for j in range(POLY_SAMPLES):
            sy = y0 + (j + 0.5) * (y1 - y0) / POLY_SAMPLES
            if not _point_in_poly(sx, sy, poly):
                continue
            total += 1
            if _point_in_poly(sx, sy, parent):
                inside += 1
    return bool(total) and inside / float(total) >= COMPONENT_ON_PARENT_MIN


def resolve_overlaps(objects):
    """A cell belongs to ONE object. Hand each contested cell to its owner.

    Two objects claiming the same cell is two objects the planner can aim a
    pour or a pickup at and hit the wrong one. The SMALLER outline wins a
    contested cell, because the smaller claim is always the more specific one
    -- that is what "resting on" means, and it is why a plant traced loosely
    across the board cannot take the cup's own cells away from it. An object
    never loses its CENTER cell.
    """
    areas = []
    for o in objects:
        poly = o.get("polygon")
        areas.append(_poly_area(poly) if poly and len(poly) >= 3
                     else float("inf"))

    owner = {}
    for i, o in enumerate(objects):
        for cell in _touch_cells(o):
            bid = -areas[i]
            if cell not in owner or bid > owner[cell][0]:
                owner[cell] = (bid, i)

    for i, o in enumerate(objects):
        cells = _touch_cells(o)
        kept = [c for c in cells if owner.get(c, (None, i))[1] == i]
        lost = len(cells) - len(kept)
        centre = str(o.get("center") or "").strip().upper()
        if centre and centre not in kept:
            kept.append(centre)
        if lost > 0:
            print(f"[cells] {o.get('name')}: {lost} cell(s) "
                  f"belonged to a smaller object on top of it")
        o["touches"] = ",".join(kept)
    return objects


def restrict_to_reachable(objects, dropped=None):
    """Drop every cell the gripper's own geometry can never reach from each
    object's TOUCHES (and CENTER, if the cell affected is the centre)
    before the planner ever sees this object list.

    The old approach put every cell in front of the planner, including ones
    physically out of reach, and relied on a prompt rule telling it never to
    write a goto there. That is one more place a plan can go wrong for no
    reason the operator caused -- the planner has to notice the warning,
    re-derive which of an object's cells the warning applies to, and never
    slip. Filtering here removes the choice instead of trusting the
    planner not to make it: an unreachable coordinate is not one it is
    told to avoid, it is one that was never offered.

    Same shape as resolve_overlaps, and meant to run right alongside it, on
    the same objects list, before disambiguate_names/object_list_text.
    """
    bad_rows = unreachable_rows()
    bad_cols = unreachable_cols()
    if not bad_rows and not bad_cols:
        return objects

    def reachable(coord):
        return coord is not None and coord[1] not in bad_rows and coord[0] not in bad_cols

    kept_objects = []
    for o in objects:
        cells = _touch_cells(o)
        kept = [c for c in cells if reachable(parse_coordinate(c))]
        centre = str(o.get("center") or "").strip().upper()
        centre_coord = parse_coordinate(centre)
        if centre and not reachable(centre_coord):
            if kept:
                cc, cr = centre_coord or (0, 0)
                centre = min(kept, key=lambda c: (
                    (parse_coordinate(c)[0] - cc) ** 2
                    + (parse_coordinate(c)[1] - cr) ** 2))
            else:
                centre = ""
        if centre and centre not in kept:
            kept.append(centre)
        if not kept:
            print(f"[cells] {o.get('name')}: entirely out of reach -- "
                 f"dropped from the object list")
            if dropped is not None:
                entry = {"name": o.get("name"), "center": o.get("center"),
                         "aka": list(o.get("aka") or [])}
                if all(d.get("name") != entry["name"] for d in dropped):
                    dropped.append(entry)
            continue
        if len(kept) != len(cells):
            print(f"[cells] {o.get('name')}: {len(cells) - len(kept)} "
                 f"cell(s) out of reach -- dropped")
        o["touches"] = ",".join(kept)
        o["center"] = centre
        kept_objects.append(o)
    return kept_objects


def _touch_cells(obj):
    """An object's TOUCHES as a flat list of single cell names.

    Expands range notation ("I6-M6") as well as plain cells, because
    compact_cells() WRITES that notation -- obj_to_line shows the planner
    "TOUCHES: I6-M6,I7-M7" -- and anything that reads touches back has to
    understand what was written. A plain comma split returned the literal
    string "I6-M6", which parse_coordinate cannot read, so every range
    counted as an unparseable cell: restrict_to_reachable deleted all ten
    cells of a shelf sitting in the middle of the reachable board and left
    it holding only its CENTER, and resolve_overlaps could not see those
    cells to arbitrate them at all.
    """
    raw = obj.get("touches") or ""
    if isinstance(raw, (list, tuple)):
        raw = ",".join(str(c) for c in raw)
    cells, seen = [], set()
    for token in str(raw).split(","):
        token = token.strip().upper()
        if not token:
            continue
        if "-" in token:
            for col, row in expand_cell_spec(token):
                name = coordinate_name(col, row)
                if name not in seen:
                    seen.add(name)
                    cells.append(name)
            continue
        if token not in seen:
            seen.add(token)
            cells.append(token)
    return cells


def _first_json_object(text: str):
    """The span of the first balanced {...} object in text, or None.

    A naive greedy regex (first '{' to last '}') swallows any trailing prose
    that happens to contain a brace (e.g. "the {corner} shelf"), producing a
    span json.loads can't parse even though a valid object was right there.
    Counting braces (respecting quoted strings) finds its real end instead.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def size_class(span_in: float) -> str:
    """The planner's SIZE word for an outline this many inches across."""
    if span_in <= 0:
        return "?"
    return "small" if span_in < 4.0 else "medium" if span_in <= 10.0 else "large"


GRIP_PART_PRIORITY = ("handle", "grip", "shaft", "stick", "pole", "stem",
                      "strap", "neck", "rim", "edge", "wall", "body", "base")

GRIP_AVOID_PARTS = (
    "blade", "cutting edge", "sharp", "tooth", "teeth", "tine", "point",
    "burner", "hob", "hotplate", "heating element", "element", "flame",
    "bristle", "brush head", "mop head", "head", "pad", "sponge",
    "spout", "nozzle", "trigger", "button", "switch", "dial", "knob",
    "screen", "display", "glass", "window", "panel",
    "cavity", "interior", "drum", "opening", "slot", "contents", "lid",
)

GRIP_HAZARD_PARTS = ("blade", "cutting edge", "sharp", "tooth", "teeth",
                     "tine", "burner", "hob", "hotplate", "heating element",
                     "flame")


def _is_hazard_part(name: str) -> bool:
    low = str(name or "").strip().lower()
    return any(bad in low for bad in GRIP_HAZARD_PARTS)


def _is_avoid_part(name: str, extra=()) -> bool:
    low = str(name or "").strip().lower()
    if not low:
        return True
    bad_words = tuple(GRIP_AVOID_PARTS) + tuple(
        str(e).strip().lower() for e in extra if str(e).strip())
    return any(bad and bad in low for bad in bad_words)


def _comp_verdict(c) -> str:
    """The component pass's own verdict for a part: 'hold', 'avoid', or ''."""
    v = str(c.get("grip") or "").strip().lower()
    return v if v in ("hold", "avoid") else ""


def object_cells(o) -> set:
    """Every cell an object occupies, upper-cased, CENTER included."""
    cells = {str(o.get("center") or "").strip().upper()}
    for c in str(o.get("touches") or "").split(","):
        c = c.strip().upper()
        if c:
            cells.add(c)
    cells.discard("")
    return cells


GRIP_CORNER_INSET = 0.35


def top_right_grip_point(o):
    """The object's top-right corner as a (col, row) point on the object.

    Read off the OUTLINE (FastSAM's, traced from the pixels), not
    off its cells: the outline point nearest the outline's own top-right
    bounding corner, pulled GRIP_CORNER_INSET toward the object's middle.
    A boundary cell can be one the object barely covers; this point is
    always on the object. None when there is no outline.
    """
    poly = o.get("polygon") if isinstance(o, dict) else None
    if not poly or len(poly) < 3:
        return None
    try:
        pts = [(float(p[0]), float(p[1])) for p in poly]
    except (TypeError, ValueError, IndexError):
        return None
    dense = []
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        steps = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.1)))
        dense.extend((a[0] + (b[0] - a[0]) * k / steps,
                      a[1] + (b[1] - a[1]) * k / steps) for k in range(steps))
    max_c = max(p[0] for p in pts)
    min_r = min(p[1] for p in pts)
    corner = min(dense, key=lambda p: math.hypot(max_c - p[0], p[1] - min_r))
    return _inset(corner, _poly_centroid(pts), GRIP_CORNER_INSET)


def top_right_grip_cell(o) -> str:
    """Top-right occupied cell in camera/grid view.

    Scored against the object's own bounding corner (its rightmost column,
    its topmost row -- row 0 is the top of the image) rather than picked
    column-first: column-first degenerates on a diagonal object (a sock
    lying top-left to bottom-right) where the rightmost column is only
    reached near the BOTTOM of the shape, handing back a cell nowhere near
    the visual top-right. Minimising distance to the bounding corner keeps
    the grip on whichever occupied cell is genuinely closest to top-right,
    while still only ever choosing a cell the object actually occupies (so
    an L or a curve whose bounding-box corner is bare board still grips
    itself, not empty space).

    An outline (top_right_grip_point) is preferred when the resulting cell
    is one the object's own cells confirm it occupies -- more precise than
    the cell-based fallback on a shape whose bounding corner is bare board.
    """
    parsed = []
    for cell in object_cells(o):
        coord = parse_coordinate(cell)
        if coord is not None:
            parsed.append((coord[0], coord[1], cell))
    if not parsed:
        return str(o.get("center") or "").strip().upper()
    pt = top_right_grip_point(o)
    if pt is not None:
        cell = _fold_point_name(pt)
        if cell in {c for _, _, c in parsed}:
            return cell
    max_col = max(c for c, _, _ in parsed)
    min_row = min(r for _, r, _ in parsed)

    def dist(item):
        col, row, _ = item
        return (max_col - col) + (row - min_row)

    return min(parsed, key=lambda item: (dist(item), -item[0], item[1]))[2]


GRIP_CELL_SLACK = 1


def cell_on_object(o, cell: str, slack: int = GRIP_CELL_SLACK) -> bool:
    """Is `cell` a cell of `o` (or within `slack` cells of one)?

    The slack ring keeps a legitimate grasp feature that juts a cell past a
    tight outline (a handle, a spout) while still ruling out anything
    genuinely elsewhere on the board.
    """
    want = parse_coordinate(str(cell or ""))
    if want is None:
        return False
    known = [parse_coordinate(c) for c in object_cells(o)]
    known = [c for c in known if c is not None]
    if not known:
        return False
    return any(abs(want[0] - c[0]) <= slack and abs(want[1] - c[1]) <= slack
               for c in known)


def default_grip_part(o):
    """Best graspable component of an object, as (part_name, cell), or None.

    Deterministic and offline -- it reads only what the component pass
    already measured. This is what makes the feature degrade gracefully:
    with Gripper AI off, timed out, or simply silent about this object, a
    knife whose handle was outlined is still picked up by the handle.
    """
    best = None
    for c in (o.get("components") or []):
        name = c.get("name") or ""
        cell = str(c.get("center") or "").strip().upper()
        verdict = _comp_verdict(c)
        if not cell or verdict == "avoid" or _is_hazard_part(name):
            continue
        if verdict != "hold" and _is_avoid_part(name):
            continue
        if not cell_on_object(o, cell):
            continue
        rank = next((i for i, key in enumerate(GRIP_PART_PRIORITY)
                    if key in name.lower()), None)
        if rank is None:
            if verdict != "hold":
                continue
            rank = len(GRIP_PART_PRIORITY)
        if best is None or rank < best[0]:
            best = (rank, name, cell)
    return (best[1], best[2]) if best else None


def _match_object(name: str, objs: list):
    low = str(name or "").strip().lower()
    if not low:
        return None
    for o in objs:
        if str(o.get("name", "")).strip().lower() == low:
            return o
    for o in objs:
        aka = o.get("aka") or []
        if isinstance(aka, str):
            aka = [aka]
        if any(str(a).strip().lower() == low for a in aka):
            return o
    for o in objs:
        on = str(o.get("name", "")).strip().lower()
        if on and (on in low or low in on):
            return o
    return None


def _component_cell(o, part: str, extra_avoid=()):
    low = str(part or "").strip().lower()
    if not low or _is_hazard_part(low) or _is_avoid_part(low, extra_avoid):
        return None, None
    comps = o.get("components") or []
    for c in comps:
        if (c.get("name") or "").strip().lower() == low:
            if _comp_verdict(c) == "avoid" or _is_hazard_part(c.get("name")):
                return None, None
            cell = str(c.get("center") or "").strip().upper()
            return (c.get("name"), cell) if cell else (None, None)
    for c in comps:
        cn = (c.get("name") or "").strip().lower()
        if not cn or _comp_verdict(c) == "avoid":
            continue
        if (cn in low or low in cn) and not _is_avoid_part(cn, extra_avoid):
            cell = str(c.get("center") or "").strip().upper()
            if cell:
                return c.get("name"), cell
    return None, None


def resolve_grip_cells(grips: list, objs: list) -> list:
    """Gripper AI's answer + the object list -> grip points the planner can use.

    Every returned cell is one the OBJECT LIST already contained for that
    object. A model answer naming an unknown object, an unsafe part, or a
    cell not on the object is discarded rather than corrected -- the
    fallback (the object's own CENTER) is the behaviour the planner had
    anyway. Objects the model skipped are filled in from their components,
    so grip points exist even when the call returned nothing at all.
    """
    resolved, claimed = [], set()

    for g in grips or []:
        if not isinstance(g, dict):
            continue
        o = _match_object(g.get("object"), objs)
        if o is None:
            continue
        name = str(o.get("name", "object"))
        if name in claimed:
            continue
        avoid = g.get("avoid") or []
        if isinstance(avoid, str):
            avoid = [avoid]
        center = str(o.get("center") or "").strip().upper()

        part_name = str(g.get("part") or "").strip()
        part, cell = _component_cell(o, part_name, avoid)
        source = "part"
        if cell and not cell_on_object(o, cell):
            part, cell = None, None
        if not cell:
            raw = str(g.get("cell") or "").strip().upper()
            if (raw in object_cells(o)
                    and not _is_hazard_part(part_name)
                    and not _is_avoid_part(part_name, avoid)):
                part, cell, source = (part_name or None), raw, "vision"
        if not cell:
            fallback = default_grip_part(o)
            if fallback:
                part, cell, source = fallback[0], fallback[1], "parts"
        if not cell or not cell_on_object(o, cell):
            continue

        cell = top_right_grip_cell(o)
        source = "camera-top-right"
        override = bool(center and cell != center)
        if not (override or g.get("approach") or avoid or g.get("why")):
            continue
        claimed.add(name)
        resolved.append({
            "object": name, "part": part or "", "cell": cell, "center": center,
            "approach": str(g.get("approach") or "").strip().lower(),
            "avoid": [str(a).strip() for a in avoid if str(a).strip()],
            "why": str(g.get("why") or "").strip(),
            "source": source, "override": override,
        })

    for o in objs:
        name = str(o.get("name", "object"))
        if name in claimed:
            continue
        corner_cell = top_right_grip_cell(o)
        if not corner_cell:
            continue
        center = str(o.get("center") or "").strip().upper()
        if corner_cell == center:
            continue
        claimed.add(name)
        resolved.append({
            "object": name, "part": "top-right corner", "cell": corner_cell,
            "center": center, "approach": "", "avoid": [], "why": "",
            "source": "camera-top-right", "override": True,
        })
    return resolved


GRIP_SUBST_RE = re.compile(
    r"(goto_coordinate\s*[:=]?\s*)([A-Za-z]{1,2})\s*,?\s*(\d{1,2})\b", re.I)


def _bare_command(line: str) -> str:
    l = re.sub(r"^\s*\d+\.\s*", "", line)
    return l.split("#", 1)[0].strip()


def _shift_coordinate_line(line: str, dc: int, dr: int):
    """Rewrite one goto_coordinate line's cell by (dc, dr) columns/rows.

    Returns the rewritten line, or the line unchanged if it does not parse
    or the shifted cell falls off the board (better to place dead-centre
    than to send the gantry somewhere CONFIG never validated).
    """
    m = GRIP_SUBST_RE.search(line)
    if not m:
        return line
    coord = parse_coordinate(f"{m.group(2).upper()}{m.group(3)}")
    if coord is None:
        return line
    col_idx, row_idx = coord[0] + dc, coord[1] + dr
    if not (0 <= col_idx < CONFIG.n_cols and 0 <= row_idx < CONFIG.n_rows):
        return line
    name = coordinate_name(col_idx, row_idx)
    nm = re.match(r"([A-Za-z]{1,2})(\d{1,2})", name)
    return GRIP_SUBST_RE.sub(
        lambda mm, _c=nm.group(1), _r=nm.group(2): f"{mm.group(1)}{_c}, {_r}",
        line, count=1)


def apply_grip_substitution(text: str, grips: list):
    """The ONLY place a grip point changes what the robot does.

    For each object with an override, finds the goto_coordinate that leads
    straight into that object's FIRST pickup and rewrites the coordinate on
    that one line, leaving every other line, every other cell, every later
    pickup of the same object untouched. A goto not immediately followed by
    pickup (a slide, a press, a contact pass) is never touched, and neither
    is a cell no override names.

    Gripping off-centre moves the object's own centre with it: the jaws
    close on the grip cell, so whatever the gripper is holding sits shifted
    from centre by exactly (grip cell - object centre), the whole time it is
    held. The very next goto_coordinate -> keep after that pickup -- the
    object's placement, per the planner's own "finish one object's full
    sequence before starting another" rule -- is shifted by that same
    vector, so it is the OBJECT's centre that lands on the destination
    cell the plan asked for, not the gripper's off-centre contact point.

    Returns (possibly-rewritten text, [grip dicts actually applied]).
    """
    overrides = {}
    for g in grips or []:
        if g.get("override") and g.get("center") and g.get("cell"):
            overrides.setdefault(str(g["center"]).strip().upper(), g)
    if not overrides:
        return text, []

    lines = text.splitlines()
    used, applied = set(), []
    pending = None
    place_shift = None

    for i, line in enumerate(lines):
        bare = _bare_command(line)
        if not bare:
            continue
        low = bare.lower()
        if low.startswith("goto_coordinate"):
            m = GRIP_SUBST_RE.search(bare)
            pending = (i, m) if m else None
            if place_shift is not None:
                dc, dr = place_shift
                lines[i] = _shift_coordinate_line(lines[i], dc, dr)
            continue
        if low == "pickup":
            if pending is not None:
                i0, m0 = pending
                cell = f"{m0.group(2).upper()}{m0.group(3)}"
                g = overrides.get(cell)
                if g is not None and cell not in used:
                    grip_coord = parse_coordinate(g["cell"])
                    centre_coord = parse_coordinate(cell)
                    nm = re.match(r"([A-Za-z]{1,2})(\d{1,2})", g["cell"])
                    if nm:
                        lines[i0] = GRIP_SUBST_RE.sub(
                            lambda mm, _c=nm.group(1), _r=nm.group(2):
                                f"{mm.group(1)}{_c}, {_r}",
                            lines[i0], count=1)
                        used.add(cell)
                        applied.append(g)
                        if grip_coord is not None and centre_coord is not None:
                            place_shift = (grip_coord[0] - centre_coord[0],
                                          grip_coord[1] - centre_coord[1])
                            if place_shift == (0, 0):
                                place_shift = None
            pending = None
            continue
        if low == "keep":
            place_shift = None
            pending = None
            continue
        pending = None
    return "\n".join(lines), applied


def _cells_of(o, shift=(0, 0)):
    """Every cell of an object (CENTER, TOUCHES, part cells), shifted."""
    out = set()
    for cell in object_cells(o):
        c = parse_coordinate(cell)
        if c is not None:
            out.add((c[0] + shift[0], c[1] + shift[1]))
    return out


def _press_part_cells(o, shift=(0, 0)):
    """Cells of an object's own WORKING parts -- a press there stays put.
    A garment's fold landmarks and a cloth's fold grip points are not
    working parts."""
    skip = set(CLOTH_FOLD_POINT_NAMES)
    for names in FOLD_ROLES.values():
        skip.update(names)
    out = set()
    for comp in o.get("components") or []:
        name = str(comp.get("name") or "").strip().lower()
        c = parse_coordinate(str(comp.get("center") or ""))
        if c is None or name in skip or name == "body":
            continue
        out.add((c[0] + shift[0], c[1] + shift[1]))
    return out


def _set_goto_cell(line: str, col: int, row: int) -> str:
    name = coordinate_name(col, row)
    nm = re.match(r"([A-Za-z]{1,2})(\d{1,2})", name)
    return GRIP_SUBST_RE.sub(
        lambda mm, _c=nm.group(1), _r=nm.group(2): f"{mm.group(1)}{_c}, {_r}",
        line, count=1)


def enforce_gripper_targets(text: str, objects, task=""):
    """Rewrite a plan so every pickup closes on the object's top-right corner
    and every bare press lands on the object's centre. See the rules above.

    Objects are followed through the plan: an object kept somewhere is found
    there by a later pickup or press. Returns (text, [change dicts]).

    A shift is applied to every goto while the object is held (so it lands
    where the plan intended), or to none of them -- never to some. The old
    version silently dropped the shift on whichever single goto happened to
    fall off-board while still shifting the pickup itself, so the object's
    real centre ended up short of its destination by a full grip's width,
    with nothing in the plan or transcript showing why (found by fuzzing
    near the board edge, 2026-09-26: a box near column T got a shifted
    top-right pickup but an unshifted destination cell). Fixed by checking
    every later goto up to the matching keep/release BEFORE touching any
    line, so an off-board goto anywhere in the held route cancels the grip
    shift for the whole route, not just its own line -- the object is then
    gripped at CENTER for that pickup, same as when it has no outline.
    """
    objs = list(objects or [])
    if not text or not objs:
        return text, []
    fold_cells = set()
    if is_fold_task(task):
        for o in objs:
            for m in fold_recipe(o).get("moves") or ():
                c = parse_coordinate(m.get("pick_cell") or "")
                if c is not None:
                    fold_cells.add(c)

    def on_board(c):
        return 0 <= c[0] < CONFIG.n_cols and 0 <= c[1] < CONFIG.n_rows

    lines = text.splitlines()
    bares = [_bare_command(l) for l in lines]
    lows = [b.lower() if b else "" for b in bares]

    def goto_cell(i):
        m = GRIP_SUBST_RE.search(bares[i])
        return parse_coordinate(f"{m.group(2).upper()}{m.group(3)}") if m else None

    def held_route(start_i):
        """[(line index, cell)] for every goto from just after `start_i`
        up to (not including) the next keep/release -- the whole route a
        shift set at `start_i` would need to apply to, checked as one."""
        out = []
        for j in range(start_i + 1, len(lines)):
            if lows[j].startswith("goto_coordinate"):
                c = goto_cell(j)
                if c is not None:
                    out.append((j, c))
            elif lows[j] in ("keep", "release"):
                break
        return out

    changes = []
    moved = [(0, 0)] * len(objs)

    def find(cell):
        hits = [i for i, o in enumerate(objs) if cell in _cells_of(o, moved[i])]
        if not hits:
            return None
        for i in hits:
            c = parse_coordinate(str(objs[i].get("center") or ""))
            if c is not None and (c[0] + moved[i][0], c[1] + moved[i][1]) == cell:
                return i
        return min(hits, key=lambda i: len(_cells_of(objs[i])))

    def try_shift(gi, planned, idx, target, action, where):
        """Apply (target - planned) to `gi` and every goto in its held
        route, all together, or not at all if any of them would leave the
        board. Updates `moved[idx]` either way, from whatever cell the
        object actually ends up registered at."""
        shift = (target[0] - planned[0], target[1] - planned[1])
        route = held_route(gi)
        if shift != (0, 0) and not all(on_board((c[0] + shift[0], c[1] + shift[1]))
                                       for _, c in route):
            target, shift = planned, (0, 0)
        if shift != (0, 0):
            lines[gi] = _set_goto_cell(lines[gi], *target)
            for j, c in route:
                lines[j] = _set_goto_cell(lines[j], c[0] + shift[0], c[1] + shift[1])
            changes.append({"object": objs[idx].get("name"), "action": action,
                            "was": coordinate_name(*planned),
                            "now": coordinate_name(*target), "where": where})
        dest = route[-1][1] if route else planned
        moved[idx] = (moved[idx][0] + dest[0] - planned[0],
                      moved[idx][1] + dest[1] - planned[1])

    last_goto = None
    holding = None
    for i, low in enumerate(lows):
        if not low:
            continue
        if low.startswith("goto_coordinate"):
            last_goto = (i, goto_cell(i))
            continue
        if low == "pickup":
            holding = None
            if last_goto is not None and last_goto[1] is not None:
                gi, planned = last_goto
                idx = find(planned)
                if idx is not None and planned not in fold_cells:
                    o = objs[idx]
                    tr = parse_coordinate(top_right_grip_cell(o))
                    target = ((tr[0] + moved[idx][0], tr[1] + moved[idx][1])
                              if tr is not None else planned)
                    if not on_board(target):
                        target = planned
                    try_shift(gi, planned, idx, target, "pickup",
                             "its top-right corner")
                    holding = idx
            last_goto = None
            continue
        if low == "keep":
            holding = None
            last_goto = None
            continue
        if low == "press":
            if holding is None and last_goto is not None and last_goto[1] is not None:
                gi, planned = last_goto
                idx = find(planned)
                if idx is not None and planned not in _press_part_cells(objs[idx], moved[idx]):
                    o = objs[idx]
                    c = parse_coordinate(str(o.get("center") or ""))
                    target = ((c[0] + moved[idx][0], c[1] + moved[idx][1])
                              if c is not None else planned)
                    if not on_board(target):
                        target = planned
                    try_shift(gi, planned, idx, target, "press", "its centre")
            last_goto = None
            continue
        if low == "release":
            last_goto = None
            continue
        last_goto = None
    return "\n".join(lines), changes


def gripper_target_lines(changes: list) -> list:
    """Applied gripper rules -> one readable sentence each, for the transcript."""
    verb = {"pickup": "pick up", "press": "press"}
    return [f"{verb.get(c['action'], c['action'])} {c['object']} at {c['now']} "
            f"- {c['where']} (plan said {c['was']})" for c in changes]


GOTO_RE = re.compile(
    r"goto_coordinate\s*[:=]?\s*([A-Za-z]{1,2})\s*,?\s*(\d{1,2})\b", re.I)


def load_custom_training():
    """Standing planner rules stored inside this single-file app."""
    data = S1_EMBEDDED_STATE.get("custom_training") or []
    return [s for s in data if isinstance(s, str) and s.strip()] \
        if isinstance(data, list) else []


def save_custom_training(rules):
    """Persist standing planner rules inside S1.py."""
    S1_EMBEDDED_STATE["custom_training"] = list(rules)
    persist_embedded_state()


def parse_plan_commands(text: str):
    """Plan text -> bare command lines, in order.

    Same shape as S1-SRC's CommandRunner._parse: numbering, comments and
    the PLAN / DESTINATIONS header are presentation; only the commands
    themselves are executable.
    """
    cmds = []
    started = False
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not started:
            if re.match(r"^(\d+\.|#)", line):
                started = True
            else:
                continue
        if line.startswith("#") or line.upper().startswith("MISSING:"):
            continue
        line = re.sub(r"^\d+\.\s*", "", line)
        line = line.split("#", 1)[0].strip()
        if line and not line.lower().startswith("invoke"):
            cmds.append(line)
    return cmds


def missing_objects(text: str):
    """Objects the planner declared absent. Nothing runs on a partial plan."""
    names = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if not line.upper().startswith("MISSING:"):
            continue
        name = re.split(r"\s+[-–]\s+", line.split(":", 1)[1].strip(),
                        maxsplit=1)[0].strip()
        if name and name not in names:
            names.append(name)
    return names


def _same_object_word(missing_name: str, obj) -> bool:
    """Does a MISSING: line's name refer to this (seen) object?"""
    m = clean_object_name(missing_name)
    names = [clean_object_name(obj.get("name"))] + [
        clean_object_name(a) for a in (obj.get("aka") or [])]
    return any(n and (n == m or n in m or m in n) for n in names)


ALREADY_DONE_RE = re.compile(r"^\s*#?\s*ALREADY DONE\s*[:\-]\s*(.*)$", re.I | re.M)


def plan_already_done(text: str) -> str:
    """The planner's reason when the task's goal is already true, else "".

    Only counts when the plan has no real actions -- an ALREADY DONE comment
    beside real commands is the planner narrating, and the commands run.
    """
    m = ALREADY_DONE_RE.search(text or "")
    if not m or has_plan_actions(parse_plan_commands(text)):
        return ""
    return m.group(1).strip() or "the task's goal is already met"


def no_action_retry_note(plan: str) -> str:
    """The corrective message for a planner answer that planned nothing."""
    reason = extract_plan_summary(plan)
    missing = missing_objects(plan)
    said = []
    if reason:
        said.append(f'you said: "{reason}"')
    if missing:
        said.append("you wrote MISSING for: " + ", ".join(missing))
    return (
        "Your answer contains NO executable commands"
        + (" (" + "; ".join(said) + ")" if said else "")
        + ", so the robot would do nothing and the task fails. You cannot "
        "ask the operator anything - there is no reply channel. Re-read "
        "YOU CANNOT ASK THE OPERATOR ANYTHING and answer again:\n"
        "- If several objects fit a singular description, PICK ONE by the "
        "rule (closest to the destination, else first in reading order), "
        "say which in a # comment, and plan it.\n"
        "- If the operator's word for an object matches no name, choose the "
        "listed object it most plausibly describes by look, material, size "
        "and shape (vision's names are guesses), say so, and plan it.\n"
        "- If the goal is already true on the board, answer only "
        "`# ALREADY DONE: <reason>` and Task_Completed.\n"
        "- Only if NO listed object could plausibly be something the task "
        "needs, keep a MISSING: line for that thing - and still plan every "
        "other part of the task.\n"
        "Answer with the command sequence only.")


def has_plan_actions(commands):
    """A completion marker cannot turn a refusal into an executable plan."""
    for command in commands:
        command = str(command).strip()
        move = GOTO_RE.fullmatch(command)
        if move and parse_coordinate(f"{move.group(1)}{move.group(2)}") is not None:
            return True
        if re.fullmatch(r"(?:pickup|keep|press|release|open_doors?|close_doors?)",
                        command, re.I):
            return True
        if re.fullmatch(r"(?:pour|slice)(?:\([^\n]*\))?", command, re.I):
            return True
    return False


def extract_plan_summary(text: str) -> str:
    """The one-line '# ...' plan summary that precedes the numbered commands.

    Everything above it (PLAN:/DESTINATIONS:) is the planner's own working
    notes and never shown; this line is what the operator actually reads
    before the coordinate steps.
    """
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+\.", line):
            break
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            if body and not body.upper().startswith("MISSING:"):
                return body
    return ""


ACTION_LABELS = {
    "pickup": "PICK UP",
    "keep": "PLACE",
    "press": "PRESS",
    "release": "RELEASE",
    "open_door": "OPEN DOOR",
    "close_door": "CLOSE DOOR",
    "pour": "POUR",
    "slice": "SLICE",
    "wait_x": "WAIT",
    "task_completed": "TASK COMPLETE",
}


def action_label(cmd: str) -> str:
    """A plan line -> the words shown on the banner while it is held."""
    bare = cmd.split("(", 1)[0].strip().lower()
    label = ACTION_LABELS.get(bare, cmd.upper())
    if bare == "pour" and "(" in cmd:
        arg = cmd.split("(", 1)[1]
        frac = re.search(r"([\d.]+)", arg)
        if frac:
            value = float(frac.group(1))
            if "%" not in arg:
                value *= 100
            label = f"POUR {value:g}%"
    elif bare == "wait_x" and "(" in cmd:
        secs = re.search(r"(\d+(?:\.\d+)?)", cmd.split("(", 1)[1])
        if secs:
            label = f"WAIT {float(secs.group(1)):g}s"
    elif bare == "slice" and "(" in cmd:
        label = "SLICE " + cmd.split("(", 1)[1].rstrip(")").strip()
    return label


SPEAK_WORDS = {"pickup": "pick up", "keep": "keep", "press": "press",
              "release": "release", "pour": "pour"}

class SimpleGripperPanel:
    """The small card a plan opens when it reaches a gripper step.

    The full GripperPanel is a workbench -- jaw slider, height pair, jog
    d-pad, four automatic buttons, a status block. Popping that open in the
    middle of a run buries the one decision the operator actually has (is
    the jaw over the work?) in controls that are wrong to touch mid-plan.
    This card has only what that decision needs:

      - a jog d-pad that sends "uq"/"dq"/"lq"/"rq" for SIMPLE_JOG_PULSE_S,
      - STOP, which is live at every moment including while the action
        itself is running,
      - DONE, which starts the action for whichever step opened it, after
        the same one-second gap every later command in that action gets.

    The card waits while the operator adjusts the head. STOP remains
    available while the action runs.
    """

    WIDTH = 380
    PAD = 22
    ROW_H = 42
    JOG_BTN = 52
    JOG_GAP = 16
    ROW_GAP = 14
    JOG_LAYOUT = {"up": (0, 1), "left": (1, 0), "right": (1, 2), "down": (2, 1)}
    JOG_ARROWS = {"up": "^", "down": "v", "left": "<", "right": ">"}

    TITLES = {"pickup": "Pick up", "keep": "Keep", "press": "Press",
              "release": "Release"}

    def __init__(self):
        self.visible = False
        self.action = ""
        self.automatic = True
        self.buttons = []
        self._anim = 0.0
        self._last_rect = None
        self.jog_dir = None
        self.jog_until = 0.0
        self.handed_off = False
        self.last_msg = ""
        self.on_run = None
        self.action_busy = None
        self.on_abort = None

    def open_for(self, action: str, automatic: bool = True):
        """A plan step has arrived. Show the card, and wait.

        The operator can adjust for as long as needed. The action starts
        (after the usual one-second gap) when they press DONE.

        No automatic action gets the card, pickup included: the head is
        wherever the operator (or the Simple Gripper card's own earlier
        jog) already left it, and every automatic action -- pickup, keep,
        press, release -- now runs straight through on its own rather than
        stopping the plan on a prompt. Manual mode still opens the card and
        waits, since there the operator IS the action.
        """
        self.action = str(action or "").lower()
        self.automatic = bool(automatic)
        self.handed_off = False
        if self.automatic:
            self.visible = False
            return self._run("auto")
        self.visible = True
        self.last_msg = (f"{self.title()}: adjust the head, then press DONE.")
        return self.last_msg

    def close(self):
        self.visible = False

    def title(self) -> str:
        return self.TITLES.get(self.action, self.action.title() or "Action")

    def running(self) -> bool:
        """Whether the automatic action this card started is still going."""
        if not self.handed_off or self.action_busy is None:
            return False
        try:
            return bool(self.action_busy())
        except Exception:
            return False

    def busy(self) -> bool:
        """Whether the plan should keep waiting on this card.

        True from the moment it opens until the action it started has
        finished -- including the whole time it sits cancelled, waiting for
        someone to press DONE. That wait is the point of cancelling.

        A running action is checked before visibility, since a keep, press
        or release starts without ever showing the card and the plan still
        has to wait for it.
        """
        if self.running():
            return True
        if not self.visible:
            return False
        return not self.handed_off

    def _jog(self, direction: str) -> str:
        """One SIMPLE_JOG_PULSE_S pulse of "uq"/"dq"/"lq"/"rq", then s."""
        if not ARDUINO.connected:
            return f"Not connected -- {direction} not sent."
        if self.jog_dir is not None:
            ARDUINO.halt()
        letter = DIRECTION_LETTERS[direction] + SLOW_SUFFIX
        if not ARDUINO.send_command(letter):
            self.jog_dir = None
            return f"Could not send {letter} -- the board may still be booting."
        self.jog_dir = direction
        self.jog_until = time.monotonic() + SIMPLE_JOG_PULSE_S
        return f'Jogging {direction} ("{letter}") for {SIMPLE_JOG_PULSE_S:g}s.'

    def stop(self) -> str:
        """Unconditional stop, live at every moment this card is open.

        Not gated on jog_dir or on whether an action is running.
        """
        self.jog_dir = None
        if self.running() and self.on_abort is not None:
            self.on_abort()
            self.last_msg = ("Stopped -- sent s and abandoned the running "
                             f"{self.action or 'action'}.")
            return self.last_msg
        if not ARDUINO.connected:
            self.last_msg = "Not connected -- nothing to stop."
            return self.last_msg
        if ARDUINO.halt():
            self.last_msg = "Stopped -- sent s."
        else:
            self.last_msg = "Could not send s -- the board may still be booting."
        return self.last_msg

    def cancel(self) -> str:
        """Keep the card waiting for DONE while the operator adjusts."""
        if not self.handed_off:
            self.last_msg = f"{self.title()}: adjust the head, then press DONE."
        return self.last_msg

    def confirm(self) -> str:
        """DONE: start the action, after its usual one-second gap."""
        return self._run("DONE")

    def _run(self, why: str) -> str:
        if self.handed_off:
            self.last_msg = f"{self.title()} is already running."
            return self.last_msg
        if self.jog_dir is not None:
            ARDUINO.halt()
            self.jog_dir = None
            self.jog_until = 0.0
        self.handed_off = True
        if not self.automatic or self.on_run is None:
            self.last_msg = f"{self.title()} confirmed ({why})."
            return self.last_msg
        self.last_msg = f"{self.title()} ({why}): {self.on_run(self.action)}"
        return self.last_msg

    def tick(self):
        now = time.monotonic()
        if self.jog_dir is not None and now >= self.jog_until:
            ARDUINO.halt()
            self.jog_dir = None
        if self.visible and self.handed_off and not self.running():
            self.close()

    def _height(self, up: bool) -> str:
        """A timed hu/hd pulse, the same shape as the jog.

        The big card's height buttons fire hu/hd and leave them running --
        right there, where the operator is watching the axis and can stop
        it. On this card, in the middle of a run, a height command that
        never ends is how a head drives itself into the board, so it is
        bounded like every other motion here.
        """
        cmd = HEIGHT_UP_CMD if up else HEIGHT_DOWN_CMD
        if not ARDUINO.connected:
            return f"Not connected -- {cmd} not sent."
        if self.jog_dir is not None:
            ARDUINO.halt()
        if not ARDUINO.send_command(cmd):
            self.jog_dir = None
            return f"Could not send {cmd} -- the board may still be booting."
        self.jog_dir = "up" if up else "down"
        self.jog_until = time.monotonic() + SIMPLE_JOG_PULSE_S
        return f"Height {'up' if up else 'down'} ({cmd}) for {SIMPLE_JOG_PULSE_S:g}s."

    def _rect_contains(self, x, y) -> bool:
        if not self._last_rect:
            return False
        px, py, pw, ph = self._last_rect
        return px <= x <= px + pw and py <= y <= py + ph

    def press(self, x, y):
        """None when the click was not ours, otherwise a status string."""
        if not self.visible:
            return None
        for b in self.buttons:
            if not b.contains(x, y):
                continue
            if b.kind == "simple_jog":
                self.last_msg = self._jog(b.value)
            elif b.kind == "simple_stop":
                self.stop()
            elif b.kind == "simple_cancel":
                self.cancel()
            elif b.kind == "simple_height":
                self.last_msg = self._height(b.value == "up")
            elif b.kind == "simple_done":
                self.confirm()
            elif b.kind == "simple_close":
                self.close()
            return self.last_msg
        return "" if self._rect_contains(x, y) else None

    def draw(self, frame, mouse=(-1, -1)):
        self._anim = ease_toward(self._anim, 1.0 if self.visible else 0.0,
                                 ANIM_RATE)
        if self._anim < 0.004:
            self.buttons = []
            return
        fh, fw = frame.shape[:2]
        pw = min(self.WIDTH, fw - 2 * self.PAD)
        jog_h = 3 * self.JOG_BTN + 2 * self.JOG_GAP
        ph = (self.PAD * 2 + 64 + jog_h
              + 3 * self.ROW_H + 2 * self.ROW_GAP + 26)
        px = (fw - pw) // 2
        py = max(self.PAD, (fh - ph) // 2)
        self._last_rect = (px, py, pw, ph)
        glass_card(frame, (px, py, px + pw, py + ph), 26, alpha=0.66)

        mx, my = mouse
        self.buttons = []
        close_top = Button("X", px + pw - 52, py + 12,
                           px + pw - 20, py + 44, "simple_close", scale=0.46)
        close_top.draw(frame, hover=close_top.contains(mx, my), shadow=False)
        self.buttons.append(close_top)
        draw_text(frame, f"Simple Gripper - {self.title()}",
                  (px + 22, py + 34), 0.48, C_TEXT, 2)

        if self.running():
            line, colour = f"{self.title()} running - STOP is live.", C_ACCENT
        elif self.handed_off:
            line, colour = f"{self.title()} sent.", C_TEXT_DIM
        else:
            line, colour = ("Adjust the head, then press DONE.", C_TEXT_DIM)
        draw_text(frame, line, (px + 22, py + 56), 0.42, colour, 1)

        bar_y = py + 66
        bar = (px + 22, bar_y, px + pw - 22, bar_y + 5)
        rounded_rect(frame, bar, 3, C_BORDER, -1)

        y = bar_y + 18
        cx = px + pw // 2
        span = self.JOG_BTN + self.JOG_GAP
        for direction, (row, col) in self.JOG_LAYOUT.items():
            bx = cx + (col - 1) * span - self.JOG_BTN // 2
            by = y + row * span
            b = Button(self.JOG_ARROWS[direction], bx, by,
                       bx + self.JOG_BTN, by + self.JOG_BTN, "simple_jog",
                       value=direction, style="ghost", scale=0.6)
            b.draw(frame, hover=b.contains(mx, my),
                   active=self.jog_dir == direction, shadow=False)
            self.buttons.append(b)
        sx = cx - self.JOG_BTN // 2
        sy = y + span
        stop = Button("STOP", sx, sy, sx + self.JOG_BTN, sy + self.JOG_BTN,
                      "simple_stop", style="primary", scale=0.4)
        stop.draw(frame, hover=stop.contains(mx, my), shadow=False)
        self.buttons.append(stop)

        y += jog_h + 12
        draw_text(frame, f'Arrows send their letter + "{SLOW_SUFFIX}" for '
                         f"{SIMPLE_JOG_PULSE_S:g}s, then s.",
                  (px + 22, y), 0.34, C_TEXT_DIM, 1)

        y += 10
        half = (pw - 22 * 2 - 12) // 2
        for label, kind_value, x0, x1 in (
                ("HEIGHT UP  (hu)", "up", px + 22, px + 22 + half),
                ("HEIGHT DOWN  (hd)", "down", px + 34 + half, px + pw - 22)):
            b = Button(label, x0, y, x1, y + self.ROW_H - 6, "simple_height",
                       value=kind_value, style="ghost", scale=0.38)
            b.draw(frame, hover=b.contains(mx, my), shadow=False)
            self.buttons.append(b)

        y += self.ROW_H + self.ROW_GAP
        cancel = Button("CANCEL", px + 22, y, px + 22 + half,
                        y + self.ROW_H - 6, "simple_cancel", style="ghost",
                        scale=0.44)
        done = Button("DONE", px + 34 + half, y, px + pw - 22,
                      y + self.ROW_H - 6, "simple_done", style="accent",
                      scale=0.44)
        cancel.draw(frame, hover=cancel.contains(mx, my), shadow=False)
        done.draw(frame, hover=done.contains(mx, my), shadow=False)
        self.buttons.extend((cancel, done))

        y += self.ROW_H + self.ROW_GAP
        close = Button("CLOSE", px + 22, y, px + pw - 22, y + self.ROW_H - 8,
                       "simple_close", style="ghost", scale=0.4)
        close.draw(frame, hover=close.contains(mx, my), shadow=False)
        self.buttons.append(close)

        if self.last_msg:
            draw_text(frame, ascii_text(self.last_msg)[:64],
                      (px + 22, y + self.ROW_H + 12), 0.34, C_TEXT_DIM, 1)


MANUAL_ACTIONS = {
    "pickup": "Pick this object up.",
    "keep": "Put this object down here.",
    "press": "Press down on this object.",
    "release": "Release the object.",
    "pour": "Pour from this object.",
}

MANUAL_GRIPPER_STEPS = False


class SpeechSpeaker:
    """Fire-and-forget macOS TTS, pre-warmed once and kept alive.

    The old version of this spawned a fresh `say` process per word --
    subprocess.Popen() itself returns in a few ms, but the process it starts
    has to load the speech engine from scratch before any sound comes out,
    which measured at 1-2+ SECONDS every single time. That is the "speaking
    happens very late" the operator saw: the label and the dispatch were
    already instant, the audio just had not started yet.

    One NSSpeechSynthesizer, created once on its own thread and never torn
    down, pays that load cost exactly once -- measured at ~1.4s -- and every
    utterance after that starts audible speech in a few milliseconds. The
    thread starts the moment this module is imported (see _SPEECH below), so
    the warm-up runs in the background during the app's own startup and is
    long finished before an operator ever reaches a real pickup/keep/press.
    """

    START_GRACE = 0.5
    SPEECH_TIMEOUT = 6.0

    def __init__(self):
        self._queue = queue.Queue()
        self._synth = None
        self._lock = threading.Lock()
        self._pending = 0
        self._dead = (sys.platform != "darwin"
                      or NSSpeechSynthesizer is None
                      or __name__ == "__mp_main__")
        if not self._dead:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        try:
            self._synth = NSSpeechSynthesizer.alloc().init()
        except Exception as e:
            print(f"[speak] could not start the speech engine: {e}")
            with self._lock:
                self._dead = True
                self._pending = 0
            return
        while True:
            word = self._queue.get()
            try:
                self._synth.startSpeakingString_(word)
                start_by = time.time() + self.START_GRACE
                while time.time() < start_by and not self._synth.isSpeaking():
                    time.sleep(0.01)
                done_by = time.time() + self.SPEECH_TIMEOUT
                while self._synth.isSpeaking():
                    if time.time() >= done_by:
                        print(f"[speak] {word!r} never finished -- moving on")
                        break
                    time.sleep(0.02)
            except Exception as e:
                print(f"[speak] failed: {e}")
            finally:
                with self._lock:
                    self._pending = max(0, self._pending - 1)

    def say(self, word: str):
        """Queue a word. A no-op off macOS or if the engine never came up."""
        with self._lock:
            if self._dead:
                return
            self._pending += 1
        self._queue.put(word)

    def busy(self) -> bool:
        """True while a word is queued or still coming out of the speaker.

        False whenever speech is unavailable, so a plan on a machine with no
        speech engine runs exactly as it always did rather than waiting on a
        word that is never going to be said.
        """
        with self._lock:
            return not self._dead and self._pending > 0


_SPEECH = SpeechSpeaker()


def speak(word: str):
    """Say the action out loud as it starts, so the operator's other hand
    knows what to do without watching the screen."""
    _SPEECH.say(word)


def speaking() -> bool:
    """True while an action word is still being spoken."""
    return _SPEECH.busy()


SPEECH_MAX_WAIT = 8.0


PLUNGE_COMMANDS = ("pickup", "pour", "press")
PLUNGE_DOWN_TIMEOUT_S = 12.0


class PlungeSequence:
    """Lower the gripper, wait for the board to say it is down, then raise it
    for exactly as long as the descent took.

    The Z axis has no sensor this program can read -- the only thing that
    knows when the gripper has finished descending is the board itself, which
    reports it by sending "s" back up the serial line. So the descent is not
    timed here, it is WATCHED: send HD, wait for that "s", and take however
    long it took as the measure of how far down it went. Raising is then the
    mirror image -- HU for that same duration, then stop -- which puts the
    gripper back where it started without needing to know the height in any
    real units.

    Every phase is driven from the frame loop rather than by sleeping, so the
    window keeps redrawing and the operator can still hit STOP mid-plunge.
    """

    def __init__(self):
        self.phase = "idle"
        self.started_at = 0.0
        self.down_duration = 0.0
        self.up_until = 0.0
        self.status = ""

    @property
    def active(self) -> bool:
        return self.phase != "idle"

    def start(self) -> bool:
        """Begin the descent. False if there is no board to talk to, in which
        case the step just carries on as it did before this existed."""
        if not ARDUINO.connected:
            self.phase = "idle"
            self.status = "No board connected -- skipping the gripper plunge."
            print(f"[plunge] {self.status}")
            return False
        self.phase = "down"
        self.started_at = time.time()
        self.down_duration = 0.0
        self.status = f"Lowering the gripper ({HEIGHT_DOWN_CMD})..."
        ARDUINO.send_command(HEIGHT_DOWN_CMD)
        print(f"[plunge] sent {HEIGHT_DOWN_CMD}, waiting for 's'")
        return True

    def note_rx(self, data: bytes):
        """Raw bytes straight off the serial line.

        Deliberately raw rather than whole lines: the board's reply is a bare
        "s" with no guarantee of a newline after it, and a line-buffered
        reader would sit on it until some later message happened to flush it
        -- by which time the measured descent is wrong. Only consulted while
        actually descending, which keeps an 's' inside some unrelated message
        from being mistaken for the answer.
        """
        if self.phase != "down" or not data:
            return
        if b"s" not in data and b"S" not in data:
            return
        self.down_duration = time.time() - self.started_at
        self.phase = "up"
        self.up_until = time.time() + self.down_duration
        self.status = (f"Raising the gripper ({HEIGHT_UP_CMD}) for "
                       f"{self.down_duration:.2f}s...")
        ARDUINO.send_command("g90")
        ARDUINO.send_command(HEIGHT_UP_CMD)
        print(f"[plunge] got 's' after {self.down_duration:.2f}s - "
              f"sent {HEIGHT_UP_CMD} for the same")

    def tick(self):
        """Called every frame. Ends the lift, or gives up on a silent board."""
        if self.phase == "idle":
            return
        now = time.time()
        if self.phase == "down":
            if now - self.started_at >= PLUNGE_DOWN_TIMEOUT_S:
                ARDUINO.halt()
                self.phase = "idle"
                self.status = ("The board never reported the gripper was "
                               "down -- stopped it and carried on.")
                print(f"[plunge] {self.status}")
            return
        if now >= self.up_until:
            ARDUINO.halt()
            self.phase = "idle"
            self.status = "Gripper back up."
            print(f"[plunge] {self.status}")

    def abort(self):
        """Operator stopped the run mid-plunge. Kill the motion, don't try to
        finish the lift -- STOP means stop."""
        if self.phase != "idle":
            ARDUINO.halt()
            print("[plunge] aborted mid-plunge")
        self.phase = "idle"
        self.status = ""


class PlanRunner:
    """Walks the plan one command at a time.

    A `goto_coordinate` is not executed - it is a DESTINATION. The live
    guidance (update_guidance) tells the operator which way to move the tag,
    and the step only completes when the tag is actually seen on that cell.
    Every other command, and every arrival, is displayed for HOLD_SECONDS
    before the next one starts.
    """

    def __init__(self):
        self.commands = []
        self.index = -1
        self.active = False
        self.mode = "idle"
        self.hold_until = 0.0
        self.label = ""
        self.finished = False
        self.await_speech = False
        self.speech_until = 0.0
        self.on_manual_action = None
        self.manual_wait = None
        self.await_manual = False
        self.await_auto = False
        self.on_auto_action = None
        self.auto_wait = None
        self.auto_press_started_at = 0.0
        self.auto_press_duration = 0.0
        self._auto_stop_until = 0.0
        self.on_step_done = None
        self.step_wait = None
        self.await_step = False
        self._step_offered = False
        if not hasattr(self, "plunge"):
            self.plunge = PlungeSequence()
        else:
            self.plunge.abort()

    def load(self, plan_text: str):
        self.commands = parse_plan_commands(plan_text)
        if not has_plan_actions(self.commands):
            self.commands = []
        self.index = -1
        self.active = False
        self.mode = "idle"
        self.label = ""
        self.finished = False
        self.await_speech = False
        self.speech_until = 0.0
        self._clear_manual()
        if not hasattr(self, "plunge"):
            self.plunge = PlungeSequence()
        else:
            self.plunge.abort()
        return len(self.commands)

    def start(self, state):
        if not self.commands:
            return False
        self.active = True
        self.index = -1
        self.finished = False
        self.await_speech = False
        self.speech_until = 0.0
        self._clear_manual()
        if not hasattr(self, "plunge"):
            self.plunge = PlungeSequence()
        else:
            self.plunge.abort()
        self._advance(state)
        return True

    def _clear_manual(self):
        """Drop any pending manual step. A stale instruction left on the
        card would otherwise sit there after a stop, and the next run would
        start already 'waiting' on a step nobody is doing."""
        self.await_manual = False
        self.await_auto = False
        self.await_step = False
        panel_clear = getattr(self, "on_manual_clear", None)
        if panel_clear is not None:
            panel_clear()

    def stop(self, state, why="Plan stopped."):
        self.active = False
        self.mode = "idle"
        self.await_speech = False
        self._clear_manual()
        self.plunge.abort()
        self.label = ""
        state.action_label = None
        state.target_col = state.target_row = None
        state.manual_move_active = False
        state.arrived = False
        state.status_message = why
        ARDUINO.send_direction(None)

    def current_command(self):
        if 0 <= self.index < len(self.commands):
            return self.commands[self.index]
        return ""

    def _advance(self, state):
        self.index += 1
        if self.index >= len(self.commands):
            self.active = False
            self.mode = "idle"
            self.label = ""
            self.finished = True
            state.action_label = None
            state.target_col = state.target_row = None
            state.status_message = "Plan finished."
            print("[plan] finished")
            ARDUINO.send_direction(None)
            return
        self._dispatch(state, self.commands[self.index])

    def _dispatch(self, state, cmd: str):
        step = f"{self.index + 1}/{len(self.commands)}"
        self._step_offered = False
        m = GOTO_RE.match(cmd)
        if m:
            coord = parse_coordinate(f"{m.group(1)}{m.group(2)}")
            if coord is None:
                print(f"[plan] {step}: {cmd!r} is off this grid - skipped")
                state.status_message = f"Step {step}: {cmd} is off the grid."
                self.mode = "hold"
                self.hold_until = time.time() + HOLD_SECONDS
                self.label = "OFF GRID"
                state.action_label = (self.label, C_AMBER)
                return
            state.target_col, state.target_row = coord
            state.arrived = False
            state.action_label = None
            self.mode = "move"
            self.label = f"GO TO {coordinate_name(*coord)}"
            print(f"[plan] {step}: move to {coordinate_name(*coord)}")
            return

        self.mode = "hold"
        self.hold_until = time.time() + HOLD_SECONDS
        self.label = action_label(cmd)
        state.action_label = (self.label, C_ACCENT)
        state.status_message = f"Step {step}: {self.label}"
        print(f"[plan] {step}: {self.label}")
        bare = cmd.split("(", 1)[0].strip().lower()
        manual = (MANUAL_GRIPPER_STEPS and bare in MANUAL_ACTIONS
                 and self.on_manual_action is not None)
        panel_auto = (not manual and bare in ("pickup", "keep", "press", "release")
                      and self.on_auto_action is not None)
        if bare in PLUNGE_COMMANDS and not manual and not panel_auto:
            self.plunge.start()
        if panel_auto:
            self.on_auto_action(bare)
            self.await_auto = True
        elif not manual and bare in ("keep", "press", "release"):
            if bare == "keep":
                ARDUINO.send_command("g0")
            elif bare == "press":
                ARDUINO.send_command("hx")
                self.auto_press_started_at = time.monotonic()
                self.auto_press_duration = AUTO_PICKUP_HX_S
                self._auto_stop_until = time.monotonic() + AUTO_PICKUP_HX_S
            else:
                ARDUINO.send_command("hu")
                self._auto_stop_until = time.monotonic() + AUTO_RELEASE_DURATION_S
        self.await_manual = False
        if manual:
            self.on_manual_action(bare)
            self.await_manual = True
        self.await_speech = False
        if bare in SPEAK_WORDS:
            speak(SPEAK_WORDS[bare])
            self.await_speech = True
            self.speech_until = time.time() + SPEECH_MAX_WAIT

    def tick(self, state):
        """Called every frame. Drives the move -> next loop.

        An arrival is not held for its own sake: the moment the tag is
        actually seen on the target cell, the next step -- almost always
        pickup/keep/press/pour/etc -- dispatches immediately, which is also
        what fires its `speak()` and puts its label on the banner. Nothing
        here waits before that happens, and HOLD_SECONDS after it (in
        _dispatch) guarantees the step is fully sent and shown before the
        runner ever moves on to leave that cell.
        """
        if not self.active:
            return
        self.plunge.tick()
        now = time.time()
        if self._auto_stop_until and time.monotonic() >= self._auto_stop_until:
            ARDUINO.halt()
            self._auto_stop_until = 0.0
        if self.mode == "move":
            if state.arrived:
                cell = coordinate_name(state.target_col, state.target_row)
                print(f"[plan] arrived at {cell}")
                self._advance(state)
        elif self.mode == "hold" and now >= self.hold_until:
            if self.await_speech and now < self.speech_until and speaking():
                return
            if self.await_speech and now >= self.speech_until:
                print("[speak] gave up waiting -- continuing the plan")
            self.await_speech = False
            if self.plunge.active:
                state.status_message = self.plunge.status
                return
            if self.await_manual:
                if self.manual_wait is None or not self.manual_wait():
                    self.await_manual = False
                else:
                    state.status_message = (
                        f"{self.label}: do it by hand, then press DONE "
                        "on the Gripper card.")
                    return
            if self.await_auto:
                if self.auto_wait is not None and self.auto_wait():
                    state.status_message = f"{self.label}: automatic gripper action in progress."
                    return
                self.await_auto = False
            if self.on_step_done is not None and not self._step_offered:
                # The step is finished and shown. The per-step checker may
                # hold the plan here until its verdict is in.
                self._step_offered = True
                self.await_step = bool(
                    self.on_step_done(self.index, self.commands[self.index]))
            if self.await_step:
                wait = self.step_wait() if self.step_wait is not None else None
                if wait:
                    state.status_message = (
                        wait if isinstance(wait, str) else
                        f"{self.label}: checking the step before going on...")
                    return
                self.await_step = False
            self._advance(state)


SIM_SPEEDS = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]
SIM_SPEED = 5.0
WAIT_MAX_PLAYBACK = 5.0
WAIT_CAPS = [2.0, 5.0, 10.0, 15.0, 30.0, 60.0]

REFRESH_RATES = [30, 45, 60, 90, 120, 0]
REFRESH_RATE = 60
IDLE_REDRAW_S = 1.0 / 30.0
EVENT_WAIT_SLICE_S = 0.004

CMD_STATES = {
    "goto":        (_bgr("#60a5fa"), "Moving..."),
    "contact":     (_bgr("#fb923c"), "Working surface..."),
    "pickup":      (_bgr("#22c55e"), "Picking up..."),
    "keep":        (_bgr("#facc15"), "Placing..."),
    "pour":        (_bgr("#22d3ee"), "Pouring..."),
    "slice":       (_bgr("#f43f5e"), "Slicing..."),
    "press":       (_bgr("#f97316"), "Pressing..."),
    "release":     (_bgr("#a78bfa"), "Releasing..."),
    "open_door":   (_bgr("#38bdf8"), "Opening door..."),
    "door_opened": (_bgr("#38bdf8"), "Door open"),
    "close_door":  (_bgr("#38bdf8"), "Closing door..."),
    "door_closed": (_bgr("#38bdf8"), "Door closed"),
    "wait":        (_bgr("#6b7280"), "Waiting..."),
    "complete":    (_bgr("#ffd700"), "Task Complete!"),
}


class SimRunner:
    """Plays the plan back as a dot. S1-SRC's timings, to the millisecond.

    One command becomes one or more "beats" -- a label, a colour, a delay,
    and optionally a cell to move to. Queuing beats rather than chaining
    timers is what lets a two-phase command (a door opens, then it is shown
    open) and the three-stage unstacker opening share one code path with a
    plain `pickup`, on a frame loop that has no timers to chain.
    """

    DELAY = {"goto": 1300, "pickup": 950, "keep": 950, "pour": 1300,
             "slice": 1100, "press": 800, "release": 800, "default": 700}
    CELL_STEP = 420
    COMPLETE_HOLD = 2500
    TRAIL = 26

    def __init__(self):
        self.commands = []
        self.index = -1
        self.active = False
        self.label = ""
        self.colour = C_ACCENT
        self.popup = ""
        self.cell = ""
        self.col = self.row = 0.0
        self.target_col = self.target_row = 0
        self.trail = []
        self.pulse = 0.0
        self._pressed = False
        self._beats = []
        self._next_at = 0.0
        self._finish_pending = False
        self._moving = False


    def load(self, commands):
        """Take the runner's own command list -- the same list object, so the
        plan checklist can tell whose step is live by identity."""
        self.commands = commands if has_plan_actions(commands) else []
        self.index = -1
        self.active = False
        self._beats = []
        self._finish_pending = False
        return len(self.commands)

    def start(self, state):
        if not self.commands:
            return False
        self.active = True
        self.index = -1
        self._pressed = False
        self._finish_pending = False
        self.trail = []
        self.col = self.row = 0.0
        self.target_col = self.target_row = 0
        self.cell = coordinate_name(0, 0)
        self.label = ""
        self.popup = ""
        self._moving = False
        self._beats = [
            self._beat("", C_ACCENT, 1000, popup="Invoking Alpha 2D unstacker"),
            self._beat("", C_ACCENT, 1000, popup="Alpha 2D stacker is unstacking"),
            self._beat("", C_ACCENT, 1000, popup="Unstacking is done..."),
        ]
        self._next_at = time.time()
        state.status_message = "Simulating the plan..."
        print(f"[sim] rehearsing {len(self.commands)} step(s)")
        return True

    def stop(self, state, why="Simulation stopped."):
        self.active = False
        self._beats = []
        self.label = ""
        self.popup = ""
        state.status_message = why

    def take_finish(self):
        """True exactly once, on the frame after the rehearsal ran to the end.

        A rehearsal that was stopped by hand never sets this: the operator
        already knows they stopped it, and it is their call what happens
        next.
        """
        if not self._finish_pending:
            return False
        self._finish_pending = False
        return True


    @staticmethod
    def _beat(label, colour, delay_ms, move=None, pressed=None, popup=""):
        return {"label": label, "colour": colour, "delay": delay_ms,
                "move": move, "pressed": pressed, "popup": popup}

    @staticmethod
    def _scaled(ms):
        """Playback speed applies live -- change it mid-rehearsal and the
        very next beat is already running at the new pace."""
        return max(40.0, ms / max(0.25, SIM_SPEED)) / 1000.0

    def tick(self, state):
        if not self.active:
            return
        self._ease()
        now = time.time()
        if now < self._next_at:
            return
        if self._moving and not self._arrived():
            return
        if self._beats:
            self._begin(self._beats.pop(0))
            return
        self._advance(state)

    def _begin(self, beat):
        if beat["popup"]:
            self.popup = beat["popup"]
        else:
            self.popup = ""
            self.label = beat["label"]
        self.colour = beat["colour"]
        if beat["pressed"] is not None:
            self._pressed = beat["pressed"]
        self._moving = beat["move"] is not None
        if beat["move"] is not None:
            self.target_col, self.target_row = beat["move"]
            self.cell = coordinate_name(*beat["move"])
        self._next_at = time.time() + self._scaled(beat["delay"])

    def _advance(self, state):
        self.index += 1
        if self.index >= len(self.commands):
            self.active = False
            self.label = ""
            self.popup = ""
            self._finish_pending = True
            print("[sim] finished")
            return
        cmd = self.commands[self.index]
        print(f"[sim] {self.index + 1}/{len(self.commands)}: {cmd}")
        self._beats = self._dispatch(cmd)
        self._begin(self._beats.pop(0))

    def _dispatch(self, cmd: str):
        """One plan line -> the beats that play it. S1-SRC's _dispatch."""
        m = GOTO_RE.match(cmd)
        if m:
            coord = parse_coordinate(f"{m.group(1)}{m.group(2)}")
            if coord is None:
                return [self._beat("Off this grid - skipped", C_AMBER,
                                   self.DELAY["default"])]
            key = "contact" if self._pressed else "goto"
            colour, label = CMD_STATES[key]
            delay = self.CELL_STEP if self._pressed else self.DELAY["goto"]
            return [self._beat(label, colour, delay, move=coord)]

        bare = cmd.split("(", 1)[0].strip().lower()

        if bare in ("pickup", "keep", "pour"):
            colour, label = CMD_STATES[bare]
            if bare == "pour" and "(" in cmd:
                frac = re.search(r"([\d.]+)", cmd.split("(", 1)[1])
                if frac:
                    f = max(0.0, min(1.0, float(frac.group(1))))
                    if f < 1.0:
                        label = f"Pouring {f * 100:g}%..."
            return [self._beat(label, colour, self.DELAY[bare])]

        if bare in ("press", "release"):
            colour, label = CMD_STATES[bare]
            return [self._beat(label, colour, self.DELAY[bare],
                               pressed=(bare == "press"))]

        if bare in ("open_door", "open_doors", "close_door", "close_doors"):
            closing = bare.startswith("close")
            c1, l1 = CMD_STATES["close_door" if closing else "open_door"]
            c2, l2 = CMD_STATES["door_closed" if closing else "door_opened"]
            return [self._beat(l1, c1, self.DELAY["press"], pressed=True),
                    self._beat(l2, c2, self.DELAY["release"], pressed=False)]

        if bare.startswith("slice"):
            colour, label = CMD_STATES["slice"]
            return [self._beat(label, colour, self.DELAY["slice"])]

        if bare.startswith("wait"):
            secs = 2.0
            found = re.search(r"(\d+(?:\.\d+)?)", cmd)
            if found:
                secs = max(0.0, float(found.group(1)))
            play = min(secs, WAIT_MAX_PLAYBACK)
            colour, _ = CMD_STATES["wait"]
            label = (f"Waiting {secs:g}s..." if play >= secs
                     else f"Waiting {secs:g}s (simulated as {play:g}s)...")
            return [self._beat(label, colour, int(play * 1000))]

        if bare == "task_completed":
            colour, label = CMD_STATES["complete"]
            return [self._beat(label, colour, self.COMPLETE_HOLD)]

        return [self._beat(action_label(cmd), C_TEXT_DIM, self.DELAY["default"])]

    def _ease(self):
        """One frame of the dot gliding toward the cell it was sent to."""
        rate = min(0.9, 0.10 * max(0.25, SIM_SPEED))
        dc = self.target_col - self.col
        dr = self.target_row - self.row
        if abs(dc) > 0.005 or abs(dr) > 0.005:
            self.col += dc * rate
            self.row += dr * rate
            self.trail.append((self.col, self.row))
            if len(self.trail) > self.TRAIL:
                self.trail.pop(0)
        else:
            self.col, self.row = float(self.target_col), float(self.target_row)
            if self.trail:
                self.trail.pop(0)
        self.pulse = (self.pulse + 0.09) % (2 * math.pi)

    def _arrived(self):
        return (abs(self.target_col - self.col) <= 0.005
                and abs(self.target_row - self.row) <= 0.005)


class AIJob:
    """Vision AI's view of the board, then planning, on a worker thread.

    Nothing here touches the frame loop: the thread only writes to its own
    fields, and the loop reads them. A failure at any stage lands in
    `error` and leaves the board exactly as it was.
    """

    def __init__(self, frame_bgr, task: str, history: str = "", vision=None,
                 board_source=None, resume: str = ""):
        self.frame = frame_bgr
        self._board_source = board_source
        # replan_note() when this job carries a task on from a failed step:
        # the planner then writes only what is left of it.
        self.resume = resume or ""
        self.vision = vision
        self.grid = None
        self.task = task
        self.history = history
        self._lock = threading.Lock()
        self.stage = "Reading the board..."
        self.objects = []
        self.plan = ""
        self.error = ""
        self.done = False
        self.vision_ready = False
        self.vision_final = False
        self.vision_shown = False

        self.questions = []
        self.answers = None
        self.cancelled = False
        self.blocked = False
        self.rejected = ""
        self.memory_rule = ""
        self.grips_applied = []
        self.already_done = ""
        self.out_of_reach = []
        self._answered = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _set_stage(self, stage: str):
        with self._lock:
            self.stage = stage

    def snapshot(self):
        """(stage, done) read together, so the loop never sees a stage that
        hasn't caught up with a done flag flipped a moment before it (or
        vice versa) -- the two are written separately on the worker thread."""
        with self._lock:
            return self.stage, self.done

    def take_questions(self):
        """The clarity questions, once, for the UI to put to the operator."""
        with self._lock:
            qs, self.questions = self.questions, []
            return qs

    def answer(self, qa):
        """[(question, answer)] from the UI -- lets the worker carry on."""
        self.answers = list(qa)
        self._answered.set()

    def cancel(self):
        """Abandon a job parked on a question, so its thread can exit."""
        self.cancelled = True
        self._answered.set()

    def _publish_vision(self, objects, final=False):
        """Hand the object list to the loop while planning is still running,
        so the list can be read in the transcript before the plan lands."""
        with self._lock:
            self.objects = list(objects)
            self.vision_ready = True
            if final:
                self.vision_final = True

    def peek_objects(self):
        """The outlines as they stand, for drawing. Empty until vision runs."""
        with self._lock:
            return list(self.objects)

    def take_vision(self):
        """The finished object list, once, for the transcript."""
        with self._lock:
            if not self.vision_final or self.vision_shown:
                return None
            self.vision_shown = True
            return list(self.objects)

    def _finish(self):
        with self._lock:
            self.done = True

    def _read_board(self):
        """Vision AI's snapshot of the board as the planner's object list.

        The outlines are already there -- FastSAM has been tracing them the
        whole time -- so the only wait is naming whatever has no name yet:
        one call, and none at all when the board has not changed since the
        last task.
        """
        if self.vision is None:
            raise ModelError("Vision AI is not running.")
        snap = self.vision.snapshot(on_wait=lambda: self._set_stage(
            "Vision AI - waiting for FastSAM's first outlines..."))
        fh, fw = snap["frame"].shape[:2]
        self.grid = Grid(fw, fh, list(snap["box"]), square_cells=False)
        save_vision_frame(snap["frame"], self.grid)
        if not snap["objects"]:
            raise ModelError("Vision AI found no objects on the board.")
        namer = self.vision.namer
        unnamed = namer.unanswered(snap["ids"])
        if unnamed:
            tier = " priority" if PRIORITY_NAMING else ""
            self._set_stage(f"Vision AI - naming {len(unnamed)} object(s) "
                            f"({NAMER_MODEL}{tier})...")
            t0 = time.time()
            problem = namer.name_now(snap["frame"], snap["objects"],
                                     snap["ids"],
                                     snap.get("region") or snap["box"])
            print(f"[timing] naming for the task took {time.time() - t0:.1f} s")
            if problem:
                if not any(tid in namer.names for tid in snap["ids"]):
                    raise ModelError(problem)
                print(f"[vision] {problem} - planning with the names there are")
        objects = planner_objects(snap, namer, self.grid)
        if not objects:
            raise ModelError("Vision AI found no objects on the board to "
                             "work with (only the robot itself).")
        print("\n=== OBJECT LIST (Vision AI) ===")
        print(object_list_text(objects))
        return objects

    def _render_before_photo(self):
        """The board as the task found it, for Error Rebounds' CHECK."""
        if self.frame is not None or not self._board_source:
            return
        source, grid_now = self._board_source
        try:
            board = render_vision_board(source, grid_now)
        except Exception as e:
            print(f"[vision] before photo failed ({e}) - using the raw frame")
            board = None
        self.frame = board if board is not None else source.copy()

    def _run(self):
        started = time.time()
        try:
            self._render_before_photo()
            client = make_client()

            verdict_box = ["non-dexterous"]
            task = self.task

            def run_dexterity():
                if not DEXTERITY_CHECK:
                    print("[dexterity] check is off - planning anyway")
                    return
                if self.resume:
                    print("[dexterity] re-planning a task that already passed")
                    return
                try:
                    verdict_box[0] = check_dexterity(client, task)
                except Exception as e:
                    print(f"[dexterity] failed ({e}) - planning anyway")

            pre = [threading.Thread(target=run_dexterity, daemon=True)]
            for t in pre:
                t.start()

            objects = self._read_board()
            resolve_overlaps(objects)
            objects = restrict_to_reachable(objects, self.out_of_reach)
            disambiguate_names(objects)

            effective_task = (self.task if is_fold_task(self.task)
                              or not is_fold_task(self.history)
                              else f"{self.task} (fold, per: {self.history})")
            objects = add_cloth_corners(objects)
            self._publish_vision(objects, final=True)
            gap_note = fold_landmark_error(objects, self.task)
            if gap_note:
                print(f"[fold] {gap_note}")

            objects_text = object_list_text(self.objects)
            task = self.task

            if any(t.is_alive() for t in pre):
                self._set_stage(f"Checking the gripper can do this "
                                f"({DEXTERITY_MODEL}) and what to remember "
                                f"({MEMORY_MODEL})...")
            for t in pre:
                t.join(timeout=API_TIMEOUT_S + 10)

            if verdict_box[0] == "dexterous":
                self.rejected = (
                    "The gripper cannot do this one -- it needs threading, "
                    "twisting a lid, peeling one item off a stack, or "
                    "fingers. If that is not what you meant, say it as a "
                    "plain move (\"put the tape on E8\"), or turn the "
                    "dexterity check off in Settings.")
                print(f"[dexterity] refused as dexterous: {task!r}")
                return

            self._set_stage(f"Re-planning the rest of the task "
                            f"({PLANNER_MODEL})..." if self.resume else
                            f"Planning the task ({PLANNER_MODEL})...")
            history_note = (f"CONVERSATION SO FAR:\n{self.history}\n\n"
                            if self.history else "")
            recipes = ""
            if is_fold_task(self.task) or is_fold_task(self.history):
                try:
                    recipes = fold_recipe_text(self.objects, self.grid)
                except Exception as e:
                    print(f"[fold] recipe failed ({e}) - planner works from parts")
            reach_note = ""
            if self.out_of_reach:
                reach_note = (
                    "OUT OF REACH (on the board and seen, but the gripper "
                    "cannot reach any part of them - never write MISSING for "
                    "these; say in a # comment that they are out of reach "
                    "and plan the rest of the task): "
                    + ", ".join(f"{d['name']} at {d['center']}"
                                for d in self.out_of_reach) + "\n\n")
            user = (f"{history_note}"
                    f"OBJECT LIST:\n{objects_text}\n\n"
                    + reach_note
                    + (f"{recipes}\n\n" if recipes else "")
                    + f"Task: {task}"
                    + (f"\n\n{self.resume}" if self.resume else ""))
            print("\n=== PLANNER INPUT ===")
            print(user)

            system = build_planner_system()
            self.plan = call_model(
                client, model=PLANNER_MODEL, max_tokens=6000, stage="Planner",
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            print("\n=== PLAN ===")
            print(self.plan)
            if (not has_plan_actions(parse_plan_commands(self.plan))
                    and not plan_already_done(self.plan)):
                note = no_action_retry_note(self.plan)
                print(f"[planner] no actions - retrying once ({note[:80]}...)")
                self._set_stage(f"Planning again ({PLANNER_MODEL})...")
                retry = call_model(
                    client, model=PLANNER_MODEL, max_tokens=6000,
                    stage="Planner (retry)",
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user},
                              {"role": "assistant", "content": self.plan},
                              {"role": "user", "content": note}])
                print("\n=== PLAN (retry) ===")
                print(retry)
                if (has_plan_actions(parse_plan_commands(retry))
                        or plan_already_done(retry)):
                    self.plan = retry
                elif missing_objects(retry) and not missing_objects(self.plan):
                    self.plan = retry
            if plan_already_done(self.plan):
                self.already_done = plan_already_done(self.plan)
                return
            if not has_plan_actions(parse_plan_commands(self.plan)):
                reason = extract_plan_summary(self.plan)
                missing = missing_objects(self.plan)
                far = [d["name"] for d in self.out_of_reach
                       if any(_same_object_word(m, d) for m in missing)]
                missing = [m for m in missing if not any(
                    _same_object_word(m, d) for d in self.out_of_reach)]
                if far and not missing:
                    raise ModelError(
                        "Not able to complete this task -- "
                        + ", ".join(far) + " is on the board but out of the "
                        "gripper's reach.")
                if missing:
                    raise ModelError(
                        "Not able to complete this task -- "
                        + ", ".join(missing) + " not found on the board."
                        + red_zone_hint())
                raise ModelError((reason + " " if reason else "")
                                 + "No physical actions were planned; "
                                 "the task has not been completed.")

            if GRIPPER_AI:
                self.plan, self.grips_applied = enforce_gripper_targets(
                    self.plan, self.objects, effective_task)
                if self.grips_applied:
                    print("[gripper] applied:\n" + "\n".join(
                        f"  {ln}" for ln in gripper_target_lines(self.grips_applied)))
        except Exception as e:
            self.error = str(e)
        finally:
            print(f"[timing] task finished in {time.time() - started:.1f} s"
                  f"{' (failed)' if self.error else ''}", flush=True)
            self._finish()


ERR3_PROMPT = """
You are the Error Rebound AI, the verification step for a robot task.

INPUTS
- Task description
- Initial image: the board at planning time (same grid on all images)
- Final image: the board after execution
- Optional: execution-start image (fresh scene captured just before execution)
- Optional: object list from the original detection (treat as fallible)
- Optional: extra-viewpoint images of the final scene
- Optional: execution events (grasp result, drops, collisions, gripper
  release, contact or charging sensor readings)

GOAL
Decide whether the task goal was achieved AND no constraints were violated,
using only visible or logged evidence. Do not infer hidden success from
position alone. Base the answer only on the task and the provided inputs.
Do not include chain-of-thought.

OUTPUT FORMAT
Return exactly these lines, with no other text, markdown, or punctuation
changes. Choose exactly ONE verdict value:

VERDICT: Done_correctly
OBJECTS: <name>=ok; <name>=ok
REASON: <short factual explanation>

VERDICT: Done_wrong,_redo
OBJECTS: <name>=ok|wrong|unverified; ...
REASON: <short factual explanation>
NEXT: FIX: <correction for ONLY the wrong objects, based on the current scene
      in the final image; do not touch objects marked ok>
      [add "RETAKE: <what is needed>" on the same line if any object is
      unverified]

VERDICT: Cannot_verify
OBJECTS: <name>=ok|unverified; ...
REASON: <short factual explanation>
NEXT: RETAKE: <view, angle, gripper clearance, or sensor evidence needed>

OBJECTS has one entry per named object or subtask. For single-object tasks,
list that one object.

RULES

1. SUCCESS CONDITIONS
Derive explicit conditions from the task: correct object, correct destination
or container, object released by the gripper, desired final state. Verify each
individually. Require a visible change between images only if the goal needs
one. If the goal was already satisfied at the start and remains satisfied
with no constraint violated, output Done_correctly.

2. UNREADABLE IMAGE
If the final image is blurred, obstructed, or taken from an angle where grid
coordinates or object positions cannot be reliably read, output Cannot_verify
with a RETAKE request. Never output Done_wrong,_redo merely because the image
is unreadable. Minor camera shifts that do not affect readability are ignored.

3. OCCLUSION
If an object is hidden inside a container, under another object, or behind the
gripper and cannot be individually confirmed, mark it unverified. Use logged
placement evidence if provided. Otherwise request RETAKE (move the gripper
clear or use another view). Do not guess.

4. HIDDEN OUTCOMES
When the goal itself depends on a state not visible from position (charging,
a clean surface, firm seating), require task-appropriate evidence: an
indicator, contact/force reading, or close inspection. If none is available,
mark the object unverified and name the evidence needed. Do not demand extra
evidence when the goal is simply an object's position.

5. PER-OBJECT REPORTING
Judge each named object independently. Never recommend redoing objects marked
ok.

6. OVERLAPPING OBJECTS
If objects share a coordinate, verify each by name against its own target.
The presence of some object at a coordinate does not satisfy the requirement.

7. OBJECT LIST IS FALLIBLE
The object list is evidence, not truth. Compare it with the initial image. If
they disagree, decide by what is visible; if that cannot be resolved, mark the
affected objects unverified. Track each object's identity from initial to
final image.

8. STALE START STATE
Applies only if an execution-start image is provided. If it differs materially
from the initial image (object moved, added, or missing beyond the task), say
so in REASON and output Cannot_verify with NEXT: RETAKE: regenerate the plan
from the current scene.

9. EQUIPMENT AND CONTAINERS
The arm, gripper, and AprilTag are equipment, not task objects. But an object
still held or not released is a failure, and a gripper covering the result
makes it unverified (rule 3). Containers are NOT ignorable when the task names
one: confirm the object is in the correct container. Differences in lighting,
shadows, and background are ignorable.

10. NATURAL STATE CHANGES
Cooking, melting, blending, or crushing that the task implies are expected and
are not errors.

11. CONSTRAINTS PRESERVED
A correct final appearance is not enough. Using events (if provided) and the
images, confirm that no object was dropped, no collision occurred, and no
unrelated object was displaced or damaged. A violated constraint means
Done_wrong,_redo even if the arrangement looks right. If events are not
provided, judge from the images alone.

12. VERDICT PRECEDENCE
- Any condition clearly unmet or any constraint violated -> Done_wrong,_redo
  (even if other objects are unverified; list those with RETAKE in NEXT).
- Otherwise, any condition not confirmable -> Cannot_verify.
- Otherwise, every condition verified with evidence and no constraint
  violated -> Done_correctly.
Prefer Cannot_verify over guessing in either direction.
""".strip()

# The one checker, by the name the operator knows it by (ERR-2, the old
# two-line verdict, is gone).
ERR_NAME = "ERR-3"
# Automatic checking, off until switched on in Settings:
#   "step" - after each finished plan step except moves (goto) and waits
#   "task" - once, when the whole plan has finished
ERR_AUTO_MODES = (("off", "Off"), ("step", "Every step"),
                  ("task", "After the task"))
ERR_AUTO = "off"
ERR_STEP_SKIP = ("goto", "wait", "task_completed", "complete")
# A step that fails its check pops up CONTINUE ANYWAY / REPLAN; the default
# one happens on its own after STEP_FAIL_WAIT_S. Replanning is automatic at
# most REPLAN_AUTO_LIMIT times per task -- after that the popup waits for a
# click, so a step the camera keeps failing cannot loop on paid calls.
STEP_FAIL_WAIT_S = 3.0
REPLAN_AUTO_LIMIT = 2


def _bare_step(cmd: str) -> str:
    """"goto_coordinate = M, 7" -> "goto_coordinate", "wait_X(5)" ->
    "wait_x", "pour(0.5)" -> "pour"."""
    return re.split(r"[(:=\s]", cmd.strip(), maxsplit=1)[0].lower()


def step_is_checked(cmd: str) -> bool:
    """True for every step that does something to an object -- pickup, keep,
    press, release, pour, slice, door steps... -- and False for a
    goto_coordinate (only a move), a wait_X and Task_Completed."""
    if GOTO_RE.match(cmd.strip()):
        return False
    return not _bare_step(cmd).startswith(ERR_STEP_SKIP)


def _cell_before(cmds, index):
    """The cell the plan last sent the robot to before step `index`."""
    for k in range(min(index, len(cmds)) - 1, -1, -1):
        m = GOTO_RE.match(cmds[k].strip())
        if m:
            return f"{m.group(1).upper()}{int(m.group(2))}"
    return None


def step_expectation(cmds, index) -> str:
    """What step `index` should have done to the board, in words, so its
    check knows what to look for."""
    cmd = cmds[index]
    bare = _bare_step(cmd)
    cell = _cell_before(cmds, index)
    at = f" at {cell}" if cell else ""
    if bare == "pickup":
        return (f"the gripper should now hold the object that was{at}; "
                "nothing else on the board should have moved")
    if bare == "keep":
        k = next((j for j in range(index - 1, -1, -1)
                  if _bare_step(cmds[j]) == "pickup"), None)
        src = _cell_before(cmds, k) if k is not None else None
        return (f"the object picked up{' at ' + src if src else ''} should "
                f"now rest{at}, let go by the gripper")
    if bare == "press":
        return f"the gripper should be pressing down{at}"
    if bare == "release":
        return f"the gripper should have stopped pressing{at}"
    if bare.startswith("open_door"):
        return f"the door{at} should now be open"
    if bare.startswith("close_door"):
        return f"the door{at} should now be closed"
    if bare == "pour":
        return f"the held object should have been tipped to pour{at}"
    if bare == "slice":
        return f"the object{at} should have been cut"
    return f"{cmd}{at} should be done"


def gripper_after(cmds, index) -> str:
    """What the gripper holds after step `index` if every step went to
    plan -- the planner must not pick up twice or forget a held object."""
    held = pressing = None
    for k in range(min(index + 1, len(cmds))):
        bare = _bare_step(cmds[k])
        if bare == "pickup":
            held = _cell_before(cmds, k) or "its cell"
        elif bare == "keep":
            held = None
        elif bare == "press":
            pressing = _cell_before(cmds, k) or "its cell"
        elif bare == "release":
            pressing = None
    text = (f"holding the object it picked up at {held}" if held
            else "holding nothing")
    return text + (f" and still pressing at {pressing}" if pressing else "")


def replan_note(cmds, plan_text, index, word, reason, fix,
                results=None) -> str:
    """The planner's brief for carrying a task on from a failed step: its
    own earlier answer, which steps ran, what the check found, and the
    order to plan only what is left -- never the whole task again."""
    results = results or {}
    n, i = len(cmds), index + 1
    rows = []
    for k, c in enumerate(cmds):
        if k < index:
            tag = {"wrong": "done - its check failed, the operator carried on",
                   "unverified": "done - its check could not confirm it"
                   }.get(results.get(k), "done")
        elif k == index:
            tag = f"done - CHECK: {word}"
        else:
            tag = "not run yet"
        rows.append(f"  {k + 1}. {c}   [{tag}]")
    rest = (f"- Then carry on with the remaining steps of your earlier plan "
            f"({i + 1} to {n}), unchanged unless the board as it is now "
            f"needs a different cell or order.\n" if i < n else "")
    done = (f"- Never repeat steps 1 to {index} - they are done.\n"
            if index > 0 else "")
    return (
        "REPLAN FROM A FAILED STEP - carry this task on; do NOT plan it from "
        "the start again.\n"
        f"You already planned this task and the robot was running your plan. "
        f"The camera check after step {i} of {n} ({cmds[index]}) says: "
        f"{word}. {reason or 'No reason given.'}\n"
        f"The checker's correction: {fix or 'none given - decide from the board'}"
        f"\n\nYOUR EARLIER ANSWER:\n{(plan_text or '').strip() or '(not kept)'}"
        "\n\nPROGRESS (numbered in the order the robot runs them):\n"
        + "\n".join(rows) +
        f"\n\nThe OBJECT LIST above is the board as it is NOW, after step {i}. "
        f"Had every step gone to plan, the gripper would now be "
        f"{gripper_after(cmds, index)} - trust the check and the OBJECT LIST "
        "over that for where things really are.\n\n"
        f"Plan ONLY what is left of the task, from step {i} onward:\n"
        f"- First put step {i} right, from the board as it is now, using the "
        "checker's correction.\n"
        + rest + done +
        f"- If step {i} is in fact fine on the board, start straight from "
        f"step {i + 1}.\n"
        "Answer in the usual format: the # summary line, the numbered "
        "commands, Task_Completed.")


def step_events(runner, index: int) -> str:
    """ERR-3's EXECUTION EVENTS for one finished step: what the app knows,
    and nothing it does not."""
    cmds = list(getattr(runner, "commands", None) or [])
    n = len(cmds)
    if not 0 <= index < n:
        return ""
    steps = "\n".join(f"  {k + 1}. {c}" for k, c in enumerate(cmds))
    return (f"Step-by-step check. Steps 1 to {index + 1} of {n} have been "
            f"carried out; step {index + 1} ({cmds[index]}) has just finished "
            f"and is the one being checked. Steps {index + 2} onward have not "
            f"run yet.\nPlan steps:\n{steps}\n"
            "No grasp, drop, collision, contact or force readings are logged "
            "by this robot: a pickup/keep step only means the command was "
            "sent, not that the object was held or released.")


def execution_events(runner) -> str:
    """What the app itself logged about the last physical run, for ERR-3's
    EXECUTION EVENTS input. Only what is actually known: which plan steps
    were carried out, and that no grasp/contact/force readings exist -- so
    the checker cannot mistake a dispatched "pickup" for a confirmed grasp."""
    cmds = list(getattr(runner, "commands", None) or [])
    if not cmds:
        return ""
    n = len(cmds)
    if getattr(runner, "finished", False):
        ran = f"All {n} plan steps were carried out."
    elif 0 <= getattr(runner, "index", -1) < n:
        i = runner.index
        ran = (f"Execution was stopped at step {i + 1} of {n} "
               f"({cmds[i]}); the steps after it never ran.")
    else:
        ran = "The plan was not executed."
    steps = "\n".join(f"  {k + 1}. {c}" for k, c in enumerate(cmds))
    return (f"{ran}\nPlan steps:\n{steps}\n"
            "No grasp, drop, collision, contact or force readings are logged "
            "by this robot: a pickup/keep step only means the command was "
            "sent, not that the object was held or released.")


def append_err_history(record: dict):
    """Append one verdict to the history embedded inside S1.py."""
    entries = S1_EMBEDDED_STATE.get("error_rebounds") or []
    entries = list(entries) if isinstance(entries, list) else []
    entries.append(record)
    S1_EMBEDDED_STATE["error_rebounds"] = entries
    persist_embedded_state()


class ErrorReboundJob:
    """The before/after check, on a worker thread.

    Same shape as AIJob so the loop can poll it the same way: the thread
    writes only to its own fields, and a failure lands in `error` without
    disturbing the board.
    """

    def __init__(self, task: str, before_bgr, after_bgr, object_list: str = "",
                 start_source=None, events: str = ""):
        self.task = task
        self.before = before_bgr
        self.after = after_bgr
        self.object_list = object_list or ""
        self.version = ERR_NAME
        # (frame, grid) as the board looked when EXECUTE was pressed.
        # Rendered on this thread, not under the operator's click.
        self.start_source = start_source
        self.events = events or ""
        self._lock = threading.Lock()
        self.stage = (f"Error Rebounds {self.version} - comparing before and "
                      f"after ({ERR_MODEL})...")
        self.verdict = ""
        self.reason = ""
        self.objects = []
        self.next = ""
        self.raw = ""
        self.error = ""
        self.done = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def snapshot(self):
        with self._lock:
            return self.stage, self.done

    def _run(self):
        try:
            if self.before is None or self.after is None:
                raise ModelError("Need both a before photo and an after photo.")
            b64_before = encode_jpeg_b64(self.before)
            b64_after = encode_jpeg_b64(self.after)
            if not b64_before or not b64_after:
                raise ModelError("Could not encode the before/after photos.")
            b64_start = None
            if self.start_source:
                source, grid_then = self.start_source
                start = render_vision_board(source, grid_then)
                b64_start = encode_jpeg_b64(start if start is not None
                                            else source)

            messages = self._messages(b64_before, b64_after, b64_start)
            client = make_client()
            print(f"\n=== ERROR REBOUNDS {self.version} INPUT ===")
            print(messages[1]["content"][0]["text"])
            self.raw = call_model(
                client, model=ERR_MODEL, max_tokens=ERR_MAX_TOKENS,
                reasoning=ERR_REASONING,
                stage=f"Error Rebounds {self.version}", messages=messages)
            print(f"\n=== ERROR REBOUNDS {self.version} ===")
            print(self.raw)
            (self.verdict, self.objects, self.reason,
             self.next) = self._parse(self.raw)
        except Exception as e:
            self.error = str(e)
        finally:
            with self._lock:
                self.done = True

    def _messages(self, b64_before, b64_after, b64_start=None):
        """The request: every picture labelled in front of it (initial,
        execution-start, final -- in the order they were taken), the object
        list as the fallible evidence the prompt's rules expect, and the
        execution events this app logs.
        """
        def picture(b64):
            return {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{b64}", "detail": "high"}}

        parts = [f"TASK:\n{self.task}"]
        if self.object_list.strip():
            parts.append("OBJECT LIST (from the original detection -- "
                         f"fallible):\n{self.object_list}")
        parts.append("EXECUTION EVENTS:\n" + (
            self.events.strip() or "None logged -- judge from the images."))
        parts.append("Images follow, each after its label. All show the same "
                     "board with the same lettered/numbered grid. No "
                     "extra-viewpoint images are available.")
        content = [{"type": "text", "text": "\n\n".join(parts)},
                   {"type": "text", "text": "INITIAL IMAGE (the board at "
                                            "planning time):"},
                   picture(b64_before)]
        if b64_start:
            content += [{"type": "text", "text": "EXECUTION-START IMAGE "
                                                 "(fresh scene captured just "
                                                 "before execution):"},
                        picture(b64_start)]
        content += [{"type": "text", "text": "FINAL IMAGE (the board after "
                                             "execution):"},
                    picture(b64_after)]
        return [{"role": "system", "content": ERR3_PROMPT},
                {"role": "user", "content": content}]

    @staticmethod
    def _parse(raw: str):
        """(verdict, [(object, status)], reason, next) from the reply.

        Read leniently -- a stray brace, backtick or case change does not
        turn a clear verdict into no verdict, and a NEXT or REASON that wraps
        onto further lines is kept whole -- but a verdict that was never
        actually given comes back "unknown" with the whole reply as its
        reason rather than being guessed.
        """
        fields, key = {}, None
        for line in (raw or "").splitlines():
            s = line.strip()
            m = re.match(r"^\W*(VERDICT|OBJECTS|REASON|NEXT)\W*:\s*(.*)$", s,
                         re.IGNORECASE)
            if m:
                key = m.group(1).upper()
                fields[key] = m.group(2).strip()
            elif key and s:
                fields[key] = f"{fields[key]} {s}".strip()
        token = re.sub(r"[^a-z_,]", "", fields.get("VERDICT", "").lower()
                       .replace(" ", "_"))
        if token.startswith("done_correct"):
            verdict = "done correctly"
        elif token.startswith("done_wrong"):
            verdict = "done wrongly"
        elif token.startswith("cannot_verif"):
            verdict = "cannot verify"
        else:
            verdict = "unknown"
        objects = []
        for item in fields.get("OBJECTS", "").split(";"):
            name, sep, status = item.partition("=")
            if sep and name.strip():
                objects.append((name.strip(), status.strip().lower()))
        reason = fields.get("REASON", "")
        if verdict == "unknown" and not reason:
            reason = (raw or "").strip()
        return verdict, objects, reason, fields.get("NEXT", "")


@dataclass
class AppState:
    typed_col: Optional[str] = None
    typed_row: Optional[int] = None
    target_col: Optional[int] = None
    target_row: Optional[int] = None
    manual_move_active: bool = False
    out_of_reach: bool = False
    last_tag_col: Optional[int] = None
    last_tag_row: Optional[int] = None
    tag_visible: bool = False
    tag_on_grid: bool = False
    tag_centered: bool = False
    tag_px: Optional[tuple] = None
    tag_raw_px: Optional[tuple] = None
    tag_raw_pts: Optional[object] = None
    target_cell_center_px: Optional[tuple] = None
    _tag_hold_px: Optional[tuple] = None
    _tag_hold_pts: Optional[object] = None
    _tag_hold_until: float = 0.0
    guide_dir: Optional[str] = None
    guide_steps: int = 0
    guide_line: str = ""
    guide_slow: bool = False
    arrived: bool = False
    action_label: Optional[tuple] = None
    dragging_corner: Optional[int] = None
    mouse: tuple = (-1, -1)
    status_message: str = ("Show an AprilTag, then pick a target."
                           "   f: fullscreen   s: settings   o: outlines   n: name objects"
                           "   Cmd+Q: quit")

    ai_task: str = ""
    ai_focus: bool = False
    ai_cursor: int = 0
    ai_select_all: bool = False
    ai_caret_reset_at: float = 0.0
    ai_objects: list = field(default_factory=list)
    show_objects: bool = True
    selected_part: Optional[tuple] = None
    history_open: bool = False
    examples_open: bool = False
    example_notice: Optional[int] = None
    example_notice_until: float = 0.0
    ai_chat: list = field(default_factory=list)
    chat_scroll: int = 0
    ai_job: Optional[object] = None
    stt_job: Optional[object] = None
    stt_insert_at: int = 0

    pending_questions: list = field(default_factory=list)
    pending_qa: list = field(default_factory=list)
    answering_free: bool = False

    exec_pending: bool = False
    exec_auto_at: float = 0.0
    exec_cancelled: bool = True
    exec_cancel_rect: Optional[tuple] = None
    popup_close_rect: Optional[tuple] = None

    missing_popup: Optional[dict] = None
    missing_popup_done_rect: Optional[tuple] = None
    missing_popup_cancel_rect: Optional[tuple] = None

    err_before: Optional[object] = None
    err_task: str = ""
    err_objects: str = ""
    err_ready: bool = False
    err_job: Optional[object] = None
    err_start: Optional[object] = None
    step_err_job: Optional[object] = None
    step_err_prev: Optional[object] = None
    step_err_note: str = ""
    step_err_index: int = -1
    auto_check_done: bool = False
    # A step that failed its check: {"index", "cmd", "title", "word",
    # "reason", "fix", "default", "deadline"} while its popup is up.
    step_fail: Optional[dict] = None
    step_fail_continue_rect: Optional[tuple] = None
    step_fail_replan_rect: Optional[tuple] = None
    step_results: dict = field(default_factory=dict)
    plan_text: str = ""
    replans: int = 0
    replan_notes: list = field(default_factory=list)
    resume_run: bool = False
    run_start: Optional[object] = None

    board_view: Optional[object] = None
    board_raw: Optional[object] = None
    board_full: Optional[object] = None


SIDEBAR_W = 380


def chat_say(state, role: str, text: str):
    """Append one message to the transcript and jump the view to the bottom."""
    text = str(text).strip()
    if not text:
        return
    state.ai_chat.append({"role": role, "text": text})
    state.chat_scroll = 0


def chat_plan(state, commands):
    """Append the live plan checklist as its own message."""
    state.ai_chat.append({"role": "plan", "text": "", "commands": commands})


FREE_ANSWER = "Something else..."


def chat_ask(state, question: str, options):
    """Put one clarity question in the transcript, as clickable options.

    S1-SRC opens a modal for this; there is no modal here, and there does
    not need to be -- the question belongs in the conversation it is part of,
    and the options are rows you click like anything else in this app.
    """
    state.ai_chat.append({"role": "choices", "text": str(question),
                          "options": list(options) + [FREE_ANSWER],
                          "answer": None})
    state.chat_scroll = 0


CHAT_HISTORY_TURNS = 6


def build_chat_history_text(ai_chat):
    """The past few turns of the transcript, formatted for the planner.

    Grouped by user task so a "Planner:"/"Result:" pair always follows the
    "User:" line it belongs to, and capped to the most recent turns so the
    prompt doesn't grow without bound over a long session.
    """
    turns = []
    current = None
    for msg in ai_chat:
        role, text = msg.get("role"), msg.get("text", "")
        if role == "user":
            current = {"user": text, "plan": None, "result": None}
            turns.append(current)
        elif current is None:
            continue
        elif role == "plan":
            commands = msg.get("commands") or []
            current["plan"] = "; ".join(commands[:20])
        elif role == "assistant":
            current["result"] = text
        elif role == "error":
            current["result"] = f"Failed - {text}"
    lines = []
    for t in turns[-CHAT_HISTORY_TURNS:]:
        lines.append(f"User: {t['user']}")
        if t["plan"]:
            lines.append(f"Planner: {t['plan']}")
        if t["result"]:
            lines.append(f"Result: {t['result']}")
    return "\n".join(lines)


TASK_EXAMPLES = (
    ("Sweeping",
     "Sweep the dust into the dustpan using the broom or brush. Sweep the area "
     "directly in front of the opening: the collector's full width by five "
     "grid coordinates outward. If vision shows a dust patch, collect that "
     "dust too. Keep the dustpan in its current position and direction.",
     "Dustpan and a broom or suitable brush. A visible dust patch is optional."),
    ("Boiling leaves",
     "Boil the leaves in the water in the pot. Put the leaves into the pot "
     "if they are outside it. The stove is already below the pot and works "
     "automatically. Do not move the pot or touch or operate the stove. "
     "Leave all unrelated objects alone.",
     "Leaves and a pot containing water. The automatic stove is already below "
     "the pot; it does not need to be shown as a separate object."),
    ("Sorting clothes",
     "Sort the white clothes from the colored clothes. Put all the white "
     "clothes into the plate or bowl. Keep the colored clothes outside it, "
     "together in a separate clear area on the board.",
     "White clothes, colored clothes, and a plate or bowl large enough "
     "to hold the white clothes."),
    ("Tidying the board",
     "Tidy and organize the board. Group similar items together and put "
     "loose items into suitable containers when available. Place the items "
     "neatly and leave clear space. Keep everything on the board.",
     "Scattered items to organize. Suitable containers are optional."),
    ("Soap: press first",
     "Use the sponge or scrubber to apply soap to the plate. First press it "
     "onto the soap bar/red continner/red cup, then lift it. Spread the soap over the entire top "
     "surface of the plate. Return the sponge or scrubber when finished.",
     "Plate, soap bar, and a sponge or scrubber."),
    ("Soap: no press on bar",
     "Use the sponge or scrubber to apply soap to the entire top surface "
     "of the plate. The sponge or scrubber already has soap on it. Do not "
     "press it onto the soap bar. Return it when finished.",
     "Plate and a sponge or scrubber already containing soap. "
     "A soap bar is not required."),
)


class AISidebar:
    """A chat panel: transcript above, prompt box below.

    Drawn to the right of the video with this app's own toolkit rather than
    a second window: HighGUI has one canvas, and a separate window would not
    share the mouse callback the rest of the UI already runs through.

    The transcript is painted into a scratch image the size of the scroll
    viewport and then blitted, so a bubble that runs past either end is
    clipped instead of spilling over the video.
    """

    PAD = 14
    ROW_H = 24
    LINE_H = 17
    SCALE = 0.42
    GAP = 10
    B_PAD = 9
    FIELD_SCALE = 0.44
    FIELD_H = 46
    FIELD_LINE_H = 20
    FIELD_MAX_LINES = 6
    MIC_GAP = 12
    MIC_W = 50 + MIC_GAP

    def __init__(self, x0: int, y0: int, width: int, height: int):
        self._history_anim = 0.0
        self.field_lines = 1
        self.set_geometry(x0, y0, width, height)

    def set_geometry(self, x0, y0, width, height):
        self.x0, self.y0 = x0, y0
        self.width, self.height = width, height
        p = self.PAD
        bottom = y0 + height
        fh = self.FIELD_H + (max(1, self.field_lines) - 1) * self.FIELD_LINE_H
        self.field = (x0 + p, bottom - p - fh,
                      x0 + width - p - 58 - self.MIC_W, bottom - p)
        self.send_btn = Button(">", x0 + width - p - 50,
                               bottom - p - self.FIELD_H,
                               x0 + width - p, bottom - p, "ai_send",
                               style="primary", scale=0.6)
        self._send_is_stop = False
        self.mic_btn = Button("", self.send_btn.x0 - self.MIC_W,
                              bottom - p - self.FIELD_H,
                              self.send_btn.x0 - self.MIC_GAP, bottom - p,
                              "ai_mic", scale=0.5)
        self.check_btn = Button("CHECK", x0 + width - p - 66, y0 + 12,
                                x0 + width - p, y0 + 40, "ai_check",
                                style="accent", scale=0.40)
        self._check_shown = False
        self.history_btn = Button("History", x0 + width - p - 150, y0 + 12,
                                  x0 + width - p - 76, y0 + 40, "ai_history",
                                  scale=0.38)
        self.examples_btn = Button("Examples", x0 + p, y0 + 48,
                                   x0 + p + 100, y0 + 78, "ai_examples",
                                   scale=0.40)
        self._example_rects = []
        self._example_popup_rect = None

        ay1 = self.field[1] - 10
        ay0 = ay1 - 40
        split = x0 + width - p - 100
        self.exec_btn = Button("EXECUTE PHYSICALLY", x0 + p, ay0, split - 8,
                               ay1, "ai_execute", style="accent", scale=0.42)
        self.resim_btn = Button("REPLAY", split, ay0, x0 + width - p, ay1,
                                "ai_resim", scale=0.40)
        self.stop_sim_btn = Button("STOP SIMULATION", x0 + p, ay0,
                                   x0 + width - p, ay1, "ai_stop_sim",
                                   style="primary", scale=0.42)
        self.stop_run_btn = Button("STOP EXECUTION", x0 + p, ay0,
                                   x0 + width - p, ay1, "ai_stop_run",
                                   style="primary", scale=0.42)
        self.reexec_btn = Button("RE-EXECUTE", x0 + p, ay0,
                                 x0 + width - p, ay1, "ai_reexecute",
                                 style="accent", scale=0.42)
        self._action_mode = None
        self.view_full = (x0, y0 + 86, x0 + width, self.field[1] - 8)
        self.view_short = (x0, y0 + 86, x0 + width, ay0 - 8)
        self.view = self.view_full
        self._max_scroll = 0
        self._bar_frac = 1.0
        self._cache = None
        self._cache_key = None
        self._history_rects = []
        self._history_list_rect = None
        self._choice_rects = []
        self._vp_origin = (x0, y0 + 86)
        self._scroll_anim = 0.0

    def contains(self, x, y):
        return (self.x0 <= x <= self.x0 + self.width
                and self.y0 <= y <= self.y0 + self.height)

    def hit_test(self, x, y, history_open=False, state=None):
        if state is not None:
            self.expire_example_notice(state)
            if state.examples_open or state.example_notice is not None:
                for rect, action in self._example_rects:
                    if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                        return action
                rect = self._example_popup_rect
                if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                    return "ai_none"
        if history_open and self._history_list_rect is not None:
            lx0, ly0, lx1, ly1 = self._history_list_rect
            if lx0 <= x <= lx1 and ly0 <= y <= ly1:
                for rect, task in self._history_rects:
                    rx0, ry0, rx1, ry1 = rect
                    if rx0 <= x <= rx1 and ry0 <= y <= ry1:
                        return ("ai_history_pick", task)
                return ("ai_history_pick", None)
        if not self.contains(x, y):
            return None
        for rect, msg, opt in self._choice_rects:
            rx0, ry0, rx1, ry1 = rect
            if rx0 <= x <= rx1 and ry0 <= y <= ry1:
                return ("ai_answer", msg, opt)
        if self.send_btn.contains(x, y):
            return "ai_stop" if self._send_is_stop else "ai_send"
        if self.mic_btn.contains(x, y):
            return "ai_mic"
        if self._action_mode == "exec":
            if self.exec_btn.contains(x, y):
                return "ai_execute"
            if self.resim_btn.contains(x, y):
                return "ai_resim"
        elif self._action_mode == "sim":
            if self.stop_sim_btn.contains(x, y):
                return "ai_stop_sim"
        elif self._action_mode == "run":
            if self.stop_run_btn.contains(x, y):
                return "ai_stop_run"
        elif self._action_mode == "done":
            if self.reexec_btn.contains(x, y):
                return "ai_reexecute"
        if self._check_shown and self.check_btn.contains(x, y):
            return "ai_check"
        if self.history_btn.contains(x, y):
            return "ai_history"
        if self.examples_btn.contains(x, y):
            return "ai_examples"
        fx0, fy0, fx1, fy1 = self.field
        if fx0 <= x <= fx1 and fy0 <= y <= fy1:
            return "ai_focus"
        return "ai_none"

    @staticmethod
    def expire_example_notice(state, now=None):
        if now is None:
            now = time.monotonic()
        if state.example_notice is not None and now >= state.example_notice_until:
            state.example_notice = None

    @staticmethod
    def handle_example_action(state, action):
        if action == "ai_examples":
            state.examples_open = not state.examples_open
            state.example_notice = None
            state.history_open = False
        elif action == "ai_example_close":
            state.examples_open = False
            state.example_notice = None
        elif isinstance(action, tuple) and action[0] == "ai_example_pick":
            index = action[1]
            state.ai_task = TASK_EXAMPLES[index][1]
            state.ai_cursor = len(state.ai_task)
            state.ai_select_all = False
            state.ai_focus = True
            state.ai_caret_reset_at = time.time()
            state.examples_open = False
            state.history_open = False
            state.example_notice = index
            state.example_notice_until = time.monotonic() + 10.0
        else:
            return False
        return True

    def _draw_examples(self, canvas, state, mouse):
        self.expire_example_notice(state)
        self._example_rects = []
        self._example_popup_rect = None
        if not state.examples_open and state.example_notice is None:
            return
        x0, y0 = self.x0 + self.PAD, self.y0 + 86
        x1 = self.x0 + self.width - self.PAD
        if state.examples_open:
            lines = []
            height = 48 + 32 * len(TASK_EXAMPLES)
        else:
            remaining = max(1, int(math.ceil(state.example_notice_until - time.monotonic())))
            lines = self._wrap(TASK_EXAMPLES[state.example_notice][2], x1 - x0 - 24, 0.40)
            height = 70 + 18 * len(lines)
        rect = (x0, y0, x1, y0 + height)
        self._example_popup_rect = rect
        glass_card(canvas, rect, 14)
        close_rect = popup_cross(canvas, rect)
        self._example_rects.append((close_rect, "ai_example_close"))
        title = "Task examples" if state.examples_open else "Objects needed"
        draw_text(canvas, title, (x0 + 12, y0 + 25), 0.44, C_ACCENT, 1)
        if state.examples_open:
            for index, (label, _, _) in enumerate(TASK_EXAMPLES):
                row = (x0 + 6, y0 + 42 + index * 32, x1 - 6, y0 + 70 + index * 32)
                hover = row[0] <= mouse[0] <= row[2] and row[1] <= mouse[1] <= row[3]
                if hover:
                    rounded_rect(canvas, row, 8, C_ACCENT_SO, -1)
                draw_text(canvas, self._fit(label, row[2] - row[0] - 16, 0.40),
                          (row[0] + 8, row[1] + 19), 0.40, C_TEXT, 1)
                self._example_rects.append((row, ("ai_example_pick", index)))
        else:
            for index, line in enumerate(lines):
                draw_text(canvas, line, (x0 + 12, y0 + 50 + index * 18),
                          0.40, C_TEXT, 1)
            draw_text(canvas, f"Closes in {remaining}s - prompt not sent",
                      (x0 + 12, rect[3] - 12), 0.36, C_TEXT_DIM, 1)

    def scroll_by(self, state, delta_px: int):
        """Wheel over the transcript. Scroll is measured up from the bottom."""
        state.chat_scroll = max(0, min(state.chat_scroll + delta_px,
                                       self._max_scroll))

    @staticmethod
    def handle_key(state, key: int):
        """Type into the prompt box. Returns "send" on Enter, "changed", or None.

        Plain typing only. Anything that needs a modifier flag or the field's
        geometry -- arrows, Cmd+A/C/V, Cmd+Delete, Shift+Enter for a new
        line -- comes through handle_edit_key, which calls this for the rest.
        """
        if not state.ai_focus:
            return None
        if key in (13, 10):
            return "send"
        if key in (8, 127):
            state.ai_caret_reset_at = time.time()
            if state.ai_select_all:
                state.ai_task, state.ai_cursor = "", 0
                state.ai_select_all = False
            elif state.ai_cursor > 0:
                state.ai_task = (state.ai_task[:state.ai_cursor - 1]
                                + state.ai_task[state.ai_cursor:])
                state.ai_cursor -= 1
            return "changed"
        if key == 27:
            state.ai_focus = False
            return "changed"
        ch = chr(key) if 32 <= key < 127 else None
        if ch and len(state.ai_task) < MAX_CHAT_CHARS:
            state.ai_caret_reset_at = time.time()
            if state.ai_select_all:
                state.ai_task, state.ai_cursor = ch, 1
                state.ai_select_all = False
            else:
                state.ai_task = (state.ai_task[:state.ai_cursor] + ch
                                + state.ai_task[state.ai_cursor:])
                state.ai_cursor += 1
            return "changed"
        return None


    @staticmethod
    def _live_runner(runner, sim):
        """Whichever runner owns the moment: the rehearsal, or the real run."""
        return sim if sim.active else runner

    def _blocks(self, state, live):
        """Every message as (role, lines, commands, height), oldest first."""
        avail = self.width - 2 * self.PAD
        own = int(avail * 0.86)
        blocks = []
        for msg in state.ai_chat:
            role = msg["role"]
            if role == "plan":
                cmds = msg["commands"]
                h = 22 + max(1, len(cmds)) * self.ROW_H + 2 * self.B_PAD
                blocks.append((role, [], cmds, avail, h))
                continue
            if role == "choices":
                lines = self._wrap(msg["text"], avail - 2 * self.B_PAD,
                                   self.SCALE)
                h = (len(lines) * self.LINE_H
                     + len(msg["options"]) * self.ROW_H
                     + 2 * self.B_PAD + 6)
                blocks.append((role, lines, msg, avail, h))
                continue
            width = own if role == "user" else avail
            lines = self._wrap(msg["text"], width - 2 * self.B_PAD, self.SCALE)
            blocks.append((role, lines, None,
                           width, len(lines) * self.LINE_H + 2 * self.B_PAD))

        for job in (state.ai_job, state.err_job):
            if job is None:
                continue
            stage, done = job.snapshot()
            if not done:
                lines = self._wrap(stage, avail - 2 * self.B_PAD, self.SCALE)
                blocks.append(("working", lines, None, avail,
                               len(lines) * self.LINE_H + 2 * self.B_PAD))
        return blocks

    @staticmethod
    def _stage_key(job):
        if job is None:
            return None
        stage, done = job.snapshot()
        return None if done else stage

    def _transcript_key(self, state, live, scroll_px):
        """Everything the transcript's appearance depends on."""
        answered = tuple(m.get("answer") for m in state.ai_chat
                         if m.get("role") == "choices")
        return (len(state.ai_chat), scroll_px, self.view, answered,
                id(live), id(live.commands), live.index, live.active,
                len(live.commands),
                self._stage_key(state.ai_job), self._stage_key(state.err_job))

    def _backdrop_sample(self, canvas):
        """A sparse sample of the pixels behind the transcript -- part of the
        cache key, so a changed background can never be served a stale
        picture of the old one."""
        vx0, vy0, vx1, vy1 = self.view
        sy = max(1, (vy1 - vy0) // 7)
        sx = max(1, (vx1 - vx0) // 7)
        return canvas[vy0:vy1:sy, vx0:vx1:sx].tobytes()

    def _draw_transcript(self, canvas, state, live):
        vx0, vy0, vx1, vy1 = self.view
        vw, vh = vx1 - vx0, vy1 - vy0
        if vw <= 0 or vh <= 0:
            return

        self._scroll_anim = ease_toward(self._scroll_anim,
                                        float(state.chat_scroll), 0.3)
        scroll_px = int(round(self._scroll_anim))

        key = (self._transcript_key(state, live, scroll_px),
               self._backdrop_sample(canvas))

        # Nothing in the transcript changed since the last frame: put back
        # the picture of it already made. Laying every bubble out again --
        # each message re-wrapped word by word -- every frame was most of
        # what the sidebar cost.
        if (key == self._cache_key and self._cache is not None
                and self._cache.shape[:2] == (vh, vw)):
            canvas[vy0:vy1, vx0:vx1] = self._cache
            state.chat_scroll = min(state.chat_scroll, self._max_scroll)
            if self._max_scroll:
                self._scrollbar(canvas, min(scroll_px, self._max_scroll))
            return

        vp = canvas[vy0:vy1, vx0:vx1].copy()
        cv2.addWeighted(vp, 1.0 - GLASS_ALPHA, np.full_like(vp, C_CARD),
                        GLASS_ALPHA, 0, dst=vp)

        blocks = self._blocks(state, live)
        total = sum(b[4] + self.GAP for b in blocks)
        self._max_scroll = max(0, total - vh)
        state.chat_scroll = min(state.chat_scroll, self._max_scroll)
        scroll_px = min(scroll_px, self._max_scroll)

        if not blocks:
            draw_text(vp, "Ask for a task, and the plan runs here.",
                      (self.PAD, 26), self.SCALE, C_TEXT_DIM, 1)
            draw_text(vp, "e.g. \"put the red cube on the tray\"",
                      (self.PAD, 26 + self.LINE_H), self.SCALE, C_TEXT_DIM, 1)
            canvas[vy0:vy1, vx0:vx1] = vp
            self._cache, self._cache_key = vp, key
            self._choice_rects = []
            return

        self._vp_origin = (vx0, vy0)
        self._choice_rects = []
        y = 0 if total <= vh else vh - total + scroll_px
        for role, lines, cmds, bw, bh in blocks:
            if y + bh >= 0 and y <= vh:
                bx0 = vw - self.PAD - bw if role == "user" else self.PAD
                self._bubble(vp, role, lines, cmds, live,
                             (bx0, y, bx0 + bw, y + bh))
            y += bh + self.GAP

        canvas[vy0:vy1, vx0:vx1] = vp
        self._cache, self._cache_key = vp, key
        self._bar_frac = vh / float(total)
        if self._max_scroll:
            self._scrollbar(canvas, scroll_px)

    def _scrollbar(self, canvas, scroll_px):
        vx0, vy0, vx1, vy1 = self.view
        vh = vy1 - vy0
        bar_h = max(24, int(vh * self._bar_frac))
        top = vy0 + int((vh - bar_h)
                        * (1 - scroll_px / float(self._max_scroll)))
        rounded_rect(canvas, (vx1 - 6, top, vx1 - 3, top + bar_h), 2,
                     C_BORDER, -1)

    def _bubble(self, vp, role, lines, cmds, live, rect):
        x0, y0, x1, y1 = rect
        if role == "user":
            rounded_rect(vp, rect, 12, C_ACCENT_SO, -1)
            colour = C_TEXT
        elif role == "error":
            rounded_rect(vp, rect, 12, C_CARD_SOFT, -1)
            rounded_rect(vp, rect, 12, C_AMBER, 1)
            colour = C_AMBER
        elif role == "working":
            rounded_rect(vp, rect, 12, C_CARD_SOFT, -1)
            colour = C_BLUE
        else:
            rounded_rect(vp, rect, 12, C_CARD_SOFT, -1)
            rounded_rect(vp, rect, 12, C_BORDER, 1)
            colour = C_TEXT

        if role == "plan":
            self._steps(vp, cmds, live, x0, y0, x1)
            return
        if role == "choices":
            self._choices(vp, lines, cmds, x0, y0, x1)
            return
        ty = y0 + self.B_PAD + 12
        for ln in lines:
            draw_text(vp, ln, (x0 + self.B_PAD, ty), self.SCALE, colour, 1)
            ty += self.LINE_H

    def _choices(self, vp, lines, msg, x0, y0, x1):
        """A question and its options. Answered options stay on screen so
        the transcript still reads as what was actually asked and said."""
        ty = y0 + self.B_PAD + 12
        for ln in lines:
            draw_text(vp, ln, (x0 + self.B_PAD, ty), self.SCALE, C_TEXT, 1)
            ty += self.LINE_H
        chosen = msg.get("answer")
        vx0, vy0 = self._vp_origin
        y = ty + 2
        for opt in msg["options"]:
            row = (x0 + 6, y, x1 - 6, y + self.ROW_H - 4)
            picked = chosen is not None and opt == chosen
            if picked:
                rounded_rect(vp, row, 10, C_ACCENT_SO, -1)
                rounded_rect(vp, row, 10, C_ACCENT, 1)
            elif chosen is None:
                rounded_rect(vp, row, 10, C_CARD, -1)
                rounded_rect(vp, row, 10, C_BORDER, 1)
            colour = C_ACCENT if picked else (
                C_TEXT if chosen is None else C_TEXT_DIM)
            label = self._fit(opt, row[2] - row[0] - 20, 0.40)
            draw_text(vp, label, (row[0] + 10, y + 16), 0.40, colour,
                      2 if picked else 1)
            if chosen is None:
                self._choice_rects.append(
                    ((row[0] + vx0, row[1] + vy0, row[2] + vx0, row[3] + vy0),
                     msg, opt))
            y += self.ROW_H

    def _steps(self, vp, cmds, live, x0, y0, x1):
        """The plan as a checklist; the live step is the one being walked.

        `live` is whichever runner owns the moment -- the rehearsal while the
        dot is moving, PlanRunner once the real run starts. Both hand the
        checklist the same list object, so identity still says whether this
        bubble is the plan currently being walked.
        """
        live_plan = cmds is live.commands and live.active
        draw_text(vp, f"PLAN  -  {len(cmds)} steps",
                  (x0 + self.B_PAD, y0 + self.B_PAD + 12), 0.40, C_ACCENT, 2)
        y = y0 + self.B_PAD + 22
        for i, cmd in enumerate(cmds):
            on_step = live_plan and i == live.index
            done = live_plan and i < live.index
            if on_step:
                rounded_rect(vp, (x0 + 4, y, x1 - 4, y + self.ROW_H - 3), 9,
                             C_ACCENT_SO, -1)
            mark = "OK" if done else ("->" if on_step else f"{i + 1}.")
            colour = C_GREEN if done else (C_ACCENT if on_step else C_TEXT_DIM)
            draw_text(vp, mark, (x0 + self.B_PAD, y + 16), 0.38, colour,
                      2 if on_step else 1)
            text = self._fit(cmd, x1 - x0 - 2 * self.B_PAD - 32, 0.40)
            draw_text(vp, text, (x0 + self.B_PAD + 30, y + 16), 0.40,
                      C_TEXT if on_step else C_TEXT_DIM, 2 if on_step else 1)
            y += self.ROW_H

    def _draw_history(self, canvas, state, mouse):
        """Every task you've sent, most recent first, click one to reuse it.

        Eases in from just under the History button rather than snapping
        into place, and fades with the same _history_anim the button-click
        toggle drives, so opening and closing both read as one motion.
        """
        mx, my = mouse
        tasks = []
        for msg in reversed(state.ai_chat):
            if msg["role"] == "user" and msg["text"] not in tasks:
                tasks.append(msg["text"])
        tasks = tasks[:12]

        anim = self._history_anim
        pad, row_h = 10, 30
        lw = self.width - 2 * self.PAD
        lh = pad * 2 + 36 + (max(1, len(tasks)) * row_h)
        lx0 = self.history_btn.x0
        ly0 = self.history_btn.y1 + 8 + int((1.0 - anim) * -10)
        rect = (lx0, ly0, min(lx0 + lw, self.x0 + self.width - self.PAD), ly0 + lh)
        self._history_list_rect = rect

        margin = 20
        bx0 = max(0, lx0 - margin)
        by0 = max(0, min(ly0, self.history_btn.y1 + 8) - margin)
        bx1 = min(canvas.shape[1], rect[2] + margin)
        by1 = min(canvas.shape[0], self.history_btn.y1 + 8 + lh + margin)
        fading = anim < 0.999
        under = canvas[by0:by1, bx0:bx1].copy() if fading else None

        glass_card(canvas, rect, 16)
        self._history_rects = [(popup_cross(canvas, rect), None)]
        if not tasks:
            draw_text(canvas, "Nothing sent yet.", (lx0 + pad, ly0 + pad + 50),
                      0.40, C_TEXT_DIM, 1)
        else:
            y = ly0 + pad + 36
            for task in tasks:
                row = (lx0 + 4, y, rect[2] - 4, y + row_h - 4)
                hovered = row[0] <= mx <= row[2] and row[1] <= my <= row[3]
                if hovered:
                    rounded_rect(canvas, row, 9, C_ACCENT_SO, -1)
                label = self._fit(task, row[2] - row[0] - 16, 0.40)
                draw_text(canvas, label, (row[0] + 8, y + 20), 0.40,
                          C_ACCENT if hovered else C_TEXT, 1)
                self._history_rects.append((row, task))
                y += row_h

        if fading:
            drawn = canvas[by0:by1, bx0:bx1]
            canvas[by0:by1, bx0:bx1] = cv2.addWeighted(
                drawn, anim, under, 1.0 - anim, 0)


    def paint_card(self, canvas):
        """The panel's frosted card and its soft border.

        main() paints this once into the cached window background and then
        draws with card=False: blending a card the size of the whole panel
        was two full-panel copies and blends every frame for a surface that
        never changes.
        """
        rect = (self.x0, self.y0, self.x0 + self.width, self.y0 + self.height)
        rounded_rect(canvas, rect, 22, C_CARD, -1, alpha=0.10)
        rounded_rect(canvas, rect, 22, C_BORDER, 1, alpha=0.45)

    def draw(self, canvas, state, runner, sim, mouse=(-1, -1), shadow=True,
             card=True):
        mx, my = mouse
        want = max(1, min(self.FIELD_MAX_LINES,
                          len(wrap_editable(state.ai_task, self._field_w(),
                                            self.FIELD_SCALE))))
        if want != self.field_lines:
            self.field_lines = want
            self.set_geometry(self.x0, self.y0, self.width, self.height)
        rect = (self.x0, self.y0, self.x0 + self.width, self.y0 + self.height)
        if shadow:
            drop_shadow(canvas, rect, 22, spread=14, strength=0.16)
        if card:
            self.paint_card(canvas)

        p = self.PAD
        draw_text(canvas, "S1-SRC PLANNER", (self.x0 + p, self.y0 + 30),
                  0.46, C_ACCENT, 2)
        busy = state.ai_job is not None and not state.ai_job.done
        checking = state.err_job is not None and not state.err_job.done
        self._send_is_stop = busy

        if sim.active:
            self._action_mode = "sim"
        elif runner.active:
            self._action_mode = "run"
        elif state.exec_pending and not busy:
            self._action_mode = "exec"
        elif runner.finished and not busy:
            self._action_mode = "done"
        else:
            self._action_mode = None

        self._check_shown = (not busy and not checking and not runner.active
                             and not sim.active and state.err_ready)
        if self._check_shown:
            self.check_btn.draw(canvas, hover=self.check_btn.contains(mx, my))
        self.history_btn.draw(canvas, hover=self.history_btn.contains(mx, my),
                              active=state.history_open)
        self.examples_btn.draw(canvas, hover=self.examples_btn.contains(mx, my),
                               active=state.examples_open)

        self.view = self.view_full if self._action_mode is None else self.view_short
        if self._action_mode == "exec":
            self.exec_btn.draw(canvas, hover=self.exec_btn.contains(mx, my))
            self.resim_btn.draw(canvas, hover=self.resim_btn.contains(mx, my))
        elif self._action_mode == "sim":
            self.stop_sim_btn.draw(
                canvas, hover=self.stop_sim_btn.contains(mx, my))
        elif self._action_mode == "run":
            self.stop_run_btn.draw(
                canvas, hover=self.stop_run_btn.contains(mx, my))
        elif self._action_mode == "done":
            self.reexec_btn.draw(
                canvas, hover=self.reexec_btn.contains(mx, my))

        self._draw_transcript(canvas, state,
                              self._live_runner(runner, sim))
        self._history_anim = ease_toward(
            self._history_anim, 1.0 if state.history_open else 0.0)
        if state.history_open or self._history_anim > 0.004:
            self._draw_history(canvas, state, mouse)
        else:
            self._history_rects = []
            self._history_list_rect = None

        fx0, fy0, fx1, fy1 = self.field
        focused = state.ai_focus
        rounded_rect(canvas, self.field, 14, C_CARD_SOFT, -1)
        rounded_rect(canvas, self.field, 14, C_ACCENT if focused else C_BORDER,
                     2 if focused else 1)
        text_y = fy0 + 28
        sc = self.FIELD_SCALE
        if not state.ai_task and not focused:
            draw_text(canvas, "Message the planner...", (fx0 + 12, text_y),
                      sc, C_TEXT_DIM, 1)
        else:
            text = state.ai_task
            lines = wrap_editable(text, self._field_w(), sc)
            first = self._field_first_line(state, lines)
            for i, (ls, le) in enumerate(lines[first:first + self.field_lines]):
                ty = text_y + i * self.FIELD_LINE_H
                shown = text[ls:le]
                if focused and state.ai_select_all and shown:
                    w, _ = text_size(shown, sc, 1)
                    rounded_rect(canvas, (fx0 + 8, ty - 15, fx0 + 12 + w,
                                          ty + 5), 4, C_ACCENT, -1, alpha=0.35)
                draw_text(canvas, shown, (fx0 + 12, ty), sc, C_TEXT, 1)
            if focused and not state.ai_select_all and caret_visible(state):
                cl, cc = caret_line_col(lines, state.ai_cursor)
                if first <= cl < first + self.field_lines:
                    ls = lines[cl][0]
                    cw, _ = text_size(text[ls:ls + cc], sc, 1)
                    cy = text_y + (cl - first) * self.FIELD_LINE_H
                    cv2.line(canvas, (fx0 + 12 + cw, cy - 15),
                             (fx0 + 12 + cw, cy + 5), C_ACCENT, 2, cv2.LINE_AA)

        self.send_btn.label = "" if busy else ">"
        self.send_btn.draw(canvas, hover=self.send_btn.contains(mx, my))
        if busy:
            cx = (self.send_btn.x0 + self.send_btn.x1) // 2
            cy = (self.send_btn.y0 + self.send_btn.y1) // 2
            s = 7
            rounded_rect(canvas, (cx - s, cy - s, cx + s, cy + s), 3,
                         C_BTN_FG, -1)

        self._draw_mic(canvas, state, mx, my)

        rounded_rect(canvas, rect, 22, GLASS_EDGE, 1)
        self._draw_examples(canvas, state, mouse)

    def _draw_mic(self, canvas, state, mx, my):
        """The microphone button, in one of three states.

        Idle    -- a ghost pill with a dark microphone glyph.
        Recording -- an accent pill, a filled glyph, and a ring that breathes
                   with the measured input level, so it is obvious at a
                   glance that the room is actually being heard and not just
                   that a button was pressed.
        Working -- the glyph dims and three dots cycle while the transcript
                   is on its way back.
        """
        rec = MIC.active
        job = state.stt_job
        working = job is not None and not job.done
        b = self.mic_btn
        cx = (b.x0 + b.x1) // 2
        cy = (b.y0 + b.y1) // 2

        if rec:
            lvl = max(0.0, min(1.0, MIC.level * 2.4))
            r = (b.y1 - b.y0) // 2
            grow = int(4 + (self.MIC_GAP // 2 - 1) * lvl)
            rounded_rect(canvas, (b.x0 - grow, b.y0 - grow,
                                  b.x1 + grow, b.y1 + grow),
                         r + grow, C_ACCENT, -1, alpha=0.16 + 0.20 * lvl)

        b.style = "accent" if rec else "ghost"
        b.draw(canvas, hover=b.contains(mx, my))

        fg = C_BTN_FG if rec else (C_TEXT_DIM if working else C_TEXT)
        if working:
            phase = int(time.time() * 3.0) % 3
            for i in range(3):
                c = C_TEXT if i == phase else C_BORDER
                cv2.circle(canvas, (cx - 9 + i * 9, cy), 3, c, -1,
                           cv2.LINE_AA)
            return

        cap_w, cap_h = 7, 10
        top = cy - cap_h - 3
        rounded_rect(canvas, (cx - cap_w // 2, top,
                              cx + cap_w // 2, cy + 1), cap_w // 2, fg, -1)
        cv2.ellipse(canvas, (cx, cy - 1), (7, 7), 0, 25, 155, fg, 2,
                    cv2.LINE_AA)
        cv2.line(canvas, (cx, cy + 6), (cx, cy + 10), fg, 2, cv2.LINE_AA)
        cv2.line(canvas, (cx - 5, cy + 11), (cx + 5, cy + 11), fg, 2,
                 cv2.LINE_AA)

        if rec:
            draw_text_centred(canvas, f"{MIC.elapsed():.0f}s",
                              (b.x0, b.y0 - 26, b.x1, b.y0 - 12),
                              0.34, C_ACCENT, 1)

    @classmethod
    def _wrap(cls, text, width, scale):
        return wrap_text(text, width, scale)

    @staticmethod
    def _fit(text, width, scale):
        return fit_text(text, width, scale)

    @staticmethod
    def _click_index(text, scale, local_x):
        """Which character boundary in `text` a click at `local_x` is
        closest to -- snaps to whichever side of the nearest glyph the
        click fell nearer, the way every text field on the platform does."""
        if local_x <= 0 or not text:
            return 0
        prev_w = 0
        for i in range(1, len(text) + 1):
            w = text_size(text[:i], scale, 1)[0]
            if w >= local_x:
                return i if (local_x - prev_w) > (w - local_x) else i - 1
            prev_w = w
        return len(text)

    def _field_w(self):
        """Usable text width inside the prompt box.

        Derived from the panel's own width rather than from self.field, so it
        can be asked BEFORE the field is re-placed for a new line count --
        the height changes, this does not.
        """
        return self.width - 2 * self.PAD - 58 - 26

    def _field_first_line(self, state, lines):
        """Index of the topmost visible line in the prompt box.

        Past FIELD_MAX_LINES the box stops growing and scrolls instead: it
        follows the caret while the field has focus, and otherwise sits at
        the top of the text.
        """
        extra = len(lines) - self.field_lines
        if extra <= 0:
            return 0
        if not state.ai_focus:
            return 0
        cl, _ = caret_line_col(lines, state.ai_cursor)
        return max(0, min(extra, cl - self.field_lines + 1))

    def move_caret_line(self, state, dy):
        """Up/down arrow: the same column, one visual line away.

        Lives on the sidebar rather than in edit_ai_task because "one line"
        only means anything against the width the field is actually drawn at.
        """
        text = state.ai_task
        sc = self.FIELD_SCALE
        lines = wrap_editable(text, self._field_w(), sc)
        cl, cc = caret_line_col(lines, state.ai_cursor)
        target = cl + (1 if dy > 0 else -1)
        state.ai_caret_reset_at = time.time()
        state.ai_select_all = False
        if target < 0:
            state.ai_cursor = 0
            return
        if target >= len(lines):
            state.ai_cursor = len(text)
            return
        ls, le = lines[cl]
        goal_x = text_size(text[ls:ls + cc], sc, 1)[0]
        ts, te = lines[target]
        col = self._click_index(text[ts:te], sc, goal_x)
        state.ai_cursor = min(ts + col, te)

    def handle_edit_key(self, state, key, mods=0):
        """One key for the prompt box, modifier flags included.

        Everything the field can receive goes through here: the keys that
        need flags cv2 threw away (Cmd+A/C/V, Cmd+Delete, Shift+Enter) and
        the ones that need the field's own geometry (up/down move by visual
        line). Plain typing falls through to handle_key unchanged. Returns
        "send", "changed", or None exactly as handle_key does.
        """
        if not state.ai_focus:
            return None
        cmd = bool(mods & CHAT_CMD_MASK)
        shift = bool(mods & CHAT_SHIFT_MASK)
        step = ARROW_KEYS.get(key)
        if step is not None:
            if step[1]:
                self.move_caret_line(state, step[1])
            else:
                edit_ai_task(state, "left" if step[0] < 0 else "right")
            return "changed"
        if cmd:
            if key in (8, 127):
                edit_ai_task(state, "delete_line")
                return "changed"
            ch = chr(key).lower() if 32 <= key < 127 else ""
            action = {"a": "select_all", "c": "copy", "v": "paste"}.get(ch)
            if action:
                edit_ai_task(state, action)
            return "changed"
        if shift and key in (10, 13):
            edit_ai_task(state, "newline")
            return "changed"
        return self.handle_key(state, key)

    def cursor_click(self, state, x, y=None):
        """Canvas point of a click on the field -> the ai_task index it
        should land the cursor on, matching the lines the field was last
        drawn with."""
        fx0, fy0, fx1, fy1 = self.field
        sc = self.FIELD_SCALE
        local_x = x - (fx0 + 12)
        text = state.ai_task
        if not text:
            return 0
        lines = wrap_editable(text, self._field_w(), sc)
        first = self._field_first_line(state, lines)
        row = 0 if y is None else int((y - (fy0 + 8)) // self.FIELD_LINE_H)
        idx = max(first, min(len(lines) - 1, first + max(0, row)))
        ls, le = lines[idx]
        return min(ls + self._click_index(text[ls:le], sc, local_x), le)

WINDOW_NAME = "Humaniod Operating System - S1"
APP_MENU_NAME = "S1"

TOP_BAR_H = 56
DETECT_MAX_W = 800
SIDE_PAD = 10


TITLE_BAR_PT = 52


def screen_size(default=(1600, 1000)):
    """Usable screen area, in the units the canvas is measured in.

    A HighGUI window maps one image pixel to one DEVICE pixel, so on a 2x
    display a canvas built to the screen's size in points covers only a
    quarter of it. AppKit is asked for the visible frame (menu bar and Dock
    already deducted) and the backing scale, and the two are multiplied.

    The Tk fallback runs in a throwaway subprocess: Tk and the Cocoa event
    loop HighGUI runs on do not coexist, and tearing a Tk root down here
    aborted the whole app ("called Tcl_FindHashEntry on deleted table"). A
    separate process cannot take this one with it, and any failure just falls
    through to the default.
    """
    if NSScreen is not None:
        try:
            screen = NSScreen.mainScreen()
            visible = screen.visibleFrame().size
            scale = float(screen.backingScaleFactor() or 1.0)
            w = int(visible.width * scale)
            h = int((visible.height - TITLE_BAR_PT) * scale)
            if w > 320 and h > 240:
                return w, h
        except Exception as e:
            print(f"[warn] could not read the screen size: {e}")

    probe = ("import tkinter;r=tkinter.Tk();"
             "print(r.winfo_screenwidth(), r.winfo_screenheight())")
    try:
        out = subprocess.run([sys.executable, "-c", probe],
                             capture_output=True, text=True, timeout=6)
        w, h = (int(v) for v in out.stdout.split()[:2])
        if w > 200 and h > 200:
            return w, h - int(TITLE_BAR_PT) - 28
    except Exception:
        pass
    return default


CANVAS_MAX_PIXELS = 0

SCREEN_MARGIN_W = 0
SCREEN_MARGIN_H = 0
MENU_BAR_H = 28
FULLSCREEN_PRIMARY = 1 << 7


def fit_frame(frame, avail_w, avail_h):
    """Scale a camera frame to fill the content area it is given.

    The canvas is built at the window's own size and shown at its natural
    size, so HighGUI never rescales it and a mouse event's coordinates *are*
    canvas coordinates. Anything else puts an unknown scale factor between
    what the user clicks and what the hit tests see, which is how every
    control ends up dead.
    """
    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return frame
    scale = min(avail_w / float(w), avail_h / float(h))
    if 0.999 < scale < 1.001:
        return frame
    # INTER_AREA only earns its cost on a real reduction: for the usual
    # near-1 fit (1920 -> 1857 wide) it was ~11x slower than INTER_LINEAR,
    # 6-7 ms of every frame, for no visible difference.
    interp = cv2.INTER_AREA if scale < 0.5 else cv2.INTER_LINEAR
    return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=interp)


def window_origin(default=(0, MENU_BAR_H)):
    """Top-left corner for the window, in points, clear of the Dock.

    visibleFrame is measured from the bottom-left of the screen; the window
    manager places from the top-left.
    """
    if NSScreen is None:
        return default
    try:
        screen = NSScreen.mainScreen()
        full, vis = screen.frame(), screen.visibleFrame()
        x = int(vis.origin.x)
        y = int(full.size.height - (vis.origin.y + vis.size.height))
        return x, max(0, y)
    except Exception:
        return default


def toggle_fullscreen():
    """Native fullscreen for the HighGUI window, via its own NSWindow.

    HighGUI's own WND_PROP_FULLSCREEN stretches the canvas and stops the
    mouse coordinates lining up with it; asking AppKit to zoom the window
    instead just makes it bigger, and the layout follows the new size on the
    next frame like any other resize.
    """
    if sys.platform != "darwin" or NSApplication is None:
        return False
    try:
        windows = list(NSApplication.sharedApplication().windows())
        target = next((w for w in windows if w.title() == WINDOW_NAME), None)
        if target is None:
            target = next((w for w in windows if w.isVisible()), None)
        if target is None:
            return False
        target.setCollectionBehavior_(FULLSCREEN_PRIMARY)
        target.toggleFullScreen_(None)
        return True
    except Exception as e:
        print(f"[warn] could not toggle fullscreen: {e}")
        return False


def poll_key():
    """Non-blocking key read, on builds old enough to lack pollKey."""
    poll = getattr(cv2, "pollKey", None)
    return poll() if poll is not None else cv2.waitKey(1)


NSEVENT_TYPE_KEYDOWN = 10
# Mouse buttons down/up (left, right, other), keys, modifier changes and the
# scroll wheel: input whose result the operator is waiting to see, so the
# frame loop draws for it at once instead of at the next camera frame.
URGENT_EVENT_TYPES = frozenset((1, 2, 3, 4, 10, 11, 12, 22, 25, 26))
_NS_ANY_EVENT = 0xFFFFFFFFFFFFFFFF
_PUMP = {"ok": None}


def _pump_available() -> bool:
    if _PUMP["ok"] is None:
        _PUMP["ok"] = bool(sys.platform == "darwin" and NSApplication is not None
                           and NSDate is not None and objc is not None
                           and not os.environ.get("S1_HIGHGUI_EVENTS"))
    return _PUMP["ok"]


def pump_events(keys, timeout=0.0):
    """Hand every queued window event to the app now; collect the keys.

    This is cv2.waitKeyEx's job, done without its two costs. On macOS
    HighGUI's waitKey takes ONE event off the queue per call and then sleeps
    10 ms (measured here: every waitKeyEx(1) took 12.3 ms, and 20 queued
    events took 20 calls). So every frame paid 12 ms doing nothing, and a
    click queued behind a few mouse moves, scrolls or enter/exit events
    waited that many whole frames before the app even saw it. Draining the
    queue directly took 0.7 ms for the same 20 events.

    Exactly as HighGUI does: a keyDown with characters is NOT passed on to
    [NSApp sendEvent:] -- its first character is reported, as waitKeyEx
    would return it, in `keys` as (code, modifier flags) -- and everything
    else is dispatched, which is what runs the mouse callback, the scroll
    monitor, menus and the window's own buttons.

    `timeout` > 0 sleeps until the first event arrives or that many seconds
    pass -- a wait that a click ends immediately, unlike time.sleep. Returns
    the set of event types seen. Falls back to cv2.waitKeyEx off macOS.
    """
    if not _pump_available():
        k = cv2.waitKeyEx(max(1, int(timeout * 1000)))
        while k not in (-1, 255):
            keys.append((k, current_modifiers()))
            k = poll_key()
        return {NSEVENT_TYPE_KEYDOWN} if keys else set()
    seen = set()
    try:
        app = NSApplication.sharedApplication()
        until = (NSDate.dateWithTimeIntervalSinceNow_(timeout) if timeout > 0
                 else NSDate.distantPast())
        with objc.autorelease_pool():
            while True:
                event = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                    _NS_ANY_EVENT, until, NSDefaultRunLoopMode, True)
                if event is None:
                    break
                until = NSDate.distantPast()
                kind = int(event.type())
                seen.add(kind)
                if kind == NSEVENT_TYPE_KEYDOWN:
                    chars = event.characters()
                    if chars:
                        keys.append((ord(chars[0]), int(event.modifierFlags())))
                        continue
                app.sendEvent_(event)
            app.updateWindows()
    except Exception as e:
        print(f"[warn] direct event handling failed ({e}) - using cv2.waitKey")
        _PUMP["ok"] = False
    return seen


def window_size(fallback):
    """The window's current image area, so the layout can follow a resize.

    Manual fullscreen and a drag of the window edge both land here. If the
    backend cannot answer, the layout simply stays where it is.
    """
    try:
        _, _, w, h = cv2.getWindowImageRect(WINDOW_NAME)
        if w > 320 and h > 240:
            return int(w), int(h)
    except Exception:
        pass
    return fallback


def name_macos_app():
    """Put APP_MENU_NAME in the macOS menu bar instead of "Python".

    The menu bar names whichever *process* is frontmost, and a HighGUI window
    belongs to the interpreter, so without this it reads "Python" -- and when
    another app is in front, that app's name is what you see, whatever this
    one is called. Both names are set before the first window is created,
    while the info dictionary is still the one AppKit will read.
    """
    if sys.platform != "darwin" or NSBundle is None:
        return
    try:
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None:
            info["CFBundleName"] = APP_MENU_NAME
        NSProcessInfo.processInfo().setProcessName_(APP_MENU_NAME)
    except Exception as e:
        print(f"[warn] could not set the app name: {e}")


APP_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "S1-logo.png")


APP_ICON_CACHE_PATH = os.path.join(tempfile.gettempdir(),
                                   "s1-logo-rounded.png")

ICON_SQUIRCLE_POWER = 5.0

ICON_ARTWORK_RATIO = 824.0 / 1024.0


def _squircle_mask_icon(src_path: str, size: int = 1024):
    """The source artwork, alpha-masked to a macOS-style rounded square.

    `NSApplication.setApplicationIconImage_` draws the image exactly as
    given -- unlike a bundled .icns, macOS does not round it for you -- so
    a plain square PNG sits in the Dock as a hard-edged square instead of
    the rounded shape every other app uses. This bakes that same shape in
    as an alpha channel before the icon is ever set.

    The rounded square is drawn at ICON_ARTWORK_RATIO of the canvas and
    centred, with the rest left transparent. Every stock macOS icon is
    built that way -- the artwork is 824pt inside a 1024pt canvas -- and
    the Dock lays icons out by their CANVAS, not by their artwork. Filling
    the canvas edge to edge therefore renders visibly larger than every
    neighbour, which is exactly what it looked like.
    """
    src = cv2.imread(src_path, cv2.IMREAD_UNCHANGED)
    if src is None:
        return None
    h, w = src.shape[:2]
    n = min(h, w)
    y0, x0 = (h - n) // 2, (w - n) // 2
    src = src[y0:y0 + n, x0:x0 + n]

    art = max(1, int(round(size * ICON_ARTWORK_RATIO)))
    src = cv2.resize(src, (art, art), interpolation=cv2.INTER_AREA)
    if src.shape[2] == 3:
        src = cv2.cvtColor(src, cv2.COLOR_BGR2BGRA)

    yy, xx = np.mgrid[0:art, 0:art].astype(np.float64)
    c = (art - 1) / 2.0
    nx, ny = (xx - c) / c, (yy - c) / c
    r = (np.abs(nx) ** ICON_SQUIRCLE_POWER
        + np.abs(ny) ** ICON_SQUIRCLE_POWER) ** (1.0 / ICON_SQUIRCLE_POWER)
    edge = 1.5 / c
    alpha = np.clip((1.0 - r) / edge + 0.5, 0.0, 1.0)
    src[:, :, 3] = np.minimum(src[:, :, 3], (alpha * 255).astype(np.uint8))

    canvas = np.zeros((size, size, 4), dtype=np.uint8)
    off = (size - art) // 2
    canvas[off:off + art, off:off + art] = src
    return canvas


def set_macos_app_icon():
    """Put S1-logo.png on the Dock icon instead of the bare Python rocket.

    Same reasoning as name_macos_app: a HighGUI window belongs to the bare
    interpreter, which has no icon of its own, so without this the Dock
    shows generic Python art. The artwork is rounded to the same squircle
    every other Dock icon uses (see _squircle_mask_icon) and cached beside
    the source file so the masking only ever runs once; NSImage then reads
    that PNG straight off disk -- no bundle, no Info.plist entry needed --
    and setApplicationIconImage_ swaps it in for the life of the process.
    A missing or unreadable source, or a cache that fails to write, is not
    fatal: the app runs exactly as it always did, just with the default
    icon, or with the unrounded square as a fallback.
    """
    if sys.platform != "darwin" or NSApplication is None or NSImage is None:
        return
    icon_path = APP_ICON_PATH
    try:
        stale = (not os.path.exists(APP_ICON_CACHE_PATH)
                 or os.path.getmtime(APP_ICON_CACHE_PATH)
                 < os.path.getmtime(APP_ICON_PATH))
        if stale:
            rounded = _squircle_mask_icon(APP_ICON_PATH)
            if rounded is not None:
                cv2.imwrite(APP_ICON_CACHE_PATH, rounded)
        if os.path.exists(APP_ICON_CACHE_PATH):
            icon_path = APP_ICON_CACHE_PATH
    except Exception as e:
        print(f"[warn] could not round the app icon: {e}")
    try:
        image = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if image is None:
            print(f"[warn] could not load app icon: {icon_path}")
            return
        NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception as e:
        print(f"[warn] could not set the app icon: {e}")


def _pasteboard_get() -> str:
    if NSPasteboard is None:
        return ""
    try:
        pb = NSPasteboard.generalPasteboard()
        return str(pb.stringForType_(NSPasteboardTypeString) or "")
    except Exception:
        return ""


def _pasteboard_set(text: str):
    if NSPasteboard is None:
        return
    try:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
    except Exception:
        pass


MAX_CHAT_CHARS = 4000


def edit_ai_task(state, action: str):
    """Cursor movement, Cmd+A/C/V/Delete and Shift+Enter on the chat field.

    Kept as one function so the key router, the sidebar and anything else
    that wants to drive the field programmatically share the exact same
    editing rules.
    """
    text, cursor = state.ai_task, state.ai_cursor
    if action != "copy":
        state.ai_caret_reset_at = time.time()
    if action == "left":
        state.ai_cursor = 0 if state.ai_select_all else max(0, cursor - 1)
        state.ai_select_all = False
    elif action == "right":
        state.ai_cursor = (len(text) if state.ai_select_all
                          else min(len(text), cursor + 1))
        state.ai_select_all = False
    elif action == "select_all":
        if text:
            state.ai_select_all = True
    elif action == "home":
        state.ai_cursor = text.rfind("\n", 0, cursor) + 1
        state.ai_select_all = False
    elif action == "end":
        nl = text.find("\n", cursor)
        state.ai_cursor = len(text) if nl < 0 else nl
        state.ai_select_all = False
    elif action == "delete_line":
        if state.ai_select_all or "\n" not in text:
            state.ai_task, state.ai_cursor = "", 0
        else:
            start = text.rfind("\n", 0, cursor) + 1
            state.ai_task = text[:start] + text[cursor:]
            state.ai_cursor = start
        state.ai_select_all = False
    elif action == "copy":
        if text:
            _pasteboard_set(text)
    elif action in ("paste", "newline"):
        if action == "newline":
            added = "\n"
        else:
            added = (_pasteboard_get().replace("\r\n", "\n")
                     .replace("\r", "\n"))
        if not added:
            return
        if state.ai_select_all:
            new_text, new_cursor = added, len(added)
        else:
            new_text = text[:cursor] + added + text[cursor:]
            new_cursor = cursor + len(added)
        state.ai_task = new_text[:MAX_CHAT_CHARS]
        state.ai_cursor = min(new_cursor, len(state.ai_task))
        state.ai_select_all = False


CHAT_CMD_MASK = 1 << 20
CHAT_SHIFT_MASK = 1 << 17


NSEVENT_TYPE_KEYDOWN = 10
NSEVENT_TYPE_SCROLLWHEEL = 22


def current_modifiers() -> int:
    """Which modifier keys are held down right now.

    cv2 hands a key back as a bare character with the modifier flags already
    thrown away, and an AppKit local event monitor -- the obvious place to
    recover them -- never sees a keyDown at all under HighGUI's event loop:
    that loop pulls a keyDown off the queue and returns its character from
    waitKey WITHOUT passing it to [NSApp sendEvent:], which is where local
    monitors (and the main menu's own Cmd key equivalents) are dispatched.
    That is why Cmd+G / Cmd+M / Cmd+; never fired while the bare letter
    still reached cv2, and why Cmd+S only ever looked like it worked -- it
    was the plain-'s' shortcut all along.

    NSEvent's class-level flags are not routed through sendEvent: and so
    still hold the truth. Read the instant a key is dequeued, they say what
    was being held when it was typed.
    """
    if NSEvent is None:
        return 0
    try:
        return int(NSEvent.modifierFlags())
    except Exception:
        return 0


def cmd_route(key, mods, chat_focused):
    """Where a key goes when Cmd is held down. Returns (route, letter):

      "quit"  -- Cmd+Q, from anywhere, whatever is open
      "chat"  -- Cmd+A/C/V while the prompt box has focus: its own editing
                 keys outrank a panel shortcut that wants the same letter
      "menu"  -- offer `letter` to the menu shortcut table
      None    -- Cmd is not held; nothing here applies

    Split out from process_key so the precedence is one testable rule
    rather than a shape buried in a closure inside main().
    """
    if not mods & CHAT_CMD_MASK:
        return None, ""
    ch = chr(key).lower() if 32 <= key < 127 else ""
    if ch == "q":
        return "quit", ch
    if chat_focused and ch in ("a", "c", "v"):
        return "chat", ch
    return "menu", ch


def install_scroll_monitor(on_scroll):
    """Trackpad/wheel scrolling, via AppKit.

    cv2.EVENT_MOUSEWHEEL on this HighGUI/Cocoa build never fires for a
    two-finger trackpad swipe (only, unreliably, for an actual mouse wheel),
    so the Settings list and the AI sidebar were unscrollable by the input
    most users on a Mac actually have. A scrollWheel event, unlike a
    keyDown, does go through [NSApp sendEvent:] on its way out of HighGUI's
    loop -- so a local monitor does see it, and this one is the whole reason
    scrolling works. Keys cannot use this route (see current_modifiers) and
    are read from cv2's own queue instead.
    """
    if sys.platform != "darwin" or NSEvent is None:
        return

    def handler(event):
        try:
            dy = (event.scrollingDeltaY() if event.hasPreciseScrollingDeltas()
                 else event.deltaY() * 8)
            if dy and on_scroll(dy):
                return None
        except Exception as e:
            print(f"[warn] scroll failed: {e}")
        return event

    try:
        NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            1 << NSEVENT_TYPE_SCROLLWHEEL, handler)
    except Exception as e:
        print(f"[warn] could not install scrolling: {e}")


if NSObject is not None:
    class _MenuTarget(NSObject):
        """The Objective-C side of a menu item's target-action pair.

        HighGUI's own Cocoa event loop (already pumped every frame by
        cv2.waitKey, which is how Cmd+Q has always worked here) delivers the
        click straight into this Python method on the same thread as the
        rest of the app, so `callback` can touch app state directly.
        """
        def fireMenuCallback_(self, sender):
            if self.callback is not None:
                self.callback()
else:
    _MenuTarget = None

_menu_targets = []


def _menu_item(title, callback, key_equivalent=""):
    """One NSMenuItem wired to a plain Python callable via _MenuTarget."""
    target = _MenuTarget.alloc().init()
    target.callback = callback
    _menu_targets.append(target)
    menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        title, "fireMenuCallback:", key_equivalent)
    menu_item.setTarget_(target)
    return menu_item


def install_examples_menu(bar, on_example):
    """Add or refresh native Examples beside Comm, even on an existing menu bar."""
    if bar is None or on_example is None or _MenuTarget is None:
        return
    examples_item = None
    insert_at = 1
    for index in range(bar.numberOfItems()):
        item = bar.itemAtIndex_(index)
        submenu = item.submenu()
        title = submenu.title() if submenu is not None else item.title()
        if title in ("File", "Comm"):
            insert_at = index + 1
        if title == "Examples":
            examples_item = item
    menu = NSMenu.alloc().initWithTitle_("Examples")
    for index, (label, _, _) in enumerate(TASK_EXAMPLES):
        menu.addItem_(_menu_item(label, lambda index=index: on_example(index)))
    if examples_item is None:
        examples_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Examples", None, "")
        bar.insertItem_atIndex_(examples_item, min(insert_at, bar.numberOfItems()))
    examples_item.setSubmenu_(menu)


def focus_macos_app(on_port_settings=None, on_serial_console=None,
                    cameras=None, on_select_camera=None,
                    current_camera=None, on_help=None, on_manual_move=None,
                    on_settings=None, on_trigonometry=None,
                    on_gripper=None, on_example=None):
    """Bring the window to the front, and give it a menu bar.

    Without a main menu there is nothing for Cmd+Q to fire: HighGUI never
    builds one, so the shortcut every Mac app has does nothing at all.

    "File" gets a "Select Camera" submenu (one item per detected camera --
    the hierarchy the camera picker needs). "Comm" gets "Port Settings..."
    and "Serial Console...". "Examples" prepares benchmark task drafts.
    "Settings" opens the same frosted settings
    card the gear button does -- playback speed, refresh rate, and the rest
    -- the way S1-SRC's own Settings menu does. "Help" gets a couple of
    informational items. `current_camera` is a callable so the checkmark
    tracks whichever camera is actually live, not just whatever was live
    when the menu was built.
    """
    if sys.platform != "darwin" or NSApplication is None:
        return
    app = NSApplication.sharedApplication()
    try:
        app.setActivationPolicy_(0)
    except Exception as e:
        print(f"[warn] could not set activation policy: {e}")
    try:
        if NSMenu is not None and app.mainMenu() is None:
            bar = NSMenu.alloc().init()
            item = NSMenuItem.alloc().init()
            bar.addItem_(item)
            menu = NSMenu.alloc().init()
            menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                f"Quit {APP_MENU_NAME}", "terminate:", "q"))
            item.setSubmenu_(menu)
            app.setMainMenu_(bar)

            insert_at = 1
            if _MenuTarget is not None and cameras and on_select_camera is not None:
                file_item = NSMenuItem.alloc().init()
                file_menu = NSMenu.alloc().initWithTitle_("File")
                if cameras and on_select_camera is not None:
                    cam_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Select Camera", None, "")
                    cam_menu = NSMenu.alloc().initWithTitle_("Select Camera")
                    for cam_index in cameras:
                        def make_cb(idx=cam_index):
                            return lambda: on_select_camera(idx)
                        entry = _menu_item(f"Camera {cam_index}", make_cb())
                        if current_camera is not None and current_camera() == cam_index:
                            entry.setState_(1)
                        cam_menu.addItem_(entry)
                    cam_item.setSubmenu_(cam_menu)
                    file_menu.addItem_(cam_item)
                file_item.setSubmenu_(file_menu)
                bar.insertItem_atIndex_(file_item, insert_at)
                insert_at += 1

            if on_serial_console is not None and _MenuTarget is not None:
                comm_item = NSMenuItem.alloc().init()
                comm_menu = NSMenu.alloc().initWithTitle_("Comm")
                comm_menu.addItem_(_menu_item("Serial Console...",
                                              on_serial_console, "k"))
                if on_manual_move is not None:
                    comm_menu.addItem_(_menu_item("Manual Move...",
                                                  on_manual_move, "m"))
                comm_menu.addItem_(NSMenuItem.separatorItem())
                comm_menu.addItem_(_menu_item("Port Settings...",
                                              on_port_settings, ","))
                comm_item.setSubmenu_(comm_menu)
                bar.insertItem_atIndex_(comm_item, insert_at)
                insert_at += 1

            if on_settings is not None and _MenuTarget is not None:
                settings_item = NSMenuItem.alloc().init()
                settings_menu = NSMenu.alloc().initWithTitle_("Settings")
                settings_menu.addItem_(_menu_item("Preferences...",
                                                  on_settings, ";"))
                settings_item.setSubmenu_(settings_menu)
                bar.insertItem_atIndex_(settings_item, insert_at)
                insert_at += 1

            if on_trigonometry is not None and _MenuTarget is not None:
                trig_item = NSMenuItem.alloc().init()
                trig_menu = NSMenu.alloc().initWithTitle_("Trigonometry")
                trig_menu.addItem_(_menu_item("Camera / Tag Height...",
                                              on_trigonometry, "t"))
                trig_item.setSubmenu_(trig_menu)
                bar.insertItem_atIndex_(trig_item, insert_at)
                insert_at += 1

            if on_gripper is not None and _MenuTarget is not None:
                grip_item = NSMenuItem.alloc().init()
                grip_menu = NSMenu.alloc().initWithTitle_("Gripper")
                grip_menu.addItem_(_menu_item("Gripper Popup...",
                                              on_gripper, "g"))
                grip_item.setSubmenu_(grip_menu)
                bar.insertItem_atIndex_(grip_item, insert_at)
                insert_at += 1

            if _MenuTarget is not None:
                help_item = NSMenuItem.alloc().init()
                help_menu = NSMenu.alloc().initWithTitle_("Help")
                about = (lambda: on_help("about")) if on_help else None
                shortcuts = (lambda: on_help("shortcuts")) if on_help else None
                help_menu.addItem_(_menu_item("About S1", about))
                help_menu.addItem_(_menu_item("Keyboard Shortcuts", shortcuts))
                help_item.setSubmenu_(help_menu)
                bar.insertItem_atIndex_(help_item, insert_at)
                insert_at += 1
        install_examples_menu(app.mainMenu(), on_example)
    except Exception as e:
        print(f"[warn] could not build the app menu: {e}")
    try:
        app.activateIgnoringOtherApps_(True)
    except Exception as e:
        print(f"[warn] could not activate the app: {e}")


def main():
    name_macos_app()
    set_macos_app_icon()
    cam_settings, saved_grid = load_settings()
    # FastSAM's worker takes seconds to come up (its own Python, Core ML);
    # start it before probing the cameras so the two waits overlap and the
    # first outlines -- which the first task waits on -- arrive sooner.
    vision = LiveVision().start()
    screen_w, screen_h = screen_size()

    try:
        cam_mgr = CameraManager(settings=cam_settings)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        vision.stop()
        sys.exit(1)

    detector = AprilTagDetector()
    tracker = TagTracker(DETECT_MAX_W)
    state = AppState()

    win_w = max(960, screen_w - SCREEN_MARGIN_W)
    win_h = max(600, screen_h - SCREEN_MARGIN_H)
    if CANVAS_MAX_PIXELS and win_w * win_h > CANVAS_MAX_PIXELS:
        k = (CANVAS_MAX_PIXELS / float(win_w * win_h)) ** 0.5
        win_w, win_h = int(win_w * k), int(win_h * k)
    side_w = max(SIDEBAR_W, min(560, win_w // 5))
    avail_w = max(320, win_w - 3 * SIDE_PAD - side_w)
    avail_h = max(240, win_h - TOP_BAR_H)

    deadline = time.time() + 5.0
    ok, frame = cam_mgr.read()
    while not ok and time.time() < deadline:
        time.sleep(0.05)
        ok, frame = cam_mgr.read()
    if not ok:
        print("ERROR: could not read from camera.")
        vision.stop()
        sys.exit(1)
    frame = fit_frame(frame, avail_w, avail_h)
    frame_h, frame_w = frame.shape[:2]

    box, square = None, True
    if saved_grid:
        saved_box, saved_size, square, saved_rel = saved_grid
        if saved_rel and len(saved_rel) == 4:
            box = [saved_rel[0] * frame_w, saved_rel[1] * frame_h,
                   saved_rel[2] * frame_w, saved_rel[3] * frame_h]
        elif saved_box and saved_size and tuple(saved_size) == (frame_w, frame_h):
            box = saved_box
    grid = Grid(frame_w, frame_h, box, square_cells=square)
    if box and square and abs(grid.cell_w - grid.cell_h) > 1.0:
        grid.reset_box()
    total_w, total_h = win_w, win_h
    video_x = SIDE_PAD + (avail_w - frame_w) // 2
    video_y = TOP_BAR_H + (avail_h - frame_h) // 2

    sidebar = AISidebar(win_w - SIDE_PAD - side_w, TOP_BAR_H, side_w, avail_h)
    runner = PlanRunner()
    sim = SimRunner()
    camera_dd = Dropdown("Camera", 20, 8, 190, 50, "camera")
    camera_dd.ITEM_W = 96
    camera_dd.set_items([(i, f"Cam {i}") for i in cam_mgr.available_indices])
    settings_button = Button("Settings", total_w - 140, 12, total_w - 20, 44,
                             "settings", style="primary", scale=0.46)

    def relayout(w, h):
        """Re-place everything around a video of this size."""
        nonlocal frame_w, frame_h, total_w, total_h, video_x, video_y
        nonlocal settings_button
        frame_w, frame_h = w, h
        total_w, total_h = win_w, win_h
        video_x = SIDE_PAD + (avail_w - w) // 2
        video_y = TOP_BAR_H + (avail_h - h) // 2
        grid.update_size(w, h)
        sidebar.set_geometry(win_w - SIDE_PAD - side_w, TOP_BAR_H, side_w,
                             avail_h)
        settings_button = Button("Settings", total_w - 140, 12, total_w - 20,
                                 44, "settings", style="primary", scale=0.46)

    def on_grid_size_changed():
        grid.config_changed()
        state.typed_col = None
        state.typed_row = None
        state.target_col = state.target_row = None
        state.manual_move_active = False
        state.last_tag_col = state.last_tag_row = None
        state.arrived = False
        state.action_label = None
        state.ai_objects = []
        sim.stop(state, "Grid resized -- plan cleared.")
        state.exec_pending = False
        runner.stop(state, "Grid resized -- plan cleared.")

    settings_panel = SettingsPanel(cam_settings, grid, on_grid_size_changed, state)
    trig_panel = TrigPanel()
    port_panel = PortPanel(ARDUINO)
    console_panel = ConsolePanel(ARDUINO)
    manual_move_panel = ManualMovePanel()
    gripper_panel = GripperPanel()
    ARDUINO.on_line = console_panel.log
    console_panel.on_rx_bytes = runner.plunge.note_rx
    simple_gripper = SimpleGripperPanel()
    simple_gripper.on_run = (
        lambda action: gripper_panel.start_automatic_action(action, immediate=True))
    simple_gripper.action_busy = gripper_panel.automatic_busy
    simple_gripper.on_abort = gripper_panel.abort_automatic_action
    runner.on_manual_action = (
        lambda action: simple_gripper.open_for(action, automatic=False))
    runner.manual_wait = simple_gripper.busy
    runner.on_manual_clear = simple_gripper.close
    runner.on_auto_action = simple_gripper.open_for
    runner.auto_wait = simple_gripper.busy
    runner.on_step_done = lambda i, cmd: step_check_start(i, cmd)
    runner.step_wait = lambda: step_fail_wait()

    def on_serial_bytes(data):
        runner.plunge.note_rx(data)
        gripper_panel.note_rx(data)

    console_panel.on_rx_bytes = on_serial_bytes

    auto_port = ARDUINO.guess_arduino_port()
    if auto_port:
        ARDUINO.connect(auto_port)
        port_panel.selected_port = ARDUINO.port
    else:
        console_panel.log("sys", "No Arduino-looking port found at startup -- "
                                 "use File > Port Settings to pick one.")

    def pump_vision_outlines():
        """Draw whatever vision has so far, coarse pass included."""
        job = state.ai_job
        if job is not None and job.vision_ready:
            objs = job.peek_objects()
            if objs:
                state.ai_objects = objs

    def select_part_at(vx, vy):
        """Click a part of an outlined object to aim at it.

        The board is the natural place to say "that bit": a click resolves to
        the smallest part containing it, sets the target to that part's cell,
        and says what it is and whether it may be gripped.
        """
        if not (state.show_objects and state.ai_objects):
            return
        hit = part_at_point(grid, state.ai_objects, vx, vy)
        if hit is None:
            if state.selected_part is not None:
                state.selected_part = None
                state.status_message = "Selection cleared."
            return
        oi, ci = hit
        obj = state.ai_objects[oi]
        name = str(obj.get("name", "object"))
        if ci is None:
            state.selected_part = None
            cell_txt = str(obj.get("center") or "")
            label = name
            grip = ""
        else:
            comp = (obj.get("components") or [])[ci]
            state.selected_part = (oi, ci)
            cell_txt = str(comp.get("center") or obj.get("center") or "")
            label = f"{name} / {comp.get('name', 'part')}"
            g = str(comp.get("grip") or "").lower()
            grip = "  (hold here)" if g == "hold" else \
                   "  (do not grip)" if g == "avoid" else ""
        cell = parse_coordinate(cell_txt)
        if cell is None:
            state.status_message = f"{label} has no cell to aim at."
            return
        col_idx, row_idx = cell
        state.typed_col = CONFIG.columns[col_idx]
        state.typed_row = CONFIG.rows[row_idx]
        handle_go(state)
        state.status_message = f"{label} @ {cell_txt}{grip}"

    def collect_vision_result():
        """Show what vision saw, the moment it has seen it.

        Vision finishes seconds before the planner does, and everything it
        found is on the board already -- holding the object list back until a
        plan exists just leaves the operator watching a spinner.
        """
        job = state.ai_job
        if job is None:
            return
        objects = job.take_vision()
        if not objects:
            return
        state.ai_objects = objects
        chat_say(state, "assistant", vision_report_text(objects))

    def pump_questions():
        """Put the clarity stage's question to the operator, one at a time."""
        job = state.ai_job
        if job is None or state.pending_questions:
            return
        qs = job.take_questions()
        if not qs:
            return
        state.pending_questions = list(qs)
        state.pending_qa = []
        ask_next_question()

    def ask_next_question():
        q = state.pending_questions[0]
        chat_say(state, "assistant", "Before I start:")
        chat_ask(state, q["question"], q["options"])

    def answer_question(msg, option):
        """One option clicked. Ask the next, or release the worker."""
        job = state.ai_job
        if not state.pending_questions or job is None:
            return
        if option == FREE_ANSWER:
            state.answering_free = True
            state.ai_focus = True
            state.status_message = "Type your answer, then press Enter."
            return
        msg["answer"] = option
        record_answer(option)

    def record_answer(text: str):
        job = state.ai_job
        if job is None or not state.pending_questions:
            return
        q = state.pending_questions.pop(0)
        state.pending_qa.append((q["question"], text))
        chat_say(state, "user", text)
        state.answering_free = False
        if state.pending_questions:
            ask_next_question()
        else:
            job.answer(state.pending_qa)
            state.pending_qa = []
            state.status_message = "Thanks -- planning now."

    def collect_ai_result():
        """Fold a finished job into the board, and start the plan running.

        Nothing runs on a partial plan: a MISSING line means the planner
        abandoned a sub-task for want of an object, and executing the rest
        would look like success.
        """
        job, state.ai_job = state.ai_job, None
        state.pending_questions = []
        state.pending_qa = []
        state.answering_free = False
        if job.error:
            runner.load("")
            sim.load([])
            state.exec_pending = False
            state.exec_cancelled = True
            chat_say(state, "error", job.error)
            state.status_message = "Planning failed."
            return
        if job.cancelled:
            return
        if job.rejected:
            chat_say(state, "error", job.rejected)
            state.status_message = "Task needs a dexterous gripper."
            return
        if job.memory_rule:
            rules = load_custom_training()
            rules.append(job.memory_rule)
            save_custom_training(rules)
            chat_say(state, "assistant",
                     f"Saved to custom training: \"{job.memory_rule}\"\n"
                     f"It now applies to every task. Remove it by editing "
                     f"{os.path.basename(TRAINING_PATH)}.")
        try:
            collect_vision_result()
            if job.already_done:
                runner.load("")
                sim.load([])
                state.exec_pending = False
                msg = f"Nothing to do -- {job.already_done}."
                chat_say(state, "assistant", msg)
                state.status_message = msg
                return
            missing = missing_objects(job.plan)
            far = [d["name"] for d in job.out_of_reach
                   if any(_same_object_word(m, d) for m in missing)]
            missing = [m for m in missing
                       if not any(_same_object_word(m, d) for d in job.out_of_reach)]
            if runner.load(job.plan) == 0:
                summary = extract_plan_summary(job.plan)
                if far and not missing:
                    why = ("Not able to complete this task -- " +
                          ", ".join(far) + " is on the board but out of "
                          "the gripper's reach.")
                elif missing:
                    why = ("Not able to complete this task -- " +
                          ", ".join(missing) + " not found on the board." +
                          red_zone_hint())
                else:
                    why = ((summary + " ") if summary else "") + (
                        "No physical actions were planned; the task has not "
                        "been completed.")
                sim.load([])
                state.exec_pending = False
                chat_say(state, "error", why)
                state.status_message = why
                if missing:
                    state.missing_popup = {"task": job.task, "names": missing}
                return
            summary = extract_plan_summary(job.plan)
            if summary:
                chat_say(state, "assistant", summary)
            if missing:
                chat_say(state, "assistant",
                        "Note: could not find " + ", ".join(missing) +
                        " -- that part was skipped, the rest of the task "
                        "still ran.")
            if far:
                chat_say(state, "assistant",
                        "Note: " + ", ".join(far) + " is out of the "
                        "gripper's reach -- that part was skipped.")
            if job.grips_applied:
                lines = gripper_target_lines(job.grips_applied)
                chat_say(state, "assistant",
                        "Gripper:\n" + "\n".join(f"- {ln}" for ln in lines))
            chat_plan(state, runner.commands)
            state.plan_text = job.plan
            if job.resume:
                # The rest of a task, re-planned after a failed step. The
                # task's own before photo and object list stay as they were,
                # and the robot is mid-task: straight to the hand-off
                # countdown, no rehearsal (REPLAY still plays it).
                sim.load(runner.commands)
                state.resume_run = True
                state.exec_pending = True
                state.exec_cancelled = False
                state.exec_auto_at = time.monotonic() + AUTO_EXECUTE_DELAY
                chat_say(state, "assistant",
                         f"Re-planned the rest of the task. Carrying on "
                         f"physically in {AUTO_EXECUTE_DELAY:g}s -- press "
                         f"CANCEL if you need more time.")
                return
            state.replans = 0
            state.replan_notes = []
            state.resume_run = False
            state.err_before = job.frame
            state.err_task = job.task
            state.err_objects = object_list_text(job.objects)
            state.err_ready = False
            state.err_start = None
            sim.load(runner.commands)
            sim.start(state)
            chat_say(state, "assistant",
                     "Simulating the plan on the board -- watch the dot. "
                     "Nothing physical happens until you press EXECUTE.")
        except Exception as e:
            chat_say(state, "error", f"Could not use the AI result: {e}")
            state.status_message = "Planning failed."

    def finish_simulation():
        """The rehearsal reached the end -- offer the real thing, and start
        it on its own in AUTO_EXECUTE_DELAY seconds unless cancelled."""
        if not sim.take_finish():
            return
        state.exec_pending = True
        state.exec_cancelled = False
        state.exec_auto_at = time.monotonic() + AUTO_EXECUTE_DELAY
        state.status_message = (f"Simulation finished -- executing physically "
                                f"in {AUTO_EXECUTE_DELAY:g}s unless cancelled.")
        chat_say(state, "assistant",
                 f"Simulation complete. Executing physically in "
                 f"{AUTO_EXECUTE_DELAY:g}s -- press CANCEL if you need more "
                 f"time, or REPLAY to watch it again.")

    def cancel_auto_execute():
        """CANCEL on the countdown popup, or Esc: stop the auto-start.

        The rehearsed plan stays loaded and ready -- this only calls off the
        automatic hand-off, the same way stopping the dot or a physical run
        does (see ai_stop_sim/ai_stop_run below).
        """
        if state.exec_cancelled:
            return
        state.exec_cancelled = True
        state.exec_cancel_rect = None
        state.status_message = ("Auto-execute cancelled. Press EXECUTE "
                                "PHYSICALLY whenever you're ready.")
        chat_say(state, "assistant",
                 "Cancelled. Press EXECUTE PHYSICALLY whenever you're ready.")

    def start_execution():
        """EXECUTE: hand the rehearsed plan to the real, tag-guided runner."""
        state.exec_pending = False
        state.exec_cancelled = True
        state.exec_cancel_rect = None
        if not runner.commands:
            chat_say(state, "error", "No plan loaded to execute.")
            return
        sim.stop(state, "Simulation stopped.")
        state.err_ready = True
        mark_execution_start()
        chat_say(state, "assistant",
                 "Executing physically. Move the tag as the banner says -- "
                 "each step completes when the tag is actually seen there.")
        runner.start(state)

    def step_check_start(index, cmd):
        """The runner finished a step. With "Check every step" on, photograph
        the board and compare it with how it was before this step. True
        holds the plan until the verdict is in."""
        if (ERR_AUTO != "step" or not step_is_checked(cmd)
                or state.err_before is None):
            return False
        source, grid_now = vision_source(state, grid)
        if source is None:
            return False
        after = render_vision_board(source, grid_now)
        if after is None:
            after = source
        before = state.step_err_prev
        if before is None and state.run_start is not None:
            src0, grid0 = state.run_start
            before = render_vision_board(src0, grid0)
            if before is None:
                before = src0
        if before is None:
            before = state.err_before
        cmds = runner.commands
        n = len(cmds)
        task = (f"{state.err_task}\n\nSTEP CHECK: judge ONLY step "
                f"{index + 1} of {n}, {cmd}: {step_expectation(cmds, index)}. "
                f"The initial image is the board just before this step and "
                f"the final image just after it. Later steps have not run "
                f"yet, so do not fail it for work still to come.")
        state.step_err_note = f"Step {index + 1}/{n}: {cmd}"
        state.step_err_index = index
        state.step_err_job = ErrorReboundJob(
            task, before, after, state.err_objects,
            events=step_events(runner, index)).start()
        state.step_err_prev = after
        state.status_message = (f"Error Rebounds {ERR_NAME}: checking "
                                f"{state.step_err_note}...")
        return True

    def collect_step_err_result():
        """The per-step verdict. Right: carry on. Wrong: the popup offers
        CONTINUE ANYWAY or REPLAN and replans on its own after
        STEP_FAIL_WAIT_S. Not verifiable (the gripper over the object, an
        unreadable reply): the same popup, but it carries on by itself --
        replanning a pickup nobody saw fail would pick up twice. A failed
        call never stops the run; the whole-task CHECK is still there."""
        job = state.step_err_job
        if job is None or not job.done:
            return
        state.step_err_job = None
        if not runner.active:
            return
        index = state.step_err_index
        name = f"Error Rebounds {job.version} - {state.step_err_note}"
        append_err_history({
            "task": job.task, "version": job.version, "step": state.step_err_note,
            "verdict": job.verdict,
            "objects": [f"{obj}={status}" for obj, status in job.objects],
            "reason": job.reason, "next": job.next, "model": ERR_MODEL,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        if job.error:
            chat_say(state, "error", f"{name}: check failed ({job.error}) - "
                     "carrying on.")
            return
        if job.verdict == "done correctly":
            state.step_results[index] = "ok"
            chat_say(state, "assistant", f"{name}: done correctly.")
            return
        wrong = job.verdict == "done wrongly"
        word = ("DONE WRONG" if wrong else "CANNOT VERIFY"
                if job.verdict == "cannot verify" else "NO CLEAR VERDICT")
        state.step_results[index] = "wrong" if wrong else "unverified"
        cmd = runner.commands[index] if 0 <= index < len(runner.commands) else ""
        step = f"Step {index + 1}/{len(runner.commands)} ({action_label(cmd)})"
        default = "replan" if wrong else "continue"
        auto = not wrong or state.replans < REPLAN_AUTO_LIMIT
        state.step_fail = {
            "index": index, "cmd": cmd, "word": word,
            "title": f"{step} went wrong" if wrong
                     else f"{step} could not be checked",
            "reason": job.reason, "fix": (job.next or "").strip(),
            "default": default,
            "deadline": time.monotonic() + STEP_FAIL_WAIT_S if auto else None,
        }
        chat_say(state, "error", f"{name}: {word}.\n{job.reason}".strip())
        state.status_message = state.step_fail["title"]

    def step_fail_wait():
        """The runner's step gate: hold while a check runs or its popup is
        up; the popup's title is what the status line shows meanwhile."""
        if state.step_fail is not None:
            return f"{state.step_fail['title']} - continue or replan?"
        return state.step_err_job is not None

    def tick_step_fail():
        """Once a frame: the popup's default action when its time is up,
        and no popup left behind by a run stopped from the sidebar."""
        fail = state.step_fail
        if fail is None:
            return
        if not runner.active:
            state.step_fail = None
            return
        if fail["deadline"] is not None and time.monotonic() >= fail["deadline"]:
            if fail["default"] == "replan":
                step_fail_replan()
            else:
                step_fail_continue()

    def step_fail_continue():
        """CONTINUE ANYWAY: the runner goes on to the next step as planned."""
        fail, state.step_fail = state.step_fail, None
        if fail is None:
            return
        chat_say(state, "assistant",
                 f"Carrying on with the plan after step {fail['index'] + 1}.")
        state.status_message = "Carrying on with the plan."

    def step_fail_replan():
        """REPLAN: stop here and have the planner write only what is left
        of the task -- its own plan, how far it got and what the check
        found go with it -- then carry on from there."""
        fail, state.step_fail = state.step_fail, None
        if fail is None:
            return
        cmds = list(runner.commands)
        index = fail["index"]
        runner.stop(state, f"Re-planning from step {index + 1}...")
        if state.ai_job is not None and not state.ai_job.done:
            return
        source, grid_now = vision_source(state, grid)
        if source is None or vision.failed:
            chat_say(state, "error", vision.failed or
                     "No frame from the camera to re-plan from.")
            return
        note = replan_note(cmds, state.plan_text, index, fail["word"],
                           fail["reason"], fail["fix"], state.step_results)
        state.replans += 1
        state.replan_notes.append(
            f"Step {index + 1} of the plan then running ({fail['cmd']}) "
            f"failed its check ({fail['word']}: {fail['reason'] or 'no reason'}); "
            f"the rest of the task was re-planned from there.")
        sim.stop(state, "Re-planning after a failed step")
        state.exec_pending = False
        state.exec_cancelled = True
        chat_say(state, "assistant",
                 f"Re-planning from step {index + 1} -- only what is left of "
                 f"the task, not the whole task.")
        state.ai_job = AIJob(None, state.err_task,
                             build_chat_history_text(state.ai_chat),
                             vision=vision, board_source=(source, grid_now),
                             resume=note).start()

    def mark_execution_start():
        """Keep the board as it is right now, the instant a physical run
        starts: ERR-3's execution-start image. Only a reference to a camera
        frame nothing draws on -- it is rendered on the checker's thread."""
        source, grid_now = vision_source(state, grid)
        start = (source, grid_now) if source is not None else None
        state.run_start = start
        if not state.resume_run:
            # A run carrying a task on after a replan keeps the task's own
            # execution-start photo for the whole-task CHECK.
            state.err_start = start
        state.step_err_prev = None
        state.step_err_job = None
        state.step_fail = None
        state.step_results = {}
        state.auto_check_done = False

    def launch_err_check():
        """CHECK: photograph the board as it is now and compare the pair.

        The after shot is taken here, at the moment of the click, from the
        live camera -- there is nothing to upload, unlike S1-SRC, because
        this app is looking at the real board the whole time.
        """
        if state.err_job is not None and not state.err_job.done:
            return
        if state.err_before is None:
            chat_say(state, "error",
                     "Nothing to check yet -- run a task first.")
            return
        source, grid_now = vision_source(state, grid)
        if source is None:
            chat_say(state, "error",
                     "No frame from the camera for the after photo.")
            return
        after = render_vision_board(source, grid_now)
        if after is None:
            after = source
        events = execution_events(runner)
        if state.replan_notes:
            events = "\n".join([events] + state.replan_notes).strip()
        state.err_job = ErrorReboundJob(
            state.err_task, state.err_before, after, state.err_objects,
            start_source=state.err_start, events=events).start()
        state.status_message = (f"Error Rebounds {ERR_NAME}: checking the "
                                f"finished task...")

    def collect_err_result():
        """Print the checker's own verdict. Never touches the plan or board."""
        job = state.err_job
        if job is None or not job.done:
            return
        state.err_job = None
        name = f"Error Rebounds {job.version}"
        if job.error:
            chat_say(state, "error", f"{name} failed: {job.error}")
            state.status_message = f"{name} failed."
            return
        if job.verdict == "done correctly":
            head, role = f"{name}  -  DONE CORRECTLY", "assistant"
        elif job.verdict == "done wrongly":
            head, role = f"{name}  -  DONE WRONG, REDO", "error"
        elif job.verdict == "cannot verify":
            head, role = f"{name}  -  CANNOT VERIFY", "error"
        else:
            head, role = f"{name}  -  no clear verdict", "error"
        lines = [head]
        if job.objects:
            lines.append("Objects: " + "; ".join(
                f"{obj} = {status}" for obj, status in job.objects))
        if job.reason:
            lines.append(f"Reason: {job.reason}")
        if job.next:
            lines.append(f"Next: {job.next}")
        chat_say(state, role, "\n".join(lines))
        state.status_message = head
        append_err_history({
            "task": job.task,
            "version": job.version,
            "verdict": job.verdict,
            "objects": [f"{obj}={status}" for obj, status in job.objects],
            "reason": job.reason,
            "next": job.next,
            "model": ERR_MODEL,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        })

    def launch_ai():
        """Snapshot the board and hand it to vision, then the planner."""
        task = state.ai_task.strip()
        if not task:
            return
        if state.answering_free and state.pending_questions:
            state.ai_task = ""
            state.ai_cursor = 0
            state.ai_select_all = False
            for msg in reversed(state.ai_chat):
                if msg.get("role") == "choices" and msg.get("answer") is None:
                    msg["answer"] = FREE_ANSWER
                    break
            record_answer(task)
            return
        if state.ai_job is not None and not state.ai_job.done:
            if state.ai_job.blocked:
                state.ai_job.cancel()
                state.ai_job = None
                state.pending_questions = []
                state.pending_qa = []
                state.answering_free = False
                chat_say(state, "assistant", "Starting over with the new task.")
            else:
                return
        history = build_chat_history_text(state.ai_chat)
        chat_say(state, "user", task)
        state.ai_task = ""
        state.ai_cursor = 0
        state.ai_select_all = False
        source, grid_now = vision_source(state, grid)
        if source is None:
            chat_say(state, "error", "No frame from the camera yet.")
            return
        if vision.failed:
            chat_say(state, "error", vision.failed)
            return
        sim.stop(state, f"Planning: {task}")
        state.exec_pending = False
        runner.stop(state, f"Planning: {task}")
        # The "before" photo for Error Rebounds is rendered on the job's own
        # thread: ~12 ms of drawing used to sit between the click and the
        # window showing the task was sent.
        state.ai_job = AIJob(None, task, history, vision=vision,
                             board_source=(source, grid_now)).start()

    def toggle_voice(state):
        """The microphone button: start a take, or end one and transcribe.

        Press-to-start / press-to-stop rather than hold-to-talk. HighGUI
        delivers a button-up wherever the pointer happens to be, so a
        hold-to-talk button loses the take whenever the mouse drifts off it
        mid-sentence -- and someone dictating a long task looks at the board,
        not at the cursor.
        """
        if MIC.active:
            samples, rate = MIC.stop()
            secs = len(samples) / float(rate or 1)
            if secs < 0.2:
                state.status_message = "Too short -- hold it while you speak."
                return
            state.stt_insert_at = state.ai_cursor
            state.stt_job = TranscribeJob(samples, rate).start()
            state.status_message = "Transcribing..."
            return

        if state.stt_job is not None and not state.stt_job.done:
            return
        if state.stt_job is not None:
            state.stt_job = None
        why = MIC.start()
        if why:
            chat_say(state, "error", why)
            state.status_message = "Microphone unavailable."
            return
        state.ai_focus = True
        state.ai_select_all = False
        state.ai_caret_reset_at = time.time()
        state.status_message = "Listening -- press the microphone again to stop."

    def collect_transcript():
        """Poll the transcription job and type its text into the prompt box.

        The text is inserted at the caret position captured when the take
        ended, so dictating into the middle of a half-typed sentence does
        the obvious thing, and anything typed while the model was working is
        kept rather than overwritten.
        """
        job = state.stt_job
        if job is None or not job.done:
            return
        state.stt_job = None
        if job.cancelled:
            return
        if job.error:
            chat_say(state, "error", job.error)
            state.status_message = job.error
            return
        text = job.text.strip()
        if not text:
            state.status_message = "Nothing recognised."
            return
        merged, caret = merge_transcript(state.ai_task, text,
                                         state.stt_insert_at)
        state.ai_task = merged
        state.ai_cursor = caret
        state.ai_select_all = False
        state.ai_focus = True
        state.ai_caret_reset_at = time.time()
        state.status_message = "Transcribed."

    def on_mouse(event, x, y, flags, userdata):
        state.mouse = (x, y)
        if DEBUG_INPUT and event == cv2.EVENT_LBUTTONDOWN:
            print(f"[click] ({x}, {y})"
                  f" popup_close_rect={state.popup_close_rect}"
                  f" exec_cancel_rect={state.exec_cancel_rect}"
                  f" camera_dd.open={camera_dd.open}"
                  f" sidebar.contains={sidebar.contains(x, y)}"
                  f" sidebar.box=({sidebar.x0},{sidebar.y0},"
                  f"{sidebar.x0 + sidebar.width},{sidebar.y0 + sidebar.height})",
                  flush=True)
        vx = x - video_x
        vy = y - video_y
        in_video = 0 <= vy < frame_h and 0 <= vx < frame_w

        if event == cv2.EVENT_LBUTTONDOWN:
            if state.step_fail is not None:
                for rect, act in ((state.step_fail_continue_rect,
                                   step_fail_continue),
                                  (state.step_fail_replan_rect,
                                   step_fail_replan)):
                    if rect is not None:
                        bx0, by0, bx1, by1 = rect
                        if bx0 <= vx <= bx1 and by0 <= vy <= by1:
                            act()
                            return
            if state.missing_popup is not None:
                task = state.missing_popup["task"]
                if state.missing_popup_done_rect is not None:
                    bx0, by0, bx1, by1 = state.missing_popup_done_rect
                    if bx0 <= vx <= bx1 and by0 <= vy <= by1:
                        state.missing_popup = None
                        state.ai_task = task
                        launch_ai()
                        return
                if state.missing_popup_cancel_rect is not None:
                    bx0, by0, bx1, by1 = state.missing_popup_cancel_rect
                    if bx0 <= vx <= bx1 and by0 <= vy <= by1:
                        state.missing_popup = None
                        chat_say(state, "assistant",
                                "Task cancelled.")
                        state.status_message = "Task cancelled."
                        return
                return
            if state.popup_close_rect is not None:
                bx0, by0, bx1, by1 = state.popup_close_rect
                if bx0 <= vx <= bx1 and by0 <= vy <= by1:
                    if sim.active and sim.popup:
                        sim.popup = ""
                    else:
                        cancel_auto_execute()
                    state.popup_close_rect = None
                    return
            if state.exec_cancel_rect is not None:
                bx0, by0, bx1, by1 = state.exec_cancel_rect
                if bx0 <= vx <= bx1 and by0 <= vy <= by1:
                    cancel_auto_execute()
                    return
            if camera_dd.open:
                chosen = camera_dd.hit_item(x, y)
                on_button = camera_dd.contains(x, y)
                in_list = camera_dd.list_contains(x, y)
                camera_dd.open = False
                if chosen is not None:
                    if cam_mgr.select(chosen):
                        state.status_message = f"Camera {chosen} selected."
                    else:
                        state.status_message = f"Camera {chosen} failed to open."
                    return
                if on_button or in_list:
                    return
            if camera_dd.contains(x, y):
                camera_dd.open = not camera_dd.open
                return
            if settings_button.contains(x, y):
                settings_panel.toggle()
                state.status_message = ("Settings open." if settings_panel.visible
                                        else "Settings closed.")
                return

            if sidebar.contains(x, y):
                hit = sidebar.hit_test(x, y, history_open=state.history_open,
                                       state=state)
                if DEBUG_INPUT:
                    print(f"[click] sidebar.hit_test -> {hit}", flush=True)
                if hit == "ai_check":
                    state.history_open = False
                    state.examples_open = False
                    launch_err_check()
                elif sidebar.handle_example_action(state, hit):
                    pass
                elif isinstance(hit, tuple) and hit[0] == "ai_answer":
                    state.history_open = False
                    answer_question(hit[1], hit[2])
                elif isinstance(hit, tuple) and hit[0] == "ai_history_pick":
                    if hit[1] is not None:
                        state.ai_task = hit[1]
                        state.ai_cursor = len(hit[1])
                        state.ai_select_all = False
                        state.ai_focus = True
                        state.ai_caret_reset_at = time.time()
                    state.history_open = False
                elif hit == "ai_history":
                    state.examples_open = False
                    state.example_notice = None
                    state.history_open = not state.history_open
                elif hit == "ai_send":
                    state.history_open = False
                    launch_ai()
                elif hit == "ai_mic":
                    state.history_open = False
                    toggle_voice(state)
                elif hit == "ai_execute":
                    state.history_open = False
                    start_execution()
                elif hit == "ai_resim":
                    state.history_open = False
                    sim.start(state)
                elif hit == "ai_stop":
                    state.history_open = False
                    state.ai_job = None
                    state.status_message = "Stopped."
                    chat_say(state, "assistant", "Stopped.")
                elif hit == "ai_stop_sim":
                    state.history_open = False
                    sim.stop(state, "Simulation stopped.")
                    state.exec_pending = True
                    state.exec_cancelled = True
                    chat_say(state, "assistant",
                             "Simulation stopped. Press EXECUTE PHYSICALLY "
                             "when you want to run it for real, or REPLAY "
                             "to watch it again.")
                elif hit == "ai_stop_run":
                    state.history_open = False
                    runner.stop(state, "Execution stopped.")
                    state.exec_pending = bool(runner.commands)
                    state.exec_cancelled = True
                    chat_say(state, "assistant",
                             "Execution stopped. Press EXECUTE PHYSICALLY to "
                             "run it again from the top.")
                elif hit == "ai_reexecute":
                    state.history_open = False
                    mark_execution_start()
                    chat_say(state, "assistant",
                             "Re-executing physically from the top. Move the "
                             "tag as the banner says.")
                    runner.start(state)
                elif hit == "ai_focus":
                    state.history_open = False
                    state.ai_cursor = sidebar.cursor_click(state, x, y)
                    state.ai_select_all = False
                    state.ai_focus = True
                    state.ai_caret_reset_at = time.time()
                else:
                    state.history_open = False
                return

            if in_video:
                if dispatch_video_dropdowns(
                        vx, vy, settings_panel, trig_panel, manual_move_panel):
                    save_settings(cam_settings, grid)
                    return
                consumed = simple_gripper.press(vx, vy)
                if consumed is None:
                    consumed = gripper_panel.press(vx, vy)
                if consumed is not None:
                    if consumed:
                        state.status_message = consumed
                    save_settings(cam_settings, grid)
                    return
                consumed = manual_move_panel.hit_test(vx, vy, state, runner, sim)
                if consumed is not None:
                    if consumed:
                        state.status_message = consumed
                    return
                consumed = console_panel.hit_test(vx, vy)
                if consumed is not None:
                    if consumed:
                        state.status_message = consumed
                    return
                consumed = port_panel.hit_test(vx, vy)
                if consumed is not None:
                    if consumed:
                        state.status_message = consumed
                    return
                consumed = trig_panel.hit_test(vx, vy, cam_settings, grid,
                                              state, runner, sim)
                if consumed is not None:
                    if consumed:
                        state.status_message = consumed
                    return
                consumed = settings_panel.hit_test(vx, vy)
                if consumed is not None:
                    if consumed:
                        state.status_message = consumed
                    return
                if settings_panel.edit_corners:
                    idx = grid.nearest_corner(vx, vy)
                    if idx is not None:
                        state.dragging_corner = idx
                        state.status_message = f"Dragging corner {idx + 1}."
                    return
                select_part_at(vx, vy)
                return

        elif event == cv2.EVENT_MOUSEWHEEL:
            if settings_panel.wants_scroll(vx, vy):
                delta = flags >> 16
                if delta > 32767:
                    delta -= 65536
                settings_panel.scroll_by(int(round(-delta * 0.4)))
            elif sidebar.contains(x, y):
                delta = flags >> 16
                if delta > 32767:
                    delta -= 65536
                px = delta * 0.4
                if 0 < abs(px) < 1:
                    px = 1.0 if px > 0 else -1.0
                sidebar.scroll_by(state, int(round(px)))
            return

        elif event == cv2.EVENT_MOUSEMOVE:
            moved = gripper_panel.drag(vx, vy)
            if moved is not None:
                state.status_message = moved
            elif state.dragging_corner is not None:
                grid.move_corner(state.dragging_corner, vx, vy)

        elif event == cv2.EVENT_LBUTTONUP:
            if gripper_panel.release():
                return
            if state.dragging_corner is not None:
                state.dragging_corner = None
                state.status_message = "Boundary updated and saved."
                save_settings(cam_settings, grid)

    name_macos_app()
    set_macos_app_icon()
    def process_key(key, mods=0):
        """One keypress, with whatever modifiers were held. Returns "quit"
        when the app should close.

        `mods` comes from current_modifiers() rather than from the key code:
        cv2 reports Cmd+G as a bare "g", so the flags have to be read
        separately or every Cmd shortcut collapses into its plain letter.
        """
        route, ch = cmd_route(key, mods, state.ai_focus)
        if route == "quit":
            return "quit"
        if route == "menu":
            if on_cmd_key(ch):
                return None
            if not state.ai_focus:
                return None
        if console_panel.focused:
            console_panel.handle_key(key)
            return None
        if manual_move_panel.text_focus:
            manual_move_panel.handle_key(key, state, runner, sim)
            return None
        was_focused = state.ai_focus
        if sidebar.handle_edit_key(state, key, mods) == "send":
            launch_ai()
            return None
        if was_focused:
            return None
        if manual_move_panel.handle_nav_key(key, state, runner, sim):
            return None

        if key == 27 and state.missing_popup is not None:
            state.missing_popup = None
            chat_say(state, "assistant", "Task cancelled.")
            state.status_message = "Task cancelled."
            return None
        if key == 27 and state.exec_cancel_rect is not None:
            cancel_auto_execute()
            return None
        if key == 27 or key == ord('q'):
            if console_panel.visible:
                console_panel.toggle()
            elif port_panel.visible:
                port_panel.toggle()
            elif manual_move_panel.visible:
                manual_move_panel.close()
            elif settings_panel.visible:
                settings_panel.toggle()
            elif trig_panel.visible:
                trig_panel.toggle()
            elif gripper_panel.visible:
                gripper_panel.close()
            else:
                return "quit"
            return None
        if key == ord('f'):
            if not toggle_fullscreen():
                state.status_message = "Fullscreen is not available here."
            return None
        if key == ord('o'):
            state.show_objects = not state.show_objects
            state.status_message = ("Object outlines on." if state.show_objects
                                    else "Object outlines off.")
            return None
        if key == ord('n'):
            vision.name_now()
            state.status_message = (vision.failed or vision.namer.current_message()
                                    or f"Naming objects ({NAMER_MODEL})...")
            return None
        if key == ord('s'):
            settings_panel.toggle()
        if key == ord('w'):
            save_settings(cam_settings, grid)
            state.status_message = "Settings saved."
        return None

    def select_camera_from_menu(index):
        if cam_mgr.select(index):
            state.status_message = f"Switched to camera {index}."
        else:
            state.status_message = f"Camera {index} is already selected."

    def show_help(topic):
        if topic == "about":
            chat_say(state, "assistant",
                     "S1-SRC-- AprilTag-guided gantry assistant: Vision AI "
                     "(FastSAM outlines, tracked and named) feeding the "
                     "S1-SRC planner.")
        elif topic == "shortcuts":
            chat_say(state, "assistant",
                     "Shortcuts: F fullscreen, O toggle object outlines, "
                     "N name the objects on the board, "
                     "W save settings, Esc cancel/quit, Cmd+, Port Settings, "
                     "Cmd+K Serial Console, Cmd+M Manual Move, "
                     "Cmd+; Settings, Cmd+T Trigonometry, Cmd+G Gripper.")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(WINDOW_NAME, win_w, win_h)
    cv2.moveWindow(WINDOW_NAME, *window_origin())
    cv2.setMouseCallback(WINDOW_NAME, on_mouse)
    MENU_ACTIONS = {
        ",": port_panel.open,
        "k": console_panel.open,
        "m": manual_move_panel.toggle,
        ";": settings_panel.toggle,
        "t": trig_panel.toggle,
        "g": gripper_panel.toggle,
    }

    def on_cmd_key(ch):
        """Fire a menu shortcut. True when it was ours, so the AppKit
        monitor can swallow the event instead of letting the bare letter
        fall through to cv2 and trigger a plain-letter shortcut too."""
        action = MENU_ACTIONS.get(ch)
        if action is None:
            return False
        action()
        return True

    focus_macos_app(on_port_settings=MENU_ACTIONS[","],
                    on_serial_console=MENU_ACTIONS["k"],
                    cameras=cam_mgr.available_indices,
                    on_select_camera=select_camera_from_menu,
                    current_camera=cam_mgr.current_index,
                    on_help=show_help,
                    on_manual_move=MENU_ACTIONS["m"],
                    on_settings=MENU_ACTIONS[";"],
                    on_trigonometry=MENU_ACTIONS["t"],
                    on_gripper=MENU_ACTIONS["g"],
                    on_example=lambda index: sidebar.handle_example_action(
                        state, ("ai_example_pick", index)))
    def on_scroll(dy):
        """A trackpad/wheel scroll, delivered via AppKit because
        cv2.EVENT_MOUSEWHEEL never fires for a two-finger swipe on this
        HighGUI build (see install_scroll_monitor). `dy` is AppKit's own
        sign convention, natural scrolling already applied: fingers down
        gives a POSITIVE dy and should reveal whatever sits above.

        The two panels count their scroll in opposite directions, so they
        need opposite signs here -- getting this wrong is what made the
        transcript feel unscrollable. SettingsPanel.scroll is a normal
        top-down offset, so revealing content above means decreasing it.
        AISidebar.chat_scroll is measured UP FROM THE BOTTOM (0 = newest
        message, the resting position), so revealing older messages means
        INCREASING it. Negating both, as this did, left the only working
        gesture the counter-intuitive one: swiping down to reach the
        history just pinned chat_scroll at 0 and looked completely dead.
        The cv2 wheel path below already had this asymmetry right.

        Uses state.mouse for the pointer position rather than trying to
        convert the NSEvent's own window-relative location -- state.mouse
        is already kept current by cv2's own MOUSEMOVE callback, in exactly
        the coordinate space wants_scroll()/sidebar.contains() expect.
        """
        mx, my = state.mouse
        vx, vy = mx - video_x, my - video_y
        if settings_panel.wants_scroll(vx, vy):
            settings_panel.scroll_by(int(round(-dy * 2)))
            return True
        if sidebar.contains(mx, my):
            px = dy * 2
            if 0 < abs(px) < 1:
                px = 1.0 if px > 0 else -1.0
            sidebar.scroll_by(state, int(round(px)))
            return True
        return False

    install_scroll_monitor(on_scroll)

    def prewarm_settings_card():
        """Record the Settings card's ~50 button stamps now, while the
        window is still coming up: the first open used to stall ~70 ms
        doing it under the operator's click."""
        was = (settings_panel.visible, settings_panel._anim)
        settings_panel.visible, settings_panel._anim = True, 1.0
        try:
            settings_panel.draw(np.zeros((frame_h, frame_w, 3), np.uint8))
        except Exception as e:
            print(f"[warn] settings pre-draw failed: {e}")
        finally:
            settings_panel.visible, settings_panel._anim = was
            settings_panel.buttons = []

    prewarm_settings_card()

    last_status = None
    last_vision_note = ""
    frame_count = 0
    wallpaper_base = None
    wallpaper_sprites = None
    wallpaper_size = None
    wash = None
    wash_have = None
    canvas = None
    cam_have = None
    base = None
    base_grid_have = None
    startup_t = time.time()
    last_draw = 0.0

    while True:
        try:
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
        except cv2.error:
            break

        keys = []
        seen = pump_events(keys)
        # Draw when there is something new to show: input the operator is
        # waiting on (at once), a new camera frame (capped at REFRESH_RATE),
        # or -- so the sim dot, panels, caret and spinners keep moving even
        # with no camera -- every IDLE_REDRAW_S. The wait in between is
        # spent inside pump_events, which a click ends immediately; the old
        # time.sleep held a click until the sleep ran out.
        while not keys and not (seen & URGENT_EVENT_TYPES):
            now = time.perf_counter()
            cap = 1.0 / REFRESH_RATE if REFRESH_RATE > 0 else 0.0
            idle = max(cap, IDLE_REDRAW_S)
            fresh_cam = (cam_have is None
                         or cam_mgr.latest()[1] != cam_have[0])
            due = last_draw + (cap if fresh_cam else idle)
            if now >= due:
                break
            seen |= pump_events(keys, min(EVENT_WAIT_SLICE_S, due - now))
        last_draw = time.perf_counter()
        if any(process_key(k, m) == "quit" for k, m in keys):
            break

        raw, seq = cam_mgr.latest()
        if raw is None:
            print("[warn] frame grab failed, retrying...")
            time.sleep(0.05)
            continue

        new_win = window_size((win_w, win_h))
        if new_win != (win_w, win_h):
            win_w, win_h = new_win
            side_w = max(SIDEBAR_W, min(560, win_w // 5))
            avail_w = max(320, win_w - 3 * SIDE_PAD - side_w)
            avail_h = max(240, win_h - TOP_BAR_H)
            frame_w = frame_h = -1

        # Each camera frame is adjusted, fitted and handed to the tag
        # tracker and to vision ONCE. The window redraws up to twice per
        # camera frame (60 vs 30 fps) and used to redo all of it -- copies,
        # resize, blur and grid -- every time.
        cs = cam_mgr.settings
        cam_key = (seq, avail_w, avail_h, cs.zoom, cs.brightness, cs.contrast,
                   cs.saturation, cs.sharpness, cs.rotation, cs.mirror)
        fresh = cam_key != cam_have or state.board_raw is None
        if fresh:
            full = cs.apply(raw)
            fitted = fit_frame(full, avail_w, avail_h)
            if fitted is full:
                fitted = full.copy()
            state.board_full = full
            state.board_raw = fitted
            cam_have = cam_key
            fh_, fw_ = fitted.shape[:2]
            if (fw_, fh_) != (frame_w, frame_h):
                relayout(fw_, fh_)
                wash_have = None
            tracker.submit(fitted)
        h, w = state.board_raw.shape[:2]

        found, ids = tracker.latest((h, w))
        tag_col_idx = tag_row_idx = None
        tag_mark = None
        seen = ids is not None and len(ids) > 0
        if seen:
            pts = found[0].reshape(4, 2)
            state.tag_raw_pts = pts.copy()
            cx, cy = detector.tag_center(found[0])
            state.tag_raw_px = (cx, cy)
            ocx, ocy = correct_tag_position(cx, cy, grid)
            if (ocx, ocy) != (cx, cy):
                pts = pts + np.array([ocx - cx, ocy - cy], dtype=np.float32)
            cx, cy = ocx, ocy
            state._tag_hold_px = (cx, cy)
            state._tag_hold_pts = pts
            state._tag_hold_until = time.time() + TAG_HOLD_SECONDS
            state.tag_visible = True
            tag_mark = "seen"
        elif state._tag_hold_px is not None and time.time() < state._tag_hold_until:
            cx, cy = state._tag_hold_px
            pts = state._tag_hold_pts
            state.tag_visible = True
            tag_mark = "held"
        else:
            state.tag_visible = False
            state.tag_raw_pts = None
            pts = None
        state.tag_on_grid = False
        state.tag_centered = False
        state.tag_px = (cx, cy) if state.tag_visible else None
        if state.tag_visible:
            state.tag_on_grid = grid.contains_pixel(cx, cy)
            clamped_col, clamped_row = grid.pixel_to_cell(cx, cy)
            state.last_tag_col, state.last_tag_row = clamped_col, clamped_row
            if state.tag_on_grid:
                tag_col_idx, tag_row_idx = clamped_col, clamped_row
                if pts is not None:
                    state.tag_centered = tag_cell_centering(
                        pts, grid, clamped_col, clamped_row)
        if state.target_col is not None:
            tcx0, tcy0, tcx1, tcy1 = grid.cell_rect(state.target_col, state.target_row)
            state.target_cell_center_px = ((tcx0 + tcx1) / 2.0, (tcy0 + tcy1) / 2.0)
        else:
            state.target_cell_center_px = None
        update_guidance(state)

        if fresh:
            full = state.board_full
            fsx = full.shape[1] / float(w)
            fsy = full.shape[0] / float(h)
            vision.submit(full, (grid.box[0] * fsx, grid.box[1] * fsy,
                                 grid.box[2] * fsx, grid.box[3] * fsy),
                          None if state.tag_raw_pts is None
                          else state.tag_raw_pts * np.float32([fsx, fsy]),
                          region=reachable_box(grid.box, fsx, fsy))

        grid_key = (tuple(grid.box), CONFIG.n_cols, CONFIG.n_rows,
                    frozenset(unreachable_rows() | fixed_unreachable_rows()),
                    frozenset(unreachable_cols()), settings_panel.edit_corners)
        if fresh or base is None or grid_key != base_grid_have:
            base = state.board_raw.copy()
            grid.draw(base, show_corners=settings_panel.edit_corners)
            base_grid_have = grid_key
            state.board_view = base
        frame = base.copy()

        if tag_mark == "seen":
            cv2.aruco.drawDetectedMarkers(frame, found, ids)
            cv2.circle(frame, (int(cx), int(cy)), 7, C_ACCENT, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(cx), int(cy)), 7, _bgr("#ffffff"), 2, cv2.LINE_AA)
        elif tag_mark == "held":
            cv2.circle(frame, (int(cx), int(cy)), 7, C_AMBER, 2, cv2.LINE_AA)

        if tag_col_idx is not None:
            grid.highlight_cell(frame, tag_col_idx, tag_row_idx, C_BLUE)

        if state.target_col is not None:
            grid.highlight_cell(frame, state.target_col, state.target_row, C_GREEN)
            if (tag_col_idx == state.target_col and tag_row_idx == state.target_row
                    and not state.tag_centered):
                tcx0, tcy0, tcx1, tcy1 = grid.cell_rect(state.target_col,
                                                        state.target_row)
                ccx, ccy = int((tcx0 + tcx1) / 2), int((tcy0 + tcy1) / 2)
                cv2.drawMarker(frame, (ccx, ccy), C_AMBER,
                              cv2.MARKER_CROSS, 16, 2, cv2.LINE_AA)
                cv2.line(frame, (int(cx), int(cy)), (ccx, ccy), C_AMBER, 1,
                        cv2.LINE_AA)

        if state.show_objects:
            view = vision.view()
            if view is not None:
                draw_live_vision(frame, view, vision.namer.names,
                                 vision.namer.info,
                                 w / float(view["frame"].shape[1]))
            if state.ai_objects:
                draw_object_overlays(frame, grid, state.ai_objects,
                                     selected=state.selected_part,
                                     outlines=False)
        vision_note = vision.failed or vision.namer.current_message()
        if vision_note and vision_note != last_vision_note:
            state.status_message = vision_note
        last_vision_note = vision_note

        pump_vision_outlines()
        collect_vision_result()
        pump_questions()
        if state.ai_job is not None and state.ai_job.done:
            collect_ai_result()
        collect_err_result()
        collect_step_err_result()
        tick_step_fail()
        if (ERR_AUTO == "task" and runner.finished and state.err_ready
                and not state.auto_check_done and state.err_job is None):
            # "After the task": the plan just ran to its end -- check it once.
            state.auto_check_done = True
            launch_err_check()
        collect_transcript()
        if MIC.active and MIC.elapsed() > STT_MAX_SECONDS:
            toggle_voice(state)
        ARDUINO.maybe_reconnect()
        port_panel.maybe_rescan()
        console_panel.pump()
        sim.tick(state)
        finish_simulation()
        runner.tick(state)
        gripper_panel.tick()
        simple_gripper.tick()

        if sim.active:
            grid.highlight_cell(frame, sim.target_col, sim.target_row,
                                sim.colour)
        draw_sim_overlay(frame, grid, sim)
        draw_guidance_banner(frame, state)
        state.popup_close_rect = None
        if sim.active and sim.popup:
            state.popup_close_rect = draw_sim_popup(frame, sim.popup)
            state.exec_cancel_rect = None
        elif (state.exec_pending and not state.exec_cancelled
              and not sim.active and not runner.active):
            # Monotonic: the wall clock can step by seconds and start the
            # robot before the countdown the operator sees has run out.
            remaining = state.exec_auto_at - time.monotonic()
            if remaining <= 0:
                start_execution()
                state.exec_cancel_rect = None
            else:
                state.exec_cancel_rect = draw_exec_countdown_popup(
                    frame, remaining)
                state.popup_close_rect = countdown_cross_rect(frame, remaining)
        else:
            state.exec_cancel_rect = None

        state.missing_popup_done_rect = None
        state.missing_popup_cancel_rect = None
        if state.missing_popup is not None:
            (state.missing_popup_done_rect,
             state.missing_popup_cancel_rect) = draw_missing_popup(
                frame, state.missing_popup["names"])

        state.step_fail_continue_rect = state.step_fail_replan_rect = None
        if state.step_fail is not None and runner.active:
            fail = state.step_fail
            left = (None if fail["deadline"] is None
                    else fail["deadline"] - time.monotonic())
            (state.step_fail_continue_rect,
             state.step_fail_replan_rect) = draw_step_fail_popup(frame, fail, left)

        mx, my = state.mouse
        settings_panel.draw(frame, (mx - video_x, my - video_y))
        trig_panel.draw(frame, grid, (mx - video_x, my - video_y))
        port_panel.draw(frame, (mx - video_x, my - video_y))
        console_panel.draw(frame, (mx - video_x, my - video_y))
        manual_move_panel.draw(frame, (mx - video_x, my - video_y))
        gripper_panel.draw(frame, (mx - video_x, my - video_y))
        gripper_panel.draw_lists(frame, (mx - video_x, my - video_y))
        simple_gripper.draw(frame, (mx - video_x, my - video_y))
        manual_move_panel.draw_lists(frame, (mx - video_x, my - video_y))
        trig_panel.draw_lists(frame, (mx - video_x, my - video_y))
        settings_panel.draw_lists(frame, (mx - video_x, my - video_y))

        # The window's background is built once per layout, with the
        # sidebar's frosted card already on it. It used to be repainted 20
        # times a second (a hue cycle) and on every mouse move (parallax),
        # and every repaint forced the whole canvas -- and every translucent
        # panel on it -- to be composed again: frames the operator felt as
        # lag between a click and its result.
        wash_key = (total_w, total_h, video_x, video_y, w, h,
                    sidebar.x0, sidebar.y0, sidebar.width, sidebar.height)
        if wash is None or wash_key != wash_have:
            if (wallpaper_base is None or wallpaper_size != (total_w, total_h)):
                wallpaper_base, wallpaper_sprites = build_wallpaper_base(
                    total_w, total_h)
                wallpaper_size = (total_w, total_h)
            wash = paint_wallpaper(wallpaper_base, wallpaper_sprites,
                                   total_w, total_h, None, hue_shift=0.0)
            drop_shadow(wash, (video_x, video_y, video_x + w, video_y + h),
                        22, spread=14, strength=0.18)
            drop_shadow(wash, (sidebar.x0, sidebar.y0,
                               sidebar.x0 + sidebar.width,
                               sidebar.y0 + sidebar.height),
                        22, spread=14, strength=0.16)
            sidebar.paint_card(wash)
            wash_have = wash_key
            canvas = None
        if canvas is None or canvas.shape != wash.shape:
            canvas = wash.copy()
        else:
            np.copyto(canvas, wash)

        video_rect = (video_x, video_y, video_x + w, video_y + h)
        canvas[video_y:video_y + h, video_x:video_x + w] = frame
        round_video_corners(canvas, wash, video_x, video_y, w, h)
        rounded_rect(canvas, video_rect, 22, C_BORDER, 1)

        camera_dd.draw(canvas, f"Cam {cam_mgr.current_index()}",
                       hover=camera_dd.contains(mx, my))
        settings_button.draw(canvas, hover=settings_button.contains(mx, my))
        draw_text(canvas, f"{CONFIG.n_cols}x{CONFIG.n_rows} grid   "
                          f"Vision AI: {vision.status()}",
                  (206, 34), 0.44, C_TEXT_DIM, 1)

        typed = f"{state.typed_col or '--'}{state.typed_row if state.typed_row else ''}"
        chip_w = max(96, text_size(typed, 0.5, 2)[0] + 60)
        chip = (total_w - 160 - chip_w, 12, total_w - 156, 44)
        rounded_rect(canvas, chip, 16, C_ACCENT_SO, -1)
        draw_text(canvas, "Target", (chip[0] + 16, 33), 0.42, C_ACCENT, 1)
        draw_text(canvas, typed, (chip[0] + 74, 33), 0.5, C_ACCENT, 2)

        sidebar.draw(canvas, state, runner, sim, (mx, my), shadow=False,
                     card=False)

        if DEBUG_INPUT and state.status_message != last_status:
            last_status = state.status_message
            print(f"[status] {last_status}", flush=True)

        status_y = total_h - 12
        draw_text(canvas, state.status_message, (28, status_y), 0.44,
                  C_TEXT_DIM, 1)

        camera_dd.draw_list(canvas, cam_mgr.current_index(), (mx, my))

        frame_count += 1
        if DEBUG_INPUT and (frame_count == 5 or frame_count % 120 == 0):
            print(f"[layout] canvas={total_w}x{total_h} "
                  f"settings={settings_button.x0},{settings_button.y0},"
                  f"{settings_button.x1},{settings_button.y1}", flush=True)
        cv2.imshow(WINDOW_NAME, canvas)
        if time.time() - startup_t < 5.0:
            cv2.setMouseCallback(WINDOW_NAME, on_mouse)
            if sys.platform == "darwin" and NSApplication is not None:
                try:
                    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                except Exception as e:
                    print(f"[warn] could not re-activate the app: {e}")

    ARDUINO.send_direction(None)
    ARDUINO.disconnect()
    tracker.stop()
    vision.stop()
    cam_mgr.release()
    flush_embedded_state()
    cv2.destroyAllWindows()


def vision_source(state: AppState, grid: Grid):
    """(frame, grid) for the Error Rebounds photos -- the sharpest frame
    available.

    The camera shoots well above what the window shows, and the display frame
    is that shot scaled down. The photos use the original instead, with the
    board box scaled up to match it, so a small object is a few hundred
    pixels rather than a few dozen. Grid units come back the same either way,
    which is what makes the swap free.

    The returned grid is a snapshot: the operator is free to drag a corner
    while a request is in flight.
    """
    fitted = state.board_raw if state.board_raw is not None else state.board_view
    full = state.board_full
    if fitted is None and full is None:
        return None, grid
    if full is None or fitted is None:
        frame = fitted if fitted is not None else full
        return frame, Grid(grid.frame_width, grid.frame_height, list(grid.box),
                           square_cells=grid.square_cells)
    fh, fw = fitted.shape[:2]
    uh, uw = full.shape[:2]
    if (uw, uh) == (fw, fh) or fw <= 0 or fh <= 0:
        return fitted, Grid(grid.frame_width, grid.frame_height, list(grid.box),
                            square_cells=grid.square_cells)
    sx, sy = uw / float(fw), uh / float(fh)
    box = [grid.box[0] * sx, grid.box[1] * sy, grid.box[2] * sx, grid.box[3] * sy]
    return full, Grid(uw, uh, box, square_cells=grid.square_cells)


def handle_go(state: AppState):
    if state.typed_col is None or state.typed_row is None:
        state.status_message = "Pick a column letter and a row number first."
        return
    coord = parse_coordinate(f"{state.typed_col}{state.typed_row}")
    if coord is None:
        state.status_message = "Invalid coordinate."
        return
    target_col, target_row = coord

    if state.last_tag_col is None:
        state.status_message = "No AprilTag detected yet -- show the tag to the camera first."
        return

    state.target_col, state.target_row = target_col, target_row
    state.arrived = False
    print(f"\n[guide] Target: {coordinate_name(target_col, target_row)}")
    update_guidance(state)


def update_guidance(state: AppState):
    """Re-derive the directions from where the tag is *now*.

    Called every frame: the guidance is not a route handed out once at GO
    time but a live readout of what is still left to do, so moving the tag
    (or being pushed off course) immediately changes what it says. "Arrived"
    is only ever shown when the tag is actually sitting on the target.
    """
    state.out_of_reach = False
    if automatic_gripper_busy():
        return
    if state.target_col is None:
        ARDUINO.send_direction(None)
        return
    if state.action_label is not None:
        ARDUINO.send_direction(None)
        return

    target_name = coordinate_name(state.target_col, state.target_row)
    stop_col, stop_row = tag_cell_for(state.target_col, state.target_row)
    off_c, off_r = gripper_offset()
    if (off_c or off_r) and not (0 <= stop_col < CONFIG.n_cols
                                 and 0 <= stop_row < CONFIG.n_rows):
        state.guide_dir, state.guide_steps, state.guide_line = None, 0, ""
        state.guide_slow = False
        state.arrived = False
        state.out_of_reach = True
        state.status_message = (
            f"{target_name} is out of reach with a {gripper_offset_label()} "
            f"gripper offset -- the tag would have to leave the board.")
        ARDUINO.send_direction(None)
        return

    if state.last_tag_col is None:
        state.guide_dir, state.guide_steps, state.guide_line = None, 0, ""
        state.guide_slow = False
        state.arrived = False
        state.status_message = f"-> {target_name}: show the AprilTag to the camera."
        ARDUINO.send_direction(None)
        return

    moves = build_path_commands(state.last_tag_col, state.last_tag_row,
                                stop_col, stop_row)
    here = cell_label(*gripper_cell(state.last_tag_col, state.last_tag_row))
    off_note = ("" if not (off_c or off_r) else
                f"  (tag -> {cell_label(stop_col, stop_row)})")
    stale = "" if state.tag_visible else "  (tag lost -- last seen here)"
    off_grid = state.tag_visible and not state.tag_on_grid

    if not moves:
        state.guide_dir, state.guide_steps, state.guide_line = None, 0, ""
        state.guide_slow = False
        in_cell = bool(state.tag_visible) and state.tag_on_grid
        state.arrived = in_cell
        if state.arrived:
            state.status_message = f"Arrived at {target_name}."
        elif off_grid:
            state.status_message = (f"{target_name}: tag seen just off the "
                                    f"grid -- move it onto the board.")
        else:
            state.status_message = f"At {target_name}{stale}"
    else:
        state.arrived = False
        state.guide_dir = moves[0]
        state.guide_steps = sum(1 for m in moves if m == state.guide_dir)
        state.guide_line = condense_commands(moves)
        state.guide_slow = len(moves) <= SLOW_APPROACH_CELLS
        lead = "Tag off the grid" if off_grid else here
        slow_note = "  (slowing in)" if state.guide_slow else ""
        state.status_message = (f"{lead} -> {target_name}: "
                                f"{state.guide_line}{stale}{slow_note}"
                                f"{off_note}")

    ARDUINO.send_direction(state.guide_dir, slow=state.guide_slow)

    if state.status_message != _LAST_SPOKEN.get("msg"):
        _LAST_SPOKEN["msg"] = state.status_message
        print(f"[guide] {state.status_message}")


_LAST_SPOKEN = {}


ARROWS = {"up": "^", "down": "v", "left": "<", "right": ">"}


OBJECT_COLOURS = [_bgr(c) for c in ("#0ea5e9", "#f97316", "#ec4899",
                                    "#22c55e", "#a855f7", "#eab308",
                                    "#14b8a6", "#ef4444")]


def _draw_poly_shape(frame, grid: Grid, poly, colour, alpha=0.16, thickness=3):
    """A many-sided outline, filled and stroked -- the real silhouette vision
    reported, not a union of grid squares.

    Blended on the outline's OWN bounding box, the same way rounded_rect
    does it. A full-frame copy and a full-frame blend per polygon -- and
    there are two per object once its parts are counted -- was measurably
    the most expensive thing on this canvas, well ahead of everything else
    put together.
    """
    pts = np.array([grid.grid_to_pixel(cf, rf) for cf, rf in poly], np.int32)
    if len(pts) < 3:
        return
    h, w = frame.shape[:2]
    x0 = max(0, int(pts[:, 0].min()))
    x1 = min(w, int(pts[:, 0].max()) + 1)
    y0 = max(0, int(pts[:, 1].min()))
    y1 = min(h, int(pts[:, 1].max()) + 1)
    if x1 > x0 and y1 > y0:
        region = frame[y0:y1, x0:x1]
        overlay = region.copy()
        cv2.fillPoly(overlay, [pts - (x0, y0)], colour)
        frame[y0:y1, x0:x1] = cv2.addWeighted(overlay, alpha, region,
                                              1 - alpha, 0)
    cv2.polylines(frame, [pts], True, colour, thickness, cv2.LINE_AA)


def _stamp_small(frame, text, x, y, colour):
    """A part's name, small, with a dark halo so it reads over the video."""
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                colour, 1, cv2.LINE_AA)


def part_at_point(grid: Grid, objects, px, py):
    """(object index, component index) under a pixel, or None.

    Parts are tested before whole objects, and smaller parts before bigger
    ones, so clicking a knife's blade selects the blade and not the knife.
    """
    col_f, row_f = grid.pixel_to_grid(px, py)
    hits = []
    for i, o in enumerate(objects):
        for ci, comp in enumerate(o.get("components") or []):
            cpoly = comp.get("polygon")
            if cpoly and _point_in_poly(col_f, row_f, cpoly):
                hits.append((abs(_poly_area(cpoly)), i, ci))
    if hits:
        hits.sort()
        return hits[0][1], hits[0][2]
    for i, o in enumerate(objects):
        poly = o.get("polygon")
        if poly and _point_in_poly(col_f, row_f, poly):
            return i, None
    return None


def draw_object_overlays(frame, grid: Grid, objects, show_names=True,
                         selected=None, outlines=True):
    """Outline what vision reported: its actual polygon silhouette where one
    was given, its parts, and its centre.

    With `outlines` off -- Vision AI is drawing the live outlines and names
    already -- only what the plan was made from is marked: each object's
    centre, its parts' spots, and the part clicked on.

    Drawn after the board snapshot is taken, so none of it is ever fed back
    to the model as if it were part of the scene.
    """
    for i, o in enumerate(objects):
        colour = OBJECT_COLOURS[i % len(OBJECT_COLOURS)]
        poly = o.get("polygon")

        cells = []
        for name in str(o.get("touches") or "").split(","):
            cell = parse_coordinate(name.strip())
            if cell is not None:
                cells.append(cell)
        if not cells and not poly:
            continue
        owned = set(cells)

        if not outlines:
            pass
        elif poly:
            _draw_poly_shape(frame, grid, poly, colour)
        else:
            for col, row in cells:
                rounded_rect(frame, grid.cell_rect(col, row), 0, colour, -1,
                             alpha=0.16)
            for col, row in cells:
                x0, y0, x1, y1 = (int(v) for v in grid.cell_rect(col, row))
                if (col, row - 1) not in owned:
                    cv2.line(frame, (x0, y0), (x1, y0), colour, 3, cv2.LINE_AA)
                if (col, row + 1) not in owned:
                    cv2.line(frame, (x0, y1), (x1, y1), colour, 3, cv2.LINE_AA)
                if (col - 1, row) not in owned:
                    cv2.line(frame, (x0, y0), (x0, y1), colour, 3, cv2.LINE_AA)
                if (col + 1, row) not in owned:
                    cv2.line(frame, (x1, y0), (x1, y1), colour, 3, cv2.LINE_AA)

        centre = parse_coordinate(str(o.get("center") or ""))
        if centre is not None:
            pt = o.get("center_pt")
            if pt:
                cx, cy = (int(v) for v in grid.grid_to_pixel(pt[0], pt[1]))
            else:
                cx, cy = (int(v) for v in grid.cell_to_pixel_center(*centre))
            cv2.circle(frame, (cx, cy), 5, colour, -1, cv2.LINE_AA)
            cv2.circle(frame, (cx, cy), 5, _bgr("#ffffff"), 1, cv2.LINE_AA)

        comps = o.get("components") or []
        if not comps and poly and garment_family(o) == "flat":
            comps = cloth_corner_components(o)
        for ci, comp in enumerate(comps):
            picked = (selected is not None and selected == (i, ci))
            cpoly = comp.get("polygon")
            grip = str(comp.get("grip") or "").lower()
            tint = (C_RED if grip == "avoid" else
                    C_GREEN if grip == "hold" else colour)
            if cpoly and (outlines or picked):
                _draw_poly_shape(frame, grid, cpoly, tint,
                                 alpha=0.24 if picked else 0.12,
                                 thickness=3 if picked else 2)
                if show_names:
                    xs = [p[0] for p in cpoly]; ys = [p[1] for p in cpoly]
                    if (max(xs) - min(xs) > 0.45 or max(ys) - min(ys) > 0.45
                            or picked):
                        lx, ly = grid.grid_to_pixel(min(xs), min(ys))
                        _stamp_small(frame, str(comp.get("name", "part")),
                                     int(lx) + 3, int(ly) - 3, tint)
                continue
            spot = parse_coordinate(str(comp.get("center") or ""))
            if spot is None or spot == centre:
                continue
            cpt = comp.get("center_pt")
            if cpt:
                px, py = (int(v) for v in grid.grid_to_pixel(cpt[0], cpt[1]))
            else:
                px, py = (int(v) for v in grid.cell_to_pixel_center(*spot))
            cv2.circle(frame, (px, py), 6, tint, 2, cv2.LINE_AA)

        if not show_names or not outlines:
            continue
        if poly:
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            lx, ly = grid.grid_to_pixel(min(xs), min(ys))
            lx, ly = int(lx), int(ly)
        else:
            top = min(cells, key=lambda c: (c[1], c[0]))
            lx, ly = (int(v) for v in grid.cell_rect(*top)[:2])
        label = str(o.get("name") or "object")
        tw, th = text_size(label, 0.42, 1)
        chip = (lx + 2, ly - th - 12, lx + tw + 18, ly - 2)
        rounded_rect(frame, chip, 8, colour, -1, alpha=0.88)
        draw_text(frame, label, (lx + 10, ly - 8), 0.42, _bgr("#ffffff"), 1)


def draw_guidance_banner(frame, state: AppState):
    """A big live cue over the video: which way, and how many cells."""
    if state.action_label is not None:
        label, colour = state.action_label
    elif state.target_col is None:
        return
    elif state.out_of_reach:
        label, colour = "OUT OF REACH", C_AMBER
    elif state.arrived:
        label, colour = "ARRIVED", C_GREEN
    elif state.guide_dir:
        label = (f"{ARROWS[state.guide_dir]}  {state.guide_dir.upper()} "
                 f"x{state.guide_steps}")
        if state.guide_slow:
            label += "  SLOW"
        colour = C_AMBER if state.guide_slow else C_ACCENT
    elif state.tag_visible and state.tag_on_grid:
        label, colour = "CENTER TAG", C_AMBER
    elif state.last_tag_col is None:
        label, colour = "SHOW THE TAG", C_TEXT_DIM
    else:
        label, colour = "TAG LOST", C_TEXT_DIM

    fw = frame.shape[1]
    tw = text_size(label, 1.1, 3)[0]
    bw = tw + 72
    rect = ((fw - bw) // 2, 18, (fw + bw) // 2, 88)
    glass_card(frame, rect, 35, alpha=0.55)
    rounded_rect(frame, rect, 35, colour, 2)
    draw_text_centred(frame, label, rect, 1.1, colour, 3)


def draw_sim_overlay(frame, grid: Grid, sim):
    """The rehearsal on the board: trail, glowing dot, and what it is doing.

    S1-SRC's GridOverlay, painted with this app's own primitives. The dot
    is deliberately nothing like the AprilTag marker the real run draws --
    a rehearsal must never be mistakable for the thing itself.
    """
    if not sim.active:
        return
    fh, fw = frame.shape[:2]
    colour = sim.colour
    r = max(6.0, min(grid.cell_w, grid.cell_h) * 0.42)

    if len(sim.trail) > 1:
        overlay = frame.copy()
        n = len(sim.trail)
        for i in range(n - 1):
            p0 = grid.grid_to_pixel(sim.trail[i][0] + 0.5, sim.trail[i][1] + 0.5)
            p1 = grid.grid_to_pixel(sim.trail[i + 1][0] + 0.5,
                                    sim.trail[i + 1][1] + 0.5)
            thick = max(1, int(round(1 + 3.0 * (i / float(n)))))
            cv2.line(overlay, (int(p0[0]), int(p0[1])),
                     (int(p1[0]), int(p1[1])), colour, thick, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    px, py = grid.grid_to_pixel(sim.col + 0.5, sim.row + 0.5)
    px, py = int(round(px)), int(round(py))
    pulse = math.sin(sim.pulse)

    glow = frame.copy()
    for k in range(4, 0, -1):
        cv2.circle(glow, (px, py), int(r * (0.9 + 0.32 * k * (1.0 + 0.18 * pulse))),
                   colour, -1, cv2.LINE_AA)
    cv2.addWeighted(glow, 0.18, frame, 0.82, 0, frame)

    cv2.circle(frame, (px, py), int(r), colour, -1, cv2.LINE_AA)
    cv2.circle(frame, (px, py), int(r), _bgr("#ffffff"), 2, cv2.LINE_AA)
    cv2.circle(frame, (int(px - r * 0.18), int(py - r * 0.18)),
               max(2, int(r * 0.38)), _bgr("#ffffff"), -1, cv2.LINE_AA)

    if sim.cell:
        w, _ = text_size(sim.cell, 0.5, 2)
        draw_text(frame, sim.cell, (px - w // 2, int(py + r) + 22), 0.5,
                  _bgr("#ffffff"), 3)
        draw_text(frame, sim.cell, (px - w // 2, int(py + r) + 22), 0.5,
                  colour, 1)

    label = sim.label or "Simulating..."
    label = f"SIMULATION  -  {label}"
    if SIM_SPEED != 1.0:
        label += f"   -   {SIM_SPEED:g}x"
    tw = text_size(label, 0.6, 2)[0]
    bw = tw + 60
    rect = ((fw - bw) // 2, fh - 82, (fw + bw) // 2, fh - 30)
    glass_card(frame, rect, 26, alpha=0.55)
    rounded_rect(frame, rect, 26, colour, 2)
    draw_text_centred(frame, label, rect, 0.6, colour, 2)


def popup_cross(frame, rect):
    x0, y0, x1, y1 = rect
    button = Button("X", x1 - 42, y0 + 8, x1 - 10, y0 + 40,
                    "popup_close", scale=0.46)
    button.draw(frame, shadow=False)
    return (button.x0, button.y0, button.x1, button.y1)


def countdown_cross_rect(frame, seconds_left):
    text = f"Executing physically in {max(0, math.ceil(seconds_left))}s..."
    fh, fw = frame.shape[:2]
    bw = max(text_size(text, 0.8, 2)[0] + 96, 320)
    return ((fw + bw) // 2 - 42, (fh - 150) // 2 + 8,
            (fw + bw) // 2 - 10, (fh - 150) // 2 + 40)


def draw_sim_popup(frame, text: str):
    """S1-SRC's centred pop-up -- the unstacker stages, and the hand-off."""
    if not text:
        return
    fh, fw = frame.shape[:2]
    tw = text_size(text, 0.86, 2)[0]
    bw, bh = tw + 96, 104
    rect = ((fw - bw) // 2, (fh - bh) // 2, (fw + bw) // 2, (fh + bh) // 2)
    drop_shadow(frame, rect, 26, spread=14, strength=0.22)
    glass_card(frame, rect, 26, alpha=0.75)
    rounded_rect(frame, rect, 26, C_ACCENT, 2)
    draw_text_centred(frame, text, rect, 0.86, C_TEXT, 2)
    return popup_cross(frame, rect)


def draw_exec_countdown_popup(frame, seconds_left: float) -> tuple:
    """The hand-off popup, with a live countdown and a way to stop it.

    Physical execution starts on its own when the countdown reaches zero --
    CANCEL (or Esc) is the only thing standing in its way. Returns the
    CANCEL button's rect, in this frame's own pixels, for the caller to
    hit-test in on_mouse the same way every other panel here does.
    """
    secs = max(0, math.ceil(seconds_left))
    text = f"Executing physically in {secs}s..."
    fh, fw = frame.shape[:2]
    tw = text_size(text, 0.8, 2)[0]
    bw, bh = max(tw + 96, 320), 150
    rect = ((fw - bw) // 2, (fh - bh) // 2, (fw + bw) // 2, (fh + bh) // 2)
    x0, y0, x1, y1 = rect
    drop_shadow(frame, rect, 26, spread=14, strength=0.22)
    glass_card(frame, rect, 26, alpha=0.75)
    rounded_rect(frame, rect, 26, C_ACCENT, 2)
    draw_text_centred(frame, text, (x0, y0 + 14, x1, y0 + 74), 0.8, C_TEXT, 2)
    btn_w = 150
    cancel_btn = Button("CANCEL", x0 + (bw - btn_w) // 2, y1 - 60,
                        x0 + (bw - btn_w) // 2 + btn_w, y1 - 20, "cancel_exec")
    cancel_btn.draw(frame, shadow=False)
    popup_cross(frame, rect)
    return (cancel_btn.x0, cancel_btn.y0, cancel_btn.x1, cancel_btn.y1)


def draw_step_fail_popup(frame, fail, seconds_left) -> tuple:
    """A step failed its check mid-run: CONTINUE ANYWAY or REPLAN. The
    default one (accent) happens on its own when `seconds_left` runs out;
    None means no countdown -- wait for a click. Returns (continue_rect,
    replan_rect) in this frame's own pixels."""
    replan_first = fail.get("default") == "replan"
    title = fail.get("title") or "A step went wrong"
    fh, fw = frame.shape[:2]
    bw = min(max(540, text_size(title, 0.78, 2)[0] + 96), fw - 32)
    lines = wrap_text(fail.get("reason") or "No reason given.", bw - 72, 0.52)[:3]
    if seconds_left is None:
        foot = "Choose how to go on."
    else:
        secs = max(0, math.ceil(seconds_left))
        foot = (f"Replanning from this step in {secs}s..." if replan_first
                else f"Carrying on in {secs}s...")
    bh = 60 + 26 * len(lines) + 40 + 64
    rect = ((fw - bw) // 2, (fh - bh) // 2, (fw + bw) // 2, (fh + bh) // 2)
    x0, y0, x1, y1 = rect
    drop_shadow(frame, rect, 26, spread=14, strength=0.22)
    glass_card(frame, rect, 26, alpha=0.78)
    rounded_rect(frame, rect, 26, C_RED if replan_first else C_AMBER, 2)
    draw_text_centred(frame, title, (x0, y0 + 14, x1, y0 + 56), 0.78, C_TEXT, 2)
    y = y0 + 58
    for line in lines:
        draw_text_centred(frame, line, (x0 + 28, y, x1 - 28, y + 26), 0.52,
                          C_TEXT_DIM, 1)
        y += 26
    draw_text_centred(frame, foot, (x0, y + 6, x1, y + 36), 0.56, C_TEXT, 1)
    btn_w = (bw - 64 - 16) // 2
    by0, by1 = y1 - 62, y1 - 18
    cont = Button("Continue anyway", x0 + 32, by0, x0 + 32 + btn_w, by1,
                  "step_fail_continue",
                  style="ghost" if replan_first else "accent", scale=0.56)
    repl = Button("Replan", x1 - 32 - btn_w, by0, x1 - 32, by1,
                  "step_fail_replan",
                  style="accent" if replan_first else "ghost", scale=0.56)
    cont.draw(frame, shadow=False)
    repl.draw(frame, shadow=False)
    return ((cont.x0, cont.y0, cont.x1, cont.y1),
            (repl.x0, repl.y0, repl.x1, repl.y1))


def draw_missing_popup(frame, names) -> tuple:
    """The whole task was blocked for want of an object -- offer to add it
    and try again, rather than just erroring out. Returns
    (done_rect, cancel_rect) in this frame's own pixels, for on_mouse to
    hit-test the same way every other panel here does.

    DONE is the big, primary action (add the object, then restart the same
    task from scratch); CANCEL is a small X cross, not a text button, so it
    is never mistaken for the expected next step.
    """
    what = ", ".join(names) if names else "the missing object"
    line1 = "Add this object"
    line2 = f"({what}), then press Done to try again."
    fh, fw = frame.shape[:2]
    tw = max(text_size(line1, 0.9, 2)[0], text_size(line2, 0.62, 1)[0])
    bw, bh = max(tw + 96, 360), 190
    rect = ((fw - bw) // 2, (fh - bh) // 2, (fw + bw) // 2, (fh + bh) // 2)
    x0, y0, x1, y1 = rect
    drop_shadow(frame, rect, 26, spread=14, strength=0.22)
    glass_card(frame, rect, 26, alpha=0.78)
    rounded_rect(frame, rect, 26, C_ACCENT, 2)
    draw_text_centred(frame, line1, (x0, y0 + 16, x1, y0 + 58), 0.9, C_TEXT, 2)
    draw_text_centred(frame, line2, (x0, y0 + 58, x1, y0 + 92), 0.62, C_TEXT, 1)
    done_w = 190
    done_btn = Button("Done", x0 + (bw - done_w) // 2, y1 - 66,
                      x0 + (bw - done_w) // 2 + done_w, y1 - 20,
                      "missing_popup_done", style="accent", scale=0.72)
    done_btn.draw(frame, shadow=False)
    cancel_rect = popup_cross(frame, rect)
    return ((done_btn.x0, done_btn.y0, done_btn.x1, done_btn.y1), cancel_rect)


def run_single_file_self_test():
    """Exercise the critical gripper/state paths without any sidecar files."""
    checks_top = 0

    def check_top(condition, message):
        nonlocal checks_top
        checks_top += 1
        if not condition:
            raise AssertionError(message)

    for a, b, c, d in [(0, 0, 100, 0), (10, 10, 10, 20), (0, 0, 1, 1),
                       (0, 0, 2, 100), (50, 0, 100, 3), (0, 97, 100, 100)]:
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        blur_band(frame, a, b, c, d)
    check_top(True, "degenerate blur_band rects did not crash")

    frame = np.random.randint(0, 255, (400, 600, 3), dtype=np.uint8).astype(np.uint8)
    before_var = frame[50:350, 50:550].astype(np.float64).var()
    blur_band(frame, 50, 50, 550, 350)
    after_var = frame[50:350, 50:550].astype(np.float64).var()
    check_top(after_var < before_var * 0.5,
              f"blur_band no longer visibly smooths its band: "
              f"{before_var:.1f} -> {after_var:.1f}")
    frame2 = np.full((400, 600, 3), 200, dtype=np.uint8)
    corner_before = frame2[0:20, 0:20].copy()
    blur_band(frame2, 50, 50, 550, 350)
    check_top(np.array_equal(frame2[0:20, 0:20], corner_before),
              "blur_band touched pixels outside its own rect")

    class _Bag:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _fake_resp(text, finish="stop", with_reason=True):
        msg = _Bag(content=text)
        choice = (_Bag(message=msg, finish_reason=finish)
                  if with_reason else _Bag(message=msg))
        return _Bag(choices=[choice])

    def _fake_client(resp):
        return _Bag(chat=_Bag(completions=_Bag(create=lambda **kw: resp)))

    truncated = '{"objects": [{"n": 1, "name": "white sock"'
    try:
        parse_naming_reply(truncated, 1)
        check_top(False, "a truncated naming reply parsed as if it were whole")
    except ValueError:
        pass
    try:
        call_model(_fake_client(_fake_resp(truncated, "length")),
                   model="x", messages=[], max_tokens=8000, stage="Naming")
        check_top(False, "a length-capped reply was accepted as a real answer")
    except ModelError as e:
        check_top("cap" in str(e).lower(),
                  f"the truncation error does not name the cap: {e}")
    check_top(call_model(_fake_client(_fake_resp('{"objects": []}')),
                         model="x", messages=[], max_tokens=10) == '{"objects": []}',
              "a normal reply stopped going through")
    check_top(call_model(_fake_client(_fake_resp("hi", with_reason=False)),
                         model="x", messages=[], max_tokens=10) == "hi",
              "a response without finish_reason raised instead of passing")

    prompt = naming_prompt(3, [None, "1", None], VISION_SCENE_HINT)
    check_top("- 2 is a part of 1" in prompt,
              "the naming prompt lost which outline is a part of which")
    for word in ('"robot"', '"loose"', '"color"', '"desc"', "gantry robot",
                 "from 1 to 3"):
        check_top(word in prompt, f"the naming prompt lost {word}")
    got = parse_naming_reply(
        'Here: {"objects": [{"n": 1, "name": "Bowl", "color": "Green", '
        '"desc": "round ceramic bowl"}, {"n": 2, "name": "sock", "loose": true}, '
        '{"n": 3, "name": "unknown"}, {"n": 9, "name": "ghost"}, {"n": "x"}, 7]}', 3)
    check_top(set(got) == {1, 2}, f"naming reply numbers wrong: {sorted(got)}")
    check_top(got[1]["name"] == "bowl" and got[1]["color"] == "green"
              and got[1]["desc"] == "round ceramic bowl" and not got[1]["robot"],
              f"naming reply fields wrong: {got[1]}")
    check_top(got[2]["loose"] is True and got[1]["loose"] is False,
              "the loose flag was not read")

    def _square(x0, y0, x1, y1):
        return [np.array([[[x0, y0]], [[x1, y0]], [[x1, y1]], [[x0, y1]]], np.int32)]

    _board = (100, 100, 900, 900)
    _kept = keep_on_board([_square(110, 110, 890, 890), _square(950, 950, 990, 990),
                           _square(300, 300, 400, 400)], _board)
    check_top(len(_kept) == 1 and object_bbox(_kept[0])[0] == 300,
              "keep_on_board kept the board itself or an object off the board")
    _tag = np.float32([[300, 300], [340, 300], [340, 340], [300, 340]])
    _left = drop_tag_objects([_square(295, 295, 345, 345), _square(305, 305, 315, 315),
                              _square(200, 200, 500, 500), _square(600, 600, 700, 700)],
                             _tag)
    check_top([object_bbox(o)[0] for o in _left] == [200, 600],
              "drop_tag_objects kept the tag, or dropped what the tag hovers over")
    _vframe = np.full((1000, 1000, 3), 200, np.uint8)
    _trk = ObjectTracker()
    _a = _trk.update([_square(200, 200, 300, 300)], [None], 1.0, _vframe)
    _b = _trk.update([_square(210, 205, 310, 305)], [None], 1.1, _vframe)
    check_top(_a == _b, "the tracker lost an object that moved 10 px")
    _c = _trk.update([_square(212, 206, 312, 306), _square(600, 600, 650, 650)],
                     [None, None], 1.2, _vframe)
    check_top(_c[0] == _a[0] and _c[1] != _a[0], "a new object took an existing ID")
    _rgb, _r, _lx, _ty = fastsam_letterbox(np.zeros((480, 960, 3), np.uint8))
    check_top(_rgb.shape == (FASTSAM_IMGSZ, FASTSAM_IMGSZ, 3) and _lx == 0
              and _ty == (FASTSAM_IMGSZ - 320) // 2
              and abs(_r - FASTSAM_IMGSZ / 960) < 1e-9, "fastsam_letterbox changed")

    _vgrid = Grid(1000, 1000, list(_board), square_cells=False)
    _vobjects = [_square(200, 200, 500, 500), _square(260, 260, 340, 340),
                 _square(400, 400, 440, 440), _square(600, 600, 700, 700),
                 _square(750, 150, 850, 250), _square(150, 700, 250, 800)]
    _vparents = find_parents(_vobjects)
    check_top(_vparents == [None, 0, 0, None, None, None],
              f"find_parents: {_vparents}")
    _vnamer = ObjectNamer()
    _vnamer.names = {11: "bowl", 12: "sock", 13: "logo", 14: "cup",
                     15: "stepper motor"}
    _vnamer.info = {
        11: {"color": "green", "desc": "round bowl", "robot": False, "loose": False},
        12: {"color": "black", "desc": "", "robot": False, "loose": True},
        13: {"color": "white", "desc": "", "robot": False, "loose": False},
        15: {"color": "silver", "desc": "", "robot": True, "loose": False}}
    _vsnap = {"frame": _vframe, "box": _board, "objects": _vobjects,
              "ids": [11, 12, 13, 14, 15, 16], "parents": _vparents}
    _vlist = planner_objects(_vsnap, _vnamer, _vgrid)
    _vby = {o["name"]: o for o in _vlist}
    check_top(set(_vby) == {"bowl", "sock", "cup", "unidentified object"},
              f"planner objects: {sorted(_vby)}")
    check_top([c["name"] for c in _vby["bowl"]["components"]] == ["logo"],
              f"bowl components: {_vby['bowl']['components']}")
    check_top("lying on/in the bowl" in _vby["sock"]["desc"],
              f"sock desc: {_vby['sock']['desc']}")
    check_top(_vby["cup"]["center"] == "N14" and _vby["cup"]["color"] == "white"
              and "name_uncertain" not in _vby["cup"],
              f"cup: {_vby['cup']}")
    check_top(_vby["unidentified object"].get("name_uncertain") is True,
              "an unnamed outline is not marked as an uncertain name")
    for _o in _vlist:
        check_top(parse_coordinate(_o["center"]) is not None
                  and _o["center"] in _touch_cells(_o)
                  and _o["size"] in ("small", "medium", "large"),
                  f"{_o['name']}: not a plannable object line: {obj_to_line(_o)}")
    check_top(len(object_list_text(_vlist).splitlines()) == 4,
              "the OBJECT LIST is not one line per object")
    check_top(_vnamer.name_now(_vframe, _vobjects, [11, 12, 13, 14, 15], _board) == "",
              "naming an already-named board did not return straight away")

    class _FakeVision:
        """Every outline already named, so no naming call is ever made."""
        failed = ""
        namer = _vnamer

        def snapshot(self, timeout=0, on_wait=None):
            return dict(_vsnap, objects=_vobjects[:5], ids=[11, 12, 13, 14, 15],
                        parents=find_parents(_vobjects[:5]))

    _job = AIJob(None, "put the sock in the cup", vision=_FakeVision())
    _jobjs = _job._read_board()
    check_top({o["name"] for o in _jobjs} >= {"bowl", "sock", "cup"},
              f"AIJob read the board as {[o['name'] for o in _jobjs]}")
    _lv = LiveVision()
    _lv.failed = "no model here"
    try:
        _lv.snapshot(timeout=0)
        check_top(False, "a snapshot from a stopped Vision AI did not raise")
    except ModelError as e:
        check_top("no model here" in str(e), f"wrong snapshot error: {e}")

    _was = (VISION_CONF, NAMER_MODEL, PRIORITY_NAMING)
    load_vision_settings({"conf_thres": 5.0, "namer_model": NAMER_MODELS[-1],
                          "priority_naming": "yes", "auto_name": True})
    check_top(VISION_CONF == _was[0] and NAMER_MODEL == NAMER_MODELS[-1]
              and PRIORITY_NAMING == _was[2],
              "an out-of-range or wrong-typed vision setting was accepted")
    load_vision_settings({"conf_thres": _was[0], "namer_model": _was[1]})

    # -- responsiveness: caches and stamps must draw what direct drawing did
    _texts = ["", "short", "a much longer line of words that has to wrap " * 3,
              "line one\nline two\n\nline four"]
    for _t in _texts:
        check_top(wrap_text(_t, 180, 0.42) == _wrap_text(_t, 180, 0.42)
                  and wrap_text(_t, 180, 0.42) == wrap_text(_t, 180, 0.42),
                  f"memoised wrap_text differs for {_t[:20]!r}")
        check_top(wrap_editable(_t, 180, 0.44) == _wrap_editable(_t, 180, 0.44),
                  f"memoised wrap_editable differs for {_t[:20]!r}")
        _slow = _t
        if text_size(_slow, 0.4, 1)[0] > 120:
            while _slow and text_size(_slow + "...", 0.4, 1)[0] > 120:
                _slow = _slow[:-1]
            _slow += "..."
        check_top(fit_text(_t, 120, 0.4) == _slow,
                  f"fit_text's bisection cut {_t[:20]!r} differently")
    _rng = np.random.default_rng(7)
    for _rect, _sp in (((40, 30, 160, 62), 6), ((-6, 10, 70, 44), 5),
                       ((60, 50, 260, 180), 14)):
        _base = _rng.integers(0, 256, (240, 320, 3)).astype(np.uint8)
        _direct, _stamped = _base.copy(), _base.copy()
        _draw_shadow_rings(_direct, _rect, 16, _sp, 0.15)
        drop_shadow(_stamped, _rect, 16, spread=_sp, strength=0.15)
        drop_shadow(_again := _base.copy(), _rect, 16, spread=_sp, strength=0.15)
        check_top(int(np.abs(_direct.astype(int) - _stamped.astype(int)).max()) <= 8
                  and np.array_equal(_stamped, _again),
                  f"stamped shadow {_rect} differs from drawing it")
    for _style, _hover in (("primary", False), ("ghost", True), ("accent", False)):
        _btn = Button("Go", 40, 40, 160, 72, "x", style=_style)
        _base = _rng.integers(0, 256, (140, 220, 3)).astype(np.uint8)
        _direct, _stamped = _base.copy(), _base.copy()
        _btn._paint(_direct, hover=_hover)
        _btn.draw(_stamped, hover=_hover)
        check_top(int(np.abs(_direct.astype(int) - _stamped.astype(int)).max()) <= 8,
                  f"stamped {_style} button differs from drawing it")
    _gframe = _rng.integers(0, 256, (300, 400, 3)).astype(np.uint8)
    _sg = Grid(400, 300, [60, 20, 340, 300], square_cells=False)
    _direct = _gframe.copy()
    _sg._draw_overlay(_direct)
    _stamped = _gframe.copy()
    AffineStamp(400, 300, _sg._draw_overlay).apply(_stamped, 0, 0)
    check_top(int(np.abs(_direct.astype(int) - _stamped.astype(int)).max()) <= 8,
              "the recorded grid overlay differs from drawing it")

    # -- Vision AI looks only at the reachable (non-red) cells
    # (through globals(): this function declares these two `global` further
    # down, and naming them before that declaration is a SyntaxError)
    _g = globals()
    _off = (_g["GRIPPER_OFFSET_UP_DOWN"], _g["GRIPPER_OFFSET_RIGHT_LEFT"],
            CONFIG.n_rows, CONFIG.n_cols)
    try:
        _g["GRIPPER_OFFSET_UP_DOWN"], _g["GRIPPER_OFFSET_RIGHT_LEFT"] = -7, 0
        CONFIG.n_rows = CONFIG.n_cols = 20
        check_top(reachable_cells() == (0, 0, 20, 13),
                  f"reachable cells with the gripper 7 up: {reachable_cells()}")
        _rb = reachable_box((100, 0, 300, 200))
        check_top(all(abs(a - b) < 1e-6 for a, b in zip(_rb, (100, 0, 300, 130))),
                  f"reachable box: {_rb}")
        _rb2 = reachable_box((100, 0, 300, 200), 2.0, 3.0)
        check_top(all(abs(a - b) < 1e-6 for a, b in zip(_rb2, (200, 0, 600, 390))),
                  f"scaled reachable box: {_rb2}")
        _g["GRIPPER_OFFSET_UP_DOWN"], _g["GRIPPER_OFFSET_RIGHT_LEFT"] = 10, 10
        CONFIG.n_cols = 10
        check_top(reachable_box((0, 0, 100, 100)) == NO_REACH,
                  "a board with no reachable column still gave Vision AI a region")
    finally:
        (_g["GRIPPER_OFFSET_UP_DOWN"], _g["GRIPPER_OFFSET_RIGHT_LEFT"],
         CONFIG.n_rows, CONFIG.n_cols) = _off
    _lv2 = LiveVision()
    _lv2._thread = object()
    _lv2.submit(_vframe, (0, 0, 10, 10), None, region=(1, 2, 3, 4))
    check_top(_lv2._pending[3] == (1.0, 2.0, 3.0, 4.0),
              "LiveVision.submit dropped the reachable region")
    _lv2.submit(_vframe, (0, 0, 10, 10), None, region=NO_REACH)
    check_top(_lv2._pending[3] == NO_REACH, "NO_REACH did not reach the feeder")

    # -- an outline the model already called "unknown" is not asked again
    _un = ObjectNamer()
    _un.names = {1: "bowl"}
    _un.asked = {1, 2}
    check_top(_un.unanswered([1, 2, 3]) == [3],
              f"unanswered: {_un.unanswered([1, 2, 3])}")
    check_top(_un.name_now(_vframe, _vobjects[:2], [1, 2], _board) == "",
              "a task re-asked about an outline already answered 'unknown'")
    check_top(not any(hasattr(_x, _a) for _x in (ObjectNamer, LiveVision)
                      for _a in ("auto", "prefetch", "prepare_names")),
              "something still names objects outside a task or the N key")

    # -- priority mode: naming asks for the priority tier, falls back cleanly
    _calls = []

    def _tier_create(**kw):
        _calls.append(kw.get("service_tier"))
        if kw.get("service_tier") == "priority" and kw["model"] == "refuses":
            raise RuntimeError("Invalid value for service_tier: priority")
        return _fake_resp("ok")

    _tier_client = _Bag(chat=_Bag(completions=_Bag(create=_tier_create)))
    call_model(_tier_client, model="m", messages=[], max_tokens=5, priority=True)
    call_model(_tier_client, model="m", messages=[], max_tokens=5)
    check_top(_calls == ["priority", None],
              f"priority tier not asked for exactly when wanted: {_calls}")
    _calls.clear()
    check_top(call_model(_tier_client, model="refuses", messages=[],
                         max_tokens=5, priority=True) == "ok"
              and _calls == ["priority", None] and "refuses" in _PRIORITY_REFUSED,
              f"a refused priority tier did not fall back: {_calls}")
    _calls.clear()
    call_model(_tier_client, model="refuses", messages=[], max_tokens=5,
               priority=True)
    check_top(_calls == [None], "a refusing model was asked for priority again")
    _PRIORITY_REFUSED.discard("refuses")
    check_top({1, 10, 22} <= URGENT_EVENT_TYPES and 5 not in URGENT_EVENT_TYPES,
              "clicks/keys/scrolls must redraw at once; plain mouse moves not")

    # -- the transcript picture is reused until something in it changes
    _ts_state = AppState()
    chat_say(_ts_state, "user", "move the cup to B3")
    _ts_bar = AISidebar(400, 60, 380, 700)
    _ts_canvas = np.full((800, 800, 3), 230, np.uint8)
    _ts_runner, _ts_sim = PlanRunner(), SimRunner()
    _ts_bar.draw(_ts_canvas, _ts_state, _ts_runner, _ts_sim)
    _first = _ts_canvas.copy()
    _ts_canvas[:] = 230
    _ts_bar.draw(_ts_canvas, _ts_state, _ts_runner, _ts_sim)
    check_top(np.array_equal(_first, _ts_canvas),
              "the cached transcript drew differently from the first draw")
    chat_say(_ts_state, "assistant", "Done -- the cup is on B3 now.")
    _ts_canvas[:] = 230
    _ts_bar.draw(_ts_canvas, _ts_state, _ts_runner, _ts_sim)
    check_top(not np.array_equal(_first, _ts_canvas),
              "a new message did not show: the transcript cache went stale")

    # -- the planner reads parts Vision AI never lists from the outline
    _sys = build_planner_system()
    for _want in ("The OPENING (the lip) is the dustpan's LARGER edge",
                  "The opening always faces AWAY from the handle",
                  "the bristle HEAD is the WIDER",
                  "An absent part is never missing",
                  "never write MISSING for it",
                  "the machine's\nCENTER is the drum"):
        check_top(_want in _sys, f"the planner prompt lost {_want!r}")
    for _gone in ("lip/opening, tray and handle components",
                  "ask for a clearer view", "(aka: hatch/lid)",
                  "or bare name when no"):
        check_top(_gone not in _sys,
                  f"the planner prompt still relies on {_gone!r}")

    # -- Error Rebounds: ERR-3 only, on the cheap model at low reasoning
    check_top(not any(n in globals() for n in (
                  "ERR_TESTER_PROMPT", "ERR2_PROMPT", "ERR_VERSIONS",
                  "ERR_STEP_VERSION")),
              "ERR-2 or the checker choice is still in the app")
    _p3 = ErrorReboundJob._parse
    check_top(_p3("VERDICT: Done_correctly\nOBJECTS: black sock=ok\n"
                  "REASON: the sock is in the bowl at F4")
              == ("done correctly", [("black sock", "ok")],
                  "the sock is in the bowl at F4", ""),
              f"ERR-3 done-correctly reply misread: {_p3('VERDICT: Done_correctly')}")
    _v, _o, _r, _n = _p3("VERDICT: Done_wrong,_redo\n"
                         "OBJECTS: black sock=wrong; green bowl=ok; cup=unverified\n"
                         "REASON: sock left at M4\n"
                         "NEXT: FIX: move the black sock from M4 into the bowl\n"
                         "      RETAKE: move the gripper clear of the cup")
    check_top(_v == "done wrongly"
              and _o == [("black sock", "wrong"), ("green bowl", "ok"),
                         ("cup", "unverified")]
              and _n.startswith("FIX: move the black sock")
              and "RETAKE: move the gripper clear" in _n,
              f"ERR-3 redo reply misread: {(_v, _o, _r, _n)}")
    check_top(_p3("VERDICT: Cannot_verify\nOBJECTS: sock=unverified\n"
                  "REASON: gripper covers the bowl\n"
                  "NEXT: RETAKE: move the gripper clear")[0] == "cannot verify",
              "ERR-3 cannot-verify reply misread")
    check_top(_p3("VERDICT: {Done_correctly}\nOBJECTS: a=ok\nREASON: x")[0]
              == "done correctly", "a braced ERR-3 verdict was not read")
    _junk = _p3("I think it worked.")
    check_top(_junk[0] == "unknown" and _junk[2] == "I think it worked.",
              f"an ERR-3 reply with no verdict was guessed at: {_junk}")

    _er = PlanRunner()
    check_top(execution_events(_er) == "", "events invented for an empty plan")
    _er.commands = ["goto_coordinate = M, 4", "pickup", "goto_coordinate = F, 4",
                    "keep"]
    _er.index, _er.finished = 1, False
    _ev = execution_events(_er)
    check_top("stopped at step 2 of 4 (pickup)" in _ev
              and "only means the command was sent" in _ev,
              f"stopped-run events: {_ev}")
    _er.index, _er.finished = 4, True
    check_top(execution_events(_er).startswith("All 4 plan steps"),
              "finished-run events")
    _er.index, _er.finished = -1, False
    check_top(execution_events(_er).startswith("The plan was not executed"),
              "never-run events")

    _img = np.full((60, 80, 3), 128, np.uint8)
    _j3 = ErrorReboundJob("put the sock in the bowl", _img, _img, "OBJECT: sock",
                          events="All 4 plan steps were carried out.")
    _m3 = _j3._messages("B", "A", "S")
    _parts = _m3[1]["content"]
    _labels = [c["text"].split(" ")[0] for c in _parts[1:] if c["type"] == "text"]
    _urls = [c["image_url"]["url"][-1] for c in _parts if c["type"] == "image_url"]
    check_top(_m3[0]["content"] == ERR3_PROMPT
              and _labels == ["INITIAL", "EXECUTION-START", "FINAL"]
              and _urls == ["B", "S", "A"]
              and "fallible" in _parts[0]["text"]
              and "All 4 plan steps" in _parts[0]["text"],
              f"ERR-3's request is not laid out as its prompt expects: {_labels} {_urls}")
    check_top([c["type"] for c in _j3._messages("B", "A")[1]["content"]].count(
              "image_url") == 2, "ERR-3 without an execution-start photo")

    _sent = {}

    def _err_create(**kw):
        _sent.update(kw)
        return _fake_resp("VERDICT: Cannot_verify\nOBJECTS: sock=unverified\n"
                          "REASON: the gripper covers the bowl\n"
                          "NEXT: RETAKE: move the gripper clear")

    _mc = globals()["make_client"]
    globals()["make_client"] = lambda: _Bag(chat=_Bag(completions=_Bag(
        create=_err_create)))
    try:
        _run3 = ErrorReboundJob("put the sock in the bowl", _img, _img, "",
                                start_source=(_img, Grid(80, 60, [0, 0, 80, 60])))
        _run3._run()
    finally:
        globals()["make_client"] = _mc
    check_top(not _run3.error and _run3.verdict == "cannot verify"
              and _run3.objects == [("sock", "unverified")]
              and _run3.next == "RETAKE: move the gripper clear"
              and _sent.get("model") == ERR_MODEL == "gpt-6-luna"
              and _sent.get("reasoning_effort") == ERR_REASONING == "low"
              and _sent.get("max_completion_tokens") == ERR_MAX_TOKENS
              and _run3.version == "ERR-3"
              and sum(c["type"] == "image_url"
                      for c in _sent["messages"][1]["content"]) == 3,
              f"an ERR-3 check did not run end to end: {_run3.error or _run3.verdict}")

    # -- a model that refuses the reasoning effort is asked at its default
    _eff = []

    def _eff_create(**kw):
        _eff.append(kw.get("reasoning_effort"))
        if kw.get("reasoning_effort") and kw["model"] == "no-effort":
            raise RuntimeError("Unsupported value: 'reasoning_effort' does "
                               "not support 'low' with this model.")
        return _fake_resp("ok")

    _eff_client = _Bag(chat=_Bag(completions=_Bag(create=_eff_create)))
    check_top(call_model(_eff_client, model="no-effort", messages=[],
                         max_tokens=5, reasoning="low") == "ok"
              and _eff == ["low", None]
              and ("no-effort", "low") in _REASONING_REFUSED,
              f"a refused reasoning effort did not fall back: {_eff}")
    _eff.clear()
    call_model(_eff_client, model="no-effort", messages=[], max_tokens=5,
               reasoning="low")
    call_model(_eff_client, model="takes-it", messages=[], max_tokens=5,
               reasoning="low")
    check_top(_eff == [None, "low"],
              f"reasoning effort re-sent to a refusing model, or not sent: {_eff}")
    _REASONING_REFUSED.discard(("no-effort", "low"))

    _ck_state = AppState()
    _ck_state.err_ready = True
    _ck_bar = AISidebar(400, 60, 380, 700)
    _ck_canvas = np.full((800, 800, 3), 230, np.uint8)
    _ck_bar.draw(_ck_canvas, _ck_state, PlanRunner(), SimRunner())
    _cb = _ck_bar.check_btn
    check_top(_ck_bar.hit_test((_cb.x0 + _cb.x1) // 2, (_cb.y0 + _cb.y1) // 2,
                               state=_ck_state) == "ai_check",
              "CHECK no longer answers a click")
    check_top(_cb.x0 > _ck_bar.history_btn.x1 and _cb.label == "CHECK",
              "the CHECK pill overlaps History")

    # -- per-step checks: every action step, never a move
    for _c, _want in (("pickup", True), ("keep", True), ("press", True),
                      ("release", True), ("open_door", True),
                      ("close_door", True), ("pour(0.5)", True),
                      ("slice(sock, 3)", True),
                      ("goto_coordinate = M, 7", False),
                      ("goto_coordinate C4", False), ("wait_X(5)", False),
                      ("Task_Completed", False)):
        check_top(step_is_checked(_c) is _want,
                  f"step_is_checked({_c!r}) should be {_want}")
    _sr = PlanRunner()
    _sr.commands = ["goto_coordinate = C, 4", "pickup", "Task_Completed"]
    check_top("step 2" in step_events(_sr, 1).lower()
              and "has just finished" in step_events(_sr, 1),
              "step_events does not say which step was just finished")
    _sst = AppState()
    _offered, _hold = [], [True]
    _sr.on_step_done = lambda i, c: (_offered.append(i), _hold[0])[1]
    _sr.step_wait = lambda: _hold[0]
    _sr.mode, _sr.active, _sr.index, _sr.hold_until = "hold", True, 1, 0.0
    _sr.tick(_sst)
    check_top(_offered == [1] and _sr.index == 1 and _sr.await_step,
              "the runner did not wait for the step check")
    _sr.tick(_sst)
    check_top(_offered == [1] and _sr.index == 1,
              "the runner re-offered the same step or moved on early")
    _hold[0] = False
    _sr.tick(_sst)
    check_top(_sr.index == 2, "the runner did not go on after the verdict")
    _sr.on_step_done = lambda i, c: False
    _sr.mode, _sr.index, _sr.hold_until, _sr._step_offered = "hold", 1, 0.0, False
    _sr.tick(_sst)
    check_top(_sr.index == 2, "a step with no check was held up")
    _hold[0] = "Step 2/3 (PICK UP) went wrong - continue or replan?"
    _sr.on_step_done = lambda i, c: True
    _sr.mode, _sr.index, _sr.hold_until, _sr._step_offered = "hold", 1, 0.0, False
    _sr.step_wait = lambda: _hold[0]
    _sr.tick(_sst)
    check_top(_sr.index == 1 and _sst.status_message == _hold[0],
              "the runner did not hold on the failed step's popup")

    # -- a failed step: what it should have done, and the planner's brief
    _plan = ["goto_coordinate = C, 5", "pickup", "goto_coordinate = A, 1",
             "keep", "goto_coordinate = H, 6", "press", "release",
             "Task_Completed"]
    check_top("hold the object that was at C5" in step_expectation(_plan, 1)
              and "picked up at C5" in step_expectation(_plan, 3)
              and "rest at A1" in step_expectation(_plan, 3),
              f"step expectations: {step_expectation(_plan, 1)!r} / "
              f"{step_expectation(_plan, 3)!r}")
    check_top(gripper_after(_plan, 1) == "holding the object it picked up at C5"
              and gripper_after(_plan, 3) == "holding nothing"
              and gripper_after(_plan, 5) == "holding nothing and still pressing at H6",
              f"gripper_after: {gripper_after(_plan, 5)!r}")
    _note = replan_note(_plan, "# move the sock\n1. goto_coordinate = C, 5",
                        3, "DONE WRONG", "the sock is at B1, not A1",
                        "FIX: move the sock from B1 to A1", {1: "unverified"})
    for _want in ("do NOT plan it from the start", "YOUR EARLIER ANSWER:",
                  "# move the sock", "4. keep   [done - CHECK: DONE WRONG]",
                  "2. pickup   [done - its check could not confirm it]",
                  "5. goto_coordinate = H, 6   [not run yet]",
                  "FIX: move the sock from B1 to A1",
                  "Never repeat steps 1 to 3", "(5 to 8)",
                  "start straight from step 5", "holding nothing"):
        check_top(_want in _note, f"the replan brief lacks {_want!r}")
    check_top("Never repeat" not in replan_note(_plan, "", 0, "DONE WRONG",
                                                 "", "", {}),
              "a replan from step 1 told the planner steps were done")
    _pf = np.full((700, 1100, 3), 200, np.uint8)
    _cr, _rr = draw_step_fail_popup(
        _pf, {"title": "Step 4/8 (PLACE) went wrong", "default": "replan",
              "reason": "the sock is at B1, not A1 " * 6}, 2.4)
    check_top(_cr[2] < _rr[0] and 0 <= _cr[0] and _rr[2] <= 1100
              and 0 <= _cr[1] < _cr[3] <= 700,
              f"the failed-step popup's buttons: {_cr} {_rr}")
    _cr2, _ = draw_step_fail_popup(_pf, {"title": "t", "default": "continue",
                                         "reason": ""}, None)
    check_top(_cr2[2] > _cr2[0], "the popup without a countdown did not draw")

    # -- a replan job: the planner hears the brief, the dexterity gate is skipped
    _planner_in, _dex = [], []
    _was_dex = globals()["DEXTERITY_CHECK"]

    def _plan_create(**kw):
        _planner_in.append(kw["messages"][-1]["content"])
        return _fake_resp("# put the sock right\n1. goto_coordinate = B, 1\n"
                          "2. pickup\n3. goto_coordinate = A, 1\n4. keep\n"
                          "Task_Completed")

    _mc2, _cd = globals()["make_client"], globals()["check_dexterity"]
    globals()["make_client"] = lambda: _Bag(chat=_Bag(completions=_Bag(
        create=_plan_create)))
    globals()["check_dexterity"] = lambda *a, **k: _dex.append(1) or "dexterous"
    globals()["DEXTERITY_CHECK"] = True
    try:
        _rj = AIJob(None, "put the sock in the cup", vision=_FakeVision(),
                    resume=_note)
        _rj._run()
    finally:
        globals()["make_client"], globals()["check_dexterity"] = _mc2, _cd
        globals()["DEXTERITY_CHECK"] = _was_dex
    check_top(not _rj.error and not _rj.rejected and not _dex
              and len(_planner_in) == 1
              and _planner_in[0].rstrip().endswith(_note.rstrip())
              and "Task: put the sock in the cup" in _planner_in[0]
              and "pickup" in parse_plan_commands(_rj.plan),
              f"a replan job: error={_rj.error!r} rejected={_rj.rejected!r} "
              f"dexterity calls={len(_dex)} planner calls={len(_planner_in)}")

    _saved_settings = copy.deepcopy(S1_EMBEDDED_STATE.get("settings") or {})
    _saved_auto = globals()["ERR_AUTO"]
    try:
        _ss = copy.deepcopy(_saved_settings)
        # Settings saved while ERR-2 existed still load.
        _ss.setdefault("behaviour", {}).update(
            {"err_auto": "task", "err_version": "ERR-2",
             "err_step_version": "ERR-2"})
        S1_EMBEDDED_STATE["settings"] = _ss
        load_settings()
        check_top(globals()["ERR_AUTO"] == "task",
                  "automatic ERR settings not restored at launch")
        _ss["behaviour"].update({"err_auto": "always"})
        load_settings()
        check_top(globals()["ERR_AUTO"] == "task",
                  "an unknown automatic ERR setting was accepted")
        _ss["behaviour"].pop("err_auto")
        globals()["ERR_AUTO"] = "step"
        _orig_persist = globals()["persist_embedded_state"]
        globals()["persist_embedded_state"] = lambda *a, **k: True
        try:
            save_settings(CameraSettings(), Grid(640, 480))
        finally:
            globals()["persist_embedded_state"] = _orig_persist
        _b = S1_EMBEDDED_STATE["settings"]["behaviour"]
        check_top(_b["err_auto"] == "step" and "err_version" not in _b
                  and "err_step_version" not in _b,
                  f"the automatic ERR mode was not saved cleanly: {_b}")
    finally:
        S1_EMBEDDED_STATE["settings"] = _saved_settings
        load_settings()
        globals()["ERR_AUTO"] = _saved_auto

    print(f"[blur_band] {checks_top} checks passed")

    class Clock:
        def __init__(self):
            self.now = 100.0

        def monotonic(self):
            return self.now

    class FakeArduino:
        connected = True

        def __init__(self, clock):
            self.clock = clock
            self.commands = []
            self.directions = []
            self.failed_writes = 0

        def send_command(self, command):
            assert command == command.lower(), command
            if self.failed_writes:
                self.failed_writes -= 1
                return False
            self.commands.append((self.clock.now, command))
            return True

        def halt(self):
            self.commands.append((self.clock.now, "s"))
            return True

        def send_direction(self, direction, slow=False):
            self.directions.append(direction)
            self.commands.append((self.clock.now, "<guidance>"))
            return True

    checks = 0

    def check(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    global ARDUINO
    old = (ARDUINO, time.monotonic)
    global GRIPPER_NUDGE_S, GRIPPER_NUDGE_ACTIONS
    old_nudge = (GRIPPER_NUDGE_S, dict(GRIPPER_NUDGE_ACTIONS))
    GRIPPER_NUDGE_S = 0.0
    GRIPPER_NUDGE_ACTIONS = {k: False for k in GRIPPER_NUDGE_ACTIONS}
    try:
        clock = Clock()
        fake = FakeArduino(clock)
        ARDUINO = fake
        time.monotonic = clock.monotonic
        panel = GripperPanel()

        def advance(seconds):
            clock.now += seconds
            panel.tick()

        panel.start_automatic_action("pickup")
        advance(AUTO_ACTION_GAP_S)
        clock.now += 0.7
        check(panel.note_rx(b"S"), "uppercase sensor S was not accepted")
        descent = panel.auto_grip_down_duration
        advance(AUTO_GRIP_COMMAND_DELAY_S)
        advance(AUTO_PICKUP_HX_S)
        advance(AUTO_GRIP_COMMAND_DELAY_S)
        advance(AUTO_GRIP_COMMAND_DELAY_S)
        hu_sent_at = clock.now
        check(fake.commands[-1][1] == "hu", "hu was not sent on schedule")
        planned_raise = panel.auto_grip_up_until - hu_sent_at
        check(abs(planned_raise - descent) < 1e-6,
              f"hu was scheduled to raise for {planned_raise:.3f}s, "
              f"expected the {descent:.3f}s descent")
        advance(descent + 0.05)
        advance(AUTO_ACTION_GAP_S)
        commands = [command for _, command in fake.commands]
        check(commands == ["hd", "hx", "s", "g90", "hu", "s"],
              f"unexpected pickup sequence: {commands}")
        check(not any(c in ("u", "d", "l", "r") for c in commands),
              f"the deleted approach offset still drives the axes: {commands}")
        times = [at for at, _ in fake.commands]
        check(times[1] - times[0] >= AUTO_GRIP_COMMAND_DELAY_S,
              "hx followed the IR sensor without the one-second gap")
        check(times[2] - times[1] >= AUTO_PICKUP_HX_S, "hx duration was short")
        check(times[3] - times[2] >= AUTO_GRIP_COMMAND_DELAY_S,
              "hx-to-g90 wait was short")
        check(times[4] - times[3] >= AUTO_GRIP_COMMAND_DELAY_S,
              "g90-to-hu wait was short")
        check(panel.offset_phase == "idle", "pickup state did not reset")

        clock.now = 200.0
        fake.commands = []
        panel = GripperPanel()
        panel.start_automatic_action("keep")
        panel.start_automatic_action("keep")
        for _ in range(20):
            panel.offset_until = clock.now
            panel.tick()
        check([command for _, command in fake.commands] == ["g0", "g0"],
              "repeated automatic clicks were not queued and replayed")
        check(not panel.pending_auto_actions and panel.offset_phase == "idle",
              "repeated automatic action did not return to idle")

        clock.now = 300.0
        fake.commands = []
        fake.failed_writes = 2
        panel = GripperPanel()
        panel.start_automatic_action("keep")
        panel.offset_until = clock.now
        panel.tick()
        panel.tick()
        panel.tick()
        check([command for _, command in fake.commands] == ["g0"],
              "transient serial writes were not retried")

        panel.visible = True
        frame = np.zeros((650, 1200, 3), dtype=np.uint8)
        panel.draw(frame, (0, 0))
        auto_buttons = sorted(
            (button for button in panel.buttons
             if button.kind.startswith("grip_auto")), key=lambda button: button.x0)
        check(len(auto_buttons) == 4, "automatic gripper buttons are missing")
        check(all(right.x0 - left.x1 > 10
                  for left, right in zip(auto_buttons, auto_buttons[1:])),
              "automatic gripper click targets overlap")

        for packet in (b"S", b"s", b"S\r\n", b"ok S", b"stop"):
            check(has_serial_stop_signal(packet),
                  f"real contact packet {packet!r} was not accepted")
        for packet in (b"sensors ok", b"pos 40", b"status", b"", b"hd"):
            check(not has_serial_stop_signal(packet),
                  f"{packet!r} was wrongly read as contact")

        clock.now = 400.0
        fake.commands = []
        panel = GripperPanel()
        panel.start_automatic_action("pickup")
        advance(1.0)
        check(panel.auto_grip_phase == panel.AUTO_GRIP_DOWN,
              "pickup did not start descending")
        advance(AUTO_GRIP_DOWN_MAX_S)
        commands = [command for _, command in fake.commands]
        check(commands == ["hd", "s"],
              f"a sensorless descent did not stop at hd: {commands}")
        check("g90" not in commands,
              "the jaw closed even though nothing was ever reached")
        check(panel.offset_failed, "a failed pickup reported success")
        check(panel.offset_phase == "idle" and
              panel.auto_grip_phase == panel.AUTO_GRIP_IDLE,
              "a failed pickup did not return to idle")

        clock.now = 500.0
        fake.commands = []
        panel = GripperPanel()
        panel.start_automatic_action("release")
        advance(AUTO_ACTION_GAP_S)
        check([command for _, command in fake.commands] == ["hu"],
              "release did not send hu")
        advance(AUTO_RELEASE_DURATION_S / 2.0)
        check([command for _, command in fake.commands] == ["hu"],
              "release stopped before its full duration")
        advance(AUTO_RELEASE_DURATION_S)
        times = dict((command, at) for at, command in fake.commands)
        commands = [command for _, command in fake.commands]
        check(commands == ["hu", "s"], f"release did not run hu then s: {commands}")
        check(times["s"] - times["hu"] > AUTO_RELEASE_DURATION_S - 1e-6,
              f"release ran for less than {AUTO_RELEASE_DURATION_S:.1f}s")

        clock.now = 600.0
        fake.commands = []
        panel = GripperPanel()
        panel.start_automatic_action("press")
        advance(AUTO_ACTION_GAP_S)
        check([c for _, c in fake.commands] == ["hx"],
              f"press did not start with hx: {fake.commands}")
        for _ in range(40):
            advance(0.1)
        check([c for _, c in fake.commands] == ["hx"],
              f"press cut its own descent short: {fake.commands}")
        check(panel.offset_phase == "press_down",
              "press left the descent without a limit switch")
        descent = clock.now - panel.auto_press_started_at
        check(panel.note_rx(b"s"), "the lowercase limit-switch s was refused")
        check([c for _, c in fake.commands] == ["hx", "hu"],
              f"the limit switch did not start the back-off: {fake.commands}")
        advance(AUTO_PRESS_BACKOFF_S / 2.0)
        check([c for _, c in fake.commands] == ["hx", "hu"],
              "the back-off stopped before it had lifted anything")
        advance(AUTO_PRESS_BACKOFF_S)
        commands = [c for _, c in fake.commands]
        check(commands == ["hx", "hu", "s"],
              f"press did not run hx, then hu, then s: {commands}")
        times = [at for at, _ in fake.commands]
        check(times[2] - times[1] > AUTO_PRESS_BACKOFF_S - 1e-6,
              "the back-off sent hu and s in the same instant")
        advance(AUTO_ACTION_GAP_S)
        check(panel.offset_phase == "idle" and not panel.offset_failed,
              "press did not finish cleanly")
        expected_recorded = descent - AUTO_PRESS_BACKOFF_S
        check(abs(panel.auto_press_duration - expected_recorded) < 1e-6,
              f"press recorded {panel.auto_press_duration:.3f}s, "
              f"expected {expected_recorded:.3f}s")
        check(expected_recorded > AUTO_RELEASE_DURATION_S + 0.5,
              "this case no longer distinguishes a measured lift from the "
              "flat one -- lengthen the descent above")
        fake.commands = []
        panel.start_automatic_action("release")
        advance(AUTO_ACTION_GAP_S)
        check([c for _, c in fake.commands] == ["hu"], "release did not lift")
        advance(AUTO_RELEASE_DURATION_S + 0.1)
        check([c for _, c in fake.commands] == ["hu"],
              "release stopped at the flat duration instead of undoing the "
              "press -- the tool is left standing below where it started")
        advance(expected_recorded - AUTO_RELEASE_DURATION_S)
        commands = [c for _, c in fake.commands]
        check(commands == ["hu", "s"], f"release did not end: {commands}")
        times = [at for at, _ in fake.commands]
        lifted = times[1] - times[0]
        check(expected_recorded - 1e-6 <= lifted <= expected_recorded + 0.2,
              f"release lifted for {lifted:.2f}s, expected the press's own "
              f"{expected_recorded:.2f}s")
        check(panel.auto_press_duration == 0.0,
              "the press depth survived the release that undid it")

        clock.now = 650.0
        fake.commands = []
        panel = GripperPanel()
        panel.start_automatic_action("press")
        advance(AUTO_ACTION_GAP_S)
        check(panel.offset_phase == "press_down", "press did not descend")
        advance(AUTO_GRIP_DOWN_MAX_S)
        commands = [c for _, c in fake.commands]
        check(commands == ["hx", "s"],
              f"a switchless press did not stop at hx: {commands}")
        check("hu" not in commands,
              "the press backed off from a switch it never reached")
        check(panel.offset_failed, "a failed press reported success")
        check(panel.offset_phase == "idle", "a failed press did not reset")

        clock.now = 700.0
        fake.commands = []
        fake.failed_writes = 10 ** 6
        panel = GripperPanel()
        panel.start_automatic_action("keep")
        for _ in range(60):
            advance(AUTO_ACTION_MAX_S / 20.0)
            if panel.offset_phase == "idle":
                break
        check(panel.offset_phase == "idle",
              "an automatic action against a dead port never finished")
        check(panel.offset_failed, "a timed-out action reported success")
        check(fake.commands and fake.commands[-1][1] == "s",
              "the watchdog gave up without stopping the axes")
        fake.failed_writes = 0

        clock.now = 900.0
        fake.commands = []
        fake.directions = []
        fake.failed_writes = 0
        panel = GripperPanel()
        guided_state = AppState()
        guided_state.tag_visible = True
        guided_state.tag_on_grid = True
        guided_state.last_tag_col, guided_state.last_tag_row = 9, 5
        guided_state.target_col, guided_state.target_row = 10, 4
        panel.start_automatic_action("pickup")
        wander = 0
        for _ in range(4000):
            clock.now += 1 / 30.0
            wander = (wander + 1) % 90
            guided_state.last_tag_col = 10 if wander > 45 else 9
            guided_state.last_tag_row = 4 if wander > 45 else 5
            if panel.auto_grip_phase == panel.AUTO_GRIP_DOWN:
                if clock.now - panel.auto_grip_started_at >= 6.0:
                    panel.note_rx(b"S")
            update_guidance(guided_state)
            panel.tick()
            if not panel.automatic_busy():
                break
        check(not panel.automatic_busy(),
              "the guided automatic pickup never finished")
        check(not fake.directions,
              f"guidance wrote to the port mid-action: {fake.directions}")
        sent = [command for _, command in fake.commands]
        check("<guidance>" not in sent, f"guidance interrupted the action: {sent}")
        check("hd" in sent and "hx" in sent, f"the pickup did not run: {sent}")
        between = sent[sent.index("hd") + 1:sent.index("hx")]
        check(not between,
              f"the descent was interrupted by {between}")

        clock.now = 800.0
        fake.commands = []
        fake.failed_writes = 0
        panel = GripperPanel()
        for queued in ("pickup", "keep", "press", "release"):
            panel.start_automatic_action(queued)
        for _ in range(4000):
            advance(0.05)
            if panel.auto_grip_phase == panel.AUTO_GRIP_DOWN:
                panel.note_rx(b"S")
            if panel.offset_phase == "press_down":
                panel.note_rx(b"S")
            if panel.offset_phase == "idle" and not panel.pending_auto_actions:
                break
        check(panel.offset_phase == "idle" and not panel.pending_auto_actions,
              "four chained automatic actions did not all finish")
        check(not panel.offset_failed, "a chained automatic action failed")
        chain = [command for _, command in fake.commands]
        moving = ("r", "d", "l", "u", "hd", "hx", "hu")
        strays = [index for index, command in enumerate(chain)
                  if command == "s" and (index == 0
                                         or chain[index - 1] not in moving)]
        check(not strays,
              f"stop sent with nothing to stop, at {strays} of {chain}")
        check(chain == ["hd", "hx", "s", "g90", "hu", "s",
                        "g0",
                        "hx", "hu", "s",
                        "hu", "s"],
              f"the chained actions did not all run: {chain}")

        box = {"name": "box", "center": "D4",
               "touches": "C3,D3,E3,C4,D4,E4,C5,D5,E5"}
        check(top_right_grip_cell(box) == "E3",
              f"square did not grip top-right: {top_right_grip_cell(box)}")
        ell = {"name": "ell", "center": "C5", "touches": "C3,C4,C5,D5,E5"}
        check(top_right_grip_cell(ell) == "E5",
              f"L-shape grip left the object: {top_right_grip_cell(ell)}")
        tall = {"name": "tall", "center": "B6",
                "touches": "B2,B6,B10"}
        check(top_right_grip_cell(tall) == "B2",
              f"tie did not resolve to the top: {top_right_grip_cell(tall)}")
        sock = {"name": "sock", "center": "C9", "touches":
                "B5,B6,B7,C6,C7,C8,C9,C10,D9,D10,D11,D12,D13"}
        check(top_right_grip_cell(sock) == "C6",
              f"diagonal object gripped low instead of top-right: "
              f"{top_right_grip_cell(sock)}")
        check(top_right_grip_cell({"name": "bare", "center": "H8"}) == "H8",
              "a cell-less object did not fall back to its centre")

        class _SlowPort:
            is_open = True
            def write(self, data):
                time.sleep(0.4)
            def close(self):
                self.is_open = False
        link = SerialLink()
        link.conn = _SlowPort()
        link._ready_at = 0.0
        t0 = time.time()
        link.send_direction("up")
        elapsed = time.time() - t0
        check(elapsed < 0.1,
              f"send_direction blocked the caller for {elapsed:.2f}s -- "
              f"the write is not actually off the main thread")

        grips = [{"object": "box", "part": "body", "cell": "D4",
                  "approach": "top", "why": "flat lid"}]
        resolved = resolve_grip_cells(grips, [box])
        check(len(resolved) == 1 and resolved[0]["cell"] == "E3",
              f"the model's cell was not moved to the corner: {resolved}")
        check(resolved[0]["source"] == "camera-top-right",
              f"wrong grip source: {resolved}")
        silent = resolve_grip_cells([], [box])
        check(len(silent) == 1 and silent[0]["cell"] == "E3"
              and silent[0]["part"] == "top-right corner",
              f"a skipped object did not get a corner grip: {silent}")

        def wire():
            gp = GripperPanel()
            card = SimpleGripperPanel()
            card.on_run = (
                lambda action: gp.start_automatic_action(action, immediate=True))
            card.action_busy = gp.automatic_busy
            card.on_abort = gp.abort_automatic_action
            return gp, card

        clock.now = 1000.0
        fake.commands = []
        fake.failed_writes = 0
        gp, card = wire()
        card.open_for("pickup", automatic=False)
        check(card.visible and card.busy(), "the card did not open and hold")
        check(not card.handed_off and not gp.automatic_busy(),
              "opening the card started an action on its own")
        check(not fake.commands, "opening the card already sent something")
        clock.now += 60.0
        card.tick()
        check(not card.handed_off and card.busy(),
              "the card ran the action while it was still being adjusted")
        card._jog("up")
        check([c for _, c in fake.commands] == ["u" + SLOW_SUFFIX],
              f"jog sent the wrong token: {fake.commands}")
        clock.now += SIMPLE_JOG_PULSE_S
        card.tick()
        check([c for _, c in fake.commands] == ["u" + SLOW_SUFFIX, "s"],
              f"the jog pulse did not end with s: {fake.commands}")
        fake.commands = []
        card._height(True)
        check([c for _, c in fake.commands] == [HEIGHT_UP_CMD],
              f"height up sent the wrong token: {fake.commands}")
        clock.now += SIMPLE_JOG_PULSE_S
        card.tick()
        check([c for _, c in fake.commands] == [HEIGHT_UP_CMD, "s"],
              f"the height pulse never ended: {fake.commands}")
        fake.commands = []
        card._height(False)
        clock.now += SIMPLE_JOG_PULSE_S
        card.tick()
        check([c for _, c in fake.commands] == [HEIGHT_DOWN_CMD, "s"],
              f"height down did not pulse and stop: {fake.commands}")
        check(not card.handed_off,
              "adjusting the height ran the action")

        fake.commands = []
        card.confirm()
        check(card.handed_off and not card.running() and not card.busy(),
              "DONE on a manual step did not release the plan")
        check(not fake.commands, f"a manual DONE drove hardware: {fake.commands}")
        card.tick()
        check(not card.visible, "the card stayed up after a manual DONE")

        clock.now = 1100.0
        fake.commands = []
        gp, card = wire()
        card.open_for("pickup", automatic=False)
        card.cancel()
        clock.now += 30.0
        card.tick()
        check(not card.handed_off,
              "a cancelled card ran the action anyway")
        check(card.busy(), "a cancelled card stopped holding the plan")
        check(not fake.commands, f"a cancelled card sent {fake.commands}")
        card.confirm()
        check(card.handed_off and not fake.commands,
              f"DONE after cancel drove hardware: {fake.commands}")

        clock.now = 1200.0
        fake.commands = []
        gp, card = wire()
        card.open_for("pickup", automatic=False)
        card.stop()
        check([c for _, c in fake.commands] == ["s"],
              f"STOP did not send exactly one s: {fake.commands}")
        clock.now += 30.0
        card.tick()
        check(not card.handed_off, "a stopped card started the action anyway")

        clock.now = 1400.0
        fake.commands = []
        gp, card = wire()
        card.open_for("press", automatic=False)
        card.confirm()
        check(card.handed_off and not fake.commands,
              f"a manual step drove the hardware: {fake.commands}")
        check(not card.busy(), "a confirmed manual step still held the plan")
        card.tick()
        check(not card.visible, "a confirmed manual card did not close")

        for action, first in (("pickup", "hd"), ("keep", "g0"),
                              ("press", "hx"), ("release", "hu")):
            clock.now += 10.0
            fake.commands = []
            gp, card = wire()
            card.open_for(action)
            check(not card.visible, f"automatic {action} opened the card")
            check(card.handed_off, f"automatic {action} did not hand off")
            check(not fake.commands,
                  f"automatic {action} sent a command before its gap: {fake.commands}")
            check(card.busy(), f"automatic {action} did not hold the plan")
            clock.now += AUTO_ACTION_GAP_S
            gp.tick()
            check(fake.commands == [(clock.now, first)],
                  f"automatic {action} did not run on its own: {fake.commands}")
            for _ in range(400):
                clock.now += 1 / 30.0
                if gp.offset_phase == "press_down":
                    gp.note_rx(b"S")
                if gp.auto_grip_phase == gp.AUTO_GRIP_DOWN:
                    gp.note_rx(b"S")
                gp.tick()
                card.tick()
                if not card.busy():
                    break
            check(not card.busy(),
                  f"automatic {action} held the plan after it finished")
            check(not card.visible, f"automatic {action} left the card up")

        clock.now += 10.0
        fake.commands = []
        gp, card = wire()
        card.open_for("keep", automatic=False)
        check(card.visible and not card.handed_off,
              "a manual keep did not open the card and wait")

        for action, first in (("pickup", "hd"), ("keep", "g0"),
                              ("press", "hx"), ("release", "hu")):
            clock.now += 10.0
            fake.commands = []
            fake.failed_writes = 1
            gp, card = wire()
            card.open_for(action)
            check(card.busy() and not fake.commands,
                  f"failed {action} write lost the action")
            clock.now += AUTO_ACTION_GAP_S
            for _ in range(2):
                if fake.commands:
                    break
                gp.tick()
            check(fake.commands == [(clock.now, first)],
                  f"{action} did not retry: {fake.commands}")
            card.stop()

        card.open_for("pickup", automatic=False)
        frame = np.zeros((700, 1000, 3), dtype=np.uint8)
        card.draw(frame, (-1, -1))
        card.draw(frame, (-1, -1))
        kinds = {b.kind for b in card.buttons}
        check(kinds == {"simple_jog", "simple_stop", "simple_height",
                        "simple_cancel", "simple_done", "simple_close"},
              f"unexpected Simple Gripper buttons: {sorted(kinds)}")
        heights = [b for b in card.buttons if b.kind == "simple_height"]
        check({b.value for b in heights} == {"up", "down"},
              "the height pair is not up and down")
        jogs = [b for b in card.buttons if b.kind == "simple_jog"]
        check(len(jogs) == 4, "the jog pad is not four arrows")
        check({b.value for b in jogs} == {"up", "down", "left", "right"},
              "the jog pad is missing a direction")
        done = next(b for b in card.buttons if b.kind == "simple_done")
        fake.commands = []
        card.press((done.x0 + done.x1) // 2, (done.y0 + done.y1) // 2)
        check(card.handed_off and not fake.commands,
              f"the manual DONE click drove hardware: {fake.commands}")
        card.open_for("pickup", automatic=False)
        for b in card.buttons:
            cx = (b.x0 + b.x1) // 2
            cy = (b.y0 + b.y1) // 2
            check(card.press(cx, cy) is not None,
                  f"the {b.kind} button is drawn but does nothing")
            if b.kind == "simple_close":
                card.open_for("pickup", automatic=False)
        for i, a in enumerate(card.buttons):
            for b in card.buttons[i + 1:]:
                overlap = (a.x0 - 5 <= b.x1 + 5 and b.x0 - 5 <= a.x1 + 5
                           and a.y0 - 5 <= b.y1 + 5 and b.y0 - 5 <= a.y1 + 5)
                check(not overlap,
                      f"{a.kind} and {b.kind} have overlapping hit boxes")

        for gone in ("GRIPPER_ACTION_OFFSET_ENABLED", "GRIPPER_ACTION_OFFSET_DIR",
                     "GRIPPER_HORIZONTAL_OFFSET_DIR", "GRIPPER_VERTICAL_OFFSET_DIR"):
            check(gone not in globals(), f"{gone} survived the offset removal")

        state = S1_EMBEDDED_STATE
        check(isinstance(state.get("settings"), dict), "embedded settings missing")
        check(isinstance(state.get("custom_training"), list),
              "embedded custom training missing")
        check(isinstance(state.get("error_rebounds"), list),
              "embedded error history missing")

        GRIPPER_NUDGE_S = 0.2
        GRIPPER_NUDGE_ACTIONS = {"pickup": True, "keep": False,
                                 "press": False, "release": False}
        clock.now += 10.0
        start_at = clock.now
        fake.commands = []
        gp = GripperPanel()
        gp.start_automatic_action("pickup")
        letter = DIRECTION_LETTERS[GRIPPER_NUDGE_DIRECTION] + SLOW_SUFFIX
        check(fake.commands == [(start_at, letter)],
              f"the nudge did not fire immediately: {fake.commands}")
        check(gp.automatic_busy(), "the nudge did not hold the plan")
        clock.now = start_at + GRIPPER_NUDGE_S * 0.5
        gp.tick()
        check(fake.commands == [(start_at, letter)],
              f"the nudge stopped early: {fake.commands}")
        clock.now = start_at + GRIPPER_NUDGE_S * 2
        gp.tick()
        check(fake.commands[-1] == (clock.now, "s"),
              f"the nudge did not stop on its own: {fake.commands}")
        clock.now += AUTO_ACTION_GAP_S
        gp.tick()
        check(fake.commands[-1] == (clock.now, "hd"),
              f"the action did not start after the nudge's own gap: {fake.commands}")

        clock.now += 10.0
        fake.commands = []
        gp = GripperPanel()
        gp.start_automatic_action("keep")
        check(not fake.commands, f"a disabled nudge still fired: {fake.commands}")
        clock.now += AUTO_ACTION_GAP_S
        gp.tick()
        check(fake.commands == [(clock.now, "g0")],
              f"keep without a nudge did not run normally: {fake.commands}")

        clock.now += 10.0
        fake.commands = []
        GRIPPER_NUDGE_S = 0.0
        GRIPPER_NUDGE_ACTIONS["keep"] = True
        gp = GripperPanel()
        gp.start_automatic_action("keep")
        check(not fake.commands, f"a zero-length nudge still fired: {fake.commands}")

        clock.now += 10.0
        fake.commands = []
        fake.failed_writes = 1
        GRIPPER_NUDGE_S = 0.2
        gp = GripperPanel()
        gp.start_automatic_action("keep")
        check(not fake.commands, "a failed nudge write was recorded as sent")
        check(gp.offset_phase == "wait_action",
              "a failed nudge write did not fall through to the normal wait")
        clock.now += AUTO_ACTION_GAP_S
        gp.tick()
        check(fake.commands == [(clock.now, "g0")],
              f"the action did not still run after a failed nudge: {fake.commands}")
    finally:
        (ARDUINO, time.monotonic) = old
        GRIPPER_NUDGE_S, GRIPPER_NUDGE_ACTIONS = old_nudge

    global GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT
    old_offset = (GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT)
    try:
        GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT = -5, 0
        objs = [
            {"name": "shelf", "center": "A17",
             "touches": "A14,A15,A16,A17,A18"},
            {"name": "ghost", "center": "A20", "touches": "A19,A20"},
            {"name": "mug", "center": "B1", "touches": "B1,B2"},
        ]
        kept = restrict_to_reachable(objs)
        names = [o["name"] for o in kept]
        check(names == ["shelf", "mug"],
              f"restrict_to_reachable kept the wrong objects: {names}")
        shelf = kept[0]
        check(shelf["touches"] == "A14,A15",
              f"unreachable TOUCHES cells were not dropped: {shelf['touches']}")
        check(shelf["center"] == "A15",
              f"an unreachable CENTER was not recentred onto a kept cell: "
              f"{shelf['center']}")
        mug = kept[1]
        check(mug["touches"] == "B1,B2" and mug["center"] == "B1",
              f"a fully reachable object was altered: {mug}")
    finally:
        GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT = old_offset

    global persist_embedded_state
    global GRIPPER_VERTICAL_DIRECTION, GRIPPER_HORIZONTAL_DIRECTION
    old_directions = (GRIPPER_VERTICAL_DIRECTION, GRIPPER_HORIZONTAL_DIRECTION)
    old_persist = persist_embedded_state
    old_settings = copy.deepcopy(S1_EMBEDDED_STATE.get("settings"))
    old_offset = (GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT)
    saved = []
    persist_embedded_state = lambda: saved.append(True)
    try:
        load_gripper_offsets({})
        check(gripper_offset() == (0, -7), "offset defaults changed")
        for vertical in range(-10, 11):
            for horizontal in range(-10, 11):
                load_gripper_offsets({"gripper_up_down": vertical,
                                      "gripper_right_left": horizontal})
                check(gripper_offset() == (horizontal, vertical), "axes not combined")
                stop = tag_cell_for(9, 9)
                check(stop == (9 - horizontal, 9 - vertical), "wrong tag stop")
                check(gripper_cell(*stop) == (9, 9), "offset inverse failed")
        for direction, expected in (("up", (0, -4)), ("down", (0, 4)),
                                    ("left", (-4, 0)), ("right", (4, 0))):
            load_gripper_offsets({"gripper_cells": 4, "gripper_dir": direction})
            check(gripper_offset() == expected, "legacy migration failed")
        for width, height in ((400, 480), (640, 480), (1280, 720)):
            load_gripper_offsets({})
            canvas = np.zeros((height, width, 3), dtype=np.uint8)
            panel = TrigPanel()
            panel.visible = True
            panel._anim = 1.0
            panel.draw(canvas)
            grid = Grid(width, height)
            manual = ManualMovePanel()
            manual.visible = True
            manual.draw(canvas)
            settings = SettingsPanel(CameraSettings(), grid, lambda: None)
            def click(x, y):
                consumed = dispatch_video_dropdowns(x, y, settings, panel, manual)
                if consumed:
                    save_settings(CameraSettings(), grid)
                return consumed
            check(panel.offset_values() == (7, "up", 0, "right"), "four defaults wrong")
            for index, dd in enumerate(panel.offset_dropdowns):
                for value, _ in dd.items:
                    before = panel.offset_values()
                    check(click((dd.x0+dd.x1)//2, (dd.y0+dd.y1)//2) and dd.open,
                          "dropdown did not open")
                    manual.letter_dd.open = True
                    manual.draw_lists(canvas)
                    panel.draw_lists(canvas)
                    r = next(r for r in dd._item_rects if r[4] == value)
                    check(0 <= r[0] < r[2] < width and 0 <= r[1] < r[3] < height,
                          "dropdown choice clipped")
                    far_x = r[0] + dd.ITEM_W - 1
                    far_y = r[1] + dd.ITEM_H - 1
                    corner_hit = dd.hit_item(far_x, far_y)
                    check(corner_hit == value,
                          f"a click in the cell's gap missed the item: "
                          f"got {corner_hit!r}, wanted {value!r}")
                    check(click((r[0]+r[2])//2, (r[1]+r[3])//2), "selection missed")
                    expected = list(before)
                    expected[index] = value
                    check(panel.offset_values() == tuple(expected) and not dd.open,
                          "selection changed another field")
                    load_gripper_offsets(S1_EMBEDDED_STATE["settings"]["trig_offset"])
                    check(panel.offset_values() == tuple(expected), "four fields did not persist")
                    manual.letter_dd.open = False
            for index, value in ((0, 0), (1, "down"), (0, 3),
                                 (2, 0), (3, "left"), (2, 2), (2, 1)):
                dd = panel.offset_dropdowns[index]
                panel.hit_test((dd.x0+dd.x1)//2, (dd.y0+dd.y1)//2,
                               CameraSettings(), grid, None)
                panel.draw(canvas)
                r = next(r for r in dd._item_rects if r[4] == value)
                panel.hit_test((r[0]+r[2])//2, (r[1]+r[3])//2,
                               CameraSettings(), grid, None)
                load_gripper_offsets(S1_EMBEDDED_STATE["settings"]["trig_offset"])
                check(panel.offset_values()[index] == value, "direct selection failed")
            check(gripper_offset() == (-1, 3), "number and direction did not compose")
            panel.vertical_dd.open = True
            panel.toggle()
            check(not any(dd.open for dd in panel.offset_dropdowns), "hidden popup stayed open")
        check(len(saved) >= 156, "dropdown choices were not saved")
    finally:
        persist_embedded_state = old_persist
        GRIPPER_VERTICAL_DIRECTION, GRIPPER_HORIZONTAL_DIRECTION = old_directions
        S1_EMBEDDED_STATE["settings"] = old_settings
        GRIPPER_OFFSET_UP_DOWN, GRIPPER_OFFSET_RIGHT_LEFT = old_offset

    for screen_w, screen_h, panel_w in ((800, 600, 340), (1280, 900, 400)):
        example_state = AppState()
        example_sidebar = AISidebar(screen_w - panel_w - 12, 64,
                                    panel_w, screen_h - 96)
        example_runner, example_sim = PlanRunner(), SimRunner()
        example_canvas = np.full((screen_h, screen_w, 3), 225, dtype=np.uint8)

        def draw_examples_test():
            example_sidebar.draw(example_canvas, example_state,
                                 example_runner, example_sim)

        def click_example_rect(rect):
            action = example_sidebar.hit_test((rect[0] + rect[2]) // 2,
                                              (rect[1] + rect[3]) // 2,
                                              state=example_state)
            check(example_sidebar.handle_example_action(example_state, action),
                  f"example click was not handled: {action}")

        for index, (_, prompt, _) in enumerate(TASK_EXAMPLES):
            example_state.ai_task = "previous draft"
            example_state.ai_select_all = True
            example_state.history_open = True
            draw_examples_test()
            button = example_sidebar.examples_btn
            click_example_rect((button.x0, button.y0, button.x1, button.y1))
            draw_examples_test()
            check(example_state.examples_open and not example_state.history_open,
                  "examples did not replace the history menu")
            row = next(rect for rect, action in example_sidebar._example_rects
                       if action == ("ai_example_pick", index))
            click_example_rect(row)
            draw_examples_test()
            check(example_state.ai_task == prompt and example_state.ai_focus
                  and example_state.ai_cursor == len(prompt)
                  and not example_state.ai_select_all,
                  "example did not fill an editable, focused draft")
            check(not example_state.ai_chat and example_state.ai_job is None
                  and not example_runner.active and not example_sim.active
                  and not example_state.exec_pending,
                  "selecting an example sent or executed the prompt")
            check(AISidebar.handle_key(example_state, 13) == "send",
                  "Enter no longer submits the prepared draft")
            rect = example_sidebar._example_popup_rect
            check(0 <= rect[0] < rect[2] <= screen_w
                  and 0 <= rect[1] < rect[3] <= example_sidebar.field[1],
                  "object reminder is clipped or covers the prompt")
            check(9.0 < example_state.example_notice_until - time.monotonic() <= 10.0,
                  "object reminder did not start its ten-second timer")
            example_sidebar.expire_example_notice(
                example_state, example_state.example_notice_until - 0.001)
            check(example_state.example_notice == index, "reminder closed too early")
            example_sidebar.expire_example_notice(
                example_state, example_state.example_notice_until)
            draw_examples_test()
            check(example_state.example_notice is None
                  and not example_sidebar._example_rects
                  and example_state.ai_task == prompt,
                  "reminder expiry changed the draft or left click targets")
        example_sidebar.handle_example_action(example_state, "ai_examples")
        draw_examples_test()
        click_example_rect(example_sidebar._example_rects[0][0])
        check(not example_state.examples_open, "example menu X did not close")
        example_sidebar.handle_example_action(example_state, ("ai_example_pick", 0))
        draw_examples_test()
        click_example_rect(example_sidebar._example_rects[0][0])
        check(example_state.example_notice is None and example_state.ai_task,
              "reminder X did not close while preserving the draft")

    if NSMenu is not None and _MenuTarget is not None:
        NSApplication.sharedApplication()
        test_bar = NSMenu.alloc().init()
        for title in ("S1", "File", "Comm", "Settings"):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
            item.setSubmenu_(NSMenu.alloc().initWithTitle_(title))
            test_bar.addItem_(item)
        native_state = AppState()
        install_examples_menu(test_bar, lambda index: AISidebar.handle_example_action(
            native_state, ("ai_example_pick", index)))
        check(test_bar.numberOfItems() == 5
              and test_bar.itemAtIndex_(3).submenu().title() == "Examples",
              "native Examples menu is missing beside Comm")
        native_menu = test_bar.itemAtIndex_(3).submenu()
        check(native_menu.numberOfItems() == len(TASK_EXAMPLES),
              "native Examples menu does not contain all six tasks")
        for index, (label, prompt, _) in enumerate(TASK_EXAMPLES):
            item = native_menu.itemAtIndex_(index)
            check(item.title() == label, "native example label/order is wrong")
            item.target().fireMenuCallback_(item)
            check(native_state.ai_task == prompt and native_state.ai_focus
                  and native_state.example_notice == index
                  and native_state.ai_job is None and not native_state.ai_chat,
                  "native example failed to prepare the draft and object reminder")
        install_examples_menu(test_bar, lambda index: None)
        check(test_bar.numberOfItems() == 5, "native menu installation duplicated Examples")

    for center, head, grip, target, planned, final in (
            ("E7", "E6", "E4", "I5", "I6", "I3"),
            ("M6", "N6", "K6", "G8", "F8", "D8"),
            ("H8", "G7", "J9", "L5", "M6", "O7")):
        path = (f"goto_coordinate = {center[:-1]}, {center[-1]}\npickup\n"
                f"goto_coordinate = {planned[:-1]}, {planned[-1]}\npress\n"
                f"goto_coordinate = {planned[:-1]}, {planned[-1]}\nrelease\nkeep")
        rewritten, _ = apply_grip_substitution(path, [
            {"override": True, "center": center, "cell": grip}])
        check(rewritten.count(f"goto_coordinate = {final[:-1]}, {final[-1]}") == 2,
              "grip correction did not preserve sweep head positions")
        fc, fr = parse_coordinate(final)
        hc, hr = parse_coordinate(head)
        gc, gr = parse_coordinate(grip)
        check((fc + hc - gc, fr + hr - gr) == parse_coordinate(target),
              "translated bristles do not reach the requested working point")

    for refusal in (
            "# Sleeve and hem locations are unresolved.\n1. Task_Completed",
            "# Cannot fold this shirt.\nTask_Completed",
            "# Cannot fold.\n1. task_completed\n2. Task_Completed",
            "# Cannot fold.\nThe sleeves are unresolved.\nTask_Completed",
            "# Cannot fold.\n1. wait_X(1)\n2. Task_Completed"):
        runner_test = PlanRunner()
        check(runner_test.load(refusal) == 0, "refusal became a runnable plan")
        check(not runner_test.start(AppState()), "refused plan started")
        sim_test = SimRunner()
        sim_test._finish_pending = True
        check(sim_test.load(parse_plan_commands(refusal)) == 0,
              "completion-only plan entered simulation")
        check(not sim_test.start(AppState()) and not sim_test.take_finish(),
              "refusal could trigger the execution countdown")

    two_fold_plan = ("# Fold sleeve onto sleeve, then hem onto body.\n"
                     "1. goto_coordinate = C, 5\n2. pickup\n"
                     "3. goto_coordinate = Q, 5\n4. keep\n"
                     "5. goto_coordinate = N, 11\n6. pickup\n"
                     "7. goto_coordinate = M, 7\n8. keep\n9. Task_Completed")
    runner_test = PlanRunner()
    check(runner_test.load(two_fold_plan) == 9,
          "valid two-fold plan was rejected")
    check(runner_test.commands.count("pickup") == 2
          and runner_test.commands.count("keep") == 2,
          "two folds gained or lost a grip/release")
    sim_test = SimRunner()
    check(sim_test.load(runner_test.commands) == 9
          and sim_test.commands is runner_test.commands,
          "valid simulation lost the runner command list")

    def fold_part(name, x, y):
        return {"name": name, "polygon": [[x, y], [x + .6, y],
                                           [x + .6, y + .6], [x, y + .6]]}
    complete_top = {"name": "orange t-shirt", "color": "orange",
                    "desc": "Unfolded shirt, collar toward row 1.",
                    "polygon": [[2, 1], [17, 1], [17, 11], [2, 11]],
                    "components": [fold_part("sleeve_left", 2.1, 4),
                                   fold_part("sleeve_right", 16, 4),
                                   fold_part("hem_left", 5, 10),
                                   fold_part("hem_right", 13, 10),
                                   fold_part("shoulder_left", 5, 1.2),
                                   fold_part("shoulder_right", 13, 1.2),
                                   fold_part("body", 10, 6)]}
    def located(parts):
        out = []
        for part in parts:
            cell, cells, pt = polygon_to_cells(part["polygon"])
            entry = dict(part, center=coordinate_name(*cell),
                         touches=",".join(coordinate_name(*c) for c in cells))
            set_center_pt(entry, pt)
            out.append(entry)
        return out

    broken_poly = [[2, 1], [17, 1], [17, 7], [2, 7]]
    broken_cell, broken_cells, _ = polygon_to_cells(broken_poly)
    broken_top = dict(
        complete_top, polygon=broken_poly,
        center=coordinate_name(*broken_cell),
        touches=",".join(coordinate_name(*c) for c in broken_cells),
        components=[{"name": n} for n in
                    ("sleeve_left", "sleeve_right", "hem_left", "body")])
    gaps = fold_landmark_gaps(broken_top)
    check(len(gaps) == 4 and "sleeve_left" in gaps and "sleeve_right" in gaps,
          "name-only folding parts were treated as located")
    check(any("shoulder_left/shoulder_right" in g for g in gaps),
          "a top with no located shoulder was allowed to fold -- the hem "
          "fold would have had nowhere to land")
    check(any("hem_left/hem_right" in g for g in gaps),
          "a top with no located hem was allowed to fold")
    rec = fold_recipe(dict(complete_top,
                           components=located(complete_top["components"])))
    check([m["pick_name"] for m in rec["moves"]] == ["sleeve_left", "hem_right"]
          and [m["place_name"] for m in rec["moves"]] == ["sleeve_right", "shoulder_right"]
          and not rec["missing"],
          f"the fold framework changed the verified t-shirt fold: {rec}")
    check("No folding plan was started" in fold_landmark_error(
              [broken_top], "fold my shirt"),
          "fold_landmark_error's own gap-reporting text changed (AIJob no "
          "longer raises it -- see fold_landmark_error's call site -- but the "
          "string is still what fold_recipe_text turns into a per-garment "
          "CANNOT FOLD/MISSING: line)")
    check(not fold_landmark_error([broken_top], "move the shirt"),
          "a garment missing fold landmarks blocked a task that does not fold")

    folder = os.path.dirname(SCRIPT_PATH)
    allowed = {os.path.basename(SCRIPT_PATH),
               os.path.basename(APP_ICON_PATH)}
    extras = sorted(name for name in os.listdir(folder) if name not in allowed)
    check(not extras, f"S1-SRCfolder contains extra files: {extras}")
    print(f"S1-SRCsingle-file self-test passed ({checks} checks).")


def remove_local_bytecode_cache():
    """Keep the S1-SRCfolder single-file even when another script imports S1."""
    cache = os.path.join(os.path.dirname(SCRIPT_PATH), "__pycache__")
    if os.path.isdir(cache):
        shutil.rmtree(cache, ignore_errors=True)


remove_local_bytecode_cache()


if __name__ == "__main__":
    if FASTSAM_BUILD_FLAG in sys.argv:
        build_fastsam_model()
    elif "--self-test" in sys.argv:
        run_single_file_self_test()
    else:
        main()
