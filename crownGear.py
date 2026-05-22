"""Crown Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric crown gears (face gears).

Copyright 2025, Chris Bruner
Version v0.2
License LGPL V2.1
"""

"""Crown Gear generator for FreeCAD
"""
import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher
import os
import math
import genericCrown
from genericGear import _VarSetWatcher, ViewProviderGearResult
from PySide import QtCore

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "crownGear.svg")


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================


def validateCrownParameters(parameters):
    # Crown gear doesn't use pitch_angle, so we just check module/teeth
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["face_width"] <= 0:
        raise gearMath.GearParameterError("Face width must be positive")


def generateCrownGearPart(doc, parameters):
    """Generate crown gear using the generic crown system.

    Crown gears are disk-shaped gears with rack-like teeth radiating from center.
    They mesh with spur gears at 90-degree angles.
    """
    validateCrownParameters(parameters)

    # Use the generic crown builder with rack tooth profile
    result = genericCrown.crownGear(
        doc, parameters, profile_func=gearMath.generateRackToothProfile
    )

    return result


def createCrownGearVarSet(doc, name):
    """Create a VarSet for CrownGear parameters."""
    var_set = doc.addObject("App::VarSet", name)

    var_set.addProperty(
        "App::PropertyString", "Version", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
    ).Version = "0.2"

    var_set.addProperty(
        "App::PropertyInteger", "NumberOfTeeth", "CrownGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
    ).NumberOfTeeth = 30

    var_set.addProperty(
        "App::PropertyLength", "Module", "CrownGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
    ).Module = 1.0

    var_set.addProperty(
        "App::PropertyAngle", "PressureAngle", "CrownGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = 20.0

    var_set.addProperty(
        "App::PropertyAngle", "SpiralAngle", "CrownGear",
        QT_TRANSLATE_NOOP("App::Property", "Spiral angle (0 for straight)"),
    ).SpiralAngle = 0.0

    var_set.addProperty(
        "App::PropertyLength", "FaceWidth", "CrownGear",
        QT_TRANSLATE_NOOP("App::Property", "Face width"),
    ).FaceWidth = 5.0

    var_set.addProperty(
        "App::PropertyLength", "BoreDiameter", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
    ).BoreDiameter = 5.0

    var_set.addProperty(
        "App::PropertyLength", "KeywayWidth", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
    ).KeywayWidth = 2.0

    var_set.addProperty(
        "App::PropertyLength", "KeywayDepth", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
    ).KeywayDepth = 1.0

    var_set.addProperty(
        "App::PropertyBool", "BoreEnabled", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable bore hole"),
    ).BoreEnabled = True

    var_set.addProperty(
        "App::PropertyBool", "KeywayEnabled", "Bore",
        QT_TRANSLATE_NOOP("App::Property", "Enable keyway in bore"),
    ).KeywayEnabled = False

    var_set.addProperty(
        "App::PropertyLength", "PitchDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter"), 1,
    )
    var_set.setExpression("PitchDiameter", "Module * NumberOfTeeth")

    return var_set


