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
import util
import Part
import Sketcher
import os
import math

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'wormGear.svg') 

def QT_TRANSLATE_NOOP(scope, text): return text

# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================

def validateWormParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["worm_diameter"] <= 0: raise gearMath.GearParameterError("Worm Diameter must be positive")
    if parameters["length"] <= 0: raise gearMath.GearParameterError("Length must be positive")

def generateWormGearPart(doc, parameters):
    validateWormParameters(parameters)
    body_name = parameters.get("body_name", "WormGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_threads = parameters["num_threads"] # z1
    worm_dia = parameters["worm_diameter"] # Pitch Diameter
    length = parameters["length"]
    helix_len = parameters.get("helix_length", length)
    center_helix = parameters.get("center_helix", True)
    
    if helix_len > length: helix_len = length
    
    pressure_angle = parameters["pressure_angle"]
    right_handed = parameters["right_handed"]
    
    # Calculate Z-Offset for centering
    z_offset = 0.0
    if center_helix:
        z_offset = (length - helix_len) / 2.0
    
    # Geometry Constants
    addendum = module * gearMath.ADDENDUM_FACTOR
    dedendum = module * gearMath.DEDENDUM_FACTOR
    whole_depth = addendum + dedendum
    
    # User Request: WormDiameter parameter should be the Cylinder (Root) Diameter
    root_dia = worm_dia 
    
    pitch = math.pi * module
    lead = pitch * num_threads
    
    # 1. Base Cylinder (Root)
    sk_base = util.createSketch(body, 'RootShaft')
    sk_base.MapMode = 'Deactivated'
    c_base = sk_base.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), root_dia/2), False)
    sk_base.addConstraint(Sketcher.Constraint('Diameter', c_base, root_dia))
    
    pad_base = body.newObject('PartDesign::Pad', 'Base')
    pad_base.Profile = sk_base
    pad_base.Length = length
    body.Tip = pad_base
    
    # 2. Thread Profile
    # Standard FreeCAD Workflow: Attach Sketch to XZ Plane, Offset by Radius.
    
    sk_profile = util.createSketch(body, 'ThreadProfile')
    
    # Find XZ Plane
    xz_plane = None
    if hasattr(body, 'Origin') and body.Origin:
        for child in body.Origin.Group:
            if 'XZ' in child.Name or 'XZ' in child.Label:
                xz_plane = child
                break
        # Fallback
        if not xz_plane and len(body.Origin.Group) > 1:
             xz_plane = body.Origin.Group[1]

    if xz_plane:
        sk_profile.AttachmentSupport = [(xz_plane, '')]
        sk_profile.MapMode = 'ObjectXY' # Align sketch local system with plane
        # sk_profile.AttachmentOffset removed. Geometry will be offset instead.
    else:
        # Fallback: Manual
        sk_profile.MapMode = 'Deactivated'
        # Placement at Origin, Rotated to XZ orientation
        sk_profile.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(App.Vector(1,0,0), 90))

    # Coordinates: (Radial, Axial) -> (Sketch X, Sketch Y) on XZ Plane
    tan_a = math.tan(pressure_angle * util.DEG_TO_RAD)
    
    # Axial Widths (Half-widths)
    # At Root (Radial=0): Root is WIDER than pitch line.
    hw_root = (pitch / 4.0) + (dedendum * tan_a)
    
    # At Tip (Radial=whole_depth): Tip is NARROWER than pitch line.
    hw_tip = (pitch / 4.0) - (addendum * tan_a)
    if hw_tip < 0: hw_tip = 0.01
    
    # Offset geometry by Root Radius in X (Radial)
    r_offset = root_dia / 2.0
    
    # P0: (0, hw_root)  -> X=r_offset (Radial start), Y=hw (Axial +)
    # Apply Z-Offset to Y component (Axial position)
    p0 = App.Vector(r_offset, hw_root + z_offset, 0)
    p1 = App.Vector(r_offset + whole_depth, hw_tip + z_offset, 0)
    p2 = App.Vector(r_offset + whole_depth, -hw_tip + z_offset, 0)
    p3 = App.Vector(r_offset, -hw_root + z_offset, 0)
    
    pts = [p0, p1, p2, p3, p0]
    
    for i in range(4):
        line = Part.LineSegment(pts[i], pts[i+1])
        sk_profile.addGeometry(line, False)
        
    # 3. Helix
    helix = body.newObject('PartDesign::AdditiveHelix', 'WormThread')
    helix.Profile = sk_profile
    helix.Pitch = lead 
    helix.Height = helix_len
    helix.Reversed = False
    helix.LeftHanded = not right_handed
    
    # CORRECT AXIS LINK: Use Sketch V-Axis (Global Z)
    helix.ReferenceAxis = (sk_profile, ['V_Axis'])
    body.Tip = helix

    # 4. Pattern (Multi-Start)
    if num_threads > 1:
        polar = util.createPolar(body, helix, None, num_threads, 'Threads')
        # Fix axis
        polar.Axis = (sk_base, ['N_Axis'])
        body.Tip = polar

    # 5. Bore
    if parameters.get("bore_type", "none") != "none":
         util.createBore(body, parameters, length + 10.0)

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass

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
        obj.addProperty("App::PropertyLength", "Length", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Total length of the worm cylinder")).Length = 50.0
        obj.addProperty("App::PropertyLength", "HelixLength", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Length of the threaded portion")).HelixLength = 40.0
        obj.addProperty("App::PropertyBool", "CenterHelix", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Center the helix along the cylinder")).CenterHelix = True
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
        if prop in ["Module", "NumberOfThreads", "WormDiameter", "Length", "HelixLength"]:
            try:
                # Calc Lead Angle
                m = fp.Module.Value
                z1 = fp.NumberOfThreads
                d = fp.WormDiameter.Value
                if d > 0:
                    val = (m * z1) / d
                    fp.LeadAngle = math.degrees(math.atan(val))
                
                # Clamp Helix Length
                if fp.HelixLength.Value > fp.Length.Value:
                    fp.HelixLength = fp.Length.Value
            except: pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_threads": int(self.Object.NumberOfThreads),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "worm_diameter": float(self.Object.WormDiameter.Value),
            "length": float(self.Object.Length.Value),
            "helix_length": float(self.Object.HelixLength.Value),
            "center_helix": bool(self.Object.CenterHelix),
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
                generateWormGearPart(App.ActiveDocument, self.GetParameters())
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