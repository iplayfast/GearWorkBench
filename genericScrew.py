"""Generic Screw Gear generator for FreeCAD

This module provides a generic screw gear builder that can work with different
tooth profile functions (involute, cycloid, etc.).

Screw gears (also called crossed-axis helical gears) operate on non-parallel,
non-intersecting shafts, typically at 90 degrees to each other.

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""

from __future__ import division

import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher
import math


def screwGear(doc, parameters, profile_func):
    """Screw gear generator that accepts a custom tooth profile function.

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters including:
            - module: Normal module (tooth size)
            - num_teeth: Number of teeth
            - pressure_angle: Normal pressure angle in degrees
            - helix_angle: Helix angle in degrees
            - face_width: Width of gear face
            - handedness: "Right" or "Left" hand helix
            - bore_type: Type of bore ("none", "circular", "square", "hexagonal", "keyway")
            - bore_diameter: Diameter of bore
            - body_name: Name for the PartDesign Body
        profile_func: Function(sketch, parameters) that generates the tooth profile geometry

    Returns:
        The PartDesign Body containing the screw gear
    """
    body_name = parameters.get("body_name", "ScrewGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]  # Normal module
    num_teeth = parameters["num_teeth"]
    pressure_angle_deg = parameters["pressure_angle"]
    helix_angle_deg = parameters["helix_angle"]
    face_width = parameters["face_width"]
    handedness = parameters.get("handedness", "Right")
    bore_type = parameters.get("bore_type", "none")

    # Calculate effective transverse module and pitch diameter
    transverse_mod = gearMath.transverse_module(module, helix_angle_deg)
    pitch_dia = gearMath.pitch_diameter(transverse_mod, num_teeth)

    # Calculate Transverse Pressure Angle
    # tan(alpha_t) = tan(alpha_n) / cos(beta)
    alpha_n_rad = pressure_angle_deg * util.DEG_TO_RAD
    beta_rad = helix_angle_deg * util.DEG_TO_RAD
    alpha_t_rad = math.atan(math.tan(alpha_n_rad) / math.cos(beta_rad))
    pressure_angle_t_deg = alpha_t_rad * util.RAD_TO_DEG

    r_pitch = pitch_dia / 2.0
    root_dia = (
        gearMath.root_radius(pitch_dia, transverse_mod) * 2.0
    )  # Dedendum diameter from transverse module

    # 1. Dedendum Cylinder (Base Feature)
    dedendum_radius = root_dia / 2.0

    # Create base sketch for the cylinder
    base_sketch = util.createSketch(body, "BaseSketch")
    base_circle = base_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), dedendum_radius), False
    )
    base_sketch.addConstraint(
        Sketcher.Constraint("Diameter", base_circle, dedendum_radius * 2)
    )

    # Create the base pad (dedendum cylinder)
    dedendum_pad = util.createPad(body, base_sketch, face_width, "DedendumCylinder")
    body.Tip = dedendum_pad

    # 2. Tooth Profile Sketch (using transverse parameters)
    tooth_profile_sketch = util.createSketch(body, "ToothProfile2D")

    profile_params = parameters.copy()
    profile_params["module"] = transverse_mod
    profile_params["pressure_angle"] = pressure_angle_t_deg

    profile_func(tooth_profile_sketch, profile_params)

    # 3. Create the helical sweep
    screw_helix = body.newObject("PartDesign::AdditiveHelix", "ScrewToothHelix")
    screw_helix.Profile = tooth_profile_sketch
    screw_helix.Height = face_width

    # Use the body's Z-axis from Origin as reference
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]  # Z_Axis from body's Origin
    screw_helix.ReferenceAxis = (z_axis, [""])

    # Pitch for screw gear
    helix_pitch_val = abs(
        (math.pi * pitch_dia) / math.tan(helix_angle_deg * util.DEG_TO_RAD)
    )
    screw_helix.Pitch = helix_pitch_val
    if handedness == "Left":
        screw_helix.LeftHanded = True

    body.Tip = screw_helix

    # 4. Create polar pattern
    polar = body.newObject("PartDesign::PolarPattern", "ScrewTeethPolar")
    polar.Axis = (z_axis, [""])
    polar.Angle = 360
    polar.Occurrences = num_teeth
    polar.Originals = [screw_helix]
    screw_helix.Visibility = False
    polar.Visibility = True
    body.Tip = polar

    # 6. Add bore
    if bore_type != "none":
        util.createBore(body, parameters, face_width)

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return body
