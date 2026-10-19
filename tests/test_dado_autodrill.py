# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import Part
import ShaperDados

from util import assert_eq, assert_true
from util import make_cutout, make_plane, make_sketch, mm


def _make_dado_with_open_wire(doc, cutout, line_length=mm(4)):
    """Helper: create a dados with a single open-wire sketch."""
    dado_plane = cutout.FrontFace
    dado_sketch = doc.addObject("Sketcher::SketchObject", "Dado_autodrill")
    dado_sketch.AttachmentSupport = (dado_plane, [''])
    dado_sketch.MapMode = 'FlatFace'
    p1 = App.Vector(-line_length / 2, 0, 0)
    p2 = App.Vector(line_length / 2, 0, 0)
    dado_sketch.addGeometry(Part.LineSegment(p1, p2), False)

    dados = ShaperDados.create_uninitialized(cutout, "Dados_autodrill")
    dados.Label = "Dados_autodrill"
    dados.Face = dado_plane
    dados.Depth = mm(0.25)
    dados.Width = mm(0.25)
    dados.Tolerance = mm(0.01)
    dados.Sketches = [dado_sketch]
    dados.HoleDiameter = mm(0.125)
    return dados


def _count_autodrill_faces(dados):
    """Count the number of faces in the AutodrillFaces shape."""
    faces = dados.AutodrillFaces
    if faces.isNull() or not faces.Faces:
        return 0
    return len(faces.Faces)


def _run_autodrill_test(max_holes, min_dist, end_dist, line_length=mm(4),
                        expected_min=0, expected_max=None):
    """Run a single autodrill configuration and check hole count."""
    min_dist_v = min_dist.Value if hasattr(min_dist, 'Value') else min_dist
    end_dist_v = end_dist.Value if hasattr(end_dist, 'Value') else end_dist
    doc = App.newDocument(f"test_autodrill_{max_holes}_{int(min_dist_v)}_{int(end_dist_v)}")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0), rot=(0, 0, 0))
        sketch = make_sketch(doc, plane, "Outline", closed=True)
        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = sketch

        dados = _make_dado_with_open_wire(doc, cutout, line_length=line_length)
        dados.MaxHolesPerLine = max_holes
        dados.MinHoleDistance = min_dist
        dados.EndDistance = end_dist

        doc.recompute()
        n_faces = _count_autodrill_faces(dados)
        if expected_max is not None:
            assert_true(n_faces <= expected_max, f"drill faces ({n_faces}) <= max ({expected_max})")
        if expected_min is not None:
            assert_true(n_faces >= expected_min, f"drill faces ({n_faces}) >= min ({expected_min})")
        return n_faces
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_dado_autodrill_hole_counts():
    """Test autodrill with 1, 2, 3, 10, 100 max holes.

    The line is 4 inches long, so all of these should be able to fit at least
    their max_holes count (given reasonable min_distance).
    """
    ok = True
    results = {}
    # For a 4-inch line with end_distance=0.5" and min_distance=0.5",
    # we have 4 - 2*0.5 = 3 inches of usable length.
    # max_holes_that_fit = floor(3 / 0.5) + 1 = 7
    for max_holes in [1, 2, 3, 10, 100]:
        results[max_holes] = _run_autodrill_test(
            max_holes=max_holes,
            min_dist=App.Units.Quantity("0.5 in"),
            end_dist=App.Units.Quantity("0.5 in"),
            expected_max=max_holes,
        )

    # Check that more holes means more or equal drill faces
    assert_true(results[1] <= results[2], "1 hole <= 2 holes")
    assert_true(results[2] <= results[3], "2 holes <= 3 holes")
    assert_true(results[3] <= results[10], "3 holes <= 10 holes")
    assert_true(results[10] <= results[100], "10 holes <= 100 holes")
    return ok


def test_dado_autodrill_disabled():
    """MaxHolesPerLine=0 should produce no autodrill faces."""
    n = _run_autodrill_test(
        max_holes=0,
        min_dist=App.Units.Quantity("0.5 in"),
        end_dist=App.Units.Quantity("0.5 in"),
        expected_max=0,
    )
    assert_eq("autodrill face count", n, 0)


def test_dado_autodrill_edge_distances():
    """Test various end distances (edge distances)."""
    ok = True
    line_len = mm(4)  # 4 inches
    # With end_dist=0.25, usable = 4 - 0.5 = 3.5; max_holes_that_fit = floor(3.5/1)+1 = 4
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("1 in"),
        end_dist=App.Units.Quantity("0.25 in"), line_length=line_len,
        expected_max=4,
    )
    # With end_dist=1.0, usable = 4 - 2 = 2; max_holes_that_fit = floor(2/1)+1 = 3
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("1 in"),
        end_dist=App.Units.Quantity("1.0 in"), line_length=line_len,
        expected_max=3,
    )
    # With end_dist=1.5, usable = 4 - 3 = 1; max_holes_that_fit = floor(1/1)+1 = 2
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("1 in"),
        end_dist=App.Units.Quantity("1.5 in"), line_length=line_len,
        expected_max=2,
    )
    # With end_dist=2.0, usable = 4 - 4 = 0; edge.Length == 2*end_distance so
    # it still tries to fit one hole (at the center), giving 1 face
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("1 in"),
        end_dist=App.Units.Quantity("2.0 in"), line_length=line_len,
        expected_max=1,
    )
    return ok


