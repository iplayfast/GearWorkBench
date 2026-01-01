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

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'rackGear.svg')

# Debug: print icon path
# App.Console.PrintMessage(f"Rack Gear icon path: {mainIcon}\n")
if not os.path.exists(mainIcon):
    App.Console.PrintWarning(f"Rack Gear icon not found at: {mainIcon}\n")

version = 'Nov 30, 2025'


def QT_TRANSLATE_NOOP(scope, text):
    return text

# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================

def validateRackParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < 1: raise gearMath.GearParameterError("Teeth must be >= 1")
    if parameters["height"] <= 0: raise gearMath.GearParameterError("Height must be positive")
    if parameters["base_thickness"] <= 0: raise gearMath.GearParameterError("Base thickness must be positive")

def generateRackToothProfile(sketch, parameters):
    module = parameters["module"]
    pressure_angle = parameters["pressure_angle"]
    
    addendum = module * gearMath.ADDENDUM_FACTOR
    dedendum = module * gearMath.DEDENDUM_FACTOR
    tan_alpha = math.tan(pressure_angle * util.DEG_TO_RAD)
    half_pitch_width = (math.pi * module) / 4.0
    
    y_top = addendum
    x_top = half_pitch_width - (addendum * tan_alpha)
    y_bot = -dedendum
    x_bot = half_pitch_width + (dedendum * tan_alpha)
    
    p_tl = App.Vector(-x_top, y_top, 0)
    p_tr = App.Vector(x_top, y_top, 0)
    p_br = App.Vector(x_bot, y_bot, 0)
    p_bl = App.Vector(-x_bot, y_bot, 0)
    
    points = [p_tl, p_tr, p_br, p_bl, p_tl]
    for i in range(4):
        line = Part.LineSegment(points[i], points[i+1])
        idx = sketch.addGeometry(line, False)
        sketch.addConstraint(Sketcher.Constraint('Block', idx))
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i+1)%4, 1))

def generateRackPart(doc, parameters):
    """Generate standard involute rack using the generic rack system.

    Standard racks use involute tooth profiles with pressure angle.
    """
    validateRackParameters(parameters)

    # Use the generic rack builder with involute profile
    result = genericRack.genericRackGear(
        doc,
        parameters,
        profile_func=generateRackToothProfile
    )

    return result

class RackGearCreateObject():
    """Command to create a new rack gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Gear Rack",
            'ToolTip': "Create parametric gear rack"
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # Generate Unique Body Name
        base_name = "RackGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "RackGearParameters")
        rack_gear = RackGear(gear_obj)
        
        # Assign unique name
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return rack_gear

    def IsActive(self):
        return True


class RackGear():
    """FeaturePython object for parametric rack gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultRackParameters()

        # Read-only Info
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = version

        # Main Parameters (Note: TotalLength is now in 'RackGear' group so it's editable)
        obj.addProperty("App::PropertyLength", "Module", "RackGear", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "RackGear", QT_TRANSLATE_NOOP("App::Property", "Number of teeth")).NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyLength", "TotalLength", "RackGear", QT_TRANSLATE_NOOP("App::Property", "Total length (Pitch * Teeth)")).TotalLength = 0.0
        
        obj.addProperty("App::PropertyAngle", "PressureAngle", "RackGear", QT_TRANSLATE_NOOP("App::Property", "Pressure angle")).PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyLength", "Height", "RackGear", QT_TRANSLATE_NOOP("App::Property", "Gear face width (extrusion height)")).Height = H["height"]
        obj.addProperty("App::PropertyLength", "BaseThickness", "RackGear", QT_TRANSLATE_NOOP("App::Property", "Thickness of base below roots")).BaseThickness = H["base_thickness"]
        obj.addProperty("App::PropertyString", "BodyName", "RackGear", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = H["body_name"]

        self.Type = 'RackGear'
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_body_name = obj.BodyName
        obj.Proxy = self

        # Trigger initial calculation
        self.onChanged(obj, "Module")

    def __getstate__(self): return self.Type
    def __setstate__(self, state):
        if state: self.Type = state

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
            if pitch <= 0: return

            if prop == "TotalLength":
                # User changed Length -> Calculate Teeth
                # Round to nearest integer (cannot have 10.5 teeth)
                new_teeth = int(round(fp.TotalLength.Value / pitch))
                if new_teeth < 1: new_teeth = 1
                
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
    FreeCADGui.addCommand('RackGearCreateObject', RackGearCreateObject())
except Exception: pass