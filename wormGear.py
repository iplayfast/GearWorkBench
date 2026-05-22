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
from genericGear import _VarSetWatcher, ViewProviderGearResult
from PySide import QtCore

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

    # Alignment — position at center distance, wheel midline at worm mid-height.
    # The WheelPhase parameter (in the VarSet) lets the user dial in the tooth
    # mesh by rotating the wheel about its own axis.
    worm_length = parameters.get("length", 50.0)
    wheel_phase = parameters.get("wheel_phase", 0.0)
    r_align = App.Rotation(App.Vector(1, 0, 0), 90) * App.Rotation(App.Vector(0, 0, 1), wheel_phase)
    gear_body.Placement = App.Placement(
        App.Vector(center_distance, height / 2.0, worm_length / 2.0),
        r_align
    )


def createWormGearVarSet(doc, name):
    """Create a VarSet for WormGear parameters."""
    var_set = doc.addObject("App::VarSet", name)

    var_set.addProperty(
        "App::PropertyString", "Version", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Workbench version"), 1,
    ).Version = "0.1"

    var_set.addProperty(
        "App::PropertyLength", "Module", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "Gear module"),
    ).Module = 1.0

    var_set.addProperty(
        "App::PropertyLength", "WormDiameter", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "Root diameter of worm"),
    ).WormDiameter = 20.0

    var_set.addProperty(
        "App::PropertyInteger", "NumberOfThreads", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of threads (starts)"),
    ).NumberOfThreads = 1

    var_set.addProperty(
        "App::PropertyAngle", "PressureAngle", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20)"),
    ).PressureAngle = 20.0

    var_set.addProperty(
        "App::PropertyLength", "Length", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "Total length of worm cylinder"),
    ).Length = 50.0

    var_set.addProperty(
        "App::PropertyLength", "HelixLength", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "Length of threaded portion"),
    ).HelixLength = 40.0

    var_set.addProperty(
        "App::PropertyBool", "CenterHelix", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "Center helix along cylinder"),
    ).CenterHelix = True

    var_set.addProperty(
        "App::PropertyBool", "RightHanded", "WormGear",
        QT_TRANSLATE_NOOP("App::Property", "True = right-handed, False = left-handed"),
    ).RightHanded = True

    var_set.addProperty(
        "App::PropertyBool", "CreateMatingGear", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Create the mating worm wheel"),
    ).CreateMatingGear = True

    var_set.addProperty(
        "App::PropertyInteger", "GearTeeth", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Number of teeth on mating gear"),
    ).GearTeeth = 30

    var_set.addProperty(
        "App::PropertyLength", "GearHeight", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Height/thickness of mating gear"),
    ).GearHeight = 10.0

    var_set.addProperty(
        "App::PropertyFloat", "Clearance", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Clearance factor"),
    ).Clearance = 0.1

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

    # Mating gear bore/keyway
    var_set.addProperty(
        "App::PropertyBool", "MatingBoreEnabled", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Enable bore in mating gear"),
    ).MatingBoreEnabled = True

    var_set.addProperty(
        "App::PropertyLength", "MatingBoreDiameter", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Bore diameter of mating gear"),
    ).MatingBoreDiameter = 5.0

    var_set.addProperty(
        "App::PropertyBool", "MatingKeywayEnabled", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Enable keyway in mating gear"),
    ).MatingKeywayEnabled = False

    var_set.addProperty(
        "App::PropertyLength", "MatingKeywayWidth", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Keyway width of mating gear"),
    ).MatingKeywayWidth = 2.0

    var_set.addProperty(
        "App::PropertyLength", "MatingKeywayDepth", "MatingGear",
        QT_TRANSLATE_NOOP("App::Property", "Keyway depth of mating gear"),
    ).MatingKeywayDepth = 1.0

    var_set.addProperty(
        "App::PropertyAngle", "LeadAngle", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Lead angle of worm thread"), 1,
    )
    var_set.setExpression("LeadAngle",
        "atan(Module * pi * NumberOfThreads / (WormDiameter * pi))")

    # WheelPhase now lives on the Regenerate object, not the VarSet.

    var_set.addProperty(
        "App::PropertyLength", "CenterDistance", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Distance between worm and wheel axes"), 1,
    )
    var_set.setExpression("CenterDistance",
        "WormDiameter / 2 + 1.25 * Module + Module * GearTeeth / 2")

    var_set.addProperty(
        "App::PropertyLength", "WheelPitchDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Pitch diameter of mating wheel"), 1,
    )
    var_set.setExpression("WheelPitchDiameter", "Module * GearTeeth")

    return var_set


