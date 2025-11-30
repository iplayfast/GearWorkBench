"""Cycloid Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric cycloidal gears (clock/watch standard).

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""
from __future__ import division

import os
import FreeCADGui
import FreeCAD as App
import gearMath
from PySide import QtCore

# Set up icon paths
smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'cycloidGear.svg')

# Debug: print icon path
App.Console.PrintMessage(f"Cycloid Gear icon path: {mainIcon}\n")
if not os.path.exists(mainIcon):
    App.Console.PrintWarning(f"Cycloid Gear icon not found at: {mainIcon}\n")

version = 'Nov 30, 2025'


def QT_TRANSLATE_NOOP(scope, text):
    return text


class CycloidGearCreateObject():
    """Command to create a new cycloid gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Cycloid Gear",
            'ToolTip': "Create parametric cycloidal gear.\nUse Case: Clocks, watches, and low-friction mechanisms.\nNOT for high-torque power transmission."
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # Unique Body Name
        base_name = "CycloidGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "CycloidGearParameters")
        cycloid_gear = CycloidGear(gear_obj)
        
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return cycloid_gear

    def IsActive(self):
        return True


class CycloidGear():
    """FeaturePython object for parametric cycloid gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultCycloidParameters()

        # Read-only
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Pitch diameter"), 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Tip diameter"), 1)
        obj.addProperty("App::PropertyLength", "RootDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Root diameter"), 1)

        # Parameters
        obj.addProperty("App::PropertyLength", "Module", "CycloidGear", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "CycloidGear", QT_TRANSLATE_NOOP("App::Property", "Number of teeth")).NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyLength", "Height", "CycloidGear", QT_TRANSLATE_NOOP("App::Property", "Gear thickness")).Height = H["height"]
        obj.addProperty("App::PropertyFloat", "AddendumFactor", "CycloidGear", QT_TRANSLATE_NOOP("App::Property", "Head height factor (standard ~1.4)")).AddendumFactor = H["addendum_factor"]
        obj.addProperty("App::PropertyFloat", "DedendumFactor", "CycloidGear", QT_TRANSLATE_NOOP("App::Property", "Root depth factor (standard ~1.6)")).DedendumFactor = H["dedendum_factor"]
        
        obj.addProperty("App::PropertyString", "BodyName", "CycloidGear", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = H["body_name"]

        # Bore
        obj.addProperty("App::PropertyEnumeration", "BoreType", "Bore", QT_TRANSLATE_NOOP("App::Property", "Type of center hole"))
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]
        obj.addProperty("App::PropertyLength", "BoreDiameter", "Bore", QT_TRANSLATE_NOOP("App::Property", "Bore diameter")).BoreDiameter = H["bore_diameter"]

        self.Type = 'CycloidGear'
        self.Object = obj
        self.doc = App.ActiveDocument
        obj.Proxy = self
        
        self.onChanged(obj, "Module")

    def __getstate__(self): return self.Type
    def __setstate__(self, state): 
        if state: self.Type = state

    def onChanged(self, fp, prop):
        self.Dirty = True
        if prop in ["Module", "NumberOfTeeth", "AddendumFactor", "DedendumFactor"]:
            try:
                m = fp.Module.Value
                z = fp.NumberOfTeeth
                ha = fp.AddendumFactor
                hf = fp.DedendumFactor
                
                fp.PitchDiameter = m * z
                fp.OuterDiameter = m * z + 2 * (m * ha)
                fp.RootDiameter = m * z - 2 * (m * hf)
            except: pass

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
                gearMath.validateCycloidParameters(parameters)
                gearMath.generateCycloidGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
                App.Console.PrintMessage("Cycloid gear generated successfully\n")
            except Exception as e:
                App.Console.PrintError(f"Cycloid Gear Error: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())

    def execute(self, obj):
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderCycloidGear:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.part = obj
        self.iconfile = iconfile if iconfile else mainIcon

    def attach(self, obj):
        self.ViewObject = obj
        self.Object = obj.Object

    def updateData(self, fp, prop): return
    def getDisplayModes(self, obj): return ["Shaded", "Wireframe", "Flat Lines"]
    def getDefaultDisplayMode(self): return "Shaded"
    def setDisplayMode(self, mode): return mode
    def onChanged(self, vobj, prop): return
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
    def __setstate__(self, state):
        self.iconfile = state if state else mainIcon

try:
    FreeCADGui.addCommand('CycloidGearCreateObject', CycloidGearCreateObject())
except Exception: pass