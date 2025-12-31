"""Generic Internal Gear Framework for FreeCAD

This module provides a unified framework for creating internal (ring) gear types
using a master herringbone gear builder that handles all cases through
helix angle distribution parameters.

Supports: Internal Spur, Internal Helical, Internal Herringbone gears

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

version = "Dec 29, 2025"


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
# INTERNAL TOOTH PROFILE GENERATORS
# ============================================================================

def generateInternalToothProfile(sketch, parameters):
    """
    Generate internal gear tooth profile (teeth pointing inward).
    Uses B-splines for involute flanks, arcs for tip and root.

    For internal gears, the involute is parameterized by roll angle (phi)
    and positioned differently than external gears.
    """
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * util.DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    # Internal gear diameter calculations
    dw = module * num_teeth  # Pitch diameter
    dg = dw * math.cos(pressure_angle_rad)  # Base diameter
    rb = dg / 2.0  # Base radius

    # For internal gears: addendum is INWARD (smaller), dedendum is OUTWARD (larger)
    da_internal = dw - 2 * module * (gearMath.ADDENDUM_FACTOR + profile_shift)  # Inner tip diameter
    df_internal = dw + 2 * module * (gearMath.DEDENDUM_FACTOR - profile_shift)  # Outer root diameter

    # Tooth thickness angle calculation for internal gear
    # beta is half the angular tooth thickness at pitch circle
    beta = (math.pi / (2 * num_teeth)) + (2 * profile_shift * math.tan(pressure_angle_rad) / num_teeth)
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    tooth_center_offset = beta - inv_alpha  # Note: MINUS for internal gear

    # Generate involute points parameterized by roll angle (phi)
    num_points = 20
    epsilon = 0.001
    start_radius = max(da_internal / 2.0, rb + epsilon)
    end_radius = df_internal / 2.0

    # Calculate phi range from radii
    # r = rb * sqrt(1 + phi^2), so phi = sqrt((r/rb)^2 - 1)
    phi_start = math.sqrt(max(0, (start_radius / rb)**2 - 1))
    phi_end = math.sqrt(max(0, (end_radius / rb)**2 - 1))

    right_flank_pts = []

    for i in range(num_points):
        t = i / (num_points - 1)
        phi = phi_start + t * (phi_end - phi_start)

        # Radius at this roll angle
        r = rb * math.sqrt(1 + phi**2)

        # Involute function: inv(phi) = phi - atan(phi) for internal gear parameterization
        theta_inv = phi - math.atan(phi)

        # Angle from Y-axis (tooth centered on Y-axis pointing up)
        angle = (math.pi / 2.0) - tooth_center_offset - theta_inv

        # Point on involute
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        right_flank_pts.append(App.Vector(x, y, 0))

    # Mirror for left flank
    left_flank_pts = util.mirrorPointsX(right_flank_pts)

    geo_list = []

    # 1. Right involute flank (B-spline)
    if len(right_flank_pts) >= 2:
        bspline = Part.BSplineCurve()
        bspline.interpolate(right_flank_pts)
        geo_list.append(sketch.addGeometry(bspline, False))

    # 2. Root arc (outer edge at df_internal)
    # Project endpoints onto df_internal circle to ensure all 3 points are coplanar
    r_root = df_internal / 2.0
    angle_root_right = math.atan2(right_flank_pts[-1].y, right_flank_pts[-1].x)
    angle_root_left = math.atan2(left_flank_pts[-1].y, left_flank_pts[-1].x)
    p_root_right = App.Vector(r_root * math.cos(angle_root_right), r_root * math.sin(angle_root_right), 0)
    p_root_left = App.Vector(r_root * math.cos(angle_root_left), r_root * math.sin(angle_root_left), 0)
    p_root_mid = App.Vector(0, r_root, 0)
    root_arc = Part.Arc(p_root_right, p_root_mid, p_root_left)
    geo_list.append(sketch.addGeometry(root_arc, False))

    # 3. Left involute flank (B-spline)
    if len(left_flank_pts) >= 2:
        bspline = Part.BSplineCurve()
        bspline.interpolate(left_flank_pts)
        geo_list.append(sketch.addGeometry(bspline, False))

    # 4. Tip arc (inner edge at da_internal)
    # Project endpoints onto da_internal circle to ensure all 3 points are coplanar
    r_tip = da_internal / 2.0
    angle_tip_left = math.atan2(left_flank_pts[-1].y, left_flank_pts[-1].x)
    angle_tip_right = math.atan2(right_flank_pts[0].y, right_flank_pts[0].x)
    p_tip_left = App.Vector(r_tip * math.cos(angle_tip_left), r_tip * math.sin(angle_tip_left), 0)
    p_tip_right = App.Vector(r_tip * math.cos(angle_tip_right), r_tip * math.sin(angle_tip_right), 0)
    p_tip_mid = App.Vector(0, r_tip, 0)
    tip_arc = Part.Arc(p_tip_left, p_tip_mid, p_tip_right)
    geo_list.append(sketch.addGeometry(tip_arc, False))

    util.finalizeSketchGeometry(sketch, geo_list)


def generateInternalSpurGearProfile(sketch, parameters):
    """Default profile function for internal spur gears."""
    generateInternalToothProfile(sketch, parameters)


def generateInternalHelicalGearProfile(sketch, parameters):
    """
    Profile function for internal helical/herringbone gears.
    Converts from normal module (manufacturing standard) to transverse values.
    """
    helix_angle = parameters.get("helix_angle", 0.0)

    if helix_angle == 0:
        generateInternalToothProfile(sketch, parameters)
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

    generateInternalToothProfile(sketch, transverse_params)


# ============================================================================
# MASTER INTERNAL GEAR BUILDER
# ============================================================================

def genericInternalHerringboneGear(
    doc,
    parameters,
    angle1: float,
    angle2: float,
    profile_func: Optional[Callable] = None,
):
    """
    Master builder for all internal gear types using herringbone pattern.

    Creates tooth using up to 3 sketches (bottom, middle, top) based on angles:
    - If angle1 == 0: two-sketch mode (bottom→top)
    - If angle1 != 0: three-sketch mode (bottom→middle→top)

    Parameters use NORMAL module convention for helical/herringbone gears.
    """
    validateInternalParameters(parameters)

    body_name = parameters.get("body_name", "GenericInternalGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)

    # Ensure helix_angle is in parameters for profile function
    if "helix_angle" not in parameters:
        parameters = parameters.copy()
        parameters["helix_angle"] = abs(angle1) if angle1 != 0 else abs(angle2)

    # Calculate dimensions using transverse module if helical
    helix_angle = parameters.get("helix_angle", 0.0)
    module = parameters["module"]
    if helix_angle != 0:
        beta_rad = helix_angle * util.DEG_TO_RAD
        mt = module / math.cos(beta_rad)
    else:
        mt = module

    dw = mt * num_teeth
    rf_internal = dw / 2.0 + mt * (gearMath.DEDENDUM_FACTOR - profile_shift)
    outer_diameter = rf_internal * 2.0 + 2 * rim_thickness

    if profile_func is None:
        profile_func = generateInternalHelicalGearProfile

    if angle1 == 0:
        return _createTwoSketchInternalGear(
            body, parameters, height, num_teeth, angle2, rf_internal, outer_diameter, rim_thickness, profile_func
        )
    else:
        return _createThreeSketchInternalGear(
            body, parameters, height, num_teeth, angle1, angle2, rf_internal, outer_diameter, rim_thickness, profile_func
        )


def _createTwoSketchInternalGear(
    body, parameters, height, num_teeth, angle2, rf_internal, outer_diameter, rim_thickness, profile_func
):
    """Create internal gear with 2 sketches (angle1 == 0)."""
    doc = body.Document

    # Bottom sketch
    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    # Top sketch with rotation
    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle2)
    )
    profile_func(sketch_top, parameters)

    # Loft the tooth
    tooth_loft = body.newObject("PartDesign::AdditiveLoft", "SingleTooth")
    tooth_loft.Profile = sketch_bottom
    tooth_loft.Sections = [sketch_top]
    tooth_loft.Ruled = True

    # Polar pattern for all teeth - use body's Origin Z axis directly
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]  # Z axis
    gear_teeth.Axis = (z_axis, [""])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [tooth_loft]

    tooth_loft.Visibility = False
    sketch_bottom.Visibility = False
    sketch_top.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    # Recompute to ensure polar pattern is fully resolved before adding ring
    doc.recompute()

    # Outer ring
    ring_sketch = util.createSketch(body, "Ring")
    outer_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", outer_circle, outer_diameter))

    inner_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), rf_internal), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", inner_circle, rf_internal * 2.0))

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")
    gear_teeth.Visibility = False
    ring_pad.Visibility = True
    body.Tip = ring_pad

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


def _createThreeSketchInternalGear(
    body, parameters, height, num_teeth, angle1, angle2, rf_internal, outer_diameter, rim_thickness, profile_func
):
    """Create internal gear with 3 sketches (herringbone pattern)."""
    doc = body.Document
    half_height = height / 2.0

    # Bottom sketch
    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    # Middle sketch with angle1 rotation
    sketch_middle = util.createSketch(body, "ToothProfile_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(0, 0, half_height), App.Rotation(App.Vector(0, 0, 1), angle1)
    )
    profile_func(sketch_middle, parameters)

    # Top sketch with angle1 + angle2 rotation
    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle1 + angle2)
    )
    profile_func(sketch_top, parameters)

    # Lower half loft
    loft_lower = body.newObject("PartDesign::AdditiveLoft", "ToothLower")
    loft_lower.Profile = sketch_bottom
    loft_lower.Sections = [sketch_middle]
    loft_lower.Ruled = True

    # Upper half loft
    loft_upper = body.newObject("PartDesign::AdditiveLoft", "ToothUpper")
    loft_upper.Profile = sketch_middle
    loft_upper.Sections = [sketch_top]
    loft_upper.Ruled = True

    # Polar pattern for all teeth
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]
    gear_teeth.Axis = (z_axis, [""])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [loft_lower, loft_upper]

    loft_lower.Visibility = False
    loft_upper.Visibility = False
    sketch_bottom.Visibility = False
    sketch_middle.Visibility = False
    sketch_top.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    # Outer ring
    ring_sketch = util.createSketch(body, "Ring")
    outer_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", outer_circle, outer_diameter))

    inner_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), rf_internal), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", inner_circle, rf_internal * 2.0))

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")
    gear_teeth.Visibility = False
    ring_pad.Visibility = True
    body.Tip = ring_pad

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


# ============================================================================
# SPECIALIZED INTERNAL GEAR FUNCTIONS
# ============================================================================

def genericInternalHelixGear(
    doc, parameters, helix_angle: float, profile_func: Optional[Callable] = None
):
    """
    Create an internal helical gear (single helix angle).
    Uses two-sketch mode with calculated total rotation.
    """
    if profile_func is None:
        profile_func = generateInternalHelicalGearProfile

    params_with_helix = parameters.copy()
    params_with_helix["helix_angle"] = helix_angle

    # Calculate total rotation for top sketch
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

    return genericInternalHerringboneGear(
        doc, params_with_helix, 0.0, total_rotation_deg, profile_func
    )


def genericInternalSpurGear(doc, parameters, profile_func: Optional[Callable] = None):
    """
    Create an internal spur gear (zero helix angle).
    Uses two-sketch mode with no rotation.
    """
    if profile_func is None:
        profile_func = generateInternalSpurGearProfile

    return genericInternalHerringboneGear(doc, parameters, 0.0, 0.0, profile_func)


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================

class GenericInternalSpurGear:
    """FeaturePython object for parametric internal spur gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty("App::PropertyLength", "Module", "InternalSpurGear", "Normal module").Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "InternalSpurGear", "Number of teeth").NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyAngle", "PressureAngle", "InternalSpurGear", "Pressure angle").PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyFloat", "ProfileShift", "InternalSpurGear", "Profile shift coefficient").ProfileShift = H["profile_shift"]
        obj.addProperty("App::PropertyLength", "Height", "InternalSpurGear", "Gear height").Height = H["height"]
        obj.addProperty("App::PropertyLength", "RimThickness", "InternalSpurGear", "Rim thickness").RimThickness = H["rim_thickness"]
        obj.addProperty("App::PropertyString", "BodyName", "InternalSpurGear", "Body name").BodyName = "GenericInternalSpurGear"

        self.Type = "GenericInternalSpurGear"
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        self.Dirty = True
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, module, profile_shift)
                outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, module, profile_shift, rim_thickness)

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
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                genericInternalSpurGear(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Internal Spur Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


class GenericInternalHelixGear:
    """FeaturePython object for parametric internal helical gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty("App::PropertyLength", "Module", "InternalHelicalGear", "Normal module").Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "InternalHelicalGear", "Number of teeth").NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyAngle", "PressureAngle", "InternalHelicalGear", "Normal pressure angle").PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyFloat", "ProfileShift", "InternalHelicalGear", "Profile shift coefficient").ProfileShift = H["profile_shift"]
        obj.addProperty("App::PropertyLength", "Height", "InternalHelicalGear", "Gear height").Height = H["height"]
        obj.addProperty("App::PropertyLength", "RimThickness", "InternalHelicalGear", "Rim thickness").RimThickness = H["rim_thickness"]
        obj.addProperty("App::PropertyAngle", "HelixAngle", "InternalHelicalGear", "Helix angle").HelixAngle = 15.0
        obj.addProperty("App::PropertyString", "BodyName", "InternalHelicalGear", "Body name").BodyName = "GenericInternalHelixGear"

        self.Type = "GenericInternalHelixGear"
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        self.Dirty = True
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness", "HelixAngle"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value
                helix_angle = fp.HelixAngle.Value

                # Use transverse values for display
                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, mt, profile_shift)
                outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, mt, profile_shift, rim_thickness)

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
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                genericInternalHelixGear(App.ActiveDocument, parameters, parameters["helix_angle"])
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Internal Helical Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


class GenericInternalHerringboneGear:
    """FeaturePython object for parametric internal herringbone gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty("App::PropertyLength", "Module", "InternalHerringboneGear", "Normal module").Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "InternalHerringboneGear", "Number of teeth").NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyAngle", "PressureAngle", "InternalHerringboneGear", "Normal pressure angle").PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyFloat", "ProfileShift", "InternalHerringboneGear", "Profile shift coefficient").ProfileShift = H["profile_shift"]
        obj.addProperty("App::PropertyLength", "Height", "InternalHerringboneGear", "Gear height").Height = H["height"]
        obj.addProperty("App::PropertyLength", "RimThickness", "InternalHerringboneGear", "Rim thickness").RimThickness = H["rim_thickness"]
        obj.addProperty("App::PropertyAngle", "HelixAngle", "InternalHerringboneGear", "Helix angle").HelixAngle = 30.0
        obj.addProperty("App::PropertyString", "BodyName", "InternalHerringboneGear", "Body name").BodyName = "GenericInternalHerringboneGear"

        self.Type = "GenericInternalHerringboneGear"
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        self.Dirty = True
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness", "HelixAngle"]:
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
                inner_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, mt, profile_shift)
                outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, mt, profile_shift, rim_thickness)

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
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                helix_angle = parameters["helix_angle"]
                # Calculate twist for herringbone (half height each direction)
                mn = parameters["module"]
                num_teeth = parameters["num_teeth"]
                height = parameters["height"]
                beta_rad = helix_angle * util.DEG_TO_RAD

                if helix_angle != 0:
                    mt = mn / math.cos(beta_rad)
                    pitch_radius = mt * num_teeth / 2.0
                    half_rotation_rad = (height / 2.0) * math.tan(beta_rad) / pitch_radius
                    half_rotation_deg = half_rotation_rad * util.RAD_TO_DEG
                else:
                    half_rotation_deg = 0.0

                # Herringbone: angle1 = +twist, angle2 = -twist (back to center)
                genericInternalHerringboneGear(
                    App.ActiveDocument, parameters, half_rotation_deg, -half_rotation_deg
                )
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
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

class GenericInternalSpurGearCommand:
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

        base_name = "GenericInternalSpurGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalSpurGearParameters")
        gear = GenericInternalSpurGear(gear_obj)
        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


class GenericInternalHelixGearCommand:
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

        base_name = "GenericInternalHelixGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalHelixGearParameters")
        gear = GenericInternalHelixGear(gear_obj)
        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


class GenericInternalHerringboneGearCommand:
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

        base_name = "GenericInternalHerringboneGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalHerringboneGearParameters")
        gear = GenericInternalHerringboneGear(gear_obj)
        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


# Register commands
try:
    FreeCADGui.addCommand("GenericInternalSpurGearCommand", GenericInternalSpurGearCommand())
    FreeCADGui.addCommand("GenericInternalHelixGearCommand", GenericInternalHelixGearCommand())
    FreeCADGui.addCommand("GenericInternalHerringboneGearCommand", GenericInternalHerringboneGearCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register internal gear commands: {e}\n")
