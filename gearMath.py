#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Involute Gear Mathematics and Generation

This module contains all the mathematical functions for generating parametric
gears for the GearWorkbench (Spur, Internal, Rack, Cycloid, Bevel, Crown).

Copyright 2025, Chris Bruner
Version v0.2.1
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

# Constants
MIN_TEETH = 3
MAX_TEETH = 200
MIN_MODULE = 0.30
MAX_MODULE = 75.0
ADDENDUM_FACTOR = 1.0
DEDENDUM_FACTOR = 1.25

class GearParameterError(ParameterValidationError):
    """Raised when gear parameters are invalid."""
    pass

# ============================================================================ 
# MATH HELPERS
# ============================================================================ 

def calcPitchDiameter(module: float, num_teeth: int) -> float:
    return module * num_teeth

def calcBaseDiameter(pitch_diameter: float, pressure_angle_deg: float) -> float:
    return pitch_diameter * math.cos(pressure_angle_deg * DEG_TO_RAD)

def calcAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter + 2 * module * (ADDENDUM_FACTOR + profile_shift)

def calcDedendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter - 2 * module * (DEDENDUM_FACTOR - profile_shift)

def calcInternalAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter - 2 * module * (ADDENDUM_FACTOR + profile_shift)

def calcInternalDedendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0, rim_thickness: float = 3.0) -> float:
    return pitch_diameter + 2 * module * (DEDENDUM_FACTOR - profile_shift) + 2 * rim_thickness

# ============================================================================ 
# VALIDATION & DEFAULTS
# ============================================================================ 

def validateSpurParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < MIN_TEETH: raise GearParameterError(f"Teeth < {MIN_TEETH}")
    if parameters["height"] <= 0: raise GearParameterError("Height must be positive")

def validateInternalParameters(parameters: Dict[str, Any]) -> None:
    validateSpurParameters(parameters) 

def validateRackParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < 1: raise GearParameterError("Teeth must be >= 1")
    if parameters["height"] <= 0: raise GearParameterError("Height must be positive")
    if parameters["base_thickness"] <= 0: raise GearParameterError("Base thickness must be positive")

def validateCycloidParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < 3: raise GearParameterError("Teeth must be >= 3")
    if parameters["height"] <= 0: raise GearParameterError("Height must be positive")

def validateCycloidRackParameters(parameters: Dict[str, Any]) -> None:
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < 1: raise GearParameterError("Teeth must be >= 1")
    if parameters["height"] <= 0: raise GearParameterError("Height must be positive")

def generateDefaultParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 20, "pressure_angle": 20.0, "profile_shift": 0.0, 
            "height": 10.0, "bore_type": "none", "bore_diameter": 5.0, "body_name": "SpurGear"}

def generateDefaultInternalParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 15, "pressure_angle": 20.0, "profile_shift": 0.0, 
            "height": 10.0, "rim_thickness": 3.0, "body_name": "InternalSpurGear"}

def generateDefaultRackParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 10, "pressure_angle": 20.0, "height": 10.0, 
            "base_thickness": 5.0, "body_name": "RackGear"}

def generateDefaultCycloidParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 30, "height": 5.0, "addendum_factor": 1.4, 
            "dedendum_factor": 1.6, "bore_type": "none", "bore_diameter": 5.0, "body_name": "CycloidGear"}

def generateDefaultCycloidRackParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 10, "height": 5.0, "addendum_factor": 1.4,
            "dedendum_factor": 1.6, "base_thickness": 5.0, "body_name": "CycloidRack"}

# ============================================================================ 
# SPUR GEAR GENERATION (EXTERNAL)
# ============================================================================ 

