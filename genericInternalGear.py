"""Internal Gear Framework for FreeCAD

This module provides a unified framework for creating internal (ring) gear types
using a master herringbone gear builder that handles all cases through
helix angle distribution parameters.

Refactored to use Boolean Cut with EXTERNAL TOOTH PROFILE (The Gap).
Fixes:
- Adds clearance epsilon to cutter to prevent coincident face errors.

Copyright 2025, Chris Bruner
Version v1.3.0
License LGPL V2.1
"""

import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher
import os
import math
from typing import Optional, Callable
from PySide import QtCore

# Import shared VarSet watcher from the generic gear module
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")

version = "Dec 31, 2025"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VALIDATION
# ============================================================================


def validateInternalParameters(parameters):
    """Validate common internal gear parameters."""
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")


# ============================================================================
# PROFILE GENERATORS
# ============================================================================


def generateInternalCutterProfile(sketch, parameters):
    """
    Generates the CUTTER profile.
    For an internal gear, the 'Gap' is the shape of an EXTERNAL tooth.
    So we call the standard external tooth generator here.

    IMPORTANT: We add a small positive profile shift to the cutter to create
    backlash clearance, allowing the external gear to fit into the gap.
    """
    # Add backlash clearance by increasing the cutter's profile shift
    # This makes the tooth gap slightly larger than the mating tooth
    cutter_params = parameters.copy()

    # Use backlash parameter (default 0.15 for 3D printing, typical range 0.05-0.25)
    backlash = parameters.get("backlash", 0.15)
    original_shift = parameters.get("profile_shift", 0.0)
    cutter_params["profile_shift"] = original_shift + backlash

    gearMath.generateToothProfile(sketch, cutter_params)


def generateInternalHelicalCutterProfile(sketch, parameters):
    """
    Generates the Helical CUTTER profile (Transverse conversion).

    IMPORTANT: We add a small positive profile shift to the cutter to create
    backlash clearance, allowing the external gear to fit into the gap.
    """
    helix_angle = parameters.get("helix_angle", 0.0)

    if helix_angle == 0:
        generateInternalCutterProfile(sketch, parameters)
        return

    # Convert to transverse values
    beta_rad = helix_angle * util.DEG_TO_RAD
    cos_beta = math.cos(beta_rad)

    mn = parameters["module"]
    alpha_n = parameters["pressure_angle"]
    alpha_n_rad = alpha_n * util.DEG_TO_RAD

    # Transverse module and pressure angle
    mt = mn / cos_beta
    alpha_t_rad = math.atan(math.tan(alpha_n_rad) / cos_beta)
    alpha_t = alpha_t_rad * util.RAD_TO_DEG

    transverse_params = parameters.copy()
    transverse_params["module"] = mt
    transverse_params["pressure_angle"] = alpha_t

    # Add backlash clearance by increasing the cutter's profile shift
    # This makes the tooth gap slightly larger than the mating tooth
    backlash = parameters.get("backlash", 0.15)
    original_shift = parameters.get("profile_shift", 0.0)
    transverse_params["profile_shift"] = original_shift + backlash

    # Generate the EXTERNAL tooth profile (which is the cutter for the gap)
    gearMath.generateToothProfile(sketch, transverse_params)


# ============================================================================
# MASTER INTERNAL GEAR BUILDER
# ============================================================================


