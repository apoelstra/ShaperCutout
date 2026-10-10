# SPDX-License-Identifier: GPL-3.0-or-later

import os
from os.path import abspath, dirname

from shaper_cutout_util.expr_template import _ExprTemplate, make_expr_template  # noqa: F401
from shaper_cutout_util.faces import cleanFaces  # noqa: F401
from shaper_cutout_util.misc import copy_property, \
    force_combo_to_value, parent_cutout  # noqa: F401
from shaper_cutout_util.selection import Objects, ShaperCutoutType, selection  # noqa: F401
from shaper_cutout_util.sketch import global_normal, objects_are_parallel  # noqa: F401

_ADDON_ROOT = dirname(dirname(dirname(dirname(abspath(__file__)))))
_ICON_ROOT = os.path.join(_ADDON_ROOT, "Resources", "Icons")