def test_dado_autodrill_min_spacing():
    """Test various minimum hole spacings."""
    line_len = mm(4)  # 4 inches, end_dist=0.5"
    # usable = 3 inches
    # min_dist=3.0: floor(3/3)+1 = 2
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("3 in"),
        end_dist=App.Units.Quantity("0.5 in"), line_length=line_len,
        expected_max=2,
    )
    # min_dist=1.0: floor(3/1)+1 = 4
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("1 in"),
        end_dist=App.Units.Quantity("0.5 in"), line_length=line_len,
        expected_max=4,
    )
    # min_dist=0.1: floor(3/0.1)+1 = 31 n_holes; autodrill_holes adds
    # 2 end holes + n_holes loop holes (with duplicates), so we use a
    # generous upper bound
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("0.1 in"),
        end_dist=App.Units.Quantity("0.5 in"), line_length=line_len,
        expected_max=65,
    )


def test_dado_autodrill_combined():
    """Test combined min_distance and max_holes limiting.

    With a short line and large min_distance, max_holes should not matter
    much. With a long line and small min_distance, max_holes should be the
    binding constraint.
    """
    # Long line, small min_dist, max_holes=3 -> should get exactly 3
    _run_autodrill_test(
        max_holes=3, min_dist=App.Units.Quantity("0.1 in"),
        end_dist=App.Units.Quantity("0.25 in"), line_length=mm(6),
        expected_max=3,
    )
    # Short line, large min_dist, max_holes=100 -> min_dist is binding
    _run_autodrill_test(
        max_holes=100, min_dist=App.Units.Quantity("3 in"),
        end_dist=App.Units.Quantity("0.25 in"), line_length=mm(4),
        expected_max=2,
    )


def _line_autodrill_centers(doc, line_length, end_dist, min_dist, max_holes):
    """Create a single-edge open dado sketch and return the centers of the
    autodrill holes (in wire/face local coordinates along the line)."""
    from ShaperDados import autodrill_holes
    from Part import LineSegment
    wire = Part.Wire(LineSegment(App.Vector(0, 0, 0),
                                 App.Vector(line_length, 0, 0)).toShape())
    return [c for c in autodrill_holes(
        wire,
        min_distance=min_dist.Value if hasattr(min_dist, 'Value') else min_dist,
        end_distance=end_dist.Value if hasattr(end_dist, 'Value') else end_dist,
        max_holes=max_holes,
    )]


def test_dado_autodrill_no_duplicate_hole_centers():
    """Autodrill hole centers must be unique -- end holes belong to the
    evenly-spaced set, not appended twice.

    Regression: for max_holes > 1 the code appended the two end holes AND
    then generated the evenly-spaced interior points, so the end positions
    appeared twice (also uncovered because the existing tests only asserted
    a *maximum* hole count)."""
    line_len = mm(4)          # 101.6 mm
    end_dist = mm(0.5)         # 12.7 mm from each end
    usable = line_len - 2 * end_dist  # 76.2 mm

    # n=2: no interior holes; the two endpoints must each appear exactly once.
    centers = _line_autodrill_centers(None, line_len,
                                      App.Units.Quantity(f"{end_dist} mm"),
                                      App.Units.Quantity("10 mm"), 2)
    xs = sorted(round(c.x, 4) for c in centers)
    assert_eq("with n=2, hole count", len(centers), 2)
    assert_true(abs(xs[0] - end_dist) < 1e-6,
                f"first hole at end_distance from the start, got {xs[0]} vs {end_dist}")
    assert_true(abs(xs[1] - (end_dist + usable)) < 1e-6,
                f"second hole at the far end offset, got {xs[1]} vs {end_dist + usable}")

    # n=4 on the same line: positions must be unique and within tolerance of
    # the analytic spread [end, end + usable/3, end + 2*usable/3, end+usable].
    centers = _line_autodrill_centers(None, line_len,
                                      App.Units.Quantity(f"{end_dist} mm"),
                                      App.Units.Quantity("1 mm"), 4)
    xs = sorted(round(c.x, 4) for c in centers)
    assert_eq("with n=4, hole count", len(xs), 4)
    assert_eq("n=4 hole x positions unique", len(set(xs)), 4)
    spread = usable / 3.0
    expected = [end_dist, end_dist + spread, end_dist + 2 * spread, end_dist + usable]
    for got, want in zip(xs, expected):
        assert_true(abs(got - want) < 1e-3,
                    f"hole at x={got} does not match expected {want}")
    return True


def test_dado_autodrill_min_spacing_enforced_between_generated_holes():
    """Adjacent autodrill holes must never be closer than MinHoleDistance,
    even when the requested max_holes fits more holes than the minimum
    spacing would allow (the cap is applied before generation, not by
    hoping OCC deduplicates the doubled-up end points)."""
    line_len = mm(4)
    end_dist = mm(0.25)
    min_dist = mm(2.0)   # 50.8 mm, so at most 2 holes fit on a 76.2 mm run
    centers = _line_autodrill_centers(None, line_len,
                                      App.Units.Quantity(f"{end_dist} mm"),
                                      App.Units.Quantity(f"{min_dist} mm"), 100)
    xs = sorted(c.x for c in centers)
    for a, b in zip(xs[:-1], xs[1:]):
        assert_true(b - a >= min_dist - 1e-9,
                    f"adjacent holes ({a}, {b}) violate min spacing {min_dist}")
    return True


def register_tests(all_tests):
    all_tests.append(test_dado_autodrill_hole_counts)
    all_tests.append(test_dado_autodrill_disabled)
    all_tests.append(test_dado_autodrill_edge_distances)
    all_tests.append(test_dado_autodrill_min_spacing)
    all_tests.append(test_dado_autodrill_combined)
    all_tests.append(test_dado_autodrill_no_duplicate_hole_centers)
    all_tests.append(test_dado_autodrill_min_spacing_enforced_between_generated_holes)
