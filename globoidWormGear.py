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

    # Arc radius for globoid curve (centered at gear center)
    # For proper hourglass shape, the arc radius should be approximately equal to the gear pitch radius
    # This creates a more pronounced globoid shape that properly wraps around the gear
    arc_radius = gear_pitch_radius * 0.9  # Slightly smaller than gear pitch radius for proper wrapping

    # Validate arc_radius is positive
    if arc_radius <= 0:
        raise gearMath.GearParameterError(
            f"Invalid geometry: arc_radius ({arc_radius:.2f}) must be positive. "
            f"Try increasing module or gear teeth, or decreasing worm diameter."
        )

    # Maximum worm length is limited by arc geometry (cannot exceed 2 * arc_radius)
    max_worm_length = arc_radius * 2.0 * 0.98  # 98% of max to avoid edge cases

    # Determine threaded section span
    # Thread must be long enough to cover the wheel height plus margin
    # Add 20% extra length to ensure full engagement with wheel teeth
    gear_height = parameters.get("gear_height", 10.0)
    min_thread_length = (gear_height + 4 * module) * 1.2  # 20% longer, plus margin on each side

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
    total_half_length = max(cylinder_length / 2.0, tooth_half_length + 0.01)

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

    # Calculate Arc Geometry
    arc_center = App.Vector(-center_distance, 0.0, 0)
    angle_span = 2.0 * half_angle_rad  # Already calculated from effective_worm_length
    # Angles for Part.ArcOfCircle (counter-clockwise from X-axis)
    # We want a curve to the left. Center is at -CD.
    # The arc bulges towards +X.
    # Actually, let's stick to the previous correct geometry:
    # Center at -CD. Radius R.
    # We want the arc segment that is closest to the axis (smallest X).
    # That is around angle 0.
    start_angle = -angle_span / 2.0
    end_angle = angle_span / 2.0

    # GEOMETRY CREATION (Counter-clockwise loop)
    geoList = []
    
    # 1. Right Line (Axis) - Upwards
    # From (0, -Len/2) to (0, Len/2)
    p_br_axis = App.Vector(0, -half_cylinder_length, 0)
    p_tr_axis = App.Vector(0, half_cylinder_length, 0)
    geoList.append(Part.LineSegment(p_br_axis, p_tr_axis))
    
    # 2. Top Line - Leftwards
    # From (0, Len/2) to (-OuterR, Len/2)
    p_tl_corner = App.Vector(-rect_outer_radius, half_cylinder_length, 0)
    geoList.append(Part.LineSegment(p_tr_axis, p_tl_corner))

    # 3. Top-Left Vertical Line - Downwards
    # From (-OuterR, Len/2) to Arc Start (-OuterR, WormLen/2) ??
    # Wait, the Arc is curved. The vertical line connects to the Arc EndPoint.
    # The Arc EndPoint X is determined by the arc radius and angle.
    # X = -CD + R*cos(end_angle). Y = R*sin(end_angle) = WormLen/2
    # So the vertical line goes from Top Corner to Arc Top.
    
    # Calculate Arc End Points
    # Top Point (End of Arc)
    arc_top_y = arc_radius * math.sin(end_angle)
    arc_top_x = -center_distance + arc_radius * math.cos(end_angle)
    p_arc_top = App.Vector(arc_top_x, arc_top_y, 0)
    
    # Bottom Point (Start of Arc)
    arc_bot_y = arc_radius * math.sin(start_angle)
    arc_bot_x = -center_distance + arc_radius * math.cos(start_angle)
    p_arc_bot = App.Vector(arc_bot_x, arc_bot_y, 0)
    
    # Line 3: From Top Corner to Arc Top
    geoList.append(Part.LineSegment(p_tl_corner, p_arc_top))
    
    # 4. The Arc - Downwards?
    # Sketcher arcs usually go CCW. 
    # If we want a contiguous loop, we need to order points carefully.
    # Current loop: Axis(Up) -> Top(Left) -> TL_Vert(Down) -> Arc(Down) -> BL_Vert(Down) -> Bot(Right)
    # Arc needs to go from Top to Bottom.
    # Part.ArcOfCircle(circle, start, end) goes CCW from start to end.
    # Start(-ang) is Bottom. End(+ang) is Top.
    # So ArcOfCircle goes Bottom -> Top.
    # We need Top -> Bottom.
    # We can add the curve, but we need to constrain it correctly.
    # Let's add it as is (Bottom->Top) but constrain the endpoints to match the loop direction.
    circle_base = Part.Circle(arc_center, App.Vector(0, 0, 1), arc_radius)
    arc_geo = Part.ArcOfCircle(circle_base, start_angle, end_angle)
    geoList.append(arc_geo)
    
    # 5. Bottom-Left Vertical Line
    # From Arc Bottom to Bottom Corner
    p_bl_corner = App.Vector(-rect_outer_radius, -half_cylinder_length, 0)
    geoList.append(Part.LineSegment(p_arc_bot, p_bl_corner))
    
    # 6. Bottom Line - Rightwards
    # From Bottom Corner to Axis Bottom
    geoList.append(Part.LineSegment(p_bl_corner, p_br_axis))
    
    # Add all geometry
    # Indices:
    # 0: Right Line (Axis)
    # 1: Top Line
    # 2: Top-Left Vertical
    # 3: Arc (Start=Bot, End=Top)
    # 4: Bot-Left Vertical
    # 5: Bottom Line
    idx_right = 0
    idx_top = 1
    idx_tl = 2
    idx_arc = 3
    idx_bl = 4
    idx_bot = 5
    
    sk_base.addGeometry(geoList, False)
    
    # CONSTRAINTS
    
    # 1. Coincident Connections
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_right, 2, idx_top, 1))
    # Top End -> TL Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_top, 2, idx_tl, 1))
    # TL End -> Arc End (Top)
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_tl, 2, idx_arc, 2))
    # Arc Start (Bot) -> BL Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_arc, 1, idx_bl, 1))
    # BL End -> Bot Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_bl, 2, idx_bot, 1))
    # Bot End -> Right Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_bot, 2, idx_right, 1))
    
    # 2. Geometric Constraints
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_right))
    sk_base.addConstraint(Sketcher.Constraint('Horizontal', idx_top))
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_tl))
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_bl))
    sk_base.addConstraint(Sketcher.Constraint('Horizontal', idx_bot))
    
    # 3. Placement Constraints
    # Right Line on Y Axis - REMOVED (Redundant with Symmetry/Vertical?)
    # sk_base.addConstraint(Sketcher.Constraint('PointOnObject', idx_right, 1, -2)) 
    
    # Arc Center on X Axis (Horizontal alignment with Origin) - ADDED per Option A
    sk_base.addConstraint(Sketcher.Constraint('PointOnObject', idx_arc, 3, -1))
    
    # 4. Dimensional Constraints
    # Cylinder Length (Right Line Length)
    cst_len = sk_base.addConstraint(Sketcher.Constraint('DistanceY', idx_right, 1, idx_right, 2, cylinder_length))
    sk_base.setExpression(f'Constraints[{cst_len}]', 'GloboidWormGearParameters.CylinderLength')
    
    # Symmetry for Cylinder (Right Line midpoint on Origin)
    sk_base.addConstraint(Sketcher.Constraint('Symmetric', idx_right, 1, idx_right, 2, -1, 1))
    
    # Constrain Arc Radius.
    cst_rad = sk_base.addConstraint(Sketcher.Constraint('Radius', idx_arc, arc_radius))
    
    # Constrain Arc Center Distance
    cst_cd = sk_base.addConstraint(Sketcher.Constraint('DistanceX', idx_arc, 3, idx_right, 1, center_distance))
    
    # Worm Length (Vertical Span of Arc) - use effective_worm_length which is clamped to valid range
    cst_worm_len = sk_base.addConstraint(Sketcher.Constraint('DistanceY', idx_arc, 1, idx_arc, 2, effective_worm_length))
    # Only link to property if worm_length wasn't clamped (otherwise expression would override our clamping)
    if worm_length > 0.01 and worm_length <= max_worm_length:
        sk_base.setExpression(f'Constraints[{cst_worm_len}]', 'GloboidWormGearParameters.WormLength')
    
    # Vertical Alignment for Arc Endpoints (Ensures symmetry about X-axis without overconstraining)
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_arc, 1, idx_arc, 2))

    # Removed: Symmetry for Arc - redundant with explicit arc center position + worm length span
    # Arc endpoints are fully determined by: center position, radius, and vertical span

    # Removed: Block constraint - not parametric, causes overconstraint

    doc.recompute()

    # Check if sketch solved successfully
    if sk_base.Shape.isNull():
        App.Console.PrintError(f"GloboidCylinder sketch failed to solve. Geometry params:\n")
        App.Console.PrintError(f"  arc_radius={arc_radius:.2f}, effective_worm_length={effective_worm_length:.2f}\n")
        App.Console.PrintError(f"  half_angle_rad={half_angle_rad:.4f}, angle_span={angle_span:.4f}\n")
        App.Console.PrintError(f"  center_distance={center_distance:.2f}, outer_throat_radius={outer_throat_radius:.2f}\n")
        raise gearMath.GearParameterError("Sketch failed to solve - check parameter combination")

    # 1. REVOLUTION - Create using Part module (outside the body)
    # We'll do the boolean cut in Part space, then import the result as BaseFeature
    # This is cleaner than mixing PartDesign and Part operations

    # First, create the revolution shape from the sketch
    # Get the sketch wire/face
    sk_base_shape = sk_base.Shape

    # Create revolution using Part module
    # Revolve around Z-axis (vertical axis in XZ plane sketch)
    rev_axis = App.Vector(0, 0, 1)
    rev_center = App.Vector(0, 0, 0)

    # Make a face from the sketch wire and revolve it
    try:
        sketch_face = Part.Face(sk_base_shape)
        rev_shape = sketch_face.revolve(rev_center, rev_axis, 360)
    except Exception as e:
        App.Console.PrintError(f"Revolution failed: {e}\n")
        App.Console.PrintError(f"Sketch wire count: {len(sk_base_shape.Wires)}, Edge count: {len(sk_base_shape.Edges)}\n")
        raise gearMath.GearParameterError(f"Cannot create revolution: {e}")

    # 2. THREAD GENERATION (B-Rep Loft)
    # Create Thread Profile Sketch
    sk_thread_profile = util.createSketch(body, 'ThreadProfile')
    sk_thread_profile.MapMode = 'Deactivated' # Sketch is standalone, its placement is handled by transformation in loop
    
    # Calculate thread profile geometry (trapezoidal cross-section - the 'gap')
    tan_pressure = math.tan(pressure_angle * util.DEG_TO_RAD)
    
    # Half-width at pitch line, reduced slightly for clearance
    half_width_pitch_line = (math.pi * module) / 4.0 - (0.05 * module)

    # Parametric values for the trapezoid in sketch space
    # In this sketch: X-axis = Height/Depth, Y-axis = Width (Chris's interpretation)
    profile_height = dedendum + addendum
    
    # The trapezoid will start at X=0 in the sketch for simplicity, 
    # its final radial position handled by transformations.
    offset_x = 0 

    # Half-width of the gap at the root (narrower)
    width_root = half_width_pitch_line - (dedendum * tan_pressure) 
    # Half-width of the gap at the tip (wider)
    width_tip = half_width_pitch_line + (addendum * tan_pressure) 

    # Define the 4 points of the trapezoid (closed profile)
    # Points ordered so both vertical lines go from -Y to +Y (consistent direction)
    # P1 = Root, -Y    P2 = Root, +Y    P3 = Tip, +Y    P4 = Tip, -Y
    p1 = App.Vector(offset_x, -width_root, 0)                  # Root line start (-Y)
    p2 = App.Vector(offset_x, width_root, 0)                   # Root line end (+Y)
    p3 = App.Vector(offset_x + profile_height, width_tip, 0)   # Tip, +Y
    p4 = App.Vector(offset_x + profile_height, -width_tip, 0)  # Tip, -Y

    # Add lines to sketch - note top_line goes from p4 to p3 (same -Y to +Y direction as bottom)
    idx_bottom_line = sk_thread_profile.addGeometry(Part.LineSegment(p1, p2), False)   # Geo 0: Root line (-Y to +Y)
    idx_right_flank = sk_thread_profile.addGeometry(Part.LineSegment(p2, p3), False)   # Geo 1: Right flank
    idx_top_line = sk_thread_profile.addGeometry(Part.LineSegment(p4, p3), False)      # Geo 2: Tip line (-Y to +Y) FIXED
    idx_left_flank = sk_thread_profile.addGeometry(Part.LineSegment(p4, p1), False)    # Geo 3: Left flank
    
    # CONSTRAINTS for ThreadProfile sketch
    
    # 1. Coincident Connections (Close the loop)
    # bottom_line: p1->p2, right_flank: p2->p3, top_line: p4->p3, left_flank: p4->p1
    sk_thread_profile.addConstraint(Sketcher.Constraint('Coincident', idx_bottom_line, 2, idx_right_flank, 1)) # P2: bottom end = right start
    sk_thread_profile.addConstraint(Sketcher.Constraint('Coincident', idx_right_flank, 2, idx_top_line, 2))   # P3: right end = top end
    sk_thread_profile.addConstraint(Sketcher.Constraint('Coincident', idx_top_line, 1, idx_left_flank, 1))    # P4: top start = left start
    sk_thread_profile.addConstraint(Sketcher.Constraint('Coincident', idx_left_flank, 2, idx_bottom_line, 1)) # P1: left end = bottom start
    
    # 2. Symmetry Constraints
    # Center the 'bottom_line' and 'top_line' symmetrically around the X-axis (horizontal axis)
    # Reference -1 = X-axis (NOT -1,1 which is Origin point!)
    sk_thread_profile.addConstraint(Sketcher.Constraint('Symmetric', idx_bottom_line, 1, idx_bottom_line, 2, -1))
    sk_thread_profile.addConstraint(Sketcher.Constraint('Symmetric', idx_top_line, 1, idx_top_line, 2, -1)) 

    # 3. Dimensional Constraints
    # X-Position of bottom line (anchors the trapezoid position)
    sk_thread_profile.addConstraint(Sketcher.Constraint('DistanceX', -1, 1, idx_bottom_line, 1, offset_x))
    # Height of the trapezoid (distance between bottom and top lines)
    sk_thread_profile.addConstraint(Sketcher.Constraint('DistanceX', idx_bottom_line, 1, idx_top_line, 1, profile_height))

    # Y-Dimensions (Widths)
    # Length of the 'bottom_line' line (root width)
    sk_thread_profile.addConstraint(Sketcher.Constraint('DistanceY', idx_bottom_line, 1, idx_bottom_line, 2, width_root * 2))
    # Length of the 'top_line' line (tip width)
    sk_thread_profile.addConstraint(Sketcher.Constraint('DistanceY', idx_top_line, 1, idx_top_line, 2, width_tip * 2))

    doc.recompute()

    # Thread helix: one complete thread wraps around the worm over a distance of (pitch * num_threads)
    # Pitch = pi * module for a worm
    thread_pitch = math.pi * module

    # For the worm_length, how many degrees does the thread rotate?
    # One full wrap (360 deg) covers distance = thread_pitch
    # Use effective_worm_length (already clamped to valid range)
    worm_rotation_angle = 360.0 * effective_worm_length / thread_pitch

    # Calculate loft parameters
    # Number of cross-sections for loft (more = smoother thread)
    # Need enough steps to handle the rotation smoothly
    # At least 10 steps per 360 degrees of rotation
    min_steps_per_rotation = 10
    rotations = worm_rotation_angle / 360.0
    loft_steps = max(20, int(rotations * min_steps_per_rotation * 4))

    App.Console.PrintMessage(f"Thread params: pitch={thread_pitch:.2f}, length={effective_worm_length:.2f}, rotation={worm_rotation_angle:.1f} deg, loft_steps={loft_steps}\n")
    App.Console.PrintMessage(f"Geometry: outer_throat_radius={outer_throat_radius:.2f}, arc_radius={arc_radius:.2f}, center_distance={center_distance:.2f}\n")
    App.Console.PrintMessage(f"Profile: height={profile_height:.2f}, width_root={width_root:.2f}, width_tip={width_tip:.2f}\n")

    # Now extract the geometry from the sketch
    # We need to get the profile points in the correct order for lofting
    # The sketch has 4 points forming a trapezoid, but Wire.Vertexes may not be in perimeter order

    # Get the 4 corner points from the sketch geometry directly
    # Based on how we created the sketch:
    # p1 = (0, -width_root)  - root, bottom
    # p2 = (0, +width_root)  - root, top
    # p3 = (profile_height, +width_tip)  - tip, top
    # p4 = (profile_height, -width_tip)  - tip, bottom

    # For a proper closed loop going clockwise: p1 -> p4 -> p3 -> p2 -> p1
    # Or counter-clockwise: p1 -> p2 -> p3 -> p4 -> p1

    # Define the points in order around the perimeter (clockwise when viewed from +X)
    # This ensures the loft connects corresponding points correctly
    # Going: root-bottom -> root-top -> tip-top -> tip-bottom
    profile_points = [
        App.Vector(0, -width_root, 0),            # root, -Y side
        App.Vector(profile_height, -width_tip, 0), # tip, -Y side
        App.Vector(profile_height, width_tip, 0),  # tip, +Y side
        App.Vector(0, width_root, 0),              # root, +Y side
    ]

    App.Console.PrintMessage(f"Thread profile points (ordered):\n")
    for i, p in enumerate(profile_points):
        App.Console.PrintMessage(f"  P{i}: ({p.x:.2f}, {p.y:.2f})\n")

    # For a globoid worm:
    # - Worm axis is now along Z (length direction)
    # - Thread wraps helically around Z-axis
    # - Profile is perpendicular to helix path
    # - Worm throat is at X (radial direction)

    # Handedness direction factor
    direction_factor = 1.0 if right_handed else -1.0

    # Generate thread profile at multiple positions along the worm
    wires = []
    for i in range(loft_steps + 1):
        # Parameter from -0.5 to +0.5 along the worm length
        t = (i / loft_steps) - 0.5

        # Z position along worm axis (use effective_worm_length which is already clamped)
        z_pos = t * effective_worm_length

        # Helix angle: worm rotates as we move along Z
        # Total rotation over worm_length is worm_rotation_angle
        # Apply direction factor for handedness
        helix_angle_deg = t * worm_rotation_angle * direction_factor
        helix_angle_rad = helix_angle_deg * util.DEG_TO_RAD

        # Helix rotation around Z-axis (same for all points in this cross-section)
        cos_h = math.cos(helix_angle_rad)
        sin_h = math.sin(helix_angle_rad)

        pts_transformed = []
        for p in profile_points:
            # Profile point coordinates:
            # p.x = radial depth (0 at root/narrow, profile_height at tip/wide)
            # p.y = width along thread direction (symmetric about 0)

            # The profile width (p.y) runs along the worm axis (Z direction)
            # It does NOT rotate with the helix - stays parallel to Z-axis
            actual_z = z_pos + p.y

            # For globoid worm, the radius varies along Z (hourglass shape)
            # Each point must use the radius at ITS actual Z position
            if abs(actual_z) <= arc_radius * 0.999:  # Within the arc region
                local_radius = center_distance - math.sqrt(arc_radius**2 - actual_z**2)
            else:
                # Outside arc region - use the shoulder radius
                local_radius = shoulder_radius

            # The thread tool cuts INTO the cylinder surface
            # p.x=0 is the narrow end (root of gap) - at the bottom of the groove (below surface)
            # p.x=profile_height is the wide end (tip of gap) - at the surface
            # But for boolean cut to work, the tool must extend OUTSIDE the cylinder
            # So we add clearance: root goes below surface, tip goes above surface
            # REDUCED CLEARANCE: Large clearance shifts the tool out, making the cut narrower at surface (flat teeth)
            clearance = module * 0.1 
            radial_pos = local_radius - profile_height + p.x + clearance

            # Position in worm frame (Z-axis is worm axis)
            # Only the radial position rotates around Z-axis by helix angle
            # The Z position (axial) stays fixed - profile width is parallel to axis
            # Rotation in XY plane:
            px = radial_pos * cos_h
            py = radial_pos * sin_h
            pz = actual_z

            pts_transformed.append(App.Vector(px, py, pz))

        # Close the polygon by adding the first point at the end
        if pts_transformed:
            pts_transformed.append(pts_transformed[0])
        wires.append(Part.makePolygon(pts_transformed))
        
    # Loft thread profile across all wire sections
    thread_solid = Part.makeLoft(wires, solid=True, ruled=False)

    # For multi-start worms, create additional threads rotated around Z-axis
    if num_threads > 1:
        thread_solids = [thread_solid]
        angle_between_threads = 360.0 / num_threads
        for thread_idx in range(1, num_threads):
            rotation_angle = thread_idx * angle_between_threads
            # Create rotation matrix around Z-axis
            rotation = App.Rotation(App.Vector(0, 0, 1), rotation_angle)
            placement = App.Placement(App.Vector(0, 0, 0), rotation)
            # Copy and rotate the thread
            rotated_thread = thread_solid.copy()
            rotated_thread.Placement = placement
            thread_solids.append(rotated_thread)

        # Fuse all threads together
        combined_thread = thread_solids[0]
        for additional_thread in thread_solids[1:]:
            combined_thread = combined_thread.fuse(additional_thread)
        thread_solid = combined_thread
        App.Console.PrintMessage(f"Created {num_threads}-start worm thread\n")

    # Container for Thread Tool (Part::Feature, OUTSIDE BODY)
    # This is the "Tool" for the Boolean Cut
    thread_name = f"{body_name}_ThreadTool"
    thread_obj = doc.getObject(thread_name)
    if not thread_obj:
        thread_obj = doc.addObject("Part::Feature", thread_name)
    thread_obj.Shape = thread_solid
    thread_obj.Visibility = False

    # 3. INTEGRATION - Use Part.Shape.cut() and set as BaseFeature
    # All geometry is built in Part space, then imported as BaseFeature
    # This gives a clean PartDesign body where subsequent features work properly

    # Perform boolean cut using Part module
    try:
        cut_shape = rev_shape.cut(thread_solid)
    except Exception as e:
        App.Console.PrintError(f"Boolean cut failed: {e}\n")
        cut_shape = rev_shape  # Fallback to uncut shape

    # Store the cut result in a Part::Feature (outside the body)
    cut_result_name = f"{body_name}_CutResult"
    cut_result = doc.getObject(cut_result_name)
    if not cut_result:
        cut_result = doc.addObject("Part::Feature", cut_result_name)
    cut_result.Shape = cut_shape
    cut_result.Visibility = False

    # Set the cut result as the BaseFeature of the body
    # BaseFeature is the starting point for PartDesign operations
    # With no other features, it IS the body's shape and Tip is None
    body.BaseFeature = cut_result

    # Hide thread tool
    thread_obj.Visibility = False

    # Show the body
    body.ViewObject.Visibility = True

    # 4. BORE
    if bore_type != "none":
        # Note: bore may not work properly with Part::Feature in body
        # but we'll try
        try:
            # Bore starts at top (Z = Length/2) and cuts down (Reversed=False for standard pocket behavior against normal)
            bore_placement = App.Placement(App.Vector(0, 0, cylinder_length / 2.0), App.Rotation())
            util.createBore(body, parameters, cylinder_length, placement=bore_placement, reversed=False)
        except Exception as e:
            App.Console.PrintWarning(f"Could not add bore: {e}\n")

    doc.recompute()

    # 5. MATING GEAR (Worm Wheel)
    create_mating_gear = parameters.get("create_mating_gear", True)
    if create_mating_gear:
        try:
            # Pass worm pitch radius for groove calculation
            # The wheel teeth should extend to the worm's pitch circle
            generateMatingGear(doc, parameters, center_distance, worm_pitch_radius, addendum, dedendum)
        except Exception as e:
            App.Console.PrintWarning(f"Could not create mating gear: {e}\n")
            import traceback
            App.Console.PrintWarning(traceback.format_exc())

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass


