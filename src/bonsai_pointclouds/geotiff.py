# Bonsai Point Clouds - PCV/IFC bridge for Bonsai
# Copyright (C) 2026 Carlo Pavan
#
# This file is part of Bonsai Point Clouds.
#
# Bonsai Point Clouds is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Bonsai Point Clouds is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Bonsai Point Clouds.  If not, see <http://www.gnu.org/licenses/>.

"""Minimal GeoTIFF writer — pure Python stdlib (struct + zlib), zero external deps.

Writes classic TIFF (little-endian, single strip) with:
  - Deflate / zlib compression (COMPRESSION = 8), horizontal-differencing
    predictor (PREDICTOR = 2) for grayscale; no predictor for RGB.
  - GeoTIFF georef tags: ModelPixelScaleTag (33550) + ModelTiepointTag (33922).
    No CRS tag is written — coordinates are treated as project-local.
  - Supported modes: "L" (8-bit grayscale) and "RGB" (8-bit RGB, chunky).

Usage::

    from . import geotiff
    geotiff.write(
        filepath    = "/path/to/output.tif",
        pixels      = arr,           # uint8 ndarray, shape (H,W) or (H,W,3)
        x_origin    = 1234.5,        # world X of top-left pixel corner (metres)
        y_origin    = 5678.9,        # world Y of top-left pixel corner (metres)
        pixel_size  = 0.005,         # metres per pixel
        mode        = "L",           # "L" or "RGB"
    )

The file can be read by GDAL, QGIS, rasterio, and BricsCAD (IMAGEATTACH).
"""

from __future__ import annotations
import struct
import zlib
import numpy as np

# ---------------------------------------------------------------------------
# TIFF type codes
# ---------------------------------------------------------------------------
_SHORT  = 3
_LONG   = 4
_DOUBLE = 12

# ---------------------------------------------------------------------------
# TIFF / GeoTIFF tag numbers
# ---------------------------------------------------------------------------
_TAG_IMAGE_WIDTH        = 256
_TAG_IMAGE_LENGTH       = 257
_TAG_BITS_PER_SAMPLE    = 258
_TAG_COMPRESSION        = 259   # 8 = Deflate
_TAG_PHOTOMETRIC        = 262   # 1 = BlackIsZero, 2 = RGB
_TAG_STRIP_OFFSETS      = 273
_TAG_SAMPLES_PER_PIXEL  = 277
_TAG_ROWS_PER_STRIP     = 278
_TAG_STRIP_BYTE_COUNTS  = 279
_TAG_PLANAR_CONFIG      = 284   # 1 = chunky
_TAG_PREDICTOR          = 317   # 1 = none, 2 = horizontal diff
_TAG_EXTRA_SAMPLES      = 338   # 2 = unassociated (straight) alpha
_TAG_MODEL_PIXEL_SCALE  = 33550
_TAG_MODEL_TIEPOINT     = 33922
_TAG_GEO_KEY_DIRECTORY  = 34735


# ---------------------------------------------------------------------------
# IFD entry helpers
# ---------------------------------------------------------------------------

def _ifd_inline_short(tag: int, value: int) -> bytes:
    """IFD entry: SHORT type, count=1, value stored inline (padded to 4 bytes)."""
    return struct.pack("<HHIHH", tag, _SHORT, 1, value, 0)


def _ifd_inline_long(tag: int, value: int) -> bytes:
    """IFD entry: LONG type, count=1, value stored inline."""
    return struct.pack("<HHII", tag, _LONG, 1, value)


def _ifd_offset(tag: int, type_: int, count: int, offset: int) -> bytes:
    """IFD entry with value residing at *offset* in the file."""
    return struct.pack("<HHII", tag, type_, count, offset)


# ---------------------------------------------------------------------------
# Horizontal-differencing predictor (improves Deflate ratio on 8-bit data)
# ---------------------------------------------------------------------------

