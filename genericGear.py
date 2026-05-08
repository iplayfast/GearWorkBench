"""Generic Gear Framework for FreeCAD

This module provides a unified framework for creating different gear types
using a master herringbone gear builder that handles all cases through
helix angle distribution parameters.

Copyright 2025, Chris Bruner
Version v1.0.0
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

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def validateCommonParameters(parameters):
    """Validate common gear parameters."""
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")


def _applyOriginAndAngle(body, parameters):
    """Apply origin translation and angle rotation to the gear body.

    Args:
        body: FreeCAD body object
        parameters: Gear parameters dict with origin_x, origin_y, origin_z, and angle
    """
    origin_x = parameters.get("origin_x", 0.0)
    origin_y = parameters.get("origin_y", 0.0)
    origin_z = parameters.get("origin_z", 0.0)
    angle = parameters.get("angle", 0.0)

    # Create placement from origin and angle
    # IMPORTANT: Set the placement directly, don't multiply!
    # Multiplying would accumulate transforms on each recompute
    translation = App.Vector(origin_x, origin_y, origin_z)
    rotation = App.Rotation(App.Vector(0, 0, 1), angle)

    body.Placement = App.Placement(translation, rotation)


# ============================================================================
# SPURGEAR VARSET AND MASTER BORE FUNCTIONS
# ============================================================================


def createSpurGearVarSet(doc, name):
    """Create a VarSet for SpurGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultParameters()

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
        "SpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength",
        "Module",
        "SpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength",
        "Height",
        "SpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyLength",
        "BoreDiameter",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
    ).BoreDiameter = H["bore_diameter"]

    var_set.addProperty(
        "App::PropertyLength",
        "KeywayWidth",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
    ).KeywayWidth = 2.0

    var_set.addProperty(
        "App::PropertyLength",
        "KeywayDepth",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
    ).KeywayDepth = 1.0

    var_set.addProperty(
        "App::PropertyAngle",
        "PressureAngle",
        "SpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyFloat",
        "ProfileShift",
        "SpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
    ).ProfileShift = H["profile_shift"]

    var_set.addProperty(
        "App::PropertyFloat",
        "Backlash",
        "SpurGear",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
    ).Backlash = 0.0

    var_set.addProperty(
        "App::PropertyBool",
        "BoreEnabled",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable bore hole in gear"),
    ).BoreEnabled = True

    var_set.addProperty(
        "App::PropertyBool",
        "KeywayEnabled",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable keyway in gear"),
    ).KeywayEnabled = False

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
        "OuterDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
        1,
    )
    var_set.setExpression(
        "OuterDiameter",
        "PitchDiameter + 2 * Module * (1 + ProfileShift)",
    )

    var_set.addProperty(
        "App::PropertyLength",
        "RootDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
        1,
    )
    var_set.setExpression(
        "RootDiameter",
        "PitchDiameter - 2 * Module * (1.25 - ProfileShift)",
    )

    return var_set


def createHelixGearVarSet(doc, name):
    """Create a VarSet for HelixGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultParameters()

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
        "HelixGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength",
        "Module",
        "HelixGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength",
        "Height",
        "HelixGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyAngle",
        "HelixAngle",
        "HelixGear",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle in degrees"),
    ).HelixAngle = 15.0

    var_set.addProperty(
        "App::PropertyLength",
        "BoreDiameter",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
    ).BoreDiameter = H["bore_diameter"]

    var_set.addProperty(
        "App::PropertyLength",
        "KeywayWidth",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
    ).KeywayWidth = 2.0

    var_set.addProperty(
        "App::PropertyLength",
        "KeywayDepth",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
    ).KeywayDepth = 1.0

    var_set.addProperty(
        "App::PropertyAngle",
        "PressureAngle",
        "HelixGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyFloat",
        "ProfileShift",
        "HelixGear",
        QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
    ).ProfileShift = H["profile_shift"]

    var_set.addProperty(
        "App::PropertyFloat",
        "Backlash",
        "HelixGear",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
    ).Backlash = 0.0

    var_set.addProperty(
        "App::PropertyBool",
        "BoreEnabled",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable bore hole in gear"),
    ).BoreEnabled = True

    var_set.addProperty(
        "App::PropertyBool",
        "KeywayEnabled",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable keyway in gear"),
    ).KeywayEnabled = False

    var_set.addProperty(
        "App::PropertyLength",
        "PitchDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
        1,
    )
    var_set.setExpression("PitchDiameter",
        "Module / cos(HelixAngle) * NumberOfTeeth")

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
        "OuterDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
        1,
    )
    var_set.setExpression(
        "OuterDiameter",
        "PitchDiameter + 2 * Module / cos(HelixAngle) * (1 + ProfileShift)",
    )

    var_set.addProperty(
        "App::PropertyLength",
        "RootDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
        1,
    )
    var_set.setExpression(
        "RootDiameter",
        "PitchDiameter - 2 * Module / cos(HelixAngle) * (1.25 - ProfileShift)",
    )

    return var_set


def createHerringboneGearVarSet(doc, name):
    """Create a VarSet for HerringboneGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultParameters()

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
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength",
        "Module",
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength",
        "Height",
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyAngle",
        "Angle1",
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle bottom to middle (degrees)"),
    ).Angle1 = 15.0

    var_set.addProperty(
        "App::PropertyAngle",
        "Angle2",
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle middle to top (degrees)"),
    ).Angle2 = -15.0

    var_set.addProperty(
        "App::PropertyLength",
        "BoreDiameter",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
    ).BoreDiameter = H["bore_diameter"]

    var_set.addProperty(
        "App::PropertyLength",
        "KeywayWidth",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
    ).KeywayWidth = 2.0

    var_set.addProperty(
        "App::PropertyLength",
        "KeywayDepth",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
    ).KeywayDepth = 1.0

    var_set.addProperty(
        "App::PropertyAngle",
        "PressureAngle",
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyFloat",
        "ProfileShift",
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
    ).ProfileShift = H["profile_shift"]

    var_set.addProperty(
        "App::PropertyFloat",
        "Backlash",
        "HerringboneGear",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
    ).Backlash = 0.0

    var_set.addProperty(
        "App::PropertyBool",
        "BoreEnabled",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable bore hole in gear"),
    ).BoreEnabled = True

    var_set.addProperty(
        "App::PropertyBool",
        "KeywayEnabled",
        "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable keyway in gear"),
    ).KeywayEnabled = False

    var_set.addProperty(
        "App::PropertyLength",
        "PitchDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
        1,
    )
    var_set.setExpression("PitchDiameter", "Module / cos(Angle1) * NumberOfTeeth")

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
        "OuterDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
        1,
    )
    var_set.setExpression(
        "OuterDiameter",
        "PitchDiameter + 2 * Module / cos(Angle1) * (1 + ProfileShift)",
    )

    var_set.addProperty(
        "App::PropertyLength",
        "RootDiameter",
        "read only",
        QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
        1,
    )
    var_set.setExpression(
        "RootDiameter",
        "PitchDiameter - 2 * Module / cos(Angle1) * (1.25 - ProfileShift)",
    )

    return var_set