class WormGearResult:
    """FeaturePython for auto-regeneration of worm gear."""

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = None
        self._last_wd = None
        self._last_nt = None
        self._last_pa = None
        self._last_len = None
        self._last_hl = None
        self._last_ch = None
        self._last_rh = None
        self._last_cm = None
        self._last_gt = None
        self._last_gh = None
        self._last_cl = None
        self._last_mb = None
        self._last_mbd = None
        self._last_mk = None
        self._last_mkw = None
        self._last_mkd = None
        self._watcher = None
        self._needs_rebuild = False
        self.Type = "WormGearResult"

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
        ).Version = "0.1"

        obj.addProperty(
            "App::PropertyString", "Status", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"), 1,
        )
        obj.addProperty("App::PropertyAngle","WheelPhase","Gear",
            QT_TRANSLATE_NOOP("App::Property","Wheel tooth phase offset (tweak for meshing)")).WheelPhase = 5.0

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
        self._last_m = self._last_wd = self._last_nt = None
        self._last_pa = self._last_len = self._last_hl = None
        self._last_rh = self._last_cm = None
        self._last_gt = self._last_gh = self._last_cl = None
        self._last_mb = self._last_mbd = self._last_mk = None
        self._last_mkw = self._last_mkd = None
        self._watcher = None
        self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last_m = float(v.Module.Value)
            self._last_wd = float(v.WormDiameter.Value)
            self._last_nt = int(v.NumberOfThreads)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_len = float(v.Length.Value)
            self._last_hl = float(v.HelixLength.Value)
            self._last_ch = bool(v.CenterHelix)
            self._last_rh = bool(v.RightHanded)
            self._last_cm = bool(v.CreateMatingGear)
            self._last_gt = int(v.GearTeeth)
            self._last_gh = float(v.GearHeight.Value)
            self._last_cl = float(v.Clearance)
            self._last_mb = bool(v.MatingBoreEnabled)
            self._last_mbd = float(v.MatingBoreDiameter.Value)
            self._last_mk = bool(v.MatingKeywayEnabled)
            self._last_mkw = float(v.MatingKeywayWidth.Value)
            self._last_mkd = float(v.MatingKeywayDepth.Value)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset(("Module", "WormDiameter", "NumberOfThreads",
                               "PressureAngle", "Length", "HelixLength",
                               "CenterHelix", "RightHanded", "CreateMatingGear",
                               "GearTeeth", "GearHeight", "Clearance",
                               "MatingBoreEnabled", "MatingBoreDiameter",
                               "MatingKeywayEnabled", "MatingKeywayWidth",
                               "MatingKeywayDepth")),
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

    def onChanged(self, fp, prop):
        if prop == "WheelPhase" and not self._rebuilding:
            try:
                bn = str(self.Object.BodyName)
                wb = fp.Document.getObject(f"{bn}_WormWheel")
                if wb:
                    wp = fp.WheelPhase.Value
                    base = wb.Placement.Base
                    r = App.Rotation(App.Vector(1,0,0),90) * App.Rotation(App.Vector(0,0,1), wp)
                    wb.Placement = App.Placement(base, r)
            except Exception:
                pass

    def _values_changed(self):
        v = self._getVarSet()
        if not v:
            return False
        if self._last_m is None:
            return True
        EPS = 1e-9
        return (abs(float(v.Module.Value) - self._last_m) > EPS or
                abs(float(v.WormDiameter.Value) - self._last_wd) > EPS or
                int(v.NumberOfThreads) != self._last_nt or
                abs(float(v.PressureAngle.Value) - self._last_pa) > EPS or
                abs(float(v.Length.Value) - self._last_len) > EPS or
                abs(float(v.HelixLength.Value) - self._last_hl) > EPS or
                bool(v.CenterHelix) != self._last_ch or
                bool(v.RightHanded) != self._last_rh or
                bool(v.CreateMatingGear) != self._last_cm or
                int(v.GearTeeth) != self._last_gt or
                abs(float(v.GearHeight.Value) - self._last_gh) > EPS or
                abs(float(v.Clearance) - self._last_cl) > EPS or
                bool(v.MatingBoreEnabled) != self._last_mb or
                abs(float(v.MatingBoreDiameter.Value) - self._last_mbd) > EPS or
                bool(v.MatingKeywayEnabled) != self._last_mk or
                abs(float(v.MatingKeywayWidth.Value) - self._last_mkw) > EPS or
                abs(float(v.MatingKeywayDepth.Value) - self._last_mkd) > EPS)

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
            self._last_wd = float(v.WormDiameter.Value)
            self._last_nt = int(v.NumberOfThreads)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_len = float(v.Length.Value)
            self._last_hl = float(v.HelixLength.Value)
            self._last_ch = bool(v.CenterHelix)
            self._last_rh = bool(v.RightHanded)
            self._last_cm = bool(v.CreateMatingGear)
            self._last_gt = int(v.GearTeeth)
            self._last_gh = float(v.GearHeight.Value)
            self._last_cl = float(v.Clearance)
            self._last_mb = bool(v.MatingBoreEnabled)
            self._last_mbd = float(v.MatingBoreDiameter.Value)
            self._last_mk = bool(v.MatingKeywayEnabled)
            self._last_mkw = float(v.MatingKeywayWidth.Value)
            self._last_mkd = float(v.MatingKeywayDepth.Value)

            if self._last_m <= 0 or self._last_wd <= 0 or self._last_len <= 0:
                self.Object.Status = "Invalid params"
                return

            body_name = str(self.Object.BodyName)
            doc = self.Object.Document

            self._stopWatcher()

            saved_placement = None
            saved_wheel_placement = None
            old = doc.getObject(body_name)
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
            # Save mating wheel placement before it gets destroyed by readyPart
            old_wheel = doc.getObject(f"{body_name}_WormWheel")
            if old_wheel:
                saved_wheel_placement = App.Placement(old_wheel.Placement)

            self.Object.Status = "Generating worm gear..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            parameters = {
                "module": self._last_m,
                "worm_diameter": self._last_wd,
                "num_threads": self._last_nt,
                "pressure_angle": self._last_pa,
                "length": self._last_len,
                "helix_length": self._last_hl,
                "center_helix": self._last_ch,
                "right_handed": self._last_rh,
                "bore_type": "none",
                "bore_diameter": float(v.BoreDiameter.Value),
                "keyway_width": float(v.KeywayWidth.Value),
                "keyway_depth": float(v.KeywayDepth.Value),
                "body_name": body_name,
                "create_mating_gear": self._last_cm,
                "gear_teeth": self._last_gt,
                "gear_height": self._last_gh,
                "clearance": self._last_cl,
                "wheel_phase": 0.0,
            }
            generateWormGearPart(doc, parameters)
            # Apply stored WheelPhase rotation to the wheel body
            try:
                wp = self.Object.WheelPhase.Value
                if abs(wp) > 0.001:
                    wb = doc.getObject(f"{body_name}_WormWheel")
                    if wb:
                        base = wb.Placement.Base
                        r = App.Rotation(App.Vector(1,0,0),90) * App.Rotation(App.Vector(0,0,1), wp)
                        wb.Placement = App.Placement(base, r)
            except Exception:
                pass

            body_out = doc.getObject(body_name)
            if body_out:
                bore_sk = util.createSketch(body_out, "Bore")
                bore_circle = bore_sk.addGeometry(
                    Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1),
                                float(v.BoreDiameter.Value) / 2.0), False)
                bore_sk.addConstraint(Sketcher.Constraint("Coincident", bore_circle, 3, -1, 1))
                cst = bore_sk.addConstraint(
                    Sketcher.Constraint("Diameter", bore_circle, float(v.BoreDiameter.Value)))
                bore_sk.setExpression(f"Constraints[{cst}]", f"<<{v.Name}>>.BoreDiameter")
                bore_pocket = util.createPocket(body_out, bore_sk, 200.0, "Bore")
                bore_pocket.Reversed = True
                bore_pocket.setExpression("Length", "200mm")
                bore_pocket.setExpression("Suppressed",
                    f"<<{v.Name}>>.BoreEnabled ? False : True")

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
                kw_sk.setExpression(f"Constraints[{cst}]",
                    f"<<{v.Name}>>.KeywayWidth / -2.0")
                cst = kw_sk.addConstraint(Sketcher.Constraint("DistanceY",
                    kw_lines[0], 1, -1, 1, -tiny))
                kw_sk.setExpression(f"Constraints[{cst}]",
                    f"<<{v.Name}>>.BoreDiameter / 2.0 - <<{v.Name}>>.KeywayDepth")
                cst = kw_sk.addConstraint(Sketcher.Constraint("DistanceX",
                    kw_lines[0], 2, -1, 1, tiny))
                kw_sk.setExpression(f"Constraints[{cst}]",
                    f"<<{v.Name}>>.KeywayWidth / 2.0")
                cst = kw_sk.addConstraint(Sketcher.Constraint("DistanceY",
                    kw_lines[1], 2, -1, 1, tiny))
                kw_sk.setExpression(f"Constraints[{cst}]",
                    f"<<{v.Name}>>.BoreDiameter / 2.0 + <<{v.Name}>>.KeywayDepth")
                kw_pocket = util.createPocket(body_out, kw_sk, 200.0, "Keyway")
                kw_pocket.Reversed = True
                kw_pocket.setExpression("Suppressed",
                    f"<<{v.Name}>>.KeywayEnabled ? False : True")
                body_out.Tip = kw_pocket

            if saved_placement:
                body_out = doc.getObject(body_name)
                if body_out:
                    body_out.Placement = saved_placement

            # Mating gear bore/keyway
            if self._last_cm:
                mate_name = f"{body_name}_WormWheel"
                mate_body = doc.getObject(mate_name)
                if mate_body:
                    mbore_sk = util.createSketch(mate_body, "Bore")
                    mbore_circle = mbore_sk.addGeometry(
                        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1),
                                    float(v.MatingBoreDiameter.Value) / 2.0), False)
                    mbore_sk.addConstraint(Sketcher.Constraint("Coincident", mbore_circle, 3, -1, 1))
                    cst = mbore_sk.addConstraint(Sketcher.Constraint("Diameter",
                        mbore_circle, float(v.MatingBoreDiameter.Value)))
                    mbore_sk.setExpression(f"Constraints[{cst}]",
                        f"<<{v.Name}>>.MatingBoreDiameter")
                    mbore_pocket = util.createPocket(mate_body, mbore_sk, 200.0, "Bore")
                    mbore_pocket.Reversed = True
                    mbore_pocket.setExpression("Suppressed",
                        f"<<{v.Name}>>.MatingBoreEnabled ? False : True")

                    mkw_sk = util.createSketch(mate_body, "Keyway")
                    pts2 = [App.Vector(-0.5, -0.5, 0), App.Vector(0.5, -0.5, 0),
                            App.Vector(0.5, 0.5, 0), App.Vector(-0.5, 0.5, 0)]
                    mkw_lines = []
                    for i in range(4):
                        mkw_lines.append(mkw_sk.addGeometry(
                            Part.LineSegment(pts2[i], pts2[(i + 1) % 4]), False))
                    for i in range(4):
                        mkw_sk.addConstraint(Sketcher.Constraint("Coincident",
                            mkw_lines[i], 2, mkw_lines[(i + 1) % 4], 1))
                    mkw_sk.addConstraint(Sketcher.Constraint("Horizontal", mkw_lines[0]))
                    mkw_sk.addConstraint(Sketcher.Constraint("Vertical", mkw_lines[1]))
                    mkw_sk.addConstraint(Sketcher.Constraint("Horizontal", mkw_lines[2]))
                    mkw_sk.addConstraint(Sketcher.Constraint("Vertical", mkw_lines[3]))
                    cst = mkw_sk.addConstraint(Sketcher.Constraint("DistanceX",
                        mkw_lines[0], 1, -1, 1, -tiny))
                    mkw_sk.setExpression(f"Constraints[{cst}]",
                        f"<<{v.Name}>>.MatingKeywayWidth / -2.0")
                    cst = mkw_sk.addConstraint(Sketcher.Constraint("DistanceY",
                        mkw_lines[0], 1, -1, 1, -tiny))
                    mkw_sk.setExpression(f"Constraints[{cst}]",
                        f"<<{v.Name}>>.MatingBoreDiameter / 2.0 - <<{v.Name}>>.MatingKeywayDepth")
                    cst = mkw_sk.addConstraint(Sketcher.Constraint("DistanceX",
                        mkw_lines[0], 2, -1, 1, tiny))
                    mkw_sk.setExpression(f"Constraints[{cst}]",
                        f"<<{v.Name}>>.MatingKeywayWidth / 2.0")
                    cst = mkw_sk.addConstraint(Sketcher.Constraint("DistanceY",
                        mkw_lines[1], 2, -1, 1, tiny))
                    mkw_sk.setExpression(f"Constraints[{cst}]",
                        f"<<{v.Name}>>.MatingBoreDiameter / 2.0 + <<{v.Name}>>.MatingKeywayDepth")
                    mkw_pocket = util.createPocket(mate_body, mkw_sk, 200.0, "Keyway")
                    mkw_pocket.Reversed = True
                    mkw_pocket.setExpression("Suppressed",
                        f"<<{v.Name}>>.MatingKeywayEnabled ? False : True")
                    mate_body.Tip = mkw_pocket

            # Restore mating wheel placement
            if saved_wheel_placement:
                wheel_out = doc.getObject(f"{body_name}_WormWheel")
                if wheel_out:
                    wheel_out.Placement = saved_wheel_placement

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


