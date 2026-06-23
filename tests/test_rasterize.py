"""Tests for rasterize.py — numpy-only rasterizer, no Blender needed."""
import numpy as np

from conftest import rasterize as R


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eye():
    """Identity cam_to_world (camera at origin, looking down -Z)."""
    return np.eye(4, dtype=np.float64)


def _cloud(pts, rgb=None):
    """Build a (coords, colors) cloud tuple from a list of [x, y, z] points."""
    coords = np.array(pts, dtype=np.float32)
    colors = (
        np.array(rgb, dtype=np.float32)
        if rgb is not None
        else np.ones((len(coords), 4), dtype=np.float32)
    )
    return coords, colors


# Camera: 1m × 1m ortho, 0.1 m/px → 10×10 image, 0.1 m slab depth
CAM_W, CAM_H, PS, DEPTH = 1.0, 1.0, 0.1, 0.1


def _ras(clouds, mode="L", background="BLACK", **kw):
    return R.rasterize(clouds, _eye(), CAM_W, CAM_H, DEPTH, PS,
                       mode=mode, background=background, **kw)


# ---------------------------------------------------------------------------
# Empty cloud
# ---------------------------------------------------------------------------

def test_empty_black():
    pixels, *_ = _ras([])
    assert pixels.shape == (10, 10)
    assert pixels.max() == 0


def test_empty_white():
    pixels, *_ = _ras([], background="WHITE")
    assert pixels.min() == 255


def test_empty_transparent_is_rgba():
    pixels, *_ = _ras([], background="TRANSPARENT")
    assert pixels.ndim == 3 and pixels.shape[2] == 4


def test_empty_transparent_fully_clear():
    pixels, *_ = _ras([], background="TRANSPARENT")
    assert pixels[:, :, 3].max() == 0   # alpha channel all zero


# ---------------------------------------------------------------------------
# Single point
# ---------------------------------------------------------------------------

def test_point_in_front_hits_centre():
    # Point at world (0,0,-0.01): cam-space (0,0,-0.01) → centre pixel (5,5)
    pixels, *_ = _ras([_cloud([[0.0, 0.0, -0.01]])])
    assert pixels[5, 5] > 0


def test_point_behind_camera_excluded():
    # z > 0 → behind camera
    pixels, *_ = _ras([_cloud([[0.0, 0.0, 0.5]])])
    assert pixels.max() == 0


def test_point_beyond_slab_excluded():
    # z < -DEPTH
    pixels, *_ = _ras([_cloud([[0.0, 0.0, -0.5]])])
    assert pixels.max() == 0


def test_point_outside_frustum_excluded():
    pixels, *_ = _ras([_cloud([[2.0, 0.0, -0.01]])])
    assert pixels.max() == 0


# ---------------------------------------------------------------------------
# Pixel-index accuracy
# ---------------------------------------------------------------------------

def test_corner_point_hits_corner_pixel():
    # Top-left corner of cam in cam space: (−0.45, +0.45, −0.01)
    # → col = floor((−0.45+0.5)/0.1) = floor(0.5) = 0
    # → row = floor((0.5−0.45)/0.1) = floor(0.5) = 0
    pixels, *_ = _ras([_cloud([[-0.45, 0.45, -0.01]])])
    assert pixels[0, 0] > 0


def test_density_increases_with_more_points():
    one  = _ras([_cloud([[0.0, 0.0, -0.01]] * 1)])[0][5, 5]
    many = _ras([_cloud([[0.0, 0.0, -0.01]] * 100)])[0][5, 5]
    assert many >= one


# ---------------------------------------------------------------------------
# Transparent background
# ---------------------------------------------------------------------------

def test_transparent_hit_pixel_is_opaque():
    pixels, *_ = _ras([_cloud([[0.0, 0.0, -0.01]])], background="TRANSPARENT")
    assert pixels[5, 5, 3] == 255


def test_transparent_empty_pixel_is_clear():
    pixels, *_ = _ras([_cloud([[0.0, 0.0, -0.01]])], background="TRANSPARENT")
    # pixel (0,0) is far from the single point → should be transparent
    assert pixels[0, 0, 3] == 0


# ---------------------------------------------------------------------------
# RGB mode
# ---------------------------------------------------------------------------

def test_rgb_mode_shape():
    pixels, *_ = _ras([_cloud([[0.0, 0.0, -0.01]])], mode="RGB")
    assert pixels.shape == (10, 10, 3)


def test_rgb_red_point():
    red = [1.0, 0.0, 0.0, 1.0]
    pixels, *_ = _ras([_cloud([[0.0, 0.0, -0.01]], rgb=[red])], mode="RGB")
    r, g, b = pixels[5, 5]
    assert r > g and r > b


def test_rgb_transparent_is_rgba():
    pixels, *_ = _ras([_cloud([[0.0, 0.0, -0.01]])], mode="RGB", background="TRANSPARENT")
    assert pixels.shape == (10, 10, 4)


# ---------------------------------------------------------------------------
# GeoTIFF origin
# ---------------------------------------------------------------------------

def test_geo_origin_identity_camera():
    # With identity cam, top-left world corner = (−half_w, +half_h) = (−0.5, +0.5)
    _, xo, yo = _ras([])
    assert abs(xo - (-0.5)) < 1e-9
    assert abs(yo - (+0.5)) < 1e-9


def test_geo_origin_translated_camera():
    # Camera translated +10 in X and +20 in Y
    cam = np.eye(4, dtype=np.float64)
    cam[0, 3] = 10.0
    cam[1, 3] = 20.0
    _, xo, yo = R.rasterize([], cam, CAM_W, CAM_H, DEPTH, PS)
    assert abs(xo - (10.0 - 0.5)) < 1e-9
    assert abs(yo - (20.0 + 0.5)) < 1e-9


# ---------------------------------------------------------------------------
# Image dimensions
# ---------------------------------------------------------------------------

def test_image_size_exact():
    pixels, *_ = R.rasterize([], _eye(), 2.0, 1.5, DEPTH, 0.1)
    assert pixels.shape == (15, 20)   # H=ceil(1.5/0.1), W=ceil(2.0/0.1)


def test_image_size_non_round():
    # cam_width not a multiple of pixel_size → ceil
    pixels, *_ = R.rasterize([], _eye(), 1.05, 1.05, DEPTH, 0.1)
    assert pixels.shape == (11, 11)   # ceil(1.05/0.1) = 11
