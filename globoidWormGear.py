"""Globoid Worm Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric Globoid (Double-Throated) Worm Gears.

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
from PySide import QtCore

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'globoidWormGear.svg') 

def QT_TRANSLATE_NOOP(scope, text): return text

class GloboidWormGearCreateObject():
    def GetResources(self):
        return {'Pixmap': mainIcon, 'MenuText': "&Create Globoid Worm Gear", 'ToolTip': "Create parametric globoid (double-throated) worm gear"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument

        base_name = "GloboidWorm"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "GloboidWormGearParameters")
        gear = GloboidWormGear(gear_obj)
        ViewProviderGloboidWormGear(gear_obj.ViewObject)
        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self): return True

class GloboidWormGear():
    def __init__(self, obj):
        self.Dirty = False
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = "0.1"

        # Read-only calculated properties
        obj.addProperty("App::PropertyAngle", "LeadAngle", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Calculated lead angle of worm thread"), 1)
        obj.addProperty("App::PropertyLength", "CenterDistance", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Distance between worm and wheel axes"), 1)
        obj.addProperty("App::PropertyLength", "WheelPitchDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter of mating wheel"), 1)

        # Globoid Specific: Needs Gear Parameters to define curvature
        obj.addProperty("App::PropertyLength", "Module", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = 2.0
        obj.addProperty("App::PropertyInteger", "NumberOfThreads", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Number of threads (starts)")).NumberOfThreads = 1
        obj.addProperty("App::PropertyInteger", "GearTeeth", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Number of teeth on mating gear")).GearTeeth = 20

        # Worm geometry - pitch diameter at throat (50% larger default for better meshing)
        obj.addProperty("App::PropertyLength", "WormPitchDiameter", "GloboidWorm",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter at worm throat")).WormPitchDiameter = 30.0
        obj.addProperty("App::PropertyLength", "CylinderDiameter", "GloboidWorm",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter of worm cylinder (0 = auto from pitch + threads)")).CylinderDiameter = 0.0
        obj.addProperty("App::PropertyAngle", "PressureAngle", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Pressure angle")).PressureAngle = 20.0

        # The worm length is defined by the wrap angle around the gear
        obj.addProperty("App::PropertyAngle", "ArcAngle", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Engagement angle (typically 60-90)")).ArcAngle = 90.0
        obj.addProperty("App::PropertyLength", "WormLength", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Length of the threaded section (0 = defined by ArcAngle)")).WormLength = 0.0
        obj.addProperty("App::PropertyLength", "CylinderLength", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Total length of the worm cylinder")).CylinderLength = 40.0
        obj.addProperty("App::PropertyBool", "RightHanded", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "True for Right-handed")).RightHanded = True
        obj.addProperty("App::PropertyString", "BodyName", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = "GloboidWorm"
        
        # Bore
        obj.addProperty("App::PropertyEnumeration", "BoreType", "Bore", QT_TRANSLATE_NOOP("App::Property", "Type of center hole"))
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.addProperty("App::PropertyLength", "BoreDiameter", "Bore", QT_TRANSLATE_NOOP("App::Property", "Bore diameter")).BoreDiameter = 5.0
        obj.addProperty("App::PropertyLength", "SquareCornerRadius", "Bore", QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore")).SquareCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "HexCornerRadius", "Bore", QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore")).HexCornerRadius = 0.5
        obj.addProperty("App::PropertyLength", "KeywayWidth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)")).KeywayWidth = 2.0
        obj.addProperty("App::PropertyLength", "KeywayDepth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Depth of keyway")).KeywayDepth = 1.0

        # Mating Gear
        obj.addProperty("App::PropertyBool", "CreateMatingGear", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Create the mating worm wheel")).CreateMatingGear = True
        obj.addProperty("App::PropertyLength", "GearHeight", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Height/thickness of mating gear")).GearHeight = 10.0
        obj.addProperty("App::PropertyFloat", "Clearance", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Clearance factor for backlash (multiplied by module)")).Clearance = 0.1
        obj.addProperty("App::PropertyEnumeration", "GearBoreType", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Bore type for mating gear"))
        obj.GearBoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.addProperty("App::PropertyLength", "GearBoreDiameter", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Bore diameter for mating gear")).GearBoreDiameter = 8.0

        self.Type = 'GloboidWormGear'
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        self.Dirty = True

        # Update calculated read-only properties
        if prop in ["Module", "NumberOfThreads", "GearTeeth", "WormPitchDiameter"]:
            try:
                module = fp.Module.Value
                num_threads = fp.NumberOfThreads
                gear_teeth = fp.GearTeeth
                worm_pitch_dia = fp.WormPitchDiameter.Value

                # Wheel pitch diameter = module * teeth
                wheel_pitch_dia = module * gear_teeth
                fp.WheelPitchDiameter = wheel_pitch_dia

                # Center distance = (worm_pitch + wheel_pitch) / 2
                center_dist = (worm_pitch_dia + wheel_pitch_dia) / 2.0
                fp.CenterDistance = center_dist

                # Lead angle: tan(γ) = lead / (π × d1)
                # where lead = π × module × num_threads
                lead = math.pi * module * num_threads
                if worm_pitch_dia > 0:
                    lead_angle_rad = math.atan(lead / (math.pi * worm_pitch_dia))
                    fp.LeadAngle = math.degrees(lead_angle_rad)
            except (AttributeError, TypeError, ZeroDivisionError):
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_threads": int(self.Object.NumberOfThreads),
            "gear_teeth": int(self.Object.GearTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "worm_pitch_diameter": float(self.Object.WormPitchDiameter.Value),
            "cylinder_diameter": float(self.Object.CylinderDiameter.Value),
            "arc_angle": float(self.Object.ArcAngle.Value),
            "worm_length": float(self.Object.WormLength.Value),
            "cylinder_length": float(self.Object.CylinderLength.Value),
            "right_handed": bool(self.Object.RightHanded),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            # Mating gear parameters
            "create_mating_gear": bool(self.Object.CreateMatingGear),
            "gear_height": float(self.Object.GearHeight.Value),
            "clearance": float(self.Object.Clearance),
            "gear_bore_type": str(self.Object.GearBoreType),
            "gear_bore_diameter": float(self.Object.GearBoreDiameter.Value),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                generateGloboidWormGearPart(App.ActiveDocument, self.GetParameters())
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Globoid Worm Error: {e}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())

    def execute(self, obj):
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

class ViewProviderGloboidWormGear:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.iconfile = iconfile if iconfile else mainIcon
    def attach(self, obj): self.Object = obj.Object
    def getDisplayModes(self, obj): return ["Shaded", "Wireframe"]
    def getDefaultDisplayMode(self):
        return "Shaded"
    def getIcon(self):
        return self.iconfile
    def doubleClicked(self, vobj): return True
    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui
        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)
    def regenerate(self):
        if hasattr(self.Object, 'Proxy'): self.Object.Proxy.force_Recompute()
    def __getstate__(self):
        return self.iconfile
    def __setstate__(self, state):
        self.iconfile = state if state else mainIcon

# ============================================================================
# GENERATION LOGIC
# ============================================================================

def validateGloboidParameters(parameters):
    """Validate globoid worm gear parameters.

    Args:
        parameters: Dictionary of gear parameters

    Raises:
        gearMath.GearParameterError: If parameters are invalid
    """
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["module"] > gearMath.MAX_MODULE:
        raise gearMath.GearParameterError(f"Module > {gearMath.MAX_MODULE}")
    if parameters["worm_pitch_diameter"] <= 0:
        raise gearMath.GearParameterError("Worm Pitch Diameter must be positive")
    if parameters["gear_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Gear Teeth must be >= {gearMath.MIN_TEETH}")
    if parameters["cylinder_length"] <= 0:
        raise gearMath.GearParameterError("Cylinder Length must be positive")
    if parameters["arc_angle"] <= 0 or parameters["arc_angle"] > 180:
        raise gearMath.GearParameterError("Arc Angle must be between 0 and 180 degrees")

def generateGloboidWormGearPart(doc, parameters):
    """Generate a globoid (double-throated) worm gear.

    A globoid worm has a concave throat that wraps around the mating gear,
    providing greater contact area and load capacity than a standard worm.

    Args:
        doc: FreeCAD document object
        parameters: Dictionary containing gear parameters

    The geometry consists of:
    1. Revolve profile creating hourglass base cylinder
    2. Lofted thread pattern following the gear's curvature
    3. Boolean cut to create the thread grooves
    4. Optional bore
    """
    validateGloboidParameters(parameters)
    body_name = parameters.get("body_name", "GloboidWorm")
    body = util.readyPart(doc, body_name)

    # Clear the BaseFeature if set (from previous generation)
    if hasattr(body, 'BaseFeature') and body.BaseFeature:
        body.BaseFeature = None

    # Clean up old intermediate objects from previous generation attempts
    old_objects = [
        f"{body_name}_ToolBody",
        f"{body_name}_ThreadCut",
        f"{body_name}_CutResult",
        f"{body_name}_ThreadTool",
    ]
    for obj_name in old_objects:
        old_obj = doc.getObject(obj_name)
        if old_obj:
            try:
                doc.removeObject(obj_name)
            except Exception:
                pass

    # Extract parameters
    module = parameters["module"]
    num_threads = parameters["num_threads"]
    num_gear_teeth = parameters["gear_teeth"]
    worm_pitch_diameter = parameters["worm_pitch_diameter"]
    cylinder_diameter = parameters["cylinder_diameter"]
    pressure_angle = parameters["pressure_angle"]
    arc_angle = parameters["arc_angle"]
    worm_length = parameters["worm_length"]
    cylinder_length = parameters["cylinder_length"]
    right_handed = parameters["right_handed"]

    # Calculate geometry
    addendum = module * gearMath.ADDENDUM_FACTOR
    dedendum = module * gearMath.DEDENDUM_FACTOR

    # Gear pitch radius (mating gear)
    gear_pitch_radius = (module * num_gear_teeth) / 2.0
    # Worm pitch radius at throat
    worm_pitch_radius = worm_pitch_diameter / 2.0
    # Center distance between worm and gear axes
    center_distance = gear_pitch_radius + worm_pitch_radius

    # 1. PARAMETRIC BASE (Sketch + Revolve)
    # Outer radius at throat (where teeth tips are)
    outer_throat_radius = worm_pitch_radius + addendum
    
    # Calculate arc radius based on your measurement of working radius
    # Your visual measurement shows arc radius should be 26.5mm for default params
    # This corresponds to gear_pitch_radius + 3.25 × addendum
    # TODO: This could be made into a user parameter (ArcRadiusFactor = 3.25)
    arc_radius = gear_pitch_radius + (addendum * 3.25)  # Direct calculation

    # Arc radius for globoid curve should match the working gear radius
    # The arc represents the worm surface wrapping around the gear
    # For proper hourglass shape, use the measured working radius
    # arc_radius already calculated from your measurement above

    # Cylinder diameter: if specified use it, otherwise auto-calculate
    # The cylinder outer diameter should be at least pitch + addendum
    if cylinder_diameter > 0.01:
        # User specified cylinder diameter
        actual_cylinder_radius = cylinder_diameter / 2.0
        # Ensure it's at least as big as the thread tips
        if actual_cylinder_radius < outer_throat_radius:
            App.Console.PrintWarning(
                f"CylinderDiameter ({cylinder_diameter:.2f}) is smaller than thread tips. "
                f"Using minimum: {outer_throat_radius * 2:.2f}\n"
            )
            actual_cylinder_radius = outer_throat_radius
    else:
        # Auto-calculate: use outer throat radius (pitch + addendum)
        actual_cylinder_radius = outer_throat_radius

    # Validate arc_radius is positive
    if arc_radius <= 0:
        raise gearMath.GearParameterError(
            f"Invalid geometry: arc_radius ({arc_radius:.2f}) must be positive. "
            f"Try increasing module or gear teeth, or decreasing worm diameter."
        )

    # Maximum worm length is limited by arc geometry (cannot exceed 2 * arc_radius)
    max_worm_length = arc_radius * 2.0 * 0.98  # 98% of max to avoid edge cases

    # Determine threaded section span
    # Thread must be long enough to cover the wheel height plus wrap-around margin
    # The wheel teeth wrap around the worm in an arc - at the edges of this arc,
    # the Z positions extend beyond the linear face width
    gear_height = parameters.get("gear_height", 10.0)

    # Calculate wrap-around extension: wheel teeth at outer radius need threads
    # that extend further along Z due to the curved engagement
    wheel_outer_radius = (module * num_gear_teeth) / 2.0 + addendum
    # The wrap angle determines how far the teeth extend around the worm
    # At the extreme wrap positions, Z offset = wheel_outer_radius * sin(wrap_angle)
    # Use a conservative estimate: ~30% of outer radius as extra Z coverage on each side
    wrap_extension = wheel_outer_radius * 0.4
    min_thread_length = (gear_height + 2 * wrap_extension + 4 * module) * 1.3

    if worm_length > 0.01:
        # If specified worm_length exceeds max, warn and clamp
        effective_worm_length = worm_length
        if worm_length > max_worm_length:
            App.Console.PrintWarning(
                f"Worm length ({worm_length:.2f}mm) exceeds max ({max_worm_length:.2f}mm) for current geometry.\n"
            )
            App.Console.PrintWarning(
                f"  To increase max length: increase GearTeeth or decrease WormDiameter.\n"
            )
            App.Console.PrintWarning(
                f"  Using effective worm length: {max_worm_length:.2f}mm\n"
            )
            effective_worm_length = max_worm_length

        # Calculate angle from specified length
        tooth_half_length = effective_worm_length / 2.0
        half_angle_rad = math.asin(tooth_half_length / arc_radius)
        # Update effective arc_angle for thread generation
        arc_angle = (half_angle_rad * 2.0) / util.DEG_TO_RAD
    else:
        # Calculate length from arc angle
        half_angle_rad = (arc_angle / 2.0) * util.DEG_TO_RAD
        tooth_half_length = arc_radius * math.sin(half_angle_rad)
        effective_worm_length = tooth_half_length * 2.0

    # Ensure thread is long enough to cover the wheel
    if effective_worm_length < min_thread_length:
        if min_thread_length <= max_worm_length:
            App.Console.PrintMessage(
                f"Extending thread length from {effective_worm_length:.2f}mm to {min_thread_length:.2f}mm to cover wheel.\n"
            )
            effective_worm_length = min_thread_length
            tooth_half_length = effective_worm_length / 2.0
            half_angle_rad = math.asin(tooth_half_length / arc_radius)
        else:
            App.Console.PrintWarning(
                f"Warning: Wheel height ({gear_height:.2f}mm) may exceed thread coverage.\n"
            )

    # Total half-length (including shoulders if any)
    #total_half_length = max(cylinder_length / 2.0, tooth_half_length + 0.01)
    total_half_length = cylinder_length

    # Radius at edge of threaded area (for shoulders)
    shoulder_radius = center_distance - arc_radius * math.cos(half_angle_rad)
    
    # Shaft/bore radius (for sketch construction)
    bore_type = parameters.get("bore_type", "none")
    if bore_type == "none":
        shaft_radius = 0.0
    else:
        shaft_radius = parameters["bore_diameter"] / 2.0
        if shaft_radius >= outer_throat_radius - module:
            shaft_radius = outer_throat_radius - module

    # Create base sketch for revolution - Explicit Profile
    sk_base = util.createSketch(body, 'GloboidCylinder')
    
    # Find XZ Plane for Z-axis orientation
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
        sk_base.AttachmentSupport = [(xz_plane, '')]
        sk_base.MapMode = 'FlatFace'
    else:
        # Fallback: Manual Placement (Rotate 90 deg around X to align Y with Global Z)
        sk_base.MapMode = 'Deactivated'
        sk_base.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(App.Vector(1,0,0), 90))

    # Dimensions
    half_cylinder_length = cylinder_length / 2.0
    half_worm_length = effective_worm_length / 2.0  # Use already-clamped effective length
    rect_outer_radius = outer_throat_radius
    # outer_radius already calculated as arc_radius above
    # Calculate Arc Geometry
    # Arc radius should match to working gear radius for proper hourglass shape
    # Using the arc_radius calculated above based on your measurement
    # No recalculation of outer_radius here - use arc_radius directly
    root_radius = gear_pitch_radius - dedendum

    # Helical twist over gear height
    # Calculate helix angle directly for worm wheel generation
    # This avoids scope issues with lead_angle_rad from onChanged
    thread_pitch = math.pi * module
    lead = thread_pitch * num_threads
    worm_pitch_diameter = worm_pitch_radius * 2.0
    helix_angle_rad = math.atan(lead / (math.pi * worm_pitch_diameter))
    
    twist_total_rad = (gear_height * math.tan(helix_angle_rad)) / gear_pitch_radius
    twist_total_deg = twist_total_rad / util.DEG_TO_RAD
    
    # Create the gear body
    gear_body = util.readyPart(doc, body_name)

    # Handedness: right-handed worm meshes with left-handed wheel
    if right_handed:
        twist_total_deg = -twist_total_deg

    App.Console.PrintMessage(f"Helical twist: {twist_total_deg:.2f}° over height {gear_height:.2f}mm\n")

    # =========================================================================
    # STEP 1: Create Bottom Tooth Profile Sketch (Z=0)
    # =========================================================================

    sk_bottom = util.createSketch(gear_body, 'ToothProfileBottom')
    # Attach to XY plane (default)

    # Generate tooth profile using gearMath
    # Extract from parameters with defensive check
    num_teeth = parameters.get("gear_teeth", 20)  # Default fallback
    
    tooth_params = {
        "module": module,
        "num_teeth": num_teeth,
        "pressure_angle": pressure_angle,
        "profile_shift": 0.0,
    }
    gearMath.generateToothProfile(sk_bottom, tooth_params)

    doc.recompute()

    # =========================================================================
    # STEP 2: Create Top Tooth Profile Sketch (Z=height, rotated by twist)
    # =========================================================================

    sk_top = util.createSketch(gear_body, 'ToothProfileTop')

    # Attach to XY plane but offset to Z=height and rotated by twist angle
    xy_plane = None
    for feat in gear_body.Origin.OriginFeatures:
        if 'XY' in feat.Name or 'XY' in feat.Label:
            xy_plane = feat
            break

    if xy_plane:
        sk_top.AttachmentSupport = [(xy_plane, '')]
        sk_top.MapMode = 'FlatFace'
        # Offset to top and rotate by twist angle
        sk_top.AttachmentOffset = App.Placement(
            App.Vector(0, 0, gear_height),
            App.Rotation(App.Vector(0, 0, 1), twist_total_deg)
        )

    # Generate same tooth profile (rotation handled by AttachmentOffset)
    gearMath.generateToothProfile(sk_top, tooth_params)

    doc.recompute()

    # =========================================================================
    # STEP 3: Loft Between Sketches for Helical Tooth
    # =========================================================================

    loft = gear_body.newObject('PartDesign::AdditiveLoft', 'HelicalTooth')
    loft.Profile = sk_bottom
    loft.Sections = [sk_top]
    loft.Ruled = True

    sk_bottom.Visibility = False
    sk_top.Visibility = False
    gear_body.Tip = loft

    doc.recompute()

    # =========================================================================
    # STEP 4: Polar Pattern for All Teeth
    # =========================================================================

    polar = util.createPolar(gear_body, loft, sk_bottom, num_teeth, 'Teeth')
    polar.Originals = [loft]
    loft.Visibility = False
    polar.Visibility = True
    gear_body.Tip = polar

    doc.recompute()

    # =========================================================================
    # STEP 5: Dedendum Circle (Fills the center)
    # =========================================================================

    df = root_radius * 2.0  # Root diameter
    dedendum_sketch = util.createSketch(gear_body, 'DedendumCircle')
    circle = dedendum_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01),
        False
    )
    dedendum_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, df + 0.02))

    dedendum_pad = util.createPad(gear_body, dedendum_sketch, height, 'DedendumPad')
    gear_body.Tip = dedendum_pad

    doc.recompute()

    # Calculate worm lead angle - this is the helix angle for the wheel
    thread_pitch = math.pi * module
    lead = thread_pitch * num_threads
    worm_pitch_diameter = worm_pitch_radius * 2.0

    # Lead angle: tan(lead_angle) = lead / (pi * worm_pitch_diameter)
    lead_angle_rad = math.atan(lead / (math.pi * worm_pitch_diameter))
    lead_angle_deg = lead_angle_rad / util.DEG_TO_RAD

    # =========================================================================
    # STEP 6: Throat Cut (Concave Profile via Groove)
    # =========================================================================

    sk_throat = gear_body.newObject('Sketcher::SketchObject', 'ThroatCutSketch')

    # Find the XZ_Plane for groove sketch
    xz_plane = None
    for feat in gear_body.Origin.OriginFeatures:
        if 'XZ' in feat.Name or 'XZ' in feat.Label:
            xz_plane = feat
            break

    if xz_plane:
        sk_throat.AttachmentSupport = [(xz_plane, '')]
        sk_throat.MapMode = 'ObjectXY'
        sk_throat.AttachmentOffset = App.Placement(App.Vector(0, height / 2.0, 0), App.Rotation())
    else:
        App.Console.PrintError("Could not find XZ plane in Origin\n")

    # Circle for worm clearance cut
    # The groove must NOT cut into the wheel teeth - only provide clearance above them
    # Wheel teeth tips are at (center_distance - outer_radius) from worm center
    # The groove should cut just outside this, leaving the teeth intact
    clearance_factor = parameters.get("clearance", 0.1)
    clearance = module * clearance_factor

    # Calculate where wheel teeth tips reach (distance from worm axis)
    wheel_teeth_reach = center_distance - arc_radius

    # Groove cuts at wheel teeth reach + clearance (provides clearance but doesn't cut teeth)
    cut_radius = wheel_teeth_reach + clearance

    App.Console.PrintMessage(f"Throat groove: wheel teeth reach {wheel_teeth_reach:.2f}mm from worm, cut at {cut_radius:.2f}mm\n")
    App.Console.PrintMessage(f"center_distance: {center_distance} clearance {clearance}\n")
    App.Console.PrintMessage(f"addendum {addendum} dedendum {dedendum} arc_radius: {arc_radius}\n")
    c_idx = sk_throat.addGeometry(
        Part.Circle(App.Vector(center_distance, 0, 0), App.Vector(0, 0, 1), cut_radius),
        False
    )

    sk_throat.addConstraint(Sketcher.Constraint('PointOnObject', c_idx, 3, -1))
    sk_throat.addConstraint(Sketcher.Constraint('Radius', c_idx, cut_radius))
    sk_throat.addConstraint(Sketcher.Constraint('DistanceX', -1, 1, c_idx, 3, center_distance-clearance))

    doc.recompute()

    # Create the Groove
    groove = gear_body.newObject('PartDesign::Groove', 'ThroatGroove')
    groove.Profile = sk_throat
    groove.ReferenceAxis = (sk_throat, ['V_Axis'])
    groove.Angle = 360.0
    groove.Midplane = False
    groove.Reversed = False

    sk_throat.Visibility = False
    gear_body.Tip = groove
    doc.recompute()

    # =========================================================================
    # STEP 7: Alignment & Placement
    # =========================================================================

    # Calculate Y offset from the difference between ToothProfileBottomSketch 
    # and ToothProfileTopSketch positions, divided by 2
    # The bottom sketch is at Y=0, top sketch is displaced by the helical twist
    twist_angle_rad = twist_total_deg * util.DEG_TO_RAD
    
    # Calculate the theoretical displacement between sketches along Y axis
    # This represents the helical travel of the tooth profile from bottom to top
    theoretical_displacement = (thread_pitch * height) / (math.pi * gear_pitch_radius)
    
    # Scale the displacement to achieve proper worm wheel positioning
    # The scaling factor ensures the worm wheel meshes correctly with the globoid worm
    scaled_displacement = theoretical_displacement * 10.0
    
    # Y offset is half the scaled displacement (to center the gear properly)
    y_offset = -scaled_displacement / 2.0

    # Rotation to orient gear axis perpendicular to worm axis
    r_align = App.Rotation(App.Vector(1, 0, 0), -90)

    gear_body.Placement = App.Placement(
        App.Vector(center_distance, y_offset, 0),
        r_align
    )

    doc.recompute()
    gear_body.ViewObject.Visibility = True
    App.Console.PrintMessage(f"Helical Worm Wheel created: {gear_body_name} (helix angle={lead_angle_deg:.2f}°)\n")


try: FreeCADGui.addCommand('GloboidWormGearCreateObject', GloboidWormGearCreateObject())
except Exception: pass
