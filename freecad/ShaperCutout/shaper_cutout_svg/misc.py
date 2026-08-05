# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
from draftfunctions.svgshapes import get_path
import Part


def classify_wires(cutout_face: App.DocumentObject) -> ([Part.Wire], [Part.Wire]):
    """Return (outer_wires, inner_wires).
    We use a basic heuristic where a wire is 'inner' (i.e. a hole) if its first
    vertex lies inside another wire's face. In cases where this fails we don't
    have a well-defined inside/outside distinction anyway."""
    if len(cutout_face.Wires) <= 1:
        return cutout_face.Wires, []

    outer = []
    inner = []
    for i, w in enumerate(cutout_face.Wires):
        test_pt = w.Vertexes[0].Point
        is_inner = False
        for j, f in enumerate(cutout_face.Faces):
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


def _extract_path_d(svg_str):
    """Extract the d="..." value from an SVG path string."""
    start = svg_str.find(' d="')
    if start == -1:
        return ""
    start += 4  # skip ' d="'
    end = svg_str.find('"', start)
    return svg_str[start:end]


def wire_to_d(wire: Part.Wire) -> str:
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


def custom_anchor_wire(outline_wires: [Part.Wire]) -> Part.Wire:
    """Find the best 90-degree corner in the outline wires.
    Returns a Part.Wire triangle in 3D representing the anchor, or None."""
    import math

    # Collect all straight edges from all outline wires
    straight_edges = []
    for wire in outline_wires:
        for edge in wire.Edges:
            if isinstance(edge.Curve, Part.Line):
                straight_edges.append(edge)

    if len(straight_edges) < 2:
        return None

    # Group edges by angle using tolerance 1e-4
    angle_groups = {}
    for edge in straight_edges:
        p0 = edge.Vertexes[0].Point
        p1 = edge.Vertexes[1].Point
        dx = p1.x - p0.x
        dy = p1.y - p0.y
        angle = math.atan2(dy, dx)
        # Round both up and down to tolerance
        tol = 1e-4
        angle_up = math.ceil(angle / tol) * tol
        angle_down = math.floor(angle / tol) * tol
        for key in (angle_up, angle_down):
            if key not in angle_groups or edge.Length > angle_groups[key].Length:
                angle_groups[key] = edge

    # Sort by angle (ascending) to prefer X-axis proximity
    sorted_angles = sorted(angle_groups.keys())

    # Find orthogonal pairs
    best_score = -1
    best_pair = None
    for angle in sorted_angles:
        edge1 = angle_groups[angle]
        # Check angle + 90 degrees
        for offset in (math.pi / 2, -math.pi / 2):
            target_angle = angle + offset
            # Find closest matching angle in groups
            for key in sorted_angles:
                if abs(key - target_angle) < 1e-4:
                    edge2 = angle_groups[key]
                    score = edge1.Length + edge2.Length
                    if score > best_score:
                        best_score = score
                        best_pair = (edge1, edge2)
                    break

    if best_pair is None:
        return None

    edge1, edge2 = best_pair

    # Compute intersection of the two edge lines
    p1_start = edge1.Vertexes[0].Point
    p1_end = edge1.Vertexes[1].Point
    p2_start = edge2.Vertexes[0].Point
    p2_end = edge2.Vertexes[1].Point

    # Line-line intersection in 2D (XY plane)
    x1, y1 = p1_start.x, p1_start.y
    x2, y2 = p1_end.x, p1_end.y
    x3, y3 = p2_start.x, p2_start.y
    x4, y4 = p2_end.x, p2_end.y

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    ix = x1 + t * (x2 - x1)
    iy = y1 + t * (y2 - y1)
    shared_pt = App.Vector(ix, iy, p1_start.z)  # all z coords will be the same, just pick one

    # Compute direction vectors
    def dir_away(edge, pt):
        p0 = edge.Vertexes[0].Point
        p1 = edge.Vertexes[1].Point
        if (p0 - pt).Length < 1e-4:
            return (p1 - pt).normalize()
        else:
            return (p0 - pt).normalize()

    d1 = dir_away(edge1, shared_pt)
    d2 = dir_away(edge2, shared_pt)

    # Shorter leg = X, longer = Y per Shaper spec
    short_dir = d1 if edge1.Length <= edge2.Length else d2
    long_dir = d2 if edge1.Length <= edge2.Length else d1
    size_short = 15.0
    size_long = 30.0
    p0 = shared_pt
    p1 = shared_pt + short_dir * size_short
    p2 = shared_pt + long_dir * size_long

    return Part.Wire(Part.makePolygon([p0, p1, p2, p0]))