def createMasterBore(body, parameters, height, varset_name):
    """Create bore with expression-based circle and keyway."""
    bore_diameter = parameters.get("bore_diameter", 0.0)
    keyway_width = parameters.get("keyway_width", 2.0)
    keyway_depth = parameters.get("keyway_depth", 1.0)

    bore_sketch = util.createSketch(body, "Bore")
    circle = bore_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), bore_diameter / 2.0),
        False,
    )
    bore_sketch.addConstraint(Sketcher.Constraint("Coincident", circle, 3, -1, 1))
    cst = bore_sketch.addConstraint(Sketcher.Constraint("Diameter", circle, bore_diameter))
    bore_sketch.setExpression(f"Constraints[{cst}]", f"<<{varset_name}>>.BoreDiameter")

    bore_pocket = util.createPocket(body, bore_sketch, height, "Bore")
    bore_pocket.Reversed = True
    bore_pocket.setExpression("Length", f"<<{varset_name}>>.Height")
    bore_pocket.setExpression("Suppressed", f"<<{varset_name}>>.BoreEnabled ? False : True")

    tiny = 0.01
    key_sketch = util.createSketch(body, "Keyway")
    pts = [App.Vector(-0.5, -0.5, 0), App.Vector(0.5, -0.5, 0),
           App.Vector(0.5, 0.5, 0), App.Vector(-0.5, 0.5, 0)]
    lines = []
    for i in range(4):
        lines.append(key_sketch.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False))
    for i in range(4):
        key_sketch.addConstraint(Sketcher.Constraint("Coincident", lines[i], 2, lines[(i + 1) % 4], 1))
    key_sketch.addConstraint(Sketcher.Constraint("Horizontal", lines[0]))
    key_sketch.addConstraint(Sketcher.Constraint("Vertical", lines[1]))
    key_sketch.addConstraint(Sketcher.Constraint("Horizontal", lines[2]))
    key_sketch.addConstraint(Sketcher.Constraint("Vertical", lines[3]))

    cst = key_sketch.addConstraint(Sketcher.Constraint("DistanceX", lines[0], 1, -1, 1, -tiny))
    key_sketch.setExpression(f"Constraints[{cst}]", f"<<{varset_name}>>.KeywayWidth / -2.0")
    cst = key_sketch.addConstraint(Sketcher.Constraint("DistanceY", lines[0], 1, -1, 1, -tiny))
    key_sketch.setExpression(f"Constraints[{cst}]",
        f"<<{varset_name}>>.BoreDiameter / 2.0 - <<{varset_name}>>.KeywayDepth")
    cst = key_sketch.addConstraint(Sketcher.Constraint("DistanceX", lines[0], 2, -1, 1, tiny))
    key_sketch.setExpression(f"Constraints[{cst}]", f"<<{varset_name}>>.KeywayWidth / 2.0")
    cst = key_sketch.addConstraint(Sketcher.Constraint("DistanceY", lines[1], 2, -1, 1, tiny))
    key_sketch.setExpression(f"Constraints[{cst}]",
        f"<<{varset_name}>>.BoreDiameter / 2.0 + <<{varset_name}>>.KeywayDepth")

    key_pocket = util.createPocket(body, key_sketch, height, "Keyway")
    key_pocket.Reversed = True
    key_pocket.setExpression("Suppressed", f"<<{varset_name}>>.KeywayEnabled ? False : True")
    body.Tip = key_pocket


# ============================================================================
# MASTER GEAR BUILDER - HERRINGBONE
# ============================================================================