def generateMatingGear(doc, parameters, center_distance, worm_pitch_radius, worm_addendum, worm_dedendum):
    """Generate the mating worm wheel (gear) for the globoid worm.

    Creates a Throated Helical Gear using parametric PartDesign operations:
    1. Creates tooth profile sketch at bottom
    2. Creates rotated tooth profile sketch at top
    3. Uses AdditiveLoft between sketches for helical tooth
    4. Polar pattern for all teeth
    5. Cuts concave throat groove

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters
        center_distance: Distance between worm and gear axes
        worm_pitch_radius: Pitch radius of worm at throat
        worm_addendum: Worm tooth addendum (tip extension above pitch)
        worm_dedendum: Worm tooth dedendum (root depth below pitch)
    """
    """Generate the mating worm wheel (gear) for the globoid worm.

    Creates a Throated Helical Gear using parametric PartDesign operations:
    1. Creates tooth profile sketch at bottom
    2. Creates rotated tooth profile sketch at top
    3. Uses AdditiveLoft between sketches for helical tooth
    4. Polar pattern for all teeth
    5. Cuts concave throat groove

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters
        center_distance: Distance between worm and gear axes
        worm_pitch_radius: Pitch radius of the worm at throat
        worm_addendum: Worm tooth addendum (tip extension above pitch)
        worm_dedendum: Worm tooth dedendum (root depth below pitch)
    """
    body_name = parameters.get("body_name", "GloboidWorm")
    gear_body_name = f"{body_name}_WormWheel"

    # Extract parameters
    module = parameters["module"]
    num_teeth = parameters["gear_teeth"]
    height = parameters["gear_height"]
    pressure_angle = parameters["pressure_angle"]
    num_threads = parameters["num_threads"]
    right_handed = parameters["right_handed"]

    # Calculate worm lead angle - this is the helix angle for the wheel
    thread_pitch = math.pi * module
    lead = thread_pitch * num_threads
    worm_pitch_diameter = worm_pitch_radius * 2.0

    # Lead angle: tan(lead_angle) = lead / (pi * worm_pitch_diameter)
    lead_angle_rad = math.atan(lead / (math.pi * worm_pitch_diameter))
    lead_angle_deg = lead_angle_rad / util.DEG_TO_RAD

    App.Console.PrintMessage(f"Worm wheel: lead_angle={lead_angle_deg:.2f}°, num_teeth={num_teeth}\n")
    App.Console.PrintMessage(f"Worm: thread_pitch={thread_pitch:.2f}, lead={lead:.2f}, worm_pitch_dia={worm_pitch_diameter:.2f}\n")

    # Clean up existing gear body
    gear_body = util.readyPart(doc, gear_body_name)