def internalHerringboneGear(
    doc,
    parameters,
    angle1: float,
    angle2: float,
    profile_func: Optional[Callable] = None,
):
    """
    Master builder using Boolean Cut.
    """
    validateInternalParameters(parameters)

    body_name = parameters.get("body_name", "InternalGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)
    backlash = parameters.get("backlash", 0.15)

    # For herringbone gears, use helical tooth profile with transverse module
    # Calculate transverse module using the helix angle magnitude
    # For symmetric herringbone (angle2 = -angle1), use magnitude of angle1
    helix_angle_magnitude = abs(angle1) if angle1 != 0 else abs(angle2)

    if "helix_angle" not in parameters:
        parameters = parameters.copy()
        parameters["helix_angle"] = helix_angle_magnitude

    if helix_angle_magnitude != 0:
        beta_rad = helix_angle_magnitude * util.DEG_TO_RAD
        mt = parameters["module"] / math.cos(beta_rad)  # transverse module
    else:
        mt = parameters["module"]

    dw = mt * num_teeth

    # CALCULATE DIAMETERS
    # Tip Radius (Inner Hole): where the teeth END.
    ra_internal = dw / 2.0 - mt * (gearMath.ADDENDUM_FACTOR + profile_shift)

    # Root Radius (Bottom of the cut): where the teeth START.
    rf_internal = dw / 2.0 + mt * (gearMath.DEDENDUM_FACTOR - profile_shift)

    # Outer Diameter of the Part
    outer_diameter = rf_internal * 2.0 + 2 * rim_thickness

    if profile_func is None:
        profile_func = generateInternalHelicalCutterProfile

    # CUTTER CONFIGURATION
    # Use a copy of parameters - profile_shift (including backlash) will control cutter size
    cut_params = parameters.copy()
    # Note: We no longer override tip_radius here, allowing backlash to affect cutter dimensions

    # All internal gear types (spur, helix, herringbone) use the
    # three-sketch builder — the two-sketch path was removed since
    # three sketches handle all cases with simpler, unified code.
    return _createThreeSketchInternalGear(
            body,
            cut_params,
            height,
            num_teeth,
            angle1,
            angle2,
            ra_internal,
            outer_diameter,
            profile_func,
        )


def _createTwoSketchInternalGear(
    body,
    parameters,
    height,
    num_teeth,
    angle2,
    ra_internal,
    outer_diameter,
    profile_func,
):
    """Create internal gear with 2 sketches (Subtractive).

    Creates full ring, then one tooth gap, then patterns the cut.
    Much faster than patterning ring segments.
    """
    doc = body.Document

    # 1. Create FULL Ring (360-degree annulus)
    ring_sketch = util.createSketch(body, "Ring")

    # Create full circles
    outer_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0)
    inner_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), ra_internal)

    outer_circle_idx = ring_sketch.addGeometry(outer_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle_idx, 3, -1, 1))
    cst_outer = ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", outer_circle_idx, outer_diameter)
    )

    inner_circle_idx = ring_sketch.addGeometry(inner_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle_idx, 3, -1, 1))
    cst_inner = ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", inner_circle_idx, ra_internal * 2.0)
    )

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")
    vn = parameters.get("varset_name")
    if vn:
        ring_pad.setExpression("Length", f"<<{vn}>>.Height")
        ring_sketch.setExpression(f"Constraints[{cst_inner}]", f"<<{vn}>>.InnerDiameter")
        ring_sketch.setExpression(f"Constraints[{cst_outer}]", f"<<{vn}>>.OuterDiameter")

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal gear: Created ring base...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 2. Create Cutters for ONE tooth gap
    sketch_bottom = util.createSketch(body, "ToothGap_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    sketch_bottom.MapMode = "Deactivated"
    profile_func(sketch_bottom, parameters)

    sketch_top = util.createSketch(body, "ToothGap_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle2)
    )
    sketch_top.MapMode = "Deactivated"
    profile_func(sketch_top, parameters)
    if vn:
        sketch_top.setExpression("Placement.Base.z", f"<<{vn}>>.Height")

    # 3. Subtractive Loft for ONE tooth gap
    tooth_cut = body.newObject("PartDesign::SubtractiveLoft", "ToothGapCut")
    tooth_cut.Profile = sketch_bottom
    tooth_cut.Sections = [sketch_top]
    tooth_cut.Ruled = True
    tooth_cut.Refine = False

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal gear: Created tooth gap cut...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 4. Pattern the CUT operation (not the ring)
    App.Console.PrintMessage(f"Internal gear: Creating polar pattern for {num_teeth} teeth (this may take a while)...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]
    gear_teeth.Axis = (z_axis, ["N_Axis"])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [tooth_cut]
    if vn:
        gear_teeth.setExpression("Occurrences", f"<<{vn}>>.NumberOfTeeth")

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal gear: Polar pattern created, finalizing...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # Cleanup
    ring_sketch.Visibility = False
    sketch_bottom.Visibility = False
    sketch_top.Visibility = False
    tooth_cut.Visibility = False
    ring_pad.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    doc.recompute()

    # Show completion in FreeCAD Report View
    App.Console.PrintMessage(f"✓ Internal gear with {num_teeth} teeth created successfully!\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


def _createThreeSketchInternalGear(
    body,
    parameters,
    height,
    num_teeth,
    angle1,
    angle2,
    ra_internal,
    outer_diameter,
    profile_func,
):
    """
    Create internal herringbone gear as two helical halves joined at midpoint.

    This creates a true herringbone by:
    1. Bottom half: helical gear from Z=0 to Z=height/2 with helix angle = angle1
    2. Top half: helical gear from Z=height/2 to Z=height with helix angle = angle2

    For a symmetric herringbone, angle2 = -angle1.
    """
    doc = body.Document
    half_height = height / 2.0

    # Calculate sketch rotations based on helical gear math
    # Rotation = (height_segment) * tan(helix_angle) / pitch_radius
    mn = parameters["module"]
    helix_angle1 = angle1  # Helix angle in degrees for bottom half
    helix_angle2 = angle2  # Helix angle in degrees for top half

    # Use transverse module for pitch radius calculation
    if helix_angle1 != 0:
        beta_rad1 = helix_angle1 * util.DEG_TO_RAD
        mt1 = mn / math.cos(beta_rad1)
    else:
        mt1 = mn

    if helix_angle2 != 0:
        beta_rad2 = helix_angle2 * util.DEG_TO_RAD
        mt2 = mn / math.cos(beta_rad2)
    else:
        mt2 = mn

    # Use average transverse module for pitch radius (should be same for both halves)
    mt_avg = (mt1 + mt2) / 2.0
    pitch_radius = mt_avg * num_teeth / 2.0

    # Calculate rotation for each sketch
    # Bottom half: 0 to height/2 with helix_angle1
    if helix_angle1 != 0:
        rotation_middle = half_height * math.tan(helix_angle1 * util.DEG_TO_RAD) / pitch_radius
        rotation_middle_deg = rotation_middle * util.RAD_TO_DEG
    else:
        rotation_middle_deg = 0.0

    # Top half: height/2 to height with helix_angle2
    if helix_angle2 != 0:
        rotation_top_increment = half_height * math.tan(helix_angle2 * util.DEG_TO_RAD) / pitch_radius
        rotation_top_deg = rotation_middle_deg + (rotation_top_increment * util.RAD_TO_DEG)
    else:
        rotation_top_deg = rotation_middle_deg

    # 1. Create FULL Ring (360-degree annulus)
    ring_sketch = util.createSketch(body, "Ring")

    # Create full circles
    outer_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0)
    inner_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), ra_internal)

    outer_circle_idx = ring_sketch.addGeometry(outer_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle_idx, 3, -1, 1))
    cst_outer = ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", outer_circle_idx, outer_diameter)
    )

    inner_circle_idx = ring_sketch.addGeometry(inner_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle_idx, 3, -1, 1))
    cst_inner = ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", inner_circle_idx, ra_internal * 2.0)
    )

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")
    vn = parameters.get("varset_name")
    if vn:
        ring_pad.setExpression("Length", f"<<{vn}>>.Height")
        ring_sketch.setExpression(f"Constraints[{cst_inner}]", f"<<{vn}>>.InnerDiameter")
        ring_sketch.setExpression(f"Constraints[{cst_outer}]", f"<<{vn}>>.OuterDiameter")

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal herringbone: Created ring base...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 2. Create Cutters for ONE tooth gap (The Gap)
    sketch_bottom = util.createSketch(body, "ToothGap_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    sketch_bottom.MapMode = "Deactivated"
    profile_func(sketch_bottom, parameters)

    sketch_middle = util.createSketch(body, "ToothGap_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(0, 0, half_height), App.Rotation(App.Vector(0, 0, 1), rotation_middle_deg)
    )
    sketch_middle.MapMode = "Deactivated"
    profile_func(sketch_middle, parameters)
    if vn:
        sketch_middle.setExpression("Placement.Base.z", f"<<{vn}>>.Height / 2.0")

    sketch_top = util.createSketch(body, "ToothGap_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), rotation_top_deg)
    )
    sketch_top.MapMode = "Deactivated"
    profile_func(sketch_top, parameters)
    if vn:
        sketch_top.setExpression("Placement.Base.z", f"<<{vn}>>.Height")

    # 3. Apply Subtractive Lofts for ONE tooth gap
    cut_lower = body.newObject("PartDesign::SubtractiveLoft", "ToothGapLower")
    cut_lower.Profile = sketch_bottom
    cut_lower.Sections = [sketch_middle]
    cut_lower.Ruled = True
    cut_lower.Refine = False

    cut_upper = body.newObject("PartDesign::SubtractiveLoft", "ToothGapUpper")
    cut_upper.Profile = sketch_middle
    cut_upper.Sections = [sketch_top]
    cut_upper.Ruled = True
    cut_upper.Refine = False

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal herringbone: Created tooth gap cuts...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 4. Pattern BOTH CUT operations together (faster than separate patterns)
    App.Console.PrintMessage(f"Internal herringbone: Creating polar pattern for {num_teeth} teeth (this may take a while)...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]
    gear_teeth.Axis = (z_axis, ["N_Axis"])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [cut_lower, cut_upper]
    if parameters.get("varset_name"):
        gear_teeth.setExpression("Occurrences", f"<<{parameters['varset_name']}>>.NumberOfTeeth")

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal herringbone: Polar pattern created, finalizing...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # Cleanup
    ring_sketch.Visibility = False
    sketch_bottom.Visibility = False
    sketch_middle.Visibility = False
    sketch_top.Visibility = False
    cut_lower.Visibility = False
    cut_upper.Visibility = False
    ring_pad.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    doc.recompute()

    # Show completion in FreeCAD Report View
    App.Console.PrintMessage(f"✓ Internal herringbone gear with {num_teeth} teeth created successfully!\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


# ============================================================================
# SPECIALIZED INTERNAL GEAR FUNCTIONS
# ============================================================================


def internalHelixGear(
    doc, parameters, helix_angle: float, profile_func: Optional[Callable] = None
):
    if profile_func is None:
        profile_func = generateInternalHelicalCutterProfile

    params_with_helix = parameters.copy()
    params_with_helix["helix_angle"] = helix_angle

    mn = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    beta_rad = helix_angle * util.DEG_TO_RAD

    if helix_angle != 0:
        mt = mn / math.cos(beta_rad)
        pitch_radius = mt * num_teeth / 2.0
        total_rotation_rad = height * math.tan(beta_rad) / pitch_radius
        total_rotation_deg = total_rotation_rad * util.RAD_TO_DEG
    else:
        total_rotation_deg = 0.0

    # Pass same angle twice: angle1==angle2 triggers efficient 2-sketch helical mode
    return internalHerringboneGear(
        doc, params_with_helix, total_rotation_deg, total_rotation_deg, profile_func
    )


def internalSpurGear(doc, parameters, profile_func: Optional[Callable] = None):
    if profile_func is None:
        profile_func = generateInternalCutterProfile  # Use External profile as cutter

    return internalHerringboneGear(doc, parameters, 0.0, 0.0, profile_func)


# ============================================================================
# VARSET
# ============================================================================


def createInternalSpurGearVarSet(doc, name):
    """Create a VarSet for InternalSpurGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultInternalParameters()

    var_set.addProperty(
        "App::PropertyString",
        "Version",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
        1,
    ).Version = version

    var_set.addProperty(
        "App::PropertyInteger",
        "NumberOfTeeth",
        "InternalSpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength",
        "Module",
        "InternalSpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength",
        "Height",
        "InternalSpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyLength",
        "RimThickness",
        "InternalSpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Rim thickness"),
    ).RimThickness = H["rim_thickness"]

    var_set.addProperty(
        "App::PropertyAngle",
        "PressureAngle",
        "InternalSpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyFloat",
        "ProfileShift",
        "InternalSpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
    ).ProfileShift = H["profile_shift"]

    var_set.addProperty(
        "App::PropertyFloat",
        "Backlash",
        "InternalSpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance"),
    ).Backlash = 0.15

    var_set.addProperty(
        "App::PropertyLength",
        "PitchDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
        1,
    )
    var_set.setExpression("PitchDiameter", "Module * NumberOfTeeth")

    var_set.addProperty(
        "App::PropertyLength",
        "BaseDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Base circle diameter (involute origin)"),
        1,
    )
    var_set.setExpression(
        "BaseDiameter", "PitchDiameter * cos(PressureAngle)"
    )

    var_set.addProperty(
        "App::PropertyLength",
        "InnerDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Inner tip diameter"),
        1,
    )
    var_set.setExpression(
        "InnerDiameter",
        "PitchDiameter - 2 * Module * (1 + ProfileShift)",
    )

    var_set.addProperty(
        "App::PropertyLength",
        "OuterDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer root diameter"),
        1,
    )
    var_set.setExpression(
        "OuterDiameter",
        "PitchDiameter + 2 * Module * (1.25 - ProfileShift) + 2 * RimThickness",
    )

    return var_set


def createInternalHelixGearVarSet(doc, name):
    """Create a VarSet for InternalHelixGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultInternalParameters()

    var_set.addProperty(
        "App::PropertyString", "Version", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
    ).Version = version

    var_set.addProperty(
        "App::PropertyInteger", "NumberOfTeeth", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength", "Module", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength", "Height", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyLength", "RimThickness", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Rim thickness"),
    ).RimThickness = H["rim_thickness"]

    var_set.addProperty(
        "App::PropertyAngle", "HelixAngle", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle in degrees"),
    ).HelixAngle = 15.0

    var_set.addProperty(
        "App::PropertyAngle", "PressureAngle", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyFloat", "ProfileShift", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
    ).ProfileShift = H["profile_shift"]

    var_set.addProperty(
        "App::PropertyFloat", "Backlash", "InternalHelicalGear",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance"),
    ).Backlash = 0.15

    var_set.addProperty(
        "App::PropertyLength", "PitchDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"), 1,
    )
    var_set.setExpression("PitchDiameter",
        "Module / cos(HelixAngle) * NumberOfTeeth")

    var_set.addProperty(
        "App::PropertyLength", "BaseDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Base circle diameter (involute origin)"), 1,
    )
    var_set.setExpression("BaseDiameter", "PitchDiameter * cos(PressureAngle)")

    var_set.addProperty(
        "App::PropertyLength", "InnerDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Inner tip diameter"), 1,
    )
    var_set.setExpression("InnerDiameter",
        "PitchDiameter - 2 * Module / cos(HelixAngle) * (1 + ProfileShift)")

    var_set.addProperty(
        "App::PropertyLength", "OuterDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer root diameter"), 1,
    )
    var_set.setExpression("OuterDiameter",
        "PitchDiameter + 2 * Module / cos(HelixAngle) * (1.25 - ProfileShift) + 2 * RimThickness")

    return var_set


