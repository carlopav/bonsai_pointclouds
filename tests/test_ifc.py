"""Tests for the IFC document pattern used by bonsai_pointclouds.

tool.py drives ifcopenshell through bonsai's tool.Ifc.run() — which is a thin
wrapper around ifcopenshell.api.run().  These tests exercise the same API calls
directly, without Blender, to verify the IFC model structure we produce.

We also inline get_location() / remove_documents() logic (4-line functions that
are pure ifcopenshell) so they can run outside Blender.
"""
import ifcopenshell
import ifcopenshell.api
import pytest

# const.py has no Blender dependency — import it directly
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src" / "bonsai_pointclouds"))
import const


# ---------------------------------------------------------------------------
# Helpers that mirror tool.py without the bonsai.tool wrapper
# ---------------------------------------------------------------------------

def _create_ifc4() -> ifcopenshell.file:
    ifc = ifcopenshell.file(schema="IFC4")
    ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Test")
    return ifc


def _create_ifc2x3() -> ifcopenshell.file:
    ifc = ifcopenshell.file(schema="IFC2X3")
    ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Test")
    return ifc


def _add_annotation(ifc: ifcopenshell.file, name: str) -> ifcopenshell.entity_instance:
    """Replicate create_annotation (without placement/container for isolation)."""
    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcAnnotation", name=name)
    element.ObjectType = const.ANNOTATION_OBJECT_TYPE
    return element


def _add_document_reference(
    ifc: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    location: str,
) -> None:
    """Replicate add_document_reference (without CreationTime for schema-neutral test)."""
    ref_name = f"{const.DOCUMENT_REF_PREFIX}{element.Name}"
    information = ifcopenshell.api.run("document.add_information", ifc)
    information.Name = ref_name
    reference = ifcopenshell.api.run("document.add_reference", ifc, information=information)
    reference.Name = ref_name
    reference.Location = location
    ifcopenshell.api.run("document.assign_document", ifc, products=[element], document=reference)


def _get_location(element: ifcopenshell.entity_instance) -> str:
    """Inline of tool.PointCloud.get_location() — pure ifcopenshell."""
    for rel in getattr(element, "HasAssociations", []):
        if rel.is_a("IfcRelAssociatesDocument"):
            location = getattr(rel.RelatingDocument, "Location", None)
            if location:
                return location
    return ""


def _remove_documents(
    ifc: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
) -> None:
    """Inline of tool.PointCloud.remove_documents() — pure ifcopenshell."""
    for rel in list(getattr(element, "HasAssociations", [])):
        if not rel.is_a("IfcRelAssociatesDocument"):
            continue
        reference = rel.RelatingDocument
        information = reference.ReferencedDocument  # IFC4 only in this test
        if information:
            ifcopenshell.api.run("document.remove_information", ifc, information=information)
        else:
            ifcopenshell.api.run("document.remove_reference", ifc, reference=reference)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ifc():
    return _create_ifc4()


@pytest.fixture
def element(ifc):
    return _add_annotation(ifc, "ScanA")


@pytest.fixture
def element_with_doc(ifc, element):
    _add_document_reference(ifc, element, "./clouds/scan_a.ply")
    return element


# ---------------------------------------------------------------------------
# IfcAnnotation structure
# ---------------------------------------------------------------------------

def test_annotation_ifc_class(element):
    assert element.is_a("IfcAnnotation")


def test_annotation_object_type(element):
    assert element.ObjectType == const.ANNOTATION_OBJECT_TYPE


def test_annotation_name(element):
    assert element.Name == "ScanA"


# ---------------------------------------------------------------------------
# Document reference structure
# ---------------------------------------------------------------------------

def test_document_reference_naming(ifc, element):
    _add_document_reference(ifc, element, "./clouds/scan_a.ply")
    refs = ifc.by_type("IfcDocumentReference")
    assert len(refs) == 1
    assert refs[0].Name == f"{const.DOCUMENT_REF_PREFIX}ScanA"


