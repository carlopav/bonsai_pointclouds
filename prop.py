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


class PointCloud(PropertyGroup):
    name: StringProperty(name="Name")
    ifc_definition_id: IntProperty(name="IFC Definition ID")
    location: StringProperty(name="Location", default="")
    scale: FloatProperty(name="Scale", default=1.0)
    is_visible: BoolProperty(name="Is Visible", default=True)
    is_clipped: BoolProperty(name="Is Clipped", default=False)
    is_loaded: BoolProperty(name="Is Loaded", default=False)
    has_clipbox: BoolProperty(name="Has Clip Box", default=False)

    if TYPE_CHECKING:
        name: str
        ifc_definition_id: int
        location: str
        scale: float
        is_visible: bool
        is_clipped: bool
        is_loaded: bool
        has_clipbox: bool


class BIMPointCloudProperties(PropertyGroup):
    is_editing: BoolProperty(name="Is Editing", default=False)
    point_clouds: CollectionProperty(name="Point Clouds", type=PointCloud)
    active_point_cloud_index: IntProperty(name="Active Point Cloud Index")

    if TYPE_CHECKING:
        is_editing: bool
        point_clouds: bpy.types.bpy_prop_collection_idprop[PointCloud]
        active_point_cloud_index: int

    @property
    def active_point_cloud(self) -> Union[PointCloud, None]:
        return tool.Blender.get_active_uilist_element(self.point_clouds, self.active_point_cloud_index)