def createInternalHerringboneGearVarSet(doc, name):
    """Create a VarSet for InternalHerringboneGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultInternalParameters()

    var_set.addProperty(
        "App::PropertyString", "Version", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
    ).Version = version

    var_set.addProperty(
        "App::PropertyInteger", "NumberOfTeeth", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength", "Module", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength", "Height", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyLength", "RimThickness", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Rim thickness"),
    ).RimThickness = H["rim_thickness"]

    var_set.addProperty(
        "App::PropertyAngle", "Angle1", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle bottom to middle (degrees)"),
    ).Angle1 = 15.0

    var_set.addProperty(
        "App::PropertyAngle", "Angle2", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle middle to top (degrees)"),
    ).Angle2 = -15.0

    var_set.addProperty(
        "App::PropertyAngle", "PressureAngle", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyFloat", "ProfileShift", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
    ).ProfileShift = H["profile_shift"]

    var_set.addProperty(
        "App::PropertyFloat", "Backlash", "InternalHerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance"),
    ).Backlash = 0.15

    var_set.addProperty(
        "App::PropertyLength", "PitchDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"), 1,
    )
    var_set.setExpression("PitchDiameter", "Module / cos(Angle1) * NumberOfTeeth")

    var_set.addProperty(
        "App::PropertyLength", "BaseDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Base circle diameter"), 1,
    )
    var_set.setExpression("BaseDiameter", "PitchDiameter * cos(PressureAngle)")

    var_set.addProperty(
        "App::PropertyLength", "InnerDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Inner tip diameter"), 1,
    )
    var_set.setExpression("InnerDiameter",
        "PitchDiameter - 2 * Module / cos(Angle1) * (1 + ProfileShift)")

    var_set.addProperty(
        "App::PropertyLength", "OuterDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer root diameter"), 1,
    )
    var_set.setExpression("OuterDiameter",
        "PitchDiameter + 2 * Module / cos(Angle1) * (1.25 - ProfileShift) + 2 * RimThickness")

    return var_set


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================


class InternalSpurGear:
    """FeaturePython object for parametric internal spur gear."""

    def __init__(self, obj):
        self.Dirty = False
        self.recomputing = False  # Guard against concurrent recompute calls
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty(
            "App::PropertyString", "Version", "read only", "", 1
        ).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty(
            "App::PropertyLength", "Module", "InternalSpurGear", "Normal module"
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "InternalSpurGear",
            "Number of teeth",
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "InternalSpurGear",
            "Normal pressure angle",
        ).PressureAngle = H["pressure_angle"]
        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "InternalSpurGear",
            "Profile shift coefficient",
        ).ProfileShift = H["profile_shift"]
        obj.addProperty(
            "App::PropertyLength", "Height", "InternalSpurGear", "Gear height"
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyLength", "RimThickness", "InternalSpurGear", "Rim thickness"
        ).RimThickness = H["rim_thickness"]
        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "InternalSpurGear",
            "Backlash clearance (extra profile shift for tooth gaps, 0.1-0.2 for 3D printing)"
        ).Backlash = 0.15
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalSpurGear", "Body name"
        ).BodyName = "InternalSpurGear"

        # Store the actual body name created by gear generator
        self.created_body_name = None
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies

        self.Type = "InternalSpurGear"
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        doc.removeObject(old_name)  # removeObject expects a string
            self.last_body_name = new_name

        # Only mark dirty for properties that require full gear rebuild
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash"]:
            self.Dirty = True

        if prop in [
            "Module",
            "NumberOfTeeth",
            "PressureAngle",
            "ProfileShift",
            "RimThickness",
            "Backlash",
        ]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(
                    pitch_dia, module, profile_shift
                )
                outer_dia = gearMath.calcInternalDedendumDiameter(
                    pitch_dia, module, profile_shift, rim_thickness
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia
            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "backlash": float(self.Object.Backlash),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty and not self.recomputing:
            try:
                self.recomputing = True  # Mark as recomputing
                parameters = self.GetParameters()

                # Get the actual body name that was created (from our stored value)
                actual_body_name = (
                    self.created_body_name
                    if hasattr(self, "created_body_name")
                    else None
                )

                # Use the actual body name to delete the old one
                body_name = (
                    actual_body_name
                    if actual_body_name
                    else parameters.get("body_name", "InternalSpurGear")
                )

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists and has same name
                old_body = doc.getObject(body_name)
                if old_body and old_body.isValid():
                    # Delete all child objects first (features inside the body)
                    if hasattr(old_body, 'Group'):
                        for obj in old_body.Group:
                            if obj and obj.isValid():
                                try:
                                    doc.removeObject(obj.Name)
                                except Exception as e:
                                    App.Console.PrintWarning(f"Could not remove {obj.Name}: {e}\n")

                    # Now delete the body itself
                    try:
                        doc.removeObject(body_name)
                        App.Console.PrintMessage(f"Deleted old body: {body_name}\n")
                    except Exception as e:
                        App.Console.PrintError(f"Failed to delete old body: {e}\n")

                    # Wait for deletion to complete
                    doc.recompute()

                # Create new body with parameters
                internalSpurGear(doc, parameters)

                # Store the newly created body name
                new_body = doc.getObject(
                    parameters.get("body_name", "InternalSpurGear")
                )
                if new_body and new_body.isValid():
                    self.created_body_name = parameters.get(
                        "body_name", "InternalSpurGear"
                    )
                    App.Console.PrintMessage(
                        f"Created new body: {self.created_body_name}\n"
                    )

                    # (recompute is already called at end of internalSpurGear function)

                    self.Dirty = False
                    self.recomputing = False
            except Exception as e:
                self.recomputing = False  # Clear recomputing flag on error
                App.Console.PrintError(f"Internal Spur Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


def createInternalGearVarSet(doc, name):
    """Unified VarSet for internal gears (spur, helix, herringbone)."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultInternalParameters()

    var_set.addProperty(
        "App::PropertyString", "Version", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
    ).Version = version

    var_set.addProperty(
        "App::PropertyEnumeration", "GearType", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Gear style"),
    )
    var_set.GearType = ["Spur", "Helix", "Herringbone"]
    var_set.GearType = "Spur"

    var_set.addProperty(
        "App::PropertyEnumeration", "ToothProfile", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Tooth profile style"),
    )
    var_set.ToothProfile = ["Involute", "Cycloidal"]
    var_set.ToothProfile = "Involute"

    var_set.addProperty(
        "App::PropertyInteger", "NumberOfTeeth", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength", "Module", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength", "Height", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyLength", "RimThickness", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Rim thickness"),
    ).RimThickness = H["rim_thickness"]

    var_set.addProperty(
        "App::PropertyAngle", "Angle1", "Angles",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle (bottom→middle)"),
    ).Angle1 = 15.0

    var_set.addProperty(
        "App::PropertyAngle", "Angle2", "Angles",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle (middle→top)"),
    ).Angle2 = -15.0

    var_set.addProperty(
        "App::PropertyAngle", "PressureAngle", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyFloat", "ProfileShift", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
    ).ProfileShift = H["profile_shift"]

    var_set.addProperty(
        "App::PropertyFloat", "Backlash", "Gear",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance"),
    ).Backlash = 0.15

    var_set.addProperty(
        "App::PropertyFloat", "AddendumFactor", "CycloidalGear",
        QT_TRANSLATE_NOOP("App::Property", "Head height factor (~1.4 for cycloidal)"),
    ).AddendumFactor = 1.4

    var_set.addProperty(
        "App::PropertyFloat", "DedendumFactor", "CycloidalGear",
        QT_TRANSLATE_NOOP("App::Property", "Root depth factor (~1.6 for cycloidal)"),
    ).DedendumFactor = 1.6

    var_set.addProperty(
        "App::PropertyLength", "PitchDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"), 1,
    )
    var_set.setExpression("PitchDiameter",
        "Module / cos(Angle1) * NumberOfTeeth")

    var_set.addProperty(
        "App::PropertyLength", "BaseDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Base circle diameter (involute origin)"), 1,
    )
    var_set.setExpression("BaseDiameter", "PitchDiameter * cos(PressureAngle)")

    var_set.addProperty(
        "App::PropertyLength", "InnerDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Inner tip diameter"), 1,
    )
    var_set.setExpression("InnerDiameter",
        "PitchDiameter - 2 * Module / cos(Angle1) * (1 + ProfileShift)")

    var_set.addProperty(
        "App::PropertyLength", "OuterDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer root diameter"), 1,
    )
    var_set.setExpression("OuterDiameter",
        "PitchDiameter + 2 * Module / cos(Angle1) * (1.25 - ProfileShift) + 2 * RimThickness")

    return var_set


