"""Double Helical Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric involute double helical gears.

Copyright 2025, Chris Bruner
Version v0.1.3
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
mainIcon = os.path.join(smWB_icons_path, 'DoubleHelicalGear.svg') 

version = 'Nov 30, 2025'

def QT_TRANSLATE_NOOP(scope, text): return text

# ============================================================================
# GENERATION LOGIC (Placeholder for double helical gear specific logic)
# ============================================================================

def validateDoubleHelicalParameters(parameters):
    # TODO: Add specific validation for double helical gear parameters
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH: raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0: raise gearMath.GearParameterError("Height must be positive")

def generateDoubleHelicalGearPart(doc, parameters):
    validateDoubleHelicalParameters(parameters)
    
    body_name = parameters.get("body_name", "DoubleHelicalGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"]
    num_teeth = parameters["num_teeth"]
    pressure_angle_deg = parameters["pressure_angle"]
    profile_shift = parameters.get("profile_shift", 0.0)
    height = parameters["height"]
    helix_angle_deg = parameters["helix_angle"]
    fishbone_width = parameters["fishbone_width"]
    bore_type = parameters.get("bore_type", "none")

    half_h = (height - fishbone_width) / 2.0
    if half_h <= 0:
        raise gearMath.GearParameterError("Height must be greater than Fishbone Width")

    pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
    pitch_r = pitch_dia / 2.0
    base_r = gearMath.base_radius(pitch_dia, pressure_angle_deg)
    outer_dia = gearMath.calcAddendumDiameter(pitch_dia, module, profile_shift)
    root_dia = gearMath.calcDedendumDiameter(pitch_dia, module, profile_shift)

    # Calculate helix pitch (height for one full rotation)
    helix_pitch = (math.pi * pitch_dia) / math.tan(helix_angle_deg * util.DEG_TO_RAD)
    if helix_pitch == 0:
        raise gearMath.GearParameterError("Helix pitch cannot be zero with given helix angle.")

    # 1. Dedendum Cylinder (Base Feature)
    # The radius should precisely match the root of the tooth profile for clean fusion.
    dedendum_radius = root_dia / 2.0
    
    # Create a generic Feature to hold the base cylinder shape
    dedendum_cylinder_feature = body.newObject("PartDesign::Feature", "DedendumCylinderFeature")
    # Define the cylinder shape directly centered at Z=0
    dedendum_cylinder_shape = Part.makeCylinder(dedendum_radius, height, App.Vector(0,0, -height/2.0), App.Vector(0,0,1))
    dedendum_cylinder_feature.Shape = dedendum_cylinder_shape
    
    body.BaseFeature = dedendum_cylinder_feature # Explicitly set as BaseFeature
    
    # 2. Tooth Profile Sketch (Centered at Z=0)
    sketch = util.createSketch(body, 'ToothProfile')
    sketch.MapMode = 'Deactivated'
    sketch.Placement = App.Placement(App.Vector(0,0,0), App.Rotation(0,0,0,1))
    gearMath.generateToothProfile(sketch, parameters)
    
    # Create a Datum Line for the Z-axis
    z_axis_line = body.newObject("PartDesign::Line", "Z_Axis_DatumLine")
    z_axis_line.MapMode = "Deactivated"
    
    # 3. Upper Helical Half (Left Handed) - Starts at Z=+fishbone_width/2, grows to +Z
    # By positioning the helix at fishbone_width/2 and using half_h height,
    # the fishbone gap is created naturally without needing a pocket operation
    helix_upper = body.newObject("PartDesign::AdditiveHelix", "HelicalHalf_Upper")
    helix_upper.Profile = sketch
    helix_upper.Height = half_h  # (height - fishbone_width) / 2.0
    helix_upper.Pitch = abs(helix_pitch)
    helix_upper.LeftHanded = True
    helix_upper.ReferenceAxis = (z_axis_line, [''])
    helix_upper.Placement = App.Placement(App.Vector(0, 0, fishbone_width/2.0), App.Rotation(0,0,0,1))

    # 4. Lower Helical Half (Right Handed) - Starts at Z=-fishbone_width/2, grows to -Z (Reversed)
    helix_lower = body.newObject("PartDesign::AdditiveHelix", "HelicalHalf_Lower")
    helix_lower.Profile = sketch
    helix_lower.Height = half_h  # (height - fishbone_width) / 2.0
    helix_lower.Pitch = abs(helix_pitch)
    helix_lower.LeftHanded = False
    helix_lower.Reversed = True
    helix_lower.ReferenceAxis = (z_axis_line, [''])
    helix_lower.Placement = App.Placement(App.Vector(0, 0, -fishbone_width/2.0), App.Rotation(0,0,0,1))

    # Explicitly fuse the helical halves with the dedendum cylinder to ensure single solids
    # before patterning. This addresses the "multiple solids" error.
    fused_upper_tooth = body.newObject("PartDesign::Boolean", "UpperToothOnHub")
    fused_upper_tooth.Type = "Fuse"
    fused_upper_tooth.addObjects([dedendum_cylinder_feature, helix_upper])
    
    fused_lower_tooth = body.newObject("PartDesign::Boolean", "LowerToothOnHub")
    fused_lower_tooth.Type = "Fuse"
    fused_lower_tooth.addObjects([dedendum_cylinder_feature, helix_lower])
    
    dedendum_cylinder_feature.Visibility = False
    helix_upper.Visibility = False
    helix_lower.Visibility = False

    # 5. Polar Pattern (Pattern both fused helices)
    polar = body.newObject('PartDesign::PolarPattern', 'DoubleHelicalTeethPolar')
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]  # Z_Axis from body's Origin
    polar.Axis = (z_axis, [''])
    polar.Angle = 360
    polar.Occurrences = num_teeth
    polar.Originals = [fused_upper_tooth, fused_lower_tooth] # Pattern the fused single teeth
    fused_upper_tooth.Visibility = False
    fused_lower_tooth.Visibility = False
    polar.Visibility = True
    body.Tip = polar

    # 6. Fishbone Gap - Created naturally by helix positioning
    # The gap from Z=-fishbone_width/2 to Z=+fishbone_width/2 exists because
    # the helixes start at ±fishbone_width/2 instead of Z=0.
    # The dedendum cylinder fills the hub through this gap region.

    # 7. Bore
    if bore_type != "none":
        util.createBore(body, parameters, height)
        
    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass



class DoubleHelicalGearCreateObject():
    """Command to create a new double helical gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Double Helical Gear",
            'ToolTip': "Create parametric involute double helical gear"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # --- Generate Unique Body Name ---
        base_name = "DoubleHelicalGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "DoubleHelicalGearParameters")
        double_helical_gear = DoubleHelicalGear(gear_obj)
        
        # Assign unique name to the property so gearMath uses it
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return double_helical_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class DoubleHelicalGear():
    """FeaturePython object for parametric double helical gear."""

    def __init__(self, obj):
        """Initialize double helical gear with default parameters.

        Args:
            obj: FreeCAD document object
        """
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

        # Core gear parameters
        obj.addProperty(
            "App::PropertyLength", "Module", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger", "NumberOfTeeth", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyLength", "Height", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]
        
        # Double Helical specific properties (placeholders for now)
        obj.addProperty(
            "App::PropertyAngle", "HelixAngle", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle of the teeth")
        ).HelixAngle = 30.0 # Default helix angle

        obj.addProperty(
            "App::PropertyLength", "FishboneWidth", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of the fishbone/gap in the center")
        ).FishboneWidth = 2.0 # Default fishbone width

        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString", "BodyName", "DoubleHelicalGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = H["body_name"]

        # Bore parameters
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
            "App::PropertyLength", "SquareCornerRadius", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore")
        ).SquareCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength", "HexCornerRadius", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore")
        ).HexCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength", "KeywayWidth", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)")
        ).KeywayWidth = 2.0

        obj.addProperty(
            "App::PropertyLength", "KeywayDepth", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Depth of keyway")
        ).KeywayDepth = 1.0

        self.Type = 'DoubleHelicalGear'
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
        """Called when a property changes.

        Args:
            fp: Feature Python object
            prop: Property name that changed
        """
        # Mark for recompute when any property changes
        self.Dirty = True

        # Update read-only calculated properties
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "HelixAngle"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                helix_angle = fp.HelixAngle.Value # Use helix angle for calculations

                # Calculate derived dimensions (adapt for helical/double helical if necessary)
                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(pitch_dia, module, profile_shift)
                root_dia = gearMath.calcDedendumDiameter(pitch_dia, module, profile_shift)

                # Update read-only properties
                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.OuterDiameter = outer_dia
                fp.RootDiameter = root_dia

            except (AttributeError, TypeError):
                # Properties not fully initialized yet
                pass

    def GetParameters(self):
        """Get current parameters as dictionary.

        Returns:
            Dictionary of current parameter values
        """
        parameters = {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "helix_angle": float(self.Object.HelixAngle.Value), # Add helix angle to parameters
            "fishbone_width": float(self.Object.FishboneWidth.Value), # Add fishbone width
            "body_name": str(self.Object.BodyName), # Pass body name to math
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
                generateDoubleHelicalGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Double Helical Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Double Helical Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Double Helical Gear Error: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())
                raise

    def set_dirty(self):
        """Mark object as needing recomputation."""
        self.Dirty = True

    def execute(self, obj):
        """Execute gear generation with delay.

        Args:
            obj: FreeCAD document object
        """
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderDoubleHelicalGear:
    """View provider for DoubleHelicalGear object."""

    def __init__(self, obj, iconfile=None):
        """Initialize view provider.

        Args:
            obj: View provider object
            iconfile: Optional path to icon file
        """
        obj.Proxy = self
        self.part = obj
        self.iconfile = iconfile if iconfile else mainIcon

    def attach(self, obj):
        """Setup the scene sub-graph.

        Args:
            obj: View provider object
        """
        self.ViewObject = obj
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        """Called when a property of the handled feature has changed.

        Args:
            fp: Feature Python object
            prop: Property name that changed
        """
        return

    def getDisplayModes(self, obj):
        """Return a list of display modes.

        Args:
            obj: View provider object

        Returns:
            List of mode names
        """
        modes = ["Shaded", "Wireframe", "Flat Lines"]
        return modes

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode.

        Returns:
            Mode name string
        """
        return "Shaded"

    def setDisplayMode(self, mode):
        """Set the display mode.

        Args:
            mode: Display mode name

        Returns:
            Actual mode to use
        """
        return mode

    def onChanged(self, vobj, prop):
        """Called when a view property has changed.

        Args:
            vobj: View provider object
            prop: Property name that changed
        """
        return

    def getIcon(self):
        """Return the icon in XPM format.

        Returns:
            Path to icon file or XPM data
        """
        return self.iconfile

    def doubleClicked(self, vobj):
        """Called when object is double-clicked.

        Args:
            vobj: View provider object

        Returns:
            True if handled
        """
        return True

    def setupContextMenu(self, vobj, menu):
        """Setup custom context menu.

        Args:
            vobj: View provider object
            menu: QMenu object to add items to
        """
        from PySide import QtGui, QtCore

        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        """Force regeneration of the gear."""
        if hasattr(self.Object, 'Proxy'):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        """Return object state for serialization.

        Returns:
            Icon file path
        """
        return self.iconfile

    def __setstate__(self, state):
        """Restore object state from serialization.

        Args:
            state: Previously saved state
        """
        if state:
            self.iconfile = state
        else:
            self.iconfile = mainIcon
        return None


# Register command with FreeCAD
try:
    FreeCADGui.addCommand('DoubleHelicalGearCreateObject', DoubleHelicalGearCreateObject())
    # App.Console.PrintMessage("DoubleHelicalGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register DoubleHelicalGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())
