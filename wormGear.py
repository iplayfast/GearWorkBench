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
        polar = util.createPolar(body, helix, sk_base, num_threads, 'Threads')
        # Fix axis
        polar.Axis = (sk_base, ['N_Axis'])
        polar.Originals = [helix]
        helix.Visibility = False
        polar.Visibility = True
        body.Tip = polar

    # 5. Bore
    if parameters.get("bore_type", "none") != "none":
         util.createBore(body, parameters, length + 10.0)

    # 6. Mating Gear
    if parameters.get("create_mating_gear", False):
        worm_pitch_radius = (root_dia / 2.0) + dedendum
        wheel_teeth = parameters.get("gear_teeth", 30)
        wheel_pitch_radius = (module * wheel_teeth) / 2.0
        center_distance = worm_pitch_radius + wheel_pitch_radius
        
        generateMatingGear(doc, parameters, center_distance, worm_pitch_radius, addendum, dedendum)

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass


def generateMatingGear(doc, parameters, center_distance, worm_pitch_radius, worm_addendum, worm_dedendum):
    """Generate the mating worm wheel (gear)."""
    body_name = parameters.get("body_name", "WormGear")
    gear_body_name = f"{body_name}_WormWheel"

    # Extract parameters
    module = parameters["module"]
    num_teeth = parameters["gear_teeth"]
    height = parameters["gear_height"]
    pressure_angle = parameters["pressure_angle"]
    num_threads = parameters["num_threads"]
    right_handed = parameters["right_handed"]

    # Calculate worm lead angle
    thread_pitch = math.pi * module
    lead = thread_pitch * num_threads
    worm_pitch_diameter = worm_pitch_radius * 2.0

    lead_angle_rad = math.atan(lead / (math.pi * worm_pitch_diameter))
    
    # Clean up existing gear body
    gear_body = util.readyPart(doc, gear_body_name)

    # Calculate gear geometry
    pitch_diameter = module * num_teeth
    gear_pitch_radius = pitch_diameter / 2.0
    dedendum = module * gearMath.DEDENDUM_FACTOR
    root_radius = gear_pitch_radius - dedendum

    # Helical twist
    # Helix Angle of Wheel = Lead Angle of Worm
    helix_angle_rad = lead_angle_rad
    twist_total_rad = (height * math.tan(helix_angle_rad)) / gear_pitch_radius
    twist_total_deg = twist_total_rad / util.DEG_TO_RAD

    if right_handed:
        twist_total_deg = -twist_total_deg

    # Calculate required Tip Radius for Throated Gear
    # The gear blank must extend to the "corners" of the worm envelope
    # Corner limit: x = CD - sqrt(r_root^2 - (h/2)^2)
    # We want to be slightly larger than this to ensure a clean cut
    worm_root_radius = worm_pitch_radius - worm_dedendum
    half_height = height / 2.0
    
    if worm_root_radius > half_height:
        # Normal case: Worm curvature covers the gear width
        corner_gap = center_distance - math.sqrt(worm_root_radius**2 - half_height**2)
    else:
        # Edge case: Gear is wider than worm curvature (wraps > 180 deg?)
        # Limit to center distance (tangency)
        corner_gap = center_distance
        
    # Set tip radius to cover the gap + clearance margin
    # We use a slightly larger radius so the Groove cuts the tips cleanly
    tip_radius_override = corner_gap + 0.1 * module

    # STEP 1: Bottom Profile
    sk_bottom = util.createSketch(gear_body, 'ToothProfileBottom')
    tooth_params = {
        "module": module,
        "num_teeth": num_teeth,
        "pressure_angle": pressure_angle,
        "profile_shift": 0.0,
        "tip_radius": tip_radius_override
    }
    gearMath.generateToothProfile(sk_bottom, tooth_params)

    # STEP 2: Top Profile
    sk_top = util.createSketch(gear_body, 'ToothProfileTop')
    xy_plane = None
    if hasattr(gear_body, 'Origin') and gear_body.Origin:
        for feat in gear_body.Origin.Group:
            if 'XY' in feat.Name or 'XY' in feat.Label:
                xy_plane = feat
                break
    
    if xy_plane:
        sk_top.AttachmentSupport = [(xy_plane, '')]
        sk_top.MapMode = 'FlatFace'
        sk_top.AttachmentOffset = App.Placement(
            App.Vector(0, 0, height),
            App.Rotation(App.Vector(0, 0, 1), twist_total_deg)
        )
    else:
        sk_top.MapMode = 'Deactivated'
        sk_top.Placement = App.Placement(
             App.Vector(0, 0, height),
             App.Rotation(App.Vector(0, 0, 1), twist_total_deg)
        )

    gearMath.generateToothProfile(sk_top, tooth_params)

    # STEP 3: Loft
    loft = gear_body.newObject('PartDesign::AdditiveLoft', 'HelicalTooth')
    loft.Profile = sk_bottom
    loft.Sections = [sk_top]
    loft.Ruled = True

    sk_bottom.Visibility = False
    sk_top.Visibility = False

    # STEP 4: Polar
    polar = util.createPolar(gear_body, loft, sk_bottom, num_teeth, 'Teeth')
    polar.Originals = [loft]
    loft.Visibility = False
    polar.Visibility = True
    gear_body.Tip = polar

    # STEP 5: Dedendum
    df = root_radius * 2.0
    ded_sketch = util.createSketch(gear_body, 'DedendumCircle')
    circle = ded_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01), False)
    ded_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    ded_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, df + 0.02))
    ded_pad = util.createPad(gear_body, ded_sketch, height, 'DedendumPad')
    gear_body.Tip = ded_pad

    # STEP 6: Throat Cut
    sk_throat = gear_body.newObject('Sketcher::SketchObject', 'ThroatCutSketch')
    xz_plane = None
    if hasattr(gear_body, 'Origin') and gear_body.Origin:
        for feat in gear_body.Origin.Group:
            if 'XZ' in feat.Name or 'XZ' in feat.Label:
                xz_plane = feat
                break
    
    if xz_plane:
        sk_throat.AttachmentSupport = [(xz_plane, '')]
        sk_throat.MapMode = 'ObjectXY'
        sk_throat.AttachmentOffset = App.Placement(App.Vector(0, height / 2.0, 0), App.Rotation())
    else:
        # Fallback: Manual alignment to XZ plane
        sk_throat.MapMode = 'Deactivated'
        # Rotate 90 deg X to align Y with Z. Offset in Z (Body Z) is height/2.
        sk_throat.Placement = App.Placement(App.Vector(0, 0, height / 2.0), App.Rotation(App.Vector(1,0,0), 90))
    
    # Worm clearance cut
    clearance = module * parameters.get("clearance", 0.1)
    # Throat cut should match Worm Root (to clear the shaft)
    worm_root_radius = worm_pitch_radius - worm_dedendum
    cut_radius = worm_root_radius + clearance

    c_idx = sk_throat.addGeometry(
        Part.Circle(App.Vector(-center_distance, 0, 0), App.Vector(0, 0, 1), cut_radius),
        False
    )
    sk_throat.addConstraint(Sketcher.Constraint('PointOnObject', c_idx, 3, -1))
    sk_throat.addConstraint(Sketcher.Constraint('Radius', c_idx, cut_radius))
    sk_throat.addConstraint(Sketcher.Constraint('DistanceX', c_idx, 3, -1, 1, -center_distance))
    
    groove = gear_body.newObject('PartDesign::Groove', 'ThroatGroove')
    groove.Profile = sk_throat
    groove.ReferenceAxis = (sk_throat, ['V_Axis'])
    
    groove.Angle = 360.0
    sk_throat.Visibility = False
    gear_body.Tip = groove

    # Alignment
    worm_length = parameters.get("length", 50.0)
    r_align = App.Rotation(App.Vector(1, 0, 0), 90)
    gear_body.Placement = App.Placement(
        App.Vector(center_distance, height / 2.0, worm_length / 2.0),
        r_align
    )


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
        obj.addProperty("App::PropertyLength", "CenterDistance", "read only", QT_TRANSLATE_NOOP("App::Property", "Distance between worm and wheel axes"), 1)
        obj.addProperty("App::PropertyLength", "WheelPitchDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Pitch diameter of mating wheel"), 1)
        
        obj.addProperty("App::PropertyLength", "Module", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = 1.0
        obj.addProperty("App::PropertyLength", "WormDiameter", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Root Diameter of the worm")).WormDiameter = 20.0
        obj.addProperty("App::PropertyInteger", "NumberOfThreads", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Number of threads (starts)")).NumberOfThreads = 1
        obj.addProperty("App::PropertyAngle", "PressureAngle", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Pressure angle")).PressureAngle = 20.0
        obj.addProperty("App::PropertyLength", "Length", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Total length of the worm cylinder")).Length = 50.0
        obj.addProperty("App::PropertyLength", "HelixLength", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Length of the threaded portion")).HelixLength = 40.0
        obj.addProperty("App::PropertyBool", "CenterHelix", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Center the helix along the cylinder")).CenterHelix = True
        obj.addProperty("App::PropertyBool", "RightHanded", "WormGear", QT_TRANSLATE_NOOP("App::Property", "True for Right-handed, False for Left-handed")).RightHanded = True
        obj.addProperty("App::PropertyString", "BodyName", "WormGear", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = "WormGear"
        
        # Mating Gear
        obj.addProperty("App::PropertyBool", "CreateMatingGear", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Create the mating worm wheel")).CreateMatingGear = True
        obj.addProperty("App::PropertyInteger", "GearTeeth", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Number of teeth on mating gear")).GearTeeth = 30
        obj.addProperty("App::PropertyLength", "GearHeight", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Height/thickness of mating gear")).GearHeight = 10.0
        obj.addProperty("App::PropertyFloat", "Clearance", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Clearance factor")).Clearance = 0.1

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
        if prop in ["Module", "NumberOfThreads", "WormDiameter", "Length", "HelixLength", "GearTeeth"]:
            try:
                m = fp.Module.Value
                z1 = fp.NumberOfThreads
                d_root = fp.WormDiameter.Value
                
                # Worm Pitch Diameter = Root + 2*Dedendum
                # Dedendum = m * 1.25
                d_pitch = d_root + 2 * m * gearMath.DEDENDUM_FACTOR
                
                if d_pitch > 0:
                    val = (m * z1) / d_pitch
                    fp.LeadAngle = math.degrees(math.atan(val))
                
                # Wheel Pitch Diameter
                wheel_pitch = m * fp.GearTeeth
                fp.WheelPitchDiameter = wheel_pitch
                
                # Center Distance
                fp.CenterDistance = (d_pitch + wheel_pitch) / 2.0
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
            "create_mating_gear": bool(self.Object.CreateMatingGear),
            "gear_teeth": int(self.Object.GearTeeth),
            "gear_height": float(self.Object.GearHeight.Value),
            "clearance": float(self.Object.Clearance),
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
        QtCore.QTimer.singleShot(50, self.recompute)

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