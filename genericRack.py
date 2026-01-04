"""Generic Rack generator for FreeCAD

This module provides a generic rack builder that can work with different
tooth profile functions (involute, cycloid, etc.).

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""

from __future__ import division

import FreeCAD as App
import gearMath
import util
import Part
import Sketcher
import math


def rackGear(doc, parameters, profile_func):
    """Rack gear generator that accepts a custom tooth profile function.

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters including:
            - module: Gear module
            - num_teeth: Number of teeth
            - height: Extrusion height (face width)
            - base_thickness: Thickness of base plate below roots
            - body_name: Name for the PartDesign Body
        profile_func: Function(sketch, parameters) that generates the tooth profile geometry

    Returns:
        The PartDesign Body containing the rack
    """
    body_name = parameters.get("body_name", "Rack")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    base_thickness = parameters["base_thickness"]

    pitch = math.pi * module

    # Use custom dedendum factor if provided (for cycloid and other special racks)
    dedendum_factor = parameters.get("dedendum_factor", gearMath.DEDENDUM_FACTOR)
    dedendum = module * dedendum_factor

    # Create tooth sketch and generate profile using the provided function
    tooth_sketch = util.createSketch(body, "ToothProfile")
    profile_func(tooth_sketch, parameters)
    tooth_pad = util.createPad(body, tooth_sketch, height, "Tooth")

    # Create linear pattern of teeth
    pattern = body.newObject("PartDesign::LinearPattern", "TeethPattern")
    pattern.Originals = [tooth_pad]
    pattern.Direction = (tooth_sketch, ["H_Axis"])
    pattern.Occurrences = num_teeth
    if num_teeth > 1:
        pattern.Length = (num_teeth - 1) * pitch
    else:
        pattern.Length = 0

    tooth_pad.Visibility = False
    pattern.Visibility = True
    body.Tip = pattern

    # Create base plate
    start_x = -pitch / 2.0
    end_x = (num_teeth - 1) * pitch + pitch / 2.0

    base_sketch = util.createSketch(body, "BaseProfile")
    y_root = -dedendum
    y_base = -dedendum - base_thickness

    p_tl = App.Vector(start_x, y_root, 0)
    p_tr = App.Vector(end_x, y_root, 0)
    p_br = App.Vector(end_x, y_base, 0)
    p_bl = App.Vector(start_x, y_base, 0)

    points = [p_tl, p_tr, p_br, p_bl, p_tl]
    for i in range(4):
        line = Part.LineSegment(points[i], points[i + 1])
        idx = base_sketch.addGeometry(line, False)
        base_sketch.addConstraint(Sketcher.Constraint("Block", idx))
    for i in range(4):
        base_sketch.addConstraint(
            Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1)
        )

    base_pad = util.createPad(body, base_sketch, height, "Base")

    pattern.Visibility = False
    base_pad.Visibility = True
    body.Tip = base_pad

    doc.recompute()
    if App.GuiUp:
        try:
            import FreeCADGui

            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return body
