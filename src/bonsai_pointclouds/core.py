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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ifcopenshell
    from .tool import PointCloud


def load_point_clouds(point_cloud: type[PointCloud]) -> None:
    point_cloud.import_point_clouds()
    point_cloud.set_is_editing(True)


def disable_editing(point_cloud: type[PointCloud]) -> None:
    point_cloud.set_is_editing(False)


def add_point_cloud(
    point_cloud: type[PointCloud],
    name: str,
    location: str,
) -> ifcopenshell.entity_instance:
    element = point_cloud.create_annotation(name=name, location=location)
    point_cloud.import_point_clouds()
    return element


def remove_point_cloud(
    point_cloud: type[PointCloud],
    element: ifcopenshell.entity_instance,
) -> None:
    point_cloud.remove_objects(element)
    point_cloud.remove_documents(element)
    point_cloud.remove_annotation(element)
    point_cloud.import_point_clouds()


def load(point_cloud: type[PointCloud], element: ifcopenshell.entity_instance) -> "str | None":
    error = point_cloud.load(element)
    point_cloud.import_point_clouds()
    return error


def toggle_visibility(
    point_cloud: type[PointCloud],
    element: ifcopenshell.entity_instance,
    is_visible: bool,
) -> None:
    point_cloud.set_visibility(element, is_visible)
    point_cloud.import_point_clouds()


def create_clip_box(
    point_cloud: type[PointCloud],
    element: ifcopenshell.entity_instance,
) -> bool:
    created = point_cloud.create_clip_box(element)
    point_cloud.import_point_clouds()
    return created


def toggle_clipping(
    point_cloud: type[PointCloud],
    element: ifcopenshell.entity_instance,
    is_clipped: bool,
) -> bool:
    applied = point_cloud.set_clipping(element, is_clipped)
    point_cloud.import_point_clouds()
    return applied


def align_clip_to_view(
    point_cloud: type[PointCloud],
    element: ifcopenshell.entity_instance,
) -> "str | None":
    error = point_cloud.align_clip_to_view(element)
    point_cloud.import_point_clouds()
    return error
