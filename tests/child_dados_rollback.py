# SPDX-License-Identifier: GPL-3.0-or-later
"""Child script for test_dados_rollback: exercise transaction rollback of
ShaperDados creation/edits. Must be run as a SUBPROCESS (pre-fix it
segfaults the interpreter).

Exit 0 + 'CHILD-OK' on success. Any failure -> nonzero exit; SIGSEGV -> -11.
Idempotent (FreeCADCmd re-runs scripts that raise): no side effects beyond
this process.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD as App

import ShaperCutout  # noqa: F401
import ShaperDados
from util import make_plane, make_sketch, make_cutout


def dados_objects(doc):
    return [o.Name for o in doc.Objects
            if getattr(o, 'Type', '') == 'ShaperDados']


def main():
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
    if dados_objects(doc):
        print(f"CHILD-FAIL: Dados survived abort: {dados_objects(doc)}")
        return 2
    if list(cutout.Dados):
        print(f"CHILD-FAIL: cutout.Dados not restored: {list(cutout.Dados)}")
        return 2
    if cutout.FrontFace is None or cutout.BackFace is None:
        print("CHILD-FAIL: cutout face planes damaged by abort")
        return 2
    print("scenario1 ok (abort)", flush=True)

    # -- scenario 2: undo an accepted create-Dados transaction (Ctrl+Z)
    doc.openTransaction("Create Dados")
    dados = ShaperDados.create_uninitialized(cutout, "Dados")
    dados.Face = cutout.FrontFace
    dados.Sketches = [dsk]
    dados.recompute()
    cutout.recompute()
    doc.commitTransaction()
    if not dados_objects(doc):
        print("CHILD-FAIL: Dados missing after commit")
        return 2
    doc.undo()
    if dados_objects(doc):
        print(f"CHILD-FAIL: Dados survived undo: {dados_objects(doc)}")
        return 2
    if list(cutout.Dados):
        print(f"CHILD-FAIL: cutout.Dados not restored after undo: {list(cutout.Dados)}")
        return 2
    print("scenario2 ok (undo)", flush=True)

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
    if abs(z_after - z_before) < 1e-6:
        print("CHILD-FAIL: depth change did not move the dado plane")
        return 2
    doc.undo()
    z_restored = dados.DadoPlane.Placement.Base.z
    if abs(z_restored - z_before) > 1e-6:
        print(f"CHILD-FAIL: undo did not restore plane z {z_restored} != {z_before}")
        return 2
    print("scenario3 ok (undo depth tweak)", flush=True)

    return 0


try:
    rc = main()
except Exception as e:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    print(f"CHILD-FAIL: {e!r}")
    rc = 3
if rc == 0:
    print("CHILD-OK")
sys.stdout.flush()
os._exit(rc)
