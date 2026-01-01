"""Bevel Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric bevel gears.

Copyright 2025, Chris Bruner
Version v0.2
License LGPL V2.1
"""
"""Bevel Gear generator for FreeCAD
"""
import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher
import os
import math
import genericBevel

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'bevelGear.svg') 

def QT_TRANSLATE_NOOP(scope, text): return text

# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================

def validateBevelParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH: raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["face_width"] <= 0: raise gearMath.GearParameterError("Face width must be positive")
    if parameters["pitch_angle"] <= 0 or parameters["pitch_angle"] > 90:
        raise gearMath.GearParameterError("Pitch angle must be between 0 and 90 degrees")

def generateBevelGearPart(doc, parameters):
    """Generate bevel gear using the generic bevel system.

    Bevel gears use lofted tooth profiles that taper from outer to inner radius.
    Supports straight and spiral bevel configurations.
    """
    validateBevelParameters(parameters)

    # Use the generic bevel builder with involute tooth profile
    result = genericBevel.genericBevelGear(
        doc,
        parameters,
        profile_func=gearMath.generateToothProfile
    )

    return result

class BevelGearCreateObject():
    def GetResources(self):
        return {'Pixmap': mainIcon, 'MenuText': "&Create Bevel Gear", 'ToolTip': "Create parametric bevel gear"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        
        base_name = "BevelGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "BevelGearParameters")
        gear = BevelGear(gear_obj)
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        return gear

    def IsActive(self): return True

class BevelGear():
    def __init__(self, obj):
        self.Dirty = False
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = "0.2"
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Pitch diameter"), 1)
        obj.addProperty("App::PropertyLength", "ConeDistance", "read only", QT_TRANSLATE_NOOP("App::Property", "Outer cone distance"), 1)

        obj.addProperty("App::PropertyLength", "Module", "BevelGear", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = 1.0
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "BevelGear", QT_TRANSLATE_NOOP("App::Property", "Number of teeth")).NumberOfTeeth = 20
        obj.addProperty("App::PropertyAngle", "PressureAngle", "BevelGear", QT_TRANSLATE_NOOP("App::Property", "Pressure angle")).PressureAngle = 20.0
        obj.addProperty("App::PropertyAngle", "PitchAngle", "BevelGear", QT_TRANSLATE_NOOP("App::Property", "Pitch Cone Angle (45deg for 1:1)")).PitchAngle = 45.0
        obj.addProperty("App::PropertyAngle", "SpiralAngle", "BevelGear", QT_TRANSLATE_NOOP("App::Property", "Spiral angle (0 for straight)")).SpiralAngle = 0.0
        obj.addProperty("App::PropertyLength", "FaceWidth", "BevelGear", QT_TRANSLATE_NOOP("App::Property", "Face Width")).FaceWidth = 5.0
        obj.addProperty("App::PropertyString", "BodyName", "BevelGear", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = "BevelGear"
        
        obj.addProperty("App::PropertyEnumeration", "BoreType", "Bore", QT_TRANSLATE_NOOP("App::Property", "Type of center hole"))
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.addProperty("App::PropertyLength", "BoreDiameter", "Bore", QT_TRANSLATE_NOOP("App::Property", "Bore diameter")).BoreDiameter = 5.0
        obj.addProperty("App::PropertyLength", "SquareCornerRadius", "Bore", QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore")).SquareCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "HexCornerRadius", "Bore", QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore")).HexCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "KeywayWidth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)")).KeywayWidth = 2.0
        obj.addProperty("App::PropertyLength", "KeywayDepth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Depth of keyway")).KeywayDepth = 1.0

        self.Type = 'BevelGear'
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
                        if hasattr(old_body, 'removeObjectsFromDocument'):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
                self.last_body_name = new_name
        if prop in ["Module", "NumberOfTeeth", "PitchAngle"]:
            try:
                m = fp.Module.Value
                z = fp.NumberOfTeeth
                angle = fp.PitchAngle.Value
                pd = m * z
                fp.PitchDiameter = pd
                sin_a = math.sin(math.radians(angle))
                if abs(sin_a) < 0.001: sin_a = 0.001
                fp.ConeDistance = pd / (2.0 * sin_a)
            except: pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "pitch_angle": float(self.Object.PitchAngle.Value),
            "spiral_angle": float(self.Object.SpiralAngle.Value),
            "face_width": float(self.Object.FaceWidth.Value),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            "body_name": str(self.Object.BodyName)
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                generateBevelGearPart(App.ActiveDocument, self.GetParameters())
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Bevel Error: {e}\n")

    def execute(self, obj):
        import PySide.QtCore as QtCore
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)

class ViewProviderBevelGear:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.iconfile = iconfile if iconfile else mainIcon
    def attach(self, obj): self.Object = obj.Object
    def getDisplayModes(self, obj): return ["Shaded", "Wireframe"]
    def getDefaultDisplayMode(self): return "Shaded"
    def getIcon(self): return self.iconfile
    def doubleClicked(self, vobj): return True
    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui
        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)
    def regenerate(self):
        if hasattr(self.Object, 'Proxy'): self.Object.Proxy.force_Recompute()
    def __getstate__(self): return self.iconfile
    def __setstate__(self, state): self.iconfile = state if state else mainIcon

try: FreeCADGui.addCommand('BevelGearCreateObject', BevelGearCreateObject())
except Exception: pass