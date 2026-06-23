"""Tests for geotiff.py — pure TIFF binary structure, no Blender needed."""
import struct
import zlib

import numpy as np

from conftest import (
    parse_ifd,
    inline_short, inline_long,
    read_shorts, strip_bytes,
    reverse_predictor,
)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_header(tif):
    data = tif(np.zeros((4, 4), dtype=np.uint8))
    assert data[:2] == b"II"
    assert struct.unpack_from("<H", data, 2)[0] == 42
    assert struct.unpack_from("<I", data, 4)[0] == 8   # IFD at byte 8


def test_ifd_tags_ascending(tif):
    data = tif(np.zeros((4, 4), dtype=np.uint8))
    ifd_off = struct.unpack_from("<I", data, 4)[0]
    n = struct.unpack_from("<H", data, ifd_off)[0]
    tag_list = [
        struct.unpack_from("<H", data, ifd_off + 2 + i * 12)[0]
        for i in range(n)
    ]
    assert tag_list == sorted(tag_list)


def test_ifd_no_next_ifd(tif):
    data = tif(np.zeros((4, 4), dtype=np.uint8))
    ifd_off = struct.unpack_from("<I", data, 4)[0]
    n = struct.unpack_from("<H", data, ifd_off)[0]
    next_off = ifd_off + 2 + n * 12
    assert struct.unpack_from("<I", data, next_off)[0] == 0


def test_file_size_consistent(tif):
    data = tif(np.zeros((6, 8), dtype=np.uint8))
    tags = parse_ifd(data)
    strip_off = inline_long(tags, 273)
    strip_bc  = inline_long(tags, 279)
    assert len(data) == strip_off + strip_bc


# ---------------------------------------------------------------------------
# L (grayscale) mode
# ---------------------------------------------------------------------------

def test_L_core_tags(tif):
    data = tif(np.zeros((4, 4), dtype=np.uint8))
    tags = parse_ifd(data)
    assert inline_short(tags, 259) == 8    # COMPRESSION = Deflate
    assert inline_short(tags, 262) == 1    # PHOTOMETRIC = BlackIsZero
    assert inline_short(tags, 277) == 1    # SAMPLES_PER_PIXEL
    assert inline_short(tags, 284) == 1    # PLANAR_CONFIG = chunky
    assert inline_short(tags, 317) == 2    # PREDICTOR = horizontal diff
    assert 338 not in tags                 # no ExtraSamples


def test_L_dimensions(tif):
    data = tif(np.zeros((6, 8), dtype=np.uint8))
    tags = parse_ifd(data)
    assert inline_long(tags, 256) == 8    # IMAGE_WIDTH
    assert inline_long(tags, 257) == 6    # IMAGE_LENGTH
    assert inline_long(tags, 278) == 6    # ROWS_PER_STRIP


def test_L_roundtrip(tif):
    rng = np.random.default_rng(0)
    px = rng.integers(0, 256, (8, 12), dtype=np.uint8)
    data = tif(px)
    tags = parse_ifd(data)
    raw = zlib.decompress(strip_bytes(data, tags))
    delta = np.frombuffer(raw, dtype=np.uint8).reshape(8, 12)
    assert np.array_equal(reverse_predictor(delta), px)


# ---------------------------------------------------------------------------
# RGB mode
# ---------------------------------------------------------------------------

def test_RGB_core_tags(tif):
    data = tif(np.zeros((4, 4, 3), dtype=np.uint8))
    tags = parse_ifd(data)
    assert inline_short(tags, 262) == 2    # PHOTOMETRIC = RGB
    assert inline_short(tags, 277) == 3    # SAMPLES_PER_PIXEL
    assert inline_short(tags, 317) == 1    # PREDICTOR = none
    assert 338 not in tags                 # no ExtraSamples


def test_RGB_bits_per_sample(tif):
    data = tif(np.zeros((4, 4, 3), dtype=np.uint8))
    tags = parse_ifd(data)
    bps = read_shorts(data, tags, 258)
    assert bps == (8, 8, 8)


def test_RGB_roundtrip(tif):
    rng = np.random.default_rng(1)
    px = rng.integers(0, 256, (4, 6, 3), dtype=np.uint8)
    data = tif(px)
    tags = parse_ifd(data)
    raw = zlib.decompress(strip_bytes(data, tags))
    assert np.frombuffer(raw, dtype=np.uint8).tobytes() == px.tobytes()


# ---------------------------------------------------------------------------
# RGBA mode (transparent background from rasterize)
# ---------------------------------------------------------------------------

def test_RGBA_core_tags(tif):
    data = tif(np.zeros((4, 4, 4), dtype=np.uint8))
    tags = parse_ifd(data)
    assert inline_short(tags, 262) == 2    # PHOTOMETRIC = RGB
    assert inline_short(tags, 277) == 4    # SAMPLES_PER_PIXEL
    assert inline_short(tags, 317) == 1    # PREDICTOR = none
    assert inline_short(tags, 338) == 2    # ExtraSamples = unassociated alpha


def test_RGBA_bits_per_sample(tif):
    data = tif(np.zeros((4, 4, 4), dtype=np.uint8))
    tags = parse_ifd(data)
    bps = read_shorts(data, tags, 258)
    assert bps == (8, 8, 8, 8)


def test_RGBA_roundtrip(tif):
    rng = np.random.default_rng(2)
    px = rng.integers(0, 256, (4, 6, 4), dtype=np.uint8)
    data = tif(px)
    tags = parse_ifd(data)
    raw = zlib.decompress(strip_bytes(data, tags))
    assert np.frombuffer(raw, dtype=np.uint8).tobytes() == px.tobytes()


# ---------------------------------------------------------------------------
# GeoTIFF metadata
# ---------------------------------------------------------------------------

def test_pixel_scale(tif):
    data = tif(np.zeros((4, 4), dtype=np.uint8), pixel_size=0.005)
    tags = parse_ifd(data)
    typ, count, off = tags[33550]   # ModelPixelScaleTag
    assert typ == 12 and count == 3  # DOUBLE × 3
    sx, sy, sz = struct.unpack_from("<ddd", data, off)
    assert abs(sx - 0.005) < 1e-12
    assert abs(sy - 0.005) < 1e-12
    assert sz == 0.0


def test_tiepoint(tif):
    data = tif(np.zeros((4, 4), dtype=np.uint8), x_origin=123.4, y_origin=567.8)
    tags = parse_ifd(data)
    typ, count, off = tags[33922]   # ModelTiepointTag
    assert count == 6
    i, j, k, x, y, z = struct.unpack_from("<dddddd", data, off)
    assert i == j == k == 0.0
    assert abs(x - 123.4) < 1e-9
    assert abs(y - 567.8) < 1e-9


def test_geokey_model_type_user_defined(tif):
    # GTModelTypeGeoKey must be 32767 (user-defined); 0 crashes BricsCAD
    data = tif(np.zeros((4, 4), dtype=np.uint8))
    tags = parse_ifd(data)
    gk = read_shorts(data, tags, 34735)   # GeoKeyDirectoryTag
    # Structure: [ver, rev, minor, nkeys, key0_id, key0_loc, key0_count, key0_val, ...]
    assert gk[4] == 1024      # GTModelTypeGeoKey ID
    assert gk[7] == 32767     # value = user-defined (not 0)


def test_geokey_raster_type(tif):
    data = tif(np.zeros((4, 4), dtype=np.uint8))
    tags = parse_ifd(data)
    gk = read_shorts(data, tags, 34735)
    assert gk[8] == 1025   # GTRasterTypeGeoKey ID
    assert gk[11] == 1     # RasterPixelIsArea
