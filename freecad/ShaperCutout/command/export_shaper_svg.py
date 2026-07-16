# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part

from draftfunctions.svgshapes import get_path
from PySide import QtWidgets


# ---------------------------------------------------------------------------
# Wire classification (outer vs hole)
# ---------------------------------------------------------------------------

def _classify_wires(wires):
    """Return (outer_wires, inner_wires).
    We use a basic heuristic where a wire is 'inner' (i.e. a hole) if its first
    vertex lies inside another wire's face. In cases where this fails we don't
    have a well-defined inside/outside distinction anyway."""
    if len(wires) <= 1:
        return wires, []

    faces = []
    for w in wires:
        try:
            faces.append(Part.Face(w))
        except Exception:
            faces.append(None)

    outer = []
    inner = []
    for i, w in enumerate(wires):
        test_pt = w.Vertexes[0].Point
        is_inner = False
        for j, f in enumerate(faces):
            if i == j or f is None:
                continue
            if f.isInside(test_pt, 1e-3, True):
                is_inner = True
                break
        if is_inner:
            inner.append(w)
        else:
            outer.append(w)
    return outer, inner


# ---------------------------------------------------------------------------
# Draft projection helpers
# ---------------------------------------------------------------------------

def _extract_path_d(svg_str):
    """Extract the d="..." value from an SVG path string."""
    start = svg_str.find(' d="')
    if start == -1:
        return ""
    start += 4  # skip ' d="'
    end = svg_str.find('"', start)
    return svg_str[start:end]


def _wire_to_d(wire):
    """Project a wire onto the plane and return the SVG path d string."""
    # We need a stub object with a Name attribute for get_path
    class _Stub:
        Name = "stub"
    svg_str = get_path(
        obj=_Stub(),
        plane=None,
        fill="black",  # just need a dummy to cause get_path to close the path
        pathdata=[],
        stroke="black",
        linewidth=0.1,
        lstyle="solid",
        wires=[wire],
    )
    return _extract_path_d(svg_str)


# ---------------------------------------------------------------------------
# Miter rectangle helpers
# ---------------------------------------------------------------------------

def _miter_rect_faces(cutout, xy_matrix):
    """Compute miter rectangle faces in projected (XY) space.
    Returns (rect_faces, union_face) where union_face is None if no miters."""
    import math as _math

    thickness = cutout.Thickness.Value
    normal_3d = cutout.CenterPlane.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    half = thickness / 2.0

    rect_faces = []

    for member in cutout.Group:
        if getattr(member, 'Type', None) != 'ShaperMiter':
            continue
        if not member.Edges or member.Angle is None:
            continue
        angle_deg = member.Angle.Value
        if angle_deg == 0:
            continue
        if angle_deg <= -90 or angle_deg >= 90:
            continue
        miter_axis = member.MiterAxis

        for (linked_obj, subnames) in member.Edges:
            for subname in subnames:
                if not subname.startswith('Edge'):
                    continue
                try:
                    edge_shape = linked_obj.Shape.getElement(subname)
                except Exception:
                    continue
                if not isinstance(edge_shape.Curve, Part.Line):
                    continue

                p0_3d = edge_shape.Vertexes[0].Point
                p1_3d = edge_shape.Vertexes[1].Point
                edge_vec_3d = p1_3d - p0_3d
                face_normal_3d = edge_vec_3d.cross(normal_3d).normalize()

                far_dist = _math.tan(_math.radians(angle_deg)) * thickness
                far_vec_3d = far_dist * face_normal_3d

                if miter_axis == 'Front':
                    offset_vec_3d = App.Vector(0, 0, 0)
                elif miter_axis == 'Center':
                    offset_vec_3d = -far_vec_3d / 2
                else:  # Back
                    offset_vec_3d = -far_vec_3d

                # The 4 corners of the miter rectangle in 3D (on the center plane)
                # near_a/near_b are the edge endpoints offset to the center plane,
                # far_a/far_b are the far corners.
                near_a_3d = p0_3d + half * normal_3d + offset_vec_3d
                near_b_3d = p1_3d + half * normal_3d + offset_vec_3d
                far_a_3d  = near_a_3d + far_vec_3d
                far_b_3d  = near_b_3d + far_vec_3d

                # Project all 4 corners onto XY plane
                def proj(pt):
                    v = xy_matrix.multiply(pt)
                    return App.Vector(v.x, v.y, 0)

                na = proj(near_a_3d)
                nb = proj(near_b_3d)
                fa = proj(far_a_3d)
                fb = proj(far_b_3d)

                try:
                    wire = Part.makePolygon([na, nb, fb, fa, na])
                    face = Part.Face(wire)
                    rect_faces.append(face)
                except Exception as e:
                    App.Console.PrintWarning(f"export_shaper_svg: miter rect failed: {e}\n")

    if not rect_faces:
        return [], None

    union_face = rect_faces[0]
    for f in rect_faces[1:]:
        try:
            union_face = union_face.fuse(f)
        except Exception as e:
            App.Console.PrintWarning(f"export_shaper_svg: miter union failed: {e}\n")

    return rect_faces, union_face


