"""Geneva Wheel (Maltese Cross) mechanism generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating a parametric Geneva wheel mechanism. The Geneva wheel converts
continuous rotation into intermittent motion.

Based on the Geneva_Wheel_GUI.FCMacro by Isaac Ayala (drei) & Mark Stephen (quick61).

Copyright 2025, Chris Bruner
Version v0.1
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
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "genevaWheel.svg")

version = "0.1"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VALIDATION & MATH
# ============================================================================


def validateGenevaParameters(params):
    """Validate Geneva wheel parameters.

    Args:
        params: Dictionary with keys: num_slots, crank_radius, pin_radius, tolerance, height

    Raises:
        gearMath.GearParameterError: If parameters are invalid
    """
    n = params["num_slots"]
    a = params["crank_radius"]
    p = params["pin_radius"]
    t = params["tolerance"]
    h = params["height"]

    if n < 3:
        raise gearMath.GearParameterError("Number of slots must be >= 3")
    if a <= 0:
        raise gearMath.GearParameterError("Crank radius must be positive")
    if p <= 0:
        raise gearMath.GearParameterError("Pin radius must be positive")
    if t < 0:
        raise gearMath.GearParameterError("Tolerance must be >= 0")
    if h <= 0:
        raise gearMath.GearParameterError("Height must be positive")
    if a <= 3 * p + t:
        raise gearMath.GearParameterError(
            f"Crank radius ({a}) must be > 3*pin_radius + tolerance ({3*p + t})"
        )


def calculateGenevaGeometry(params):
    """Calculate derived Geneva wheel geometry from input parameters.

    Args:
        params: Dictionary with keys: num_slots, crank_radius, pin_radius, tolerance

    Returns:
        Dictionary with derived values: c, b, s, w, y, z, v, m
    """
    n = params["num_slots"]
    a = params["crank_radius"]
    p = params["pin_radius"]
    t = params["tolerance"]

    c = a / math.sin(math.pi / n)  # Center distance
    b = math.sqrt(c**2 - a**2)  # Wheel radius
    s = a + b - c  # Slot center width
    w = p + t  # Slot width
    y = a - 3 * p  # Stop arc radius
    z = y - t  # Stop disc radius
    v = (b * z) / a  # Clearance arc radius
    m = math.sqrt(v**2 + z**2)  # Clearance cut axis offset

    return {"c": c, "b": b, "s": s, "w": w, "y": y, "z": z, "v": v, "m": m}


# ============================================================================
# PARTDESIGN GENERATION
# ============================================================================


def _addCircleSketch(body, name, radius, cx=0.0, cy=0.0):
    """Create a sketch with a single circle and Block constraint.

    Returns (sketch, geometry_index).
    """
    sk = util.createSketch(body, name)
    idx = sk.addGeometry(
        Part.Circle(App.Vector(cx, cy, 0), App.Vector(0, 0, 1), radius), False
    )
    sk.addConstraint(Sketcher.Constraint('Block', idx))
    return sk


def _buildGenevaWheel(doc, params, geo, body_name):
    """Build the Geneva wheel using PartDesign features.

    Built centered at body origin; caller sets body.Placement to offset.
    Features: base disc pad, stop arc pockets (polar), slot pockets (polar).
    """
    n = params["num_slots"]
    h = params["height"]
    c = geo["c"]
    b = geo["b"]
    s = geo["s"]
    w = geo["w"]
    y = geo["y"]

    body = util.readyPart(doc, body_name)

    # 1. Base disc (centered at origin in body space)
    sk_disc = _addCircleSketch(body, "WheelDisc", b)
    disc_pad = util.createPad(body, sk_disc, h, "WheelDisc")
    body.Tip = disc_pad

    # 2. Stop arc cuts — circle of radius y at distance c, offset by 180/n
    # In wheel-local coords, the crank center is at (c, 0).
    # Stop arcs are rotated by (180/n + 360/n) from X-axis so they fall between slots.
    stop_angle = math.pi / n + 2 * math.pi / n  # first cut position
    cx_stop = c * math.cos(stop_angle)
    cy_stop = c * math.sin(stop_angle)

    sk_stop = _addCircleSketch(body, "StopArc", y, cx_stop, cy_stop)
    stop_pocket = util.createPocket(body, sk_stop, h, "StopArc")
    stop_pocket.Reversed = True
    body.Tip = stop_pocket

    stop_polar = util.createPolar(body, stop_pocket, sk_disc, n, "StopArcs")
    stop_polar.Originals = [stop_pocket]
    stop_pocket.Visibility = False
    body.Tip = stop_polar

    # 3. Slot cuts — stadium shape (rectangle + semicircle cap)
    # In wheel-local coords, slot inner end is at distance (c - a) along X
    c_a = c - params["crank_radius"]  # radial distance from wheel center to slot inner end
    # Extend slot slightly past wheel edge so cut goes cleanly through
    slot_outer = c_a + s + 0.1

    sk_slot = util.createSketch(body, "Slot")

    # Slot profile: 3 lines + 1 semicircular arc forming a closed stadium
    # Bottom line
    g0 = sk_slot.addGeometry(Part.LineSegment(
        App.Vector(c_a, -w, 0), App.Vector(slot_outer, -w, 0)), False)
    # Right end
    g1 = sk_slot.addGeometry(Part.LineSegment(
        App.Vector(slot_outer, -w, 0), App.Vector(slot_outer, w, 0)), False)
    # Top line
    g2 = sk_slot.addGeometry(Part.LineSegment(
        App.Vector(slot_outer, w, 0), App.Vector(c_a, w, 0)), False)
    # Semicircle cap (left end)
    g3 = sk_slot.addGeometry(Part.Arc(
        App.Vector(c_a, w, 0),
        App.Vector(c_a - w, 0, 0),
        App.Vector(c_a, -w, 0)), False)

    geo_indices = [g0, g1, g2, g3]
    util.finalizeSketchGeometry(sk_slot, geo_indices, closed=True, block=True)

    slot_pocket = util.createPocket(body, sk_slot, h, "Slot")
    slot_pocket.Reversed = True
    body.Tip = slot_pocket

    slot_polar = util.createPolar(body, slot_pocket, sk_disc, n, "Slots")
    slot_polar.Originals = [slot_pocket]
    slot_pocket.Visibility = False
    body.Tip = slot_polar

    # 4. Bore
    bore_type = params.get("wheel_bore_type", "none")
    if bore_type != "none":
        bore_params = {
            "bore_type": bore_type,
            "bore_diameter": params.get("wheel_bore_diameter", 5.0),
        }
        try:
            util.createBore(body, bore_params, h)
        except Exception as e:
            App.Console.PrintWarning(f"Could not add wheel bore: {e}\n")

    # 5. Offset body to wheel position
    body.Placement = App.Placement(App.Vector(-c, 0, 0), App.Rotation())


def _buildDriveCrank(doc, params, geo, body_name):
    """Build the drive crank using PartDesign features.

    Features: base disc (reversed pad), locking disc (pad), clearance pocket, pin pad.
    """
    a = params["crank_radius"]
    p = params["pin_radius"]
    h = params["height"]
    z_val = geo["z"]
    v = geo["v"]
    m = geo["m"]

    body = util.readyPart(doc, body_name)

    # 1. Base disc — larger radius, extends below Z=0 (reversed)
    sk_base = _addCircleSketch(body, "CrankBase", a + 2 * p)
    base_pad = util.createPad(body, sk_base, h, "CrankBase")
    base_pad.Reversed = True  # Extend from Z=0 downward to Z=-h
    body.Tip = base_pad

    # 2. Locking disc — smaller radius, extends above Z=0
    sk_lock = _addCircleSketch(body, "LockingDisc", z_val)
    lock_pad = util.createPad(body, sk_lock, h, "LockingDisc")
    body.Tip = lock_pad

    # 3. Clearance cut — circle at (-m, 0), radius v, through locking disc
    sk_clear = _addCircleSketch(body, "ClearanceCut", v, -m, 0.0)
    clear_pocket = util.createPocket(body, sk_clear, h, "ClearanceCut")
    clear_pocket.Reversed = True
    body.Tip = clear_pocket

    # 4. Drive pin — circle at (-a, 0), radius p, same height as locking disc
    sk_pin = _addCircleSketch(body, "DrivePin", p, -a, 0.0)
    pin_pad = util.createPad(body, sk_pin, h, "DrivePin")
    body.Tip = pin_pad

    # 5. Bore
    bore_type = params.get("crank_bore_type", "none")
    if bore_type != "none":
        bore_params = {
            "bore_type": bore_type,
            "bore_diameter": params.get("crank_bore_diameter", 5.0),
        }
        try:
            util.createBore(body, bore_params, 2 * h)
        except Exception as e:
            App.Console.PrintWarning(f"Could not add crank bore: {e}\n")


def _removeBody(doc, body_name):
    """Remove a body cleanly."""
    obj = doc.getObject(body_name)
    if obj:
        if hasattr(obj, "removeObjectsFromDocument"):
            obj.removeObjectsFromDocument()
        doc.removeObject(body_name)


def generateGenevaWheelPart(doc, params):
    """Orchestrate creation of both Geneva wheel bodies.

    Creates two PartDesign::Body objects:
    - Drive crank at origin
    - Geneva wheel offset to (-c, 0, 0)
    """
    validateGenevaParameters(params)
    geo = calculateGenevaGeometry(params)

    crank_body_name = params.get("crank_body_name", "GenevaCrank")
    wheel_body_name = params.get("wheel_body_name", "GenevaWheel")

    _buildDriveCrank(doc, params, geo, crank_body_name)
    _buildGenevaWheel(doc, params, geo, wheel_body_name)

    doc.recompute()


def createGenevaWheelVarSet(doc, name):
    vs = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultGenevaParameters()
    vs.addProperty("App::PropertyString","Version","read only","",1).Version = version
    vs.addProperty("App::PropertyInteger","NumberOfSlots","GenevaWheel","Number of slots").NumberOfSlots = H["num_slots"]
    vs.addProperty("App::PropertyLength","CrankRadius","GenevaWheel","Drive crank radius").CrankRadius = H["crank_radius"]
    vs.addProperty("App::PropertyLength","PinRadius","GenevaWheel","Drive pin radius").PinRadius = H["pin_radius"]
    vs.addProperty("App::PropertyLength","Tolerance","GenevaWheel","Clearance tolerance").Tolerance = H["tolerance"]
    vs.addProperty("App::PropertyLength","Height","GenevaWheel","Mechanism thickness").Height = H["height"]
    vs.addProperty("App::PropertyLength","CrankBoreDiameter","CrankBore","Crank bore diameter").CrankBoreDiameter = H["bore_diameter"]
    vs.addProperty("App::PropertyBool","CrankBoreEnabled","CrankBore","Enable crank bore").CrankBoreEnabled = True
    vs.addProperty("App::PropertyLength","WheelBoreDiameter","WheelBore","Wheel bore diameter").WheelBoreDiameter = H["bore_diameter"]
    vs.addProperty("App::PropertyBool","WheelBoreEnabled","WheelBore","Enable wheel bore").WheelBoreEnabled = True
    vs.addProperty("App::PropertyLength","WheelRadius","read only","Wheel radius",1)
    vs.addProperty("App::PropertyLength","CenterDistance","read only","Center distance",1)
    vs.addProperty("App::PropertyLength","SlotCenterWidth","read only","Slot center width",1)
    return vs


class GenevaWheelResult:
    def __init__(self, obj, varset):
        self._varset=varset; self._rebuilding=False
        self._last_ns=self._last_cr=self._last_pr=self._last_tol=self._last_h=None
        self._watcher=None; self._needs_rebuild=False; self.Type="GenevaWheelResult"
        obj.addProperty("App::PropertyString","VarSetName","Gear","",1).VarSetName=varset.Name
        obj.addProperty("App::PropertyString","CrankBodyName","GenevaWheel","").CrankBodyName=varset.Name.replace("_values","_Crank",1)
        obj.addProperty("App::PropertyString","WheelBodyName","GenevaWheel","").WheelBodyName=varset.Name.replace("_values","_Wheel",1)
        obj.addProperty("App::PropertyString","Version","read only","",1).Version=version
        obj.addProperty("App::PropertyString","Status","read only","",1)
        obj.Proxy=self; self.Object=obj; obj.Status="Not yet generated"
        self._startWatcher(varset.Name)
    def __getstate__(self): return self.Type
    def __setstate__(self,s):
        if s: self.Type=s
        self._varset=None; self._rebuilding=False
        self._last_ns=self._last_cr=self._last_pr=self._last_tol=self._last_h=None
        self._watcher=None; self._needs_rebuild=False
    def onDocumentRestored(self,obj):
        self.Object=obj; v=self._getVarSet()
        if v:
            self._last_ns=int(v.NumberOfSlots); self._last_cr=float(v.CrankRadius.Value)
            self._last_pr=float(v.PinRadius.Value); self._last_tol=float(v.Tolerance.Value)
            self._last_h=float(v.Height.Value)
            self._startWatcher(v.Name); obj.Status="Up to date"
    def _startWatcher(self,vn):
        self._stopWatcher(); self._watcher=_VarSetWatcher(self,vn,watched=frozenset((
            "NumberOfSlots","CrankRadius","PinRadius","Tolerance","Height",
            "CrankBoreEnabled","CrankBoreDiameter","WheelBoreEnabled","WheelBoreDiameter")))
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
        if not v or self._last_ns is None: return v is not None
        E=1e-9
        return (int(v.NumberOfSlots)!=self._last_ns or abs(float(v.CrankRadius.Value)-self._last_cr)>E or
                abs(float(v.PinRadius.Value)-self._last_pr)>E or abs(float(v.Tolerance.Value)-self._last_tol)>E or
                abs(float(v.Height.Value)-self._last_h)>E)
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
            vn=v.Name; d=self.Object.Document
            self._last_ns=int(v.NumberOfSlots); self._last_cr=float(v.CrankRadius.Value)
            self._last_pr=float(v.PinRadius.Value); self._last_tol=float(v.Tolerance.Value)
            self._last_h=float(v.Height.Value)
            if self._last_ns<3 or self._last_cr<=0 or self._last_h<=0:
                self.Object.Status="Invalid params"; return
            saved_placements={}
            for bn in [self.Object.CrankBodyName, self.Object.WheelBodyName]:
                self._stopWatcher()
                old=d.getObject(bn)
                if old:
                    saved_placements[bn]=App.Placement(old.Placement)
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
            generateGenevaWheelPart(d,{
                "num_slots":self._last_ns,"crank_radius":self._last_cr,"pin_radius":self._last_pr,
                "tolerance":self._last_tol,"height":self._last_h,
                "crank_body_name":str(self.Object.CrankBodyName),
                "wheel_body_name":str(self.Object.WheelBodyName),
            })
            for name, boren, borkey in [
                (str(self.Object.CrankBodyName),"CrankBoreEnabled","CrankBoreDiameter"),
                (str(self.Object.WheelBodyName),"WheelBoreEnabled","WheelBoreDiameter"),
            ]:
                bo=d.getObject(name)
                if bo:
                    sk=util.createSketch(bo,"Bore")
                    bd=float(getattr(v,borkey).Value)
                    ci=sk.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),bd/2),False)
                    sk.addConstraint(Sketcher.Constraint("Coincident",ci,3,-1,1))
                    cs=sk.addConstraint(Sketcher.Constraint("Diameter",ci,bd))
                    sk.setExpression(f"Constraints[{cs}]",f"<<{v.Name}>>.{borkey}")
                    pk=util.createPocket(bo,sk,100.0,"Bore"); pk.Reversed=True
                    pk.setExpression("Suppressed",f"<<{v.Name}>>.{boren} ? False : True")
                    bo.Tip=pk
            # Restore crank placement; position wheel relative to crank
            # using the NEW center distance (c changes when num_slots changes)
            crank_bn = str(self.Object.CrankBodyName)
            wheel_bn = str(self.Object.WheelBodyName)
            crank_body = d.getObject(crank_bn)
            wheel_body = d.getObject(wheel_bn)
            geo = calculateGenevaGeometry({
                "num_slots": self._last_ns, "crank_radius": self._last_cr,
                "pin_radius": self._last_pr, "tolerance": self._last_tol,
            })
            v.WheelRadius = geo["b"]
            v.CenterDistance = geo["c"]
            v.SlotCenterWidth = geo["s"]
            if crank_body and crank_bn in saved_placements:
                crank_body.Placement = saved_placements[crank_bn]
            if wheel_body:
                crank_pl = crank_body.Placement if crank_body else App.Placement()
                wheel_offset = App.Placement(App.Vector(-geo["c"], 0, 0), App.Rotation())
                wheel_body.Placement = crank_pl.multiply(wheel_offset)
            d.recompute()
            self.Object.Status="Up to date"
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
        except Exception as e:
            import traceback; App.Console.PrintError(traceback.format_exc())
            self.Object.Status="Error"
        finally:
            if vn: self._startWatcher(vn)
            self._rebuilding=False
    def force_Recompute(self): self._rebuild()


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================


class GenevaWheelCreateObject:
    """Command to create a new Geneva wheel mechanism."""

    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Geneva Wheel",
            "ToolTip": "Create parametric Geneva wheel (Maltese cross) mechanism.\n"
            "Converts continuous rotation to intermittent motion.\n"
            "Creates drive crank and Geneva wheel as separate bodies.",
        }

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        base = "GenevaWheel_values"; un = base; c = 1
        while doc.getObject(un): un = f"{base}{c:03d}"; c += 1
        vs = createGenevaWheelVarSet(doc, un)
        gn = "Regenerate"; c = 1
        while doc.getObject(gn): gn = f"Regenerate{c:03d}"; c += 1
        go = doc.addObject("Part::FeaturePython", gn)
        GenevaWheelResult(go, vs)
        ViewProviderGearResult(go.ViewObject, mainIcon)
        go.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


class GenevaWheel:
    """FeaturePython object for parametric Geneva wheel mechanism."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultGenevaParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Version"), 1,
        ).Version = version
        obj.addProperty(
            "App::PropertyLength", "WheelRadius", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Geneva wheel radius (b)"), 1,
        )
        obj.addProperty(
            "App::PropertyLength", "CenterDistance", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Distance between crank and wheel centers (c)"), 1,
        )
        obj.addProperty(
            "App::PropertyLength", "SlotCenterWidth", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Width of slot at center (s)"), 1,
        )

        # Editable parameters
        obj.addProperty(
            "App::PropertyInteger", "NumberOfSlots", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Number of slots (driven positions per revolution)"),
        ).NumberOfSlots = H["num_slots"]
        obj.addProperty(
            "App::PropertyLength", "CrankRadius", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Radius of the drive crank arm"),
        ).CrankRadius = H["crank_radius"]
        obj.addProperty(
            "App::PropertyLength", "PinRadius", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Radius of the drive pin"),
        ).PinRadius = H["pin_radius"]
        obj.addProperty(
            "App::PropertyLength", "Tolerance", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Clearance tolerance"),
        ).Tolerance = H["tolerance"]
        obj.addProperty(
            "App::PropertyLength", "Height", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Thickness of the mechanism"),
        ).Height = H["height"]

        # Body names
        obj.addProperty(
            "App::PropertyString", "CrankBodyName", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Name of the drive crank body"),
        ).CrankBodyName = H["crank_body_name"]
        obj.addProperty(
            "App::PropertyString", "WheelBodyName", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Name of the Geneva wheel body"),
        ).WheelBodyName = H["wheel_body_name"]

        # Crank bore
        obj.addProperty(
            "App::PropertyEnumeration", "CrankBoreType", "CrankBore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole for crank"),
        )
        obj.CrankBoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.CrankBoreType = H["bore_type"]
        obj.addProperty(
            "App::PropertyLength", "CrankBoreDiameter", "CrankBore",
            QT_TRANSLATE_NOOP("App::Property", "Bore diameter for crank"),
        ).CrankBoreDiameter = H["bore_diameter"]

        # Wheel bore
        obj.addProperty(
            "App::PropertyEnumeration", "WheelBoreType", "WheelBore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole for wheel"),
        )
        obj.WheelBoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.WheelBoreType = H["bore_type"]
        obj.addProperty(
            "App::PropertyLength", "WheelBoreDiameter", "WheelBore",
            QT_TRANSLATE_NOOP("App::Property", "Bore diameter for wheel"),
        ).WheelBoreDiameter = H["bore_diameter"]

        self.Type = "GenevaWheel"
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_crank_name = obj.CrankBodyName
        self.last_wheel_name = obj.WheelBodyName
        obj.Proxy = self

        self.onChanged(obj, "NumberOfSlots")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        self.Dirty = True

        if prop == "CrankBodyName":
            old_name = self.last_crank_name
            new_name = fp.CrankBodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    _removeBody(doc, old_name)
                self.last_crank_name = new_name

        if prop == "WheelBodyName":
            old_name = self.last_wheel_name
            new_name = fp.WheelBodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    _removeBody(doc, old_name)
                self.last_wheel_name = new_name

        # Update read-only calculated properties
        if prop in ["NumberOfSlots", "CrankRadius", "PinRadius", "Tolerance"]:
            try:
                n = fp.NumberOfSlots
                a = fp.CrankRadius.Value
                p = fp.PinRadius.Value
                t = fp.Tolerance.Value
                if n >= 3 and a > 0:
                    c = a / math.sin(math.pi / n)
                    b = math.sqrt(c**2 - a**2)
                    s = a + b - c
                    fp.WheelRadius = b
                    fp.CenterDistance = c
                    fp.SlotCenterWidth = s
            except (AttributeError, TypeError, ZeroDivisionError, ValueError):
                pass

    def GetParameters(self):
        return {
            "num_slots": int(self.Object.NumberOfSlots),
            "crank_radius": float(self.Object.CrankRadius.Value),
            "pin_radius": float(self.Object.PinRadius.Value),
            "tolerance": float(self.Object.Tolerance.Value),
            "height": float(self.Object.Height.Value),
            "crank_body_name": str(self.Object.CrankBodyName),
            "wheel_body_name": str(self.Object.WheelBodyName),
            "crank_bore_type": str(self.Object.CrankBoreType),
            "crank_bore_diameter": float(self.Object.CrankBoreDiameter.Value),
            "wheel_bore_type": str(self.Object.WheelBoreType),
            "wheel_bore_diameter": float(self.Object.WheelBoreDiameter.Value),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                doc = App.ActiveDocument
                params = self.GetParameters()
                crank_bn = params["crank_body_name"]
                # Save crank placement before rebuild
                old_crank = doc.getObject(crank_bn)
                saved_crank_pl = App.Placement(old_crank.Placement) if old_crank else None

                generateGenevaWheelPart(doc, params)
                self.Dirty = False

                # Restore crank; position wheel relative to crank with new c
                crank_body = doc.getObject(crank_bn)
                wheel_body = doc.getObject(params["wheel_body_name"])
                if crank_body and saved_crank_pl:
                    crank_body.Placement = saved_crank_pl
                if wheel_body:
                    crank_pl = crank_body.Placement if crank_body else App.Placement()
                    geo = calculateGenevaGeometry(params)
                    wheel_offset = App.Placement(App.Vector(-geo["c"], 0, 0), App.Rotation())
                    wheel_body.Placement = crank_pl.multiply(wheel_offset)

                doc.recompute()
            except Exception as e:
                App.Console.PrintError(f"Geneva Wheel Error: {e}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)


class ViewProviderGenevaWheel:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.iconfile = iconfile if iconfile else mainIcon

    def attach(self, obj):
        self.ViewObject = obj
        self.Object = obj.Object

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
        return True

    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui
        action = QtGui.QAction("Regenerate Geneva Wheel", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        if hasattr(self.Object, "Proxy"):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        return self.iconfile

    def __setstate__(self, state):
        self.iconfile = state if state else mainIcon


try:
    FreeCADGui.addCommand("GenevaWheelCreateObject", GenevaWheelCreateObject())
except Exception:
    pass
