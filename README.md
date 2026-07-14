# ShaperCutout

This is a FreeCAD extension for building objects out of plywood cut sheets. It
assumes you have a XY CNC mill, and was designed in particular for the
[Shaper Origin](https://www.shapertools.com/en-us/origin). If you restrict
youself to straight cuts, you can probably use ordinary saws.

It also supports miter cuts on straight edges, which the Shaper does not
directly support; it assumes that you will cut out pieces with the Shaper
then do a mitering pass with a table saw or with a chamfer bit on a router.

## Installation

To use the ShaperCutout workbench, just symlink it into your Mod directory.

```
ln -s . ~/.local/share/FreeCAD/Mod/
```

To find your directory, run `App.getUserAppDir()` in the Python console in FreeCAD and
tack `/Mod/` onto the end.

## Usage

The primary object in the ShaperCutout extension is the `ShaperCutout`, which can be
constructed by clicking the "Create Shaper Cutout" button (looks like a plywood cutout
with a star cut out of it). To create a cutout, you will need:

* a DatumPlane which your sheet will be centered on
* a Sketch which is attached to (or at least, parallel to) that plane

The Cutout will appear in your TreeView, and will contain the plane and outline sketch
(if you chose the "move into group" options), as well as two new planes: a back and
front face. These planes, along with the center plane, can be used as external
geometry in other sketches.

The expected workflow is, roughly:

1. Create DatumPlanes for each of your sheets.
2. Roughly draw outlines on each plane.
3. Turn the 
4. Roughly draw dado outlines on the Front and Back faces.
5. Turn the dado outlines into Dados. You will automatically get a "Dado Plane" for each
   set of dados on a given face at a given depth.
6. Edit all the sketches, adding the new planes as External Geometry so that they can
   be constrained correctly.

Once you have all our cutouts, you can export them to SVG files that can be understood by
the Origin.

