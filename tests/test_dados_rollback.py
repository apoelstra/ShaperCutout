# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression test: transaction rollback / undo of ShaperDados creation.

Found by GUI fuzzing: pressing Cancel on the create-Dados task panel (or
undoing a Dados creation) segfaulted FreeCAD inside
PropertyLinkBase::breakLinks. The rollback clears Dados.DadoPlane, which
re-entered ShaperDados.onChanged -> ensure_dado_plane -> Document.addObject
while breakLinks was still iterating the document's object array. The fix
guards ensure_dado_plane on Document.Transacting.

This test must run the scenario in a SUBPROCESS: pre-fix, the failure mode
is a hard SIGSEGV that would take the whole test harness down with it.
"""

import os
import subprocess
import sys

import FreeCAD as App

from util import assert_true


def print_stdout(msg):
    os.write(2, msg.encode("utf-8", errors="backslashreplace"))


def _child_binary():
    """Locate the FreeCADCmd-style binary we are running under."""
    cand = sys.executable
    if os.path.exists(cand):
        return cand
    cand = os.path.join(App.getHomePath(), 'bin', 'FreeCADCmd')
    if os.path.exists(cand):
        return cand
    return None


def test_dados_transaction_rollback_child():
    """Child script (abort/undo Dados) exits 0 and prints CHILD-OK."""
    binary = _child_binary()
    if binary is None:
        print_stdout("skipped (cannot locate FreeCAD binary for subprocess)")
        return
    child = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'child_dados_rollback.py')
    try:
        proc = subprocess.run(
            [binary, child], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise AssertionError("child Dados-rollback test hung (timeout 300s)")

    output = proc.stdout + proc.stderr
    if proc.returncode != 0 or 'CHILD-OK' not in proc.stdout:
        raise AssertionError(
            f"child Dados-rollback test failed (exit {proc.returncode}); "
            f"a SIGSEGV here is the DadoPlane-recreation crash:\n"
            f"--- child output ---\n{output[-4000:]}")
    assert_true('scenario1 ok' in proc.stdout, "scenario1 missing")
    assert_true('scenario2 ok' in proc.stdout, "scenario2 missing")
    assert_true('scenario3 ok' in proc.stdout, "scenario3 missing")


ALL_TESTS = [test_dados_transaction_rollback_child]


def register_tests(all_tests):
    all_tests.extend(ALL_TESTS)
