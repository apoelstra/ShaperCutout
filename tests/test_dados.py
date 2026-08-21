# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import Part
import Sketcher
import ShaperDados

from util import assert_eq, assert_true, assert_volume
from util import make_cutout, make_plane, make_sketch, mm


def test_dado_closed_wire():
    """Dado with a closed wire (arbitrary shape) should cut a pocket."""
    doc = App.newDocument("test_dado_closed")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0), rot=(0, 0, 0))
        sketch = make_sketch(doc, plane, "Outline", closed=True)

        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = sketch

        # Dado sketch: a small closed rectangle on the front face
        dado_plane = cutout.FrontFace
        dado_sketch = doc.addObject("Sketcher::SketchObject", "Dado_closed")
        dado_sketch.AttachmentSupport = (dado_plane, [''])
        dado_sketch.MapMode = 'FlatFace'

        # Draw a closed rectangle (5mm x 10mm)
        w, h = mm(0.5), mm(1.0)
        pts = [
            App.Vector(-w/2, -h/2, 0),
            App.Vector(w/2, -h/2, 0),
            App.Vector(w/2, h/2, 0),
            App.Vector(-w/2, h/2, 0),
        ]
        for i in range(4):
            dado_sketch.addGeometry(Part.LineSegment(pts[i], pts[(i+1) % 4]), False)
        for i in range(4):
            dado_sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i+1) % 4, 1))
        dado_sketch.addConstraint(Sketcher.Constraint('Horizontal', 0))
        dado_sketch.addConstraint(Sketcher.Constraint('Vertical', 1))
        dado_sketch.addConstraint(Sketcher.Constraint('DistanceX', 0, w))
        dado_sketch.addConstraint(Sketcher.Constraint('DistanceY', 1, h))

        dados = ShaperDados.create_uninitialized(cutout, "Dados_closed")
        dados.Label = "Dados_closed"
        dados.Face = dado_plane
        dados.Depth = mm(0.2)
        dados.Width = mm(1.0)
        dados.Tolerance = mm(0.1)
        dados.Sketches = [dado_sketch]
        dados.MaxHolesPerLine = 0

        doc.recompute()
        assert_volume(cutout, 196644.768)

        # Pocket shape should exist and have solids
        pocket = dados.PocketShape
        assert_true(not pocket.isNull() and len(pocket.Solids) > 0, "dado pocket has solids")
        pv = sum(s.Volume for s in pocket.Solids)
        assert_eq("total pocket volume", pv, 1638.7064)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_dado_open_wire():
    """Dado with an open wire (centerline) should cut a pocket."""
    doc = App.newDocument("test_dado_open")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0), rot=(0, 0, 0))
        sketch = make_sketch(doc, plane, "Outline", closed=True)

        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = sketch

        dado_plane = cutout.FrontFace
        dado_sketch = doc.addObject("Sketcher::SketchObject", "Dado_open")
        dado_sketch.AttachmentSupport = (dado_plane, [''])
        dado_sketch.MapMode = 'FlatFace'

        # Draw an open line (centerline of the dado)
        p1 = App.Vector(-mm(2), 0, 0)
        p2 = App.Vector(mm(2), 0, 0)
        dado_sketch.addGeometry(Part.LineSegment(p1, p2), False)

        dados = ShaperDados.create_uninitialized(cutout, "Dados_open")
        dados.Label = "Dados_open"
        dados.Face = dado_plane
        dados.Depth = mm(0.2)
        dados.Width = mm(0.25)
        dados.Tolerance = mm(0.01)
        dados.Sketches = [dado_sketch]
        dados.MaxHolesPerLine = 0

        doc.recompute()
        assert_volume(cutout, 196644.768)

        pocket = dados.PocketShape
        assert_true(not pocket.isNull() and len(pocket.Solids) > 0, "dado pocket has solids")
        pv = sum(s.Volume for s in pocket.Solids)
        assert_eq("total pocket volume", pv, 3557.30385312)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_dado_both_closed_and_open():
    """Dado set with both a closed wire and an open wire."""
    doc = App.newDocument("test_dado_both")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0), rot=(0, 0, 0))
        sketch = make_sketch(doc, plane, "Outline", closed=True)

        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = sketch

        dado_plane = cutout.FrontFace

        # Closed wire sketch (a rectangle)
        closed_sketch = doc.addObject("Sketcher::SketchObject", "Dado_closed")
        closed_sketch.AttachmentSupport = (dado_plane, [''])
        closed_sketch.MapMode = 'FlatFace'
        w, h = mm(0.5), mm(1.0)
        pts = [
            App.Vector(-w/2, mm(1), 0),
            App.Vector(w/2, mm(1), 0),
            App.Vector(w/2, mm(1) + h, 0),
            App.Vector(-w/2, mm(1) + h, 0),
        ]
        for i in range(4):
            closed_sketch.addGeometry(Part.LineSegment(pts[i], pts[(i+1) % 4]), False)
        for i in range(4):
            closed_sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i+1) % 4, 1))

        # Open wire sketch (a line)
        open_sketch = doc.addObject("Sketcher::SketchObject", "Dado_open")
        open_sketch.AttachmentSupport = (dado_plane, [''])
        open_sketch.MapMode = 'FlatFace'
        p1 = App.Vector(-mm(2), -mm(1), 0)
        p2 = App.Vector(mm(2), -mm(1), 0)
        open_sketch.addGeometry(Part.LineSegment(p1, p2), False)

        dados = ShaperDados.create_uninitialized(cutout, "Dados_both")
        dados.Label = "Dados_both"
        dados.Face = dado_plane
        dados.Depth = mm(0.2)
        dados.Width = mm(0.25)
        dados.Tolerance = mm(0.01)
        dados.Sketches = [closed_sketch, open_sketch]
        dados.MaxHolesPerLine = 0

        doc.recompute()
        assert_volume(cutout, 196644.768)

        pocket = dados.PocketShape
        assert_true(not pocket.isNull() and len(pocket.Solids) > 0, "dado pocket has solids")
        pv = sum(s.Volume for s in pocket.Solids)
        assert_eq("total pocket volume", pv, 5196.01025312)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_dado_closed_wire)
    all_tests.append(test_dado_open_wire)
    all_tests.append(test_dado_both_closed_and_open)