def herringboneGear(
    doc,
    parameters,
    angle1: float,
    angle2: float,
    profile_func: Optional[Callable] = None,
):
    """
    Master builder for all gear types using herringbone pattern.

    Creates tooth using 3 sketches (bottom, middle, top) over the full
    height, handling spur (angles=0), helical (angle1==angle2), and
    herringbone (angle1≠angle2) through rotation of the middle/top
    sketches.

    Parameters use NORMAL module convention for helical/herringbone gears.

    Args:
        doc: FreeCAD document
        parameters: Gear parameters dict
        angle1: Rotation angle from bottom to middle sketch (degrees)
        angle2: Rotation angle from middle to top sketch (degrees)
        profile_func: Optional tooth profile function (uses default if None)

    Returns:
        Dictionary with 'body' key containing created body object
    """
    validateCommonParameters(parameters)

    # Apply backlash for external gears: subtract from profile shift to make teeth thinner
    backlash = parameters.get("backlash", 0.0)
    if backlash != 0.0:
        parameters = parameters.copy()
        original_shift = parameters.get("profile_shift", 0.0)
        parameters["profile_shift"] = original_shift - backlash

    body_name = parameters.get("body_name", "GenericGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    bore_type = parameters.get("bore_type", "none")

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
    # Use custom dedendum factor if provided (for cycloid and other special gears)
    dedendum_factor = parameters.get("dedendum_factor", gearMath.DEDENDUM_FACTOR)
    df = dw - 2 * mt * (dedendum_factor - profile_shift)

    if profile_func is None:
        profile_func = gearMath.generateHelicalGearProfile

    # All gear types (spur, helix, herringbone) use the three-sketch
    # builder — the two-sketch path was removed since three sketches
    # handle all cases with simpler, unified code.
    return _createThreeSketchHerringbone(
            body,
            parameters,
            height,
            num_teeth,
            angle1,
            angle2,
            df,
            bore_type,
            profile_func,
        )


def _createTwoSketchHerringbone(
    body,
    parameters,
    height: float,
    num_teeth: int,
    angle2: float,
    df: float,
    bore_type: str,
    profile_func: Callable,
):
    """Create herringbone with 2 sketches (angle1 == 0)."""
    doc = body.Document

    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle2)
    )
    profile_func(sketch_top, parameters)

    vn = parameters.get("varset_name")
    if vn:
        sketch_top.setExpression("Placement.Base.z", f"<<{vn}>>.Height")

    tooth_loft = body.newObject("PartDesign::AdditiveLoft", "SingleTooth")
    tooth_loft.Profile = sketch_bottom
    tooth_loft.Sections = [sketch_top]
    tooth_loft.Ruled = True

    gear_teeth = util.createPolar(body, tooth_loft, sketch_bottom, num_teeth, "Teeth")
    vn = parameters.get("varset_name")
    if vn:
        gear_teeth.setExpression("Occurrences", f"<<{vn}>>.NumberOfTeeth")
    gear_teeth.Originals = [tooth_loft]
    tooth_loft.Visibility = False
    sketch_bottom.Visibility = False
    sketch_top.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    dedendum_sketch = util.createSketch(body, "DedendumCircle")
    circle = dedendum_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01), False
    )
    dedendum_sketch.addConstraint(Sketcher.Constraint("Coincident", circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint("Diameter", circle, df + 0.02))

    dedendum_pad = util.createPad(body, dedendum_sketch, height, "DedendumCircle")
    vn = parameters.get("varset_name")
    if vn:
        dedendum_pad.setExpression("Length", f"<<{vn}>>.Height")
    body.Tip = dedendum_pad

    vn = parameters.get("varset_name")
    if vn:
        createMasterBore(body, parameters, height, vn)
    elif bore_type != "none":
        bore_enabled = parameters.get("bore_enabled", True)
        if bore_enabled:
            keyway_enabled = parameters.get("keyway_enabled", True)
            util.createBore(body, parameters, height, keyway_enabled=keyway_enabled)

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    _applyOriginAndAngle(body, parameters)

    return {"body": body}


def _createThreeSketchHerringbone(
    body,
    parameters,
    height: float,
    num_teeth: int,
    angle1: float,
    angle2: float,
    df: float,
    bore_type: str,
    profile_func: Callable,
):
    """
    Create herringbone with 3 sketches as two helical halves joined at midpoint.

    This creates a true herringbone by:
    1. Bottom half: helical gear from Z=0 to Z=height/2 with helix angle = angle1
    2. Top half: helical gear from Z=height/2 to Z=height with helix angle = angle2

    For a symmetric herringbone, angle2 = -angle1.
    """
    doc = body.Document

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
    half_height = height / 2.0
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

    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    sketch_middle = util.createSketch(body, "ToothProfile_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(0, 0, half_height), App.Rotation(App.Vector(0, 0, 1), rotation_middle_deg)
    )
    profile_func(sketch_middle, parameters)

    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), rotation_top_deg)
    )
    profile_func(sketch_top, parameters)

    vn = parameters.get("varset_name")
    if vn:
        sketch_middle.setExpression("Placement.Base.z", f"<<{vn}>>.Height / 2.0")
        sketch_top.setExpression("Placement.Base.z", f"<<{vn}>>.Height")

    loft_bottom = body.newObject("PartDesign::AdditiveLoft", "BottomHalfTooth")
    loft_bottom.Profile = sketch_bottom
    loft_bottom.Sections = [sketch_middle]
    loft_bottom.Ruled = True

    loft_top = body.newObject("PartDesign::AdditiveLoft", "TopHalfTooth")
    loft_top.Profile = sketch_middle
    loft_top.Sections = [sketch_top]
    loft_top.Ruled = True

    gear_teeth = util.createPolar(body, loft_bottom, sketch_bottom, num_teeth, "Teeth")
    vn = parameters.get("varset_name")
    if vn:
        gear_teeth.setExpression("Occurrences", f"<<{vn}>>.NumberOfTeeth")
    gear_teeth.Originals = [loft_bottom, loft_top]
    loft_bottom.Visibility = False
    loft_top.Visibility = False
    sketch_bottom.Visibility = False
    sketch_middle.Visibility = False
    sketch_top.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    dedendum_sketch = util.createSketch(body, "DedendumCircle")
    circle = dedendum_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01), False
    )
    dedendum_sketch.addConstraint(Sketcher.Constraint("Coincident", circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint("Diameter", circle, df + 0.02))

    dedendum_pad = util.createPad(body, dedendum_sketch, height, "DedendumCircle")
    vn = parameters.get("varset_name")
    if vn:
        dedendum_pad.setExpression("Length", f"<<{vn}>>.Height")
    body.Tip = dedendum_pad

    vn = parameters.get("varset_name")
    if vn:
        createMasterBore(body, parameters, height, vn)
    elif bore_type != "none":
        bore_enabled = parameters.get("bore_enabled", True)
        if bore_enabled:
            keyway_enabled = parameters.get("keyway_enabled", True)
            util.createBore(body, parameters, height, keyway_enabled=keyway_enabled)

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    _applyOriginAndAngle(body, parameters)

    return {"body": body}


# ============================================================================
# SPECIALIZED GEAR FUNCTIONS
# ============================================================================


def helixGear(
    doc, parameters, helix_angle: float, profile_func: Optional[Callable] = None
):
    """
    Create a helical gear (single helix angle throughout).

    Uses two-sketch mode (angle1=0) with calculated total rotation for top sketch.
    Total rotation = height * tan(helix_angle) / pitch_radius

    Parameters use NORMAL module convention (standard for manufacturing):
    - module: normal module (mn)
    - pressure_angle: normal pressure angle (αn)
    The profile function converts to transverse values internally.

    Args:
        doc: FreeCAD document
        parameters: Gear parameters dict (with normal module)
        helix_angle: Helix angle in degrees
        profile_func: Optional tooth profile function (uses helical default if None)

    Returns:
        Dictionary with 'body' key containing created body object
    """
    if profile_func is None:
        profile_func = gearMath.generateHelicalGearProfile

    # Add helix angle to parameters so profile function can calculate transverse values
    params_with_helix = parameters.copy()
    params_with_helix["helix_angle"] = helix_angle

    # Backlash is applied in herringboneGear() — do not apply here too

    # Calculate total rotation for top sketch
    # Using transverse module for pitch radius calculation
    mn = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    beta_rad = helix_angle * util.DEG_TO_RAD

    if helix_angle != 0:
        mt = mn / math.cos(beta_rad)  # transverse module
        pitch_radius = mt * num_teeth / 2.0
        # Total twist in radians, then convert to degrees
        total_rotation_rad = height * math.tan(beta_rad) / pitch_radius
        total_rotation_deg = total_rotation_rad * util.RAD_TO_DEG
    else:
        total_rotation_deg = 0.0

    # Pass same angle twice: angle1==angle2 triggers efficient 2-sketch helical mode
    return herringboneGear(
        doc, params_with_helix, total_rotation_deg, total_rotation_deg, profile_func
    )


def spurGear(doc, parameters, profile_func: Optional[Callable] = None):
    """
    Create a spur gear (zero helix angle).

    This is implemented as a herringbone gear with zero angles:
    angle1 = 0, angle2 = 0

    Args:
        doc: FreeCAD document
        parameters: Gear parameters dict
        profile_func: Optional tooth profile function (uses spur default if None)

    Returns:
        Dictionary with 'body' key containing created body object
    """
    if profile_func is None:
        profile_func = gearMath.generateSpurGearProfile

    # Backlash is applied in herringboneGear() — do not apply here too
    return herringboneGear(doc, parameters, 0.0, 0.0, profile_func)


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================

version = "Dec 29, 2025"


class SpurGear:
    """FeaturePython object for parametric spur gear (legacy compatibility)."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultParameters()
        obj.addProperty("App::PropertyString", "Version", "read only",
                        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "RootDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "SpurGear",
                        QT_TRANSLATE_NOOP("App::Property", "Number of teeth")).NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyLength", "Module", "SpurGear", "").Module = H["module"]
        obj.addProperty("App::PropertyLength", "Height", "SpurGear", "").Height = H["height"]
        obj.addProperty("App::PropertyAngle", "PressureAngle", "SpurGear", "").PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyFloat", "ProfileShift", "SpurGear", "").ProfileShift = H["profile_shift"]
        obj.addProperty("App::PropertyFloat", "Backlash", "SpurGear", "", 1).Backlash = 0.0
        obj.addProperty("App::PropertyString", "BodyName", "SpurGear", "").BodyName = H["body_name"]
        obj.addProperty("App::PropertyEnumeration", "BoreType", "Bore", "")
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]
        obj.addProperty("App::PropertyLength", "BoreDiameter", "Bore", "").BoreDiameter = H["bore_diameter"]
        obj.addProperty("App::PropertyLength", "SquareCornerRadius", "Bore", "").SquareCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "HexCornerRadius", "Bore", "").HexCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "KeywayWidth", "Bore", "").KeywayWidth = 2.0
        obj.addProperty("App::PropertyLength", "KeywayDepth", "Bore", "").KeywayDepth = 1.0
        obj.addProperty("App::PropertyDistance", "OriginX", "Placement", "").OriginX = 0.0
        obj.addProperty("App::PropertyDistance", "OriginY", "Placement", "").OriginY = 0.0
        obj.addProperty("App::PropertyDistance", "OriginZ", "Placement", "").OriginZ = 0.0
        obj.addProperty("App::PropertyAngle", "Angle", "Placement", "").Angle = 0.0
        self.Type = "SpurGear"
        self.Object = obj
        self.last_body_name = None
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def __getstate__(self): return self.Type
    def __setstate__(self, state):
        if state: self.Type = state

    def onChanged(self, fp, prop):
        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        if hasattr(old_body, "removeObjectsFromDocument"):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
            self.last_body_name = new_name
        # Only mark dirty for properties that require full gear rebuild
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash"]:
            self.Dirty = True
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash", "Height"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                fp.OuterDiameter = gearMath.calcAddendumDiameter(pitch_dia, module, profile_shift)
                fp.RootDiameter = gearMath.calcDedendumDiameter(pitch_dia, module, profile_shift)
            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        obj = self.Object
        return {"module": float(obj.Module.Value), "num_teeth": int(obj.NumberOfTeeth),
                "pressure_angle": float(obj.PressureAngle.Value), "profile_shift": float(obj.ProfileShift),
                "backlash": float(obj.Backlash), "height": float(obj.Height.Value),
                "body_name": str(obj.BodyName), "bore_type": str(obj.BoreType),
                "bore_diameter": float(obj.BoreDiameter.Value),
                "square_corner_radius": float(obj.SquareCornerRadius.Value),
                "hex_corner_radius": float(obj.HexCornerRadius.Value),
                "keyway_width": float(obj.KeywayWidth.Value), "keyway_depth": float(obj.KeywayDepth.Value),
                "origin_x": float(obj.OriginX.Value), "origin_y": float(obj.OriginY.Value),
                "origin_z": float(obj.OriginZ.Value), "angle": float(obj.Angle.Value)}

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                spurGear(App.ActiveDocument, self.GetParameters())
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Spur Gear Error: {str(e)}\n")

    def execute(self, obj):
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class _VarSetWatcher:
    """Watches a VarSet for property changes that affect gear geometry.

    Two rebuild triggers:
    - IMMEDIATE (default: Module): PropertyLength (commits on Enter) —
      rebuilds via a short QTimer defer.
    - DEFERRED: PropertyAngle/PropertyFloat (fire on every keystroke).
      Sets a flag and waits for slotRecomputedDocument (FreeCAD's busy
      cursor ends), then rebuilds once with the final values.

    immediate / deferred can be passed as frozensets to __init__ to
    configure which property names go in each bucket for a given gear.
    """

    def __init__(self, generator, varset_name,
                 watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash"))):
        self._generator = generator
        self._varset_name = varset_name
        self._doc_name = None
        self._watched = watched

    def slotChangedObject(self, obj, prop):
        if obj.Name != self._varset_name:
            return
        if prop in self._watched:
            self._doc_name = obj.Document.Name
            self._generator._set_needs_rebuild()

    def slotRecomputedDocument(self, doc):
        """Fires when FreeCAD finishes a recompute cycle (busy cursor ends)."""
        if self._doc_name and doc.Name == self._doc_name:
            self._generator._on_recompute_finished()


def createGearVarSet(doc, name):
    """Unified VarSet for external gears (spur, helix, herringbone)."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultParameters()

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
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
    ).Backlash = 0.0

    var_set.addProperty(
        "App::PropertyFloat", "AddendumFactor", "CycloidalGear",
        QT_TRANSLATE_NOOP("App::Property", "Head height factor (~1.4 for cycloidal)"),
    ).AddendumFactor = 1.4

    var_set.addProperty(
        "App::PropertyFloat", "DedendumFactor", "CycloidalGear",
        QT_TRANSLATE_NOOP("App::Property", "Root depth factor (~1.6 for cycloidal)"),
    ).DedendumFactor = 1.6

    var_set.addProperty(
        "App::PropertyLength", "BoreDiameter", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
    ).BoreDiameter = H["bore_diameter"]

    var_set.addProperty(
        "App::PropertyLength", "KeywayWidth", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
    ).KeywayWidth = 2.0

    var_set.addProperty(
        "App::PropertyLength", "KeywayDepth", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
    ).KeywayDepth = 1.0

    var_set.addProperty(
        "App::PropertyBool", "BoreEnabled", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable bore hole in gear"),
    ).BoreEnabled = True

    var_set.addProperty(
        "App::PropertyBool", "KeywayEnabled", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable keyway in gear"),
    ).KeywayEnabled = False

    var_set.addProperty(
        "App::PropertyLength", "PitchDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"), 1,
    )
    var_set.setExpression("PitchDiameter", "Module / cos(Angle1) * NumberOfTeeth")

    var_set.addProperty(
        "App::PropertyLength", "BaseDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Base circle diameter (involute origin)"), 1,
    )
    var_set.setExpression("BaseDiameter", "PitchDiameter * cos(PressureAngle)")

    var_set.addProperty(
        "App::PropertyLength", "OuterDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"), 1,
    )
    var_set.setExpression("OuterDiameter",
        "PitchDiameter + 2 * Module / cos(Angle1) * (1 + ProfileShift)")

    var_set.addProperty(
        "App::PropertyLength", "RootDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"), 1,
    )
    var_set.setExpression("RootDiameter",
        "PitchDiameter - 2 * Module / cos(Angle1) * (1.25 - ProfileShift)")

    return var_set