class InternalGearResult:
    """Unified FeaturePython for auto-regeneration of internal gears.

    Replaces InternalSpurGearResult, InternalHelixGearResult,
    InternalHerringboneGearResult.  Reads GearType from the VarSet
    to dispatch the correct profile function and set angle defaults.
    """

    _ANGLE_DEFAULTS = {
        "Spur": (0.0, 0.0),
        "Helix": (15.0, 15.0),
        "Herringbone": (15.0, -15.0),
    }

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_rt = None
        self._last_nt = None
        self._last_a1 = None
        self._last_a2 = None
        self._last_gt = None
        self._last_tp = None
        self._last_af = None
        self._last_df = None
        self._gt_changed = False
        self._tp_changed = False
        self._watcher = None
        self._needs_rebuild = False
        self.Type = "InternalGearResult"

        obj.addProperty(
            "App::PropertyString", "VarSetName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"), 1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString", "BodyName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString", "Status", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"), 1,
        )

        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._apply_gear_type_defaults(varset)
        self._startWatcher(varset.Name)

    def _apply_gear_type_defaults(self, vs):
        gt = str(vs.GearType)
        a1, a2 = self._ANGLE_DEFAULTS.get(gt, (0.0, 0.0))
        vs.Angle1 = a1
        vs.Angle2 = a2
        hide_angle = gt == "Spur"
        try:
            vs.setEditorMode("Angle1", 1 if hide_angle else 0)
            vs.setEditorMode("Angle2", 1 if hide_angle else 0)
        except Exception:
            pass
        tp = str(vs.ToothProfile)
        is_cycloid = tp == "Cycloidal"
        try:
            vs.setEditorMode("PressureAngle", 2 if is_cycloid else 0)
            vs.setEditorMode("ProfileShift", 2 if is_cycloid else 0)
            vs.setEditorMode("Backlash", 2 if is_cycloid else 0)
            vs.setEditorMode("BaseDiameter", 2 if is_cycloid else 0)
            vs.setEditorMode("InnerDiameter", 2 if is_cycloid else 0)
            vs.setEditorMode("AddendumFactor", 2 if not is_cycloid else 0)
            vs.setEditorMode("DedendumFactor", 2 if not is_cycloid else 0)
        except Exception:
            pass

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state
        self._varset = None
        self._rebuilding = False
        self._last_m = self._last_pa = self._last_ps = None
        self._last_bl = self._last_rt = self._last_nt = None
        self._last_a1 = self._last_a2 = self._last_gt = None
        self._last_tp = self._last_af = self._last_df = None
        self._gt_changed = self._tp_changed = False
        self._watcher = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            self._last_gt = str(v.GearType)
            self._last_tp = str(v.ToothProfile)
            if hasattr(v, "AddendumFactor"):
                self._last_af = float(v.AddendumFactor)
                self._last_df = float(v.DedendumFactor)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle",
                               "ProfileShift", "Backlash", "RimThickness",
                               "Angle1", "Angle2", "GearType", "ToothProfile",
                               "AddendumFactor", "DedendumFactor")),
        )
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try:
                App.removeDocumentObserver(self._watcher)
            except Exception:
                pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is None:
            try:
                name = self.Object.VarSetName
                self._varset = self.Object.Document.getObject(name)
            except AttributeError:
                pass
        return self._varset

    def execute(self, obj):
        pass

    def _values_changed(self):
        v = self._getVarSet()
        if not v:
            return False
        if self._last_m is None:
            return True
        EPS = 1e-9
        m = float(v.Module.Value)
        pa = float(v.PressureAngle.Value)
        ps = float(v.ProfileShift)
        bl = float(v.Backlash)
        rt = float(v.RimThickness.Value)
        nt = int(v.NumberOfTeeth)
        a1 = float(v.Angle1.Value)
        a2 = float(v.Angle2.Value)
        gt = str(v.GearType)
        return (abs(m - self._last_m) > EPS or
                abs(pa - self._last_pa) > EPS or
                abs(ps - self._last_ps) > EPS or
                abs(bl - self._last_bl) > EPS or
                abs(rt - self._last_rt) > EPS or
                nt != self._last_nt or
                abs(a1 - self._last_a1) > EPS or
                abs(a2 - self._last_a2) > EPS or
                gt != self._last_gt or
                str(v.ToothProfile) != self._last_tp or
                (hasattr(v, "AddendumFactor") and
                 (abs(float(v.AddendumFactor) - self._last_af) > EPS or
                  abs(float(v.DedendumFactor) - self._last_df) > EPS)))

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        v = self._getVarSet()
        if not v:
            return
        changed = False
        gt = str(v.GearType)
        if gt != self._last_gt:
            self._last_gt = gt
            self._gt_changed = True
            self._apply_gear_type_defaults(v)
            changed = True
        tp = str(v.ToothProfile)
        if tp != self._last_tp:
            self._last_tp = tp
            self._tp_changed = True
            self._apply_gear_type_defaults(v)
            changed = True
        if not changed and not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Regenerating..."
        except Exception:
            pass
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding:
            return
        if not self._gt_changed and not self._tp_changed and not self._values_changed():
            return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding = True
        self._gt_changed = False
        self._tp_changed = False
        varset_name = None
        try:
            v = self._getVarSet()
            if not v:
                return
            varset_name = v.Name
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            self._last_gt = str(v.GearType)
            self._last_tp = str(v.ToothProfile)
            if hasattr(v, "AddendumFactor"):
                self._last_af = float(v.AddendumFactor)
                self._last_df = float(v.DedendumFactor)

            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            if root_dia <= 0 or self._last_m <= 0 or effective_shift < -1.0 or effective_shift > 0.8:
                self.Object.Status = "Invalid params"
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            self._stopWatcher()

            self.Object.Status = "Removing old body..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            old = doc.getObject(body_name)
            if old:
                children = list(old.Group)
                for child in children:
                    for prop in child.PropertiesList:
                        try:
                            child.setExpression(prop, None)
                        except Exception:
                            pass
                for child in reversed(children):
                    try:
                        doc.removeObject(child.Name)
                    except Exception:
                        pass
                doc.removeObject(body_name)

            self.Object.Status = "Generating gear geometry..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            profile_func = generateInternalHelicalCutterProfile
            is_cycloid = self._last_tp == "Cycloidal"
            if is_cycloid:
                import cycloidGear as _cg
                profile_func = _cg.generateCycloidToothProfile
            elif self._last_gt == "Spur":
                profile_func = generateInternalCutterProfile

            parameters = {
                "module": self._last_m,
                "num_teeth": num_teeth,
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "rim_thickness": self._last_rt,
                "body_name": body_name,
                "varset_name": v.Name,
            }
            if is_cycloid:
                parameters["addendum_factor"] = self._last_af
                parameters["dedendum_factor"] = self._last_df
            internalHerringboneGear(doc, parameters, self._last_a1, self._last_a2, profile_func)
            self.Object.Status = "Up to date"
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()
        except Exception as e:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            try:
                partial = doc.getObject(body_name)
                if partial:
                    for child in list(partial.Group):
                        try:
                            doc.removeObject(child.Name)
                        except Exception:
                            pass
                    doc.removeObject(body_name)
            except Exception:
                pass
            self.Object.Status = "Error"
        finally:
            if varset_name:
                self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self):
        self._rebuild()


