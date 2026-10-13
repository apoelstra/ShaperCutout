# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Optional, Tuple

import FreeCAD as App
from PySide import QtWidgets

from .misc import copy_property
from .selection import ShaperCutoutType


def global_normal(obj):
    """Determines the normal vector to the plane of the object's global placement.

    Intended for use with sketches and planes."""
    return obj.getGlobalPlacement().Rotation.multVec(App.Vector(0, 0, 1))


def objects_are_parallel(obj1, obj2):
    """Determines whether two objects are parallel (or anti-parallel) based on global placement.

    Intended for use with sketches and planes."""
    if obj1 is None or obj2 is None:
        return False
    return global_normal(obj1).cross(global_normal(obj2)).Length < 1e-6

def attachment_target(sketch: App.DocumentObject):
    """Returns the (object, subelement) that the sketch's attachment points at.

    subelement is '' when the sketch is attached to the whole object (e.g.
    a datum plane), or e.g. 'Face2' when attached to one of its faces.
    Returns None when the sketch is not attached (no support links, or
    MapMode deactivated).
    """
    if getattr(sketch, 'MapMode', 'Deactivated') in ('Deactivated', ''):
        return None

    support = getattr(sketch, 'AttachmentSupport', None)
    if support is None or len(support) == 0:
        return None
    first = support[0]
    if not isinstance(first, (tuple, list)) or len(first) == 0 \
            or not isinstance(first[0], App.DocumentObject):
        return None

    subs = first[1] if len(first) > 1 else None
    if subs is None:
        sub = ''
    elif isinstance(subs, str):
        sub = subs
    elif len(subs) > 0:
        sub = subs[0] or ''
    else:
        sub = ''
    return first[0], sub


def _attachment_target(sketch: App.DocumentObject) -> Optional[App.DocumentObject]:
    """Returns the object that the sketch's attachment points at, if any.

    Ignores subelements.
    """
    target = attachment_target(sketch)
    return target[0] if target is not None else None


def reattach_to_plane(sketch: App.DocumentObject, plane: App.DocumentObject):
    """Attach `sketch` to `plane`, preserving its global placement.

    The sketch's current global placement is re-expressed as an
    AttachmentOffset relative to the new plane, so geometry drawn on the
    sketch does not move.
    """
    placement = App.Placement(sketch.getGlobalPlacement())
    offset = plane.getGlobalPlacement().inverse().multiply(placement)
    sketch.AttachmentSupport = [(plane, '')]
    sketch.MapMode = 'FlatFace'
    sketch.AttachmentOffset = offset


def get_or_create_attachment_plane(sketch: App.DocumentObject) -> Optional[App.DocumentObject]:
    """Return the sketch's attachment support, if it is a plane.

    If it is not a plane, offer to create a plane, copying the sketch's original attachment,
    and move the plane to that.
    """
    assert ShaperCutoutType.SKETCH.is_type_of(sketch)
    if sketch is None:
        return None

    support = _attachment_target(sketch)
    if support is not None and ShaperCutoutType.PLANE.is_type_of(support):
        return support

    answer = QtWidgets.QMessageBox.question(
        None, "Create Attachment Plane",
        f"The selected sketch '{sketch.Label}' is not attached to a plane.\n\n"
        "Create a new plane and attach the sketch to it, so it can be used "
        "as the backing plane for a cutout?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.Yes)

    if answer != QtWidgets.QMessageBox.Yes:
        return None

    support = sketch.Document.addObject('Part::DatumPlane', f'{sketch.Label}_Attachment')
    copy_property(sketch, support, 'AttachmentSupport')
    copy_property(sketch, support, 'AttachmentOffset')
    copy_property(sketch, support, 'MapMode')
    sketch.AttachmentSupport = [(support, '')]
    sketch.AttachmentOffset = App.Placement()
    sketch.MapMode = 'FlatFace'

    return support
