
import FreeCAD as App
import Part

from enum import Enum
import math
from typing import List, Optional, Tuple

from shaper_cutout_svg import intersect_lines_2d


def _same_segment(
    s1: Tuple[App.Vector, App.Vector],
    s2: Tuple[App.Vector, App.Vector],
    tol: float = 1e-6,
) -> bool:
    """True if the two (p0, p1) segments have the same endpoints (either direction)."""
    return (((s1[0] - s2[0]).Length < tol and (s1[1] - s2[1]).Length < tol)
            or ((s1[0] - s2[1]).Length < tol and (s1[1] - s2[0]).Length < tol))


def _point_segment_distance(pt: App.Vector, p0: App.Vector, p1: App.Vector) -> float:
    """Distance from `pt` to the finite segment p0-p1 (XY plane)."""
    d = p1 - p0
    len2 = d.x * d.x + d.y * d.y
    if len2 < 1e-12:
        return math.hypot(pt.x - p0.x, pt.y - p0.y)
    t = ((pt.x - p0.x) * d.x + (pt.y - p0.y) * d.y) / len2
    t = max(0.0, min(1.0, t))
    return math.hypot(pt.x - (p0.x + t * d.x), pt.y - (p0.y + t * d.y))


class SvgAnchorPlacerMode(Enum):
    VERTEX = 1
    INTERSECTION = 2


class SvgAnchorPlacerAction(Enum):
    CANCEL = 1
    CONTINUE = 2
    APPLY = 3


class SvgAnchorFrame:
    """The "frame" of a custom anchor."""

    # The Shaper custom anchor is a right triangle with legs of these lengths
    # (short leg along the anchor's X axis, long leg along its Y axis).
    ANCHOR_SHORT = 15.0
    ANCHOR_LONG = 30.0

    def __init__(
        self,
        vertex: App.Vector,
        long_dir: App.Vector,
        short_dir: App.Vector,
    ):
        self.vertex = vertex
        self._rotation = 0.0
        self._cos = 1.0
        self._sin = 0.0

        self._long_dir = long_dir
        self._short_dir = short_dir or App.Vector(-long_dir.y, long_dir.x, 0)
        assert self._long_dir.z < 1e-8
        assert self._short_dir.z < 1e-8

    def long_dir(self) -> App.Vector:
        v = self._long_dir
        return App.Vector(v.x * self._cos - v.y * self._sin, v.x * self._sin + v.y * self._cos, 0)

    def short_dir(self) -> App.Vector:
        v = self._short_dir
        return App.Vector(v.x * self._cos - v.y * self._sin, v.x * self._sin + v.y * self._cos, 0)

    def set_rotation(self, degrees: float):
        self._rotation = math.radians(degrees)
        self._cos = math.cos(self._rotation)
        self._sin = math.sin(self._rotation)

    def triangle_wire(self) -> Part.Wire:
        """Build the Shaper custom anchor triangle at `self.vertex`, with its short leg
        (ANCHOR_SHORT) along `short_dir` and its long leg (ANCHOR_LONG) along
        `long_dir`."""
        p0 = self.vertex
        p1 = p0 + self.short_dir() * self.ANCHOR_SHORT
        p2 = p0 + self.long_dir() * self.ANCHOR_LONG
        return Part.Wire(Part.makePolygon([p0, p1, p2, p0]))


