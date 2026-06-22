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

import os
import bpy
import bonsai.tool as tool
from . import core
from .tool import PointCloud


class LoadPointClouds(bpy.types.Operator):
    bl_idname = "bonsai_pointclouds.load_point_clouds"
    bl_label = "Load Point Clouds"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        core.load_point_clouds(PointCloud)
        return {"FINISHED"}


class DisableEditing(bpy.types.Operator):
    bl_idname = "bonsai_pointclouds.disable_editing"
    bl_label = "Disable Point Cloud Editing"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        core.disable_editing(PointCloud)
        return {"FINISHED"}


class AddPointCloud(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bonsai_pointclouds.add_point_cloud"
    bl_label = "Add Point Cloud"
    bl_options = {"REGISTER", "UNDO"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.ply;*.las;*.laz;*.e57", options={"HIDDEN"})
    name: bpy.props.StringProperty(name="Name", default="")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def _execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "No file selected")
            return {"CANCELLED"}
        name = self.name or os.path.splitext(os.path.basename(self.filepath))[0]
        location = PointCloud.get_relative_location(self.filepath)
        core.add_point_cloud(tool.Ifc, PointCloud, name=name, location=location)


class RemovePointCloud(bpy.types.Operator, tool.Ifc.Operator):
    bl_idname = "bonsai_pointclouds.remove_point_cloud"
    bl_label = "Remove Point Cloud"
    bl_options = {"REGISTER", "UNDO"}
    point_cloud: bpy.props.IntProperty()

    def _execute(self, context):
        element = tool.Ifc.get().by_id(self.point_cloud)
        core.remove_point_cloud(tool.Ifc, PointCloud, element)


class LoadPointCloudData(bpy.types.Operator):
    bl_idname = "bonsai_pointclouds.load_point_cloud_data"
    bl_label = "Load Point Cloud Into Viewport"
    bl_options = {"REGISTER", "UNDO"}
    point_cloud: bpy.props.IntProperty()

    def execute(self, context):
        element = tool.Ifc.get().by_id(self.point_cloud)
        error = core.load_pcv(PointCloud, element)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class TogglePointCloudVisibility(bpy.types.Operator):
    bl_idname = "bonsai_pointclouds.toggle_visibility"
    bl_label = "Toggle Point Cloud Visibility"
    bl_options = {"REGISTER", "UNDO"}
    point_cloud: bpy.props.IntProperty()
    is_visible: bpy.props.BoolProperty()

    def execute(self, context):
        element = tool.Ifc.get().by_id(self.point_cloud)
        core.toggle_visibility(PointCloud, element, self.is_visible)
        return {"FINISHED"}


class CreateClipBox(bpy.types.Operator):
    bl_idname = "bonsai_pointclouds.create_clip_box"
    bl_label = "Create Clip Box"
    bl_options = {"REGISTER", "UNDO"}
    point_cloud: bpy.props.IntProperty()

    def execute(self, context):
        element = tool.Ifc.get().by_id(self.point_cloud)
        if not core.create_clip_box(PointCloud, element):
            self.report({"ERROR"}, "Load the point cloud before creating a clip box")
            return {"CANCELLED"}
        return {"FINISHED"}


class SelectClipBox(bpy.types.Operator):
    bl_idname = "bonsai_pointclouds.select_clip_box"
    bl_label = "Select Clip Box"
    bl_options = {"REGISTER", "UNDO"}
    point_cloud: bpy.props.IntProperty()

    def execute(self, context):
        element = tool.Ifc.get().by_id(self.point_cloud)
        if not PointCloud.select_clip_box(element):
            self.report({"ERROR"}, "Clip box not found")
            return {"CANCELLED"}
        return {"FINISHED"}


class TogglePointCloudClipping(bpy.types.Operator):
    bl_idname = "bonsai_pointclouds.toggle_clipping"
    bl_label = "Toggle Point Cloud Clipping"
    bl_options = {"REGISTER", "UNDO"}
    point_cloud: bpy.props.IntProperty()
    is_clipped: bpy.props.BoolProperty()

    def execute(self, context):
        element = tool.Ifc.get().by_id(self.point_cloud)
        if not core.toggle_clipping(PointCloud, element, self.is_clipped):
            self.report({"WARNING"}, "No clip box available. Create one first.")
            return {"CANCELLED"}
        return {"FINISHED"}
