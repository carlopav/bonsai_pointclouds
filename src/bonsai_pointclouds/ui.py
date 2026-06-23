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

import bpy
import bonsai.tool as tool
from bpy.types import Panel, UIList
from .tool import PointCloud
from .data import PointCloudsData
from .prop import BIMPointCloudProperties, PointCloud as PointCloudItem


class BIM_PT_tab_point_clouds(Panel):
    bl_idname = "BIM_PT_tab_point_clouds"
    bl_label = "Point Clouds"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_order = 2
    bim_tab_name = "DRAWINGS"

    @classmethod
    def poll(cls, context):
        return tool.Blender.should_show_panel(context, cls.bim_tab_name, cls.bl_idname) and tool.Ifc.get()

    def draw(self, context):
        pass


class BIM_PT_point_clouds(Panel):
    bl_label = "Point Clouds"
    bl_idname = "BIM_PT_point_clouds"
    bl_options = {"HIDE_HEADER"}
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_point_clouds"

    def draw(self, context):
        if not PointCloudsData.is_loaded:
            PointCloudsData.load()

        if not PointCloudsData.data["has_saved_ifc"]:
            row = self.layout.row()
            row.label(text="No IFC Project Loaded/Saved", icon="ERROR")
            return

        self.props = PointCloud.get_pointcloud_props()

        row = self.layout.row(align=True)
        row.label(text="{} Point Clouds found".format(len(PointCloudsData.data["point_clouds"])), icon="OUTLINER_OB_POINTCLOUD")

        if self.props.is_editing:
            row.operator("bonsai_pointclouds.add_point_cloud", text="", icon="ADD")
            active = self.props.active_point_cloud
            load = row.row(align=True)
            load.enabled = active is not None
            load_op = load.operator("bonsai_pointclouds.load_point_cloud_data", text="", icon="IMPORT")
            if active is not None:
                load_op.point_cloud = active.ifc_definition_id
            align = row.row(align=True)
            align.enabled = active is not None
            align_op = align.operator("bonsai_pointclouds.align_clip_to_view", text="", icon="VIEW_CAMERA")
            if active is not None:
                align_op.point_cloud = active.ifc_definition_id
            row.operator("bonsai_pointclouds.disable_editing", text="", icon="CANCEL")
        else:
            row.operator("bonsai_pointclouds.load_point_clouds", text="", icon="IMPORT")
            return

        self.layout.template_list(
            "BIM_UL_point_clouds",
            "",
            self.props,
            "point_clouds",
            self.props,
            "active_point_cloud_index",
        )

        # Per-cloud settings shown below the list for the selected entry.
        active = self.props.active_point_cloud
        if active is not None:
            box = self.layout.box()
            col = box.column(align=True)
            col.prop(active, "point_size")
            col.prop(active, "opacity")
            col.prop(active, "draw_on_top")


class BIM_UL_point_clouds(UIList):
    def draw_item(
        self,
        context,
        layout: bpy.types.UILayout,
        data: BIMPointCloudProperties,
        item: PointCloudItem,
        icon,
        active_data,
        active_propname,
    ) -> None:
        if not item:
            return

        row = layout.row(align=True)
        row.label(text=item.name, icon="OUTLINER_OB_POINTCLOUD" if item.is_loaded else "OUTLINER_DATA_POINTCLOUD")

        vis_op = row.operator(
            "bonsai_pointclouds.toggle_visibility",
            text="",
            icon="HIDE_OFF" if item.is_visible else "HIDE_ON",
        )
        vis_op.point_cloud = item.ifc_definition_id
        vis_op.is_visible = not item.is_visible

        # Clipping is available for both PCV and the GPU viewer.
        if item.has_clipbox:
            clip_op = row.operator("bonsai_pointclouds.select_clip_box", text="", icon="MESH_CUBE")
        else:
            clip_op = row.operator("bonsai_pointclouds.create_clip_box", text="", icon="MESH_CUBE")
        clip_op.point_cloud = item.ifc_definition_id

        toggle_clip = row.operator(
            "bonsai_pointclouds.toggle_clipping",
            text="",
            icon="CLIPUV_HLT" if item.is_clipped else "CLIPUV_DEHLT",
        )
        toggle_clip.point_cloud = item.ifc_definition_id
        toggle_clip.is_clipped = not item.is_clipped

        remove_op = row.operator("bonsai_pointclouds.remove_point_cloud", text="", icon="X")
        remove_op.point_cloud = item.ifc_definition_id
