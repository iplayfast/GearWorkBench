#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Involute Gear Mathematics and Generation Helpers

This module contains shared constants, mathematical helpers, and generic
profile generation functions used by specific gear implementations.

Copyright 2025, Chris Bruner
Version v0.2.2 (Refactored)
License LGPL V2.1
"""

import math
import logging
import util
from typing import Tuple, List, Dict, Any, Optional
import FreeCAD as App
import Part
import Sketcher

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

class GearParameterError(ValueError):
    """Raised when gear parameters are invalid."""
    pass

# ============================================================================
# MATH HELPERS
# ============================================================================

def calcPitchDiameter(module: float, num_teeth: int) -> float:
    return module * num_teeth

def calcBaseDiameter(pitch_diameter: float, pressure_angle_deg: float) -> float:
    return pitch_diameter * math.cos(pressure_angle_deg * util.DEG_TO_RAD)

def calcAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter + 2 * module * (ADDENDUM_FACTOR + profile_shift)

def calcDedendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter - 2 * module * (DEDENDUM_FACTOR - profile_shift)

def calcInternalAddendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    return pitch_diameter - 2 * module * (ADDENDUM_FACTOR + profile_shift)

def calcInternalDedendumDiameter(pitch_diameter: float, module: float, profile_shift: float = 0.0, rim_thickness: float = 3.0) -> float:
    return pitch_diameter + 2 * module * (DEDENDUM_FACTOR - profile_shift) + 2 * rim_thickness

# ============================================================================
# GENERIC TOOTH PROFILE GENERATORS
# ============================================================================

def generateToothProfile(sketch, parameters):
    """
    Generates EXTERNAL involute tooth profile.
    Used by: SpurGear, BevelGear.
    """
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * util.DEG_TO_RAD
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

    util.finalizeSketchGeometry(sketch, geo_list)

def generateRackToothProfile(sketch, parameters):
    """
    Generates trapezoidal Rack profile.
    Used by: RackGear, CrownGear.
    """
    module = parameters["module"]
    pressure_angle = parameters["pressure_angle"]
    
    addendum = module * ADDENDUM_FACTOR
    dedendum = module * DEDENDUM_FACTOR
    tan_alpha = math.tan(pressure_angle * util.DEG_TO_RAD)
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

# Defaults are still useful for init
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
