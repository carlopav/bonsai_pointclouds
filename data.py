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
import ifcopenshell.util.element
import bonsai.tool as tool
from . import const


def refresh():
    PointCloudsData.is_loaded = False


class PointCloudsData:
    data = {}
    is_loaded = False

    @classmethod
    def load(cls):
        cls.data = {
            "has_saved_ifc": cls.has_saved_ifc(),
            "point_clouds": cls.point_clouds(),
        }
        cls.is_loaded = True

    @classmethod
    def has_saved_ifc(cls):
        return os.path.isfile(tool.Ifc.get_path())

    @classmethod
    def point_clouds(cls):
        results = []
        if not tool.Ifc.get():
            return results
        for element in tool.Ifc.get().by_type("IfcAnnotation"):
            if element.ObjectType != const.ANNOTATION_OBJECT_TYPE:
                continue
            pset = ifcopenshell.util.element.get_pset(element, const.PSET_NAME) or {}
            results.append(
                {
                    "ifc_definition_id": element.id(),
                    "name": element.Name or "Unnamed",
                    "location": pset.get(const.PROP_LOCATION, ""),
                    "scale": pset.get(const.PROP_SCALE, const.DEFAULT_SCALE),
                    "is_visible": pset.get(const.PROP_IS_VISIBLE, True),
                    "is_clipped": pset.get(const.PROP_IS_CLIPPED, False),
                }
            )
        return results
