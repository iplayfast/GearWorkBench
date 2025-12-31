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





def pitch_radius(module: float, num_teeth: int) -> float:
    """
    Calculate pitch radius from module and number of teeth.
    """
    return calcPitchDiameter(module, num_teeth) / 2.0


def pitch_diameter(module: float, num_teeth: int) -> float:
    """
    Calculate pitch diameter from module and number of teeth.
    Alias for calcPitchDiameter.
    """
    return calcPitchDiameter(module, num_teeth)


def base_radius(pitch_diameter: float, pressure_angle_deg: float) -> float:
    """
    Calculate base radius from pitch diameter and pressure angle.
    """
    return calcBaseDiameter(pitch_diameter, pressure_angle_deg) / 2.0


def outer_radius(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    """
    Calculate outer (tip) radius.
    """
    return calcAddendumDiameter(pitch_diameter, module, profile_shift) / 2.0


def root_radius(pitch_diameter: float, module: float, profile_shift: float = 0.0) -> float:
    """
    Calculate root radius.
    """
    return calcDedendumDiameter(pitch_diameter, module, profile_shift) / 2.0


def transverse_module(normal_module: float, helix_angle_deg: float) -> float:
    """
    Calculate transverse module from normal module and helix angle.
    """
    beta = helix_angle_deg * util.DEG_TO_RAD
    return normal_module / math.cos(beta)


def twist_per_height(helix_angle_deg: float, radius: float) -> float:
    """
    Calculate twist per unit height for helical gears.
    """
    beta = helix_angle_deg * util.DEG_TO_RAD
    return math.tan(beta) / radius if radius != 0 else 0.0

# ============================================================================


def _unit_xy(v: App.Vector) -> App.Vector:
    l = math.hypot(v.x, v.y)
    if l == 0:
        return App.Vector(0, 1, 0)
    return App.Vector(v.x / l, v.y / l, 0)

def _angle_xy(v: App.Vector) -> float:
    return math.atan2(v.y, v.x)



# ============================================================================
# GENERIC TOOTH PROFILE GENERATORS
# ============================================================================

def generateToothProfile(sketch, parameters):
    """
    Generates EXTERNAL involute tooth profile.
    Uses B-splines for involute flanks, arc for top land, lines for root.
    """
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * util.DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    # Calculate gear dimensions
    dw = module * num_teeth  # pitch diameter
    rb = dw * math.cos(pressure_angle_rad) / 2.0  # base radius
    ra = dw / 2.0 + module * (ADDENDUM_FACTOR + profile_shift)  # addendum radius
    rf = dw / 2.0 - module * (DEDENDUM_FACTOR - profile_shift)  # root radius

    if "tip_radius" in parameters:
        ra = parameters["tip_radius"]

    # Half angular tooth thickness at base circle
    s_pitch = module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    theta_base = s_pitch / dw + inv_alpha

    # Fixed rotation to position tooth on Y-axis
    rotation = math.pi / 2.0 - theta_base

    # Generate involute points
    num_points = 12
    start_radius = max(rb + 0.001, rf)
    involute_pts = []
    is_pointed = False

    for i in range(num_points):
        t = i / (num_points - 1)
        r = start_radius + t * (ra - start_radius)

        if r <= rb:
            roll_angle = 0
        else:
            phi = math.acos(rb / r)
            roll_angle = math.tan(phi)

        # Raw involute point
        x_inv = rb * (math.cos(roll_angle) + roll_angle * math.sin(roll_angle))
        y_inv = rb * (math.sin(roll_angle) - roll_angle * math.cos(roll_angle))

        # Rotate to position
        x_rot = x_inv * math.cos(rotation) - y_inv * math.sin(rotation)
        y_rot = x_inv * math.sin(rotation) + y_inv * math.cos(rotation)

        if x_rot <= 0.001:
            is_pointed = True
            involute_pts.append(App.Vector(0, math.sqrt(x_inv**2 + y_inv**2), 0))
            break

        involute_pts.append(App.Vector(x_rot, y_rot, 0))

    # Mirror for left flank
    left_pts = util.mirrorPointsX(involute_pts)

    geo_list = []
    has_radial = rf < rb

    # 1. Right radial flank (line from root to base, if needed)
    if has_radial:
        p_root_right = App.Vector(rf * math.cos(rotation), rf * math.sin(rotation), 0)
        line = Part.LineSegment(p_root_right, involute_pts[0])
        geo_list.append(sketch.addGeometry(line, False))
    else:
        p_root_right = involute_pts[0]

    # 2. Right involute flank (B-spline)
    if len(involute_pts) >= 2:
        bspline = Part.BSplineCurve()
        bspline.interpolate(involute_pts)
        geo_list.append(sketch.addGeometry(bspline, False))

    # 3. Top land (arc or line)
    p_tip_right = involute_pts[-1]
    p_tip_left = left_pts[0]

    if not is_pointed and p_tip_right.x > 0.001 and p_tip_left.x < -0.001:
        # Arc on addendum circle
        angle_right = math.atan2(p_tip_right.y, p_tip_right.x)
        angle_left = math.atan2(p_tip_left.y, p_tip_left.x)
        if angle_right < 0:
            angle_right += 2 * math.pi
        if angle_left < 0:
            angle_left += 2 * math.pi

        arc_circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), ra)
        arc = Part.ArcOfCircle(arc_circle, angle_right, angle_left)
        geo_list.append(sketch.addGeometry(arc, False))
    else:
        # Pointed or nearly pointed - use line
        line = Part.LineSegment(p_tip_right, p_tip_left)
        geo_list.append(sketch.addGeometry(line, False))

    # 4. Left involute flank - use line segments instead of B-spline
    if len(left_pts) >= 2:
        # Use simple line segments through left involute points
        for i in range(len(left_pts) - 1):
            line = Part.LineSegment(left_pts[i], left_pts[i + 1])
            geo_list.append(sketch.addGeometry(line, False))
        
    

    # 5. Left radial flank (line, if needed)
    if has_radial:
        p_root_left = App.Vector(-p_root_right.x, p_root_right.y, 0)
        line = Part.LineSegment(left_pts[-1], p_root_left)
        geo_list.append(sketch.addGeometry(line, False))
    else:
        p_root_left = left_pts[-1]

    # 6. Root closure (line)
    root_line = Part.LineSegment(p_root_left, p_root_right)
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
    return {"module": 1.0, "num_teeth": 45, "pressure_angle": 20.0, "profile_shift": 0.0, 
            "height": 10.0, "rim_thickness": 3.0, "body_name": "InternalSpurGear"}

def generateDefaultRackParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 20, "pressure_angle": 20.0, "height": 10.0, 
            "base_thickness": 5.0, "body_name": "RackGear"}

def generateDefaultCycloidParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 30, "height": 5.0, "addendum_factor": 1.4, 
            "dedendum_factor": 1.6, "bore_type": "none", "bore_diameter": 5.0, "body_name": "CycloidGear"}

def generateDefaultCycloidRackParameters() -> Dict[str, Any]:
    return {"module": 1.0, "num_teeth": 20, "height": 5.0, "addendum_factor": 1.4,
            "dedendum_factor": 1.6, "base_thickness": 5.0, "body_name": "CycloidRack"}

# ============================================================================
# GEAR TYPE DEFAULT PROFILE FUNCTIONS
# ============================================================================

def generateSpurGearProfile(sketch, parameters):
    """
    Default tooth profile function for spur gears.
    Wrapper around generateToothProfile for explicit type identification.
    """
    generateToothProfile(sketch, parameters)

def generateHelicalGearProfile(sketch, parameters):
    """
    Tooth profile function for helical/herringbone gears.

    Converts from normal module convention (manufacturing standard) to
    transverse values for the tooth profile:
    - Transverse module: mt = mn / cos(β)
    - Transverse pressure angle: tan(αt) = tan(αn) / cos(β)

    Args:
        sketch: FreeCAD sketch object
        parameters: Dict with normal module, normal pressure angle, helix_angle
    """
    helix_angle = parameters.get("helix_angle", 0.0)

    if helix_angle == 0:
        # No helix - use parameters as-is (spur gear)
        generateToothProfile(sketch, parameters)
        return

    # Convert to transverse values
    beta_rad = helix_angle * util.DEG_TO_RAD
    cos_beta = math.cos(beta_rad)

    mn = parameters["module"]  # normal module
    alpha_n = parameters["pressure_angle"]  # normal pressure angle (degrees)
    alpha_n_rad = alpha_n * util.DEG_TO_RAD

    # Transverse module: mt = mn / cos(β)
    mt = mn / cos_beta

    # Transverse pressure angle: tan(αt) = tan(αn) / cos(β)
    alpha_t_rad = math.atan(math.tan(alpha_n_rad) / cos_beta)
    alpha_t = alpha_t_rad * util.RAD_TO_DEG

    # Create modified parameters with transverse values
    transverse_params = parameters.copy()
    transverse_params["module"] = mt
    transverse_params["pressure_angle"] = alpha_t

    generateToothProfile(sketch, transverse_params)