class InternalSpurGearResult:
    """FeaturePython for auto-regeneration of internal spur gear.

    Same DocumentObserver pattern as SpurGearResult in genericGear.py.
    """

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_rt = None
        self._last_nt = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False
        self.Type = "InternalSpurGearResult"

        obj.addProperty(
            "App::PropertyString", "VarSetName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"), 1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString", "BodyName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString", "Status", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"), 1,
        )

        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state
        self._varset = None
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_rt = None
        self._last_nt = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle",
                               "ProfileShift", "Backlash", "RimThickness")),
        )
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try:
                App.removeDocumentObserver(self._watcher)
            except Exception:
                pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is None:
            try:
                name = self.Object.VarSetName
                self._varset = self.Object.Document.getObject(name)
            except AttributeError:
                pass
        return self._varset

    def execute(self, obj):
        pass

    def _values_changed(self):
        v = self._getVarSet()
        if not v:
            return False
        if self._last_m is None:
            return True
        EPS = 1e-9
        nt = int(v.NumberOfTeeth)
        return (abs(float(v.Module.Value) - self._last_m) > EPS or
                abs(float(v.PressureAngle.Value) - self._last_pa) > EPS or
                abs(float(v.ProfileShift) - self._last_ps) > EPS or
                abs(float(v.Backlash) - self._last_bl) > EPS or
                abs(float(v.RimThickness.Value) - self._last_rt) > EPS or
                nt != self._last_nt)

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        if not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Needs regeneration"
        except Exception:
            pass

    def _on_recompute_finished(self):
        if not self._needs_rebuild:
            return
        if self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        QtCore.QTimer.singleShot(0, self._rebuild)

    def _rebuild(self):
        self._rebuilding = True
        varset_name = None
        try:
            v = self._getVarSet()
            if not v:
                return
            varset_name = v.Name
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)

            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            if root_dia <= 0 or self._last_m <= 0 or effective_shift < -1.0 or effective_shift > 0.8:
                self.Object.Status = f"Invalid params"
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            self._stopWatcher()

            old = doc.getObject(body_name)
            if old:
                children = list(old.Group)
                for child in children:
                    for prop in child.PropertiesList:
                        try:
                            child.setExpression(prop, None)
                        except Exception:
                            pass
                for child in reversed(children):
                    try:
                        doc.removeObject(child.Name)
                    except Exception:
                        pass
                doc.removeObject(body_name)

            parameters = {
                "module": self._last_m,
                "num_teeth": num_teeth,
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "rim_thickness": self._last_rt,
                "body_name": body_name,
                "varset_name": v.Name,
            }
            internalSpurGear(doc, parameters)
            self.Object.Status = "Up to date"
        except Exception as e:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            try:
                partial = doc.getObject(body_name)
                if partial:
                    for child in list(partial.Group):
                        try:
                            doc.removeObject(child.Name)
                        except Exception:
                            pass
                    doc.removeObject(body_name)
            except Exception:
                pass
            self.Object.Status = "Error"
        finally:
            if varset_name:
                self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self):
        self._rebuild()


