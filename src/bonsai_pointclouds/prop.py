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

from __future__ import annotations
import bpy
import bonsai.tool as tool
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    CollectionProperty,
)
from typing import TYPE_CHECKING, Union
from . import const


# ------------------------------------------------------------------
# Per-cloud setting update callbacks
# These fire when the user edits a property in the panel.
# They dispatch to the active backend (our viewer or PCV).
# ------------------------------------------------------------------


def _update_point_size(self: "PointCloud", _context: bpy.types.Context) -> None:
    from .viewer import PointCloudViewer
    # Our viewer reads point_size directly from the prop at draw time, so we
    # only need to trigger a redraw.  For PCV, try to push the value.
    PointCloudViewer.tag_redraw()
    key = self.host_obj_name
    if key and not PointCloudViewer.exists(key):
        obj = bpy.data.objects.get(key)
        if obj:
            _try_set_pcv(obj, "point_size", self.point_size)


def _update_opacity(self: "PointCloud", _context: bpy.types.Context) -> None:
    key = self.host_obj_name
    if not key:
        return
    from .viewer import PointCloudViewer
    if PointCloudViewer.exists(key):
        # Opacity is baked into vertex colors — needs a batch rebuild.
        PointCloudViewer.set_opacity(key, self.opacity)
    else:
        obj = bpy.data.objects.get(key)
        if obj:
            _try_set_pcv(obj, "alpha", self.opacity)


def _update_draw_on_top(self: "PointCloud", _context: bpy.types.Context) -> None:
    from .viewer import PointCloudViewer
    # Viewer reads draw_on_top from the prop at draw time — just redraw.
    PointCloudViewer.tag_redraw()


def _try_set_pcv(obj: "bpy.types.Object", attr: str, value) -> None:
    """Best-effort: push a value to PCV shader or data props."""
    props = getattr(obj, const.PCV_PROPERTY_GROUP, None)
    if props is None:
        return
    for target in (getattr(props, const.PCV_SHADER_GROUP, None), props):
        if target is not None and hasattr(target, attr):
            try:
                setattr(target, attr, value)
            except (AttributeError, TypeError):
                pass
            break


# ------------------------------------------------------------------
# Property groups
# ------------------------------------------------------------------

class PointCloud(PropertyGroup):
    name: StringProperty(name="Name")
    ifc_definition_id: IntProperty(name="IFC Definition ID")
    is_visible: BoolProperty(name="Is Visible", default=True)
    is_clipped: BoolProperty(name="Is Clipped", default=False)
    is_loaded: BoolProperty(name="Is Loaded", default=False)
    has_clipbox: BoolProperty(name="Has Clip Box", default=False)

    # Key into PointCloudViewer.clouds / host Blender object name.
    # Set when the cloud is loaded; used by update callbacks.
    host_obj_name: StringProperty(name="Host Object Name")

    # Per-cloud rendering settings (apply to our viewer; best-effort for PCV).
    point_size: IntProperty(
        name="Point Size",
        default=int(const.VIEWER_POINT_SIZE),
        min=1,
        max=50,
        subtype="PIXEL",
        update=_update_point_size,
    )
    opacity: FloatProperty(
        name="Opacity",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
        update=_update_opacity,
    )
    draw_on_top: BoolProperty(
        name="Draw on Top",
        description="Disable depth testing so the cloud is always visible through geometry",
        default=False,
        update=_update_draw_on_top,
    )

    if TYPE_CHECKING:
        name: str
        ifc_definition_id: int
        is_visible: bool
        is_clipped: bool
        is_loaded: bool
        has_clipbox: bool
        host_obj_name: str
        point_size: int
        opacity: float
        draw_on_top: bool


class BIMPointCloudProperties(PropertyGroup):
    is_editing: BoolProperty(name="Is Editing", default=False)
    has_pcv: BoolProperty(name="Has PCV", default=False)
    point_clouds: CollectionProperty(name="Point Clouds", type=PointCloud)
    active_point_cloud_index: IntProperty(name="Active Point Cloud Index")

    if TYPE_CHECKING:
        is_editing: bool
        has_pcv: bool
        point_clouds: bpy.types.bpy_prop_collection_idprop[PointCloud]
        active_point_cloud_index: int

    @property
    def active_point_cloud(self) -> Union[PointCloud, None]:
        return tool.Blender.get_active_uilist_element(self.point_clouds, self.active_point_cloud_index)
