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
from bpy.app.handlers import persistent

from . import data, operator, prop, ui
from .viewer import PointCloudViewer

bl_info = {
    "name": "Bonsai Point Clouds",
    "description": "Bridge between Bonsai (IFC) and Point Cloud Visualizer (PCV)",
    "author": "Carlo Pavan",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Scene > Drawings and Documents > Point Clouds",
    "warning": "Requires the Bonsai and Point Cloud Visualizer add-ons",
    "category": "Bonsai",
    "doc_url": "https://github.com/carlopav/bonsai_pointclouds",
    "tracker_url": "https://github.com/carlopav/bonsai_pointclouds/issues",
}

classes = (
    prop.PointCloud,
    prop.BIMPointCloudProperties,
    operator.LoadPointClouds,
    operator.DisableEditing,
    operator.AddPointCloud,
    operator.RemovePointCloud,
    operator.LoadPointCloudData,
    operator.TogglePointCloudVisibility,
    operator.CreateClipBox,
    operator.SelectClipBox,
    operator.TogglePointCloudClipping,
    ui.BIM_PT_tab_point_clouds,
    ui.BIM_PT_point_clouds,
    ui.BIM_UL_point_clouds,
)


@persistent
def refresh_point_clouds(*args):
    data.refresh()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.BIMPointCloudProperties = bpy.props.PointerProperty(type=prop.BIMPointCloudProperties)
    bpy.app.handlers.undo_post.append(refresh_point_clouds)
    bpy.app.handlers.redo_post.append(refresh_point_clouds)
    bpy.app.handlers.load_post.append(refresh_point_clouds)
    PointCloudViewer.register()


def unregister():
    PointCloudViewer.unregister()
    for handler in (refresh_point_clouds,):
        for app_handler in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post, bpy.app.handlers.load_post):
            if handler in app_handler:
                app_handler.remove(handler)
    del bpy.types.Scene.BIMPointCloudProperties
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
