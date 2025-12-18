"""Internal Double Helical Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric involute internal double helical (herringbone) gears.

Copyright 2025, Chris Bruner
Version v0.1.0
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
mainIcon = os.path.join(smWB_icons_path, 'InternalDoubleHelicalGear.svg')

version = 'Dec 11, 2025'

def QT_TRANSLATE_NOOP(scope, text): return text

# ============================================================================
# GENERATION LOGIC
# ============================================================================

def validateInternalDoubleHelicalParameters(parameters):
    """Validate parameters for internal double helical gear."""
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")
    if parameters["helix_angle"] <= 0 or parameters["helix_angle"] >= 90:
        raise gearMath.GearParameterError("Helix angle must be between 0 and 90 degrees")
    if parameters["fishbone_width"] < 0:
        raise gearMath.GearParameterError("Fishbone width cannot be negative")
    if parameters["fishbone_width"] >= parameters["height"]:
        raise gearMath.GearParameterError("Fishbone width must be less than total height")


def generateInternalToothProfile(sketch, parameters):
    """Generate internal gear tooth profile (teeth pointing inward).

    Args:
        sketch: FreeCAD Sketcher object to add geometry to
        parameters: Dictionary with gear parameters
    """
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_rad = parameters["pressure_angle"] * util.DEG_TO_RAD
    profile_shift = parameters.get("profile_shift", 0.0)

    # Internal gear diameter calculations (teeth point inward)
    dw = module * num_teeth  # Pitch diameter
    dg = dw * math.cos(pressure_angle_rad)  # Base diameter

    # For internal gears: addendum is INWARD (smaller), dedendum is OUTWARD (larger)
    da_internal = dw - 2 * module * (gearMath.ADDENDUM_FACTOR + profile_shift)
    df_internal = dw + 2 * module * (gearMath.DEDENDUM_FACTOR - profile_shift)

    # Tooth thickness angle calculations
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
        phi_start = math.sqrt(max(0, (2*start_radius/dg)**2 - 1))
        phi_end = math.sqrt(max(0, (2*end_radius/dg)**2 - 1))
        phi = phi_start + t * (phi_end - phi_start)

        r = (dg / 2.0) * math.sqrt(1 + phi**2)
        theta_inv = phi - math.atan(phi)
        angle = (math.pi / 2.0) - tooth_center_offset - theta_inv
        right_flank_geo.append(App.Vector(r * math.cos(angle), r * math.sin(angle), 0))

    left_flank_geo = util.mirrorPointsX(right_flank_geo)

    geo_list = []

    # Right involute flank
    bspline_right = Part.BSplineCurve()
    bspline_right.interpolate(right_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_right, False))

    # Root arc (outer edge of internal gear tooth)
    p_root_start = right_flank_geo[-1]
    p_root_end = left_flank_geo[0]
    p_root_mid = App.Vector(0, df_internal/2.0, 0)
    root_arc = Part.Arc(p_root_start, p_root_mid, p_root_end)
    geo_list.append(sketch.addGeometry(root_arc, False))

    # Left involute flank
    bspline_left = Part.BSplineCurve()
    bspline_left.interpolate(left_flank_geo)
    geo_list.append(sketch.addGeometry(bspline_left, False))

    # Tip arc (inner edge of internal gear tooth)
    p_tip_start = left_flank_geo[-1]
    p_tip_end = right_flank_geo[0]
    p_tip_mid = App.Vector(0, da_internal/2.0, 0)
    tip_arc = Part.Arc(p_tip_start, p_tip_mid, p_tip_end)
    geo_list.append(sketch.addGeometry(tip_arc, False))

    util.finalizeSketchGeometry(sketch, geo_list)


def generateInternalDoubleHelicalGearPart(doc, parameters):
    """Generate complete internal double helical gear geometry.

    Args:
        doc: FreeCAD document
        parameters: Dictionary with gear parameters
    """
    validateInternalDoubleHelicalParameters(parameters)

    body_name = parameters.get("body_name", "InternalDoubleHelicalGear")
    body = util.readyPart(doc, body_name)

    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_deg = parameters["pressure_angle"]
    profile_shift = parameters.get("profile_shift", 0.0)
    height = parameters["height"]
    helix_angle_deg = parameters["helix_angle"]
    fishbone_width = parameters["fishbone_width"]
    rim_thickness = parameters.get("rim_thickness", 3.0)

    # Calculate half height for each helix section
    half_h = (height - fishbone_width) / 2.0
    if half_h <= 0:
        raise gearMath.GearParameterError("Height must be greater than Fishbone Width")

    # Diameter calculations for internal gear
    dw = module * num_teeth  # Pitch diameter
    pitch_r = dw / 2.0

    # For internal gears: addendum is inward, dedendum is outward
    da_internal = dw - 2 * module * (gearMath.ADDENDUM_FACTOR + profile_shift)  # Inner (tip)
    df_internal = dw + 2 * module * (gearMath.DEDENDUM_FACTOR - profile_shift)  # Outer (root)
    outer_diameter = df_internal + 2 * rim_thickness  # Overall outer ring diameter

    # Calculate helix pitch
    helix_pitch = (math.pi * dw) / math.tan(helix_angle_deg * util.DEG_TO_RAD)
    if helix_pitch == 0:
        raise gearMath.GearParameterError("Helix pitch cannot be zero with given helix angle.")

    # 1. Outer Ring (Base Feature) - Creates the solid ring
    # This is the main body that teeth will be added to
    ring_sketch = util.createSketch(body, 'OuterRing')
    ring_sketch.MapMode = 'Deactivated'
    ring_sketch.Placement = App.Placement(App.Vector(0, 0, -height/2.0), App.Rotation(0,0,0,1))

    # Outer circle
    outer_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0), False)
    ring_sketch.addConstraint(Sketcher.Constraint('Coincident', outer_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint('Diameter', outer_circle, outer_diameter))

    # Inner circle (at dedendum - root of internal teeth)
    inner_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df_internal / 2.0), False)
    ring_sketch.addConstraint(Sketcher.Constraint('Coincident', inner_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint('Diameter', inner_circle, df_internal))

    ring_pad = util.createPad(body, ring_sketch, height, 'OuterRing', midplane=False)

    # 2. Tooth Profile Sketch (centered at Z=0)
    sketch = util.createSketch(body, 'ToothProfile')
    sketch.MapMode = 'Deactivated'
    sketch.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0,0,0,1))
    generateInternalToothProfile(sketch, parameters)

    # 3. Create Datum Line for Z-axis
    z_axis_line = body.newObject("PartDesign::Line", "Z_Axis_DatumLine")
    z_axis_line.MapMode = "Deactivated"

    # 4. Upper Helical Half (Left Handed) - Starts at Z=+fishbone_width/2
    helix_upper = body.newObject("PartDesign::AdditiveHelix", "HelicalHalf_Upper")
    helix_upper.Profile = sketch
    helix_upper.Height = half_h
    helix_upper.Pitch = abs(helix_pitch)
    helix_upper.LeftHanded = True
    helix_upper.ReferenceAxis = (z_axis_line, [''])
    helix_upper.Placement = App.Placement(App.Vector(0, 0, fishbone_width/2.0), App.Rotation(0,0,0,1))

    # 5. Lower Helical Half (Right Handed) - Starts at Z=-fishbone_width/2, grows to -Z
    helix_lower = body.newObject("PartDesign::AdditiveHelix", "HelicalHalf_Lower")
    helix_lower.Profile = sketch
    helix_lower.Height = half_h
    helix_lower.Pitch = abs(helix_pitch)
    helix_lower.LeftHanded = False
    helix_lower.Reversed = True
    helix_lower.ReferenceAxis = (z_axis_line, [''])
    helix_lower.Placement = App.Placement(App.Vector(0, 0, -fishbone_width/2.0), App.Rotation(0,0,0,1))

    # 6. Polar Pattern - Use body's Origin Z_Axis for proper axis reference
    polar = body.newObject('PartDesign::PolarPattern', 'InternalDoubleHelicalTeethPolar')
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

    # 7. Fishbone Gap - Created naturally by helix positioning
    # The gap from Z=-fishbone_width/2 to Z=+fishbone_width/2 exists because
    # the helixes start at ±fishbone_width/2 instead of Z=0.
    # The outer ring provides connection through this gap region.

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass


class InternalDoubleHelicalGearCreateObject():
    """Command to create a new internal double helical gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Internal Double Helical Gear",
            'ToolTip': "Create parametric involute internal double helical (herringbone) gear"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Generate unique body name
        base_name = "InternalDoubleHelicalGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalDoubleHelicalGearParameters")
        internal_double_helical_gear = InternalDoubleHelicalGear(gear_obj)

        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return internal_double_helical_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class InternalDoubleHelicalGear():
    """FeaturePython object for parametric internal double helical gear."""

    def __init__(self, obj):
        """Initialize internal double helical gear with default parameters."""
        self.Dirty = False
        H = gearMath.generateDefaultInternalParameters()

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
            "App::PropertyLength", "InnerDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Inner diameter (tip of teeth pointing inward)"),
            1
        )

        obj.addProperty(
            "App::PropertyLength", "OuterDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (ring outer edge)"),
            1
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyLength", "Module", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger", "NumberOfTeeth", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyLength", "Height", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyLength", "RimThickness", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Thickness of outer rim beyond tooth roots")
        ).RimThickness = H["rim_thickness"]

        # Double Helical specific properties
        obj.addProperty(
            "App::PropertyAngle", "HelixAngle", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle of the teeth")
        ).HelixAngle = 30.0

        obj.addProperty(
            "App::PropertyLength", "FishboneWidth", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of the fishbone/gap in the center")
        ).FishboneWidth = 2.0

        # Body Name Property
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalDoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = "InternalDoubleHelicalGear"

        self.Type = 'InternalDoubleHelicalGear'
        self.Object = obj
        self.doc = App.ActiveDocument
        obj.Proxy = self

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

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness", "HelixAngle"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value

                # Calculate derived dimensions
                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, module, profile_shift)
                outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, module, profile_shift, rim_thickness)

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia

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
            "rim_thickness": float(self.Object.RimThickness.Value),
            "helix_angle": float(self.Object.HelixAngle.Value),
            "fishbone_width": float(self.Object.FishboneWidth.Value),
            "body_name": str(self.Object.BodyName),
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
                generateInternalDoubleHelicalGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Internal Double Helical Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Internal Double Helical Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Internal Double Helical Gear Error: {str(e)}\n")
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


class ViewProviderInternalDoubleHelicalGear:
    """View provider for InternalDoubleHelicalGear object."""

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
    FreeCADGui.addCommand('InternalDoubleHelicalGearCreateObject', InternalDoubleHelicalGearCreateObject())
except Exception as e:
    App.Console.PrintError(f"Failed to register InternalDoubleHelicalGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())
