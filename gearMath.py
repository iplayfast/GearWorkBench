#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Involute Gear Mathematics and Generation

This module contains all the mathematical functions for generating involute
spur gears, including the involute profile, tooth dimensions, and validation.

Copyright 2025, Chris Bruner
Version v0.1.3
License LGPL V2.1
"""

import math
import logging
from typing import Tuple, List, Dict, Any, Optional
import FreeCAD
try:
    import FreeCADGui as Gui
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
import FreeCAD as App
import Part
import Sketcher

# Import common utilities
import util
from util import DEG_TO_RAD, RAD_TO_DEG, ParameterValidationError

# Setup logging
logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

# Gear-specific constants
MIN_TEETH = 3
MAX_TEETH = 200
MIN_MODULE = 0.30
MAX_MODULE = 75.0
MIN_PRESSURE_ANGLE = 1.0
MAX_PRESSURE_ANGLE = 35.0
MIN_PROFILE_SHIFT = -1.0
MAX_PROFILE_SHIFT = 1.0

# Standard gear tooth proportions (ISO 53:1998)
ADDENDUM_FACTOR = 1.0
DEDENDUM_FACTOR = 1.25

class GearParameterError(ParameterValidationError):
    """Raised when gear parameters are invalid."""
    pass

# ============================================================================
# Math Helpers
# ============================================================================

def calcPitchDiameter(module: float, num_teeth: int) -> float:
    return module * num_teeth

def calcBaseDiameter(pitch_diameter: float, pressure_angle_deg: float) -> float:
    pressure_angle_rad = pressure_angle_deg * DEG_TO_RAD
    return pitch_diameter * math.cos(pressure_angle_rad)

def calcAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter + 2 * module * (ADDENDUM_FACTOR + profile_shift)

def calcDedendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter - 2 * module * (DEDENDUM_FACTOR - profile_shift)

def calcInternalAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    """Calculate internal gear addendum (inner tip) diameter."""
    return pitch_diameter - 2 * module * (ADDENDUM_FACTOR + profile_shift)

def calcInternalDedendumDiameter(pitch_diameter: float, module: float,
                                  profile_shift: float = 0.0, rim_thickness: float = 3.0) -> float:
    """Calculate internal gear dedendum (outer) diameter."""
    return pitch_diameter + 2 * module * (DEDENDUM_FACTOR - profile_shift) + 2 * rim_thickness

# ============================================================================
# Validation & Defaults
# ============================================================================

def validateSpurParameters(parameters: Dict[str, Any]) -> None:
    """Validate spur gear parameters."""
    module = parameters.get("module", 0)
    num_teeth = parameters.get("num_teeth", 0)
    height = parameters.get("height", 0)

    if module < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if num_teeth < MIN_TEETH: raise GearParameterError(f"Teeth < {MIN_TEETH}")
    if height <= 0: raise GearParameterError("Height must be positive")
    logger.info("Spur parameter validation passed")

def validateInternalParameters(parameters: Dict[str, Any]) -> None:
    validateSpurParameters(parameters) 

def generateDefaultParameters() -> Dict[str, Any]:
    return {
        "module": 1.0,
        "num_teeth": 20,
        "pressure_angle": 20.0,
        "profile_shift": 0.0,
        "height": 10.0,
        "bore_type": "none",
        "bore_diameter": 5.0,
        "body_name": "SpurGear"
    }

def generateDefaultInternalParameters() -> Dict[str, Any]:
    return {
        "module": 1.0,
        "num_teeth": 15,
        "pressure_angle": 20.0,
        "profile_shift": 0.0,
        "height": 10.0,
        "rim_thickness": 3.0,
        "body_name": "InternalSpurGear"
    }

# ============================================================================
# TOOTH GENERATION (EXTERNAL)
# ============================================================================

def generateToothProfile(sketch, parameters: Dict[str, Any]):
    """
    Generate a single EXTERNAL spur gear tooth profile.
    Uses 5-point B-Splines for stability.
    Uses a Straight Line for the root closure to avoid crossing artifacts.
    """
    logger.info("Generating EXTERNAL tooth profile")

    # 1. Dimensions
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    dw = module * num_teeth # Pitch
    dg = dw * math.cos(pressure_angle_rad) # Base
    da = dw + 2 * module * (ADDENDUM_FACTOR + profile_shift) # Tip
    df = dw - 2 * module * (DEDENDUM_FACTOR - profile_shift) # Root

    # 2. Angular Math (Centering Tooth at Y-axis / 90 degrees)
    s_pitch = module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))
    psi = s_pitch / dw 
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    
    # 3. Calculate Involute Points (Right Flank)
    num_inv_points = 5 
    epsilon = 0.001
    start_radius = max(dg/2.0 + epsilon, df/2.0)
    end_radius = da/2.0
    
    involute_pts = []
    
    for i in range(num_inv_points):
        t = i / (num_inv_points - 1)
        r = start_radius + t * (end_radius - start_radius)
        
        val = (dg / 2.0) / r
        if val > 1.0: val = 1.0
        phi = math.acos(val)
        
        inv_phi = math.tan(phi) - phi
        
        # CORRECTED ANGLE FORMULA: Taper towards tip
        theta = (math.pi / 2.0) - psi - inv_alpha + inv_phi
        
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        involute_pts.append(App.Vector(x, y, 0))

    # 4. Construct Flank Arrays
    right_flank_geo = involute_pts
    left_flank_geo = []
    for vec in reversed(right_flank_geo):
        left_flank_geo.append(App.Vector(-vec.x, vec.y, 0))

    # 5. Create Geometry Objects
    geo_list = []
    has_radial_flank = df < dg
    
    # A. Right Radial Line (Optional: Root -> Base)
    if has_radial_flank:
        theta_base = (math.pi / 2.0) - psi - inv_alpha
        p_base = right_flank_geo[0]
        p_root = App.Vector((df/2.0) * math.cos(theta_base), (df/2.0) * math.sin(theta_base), 0)
        
        line = Part.LineSegment(p_root, p_base)
        idx = sketch.addGeometry(line, False)
        geo_list.append(idx)
    else:
        p_root = right_flank_geo[0]

    # B. Right Involute
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_geo)
    idx_right_inv = sketch.addGeometry(bspline_right, False)
    geo_list.append(idx_right_inv)
    
    # C. Tip Arc
    p_tip_right = right_flank_geo[-1]
    p_tip_left = left_flank_geo[0]
    p_tip_mid = App.Vector(0, da/2.0, 0)
    tip_arc = Part.Arc(p_tip_right, p_tip_mid, p_tip_left)
    idx_tip = sketch.addGeometry(tip_arc, False)
    geo_list.append(idx_tip)
    
    # D. Left Involute
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_geo)
    idx_left_inv = sketch.addGeometry(bspline_left, False)
    geo_list.append(idx_left_inv)
    
    # E. Left Radial Line (Optional)
    if has_radial_flank:
        p_base_left = left_flank_geo[-1]
        p_root_left = App.Vector(-p_root.x, p_root.y, 0)
        line = Part.LineSegment(p_base_left, p_root_left)
        idx = sketch.addGeometry(line, False)
        geo_list.append(idx)
    else:
        p_root_left = left_flank_geo[-1]

    # F. Root Closure (Straight Line)
    # Changed from Arc to Line to prevent "crossing" artifacts.
    root_line = Part.LineSegment(p_root_left, p_root)
    idx_root = sketch.addGeometry(root_line, False)
    geo_list.append(idx_root)

    # 6. Constrain and Block
    count = len(geo_list)
    for i in range(count):
        curr = geo_list[i]
        next_g = geo_list[(i+1)%count]
        sketch.addConstraint(Sketcher.Constraint('Coincident', curr, 2, next_g, 1))
        
    for idx in geo_list:
        sketch.addConstraint(Sketcher.Constraint('Block', idx))
        
    logger.info("External tooth profile generated successfully.")

# ============================================================================
# MAIN GENERATORS
# ============================================================================

def generateSpurGearPart(doc, parameters):
    validateSpurParameters(parameters)
    logger.info("Generating spur gear")
    
    # Use the User-Defined Body Name
    body_name = parameters.get("body_name", "SpurGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    bore_type = parameters.get("bore_type", "none")
    
    dw = module * num_teeth
    df = dw - 2 * module * (DEDENDUM_FACTOR - profile_shift)

    # 1. Tooth Profile
    sketch = util.createSketch(body, 'ToothProfile')
    generateToothProfile(sketch, parameters)
    
    tooth_pad = util.createPad(body, sketch, height, 'Tooth')
    
    # 2. Polar Pattern
    polar = util.createPolar(body, tooth_pad, sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar
    
    # 3. Dedendum Circle (Fills the center)
    dedendum_sketch = util.createSketch(body, 'DedendumCircle')
    # Slight overlap (+0.01) ensures robust boolean fusion
    circle = dedendum_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01), False)
    dedendum_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, df + 0.02))
    
    dedendum_pad = util.createPad(body, dedendum_sketch, height, 'DedendumCircle')
    body.Tip = dedendum_pad

    # 4. Bore
    if bore_type != "none":
        generateBore(body, parameters, height)
        
    doc.recompute()
    if GUI_AVAILABLE:
        try: Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass

def generateInternalSpurGearPart(doc, parameters):
    validateInternalParameters(parameters)
    logger.info("Generating internal gear")

    # Use User-Defined Body Name
    body_name = parameters.get("body_name", "InternalSpurGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    module = parameters["module"]
    profile_shift = parameters.get("profile_shift", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)

    dw = module * num_teeth
    df_internal = dw + 2 * module * (DEDENDUM_FACTOR - profile_shift)
    outer_diameter = df_internal + 2 * rim_thickness

    # 1. Tooth Profile
    tooth_sketch = util.createSketch(body, 'Tooth')
    generateInternalToothProfile(tooth_sketch, parameters)

    tooth_pad = util.createPad(body, tooth_sketch, height, 'Tooth')
    
    # 2. Polar Pattern
    polar = util.createPolar(body, tooth_pad, tooth_sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar

    # 3. Outer Ring
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

# ============================================================================
# INTERNAL TOOTH GENERATION
# ============================================================================

def generateInternalToothProfile(sketch, parameters: Dict[str, Any]):
    """
    Generates internal tooth profile (Wide at Root, Narrow at Tip).
    Uses 5-point B-Splines for stability.
    """
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    dw = module * num_teeth
    dg = dw * math.cos(pressure_angle_rad)
    da_internal = dw - 2 * module * (ADDENDUM_FACTOR + profile_shift) 
    df_internal = dw + 2 * module * (DEDENDUM_FACTOR - profile_shift) 

    beta = (math.pi / (2 * num_teeth)) + (2 * profile_shift * math.tan(pressure_angle_rad) / num_teeth)
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    tooth_center_offset = beta - inv_alpha

    # Involute Points (Right Flank)
    num_inv_points = 5 
    epsilon = 0.001
    start_radius = max(da_internal/2.0, dg/2.0 + epsilon)
    end_radius = df_internal/2.0

    involute_start = math.sqrt(max(0, (2*start_radius/dg)**2 - 1))
    involute_end = math.sqrt(max(0, (2*end_radius/dg)**2 - 1))

    right_flank_geo = []
    for i in range(num_inv_points):
        t = i / (num_inv_points - 1)
        phi = involute_start + t * (involute_end - involute_start)
        r = (dg / 2.0) * math.sqrt(1 + phi**2)
        theta_inv = phi - math.atan(phi)
        
        # Internal Gear: Width INCREASES as radius increases
        angle = (math.pi / 2.0) - tooth_center_offset - theta_inv
        
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        right_flank_geo.append(App.Vector(x, y, 0))

    left_flank_inner_to_outer = []
    for vec in right_flank_geo:
        left_flank_inner_to_outer.append(App.Vector(-vec.x, vec.y, 0))
    left_flank_geo = list(reversed(left_flank_inner_to_outer))

    geo_list = []

    # 1. Right Involute
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_right, False))
    
    # 2. Root Arc (Top/Outer)
    p_root_start = right_flank_geo[-1]
    p_root_end = left_flank_geo[0]
    p_root_mid = App.Vector(0, df_internal/2.0, 0)
    root_arc = Part.Arc(p_root_start, p_root_mid, p_root_end)
    geo_list.append(sketch.addGeometry(root_arc, False))
    
    # 3. Left Involute
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_left, False))
    
    # 4. Tip Arc (Bottom/Inner)
    p_tip_start = left_flank_geo[-1]
    p_tip_end = right_flank_geo[0]
    p_tip_mid = App.Vector(0, da_internal/2.0, 0)
    tip_arc = Part.Arc(p_tip_start, p_tip_mid, p_tip_end)
    geo_list.append(sketch.addGeometry(tip_arc, False))
    
    # Constraints & Blocking
    count = len(geo_list)
    for i in range(count):
        sketch.addConstraint(Sketcher.Constraint('Coincident', geo_list[i], 2, geo_list[(i+1)%count], 1))
    
    for idx in geo_list:
        sketch.addConstraint(Sketcher.Constraint('Block', idx))

# ============================================================================
# BORE GENERATORS
# ============================================================================

def generateBore(body, parameters, height):
    bore_type = parameters["bore_type"]
    bore_diameter = parameters["bore_diameter"]

    if bore_type == "circular":
        generateCircularBore(body, bore_diameter, height)
    elif bore_type == "square":
        generateSquareBore(body, bore_diameter, parameters.get("square_corner_radius", 0.5), height)
    elif bore_type == "hexagonal":
        generateHexBore(body, bore_diameter, parameters.get("hex_corner_radius", 0.5), height)
    elif bore_type == "keyway":
        generateKeywayBore(body, bore_diameter, parameters.get("keyway_width", 2.0), parameters.get("keyway_depth", 1.0), height)

def generateCircularBore(body, diameter, height):
    sketch = util.createSketch(body, 'CircularBore')
    circle = sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), diameter / 2), False)
    sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    sketch.addConstraint(Sketcher.Constraint('Diameter', circle, diameter))
    pocket = util.createPocket(body, sketch, height, 'Bore')
    body.Tip = pocket

def generateSquareBore(body, size, corner_radius, height):
    sketch = util.createSketch(body, 'SquareBore')
    half_size = size / (2 * math.sqrt(2))
    points = [App.Vector(half_size, half_size, 0), App.Vector(-half_size, half_size, 0),
              App.Vector(-half_size, -half_size, 0), App.Vector(half_size, -half_size, 0)]
    util.addPolygonToSketch(sketch, points, closed=True)
    pocket = util.createPocket(body, sketch, height, 'Bore')
    body.Tip = pocket

def generateHexBore(body, diameter, corner_radius, height):
    sketch = util.createSketch(body, 'HexBore')
    radius = diameter / 2.0
    points = []
    for i in range(6):
        angle = i * 60 * DEG_TO_RAD
        points.append(App.Vector(radius * math.cos(angle), radius * math.sin(angle), 0))
    util.addPolygonToSketch(sketch, points, closed=True)
    pocket = util.createPocket(body, sketch, height, 'Bore')
    body.Tip = pocket

def generateKeywayBore(body, bore_diameter, keyway_width, keyway_depth, height):
    generateCircularBore(body, bore_diameter, height)
    sketch = util.createSketch(body, 'Keyway')
    w = keyway_width / 2.0
    l = bore_diameter
    points = [App.Vector(-w, 0, 0), App.Vector(w, 0, 0), App.Vector(w, l, 0), App.Vector(-w, l, 0)]
    util.addPolygonToSketch(sketch, points, closed=True)
    pocket = util.createPocket(body, sketch, keyway_depth, 'Keyway')
    body.Tip = pocket

def checkUndercut(num_teeth, pressure_angle_deg, profile_shift=0.0):
    return False, 0

# ============================================================================
# RACK GENERATION
# ============================================================================

def generateDefaultRackParameters() -> Dict[str, Any]:
    return {
        "module": 1.0,
        "num_teeth": 10,
        "pressure_angle": 20.0,
        "height": 10.0,
        "base_thickness": 5.0,
        "body_name": "RackGear"
    }

def validateRackParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < 1: raise GearParameterError("Teeth must be >= 1")
    if parameters["height"] <= 0: raise GearParameterError("Height must be positive")
    if parameters["base_thickness"] <= 0: raise GearParameterError("Base thickness must be positive")

def generateRackToothProfile(sketch, parameters: Dict[str, Any]):
    """
    Generate a single trapezoidal rack tooth centered at X=0.
    """
    module = parameters["module"]
    pressure_angle = parameters["pressure_angle"]
    
    # Rack Dimensions
    # Pitch: pi * m
    # Addendum (top): m
    # Dedendum (bottom): 1.25 * m
    addendum = module * ADDENDUM_FACTOR
    dedendum = module * DEDENDUM_FACTOR
    
    # Calculate X coordinates based on pressure angle slope
    # Slope dx = y * tan(alpha)
    tan_alpha = math.tan(pressure_angle * DEG_TO_RAD)
    
    # At Pitch Line (y=0), tooth thickness = pi*m / 2
    half_pitch_width = (math.pi * module) / 4.0
    
    # Top Points (y = +addendum)
    # Tooth gets narrower at top
    y_top = addendum
    x_top = half_pitch_width - (addendum * tan_alpha)
    
    # Bottom Points (y = -dedendum)
    # Tooth gets wider at bottom
    y_bot = -dedendum
    x_bot = half_pitch_width + (dedendum * tan_alpha)
    
    # Create Points (Clockwise or CCW)
    # Top Left -> Top Right -> Bottom Right -> Bottom Left -> Close
    p_tl = App.Vector(-x_top, y_top, 0)
    p_tr = App.Vector(x_top, y_top, 0)
    p_br = App.Vector(x_bot, y_bot, 0)
    p_bl = App.Vector(-x_bot, y_bot, 0)
    
    points = [p_tl, p_tr, p_br, p_bl, p_tl]
    
    # Create Geometry
    for i in range(4):
        line = Part.LineSegment(points[i], points[i+1])
        idx = sketch.addGeometry(line, False)
        # Block geometry
        sketch.addConstraint(Sketcher.Constraint('Block', idx))
        
    # Connect corners
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i+1)%4, 1))

def generateRackPart(doc, parameters):
    validateRackParameters(parameters)
    logger.info("Generating rack gear")
    
    body_name = parameters.get("body_name", "RackGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    base_thickness = parameters["base_thickness"]
    
    pitch = math.pi * module
    dedendum = module * DEDENDUM_FACTOR

    # 1. Create Single Tooth
    tooth_sketch = util.createSketch(body, 'ToothProfile')
    generateRackToothProfile(tooth_sketch, parameters)
    
    tooth_pad = util.createPad(body, tooth_sketch, height, 'Tooth')
    
    # 2. Linear Pattern
    # Pattern along X axis
    pattern = body.newObject('PartDesign::LinearPattern', 'TeethPattern')
    pattern.Originals = [tooth_pad]
    pattern.Direction = (tooth_sketch, ['H_Axis']) # Use sketch horizontal axis
    pattern.Length = pitch * num_teeth # Total length covered? No, Pattern Length usually means total span
    # In FreeCAD LinearPattern, Length usually means "Overall Length" or "Step Size" depending on mode
    # Assuming 'Original' mode (Step Size? No, typically Length is total distance)
    # Actually, standard behavior: Length = distance from 1st to Last.
    # Distance = (N-1) * pitch
    
    # However, forcing specific properties is safer:
    pattern.Length = pitch * (num_teeth) # Just to set a value
    # We want "Step" mode if available, or just set Total Length
    # Let's set it to recompute based on occurrences
    pattern.Occurrences = num_teeth
    
    # Note: FreeCAD Python API for LinearPattern can be tricky.
    # By default it might use "Overall Length".
    # Distance = (count - 1) * pitch
    if num_teeth > 1:
        pattern.Length = (num_teeth - 1) * pitch
    else:
        pattern.Length = 0
        
    tooth_pad.Visibility = False
    pattern.Visibility = True
    body.Tip = pattern
    
    # 3. Base Bar (The structural rack underneath)
    # Needs to run from Start of first tooth to End of last tooth
    # Tooth 1 center is 0. Width approx pitch/2.
    # Let's make the base span the full theoretical pitch length: N * pitch
    # Centered?
    # Tooth 1 is at 0. Tooth N is at (N-1)*p.
    # Start X = -pitch/2. End X = (N-1)*pitch + pitch/2
    
    start_x = -pitch / 2.0
    end_x = (num_teeth - 1) * pitch + pitch / 2.0
    
    # Y top = -dedendum (Root line)
    # Y bot = -dedendum - base_thickness
    
    base_sketch = util.createSketch(body, 'BaseProfile')
    
    p_tl = App.Vector(start_x, -dedendum, 0)
    p_tr = App.Vector(end_x, -dedendum, 0)
    p_br = App.Vector(end_x, -dedendum - base_thickness, 0)
    p_bl = App.Vector(start_x, -dedendum - base_thickness, 0)
    
    points = [p_tl, p_tr, p_br, p_bl, p_tl]
    
    for i in range(4):
        line = Part.LineSegment(points[i], points[i+1])
        idx = base_sketch.addGeometry(line, False)
        base_sketch.addConstraint(Sketcher.Constraint('Block', idx))
    
    for i in range(4):
        base_sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i+1)%4, 1))
        
    base_pad = util.createPad(body, base_sketch, height, 'Base')
    
    pattern.Visibility = False
    base_pad.Visibility = True
    body.Tip = base_pad
    
    doc.recompute()
    if GUI_AVAILABLE:
        try: Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass



# ============================================================================
# CYCLOID GENERATION (CLOCK/WATCH PROFILE)
# ============================================================================

def generateDefaultCycloidParameters() -> Dict[str, Any]:
    return {
        "module": 1.0,
        "num_teeth": 30, # Clocks usually have high tooth counts
        "height": 5.0,
        "addendum_factor": 1.4, # Typical for clocks (taller teeth)
        "dedendum_factor": 1.6,
        "bore_type": "none",
        "bore_diameter": 5.0,
        "body_name": "CycloidGear"
    }

def validateCycloidParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < 3: raise GearParameterError("Teeth must be >= 3")
    if parameters["height"] <= 0: raise GearParameterError("Height must be positive")

def generateCycloidToothProfile(sketch, parameters: Dict[str, Any]):
    """
    Generate a single Cycloidal tooth profile (Epicycloid Tip + Hypocycloid Root).
    Clock gears typically use a rolling circle diameter = Radius of Pitch / 2
    (which results in straight radial flanks for the root), or standard ratios.
    
    We will use a generic rolling circle r = Module * 3 (Approx mating with 12t pinion)
    to produce the classic "curved base" look.
    """
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    addendum = module * parameters["addendum_factor"]
    dedendum = module * parameters["dedendum_factor"]
    
    # Radii
    R = (module * num_teeth) / 2.0 # Pitch Radius
    Ra = R + addendum # Tip Radius
    Rf = R - dedendum # Root Radius
    
    # Rolling Circle Radius (r)
    # Standard clock practice: Rolling circle diam = Pitch Radius of mating pinion.
    # We assume a generic mating pinion of 10-12 teeth for shape generation.
    # r = (m * 10) / 4 = 2.5m
    r_roll = 2.5 * module 
    
    # Angular width of tooth at Pitch Circle
    # Total pitch angle = 2*pi / z
    # Tooth width = Space width = pi/z
    # Half tooth width angle = pi / (2*z)
    half_tooth_angle = math.pi / (2.0 * num_teeth)
    
    # --- 1. EPICYCLOID (Addendum / Tip) ---
    # Rolling r_roll on OUTSIDE of R
    # Limit: When curve hits radius Ra
    
    epi_pts = []
    # Resolution
    steps = 7
    
    # Need to solve for max rolling angle theta where radius == Ra
    # Approx brute force for generating points is safer than analytical intersection for BSplines
    # We scan theta until distance > Ra
    
    for i in range(steps + 1):
        # Rolling angle parameter t
        # Max reasonable rolling angle?
        t = i * (0.5 / steps) # trial range 0.5 rads
        
        # Epicycloid equations
        # x = (R+r)*cos(t) - r*cos((R+r)/r * t)
        # y = (R+r)*sin(t) - r*sin((R+r)/r * t)
        
        # NOTE: This generates a curve starting at (R,0).
        # We need to rotate this to the correct start position (half_tooth_angle)
        
        cx = (R + r_roll) * math.cos(t) - r_roll * math.cos((R + r_roll)/r_roll * t)
        cy = (R + r_roll) * math.sin(t) - r_roll * math.sin((R + r_roll)/r_roll * t)
        
        # Check radius
        dist = math.sqrt(cx*cx + cy*cy)
        if dist > Ra:
            # Simple lerp to clip exactly at Ra would be better, but for visual B-Spline,
            # stopping at last valid point is okay, or we clamp.
            # Let's just use the calculated points up to Ra.
            # If the first step jumps past Ra (unlikely), this fails.
            
            # Recalculate exact t intersection? 
            # Law of Cosines on rolling triangle is easier.
            break
            
        epi_pts.append(App.Vector(cx, cy, 0))
    
    # Fix: Ensure last point is exactly at Ra?
    # For now, just using generated points.
    
    # Rotate points to Right Flank position
    # The curve starts at angle 0. We want it to start at angle = half_tooth_angle.
    # But wait, the standard equation starts at (R,0) with tangent vertical? No, tangent radial.
    # Epicycloid at t=0 is (R,0).
    # We want the tooth centered on Y axis (90 deg).
    # Right flank pitch point is at angle (90 - half_tooth_deg).
    
    # Let's work in "Tooth Center = 0" space first, then rotate.
    # Right Flank Pitch Point = (R * cos(-half_tooth_angle), R * sin(-half_tooth_angle))?
    # No, let's stick to: Tooth Center = Y Axis.
    # Right Flank Pitch Angle = pi/2 - half_tooth_angle.
    
    # Our generated curve starts at (R, 0) (Angle 0).
    # We need to rotate it so (R,0) lands at Right Flank Pitch Angle.
    rot_bias = (math.pi / 2.0) - half_tooth_angle
    
    right_addendum_geo = []
    for p in epi_pts:
        # Rotate p by rot_bias
        xn = p.x * math.cos(rot_bias) - p.y * math.sin(rot_bias)
        yn = p.x * math.sin(rot_bias) + p.y * math.cos(rot_bias)
        right_addendum_geo.append(App.Vector(xn, yn, 0))
        
    # --- 2. HYPOCYCLOID (Dedendum / Root) ---
    # Rolling r_roll on INSIDE of R
    hypo_pts = []
    for i in range(steps + 1):
        t = i * (0.5 / steps)
        # Hypocycloid equations
        # x = (R-r)*cos(t) + r*cos((R-r)/r * t)
        # y = (R-r)*sin(t) - r*sin((R-r)/r * t)
        
        # Note the sign change in Y term for standard hypocycloid definition starting at (R,0)
        # Note: If R=2r, this becomes a straight line along X axis.
        
        cx = (R - r_roll) * math.cos(t) + r_roll * math.cos((R - r_roll)/r_roll * t)
        cy = -( (R - r_roll) * math.sin(t) - r_roll * math.sin((R - r_roll)/r_roll * t) )
        # Negate Y because generated hypocycloid goes "down" (negative angle) from X axis start?
        # Standard param usually goes "up" or "down" depending on definition.
        # We need the curve that goes inwards from R.
        
        dist = math.sqrt(cx*cx + cy*cy)
        if dist < Rf:
            break
        hypo_pts.append(App.Vector(cx, cy, 0))

    # The hypocycloid above likely curves "down" (negative Y relative to radial line).
    # We need to mirror/rotate it to align tangent with the epicycloid at pitch point.
    
    # Actually, simpler logic:
    # Rotate the Hypocycloid so its start (R,0) aligns with Pitch Angle.
    # AND mirror Y because we want it to curve "in" relative to the tooth mass.
    
    right_dedendum_geo = []
    for p in hypo_pts:
        # We mirror Y of the raw calc to make it continuous with epicycloid slope
        # (Epicycloid goes "out and away", Hypocycloid goes "in and away")
        
        # Raw Hypo (t) goes to Y<0.
        # We want it to join Epicycloid (t) which goes Y>0? 
        # No, they meet at (R,0). 
        # At t=small, Epi X < R? No, Epi X > R.
        # Hypo X < R.
        # Y values? 
        # We need to ensure continuity.
        
        # Let's just apply the rotation bias.
        # For the generated Hypo points, Y is negative (standard eq).
        # This means it curves "CW" from the starting radial line. 
        # This is correct for the Right Flank (which faces Right).
        
        xn = p.x * math.cos(rot_bias) - p.y * math.sin(rot_bias)
        yn = p.x * math.sin(rot_bias) + p.y * math.cos(rot_bias)
        right_dedendum_geo.append(App.Vector(xn, yn, 0))

    # --- 3. Assemble Full Tooth ---
    # Right Flank = Reverse(Dedendum) + Addendum
    # (We want Root -> Tip direction)
    
    right_flank_full = list(reversed(right_dedendum_geo)) + right_addendum_geo[1:] # Skip duplicate pitch point
    
    # Left Flank = Mirror X of Right Flank
    # Direction: Tip -> Root
    left_flank_full = []
    for p in reversed(right_flank_full):
        left_flank_full.append(App.Vector(-p.x, p.y, 0))
        
    # --- 4. Geometry Construction ---
    geo_list = []
    
    # Right Flank
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_full)
    geo_list.append(sketch.addGeometry(bspline_right, False))
    
    # Tip Arc
    p_tip_right = right_flank_full[-1]
    p_tip_left = left_flank_full[0]
    p_tip_mid = App.Vector(0, Ra, 0)
    tip_arc = Part.Arc(p_tip_right, p_tip_mid, p_tip_left)
    geo_list.append(sketch.addGeometry(tip_arc, False))
    
    # Left Flank
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_full)
    geo_list.append(sketch.addGeometry(bspline_left, False))
    
    # Root Arc (Closing the gap)
    # Center of gear is (0,0). Root radius Rf.
    # We need an arc from Left Root End to Right Root Start centered at 0,0
    p_root_left = left_flank_full[-1]
    p_root_right = right_flank_full[0]
    
    # Calculate angle for midpoint
    # It is -90 degrees (270) or just negative Y
    p_root_mid = App.Vector(0, Rf, 0) # Placeholder
    # Actually, we can use util.sketchArc or just Part.Arc
    # We want a concave arc.
    # Midpoint should be at (0, Rf) ? No, that's top. (0, -Rf) is bottom? No.
    # We are at the bottom of the tooth gap? No, we are at the bottom of the TOOTH.
    # The tooth is centered at Y+. The root arc connects the base of the tooth.
    # This segment is actually inside the gear body.
    # A straight line is safer/cleaner.
    
    root_line = Part.LineSegment(p_root_left, p_root_right)
    geo_list.append(sketch.addGeometry(root_line, False))
    
    # Constraints & Blocking
    count = len(geo_list)
    for i in range(count):
        sketch.addConstraint(Sketcher.Constraint('Coincident', geo_list[i], 2, geo_list[(i+1)%count], 1))
    
    for idx in geo_list:
        sketch.addConstraint(Sketcher.Constraint('Block', idx))


def generateCycloidGearPart(doc, parameters):
    validateCycloidParameters(parameters)
    logger.info("Generating cycloid gear")
    
    body_name = parameters.get("body_name", "CycloidGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    dedendum_factor = parameters["dedendum_factor"]
    
    # Dedendum Radius (for the solid disc)
    # Rf = (m*z)/2 - m*hf
    Rf = (module * num_teeth) / 2.0 - (module * dedendum_factor)
    
    # 1. Tooth
    sketch = util.createSketch(body, 'ToothProfile')
    generateCycloidToothProfile(sketch, parameters)
    tooth_pad = util.createPad(body, sketch, height, 'Tooth')
    
    # 2. Pattern
    polar = util.createPolar(body, tooth_pad, sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar
    
    # 3. Dedendum Circle (Body)
    ded_sketch = util.createSketch(body, 'DedendumCircle')
    circle = ded_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), Rf + 0.01), False) # Overlap
    ded_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    ded_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, (Rf + 0.01)*2))
    
    ded_pad = util.createPad(body, ded_sketch, height, 'DedendumCircle')
    body.Tip = ded_pad
    
    # 4. Bore
# ============================================================================
# BEVEL & CROWN GEAR GENERATION
# ============================================================================

def validateBevelParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < MIN_TEETH: raise GearParameterError(f"Teeth < {MIN_TEETH}")
    if parameters["face_width"] <= 0: raise GearParameterError("Face width must be positive")
    if parameters["pitch_angle"] <= 0 or parameters["pitch_angle"] > 90:
        raise GearParameterError("Pitch angle must be between 0 and 90 degrees")

def validateCrownParameters(parameters: Dict[str, Any]) -> None:
    # Crown gear doesn't use pitch_angle, so we just check module/teeth
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < MIN_TEETH: raise GearParameterError(f"Teeth < {MIN_TEETH}")
    if parameters["face_width"] <= 0: raise GearParameterError("Face width must be positive")

def generateBevelGearPart(doc, parameters):
    validateBevelParameters(parameters)
    body_name = parameters.get("body_name", "BevelGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    face_width = parameters["face_width"]
    pitch_angle = parameters["pitch_angle"]
    pressure_angle = parameters["pressure_angle"]
    
    # Geometry
    r_pitch = (module * num_teeth) / 2.0
    sin_delta = math.sin(pitch_angle * DEG_TO_RAD)
    if sin_delta < 0.001: sin_delta = 0.001
    cone_dist = r_pitch / sin_delta
    
    if face_width > cone_dist * 0.5:
        face_width = cone_dist * 0.5
        App.Console.PrintWarning(f"Face width clamped to {face_width}mm\n")

    cone_dist_inner = cone_dist - face_width
    scale_factor = cone_dist_inner / cone_dist
    module_inner = module * scale_factor

    z_outer = cone_dist
    z_inner = cone_dist_inner

    dedendum = module * DEDENDUM_FACTOR
    dedendum_inner = module_inner * DEDENDUM_FACTOR
    
    r_root_outer = r_pitch - (dedendum * math.cos(pitch_angle * DEG_TO_RAD))
    r_root_inner = (r_pitch * scale_factor) - (dedendum_inner * math.cos(pitch_angle * DEG_TO_RAD))
    if r_root_outer < 0.1: r_root_outer = 0.1
    if r_root_inner < 0.1: r_root_inner = 0.1

    # Base Cone
    sk_core_out = util.createSketch(body, 'CoreCircle_Outer')
    sk_core_out.MapMode = 'Deactivated'
    c1 = sk_core_out.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_root_outer), False)
    sk_core_out.addConstraint(Sketcher.Constraint('Diameter', c1, r_root_outer * 2))
    sk_core_out.Placement = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
    
    sk_core_in = util.createSketch(body, 'CoreCircle_Inner')
    sk_core_in.MapMode = 'Deactivated'
    c2 = sk_core_in.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_root_inner), False)
    sk_core_in.addConstraint(Sketcher.Constraint('Diameter', c2, r_root_inner * 2))
    sk_core_in.Placement = App.Placement(App.Vector(0, 0, z_inner), App.Rotation(0,0,0))
    
    base_loft = body.newObject('PartDesign::AdditiveLoft', 'BaseCone')
    base_loft.Profile = sk_core_out
    base_loft.Sections = [sk_core_in]
    base_loft.Ruled = True
    body.Tip = base_loft
    
    # Spiral Twist
    spiral_angle = parameters.get("spiral_angle", 0.0)
    twist_angle_deg = 0.0
    if abs(spiral_angle) > 0.001:
        cone_dist_mean = (cone_dist + cone_dist_inner) / 2.0
        r_mean = cone_dist_mean * sin_delta
        twist_arc = face_width * math.tan(spiral_angle * DEG_TO_RAD)
        twist_angle_rad = twist_arc / r_mean
        twist_angle_deg = twist_angle_rad * RAD_TO_DEG

    # Tooth Profiles
    params_outer = parameters.copy()
    params_inner = parameters.copy()
    params_inner["module"] = module_inner
    
    sk_tooth_out = util.createSketch(body, 'ToothProfile_Outer')
    generateToothProfile(sk_tooth_out, params_outer)
    sk_tooth_out.MapMode = 'Deactivated'
    sk_tooth_out.Placement = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
    
    sk_tooth_in = util.createSketch(body, 'ToothProfile_Inner')
    generateToothProfile(sk_tooth_in, params_inner)
    sk_tooth_in.MapMode = 'Deactivated'
    # Apply Twist Rotation
    sk_tooth_in.Placement = App.Placement(App.Vector(0, 0, z_inner), App.Rotation(App.Vector(0,0,1), twist_angle_deg))
    
    # Loft Tooth
    tooth_loft = body.newObject('PartDesign::AdditiveLoft', 'Tooth')
    tooth_loft.Profile = sk_tooth_out
    tooth_loft.Sections = [sk_tooth_in]
    tooth_loft.Ruled = False 
    
    # Pattern
    polar = util.createPolar(body, tooth_loft, sk_core_out, num_teeth, 'Teeth')
    polar.Originals = [tooth_loft]
    body.Tip = polar
    
    # Bore
    if parameters.get("bore_type", "none") != "none":
        z_outer_place = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
        util.createBore(body, parameters, cone_dist + 10.0, placement=z_outer_place, reversed=False)

    doc.recompute()
    if GUI_AVAILABLE:
        try: Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass

def generateCrownGearPart(doc, parameters):
    print("Generating Crown Gear...")
    validateCrownParameters(parameters)
    body_name = parameters.get("body_name", "CrownGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    face_width = parameters["face_width"]
    
    r_pitch = (module * num_teeth) / 2.0
    r_outer = r_pitch
    r_inner = r_outer - face_width
    if r_inner < 1.0: r_inner = 1.0
    
    scale_factor = r_inner / r_outer
    module_inner = module * scale_factor
    
    dedendum = module * DEDENDUM_FACTOR
    base_thickness = parameters.get("height", 3 * module)

    # Base Disk
    sk_base = util.createSketch(body, 'BaseDisk')
    sk_base.MapMode = 'Deactivated'
    c_out = sk_base.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_outer), False)
    sk_base.addConstraint(Sketcher.Constraint('Diameter', c_out, r_outer * 2))
    sk_base.Placement = App.Placement(App.Vector(0, 0, -dedendum), App.Rotation(0,0,0))
    
    pad_base = body.newObject('PartDesign::Pad', 'Base')
    pad_base.Profile = sk_base
    pad_base.Length = base_thickness
    pad_base.Reversed = True 
    body.Tip = pad_base

    # Profiles
    rot_placement = App.Rotation(90, 0, 90)
    
    # Twist
    spiral_angle = parameters.get("spiral_angle", 0.0)
    twist_angle_deg = 0.0
    if abs(spiral_angle) > 0.001:
        r_mean = (r_outer + r_inner) / 2.0
        twist_arc = face_width * math.tan(spiral_angle * DEG_TO_RAD)
        twist_angle_rad = twist_arc / r_mean
        twist_angle_deg = twist_angle_rad * RAD_TO_DEG
    
    params_out = parameters.copy()
    sk_tooth_out = util.createSketch(body, 'ToothProfile_Outer')
    generateRackToothProfile(sk_tooth_out, params_out)
    sk_tooth_out.MapMode = 'Deactivated'
    sk_tooth_out.Placement = App.Placement(App.Vector(r_outer, 0, 0), rot_placement)
    
    params_in = parameters.copy()
    params_in["module"] = module_inner
    sk_tooth_in = util.createSketch(body, 'ToothProfile_Inner')
    generateRackToothProfile(sk_tooth_in, params_in)
    sk_tooth_in.MapMode = 'Deactivated'
    
    # Twisted Placement
    rot_z = App.Rotation(App.Vector(0,0,1), twist_angle_deg)
    final_pos = rot_z.multVec(App.Vector(r_inner, 0, 0))
    final_rot = rot_z.multiply(rot_placement)
    sk_tooth_in.Placement = App.Placement(final_pos, final_rot)
    
    # Loft
    tooth_loft = body.newObject('PartDesign::AdditiveLoft', 'Tooth')
    tooth_loft.Profile = sk_tooth_out
    tooth_loft.Sections = [sk_tooth_in]
    tooth_loft.Ruled = True
    body.Tip = tooth_loft
    
    # Pattern
    polar = util.createPolar(body, tooth_loft, sk_base, num_teeth, 'Teeth')
    polar.Originals = [tooth_loft]
    body.Tip = polar
    
    # Bore
    if parameters.get("bore_type", "none") != "none":
         z_top = dedendum + module + 10.0
         top_place = App.Placement(App.Vector(0, 0, z_top), App.Rotation(0,0,0))
         util.createBore(body, parameters, z_top + base_thickness + dedendum + 10.0, placement=top_place, reversed=False)

    doc.recompute()
    if GUI_AVAILABLE:
        try: Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass

# ============================================================================
# WORM GEAR GENERATION
# ============================================================================

def validateWormParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["worm_diameter"] <= 0: raise GearParameterError("Worm Diameter must be positive")
    if parameters["length"] <= 0: raise GearParameterError("Length must be positive")

def generateWormGearPart(doc, parameters):
    print("Generating Worm Gear...")
    validateWormParameters(parameters)
    body_name = parameters.get("body_name", "WormGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_threads = parameters["num_threads"] # z1
    worm_dia = parameters["worm_diameter"] # Pitch Diameter
    length = parameters["length"]
    pressure_angle = parameters["pressure_angle"]
    right_handed = parameters["right_handed"]
    
    # Geometry Constants
    addendum = module * ADDENDUM_FACTOR
    dedendum = module * DEDENDUM_FACTOR
    whole_depth = addendum + dedendum
    
    root_dia = worm_dia - 2 * dedendum
    
    pitch = math.pi * module
    lead = pitch * num_threads
    
    # 1. Base Cylinder (Root)
    sk_base = util.createSketch(body, 'RootShaft')
    sk_base.MapMode = 'Deactivated'
    c_base = sk_base.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), root_dia/2), False)
    sk_base.addConstraint(Sketcher.Constraint('Diameter', c_base, root_dia))
    
    pad_base = body.newObject('PartDesign::Pad', 'Base')
    pad_base.Profile = sk_base
    pad_base.Length = length
    body.Tip = pad_base
    
    # 2. Thread Profile
    # Standard FreeCAD Workflow: Attach Sketch to XZ Plane, Offset by Radius.
    
    sk_profile = util.createSketch(body, 'ThreadProfile')
    
    # Find XZ Plane
    xz_plane = None
    if hasattr(body, 'Origin') and body.Origin:
        for child in body.Origin.Group:
            if 'XZ' in child.Name or 'XZ' in child.Label:
                xz_plane = child
                break
        # Fallback
        if not xz_plane and len(body.Origin.Group) > 1:
             xz_plane = body.Origin.Group[1]

    if xz_plane:
        sk_profile.AttachmentSupport = [(xz_plane, '')]
        sk_profile.MapMode = 'ObjectXY' # Align sketch local system with plane
        sk_profile.AttachmentOffset = App.Placement(App.Vector(root_dia/2, 0, 0), App.Rotation(0,0,0))
    else:
        # Fallback: Manual
        sk_profile.MapMode = 'Deactivated'
        sk_profile.Placement = App.Placement(App.Vector(root_dia/2, 0, 0), App.Rotation(App.Vector(1,0,0), 90))

    # Coordinates: (Radial, Axial) -> (Sketch X, Sketch Y) on XZ Plane
    tan_a = math.tan(pressure_angle * DEG_TO_RAD)
    
    # Axial Widths (Half-widths)
    # At Root (Radial=0): Root is WIDER than pitch line.
    hw_root = (pitch / 4.0) + (dedendum * tan_a)
    
    # At Tip (Radial=whole_depth): Tip is NARROWER than pitch line.
    hw_tip = (pitch / 4.0) - (addendum * tan_a)
    if hw_tip < 0: hw_tip = 0.01
    
    # P0: (0, hw_root)  -> X=0 (Radial start), Y=hw (Axial +)
    p0 = App.Vector(0, hw_root, 0)
    p1 = App.Vector(whole_depth, hw_tip, 0)
    p2 = App.Vector(whole_depth, -hw_tip, 0)
    p3 = App.Vector(0, -hw_root, 0)
    
    pts = [p0, p1, p2, p3, p0]
    
    for i in range(4):
        line = Part.LineSegment(pts[i], pts[i+1])
        sk_profile.addGeometry(line, False)
        
    # 3. Helix
    helix = body.newObject('PartDesign::AdditiveHelix', 'WormThread')
    helix.Profile = sk_profile
    helix.Pitch = lead 
    helix.Height = length + 2*pitch
    helix.Reversed = False
    helix.LeftHanded = not right_handed
    
    # CORRECT AXIS LINK: Use Sketch V-Axis (Global Z)
    helix.ReferenceAxis = (sk_profile, ['V_Axis'])
    
    body.Tip = helix
    
    # 4. Pattern (Multi-Start)
    if num_threads > 1:
        polar = util.createPolar(body, helix, None, num_threads, 'Threads')
        # Fix axis
        polar.Axis = (sk_base, ['N_Axis'])
        body.Tip = polar

    # 5. Bore
    if parameters.get("bore_type", "none") != "none":
         util.createBore(body, parameters, length + 10.0)

    doc.recompute()
    if GUI_AVAILABLE:
        try: Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass        