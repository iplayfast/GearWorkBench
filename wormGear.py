"""Worm Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric Worm Gears.

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""
import FreeCAD as App
import FreeCADGui
import gearMath
import os
import math

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'wormGear.svg') 

def QT_TRANSLATE_NOOP(scope, text): return text

class WormGearCreateObject():
    def GetResources(self):
        return {'Pixmap': mainIcon, 'MenuText': "&Create Worm Gear", 'ToolTip': "Create parametric worm gear"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        
        base_name = "WormGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "WormGearParameters")
        gear = WormGear(gear_obj)
        gear_obj.BodyName = unique_name
        
        gear.force_Recompute()
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        return gear

    def IsActive(self): return True

class WormGear():
    def __init__(self, obj):
        self.Dirty = False
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = "0.1"
        obj.addProperty("App::PropertyAngle", "LeadAngle", "read only", QT_TRANSLATE_NOOP("App::Property", "Lead Angle"), 1)
        
        obj.addProperty("App::PropertyLength", "Module", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = 1.0
        obj.addProperty("App::PropertyLength", "WormDiameter", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Pitch Diameter of the worm")).WormDiameter = 20.0
        obj.addProperty("App::PropertyInteger", "NumberOfThreads", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Number of threads (starts)")).NumberOfThreads = 1
        obj.addProperty("App::PropertyAngle", "PressureAngle", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Pressure angle")).PressureAngle = 20.0
        obj.addProperty("App::PropertyLength", "Length", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Length of the worm")).Length = 50.0
        obj.addProperty("App::PropertyBool", "RightHanded", "WormGear", QT_TRANSLATE_NOOP("App::Property", "True for Right-handed, False for Left-handed")).RightHanded = True
        obj.addProperty("App::PropertyString", "BodyName", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = "WormGear"
        
        # Bore Parameters
        obj.addProperty("App::PropertyEnumeration", "BoreType", "Bore", QT_TRANSLATE_NOOP("App::Property", "Type of center hole"))
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.addProperty("App::PropertyLength", "BoreDiameter", "Bore", QT_TRANSLATE_NOOP("App::Property", "Bore diameter")).BoreDiameter = 5.0
        obj.addProperty("App::PropertyLength", "SquareCornerRadius", "Bore", QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore")).SquareCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "HexCornerRadius", "Bore", QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore")).HexCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "KeywayWidth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)")).KeywayWidth = 2.0
        obj.addProperty("App::PropertyLength", "KeywayDepth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Depth of keyway")).KeywayDepth = 1.0

        self.Type = 'WormGear'
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        self.Dirty = True
        if prop in ["Module", "NumberOfThreads", "WormDiameter"]:
            try:
                m = fp.Module.Value
                z1 = fp.NumberOfThreads
                d = fp.WormDiameter.Value
                if d > 0:
                    # Lead Angle = atan( (m * z1) / d )
                    val = (m * z1) / d
                    angle = math.degrees(math.atan(val))
                    fp.LeadAngle = angle
            except: pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_threads": int(self.Object.NumberOfThreads),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "worm_diameter": float(self.Object.WormDiameter.Value),
            "length": float(self.Object.Length.Value),
            "right_handed": bool(self.Object.RightHanded),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value)
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                gearMath.generateWormGearPart(App.ActiveDocument, self.GetParameters())
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Worm Gear Error: {e}\n")

    def execute(self, obj):
        import PySide.QtCore as QtCore
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)

class ViewProviderWormGear:
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

try: FreeCADGui.addCommand('WormGearCreateObject', WormGearCreateObject())
except Exception: pass