def test_document_information_naming(ifc, element):
    _add_document_reference(ifc, element, "./clouds/scan_a.ply")
    infos = ifc.by_type("IfcDocumentInformation")
    assert len(infos) == 1
    assert infos[0].Name == f"{const.DOCUMENT_REF_PREFIX}ScanA"


def test_document_reference_location(ifc, element):
    _add_document_reference(ifc, element, "./clouds/scan_a.ply")
    refs = ifc.by_type("IfcDocumentReference")
    assert refs[0].Location == "./clouds/scan_a.ply"


def test_association_links_element_to_reference(ifc, element):
    _add_document_reference(ifc, element, "./clouds/scan_a.ply")
    rels = [r for r in element.HasAssociations if r.is_a("IfcRelAssociatesDocument")]
    assert len(rels) == 1
    assert rels[0].RelatingDocument.is_a("IfcDocumentReference")


# ---------------------------------------------------------------------------
# get_location
# ---------------------------------------------------------------------------

def test_get_location_returns_path(element_with_doc):
    assert _get_location(element_with_doc) == "./clouds/scan_a.ply"


def test_get_location_empty_without_document(element):
    assert _get_location(element) == ""


def test_get_location_multiple_clouds_independent(ifc):
    el_a = _add_annotation(ifc, "ScanA")
    el_b = _add_annotation(ifc, "ScanB")
    _add_document_reference(ifc, el_a, "./clouds/a.ply")
    _add_document_reference(ifc, el_b, "./clouds/b.ply")
    assert _get_location(el_a) == "./clouds/a.ply"
    assert _get_location(el_b) == "./clouds/b.ply"


# ---------------------------------------------------------------------------
# remove_documents
# ---------------------------------------------------------------------------

def test_remove_documents_clears_association(ifc, element_with_doc):
    _remove_documents(ifc, element_with_doc)
    rels = [r for r in getattr(element_with_doc, "HasAssociations", [])
            if r.is_a("IfcRelAssociatesDocument")]
    assert len(rels) == 0


def test_remove_documents_removes_reference_from_model(ifc, element_with_doc):
    _remove_documents(ifc, element_with_doc)
    assert len(ifc.by_type("IfcDocumentReference")) == 0


def test_remove_documents_removes_information_from_model(ifc, element_with_doc):
    _remove_documents(ifc, element_with_doc)
    assert len(ifc.by_type("IfcDocumentInformation")) == 0


def test_remove_documents_location_returns_empty(ifc, element_with_doc):
    _remove_documents(ifc, element_with_doc)
    assert _get_location(element_with_doc) == ""


def test_remove_documents_does_not_affect_other_clouds(ifc):
    el_a = _add_annotation(ifc, "ScanA")
    el_b = _add_annotation(ifc, "ScanB")
    _add_document_reference(ifc, el_a, "./clouds/a.ply")
    _add_document_reference(ifc, el_b, "./clouds/b.ply")
    _remove_documents(ifc, el_a)
    assert _get_location(el_b) == "./clouds/b.ply"


# ---------------------------------------------------------------------------
# IFC2X3 schema: CreationTime must not be set (attribute does not exist)
# ---------------------------------------------------------------------------

def test_ifc4_creation_time_accepts_iso_string():
    # In IFC4, CreationTime is IfcDateTime (a string) — we set it freely.
    ifc = ifcopenshell.file(schema="IFC4")
    info = ifc.create_entity("IfcDocumentInformation", Identification="X", Name="Test")
    info.CreationTime = "2026-01-01T10:00:00"
    assert info.CreationTime == "2026-01-01T10:00:00"


def test_ifc2x3_uses_document_id_attribute():
    # In IFC2X3, the primary identifier is DocumentId; IFC4 uses Identification.
    # This schema difference is why our code checks get_schema() before
    # setting CreationTime (which in IFC2X3 expects IfcDateAndTime, not a string).
    ifc = ifcopenshell.file(schema="IFC2X3")
    info = ifc.create_entity("IfcDocumentInformation", DocumentId="X", Name="Test")
    assert hasattr(info, "DocumentId")
    assert not hasattr(info, "Identification")