class InternalHelixGearResult:
    """FeaturePython for auto-regeneration of internal helical gear.

    Same DocumentObserver pattern as InternalSpurGearResult.  Tracks
    additional HelixAngle parameter.
    """

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_rt = None
        self._last_nt = None
        self._last_ha = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False
        self.Type = "InternalHelixGearResult"

        obj.addProperty(
            "App::PropertyString", "VarSetName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"), 1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString", "BodyName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString", "Status", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"), 1,
        )
        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state
        self._varset = None
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_rt = None
        self._last_nt = None
        self._last_ha = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_ha = float(v.HelixAngle.Value)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle",
                               "ProfileShift", "Backlash", "RimThickness",
                               "HelixAngle")),
        )
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try:
                App.removeDocumentObserver(self._watcher)
            except Exception:
                pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is None:
            try:
                name = self.Object.VarSetName
                self._varset = self.Object.Document.getObject(name)
            except AttributeError:
                pass
        return self._varset

    def execute(self, obj):
        pass

    def _values_changed(self):
        v = self._getVarSet()
        if not v:
            return False
        if self._last_m is None:
            return True
        EPS = 1e-9
        nt = int(v.NumberOfTeeth)
        return (abs(float(v.Module.Value) - self._last_m) > EPS or
                abs(float(v.PressureAngle.Value) - self._last_pa) > EPS or
                abs(float(v.ProfileShift) - self._last_ps) > EPS or
                abs(float(v.Backlash) - self._last_bl) > EPS or
                abs(float(v.RimThickness.Value) - self._last_rt) > EPS or
                abs(float(v.HelixAngle.Value) - self._last_ha) > EPS or
                nt != self._last_nt)

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        if not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Needs regeneration"
        except Exception:
            pass

    def _on_recompute_finished(self):
        if not self._needs_rebuild:
            return
        if self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding:
            return
        if not self._values_changed():
            return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding = True
        varset_name = None
        try:
            v = self._getVarSet()
            if not v:
                return
            varset_name = v.Name
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_ha = float(v.HelixAngle.Value)

            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            if root_dia <= 0 or self._last_m <= 0 or effective_shift < -1.0 or effective_shift > 0.8:
                self.Object.Status = f"Invalid params"
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            self._stopWatcher()

            old = doc.getObject(body_name)
            if old:
                children = list(old.Group)
                for child in children:
                    for prop in child.PropertiesList:
                        try:
                            child.setExpression(prop, None)
                        except Exception:
                            pass
                for child in reversed(children):
                    try:
                        doc.removeObject(child.Name)
                    except Exception:
                        pass
                doc.removeObject(body_name)

            parameters = {
                "module": self._last_m,
                "num_teeth": num_teeth,
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "rim_thickness": self._last_rt,
                "body_name": body_name,
                "varset_name": v.Name,
            }
            internalHelixGear(doc, parameters, self._last_ha)
            self.Object.Status = "Up to date"
        except Exception as e:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            try:
                partial = doc.getObject(body_name)
                if partial:
                    for child in list(partial.Group):
                        try:
                            doc.removeObject(child.Name)
                        except Exception:
                            pass
                    doc.removeObject(body_name)
            except Exception:
                pass
            self.Object.Status = "Error"
        finally:
            if varset_name:
                self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self):
        self._rebuild()


