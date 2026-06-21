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

"""Naming conventions, IFC schema mapping and PCV API constants.

The IFC data is persistent. Each point cloud is stored as an IfcAnnotation
(rooted product, carries placement and a property set) with an associated
IfcDocumentReference holding the file path. The clip box is a Blender object
driving PCV's clipping; only its enabled state is persisted in the pset.
"""

# IFC schema mapping
ANNOTATION_OBJECT_TYPE = "PointCloud"
CLIPBOX_OBJECT_TYPE = "PointCloudClip"

PSET_NAME = "Pset_PointCloud_120g"
# Property keys stored in PSET_NAME on the point cloud IfcAnnotation.
PROP_LOCATION = "Location"  # file path, relative to the IFC file
PROP_SCALE = "Scale"
PROP_SCAN_DATE = "ScanDate"
PROP_IS_VISIBLE = "IsVisible"
PROP_IS_CLIPPED = "IsClipped"

# Blender object naming derived from the IFC element id.
HOST_OBJECT_PREFIX = "PointCloud"
CLIPBOX_OBJECT_PREFIX = "PointCloudClip"

# Point Cloud Visualizer v3 (Jakub Uhlik) public API. Drive PCV only through
# these; never modify or redistribute its source.
# PCV may be installed either as a legacy add-on or as an extension, so the
# import path differs; try each in order.
PCV_IMPORT_PATHS = (
    "point_cloud_visualizer",
    "bl_ext.user_default.point_cloud_visualizer",
)
PCV_PROPERTY_GROUP = "point_cloud_visualizer"
PCV_SHADER_GROUP = "shader"

# Clip planes are derived from a bounding box object assigned to the shader.
PCV_CLIP_BBOX_OBJECT_PROP = "clip_planes_from_bbox_object"
PCV_CLIP_BBOX_LIVE_PROP = "clip_planes_from_bbox_object_live"
PCV_CLIP_ENABLED_PROP = "clip_enabled"

# Supported point cloud formats mapped to PCV file types.
PCV_FORMAT_MAPPING = {
    ".ply": "PLY",
    ".las": "LAS",
    ".laz": "LAS",
    ".e57": "E57",
}

DEFAULT_SCALE = 1.0
