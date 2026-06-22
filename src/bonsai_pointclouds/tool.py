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
import os
import importlib
import bpy
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import bonsai.tool as tool
from datetime import datetime
from mathutils import Matrix
from pathlib import Path
from typing import Optional, Union
from . import const
from .data import PointCloudsData
from .viewer import PointCloudViewer, read_ply

# Side length of the clip box mesh cube, in metres.
CLIPBOX_SIZE = 3.0


# A custom Blender object property links a viewport object back to its IFC element.
LINK_PROP = "bonsai_pointcloud_id"


class PointCloud:
    # Properties -------------------------------------------------------------

    @classmethod
    def get_pointcloud_props(cls) -> "BIMPointCloudProperties":
        return bpy.context.scene.BIMPointCloudProperties

    @classmethod
    def has_pcv(cls) -> bool:
        return cls.get_pcv_module() is not None

    @classmethod
    def import_point_clouds(cls) -> None:
        PointCloudsData.load()
        props = cls.get_pointcloud_props()
        props.has_pcv = cls.has_pcv()
        props.point_clouds.clear()
        for pointcloud in PointCloudsData.data["point_clouds"]:
            new = props.point_clouds.add()
            new.ifc_definition_id = pointcloud["ifc_definition_id"]
            new.name = pointcloud["name"]
            new.location = pointcloud["location"]
            element = tool.Ifc.get().by_id(new.ifc_definition_id)
            new.is_loaded = cls.get_host_object(element) is not None
            new.has_clipbox = cls.get_clipbox_object(element) is not None
            new.is_visible = cls.get_is_visible(element)
            new.is_clipped = cls.get_is_clipped(element)

    @classmethod
    def set_is_editing(cls, is_editing: bool) -> None:
        cls.get_pointcloud_props().is_editing = is_editing

    # IFC --------------------------------------------------------------------

    @classmethod
    def create_annotation(cls, name: str, location: str) -> ifcopenshell.entity_instance:
        element = tool.Ifc.run("root.create_entity", ifc_class="IfcAnnotation", name=name)
        element.ObjectType = const.ANNOTATION_OBJECT_TYPE
        # Give the annotation an (identity) placement so its position is persisted.
        tool.Ifc.run("geometry.edit_object_placement", product=element)
        cls.add_document_reference(element, location)
        return element

    @classmethod
    def add_document_reference(cls, element: ifcopenshell.entity_instance, location: str) -> None:
        ref_name = f"{const.DOCUMENT_REF_PREFIX}{element.Name}"
        information = tool.Ifc.run("document.add_information")
        information.Name = ref_name
        if tool.Ifc.get_schema() != "IFC2X3":
            information.CreationTime = datetime.now().isoformat(timespec="seconds")
        reference = tool.Ifc.run("document.add_reference", information=information)
        reference.Name = ref_name
        reference.Location = location
        tool.Ifc.run("document.assign_document", products=[element], document=reference)

    @classmethod
    def get_location(cls, element: ifcopenshell.entity_instance) -> str:
        """Read the file path from the associated IfcDocumentReference."""
        for rel in getattr(element, "HasAssociations", []):
            if rel.is_a("IfcRelAssociatesDocument"):
                location = getattr(rel.RelatingDocument, "Location", None)
                if location:
                    return location
        return ""

    @classmethod
    def remove_documents(cls, element: ifcopenshell.entity_instance) -> None:
        """Remove the document reference(s) and information associated with the element."""
        for rel in getattr(element, "HasAssociations", []):
            if not rel.is_a("IfcRelAssociatesDocument"):
                continue
            reference = rel.RelatingDocument
            if tool.Ifc.get_schema() == "IFC2X3":
                information = (reference.ReferenceToDocument or [None])[0]
            else:
                information = reference.ReferencedDocument
            if information:
                tool.Ifc.run("document.remove_information", information=information)
            else:
                tool.Ifc.run("document.remove_reference", reference=reference)

    @classmethod
    def remove_annotation(cls, element: ifcopenshell.entity_instance) -> None:
        tool.Ifc.run("root.remove_product", product=element)

    # Blender / viewport objects --------------------------------------------

    @classmethod
    def get_host_object(cls, element: ifcopenshell.entity_instance) -> Optional[bpy.types.Object]:
        for obj in bpy.context.scene.objects:
            if obj.get(LINK_PROP) == element.id() and not obj.get("is_clipbox"):
                return obj
        return None

    @classmethod
    def get_clipbox_object(cls, element: ifcopenshell.entity_instance) -> Optional[bpy.types.Object]:
        for obj in bpy.context.scene.objects:
            if obj.get(LINK_PROP) == element.id() and obj.get("is_clipbox"):
                return obj
        return None

    @classmethod
    def remove_objects(cls, element: ifcopenshell.entity_instance) -> None:
        host = cls.get_host_object(element)
        if host is not None:
            PointCloudViewer.remove(host.name)
        for obj in (host, cls.get_clipbox_object(element)):
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)

    @classmethod
    def set_visibility(cls, element: ifcopenshell.entity_instance, is_visible: bool) -> None:
        """Show/hide the cloud via the active backend (PCV erase, or our viewer draw flag)."""
        obj = cls.get_host_object(element)
        if obj is None:
            return
        pcv = cls.get_pcv_module()
        if pcv is not None and obj.name in pcv.mechanist.PCVMechanist.cache:
            pcv.mechanist.PCVMechanist.cache[obj.name]["draw"] = is_visible
            pcv.mechanist.PCVMechanist.tag_redraw()
        elif PointCloudViewer.exists(obj.name):
            PointCloudViewer.set_draw(obj.name, is_visible)

    @classmethod
    def get_is_visible(cls, element: ifcopenshell.entity_instance) -> bool:
        """Current draw state of the cloud (session-only, defaults to True)."""
        obj = cls.get_host_object(element)
        if obj is None:
            return True
        pcv = cls.get_pcv_module()
        if pcv is not None and obj.name in pcv.mechanist.PCVMechanist.cache:
            return bool(pcv.mechanist.PCVMechanist.cache[obj.name]["draw"])
        if PointCloudViewer.exists(obj.name):
            return PointCloudViewer.is_drawn(obj.name)
        return True

    @classmethod
    def get_is_clipped(cls, element: ifcopenshell.entity_instance) -> bool:
        """Whether PCV clipping is currently enabled for the cloud (session-only)."""
        obj = cls.get_host_object(element)
        shader = cls.get_pcv_shader(obj) if obj else None
        if shader is None:
            return False
        return bool(getattr(shader, const.PCV_CLIP_ENABLED_PROP, False))

    # Path resolution --------------------------------------------------------

    @classmethod
    def get_ifc_directory(cls) -> str:
        return os.path.dirname(tool.Ifc.get_path())

    @classmethod
    def get_relative_location(cls, filepath: str) -> str:
        ifc_dir = cls.get_ifc_directory()
        try:
            relative = os.path.relpath(filepath, ifc_dir)
            return "./" + relative.replace("\\", "/")
        except ValueError:
            return Path(filepath).resolve().as_posix()

    @classmethod
    def get_absolute_location(cls, location: str) -> str:
        path = Path(location)
        if path.is_absolute():
            return str(path)
        return str((Path(cls.get_ifc_directory()) / location).resolve())

    @classmethod
    def get_filetype(cls, filepath: str) -> Optional[str]:
        return const.PCV_FORMAT_MAPPING.get(Path(filepath).suffix.lower())

    # PCV --------------------------------------------------------------------

    @classmethod
    def get_pcv_module(cls):
        for path in const.PCV_IMPORT_PATHS:
            try:
                return importlib.import_module(path)
            except ModuleNotFoundError:
                continue
        return None

    @classmethod
    def get_pcv_shader(cls, obj: bpy.types.Object):
        props = getattr(obj, const.PCV_PROPERTY_GROUP, None)
        if props is None:
            return None
        return getattr(props, const.PCV_SHADER_GROUP, None)

    @classmethod
    def ensure_host(cls, element: ifcopenshell.entity_instance) -> bpy.types.Object:
        """Return the host Empty for the cloud, creating and placing it if needed."""
        obj = cls.get_host_object(element)
        if obj is None:
            obj = bpy.data.objects.new(f"{const.HOST_OBJECT_PREFIX}/{element.Name}", None)
            obj[LINK_PROP] = element.id()
            bpy.context.scene.collection.objects.link(obj)
            # Link to the IFC element so Bonsai manages and persists its placement.
            tool.Ifc.link(element, obj)
            obj.matrix_world = cls.get_element_matrix(element)
        return obj

    @classmethod
    def load(cls, element: ifcopenshell.entity_instance) -> Optional[str]:
        """Load the point cloud into the viewport, preferring PCV over our viewer.

        Returns None on success, or an error message describing what failed.
        """
        location = cls.get_location(element)
        if not location:
            return "No file path stored on this point cloud"
        filepath = cls.get_absolute_location(location)
        if not Path(filepath).exists():
            return f"File not found: {filepath}"
        filetype = cls.get_filetype(filepath)
        if not filetype:
            return f"Unsupported file type: {Path(filepath).suffix}"

        obj = cls.ensure_host(element)
        pcv = cls.get_pcv_module()
        if pcv is not None:
            return cls._load_with_pcv(pcv, obj, filepath, filetype)
        return cls._load_with_viewer(obj, filepath, filetype)

    @classmethod
    def _load_with_pcv(cls, pcv, obj, filepath: str, filetype: str) -> Optional[str]:
        props = getattr(obj, const.PCV_PROPERTY_GROUP)
        props.data.filepath = bpy.path.abspath(filepath)
        props.data.filetype = filetype
        pd = pcv.mechanist.PCVStoker.load(props, operator=None)
        if not pd:
            return "PCV could not read the point cloud data"
        pcv.mechanist.PCVMechanist.init()
        pcv.mechanist.PCVMechanist.data(obj, pd, draw=True)
        pcv.mechanist.PCVMechanist.tag_redraw()
        return None

    @classmethod
    def _load_with_viewer(cls, obj, filepath: str, filetype: str) -> Optional[str]:
        if filetype != "PLY":
            return f"{filetype} files require the Point Cloud Visualizer add-on"
        try:
            coords, colors = read_ply(filepath)
        except (ValueError, OSError) as e:
            return f"Could not read PLY: {e}"
        if coords is None or len(coords) == 0:
            return "No points found in file"
        PointCloudViewer.load(obj.name, coords, colors)
        return None

    @classmethod
    def get_element_matrix(cls, element: ifcopenshell.entity_instance) -> Matrix:
        """World matrix from the element placement (unit-scaled, no georef offset)."""
        if not element.ObjectPlacement:
            return Matrix()
        unit_scale = ifcopenshell.util.unit.calculate_unit_scale(tool.Ifc.get())
        matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
        matrix[0][3] *= unit_scale
        matrix[1][3] *= unit_scale
        matrix[2][3] *= unit_scale
        return Matrix(matrix.tolist())

    # Clipping ---------------------------------------------------------------

    @classmethod
    def create_clip_box(cls, element: ifcopenshell.entity_instance) -> bool:
        """Create a fixed 3 m clip box at the cloud location and feed it to PCV.

        The clip box is a session-only Blender object; it is not persisted in IFC.
        """
        host = cls.get_host_object(element)
        if host is None:
            return False

        cube = cls.get_clipbox_object(element)
        if cube is None:
            mesh = bpy.data.meshes.new(f"{const.CLIPBOX_OBJECT_PREFIX}/{element.Name}")
            cube = bpy.data.objects.new(mesh.name, mesh)
            cube[LINK_PROP] = element.id()
            cube["is_clipbox"] = True
            bpy.context.scene.collection.objects.link(cube)
            cls._build_cube(mesh, CLIPBOX_SIZE)

        cube.matrix_world.translation = host.matrix_world.translation
        cube.display_type = "WIRE"
        cube.show_in_front = True
        cube.hide_render = True

        return cls.set_clipping(element, True)

    @classmethod
    def select_clip_box(cls, element: ifcopenshell.entity_instance) -> bool:
        """Select the clip box (unhiding it if needed) and make it active."""
        cube = cls.get_clipbox_object(element)
        if cube is None:
            return False
        cube.hide_set(False)
        cube.hide_viewport = False
        bpy.ops.object.select_all(action="DESELECT")
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        return True

    @classmethod
    def set_clipping(cls, element: ifcopenshell.entity_instance, is_clipped: bool) -> bool:
        host = cls.get_host_object(element)
        shader = cls.get_pcv_shader(host) if host else None
        if shader is None:
            return False
        cube = cls.get_clipbox_object(element)
        if is_clipped and cube is None:
            return False
        setattr(shader, const.PCV_CLIP_BBOX_OBJECT_PROP, cube if is_clipped else None)
        setattr(shader, const.PCV_CLIP_BBOX_LIVE_PROP, is_clipped)
        setattr(shader, const.PCV_CLIP_ENABLED_PROP, is_clipped)
        return True

    @staticmethod
    def _build_cube(mesh: bpy.types.Mesh, size: float) -> None:
        h = size / 2.0
        verts = [
            (-h, -h, -h),
            (h, -h, -h),
            (h, h, -h),
            (-h, h, -h),
            (-h, -h, h),
            (h, -h, h),
            (h, h, h),
            (-h, h, h),
        ]
        faces = [
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
