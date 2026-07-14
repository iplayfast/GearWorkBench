"""Generic Rack generator for FreeCAD

This module provides a generic rack builder that can work with different
tooth profile functions (involute, cycloid, etc.).

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""

from __future__ import division

import FreeCAD as App
from . import gearMath
from . import util
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
            - angle1, angle2: Helix angles (0 for spur, same for helical,
              opposite for herringbone)
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
    angle1 = parameters.get("angle1", 0.0)
    angle2 = parameters.get("angle2", 0.0)

    pitch = math.pi * module

    dedendum_factor = parameters.get("dedendum_factor", gearMath.DEDENDUM_FACTOR)
    dedendum = module * dedendum_factor

    # Calculate rotation per unit height for helical twist
    # Linear twist: total_rotation = height * tan(angle) / (module * num_teeth / 2)
    # Rack twist is linear along the rack, not angular around a circle.
    # For a rack, the "rotation" is actually a shear / lateral shift:
    # shift_x = height * tan(helix_angle)
    # This shifts the top sketch laterally by shift_x relative to the bottom.
    half_height = height / 2.0
    if angle1 != 0:
        shift_mid = half_height * math.tan(math.radians(angle1))
    else:
        shift_mid = 0.0
    # shift_top is cumulative: middle_shift + additional from angle2
    if angle2 != 0:
        shift_top = shift_mid + half_height * math.tan(math.radians(angle2))
    else:
        shift_top = shift_mid

    # Create tooth profile sketches at Z=0, Z=half, Z=height
    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    sketch_middle = util.createSketch(body, "ToothProfile_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(shift_mid, 0, half_height), App.Rotation(0, 0, 0))
    sketch_middle.MapMode = "Deactivated"
    profile_func(sketch_middle, parameters)

    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(shift_top, 0, height), App.Rotation(0, 0, 0))
    sketch_top.MapMode = "Deactivated"
    profile_func(sketch_top, parameters)

    vn = parameters.get("varset_name")
    if vn:
        sketch_middle.setExpression("Placement.Base.z", f"<<{vn}>>.Height / 2.0")
        sketch_top.setExpression("Placement.Base.z", f"<<{vn}>>.Height")

    # Loft bottom→middle and middle→top
    loft_lower = body.newObject("PartDesign::AdditiveLoft", "ToothLower")
    loft_lower.Profile = sketch_bottom
    loft_lower.Sections = [sketch_middle]
    loft_lower.Ruled = True

    loft_upper = body.newObject("PartDesign::AdditiveLoft", "ToothUpper")
    loft_upper.Profile = sketch_middle
    loft_upper.Sections = [sketch_top]
    loft_upper.Ruled = True

    # Linear pattern of the combined loft
    pattern = body.newObject("PartDesign::LinearPattern", "TeethPattern")
    pattern.Originals = [loft_lower, loft_upper]
    pattern.Direction = (sketch_bottom, ["H_Axis"])
    pattern.Occurrences = num_teeth
    if num_teeth > 1:
        pattern.Length = (num_teeth - 1) * pitch
    else:
        pattern.Length = 0

    sketch_bottom.Visibility = False
    sketch_middle.Visibility = False
    sketch_top.Visibility = False
    loft_lower.Visibility = False
    loft_upper.Visibility = False
    pattern.Visibility = True
    body.Tip = pattern

    # Create base plate — extend to cover lateral tooth shift from helix
    max_shift_r = max(0.0, shift_mid, shift_top)
    max_shift_l = min(0.0, shift_mid, shift_top)
    start_x = -pitch / 2.0 + max_shift_l
    end_x = (num_teeth - 1) * pitch + pitch / 2.0 + max_shift_r

    base_sketch = util.createSketch(body, "BaseProfile")
    y_root = dedendum
    y_base = dedendum + base_thickness

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
    vn = parameters.get("varset_name")
    if vn:
        base_pad.setExpression("Length", f"<<{vn}>>.Height")

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
