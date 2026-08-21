# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import ShaperSlot
from shaper_cutout_util import global_normal

from util import assert_eq, assert_volume
from util import make_cutout, make_plane, make_sketch, mm


def test_slot_two_cutouts_perp():
    """Slot two cutouts whose center planes are perpendicular."""
    doc = App.newDocument("test_slot_perp")
    try:
        p1_plane = make_plane(doc, "P1", origin=(0, 0, 0), rot=(0, 0, 0))
        p2_plane = make_plane(doc, "P2", origin=(0, 0, 0), rot=(0, 0, 90))

        p1_sketch = make_sketch(doc, p1_plane, "P1_outline", closed=True)
        p2_sketch = make_sketch(doc, p2_plane, "P2_outline", closed=True)

        c1 = make_cutout(doc, p1_plane, "C1")
        c1.OutlineSketch = p1_sketch
        c2 = make_cutout(doc, p2_plane, "C2")
        c2.OutlineSketch = p2_sketch

        # Interface plane perpendicular to both
        interface = make_plane(doc, "Interface", origin=(0, 0, mm(2)), rot=(0, 90, 0))

        # Test that dados cut out of the volume.
        slot = ShaperSlot.create_uninitialized(c1, c2, interface, "Slot")
        slot.Cutout1_FrontDadoDepth = mm(0.1)
        slot.Cutout2_FrontDadoDepth = mm(0.1)
        doc.recompute()
        assert_volume(c1, 188451.236)
        assert_volume(c2, 188451.236)

        slot.Cutout1_FrontDadoDepth = mm(0.2)
        doc.recompute()
        assert_volume(c1, 186812.5296)
        assert_volume(c2, 190089.9424)

        slot.Cutout1_BackDadoDepth = mm(0.2)
        doc.recompute()
        assert_volume(c1, 183535.1168)
        assert_volume(c2, 193367.3552)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_slot_two_cutouts_weird_angle():
    """Slot two cutouts at 90 degrees but with weird rotation offsets.

    The center planes are still perpendicular (dot product of normals ~ 0),
    but they are rotated at non-axis-aligned angles (e.g. 17 degrees and
    107 degrees).
    """
    doc = App.newDocument("test_slot_weird")
    try:
        # Two planes perpendicular but at weird angles
        p1_plane = make_plane(doc, "P1", origin=(0, 0, 0), rot=(0, 0, 17))
        p2_plane = make_plane(doc, "P2", origin=(0, 0, 0), rot=(0, 0, 107))

        p1_sketch = make_sketch(doc, p1_plane, "P1_outline", closed=True)
        p2_sketch = make_sketch(doc, p2_plane, "P2_outline", closed=True)

        c1 = make_cutout(doc, p1_plane, "C1")
        c1.OutlineSketch = p1_sketch
        c2 = make_cutout(doc, p2_plane, "C2")
        c2.OutlineSketch = p2_sketch

        interface = make_plane(doc, "Interface", origin=(0, 0, mm(2)), rot=(0, 62, 0))

        slot = ShaperSlot.create_uninitialized(c1, c2, interface, "Slot")
        slot.Cutout1_FrontDadoDepth = mm(0.1)
        slot.Cutout2_FrontDadoDepth = mm(0.1)
        doc.recompute()

        assert_volume(c1, 191065.18294581206)
        assert_volume(c2, 185837.28905418783)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_slot_two_cutouts_weird_angle_perp_check():
    """Explicitly verify that the two weird-angle planes are perpendicular.

    This is a sanity check that the geometry in test_slot_two_cutouts_weird_angle
    is actually perpendicular (normals dot to ~0).
    """
    doc = App.newDocument("test_slot_perp_check")
    try:
        p1_plane = make_plane(doc, "P1", origin=(0, 0, 0), rot=(0, 0, 17))
        p2_plane = make_plane(doc, "P2", origin=(0, 0, 0), rot=(0, 0, 107))

        n1 = global_normal(p1_plane)
        n2 = global_normal(p2_plane)
        dot = abs(n1.dot(n2))
        assert_eq("plane dot product", dot, 0)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_slot_two_cutouts_perp)
    all_tests.append(test_slot_two_cutouts_weird_angle)
    all_tests.append(test_slot_two_cutouts_weird_angle_perp_check)
