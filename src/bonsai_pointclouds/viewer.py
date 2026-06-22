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

"""Minimal GPU point cloud viewer used when Point Cloud Visualizer is absent.

This is an original implementation of the classic viewport-overlay technique
(GPU batch of POINTS drawn from a draw handler, transformed by the host
object's world matrix): the points live in NumPy arrays and a single
SpaceView3D draw handler iterates the registered clouds, drawing them with
Blender's built-in FLAT_COLOR shader. It only reads PLY; LAS/E57 still require
PCV.
"""

from __future__ import annotations
import numpy as np
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from . import const


class PointCloudViewer:
    """Registry of GPU-drawn clouds, keyed by host object name."""

    clouds = {}  # key -> {"batch": GPUBatch, "draw": bool}
    _shader = None
    _handle = None

    @classmethod
    def _get_shader(cls):
        if cls._shader is None:
            cls._shader = gpu.shader.from_builtin("FLAT_COLOR")
        return cls._shader

    @classmethod
    def register(cls):
        if cls._handle is None:
            cls._handle = bpy.types.SpaceView3D.draw_handler_add(cls._draw, (), "WINDOW", "POST_VIEW")

    @classmethod
    def unregister(cls):
        if cls._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(cls._handle, "WINDOW")
            cls._handle = None
        cls.clouds.clear()
        cls._shader = None

    @classmethod
    def load(cls, key: str, coords: np.ndarray, colors: np.ndarray) -> None:
        shader = cls._get_shader()
        batch = batch_for_shader(shader, "POINTS", {"pos": coords, "color": colors})
        cls.clouds[key] = {"batch": batch, "draw": True}
        cls.tag_redraw()

    @classmethod
    def remove(cls, key: str) -> None:
        if key in cls.clouds:
            del cls.clouds[key]
            cls.tag_redraw()

    @classmethod
    def exists(cls, key: str) -> bool:
        return key in cls.clouds

    @classmethod
    def set_draw(cls, key: str, draw: bool) -> None:
        if key in cls.clouds:
            cls.clouds[key]["draw"] = draw
            cls.tag_redraw()

    @classmethod
    def is_drawn(cls, key: str) -> bool:
        entry = cls.clouds.get(key)
        return bool(entry and entry["draw"])

    @classmethod
    def tag_redraw(cls) -> None:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()

    @classmethod
    def _draw(cls) -> None:
        if not cls.clouds:
            return
        shader = cls._get_shader()
        gpu.state.point_size_set(const.VIEWER_POINT_SIZE)
        gpu.state.depth_test_set("LESS_EQUAL")
        for key, entry in list(cls.clouds.items()):
            if not entry["draw"]:
                continue
            obj = bpy.data.objects.get(key)
            if obj is None:
                continue
            with gpu.matrix.push_pop():
                gpu.matrix.multiply_matrix(obj.matrix_world)
                shader.bind()
                entry["batch"].draw(shader)
        gpu.state.depth_test_set("NONE")


# PLY reading -----------------------------------------------------------------

_PLY_DTYPES = {
    "char": "i1", "int8": "i1",
    "uchar": "u1", "uint8": "u1",
    "short": "i2", "int16": "i2",
    "ushort": "u2", "uint16": "u2",
    "int": "i4", "int32": "i4",
    "uint": "u4", "uint32": "u4",
    "float": "f4", "float32": "f4",
    "double": "f8", "float64": "f8",
}


def read_ply(filepath: str):
    """Read a PLY point cloud into (coords Nx3 float32, colors Nx4 float32).

    Supports ascii and binary little/big endian, reading the vertex element
    only (x/y/z required, red/green/blue optional). Returns (None, None) if no
    vertex data is found.
    """
    with open(filepath, "rb") as f:
        if f.readline().strip() != b"ply":
            raise ValueError("Not a PLY file")

        fmt = None
        vertex_count = 0
        properties = []  # (name, ply_type) for the vertex element
        in_vertex = False
        while True:
            line = f.readline()
            if not line:
                raise ValueError("Unexpected end of PLY header")
            tokens = line.split()
            if not tokens:
                continue
            keyword = tokens[0]
            if keyword == b"format":
                fmt = tokens[1].decode()
            elif keyword == b"element":
                in_vertex = tokens[1] == b"vertex"
                if in_vertex:
                    vertex_count = int(tokens[2])
            elif keyword == b"property" and in_vertex:
                properties.append((tokens[-1].decode(), tokens[-2].decode()))
            elif keyword == b"end_header":
                break

        if vertex_count == 0 or not properties:
            return None, None

        names = [p[0] for p in properties]
        if fmt == "ascii":
            rows = []
            read = 0
            while read < vertex_count:
                line = f.readline()
                if not line.strip():
                    continue
                rows.append([float(x) for x in line.split()])
                read += 1
            arr = np.array(rows, dtype=np.float64)
            columns = {name: arr[:, i] for i, name in enumerate(names)}
        else:
            order = "<" if fmt == "binary_little_endian" else ">"
            dtype = np.dtype([(p[0], order + _PLY_DTYPES[p[1]]) for p in properties])
            data = np.frombuffer(f.read(dtype.itemsize * vertex_count), dtype=dtype, count=vertex_count)
            columns = {name: data[name] for name in names}

    coords = np.column_stack([columns["x"], columns["y"], columns["z"]]).astype(np.float32)

    colors = np.ones((vertex_count, 4), dtype=np.float32)
    if {"red", "green", "blue"} <= set(names):
        rgb = np.column_stack([columns["red"], columns["green"], columns["blue"]]).astype(np.float32)
        # uchar colors are 0-255, float colors already 0-1.
        if rgb.max() > 1.0:
            rgb /= 255.0
        colors[:, :3] = rgb
        if "alpha" in names:
            alpha = np.asarray(columns["alpha"], dtype=np.float32)
            colors[:, 3] = alpha / 255.0 if alpha.max() > 1.0 else alpha

    return coords, colors
