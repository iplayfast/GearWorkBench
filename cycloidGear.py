"""Cycloid Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric cycloidal gears (clock/watch standard).

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
import os
import math
from PySide import QtCore
import genericGear
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "cycloidGear.svg")

if not os.path.exists(mainIcon):
    App.Console.PrintWarning(f"Cycloid Gear icon not found at: {mainIcon}\n")

version = "Nov 30, 2025"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================


def validateCycloidParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < 3:
        raise gearMath.GearParameterError("Teeth must be >= 3")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")


def generateCycloidToothProfile(sketch, parameters):
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    addendum = module * parameters["addendum_factor"]
    dedendum = module * parameters["dedendum_factor"]

    R = (module * num_teeth) / 2.0
    Ra = R + addendum
    Rf = R - dedendum
    r_roll = 2.5 * module
    half_tooth_angle = math.pi / (2.0 * num_teeth)

    def get_epi_point(t):
        cx = (R + r_roll) * math.cos(t) - r_roll * math.cos((R + r_roll) / r_roll * t)
        cy = (R + r_roll) * math.sin(t) - r_roll * math.sin((R + r_roll) / r_roll * t)
        return cx, cy

    def get_hypo_point(t):
        cx = (R - r_roll) * math.cos(t) + r_roll * math.cos((R - r_roll) / r_roll * t)
        cy = -(
            (R - r_roll) * math.sin(t) - r_roll * math.sin((R - r_roll) / r_roll * t)
        )
        return cx, cy

    # 1. Epicycloid (Tip)
    epi_pts = []
    steps = 50
    step_size = 0.5 / steps

    for i in range(steps + 1):
        t = i * step_size
        cx, cy = get_epi_point(t)
        r_cur = math.sqrt(cx * cx + cy * cy)

        if r_cur > Ra:
            # Refine t to hit Ra exactly
            t_low = (i - 1) * step_size
            t_high = t
            for _ in range(10):  # Binary search
                t_mid = (t_low + t_high) / 2.0
                mx, my = get_epi_point(t_mid)
                mr = math.sqrt(mx * mx + my * my)
                if mr > Ra:
                    t_high = t_mid
                else:
                    t_low = t_mid
            cx, cy = get_epi_point(t_low)  # Use lower bound to be safe/close
            epi_pts.append(App.Vector(cx, cy, 0))
            break

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
        t = i * step_size
        cx, cy = get_hypo_point(t)
        r_cur = math.sqrt(cx * cx + cy * cy)

        if r_cur < Rf:
            # Refine t to hit Rf exactly
            t_low = (i - 1) * step_size
            t_high = t
            for _ in range(10):
                t_mid = (t_low + t_high) / 2.0
                mx, my = get_hypo_point(t_mid)
                mr = math.sqrt(mx * mx + my * my)
                if mr < Rf:
                    t_high = t_mid  # Too deep
                else:
                    t_low = t_mid
            cx, cy = get_hypo_point(t_low)
            hypo_pts.append(App.Vector(cx, cy, 0))
            break

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
    """Generate cycloid gear using the generic gear system.

    Cycloid gears are always spur gears (angle1=0, angle2=0) since they
    don't support helical or herringbone configurations.
    """
    validateCycloidParameters(parameters)

    # Cycloid gears are spur gears (no helix)
    angle1 = 0.0
    angle2 = 0.0

    # Use the generic herringbone gear builder with cycloid profile
    result = genericGear.herringboneGear(
        doc, parameters, angle1, angle2, profile_func=generateCycloidToothProfile
    )

    return result


def createCycloidGearVarSet(doc, name):
    """Create a VarSet for CycloidGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultCycloidParameters()

    var_set.addProperty(
        "App::PropertyString", "Version", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
    ).Version = version

    var_set.addProperty(
        "App::PropertyInteger", "NumberOfTeeth", "CycloidGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength", "Module", "CycloidGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyLength", "Height", "CycloidGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyFloat", "AddendumFactor", "CycloidGear",
        QT_TRANSLATE_NOOP("App::Property", "Head height factor (standard ~1.4)"),
    ).AddendumFactor = H["addendum_factor"]

    var_set.addProperty(
        "App::PropertyFloat", "DedendumFactor", "CycloidGear",
        QT_TRANSLATE_NOOP("App::Property", "Root depth factor (standard ~1.6)"),
    ).DedendumFactor = H["dedendum_factor"]

    var_set.addProperty(
        "App::PropertyLength", "BoreDiameter", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
    ).BoreDiameter = H["bore_diameter"]

    var_set.addProperty(
        "App::PropertyLength", "PitchDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter"), 1,
    )
    var_set.setExpression("PitchDiameter", "Module * NumberOfTeeth")

    var_set.addProperty(
        "App::PropertyLength", "OuterDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Tip diameter"), 1,
    )
    var_set.setExpression("OuterDiameter",
        "PitchDiameter + 2 * Module * AddendumFactor")

    var_set.addProperty(
        "App::PropertyLength", "RootDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Root diameter"), 1,
    )
    var_set.setExpression("RootDiameter",
        "PitchDiameter - 2 * Module * DedendumFactor")

    return var_set