class CrownGearResult:
    """FeaturePython for auto-regeneration of crown gear."""

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_nt = None
        self._last_pa = None
        self._last_sa = None
        self._last_fw = None
        self._watcher = None
        self._needs_rebuild = False
        self.Type = "CrownGearResult"

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
        ).Version = "0.2"

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
        self._last_m = self._last_nt = self._last_pa = None
        self._last_sa = self._last_fw = None
        self._watcher = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_sa = float(v.SpiralAngle.Value)
            self._last_fw = float(v.FaceWidth.Value)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "NumberOfTeeth", "PressureAngle",
                               "SpiralAngle", "FaceWidth")),
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
                abs(float(v.SpiralAngle.Value) - self._last_sa) > EPS or
                abs(float(v.FaceWidth.Value) - self._last_fw) > EPS)

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        if not self._values_changed():
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
            self._last_pa = float(v.PressureAngle.Value)
            self._last_sa = float(v.SpiralAngle.Value)
            self._last_fw = float(v.FaceWidth.Value)

            if self._last_m <= 0 or self._last_nt < 3 or self._last_fw <= 0:
                self.Object.Status = "Invalid params"
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            self._stopWatcher()

            old = doc.getObject(body_name)
            saved_placement = None
            if old:
                saved_placement = App.Placement(old.Placement)
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

            self.Object.Status = "Generating gear geometry..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            parameters = {
                "module": self._last_m,
                "num_teeth": self._last_nt,
                "pressure_angle": self._last_pa,
                "spiral_angle": self._last_sa,
                "face_width": self._last_fw,
                "bore_type": "none",
                "bore_diameter": float(v.BoreDiameter.Value),
                "keyway_width": float(v.KeywayWidth.Value),
                "keyway_depth": float(v.KeywayDepth.Value),
                "body_name": body_name,
            }
            genericCrown.crownGear(doc, parameters,
                                   gearMath.generateRackToothProfile)

            body_out = doc.getObject(body_name)
            if not body_out:
                return

            # Create bore and keyway at the center of the crown disk
            bore_sk = util.createSketch(body_out, "Bore")
            bore_circle = bore_sk.addGeometry(
                Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1),
                            float(v.BoreDiameter.Value) / 2.0),
                False)
            bore_sk.addConstraint(Sketcher.Constraint("Coincident", bore_circle, 3, -1, 1))
            cst = bore_sk.addConstraint(
                Sketcher.Constraint("Diameter", bore_circle, float(v.BoreDiameter.Value)))
            bore_sk.setExpression(f"Constraints[{cst}]", f"<<{v.Name}>>.BoreDiameter")
            bore_pocket = util.createPocket(body_out, bore_sk, 100.0, "Bore")
            bore_pocket.setExpression("Length", "100mm")
            bore_pocket.setExpression("Suppressed", f"<<{v.Name}>>.BoreEnabled ? False : True")

            tiny = 0.01
            kw_sk = util.createSketch(body_out, "Keyway")
            pts = [App.Vector(-0.5, -0.5, 0), App.Vector(0.5, -0.5, 0),
                   App.Vector(0.5, 0.5, 0), App.Vector(-0.5, 0.5, 0)]
            kw_lines = []
            for i in range(4):
                kw_lines.append(kw_sk.addGeometry(
                    Part.LineSegment(pts[i], pts[(i + 1) % 4]), False))
            for i in range(4):
                kw_sk.addConstraint(Sketcher.Constraint("Coincident",
                    kw_lines[i], 2, kw_lines[(i + 1) % 4], 1))
            kw_sk.addConstraint(Sketcher.Constraint("Horizontal", kw_lines[0]))
            kw_sk.addConstraint(Sketcher.Constraint("Vertical", kw_lines[1]))
            kw_sk.addConstraint(Sketcher.Constraint("Horizontal", kw_lines[2]))
            kw_sk.addConstraint(Sketcher.Constraint("Vertical", kw_lines[3]))
            cst = kw_sk.addConstraint(Sketcher.Constraint("DistanceX",
                kw_lines[0], 1, -1, 1, -tiny))
            kw_sk.setExpression(f"Constraints[{cst}]", f"<<{v.Name}>>.KeywayWidth / -2.0")
            cst = kw_sk.addConstraint(Sketcher.Constraint("DistanceY",
                kw_lines[0], 1, -1, 1, -tiny))
            kw_sk.setExpression(f"Constraints[{cst}]",
                f"<<{v.Name}>>.BoreDiameter / 2.0 - <<{v.Name}>>.KeywayDepth")
            cst = kw_sk.addConstraint(Sketcher.Constraint("DistanceX",
                kw_lines[0], 2, -1, 1, tiny))
            kw_sk.setExpression(f"Constraints[{cst}]", f"<<{v.Name}>>.KeywayWidth / 2.0")
            cst = kw_sk.addConstraint(Sketcher.Constraint("DistanceY",
                kw_lines[1], 2, -1, 1, tiny))
            kw_sk.setExpression(f"Constraints[{cst}]",
                f"<<{v.Name}>>.BoreDiameter / 2.0 + <<{v.Name}>>.KeywayDepth")

            kw_pocket = util.createPocket(body_out, kw_sk, 100.0, "Keyway")
            kw_pocket.setExpression("Suppressed", f"<<{v.Name}>>.KeywayEnabled ? False : True")
            body_out.Tip = kw_pocket
            if saved_placement:
                body_out.Placement = saved_placement
            doc.recompute()

            self.Object.Status = "Up to date"
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()
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


class CrownGearCreateObject:
    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Crown Gear",
            "ToolTip": "Create parametric crown gear",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "CrownGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"CrownGear_values{count:03d}"
            count += 1

        varset = createCrownGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        CrownGearResult(gear_obj, varset)
        ViewProviderGearResult(
            gear_obj.ViewObject, mainIcon,
        )

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")

    def IsActive(self):
        return True


class CrownGear:
    def __init__(self, obj):
        self.Dirty = False
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Version"),
            1,
        ).Version = "0.2"
        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "CrownGear",
            QT_TRANSLATE_NOOP("App::Property", "Module"),
        ).Module = 1.0
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "CrownGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = 30
        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "CrownGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle"),
        ).PressureAngle = 20.0
        obj.addProperty(
            "App::PropertyAngle",
            "SpiralAngle",
            "CrownGear",
            QT_TRANSLATE_NOOP("App::Property", "Spiral angle (0 for straight)"),
        ).SpiralAngle = 0.0
        obj.addProperty(
            "App::PropertyLength",
            "FaceWidth",
            "CrownGear",
            QT_TRANSLATE_NOOP("App::Property", "Face Width"),
        ).FaceWidth = 5.0
        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "CrownGear",
            QT_TRANSLATE_NOOP("App::Property", "Body Name"),
        ).BodyName = "CrownGear"

        obj.addProperty(
            "App::PropertyEnumeration",
            "BoreType",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole"),
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.addProperty(
            "App::PropertyLength",
            "BoreDiameter",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Bore diameter"),
        ).BoreDiameter = 5.0
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

        self.Type = "CrownGear"
        self.Object = obj
        self.last_body_name = obj.BodyName
        obj.Proxy = self
        self.onChanged(obj, "Module")

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
        if prop in ["Module", "NumberOfTeeth"]:
            try:
                m = fp.Module.Value
                z = fp.NumberOfTeeth
                fp.PitchDiameter = m * z
            except:
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "spiral_angle": float(self.Object.SpiralAngle.Value),
            "face_width": float(self.Object.FaceWidth.Value),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                generateCrownGearPart(App.ActiveDocument, self.GetParameters())
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Crown Error: {e}\n")

    def execute(self, obj):
        import PySide.QtCore as QtCore

        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderCrownGear:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.iconfile = iconfile if iconfile else mainIcon

    def attach(self, obj):
        self.Object = obj.Object

    def getDisplayModes(self, obj):
        return ["Shaded", "Wireframe"]

    def getDefaultDisplayMode(self):
        return "Shaded"

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
    FreeCADGui.addCommand("CrownGearCreateObject", CrownGearCreateObject())
except Exception:
    pass
