"""Rack Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric gear racks.

Copyright 2025, Chris Bruner
Version v0.1.4
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
import genericRack
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "rackGear.svg")

# Debug: print icon path
# App.Console.PrintMessage(f"Rack Gear icon path: {mainIcon}\n")
if not os.path.exists(mainIcon):
    App.Console.PrintWarning(f"Rack Gear icon not found at: {mainIcon}\n")

version = "Nov 30, 2025"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================


def validateRackParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < 1:
        raise gearMath.GearParameterError("Teeth must be >= 1")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")
    if parameters["base_thickness"] <= 0:
        raise gearMath.GearParameterError("Base thickness must be positive")


def generateRackToothProfile(sketch, parameters):
    module = parameters["module"]
    pressure_angle = parameters["pressure_angle"]

    addendum = module * gearMath.ADDENDUM_FACTOR
    dedendum = module * gearMath.DEDENDUM_FACTOR
    tan_alpha = math.tan(pressure_angle * util.DEG_TO_RAD)
    half_pitch_width = (math.pi * module) / 4.0

    y_top = -addendum
    x_top = half_pitch_width - (addendum * tan_alpha)
    y_bot = dedendum
    x_bot = half_pitch_width + (dedendum * tan_alpha)

    p_tl = App.Vector(-x_top, y_top, 0)
    p_tr = App.Vector(x_top, y_top, 0)
    p_br = App.Vector(x_bot, y_bot, 0)
    p_bl = App.Vector(-x_bot, y_bot, 0)

    points = [p_tl, p_tr, p_br, p_bl, p_tl]
    for i in range(4):
        line = Part.LineSegment(points[i], points[i + 1])
        idx = sketch.addGeometry(line, False)
        sketch.addConstraint(Sketcher.Constraint("Block", idx))
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))


def generateRackPart(doc, parameters):
    """Generate standard involute rack using the generic rack system.

    Standard racks use involute tooth profiles with pressure angle.
    """
    validateRackParameters(parameters)

    # Use the generic rack builder with involute profile
    result = genericRack.rackGear(
        doc, parameters, profile_func=generateRackToothProfile
    )

    return result


def createRackGearVarSet(doc, name):
    """Create a VarSet for RackGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultRackParameters()

    var_set.addProperty(
        "App::PropertyString", "Version", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
    ).Version = version

    var_set.addProperty(
        "App::PropertyEnumeration", "GearType", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear style (reserved, only spur currently)"),
    )
    var_set.GearType = ["Spur", "Helix", "Herringbone"]
    var_set.GearType = "Spur"

    var_set.addProperty(
        "App::PropertyEnumeration", "ToothProfile", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Tooth profile style"),
    )
    var_set.ToothProfile = ["Involute", "Cycloidal"]
    var_set.ToothProfile = "Involute"

    var_set.addProperty(
        "App::PropertyInteger", "NumberOfTeeth", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = H["num_teeth"]

    var_set.addProperty(
        "App::PropertyLength", "Module", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = H["module"]

    var_set.addProperty(
        "App::PropertyAngle", "PressureAngle", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = H["pressure_angle"]

    var_set.addProperty(
        "App::PropertyLength", "Height", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear face width (extrusion height)"),
    ).Height = H["height"]

    var_set.addProperty(
        "App::PropertyLength", "BaseThickness", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Thickness of base below roots"),
    ).BaseThickness = H["base_thickness"]

    var_set.addProperty(
        "App::PropertyAngle", "Angle1", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Helix angle (reserved for future)"),
    ).Angle1 = 0.0

    var_set.addProperty(
        "App::PropertyAngle", "Angle2", "RackGear",
        QT_TRANSLATE_NOOP("App::Property", "Second helix angle (reserved for future)"),
    ).Angle2 = 0.0

    var_set.addProperty(
        "App::PropertyFloat", "AddendumFactor", "CycloidalGear",
        QT_TRANSLATE_NOOP("App::Property", "Head height factor (~1.4 for cycloidal)"),
    ).AddendumFactor = 1.4

    var_set.addProperty(
        "App::PropertyFloat", "DedendumFactor", "CycloidalGear",
        QT_TRANSLATE_NOOP("App::Property", "Root depth factor (~1.6 for cycloidal)"),
    ).DedendumFactor = 1.6

    var_set.addProperty(
        "App::PropertyLength", "TotalLength", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Total length (Pitch * Teeth)"), 1,
    )
    var_set.setExpression("TotalLength", "Module * pi * NumberOfTeeth")

    return var_set


class RackGearResult:
    """FeaturePython for auto-regeneration of rack gear."""

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_nt = None
        self._last_pa = None
        self._last_h = None
        self._last_bt = None
        self._last_gt = None
        self._last_tp = None
        self._last_a1 = None
        self._last_a2 = None
        self._last_af = None
        self._last_df = None
        self._gt_changed = False
        self._tp_changed = False
        self._watcher = None
        self._needs_rebuild = False
        self.Type = "RackGearResult"

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

    def _apply_defaults(self, vs):
        gt = str(vs.GearType)
        if gt == "Spur":
            vs.Angle1 = 0.0
            vs.Angle2 = 0.0
        elif gt == "Helix":
            vs.Angle1 = 15.0
            vs.Angle2 = 15.0
        elif gt == "Herringbone":
            vs.Angle1 = 15.0
            vs.Angle2 = -15.0

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state
        self._varset = None
        self._rebuilding = False
        self._last_m = self._last_nt = self._last_pa = None
        self._last_h = self._last_bt = None
        self._last_gt = self._last_tp = self._last_a1 = self._last_a2 = None
        self._last_af = self._last_df = None
        self._gt_changed = self._tp_changed = False
        self._watcher = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_h = float(v.Height.Value)
            self._last_bt = float(v.BaseThickness.Value)
            self._last_gt = str(v.GearType)
            self._last_tp = str(v.ToothProfile)
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            if hasattr(v, "AddendumFactor"):
                self._last_af = float(v.AddendumFactor)
                self._last_df = float(v.DedendumFactor)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle",
                               "Height", "BaseThickness", "GearType",
                               "ToothProfile", "Angle1", "Angle2",
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
                abs(float(v.PressureAngle.Value) - self._last_pa) > EPS or
                abs(float(v.Height.Value) - self._last_h) > EPS or
                abs(float(v.BaseThickness.Value) - self._last_bt) > EPS or
                str(v.GearType) != self._last_gt or
                str(v.ToothProfile) != self._last_tp or
                abs(float(v.Angle1.Value) - self._last_a1) > EPS or
                abs(float(v.Angle2.Value) - self._last_a2) > EPS or
                (hasattr(v, "AddendumFactor") and
                 (abs(float(v.AddendumFactor) - self._last_af) > EPS or
                  abs(float(v.DedendumFactor) - self._last_df) > EPS)))

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        v = self._getVarSet()
        if not v:
            return
        changed = False
        gt = str(v.GearType)
        if gt != self._last_gt:
            self._last_gt = gt
            self._gt_changed = True
            self._apply_defaults(v)
            changed = True
        tp = str(v.ToothProfile)
        if tp != self._last_tp:
            self._last_tp = tp
            self._tp_changed = True
            changed = True
        if not changed and not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Regenerating..."
        except Exception:
            pass
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding:
            return
        if not self._gt_changed and not self._tp_changed and not self._values_changed():
            return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding = True
        self._gt_changed = False
        self._tp_changed = False
        varset_name = None
        try:
            v = self._getVarSet()
            if not v:
                return
            varset_name = v.Name
            self._last_m = float(v.Module.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_h = float(v.Height.Value)
            self._last_bt = float(v.BaseThickness.Value)
            self._last_gt = str(v.GearType)
            self._last_tp = str(v.ToothProfile)
            self._last_a1 = float(v.Angle1.Value)
            self._last_a2 = float(v.Angle2.Value)
            if hasattr(v, "AddendumFactor"):
                self._last_af = float(v.AddendumFactor)
                self._last_df = float(v.DedendumFactor)

            if self._last_m <= 0 or self._last_nt < 1 or self._last_bt <= 0:
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

            is_cycloid = self._last_tp == "Cycloidal"
            profile_func = generateRackToothProfile
            if is_cycloid:
                import cycloidRack as _cr
                profile_func = _cr.generateCycloidRackToothProfile

            parameters = {
                "module": self._last_m,
                "num_teeth": self._last_nt,
                "pressure_angle": self._last_pa,
                "height": self._last_h,
                "base_thickness": self._last_bt,
                "angle1": self._last_a1,
                "angle2": self._last_a2,
                "body_name": body_name,
                "varset_name": v.Name,
            }
            if is_cycloid:
                parameters["addendum_factor"] = self._last_af
                parameters["dedendum_factor"] = self._last_df
            genericRack.rackGear(doc, parameters, profile_func)
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


class RackGearCreateObject:
    """Command to create a new rack gear object."""

    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Gear Rack",
            "ToolTip": "Create parametric gear rack",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "RackGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"RackGear_values{count:03d}"
            count += 1

        varset = createRackGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        RackGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject, mainIcon,
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        return True


class RackGear:
    """FeaturePython object for parametric rack gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultRackParameters()

        # Read-only Info
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Version"),
            1,
        ).Version = version

        # Main Parameters (Note: TotalLength is now in 'RackGear' group so it's editable)
        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "RackGear",
            QT_TRANSLATE_NOOP("App::Property", "Module"),
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "RackGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyLength",
            "TotalLength",
            "RackGear",
            QT_TRANSLATE_NOOP("App::Property", "Total length (Pitch * Teeth)"),
        ).TotalLength = 0.0

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "RackGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle"),
        ).PressureAngle = H["pressure_angle"]
        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "RackGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear face width (extrusion height)"),
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyLength",
            "BaseThickness",
            "RackGear",
            QT_TRANSLATE_NOOP("App::Property", "Thickness of base below roots"),
        ).BaseThickness = H["base_thickness"]
        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "RackGear",
            QT_TRANSLATE_NOOP("App::Property", "Body Name"),
        ).BodyName = H["body_name"]

        self.Type = "RackGear"
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_body_name = obj.BodyName
        obj.Proxy = self

        # Trigger initial calculation
        self.onChanged(obj, "Module")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """
        Bidirectional calculation:
        - If Teeth or Module changes -> Update Length
        - If Length changes -> Update Teeth (rounded to nearest int)
        """
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

        # Ensure properties exist before accessing them
        if not all(hasattr(fp, p) for p in ["Module", "NumberOfTeeth", "TotalLength"]):
            return

        try:
            pitch = math.pi * fp.Module.Value
            if pitch <= 0:
                return

            if prop == "TotalLength":
                # User changed Length -> Calculate Teeth
                # Round to nearest integer (cannot have 10.5 teeth)
                new_teeth = int(round(fp.TotalLength.Value / pitch))
                if new_teeth < 1:
                    new_teeth = 1

                # Update Teeth only if changed (prevents infinite loop)
                if fp.NumberOfTeeth != new_teeth:
                    fp.NumberOfTeeth = new_teeth
                    # Note: Setting NumberOfTeeth will recursively trigger onChanged("NumberOfTeeth")
                    # which will snap the Length to the exact pitch multiple.

            elif prop in ["Module", "NumberOfTeeth"]:
                # User changed Teeth or Module -> Calculate Exact Length
                new_length = pitch * fp.NumberOfTeeth

                # Update Length only if changed (float comparison)
                if abs(fp.TotalLength.Value - new_length) > 0.000001:
                    fp.TotalLength = new_length

        except Exception as e:
            App.Console.PrintWarning(f"RackGear onChanged error: {e}\n")

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "height": float(self.Object.Height.Value),
            "base_thickness": float(self.Object.BaseThickness.Value),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                generateRackPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
                # App.Console.PrintMessage("Rack gear generated successfully\n")
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Rack Gear Error: {str(e)}\n")

    def execute(self, obj):
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderRackGear:
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

        action = QtGui.QAction("Regenerate Rack", menu)
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
    FreeCADGui.addCommand("RackGearCreateObject", RackGearCreateObject())
except Exception:
    pass
