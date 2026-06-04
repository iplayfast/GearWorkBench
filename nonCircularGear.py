"""Non-Circular Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric non-circular gears.

Copyright 2025, Chris Bruner
Version v0.1.3
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
from PySide import QtCore
import genericNonCircular
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "NonCircularGear.svg")

version = "Nov 30, 2025"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# GENERATION LOGIC
# ============================================================================


def validateNonCircularParameters(parameters):
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")
    if parameters["number_of_lobes"] < 1:
        raise gearMath.GearParameterError("Number of lobes must be at least 1")
    if parameters["major_radius"] <= 0:
        raise gearMath.GearParameterError("Major radius must be positive")


def generateLobedProfile(parameters):
    """Generate a lobed profile using a sinusoidal radius function.

    Uses the function: R(theta) = R_avg + Amplitude * cos(N * theta)
    where N is the number of lobes.

    Args:
        parameters: Dictionary containing:
            - number_of_lobes: Number of lobes in the profile
            - major_radius: Maximum radius
            - minor_radius: Minimum radius

    Returns:
        List of App.Vector points defining the profile
    """
    number_of_lobes = parameters["number_of_lobes"]
    major_radius = parameters["major_radius"]
    minor_radius = parameters["minor_radius"]

    # Calculate average radius and amplitude
    r_avg = (major_radius + minor_radius) / 2.0
    amplitude = (major_radius - minor_radius) / 2.0

    num_points = 120  # Resolution
    profile_points = []

    for i in range(num_points):
        theta = (2 * math.pi * i) / num_points
        # The radius function
        r = r_avg + amplitude * math.cos(number_of_lobes * theta)

        x = r * math.cos(theta)
        y = r * math.sin(theta)
        profile_points.append(App.Vector(x, y, 0))

    return profile_points


def _generateToothProfilePoints(module, num_teeth, pressure_angle_deg=20.0, profile_shift=0.0):
    """Generate involute tooth profile points relative to the pitch point.

    Returns two lists of App.Vector points in a local coordinate frame where:
      - Origin is at the pitch point
      - Y-axis points radially outward (tooth extends in +Y)
      - X-axis points in the tangent direction

    Returns:
        (right_flank, left_flank)
        right_flank: list from root to tip on the right side
        left_flank:  list from tip to root on the left side (mirrored, reversed)
    """
    pressure_angle_rad = pressure_angle_deg * util.DEG_TO_RAD

    dw = module * num_teeth
    rb = dw * math.cos(pressure_angle_rad) / 2.0
    r_pitch = dw / 2.0
    ra = r_pitch + module * gearMath.ADDENDUM_FACTOR
    rf = r_pitch - module * gearMath.DEDENDUM_FACTOR

    s_pitch = module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pressure_angle_rad))
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    theta_base = s_pitch / dw + inv_alpha
    rotation = math.pi / 2.0 - theta_base

    num_points = 12
    start_radius = max(rb + 0.001, rf)
    right_flank = []

    for i in range(num_points):
        t = i / (num_points - 1)
        r = start_radius + t * (ra - start_radius)

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
            r_pt = math.hypot(x_inv, y_inv)
            right_flank.append(App.Vector(0.0, r_pt - r_pitch, 0.0))
            break

        right_flank.append(App.Vector(x_rot, y_rot - r_pitch, 0.0))

    # The involute only exists from the base circle (rb) outward, so the loop
    # above leaves each flank bottoming out at the base circle.  The root
    # circle (rf) is below that.  Extend the flank radially inward from its
    # base-circle point down to the root depth, so the flank meets the root
    # section at the SAME radius.  Without this the bridging segments cross
    # under every tooth and the padded outline self-intersects.
    if right_flank and rf < start_radius - 1e-9:
        base_pt = right_flank[0]
        cx = base_pt.x
        cy = base_pt.y + r_pitch            # vector from gear centre to point
        r0 = math.hypot(cx, cy)
        if r0 > 1e-9:
            s = rf / r0
            right_flank.insert(0, App.Vector(cx * s, cy * s - r_pitch, 0.0))

    left_flank = [App.Vector(-p.x, p.y, 0.0) for p in reversed(right_flank)]

    return right_flank, left_flank

def _arc_to_theta(target_arc, theta_samples, arc_samples):
    """Interpolate theta from arc-length position using sampled data."""
    idx = 0
    for i in range(len(arc_samples)):
        if arc_samples[i] <= target_arc:
            idx = i
    if idx >= len(arc_samples) - 1:
        return theta_samples[-1]
    t = ((target_arc - arc_samples[idx])
         / (arc_samples[idx + 1] - arc_samples[idx] + 1e-12))
    return theta_samples[idx] + t * (theta_samples[idx + 1] - theta_samples[idx])


def generateToothedProfile(parameters):
    """Generate a toothed non-circular gear profile with involute teeth.

    Places involute teeth along the lobed pitch curve at correct arc-length
    spacing. Each tooth is oriented perpendicular to the curve tangent.
    Root sections connect adjacent teeth following the pitch curve offset
    inward by dedendum.

    The lobed pitch curve is: R(theta) = R_avg + Amplitude * cos(N * theta)

    Args:
        parameters: Dictionary containing:
            - module: Tooth module (default 1.0)
            - num_teeth: Number of teeth (default 20)
            - pressure_angle: Pressure angle in degrees (default 20)
            - number_of_lobes: Number of lobes
            - major_radius: Maximum radius
            - minor_radius: Minimum radius

    Returns:
        List of App.Vector points defining the closed toothed gear outline
    """
    module = parameters.get("module", 1.0)
    num_teeth = parameters.get("num_teeth", 20)
    pressure_angle = parameters.get("pressure_angle", 20.0)
    profile_shift = parameters.get("profile_shift", 0.0)
    number_of_lobes = parameters["number_of_lobes"]
    major_radius = parameters["major_radius"]
    minor_radius = parameters["minor_radius"]

    r_avg = (major_radius + minor_radius) / 2.0
    amplitude = (major_radius - minor_radius) / 2.0
    dedendum = module * gearMath.DEDENDUM_FACTOR

    # Generate canonical tooth profile relative to pitch point
    right_flank, left_flank = _generateToothProfilePoints(
        module, num_teeth, pressure_angle, profile_shift
    )

    n_samples = max(num_teeth * 16, 1440)
    theta_samples = [0.0] * (n_samples + 1)
    arc_samples = [0.0] * (n_samples + 1)

    dtheta = 2.0 * math.pi / n_samples
    for i in range(n_samples + 1):
        theta = i * dtheta
        theta_samples[i] = theta
        if i > 0:
            theta_mid = (theta + theta_samples[i - 1]) * 0.5
            r = r_avg + amplitude * math.cos(number_of_lobes * theta_mid)
            dr = -number_of_lobes * amplitude * math.sin(number_of_lobes * theta_mid)
            ds = math.hypot(r, dr) * dtheta
            arc_samples[i] = arc_samples[i - 1] + ds
        else:
            arc_samples[i] = 0.0

    total_arc = arc_samples[-1]
    tooth_spacing = total_arc / num_teeth

    needed = num_teeth * math.pi * module
    if needed > total_arc * 1.001:
        raise gearMath.GearParameterError(
            "Teeth do not fit: %d teeth at module %.2f need %.1f mm of pitch "
            "perimeter, but the pitch curve is only %.1f mm. Reduce the tooth "
            "count or module, or enlarge the curve."
            % (num_teeth, module, needed, total_arc))

    outline = []

    for k in range(num_teeth):
        target_arc = k * tooth_spacing
        theta_k = _arc_to_theta(target_arc, theta_samples, arc_samples)

        r = r_avg + amplitude * math.cos(number_of_lobes * theta_k)
        dr_dtheta = -number_of_lobes * amplitude * math.sin(number_of_lobes * theta_k)

        P = App.Vector(r * math.cos(theta_k), r * math.sin(theta_k), 0.0)

        dx = dr_dtheta * math.cos(theta_k) - r * math.sin(theta_k)
        dy = dr_dtheta * math.sin(theta_k) + r * math.cos(theta_k)
        T = App.Vector(dx, dy, 0.0)
        T.normalize()

        N = App.Vector(math.cos(theta_k), math.sin(theta_k), 0.0)

        # Walk the tooth in the same direction the roots advance (see
        # generateControlPointProfile): up the trailing (-T) flank, over the
        # tip, down the leading (+T) flank.
        for pt in reversed(left_flank):
            outline.append(P + T * pt.x + N * pt.y)

        tip_left = left_flank[0]
        tip_right = right_flank[-1]
        num_tip = 3
        for i in range(1, num_tip + 1):
            t = i / num_tip
            mx = tip_left.x + t * (tip_right.x - tip_left.x)
            my = tip_left.y + t * (tip_right.y - tip_left.y)
            outline.append(P + T * mx + N * my)

        for pt in reversed(right_flank):
            outline.append(P + T * pt.x + N * pt.y)

        # Root fills only the gap between adjacent teeth (see
        # generateControlPointProfile).  w = tooth tangential half-width.
        w = max(abs(p.x) for p in right_flank)
        gap = tooth_spacing - 2.0 * w
        if gap < tooth_spacing * 0.05:
            w = tooth_spacing * 0.475
            gap = tooth_spacing - 2.0 * w
        n_root = 10
        for i in range(1, n_root + 1):
            t = i / (n_root + 1)
            arc_pos = target_arc + w + t * gap
            if abs(arc_pos - total_arc) < 1e-12:
                arc_pos = 0.0

            theta_mid = _arc_to_theta(arc_pos, theta_samples, arc_samples)
            r_mid = r_avg + amplitude * math.cos(number_of_lobes * theta_mid)
            nx = math.cos(theta_mid)
            ny = math.sin(theta_mid)

            outline.append(App.Vector(
                r_mid * nx - dedendum * nx,
                r_mid * ny - dedendum * ny,
                0.0
            ))

    return outline


class _PeriodicSpline:
    """Closed (periodic) interpolating spline through control points.

    Exposes only the slice of the Part.BSplineCurve interface that the
    control-point profile sampler uses: FirstParameter, LastParameter and
    value(u).  Parameter u runs 0..n (n = number of control points) and wraps
    periodically, so the curve is closed by construction.

    Implemented in pure Python (uniform periodic Catmull-Rom) because OCCT's
    BSplineCurve.interpolate() raises Standard_ConstructionError for periodic
    interpolation in some builds.  Since this curve is only sampled to trace
    the pitch line (never turned into geometry), an OCCT curve is unnecessary.
    """

    def __init__(self, pts):
        self.pts = list(pts)
        self.n = len(self.pts)

    @property
    def FirstParameter(self):
        return 0.0

    @property
    def LastParameter(self):
        return float(self.n)

    def value(self, u):
        n = self.n
        u = u % n
        i = int(math.floor(u))
        f = u - i
        p0 = self.pts[(i - 1) % n]
        p1 = self.pts[i % n]
        p2 = self.pts[(i + 1) % n]
        p3 = self.pts[(i + 2) % n]
        f2 = f * f
        f3 = f2 * f
        # Catmull-Rom basis (tension 0.5)
        x = 0.5 * (2 * p1.x
                   + (-p0.x + p2.x) * f
                   + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * f2
                   + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * f3)
        y = 0.5 * (2 * p1.y
                   + (-p0.y + p2.y) * f
                   + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * f2
                   + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * f3)
        return App.Vector(x, y, 0.0)


def generateControlPointProfile(parameters):
    """Generate a toothed gear profile from control-point-defined pitch curve.

    Reads N control points (1-5) from parameters, creates a smooth closed
    B-spline pitch curve, then places involute teeth along the curve using
    arc-length parameterization.

    Args:
        parameters: Dictionary containing:
            - point_count: Number of control points (1-5)
            - p1_x, p1_y, ... p5_x, p5_y: Control point coordinates
            - module: Tooth module
            - num_teeth: Number of teeth
            - pressure_angle: Pressure angle in degrees
            - profile_shift: Profile shift coefficient

    Returns:
        List of App.Vector points defining the closed toothed gear outline
    """
    module = parameters.get("module", 1.0)
    num_teeth = parameters.get("num_teeth", 20)
    pressure_angle = parameters.get("pressure_angle", 20.0)
    profile_shift = parameters.get("profile_shift", 0.0)
    point_count = parameters["point_count"]

    dedendum = module * gearMath.DEDENDUM_FACTOR

    # Collect active control points
    pts = []
    for i in range(point_count):
        pts.append(App.Vector(
            parameters[f"p{i+1}_x"],
            parameters[f"p{i+1}_y"],
            0.0
        ))

    # A closed pitch curve is a PERIODIC B-spline through the distinct control
    # points.  (Do NOT duplicate the first point onto the end and ask for a
    # non-periodic curve — OCCT rejects an open curve whose ends coincide with
    # Standard_ConstructionError.)  This curve is only sampled below, never
    # padded, so periodic is safe here.
    if len(pts) < 3:
        raise gearMath.GearParameterError(
            "Control-point profile needs at least 3 points (PointCount >= 3)")

    # Closed pitch curve through the control points.  Pure-Python periodic
    # spline (see _PeriodicSpline) instead of Part.BSplineCurve.interpolate,
    # which raises Standard_ConstructionError for periodic interpolation here.
    bspline = _PeriodicSpline(pts)

    u_start = bspline.FirstParameter
    u_end = bspline.LastParameter

    # Generate canonical tooth profile relative to pitch point
    right_flank, left_flank = _generateToothProfilePoints(
        module, num_teeth, pressure_angle, profile_shift
    )

    # Build dense arc-length parameterization of the B-spline
    n_dense = 500
    u_samples = [0.0] * (n_dense + 1)
    arc_samples = [0.0] * (n_dense + 1)

    prev_pt = None
    for i in range(n_dense + 1):
        u = u_start + (u_end - u_start) * i / n_dense
        u_samples[i] = u
        pt = bspline.value(u)
        if i > 0:
            ds = (pt - prev_pt).Length
            arc_samples[i] = arc_samples[i - 1] + ds
        else:
            arc_samples[i] = 0.0
        prev_pt = pt

    total_arc = arc_samples[-1]
    tooth_spacing = total_arc / num_teeth

    needed = num_teeth * math.pi * module
    if needed > total_arc * 1.001:
        raise gearMath.GearParameterError(
            "Teeth do not fit: %d teeth at module %.2f need %.1f mm of pitch "
            "perimeter, but the pitch curve is only %.1f mm. Reduce the tooth "
            "count or module, or enlarge the curve."
            % (num_teeth, module, needed, total_arc))

    # Centroid of control points for outward normal determination
    centroid = App.Vector(0, 0, 0)
    for p in pts:
        centroid += p
    centroid /= len(pts)

    def _arc_to_u(target_arc):
        idx = 0
        for i in range(len(arc_samples)):
            if arc_samples[i] <= target_arc:
                idx = i
        if idx >= len(arc_samples) - 1:
            return u_samples[-1]
        t = ((target_arc - arc_samples[idx])
             / (arc_samples[idx + 1] - arc_samples[idx] + 1e-12))
        return u_samples[idx] + t * (u_samples[idx + 1] - u_samples[idx])

    outline = []

    for k in range(num_teeth):
        target_arc = k * tooth_spacing
        u_k = _arc_to_u(target_arc)

        P = bspline.value(u_k)

        eps = 1e-6
        p_lo = bspline.value(u_k - eps)
        p_hi = bspline.value(u_k + eps)
        deriv = (p_hi - p_lo) * (0.5 / eps)
        T = App.Vector(deriv.x, deriv.y, 0.0)
        T.normalize()

        # Outward normal: perpendicular to tangent, pointing away from centroid
        N = App.Vector(-T.y, T.x, 0.0)
        if N.dot(P - centroid) < 0:
            N = -N

        # Walk the tooth in the SAME direction the root sections advance
        # (increasing arc).  left_flank is the trailing (-T) side and is stored
        # tip->root, so reverse it to climb root->tip; right_flank is the
        # leading (+T) side stored root->tip, so reverse it to descend tip->root.
        # Going up one side and down the other in arc order keeps the outline
        # monotonic and non-self-intersecting.

        # Up the trailing (-T) flank: root -> tip
        for pt in reversed(left_flank):
            outline.append(P + T * pt.x + N * pt.y)

        # Tooth tip (arc across top): trailing tip -> leading tip
        tip_left = left_flank[0]
        tip_right = right_flank[-1]
        num_tip = 3
        for i in range(1, num_tip + 1):
            t = i / num_tip
            mx = tip_left.x + t * (tip_right.x - tip_left.x)
            my = tip_left.y + t * (tip_right.y - tip_left.y)
            outline.append(P + T * mx + N * my)

        # Down the leading (+T) flank: tip -> root
        for pt in reversed(right_flank):
            outline.append(P + T * pt.x + N * pt.y)

        # Root section fills only the GAP between this tooth's leading flank
        # and the next tooth's trailing flank.  Spanning the full tooth_spacing
        # (as if teeth had zero width) makes the root lap into the next tooth
        # and the outline self-intersects.  w = tooth tangential half-width.
        w = max(abs(p.x) for p in right_flank)
        gap = tooth_spacing - 2.0 * w
        if gap < tooth_spacing * 0.05:        # teeth nearly touch
            w = tooth_spacing * 0.475
            gap = tooth_spacing - 2.0 * w
        n_root = 10
        for i in range(1, n_root + 1):
            t = i / (n_root + 1)
            arc_pos = target_arc + w + t * gap
            if abs(arc_pos - total_arc) < 1e-12:
                arc_pos = 0.0

            u_mid = _arc_to_u(arc_pos)
            P_mid = bspline.value(u_mid)

            eps = 1e-6
            p_lo = bspline.value(u_mid - eps)
            p_hi = bspline.value(u_mid + eps)
            deriv_mid = (p_hi - p_lo) * (0.5 / eps)
            T_mid = App.Vector(deriv_mid.x, deriv_mid.y, 0.0)
            T_mid.normalize()
            N_mid = App.Vector(-T_mid.y, T_mid.x, 0.0)
            if N_mid.dot(P_mid - centroid) < 0:
                N_mid = -N_mid

            outline.append(P_mid - N_mid * dedendum)

    return outline


def generateNonCircularGearPart(doc, parameters):
    """Generate non-circular gear using the generic non-circular system.

    Non-circular gears have varying radius and are used for applications
    requiring non-constant velocity ratios.
    """
    validateNonCircularParameters(parameters)

    toothed = parameters.get("module", None) is not None
    if "point_count" in parameters:
        profile_func = generateControlPointProfile
    else:
        profile_func = generateToothedProfile if toothed else generateLobedProfile

    result = genericNonCircular.nonCircularGear(
        doc, parameters, profile_func=profile_func
    )

    return result


def createNonCircularGearVarSet(doc, name):
    vs = doc.addObject("App::VarSet", name)
    vs.addProperty("App::PropertyString","Version","read only","",1).Version = version
    vs.addProperty("App::PropertyInteger","PointCount","Profile","Number of control points (1-5)").PointCount = 4
    vs.addProperty("App::PropertyDistance","P1_X","Profile","Point 1 X").P1_X = 15.0
    vs.addProperty("App::PropertyDistance","P1_Y","Profile","Point 1 Y").P1_Y = 0.0
    vs.addProperty("App::PropertyDistance","P2_X","Profile","Point 2 X").P2_X = 0.0
    vs.addProperty("App::PropertyDistance","P2_Y","Profile","Point 2 Y").P2_Y = 12.0
    vs.addProperty("App::PropertyDistance","P3_X","Profile","Point 3 X").P3_X = -15.0
    vs.addProperty("App::PropertyDistance","P3_Y","Profile","Point 3 Y").P3_Y = 0.0
    vs.addProperty("App::PropertyDistance","P4_X","Profile","Point 4 X").P4_X = 0.0
    vs.addProperty("App::PropertyDistance","P4_Y","Profile","Point 4 Y").P4_Y = -12.0
    vs.addProperty("App::PropertyDistance","P5_X","Profile","Point 5 X").P5_X = 0.0
    vs.addProperty("App::PropertyDistance","P5_Y","Profile","Point 5 Y").P5_Y = 0.0
    vs.addProperty("App::PropertyInteger","NumberOfLobes","NonCircular","Number of lobes").NumberOfLobes = 2
    vs.addProperty("App::PropertyLength","MajorRadius","NonCircular","Major radius").MajorRadius = 15.0
    vs.addProperty("App::PropertyLength","MinorRadius","NonCircular","Minor radius").MinorRadius = 10.0
    vs.addProperty("App::PropertyFloat","Module","Tooth","Tooth module").Module = 1.0
    vs.addProperty("App::PropertyInteger","NumberOfTeeth","Tooth","Number of teeth").NumberOfTeeth = 20
    vs.addProperty("App::PropertyLength","Height","NonCircular","Gear height").Height = 10.0
    vs.addProperty("App::PropertyLength","BoreDiameter","Bore","Bore diameter").BoreDiameter = 5.0
    vs.addProperty("App::PropertyLength","KeywayWidth","Bore","Keyway width").KeywayWidth = 2.0
    vs.addProperty("App::PropertyLength","KeywayDepth","Bore","Keyway depth").KeywayDepth = 1.0
    vs.addProperty("App::PropertyBool","BoreEnabled","Bore","Enable bore").BoreEnabled = True
    vs.addProperty("App::PropertyBool","KeywayEnabled","Bore","Enable keyway").KeywayEnabled = False
    vs.addProperty("App::PropertyLength","PitchDiameter","read only","",1).PitchDiameter = 0.0
    vs.addProperty("App::PropertyLength","BaseDiameter","read only","",1).BaseDiameter = 0.0
    vs.addProperty("App::PropertyLength","OuterDiameter","read only","",1).OuterDiameter = 0.0
    vs.addProperty("App::PropertyLength","RootDiameter","read only","",1).RootDiameter = 0.0
    return vs


class NonCircularGearResult:
    def __init__(self, obj, varset):
        self._varset = varset; self._rebuilding = False
        self._last_nl = self._last_mjr = self._last_mnr = self._last_h = None
        self._last_mod = self._last_nt = None
        self._last_pc = None
        self._last_p1x = self._last_p1y = None
        self._last_p2x = self._last_p2y = None
        self._last_p3x = self._last_p3y = None
        self._last_p4x = self._last_p4y = None
        self._last_p5x = self._last_p5y = None
        self._watcher = None; self._needs_rebuild = False
        self.Type = "NonCircularGearResult"
        obj.addProperty("App::PropertyString","VarSetName","Gear","",1).VarSetName=varset.Name
        obj.addProperty("App::PropertyString","BodyName","Gear","").BodyName=varset.Name.replace("_values","_Body",1)
        obj.addProperty("App::PropertyString","Version","read only","",1).Version=version
        obj.addProperty("App::PropertyString","Status","read only","",1)
        obj.Proxy=self; self.Object=obj; obj.Status="Not yet generated"
        self._startWatcher(varset.Name)
    def __getstate__(self): return self.Type
    def __setstate__(self,s):
        if s: self.Type=s
        self._varset=None; self._rebuilding=False
        self._last_nl=self._last_mjr=self._last_mnr=self._last_h=None
        self._last_mod=self._last_nt=None
        self._last_pc=None
        self._last_p1x=self._last_p1y=None
        self._last_p2x=self._last_p2y=None
        self._last_p3x=self._last_p3y=None
        self._last_p4x=self._last_p4y=None
        self._last_p5x=self._last_p5y=None
        self._watcher=None; self._needs_rebuild=False
    def onDocumentRestored(self,obj):
        self.Object=obj; v=self._getVarSet()
        if v:
            self._last_nl=int(v.NumberOfLobes); self._last_mjr=float(v.MajorRadius.Value)
            self._last_mnr=float(v.MinorRadius.Value); self._last_h=float(v.Height.Value)
            self._last_mod=float(v.Module); self._last_nt=int(v.NumberOfTeeth)
            self._last_pc = int(v.PointCount) if hasattr(v,'PointCount') else None
            self._last_p1x = float(v.P1_X.Value) if hasattr(v,'P1_X') else None
            self._last_p1y = float(v.P1_Y.Value) if hasattr(v,'P1_Y') else None
            self._last_p2x = float(v.P2_X.Value) if hasattr(v,'P2_X') else None
            self._last_p2y = float(v.P2_Y.Value) if hasattr(v,'P2_Y') else None
            self._last_p3x = float(v.P3_X.Value) if hasattr(v,'P3_X') else None
            self._last_p3y = float(v.P3_Y.Value) if hasattr(v,'P3_Y') else None
            self._last_p4x = float(v.P4_X.Value) if hasattr(v,'P4_X') else None
            self._last_p4y = float(v.P4_Y.Value) if hasattr(v,'P4_Y') else None
            self._last_p5x = float(v.P5_X.Value) if hasattr(v,'P5_X') else None
            self._last_p5y = float(v.P5_Y.Value) if hasattr(v,'P5_Y') else None
            self._startWatcher(v.Name); obj.Status="Up to date"
    def _startWatcher(self,vn):
        self._stopWatcher(); self._watcher=_VarSetWatcher(self,vn,watched=frozenset((
            "NumberOfLobes","MajorRadius","MinorRadius","Module","NumberOfTeeth",
            "Height","BoreEnabled","KeywayEnabled","BoreDiameter","KeywayWidth","KeywayDepth",
            "PointCount","P1_X","P1_Y","P2_X","P2_Y","P3_X","P3_Y","P4_X","P4_Y","P5_X","P5_Y")))
        App.addDocumentObserver(self._watcher)
    def _stopWatcher(self):
        if self._watcher:
            try: App.removeDocumentObserver(self._watcher)
            except: pass
            self._watcher=None
    def _getVarSet(self):
        if self._varset is None:
            try: self._varset=self.Object.Document.getObject(self.Object.VarSetName)
            except: pass
        return self._varset
    def execute(self,obj): pass
    def _values_changed(self):
        v=self._getVarSet()
        if not v or self._last_nl is None: return v is not None
        E=1e-9
        if int(v.NumberOfLobes)!=self._last_nl: return True
        if abs(float(v.MajorRadius.Value)-self._last_mjr)>E: return True
        if abs(float(v.MinorRadius.Value)-self._last_mnr)>E: return True
        if abs(float(v.Height.Value)-self._last_h)>E: return True
        if abs(float(v.Module)-self._last_mod)>E: return True
        if int(v.NumberOfTeeth)!=self._last_nt: return True
        if hasattr(v,'PointCount') and int(v.PointCount)!=self._last_pc: return True
        if hasattr(v,'P1_X') and abs(float(v.P1_X.Value)-self._last_p1x)>E: return True
        if hasattr(v,'P1_Y') and abs(float(v.P1_Y.Value)-self._last_p1y)>E: return True
        if hasattr(v,'P2_X') and abs(float(v.P2_X.Value)-self._last_p2x)>E: return True
        if hasattr(v,'P2_Y') and abs(float(v.P2_Y.Value)-self._last_p2y)>E: return True
        if hasattr(v,'P3_X') and abs(float(v.P3_X.Value)-self._last_p3x)>E: return True
        if hasattr(v,'P3_Y') and abs(float(v.P3_Y.Value)-self._last_p3y)>E: return True
        if hasattr(v,'P4_X') and abs(float(v.P4_X.Value)-self._last_p4x)>E: return True
        if hasattr(v,'P4_Y') and abs(float(v.P4_Y.Value)-self._last_p4y)>E: return True
        if hasattr(v,'P5_X') and abs(float(v.P5_X.Value)-self._last_p5x)>E: return True
        if hasattr(v,'P5_Y') and abs(float(v.P5_Y.Value)-self._last_p5y)>E: return True
        return False
    def _set_needs_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._needs_rebuild=True
        try: self.Object.Status="Regenerating..."
        except: pass
        QtCore.QTimer.singleShot(0,self._deferred_rebuild)
    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding: return
        if not self._values_changed(): self._needs_rebuild=False; return
        self._needs_rebuild=False; QtCore.QTimer.singleShot(0,self._deferred_rebuild)
    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._rebuild()
    def _rebuild(self):
        self._rebuilding=True; vn=None
        try:
            v=self._getVarSet()
            if not v: return
            vn=v.Name; bn=str(self.Object.BodyName); d=self.Object.Document
            self._last_nl=int(v.NumberOfLobes); self._last_mjr=float(v.MajorRadius.Value)
            self._last_mnr=float(v.MinorRadius.Value); self._last_h=float(v.Height.Value)
            self._last_mod=float(v.Module); self._last_nt=int(v.NumberOfTeeth)
            self._last_pc = int(v.PointCount) if hasattr(v,'PointCount') else None
            self._last_p1x = float(v.P1_X.Value) if hasattr(v,'P1_X') else None
            self._last_p1y = float(v.P1_Y.Value) if hasattr(v,'P1_Y') else None
            self._last_p2x = float(v.P2_X.Value) if hasattr(v,'P2_X') else None
            self._last_p2y = float(v.P2_Y.Value) if hasattr(v,'P2_Y') else None
            self._last_p3x = float(v.P3_X.Value) if hasattr(v,'P3_X') else None
            self._last_p3y = float(v.P3_Y.Value) if hasattr(v,'P3_Y') else None
            self._last_p4x = float(v.P4_X.Value) if hasattr(v,'P4_X') else None
            self._last_p4y = float(v.P4_Y.Value) if hasattr(v,'P4_Y') else None
            self._last_p5x = float(v.P5_X.Value) if hasattr(v,'P5_X') else None
            self._last_p5y = float(v.P5_Y.Value) if hasattr(v,'P5_Y') else None
            if self._last_nl<2 or self._last_mjr<=0 or self._last_mnr<=0 or self._last_h<=0:
                self.Object.Status="Invalid params"; return
            self._stopWatcher()
            saved_placement=None
            old=d.getObject(bn)
            if old:
                saved_placement=App.Placement(old.Placement)
                ch=list(old.Group)
                for c in ch:
                    for p in c.PropertiesList:
                        try: c.setExpression(p,None)
                        except: pass
                for c in reversed(ch):
                    try: d.removeObject(c.Name)
                    except: pass
                d.removeObject(bn)
            self.Object.Status="Generating..."
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
            params = {
                "number_of_lobes":self._last_nl,"major_radius":self._last_mjr,
                "minor_radius":self._last_mnr,"height":self._last_h,
                "module":self._last_mod,"num_teeth":self._last_nt,
                "pressure_angle":20.0,"profile_shift":0.0,
                "bore_type":("circular" if (bool(v.BoreEnabled) and float(v.BoreDiameter.Value)>0) else "none"),
                "bore_diameter":float(v.BoreDiameter.Value),
                "keyway_width":float(v.KeywayWidth.Value),
                "keyway_depth":float(v.KeywayDepth.Value),"body_name":bn,
                "varset_name":vn,
            }
            # Control-point pitch-curve mode: supply point_count + pN_x/pN_y so
            # generateNonCircularGearPart dispatches to generateControlPointProfile.
            # (These are the keys that function actually reads.)
            if self._last_pc is not None and self._last_pc > 0:
                params["point_count"] = self._last_pc
                for i in range(1, 6):
                    params[f"p{i}_x"] = getattr(self, f"_last_p{i}x", 0.0) or 0.0
                    params[f"p{i}_y"] = getattr(self, f"_last_p{i}y", 0.0) or 0.0

            generateNonCircularGearPart(d, params)
            d.recompute()
            if saved_placement:
                nb=d.getObject(bn)
                if nb: nb.Placement=saved_placement
            self.Object.Status="Up to date"
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
        except Exception as e:
            import traceback; App.Console.PrintError(traceback.format_exc())
            try:
                p=d.getObject(bn)
                if p:
                    for c in list(p.Group):
                        try: d.removeObject(c.Name)
                        except: pass
                    d.removeObject(bn)
            except: pass
            self.Object.Status="Error"
        finally:
            if vn: self._startWatcher(vn)
            self._rebuilding=False
    def force_Recompute(self): self._rebuild()


class NonCircularGearCreateObject:
    """Command to create a new non-circular gear object."""

    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Non-Circular Gear",
            "ToolTip": "Create parametric non-circular gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc=App.ActiveDocument
        base="NonCircularGear_values"; un=base; c=1
        while doc.getObject(un): un=f"{base}{c:03d}"; c+=1
        vs=createNonCircularGearVarSet(doc,un)
        gn="Regenerate"; c=1
        while doc.getObject(gn): gn=f"Regenerate{c:03d}"; c+=1
        go=doc.addObject("Part::FeaturePython",gn)
        NonCircularGearResult(go,vs)
        ViewProviderGearResult(go.ViewObject,mainIcon)
        go.Proxy.force_Recompute()
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


class NonCircularGear:
    """FeaturePython object for parametric non-circular gear."""

    def __init__(self, obj):
        """Initialize non-circular gear with default parameters.

        Args:
            obj: FreeCAD document object
        """
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties (less applicable for non-circular, but keep for consistency)
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        # Core gear parameters for non-circular
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfLobes",
            "NonCircularGear",
            QT_TRANSLATE_NOOP(
                "App::Property", "Number of lobes/repetitions in the profile"
            ),
        ).NumberOfLobes = 2  # Default to an elliptical-like shape

        obj.addProperty(
            "App::PropertyLength",
            "MajorRadius",
            "NonCircularGear",
            QT_TRANSLATE_NOOP(
                "App::Property", "Major radius of the non-circular profile"
            ),
        ).MajorRadius = 15.0

        obj.addProperty(
            "App::PropertyLength",
            "MinorRadius",
            "NonCircularGear",
            QT_TRANSLATE_NOOP(
                "App::Property", "Minor radius (for elliptical/lobed shapes)"
            ),
        ).MinorRadius = 10.0

        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "NonCircularGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
        ).Height = H["height"]

        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "NonCircularGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = H["body_name"]
        obj.BodyName = "NonCircularGear"  # Override default spur gear name

        # Bore parameters (keep for consistency)
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

        self.Type = "NonCircularGear"
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_body_name = obj.BodyName
        obj.Proxy = self

        # No direct derived read-only properties for non-circular in the same way
        # as involute gears. These will remain 0 unless explicitly set.
        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter"),
        ).PitchDiameter = 0.0
        obj.addProperty(
            "App::PropertyLength",
            "BaseDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Base diameter"),
        ).BaseDiameter = 0.0
        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter"),
        ).OuterDiameter = 0.0
        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter"),
        ).RootDiameter = 0.0

    def __getstate__(self):
        """Return object state for serialization."""
        return self.Type

    def __setstate__(self, state):
        """Restore object state from serialization."""
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """Called when a property changes.

        Args:
            fp: Feature Python object
            prop: Property name that changed
        """
        # Mark for recompute when any property changes
        self.Dirty = True

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        doc.removeObject(old_body)
                self.last_body_name = new_name

        # For non-circular gears, read-only properties like diameters are not
        # directly calculated in the same way as involute gears.
        # They could be derived from the profile, but for now, they are static.

    def GetParameters(self):
        """Get current parameters as dictionary.

        Returns:
            Dictionary of current parameter values
        """
        parameters = {
            "number_of_lobes": int(self.Object.NumberOfLobes),
            "major_radius": float(self.Object.MajorRadius.Value),
            "minor_radius": float(self.Object.MinorRadius.Value),
            "height": float(self.Object.Height.Value),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
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
                generateNonCircularGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Non-Circular Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Non-Circular Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Non-Circular Gear Error: {str(e)}\n")
                import traceback

                App.Console.PrintError(traceback.format_exc())
                raise

    def set_dirty(self):
        """Mark object as needing recomputation."""
        self.Dirty = True

    def execute(self, obj):
        """Execute gear generation with delay.

        Args:
            obj: FreeCAD document object
        """
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderNonCircularGear:
    """View provider for NonCircularGear object."""

    def __init__(self, obj, iconfile=None):
        """Initialize view provider.

        Args:
            obj: View provider object
            iconfile: Optional path to icon file
        """
        obj.Proxy = self
        self.part = obj
        self.iconfile = iconfile if iconfile else mainIcon

    def attach(self, obj):
        """Setup the scene sub-graph.

        Args:
            obj: View provider object
        """
        self.ViewObject = obj
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        """Called when a property of the handled feature has changed.

        Args:
            fp: Feature Python object
            prop: Property name that changed
        """
        return

    def getDisplayModes(self, obj):
        """Return a list of display modes.

        Args:
            obj: View provider object

        Returns:
            List of mode names
        """
        modes = ["Shaded", "Wireframe", "Flat Lines"]
        return modes

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode.

        Returns:
            Mode name string
        """
        return "Shaded"

    def setDisplayMode(self, mode):
        """Set the display mode.

        Args:
            mode: Display mode name

        Returns:
            Actual mode to use
        """
        return mode

    def onChanged(self, vobj, prop):
        """Called when a view property has changed.

        Args:
            vobj: View provider object
            prop: Property name that changed
        """
        return

    def getIcon(self):
        """Return the icon in XPM format.

        Returns:
            Path to icon file or XPM data
        """
        return self.iconfile

    def doubleClicked(self, vobj):
        """Called when object is double-clicked.

        Args:
            vobj: View provider object

        Returns:
            True if handled
        """
        return True

    def setupContextMenu(self, vobj, menu):
        """Setup custom context menu.

        Args:
            vobj: View provider object
            menu: QMenu object to add items to
        """
        from PySide import QtGui, QtCore

        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        """Force regeneration of the gear."""
        if hasattr(self.Object, "Proxy"):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        """Return object state for serialization.

        Returns:
            Icon file path
        """
        return self.iconfile

    def __setstate__(self, state):
        """Restore object state from serialization.

        Args:
            state: Previously saved state
        """
        if state:
            self.iconfile = state
        else:
            self.iconfile = mainIcon
        return None


# Register command with FreeCAD
try:
    FreeCADGui.addCommand("NonCircularGearCreateObject", NonCircularGearCreateObject())
    # App.Console.PrintMessage("NonCircularGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register NonCircularGearCreateObject: {e}\n")
    import traceback

    App.Console.PrintError(traceback.format_exc())
