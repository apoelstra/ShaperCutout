# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression test: transaction rollback / undo of ShaperDados creation.

Found by GUI fuzzing: pressing Cancel on the create-Dados task panel (or
undoing a Dados creation) segfaulted FreeCAD inside
PropertyLinkBase::breakLinks. The rollback clears Dados.DadoPlane, which
re-entered ShaperDados.onChanged -> ensure_dado_plane -> Document.addObject
while breakLinks was still iterating the document's object array. The fix
guards ensure_dado_plane on Document.Transacting.
"""

import FreeCAD as App
import ShaperDados

from util import assert_true, make_plane, make_sketch, make_cutout


def dados_objects(doc):
    return [o.Name for o in doc.Objects
            if getattr(o, 'Type', '') == 'ShaperDados']


def test_dados_transaction_rollback_child():
    doc = App.newDocument("rollback_probe")
    plane = make_plane(doc, "P")
    sketch = make_sketch(doc, plane, "S")
    dsk = make_sketch(doc, plane, "DS")
    cutout = make_cutout(doc, plane, "C")
    cutout.OutlineSketch = sketch
    doc.recompute()

    # -- scenario 1: abort a create-Dados transaction (the dialog Cancel path)
    doc.openTransaction("Create Dados")
    dados = ShaperDados.create_uninitialized(cutout, "Dados")
    dados.Face = cutout.FrontFace
    dados.Invert = True
    dados.Sketches = [dsk]
    dados.recompute()
    cutout.recompute()
    doc.abortTransaction()
    assert_true(
        not dados_objects(doc),
        f"CHILD-FAIL: Dados survived abort: {dados_objects(doc)}",
    )
    assert_true(
        not list(cutout.Dados),
        f"CHILD-FAIL: cutout.Dados not restored: {list(cutout.Dados)}",
    )
    assert_true(
        cutout.FrontFace is not None and cutout.BackFace is not None,
        "CHILD-FAIL: cutout face planes damaged by abort",
    )
    print("scenario1 ok (abort)", flush=True)

    # -- scenario 2: undo an accepted create-Dados transaction (Ctrl+Z)
    doc.openTransaction("Create Dados")
    dados = ShaperDados.create_uninitialized(cutout, "Dados")
    dados.Face = cutout.FrontFace
    dados.Sketches = [dsk]
    dados.recompute()
    cutout.recompute()
    doc.commitTransaction()
    assert_true(dados_objects(doc), "CHILD-FAIL: Dados missing after commit")
    doc.undo()
    assert_true(not dados_objects(doc), f"CHILD-FAIL: Dados survived undo: {dados_objects(doc)}")
    assert_true(
        not list(cutout.Dados),
        f"CHILD-FAIL: cutout.Dados not restored after undo: {list(cutout.Dados)}",
    )

    # -- scenario 3: undo a depth tweak must restore the dado plane position
    doc.openTransaction("Create Dados")
    dados = ShaperDados.create_uninitialized(cutout, "Dados")
    dados.Face = cutout.FrontFace
    dados.Sketches = [dsk]
    doc.commitTransaction()
    z_before = dados.DadoPlane.Placement.Base.z
    doc.openTransaction("Change Depth")
    dados.Depth = 12.7
    dados.recompute()
    cutout.recompute()
    doc.commitTransaction()
    z_after = dados.DadoPlane.Placement.Base.z
    assert_true(
        abs(z_after - z_before) > 1e-6,
        "CHILD-FAIL: depth change did not move the dado plane",
    )
    doc.undo()
    z_restored = dados.DadoPlane.Placement.Base.z
    assert_true(
        abs(z_restored - z_before) < 1e-6,
        f"CHILD-FAIL: undo did not restore plane z {z_restored} != {z_before}"
    )
    print("scenario3 ok (undo depth tweak)", flush=True)


ALL_TESTS = [test_dados_transaction_rollback_child]


def register_tests(all_tests):
    all_tests.extend(ALL_TESTS)