class InternalHelixGear:
    """FeaturePython object for parametric internal helical gear."""

    def __init__(self, obj):
        self.Dirty = False
        self.recomputing = False  # Guard against concurrent recompute calls
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty(
            "App::PropertyString", "Version", "read only", "", 1
        ).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty(
            "App::PropertyLength", "Module", "InternalHelicalGear", "Normal module"
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "InternalHelicalGear",
            "Number of teeth",
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "InternalHelicalGear",
            "Normal pressure angle",
        ).PressureAngle = H["pressure_angle"]
        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "InternalHelicalGear",
            "Profile shift coefficient",
        ).ProfileShift = H["profile_shift"]
        obj.addProperty(
            "App::PropertyLength", "Height", "InternalHelicalGear", "Gear height"
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyLength",
            "RimThickness",
            "InternalHelicalGear",
            "Rim thickness",
        ).RimThickness = H["rim_thickness"]
        obj.addProperty(
            "App::PropertyAngle",
            "HelixAngle",
            "InternalHelicalGear",
            "Helix angle (must match external gear for meshing)"
        ).HelixAngle = 15.0
        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "InternalHelicalGear",
            "Backlash clearance (extra profile shift for tooth gaps, 0.1-0.2 for 3D printing)"
        ).Backlash = 0.15
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalHelicalGear", "Body name"
        ).BodyName = "InternalHelixGear"

        self.Type = "InternalHelixGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        doc.removeObject(old_name)  # removeObject expects a string
            self.last_body_name = new_name

        # Only mark dirty for properties that require full gear rebuild
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash"]:
            self.Dirty = True

        if prop in [
            "Module",
            "NumberOfTeeth",
            "PressureAngle",
            "ProfileShift",
            "RimThickness",
            "HelixAngle",
            "Backlash",
        ]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value
                helix_angle = fp.HelixAngle.Value

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                outer_dia = gearMath.calcInternalDedendumDiameter(
                    pitch_dia, mt, profile_shift, rim_thickness
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia
            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "helix_angle": float(self.Object.HelixAngle.Value),
            "backlash": float(self.Object.Backlash),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty and not self.recomputing:
            try:
                self.recomputing = True  # Mark as recomputing
                parameters = self.GetParameters()

                # Get body name from the actual object, not parameters dict
                body_name_from_prop = (
                    str(self.Object.BodyName)
                    if hasattr(self.Object, "BodyName")
                    else None
                )

                # Use the property value if available
                body_name = (
                    body_name_from_prop
                    if body_name_from_prop
                    else parameters.get("body_name", "InternalHelixGear")
                )

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists and has same name
                old_body = doc.getObject(body_name)
                old_placement = None

                if old_body and old_body.isValid():
                    # Store current placement to reapply
                    old_placement = old_body.Placement

                    # Delete all child objects first (features inside the body)
                    if hasattr(old_body, 'Group'):
                        for obj in old_body.Group:
                            if obj and obj.isValid():
                                try:
                                    doc.removeObject(obj.Name)
                                except Exception as e:
                                    App.Console.PrintWarning(f"Could not remove {obj.Name}: {e}\n")

                    # Now delete the body itself
                    try:
                        doc.removeObject(body_name)
                        App.Console.PrintMessage(f"Deleted old body: {body_name}\n")
                    except Exception as e:
                        App.Console.PrintError(f"Failed to delete old body: {e}\n")

                    # Wait for deletion to complete
                    doc.recompute()

                    # Create new body with parameters
                    internalHelixGear(doc, parameters, parameters["helix_angle"])

                    # Restore placement if possible
                    new_body = doc.getObject(body_name)
                    if new_body and hasattr(old_placement, "Base"):
                        new_body.Placement = old_placement
                        App.Console.PrintMessage(
                            f"Restored placement for {body_name}\n"
                        )

                    # (recompute is already called at end of internalHelixGear function)

                    self.Dirty = False
                    self.recomputing = False
                else:
                    # No old body, just create new one
                    internalHelixGear(doc, parameters, parameters["helix_angle"])
                    self.Dirty = False
                    self.recomputing = False  # Clear recomputing flag
                    App.ActiveDocument.recompute()
            except Exception as e:
                self.recomputing = False  # Clear recomputing flag on error
                App.Console.PrintError(f"Internal Helical Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


class InternalHerringboneGear:
    """FeaturePython object for parametric internal herringbone gear."""

    def __init__(self, obj):
        self.Dirty = False
        self.recomputing = False  # Guard against concurrent recompute calls
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty(
            "App::PropertyString", "Version", "read only", "", 1
        ).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty(
            "App::PropertyLength", "Module", "InternalHerringboneGear", "Normal module"
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "InternalHerringboneGear",
            "Number of teeth",
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "InternalHerringboneGear",
            "Normal pressure angle",
        ).PressureAngle = H["pressure_angle"]
        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "InternalHerringboneGear",
            "Profile shift coefficient",
        ).ProfileShift = H["profile_shift"]
        obj.addProperty(
            "App::PropertyLength", "Height", "InternalHerringboneGear", "Gear height"
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyLength",
            "RimThickness",
            "InternalHerringboneGear",
            "Rim thickness",
        ).RimThickness = H["rim_thickness"]
        obj.addProperty(
            "App::PropertyAngle",
            "Angle1",
            "InternalHerringboneGear",
            "First helix angle (bottom to middle)"
        ).Angle1 = 15.0
        obj.addProperty(
            "App::PropertyAngle",
            "Angle2",
            "InternalHerringboneGear",
            "Second helix angle (middle to top)"
        ).Angle2 = -15.0
        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "InternalHerringboneGear",
            "Backlash clearance (extra profile shift for tooth gaps, 0.1-0.2 for 3D printing)"
        ).Backlash = 0.15
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalHerringboneGear", "Body name"
        ).BodyName = "InternalHerringboneGear"

        self.Type = "InternalHerringboneGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        doc.removeObject(old_name)  # removeObject expects a string
            self.last_body_name = new_name

        # Only mark dirty for properties that require full gear rebuild
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash"]:
            self.Dirty = True

        if prop in [
            "Module",
            "NumberOfTeeth",
            "PressureAngle",
            "ProfileShift",
            "RimThickness",
            "Angle1",
            "Angle2",
            "Backlash",
        ]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value
                angle1 = fp.Angle1.Value
                angle2 = fp.Angle2.Value

                # Use magnitude of angle1 for helix angle (like external herringbone)
                helix_angle = abs(angle1) if angle1 != 0 else abs(angle2)

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                outer_dia = gearMath.calcInternalDedendumDiameter(
                    pitch_dia, mt, profile_shift, rim_thickness
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia
            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        angle1 = float(self.Object.Angle1.Value)
        angle2 = float(self.Object.Angle2.Value)
        # Calculate helix_angle for profile generation (magnitude of angle1)
        helix_angle = abs(angle1) if angle1 != 0 else abs(angle2)

        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "helix_angle": helix_angle,
            "angle1": angle1,
            "angle2": angle2,
            "backlash": float(self.Object.Backlash),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty and not self.recomputing:
            try:
                self.recomputing = True  # Mark as recomputing
                parameters = self.GetParameters()

                # Get body name from the actual object, not parameters dict
                body_name_from_prop = (
                    str(self.Object.BodyName)
                    if hasattr(self.Object, "BodyName")
                    else None
                )

                # Use the property value if available
                body_name = (
                    body_name_from_prop
                    if body_name_from_prop
                    else parameters.get("body_name", "InternalHerringboneGear")
                )

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists
                old_body = doc.getObject(body_name)
                old_placement = None

                if old_body and old_body.isValid():
                    # Store current placement to reapply
                    old_placement = old_body.Placement

                    # Delete all child objects first (features inside the body)
                    if hasattr(old_body, 'Group'):
                        for obj in old_body.Group:
                            if obj and obj.isValid():
                                try:
                                    doc.removeObject(obj.Name)
                                except Exception as e:
                                    App.Console.PrintWarning(f"Could not remove {obj.Name}: {e}\n")

                    # Now delete the body itself
                    try:
                        doc.removeObject(body_name)
                        App.Console.PrintMessage(f"Deleted old body: {body_name}\n")
                    except Exception as e:
                        App.Console.PrintError(f"Failed to delete old body: {e}\n")

                    # Wait for deletion to complete
                    doc.recompute()

                # Create new body with parameters using user-specified angles
                angle1 = parameters.get("angle1", 15.0)
                angle2 = parameters.get("angle2", -15.0)
                internalHerringboneGear(doc, parameters, angle1, angle2)

                # Restore placement if we had an old one
                if old_placement:
                    new_body = doc.getObject(body_name)
                    if new_body and hasattr(old_placement, "Base"):
                        new_body.Placement = old_placement
                        App.Console.PrintMessage(f"Restored placement for {body_name}\n")

                # Mark recomputing as complete
                self.Dirty = False
                self.recomputing = False
            except Exception as e:
                self.recomputing = False  # Clear recomputing flag on error
                App.Console.PrintError(f"Internal Herringbone Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


# ============================================================================
# COMMANDS
# ============================================================================


class InternalSpurGearCommand:
    """Command to create internal spur gear."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "internalSpurGear.svg"),
            "MenuText": "Internal Spur Gear",
            "ToolTip": "Create parametric internal spur gear",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "InternalSpurGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"InternalSpurGear_values{count:03d}"
            count += 1

        varset = createInternalSpurGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        InternalSpurGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject,
            os.path.join(smWB_icons_path, "internalSpurGear.svg"),
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


class InternalHelixGearCommand:
    """Command to create internal helical gear."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "internalSpurGear.svg"),
            "MenuText": "Internal Helical Gear",
            "ToolTip": "Create parametric internal helical gear (normal module)",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "InternalHelixGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"InternalHelixGear_values{count:03d}"
            count += 1

        varset = createInternalHelixGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        InternalHelixGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject,
            os.path.join(smWB_icons_path, "internalSpurGear.svg"),
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


class InternalHerringboneGearResult:
    """FeaturePython for auto-regeneration of internal herringbone gear.

    Same DocumentObserver pattern.  Tracks Angle1 and Angle2.
    """

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_rt = None
        self._last_nt = None
        self._last_a1 = None
        self._last_a2 = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False
        self.Type = "InternalHerringboneGearResult"

        obj.addProperty(
            "App::PropertyString", "VarSetName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"), 1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString", "BodyName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString", "Status", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"), 1,
        )
        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state
        self._varset = None
        self._rebuilding = False
        self._last_m = self._last_pa = self._last_ps = None
        self._last_bl = self._last_rt = self._last_nt = None
        self._last_a1 = self._last_a2 = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle",
                               "ProfileShift", "Backlash", "RimThickness",
                               "Angle1", "Angle2")),
        )
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try:
                App.removeDocumentObserver(self._watcher)
            except Exception:
                pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is None:
            try:
                name = self.Object.VarSetName
                self._varset = self.Object.Document.getObject(name)
            except AttributeError:
                pass
        return self._varset

    def execute(self, obj):
        pass

    def _values_changed(self):
        v = self._getVarSet()
        if not v or self._last_m is None:
            return v is not None
        EPS = 1e-9
        return (abs(float(v.Module.Value) - self._last_m) > EPS or
                abs(float(v.PressureAngle.Value) - self._last_pa) > EPS or
                abs(float(v.ProfileShift) - self._last_ps) > EPS or
                abs(float(v.Backlash) - self._last_bl) > EPS or
                abs(float(v.RimThickness.Value) - self._last_rt) > EPS or
                int(v.NumberOfTeeth) != self._last_nt or
                abs(float(v.Angle1.Value) - self._last_a1) > EPS or
                abs(float(v.Angle2.Value) - self._last_a2) > EPS)

    def _set_needs_rebuild(self):
        if self._rebuilding or not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Needs regeneration"
        except Exception:
            pass

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed():
            return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding = True
        varset_name = None
        try:
            v = self._getVarSet()
            if not v:
                return
            varset_name = v.Name
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_rt = float(v.RimThickness.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)

            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            if root_dia <= 0 or self._last_m <= 0 or effective_shift < -1.0 or effective_shift > 0.8:
                self.Object.Status = f"Invalid params"
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            self._stopWatcher()

            old = doc.getObject(body_name)
            if old:
                children = list(old.Group)
                for child in children:
                    for prop in child.PropertiesList:
                        try:
                            child.setExpression(prop, None)
                        except Exception:
                            pass
                for child in reversed(children):
                    try:
                        doc.removeObject(child.Name)
                    except Exception:
                        pass
                doc.removeObject(body_name)

            parameters = {
                "module": self._last_m,
                "num_teeth": num_teeth,
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "rim_thickness": self._last_rt,
                "body_name": body_name,
                "varset_name": v.Name,
            }
            internalHerringboneGear(doc, parameters, self._last_a1, self._last_a2)
            self.Object.Status = "Up to date"
        except Exception as e:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            try:
                partial = doc.getObject(body_name)
                if partial:
                    for child in list(partial.Group):
                        try:
                            doc.removeObject(child.Name)
                        except Exception:
                            pass
                    doc.removeObject(body_name)
            except Exception:
                pass
            self.Object.Status = "Error"
        finally:
            if varset_name:
                self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self):
        self._rebuild()