def generateToothProfile(sketch, parameters: Dict[str, Any]):
    """Generates EXTERNAL tooth profile."""
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    dw = module * num_teeth
    dg = dw * math.cos(pressure_angle_rad)
    da = dw + 2 * module * (ADDENDUM_FACTOR + profile_shift)
    df = dw - 2 * module * (DEDENDUM_FACTOR - profile_shift)

    s_pitch = module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))
    psi = s_pitch / dw 
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    
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
        theta = (math.pi / 2.0) - psi - inv_alpha + inv_phi 
        involute_pts.append(App.Vector(r * math.cos(theta), r * math.sin(theta), 0))

    right_flank_geo = involute_pts
    left_flank_geo = util.mirrorPointsX(right_flank_geo)

    geo_list = []
    has_radial_flank = df < dg
    
    if has_radial_flank:
        theta_base = (math.pi / 2.0) - psi - inv_alpha
        p_base = right_flank_geo[0]
        p_root = App.Vector((df/2.0) * math.cos(theta_base), (df/2.0) * math.sin(theta_base), 0)
        line = Part.LineSegment(p_root, p_base)
        geo_list.append(sketch.addGeometry(line, False))
    else:
        p_root = right_flank_geo[0]

    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_right, False))
    
    p_tip_right = right_flank_geo[-1]
    p_tip_left = left_flank_geo[0]
    p_tip_mid = App.Vector(0, da/2.0, 0)
    tip_arc = Part.Arc(p_tip_right, p_tip_mid, p_tip_left)
    geo_list.append(sketch.addGeometry(tip_arc, False))
    
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_left, False))
    
    if has_radial_flank:
        p_base_left = left_flank_geo[-1]
        p_root_left = App.Vector(-p_root.x, p_root.y, 0)
        line = Part.LineSegment(p_base_left, p_root_left)
        geo_list.append(sketch.addGeometry(line, False))
    else:
        p_root_left = left_flank_geo[-1]

    # Root Closure
    root_line = Part.LineSegment(p_root_left, p_root)
    geo_list.append(sketch.addGeometry(root_line, False))

    # Debug: Check for finalizeSketchGeometry
    # print(f"DEBUG: util attributes: {dir(util)}")
    if not hasattr(util, 'finalizeSketchGeometry'):
        App.Console.PrintError("DEBUG: CRITICAL - finalizeSketchGeometry missing in util module!\n")
        # Fallback or detailed error
        raise AttributeError("finalizeSketchGeometry missing in util")

    util.finalizeSketchGeometry(sketch, geo_list)

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

# ============================================================================ 
# INTERNAL SPUR GEAR GENERATION
# ============================================================================ 

def generateInternalToothProfile(sketch, parameters: Dict[str, Any]):
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

    num_inv_points = 5 
    epsilon = 0.001
    start_radius = max(da_internal/2.0, dg/2.0 + epsilon)
    end_radius = df_internal/2.0

    right_flank_geo = []
    for i in range(num_inv_points):
        t = i / (num_inv_points - 1)
        phi = math.sqrt(max(0, (2*start_radius/dg)**2 - 1)) + t * (math.sqrt(max(0, (2*end_radius/dg)**2 - 1)) - math.sqrt(max(0, (2*start_radius/dg)**2 - 1)))
        r = (dg / 2.0) * math.sqrt(1 + phi**2)
        theta_inv = phi - math.atan(phi)
        angle = (math.pi / 2.0) - tooth_center_offset - theta_inv
        right_flank_geo.append(App.Vector(r * math.cos(angle), r * math.sin(angle), 0))

    left_flank_geo = util.mirrorPointsX(right_flank_geo)

    geo_list = []
    
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_right, False))
    
    p_root_start = right_flank_geo[-1]
    p_root_end = left_flank_geo[0]
    p_root_mid = App.Vector(0, df_internal/2.0, 0)
    root_arc = Part.Arc(p_root_start, p_root_mid, p_root_end)
    geo_list.append(sketch.addGeometry(root_arc, False))
    
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_left, False))
    
    p_tip_start = left_flank_geo[-1]
    p_tip_end = right_flank_geo[0]
    p_tip_mid = App.Vector(0, da_internal/2.0, 0)
    tip_arc = Part.Arc(p_tip_start, p_tip_mid, p_tip_end)
    geo_list.append(sketch.addGeometry(tip_arc, False))
    
    util.finalizeSketchGeometry(sketch, geo_list)

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
# RACK GENERATION
# ============================================================================ 

