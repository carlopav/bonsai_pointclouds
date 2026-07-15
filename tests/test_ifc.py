"""Tests for the IFC document pattern used by bonsai_pointclouds.

tool.py drives ifcopenshell through bonsai's tool.Ifc.run() — which is a thin
wrapper around ifcopenshell.api.run().  These tests exercise the same API calls
directly, without Blender, to verify the IFC model structure we produce.

We also inline get_location() / remove_documents() logic (4-line functions that
are pure ifcopenshell) so they can run outside Blender.
"""

import pathlib
import sys

import ifcopenshell
import ifcopenshell.api
import pytest

# const.py has no Blender dependency — import it directly
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
    # IFC2X3 requires an owner history user/application before any root.create_entity call.
    person = ifcopenshell.api.run("owner.add_person", ifc)
    organisation = ifcopenshell.api.run("owner.add_organisation", ifc)
    ifcopenshell.api.run("owner.add_person_and_organisation", ifc, person=person, organisation=organisation)
    ifcopenshell.api.run("owner.add_application", ifc)
    ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Test")
    return ifc


def _add_annotation(ifc: ifcopenshell.file, name: str) -> ifcopenshell.entity_instance:
    """Replicate create_annotation (without placement/container for isolation)."""
    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcAnnotation", name=name)
    element.ObjectType = const.ANNOTATION_OBJECT_TYPE
    return element


def _get_parent_group(ifc: ifcopenshell.file) -> ifcopenshell.entity_instance:
    """Inline of tool.PointCloud.get_parent_group() — pure ifcopenshell."""
    for group in ifc.by_type("IfcGroup"):
        if group.Name == const.PARENT_NAME and group.ObjectType == const.PARENT_NAME:
            return group
    group = ifcopenshell.api.run("group.add_group", ifc)
    ifcopenshell.api.run(
        "group.edit_group",
        ifc,
        group=group,
        attributes={"Name": const.PARENT_NAME, "ObjectType": const.PARENT_NAME},
    )
    return group


def _get_parent_document(ifc: ifcopenshell.file) -> ifcopenshell.entity_instance:
    """Inline of tool.PointCloud.get_parent_document() — pure ifcopenshell."""
    for information in ifc.by_type("IfcDocumentInformation"):
        if information.Name == const.PARENT_NAME and information.Scope == const.PARENT_NAME:
            return information
    information = ifcopenshell.api.run("document.add_information", ifc)
    id_attribute = "DocumentId" if ifc.schema == "IFC2X3" else "Identification"
    ifcopenshell.api.run(
        "document.edit_information",
        ifc,
        information=information,
        attributes={id_attribute: const.PARENT_NAME, "Name": const.PARENT_NAME, "Scope": const.PARENT_NAME},
    )
    return information


def _add_document_reference(
    ifc: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    location: str,
) -> None:
    """Replicate add_document_reference (without CreationTime for schema-neutral test)."""
    ref_name = f"{const.DOCUMENT_REF_PREFIX}{element.Name}"
    information = ifcopenshell.api.run("document.add_information", ifc, parent=_get_parent_document(ifc))
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
        if ifc.schema == "IFC2X3":
            information = (reference.ReferenceToDocument or [None])[0]
        else:
            information = reference.ReferencedDocument
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


@pytest.fixture
def ifc2x3():
    return _create_ifc2x3()


@pytest.fixture
def element_ifc2x3(ifc2x3):
    return _add_annotation(ifc2x3, "ScanA")


@pytest.fixture
def element_with_doc_ifc2x3(ifc2x3, element_ifc2x3):
    _add_document_reference(ifc2x3, element_ifc2x3, "./clouds/scan_a.ply")
    return element_ifc2x3


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
    infos = [i for i in ifc.by_type("IfcDocumentInformation") if i.Name != const.PARENT_NAME]
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
    rels = [r for r in getattr(element_with_doc, "HasAssociations", []) if r.is_a("IfcRelAssociatesDocument")]
    assert len(rels) == 0


def test_remove_documents_removes_reference_from_model(ifc, element_with_doc):
    _remove_documents(ifc, element_with_doc)
    assert len(ifc.by_type("IfcDocumentReference")) == 0


def test_remove_documents_removes_information_from_model(ifc, element_with_doc):
    _remove_documents(ifc, element_with_doc)
    # Only the POINTCLOUDS parent information remains (never removed, like
    # Bonsai's DRAWINGS parent).
    infos = ifc.by_type("IfcDocumentInformation")
    assert [i.Name for i in infos] == [const.PARENT_NAME]


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
# POINTCLOUDS parent group / document hierarchy (mirrors Bonsai's DRAWINGS
# convention from IfcOpenShell PR #7093)
# ---------------------------------------------------------------------------


def test_parent_group_attributes(ifc):
    group = _get_parent_group(ifc)
    assert group.is_a("IfcGroup")
    assert group.Name == const.PARENT_NAME
    assert group.ObjectType == const.PARENT_NAME


