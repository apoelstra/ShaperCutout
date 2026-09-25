# SPDX-License-Identifier: GPL-3.0-or-later

import re

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


def _get_path_element(wire: Part.Wire) -> str:
    """Run draftfunctions get_path on a single wire, returning the raw element."""
    class _Stub:
        Name = "stub"
    return get_path(
        obj=_Stub(),
        plane=None,
        fill="black",  # just need a dummy to cause get_path to close the path
        pathdata=[],
        stroke="black",
        linewidth=0.1,
        lstyle="solid",
        wires=[wire],
    )


def wire_to_svg(wire: Part.Wire, fill: str, stroke: str, cut_type: str = None,
                depth_attr: str = '', stroke_width: float = 1) -> str:
    """Return a complete SVG element string for a single projected wire, or ''
    if the wire produces no output.

    draftfunctions renders most wires as `<path>` elements, but a wire that
    consists of a single complete circle edge becomes a compact `<circle>`
    element (e.g. a sketch circle); both forms are handled here. Open wires
    are not closed with a 'Z' segment. `cut_type` is the Shaper cutType value
    as spelled for SVG (e.g. 'onLine'), or None to omit the attribute;
    `depth_attr` is a pre-formatted ` shaper:cutDepth="..."` attribute or '';
    `stroke_width` is omitted entirely when None.
    """
    svg_str = _get_path_element(wire)
    stripped = svg_str.strip()

    cut_attrs = ''
    if cut_type is not None:
        cut_attrs += f' shaper:cutType="{cut_type}"'
    cut_attrs += depth_attr

    width_attr = ''
    if stroke_width is not None:
        width_attr = f' stroke-width="{stroke_width}"'

    if stripped.startswith('<circle'):
        attrs = dict(re.findall(r'\s(\w+)="([^"]*)"', stripped))
        if 'cx' not in attrs or 'r' not in attrs:
            return ''
        return (f'  <circle cx="{attrs["cx"]}" cy="{attrs["cy"]}" r="{attrs["r"]}" '
                f'fill="{fill}" stroke="{stroke}"{width_attr}{cut_attrs}/>')

    d = _extract_path_d(svg_str)
    if not d:
        return ''
    # draftfunctions always closes paths; undo that for open wires so that an
    # "on line" cut doesn't cut the synthetic closing segment.
    if not wire.isClosed():
        d = d.strip()
        if d.endswith('Z'):
            d = d[:-1].rstrip()

    return (f'  <path d="{d}" fill="{fill}" stroke="{stroke}"'
            f'{width_attr}{cut_attrs}/>')


def intersect_lines_2d(p1_start: App.Vector, p1_end: App.Vector,
                       p2_start: App.Vector, p2_end: App.Vector):
    """Intersection of the two infinite lines through the given points, in the
    XY plane. Returns an App.Vector, or None if the lines are parallel."""
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
    return App.Vector(ix, iy, p1_start.z)  # all z coords will be the same, just pick one