def generateRackToothProfile(sketch, parameters: Dict[str, Any]):
    module = parameters["module"]
    pressure_angle = parameters["pressure_angle"]
    
    addendum = module * ADDENDUM_FACTOR
    dedendum = module * DEDENDUM_FACTOR
    tan_alpha = math.tan(pressure_angle * DEG_TO_RAD)
    half_pitch_width = (math.pi * module) / 4.0
    
    y_top = addendum
    x_top = half_pitch_width - (addendum * tan_alpha)
    y_bot = -dedendum
    x_bot = half_pitch_width + (dedendum * tan_alpha)
    
    p_tl = App.Vector(-x_top, y_top, 0)
    p_tr = App.Vector(x_top, y_top, 0)
    p_br = App.Vector(x_bot, y_bot, 0)
    p_bl = App.Vector(-x_bot, y_bot, 0)
    
    points = [p_tl, p_tr, p_br, p_bl, p_tl]
    for i in range(4):
        line = Part.LineSegment(points[i], points[i+1])
        idx = sketch.addGeometry(line, False)
        sketch.addConstraint(Sketcher.Constraint('Block', idx))
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i+1)%4, 1))

def generateRackPart(doc, parameters):
    validateRackParameters(parameters)
    body_name = parameters.get("body_name", "RackGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    base_thickness = parameters["base_thickness"]
    
    pitch = math.pi * module
    dedendum = module * DEDENDUM_FACTOR

    tooth_sketch = util.createSketch(body, 'ToothProfile')
    generateRackToothProfile(tooth_sketch, parameters)
    tooth_pad = util.createPad(body, tooth_sketch, height, 'Tooth')
    
    pattern = body.newObject('PartDesign::LinearPattern', 'TeethPattern')
    pattern.Originals = [tooth_pad]
    pattern.Direction = (tooth_sketch, ['H_Axis'])
    pattern.Occurrences = num_teeth
    if num_teeth > 1:
        pattern.Length = (num_teeth - 1) * pitch
    else:
        pattern.Length = 0
        
    tooth_pad.Visibility = False
    pattern.Visibility = True
    body.Tip = pattern
    
    start_x = -pitch / 2.0
    end_x = (num_teeth - 1) * pitch + pitch / 2.0
    base_sketch = util.createSketch(body, 'BaseProfile')
    y_root = -dedendum
    y_base = -dedendum - base_thickness
    
    p_tl = App.Vector(start_x, y_root, 0)
    p_tr = App.Vector(end_x, y_root, 0)
    p_br = App.Vector(end_x, y_base, 0)
    p_bl = App.Vector(start_x, y_base, 0)
    
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
# CYCLOID GEAR GENERATION
# ============================================================================ 

def generateCycloidToothProfile(sketch, parameters: Dict[str, Any]):
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    addendum = module * parameters["addendum_factor"]
    dedendum = module * parameters["dedendum_factor"]
    
    R = (module * num_teeth) / 2.0 
    Ra = R + addendum 
    Rf = R - dedendum 
    r_roll = 2.5 * module 
    half_tooth_angle = math.pi / (2.0 * num_teeth)
    
    # 1. Epicycloid (Tip)
    epi_pts = []
    steps = 7
    for i in range(steps + 1):
        t = i * (0.5 / steps)
        cx = (R + r_roll) * math.cos(t) - r_roll * math.cos((R + r_roll)/r_roll * t)
        cy = (R + r_roll) * math.sin(t) - r_roll * math.sin((R + r_roll)/r_roll * t)
        if math.sqrt(cx*cx + cy*cy) > Ra: break
        epi_pts.append(App.Vector(cx, cy, 0))
    
    rot_bias = (math.pi / 2.0) - half_tooth_angle
    right_addendum_geo = []
    for p in epi_pts:
        xn = p.x * math.cos(rot_bias) - p.y * math.sin(rot_bias)
        yn = p.x * math.sin(rot_bias) + p.y * math.cos(rot_bias)
        right_addendum_geo.append(App.Vector(xn, yn, 0))
        
    # 2. Hypocycloid (Root)
    hypo_pts = []
    for i in range(steps + 1):
        t = i * (0.5 / steps)
        cx = (R - r_roll) * math.cos(t) + r_roll * math.cos((R - r_roll)/r_roll * t)
        cy = -( (R - r_roll) * math.sin(t) - r_roll * math.sin((R - r_roll)/r_roll * t) )
        if math.sqrt(cx*cx + cy*cy) < Rf: break
        hypo_pts.append(App.Vector(cx, cy, 0))

    right_dedendum_geo = []
    for p in hypo_pts:
        xn = p.x * math.cos(rot_bias) - p.y * math.sin(rot_bias)
        yn = p.x * math.sin(rot_bias) + p.y * math.cos(rot_bias)
        right_dedendum_geo.append(App.Vector(xn, yn, 0))

    right_flank_full = list(reversed(right_dedendum_geo)) + right_addendum_geo[1:] 
    left_flank_full = util.mirrorPointsX(right_flank_full)
    
    geo_list = []
    
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_full)
    geo_list.append(sketch.addGeometry(bspline_right, False))
    
    p_tip_right = right_flank_full[-1]
    p_tip_left = left_flank_full[0]
    p_tip_mid = App.Vector(0, Ra, 0)
    tip_arc = Part.Arc(p_tip_right, p_tip_mid, p_tip_left)
    geo_list.append(sketch.addGeometry(tip_arc, False))
    
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_full)
    geo_list.append(sketch.addGeometry(bspline_left, False))
    
    p_root_left = left_flank_full[-1]
    p_root_right = right_flank_full[0]
    root_line = Part.LineSegment(p_root_left, p_root_right)
    geo_list.append(sketch.addGeometry(root_line, False))
    
    util.finalizeSketchGeometry(sketch, geo_list)

