# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
import TechDraw

from PySide import QtWidgets

from shaper_cutout_svg import classify_wires, custom_anchor_wire, wire_to_d
from shaper_cutout_util import _ICON_ROOT, are_exclusively_selected, cleanFaces, global_normal
from ShaperDados import ZERO_DEPTH_TOLERANCE, _wire_to_pipes


# ---------------------------------------------------------------------------
# Miter rectangle helpers
# ---------------------------------------------------------------------------

def _miter_rectangles(cutout: App.DocumentObject, xy_matrix: App.Matrix) -> [Part.Wire]:
    """Compute miter rectangles in projected (XY) space. Returns a list of wires,
    one per rectangle."""
    thickness = cutout.Thickness.Value
    normal_3d = global_normal(cutout.CenterPlane)

    ret_wires = []
    for member in cutout.Miters:
        new_wires = member.Proxy.rectangles(member, normal_3d, thickness)
        for wire in new_wires:
            ret_wires.append(wire.transformed(xy_matrix))

    return ret_wires


def _apply_miter_to_wires(outer_wires, inner_wires, rect_wires):
    """Fuse miter union into outer wire faces; cut from inner wire faces.
    Returns updated (outer_wires, inner_wires)."""
    new_outer = []
    for w in outer_wires:
        # For outer wires we need to invoke the TechDraw.findOuterWire algorithm to find
        # the actual outline, since e.g. Part.fuse won't combine wires the way we want.
        edges = w.Edges
        for rw in rect_wires:
            edges.extend(rw.Edges)
        new_outer.append(TechDraw.findOuterWire(edges))

    new_inner = []
    for w in inner_wires:
        # For inner wires we can use Part.cut, which *does* seem to do the right thing.
        face = Part.Face(w)
        for rw in rect_wires:
            face = face.cut(Part.Face(rw))
        new_inner.extend(face.Wires)

    return new_outer, new_inner


# ---------------------------------------------------------------------------
# SVG assembly
# ---------------------------------------------------------------------------

def _collect_paths(cutout, dado_groups, drill_holes, mirror=False, addAnchor=True):
    """Return list of SVG path element strings (no <svg> wrapper)."""
    if cutout.CutoutFace.isNull():
        return [], App.BoundBox(0)

    # The projection logic of Draft importSVG seems quite broken. I cannot directly export
    # a sketch (see https://github.com/FreeCAD/FreeCAD/pull/19765#discussion_r3575523221),
    # but I can export a Clone2D of a sketch (which is flattened to the wrong plane). If
    # I directly call get_path setting pl=None, this is what I get, while if I try setting
    # pl to a PlaneBase() with pl.align_to_placement(CenterPlane) I get output that I
    # cannot reason about.
    #
    # HOWEVER, it looks like if I just put everything on the xy plane myself, and then
    # invoke the draft functions with plane=None, things "just work" as expected. So do
    # that. This also lets us directly compute bounding boxes, set the anchor, etc.,
    # without trying to extract data from the stringly-typed get_path output.

    # This matrix will map the sketch onto the XY plane (z = 0). Anything that is parallel
    # to the sketch will get mapped to a parallel plane. If we always ignore the z coordinate
    # then the same matrix works for everything.
    xy_matrix = cutout.OutlineSketch.getGlobalPlacement().toMatrix().inverse()
    if mirror:
        # Rather than mirroring (which would require a non-unitary matrix, and cause
        # Shape.transformed to take an alternate, less-accurate codepath in which it
        # converts arcs to splines) we rotate 180 degrees around the Y axis. For a
        # 2D shape these are identical operations.
        xy_matrix.A11 *= -1
        xy_matrix.A12 *= -1
        xy_matrix.A13 *= -1
        xy_matrix.A31 *= -1
        xy_matrix.A32 *= -1
        xy_matrix.A33 *= -1

    outline_shape = cutout.CutoutFace.transformed(xy_matrix)
    outer_wires, inner_wires = classify_wires(outline_shape)
    path_elements = []

    for w in outer_wires:
        d = wire_to_d(w)
        if d:
            path_elements.append(
                f'  <path d="{d}" fill="black" stroke="black" stroke-width="1" '
                f'shaper:cutType="outside"/>')

    for w in inner_wires:
        d = wire_to_d(w)
        if d:
            path_elements.append(
                f'  <path d="{d}" fill="white" stroke="black" stroke-width="1" '
                f'shaper:cutType="inside"/>')

    for depth_mm, wires in dado_groups:
        for w in wires:
            w = w.transformed(xy_matrix)
            d = wire_to_d(w)
            if d:
                path_elements.append(
                    f'  <path d="{d}" fill="white" stroke="black" stroke-width="1" '
                    f'shaper:cutType="inside" shaper:cutDepth="{depth_mm:.4f}mm"/>')

    for (c, radius) in drill_holes:
        c = xy_matrix.multVec(c)
        path_elements.append(
            f'  <circle cx="{c.x:.4f}" cy="{c.y:.4f}" r="{radius:.4f}" '
            f'fill="white" stroke="black" stroke-width="1" '
            f'shaper:cutType="inside"/>')

    for w in _miter_rectangles(cutout, xy_matrix):
        d = wire_to_d(w)
        if d:
            path_elements.append(
                f'  <path d="{d}" fill="none" stroke="blue" stroke-width="1" '
                f'shaper:cutType="guide"/>')

    if addAnchor:
        anchor_wire = custom_anchor_wire(outer_wires)
        if not anchor_wire:
            anchor_wire = custom_anchor_wire(inner_wires)
        if anchor_wire:
            d = wire_to_d(anchor_wire)
            if d:
                path_elements.append(
                    f'  <path d="{d}" fill="red" stroke="none"/>')

    return path_elements, outline_shape.BoundBox


