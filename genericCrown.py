"""Generic Crown Gear generator for FreeCAD

This module provides a generic crown gear builder that can work with different
tooth profile functions (involute rack, cycloid rack, etc.).

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


def crownGear(doc, parameters, profile_func):
    """Crown gear generator that accepts a custom tooth profile function.

    Crown gears are disk-shaped gears with rack-like teeth radiating from the center.
    They mesh with spur gears at 90-degree angles.

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters including:
            - module: Gear module
            - num_teeth: Number of teeth
            - face_width: Radial width of gear face
            - pressure_angle: Pressure angle in degrees
            - spiral_angle: Spiral angle (0 for straight)
            - bore_type: Type of bore ("none", "circular", "square", "hexagonal", "keyway")
            - bore_diameter: Diameter of bore
            - height: Base thickness (optional, defaults to 3 * module)
            - body_name: Name for the PartDesign Body
        profile_func: Function(sketch, parameters) that generates the rack tooth profile geometry

    Returns:
        The PartDesign Body containing the crown gear
    """
    body_name = parameters.get("body_name", "CrownGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    face_width = parameters["face_width"]

    # Geometry
    r_pitch = (module * num_teeth) / 2.0
    r_outer = r_pitch
    r_inner = r_outer - face_width
    if r_inner < 1.0:
        r_inner = 1.0

    scale_factor = r_inner / r_outer
    module_inner = module * scale_factor

    dedendum = module * gearMath.DEDENDUM_FACTOR
    base_thickness = parameters.get("height", 3 * module)

    # 1. Base Disk (Created FIRST)
    sk_base = util.createSketch(body, "BaseDisk")
    sk_base.MapMode = "Deactivated"
    c_out = sk_base.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), r_outer), False
    )
    sk_base.addConstraint(Sketcher.Constraint("Diameter", c_out, r_outer * 2))
    # Place base disk top at -Dedendum (bottom of teeth)
    sk_base.Placement = App.Placement(
        App.Vector(0, 0, -dedendum), App.Rotation(0, 0, 0)
    )

    pad_base = body.newObject("PartDesign::Pad", "Base")
    pad_base.Profile = sk_base
    pad_base.Length = base_thickness
    pad_base.Reversed = True  # Extrude downwards from -dedendum
    body.Tip = pad_base

    # 2. Tooth Profiles
    rot_placement = App.Rotation(90, 0, 90)

    # Spiral Twist
    spiral_angle = parameters.get("spiral_angle", 0.0)
    twist_angle_deg = 0.0
    if abs(spiral_angle) > 0.001:
        r_mean = (r_outer + r_inner) / 2.0
        twist_arc = face_width * math.tan(spiral_angle * util.DEG_TO_RAD)
        twist_angle_rad = twist_arc / r_mean
        twist_angle_deg = twist_angle_rad * util.RAD_TO_DEG

    # Outer Profile (No Twist)
    params_out = parameters.copy()
    sk_tooth_out = util.createSketch(body, "ToothProfile_Outer")
    profile_func(sk_tooth_out, params_out)
    sk_tooth_out.MapMode = "Deactivated"
    sk_tooth_out.Placement = App.Placement(App.Vector(r_outer, 0, 0), rot_placement)

    # Inner Profile (Twisted)
    params_in = parameters.copy()
    params_in["module"] = module_inner
    sk_tooth_in = util.createSketch(body, "ToothProfile_Inner")
    profile_func(sk_tooth_in, params_in)
    sk_tooth_in.MapMode = "Deactivated"

    # Calculate Twisted Placement
    # Apply Z-rotation manually to Position and Rotation
    rot_z = App.Rotation(App.Vector(0, 0, 1), twist_angle_deg)
    final_pos = rot_z.multVec(App.Vector(r_inner, 0, 0))
    final_rot = rot_z.multiply(rot_placement)

    sk_tooth_in.Placement = App.Placement(final_pos, final_rot)

    # 3. Tooth Loft
    tooth_loft = body.newObject("PartDesign::AdditiveLoft", "Tooth")
    tooth_loft.Profile = sk_tooth_out
    tooth_loft.Sections = [sk_tooth_in]
    tooth_loft.Ruled = True
    body.Tip = tooth_loft

    # 4. Pattern
    # Use sk_base as the axis reference (Normal Axis = Z Axis)
    polar = util.createPolar(body, tooth_loft, sk_base, num_teeth, "Teeth")
    polar.Originals = [tooth_loft]
    body.Tip = polar

    # 5. Bore
    if parameters.get("bore_type", "none") != "none":
        z_top = dedendum + module + 10.0
        top_place = App.Placement(App.Vector(0, 0, z_top), App.Rotation(0, 0, 0))
        util.createBore(
            body,
            parameters,
            z_top + base_thickness + dedendum + 10.0,
            placement=top_place,
            reversed=False,
        )

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return body