class InternalHerringboneGearCommand:
    """Command to create internal herringbone gear."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "InternalDoubleHelicalGear.svg"),
            "MenuText": "Internal Herringbone Gear",
            "ToolTip": "Create parametric internal herringbone gear (normal module)",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "InternalHerringboneGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"InternalHerringboneGear_values{count:03d}"
            count += 1

        varset = createInternalHerringboneGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        InternalHerringboneGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject,
            os.path.join(smWB_icons_path, "InternalDoubleHelicalGear.svg"),
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


class InternalGearCommand:
    """Command to create a unified internal gear (spur/helix/herringbone)."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "internalGear.svg"),
            "MenuText": "Create Internal &Gear",
            "ToolTip": "Create parametric internal gear (spur, helix, or herringbone)",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "InternalGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"InternalGear_values{count:03d}"
            count += 1

        varset = createInternalGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        InternalGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject,
            os.path.join(smWB_icons_path, "internalSpurGear.svg"),
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


# Register commands
try:
    FreeCADGui.addCommand("InternalGearCommand", InternalGearCommand())
    FreeCADGui.addCommand("InternalSpurGearCommand", InternalSpurGearCommand())
    FreeCADGui.addCommand("InternalHelixGearCommand", InternalHelixGearCommand())
    FreeCADGui.addCommand(
        "InternalHerringboneGearCommand", InternalHerringboneGearCommand()
    )
except Exception as e:
    App.Console.PrintError(f"Failed to register internal gear commands: {e}\n")
