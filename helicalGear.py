"""Helical Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric involute helical gears. Supports both single helical
and double helical (herringbone) configurations via a boolean toggle.

Copyright 2025, Chris Bruner
Version v0.2.0
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
mainIcon = os.path.join(smWB_icons_path, 'HelicalGear.svg')

version = 'Dec 11, 2025'

def QT_TRANSLATE_NOOP(scope, text): return text

# ============================================================================
# GENERATION LOGIC
# ============================================================================

def validateHelicalParameters(parameters):
    """Validate helical gear parameters."""
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")
    if parameters["helix_angle"] <= 0 or parameters["helix_angle"] >= 90:
        raise gearMath.GearParameterError("Helix angle must be between 0 and 90 degrees")

    # Double helical specific validation
    if parameters.get("double_helical", False):
        fishbone_width = parameters.get("fishbone_width", 0.0)
        if fishbone_width < 0:
            raise gearMath.GearParameterError("Fishbone width cannot be negative")
        if fishbone_width >= parameters["height"]:
            raise gearMath.GearParameterError("Fishbone width must be less than total height")

    # Internal gear specific validation
    if parameters.get("internal_gear", False):
        rim_thickness = parameters.get("rim_thickness", 3.0)
        if rim_thickness <= 0:
            raise gearMath.GearParameterError("Rim thickness must be positive for internal gears")


def generateInternalToothProfile(sketch, parameters):
    """Generate INTERNAL involute tooth profile for helical gears."""
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * util.DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    dw = module * num_teeth
    dg = dw * math.cos(pressure_angle_rad)
    da_internal = dw - 2 * module * (gearMath.ADDENDUM_FACTOR + profile_shift) 
    df_internal = dw + 2 * module * (gearMath.DEDENDUM_FACTOR - profile_shift) 

    beta = (math.pi / (2 * num_teeth)) + (2 * profile_shift * math.tan(pressure_angle_rad) / num_teeth)
    inv_alpha = math.tan(pressure_angle_rad) - pressure_angle_rad
    tooth_center_offset = beta - inv_alpha

    num_inv_points = 20 
    epsilon = 0.001
    start_radius = max(da_internal/2.0, dg/2.0 + epsilon)
    end_radius = df_internal/2.0

    right_flank_geo = []
    # Avoid domain error if start > end
    if start_radius >= end_radius:
         start_radius = end_radius - epsilon

    for i in range(num_inv_points):
        t = i / (num_inv_points - 1)
        # Phi calculation for internal gear
        # phi = sqrt((2*r/dg)^2 - 1)
        phi_start = math.sqrt(max(0, (2*start_radius/dg)**2 - 1))
        phi_end = math.sqrt(max(0, (2*end_radius/dg)**2 - 1))
        phi = phi_start + t * (phi_end - phi_start)
        
        r = (dg / 2.0) * math.sqrt(1 + phi**2)
        theta_inv = phi - math.atan(phi)
        angle = (math.pi / 2.0) - tooth_center_offset - theta_inv
        right_flank_geo.append(App.Vector(r * math.cos(angle), r * math.sin(angle), 0))

    left_flank_geo = util.mirrorPointsX(right_flank_geo)

    geo_list = []
    
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_right, False))
    
    p_root_start = right_flank_geo[-1]
    p_root_end = left_flank_geo[0]
    p_root_mid = App.Vector(0, df_internal/2.0, 0)
    root_arc = Part.Arc(p_root_start, p_root_mid, p_root_end)
    geo_list.append(sketch.addGeometry(root_arc, False))
    
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_left, False))
    
    p_tip_start = left_flank_geo[-1]
    p_tip_end = right_flank_geo[0]
    p_tip_mid = App.Vector(0, da_internal/2.0, 0)
    tip_arc = Part.Arc(p_tip_start, p_tip_mid, p_tip_end)
    geo_list.append(sketch.addGeometry(tip_arc, False))
    
    util.finalizeSketchGeometry(sketch, geo_list)


def generateHelicalGearPart(doc, parameters):
    """Generate helical gear geometry.

    Supports both single helical and double helical (herringbone) configurations.

    Args:
        doc: FreeCAD document
        parameters: Dictionary with gear parameters including:
            - double_helical: Boolean to select double helical mode
            - fishbone_width: Gap width for double helical (ignored if single)
    """
    validateHelicalParameters(parameters)

    body_name = parameters.get("body_name", "HelicalGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_deg = parameters["pressure_angle"]
    profile_shift = parameters.get("profile_shift", 0.0)
    height = parameters["height"]
    helix_angle_deg = parameters["helix_angle"]
    bore_type = parameters.get("bore_type", "none")
    # Extract parameters
    double_helical = parameters.get("double_helical", False)
    internal_gear = parameters.get("internal_gear", False)
    fishbone_width = parameters.get("fishbone_width", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)

    # Calculate diameters based on gear type
    pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
    pitch_r = pitch_dia / 2.0
    
    if internal_gear:
        # Internal gear calculations
        outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, module, profile_shift, rim_thickness)
        root_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, module, profile_shift)
    else:
        # External gear calculations
        outer_dia = gearMath.calcAddendumDiameter(pitch_dia, module, profile_shift)
        root_dia = gearMath.calcDedendumDiameter(pitch_dia, module, profile_shift)

    # Calculate helix pitch (height for one full rotation)
    helix_pitch = (math.pi * pitch_dia) / math.tan(helix_angle_deg * util.DEG_TO_RAD)
    if helix_pitch == 0:
        raise gearMath.GearParameterError("Helix pitch cannot be zero with given helix angle.")

    # Calculate helix half-height (accounting for fishbone gap)
    half_h = (height - fishbone_width) / 2.0
    if half_h <= 0:
        raise gearMath.GearParameterError("Height must be greater than Fishbone Width")

    # 1. Tooth Profile Sketch (centered at Z=0)
    sketch = util.createSketch(body, 'ToothProfile')
    sketch.MapMode = 'Deactivated'
    sketch.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0,0,0,1))
    
    # Calculate Transverse parameters for the tooth profile
    transverse_mod = gearMath.transverse_module(module, helix_angle_deg)
    alpha_n_rad = pressure_angle_deg * util.DEG_TO_RAD
    beta_rad = helix_angle_deg * util.DEG_TO_RAD
    alpha_t_rad = math.atan(math.tan(alpha_n_rad) / math.cos(beta_rad))
    pressure_angle_t_deg = alpha_t_rad * util.RAD_TO_DEG
    
    profile_params = parameters.copy()
    profile_params["module"] = transverse_mod
    profile_params["pressure_angle"] = pressure_angle_t_deg
    
    if internal_gear:
        generateInternalToothProfile(sketch, profile_params)
    else:
        gearMath.generateToothProfile(sketch, profile_params)

    # 2. Create Datum Line for Z-axis reference
    z_axis_line = body.newObject("PartDesign::Line", "Z_Axis_DatumLine")
    z_axis_line.MapMode = "Deactivated"

    if double_helical:
        # Double Helical Mode: Two helixes with opposite hand, creating herringbone pattern

        # 3a. Upper Helical Half (Left Handed)
        helix_upper = body.newObject("PartDesign::AdditiveHelix", "HelicalHalf_Upper")
        helix_upper.Profile = sketch
        helix_upper.Height = half_h
        helix_upper.Pitch = abs(helix_pitch)
        helix_upper.LeftHanded = True
        helix_upper.ReferenceAxis = (z_axis_line, [''])

        # 3b. Lower Helical Half (Right Handed)  
        helix_lower = body.newObject("PartDesign::AdditiveHelix", "HelicalHalf_Lower")
        helix_lower.Profile = sketch
        helix_lower.Height = half_h
        helix_lower.Pitch = abs(helix_pitch)
        helix_lower.LeftHanded = False
        helix_lower.Reversed = True
        helix_lower.ReferenceAxis = (z_axis_line, [''])
        
        doc.recompute()

        # 4. Polar Pattern - Use body's Origin Z_Axis for reliable axis reference
        polar = body.newObject('PartDesign::PolarPattern', 'HelicalTeethPolar')
        origin = body.Origin
        z_axis = origin.OriginFeatures[2]  # Z_Axis from body's Origin
        polar.Axis = (z_axis, [''])
        polar.Angle = 360
        polar.Occurrences = num_teeth
        polar.Originals = [helix_upper, helix_lower]
        helix_upper.Visibility = False
        helix_lower.Visibility = False
        polar.Visibility = True
        body.Tip = polar

    else:
        # Single Helical Mode: One helix for full height

        # 3. Single Helix
        helix_feature = body.newObject("PartDesign::AdditiveHelix", "HelicalTooth")
        helix_feature.Profile = sketch
        helix_feature.Height = height
        helix_feature.Pitch = abs(helix_pitch)
        helix_feature.LeftHanded = False  # Can be made configurable
        helix_feature.ReferenceAxis = (z_axis_line, [''])
        
        doc.recompute()

        # 4. Polar Pattern - Use body's Origin Z_Axis for reliable axis reference
        polar = body.newObject('PartDesign::PolarPattern', 'HelicalTeethPolar')
        origin = body.Origin
        z_axis = origin.OriginFeatures[2]  # Z_Axis from body's Origin
        polar.Axis = (z_axis, [''])
        polar.Angle = 360
        polar.Occurrences = num_teeth
        polar.Originals = [helix_feature]
        helix_feature.Visibility = False
        polar.Visibility = True
        body.Tip = polar

    # 5. Hub/Ring creation (different for internal vs external gears)
    if internal_gear:
        # Internal gear: Create a ring structure
        transverse_pitch_dia = gearMath.calcPitchDiameter(transverse_mod, num_teeth)
        # Use transverse module for internal dedendum diameter (where teeth end)
        transverse_df_internal = transverse_pitch_dia + 2 * transverse_mod * (gearMath.DEDENDUM_FACTOR - profile_shift)
        outer_diameter = transverse_df_internal + 2 * rim_thickness
        
        # Create ring sketch with outer circle and inner hole
        ring_sketch = util.createSketch(body, 'GearRing')
        # Outer circle (larger diameter - outer rim)
        outer_circle = ring_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2), False)
        ring_sketch.addConstraint(Sketcher.Constraint('Coincident', outer_circle, 3, -1, 1))
        ring_sketch.addConstraint(Sketcher.Constraint('Diameter', outer_circle, outer_diameter))

        # Inner hole (smaller diameter - where the internal teeth are)
        inner_hole = ring_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), transverse_df_internal / 2), False)
        ring_sketch.addConstraint(Sketcher.Constraint('Coincident', inner_hole, 3, -1, 1))
        ring_sketch.addConstraint(Sketcher.Constraint('Diameter', inner_hole, transverse_df_internal))

        ring_pad = util.createPad(body, ring_sketch, height, 'GearRing')
        # Use symmetric padding to center the ring for double helical alignment
        if double_helical:
            ring_pad.SideType = "Symmetric"
        body.Tip = ring_pad
        
    else:
        # External gear: Create solid hub
        transverse_pitch_dia = gearMath.calcPitchDiameter(transverse_mod, num_teeth)
        transverse_root_dia = gearMath.calcDedendumDiameter(transverse_pitch_dia, transverse_mod, profile_shift)
        dedendum_sketch = util.createSketch(body, 'DedendumCircle')
        circle = dedendum_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), transverse_root_dia / 2.0 + 0.01), False)
        dedendum_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
        dedendum_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, transverse_root_dia + 0.02))
        
        dedendum_pad = util.createPad(body, dedendum_sketch, height, 'DedendumCircle')
        # Use symmetric padding to center the dedendum cylinder for double helical alignment
        if double_helical:
            dedendum_pad.SideType = "Symmetric"
        body.Tip = dedendum_pad

    # 6. Adjust body position to compensate for symmetric padding jump
    if double_helical:
        body.Placement = App.Placement(App.Vector(0, 0, height/2.0), App.Rotation(0,0,0,1))

    # 7. Bore (only for external gears - internal gears have their own bore structure)
    if not internal_gear and bore_type != "none":
        util.createBore(body, parameters, height)

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass


class HelicalGearCreateObject():
    """Command to create a new helical gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Helical Gear",
            'ToolTip': "Create parametric herringbone (double helical) gear. Set FishboneWidth for center gap."
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Generate unique body name
        base_name = "HelicalGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "HelicalGearParameters")
        helical_gear = HelicalGear(gear_obj)

        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return helical_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class HelicalGear():
    """FeaturePython object for parametric helical gear.

    Supports both single helical and double helical (herringbone) configurations.
    """

    def __init__(self, obj):
        """Initialize helical gear with default parameters."""
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1
        ).Version = version

        obj.addProperty(
            "App::PropertyLength", "PitchDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
            1
        )

        obj.addProperty(
            "App::PropertyLength", "BaseDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Base circle diameter (involute origin)"),
            1
        )

        obj.addProperty(
            "App::PropertyLength", "OuterDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
            1
        )

        obj.addProperty(
            "App::PropertyLength", "RootDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
            1
        )

        # Core gear parameters (HelicalGear section - alphabetically sorted by FreeCAD)
        obj.addProperty(
            "App::PropertyString", "BodyName", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = H["body_name"]

        obj.addProperty(
            "App::PropertyBool", "DoubleHelical", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Create double helical (herringbone) gear")
        ).DoubleHelical = False

        obj.addProperty(
            "App::PropertyLength", "FishboneWidth", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of center gap for double helical (ignored if single)")
        ).FishboneWidth = 2.0

        obj.addProperty(
            "App::PropertyLength", "Height", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle", "HelixAngle", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle of the teeth")
        ).HelixAngle = 30.0

        obj.addProperty(
            "App::PropertyBool", "InternalGear", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Create internal gear (teeth point inward)")
        ).InternalGear = False

        obj.addProperty(
            "App::PropertyLength", "Module", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger", "NumberOfTeeth", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyLength", "RimThickness", "HelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Thickness of material around internal gear teeth")
        ).RimThickness = 3.0

        self.Type = 'HelicalGear'
        self.Object = obj
        self.doc = App.ActiveDocument
        obj.Proxy = self

        # Bore parameters (Bore section - defined at the very end so it appears last)
        obj.addProperty(
            "App::PropertyEnumeration", "BoreType", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole")
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]

        obj.addProperty(
            "App::PropertyLength", "BoreDiameter", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore")
        ).BoreDiameter = H["bore_diameter"]

        obj.addProperty(
            "App::PropertyLength", "HexCornerRadius", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore")
        ).HexCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength", "KeywayDepth", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Depth of keyway")
        ).KeywayDepth = 1.0

        obj.addProperty(
            "App::PropertyLength", "KeywayWidth", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)")
        ).KeywayWidth = 2.0

        obj.addProperty(
            "App::PropertyLength", "SquareCornerRadius", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore")
        ).SquareCornerRadius = 0.5

        # Trigger initial calculation of read-only properties
        self.onChanged(obj, "Module")

    def __getstate__(self):
        """Return object state for serialization."""
        return self.Type

    def __setstate__(self, state):
        """Restore object state from serialization."""
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """Called when a property changes."""
        self.Dirty = True

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "HelixAngle", "InternalGear"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                internal_gear = getattr(fp, 'InternalGear', False)

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                
                if internal_gear:
                    # Internal gear calculations
                    outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, module, profile_shift, 3.0)
                    root_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, module, profile_shift)
                else:
                    # External gear calculations
                    outer_dia = gearMath.calcAddendumDiameter(pitch_dia, module, profile_shift)
                    root_dia = gearMath.calcDedendumDiameter(pitch_dia, module, profile_shift)

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.OuterDiameter = outer_dia
                fp.RootDiameter = root_dia

            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        """Get current parameters as dictionary."""
        parameters = {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "helix_angle": float(self.Object.HelixAngle.Value),
            "double_helical": bool(self.Object.DoubleHelical),
            "internal_gear": bool(self.Object.InternalGear),
            "fishbone_width": float(self.Object.FishboneWidth.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
        }
        return parameters

    def force_Recompute(self):
        """Force recomputation of gear."""
        self.Dirty = True
        self.recompute()

    def recompute(self):
        """Recompute gear geometry if parameters changed."""
        if self.Dirty:
            try:
                parameters = self.GetParameters()
                generateHelicalGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Helical Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Helical Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Helical Gear Error: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())
                raise

    def set_dirty(self):
        """Mark object as needing recomputation."""
        self.Dirty = True

    def execute(self, obj):
        """Execute gear generation with delay."""
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderHelicalGear:
    """View provider for HelicalGear object."""

    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.part = obj
        self.iconfile = iconfile if iconfile else mainIcon

    def attach(self, obj):
        self.ViewObject = obj
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        return

    def getDisplayModes(self, obj):
        return ["Shaded", "Wireframe", "Flat Lines"]

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def onChanged(self, vobj, prop):
        return

    def getIcon(self):
        return self.iconfile

    def doubleClicked(self, vobj):
        return True

    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui
        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        if hasattr(self.Object, 'Proxy'):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        return self.iconfile

    def __setstate__(self, state):
        if state:
            self.iconfile = state
        else:
            self.iconfile = mainIcon
        return None


# Register command with FreeCAD
try:
    FreeCADGui.addCommand('HelicalGearCreateObject', HelicalGearCreateObject())
except Exception as e:
    App.Console.PrintError(f"Failed to register HelicalGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())