def generateCycloidGearPart(doc, parameters):
    validateCycloidParameters(parameters)
    body_name = parameters.get("body_name", "CycloidGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    dedendum_factor = parameters["dedendum_factor"]
    
    Rf = (module * num_teeth) / 2.0 - (module * dedendum_factor)
    
    sketch = util.createSketch(body, 'ToothProfile')
    generateCycloidToothProfile(sketch, parameters)
    tooth_pad = util.createPad(body, sketch, height, 'Tooth')
    
    polar = util.createPolar(body, tooth_pad, sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar
    
    ded_sketch = util.createSketch(body, 'DedendumCircle')
    circle = ded_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), Rf + 0.01), False)
    ded_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    ded_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, (Rf + 0.01)*2))
    
    ded_pad = util.createPad(body, ded_sketch, height, 'DedendumCircle')
    body.Tip = ded_pad
    
    if parameters["bore_type"] != "none":
        util.createBore(body, parameters, height)
        
    doc.recompute()
    if GUI_AVAILABLE:
        try: Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass

# ============================================================================ 
# CYCLOID RACK GENERATION
# ============================================================================ 

def generateCycloidRackToothProfile(sketch, parameters: Dict[str, Any]):
    module = parameters["module"]
    addendum = module * parameters["addendum_factor"]
    dedendum = module * parameters["dedendum_factor"]
    r_roll = 2.5 * module
    pitch = math.pi * module
    half_tooth_width = pitch / 4.0
    
    # Addendum (Tip)
    val_add = max(-1.0, min(1.0, 1.0 - (addendum / r_roll)))
    t_max_add = math.acos(val_add)
    
    steps = 5
    addendum_pts = []
    for i in range(steps + 1):
        t = i * (t_max_add / steps)
        x = half_tooth_width - r_roll * (t - math.sin(t))
        y = r_roll * (1.0 - math.cos(t))
        addendum_pts.append(App.Vector(x, y, 0))
        
    # Dedendum (Root)
    val_ded = max(-1.0, min(1.0, 1.0 - (dedendum / r_roll)))
    t_max_ded = math.acos(val_ded)
    
    dedendum_pts = []
    for i in range(steps + 1):
        t = i * (t_max_ded / steps)
        # Use ADDITION to make root wider (flare outwards)
        x = half_tooth_width + r_roll * (t - math.sin(t))
        y = -r_roll * (1.0 - math.cos(t))
        dedendum_pts.append(App.Vector(x, y, 0))
        
    right_flank = list(reversed(dedendum_pts)) + addendum_pts[1:]
    left_flank = util.mirrorPointsX(right_flank)
    
    geo_list = []
    
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank)
    geo_list.append(sketch.addGeometry(bspline_right, False))
    
    line_tip = Part.LineSegment(right_flank[-1], left_flank[0])
    geo_list.append(sketch.addGeometry(line_tip, False))
    
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank)
    geo_list.append(sketch.addGeometry(bspline_left, False))
    
    line_root = Part.LineSegment(left_flank[-1], right_flank[0])
    geo_list.append(sketch.addGeometry(line_root, False))
    
    util.finalizeSketchGeometry(sketch, geo_list)

def generateCycloidRackPart(doc, parameters):
    validateCycloidRackParameters(parameters)
    body_name = parameters.get("body_name", "CycloidRack")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    base_thickness = parameters["base_thickness"]
    
    pitch = math.pi * module
    dedendum = module * parameters["dedendum_factor"]

    tooth_sketch = util.createSketch(body, 'ToothProfile')
    generateCycloidRackToothProfile(tooth_sketch, parameters)
    tooth_pad = util.createPad(body, tooth_sketch, height, 'Tooth')
    
    pattern = body.newObject('PartDesign::LinearPattern', 'TeethPattern')
    pattern.Originals = [tooth_pad]
    pattern.Direction = (tooth_sketch, ['H_Axis'])
    pattern.Occurrences = num_teeth
    if num_teeth > 1:
        pattern.Length = (num_teeth - 1) * pitch
    else:
        pattern.Length = 0
        
    tooth_pad.Visibility = False
    pattern.Visibility = True
    body.Tip = pattern
    
    start_x = -pitch / 2.0
    end_x = (num_teeth - 1) * pitch + pitch / 2.0
    
    base_sketch = util.createSketch(body, 'BaseProfile')
    y_root = -dedendum
    y_base = -dedendum - base_thickness
    
    p_tl = App.Vector(start_x, y_root, 0)
    p_tr = App.Vector(end_x, y_root, 0)
    p_br = App.Vector(end_x, y_base, 0)
    p_bl = App.Vector(start_x, y_base, 0)
    
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
# BEVEL & CROWN GEAR GENERATION
# ============================================================================ 

def validateBevelParameters(parameters: Dict[str, Any]) -> None:
    # Basic validation reusing spur logic
    if parameters["module"] < MIN_MODULE: raise GearParameterError(f"Module < {MIN_MODULE}")
    if parameters["num_teeth"] < MIN_TEETH: raise GearParameterError(f"Teeth < {MIN_TEETH}")
    if parameters["face_width"] <= 0: raise GearParameterError("Face width must be positive")
    if parameters["pitch_angle"] <= 0 or parameters["pitch_angle"] > 90:
        raise GearParameterError("Pitch angle must be between 0 and 90 degrees")

def validateCrownParameters(parameters: Dict[str, Any]) -> None:
    validateBevelParameters(parameters)

def generateBevelGearPart(doc, parameters):
    """
    Generates a solid Bevel Gear.
    Workflow:
    1. Calculate cone geometry (Outer and Inner sections).
    2. Create Outer Sketch and Inner Sketch (scaled).
    3. Loft teeth (Outer -> Inner).
    4. Polar Pattern the teeth.
    5. Create a central 'Root Cone' (Loft) to form the solid body.
    """
    validateBevelParameters(parameters)
    body_name = parameters.get("body_name", "BevelGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    face_width = parameters["face_width"]
    pitch_angle = parameters["pitch_angle"]
    pressure_angle = parameters["pressure_angle"]
    
    # --- 1. Calculate Geometry ---
    # Pitch Radius (Outer)
    r_pitch = (module * num_teeth) / 2.0
    
    # Cone Distance (Apex to Outer Pitch Circle)
    # L = R / sin(delta)
    sin_delta = math.sin(pitch_angle * DEG_TO_RAD)
    if sin_delta < 0.001: sin_delta = 0.001
    cone_dist = r_pitch / sin_delta
    
    # Clamp Face Width
    if face_width > cone_dist * 0.5:
        face_width = cone_dist * 0.5
        App.Console.PrintWarning(f"Face width clamped to {face_width}mm (max 50% of cone distance)\n")

    # Inner Cone Distance
    cone_dist_inner = cone_dist - face_width
    
    # Scale Factor (for the inner profile)
    scale_factor = cone_dist_inner / cone_dist
    
    # Inner Module (virtual)
    module_inner = module * scale_factor

    # Placement Z-coordinates (Apex at Origin 0,0,0)
    # We build the gear along the Z-axis (like a funnel).
    # Outer profile at Z = cone_dist
    # Inner profile at Z = cone_dist_inner
    z_outer = cone_dist
    z_inner = cone_dist_inner

    # --- 2. Create Core Body (Root Cone) ---
    # We do this first so the teeth are added TO it.
    # Calculate Root Radii
    # Dedendum = 1.25 * module (standard)
    dedendum = 1.25 * module
    dedendum_inner = 1.25 * module_inner
    
    # Root Radius = Pitch Radius - (Dedendum * cos(pitch_angle))
    # Note: The radius is perpendicular to Z-axis.
    r_root_outer = r_pitch - (dedendum * math.cos(pitch_angle * DEG_TO_RAD))
    r_root_inner = (r_pitch * scale_factor) - (dedendum_inner * math.cos(pitch_angle * DEG_TO_RAD))
    
    if r_root_outer < 0.1: r_root_outer = 0.1
    if r_root_inner < 0.1: r_root_inner = 0.1

    # Sketch for Root Cone Outer
    sk_core_out = util.createSketch(body, 'CoreCircle_Outer')
    sk_core_out.MapMode = 'Deactivated'
    c1 = sk_core_out.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_root_outer), False)
    sk_core_out.addConstraint(Sketcher.Constraint('Diameter', c1, r_root_outer * 2))
    sk_core_out.Placement = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
    
    # Sketch for Root Cone Inner
    sk_core_in = util.createSketch(body, 'CoreCircle_Inner')
    sk_core_in.MapMode = 'Deactivated'
    c2 = sk_core_in.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_root_inner), False)
    sk_core_in.addConstraint(Sketcher.Constraint('Diameter', c2, r_root_inner * 2))
    sk_core_in.Placement = App.Placement(App.Vector(0, 0, z_inner), App.Rotation(0,0,0))
    
    # Create Base Cone Loft
    base_loft = body.newObject('PartDesign::AdditiveLoft', 'BaseCone')
    base_loft.Profile = sk_core_out
    base_loft.Sections = [sk_core_in]
    base_loft.Ruled = True
    body.Tip = base_loft
    
    # --- 3. Create Tooth Profiles ---
    
    # Spiral / Twist Calculation
    spiral_angle = parameters.get("spiral_angle", 0.0)
    twist_angle_deg = 0.0
    if abs(spiral_angle) > 0.001:
        # Approximate Twist
        # Mean Cone Distance
        cone_dist_mean = (cone_dist + cone_dist_inner) / 2.0
        # Mean Pitch Radius
        r_mean = cone_dist_mean * sin_delta
        
        # Arc length of twist
        # s = face_width * tan(beta)
        twist_arc = face_width * math.tan(spiral_angle * DEG_TO_RAD)
        
        # Angle in Radians = s / r
        twist_angle_rad = twist_arc / r_mean
        twist_angle_deg = twist_angle_rad * RAD_TO_DEG
        
        # App.Console.PrintMessage(f"Spiral Angle: {spiral_angle}, Twist: {twist_angle_deg} deg\n")

    # Parameter sets
    params_outer = parameters.copy()
    params_inner = parameters.copy()
    params_inner["module"] = module_inner # Automatically scales the geometry
    
    # Sketch Outer Tooth
    sk_tooth_out = util.createSketch(body, 'ToothProfile_Outer')
    generateToothProfile(sk_tooth_out, params_outer)
    sk_tooth_out.MapMode = 'Deactivated'
    sk_tooth_out.Placement = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
    
    # Sketch Inner Tooth
    sk_tooth_in = util.createSketch(body, 'ToothProfile_Inner')
    generateToothProfile(sk_tooth_in, params_inner)
    sk_tooth_in.MapMode = 'Deactivated'
    # Apply Twist Rotation around Z-axis
    sk_tooth_in.Placement = App.Placement(App.Vector(0, 0, z_inner), App.Rotation(App.Vector(0,0,1), twist_angle_deg))
    
    # --- 4. Loft the Tooth ---
    tooth_loft = body.newObject('PartDesign::AdditiveLoft', 'Tooth')
    tooth_loft.Profile = sk_tooth_out
    tooth_loft.Sections = [sk_tooth_in]
    tooth_loft.Ruled = False # Smooth interpolation
    
    # --- 5. Pattern the Tooth ---
    # Use sk_core_out as the axis reference (Normal Axis = Z Axis)
    polar = util.createPolar(body, tooth_loft, sk_core_out, num_teeth, 'Teeth')
    polar.Originals = [tooth_loft]
    
    # Set Tip
    body.Tip = polar
    
    # --- 6. Bore ---
    if parameters.get("bore_type", "none") != "none":
        z_outer_place = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
        util.createBore(body, parameters, cone_dist + 10.0, placement=z_outer_place, reversed=False)

    doc.recompute()
    if GUI_AVAILABLE:
        try: Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass

def generateCrownGearPart(doc, parameters):
    # validateCrownParameters(parameters) # Removed: Checks for pitch_angle which CrownGear doesn't have
    body_name = parameters.get("body_name", "CrownGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    face_width = parameters["face_width"]
    
    # Geometry
    r_pitch = (module * num_teeth) / 2.0
    r_outer = r_pitch
    r_inner = r_outer - face_width
    if r_inner < 1.0: r_inner = 1.0
    
    scale_factor = r_inner / r_outer
    module_inner = module * scale_factor
    
    dedendum = module * DEDENDUM_FACTOR
    base_thickness = parameters.get("height", 3 * module)

    # 1. Base Disk (Created FIRST)
    sk_base = util.createSketch(body, 'BaseDisk')
    sk_base.MapMode = 'Deactivated'
    c_out = sk_base.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_outer), False)
    sk_base.addConstraint(Sketcher.Constraint('Diameter', c_out, r_outer * 2))
    # Place base disk top at -Dedendum (bottom of teeth)
    sk_base.Placement = App.Placement(App.Vector(0, 0, -dedendum), App.Rotation(0,0,0))
    
    pad_base = body.newObject('PartDesign::Pad', 'Base')
    pad_base.Profile = sk_base
    pad_base.Length = base_thickness
    pad_base.Reversed = True # Extrude downwards from -dedendum
    body.Tip = pad_base

    # 2. Tooth Profiles
    rot_placement = App.Rotation(90, 0, 90)
    
    # Spiral Twist
    spiral_angle = parameters.get("spiral_angle", 0.0)
    twist_angle_deg = 0.0
    if abs(spiral_angle) > 0.001:
        r_mean = (r_outer + r_inner) / 2.0
        twist_arc = face_width * math.tan(spiral_angle * DEG_TO_RAD)
        twist_angle_rad = twist_arc / r_mean
        twist_angle_deg = twist_angle_rad * RAD_TO_DEG
    
    # Outer Profile (No Twist)
    params_out = parameters.copy()
    sk_tooth_out = util.createSketch(body, 'ToothProfile_Outer')
    generateRackToothProfile(sk_tooth_out, params_out)
    sk_tooth_out.MapMode = 'Deactivated'
    sk_tooth_out.Placement = App.Placement(App.Vector(r_outer, 0, 0), rot_placement)
    
    # Inner Profile (Twisted)
    params_in = parameters.copy()
    params_in["module"] = module_inner
    sk_tooth_in = util.createSketch(body, 'ToothProfile_Inner')
    generateRackToothProfile(sk_tooth_in, params_in)
    sk_tooth_in.MapMode = 'Deactivated'
    
    # Calculate Twisted Placement
    # Start with base placement at (r_inner, 0, 0) facing tangent
    # base_place = App.Placement(App.Vector(r_inner, 0, 0), rot_placement)
    
    # Apply Z-rotation manually to Position and Rotation
    # NewPos = RotZ * Pos
    # NewRot = RotZ * Rot
    rot_z = App.Rotation(App.Vector(0,0,1), twist_angle_deg)
    final_pos = rot_z.multVec(App.Vector(r_inner, 0, 0))
    final_rot = rot_z.multiply(rot_placement)
    
    sk_tooth_in.Placement = App.Placement(final_pos, final_rot)
    
    # 3. Tooth Loft
    tooth_loft = body.newObject('PartDesign::AdditiveLoft', 'Tooth')
    tooth_loft.Profile = sk_tooth_out
    tooth_loft.Sections = [sk_tooth_in]
    tooth_loft.Ruled = True
    body.Tip = tooth_loft
    
    # 4. Pattern
    # Use sk_base as the axis reference (Normal Axis = Z Axis)
    polar = util.createPolar(body, tooth_loft, sk_base, num_teeth, 'Teeth')
    polar.Originals = [tooth_loft]
    body.Tip = polar
    
    # 5. Bore
    if parameters.get("bore_type", "none") != "none":
         # Crown base is at Z=-dedendum, extending DOWN.
         # Bore sketch is created at default Z=0.
         # Reversed=True (Default) cuts UP (+Z). This clears the teeth but misses the base.
         # We need to cut DOWN (-Z) to clear the base?
         # Wait, if we cut DOWN from 0, we clear -Dedendum..Down. Correct.
         # But reversed=True means +Z ??
         # Let's try explicit Placement at TOP and cut DOWN.
         
         # Better: Place at Z=module (above teeth), cut DOWN (Reversed=False).
         # Top of teeth is roughly module?
         # Let's place at Z=10.0 + module, cut down through everything.
         
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
    validateWormParameters(parameters)
    body_name = parameters.get("body_name", "WormGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_threads = parameters["num_threads"] # z1
    worm_dia = parameters["worm_diameter"] # Pitch Diameter
    length = parameters["length"]
    helix_len = parameters.get("helix_length", length)
    center_helix = parameters.get("center_helix", True)
    
    if helix_len > length: helix_len = length
    
    pressure_angle = parameters["pressure_angle"]
    right_handed = parameters["right_handed"]
    
    # Calculate Z-Offset for centering
    z_offset = 0.0
    if center_helix:
        z_offset = (length - helix_len) / 2.0
    
    # Geometry Constants
    addendum = module * ADDENDUM_FACTOR
    dedendum = module * DEDENDUM_FACTOR
    whole_depth = addendum + dedendum
    
    # User Request: WormDiameter parameter should be the Cylinder (Root) Diameter
    root_dia = worm_dia 
    
    # Pitch Diameter (for lead angle calc context, though we use fixed lead)
    # pitch_dia = root_dia + 2 * dedendum 
    
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
        # sk_profile.AttachmentOffset removed. Geometry will be offset instead.
    else:
        # Fallback: Manual
        sk_profile.MapMode = 'Deactivated'
        # Placement at Origin, Rotated to XZ orientation
        sk_profile.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(App.Vector(1,0,0), 90))

    # Coordinates: (Radial, Axial) -> (Sketch X, Sketch Y) on XZ Plane
    tan_a = math.tan(pressure_angle * DEG_TO_RAD)
    
    # Axial Widths (Half-widths)
    # At Root (Radial=0): Root is WIDER than pitch line.
    hw_root = (pitch / 4.0) + (dedendum * tan_a)
    
    # At Tip (Radial=whole_depth): Tip is NARROWER than pitch line.
    hw_tip = (pitch / 4.0) - (addendum * tan_a)
    if hw_tip < 0: hw_tip = 0.01
    
    # Offset geometry by Root Radius in X (Radial)
    r_offset = root_dia / 2.0
    
    # P0: (0, hw_root)  -> X=r_offset (Radial start), Y=hw (Axial +)
    # Apply Z-Offset to Y component (Axial position)
    p0 = App.Vector(r_offset, hw_root + z_offset, 0)
    p1 = App.Vector(r_offset + whole_depth, hw_tip + z_offset, 0)
    p2 = App.Vector(r_offset + whole_depth, -hw_tip + z_offset, 0)
    p3 = App.Vector(r_offset, -hw_root + z_offset, 0)
    
    pts = [p0, p1, p2, p3, p0]
    
    for i in range(4):
        line = Part.LineSegment(pts[i], pts[i+1])
        sk_profile.addGeometry(line, False)
        
    # 3. Helix
    helix = body.newObject('PartDesign::AdditiveHelix', 'WormThread')
    helix.Profile = sk_profile
    helix.Pitch = lead 
    helix.Height = helix_len
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