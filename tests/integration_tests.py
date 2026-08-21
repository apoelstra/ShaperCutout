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

import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui

########
# Setup
########
try:
    import ShaperCutout  # noqa: F401
    import ShaperDados  # noqa: F401
    import ShaperMiter  # noqa: F401
    import ShaperSlot  # noqa: F401
except Exception as e:
    print("Failed to import ShaperCutout modules. Is the ShaperCutout workbench installed?")
    print("")
    print(f"Exception: {e}")
    sys.exit(1)

import test_dados
import test_dado_autodrill
import test_slots

ALL_TESTS = []
test_dados.register_tests(ALL_TESTS)
test_dado_autodrill.register_tests(ALL_TESTS)
test_slots.register_tests(ALL_TESTS)

########
# Main
########

Gui.setupWithoutGUI()


# Somewhat hackily get "the arguments passed to the integration test harness" and use them as
# name filters for the test.
def run_test(test):
    App.Console.PrintMessage(f"Running {test.__name__}... ")
    try:
        test()
    except Exception as e:
        App.Console.PrintError(f"Exception {e}\n")
        App.Console.PrintError(traceback.format_exception(e))
        raise e
    App.Console.PrintMessage("Success\n")


filter = sys.argv[4:]
if filter:
    for test in ALL_TESTS:
        for f in filter:
            if f in test.__name__:
                run_test(test)
else:
    for test in ALL_TESTS:
        run_test(test)
