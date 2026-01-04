"""Generic Hypoid Gear generator for FreeCAD

This module provides a generic hypoid gear builder that can work with different
tooth profile functions (involute, cycloid, etc.).

Hypoid gears are similar to bevel gears but with offset (non-intersecting) axes.
They are commonly used in automotive differentials.

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


def hypoidGear(doc, parameters, profile_func):
    """Hypoid gear generator that accepts a custom tooth profile function.

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters including:
            - module: Gear module
            - num_teeth: Number of teeth
            - face_width: Width of gear face
            - pressure_angle: Pressure angle in degrees
            - spiral_angle: Spiral angle in degrees
            - offset: Axis offset distance (hypoid-specific)
            - pitch_angle: Pitch cone angle in degrees (default 45 for 1:1 ratio)
            - bore_type: Type of bore ("none", "circular", "square", "hexagonal", "keyway")
            - bore_diameter: Diameter of bore
            - body_name: Name for the PartDesign Body
        profile_func: Function(sketch, parameters) that generates the tooth profile geometry

    Returns:
        The PartDesign Body containing the hypoid gear
    """
    body_name = parameters.get("body_name", "HypoidGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    face_width = parameters["face_width"]
    pressure_angle = parameters["pressure_angle"]
    spiral_angle = parameters["spiral_angle"]
    offset = parameters.get("offset", 0.0)
    pitch_angle = parameters.get("pitch_angle", 45.0)

    # --- 1. Calculate Geometry ---
    # Pitch Radius (Outer)
    r_pitch = (module * num_teeth) / 2.0

    # Cone Distance (Apex to Outer Pitch Circle)
    sin_delta = math.sin(pitch_angle * util.DEG_TO_RAD)
    if sin_delta < 0.001:
        sin_delta = 0.001
    cone_dist = r_pitch / sin_delta

    # Clamp Face Width
    if face_width > cone_dist * 0.5:
        face_width = cone_dist * 0.5
        App.Console.PrintWarning(f"Face width clamped to {face_width}mm\n")

    # Inner Cone Distance
    cone_dist_inner = cone_dist - face_width

    # Scale Factor (for the inner profile)
    scale_factor = cone_dist_inner / cone_dist

    # Inner Module (virtual)
    module_inner = module * scale_factor

    # Placement Z-coordinates (Apex at Origin 0,0,0)
    # Add offset to shift the gear along Z axis
    z_outer = cone_dist + offset
    z_inner = cone_dist_inner + offset

    # --- 2. Create Core Body (Root Cone) ---
    dedendum = module * gearMath.DEDENDUM_FACTOR
    dedendum_inner = module_inner * gearMath.DEDENDUM_FACTOR

    r_root_outer = r_pitch - (dedendum * math.cos(pitch_angle * util.DEG_TO_RAD))
    r_root_inner = (r_pitch * scale_factor) - (
        dedendum_inner * math.cos(pitch_angle * util.DEG_TO_RAD)
    )

    if r_root_outer < 0.1:
        r_root_outer = 0.1
    if r_root_inner < 0.1:
        r_root_inner = 0.1

    # Sketch for Root Cone Outer
    sk_core_out = util.createSketch(body, "CoreCircle_Outer")
    sk_core_out.MapMode = "Deactivated"
    c1 = sk_core_out.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), r_root_outer), False
    )
    sk_core_out.addConstraint(Sketcher.Constraint("Diameter", c1, r_root_outer * 2))
    sk_core_out.Placement = App.Placement(
        App.Vector(0, 0, z_outer), App.Rotation(0, 0, 0)
    )

    # Sketch for Root Cone Inner
    sk_core_in = util.createSketch(body, "CoreCircle_Inner")
    sk_core_in.MapMode = "Deactivated"
    c2 = sk_core_in.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), r_root_inner), False
    )
    sk_core_in.addConstraint(Sketcher.Constraint("Diameter", c2, r_root_inner * 2))
    sk_core_in.Placement = App.Placement(
        App.Vector(0, 0, z_inner), App.Rotation(0, 0, 0)
    )

    # Create Base Cone Loft
    base_loft = body.newObject("PartDesign::AdditiveLoft", "BaseCone")
    base_loft.Profile = sk_core_out
    base_loft.Sections = [sk_core_in]
    base_loft.Ruled = True
    body.Tip = base_loft

    # --- 3. Create Tooth Profiles ---

    # Spiral / Twist Calculation
    twist_angle_deg = 0.0
    if abs(spiral_angle) > 0.001:
        cone_dist_mean = (cone_dist + cone_dist_inner) / 2.0
        r_mean = cone_dist_mean * sin_delta
        twist_arc = face_width * math.tan(spiral_angle * util.DEG_TO_RAD)
        twist_angle_rad = twist_arc / r_mean
        twist_angle_deg = twist_angle_rad * util.RAD_TO_DEG

    # Parameter sets
    params_outer = parameters.copy()
    params_inner = parameters.copy()
    params_inner["module"] = module_inner  # Automatically scales the geometry

    # Sketch Outer Tooth
    sk_tooth_out = util.createSketch(body, "ToothProfile_Outer")
    profile_func(sk_tooth_out, params_outer)
    sk_tooth_out.MapMode = "Deactivated"
    sk_tooth_out.Placement = App.Placement(
        App.Vector(0, 0, z_outer), App.Rotation(0, 0, 0)
    )

    # Sketch Inner Tooth
    sk_tooth_in = util.createSketch(body, "ToothProfile_Inner")
    profile_func(sk_tooth_in, params_inner)
    sk_tooth_in.MapMode = "Deactivated"
    # Apply Twist Rotation around Z-axis
    sk_tooth_in.Placement = App.Placement(
        App.Vector(0, 0, z_inner), App.Rotation(App.Vector(0, 0, 1), twist_angle_deg)
    )

    # --- 4. Loft the Tooth ---
    tooth_loft = body.newObject("PartDesign::AdditiveLoft", "Tooth")
    tooth_loft.Profile = sk_tooth_out
    tooth_loft.Sections = [sk_tooth_in]
    tooth_loft.Ruled = False  # Smooth interpolation

    # --- 5. Pattern the Tooth ---
    polar = util.createPolar(body, tooth_loft, sk_core_out, num_teeth, "Teeth")
    polar.Originals = [tooth_loft]
    body.Tip = polar

    # --- 6. Bore ---
    if parameters.get("bore_type", "none") != "none":
        z_outer_place = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0, 0, 0))
        util.createBore(
            body, parameters, cone_dist + 10.0, placement=z_outer_place, reversed=False
        )

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return body