def generateInternalToothProfile(sketch, parameters):
    """
    Generates INTERNAL involute tooth profile (teeth pointing inward).

    Correct loop order (closed, non-self-crossing):
      tip_right -> base_right -> ... -> root_right
      root arc on rf_internal to root_left
      root_left -> ... -> base_left
      base_left -> tip_left
      tip arc on ra_internal to tip_right
    """
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * util.DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    # Internal gear radii (note: tip is inward, root is outward)
    dw = module * num_teeth
    rb = dw * math.cos(pressure_angle_rad) / 2.0
    ra_internal = dw / 2.0 - module * (ADDENDUM_FACTOR + profile_shift)  # inner tip radius
    rf_internal = dw / 2.0 + module * (DEDENDUM_FACTOR - profile_shift)  # outer root radius

    if "tip_radius" in parameters:
        ra_internal = parameters["tip_radius"]

    # Half angular tooth thickness at base circle
    s_pitch = module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    theta_base = s_pitch / dw + inv_alpha

    # Position tooth on +Y axis
    rotation = math.pi / 2.0 - theta_base

    # --- involute generation (base -> root) ---
    num_points = 12
    start_radius = max(rb + 0.001, ra_internal)  # start at base (or slightly above) for internal
    involute_pts = []
    is_pointed = False

    for i in range(num_points):
        t = i / (num_points - 1)
        r = start_radius + t * (rf_internal - start_radius)

        if r <= rb:
            roll_angle = 0.0
        else:
            phi = math.acos(rb / r)
            roll_angle = math.tan(phi)

        x_inv = rb * (math.cos(roll_angle) + roll_angle * math.sin(roll_angle))
        y_inv = rb * (math.sin(roll_angle) - roll_angle * math.cos(roll_angle))

        x_rot = x_inv * math.cos(rotation) - y_inv * math.sin(rotation)
        y_rot = x_inv * math.sin(rotation) + y_inv * math.cos(rotation)

        if x_rot <= 0.001:
            is_pointed = True
            involute_pts.append(App.Vector(0, math.sqrt(x_inv * x_inv + y_inv * y_inv), 0))
            break

        involute_pts.append(App.Vector(x_rot, y_rot, 0))

    if len(involute_pts) < 1:
        return

    left_pts = util.mirrorPointsX(involute_pts)

    # Robustly enforce base->root order by radius
    def _r(p: App.Vector) -> float:
        return math.hypot(p.x, p.y)

    right_sorted = sorted(involute_pts, key=_r)   # base -> root
    left_sorted  = sorted(left_pts,    key=_r)    # base -> root

    base_right = right_sorted[0]
    root_right = right_sorted[-1]
    base_left  = left_sorted[0]
    root_left  = left_sorted[-1]

    # Tip points are on the ra_internal circle at +/- x for this tooth orientation
    p_tip_right = App.Vector(ra_internal * math.cos(rotation),  ra_internal * math.sin(rotation), 0)
    p_tip_left  = App.Vector(-p_tip_right.x, p_tip_right.y, 0)

    geo_list = []

    # Helper: add an arc on a given radius using the *shorter* angular span
    def _add_short_arc(radius: float, p_start: App.Vector, p_end: App.Vector):
        a0 = math.atan2(p_start.y, p_start.x)
        a1 = math.atan2(p_end.y,   p_end.x)

        # normalize to [0, 2pi)
        if a0 < 0: a0 += 2 * math.pi
        if a1 < 0: a1 += 2 * math.pi

        # choose the shorter CCW or CW span by possibly wrapping end angle
        ccw = (a1 - a0) % (2 * math.pi)
        cw  = (a0 - a1) % (2 * math.pi)

        if ccw <= cw:
            start_ang = a0
            end_ang   = a0 + ccw
        else:
            # use opposite direction by swapping and still constructing as increasing angles
            start_ang = a1
            end_ang   = a1 + cw
            # but we want arc from p_start to p_end, so reverse if needed by swapping points
            # easiest: just build arc from p_end to p_start
            p_start, p_end = p_end, p_start

        circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), radius)
        arc = Part.ArcOfCircle(circle, start_ang, end_ang)
        geo_list.append(sketch.addGeometry(arc, False))

    # 1) Tip-right -> base-right (radial-ish line) if needed
    has_radial = ra_internal < rb
    if has_radial:
        geo_list.append(sketch.addGeometry(Part.LineSegment(p_tip_right, base_right), False))
    else:
        # If no radial, ensure continuity from tip point to first involute point
        # (still add a segment; otherwise the tip arc has nothing to attach to)
        geo_list.append(sketch.addGeometry(Part.LineSegment(p_tip_right, base_right), False))

    # 2) Right involute (base -> root)
    for i in range(len(right_sorted) - 1):
        geo_list.append(sketch.addGeometry(Part.LineSegment(right_sorted[i], right_sorted[i + 1]), False))

    # 3) Root connection on rf_internal (outer circle): root_right -> root_left
    # Use arc unless the tooth is effectively pointed/degenerate
    if not is_pointed and _r(root_right) > 0.0 and _r(root_left) > 0.0:
        _add_short_arc(rf_internal, root_right, root_left)
    else:
        geo_list.append(sketch.addGeometry(Part.LineSegment(root_right, root_left), False))

    # 4) Left involute (root -> base)  [THIS IS THE CRITICAL FIX]
    for i in range(len(left_sorted) - 1, 0, -1):
        geo_list.append(sketch.addGeometry(Part.LineSegment(left_sorted[i], left_sorted[i - 1]), False))

    # 5) base-left -> tip-left (radial-ish line)
    if has_radial:
        geo_list.append(sketch.addGeometry(Part.LineSegment(base_left, p_tip_left), False))
    else:
        geo_list.append(sketch.addGeometry(Part.LineSegment(base_left, p_tip_left), False))

    # 6) Tip connection on ra_internal (inner circle): tip_left -> tip_right
    if not is_pointed and _r(p_tip_left) > 0.0 and _r(p_tip_right) > 0.0:
        _add_short_arc(ra_internal, p_tip_left, p_tip_right)
    else:
        geo_list.append(sketch.addGeometry(Part.LineSegment(p_tip_left, p_tip_right), False))

    util.finalizeSketchGeometry(sketch, geo_list)

