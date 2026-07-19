# SPDX-License-Identifier: GPL-3.0-or-later

def move_to_root(obj):
    """Remove obj from any group, placing it at document root."""
    for o in obj.InList:
        if hasattr(o, 'Group') and obj in o.Group:
            grp = list(o.Group)
            grp.remove(obj)
            o.Group = grp


def insert_if_missing(container, obj):
    if obj is not None and obj not in container.Group:
        move_to_root(obj)
        grp = list(container.Group)
        grp.insert(0, obj)
        container.Group = grp
