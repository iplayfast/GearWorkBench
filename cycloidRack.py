"""Cycloid Rack generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric cycloidal racks (to mesh with cycloid gears).

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""
from __future__ import division

import os
import math
import FreeCADGui
import FreeCAD as App
import gearMath
from PySide import QtCore

# Set up icon paths
smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'cycloidRack.svg') # User will provide this

# Debug: print icon path
# App.Console.PrintMessage(f"Cycloid Rack icon path: {mainIcon}\n")
if not os.path.exists(mainIcon):
    App.Console.PrintWarning(f"Cycloid Rack icon not found at: {mainIcon}\n")

version = 'Nov 30, 2025'


def QT_TRANSLATE_NOOP(scope, text):
    return text


class CycloidRackCreateObject():
    """Command to create a new cycloid rack object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Cycloid Rack",
            'ToolTip': "Create parametric cycloidal rack (for clocks/watches)"
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # Generate Unique Body Name
        base_name = "CycloidRack"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "CycloidRackParameters")
        rack = CycloidRack(gear_obj)
        
        # Assign unique name
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return rack

    def IsActive(self):
        return True


class CycloidRack():
    """FeaturePython object for parametric cycloid rack."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultCycloidRackParameters()

        # Read-only
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = version
        # Editable Total Length
        obj.addProperty("App::PropertyLength", "TotalLength", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Total length (Pitch * Teeth)")).TotalLength = 0.0

        # Parameters
        obj.addProperty("App::PropertyLength", "Module", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Number of teeth")).NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyLength", "Height", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Gear face width")).Height = H["height"]
        
        obj.addProperty("App::PropertyFloat", "AddendumFactor", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Head height factor")).AddendumFactor = H["addendum_factor"]
        obj.addProperty("App::PropertyFloat", "DedendumFactor", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Root depth factor")).DedendumFactor = H["dedendum_factor"]
        
        obj.addProperty("App::PropertyLength", "BaseThickness", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Thickness of base below roots")).BaseThickness = H["base_thickness"]
        obj.addProperty("App::PropertyString", "BodyName", "CycloidRack", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = H["body_name"]

        self.Type = 'CycloidRack'
        self.Object = obj
        self.doc = App.ActiveDocument
        obj.Proxy = self
        
        self.onChanged(obj, "Module")

    def __getstate__(self): return self.Type
    def __setstate__(self, state): 
        if state: self.Type = state

    def onChanged(self, fp, prop):
        self.Dirty = True
        
        if not all(hasattr(fp, p) for p in ["Module", "NumberOfTeeth", "TotalLength"]):
            return

        try:
            pitch = math.pi * fp.Module.Value
            if pitch <= 0: return

            if prop == "TotalLength":
                # Recalculate teeth from length
                new_teeth = int(round(fp.TotalLength.Value / pitch))
                if new_teeth < 1: new_teeth = 1
                if fp.NumberOfTeeth != new_teeth:
                    fp.NumberOfTeeth = new_teeth

            elif prop in ["Module", "NumberOfTeeth"]:
                # Recalculate length from teeth
                new_length = pitch * fp.NumberOfTeeth
                if abs(fp.TotalLength.Value - new_length) > 0.000001:
                    fp.TotalLength = new_length
                    
        except Exception as e:
            App.Console.PrintWarning(f"CycloidRack onChanged error: {e}\n")

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "height": float(self.Object.Height.Value),
            "addendum_factor": float(self.Object.AddendumFactor),
            "dedendum_factor": float(self.Object.DedendumFactor),
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
                gearMath.validateCycloidRackParameters(parameters)
                gearMath.generateCycloidRackPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
                # App.Console.PrintMessage("Cycloid rack generated successfully\n")
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Cycloid Rack Error: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())

    def execute(self, obj):
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderCycloidRack:
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
        action = QtGui.QAction("Regenerate Rack", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)
    def regenerate(self):
        if hasattr(self.Object, 'Proxy'): self.Object.Proxy.force_Recompute()
    def __getstate__(self): return self.iconfile
    def __setstate__(self, state):
        self.iconfile = state if state else mainIcon

try:
    FreeCADGui.addCommand('CycloidRackCreateObject', CycloidRackCreateObject())
except Exception: pass