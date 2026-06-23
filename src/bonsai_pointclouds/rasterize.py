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

"""Blender-agnostic point cloud rasterizer — numpy only, no Blender dependency.

Given one or more point clouds in world space and an orthographic camera frame,
produces a uint8 image (grayscale or RGB) suitable for GeoTIFF export.

Coordinate conventions
----------------------
- ``cam_to_world`` is a 4×4 float64 matrix whose columns are the camera's local
  X (right), Y (up), Z (backward / away from scene), and translation.  This is
  identical to Blender's ``obj.matrix_world`` for a camera object.
- The image plane is the camera's local XY plane (Z = 0 in camera space).
- Points in *front* of the camera have **negative** Z in camera local space.
- The slab captured by the export spans ``z_cam ∈ [−depth, 0]``.

Rasterization
-------------
All operations are fully vectorised (numpy).  For N points the main steps are:

1. Transform to camera space:  ``pts_cam = world_to_cam @ pts_world``  — O(N)
2. Boolean slab mask  — O(N)
3. Pixel-index computation  — O(N)
4. Accumulation via ``numpy.bincount``  — O(N), no Python loops

Grayscale output represents point *density* (log-normalised, bright = dense).
RGB output represents the average colour of all points that fall into each pixel.
"""

from __future__ import annotations
import math
import numpy as np


