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

Uses a custom GLSL shader so that:
  - gl_PointSize is set from a uniform  (gpu.state.point_size_set is a no-op in
    OpenGL Core Profile where GL_PROGRAM_POINT_SIZE is always active)
  - draw_on_top forces gl_Position.z to the near plane in the vertex stage
  - clip-box masking is done entirely on the GPU via a local_to_clip matrix
    uniform — no CPU filtering, no batch rebuild when the box moves
Only reads PLY; LAS/E57 still require PCV.
"""

from __future__ import annotations
import numpy as np
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from . import const

# ------------------------------------------------------------------
# Shader sources (Blender GPUShaderCreateInfo style:
# declarations are injected by the info object, not repeated here)
# ------------------------------------------------------------------

_VERT_GLSL = """
void main()
{
    /* Clip-box test in clip-box local space.
       u_local_to_clip transforms from host-object local coords to the
       clip box's local coords; the box occupies the unit cube [-0.5, 0.5]^3. */
    v_discard = 0.0;
    if (u_clip_enabled != 0) {
        vec4 local = u_local_to_clip * vec4(pos, 1.0);
        vec3 a = abs(local.xyz);
        if (a.x > 0.5 || a.y > 0.5 || a.z > 0.5) {
            /* Cannot discard in the vertex shader; park the vertex out of
               clip space and signal the fragment shader to discard. */
            v_discard = 1.0;
            gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
            gl_PointSize = 0.0;
            v_color = vec4(0.0);
            return;
        }
    }

    gl_Position = u_mvp * vec4(pos, 1.0);
    gl_PointSize = u_point_size;

    /* draw_on_top: collapse z to the near plane so the point always passes
       the LESS_EQUAL depth test regardless of scene geometry. */
    if (u_draw_on_top != 0) {
        gl_Position.z = -gl_Position.w;
    }

    v_color = color;
}
"""

_FRAG_GLSL = """
void main()
{
    if (v_discard > 0.5) {
        discard;
    }
    fragColor = v_color;
}
"""


def _make_shader():
    iface = gpu.types.GPUStageInterfaceInfo("PointCloud_Iface")
    iface.smooth('VEC4', 'v_color')
    iface.smooth('FLOAT', 'v_discard')

    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant('MAT4', 'u_mvp')
    info.push_constant('MAT4', 'u_local_to_clip')
    info.push_constant('FLOAT', 'u_point_size')
    info.push_constant('INT',   'u_clip_enabled')
    info.push_constant('INT',   'u_draw_on_top')
    info.vertex_in(0, 'VEC3', 'pos')
    info.vertex_in(1, 'VEC4', 'color')
    info.vertex_out(iface)
    info.fragment_out(0, 'VEC4', 'fragColor')
    info.vertex_source(_VERT_GLSL)
    info.fragment_source(_FRAG_GLSL)

    shader = gpu.shader.create_from_info(info)
    del info, iface
    return shader


def _mat4_flat(m) -> list:
    """Flatten a mathutils.Matrix to 16 floats in column-major (GLSL) order."""
    return [m[r][c] for c in range(4) for r in range(4)]


_IDENTITY_FLAT = [1, 0, 0, 0,  0, 1, 0, 0,  0, 0, 1, 0,  0, 0, 0, 1]


class PointCloudViewer:
    """Registry of GPU-drawn clouds, keyed by host object name.

    Each entry:
        batch        — GPUBatch (rebuilt only when opacity changes)
        draw         — visibility flag
        coords       — raw Nx3 float32 (host-object local space)
        colors       — raw Nx4 float32 with original alpha
        opacity      — float 0-1, multiplied into alpha at batch build time
        clip_box     — bpy.types.Object or None
        clip_enabled — bool
    """

    clouds: dict = {}
    _shader = None
    _draw_handle = None
    _depsgraph_handle = None

    @classmethod
    def _get_shader(cls):
        if cls._shader is None:
            cls._shader = _make_shader()
        return cls._shader

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def register(cls):
        if cls._draw_handle is None:
            cls._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                cls._draw, (), "WINDOW", "POST_VIEW"
            )
        if cls._depsgraph_handle is None:
            cls._depsgraph_handle = bpy.app.handlers.depsgraph_update_post.append(
                _depsgraph_update
            )

    @classmethod
    def unregister(cls):
        if cls._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(cls._draw_handle, "WINDOW")
            cls._draw_handle = None
        if cls._depsgraph_handle is not None:
            try:
                bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_update)
            except ValueError:
                pass
            cls._depsgraph_handle = None
        cls.clouds.clear()
        cls._shader = None

    # ------------------------------------------------------------------
    # Cloud management
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, key: str, coords: np.ndarray, colors: np.ndarray) -> None:
        existing = cls.clouds.get(key, {})
        entry = {
            "draw": existing.get("draw", True),
            "coords": coords,
            "colors": colors,
            "opacity": existing.get("opacity", 1.0),
            "clip_box": existing.get("clip_box"),
            "clip_enabled": existing.get("clip_enabled", False),
            "batch": None,
        }
        cls.clouds[key] = entry
        cls._rebuild_batch(key)
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
    def set_opacity(cls, key: str, opacity: float) -> None:
        if key in cls.clouds:
            cls.clouds[key]["opacity"] = opacity
            cls._rebuild_batch(key)
            cls.tag_redraw()

    @classmethod
    def set_clip(cls, key: str, clip_box, enabled: bool) -> None:
        """Enable or disable clip-box for this cloud.

        Clipping is evaluated entirely in the vertex shader — no batch rebuild.
        """
        if key in cls.clouds:
            cls.clouds[key]["clip_box"] = clip_box
            cls.clouds[key]["clip_enabled"] = enabled
            cls.tag_redraw()

    @classmethod
    def get_clip_enabled(cls, key: str) -> bool:
        entry = cls.clouds.get(key)
        return bool(entry and entry.get("clip_enabled", False))

    # ------------------------------------------------------------------
    # Batch rebuild — opacity only (baked into vertex alpha)
    # ------------------------------------------------------------------

    @classmethod
    def _rebuild_batch(cls, key: str) -> None:
        entry = cls.clouds.get(key)
        if entry is None:
            return
        coords = entry["coords"]
        colors = entry["colors"].copy()
        opacity = entry.get("opacity", 1.0)
        if opacity < 1.0:
            colors[:, 3] *= opacity
        shader = cls._get_shader()
        entry["batch"] = batch_for_shader(shader, "POINTS", {"pos": coords, "color": colors})

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

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

        # Build per-cloud prop lookup keyed by ifc_definition_id (most reliable).
        # Also index by host_obj_name as a fast path.
        prop_by_name: dict = {}
        prop_by_ifc: dict = {}
        try:
            pc_props = bpy.context.scene.BIMPointCloudProperties
            for item in pc_props.point_clouds:
                prop_by_ifc[item.ifc_definition_id] = item
                if item.host_obj_name:
                    prop_by_name[item.host_obj_name] = item
        except (AttributeError, RuntimeError):
            pass

        view_mat = gpu.matrix.get_model_view_matrix()
        proj_mat = gpu.matrix.get_projection_matrix()

        shader = cls._get_shader()
        shader.bind()
        gpu.state.depth_test_set("LESS_EQUAL")

        for key, entry in list(cls.clouds.items()):
            if not entry["draw"]:
                continue
            if entry.get("batch") is None:
                continue
            obj = bpy.data.objects.get(key)
            if obj is None:
                continue

            # Find the prop item — by name first, then by ifc_id on the object.
            prop_item = prop_by_name.get(key)
            if prop_item is None:
                ifc_id = obj.get("bonsai_pointcloud_id")
                if ifc_id is not None:
                    prop_item = prop_by_ifc.get(ifc_id)
                    if prop_item is not None:
                        prop_item.host_obj_name = key  # heal for next frame

            point_size = prop_item.point_size if prop_item else const.VIEWER_POINT_SIZE
            draw_on_top = prop_item.draw_on_top if prop_item else False
            opacity = entry.get("opacity", 1.0)

            # MVP: projection × view × model (column-major for GLSL).
            mvp = proj_mat @ view_mat @ obj.matrix_world
            shader.uniform_float("u_mvp", _mat4_flat(mvp))
            shader.uniform_float("u_point_size", point_size)
            shader.uniform_int("u_draw_on_top", 1 if draw_on_top else 0)

            clip_box = entry.get("clip_box")
            if entry.get("clip_enabled") and clip_box is not None:
                local_to_clip = clip_box.matrix_world.inverted() @ obj.matrix_world
                shader.uniform_float("u_local_to_clip", _mat4_flat(local_to_clip))
                shader.uniform_int("u_clip_enabled", 1)
            else:
                shader.uniform_float("u_local_to_clip", _IDENTITY_FLAT)
                shader.uniform_int("u_clip_enabled", 0)

            gpu.state.blend_set("ALPHA" if opacity < 1.0 else "NONE")
            entry["batch"].draw(shader)

        gpu.state.depth_test_set("NONE")
        gpu.state.blend_set("NONE")


# ------------------------------------------------------------------
# Depsgraph handler — tag redraw when a clip box moves
# ------------------------------------------------------------------

def _depsgraph_update(_, depsgraph):
    """Clip-box movement triggers a redraw; the vertex shader re-evaluates each frame."""
    if not PointCloudViewer.clouds:
        return
    for update in depsgraph.updates:
        if not update.is_updated_transform:
            continue
        obj_id = update.id
        if isinstance(obj_id, bpy.types.Object) and obj_id.get("is_clipbox"):
            PointCloudViewer.tag_redraw()
            return


# ------------------------------------------------------------------
# PLY reader
# ------------------------------------------------------------------

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

    Supports ascii and binary little/big endian. Returns (None, None) if no
    vertex data is found.
    """
    with open(filepath, "rb") as f:
        if f.readline().strip() != b"ply":
            raise ValueError("Not a PLY file")

        fmt = None
        vertex_count = 0
        properties = []
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
        if rgb.max() > 1.0:
            rgb /= 255.0
        colors[:, :3] = rgb
        if "alpha" in names:
            alpha = np.asarray(columns["alpha"], dtype=np.float32)
            colors[:, 3] = alpha / 255.0 if alpha.max() > 1.0 else alpha

    return coords, colors