def _apply_miter_to_wires(outer_wires, inner_wires, union_face):
    """Fuse miter union into outer wire faces; cut from inner wire faces.
    Returns updated (outer_wires, inner_wires)."""
    new_outer = []
    for w in outer_wires:
        try:
            face = Part.Face(w)
            result = face.fuse(union_face)
            new_outer.extend(result.Wires)
        except Exception as e:
            App.Console.PrintWarning(f"export_shaper_svg: outer miter fuse failed: {e}\n")
            new_outer.append(w)

    new_inner = []
    for w in inner_wires:
        try:
            face = Part.Face(w)
            result = face.cut(union_face)
            new_inner.extend(result.Wires)
        except Exception as e:
            App.Console.PrintWarning(f"export_shaper_svg: inner miter cut failed: {e}\n")
            new_inner.append(w)

    return new_outer, new_inner


# ---------------------------------------------------------------------------
# Custom anchor
# ---------------------------------------------------------------------------

def _find_anchor_corner(outline_wires):
    """Find the best 90-degree corner in the outline wires.
    Returns a Part.Wire triangle in 3D representing the anchor, or None."""
    best_score = -1
    best = None

    for wire in outline_wires:
        edges = wire.Edges
        n = len(edges)
        for i in range(n):
            e1 = edges[i]
            e2 = edges[(i + 1) % n]

            if not isinstance(e1.Curve, Part.Line):
                continue
            if not isinstance(e2.Curve, Part.Line):
                continue

            v1_pts = {tuple(round(x, 4) for x in v.Point) for v in e1.Vertexes}
            v2_pts = {tuple(round(x, 4) for x in v.Point) for v in e2.Vertexes}
            shared = v1_pts & v2_pts
            if not shared:
                continue
            shared_pt_key = next(iter(shared))
            shared_pt = App.Vector(*shared_pt_key)

            def dir_away(edge, pt):
                p0 = edge.Vertexes[0].Point
                p1 = edge.Vertexes[1].Point
                if (p0 - pt).Length < 1e-4:
                    return (p1 - pt).normalize()
                else:
                    return (p0 - pt).normalize()

            d1 = dir_away(e1, shared_pt)
            d2 = dir_away(e2, shared_pt)

            if abs(d1.dot(d2)) > 0.01:
                continue

            score = e1.Length ** 2 + e2.Length ** 2
            if score > best_score:
                best_score = score
                # Shorter leg = X, longer = Y per Shaper spec
                short_dir = d1 if e1.Length <= e2.Length else d2
                long_dir  = d2 if e1.Length <= e2.Length else d1
                size_short = 15.0
                size_long  = 30.0
                p0 = shared_pt
                p1 = shared_pt + short_dir * size_short
                p2 = shared_pt + long_dir  * size_long
                best = (p0, p1, p2)

    if best is None:
        return None

    p0, p1, p2 = best
    try:
        wire = Part.Wire([
            Part.makeLine(p0, p1),
            Part.makeLine(p1, p2),
            Part.makeLine(p2, p0),
        ])
        return wire
    except Exception:
        return None


# ---------------------------------------------------------------------------
# SVG assembly
# ---------------------------------------------------------------------------