# Calculate gear geometry
    pitch_diameter = module * num_teeth
    gear_pitch_radius = pitch_diameter / 2.0
    base_diameter = pitch_diameter * math.cos(pressure_angle * util.DEG_TO_RAD)
    base_radius = base_diameter / 2.0
    addendum = module * gearMath.ADDENDUM_FACTOR
    dedendum = module * gearMath.DEDENDUM_FACTOR
    outer_radius = gear_pitch_radius + addendum
    root_radius = gear_pitch_radius - dedendum

    # Helical twist over gear height
    # twist_angle = height * tan(helix_angle) / pitch_radius
    helix_angle_rad = lead_angle_rad
    twist_total_rad = (height * math.tan(helix_angle_rad)) / gear_pitch_radius
    twist_total_deg_before_handedness = twist_total_rad / util.DEG_TO_RAD

    # Handedness: right-handed worm meshes with left-handed wheel
    if right_handed:
        twist_total_deg = -twist_total_deg_before_handedness
    else:
        twist_total_deg = twist_total_deg_before_handedness

    App.Console.PrintMessage(f"Helix angle: {math.degrees(helix_angle_rad):.2f}°, twist before handedness: {twist_total_deg_before_handedness:.2f}°\n")
    App.Console.PrintMessage(f"Final twist: {twist_total_deg:.2f}° over height {height:.2f}mm (right_handed={right_handed})\n")

    # =========================================================================
    # STEP 1: Create Bottom Tooth Profile Sketch (Z=0)
    # =========================================================================

    sk_bottom = util.createSketch(gear_body, 'ToothProfileBottom')
    # Attach to XY plane (default)

    # Generate tooth profile using gearMath with standard parameters
    # Keep it simple to avoid crossing lines
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
            App.Vector(0, 0, height),
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

    # Worm clearance cut - should match Worm Root to avoid cutting teeth
    clearance_factor = parameters.get("clearance", 0.1)
    clearance = module * clearance_factor
    # Use worm root radius instead of outer radius to avoid cutting teeth
    worm_root_radius = worm_pitch_radius - worm_dedendum
    cut_radius = worm_root_radius + clearance

    # For globoid worm, account for hourglass shape at gear center (Z=0)
    # The worm curves inward, so the actual surface at gear center is closer to gear center
    # Calculate the globoid surface radius at Z=0 (center of gear)
    # From the worm generation: local_radius = center_distance - math.sqrt(arc_radius**2 - z_pos**2)
    # At Z=0: local_radius = center_distance - arc_radius
    # The groove should be positioned at this surface, not at full center_distance
    
    # Get the arc_radius used in worm generation (same calculation as in worm generation)
    gear_pitch_radius = (module * num_teeth) / 2.0
    arc_radius = gear_pitch_radius * 0.9  # Same as used in worm generation
    
