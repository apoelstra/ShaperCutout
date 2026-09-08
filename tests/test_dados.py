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


def test_dado_clone_onto_cutout():
    """Dragging a dado set onto another cutout clones it (issue #12).

    Tests the clone core: all settings (including autodrill) are copied as
    plain values (expressions are not linked), the Face maps to the target
    cutout's matching face plane, sketches are shared, and the clone cuts an
    identical pocket on a coplanar target. Also exercises the viewprovider
    drop path (with the dialog factory stubbed)."""
    doc = App.newDocument("test_dado_clone")
    try:
        # Two coplanar cutouts: a shared dado sketch cuts identical pockets.
        plane_a = make_plane(doc, "PlaneA", origin=(0, 0, 0), rot=(0, 0, 0))
        sketch_a = make_sketch(doc, plane_a, "OutlineA", closed=True)
        cutout_a = make_cutout(doc, plane_a, "CutoutA")
        cutout_a.OutlineSketch = sketch_a

        plane_b = make_plane(doc, "PlaneB", origin=(0, 0, 0), rot=(0, 0, 0))
        sketch_b = make_sketch(doc, plane_b, "OutlineB", closed=True)
        cutout_b = make_cutout(doc, plane_b, "CutoutB")
        cutout_b.OutlineSketch = sketch_b

        # Dado sketch: open line on CutoutA's front face.
        dado_sketch = doc.addObject("Sketcher::SketchObject", "Dado_line")
        dado_sketch.AttachmentSupport = (cutout_a.FrontFace, [''])
        dado_sketch.MapMode = 'FlatFace'
        dado_sketch.addGeometry(Part.LineSegment(
            App.Vector(-mm(2), 0, 0), App.Vector(mm(2), 0, 0)), False)

        dados = ShaperDados.create_uninitialized(cutout_a, "Dados_src")
        dados.Face = cutout_a.FrontFace
        dados.Invert = True
        dados.setExpression('Depth', '1 in / 5')
        dados.Width = mm(0.25)
        dados.Tolerance = mm(0.01)
        dados.Sketches = [dado_sketch]
        dados.MaxHolesPerLine = 3
        dados.HoleDiameter = mm(0.125)
        dados.MinHoleDistance = mm(1)
        dados.EndDistance = mm(0.5)
        doc.recompute()

        source_volume = sum(
            s.Volume for s in dados.PocketShape.Solids)
        assert_true(source_volume > 0, "source dado cuts a pocket")

        # --- clone_target_face maps to the same side of the target sheet ---
        face = ShaperDados.clone_target_face(dados, cutout_b)
        assert_true(face is cutout_b.FrontFace, "clone face is target FrontFace")

        # --- apply_clone copies settings as values, not links ---
        clone = ShaperDados.create_uninitialized(cutout_b, "Dados_clone")
        assert_true(ShaperDados.apply_clone(dados, clone, cutout_b),
                    "apply_clone succeeds")
        assert_true(clone.Face is cutout_b.FrontFace, "clone cuts target's face")
        assert_true(clone.Invert == dados.Invert, "Invert copied")
        assert_eq("Depth value", clone.Depth.Value, dados.Depth.Value)
        clone_exprs = [e for e in clone.ExpressionEngine]
        assert_true(len(clone_exprs) == 0,
                    f"clone has no expression links (has {clone_exprs})")
        assert_eq("Width", clone.Width.Value, dados.Width.Value)
        assert_eq("Tolerance", clone.Tolerance.Value, dados.Tolerance.Value)
        assert_true(clone.MaxHolesPerLine == dados.MaxHolesPerLine,
                    "autodrill MaxHolesPerLine copied")
        assert_eq("HoleDiameter", clone.HoleDiameter.Value, dados.HoleDiameter.Value)
        assert_eq("MinHoleDistance", clone.MinHoleDistance.Value,
                  dados.MinHoleDistance.Value)
        assert_eq("EndDistance", clone.EndDistance.Value, dados.EndDistance.Value)
        assert_true(list(clone.Sketches) == [dado_sketch], "sketches shared")
        assert_true(dados in cutout_a.Dados and cutout_a in dados.InList,
                    "original dados still on source cutout")
        assert_true(clone in cutout_b.Dados, "clone nested in target cutout")

        doc.recompute()
        clone_volume = sum(s.Volume for s in clone.PocketShape.Solids)
        assert_eq("clone pocket volume equals source", clone_volume, source_volume)
        n_drill = len(clone.AutodrillFaces.Faces) if not clone.AutodrillFaces.isNull() else 0
        assert_true(n_drill > 0, "clone autodrills too")

        # Editing the clone must not touch the source (real copies).
        clone.Depth = mm(0.1)
        doc.recompute()
        assert_eq("source Depth untouched", dados.Depth.Value, mm(0.2))

        # --- viewprovider drop path (dialog factory stubbed) ---
        import shaper_cutout_command.create_shaper_dados as csd
        import ShaperCutout

        calls = []
        orig = csd.open_dados_task_panel
        csd.open_dados_task_panel = (
            lambda cutout, dados=None, initial_sketches=[], clone_from=None:
            calls.append((cutout, dados, clone_from)))
        try:
            vp = ShaperCutout.ViewProviderShaperCutout.__new__(
                ShaperCutout.ViewProviderShaperCutout)
            vp.Object = cutout_b

            assert_true(vp.canDropObject(dados), "drop of ShaperDados accepted")
            assert_true(vp.canDropObject(dado_sketch), "drop of sketch still works")

            # Drop the source dado (owned by cutout_a) onto cutout_b: opens
            # the dialog pre-populated as a clone.
            vp.dropObject(None, dados)
            assert_true(len(calls) == 1 and calls[0][0] is cutout_b
                        and calls[0][2] is dados,
                        "drop opens dialog with clone_from set")

            # Dropping a dado already on the cutout is refused.
            calls.clear()
            vp.dropObject(None, clone)
            assert_true(len(calls) == 0, "self-drop refused")
        finally:
            csd.open_dados_task_panel = orig

        # --- nonparallel target is refused ---
        plane_c = make_plane(doc, "PlaneC", origin=(0, 0, 0), rot=(0, 0, 0))
        plane_c.Placement = App.Placement(
            App.Vector(0, 0, 0), App.Rotation(App.Vector(1, 0, 0), 45))
        sketch_c = make_sketch(doc, plane_c, "OutlineC", closed=True)
        cutout_c = make_cutout(doc, plane_c, "CutoutC")
        cutout_c.OutlineSketch = sketch_c
        doc.recompute()
        assert_true(ShaperDados.clone_target_face(dados, cutout_c) is None,
                    "nonparallel cutout cannot receive the clone")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_dado_closed_wire)
    all_tests.append(test_dado_open_wire)
    all_tests.append(test_dado_both_closed_and_open)
    all_tests.append(test_dado_clone_onto_cutout)