class SvgAnchorPlacer:
    """State of an interactive "place custom anchor" task."""

    def __init__(self, mode: SvgAnchorPlacerMode):
        self.mode = mode
        # The point or line segment the user is hovering on
        self._hover_pt: Optional[App.Vector] = None
        self._hover_seg: Optional[Tuple[App.Vector, App.Vector]] = None
        # First segment the user has clicked on, in intersection mode
        self._seg1: Optional[Tuple[App.Vector, App.Vector]] = None
        self._frame: Optional[SvgAnchorFrame] = None
        self._ortho = False

        self._line_segments: List[Tuple[App.Vector, App.Vector]] = []
        self._snap_points: List[App.Vector] = []

        self._page_width = 0.0
        self._page_height = 0.0

    def frame(self) -> Optional[SvgAnchorFrame]:
        return self._frame

    def hover_pt(self) -> Optional[App.Vector]:
        return self._hover_pt

    def hover_seg(self) -> Optional[Tuple[App.Vector, App.Vector]]:
        return self._hover_seg

    def seg1(self) -> Optional[Tuple[App.Vector, App.Vector]]:
        return self._seg1

    def ortho(self) -> bool:
        return self._ortho

    def step_rotation(self, step_deg: float):
        if self._frame is None:
            return

        current_deg = math.degrees(self._frame._rotation)
        current_deg = step_deg * round(current_deg / step_deg)
        self._frame.set_rotation(current_deg + step_deg)

    def set_page_data(
        self,
        page_width: App.Units.Quantity,
        page_height: App.Units.Quantity,
        snap_wires: List[Part.Wire],
    ):
        self._page_width = page_width.Value
        self._page_height = page_height.Value

        segs = []
        points = []
        for wire in snap_wires:
            for edge in wire.Edges:
                if isinstance(edge.Curve, Part.Line) and len(edge.Vertexes) == 2:
                    segs.append((edge.Vertexes[0].Point, edge.Vertexes[1].Point))

                center = getattr(edge.Curve, 'Center', None)
                if center is not None and (isinstance(edge.Curve, Part.Circle)
                                           or isinstance(edge.Curve, Part.ArcOfCircle)):
                    points.append(center)
                for v in edge.Vertexes:
                    points.append(v.Point)

        self._line_segments = segs
        self._snap_points = points

    def _set_frame(self, frame: Optional[SvgAnchorFrame]):
        if not frame:
            self._frame = None
            return

        # Only set the frame if we're changing the vertex. Otherwise do nothing (preserving
        # the rotation).
        if not self._frame or self._frame.vertex != frame.vertex:
            self._frame = frame

    def update_anchor_preview(self, mouse_pt: App.Vector, tol_mm: float):
        if self.mode == SvgAnchorPlacerMode.VERTEX:
            snap = self._snap_point_near(mouse_pt, tol_mm)
            self._hover_pt = snap
            if snap is not None:
                self._set_frame(self._frame_for_vertex(snap))
            else:
                self._set_frame(None)
        elif self.mode == SvgAnchorPlacerMode.INTERSECTION:
            near = self._segment_near(mouse_pt, tol_mm)
            if near is not None:
                self._hover_seg = (near[0], near[1])
                if self._seg1 is not None:
                    frame, self._ortho = \
                        self._frame_for_intersection(self._seg1, self._hover_seg)
                    self._set_frame(frame)
                else:
                    self._set_frame(None)
            else:
                self._hover_seg = None
                self._set_frame(None)
        else:
            assert False

    def on_click(self, mouse_pt: App.Vector) -> SvgAnchorPlacerAction:
        """Handle a left click during anchor placement."""
        # Vertex mode: only one click, done if it's on a vertex
        if self.mode == SvgAnchorPlacerMode.VERTEX:
            if self._frame is None:
                # not near a snap point; ignore the click
                return SvgAnchorPlacerAction.CONTINUE
            return SvgAnchorPlacerAction.APPLY

        # Intersection mode, nothing selected: select the current segment if there is one
        assert self.mode == SvgAnchorPlacerMode.INTERSECTION
        if self._seg1 is None:
            if self._hover_seg is None:
                return SvgAnchorPlacerAction.CONTINUE
            self._seg1 = self._hover_seg
            self._hover_seg = None
            self._set_frame(None)
            return SvgAnchorPlacerAction.CONTINUE

        # Intersection mode, one segment already selected
        # Hovering back over the first edge is not a second edge; ignore.
        if self._hover_seg and _same_segment(self._seg1, self._hover_seg):
            return SvgAnchorPlacerAction.CONTINUE

        # Second click: the intersection must exist and lie on the page,
        # otherwise stop without making any changes.
        frm, _ = self._frame_for_intersection(self._seg1, self._hover_seg) \
            if self._hover_seg else (None, False)
        if frm is None:
            return SvgAnchorPlacerAction.CANCEL
        if not (0 <= frm.vertex.x <= self._page_width and 0 <= frm.vertex.y <= self._page_height):
            return SvgAnchorPlacerAction.CANCEL

        self._set_frame(frm)
        return SvgAnchorPlacerAction.APPLY

    def _segment_near(
        self,
        pt: App.Vector,
        tol: float,
    ) -> Optional[Tuple[App.Vector, App.Vector, float]]:
        """Nearest line segment to `pt` within `tol` mm, as (p0, p1, distance),
        or None."""
        best = None
        for p0, p1 in self._line_segments:
            d = _point_segment_distance(pt, p0, p1)
            if d <= tol and (best is None or d < best[2]):
                best = (p0, p1, d)
        return best

    def _snap_point_near(self, pt: App.Vector, tol: float) -> Optional[App.Vector]:
        """Nearest snap point to `pt` within `tol` mm, or None."""
        best = None
        best_d = tol
        for p in self._snap_points:
            d = (p - pt).Length
            if d <= best_d and (best is None or d < best_d):
                best, best_d = p, d
        return best

    def _frame_for_vertex(self, pt: App.Vector) -> SvgAnchorFrame:
        """Default anchor frame placed at a snapped vertex (or circle center).
        The long leg aligns with the longest straight edge incident to the
        vertex; circle centers (no incident edges) align with the page axes."""
        incident = []
        tol = 1e-3
        for p0, p1 in self._line_segments:
            if (p0 - pt).Length < tol:
                incident.append((p1 - p0, (p1 - p0).Length))
            elif (p1 - pt).Length < tol:
                incident.append((p0 - p1, (p0 - p1).Length))
        if not incident:
            return SvgAnchorFrame(pt, App.Vector(1, 0, 0), App.Vector(0, 1, 0))
        incident.sort(key=lambda x: x[1], reverse=True)
        long_dir = incident[0][0].normalize()
        short_dir = None
        # If another incident edge is orthogonal to the longest one, align the
        # short leg with it, so the anchor sits squarely in the corner.
        for d, _ in incident[1:]:
            d = d.normalize()
            if abs(long_dir.dot(d)) < 0.01:
                short_dir = d
                break
        if short_dir is None:
            short_dir = App.Vector(-long_dir.y, long_dir.x, 0)
        return SvgAnchorFrame(pt, long_dir, short_dir)

    def _frame_for_intersection(self, seg1, seg2) -> Tuple[Optional[SvgAnchorFrame], bool]:
        """Anchor frame at the intersection of two segments: the long leg
        aligns with the first segment. Returns (frame, is_orthogonal), or
        (None, False) if the segments' lines are parallel."""
        origin = intersect_lines_2d(seg1[0], seg1[1], seg2[0], seg2[1])
        if origin is None:
            return None, False
        d1 = (seg1[1] - seg1[0]).normalize()
        d2 = (seg2[1] - seg2[0]).normalize()
        orthogonal = abs(d1.dot(d2)) < 0.01  # ~0.6 degrees of tolerance
        short_dir = App.Vector(-d1.y, d1.x, 0)
        return SvgAnchorFrame(origin, d1, short_dir), orthogonal
