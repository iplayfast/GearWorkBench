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

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'cycloidGear.svg')

if not os.path.exists(mainIcon):
    App.Console.PrintWarning(f"Cycloid Gear icon not found at: {mainIcon}\n")

version = 'Nov 30, 2025'


def QT_TRANSLATE_NOOP(scope, text):
    return text

# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================

def validateCycloidParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < 3: raise gearMath.GearParameterError("Teeth must be >= 3")
    if parameters["height"] <= 0: raise gearMath.GearParameterError("Height must be positive")

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
        cx = (R + r_roll) * math.cos(t) - r_roll * math.cos((R + r_roll)/r_roll * t)
        cy = (R + r_roll) * math.sin(t) - r_roll * math.sin((R + r_roll)/r_roll * t)
        return cx, cy

    def get_hypo_point(t):
        cx = (R - r_roll) * math.cos(t) + r_roll * math.cos((R - r_roll)/r_roll * t)
        cy = -( (R - r_roll) * math.sin(t) - r_roll * math.sin((R - r_roll)/r_roll * t) )
        return cx, cy
    
    # 1. Epicycloid (Tip)
    epi_pts = []
    steps = 50
    step_size = 0.5 / steps
    
    for i in range(steps + 1):
        t = i * step_size
        cx, cy = get_epi_point(t)
        r_cur = math.sqrt(cx*cx + cy*cy)
        
        if r_cur > Ra:
            # Refine t to hit Ra exactly
            t_low = (i - 1) * step_size
            t_high = t
            for _ in range(10): # Binary search
                t_mid = (t_low + t_high) / 2.0
                mx, my = get_epi_point(t_mid)
                mr = math.sqrt(mx*mx + my*my)
                if mr > Ra: t_high = t_mid
                else: t_low = t_mid
            cx, cy = get_epi_point(t_low) # Use lower bound to be safe/close
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
        r_cur = math.sqrt(cx*cx + cy*cy)
        
        if r_cur < Rf:
            # Refine t to hit Rf exactly
            t_low = (i - 1) * step_size
            t_high = t
            for _ in range(10):
                t_mid = (t_low + t_high) / 2.0
                mx, my = get_hypo_point(t_mid)
                mr = math.sqrt(mx*mx + my*my)
                if mr < Rf: t_high = t_mid # Too deep
                else: t_low = t_mid
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
    validateCycloidParameters(parameters)
    
    body_name = parameters.get("body_name", "CycloidGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    dedendum_factor = parameters["dedendum_factor"]
    
    Rf = (module * num_teeth) / 2.0 - (module * dedendum_factor)
    
    sketch = util.createSketch(body, 'ToothProfile')
    generateCycloidToothProfile(sketch, parameters)
    tooth_pad = util.createPad(body, sketch, height, 'Tooth')
    
    polar = util.createPolar(body, tooth_pad, sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar
    
    ded_sketch = util.createSketch(body, 'DedendumCircle')
    circle = ded_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), Rf + 0.01), False)
    ded_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    ded_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, (Rf + 0.01)*2))
    
    ded_pad = util.createPad(body, ded_sketch, height, 'DedendumCircle')
    body.Tip = ded_pad
    
    if parameters.get("bore_type", "none") != "none":
        util.createBore(body, parameters, height)
        
    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass

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
        self.last_body_name = obj.BodyName
        obj.Proxy = self

        self.onChanged(obj, "Module")

    def __getstate__(self): return self.Type
    def __setstate__(self, state):
        if state: self.Type = state

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