def generateInternalToothProfile1(sketch, parameters):
    """
    Generates INTERNAL involute tooth profile (teeth pointing inward).
    Uses B-splines for involute flanks, arcs for tip and root.
    Based on generateToothProfile but modified for internal gear geometry.

    For internal gears:
    - Addendum is inward (smaller radius than pitch)
    - Dedendum is outward (larger radius than pitch)
    - Involute curve is same shape but teeth point toward center
    """
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * util.DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)
    

    # Calculate internal gear dimensions
    dw = module * num_teeth  # pitch diameter
    rb = dw * math.cos(pressure_angle_rad) / 2.0  # base radius
    ra_internal = dw / 2.0 - module * (ADDENDUM_FACTOR + profile_shift)  # inner tip radius
    rf_internal = dw / 2.0 + module * (DEDENDUM_FACTOR - profile_shift)  # outer root radius
    

    if "tip_radius" in parameters:
        ra_internal = parameters["tip_radius"]

    # Half angular tooth thickness at base circle
    s_pitch = module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    theta_base = s_pitch / dw + inv_alpha
    

    # Fixed rotation to position tooth on Y-axis (pointing inward)
    rotation = math.pi / 2.0 - theta_base
    

    # Generate involute points - same math as external gear
    num_points = 12
    start_radius = max(rb + 0.001, ra_internal)
    involute_pts = []
    is_pointed = False
    

    for i in range(num_points):
        t = i / (num_points - 1)
        r = start_radius + t * (rf_internal - start_radius)

        if r <= rb:
            roll_angle = 0
        else:
            phi = math.acos(rb / r)
            roll_angle = math.tan(phi)

        # Raw involute point (same calculation as external gear)
        x_inv = rb * (math.cos(roll_angle) + roll_angle * math.sin(roll_angle))
        y_inv = rb * (math.sin(roll_angle) - roll_angle * math.cos(roll_angle))

        # Rotate to position
        x_rot = x_inv * math.cos(rotation) - y_inv * math.sin(rotation)
        y_rot = x_inv * math.sin(rotation) + y_inv * math.cos(rotation)

        if x_rot <= 0.001:
            is_pointed = True
            involute_pts.append(App.Vector(0, math.sqrt(x_inv**2 + y_inv**2), 0))    
            break

        involute_pts.append(App.Vector(x_rot, y_rot, 0))

    

    # Mirror for left flank
    
    left_pts = util.mirrorPointsX(involute_pts)
    

    geo_list = []
    has_radial = ra_internal < rb
    
    # 1. Right radial flank (line from tip to base, if needed)
    # For internal gear: tip is inward (smaller radius), root is outward (larger)
    
    if has_radial:
        p_tip_right = App.Vector(ra_internal * math.cos(rotation), ra_internal * math.sin(rotation), 0)
        line = Part.LineSegment(p_tip_right, involute_pts[0])
        geo_list.append(sketch.addGeometry(line, False))

    else:
        p_tip_right = involute_pts[0]

    # 2. Right involute flank - use line segments instead of B-spline to avoid polar freeze
    if len(involute_pts) >= 2:
        # Use simple line segments through involute points
        for i in range(len(involute_pts) - 1):
            line = Part.LineSegment(involute_pts[i], involute_pts[i + 1])
            geo_list.append(sketch.addGeometry(line, False))

    # 3. Root arc (outer edge at rf_internal)
    # For internal gear, use line to avoid overlap

    p_root_right = involute_pts[-1]
    p_root_left = left_pts[-1]


    # For internal gears, use simple line to avoid polar pattern issues

    line = Part.LineSegment(p_root_right, p_root_left)
    geo_list.append(sketch.addGeometry(line, False))

    # 4. Left involute flank - use line segments instead of B-spline

    if len(left_pts) >= 2:
        # Use simple line segments through left involute points
        for i in range(len(left_pts) - 1):
            line = Part.LineSegment(left_pts[i], left_pts[i + 1])
            geo_list.append(sketch.addGeometry(line, False))


    # 5. Left radial flank (line, if needed)

    if has_radial:
        p_tip_left = App.Vector(-p_tip_right.x, p_tip_right.y, 0)
        line = Part.LineSegment(left_pts[0], p_tip_left)
        geo_list.append(sketch.addGeometry(line, False))

    else:
        p_tip_left = left_pts[0]


    # 6. Tip connection (inner edge at ra_internal)
    # For internal gear, use line to avoid polar pattern issues

    if not is_pointed and p_tip_right.x > 0.001 and p_tip_left.x < -0.001:
        # Use simple line for internal gears

        line = Part.LineSegment(p_tip_left, p_tip_right)
        geo_list.append(sketch.addGeometry(line, False))
    elif not is_pointed:
        # Fallback: line between tip points

        line = Part.LineSegment(p_tip_left, p_tip_right)
        geo_list.append(sketch.addGeometry(line, False))
    util.finalizeSketchGeometry(sketch, geo_list)


# ============================================================================
# GEAR TYPE DEFAULT PROFILE FUNCTIONS
# ============================================================================

def generateInternalSpurGearProfile(sketch, parameters):
    """
    Default tooth profile function for internal spur gears.
    Wrapper around generateInternalToothProfile for explicit type identification.
    """
    generateInternalToothProfile(sketch, parameters)
