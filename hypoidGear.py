"""Hypoid Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric hypoid gears.

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
from dataclasses import dataclass
from typing import List, Tuple

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'HypoidGear.svg') 

version = 'Nov 30, 2025'

def QT_TRANSLATE_NOOP(scope, text): return text

# Helper dataclass (local to this module)
@dataclass
class HypoidParams:
    module: float
    teeth: int
    pressure_angle_deg: float = 20.0
    offset: float = 10.0
    spiral_angle_deg: float = 35.0
    face_width: float = 18.0
    resolution: int = 220

def build_hypoid_points(p: HypoidParams) -> List[Tuple[float, float, float]]:
    pitch_r = gearMath.pitch_radius(p.module, p.teeth)
    base_r = gearMath.base_radius(pitch_r * 2.0, p.pressure_angle_deg) # pitch_r * 2.0 to get pitch_diameter
    outer_r = gearMath.outer_radius(pitch_r * 2.0, p.module)

    gamma = p.spiral_angle_deg * util.DEG_TO_RAD
    
    # Avoid division by zero if outer_r is too small or 0
    if outer_r == 0:
        sweep_twist = 0.0
    else:
        sweep_twist = math.tan(gamma) / outer_r

    verts = []
    # Simplified approach: generate points for a single tooth profile at different axial positions
    # and then try to create wires for lofting.

    # We will generate a limited number of axial "slices" for lofting
    num_axial_slices = 5
    z_positions = [i * p.face_width / (num_axial_slices - 1) for i in range(num_axial_slices)] if num_axial_slices > 1 else [0.0]

    for tooth_idx in range(p.teeth):
        for zpos_in_slice in z_positions:
            base_offset_angle = 2 * math.pi * tooth_idx / p.teeth

            tooth_profile_points = []
            for step in range(p.resolution):
                t_param = step * 0.02 # Parameter for involute generation
                x, y = gearMath.involute_xy(base_r, t_param)
                r = math.hypot(x, y)
                if r > outer_r:
                    break
                
                # Apply base angle and twist
                current_angle = math.atan2(y, x)
                
                # The twist for hypoid gears is more complex than simple helical.
                # The sample code calculates twist based on zpos.
                twist = sweep_twist * zpos_in_slice
                ang = current_angle + base_offset_angle + twist

                # Apply gear offset
                X = r * math.cos(ang) 
                Y = r * math.sin(ang)
                Z = zpos_in_slice + p.offset # Shift the entire gear along Z by offset

                tooth_profile_points.append(App.Vector(X, Y, Z))
            verts.extend(tooth_profile_points) # Add points for this slice/tooth
    
    # This return is just raw vertices. We need to structure them for FreeCAD.
    return verts


# ============================================================================
# GENERATION LOGIC 
# ============================================================================

def validateHypoidParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH: raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["face_width"] <= 0: raise gearMath.GearParameterError("Face Width must be positive")
    # For now, allow 0 offset, but eventually hypoid means non-zero.
    # if parameters["offset"] == 0: raise gearMath.GearParameterError("Offset must not be zero for a hypoid gear")

def generateHypoidGearPart(doc, parameters):
    validateHypoidParameters(parameters)
    
    body_name = parameters.get("body_name", "HypoidGear")
    body = util.readyPart(doc, body_name)
    
    # Create HypoidParams object for the helper function
    p = HypoidParams(
        module=parameters["module"],
        teeth=parameters["num_teeth"],
        pressure_angle_deg=parameters["pressure_angle"],
        offset=parameters["offset"],
        spiral_angle_deg=parameters["spiral_angle"],
        face_width=parameters["face_width"]
    )

    # Instead of building a raw point cloud and then figuring out faces,
    # let's try to construct profiles for lofting directly.

    pitch_dia = gearMath.calcPitchDiameter(p.module, p.teeth)
    pitch_r = pitch_dia / 2.0
    base_r = gearMath.base_radius(pitch_dia, p.pressure_angle_deg)
    outer_r = gearMath.outer_radius(pitch_dia, p.module)
    root_r = gearMath.root_radius(pitch_dia, p.module)

    gamma = p.spiral_angle_deg * util.DEG_TO_RAD
    
    # Avoid division by zero if outer_r is too small or 0
    if outer_r == 0:
        sweep_twist_factor = 0.0
    else:
        sweep_twist_factor = math.tan(gamma) / outer_r # This is twist_per_z in the sample

    # Placeholder for actual hypoid gear generation logic
    # This will involve translating the `build_hypoid` sample code
    # to FreeCAD Part objects.
    
    # For now, create a simple cylinder as a placeholder
    radius = pitch_dia / 2.0 # Use pitch diameter as a guide
    
    cylinder = doc.addObject("Part::Cylinder", "PlaceholderCylinder")
    cylinder.Radius = radius
    cylinder.Height = p.face_width
    cylinder.Placement = App.Placement(App.Vector(0,0,p.offset),App.Rotation(0,0,0,1)) # Offset for visual cue
    
    body.addObject(cylinder)
    body.Tip = cylinder

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass

class HypoidGearCreateObject():
    """Command to create a new hypoid gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Hypoid Gear",
            'ToolTip': "Create parametric hypoid gear"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # --- Generate Unique Body Name ---
        base_name = "HypoidGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "HypoidGearParameters")
        hypoid_gear = HypoidGear(gear_obj)
        
        # Assign unique name to the property so gearMath uses it
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return hypoid_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class HypoidGear():
    """FeaturePython object for parametric hypoid gear."""

    def __init__(self, obj):
        """Initialize hypoid gear with default parameters.

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
            "App::PropertyLength", "Module", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger", "NumberOfTeeth", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"] # Profile shift might be applicable

        # Hypoid specific properties
        obj.addProperty(
            "App::PropertyLength", "Offset", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Offset between gear axes")
        ).Offset = 10.0

        obj.addProperty(
            "App::PropertyAngle", "SpiralAngle", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Spiral angle of the teeth")
        ).SpiralAngle = 35.0

        obj.addProperty(
            "App::PropertyLength", "FaceWidth", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of the gear face")
        ).FaceWidth = 18.0

        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString", "BodyName", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = H["body_name"]
        obj.BodyName = "HypoidGear" # Override default spur gear name

        # Bore parameters (hypoid gears typically don't have standard bores like this)
        obj.addProperty(
            "App::PropertyEnumeration", "BoreType", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole")
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = "none" # Default to none for hypoid

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


        self.Type = 'HypoidGear'
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

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        doc.removeObject(old_body)
                self.last_body_name = new_name

        # Update read-only calculated properties
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "Offset", "SpiralAngle", "FaceWidth"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                # offset = fp.Offset.Value # Not directly used in these calculations
                # spiral_angle = fp.SpiralAngle.Value # Not directly used in these calculations

                # These calculations are for a spur gear, may need adjustment for hypoid
                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(pitch_dia, module) # Profile shift might be less relevant for hypoid
                root_dia = gearMath.calcDedendumDiameter(pitch_dia, module)

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
            "offset": float(self.Object.Offset.Value),
            "spiral_angle": float(self.Object.SpiralAngle.Value),
            "face_width": float(self.Object.FaceWidth.Value),
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
                generateHypoidGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Hypoid Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Hypoid Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Hypoid Gear Error: {str(e)}\n")
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


class ViewProviderHypoidGear:
    """View provider for HypoidGear object."""

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
    FreeCADGui.addCommand('HypoidGearCreateObject', HypoidGearCreateObject())
    # App.Console.PrintMessage("HypoidGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register HypoidGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())

class HypoidGearCreateObject():
    """Command to create a new hypoid gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Hypoid Gear",
            'ToolTip': "Create parametric hypoid gear"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # --- Generate Unique Body Name ---
        base_name = "HypoidGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "HypoidGearParameters")
        hypoid_gear = HypoidGear(gear_obj)
        
        # Assign unique name to the property so gearMath uses it
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return hypoid_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class HypoidGear():
    """FeaturePython object for parametric hypoid gear."""

    def __init__(self, obj):
        """Initialize hypoid gear with default parameters.

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
            "App::PropertyLength", "Module", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger", "NumberOfTeeth", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"] # Profile shift might be applicable

        # Hypoid specific properties
        obj.addProperty(
            "App::PropertyLength", "Offset", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Offset between gear axes")
        ).Offset = 10.0

        obj.addProperty(
            "App::PropertyAngle", "SpiralAngle", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Spiral angle of the teeth")
        ).SpiralAngle = 35.0

        obj.addProperty(
            "App::PropertyLength", "FaceWidth", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of the gear face")
        ).FaceWidth = 18.0

        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString", "BodyName", "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = H["body_name"]
        obj.BodyName = "HypoidGear" # Override default spur gear name

        # Bore parameters (hypoid gears typically don't have standard bores like this)
        obj.addProperty(
            "App::PropertyEnumeration", "BoreType", "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole")
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = "none" # Default to none for hypoid

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


        self.Type = 'HypoidGear'
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

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        doc.removeObject(old_body)
                self.last_body_name = new_name

        # Update read-only calculated properties
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "Offset", "SpiralAngle", "FaceWidth"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                # offset = fp.Offset.Value # Not directly used in these calculations
                # spiral_angle = fp.SpiralAngle.Value # Not directly used in these calculations

                # These calculations are for a spur gear, may need adjustment for hypoid
                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(pitch_dia, module) # Profile shift might be less relevant for hypoid
                root_dia = gearMath.calcDedendumDiameter(pitch_dia, module)

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
            "offset": float(self.Object.Offset.Value),
            "spiral_angle": float(self.Object.SpiralAngle.Value),
            "face_width": float(self.Object.FaceWidth.Value),
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
                generateHypoidGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Hypoid Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Hypoid Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Hypoid Gear Error: {str(e)}\n")
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


class ViewProviderHypoidGear:
    """View provider for HypoidGear object."""

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
    FreeCADGui.addCommand('HypoidGearCreateObject', HypoidGearCreateObject())
    # App.Console.PrintMessage("HypoidGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register HypoidGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())
