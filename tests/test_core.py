"""Tests for core.py — pure orchestration logic, no bpy dependency.

Follows Bonsai's own core test convention: the tool class is a Mock, and
each test asserts which tool methods were called (and in what order, where
call order encodes a real invariant such as "refresh after mutating").
"""

import pathlib
import sys
from unittest.mock import Mock, call

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src" / "bonsai_pointclouds"))
import core

# ---------------------------------------------------------------------------
# load_point_clouds / disable_editing
# ---------------------------------------------------------------------------


def test_load_point_clouds_imports_then_enters_editing():
    point_cloud = Mock()
    core.load_point_clouds(point_cloud)
    assert point_cloud.mock_calls == [call.import_point_clouds(), call.set_is_editing(True)]


def test_disable_editing_sets_is_editing_false():
    point_cloud = Mock()
    core.disable_editing(point_cloud)
    point_cloud.set_is_editing.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# add_point_cloud
# ---------------------------------------------------------------------------


def test_add_point_cloud_creates_annotation_then_refreshes():
    point_cloud = Mock()
    element = point_cloud.create_annotation.return_value
    result = core.add_point_cloud(point_cloud, name="ScanA", location="./clouds/a.ply")
    point_cloud.create_annotation.assert_called_once_with(name="ScanA", location="./clouds/a.ply")
    point_cloud.import_point_clouds.assert_called_once()
    assert result is element


# ---------------------------------------------------------------------------
# remove_point_cloud
# ---------------------------------------------------------------------------


def test_remove_point_cloud_calls_in_order():
    point_cloud = Mock()
    element = Mock()
    core.remove_point_cloud(point_cloud, element)
    assert point_cloud.mock_calls == [
        call.remove_objects(element),
        call.remove_documents(element),
        call.remove_annotation(element),
        call.import_point_clouds(),
    ]


# ---------------------------------------------------------------------------
# load / unload
# ---------------------------------------------------------------------------


def test_load_refreshes_and_returns_error():
    point_cloud = Mock()
    point_cloud.load.return_value = "File not found"
    element = Mock()
    error = core.load(point_cloud, element)
    point_cloud.load.assert_called_once_with(element)
    point_cloud.import_point_clouds.assert_called_once()
    assert error == "File not found"


def test_load_returns_none_on_success():
    point_cloud = Mock()
    point_cloud.load.return_value = None
    assert core.load(point_cloud, Mock()) is None


def test_unload_syncs_item_after_unloading():
    point_cloud = Mock()
    element = Mock()
    core.unload(point_cloud, element)
    assert point_cloud.mock_calls == [call.unload(element), call.sync_item(element)]


# ---------------------------------------------------------------------------
# toggle_visibility
# ---------------------------------------------------------------------------


def test_toggle_visibility_sets_then_syncs():
    point_cloud = Mock()
    element = Mock()
    core.toggle_visibility(point_cloud, element, is_visible=False)
    assert point_cloud.mock_calls == [
        call.set_visibility(element, False),
        call.sync_item(element),
    ]


# ---------------------------------------------------------------------------
# create_clip_box
# ---------------------------------------------------------------------------


def test_create_clip_box_syncs_and_returns_result():
    point_cloud = Mock()
    point_cloud.create_clip_box.return_value = True
    element = Mock()
    result = core.create_clip_box(point_cloud, element)
    point_cloud.create_clip_box.assert_called_once_with(element)
    point_cloud.sync_item.assert_called_once_with(element)
    assert result is True


def test_create_clip_box_returns_false_when_tool_reports_failure():
    point_cloud = Mock()
    point_cloud.create_clip_box.return_value = False
    assert core.create_clip_box(point_cloud, Mock()) is False


# ---------------------------------------------------------------------------
# toggle_clipping
# ---------------------------------------------------------------------------


def test_toggle_clipping_syncs_and_returns_result():
    point_cloud = Mock()
    point_cloud.set_clipping.return_value = True
    element = Mock()
    result = core.toggle_clipping(point_cloud, element, is_clipped=True)
    point_cloud.set_clipping.assert_called_once_with(element, True)
    point_cloud.sync_item.assert_called_once_with(element)
    assert result is True


# ---------------------------------------------------------------------------
# align_clip_to_view
# ---------------------------------------------------------------------------


def test_align_clip_to_view_syncs_and_returns_error():
    point_cloud = Mock()
    point_cloud.align_clip_to_view.return_value = "No active orthographic drawing view"
    element = Mock()
    error = core.align_clip_to_view(point_cloud, element)
    point_cloud.align_clip_to_view.assert_called_once_with(element)
    point_cloud.sync_item.assert_called_once_with(element)
    assert error == "No active orthographic drawing view"


def test_align_clip_to_view_returns_none_on_success():
    point_cloud = Mock()
    point_cloud.align_clip_to_view.return_value = None
    assert core.align_clip_to_view(point_cloud, Mock()) is None


# ---------------------------------------------------------------------------
# export_geotiff
# ---------------------------------------------------------------------------


def test_export_geotiff_forwards_arguments_and_return_value():
    point_cloud = Mock()
    point_cloud.export_geotiff.return_value = ("/abs/path/out.tif", None)
    result = core.export_geotiff(
        point_cloud,
        filepath="out.tif",
        depth=0.05,
        resolution_mm=5.0,
        mode="L",
        background="BLACK",
    )
    point_cloud.export_geotiff.assert_called_once_with("out.tif", 0.05, 5.0, "L", "BLACK")
    assert result == ("/abs/path/out.tif", None)


def test_export_geotiff_propagates_error_tuple():
    point_cloud = Mock()
    point_cloud.export_geotiff.return_value = (None, "No active camera in the scene")
    result = core.export_geotiff(
        point_cloud,
        filepath="out.tif",
        depth=0.05,
        resolution_mm=5.0,
        mode="L",
        background="BLACK",
    )
    assert result == (None, "No active camera in the scene")