def _build_svg(path_elements, bb):
    """Build a complete SVG string."""
    vb_x0 = bb.XMin - 10
    vb_x1 = bb.XMax + 10
    vb_y0 = bb.YMin - 10
    vb_y1 = bb.YMax + 10
    vb_cx = (vb_x0 + vb_x1) / 2.0
    vb_cy = (vb_y0 + vb_y1) / 2.0
    vb_w = vb_x1 - vb_x0
    vb_h = vb_y1 - vb_y0
    paths_str = "\n".join(path_elements)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:shaper="http://www.shapertools.com/namespaces/shaper"
     viewBox="{vb_x0:.4f} {vb_y0:.4f} {vb_w:.4f} {vb_h:.4f}"
     width="{vb_w:.4f}mm" height="{vb_h:.4f}mm">
<g transform="rotate(180 {vb_cx:.4f} {vb_cy:.4f})">
{paths_str}
</g>
</svg>'''


# ---------------------------------------------------------------------------
# Export orchestration
# ---------------------------------------------------------------------------

def _collect_dado_groups(
    cutout: App.DocumentObject,
    exportFront: bool,
) -> ([(float, [Part.Wire])], [(Part.Point, float)]):
    """Return (dados, drill_holes).
    dados      -- list of (depth_mm, [wires])
    drill_holes -- list of (center_3d, radius)
    """
    from ShaperDados import autodrill_holes

    depth_faces = {}

    def insert_or_fuse(cutout_face, depth_mm, new_object):
        if (cutout_face, depth_mm) in depth_faces:
            new_object = depth_faces[(cutout_face, depth_mm)].fuse(new_object)
        depth_faces[(cutout_face, depth_mm)] = new_object

    drill_holes = []
    # For each depth, fuse together all the faces of the dado cutouts.
    for member in cutout.Dados:
        cutout_face = member.Face
        depth_mm = member.Depth.Value
        for sketch in (member.Sketches or []):
            if sketch is None:
                continue
            source = sketch.LinkedObject if sketch.TypeId == 'App::Link' else sketch
            if source.Shape.isNull():
                continue

            normal = source.Placement.Rotation.multVec(App.Vector(0, 0, 1))

            for w in source.Shape.Wires:
                if w.isClosed():
                    if depth_mm > ZERO_DEPTH_TOLERANCE:
                        insert_or_fuse(cutout_face, depth_mm, Part.Face(w))
                else:
                    tol = member.Tolerance.Value
                    width = member.Width.Value / 2.0
                    if depth_mm > ZERO_DEPTH_TOLERANCE:
                        for pipe in _wire_to_pipes(w, normal, tol, width):
                            insert_or_fuse(cutout_face, depth_mm, pipe)

                    # While we're here, also collect autodrill holes
                    hole_radius = member.HoleDiameter.Value / 2.0
                    if member.MaxHolesPerLine == 0 or hole_radius == 0.0:
                        continue

                    cylinders = autodrill_holes(w, member.MinHoleDistance.Value,
                                                member.EndDistance.Value, member.MaxHolesPerLine)
                    for center in cylinders:
                        drill_holes.append((center, member.HoleDiameter.Value))

    for slot in cutout.Slots:
        slot_data = slot.Proxy.slot_data_for(slot, cutout)
        if slot_data is None:
            continue
        for face in slot_data.dado_faces(cutout.CutoutFace):
            if slot_data.front_dado_depth > ZERO_DEPTH_TOLERANCE:
                insert_or_fuse(cutout.FrontFace, slot_data.front_dado_depth, face)
            if slot_data.back_dado_depth > ZERO_DEPTH_TOLERANCE:
                insert_or_fuse(cutout.BackFace, slot_data.back_dado_depth, face)

    # Then for each fused face, clean it up and turn it into a dado wire
    dados = []
    for cutout_face, depth_mm in depth_faces:
        if cutout_face == cutout.FrontFace:
            if exportFront:
                fused = cleanFaces(depth_faces[(cutout_face, depth_mm)])
                dados.append((depth_mm, fused.Wires))
        elif cutout_face == cutout.BackFace:
            if not exportFront:
                fused = cleanFaces(depth_faces[(cutout_face, depth_mm)])
                dados.append((depth_mm, fused.Wires))
        else:
            App.Console.PrintWarning(
                f"export_shaper_svg: ShaperDados face '{cutout_face.Label}' is neither "
                f"FrontFace nor BackFace of '{cutout.Label}'; skipping\n")
            continue

    # Then sort by depth and return
    return sorted(dados, key=lambda d: d[0]), drill_holes


def export(cutout, exportFront):
    """Main export entry point. Shows file dialog(s) and writes SVG(s)."""
    dados, drill_holes = _collect_dado_groups(cutout, exportFront)
    # When exporting the *front* face, mirror it. This is because in SVG, the Y coordinate
    # is interpreted in the opposite way from FreeCAD, so a naive path computation causes
    # the element to be mirrored. By explicitly mirroring we undo this.
    path_elements, bb = _collect_paths(cutout, dados, drill_holes, mirror=exportFront)

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        None,
        "Export Shaper SVG",
        cutout.Label + ("_front" if exportFront else "_back") + ".svg",
        "SVG Files (*.svg)",
    )
    if not path:
        return

    svg = _build_svg(path_elements, bb)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(svg)

    App.Console.PrintMessage(f"export_shaper_svg: wrote '{path}'\n")


# ---------------------------------------------------------------------------
# FreeCAD command
# ---------------------------------------------------------------------------

class ExportShaperSVGCmd:
    def __init__(self, exportFront):
        self.exportFront = exportFront

    def GetResources(self):
        if self.exportFront:
            icon_path = os.path.join(_ICON_ROOT, "export-svg-front.svg")
            menu_text = "Export Shaper SVG (Front)"
        else:
            icon_path = os.path.join(_ICON_ROOT, "export-svg-back.svg")
            menu_text = "Export Shaper SVG (Back)"

        return {
            "MenuText": menu_text,
            "ToolTip": "Export selected ShaperCutout to Shaper-compatible SVG file(s)",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        return App.ActiveDocument and are_exclusively_selected('ShaperCutout')

    def Activated(self):
        for obj in Gui.Selection.getSelection():
            if getattr(obj, 'Type', None) == 'ShaperCutout':
                export(obj, self.exportFront)
