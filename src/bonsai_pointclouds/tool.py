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
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import bonsai.tool as tool
from datetime import datetime
from mathutils import Matrix
from pathlib import Path
from typing import Optional
from . import const
from .data import PointCloudsData
from .viewer import PointCloudViewer, read_ply


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

        # Preserve per-cloud render settings across a refresh so the user does
        # not lose their point_size/opacity/draw_on_top when re-importing.
        saved = {
            item.ifc_definition_id: {
                "point_size": item.point_size,
                "opacity": item.opacity,
                "draw_on_top": item.draw_on_top,
            }
            for item in props.point_clouds
        }

        props.point_clouds.clear()
        for pointcloud in PointCloudsData.data["point_clouds"]:
            new = props.point_clouds.add()
            new.ifc_definition_id = pointcloud["ifc_definition_id"]
            new.name = pointcloud["name"]
            element = tool.Ifc.get().by_id(new.ifc_definition_id)
            host = cls.get_host_object(element)
            new.is_loaded = host is not None
            new.has_clipbox = cls.get_clipbox_object(element) is not None
            new.is_visible = cls.get_is_visible(element)
            new.is_clipped = cls.get_is_clipped(element)
            # Restore render settings saved before the clear.
            if new.ifc_definition_id in saved:
                s = saved[new.ifc_definition_id]
                new.point_size = s["point_size"]
                new.opacity = s["opacity"]
                new.draw_on_top = s["draw_on_top"]
            # Link the prop item to its host object so update callbacks work.
            if host is not None:
                new.host_obj_name = host.name

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
        # Contain it in a spatial structure (default IfcSite) so it is not left
        # "unsorted" — otherwise Bonsai hides it when a drawing view is active.
        container = cls.get_default_container()
        if container is not None:
            tool.Ifc.run("spatial.assign_container", products=[element], relating_structure=container)
        cls.add_document_reference(element, location)
        return element

    @classmethod
    def get_default_container(cls) -> Optional[ifcopenshell.entity_instance]:
        """Return a spatial element to contain new point clouds (prefer IfcSite)."""
        ifc = tool.Ifc.get()
        for ifc_class in ("IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace"):
            elements = ifc.by_type(ifc_class)
            if elements:
                return elements[0]
        return None

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
        # When turning the cloud back on, also undo any object-level hiding from
        # an active drawing view (PCV won't draw a hidden object).
        if is_visible:
            cls.show_host(obj)
        pcv = cls.get_pcv_module()
        if pcv is not None and obj.name in pcv.mechanist.PCVMechanist.cache:
            pcv.mechanist.PCVMechanist.cache[obj.name]["draw"] = is_visible
            pcv.mechanist.PCVMechanist.tag_redraw()
        elif PointCloudViewer.exists(obj.name):
            PointCloudViewer.set_draw(obj.name, is_visible)

    @classmethod
    def show_host(cls, host: bpy.types.Object) -> None:
        """Ensure the host object is visible in the viewport (drawing views may hide it)."""
        host.hide_viewport = False
        try:
            host.hide_set(False)
        except RuntimeError:
            # Object not in the active view layer; nothing more we can do safely.
            pass

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
        """Whether clipping is currently enabled for the cloud (session-only)."""
        obj = cls.get_host_object(element)
        if obj is None:
            return False
        if PointCloudViewer.exists(obj.name):
            entry = PointCloudViewer.clouds.get(obj.name)
            return bool(entry and entry.get("clip_enabled", False))
        shader = cls.get_pcv_shader(obj)
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
        # The module may be importable while the add-on is disabled; only treat
        # PCV as available once its property group is registered on objects.
        if not hasattr(bpy.types.Object, const.PCV_PROPERTY_GROUP):
            return None
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
            # Place it in the right Bonsai collection (matching its IFC container)
            # so the spatial outliner reflects it.
            tool.Collector.assign(obj)
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
        # A drawing view may have hidden the host; make sure it is visible.
        cls.show_host(obj)
        # Drop any previous representation so switching backends (or reloading)
        # never leaves two clouds on the same host.
        cls.clear_representations(obj)
        pcv = cls.get_pcv_module()
        if pcv is not None:
            return cls._load_with_pcv(pcv, obj, filepath, filetype)
        return cls._load_with_viewer(obj, filepath, filetype)

    @classmethod
    def clear_representations(cls, obj: bpy.types.Object) -> None:
        """Remove this host's cloud from both backends (PCV cache and our viewer)."""
        PointCloudViewer.remove(obj.name)
        pcv = cls.get_pcv_module()
        if pcv is not None and obj.name in pcv.mechanist.PCVMechanist.cache:
            del pcv.mechanist.PCVMechanist.cache[obj.name]
            pcv.mechanist.PCVMechanist.tag_redraw()

    @classmethod
    def _load_with_pcv(cls, pcv, obj, filepath: str, filetype: str) -> Optional[str]:
        pcv_props = getattr(obj, const.PCV_PROPERTY_GROUP)
        pcv_props.data.filepath = bpy.path.abspath(filepath)
        pcv_props.data.filetype = filetype
        pd = pcv.mechanist.PCVStoker.load(pcv_props, operator=None)
        if not pd:
            return "PCV could not read the point cloud data"
        pcv.mechanist.PCVMechanist.init()
        pcv.mechanist.PCVMechanist.data(obj, pd, draw=True)
        pcv.mechanist.PCVMechanist.tag_redraw()
        # Link prop item to host object; apply saved opacity to the viewer.
        ifc_id = obj.get(LINK_PROP)
        if ifc_id is not None:
            props = cls.get_pointcloud_props()
            for item in props.point_clouds:
                if item.ifc_definition_id == ifc_id:
                    item.host_obj_name = obj.name
                    from .prop import _try_set_pcv
                    _try_set_pcv(obj, "point_size", item.point_size)
                    _try_set_pcv(obj, "alpha", item.opacity)
                    break
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
        # Set host_obj_name so prop-lookup callbacks work; apply saved opacity.
        # point_size and draw_on_top are read directly from props at draw time.
        ifc_id = obj.get(LINK_PROP)
        if ifc_id is not None:
            props = cls.get_pointcloud_props()
            for item in props.point_clouds:
                if item.ifc_definition_id == ifc_id:
                    item.host_obj_name = obj.name
                    if item.opacity < 1.0:
                        PointCloudViewer.set_opacity(obj.name, item.opacity)
                    break
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
    def _ensure_clip_cube(cls, element: ifcopenshell.entity_instance) -> bpy.types.Object:
        """Return the session-only clip box object (a unit cube), creating it if needed."""
        cube = cls.get_clipbox_object(element)
        if cube is None:
            mesh = bpy.data.meshes.new(f"{const.CLIPBOX_OBJECT_PREFIX}/{element.Name}")
            cube = bpy.data.objects.new(mesh.name, mesh)
            cube[LINK_PROP] = element.id()
            cube["is_clipbox"] = True
            bpy.context.scene.collection.objects.link(cube)
            cls._build_unit_cube(mesh)
        cube.display_type = "WIRE"
        cube.show_in_front = True
        cube.hide_render = True
        return cube

    @classmethod
    def create_clip_box(cls, element: ifcopenshell.entity_instance) -> bool:
        """Create a default cube clip box at the cloud location and feed it to PCV.

        The clip box is a session-only Blender object; it is not persisted in IFC.
        """
        host = cls.get_host_object(element)
        if host is None:
            return False
        cube = cls._ensure_clip_cube(element)
        s = const.CLIPBOX_SIZE
        cube.matrix_world = Matrix.Translation(host.matrix_world.translation) @ Matrix.Diagonal((s, s, s, 1.0))
        return cls.set_clipping(element, True)

    @classmethod
    def align_clip_to_view(cls, element: ifcopenshell.entity_instance, depth: float = const.CLIPBOX_VIEW_DEPTH) -> Optional[str]:
        """Align the clip box to the active orthographic drawing camera.

        The box takes the camera's view extent (width x height) and a shallow
        ``depth`` slab at the cut plane. Returns None on success, else an error.
        """
        host = cls.get_host_object(element)
        if host is None:
            return "Load the point cloud first"
        cam = bpy.context.scene.camera
        if cam is None or cam.type != "CAMERA" or cam.data.type != "ORTHO":
            return "No active orthographic drawing view"
        # The drawing view may have hidden the host; PCV won't draw a hidden
        # object, so make sure it is visible.
        cls.show_host(host)
        width, height = cls._camera_view_extent(cam)
        existing = cls.get_clipbox_object(element)
        cube = cls._ensure_clip_cube(element)
        # Aligning to the view is temporary: remember the previous clip box so it
        # can be restored when clipping is turned off.
        if not cube.get("pcv_view_aligned"):
            cube["pcv_has_saved"] = existing is not None
            if existing is not None:
                cls._save_matrix(cube)
            cube["pcv_view_aligned"] = True
        center_z = -(cam.data.clip_start + depth / 2.0)
        cube.matrix_world = (
            cam.matrix_world
            @ Matrix.Translation((0.0, 0.0, center_z))
            @ Matrix.Diagonal((width, height, depth, 1.0))
        )
        if not cls.set_clipping(element, True):
            return "Clipping requires the Point Cloud Visualizer add-on"
        return None

    @staticmethod
    def _camera_view_extent(cam: bpy.types.Object) -> tuple[float, float]:
        """World-space (width, height) of an orthographic camera's view rectangle."""
        scene = bpy.context.scene
        rx, ry = scene.render.resolution_x, scene.render.resolution_y
        ortho = cam.data.ortho_scale
        if rx >= ry:
            return ortho, ortho * (ry / rx)
        return ortho * (rx / ry), ortho

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
        if host is None:
            return False
        cube = cls.get_clipbox_object(element)
        if is_clipped and cube is None:
            return False

        # Our viewer backend.
        if PointCloudViewer.exists(host.name):
            PointCloudViewer.set_clip(host.name, cube if is_clipped else None, is_clipped)
            return True

        # PCV backend.
        shader = cls.get_pcv_shader(host)
        if shader is None:
            return False
        # Disabling clipping ends a temporary view alignment: restore the
        # previous clip box transform if there was one.
        if not is_clipped and cube is not None and cube.get("pcv_view_aligned"):
            if cube.get("pcv_has_saved"):
                cls._restore_matrix(cube)
            cube["pcv_view_aligned"] = False
        setattr(shader, const.PCV_CLIP_BBOX_OBJECT_PROP, cube if is_clipped else None)
        setattr(shader, const.PCV_CLIP_BBOX_LIVE_PROP, is_clipped)
        setattr(shader, const.PCV_CLIP_ENABLED_PROP, is_clipped)
        return True

    @staticmethod
    def _save_matrix(obj: bpy.types.Object) -> None:
        obj["pcv_saved_matrix"] = [v for row in obj.matrix_world for v in row]

    @staticmethod
    def _restore_matrix(obj: bpy.types.Object) -> None:
        m = obj.get("pcv_saved_matrix")
        if m:
            m = list(m)
            obj.matrix_world = Matrix((m[0:4], m[4:8], m[8:12], m[12:16]))

    @staticmethod
    def _build_unit_cube(mesh: bpy.types.Mesh) -> None:
        h = 0.5
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
