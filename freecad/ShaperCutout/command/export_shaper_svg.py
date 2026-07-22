# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
import TechDraw

from draftgeoutils import faces
from draftfunctions.svgshapes import get_path
from PySide import QtWidgets

from shaper_cutout_util import are_exclusively_selected
from ShaperDados import _wire_to_pipes


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

def _miter_rectangles(cutout, xy_matrix):
    """Compute miter rectangles in projected (XY) space. Returns a list of wires,
    one per rectangle."""
    import math as _math

    thickness = cutout.Thickness.Value
    normal_3d = cutout.CenterPlane.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    half = thickness / 2.0

    ret_wires = []

    for member in cutout.Miters:
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
                    ret_wires.append(wire)
                except Exception as e:
                    App.Console.PrintWarning(f"export_shaper_svg: miter rect failed: {e}\n")

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

def _collect_paths(cutout, dado_groups, drill_holes, mirror=False, addAnchor=True):
    """Return list of SVG path element strings (no <svg> wrapper)."""
    if cutout.OutlineSketch.Shape.isNull():
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

    rect_wires = _miter_rectangles(cutout, xy_matrix)
    outer_wires, inner_wires = _apply_miter_to_wires(outer_wires, inner_wires, rect_wires)

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

    for depth_mm, wires in dado_groups:
        for w in wires:
            w = w.transformed(xy_matrix)
            d = _wire_to_d(w)
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

    for w in rect_wires:
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

def _safe_for_cleanFaces(shape):
    # TODO file a bug about this. This is literally just a copy of cleanFaces
    #  up until an unguarded call to hfaces.pop(), which will fail if you have
    #  some number of single disjoint faces.
    faceset = shape.Faces

    def find(hc):
        """Find a face with the given hashcode."""
        for f in faceset:
            if f.hashCode() == hc:
                return f

    # build lookup table
    lut = {}
    for face in faceset:
        for edge in face.Edges:
            if edge.hashCode() in lut:
                lut[edge.hashCode()].append(face.hashCode())
            else:
                lut[edge.hashCode()] = [face.hashCode()]

    # print("lut:",lut)
    # take edges shared by 2 faces
    sharedhedges = []
    for k, v in lut.items():
        if len(v) == 2:
            sharedhedges.append(k)

    # print(len(sharedhedges)," shared edges:",sharedhedges)
    # find those with same normals
    targethedges = []
    for hedge in sharedhedges:
        faces = lut[hedge]
        n1 = find(faces[0]).normalAt(0.5, 0.5)
        n2 = find(faces[1]).normalAt(0.5, 0.5)
        if n1 == n2:
            targethedges.append(hedge)

    # print(len(targethedges)," target edges:",targethedges)
    # get target faces
    hfaces = []
    for hedge in targethedges:
        for f in lut[hedge]:
            if f not in hfaces:
                hfaces.append(f)

    return len(hfaces) > 0


def _collect_dado_groups(cutout, exportFront):
    """Return (dados, drill_holes).
    dados      -- list of (depth_mm, [wires])
    drill_holes -- list of (center_3d, radius)
    """
    from ShaperDados import autodrill_holes

    dados = []
    drill_holes = []

    for member in cutout.Dados:
        face = member.Face
        depth_mm = member.Depth.Value
        wires = []
        for sketch in (member.Sketches or []):
            if sketch is None:
                continue
            source = sketch.LinkedObject if sketch.TypeId == 'App::Link' else sketch
            if source.Shape.isNull():
                continue

            normal = source.Placement.Rotation.multVec(App.Vector(0, 0, 1))
            pipes = []
            for w in source.Shape.Wires:
                if w.isClosed():
                    wires.append(w)
                else:
                    tol = member.Tolerance.Value
                    width = member.Width.Value / 2.0
                    pipes.extend(_wire_to_pipes(w, normal, tol, width))

                    # Collect autodrill holes
                    hole_radius = member.HoleDiameter.Value / 2.0
                    if member.MaxHolesPerLine == 0 or hole_radius == 0.0:
                        continue

                    cylinders = autodrill_holes(w, member.MinHoleDistance.Value,
                                                member.EndDistance.Value, member.MaxHolesPerLine)
                    for center in cylinders:
                        drill_holes.append((center, member.HoleDiameter.Value))

            if len(pipes) > 0:
                fuse = pipes[0]
                for pipe in pipes[1:]:
                    fuse = fuse.fuse(pipe)

                if _safe_for_cleanFaces(fuse):
                    fuse = faces.cleanFaces(fuse)
                wires.extend(fuse.Wires)

        if face is cutout.FrontFace:
            if exportFront:
                dados.append((depth_mm, wires))
        elif face is cutout.BackFace:
            if not exportFront:
                dados.append((depth_mm, wires))
        else:
            App.Console.PrintWarning(
                f"export_shaper_svg: ShaperDados '{member.Label}' face is neither "
                f"FrontFace nor BackFace of '{cutout.Label}'; skipping\n")
            continue

    return sorted(dados), drill_holes


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
        return App.ActiveDocument and are_exclusively_selected('ShaperCutout')

    def Activated(self):
        for obj in Gui.Selection.getSelection():
            if getattr(obj, 'Type', None) == 'ShaperCutout':
                export(obj, self.exportFront)
