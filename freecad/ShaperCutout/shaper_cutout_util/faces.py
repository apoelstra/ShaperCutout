# SPDX-License-Identifier: GPL-3.0-or-later

import Part
from draftgeoutils import faces


def _safe_for_cleanFaces(shape):
    # TODO file a bug about this. This is literally just a copy of cleanFaces
    #  up until an unguarded call to hfaces.pop(), which will fail if you have
    #  some number of single disjoint faces.
    #
    # In fact, we should just PR to replace this whole algorithm with something more efficient
    faceset = shape.Faces

    def find(hc):
        """Find a face with the given hashcode."""
        for f in faceset:
            if f.hashCode() == hc:
                return f

    # build lookup table
    lut = {}
    for face in faceset:
        for edge in face.Edges:
            if edge.hashCode() in lut:
                lut[edge.hashCode()].append(face.hashCode())
            else:
                lut[edge.hashCode()] = [face.hashCode()]

    # print("lut:",lut)
    # take edges shared by 2 faces
    sharedhedges = []
    for k, v in lut.items():
        if len(v) == 2:
            sharedhedges.append(k)

    # print(len(sharedhedges)," shared edges:",sharedhedges)
    # find those with same normals
    targethedges = []
    for hedge in sharedhedges:
        faces = lut[hedge]
        n1 = find(faces[0]).normalAt(0.5, 0.5)
        n2 = find(faces[1]).normalAt(0.5, 0.5)
        if n1 == n2:
            targethedges.append(hedge)

    # print(len(targethedges)," target edges:",targethedges)
    # get target faces
    hfaces = []
    for hedge in targethedges:
        for f in lut[hedge]:
            if f not in hfaces:
                hfaces.append(f)

    return len(hfaces) > 0


def cleanFaces(face: Part.Shape) -> Part.Shape:
    if _safe_for_cleanFaces(face):
        return faces.cleanFaces(face)
    else:
        return face