class GearResult:
    """Unified FeaturePython for auto-regeneration of external gears.

    Replaces SpurGearResult, HelixGearResult, HerringboneGearResult with
    a single class that reads GearType from the VarSet to dispatch the
    correct profile function and set default angles on type changes.
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
        self.Type = "GearResult"

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
        self._last_bl = self._last_a1 = self._last_a2 = self._last_gt = None
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
                               "ProfileShift", "Backlash", "Angle1", "Angle2",
                               "GearType", "ToothProfile", "AddendumFactor",
                               "DedendumFactor")),
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
        a1 = float(v.Angle1.Value)
        a2 = float(v.Angle2.Value)
        gt = str(v.GearType)
        tp = str(v.ToothProfile)
        af = float(v.AddendumFactor) if hasattr(v, "AddendumFactor") else self._last_af
        df = float(v.DedendumFactor) if hasattr(v, "DedendumFactor") else self._last_df
        return (abs(m - self._last_m) > EPS or
                abs(pa - self._last_pa) > EPS or
                abs(ps - self._last_ps) > EPS or
                abs(bl - self._last_bl) > EPS or
                abs(a1 - self._last_a1) > EPS or
                abs(a2 - self._last_a2) > EPS or
                gt != self._last_gt or
                tp != self._last_tp or
                abs(af - self._last_af) > EPS or
                abs(df - self._last_df) > EPS)

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        v = self._getVarSet()
        if not v:
            return
        gt = str(v.GearType)
        if gt != self._last_gt:
            self._last_gt = gt
            self._gt_changed = True
            self._apply_gear_type_defaults(v)
        tp = str(v.ToothProfile)
        if tp != self._last_tp:
            self._last_tp = tp
            self._tp_changed = True
            self._apply_gear_type_defaults(v)
        if not self._gt_changed and not self._tp_changed and not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Regenerating..."
        except Exception:
            pass
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

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
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            self._last_gt = str(v.GearType)
            self._last_tp = str(v.ToothProfile)
            if hasattr(v, "AddendumFactor"):
                self._last_af = float(v.AddendumFactor)
                self._last_df = float(v.DedendumFactor)

            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                App.Console.PrintWarning(
                    f"Gear: skipping rebuild — {self.Object.Status}\n"
                )
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            if (root_dia <= 0 or self._last_m <= 0 or
                    effective_shift < -1.0 or effective_shift > 0.8):
                self.Object.Status = (
                    f"Invalid: effective shift {effective_shift:.2f} "
                    f"out of range (shift={self._last_ps:.2f} "
                    f"backlash={self._last_bl:.2f})"
                )
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
                    except Exception as ex:
                        App.Console.PrintError(f"Gear Error: {str(ex)}\n")
                doc.removeObject(body_name)

            self.Object.Status = "Generating gear geometry..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            profile_func = gearMath.generateHelicalGearProfile
            is_cycloid = self._last_tp == "Cycloidal"
            if is_cycloid:
                import cycloidGear as _cg
                profile_func = _cg.generateCycloidToothProfile
            elif self._last_gt == "Spur":
                profile_func = gearMath.generateSpurGearProfile

            parameters = {
                "module": self._last_m,
                "num_teeth": int(v.NumberOfTeeth),
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "body_name": body_name,
                "bore_diameter": float(v.BoreDiameter.Value),
                "keyway_width": float(v.KeywayWidth.Value),
                "keyway_depth": float(v.KeywayDepth.Value),
                "bore_enabled": bool(v.BoreEnabled),
                "keyway_enabled": bool(v.KeywayEnabled),
                "varset_name": v.Name,
                "origin_x": 0.0, "origin_y": 0.0, "origin_z": 0.0, "angle": 0.0,
            }
            if is_cycloid:
                parameters["addendum_factor"] = self._last_af
                parameters["dedendum_factor"] = self._last_df
            herringboneGear(doc, parameters, self._last_a1, self._last_a2, profile_func)
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


class SpurGearResult:
    """FeaturePython for auto-regeneration of spur gear.

    Uses a DocumentObserver (not PropertyLink) to watch the VarSet.
    PropertyLink creates a dependency in FreeCAD's recompute engine
    that causes infinite loops when the gear body is rebuilt. The
    DocumentObserver sidesteps this entirely — it fires for specific
    property changes only, and since none of the 4 watched properties
    (Module, PressureAngle, ProfileShift, Backlash) are modified
    during a rebuild, the observer simply doesn't fire during rebuild.

    Other params (Height, NumberOfTeeth, BoreDiameter) update
    automatically via FreeCAD expressions on the body features.
    """

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_nt = None
        self._watcher = None
        self._rebuild_pending = False
        self._debounce_timer = None
        self._needs_rebuild = False
        self.Type = "SpurGearResult"

        obj.addProperty(
            "App::PropertyString",
            "VarSetName",
            "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"),
            1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString",
            "Status",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"),
            1,
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
        self._last_nt = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        """Re-register VarSet watcher after file load."""
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_bl = float(v.Backlash)
            self._last_nt = int(v.NumberOfTeeth)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash"))
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
        """Get VarSet, looking it up by name after file restore."""
        if self._varset is None:
            try:
                name = self.Object.VarSetName
                self._varset = self.Object.Document.getObject(name)
            except AttributeError:
                pass
        return self._varset

    def execute(self, obj):
        """No-op. Rebuild is driven by DocumentObserver, not recompute."""
        pass

    def _values_changed(self):
        """Check if tooth-profile values differ from last rebuild.

        Uses tolerance to guard against floating-point drift from
        FreeCAD's internal unit conversions.
        """
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
        nt = int(v.NumberOfTeeth)
        return (abs(m - self._last_m) > EPS or
                abs(pa - self._last_pa) > EPS or
                abs(ps - self._last_ps) > EPS or
                abs(bl - self._last_bl) > EPS or
                nt != self._last_nt)

    def _set_needs_rebuild(self):
        """Called when any watched property changes.

        Sets a flag so that slotRecomputedDocument triggers a rebuild
        after FreeCAD finishes its expression recompute cycle.
        This ensures read-only values (PitchDiameter, etc.) are calculated
        FIRST via expressions, then the gear rebuilds ONCE.
        """
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
        """Called by watcher when FreeCAD finishes a recompute cycle.

        We can't call _rebuild() directly here — we're still inside
        FreeCAD's recompute callback, and our rebuild calls doc.recompute()
        which triggers "Recursive calling of recompute" and leaves the
        new body invisible.  Defer with singleShot(0) to exit the
        callback first.
        """
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
        """Rebuild the gear body."""
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
            self._last_nt = int(v.NumberOfTeeth)

            # Validate before deleting old body — keep old gear if params are bad
            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                App.Console.PrintWarning(
                    f"Spur Gear: skipping rebuild — {self.Object.Status}\n"
                )
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            # Check root diameter and that teeth don't overlap at root
            # Angular tooth thickness at root must be positive:
            # each tooth occupies less than 360/num_teeth degrees
            if (root_dia <= 0 or self._last_m <= 0 or
                    effective_shift < -1.0 or effective_shift > 0.8):
                self.Object.Status = (
                    f"Invalid: effective shift {effective_shift:.2f} "
                    f"out of range (shift={self._last_ps:.2f} "
                    f"backlash={self._last_bl:.2f})"
                )
                App.Console.PrintWarning(
                    f"Spur Gear: skipping rebuild — {self.Object.Status}\n"
                )
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            # Stop watcher BEFORE deleting — expression cleanup can
            # fire slotChangedObject and re-enter our code.
            self._stopWatcher()

            old = doc.getObject(body_name)
            if old:
                children = list(old.Group)

                # 1. Clear all expressions on children
                for child in children:
                    for prop in child.PropertiesList:
                        try:
                            child.setExpression(prop, None)
                        except Exception:
                            pass

                # 2. Remove children individually in reverse order
                #    (leaf features first, sketches last) to avoid
                #    dangling dependency issues inside FreeCAD's
                #    recompute engine that cause infinite loops.
                for child in reversed(children):
                    name = child.Name
                    try:
                        doc.removeObject(name)
                    except Exception as ex:
                        App.Console.PrintError(f"Spur Gear Error: {str(ex)}\n")
                # 3. Remove the body itself
                doc.removeObject(body_name)
            parameters = {
                "module": self._last_m,
                "num_teeth": int(v.NumberOfTeeth),
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "body_name": body_name,
                "bore_diameter": float(v.BoreDiameter.Value),
                "keyway_width": float(v.KeywayWidth.Value),
                "keyway_depth": float(v.KeywayDepth.Value),
                "bore_enabled": bool(v.BoreEnabled),
                "keyway_enabled": bool(v.KeywayEnabled),
                "varset_name": v.Name,
                "origin_x": 0.0, "origin_y": 0.0, "origin_z": 0.0, "angle": 0.0,
            }
            spurGear(doc, parameters)
            self.Object.Status = "Up to date"
        except Exception as e:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            # Clean up any partially-created body from a failed build
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
            # Always restart watcher and clear rebuilding flag
            if varset_name:
                self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self):
        """Force rebuild (used for initial creation from Activated)."""
        self._rebuild()


class HelixGearResult:
    """FeaturePython for auto-regeneration of helical gear.

    Same DocumentObserver pattern as SpurGearResult.  Tracks an
    additional HelixAngle parameter.
    """

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_ha = None
        self._last_nt = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False
        self.Type = "HelixGearResult"

        obj.addProperty(
            "App::PropertyString",
            "VarSetName",
            "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"),
            1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString",
            "Status",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"),
            1,
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
        self._last_ha = None
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
            self._last_ha = float(v.HelixAngle.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle", "ProfileShift",
                                "Backlash", "HelixAngle")),
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
        ha = float(v.HelixAngle.Value)
        nt = int(v.NumberOfTeeth)
        return (abs(m - self._last_m) > EPS or
                abs(pa - self._last_pa) > EPS or
                abs(ps - self._last_ps) > EPS or
                abs(bl - self._last_bl) > EPS or
                abs(ha - self._last_ha) > EPS or
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
            self._last_ha = float(v.HelixAngle.Value)
            self._last_nt = int(v.NumberOfTeeth)

            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                App.Console.PrintWarning(
                    f"Helix Gear: skipping rebuild — {self.Object.Status}\n"
                )
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            if (root_dia <= 0 or self._last_m <= 0 or
                    effective_shift < -1.0 or effective_shift > 0.8):
                self.Object.Status = (
                    f"Invalid: effective shift {effective_shift:.2f} "
                    f"out of range (shift={self._last_ps:.2f} "
                    f"backlash={self._last_bl:.2f})"
                )
                App.Console.PrintWarning(
                    f"Helix Gear: skipping rebuild — {self.Object.Status}\n"
                )
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
                    name = child.Name
                    try:
                        doc.removeObject(name)
                    except Exception as ex:
                        App.Console.PrintError(f"Helix Gear Error: {str(ex)}\n")
                doc.removeObject(body_name)

            parameters = {
                "module": self._last_m,
                "num_teeth": int(v.NumberOfTeeth),
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "body_name": body_name,
                "bore_diameter": float(v.BoreDiameter.Value),
                "keyway_width": float(v.KeywayWidth.Value),
                "keyway_depth": float(v.KeywayDepth.Value),
                "bore_enabled": bool(v.BoreEnabled),
                "keyway_enabled": bool(v.KeywayEnabled),
                "varset_name": v.Name,
                "origin_x": 0.0, "origin_y": 0.0, "origin_z": 0.0, "angle": 0.0,
            }
            helixGear(doc, parameters, self._last_ha)
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


class HerringboneGearResult:
    """FeaturePython for auto-regeneration of herringbone gear.

    Same DocumentObserver pattern as SpurGearResult.  Tracks
    additional Angle1 and Angle2 parameters.
    """

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_pa = None
        self._last_ps = None
        self._last_bl = None
        self._last_a1 = None
        self._last_a2 = None
        self._last_nt = None
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False
        self.Type = "HerringboneGearResult"

        obj.addProperty(
            "App::PropertyString",
            "VarSetName",
            "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"),
            1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString",
            "Status",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"),
            1,
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
        self._last_a1 = None
        self._last_a2 = None
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
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle", "ProfileShift",
                                "Backlash", "Angle1", "Angle2")),
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
        a1 = float(v.Angle1.Value)
        a2 = float(v.Angle2.Value)
        nt = int(v.NumberOfTeeth)
        return (abs(m - self._last_m) > EPS or
                abs(pa - self._last_pa) > EPS or
                abs(ps - self._last_ps) > EPS or
                abs(bl - self._last_bl) > EPS or
                abs(a1 - self._last_a1) > EPS or
                abs(a2 - self._last_a2) > EPS or
                nt != self._last_nt)

    def _set_needs_rebuild(self):
        if self._rebuilding:
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
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            self._last_nt = int(v.NumberOfTeeth)

            if self._last_bl < 0:
                self.Object.Status = "Invalid: backlash must be >= 0"
                App.Console.PrintWarning(
                    f"Herringbone Gear: skipping rebuild — {self.Object.Status}\n"
                )
                return

            effective_shift = self._last_ps - self._last_bl
            num_teeth = int(v.NumberOfTeeth)
            pitch_dia = self._last_m * num_teeth
            root_dia = pitch_dia - 2 * self._last_m * (1.25 - effective_shift)

            if (root_dia <= 0 or self._last_m <= 0 or
                    effective_shift < -1.0 or effective_shift > 0.8):
                self.Object.Status = (
                    f"Invalid: effective shift {effective_shift:.2f} "
                    f"out of range (shift={self._last_ps:.2f} "
                    f"backlash={self._last_bl:.2f})"
                )
                App.Console.PrintWarning(
                    f"Herringbone Gear: skipping rebuild — {self.Object.Status}\n"
                )
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
                    name = child.Name
                    try:
                        doc.removeObject(name)
                    except Exception as ex:
                        App.Console.PrintError(f"Herringbone Gear Error: {str(ex)}\n")
                doc.removeObject(body_name)

            parameters = {
                "module": self._last_m,
                "num_teeth": int(v.NumberOfTeeth),
                "pressure_angle": self._last_pa,
                "profile_shift": self._last_ps,
                "backlash": self._last_bl,
                "height": float(v.Height.Value),
                "body_name": body_name,
                "bore_diameter": float(v.BoreDiameter.Value),
                "keyway_width": float(v.KeywayWidth.Value),
                "keyway_depth": float(v.KeywayDepth.Value),
                "bore_enabled": bool(v.BoreEnabled),
                "keyway_enabled": bool(v.KeywayEnabled),
                "varset_name": v.Name,
                "origin_x": 0.0, "origin_y": 0.0, "origin_z": 0.0, "angle": 0.0,
            }
            herringboneGear(doc, parameters, self._last_a1, self._last_a2)
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


class HelixGear:
    """FeaturePython object for parametric helical gear."""

    def __init__(self, obj):
        """Initialize helical gear with default parameters."""
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "BaseDiameter",
            "read only",
            QT_TRANSLATE_NOOP(
                "App::Property", "Base circle diameter (involute origin)"
            ),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
            1,
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)"),
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyAngle",
            "HelixAngle",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle in degrees"),
        ).HelixAngle = 15.0

        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
        ).Backlash = 0.0

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = "HelicalGear"

        # Bore parameters
        obj.addProperty(
            "App::PropertyEnumeration",
            "BoreType",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole"),
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]

        obj.addProperty(
            "App::PropertyLength",
            "BoreDiameter",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
        ).BoreDiameter = H["bore_diameter"]

        obj.addProperty(
            "App::PropertyLength",
            "SquareCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore"),
        ).SquareCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "HexCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore"),
        ).HexCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "KeywayWidth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
        ).KeywayWidth = 2.0

        obj.addProperty(
            "App::PropertyLength",
            "KeywayDepth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
        ).KeywayDepth = 1.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginX",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "X coordinate of gear origin"),
        ).OriginX = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginY",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Y coordinate of gear origin"),
        ).OriginY = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginZ",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Z coordinate of gear origin"),
        ).OriginZ = 0.0

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Placement",
            QT_TRANSLATE_NOOP(
                "App::Property", "Rotation angle around Z axis (degrees)"
            ),
        ).Angle = 0.0

        self.Type = "HelixGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self

        self.onChanged(obj, "Module")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """Called when a property changes."""
        self.Dirty = True

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        if hasattr(old_body, "removeObjectsFromDocument"):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
            self.last_body_name = new_name

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "HelixAngle", "Backlash", "Height"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                helix_angle = fp.HelixAngle.Value

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                root_dia = gearMath.calcDedendumDiameter(
                    pitch_dia, mt, profile_shift
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.OuterDiameter = outer_dia
                fp.RootDiameter = root_dia

            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        """Get current parameters as dictionary."""
        parameters = {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "backlash": float(self.Object.Backlash),
            "height": float(self.Object.Height.Value),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            "origin_x": float(self.Object.OriginX.Value),
            "origin_y": float(self.Object.OriginY.Value),
            "origin_z": float(self.Object.OriginZ.Value),
            "angle": float(self.Object.Angle.Value),
        }
        return parameters

    def force_Recompute(self):
        """Force recomputation of gear."""
        self.Dirty = True
        self.recompute()

    def recompute(self):
        """Recompute gear geometry if parameters changed."""
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                helix_angle = float(self.Object.HelixAngle.Value)
                helixGear(App.ActiveDocument, parameters, helix_angle)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Generic Helix Gear Error: {str(e)}\n")
                import traceback

                App.Console.PrintError(traceback.format_exc())
                raise

    def execute(self, obj):
        """Execute gear generation with delay."""
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class HerringboneGear:
    """FeaturePython object for parametric herringbone gear."""

    def __init__(self, obj):
        """Initialize herringbone gear with default parameters."""
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "BaseDiameter",
            "read only",
            QT_TRANSLATE_NOOP(
                "App::Property", "Base circle diameter (involute origin)"
            ),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
            1,
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)"),
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyAngle",
            "Angle1",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "First helix angle (bottom to middle)"),
        ).Angle1 = 15.0

        obj.addProperty(
            "App::PropertyAngle",
            "Angle2",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Second helix angle (middle to top)"),
        ).Angle2 = -15.0

        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
        ).Backlash = 0.0

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = "HerringboneGear"

        # Bore parameters
        obj.addProperty(
            "App::PropertyEnumeration",
            "BoreType",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole"),
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]

        obj.addProperty(
            "App::PropertyLength",
            "BoreDiameter",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
        ).BoreDiameter = H["bore_diameter"]

        obj.addProperty(
            "App::PropertyLength",
            "SquareCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore"),
        ).SquareCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "HexCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore"),
        ).HexCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "KeywayWidth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
        ).KeywayWidth = 2.0

        obj.addProperty(
            "App::PropertyLength",
            "KeywayDepth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
        ).KeywayDepth = 1.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginX",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "X coordinate of gear origin"),
        ).OriginX = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginY",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Y coordinate of gear origin"),
        ).OriginY = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginZ",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Z coordinate of gear origin"),
        ).OriginZ = 0.0

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Placement",
            QT_TRANSLATE_NOOP(
                "App::Property", "Rotation angle around Z axis (degrees)"
            ),
        ).Angle = 0.0

        self.Type = "HerringboneGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self

        self.onChanged(obj, "Module")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """Called when a property changes."""
        self.Dirty = True

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        if hasattr(old_body, "removeObjectsFromDocument"):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
            self.last_body_name = new_name

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Angle1", "Angle2", "Backlash", "Height"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                angle1 = fp.Angle1.Value
                angle2 = fp.Angle2.Value

                # Use magnitude of angle1 for helix angle (like internal herringbone)
                helix_angle = abs(angle1) if angle1 != 0 else abs(angle2)

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                root_dia = gearMath.calcDedendumDiameter(
                    pitch_dia, mt, profile_shift
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.OuterDiameter = outer_dia
                fp.RootDiameter = root_dia

            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        """Get current parameters as dictionary."""
        parameters = {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "backlash": float(self.Object.Backlash),
            "height": float(self.Object.Height.Value),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            "origin_x": float(self.Object.OriginX.Value),
            "origin_y": float(self.Object.OriginY.Value),
            "origin_z": float(self.Object.OriginZ.Value),
            "angle": float(self.Object.Angle.Value),
        }
        return parameters

    def force_Recompute(self):
        """Force recomputation of gear."""
        self.Dirty = True
        self.recompute()

    def recompute(self):
        """Recompute gear geometry if parameters changed."""
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                angle1 = float(self.Object.Angle1.Value)
                angle2 = float(self.Object.Angle2.Value)
                herringboneGear(App.ActiveDocument, parameters, angle1, angle2)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Generic Herringbone Gear Error: {str(e)}\n")
                import traceback

                App.Console.PrintError(traceback.format_exc())
                raise

    def execute(self, obj):
        """Execute gear generation with delay."""
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderGenericGear:
    """View provider for generic gear objects."""

    def __init__(self, obj, iconfile=None):
        """Initialize view provider."""
        obj.Proxy = self
        self.part = obj
        self.iconfile = (
            iconfile if iconfile else os.path.join(smWB_icons_path, "spurGear.svg")
        )

    def attach(self, obj):
        """Setup the scene sub-graph."""
        self.ViewObject = obj
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        """Called when a property of the handled feature has changed."""
        return

    def getDisplayModes(self, obj):
        """Return a list of display modes."""
        modes = ["Shaded", "Wireframe", "Flat Lines"]
        return modes

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode."""
        return "Shaded"

    def setDisplayMode(self, mode):
        """Set the display mode."""
        return mode

    def onChanged(self, vobj, prop):
        """Called when a view property has changed."""
        return

    def getIcon(self):
        """Return the icon in XPM format."""
        return self.iconfile

    def doubleClicked(self, vobj):
        """Called when object is double-clicked."""
        return True

    def setupContextMenu(self, vobj, menu):
        """Setup custom context menu."""
        from PySide import QtGui

        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        """Force regeneration of the gear."""
        if hasattr(self.Object, "Proxy"):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        """Return object state for serialization."""
        return self.iconfile

    def __setstate__(self, state):
        """Restore object state from serialization."""
        if state:
            self.iconfile = state
        else:
            self.iconfile = os.path.join(smWB_icons_path, "spurGear.svg")
        return None