class WormGearCreateObject():
    def GetResources(self):
        return {'Pixmap': mainIcon, 'MenuText': "&Create Worm Gear", 'ToolTip': "Create parametric worm gear"}

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "WormGear_values"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"WormGear_values{count:03d}"
            count += 1

        varset = createWormGearVarSet(doc, unique_name)

        gen_name = "Regenerate"
        count = 1
        while doc.getObject(gen_name):
            gen_name = f"Regenerate{count:03d}"
            count += 1
        gear_obj = doc.addObject("Part::FeaturePython", gen_name)
        WormGearResult(gear_obj, varset)
        ViewProviderGearResult(gear_obj.ViewObject, mainIcon)

        gear_obj.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")

    def IsActive(self):
        return True

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
                doc = App.ActiveDocument
                params = self.GetParameters()
                bn = params["body_name"]
                # Save placements before regeneration
                saved_worm = None
                saved_wheel = None
                old_worm = doc.getObject(bn)
                if old_worm:
                    saved_worm = App.Placement(old_worm.Placement)
                old_wheel = doc.getObject(f"{bn}_WormWheel")
                if old_wheel:
                    saved_wheel = App.Placement(old_wheel.Placement)
                generateWormGearPart(doc, params)
                # Restore placements
                if saved_worm:
                    body = doc.getObject(bn)
                    if body:
                        body.Placement = saved_worm
                if saved_wheel:
                    wheel = doc.getObject(f"{bn}_WormWheel")
                    if wheel:
                        wheel.Placement = saved_wheel
                self.Dirty = False
                doc.recompute()
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