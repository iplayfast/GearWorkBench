#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Involute Gear Mathematics and Generation

This module contains all the mathematical functions for generating involute
spur gears, including the involute profile, tooth dimensions, and validation.

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
Homepage https://github.com/iplayfast/GearWorkbench
"""

import math
import logging
from typing import Tuple, List, Dict, Any, Optional
import FreeCAD
from FreeCAD import Base
try:
    import FreeCADGui as Gui
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
import FreeCAD as App
import Part
from Part import BSplineCurve, makePolygon
import Sketcher

# Import common utilities
import util
from util import DEG_TO_RAD, RAD_TO_DEG, ParameterValidationError

# Setup logging
logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

# Gear-specific constants
MIN_TEETH = 6
MAX_TEETH = 150
MIN_MODULE = 0.30  # mm
MAX_MODULE = 75.0  # mm
MIN_PRESSURE_ANGLE = 1.0  # degrees
MAX_PRESSURE_ANGLE = 35.0  # degrees
STANDARD_PRESSURE_ANGLE = 20.0  # degrees
MIN_PROFILE_SHIFT = -1.0
MAX_PROFILE_SHIFT = 1.0

# Standard gear tooth proportions (ISO 53:1998)
ADDENDUM_FACTOR = 1.0  # ha* = 1.0 module
DEDENDUM_FACTOR = 1.25  # hf* = 1.25 module
CLEARANCE_FACTOR = 0.25  # c* = 0.25 module


# Use common exception type
class GearParameterError(ParameterValidationError):
    """Raised when gear parameters are invalid."""
    pass


def involuteFunction(angle: float) -> float:
    """Calculate the involute function: inv(α) = tan(α) - α."""
    return math.tan(angle) - angle


def involutePoint(base_radius: float, theta: float) -> Tuple[float, float]:
    """Calculate a point on the involute curve."""
    x = base_radius * (math.cos(theta) + theta * math.sin(theta))
    y = base_radius * (math.sin(theta) - theta * math.cos(theta))
    return x, y


def calcPitchDiameter(module: float, num_teeth: int) -> float:
    """Calculate pitch diameter: d = m × z"""
    return module * num_teeth


def calcBaseDiameter(pitch_diameter: float, pressure_angle_deg: float) -> float:
    """Calculate base circle diameter: db = d × cos(α)"""
    pressure_angle_rad = pressure_angle_deg * DEG_TO_RAD
    return pitch_diameter * math.cos(pressure_angle_rad)


def calcAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    """Calculate addendum (outer tip) diameter."""
    return pitch_diameter + 2 * module * (ADDENDUM_FACTOR + profile_shift)


def calcDedendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    """Calculate dedendum (root) diameter."""
    return pitch_diameter - 2 * module * (DEDENDUM_FACTOR - profile_shift)


def calcBaseToothThickness(module: float, pressure_angle_deg: float, profile_shift: float = 0.0) -> float:
    """Calculate tooth thickness at the pitch circle."""
    pressure_angle_rad = pressure_angle_deg * DEG_TO_RAD
    return module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))


def checkUndercut(num_teeth: int, pressure_angle_deg: float, profile_shift: float = 0.0) -> Tuple[bool, float]:
    """Check if gear will have undercutting and calculate minimum teeth."""
    pressure_angle_rad = pressure_angle_deg * DEG_TO_RAD
    sin_alpha = math.sin(pressure_angle_rad)
    min_teeth = 2.0 * ADDENDUM_FACTOR / (sin_alpha * sin_alpha) - 2.0 * profile_shift
    has_undercut = num_teeth < min_teeth
    return has_undercut, min_teeth


def validateSpurParameters(parameters: Dict[str, Any]) -> None:
    """Validate spur gear parameters for physical and mathematical constraints."""
    module = parameters.get("module", 0)
    num_teeth = parameters.get("num_teeth", 0)
    pressure_angle = parameters.get("pressure_angle", 0)
    profile_shift = parameters.get("profile_shift", 0)
    height = parameters.get("height", 0)

    if module < MIN_MODULE:
        raise GearParameterError(f"Module must be >= {MIN_MODULE} mm, got {module}")
    if module > MAX_MODULE:
        raise GearParameterError(f"Module must be <= {MAX_MODULE} mm, got {module}")

    if not isinstance(num_teeth, int) or num_teeth < MIN_TEETH:
        raise GearParameterError(f"Number of teeth must be an integer >= {MIN_TEETH}, got {num_teeth}")
    if num_teeth > MAX_TEETH:
        raise GearParameterError(f"Number of teeth must be <= {MAX_TEETH}, got {num_teeth}")

    if pressure_angle < MIN_PRESSURE_ANGLE:
        raise GearParameterError(f"Pressure angle must be >= {MIN_PRESSURE_ANGLE}°, got {pressure_angle}°")
    if pressure_angle > MAX_PRESSURE_ANGLE:
        raise GearParameterError(f"Pressure angle must be <= {MAX_PRESSURE_ANGLE}°, got {pressure_angle}°")

    if profile_shift < MIN_PROFILE_SHIFT:
        raise GearParameterError(f"Profile shift must be >= {MIN_PROFILE_SHIFT}, got {profile_shift}")
    if profile_shift > MAX_PROFILE_SHIFT:
        raise GearParameterError(f"Profile shift must be <= {MAX_PROFILE_SHIFT}, got {profile_shift}")

    if height <= 0:
        raise GearParameterError(f"Height must be > 0, got {height}")

    has_undercut, min_teeth = checkUndercut(num_teeth, pressure_angle, profile_shift)
    if has_undercut:
        logger.warning(
            f"Gear may have undercutting! {num_teeth} teeth with {pressure_angle}° pressure angle "
            f"requires minimum {min_teeth:.1f} teeth. Consider increasing teeth or using positive "
            f"profile shift (currently {profile_shift})."
        )
    logger.info("Parameter validation passed")


def generateInvoluteProfile(base_radius: float, start_angle: float, end_angle: float,
                              num_points: int = 20) -> List[Tuple[float, float]]:
    """Generate points along an involute curve."""
    points = []
    for i in range(num_points):
        t = i / (num_points - 1)
        theta = start_angle + t * (end_angle - start_angle)
        x, y = involutePoint(base_radius, theta)
        points.append((x, y))
    return points


def generateDefaultParameters() -> Dict[str, Any]:
    """Generate default spur gear parameters."""
    return {
        "module": 1.0,
        "num_teeth": 20,
        "pressure_angle": 20.0,
        "profile_shift": 0.0,
        "height": 10.0,
        "bore_type": "none",
        "bore_diameter": 5.0,
    }


def generateToothProfile(sketch, parameters: Dict[str, Any]):
    """Generate a single spur gear tooth profile (External)."""
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    dw = module * num_teeth
    dg = dw * math.cos(pressure_angle_rad)
    da = dw + 2 * module * (1 + profile_shift)
    df = dw - 2 * module * (1.25 - profile_shift)

    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    involute_rot = (math.sqrt(max(0, (dw**2 - dg**2))) / dg - math.atan(math.sqrt(max(0, (dw**2 - dg**2))) / dg)) + \
                   (1.0 / num_teeth) * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))

    num_inv_points = 20

    involute_start = 0.0
    if dg <= df:
        involute_start = math.sqrt(max(0, df**2 - dg**2)) / dg
    involute_end = math.sqrt(max(0, da**2 - dg**2)) / dg

    involute_pts_raw = []
    if df < dg:
        involute_pts_raw.append((df/2.0, 0.0))

    for i in range(num_inv_points):
        t = i / (num_inv_points - 1)
        phi = involute_start + t * (involute_end - involute_start)
        x_inv = (dg / 2.0) * (math.cos(phi) + phi * math.sin(phi))
        y_inv = (dg / 2.0) * (math.sin(phi) - phi * math.cos(phi))
        involute_pts_raw.append((x_inv, y_inv))

    right_flank_rotation = math.pi / 2.0 - involute_rot

    right_flank_points = []
    for x_pt, y_pt in involute_pts_raw:
        x_rot, y_rot = util.rotatePoint(x_pt, y_pt, right_flank_rotation)
        right_flank_points.append(App.Vector(x_rot, y_rot, 0))

    left_flank_points = []
    for vec in reversed(right_flank_points):
        left_flank_points.append(App.Vector(-vec.x, vec.y, 0))

    util.sketchCircle(sketch, 0, 0, da, -1, "addendum", True)
    util.sketchCircle(sketch, 0, 0, dw, -1, "pitch", True)
    util.sketchCircle(sketch, 0, 0, dg, -1, "base", True)
    util.sketchCircle(sketch, 0, 0, df, -1, "dedendum", True)

    try:
        right_idxs = util.addPolygonToSketch(sketch, right_flank_points, closed=False)
        left_idxs = util.addPolygonToSketch(sketch, left_flank_points, closed=False)

        for idx in right_idxs:
            sketch.addConstraint(Sketcher.Constraint('Block', idx))
        for idx in left_idxs:
            sketch.addConstraint(Sketcher.Constraint('Block', idx))

        p_right_bottom = right_flank_points[0]
        p_left_bottom = left_flank_points[-1]
        angle_R = math.atan2(p_right_bottom.y, p_right_bottom.x)
        angle_L = math.atan2(p_left_bottom.y, p_left_bottom.x)

        root_arc_info = util.sketchArc(sketch, 0, 0, df, startAngle=angle_R, endAngle=angle_L, Name="root_arc", isConstruction=False)
        root_idx = root_arc_info['index']

        sketch.addConstraint(Sketcher.Constraint('Coincident', root_idx, 1, right_idxs[0], 1))
        sketch.addConstraint(Sketcher.Constraint('Coincident', root_idx, 2, left_idxs[-1], 2))

        tip_start_vec = right_flank_points[-1]
        tip_end_vec = left_flank_points[0]
        tip_mid_vec = App.Vector(0, da/2.0, 0)

        tip_arc = Part.Arc(tip_start_vec, tip_mid_vec, tip_end_vec)
        tip_idx = sketch.addGeometry(tip_arc, False)

        sketch.addConstraint(Sketcher.Constraint('Coincident', tip_idx, 1, right_idxs[-1], 2))
        sketch.addConstraint(Sketcher.Constraint('Coincident', tip_idx, 2, left_idxs[0], 1))
        sketch.addConstraint(Sketcher.Constraint('Coincident', tip_idx, 3, -1, 1))

    except Exception as e:
        logger.error(f"Could not create or connect tooth profile: {e}")


def generateSpurGearPart(doc, parameters):
    """Generate a complete spur gear 3D model."""
    validateSpurParameters(parameters)
    logger.info("Generating spur gear")

    body = util.readyPart(doc, 'SpurGear')
    
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    bore_type = parameters.get("bore_type", "none")
    module = parameters["module"]
    profile_shift = parameters.get("profile_shift", 0.0)
    dw = module * num_teeth
    df = dw - 2 * module * (DEDENDUM_FACTOR - profile_shift)

    sketch = util.createSketch(body, 'ToothProfile')
    generateToothProfile(sketch, parameters)

    tooth_pad = util.createPad(body, sketch, height, 'Tooth')

    polar = util.createPolar(body, tooth_pad, sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar

    dedendum_sketch = util.createSketch(body, 'DedendumCircle')
    circle = dedendum_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2), False)
    dedendum_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, df))

    dedendum_pad = util.createPad(body, dedendum_sketch, height, 'DedendumCircle')
    body.Tip = dedendum_pad

    if bore_type != "none":
        generateBore(body, parameters, height)

    doc.recompute()
    if GUI_AVAILABLE:
        try:
            Gui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass


def generateBore(body, parameters, height):
    """Generate center bore in gear."""
    bore_type = parameters["bore_type"]
    bore_diameter = parameters["bore_diameter"]

    if bore_type == "circular":
        generateCircularBore(body, bore_diameter, height)
    elif bore_type == "square":
        corner_radius = parameters.get("square_corner_radius", 0.5)
        generateSquareBore(body, bore_diameter, corner_radius, height)
    elif bore_type == "hexagonal":
        corner_radius = parameters.get("hex_corner_radius", 0.5)
        generateHexBore(body, bore_diameter, corner_radius, height)
    elif bore_type == "keyway":
        keyway_width = parameters.get("keyway_width", 2.0)
        keyway_depth = parameters.get("keyway_depth", 1.0)
        generateKeywayBore(body, bore_diameter, keyway_width, keyway_depth, height)


def generateCircularBore(body, diameter, height):
    """Generate simple circular bore."""
    sketch = util.createSketch(body, 'CircularBore')
    circle = sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), diameter / 2), False)
    sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    sketch.addConstraint(Sketcher.Constraint('Diameter', circle, diameter))
    pocket = util.createPocket(body, sketch, height, 'Bore')
    body.Tip = pocket


def generateSquareBore(body, size, corner_radius, height):
    """Generate square bore with rounded corners."""
    sketch = util.createSketch(body, 'SquareBore')
    half_size = size / (2 * math.sqrt(2))
    points = [
        App.Vector(half_size, half_size, 0),
        App.Vector(-half_size, half_size, 0),
        App.Vector(-half_size, -half_size, 0),
        App.Vector(half_size, -half_size, 0),
        App.Vector(half_size, half_size, 0)
    ]
    for i in range(len(points) - 1):
        sketch.addGeometry(Part.LineSegment(points[i], points[i + 1]), False)
    pocket = util.createPocket(body, sketch, height, 'Bore')
    body.Tip = pocket


def generateHexBore(body, diameter, corner_radius, height):
    """Generate hexagonal bore."""
    sketch = util.createSketch(body, 'HexBore')
    radius = diameter / 2.0
    points = []
    for i in range(7):
        angle = i * 60 * DEG_TO_RAD
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        points.append(App.Vector(x, y, 0))
    for i in range(6):
        sketch.addGeometry(Part.LineSegment(points[i], points[i + 1]), False)
    pocket = util.createPocket(body, sketch, height, 'Bore')
    body.Tip = pocket


def generateKeywayBore(body, bore_diameter, keyway_width, keyway_depth, height):
    """Generate bore with DIN 6885 keyway."""
    generateCircularBore(body, bore_diameter, height)
    sketch = util.createSketch(body, 'Keyway')
    half_width = keyway_width / 2.0
    keyway_length = bore_diameter
    points = [
        App.Vector(-half_width, 0, 0),
        App.Vector(half_width, 0, 0),
        App.Vector(half_width, keyway_length, 0),
        App.Vector(-half_width, keyway_length, 0),
        App.Vector(-half_width, 0, 0)
    ]
    for i in range(len(points) - 1):
        sketch.addGeometry(Part.LineSegment(points[i], points[i + 1]), False)
    pocket = util.createPocket(body, sketch, keyway_depth, 'Keyway')
    body.Tip = pocket


# ============================================================================
# Internal Gear Functions
# ============================================================================

def calcInternalAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    """Calculate internal gear addendum (inner tip) diameter."""
    return pitch_diameter - 2 * module * (ADDENDUM_FACTOR + profile_shift)


def calcInternalDedendumDiameter(pitch_diameter: float, module: float,
                                  profile_shift: float = 0.0, rim_thickness: float = 5.0) -> float:
    """Calculate internal gear dedendum (outer) diameter."""
    return pitch_diameter + 2 * module * (DEDENDUM_FACTOR - profile_shift) + 2 * rim_thickness


def generateDefaultInternalParameters() -> Dict[str, Any]:
    """Generate default internal gear parameters."""
    return {
        "module": 1.0,
        "num_teeth": 15,
        "pressure_angle": 20.0,
        "profile_shift": 0.0,
        "height": 10.0,
        "rim_thickness": 3.0,
    }


def validateInternalParameters(parameters: Dict[str, Any]) -> None:
    """Validate internal gear parameters."""
    module = parameters.get("module", 0)
    num_teeth = parameters.get("num_teeth", 0)
    pressure_angle = parameters.get("pressure_angle", 0)
    profile_shift = parameters.get("profile_shift", 0)
    height = parameters.get("height", 0)
    rim_thickness = parameters.get("rim_thickness", 0)

    if module < MIN_MODULE:
        raise GearParameterError(f"Module must be >= {MIN_MODULE} mm, got {module}")
    if module > MAX_MODULE:
        raise GearParameterError(f"Module must be <= {MAX_MODULE} mm, got {module}")
    
    min_internal_teeth = 6
    if not isinstance(num_teeth, int) or num_teeth < min_internal_teeth:
        raise GearParameterError(f"Number of teeth must be an integer >= {min_internal_teeth}, got {num_teeth}")
    if num_teeth > MAX_TEETH:
        raise GearParameterError(f"Number of teeth must be <= {MAX_TEETH}, got {num_teeth}")

    if pressure_angle < MIN_PRESSURE_ANGLE:
        raise GearParameterError(f"Pressure angle must be >= {MIN_PRESSURE_ANGLE}°, got {pressure_angle}°")
    if pressure_angle > MAX_PRESSURE_ANGLE:
        raise GearParameterError(f"Pressure angle must be <= {MAX_PRESSURE_ANGLE}°, got {pressure_angle}°")

    if profile_shift < MIN_PROFILE_SHIFT:
        raise GearParameterError(f"Profile shift must be >= {MIN_PROFILE_SHIFT}, got {profile_shift}")
    if profile_shift > MAX_PROFILE_SHIFT:
        raise GearParameterError(f"Profile shift must be <= {MAX_PROFILE_SHIFT}, got {profile_shift}")

    if height <= 0:
        raise GearParameterError(f"Height must be > 0, got {height}")

    if rim_thickness < 0.5:
        raise GearParameterError(f"Rim thickness must be >= 0.5 mm, got {rim_thickness}")

    logger.info("Internal gear parameter validation passed")


def generateInternalToothProfile(sketch, parameters: Dict[str, Any]):
    """
    Generate a single internal tooth SOLID profile using 5-Point B-Splines.
    CORRECTED: Generates the TOOTH (Metal) shape (Thick at Outer Root, Thin at Inner Tip).
    """
    logger.info("Generating internal tooth profile (Inverted Tooth Shape)")

    # --- 1. Calculate Dimensions ---
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    dw = module * num_teeth
    dg = dw * math.cos(pressure_angle_rad)
    da_internal = dw - 2 * module * (ADDENDUM_FACTOR + profile_shift) # Inner Dia (Tip)
    df_internal = dw + 2 * module * (DEDENDUM_FACTOR - profile_shift) # Outer Dia (Root)

    # --- 2. Calculate Tooth Geometry (Inverted Angle for Internal Tooth) ---
    # Tooth is centered at 90 degrees (Y-axis).
    # For Internal Tooth (Metal), the thickness INCREASES as radius increases (towards root).
    
    # Calculate half-angle of the tooth thickness at pitch circle
    beta = (math.pi / (2 * num_teeth)) + (2 * profile_shift * math.tan(pressure_angle_rad) / num_teeth)
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    tooth_center_offset = beta - inv_alpha

    # Involute limits
    num_inv_points = 5 
    epsilon = 0.001
    start_radius = max(da_internal/2.0, dg/2.0 + epsilon)
    end_radius = df_internal/2.0

    involute_start = math.sqrt(max(0, (2*start_radius/dg)**2 - 1))
    involute_end = math.sqrt(max(0, (2*end_radius/dg)**2 - 1))

    # Generate Right Flank Points (Inner -> Outer)
    right_flank_geo = []
    for i in range(num_inv_points):
        t = i / (num_inv_points - 1)
        phi = involute_start + t * (involute_end - involute_start)
        
        # Radius
        r = (dg / 2.0) * math.sqrt(1 + phi**2)
        # Involute angle
        theta_inv = phi - math.atan(phi)
        
        # INVERTED ANGLE FORMULA:
        # As theta_inv increases (radius increases), we want the angle to move AWAY from 90.
        # This increases the thickness.
        angle = (math.pi / 2.0) - tooth_center_offset - theta_inv
        
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        right_flank_geo.append(App.Vector(x, y, 0))

    # Generate Left Flank Points (Outer -> Inner)
    left_flank_inner_to_outer = []
    for vec in right_flank_geo:
        # Mirror across Y-axis: (-x, y)
        left_flank_inner_to_outer.append(App.Vector(-vec.x, vec.y, 0))
        
    left_flank_geo = list(reversed(left_flank_inner_to_outer))

    # --- 3. Create Curves ---
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_geo)
    
    p_root_start = right_flank_geo[-1]
    p_root_end = left_flank_geo[0]
    p_root_mid = App.Vector(0, df_internal/2.0, 0)
    root_arc = Part.Arc(p_root_start, p_root_mid, p_root_end)
    
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_geo)
    
    p_tip_start = left_flank_geo[-1]
    p_tip_end = right_flank_geo[0]
    p_tip_mid = App.Vector(0, da_internal/2.0, 0)
    tip_arc = Part.Arc(p_tip_start, p_tip_mid, p_tip_end)

    # --- 4. Add to Sketch ---
    ids = []
    ids.append(sketch.addGeometry(bspline_right, False)) # 0
    ids.append(sketch.addGeometry(root_arc, False))      # 1
    ids.append(sketch.addGeometry(bspline_left, False))  # 2
    ids.append(sketch.addGeometry(tip_arc, False))       # 3
    
    # --- 5. Connect and Block ---
    sketch.addConstraint(Sketcher.Constraint('Coincident', ids[0], 2, ids[1], 1))
    sketch.addConstraint(Sketcher.Constraint('Coincident', ids[1], 2, ids[2], 1))
    sketch.addConstraint(Sketcher.Constraint('Coincident', ids[2], 2, ids[3], 1))
    sketch.addConstraint(Sketcher.Constraint('Coincident', ids[3], 2, ids[0], 1))
    
    for idx in ids:
        sketch.addConstraint(Sketcher.Constraint('Block', idx))

    logger.info("Internal tooth profile generated (5-Point B-Spline, Correct Shape).")


def generateInternalSpurGearPart(doc, parameters):
    """Generate a complete internal gear 3D model."""
    validateInternalParameters(parameters)
    logger.info("Generating internal gear")

    body = util.readyPart(doc, 'InternalSpurGear')

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    module = parameters["module"]
    profile_shift = parameters.get("profile_shift", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)

    dw = module * num_teeth
    df_internal = dw + 2 * module * (DEDENDUM_FACTOR - profile_shift)
    outer_diameter = df_internal + 2 * rim_thickness

    logger.info("Creating tooth sketch")
    tooth_sketch = util.createSketch(body, 'Tooth')
    generateInternalToothProfile(tooth_sketch, parameters)

    tooth_pad = util.createPad(body, tooth_sketch, height, 'Tooth')
    
    logger.info("Creating polar pattern of teeth")
    polar = util.createPolar(body, tooth_pad, tooth_sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar

    logger.info("Adding outer ring")
    ring_sketch = util.createSketch(body, 'Ring')

    outer_circle = ring_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2), False)
    ring_sketch.addConstraint(Sketcher.Constraint('Coincident', outer_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint('Diameter', outer_circle, outer_diameter))

    inner_hole = ring_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df_internal / 2), False)
    ring_sketch.addConstraint(Sketcher.Constraint('Coincident', inner_hole, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint('Diameter', inner_hole, df_internal))

    ring_pad = util.createPad(body, ring_sketch, height, 'Ring')
    
    polar.Visibility = False 
    ring_pad.Visibility = True 
    body.Tip = ring_pad

    doc.recompute()
    if GUI_AVAILABLE:
        try:
            Gui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass
    logger.info("Internal gear generation complete")


logger.info("gearMath module loaded successfully")