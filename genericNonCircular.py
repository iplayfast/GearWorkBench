"""Generic Non-Circular Gear generator for FreeCAD

Builds a non-circular gear from individual spur-gear and rack shapes
fused into a single solid.

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""

from __future__ import division

import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher
import math
from PySide import QtCore


def _spurGearOutline(parameters):
    """Return list of App.Vector forming a closed spur-gear perimeter."""
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pa = parameters.get("pressure_angle", 20.0)
    ps = parameters.get("profile_shift", 0.0)

    pr = module * num_teeth / 2.0
    pa_r = pa * util.DEG_TO_RAD
    ad = module * gearMath.ADDENDUM_FACTOR
    dd = module * gearMath.DEDENDUM_FACTOR
    ra = pr + ad
    rf = pr - dd
    rb = pr * math.cos(pa_r)

    sp = module * (math.pi / 2.0 + 2.0 * ps * math.tan(pa_r))
    inv = math.tan(pa_r) - pa_r
    tb = sp / (2.0 * pr) + inv
    rot = math.pi / 2.0 - tb

    def _tooth():
        n = 12
        sr = max(rb + 0.001, rf)
        r = []
        for i in range(n):
            t = i / (n - 1)
            r0 = sr + t * (ra - sr)
            if r0 <= rb:
                roll = 0.0
            else:
                roll = math.tan(math.acos(rb / r0))
            xi = rb * (math.cos(roll) + roll * math.sin(roll))
            yi = rb * (math.sin(roll) - roll * math.cos(roll))
            xr = xi * math.cos(rot) - yi * math.sin(rot)
            yr = xi * math.sin(rot) + yi * math.cos(rot)
            if xr <= 0.001:
                r.append(App.Vector(0, math.hypot(xi, yi), 0))
                break
            r.append(App.Vector(xr, yr, 0))
        l = [App.Vector(-p.x, p.y, 0) for p in reversed(r)]
        return r, l

    rfl, lfl = _tooth()
    pts = []
    for k in range(num_teeth):
        a = 2.0 * math.pi * k / num_teeth
        c, s = math.cos(a), math.sin(a)
        for p in rfl:
            pts.append(App.Vector(p.x * c - p.y * s, p.x * s + p.y * c, 0))
        tr, tl = rfl[-1], lfl[0]
        for i in range(1, 4):
            t = i / 4.0
            mx = tr.x + t * (tl.x - tr.x)
            my = tr.y + t * (tl.y - tr.y)
            pts.append(App.Vector(mx * c - my * s, mx * s + my * c, 0))
        for p in lfl:
            pts.append(App.Vector(p.x * c - p.y * s, p.x * s + p.y * c, 0))
        na = 2.0 * math.pi * (k + 1) / num_teeth
        for i in range(1, 7):
            t = i / 7.0
            aa = a + t * (na - a)
            pts.append(App.Vector(rf * math.cos(aa), rf * math.sin(aa), 0))
    return pts


def _rackOutline(parameters):
    """Return list of App.Vector forming a closed rack perimeter.
    Teeth in +Y, rack length along X, centered at origin.
    """
    module = parameters["module"]
    length = parameters["length"]
    pa = parameters.get("pressure_angle", 20.0)

    ad = module * gearMath.ADDENDUM_FACTOR
    dd = module * gearMath.DEDENDUM_FACTOR
    pitch = math.pi * module
    ta = math.tan(pa * util.DEG_TO_RAD)
    hp = pitch / 4.0
    wt = hp - ad * ta
    wr = hp + dd * ta

    nt = max(1, int(length / pitch))
    actual = nt * pitch
    half = actual / 2.0

    pts = []
    for k in range(nt):
        cx = -half + k * pitch + pitch / 2.0
        pts.append(App.Vector(cx + wr, -dd, 0))
        pts.append(App.Vector(cx + wt, ad, 0))
        pts.append(App.Vector(cx - wt, ad, 0))
        pts.append(App.Vector(cx - wr, -dd, 0))
        if k < nt - 1:
            nxt = cx + pitch
            for i in range(1, 4):
                t = i / 4.0
                rx = cx + wr + t * (nxt - wr - cx - wr)
                pts.append(App.Vector(rx, -dd, 0))
    return pts


def compositeNonCircular(doc, parameters):
    """Build a composite non-circular gear.

    Creates spur-gear solids at each lobe center and rack solids
    between them, fuses all into one shape, pads an interior
    cylinder on top, then adds bore/keyway.
    """
    body_name = parameters.get("body_name", "NonCircularGear")
    height = parameters["height"]
    module = parameters["module"]
    pa = parameters.get("pressure_angle", 20.0)
    centers = parameters.get("lobe_centers", [])
    bore_type = parameters.get("bore_type", "none")

    # ---- 1. Build all component solids ----
    solids = []
    total = len(centers) + len(centers)

    for idx, (lx, ly) in enumerate(centers):
        App.Console.PrintMessage(f"Building gear {idx+1}/{len(centers)} at ({lx:.1f}, {ly:.1f})...\n")
        if App.GuiUp:
            from PySide import QtCore
            QtCore.QCoreApplication.processEvents()
        radius = math.hypot(lx, ly)
        nt = max(6, int(2.0 * radius / module))
        pts = _spurGearOutline({"module": module, "num_teeth": nt,
                                "pressure_angle": pa, "profile_shift": 0.0})
        wire = Part.makePolygon(pts + [pts[0]])
        solid = Part.Face(wire).extrude(App.Vector(0, 0, height))
        a = math.atan2(ly, lx)
        solid.Placement = App.Placement(
            App.Vector(lx, ly, 0), App.Rotation(App.Vector(0, 0, 1), math.degrees(a)))
        solids.append(solid)
        if App.GuiUp:
            QtCore.QCoreApplication.processEvents()

    n = len(centers)
    for i in range(n):
        App.Console.PrintMessage(f"Building rack {i+1}/{n}...\n")
        if App.GuiUp:
            QtCore.QCoreApplication.processEvents()
        p1 = App.Vector(centers[i][0], centers[i][1], 0)
        p2 = App.Vector(centers[(i + 1) % n][0], centers[(i + 1) % n][1], 0)
        d = p2 - p1
        length = d.Length
        if length < 0.1:
            continue
        pts = _rackOutline({"module": module, "length": length, "pressure_angle": pa})
        wire = Part.makePolygon(pts + [pts[0]])
        solid = Part.Face(wire).extrude(App.Vector(0, 0, height))
        mid = (p1 + p2) * 0.5
        # +Y (teeth) points radially outward
        td = math.atan2(mid.y, mid.x)
        solid.Placement = App.Placement(
            App.Vector(mid.x, mid.y, 0),
            App.Rotation(App.Vector(0, 0, 1), math.degrees(td - math.pi / 2.0)))
        solids.append(solid)

    if not solids:
        raise gearMath.GearParameterError("No components generated")

    # ---- 2. Manual fuse chain (more robust than MultiFuse) ----
    App.Console.PrintMessage(f"Fusing {len(solids)} components...\n")
    if App.GuiUp: QtCore.QCoreApplication.processEvents()
    fused = solids[0]
    for idx, s in enumerate(solids[1:], 1):
        try:
            fused = fused.fuse(s)
        except Exception:
            try:
                fused = fused.fuse(s)
            except Exception:
                fused = Part.Compound([fused, s])
        if idx % 2 == 0 and App.GuiUp:
            QtCore.QCoreApplication.processEvents()

    # ---- 3. Interior pad (fills center, covers inner teeth) ----
    max_r = max(math.hypot(lx, ly) for lx, ly in centers)
    core_r = max(0.5, max_r - module * 3.0)
    core_edge = Part.makeCircle(core_r, App.Vector(0, 0, 0), App.Vector(0, 0, 1))
    core_wire = Part.Wire(core_edge)
    core = Part.Face(core_wire).extrude(App.Vector(0, 0, height))
    App.Console.PrintMessage("Adding interior core pad...\n")
    if App.GuiUp: QtCore.QCoreApplication.processEvents()
    fused = fused.fuse(core)

    # ---- 4. Create body with fused shape as BaseFeature ----
    App.Console.PrintMessage("Creating body...\n")
    if App.GuiUp: QtCore.QCoreApplication.processEvents()
    body = util.readyPart(doc, body_name)
    shape_obj = doc.addObject("Part::Feature", f"_{body_name}_Core")
    shape_obj.Shape = fused
    shape_obj.Visibility = False
    body.BaseFeature = shape_obj
    body.Tip = None
    doc.recompute()

    # ---- 5. Bore ----
    if bore_type != "none":
        bd = parameters["bore_diameter"]
        bore_sk = util.createSketch(body, "Bore")
        ci = bore_sk.addGeometry(
            Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), bd / 2), False)
        bore_sk.addConstraint(Sketcher.Constraint("Coincident", ci, 3, -1, 1))
        bore_sk.addConstraint(Sketcher.Constraint("Diameter", ci, bd))
        bp = util.createPocket(body, bore_sk, height + 1.0, "Bore")
        bp.Reversed = True
        body.Tip = bp

    body.ViewObject.Visibility = True
    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass
    return body