# For globoid worm, the throat is positioned closer to gear center than full center_distance
    # Based on observation, move it ~2mm closer (from -35mm to ~-33mm for this case)
    # This accounts for the hourglass shape where worm curves inward
    adjustment_factor = 0.94  # Move 6% closer to gear center
# For globoid worm, adjust groove position to avoid boolean artifacts
    # Small adjustments can make big difference in FreeCAD boolean operations
    # Use a position that's robust to precision issues
    adjusted_center_distance = center_distance - 1.85  # Fine-tuned position for clean boolean
    groove_position = -adjusted_center_distance
    
    App.Console.PrintMessage(f"Throat groove: center_distance={center_distance:.2f}, adjusted={adjusted_center_distance:.2f}\n")
    App.Console.PrintMessage(f"  groove_position={groove_position:.2f}, cut_radius={cut_radius:.2f}\n")
    App.Console.PrintMessage(f"  worm_root_radius={worm_root_radius:.2f}\n")
    App.Console.PrintMessage("Using refined groove position to avoid boolean artifacts\n")

    c_idx = sk_throat.addGeometry(
        Part.Circle(App.Vector(groove_position, 0, 0), App.Vector(0, 0, 1), cut_radius),
        False
    )

    sk_throat.addConstraint(Sketcher.Constraint('PointOnObject', c_idx, 3, -1))
    sk_throat.addConstraint(Sketcher.Constraint('Radius', c_idx, cut_radius))
    sk_throat.addConstraint(Sketcher.Constraint('DistanceX', c_idx, 3, -1, 1, groove_position))

    doc.recompute()

    # Create the Groove with precision adjustments
    groove = gear_body.newObject('PartDesign::Groove', 'ThroatGroove')
    groove.Profile = sk_throat
    groove.ReferenceAxis = (sk_throat, ['V_Axis'])
    groove.Angle = 360.0
    groove.Midplane = False
    groove.Reversed = False
    
    # Add small refinement to avoid artifacts
    groove.Refine = True
    
    sk_throat.Visibility = False
    gear_body.Tip = groove
    doc.recompute()
    
    # Additional recompute pass to resolve any remaining artifacts
    doc.recompute()
    
    App.Console.PrintMessage("Applied Refine=True to groove to reduce boolean artifacts\n")

    # =========================================================================
    # STEP 7: Alignment & Placement
    # =========================================================================

    # Rotation to orient gear axis perpendicular to worm axis
    r_align = App.Rotation(App.Vector(1, 0, 0), 90)

    gear_body.Placement = App.Placement(
        App.Vector(center_distance, height / 2.0, 0),
        r_align
    )

    doc.recompute()
    # Additional recompute to clear any remaining artifacts
    doc.recompute()
    
    gear_body.ViewObject.Visibility = True
    App.Console.PrintMessage(f"Helical Worm Wheel created: {gear_body_name} (helix angle={lead_angle_deg:.2f}°)\n")
    
    # No precision restoration needed - removed problematic API call


try: FreeCADGui.addCommand('GloboidWormGearCreateObject', GloboidWormGearCreateObject())
except Exception: pass
