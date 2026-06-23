"""
Shared helpers for bonsai_pointclouds tests.

geotiff.py and rasterize.py have zero Blender dependency, so we load them
directly from the source tree without touching the package __init__.py.
"""
import pathlib
import struct
import zlib

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Direct source imports (bypasses bpy/bonsai package machinery)
# ---------------------------------------------------------------------------
import sys
_SRC = pathlib.Path(__file__).parent.parent / "src" / "bonsai_pointclouds"
sys.path.insert(0, str(_SRC))

import geotiff   # noqa: E402
import rasterize # noqa: E402

# ---------------------------------------------------------------------------
# TIFF parsing helpers
# ---------------------------------------------------------------------------

def parse_ifd(data: bytes) -> dict:
    """Return {tag: (type, count, value_or_offset)} for the first IFD."""
    assert data[:2] == b"II", "not a little-endian TIFF"
    assert struct.unpack_from("<H", data, 2)[0] == 42, "TIFF magic wrong"
    ifd_off = struct.unpack_from("<I", data, 4)[0]
    n = struct.unpack_from("<H", data, ifd_off)[0]
    tags = {}
    for i in range(n):
        off = ifd_off + 2 + i * 12
        tag, typ, count, val = struct.unpack_from("<HHII", data, off)
        tags[tag] = (typ, count, val)
    return tags


def inline_short(tags: dict, tag: int) -> int:
    """Extract inline SHORT value from an IFD entry (count must be 1)."""
    typ, count, val = tags[tag]
    assert typ == 3 and count == 1, f"tag {tag}: expected SHORT count=1"
    return val & 0xFFFF


def inline_long(tags: dict, tag: int) -> int:
    typ, count, val = tags[tag]
    assert typ == 4 and count == 1, f"tag {tag}: expected LONG count=1"
    return val


def read_shorts(data: bytes, tags: dict, tag: int) -> tuple:
    typ, count, off = tags[tag]
    assert typ == 3, f"tag {tag}: expected SHORT"
    return struct.unpack_from(f"<{count}H", data, off)


def strip_bytes(data: bytes, tags: dict) -> bytes:
    off = inline_long(tags, 273)   # STRIP_OFFSETS
    n   = inline_long(tags, 279)   # STRIP_BYTE_COUNTS
    return data[off : off + n]


def reverse_predictor(delta: np.ndarray) -> np.ndarray:
    """Undo horizontal-differencing predictor (TIFF predictor=2)."""
    return (np.cumsum(delta.astype(np.int32), axis=1) % 256).astype(np.uint8)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tif(tmp_path):
    """Return a helper that writes pixels to a temp TIFF and returns its bytes."""
    def _write(pixels, x_origin=0.0, y_origin=0.0, pixel_size=0.005):
        p = tmp_path / "test.tif"
        geotiff.write(str(p), pixels, x_origin, y_origin, pixel_size)
        return p.read_bytes()
    return _write