def test_parent_group_is_created_once(ifc):
    first = _get_parent_group(ifc)
    second = _get_parent_group(ifc)
    assert first == second
    assert len(ifc.by_type("IfcGroup")) == 1


def test_annotation_assigned_to_parent_group(ifc, element):
    ifcopenshell.api.run("group.assign_group", ifc, group=_get_parent_group(ifc), products=[element])
    rels = [r for r in ifc.by_type("IfcRelAssignsToGroup") if r.RelatingGroup == _get_parent_group(ifc)]
    assert len(rels) == 1
    assert element in rels[0].RelatedObjects


def test_removing_annotation_keeps_parent_group(ifc, element):
    group = _get_parent_group(ifc)
    ifcopenshell.api.run("group.assign_group", ifc, group=group, products=[element])
    ifcopenshell.api.run("root.remove_product", ifc, product=element)
    assert len(ifc.by_type("IfcAnnotation")) == 0
    assert _get_parent_group(ifc) == group  # still there, found not re-created
    assert len(ifc.by_type("IfcGroup")) == 1


def test_parent_document_attributes(ifc):
    information = _get_parent_document(ifc)
    assert information.Identification == const.PARENT_NAME
    assert information.Name == const.PARENT_NAME
    assert information.Scope == const.PARENT_NAME


def test_parent_document_is_created_once(ifc):
    el_a = _add_annotation(ifc, "ScanA")
    el_b = _add_annotation(ifc, "ScanB")
    _add_document_reference(ifc, el_a, "./clouds/a.ply")
    _add_document_reference(ifc, el_b, "./clouds/b.ply")
    parents = [i for i in ifc.by_type("IfcDocumentInformation") if i.Name == const.PARENT_NAME]
    assert len(parents) == 1


def test_cloud_information_nested_under_parent(ifc, element_with_doc):
    rels = ifc.by_type("IfcDocumentInformationRelationship")
    assert len(rels) == 1
    assert rels[0].RelatingDocument.Name == const.PARENT_NAME
    child_names = [d.Name for d in rels[0].RelatedDocuments]
    assert child_names == [f"{const.DOCUMENT_REF_PREFIX}ScanA"]


def test_remove_documents_keeps_other_children_nested(ifc):
    el_a = _add_annotation(ifc, "ScanA")
    el_b = _add_annotation(ifc, "ScanB")
    _add_document_reference(ifc, el_a, "./clouds/a.ply")
    _add_document_reference(ifc, el_b, "./clouds/b.ply")
    _remove_documents(ifc, el_a)
    rels = ifc.by_type("IfcDocumentInformationRelationship")
    assert len(rels) == 1
    child_names = [d.Name for d in rels[0].RelatedDocuments]
    assert child_names == [f"{const.DOCUMENT_REF_PREFIX}ScanB"]


def test_remove_documents_purges_empty_parent_relationship(ifc, element_with_doc):
    _remove_documents(ifc, element_with_doc)
    assert len(ifc.by_type("IfcDocumentInformationRelationship")) == 0


# ---------------------------------------------------------------------------
# remove_documents — IFC2X3 branch (reference.ReferenceToDocument, the inverse
# attribute IFC2X3 uses in place of IFC4's IfcDocumentReference.ReferencedDocument)
# ---------------------------------------------------------------------------


def test_remove_documents_ifc2x3_clears_association(ifc2x3, element_with_doc_ifc2x3):
    _remove_documents(ifc2x3, element_with_doc_ifc2x3)
    rels = [r for r in getattr(element_with_doc_ifc2x3, "HasAssociations", []) if r.is_a("IfcRelAssociatesDocument")]
    assert len(rels) == 0


def test_remove_documents_ifc2x3_removes_reference_from_model(ifc2x3, element_with_doc_ifc2x3):
    _remove_documents(ifc2x3, element_with_doc_ifc2x3)
    assert len(ifc2x3.by_type("IfcDocumentReference")) == 0


def test_remove_documents_ifc2x3_removes_information_from_model(ifc2x3, element_with_doc_ifc2x3):
    _remove_documents(ifc2x3, element_with_doc_ifc2x3)
    # Only the POINTCLOUDS parent information remains (never removed, like
    # Bonsai's DRAWINGS parent).
    infos = ifc2x3.by_type("IfcDocumentInformation")
    assert [i.Name for i in infos] == [const.PARENT_NAME]


def test_remove_documents_ifc2x3_location_returns_empty(ifc2x3, element_with_doc_ifc2x3):
    _remove_documents(ifc2x3, element_with_doc_ifc2x3)
    assert _get_location(element_with_doc_ifc2x3) == ""


def test_remove_documents_ifc2x3_does_not_affect_other_clouds(ifc2x3):
    el_a = _add_annotation(ifc2x3, "ScanA")
    el_b = _add_annotation(ifc2x3, "ScanB")
    _add_document_reference(ifc2x3, el_a, "./clouds/a.ply")
    _add_document_reference(ifc2x3, el_b, "./clouds/b.ply")
    _remove_documents(ifc2x3, el_a)
    assert _get_location(el_b) == "./clouds/b.ply"