class GearTaskPanel:
    """Task panel with Regenerate button for spur gear."""

    def __init__(self, gear_obj):
        from PySide import QtGui
        self.gear_obj = gear_obj

        self.form = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(self.form)

        self.status_label = QtGui.QLabel()
        self._update_status()
        layout.addWidget(self.status_label)

        self.regen_button = QtGui.QPushButton("Regenerate Gear")
        self.regen_button.setMinimumHeight(36)
        self.regen_button.clicked.connect(self._on_regenerate)
        layout.addWidget(self.regen_button)

        layout.addStretch()

    def _update_status(self):
        status = "Unknown"
        try:
            status = self.gear_obj.Status
        except Exception:
            pass
        self.status_label.setText(f"Status: {status}")
        if status == "Needs regeneration":
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.regen_button.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")
        elif status == "Up to date":
            self.status_label.setStyleSheet("color: green;")
            self.regen_button.setStyleSheet("")
        else:
            self.status_label.setStyleSheet("")
            self.regen_button.setStyleSheet("")

    def _on_regenerate(self):
        if hasattr(self.gear_obj, "Proxy"):
            self.gear_obj.Proxy.force_Recompute()
        self._update_status()

    def accept(self):
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self):
        FreeCADGui.Control.closeDialog()
        return True

    def getStandardButtons(self):
        from PySide import QtGui
        return QtGui.QDialogButtonBox.Close