def _predict_rows(arr2d: np.ndarray) -> bytes:
    """Apply horizontal differencing row-by-row and return raw bytes."""
    # diff along axis=1: first column unchanged, rest are deltas
    delta = np.empty_like(arr2d)
    delta[:, 0]  = arr2d[:, 0]
    delta[:, 1:] = np.diff(arr2d.astype(np.int16), axis=1).astype(np.uint8)
    return delta.tobytes()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write(
    filepath: str,
    pixels: np.ndarray,
    x_origin: float,
    y_origin: float,
    pixel_size: float,
    mode: str = "L",
) -> None:
    """Write a georeferenced single-strip GeoTIFF.

    Parameters
    ----------
    filepath    : destination path
    pixels      : uint8 ndarray, shape ``(H, W)`` for grayscale or ``(H, W, 3)`` for RGB
    x_origin    : world X coordinate of the **top-left corner** of the top-left pixel
    y_origin    : world Y coordinate of the **top-left corner** of the top-left pixel
    pixel_size  : ground sampling distance in metres (square pixels assumed)
    mode        : ``"L"`` (grayscale) or ``"RGB"``
    """
    if pixels.dtype != np.uint8:
        pixels = np.clip(pixels, 0, 255).astype(np.uint8)

    # Detect mode from pixel array shape
    ndim = pixels.ndim
    if ndim == 2:
        mode = "L"          # grayscale, no alpha
    elif pixels.shape[2] == 2:
        mode = "LA"         # grayscale + alpha
    elif pixels.shape[2] == 3:
        mode = "RGB"
    else:
        mode = "RGBA"

    is_rgb      = mode in ("RGB", "RGBA")
    has_alpha   = mode in ("LA", "RGBA")
    h, w        = pixels.shape[:2]
    n_bands     = pixels.shape[2] if ndim == 3 else 1
    photometric = 2 if is_rgb else 1
    # Horizontal differencing predictor only for plain grayscale (L).
    # Multi-band and alpha modes use predictor=1 (none) to avoid
    # differencing across channel boundaries.
    predictor   = 2 if mode == "L" else 1

    # --- Compress pixel data -------------------------------------------------
    if is_rgb or has_alpha:
        raw_bytes = pixels.tobytes()          # chunky, no predictor for multi-band
    else:
        raw_bytes = _predict_rows(pixels)     # horizontal differencing for L
    compressed = zlib.compress(raw_bytes, level=6)

    # --- File layout ---------------------------------------------------------
    # Header  (8 B)
    # IFD     (2 + n_tags*12 + 4 B)   — tag count, entries, next-IFD=0
    # Extra   (variable)              — multi-value data that doesn't fit inline
    # Strip   (compressed pixel data)

    # For RGB, BitsPerSample needs 3 × SHORT stored as extra data.
    # For grayscale, a single SHORT fits inline.

    # ExtraSamples tag only needed when alpha channel is present
    n_tags    = 14 + (1 if has_alpha else 0)
    hdr_size  = 8
    ifd_size  = 2 + n_tags * 12 + 4
    extra_start = hdr_size + ifd_size

    cur = extra_start

    # BitsPerSample: inline for L, offset for multi-band (RGB/LA/RGBA)
    if n_bands > 1:
        bps_off  = cur
        bps_data = struct.pack(f"<{'H' * n_bands}", *([8] * n_bands))
        cur     += len(bps_data)
    else:
        bps_off  = None
        bps_data = b""

    # GeoKeyDirectoryTag: header (4 SHORTs) + 2 GeoKeys (4 SHORTs each) = 12 SHORTs
    # GTModelTypeGeoKey (1024) = 32767 → user-defined (project-local, no CRS)
    # GTRasterTypeGeoKey (1025) = 1    → RasterPixelIsArea
    # NOTE: value 0 (ModelTypeUndefined) triggers a fatal parse error in BricsCAD
    geokey_off  = cur
    geokey_data = struct.pack("<HHHHHHHHHHHH",
        1, 1, 0, 2,        # KeyDirectoryVersion=1, KeyRevision=1, Minor=0, NKeys=2
        1024, 0, 1, 32767, # GTModelTypeGeoKey = 32767 (user-defined / local)
        1025, 0, 1, 1,     # GTRasterTypeGeoKey = 1 (PixelIsArea)
    )
    cur += len(geokey_data)   # 24 bytes

    # ModelPixelScaleTag: (ScaleX, ScaleY, ScaleZ) — 3 DOUBLEs
    px_scale_off  = cur
    px_scale_data = struct.pack("<ddd", pixel_size, pixel_size, 0.0)
    cur          += 24

    # ModelTiepointTag: (I, J, K, X, Y, Z) — 6 DOUBLEs
    # Pixel (0,0) maps to (x_origin, y_origin).
    # Y_origin is the north/top coordinate; pixel-Y increases downward.
    tiepoint_off  = cur
    tiepoint_data = struct.pack("<dddddd", 0.0, 0.0, 0.0, x_origin, y_origin, 0.0)
    cur          += 48

    strip_off = cur   # absolute file offset of the compressed strip

    extra_bytes = bps_data + geokey_data + px_scale_data + tiepoint_data

    # --- Build IFD entries (must be in ascending tag order) ------------------
    entries = []

    entries.append(_ifd_inline_long (_TAG_IMAGE_WIDTH,       w))
    entries.append(_ifd_inline_long (_TAG_IMAGE_LENGTH,      h))

    if n_bands > 1:
        entries.append(_ifd_offset(_TAG_BITS_PER_SAMPLE, _SHORT, n_bands, bps_off))
    else:
        entries.append(_ifd_inline_short(_TAG_BITS_PER_SAMPLE, 8))

    entries.append(_ifd_inline_short(_TAG_COMPRESSION,      8))        # Deflate
    entries.append(_ifd_inline_short(_TAG_PHOTOMETRIC,       photometric))
    entries.append(_ifd_inline_long (_TAG_STRIP_OFFSETS,     strip_off))
    entries.append(_ifd_inline_short(_TAG_SAMPLES_PER_PIXEL, n_bands))
    entries.append(_ifd_inline_long (_TAG_ROWS_PER_STRIP,    h))
    entries.append(_ifd_inline_long (_TAG_STRIP_BYTE_COUNTS, len(compressed)))
    entries.append(_ifd_inline_short(_TAG_PLANAR_CONFIG,     1))        # chunky
    entries.append(_ifd_inline_short(_TAG_PREDICTOR,         predictor))
    if has_alpha:
        # ExtraSamples = 2 (unassociated / straight alpha)
        entries.append(_ifd_inline_short(_TAG_EXTRA_SAMPLES, 2))
    entries.append(_ifd_offset      (_TAG_GEO_KEY_DIRECTORY, _SHORT,  12, geokey_off))
    entries.append(_ifd_offset      (_TAG_MODEL_PIXEL_SCALE, _DOUBLE, 3, px_scale_off))
    entries.append(_ifd_offset      (_TAG_MODEL_TIEPOINT,    _DOUBLE, 6, tiepoint_off))

    # Verify ascending tag order (TIFF spec requirement)
    entries.sort(key=lambda e: struct.unpack_from("<H", e)[0])

    assert len(entries) == n_tags, f"IFD entry count mismatch: {len(entries)} vs {n_tags}"

    # --- Write file ----------------------------------------------------------
    with open(filepath, "wb") as f:
        # TIFF header: little-endian magic, version 42, offset of first IFD
        f.write(b"II")
        f.write(struct.pack("<HI", 42, hdr_size))

        # IFD
        f.write(struct.pack("<H", n_tags))
        for entry in entries:
            f.write(entry)
        f.write(struct.pack("<I", 0))   # next IFD = none

        # Extra data (multi-value fields)
        f.write(extra_bytes)

        # Pixel data (Deflate-compressed)
        f.write(compressed)
