# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui

from enum import Enum
from typing import List, Iterable, Optional, Set


SUPPORTED_PLANE_TYPES = [
    'App::Plane',
    'Part::Plane',
    'Part::DatumPlane',
    'PartDesign::Plane',
]
SUPPORTED_SKETCH_TYPES = [
    'Sketcher::SketchObject',
    'Part::Part2DObject',
    'Part::Part2DObjectPython',
]


class ShaperCutoutType(Enum):
    # Numeric values are arbitrary and should never be used.
    CUTOUT = 1
    DADOS = 2
    MITER = 3
    SLOT = 4
    SVG_PAGE = 10
    SVG_IMAGE = 11
    SVG_SHAPE = 12
    PLANE = 20
    SKETCH = 21
    OTHER = 99

    @staticmethod
    # Note: cannot write `-> ShaperCutoutType' for this function since the version of Python
    # in CI gets confused by it.
    def type_of(obj: App.DocumentObject):
        ty = getattr(obj, 'Type', None)
        tyid = getattr(obj, 'TypeId', None)

        if ty == 'ShaperCutout':
            return ShaperCutoutType.CUTOUT
        elif ty == 'ShaperDados':
            return ShaperCutoutType.DADOS
        elif ty == 'ShaperMiter':
            return ShaperCutoutType.MITER
        elif ty == 'ShaperSlot':
            return ShaperCutoutType.SLOT
        elif ty == 'ShaperSvgPage':
            return ShaperCutoutType.SVG_PAGE
        elif ty == 'ShaperSvgImage':
            return ShaperCutoutType.SVG_IMAGE
        elif ty == 'ShaperSvgShape':
            return ShaperCutoutType.SVG_SHAPE
        elif tyid in SUPPORTED_PLANE_TYPES:
            return ShaperCutoutType.PLANE
        elif tyid in SUPPORTED_SKETCH_TYPES:
            return ShaperCutoutType.SKETCH
        else:
            return ShaperCutoutType.OTHER

    def is_type_of(self, obj: App.DocumentObject) -> bool:
        return ShaperCutoutType.type_of(obj) == self


class Objects:
    def __init__(self, selection: Iterable[App.DocumentObject]):
        self.dict: dict[ShaperCutoutType, List[App.DocumentObject]] = {}
        self.total_count = 0

        for ty in ShaperCutoutType:
            self.dict[ty] = []

        for sel in selection:
            for ty in ShaperCutoutType:
                if ty.is_type_of(sel):
                    self.dict[ty].append(sel)
            self.total_count += 1

    def is_single(self, ty: ShaperCutoutType) -> bool:
        return self.total_count == 1 and len(self.dict[ty]) == 1

    def is_nonempty_exclusive(self, ty: ShaperCutoutType) -> bool:
        return self.total_count > 0 and len(self.dict[ty]) == self.total_count

    def get_single(self, ty: ShaperCutoutType) -> App.DocumentObject:
        return self.dict[ty][0]


def all_objects(doc: App.Document, exclude: Set[App.DocumentObject] = set()) -> Objects:
    if len(exclude) == 0:
        return Objects(doc.Objects)
    else:
        return Objects(set(doc.Objects) - exclude)


def selection(children_of: Optional[App.DocumentObject] = None) -> Objects:
    # Arguably we should check App.GuiUp, but that's hard to override in testing without
    # breaking lots of stuff, so instead we directly check for the Gui.Selection attribute,
    # which is easy to set in integration tests even when there is no actual GUI.
    selection = getattr(Gui, 'Selection', None)
    if not App.ActiveDocument or not selection:
        return Objects([])

    selection = selection.getSelection()
    if children_of is not None:
        children = getattr(children_of, 'Group', None)
        if children is not None:
            selection = set(selection).intersection(set(children))
    return Objects(selection)