class ViewProviderGearResult:
    """View provider for SpurGear result objects."""

    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.part = obj
        self.iconfile = (
            iconfile if iconfile else os.path.join(smWB_icons_path, "spurGear.svg")
        )

    def attach(self, obj):
        self.ViewObject = obj
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        return

    def getDisplayModes(self, obj):
        return ["Shaded", "Wireframe", "Flat Lines"]

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def onChanged(self, vobj, prop):
        return

    def getIcon(self):
        return self.iconfile

    def doubleClicked(self, vobj):
        panel = GearTaskPanel(self.Object)
        FreeCADGui.Control.showDialog(panel)
        return True

    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui

        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        if hasattr(self.Object, "Proxy"):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        return self.iconfile

    def __setstate__(self, state):
        if state:
            self.iconfile = state
        else:
            self.iconfile = os.path.join(smWB_icons_path, "spurGear.svg")
        return None


# ============================================================================
# FREECAD COMMAND CLASSES
# ============================================================================


class GearCommand:
    """Command to create a unified gear (spur/helix/herringbone)."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "gear.svg"),
            "MenuText": "Create &Gear",
            "ToolTip": "Create parametric gear (spur, helix, or herringbone)",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "Gear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"Gear_values{count:03d}"
            count += 1

        varset = createGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        GearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject, os.path.join(smWB_icons_path, "spurGear.svg")
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


class SpurGearCommand:
    """Command to create a new spur gear object."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "spurGear.svg"),
            "MenuText": "&Create Spur Gear",
            "ToolTip": "Create parametric involute spur gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "SpurGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"SpurGear_values{count:03d}"
            count += 1

        varset = createSpurGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        SpurGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject, os.path.join(smWB_icons_path, "spurGear.svg")
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class HelixGearCommand:
    """Command to create a new helical gear object."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "HelicalGear.svg"),
            "MenuText": "&Create Helical Gear",
            "ToolTip": "Create parametric involute helical gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "HelixGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"HelixGear_values{count:03d}"
            count += 1

        varset = createHelixGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        HelixGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject,
            os.path.join(smWB_icons_path, "HelicalGear.svg"),
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass


class HerringboneGearCommand:
    """Command to create a new herringbone gear object."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "DoubleHelicalGear.svg"),
            "MenuText": "&Create Herringbone Gear",
            "ToolTip": "Create parametric involute herringbone gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "HerringboneGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"HerringboneGear_values{count:03d}"
            count += 1

        varset = createHerringboneGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        HerringboneGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject,
            os.path.join(smWB_icons_path, "DoubleHelicalGear.svg"),
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass


# Register commands with FreeCAD
try:
    FreeCADGui.addCommand("GearCommand", GearCommand())
    FreeCADGui.addCommand("SpurGearCommand", SpurGearCommand())
    FreeCADGui.addCommand("HelixGearCommand", HelixGearCommand())
    FreeCADGui.addCommand("HerringboneGearCommand", HerringboneGearCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register generic gear commands: {e}\n")
    import traceback

    App.Console.PrintError(traceback.format_exc())
