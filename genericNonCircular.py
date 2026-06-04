"""
genericNonCircular.py — engine for parametric non-circular gears.

Built in the style of genericGear.py / genericInternalGear.py: a single
builder, nonCircularGear(), takes a `profile_func` and constructs a PartDesign
Body (sketch -> pad -> bore), reusing genericGear's createMasterBore() and
_applyOriginAndAngle() so the Height / Bore / Keyway parameters are bound to
the VarSet by expressions (live updates), while shape-changing parameters are
driven by the proxy's full rebuild.

The one structural difference from genericGear: a circular gear has rotational
symmetry, so its profile_func draws ONE tooth into a sketch and the builder
polar-patterns it.  A non-circular gear has no such symmetry, so its
profile_func returns the ENTIRE closed outline as a list of App.Vector points,
and the builder lays that outline down as a single closed periodic B-spline.

profile_func contract:
    profile_func(parameters) -> list[App.Vector]   # closed outline, z = 0

Copyright 2025.  License LGPL V2.1
"""

import FreeCAD as App
import FreeCADGui
import Part
import util
from genericGear import createMasterBore, _applyOriginAndAngle


# ============================================================================
# VALIDATION
# ============================================================================

def validateNonCircular(parameters):
    """Validate parameters common to every non-circular gear."""
    if float(parameters.get("height", 0.0)) <= 0.0:
        raise ValueError("Height must be positive")
    if float(parameters.get("major_radius", 1.0)) <= 0.0:
        raise ValueError("Major radius must be positive")


# ============================================================================
# OUTLINE -> SKETCH
# ============================================================================

def _dedupe(points, tol=1e-7):
    """Drop consecutive duplicate points and any explicit closing duplicate.

    A periodic B-spline closes itself, so a repeated first/last point would
    make the interpolation degenerate.
    """
    out = []
    for p in points:
        v = App.Vector(p.x, p.y, 0.0)
        if not out or (v - out[-1]).Length > tol:
            out.append(v)
    while len(out) > 3 and (out[0] - out[-1]).Length < tol:
        out.pop()
    return out


def _outlineSketch(body, points, name="Profile"):
    """Add the closed outline to a new sketch as a closed polyline.

    A periodic B-spline through this many points cannot be padded reliably
    (OCCT raises 'Geom_TrimmedCurve::parameters out of range'), so the outline
    is laid down as line segments instead.  Consecutive segments are built
    from the SAME point objects, so their shared endpoints are bit-identical
    and the wire closes exactly — PartDesign Pad accepts it with no
    constraints and no solver cost.
    """
    pts = _dedupe(points)
    n = len(pts)
    if n < 3:
        raise ValueError("Outline needs at least 3 distinct points")

    sketch = util.createSketch(body, name)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]          # last segment wraps back to the first point
        sketch.addGeometry(Part.LineSegment(a, b), False)
    return sketch


# ============================================================================
# MASTER BUILDER
# ============================================================================

def nonCircularGear(doc, parameters, profile_func=None):
    """Build a non-circular gear body from a profile function.

    Args:
        doc: FreeCAD document.
        parameters: dict.  Required: 'height', 'body_name'.  If 'varset_name'
            is present, Height/Bore/Keyway are bound to it via expressions
            (so they update without a Python rebuild); otherwise a plain bore
            is cut from the supplied numeric values.
        profile_func: callable(parameters) -> list[App.Vector] closed outline.

    Returns:
        {'body': body}
    """
    if profile_func is None:
        raise ValueError("nonCircularGear requires a profile_func")
    validateNonCircular(parameters)

    body_name = parameters.get("body_name", "NonCircularGear")
    height = float(parameters["height"])
    varset_name = parameters.get("varset_name")

    points = profile_func(parameters)
    if not points:
        raise ValueError("profile_func returned no points")

    body = util.readyPart(doc, body_name)

    # Outline -> pad
    sketch = _outlineSketch(body, points, "Profile")
    pad = util.createPad(body, sketch, height, "Body")
    if varset_name:
        pad.setExpression("Length", f"<<{varset_name}>>.Height")
    body.Tip = pad

    # Bore + keyway: expression-bound when a VarSet is available (matches the
    # genericGear philosophy), otherwise a plain numeric bore.
    if varset_name:
        createMasterBore(body, parameters, height, varset_name)
    elif parameters.get("bore_type", "none") != "none":
        util.createBore(body, parameters, height,
                        keyway_enabled=parameters.get("keyway_enabled", False))

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    _applyOriginAndAngle(body, parameters)
    return {"body": body}
