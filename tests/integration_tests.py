# SPDX-License-Identifier: GPL-3.0-or-later

"""
Simple integration tests for the ShaperCutout FreeCAD workbench.

These tests are unit-test-like: each test creates a small document, exercises
one feature, and validates the resulting geometry (solids, volumes, face counts).

To run all tests:
    FreeCADCmd ./integration_test.py

To run a specific test:
    FreeCADCmd ./integration_test.py slot_two_cutouts
"""

import os
import sys
import traceback

import FreeCADGui as Gui


def print_stdout(msg):
    os.write(2, msg.encode("utf-8", errors="backslashreplace"))


########
# Setup
########
try:
    import ShaperCutout  # noqa: F401
    import ShaperDados  # noqa: F401
    import ShaperMiter  # noqa: F401
    import ShaperSlot  # noqa: F401
except Exception as e:
    print_stdout("Failed to import ShaperCutout modules. Is the ShaperCutout workbench installed?")
    print_stdout("\n\n")
    print_stdout(f"Exception: {e}")
    sys.exit(1)

try:
    import test_cutout_properties
    import test_dados
    import test_dialog_ok_cancel
    import test_report_and_page_mouse
    import test_dialog_ok_cancel
    import test_selection_type_of
    import test_dado_autodrill
    import test_dados_face_attach
    import test_dados_face_default
    import test_dados_from_sketch
    import test_dados_rollback
    import test_create_cutout_selection
    import test_miters
    import test_page_metrics
    import test_slots
    import test_svg
    import test_svg_page_widget
    import test_svg_shape
    import test_task_panel_rejection

    ALL_TESTS = []
    test_cutout_properties.register_tests(ALL_TESTS)
    test_dados.register_tests(ALL_TESTS)
    test_dialog_ok_cancel.register_tests(ALL_TESTS)
    test_report_and_page_mouse.register_tests(ALL_TESTS)
    test_dialog_ok_cancel.register_tests(ALL_TESTS)
    test_selection_type_of.register_tests(ALL_TESTS)
    test_dado_autodrill.register_tests(ALL_TESTS)
    test_dados_face_attach.register_tests(ALL_TESTS)
    test_dados_face_default.register_tests(ALL_TESTS)
    test_dados_from_sketch.register_tests(ALL_TESTS)
    test_dados_rollback.register_tests(ALL_TESTS)
    test_create_cutout_selection.register_tests(ALL_TESTS)
    test_miters.register_tests(ALL_TESTS)
    test_page_metrics.register_tests(ALL_TESTS)
    test_slots.register_tests(ALL_TESTS)
    test_svg.register_tests(ALL_TESTS)
    test_svg_page_widget.register_tests(ALL_TESTS)
    test_svg_shape.register_tests(ALL_TESTS)
    test_task_panel_rejection.register_tests(ALL_TESTS)

    Gui.setupWithoutGUI()
except Exception as e:
    print_stdout("Failed to setup test harness.")
    print_stdout("\n\n")
    print_stdout(f"Exception: {e}")
    sys.exit(1)


# Get "the arguments passed to the integration test harness" (everything
# after the script itself) and use them as name filters for the tests.
# FreeCADCmd lays sys.argv out as [binary, script, args...], so slicing at
# a fixed index silently ignores every filter; locate the script instead.
def run_test(test):
    print_stdout(f"Running {test.__name__}... ")
    try:
        test()
        print_stdout("Success\n")
    except Exception as e:
        print_stdout(f"Exception {e}\n")
        traceback.print_exception(e)
        sys.exit(1)


try:
    _idx = next(i for i, a in enumerate(sys.argv)
                if os.path.basename(a) == os.path.basename(__file__))
    filter = sys.argv[_idx + 1:]
except StopIteration:
    filter = []
if filter:
    for test in ALL_TESTS:
        for f in filter:
            if f in test.__name__:
                run_test(test)
else:
    for test in ALL_TESTS:
        run_test(test)
