# Rick TV enclosure

[Project overview](../../README.md) · [Hardware](../README.md) · [BOM](../BOM.md)

![Assembled view rendered from the supplied STL geometry](render.png)

- [tv-parametric-model.stl](tv-parametric-model.stl): the supplied mesh with
  the parts arranged for printing. GitHub can preview the STL.
- [tv-parametric-model.scad](tv-parametric-model.scad): the supplied editable
  OpenSCAD source. Set `layout = "assembled"` for the assembled view or
  `layout = "printing"` for the part layout.
- [render.png](render.png): an assembled geometry preview, not a photograph of
  the electronics or a print-fit validation.

The STL and SCAD are preserved byte-for-byte from the supplied files. The
renderer repositions the STL's six separate parts using the source's assembly
transforms. It includes the decorative antennas
present in the CAD model; the demonstrated physical build has no antennas fitted.

## Dimensions and fit

The main body is based on a **70 mm radius** sphere with **3 mm walls**, cut
flat at `base_z = -55`. This gives a nominal 140 mm body width and 125 mm body
height, before knobs and antennas.

The file includes a front shell, rear shell, volume knob, button cap, and two
antennas. The button stem-hole diameter and depth, knob recess, and knob tube
sizes are exposed as OpenSCAD parameters.

**Speaker fit needs attention.** The rear pocket in the supplied source is
**77.5 mm** in diameter, with a **72 mm** cone-relief cut. The BOM's Adafruit
#3968 speaker is **40 mm** across. Those are different mounts: the model needs
an adapter or a revised pocket to locate that speaker. The files have not been
altered to imply a fit that has not been checked.

The display cavity is 70×52 mm, the power-breakout opening is 14×7 mm, and
case fastener features use 2.5 mm pilot / 3.2 mm clearance / 6.5 mm counterbore
diameters. Confirm the actual board, switch, potentiometer, and screws against
the print. The provided source does not include dedicated amplifier standoffs.

## Preparing a print

Open the supplied STL in your slicer, split it into its separate parts, and
check bed contact for each part. In particular, the spherical antenna tips may
need support or a different orientation. The source's `printing` layout is an
arrangement of parts, not a verified support-free print recipe.

A starting point is PLA, 0.2 mm layers, 3 walls, and 15% infill. Inspect the
cavities, bridges, and antenna overhangs in the slicer before selecting supports.
No new print or mechanical fit test was performed for this documentation.

## Recreate the preview

The included CPU renderer requires Python, NumPy, and Pillow. From this
folder, run:

```sh
python3 render_preview.py tv-parametric-model.stl render.png --printing-layout
```

This reconstructs the assembly from the six connected parts of the supplied
STL using the translations and rotations in the SCAD file. It does not modify
the mesh. This reconstruction is specific to the supplied layout; if you edit
the geometry or layout parameters, export a new assembled binary STL from
OpenSCAD and pass it to the renderer without `--printing-layout`.