def rasterize(
    clouds: list[tuple[np.ndarray, np.ndarray]],
    cam_to_world: np.ndarray,
    cam_width: float,
    cam_height: float,
    depth: float,
    pixel_size: float,
    mode: str = "L",
    background: str = "BLACK",
) -> tuple[np.ndarray, float, float]:
    """Rasterize point clouds onto an orthographic camera plane.

    Parameters
    ----------
    clouds
        List of ``(coords, colors)`` tuples.  ``coords`` is ``(N, 3)`` float32
        in world space; ``colors`` is ``(N, 4)`` float32, values in ``[0, 1]``.
    cam_to_world
        4×4 float64 camera-to-world matrix (camera local frame in world space).
    cam_width, cam_height
        Orthographic camera extents in world units (metres).
    depth
        Slab thickness in metres; only points within this depth of the image
        plane are rasterised.
    pixel_size
        Ground sampling distance in metres per pixel (square pixels).
    mode
        ``"L"`` for grayscale density map or ``"RGB"`` for colour average.

    Returns
    -------
    pixels
        ``uint8`` ndarray of shape ``(H, W)`` for grayscale, ``(H, W, 3)``
        for RGB, or ``(H, W, 4)`` for transparent background (always RGBA for
        maximum reader compatibility — LA is not widely supported).
        The top row of the image corresponds to the highest Y in camera local
        space (i.e. the camera's "up" direction).
    x_origin
        World X coordinate of the **top-left corner** of the top-left pixel
        (for the GeoTIFF ModelTiepointTag).
    y_origin
        World Y coordinate of the same corner.
    """
    W = max(1, math.ceil(cam_width  / pixel_size))
    H = max(1, math.ceil(cam_height / pixel_size))

    world_to_cam = np.linalg.inv(cam_to_world.astype(np.float64))
    half_w = cam_width  / 2.0
    half_h = cam_height / 2.0

    # Accumulators
    if mode == "RGB":
        acc_r = np.zeros(H * W, dtype=np.float64)
        acc_g = np.zeros(H * W, dtype=np.float64)
        acc_b = np.zeros(H * W, dtype=np.float64)
        acc_n = np.zeros(H * W, dtype=np.int64)
    else:
        acc_n = np.zeros(H * W, dtype=np.int64)

    for coords, colors in clouds:
        if coords is None or len(coords) == 0:
            continue

        coords = np.asarray(coords, dtype=np.float64)

        # Transform to camera local space (homogeneous multiply)
        ones   = np.ones((len(coords), 1), dtype=np.float64)
        pts_h  = np.concatenate([coords, ones], axis=1)       # (N, 4)
        pts_cam = (world_to_cam @ pts_h.T).T                  # (N, 4)

        x_cam = pts_cam[:, 0]
        y_cam = pts_cam[:, 1]
        z_cam = pts_cam[:, 2]

        # Slab filter: keep points within [−depth, 0] in camera Z
        # (negative Z = in front of the camera in Blender convention)
        mask = (z_cam >= -depth) & (z_cam <= 0.0)

        # Frustum filter: keep points within the camera extents
        mask &= (x_cam >= -half_w) & (x_cam <= half_w)
        mask &= (y_cam >= -half_h) & (y_cam <= half_h)

        if not np.any(mask):
            continue

        x_f = x_cam[mask]
        y_f = y_cam[mask]

        # Pixel indices — clamp to valid range
        # col: 0 = left  (x_cam = −half_w)
        # row: 0 = top   (y_cam = +half_h, image Y is flipped)
        col = np.floor((x_f + half_w) / pixel_size).astype(np.int32)
        row = np.floor((half_h - y_f) / pixel_size).astype(np.int32)
        col = np.clip(col, 0, W - 1)
        row = np.clip(row, 0, H - 1)

        flat = row * W + col   # (M,) flat pixel index

        # Accumulate
        np.add.at(acc_n, flat, 1)
        if mode == "RGB":
            rgb = np.asarray(colors[mask, :3], dtype=np.float64)
            np.add.at(acc_r, flat, rgb[:, 0])
            np.add.at(acc_g, flat, rgb[:, 1])
            np.add.at(acc_b, flat, rgb[:, 2])

    # --- Build output image --------------------------------------------------
    hit      = acc_n.reshape(H, W) > 0
    bg_value = 255 if background == "WHITE" else 0
    use_alpha = background == "TRANSPARENT"

    if mode == "RGB":
        img = np.full((H * W, 3), bg_value, dtype=np.float64)
        hit_flat = acc_n > 0
        img[hit_flat, 0] = acc_r[hit_flat] / acc_n[hit_flat]
        img[hit_flat, 1] = acc_g[hit_flat] / acc_n[hit_flat]
        img[hit_flat, 2] = acc_b[hit_flat] / acc_n[hit_flat]
        rgb = (img.reshape(H, W, 3) * 255).clip(0, 255).astype(np.uint8)
        if use_alpha:
            alpha = (hit * 255).astype(np.uint8)[:, :, np.newaxis]
            pixels = np.concatenate([rgb, alpha], axis=2)   # (H, W, 4)
        else:
            pixels = rgb
    else:
        density = acc_n.reshape(H, W).astype(np.float64)
        if density.max() > 0:
            log_d = np.log1p(density)
            grey  = (log_d / log_d.max() * 255).astype(np.uint8)
        else:
            grey = np.zeros((H, W), dtype=np.uint8)
        if background == "WHITE":
            grey[~hit] = 255
        if use_alpha:
            alpha = (hit * 255).astype(np.uint8)
            # Expand to RGBA (gray triplicated) — LA (gray+alpha) has poor support
            # in many TIFF readers (BricsCAD, Krita); RGBA is universally safe.
            rgb   = np.stack([grey, grey, grey], axis=2)             # (H, W, 3)
            pixels = np.concatenate([rgb, alpha[:, :, np.newaxis]], axis=2)  # (H, W, 4)
        else:
            pixels = grey

    # --- GeoTIFF origin (top-left corner of top-left pixel in world space) ---
    # Top-left corner in camera local space: (−half_w, +half_h, 0, 1)
    corner_cam = np.array([-half_w, half_h, 0.0, 1.0])
    corner_world = cam_to_world.astype(np.float64) @ corner_cam
    x_origin = float(corner_world[0])
    y_origin = float(corner_world[1])

    return pixels, x_origin, y_origin
