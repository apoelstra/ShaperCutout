# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import Part
from shaper_cutout_svg import classify_wires, custom_anchor_wire, wire_to_d
from shaper_cutout_util import cleanFaces, global_normal
from ShaperDados import ZERO_DEPTH_TOLERANCE, _wire_to_pipes


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


class SvgData:
    """Computed data used to produce a SVG rendering."""
    def __init__(
        self,
        cutout: App.DocumentObject,
        export_front: bool,
        invert: bool = False,
    ):
        self._cutout = cutout
        self._export_front = export_front

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
        self._xy_matrix = self._cutout.OutlineSketch.getGlobalPlacement().toMatrix().inverse()

        # When exporting the *front* face, mirror it. This is because in SVG, the Y coordinate
        # is interpreted in the opposite way from FreeCAD, so a naive path computation causes
        # the element to be mirrored. By explicitly mirroring we undo this.
        if export_front ^ invert:
            # Rather than mirroring (which would require a non-unitary matrix, and cause
            # Shape.transformed to take an alternate, less-accurate codepath in which it
            # converts arcs to splines) we rotate 180 degrees around the Y axis. For a
            # 2D shape these are identical operations.
            self._xy_matrix.A11 *= -1
            self._xy_matrix.A12 *= -1
            self._xy_matrix.A13 *= -1
            self._xy_matrix.A31 *= -1
            self._xy_matrix.A32 *= -1
            self._xy_matrix.A33 *= -1

        self._collect_dados_and_drill_holes()
        self._collect_paths()

    def _collect_dados_and_drill_holes(self):
        """Sets self._drill_holes and self._dado_wires"""
        from ShaperDados import autodrill_holes
        self._drill_holes = []
        depth_faces = {}

        def insert_or_fuse(cutout_face, depth_mm, new_object):
            if (cutout_face, depth_mm) in depth_faces:
                new_object = depth_faces[(cutout_face, depth_mm)].fuse(new_object)
            depth_faces[(cutout_face, depth_mm)] = new_object

        # For each depth, fuse together all the faces of the dado cutouts.
        for dados in self._cutout.Dados:
            dado_face = dados.Face
            depth_mm = dados.Depth.Value
            for sketch in (dados.Sketches or []):
                source = sketch.LinkedObject if sketch.TypeId == 'App::Link' else sketch
                if source.Shape.isNull():
                    continue
                normal = global_normal(source)

                for w in source.Shape.Wires:
                    if w.isClosed():
                        if depth_mm > ZERO_DEPTH_TOLERANCE:
                            insert_or_fuse(dado_face, depth_mm, Part.Face(w))
                    else:
                        tol = dados.Tolerance.Value
                        width = dados.Width.Value / 2.0
                        if depth_mm > ZERO_DEPTH_TOLERANCE:
                            for pipe in _wire_to_pipes(w, normal, tol, width):
                                insert_or_fuse(dado_face, depth_mm, pipe)

                        # While we're here, also collect autodrill holes
                        hole_radius = dados.HoleDiameter.Value / 2.0
                        if dados.MaxHolesPerLine == 0 or hole_radius == 0.0:
                            continue

                        cylinders = autodrill_holes(w, dados.MinHoleDistance.Value,
                                                    dados.EndDistance.Value, dados.MaxHolesPerLine)
                        for center in cylinders:
                            self._drill_holes.append((center, dados.HoleDiameter.Value))

        for slot in self._cutout.Slots:
            slot_data = slot.Proxy.slot_data_for(slot, self._cutout)
            if slot_data is None:
                continue
            for face in slot_data.dado_faces(self._cutout.CutoutFace):
                if slot_data.front_dado_depth > ZERO_DEPTH_TOLERANCE:
                    insert_or_fuse(self._cutout.FrontFace, slot_data.front_dado_depth, face)
                if slot_data.back_dado_depth > ZERO_DEPTH_TOLERANCE:
                    insert_or_fuse(self._cutout.BackFace, slot_data.back_dado_depth, face)

        # Then for each fused face, clean it up and turn it into a dado wire
        self._dado_wires = []
        for cutout_face, depth_mm in depth_faces:
            if cutout_face == self._cutout.FrontFace:
                if self._export_front:
                    fused = cleanFaces(depth_faces[(cutout_face, depth_mm)])
                    self._dado_wires.append((depth_mm, fused.Wires))
            elif cutout_face == self._cutout.BackFace:
                if not self._export_front:
                    fused = cleanFaces(depth_faces[(cutout_face, depth_mm)])
                    self._dado_wires.append((depth_mm, fused.Wires))
            else:
                App.Console.PrintWarning(
                    f"export_shaper_svg: ShaperDados face '{cutout_face.Label}' is neither "
                    f"FrontFace nor BackFace of '{self._cutout.Label}'; skipping\n")
                continue
        # Then sort by depth and return
        self._dado_wires.sort(key=lambda d: d[0])

    def _collect_paths(self):
        """Populates self._svg_paths, self._anchor_path, self.bounding_box"""
        self._svg_paths = []
        self._anchor_path = None
        if self._cutout.CutoutFace.isNull():
            self.bounding_box = App.BoundBox(0)
            return

        outline_shape = self._cutout.CutoutFace.transformed(self._xy_matrix)
        outer_wires, inner_wires = classify_wires(outline_shape)
        # We may want to come up with a more clever algorithm here which rotates to find a more
        # optimal bounding box. ChatGPT says that for a 2D shape, we can take the convex hull then
        # iterate through all its edges, and one of them will lie along the edge of the optimal
        # bounding box. It also gave me a slew of Python to compute this, which would've doubled
        # the size of the module. But some forum poster says there is a convex hull function in the
        # OpenSCAD workbench that maybe I could call. Anyway, for future work.
        self.bounding_box = outline_shape.BoundBox

        self._svg_paths.extend(self._outer_wire_paths("black", 1, "black"))

        for w in inner_wires:
            d = wire_to_d(w)
            if d:
                self._svg_paths.append(
                    f'  <path d="{d}" fill="white" stroke="black" stroke-width="1" '
                    f'shaper:cutType="inside"/>')

        for depth_mm, wires in self._dado_wires:
            for w in wires:
                w = w.transformed(self._xy_matrix)
                d = wire_to_d(w)
                if d:
                    self._svg_paths.append(
                        f'  <path d="{d}" fill="white" stroke="black" stroke-width="1" '
                        f'shaper:cutType="inside" shaper:cutDepth="{depth_mm:.4f}mm"/>')

        for (c, radius) in self._drill_holes:
            c = self._xy_matrix.multVec(c)
            self._svg_paths.append(
                f'  <circle cx="{c.x:.4f}" cy="{c.y:.4f}" r="{radius:.4f}" '
                f'fill="white" stroke="black" stroke-width="1" '
                f'shaper:cutType="inside"/>')

        for w in _miter_rectangles(self._cutout, self._xy_matrix):
            d = wire_to_d(w)
            if d:
                self._svg_paths.append(
                    f'  <path d="{d}" fill="none" stroke="blue" stroke-width="1" '
                    f'shaper:cutType="guide"/>')

        anchor_wire = custom_anchor_wire(outer_wires)
        if not anchor_wire:
            anchor_wire = custom_anchor_wire(inner_wires)
        if anchor_wire:
            d = wire_to_d(anchor_wire)
            if d:
                self._anchor_path = f'  <path d="{d}" fill="red" stroke="none"/>'

    def _outer_wire_paths(self, fill, stroke_width, color):
        """Generate SVG path strings for outer wires with given stroke width and color."""
        paths = []
        outline_shape = self._cutout.CutoutFace.transformed(self._xy_matrix)
        outer_wires, _ = classify_wires(outline_shape)
        for w in outer_wires:
            d = wire_to_d(w)
            if d:
                paths.append(
                    f'  <path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{stroke_width}" '
                    f'shaper:cutType="outside"/>')
        return paths

    def outline_svg_path(self, color):
        """Return SVG path strings for outer wires with stroke-width=2 and given color."""
        return self._outer_wire_paths("none", 8, color)

    def svg_paths(self, include_anchor=False) -> str:
        paths_str = "\n".join(self._svg_paths)
        if include_anchor and self._anchor_path:
            paths_str += "\n" + self._anchor_path
        return paths_str

    def extract_complete_svg(self, include_anchor=True) -> str:
        """Build a complete SVG string."""
        vb_x0 = self.bounding_box.XMin
        vb_x1 = self.bounding_box.XMax
        vb_y0 = self.bounding_box.YMin
        vb_y1 = self.bounding_box.YMax
        vb_cx = (vb_x0 + vb_x1) / 2.0
        vb_cy = (vb_y0 + vb_y1) / 2.0
        vb_w = vb_x1 - vb_x0
        vb_h = vb_y1 - vb_y0

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:shaper="http://www.shapertools.com/namespaces/shaper"
     viewBox="{vb_x0:.4f} {vb_y0:.4f} {vb_w:.4f} {vb_h:.4f}"
     width="{vb_w:.4f}mm" height="{vb_h:.4f}mm">
<g transform="rotate(180 {vb_cx:.4f} {vb_cy:.4f})">
{self.svg_paths(include_anchor)}
</g>
</svg>'''
