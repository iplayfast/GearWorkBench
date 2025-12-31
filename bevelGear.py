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
    """
    Generates a solid Bevel Gear.
    """
    validateBevelParameters(parameters)
    body_name = parameters.get("body_name", "BevelGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    face_width = parameters["face_width"]
    pitch_angle = parameters["pitch_angle"]
    pressure_angle = parameters["pressure_angle"]
    
    # --- 1. Calculate Geometry ---
    # Pitch Radius (Outer)
    r_pitch = (module * num_teeth) / 2.0
    
    # Cone Distance (Apex to Outer Pitch Circle)
    sin_delta = math.sin(pitch_angle * util.DEG_TO_RAD)
    if sin_delta < 0.001: sin_delta = 0.001
    cone_dist = r_pitch / sin_delta
    
    # Clamp Face Width
    if face_width > cone_dist * 0.5:
        face_width = cone_dist * 0.5
        App.Console.PrintWarning(f"Face width clamped to {face_width}mm\n")

    # Inner Cone Distance
    cone_dist_inner = cone_dist - face_width
    
    # Scale Factor (for the inner profile)
    scale_factor = cone_dist_inner / cone_dist
    
    # Inner Module (virtual)
    module_inner = module * scale_factor

    # Placement Z-coordinates (Apex at Origin 0,0,0)
    z_outer = cone_dist
    z_inner = cone_dist_inner

    # --- 2. Create Core Body (Root Cone) ---
    dedendum = module * gearMath.DEDENDUM_FACTOR
    dedendum_inner = module_inner * gearMath.DEDENDUM_FACTOR
    
    r_root_outer = r_pitch - (dedendum * math.cos(pitch_angle * util.DEG_TO_RAD))
    r_root_inner = (r_pitch * scale_factor) - (dedendum_inner * math.cos(pitch_angle * util.DEG_TO_RAD))
    
    if r_root_outer < 0.1: r_root_outer = 0.1
    if r_root_inner < 0.1: r_root_inner = 0.1

    # Sketch for Root Cone Outer
    sk_core_out = util.createSketch(body, 'CoreCircle_Outer')
    sk_core_out.MapMode = 'Deactivated'
    c1 = sk_core_out.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_root_outer), False)
    sk_core_out.addConstraint(Sketcher.Constraint('Diameter', c1, r_root_outer * 2))
    sk_core_out.Placement = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
    
    # Sketch for Root Cone Inner
    sk_core_in = util.createSketch(body, 'CoreCircle_Inner')
    sk_core_in.MapMode = 'Deactivated'
    c2 = sk_core_in.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), r_root_inner), False)
    sk_core_in.addConstraint(Sketcher.Constraint('Diameter', c2, r_root_inner * 2))
    sk_core_in.Placement = App.Placement(App.Vector(0, 0, z_inner), App.Rotation(0,0,0))
    
    # Create Base Cone Loft
    base_loft = body.newObject('PartDesign::AdditiveLoft', 'BaseCone')
    base_loft.Profile = sk_core_out
    base_loft.Sections = [sk_core_in]
    base_loft.Ruled = True
    body.Tip = base_loft
    
    # --- 3. Create Tooth Profiles ---
    
    # Spiral / Twist Calculation
    spiral_angle = parameters.get("spiral_angle", 0.0)
    twist_angle_deg = 0.0
    if abs(spiral_angle) > 0.001:
        cone_dist_mean = (cone_dist + cone_dist_inner) / 2.0
        r_mean = cone_dist_mean * sin_delta
        twist_arc = face_width * math.tan(spiral_angle * util.DEG_TO_RAD)
        twist_angle_rad = twist_arc / r_mean
        twist_angle_deg = twist_angle_rad * util.RAD_TO_DEG

    # Parameter sets
    params_outer = parameters.copy()
    params_inner = parameters.copy()
    params_inner["module"] = module_inner # Automatically scales the geometry
    
    # Sketch Outer Tooth
    sk_tooth_out = util.createSketch(body, 'ToothProfile_Outer')
    gearMath.generateToothProfile(sk_tooth_out, params_outer)
    sk_tooth_out.MapMode = 'Deactivated'
    sk_tooth_out.Placement = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
    
    # Sketch Inner Tooth
    sk_tooth_in = util.createSketch(body, 'ToothProfile_Inner')
    gearMath.generateToothProfile(sk_tooth_in, params_inner)
    sk_tooth_in.MapMode = 'Deactivated'
    # Apply Twist Rotation around Z-axis
    sk_tooth_in.Placement = App.Placement(App.Vector(0, 0, z_inner), App.Rotation(App.Vector(0,0,1), twist_angle_deg))
    
    # --- 4. Loft the Tooth ---
    tooth_loft = body.newObject('PartDesign::AdditiveLoft', 'Tooth')
    tooth_loft.Profile = sk_tooth_out
    tooth_loft.Sections = [sk_tooth_in]
    tooth_loft.Ruled = False # Smooth interpolation
    
    # --- 5. Pattern the Tooth ---
    polar = util.createPolar(body, tooth_loft, sk_core_out, num_teeth, 'Teeth')
    polar.Originals = [tooth_loft]
    body.Tip = polar
    
    # --- 6. Bore ---
    if parameters.get("bore_type", "none") != "none":
        z_outer_place = App.Placement(App.Vector(0, 0, z_outer), App.Rotation(0,0,0))
        util.createBore(body, parameters, cone_dist + 10.0, placement=z_outer_place, reversed=False)

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass

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