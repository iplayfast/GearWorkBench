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
mainIcon = os.path.join(smWB_icons_path, 'wormGear.svg') 

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
        
        # Globoid Specific: Needs Gear Parameters to define curvature
        obj.addProperty("App::PropertyLength", "Module", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = 1.0
        obj.addProperty("App::PropertyInteger", "NumberOfThreads", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Number of threads (starts)")).NumberOfThreads = 1
        obj.addProperty("App::PropertyInteger", "GearTeeth", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Number of teeth on mating gear")).GearTeeth = 30
        
        obj.addProperty("App::PropertyLength", "WormDiameter", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Throat diameter (smallest diameter)")).WormDiameter = 20.0
        obj.addProperty("App::PropertyAngle", "PressureAngle", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Pressure angle")).PressureAngle = 20.0
        
        # The worm length is defined by the wrap angle around the gear
        obj.addProperty("App::PropertyAngle", "ArcAngle", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Engagement angle (typically 60-90)")).ArcAngle = 60.0
        obj.addProperty("App::PropertyLength", "WormLength", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Length of the threaded section (0 = defined by ArcAngle)")).WormLength = 20.0
        obj.addProperty("App::PropertyLength", "CylinderLength", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Total length of the worm cylinder")).CylinderLength = 30.0
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

        self.Type = 'GloboidWormGear'
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
        self.Dirty = True

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_threads": int(self.Object.NumberOfThreads),
            "gear_teeth": int(self.Object.GearTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "worm_diameter": float(self.Object.WormDiameter.Value),
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
            "keyway_depth": float(self.Object.KeywayDepth.Value)
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
    if parameters["worm_diameter"] <= 0:
        raise gearMath.GearParameterError("Worm Diameter must be positive")
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

    # Extract parameters
    module = parameters["module"]
    num_threads = parameters["num_threads"]
    num_gear_teeth = parameters["gear_teeth"]
    throat_diameter = parameters["worm_diameter"]
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
    # Worm throat radius (smallest radius)
    worm_pitch_radius = throat_diameter / 2.0
    # Center distance between worm and gear axes
    center_distance = gear_pitch_radius + worm_pitch_radius
    
    # 1. PARAMETRIC BASE (Sketch + Revolve)
    # Outer radius at throat (where teeth are)
    outer_throat_radius = worm_pitch_radius + addendum

    # Arc radius for globoid curve (centered at gear center)
    arc_radius = center_distance - outer_throat_radius

    # Determine threaded section span
    if worm_length > 0.01:
        # Calculate angle from specified length
        # Clamp to avoid domain error in asin
        tooth_half_length = min(worm_length / 2.0, arc_radius - 0.001)
        half_angle_rad = math.asin(tooth_half_length / arc_radius)
        # Update effective arc_angle for thread generation
        arc_angle = (half_angle_rad * 2.0) / util.DEG_TO_RAD
    else:
        # Calculate length from arc angle
        half_angle_rad = (arc_angle / 2.0) * util.DEG_TO_RAD
        tooth_half_length = arc_radius * math.sin(half_angle_rad)

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
    sk_base.MapMode = 'Deactivated'

    # Dimensions
    half_cylinder_length = cylinder_length / 2.0
    half_worm_length = worm_length / 2.0 if worm_length > 0.01 else tooth_half_length
    rect_outer_radius = outer_throat_radius
    
    # Calculate Arc Geometry (same as before)
    arc_center = App.Vector(-center_distance, 0.0, 0)
    angle_span = 2.0 * math.asin(half_worm_length / arc_radius)
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
    
    # Worm Length (Vertical Span of Arc)
    cst_worm_len = sk_base.addConstraint(Sketcher.Constraint('DistanceY', idx_arc, 1, idx_arc, 2, worm_length))
    # Or link to WormLength property if logical
    if worm_length > 0.01:
        sk_base.setExpression(f'Constraints[{cst_worm_len}]', 'GloboidWormGearParameters.WormLength')
    
    # Vertical Alignment for Arc Endpoints (Ensures symmetry about X-axis without overconstraining)
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_arc, 1, idx_arc, 2))

    # Removed: Symmetry for Arc - redundant with explicit arc center position + worm length span
    # Arc endpoints are fully determined by: center position, radius, and vertical span

    # Removed: Block constraint - not parametric, causes overconstraint

    doc.recompute()

    # Revolve around Z-axis (Vertical axis of Sketch on XZ Plane)
    rev = body.newObject('PartDesign::Revolution', 'GloboidCylinderBody')
    rev.Profile = sk_base
    rev.ReferenceAxis = (sk_base, ['V_Axis'])  # Vertical Axis = Z
    rev.Angle = 360
    body.Tip = rev
    
    # 2. THREAD GENERATION (B-Rep Loft)
    # Calculate total rotation of worm as gear wraps around it
    worm_rotation_angle = arc_angle * (num_gear_teeth / num_threads)
    loft_steps = 100

    # Thread profile geometry (trapezoidal cross-section)
    tan_pressure = math.tan(pressure_angle * util.DEG_TO_RAD)
    # Half-width at pitch line, reduced slightly for clearance
    half_width_pitch = (math.pi * module) / 4.0 - (0.05 * module)

    # Thread profile coordinates (subtractive cut pattern)
    # Radial position (negative = inside worm cylinder)
    radial_root = -dedendum  # Root of thread (deepest cut)
    width_root = half_width_pitch + (dedendum * tan_pressure)  # Width at root (wider)
    radial_tip = addendum  # Tip of thread (shallow cut)
    width_tip = half_width_pitch - (addendum * tan_pressure)  # Width at tip (narrower)

    # Thread profile polygon (closed trapezoid)
    thread_profile_pts = [
        App.Vector(radial_root, -width_root, 0),
        App.Vector(radial_tip, -width_tip, 0),
        App.Vector(radial_tip, width_tip, 0),
        App.Vector(radial_root, width_root, 0),
        App.Vector(radial_root, -width_root, 0)
    ]
    
    # Generate thread profile at multiple positions along the arc
    wires = []
    for i in range(loft_steps + 1):
        # Normalized parameter from -0.5 to +0.5 along the arc
        u_normalized = (i / loft_steps) - 0.5
        # Worm rotation angle (around its axis)
        worm_angle_deg = u_normalized * worm_rotation_angle
        worm_angle_rad = worm_angle_deg * util.DEG_TO_RAD
        # Gear arc angle (position around gear)
        gear_angle_deg = u_normalized * arc_angle
        gear_angle_rad = gear_angle_deg * util.DEG_TO_RAD

        pts_transformed = []
        for p in thread_profile_pts:
            # Transform: Gear Frame (Z-Axis) -> Worm Frame (Y-Axis)
            
            # Step 1: Position at gear pitch circle (X-axis offset)
            # Input p.x is radial, p.y is width (axial)
            # Map to Gear Frame (Axis Z): 
            # X = -(Radius + p.x)  (Inward facing)
            # Y = 0                (Tangential)
            # Z = p.y              (Axial/Width)
            p_gear_x = -(gear_pitch_radius + p.x)
            p_gear_y = 0.0
            p_gear_z = p.y # Width maps to Z

            # Step 2: Rotate around Gear Axis (Z-axis)
            # Rotates X and Y. Z is invariant.
            cos_gear = math.cos(gear_angle_rad)
            sin_gear = math.sin(gear_angle_rad)
            
            px_rot = p_gear_x * cos_gear - p_gear_y * sin_gear # p_gear_y is 0
            py_rot = p_gear_x * sin_gear + p_gear_y * cos_gear
            pz_rot = p_gear_z

            # Step 3: Translate by center distance (along X)
            # Moves Gear Center to (CD, 0, 0)
            px_trans = px_rot + center_distance
            py_trans = py_rot
            pz_trans = pz_rot

            # Step 4: Rotate Worm around its Axis (Y-axis)
            # We transform the static space into the rotating worm frame
            # Rotation around Y mixes X and Z.
            cos_worm = math.cos(-worm_angle_rad)
            sin_worm = math.sin(-worm_angle_rad)
            
            px_final = px_trans * cos_worm - pz_trans * sin_worm
            pz_final = px_trans * sin_worm + pz_trans * cos_worm
            py_final = py_trans # Y (Axial) is invariant in Y-rotation

            pts_transformed.append(App.Vector(px_final, py_final, pz_final))

        wires.append(Part.makePolygon(pts_transformed))
        
    # Loft thread profile across all wire sections
    thread_solid = Part.makeLoft(wires, solid=True, ruled=False)
    
    # Container for Thread
    thread_name = f"{body_name}_ThreadTool"
    thread_obj = doc.getObject(thread_name)
    if not thread_obj:
        thread_obj = doc.addObject("Part::Feature", thread_name)
    thread_obj.Shape = thread_solid
    thread_obj.Visibility = False
    
    # 3. INTEGRATION - Use PartDesign::Boolean for Subtractive Feature
    # Bring thread into body via binder
    binder_name = f"{body_name}_ThreadBinder" # Renamed binder to be more specific
    binder_obj = None
    for obj in body.Group:
        if obj.Name == binder_name:
            binder_obj = obj
            break

    if not binder_obj:
        binder_obj = body.newObject("PartDesign::SubShapeBinder", binder_name)

    binder_obj.Support = [(thread_obj, '')]
    binder_obj.Visibility = False

    # Create a PartDesign::Boolean feature to cut the thread
    boolean_feature_name = f"{body_name}_ThreadCut"
    boolean_feature = body.newObject("PartDesign::Boolean", boolean_feature_name)
    boolean_feature.Base = rev # The cylinder is the base
    boolean_feature.Tool = binder_obj # The thread is the tool
    boolean_feature.Type = "Cut" # Perform a cut operation
    
    body.Tip = boolean_feature # Set the Boolean feature as the new tip of the body

    # 4. BORE
    if bore_type != "none":
        # Note: bore may not work properly with Part::Feature in body
        # but we'll try
        try:
            util.createBore(body, parameters, cylinder_length)
        except Exception as e:
            App.Console.PrintWarning(f"Could not add bore: {e}\n")

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

try: FreeCADGui.addCommand('GloboidWormGearCreateObject', GloboidWormGearCreateObject())
except Exception: pass