class CycloidGearResult:
    """FeaturePython for auto-regeneration of cycloid gear."""

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_nt = None
        self._last_af = None
        self._last_df = None
        self._watcher = None
        self._needs_rebuild = False
        self.Type = "CycloidGearResult"

        obj.addProperty(
            "App::PropertyString", "VarSetName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"), 1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString", "BodyName", "Gear",
            QT_TRANSLATE_NOOP("App::Property", "Name of generated body"),
        ).BodyName = varset.Name.replace("_values", "_Body", 1)

        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
        ).Version = version

        obj.addProperty(
            "App::PropertyString", "Status", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"), 1,
        )

        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state
        self._varset = None
        self._rebuilding = False
        self._last_m = self._last_nt = self._last_af = self._last_df = None
        self._watcher = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_af = float(v.AddendumFactor)
            self._last_df = float(v.DedendumFactor)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth",
                               "AddendumFactor", "DedendumFactor")),
        )
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try:
                App.removeDocumentObserver(self._watcher)
            except Exception:
                pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is None:
            try:
                name = self.Object.VarSetName
                self._varset = self.Object.Document.getObject(name)
            except AttributeError:
                pass
        return self._varset

    def execute(self, obj):
        pass

    def _values_changed(self):
        v = self._getVarSet()
        if not v:
            return False
        if self._last_m is None:
            return True
        EPS = 1e-9
        return (abs(float(v.Module.Value) - self._last_m) > EPS or
                int(v.NumberOfTeeth) != self._last_nt or
                abs(float(v.AddendumFactor) - self._last_af) > EPS or
                abs(float(v.DedendumFactor) - self._last_df) > EPS)

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        if not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Needs regeneration"
        except Exception:
            pass

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed():
            return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding = True
        varset_name = None
        try:
            v = self._getVarSet()
            if not v:
                return
            varset_name = v.Name
            self._last_m = float(v.Module.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_af = float(v.AddendumFactor)
            self._last_df = float(v.DedendumFactor)

            if self._last_m <= 0 or self._last_nt < 3:
                self.Object.Status = "Invalid params"
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            self._stopWatcher()

            old = doc.getObject(body_name)
            if old:
                children = list(old.Group)
                for child in children:
                    for prop in child.PropertiesList:
                        try:
                            child.setExpression(prop, None)
                        except Exception:
                            pass
                for child in reversed(children):
                    try:
                        doc.removeObject(child.Name)
                    except Exception:
                        pass
                doc.removeObject(body_name)

            parameters = {
                "module": self._last_m,
                "num_teeth": self._last_nt,
                "height": float(v.Height.Value),
                "addendum_factor": self._last_af,
                "dedendum_factor": self._last_df,
                "body_name": body_name,
                "bore_type": "none",
                "bore_diameter": float(v.BoreDiameter.Value),
            }
            genericGear.herringboneGear(doc, parameters, 0.0, 0.0,
                                        generateCycloidToothProfile)
            self.Object.Status = "Up to date"
        except Exception as e:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            try:
                partial = doc.getObject(body_name)
                if partial:
                    for child in list(partial.Group):
                        try:
                            doc.removeObject(child.Name)
                        except Exception:
                            pass
                    doc.removeObject(body_name)
            except Exception:
                pass
            self.Object.Status = "Error"
        finally:
            if varset_name:
                self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self):
        self._rebuild()


class CycloidGearCreateObject:
    """Command to create a new cycloid gear object."""

    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Cycloid Gear",
            "ToolTip": "Create parametric cycloidal gear.\nUse Case: Clocks, watches, and low-friction mechanisms.\nNOT for high-torque power transmission.",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "CycloidGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"CycloidGear_values{count:03d}"
            count += 1

        varset = createCycloidGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        CycloidGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject, mainIcon,
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


class CycloidGear:
    """FeaturePython object for parametric cycloid gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultCycloidParameters()

        # Read-only
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Version"),
            1,
        ).Version = version
        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter"),
            1,
        )
        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Tip diameter"),
            1,
        )
        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter"),
            1,
        )

        # Parameters
        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "CycloidGear",
            QT_TRANSLATE_NOOP("App::Property", "Module"),
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "CycloidGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "CycloidGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness"),
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyFloat",
            "AddendumFactor",
            "CycloidGear",
            QT_TRANSLATE_NOOP("App::Property", "Head height factor (standard ~1.4)"),
        ).AddendumFactor = H["addendum_factor"]
        obj.addProperty(
            "App::PropertyFloat",
            "DedendumFactor",
            "CycloidGear",
            QT_TRANSLATE_NOOP("App::Property", "Root depth factor (standard ~1.6)"),
        ).DedendumFactor = H["dedendum_factor"]

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "CycloidGear",
            QT_TRANSLATE_NOOP("App::Property", "Body Name"),
        ).BodyName = H["body_name"]

        # Bore
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
            QT_TRANSLATE_NOOP("App::Property", "Bore diameter"),
        ).BoreDiameter = H["bore_diameter"]

        self.Type = "CycloidGear"
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_body_name = obj.BodyName
        obj.Proxy = self

        self.onChanged(obj, "Module")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        self.Dirty = True
        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        if hasattr(old_body, "removeObjectsFromDocument"):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
                self.last_body_name = new_name
        if prop in ["Module", "NumberOfTeeth", "AddendumFactor", "DedendumFactor"]:
            try:
                m = fp.Module.Value
                z = fp.NumberOfTeeth
                ha = fp.AddendumFactor
                hf = fp.DedendumFactor

                fp.PitchDiameter = m * z
                fp.OuterDiameter = m * z + 2 * (m * ha)
                fp.RootDiameter = m * z - 2 * (m * hf)
            except:
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "height": float(self.Object.Height.Value),
            "addendum_factor": float(self.Object.AddendumFactor),
            "dedendum_factor": float(self.Object.DedendumFactor),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                generateCycloidGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
                # App.Console.PrintMessage("Cycloid gear generated successfully\n")
            except Exception as e:
                App.Console.PrintError(f"Cycloid Gear Error: {str(e)}\n")
                import traceback

                App.Console.PrintError(traceback.format_exc())

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)


class ViewProviderCycloidGear:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.part = obj
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

        action = QtGui.QAction("Regenerate Gear", menu)
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
    FreeCADGui.addCommand("CycloidGearCreateObject", CycloidGearCreateObject())
except Exception:
    pass