def _collect_paths(cutout, dado_groups, mirror=False, addAnchor=True):
    """Return list of SVG path element strings (no <svg> wrapper)."""
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

    xy_matrix = cutout.CenterPlane.Placement.toMatrix().inverse()
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

    outline_shape = cutout.OutlineSketch.Shape.transformed(xy_matrix)
    outline_wires = outline_shape.Wires
    outer_wires, inner_wires = _classify_wires(outline_wires)

    rect_faces, miter_union = _miter_rect_faces(cutout, xy_matrix)
    if miter_union is not None:
        outer_wires, inner_wires = _apply_miter_to_wires(outer_wires, inner_wires, miter_union)

    path_elements = []

    for w in outer_wires:
        d = _wire_to_d(w)
        if d:
            path_elements.append(
                f'  <path d="{d}" fill="black" stroke="black" stroke-width="1" '
                f'shaper:cutType="outside"/>')

    for w in inner_wires:
        d = _wire_to_d(w)
        if d:
            path_elements.append(
                f'  <path d="{d}" fill="white" stroke="black" stroke-width="1" '
                f'shaper:cutType="inside"/>')

    for depth_mm, shapes in dado_groups:
        for shape in shapes:
            for w in shape.transformed(xy_matrix).Wires:
                d = _wire_to_d(w)
                if d:
                    path_elements.append(
                        f'  <path d="{d}" fill="white" stroke="black" stroke-width="1" '
                        f'shaper:cutType="inside" shaper:cutDepth="{depth_mm:.4f}mm"/>')

    for rf in rect_faces:
        for w in rf.Wires:
            d = _wire_to_d(w)
            if d:
                path_elements.append(
                    f'  <path d="{d}" fill="none" stroke="blue" stroke-width="1" '
                    f'shaper:cutType="guide"/>')

    if addAnchor:
        anchor_wire = _find_anchor_corner(outer_wires)
        if not anchor_wire:
            anchor_wire = _find_anchor_corner(inner_wires)
        if anchor_wire:
            d = _wire_to_d(anchor_wire)
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

def _collect_dado_groups(cutout, exportFront):
    """Return list of (depth_mm, [shapes]).
    Warns if a dado face is neither FrontFace nor BackFace."""
    dados = []

    for member in cutout.Group:
        if getattr(member, 'Type', None) != 'ShaperDados':
            continue
        face = member.Face
        depth_mm = member.Depth.Value
        shapes = []
        for sketch in (member.Sketches or []):
            if sketch is None:
                continue
            source = sketch.LinkedObject if sketch.TypeId == 'App::Link' else sketch
            shapes.append(source.Shape)

        if face is cutout.FrontFace:
            if exportFront:
                dados.append((depth_mm, shapes))
        elif face is cutout.BackFace:
            if not exportFront:
                dados.append((depth_mm, shapes))
        else:
            App.Console.PrintWarning(
                f"export_shaper_svg: ShaperDados '{member.Label}' face is neither "
                f"FrontFace nor BackFace of '{cutout.Label}'; skipping\n")

    return sorted(dados)


def export(cutout, exportFront):
    """Main export entry point. Shows file dialog(s) and writes SVG(s)."""
    dados = _collect_dado_groups(cutout, exportFront)
    # When exporting the *front* face, mirror it. This is because in SVG, the Y coordinate
    # is interpreted in the opposite way from FreeCAD, so a naive path computation causes
    # the element to be mirrored. By explicitly mirroring we undo this.
    path_elements, bb = _collect_paths(cutout, dados, mirror=exportFront)

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
            icon_path = os.path.join(os.path.dirname(__file__),
                                     "../resources/icons/export-svg-front.svg")
            menu_text = "Export Shaper SVG (Front)"
        else:
            icon_path = os.path.join(os.path.dirname(__file__),
                                     "../resources/icons/export-svg-back.svg")
            menu_text = "Export Shaper SVG (Back)"

        return {
            "MenuText": menu_text,
            "ToolTip": "Export selected ShaperCutout to Shaper-compatible SVG file(s)",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        sel = Gui.Selection.getSelection()
        return (len(sel) >= 1 and
                all(getattr(o, 'Type', None) == 'ShaperCutout' for o in sel))

    def Activated(self):
        for obj in Gui.Selection.getSelection():
            if getattr(obj, 'Type', None) == 'ShaperCutout':
                export(obj, self.exportFront)
