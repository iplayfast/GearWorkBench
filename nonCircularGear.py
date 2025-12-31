"""Non-Circular Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric non-circular gears.

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
mainIcon = os.path.join(smWB_icons_path, 'NonCircularGear.svg') 

version = 'Nov 30, 2025'

def QT_TRANSLATE_NOOP(scope, text): return text

# ============================================================================
# GENERATION LOGIC 
# ============================================================================

def validateNonCircularParameters(parameters):
    if parameters["height"] <= 0: raise gearMath.GearParameterError("Height must be positive")
    if parameters["number_of_lobes"] < 1: raise gearMath.GearParameterError("Number of lobes must be at least 1")
    if parameters["major_radius"] <= 0: raise gearMath.GearParameterError("Major radius must be positive")

def generateNonCircularGearPart(doc, parameters):
    validateNonCircularParameters(parameters)
    
    body_name = parameters.get("body_name", "NonCircularGear")
    body = util.readyPart(doc, body_name)
    
    number_of_lobes = parameters["number_of_lobes"]
    major_radius = parameters["major_radius"]
    minor_radius = parameters["minor_radius"]
    height = parameters["height"]
    bore_type = parameters.get("bore_type", "none")
    
    # 1. Generate Profile Points
    # Use a sinusoidal function for the radius: R(theta) = R_avg + Amplitude * cos(N * theta)
    # R_avg = (Major + Minor) / 2
    # Amplitude = (Major - Minor) / 2
    r_avg = (major_radius + minor_radius) / 2.0
    amplitude = (major_radius - minor_radius) / 2.0
    
    num_points = 120 # Resolution
    profile_points = []
    
    for i in range(num_points):
        theta = (2 * math.pi * i) / num_points
        # The radius function
        r = r_avg + amplitude * math.cos(number_of_lobes * theta)
        
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        profile_points.append(App.Vector(x, y, 0))
    
    # Close the loop explicitly
    profile_points.append(profile_points[0])

    # 2. Create Sketch
    sketch = util.createSketch(body, 'LobedProfile')
    
    # Create a B-Spline from the points
    bspline = Part.BSplineCurve()
    bspline.interpolate(profile_points, True) # Periodic/Closed
    sketch.addGeometry(bspline, False)
    
    # 3. Extrude (Pad)
    pad = util.createPad(body, sketch, height, 'GearBody')
    body.Tip = pad

    # 4. Bore
    if bore_type != "none":
        util.createBore(body, parameters, height)

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass

class NonCircularGearCreateObject():
    """Command to create a new non-circular gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Non-Circular Gear",
            'ToolTip': "Create parametric non-circular gear"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # --- Generate Unique Body Name ---
        base_name = "NonCircularGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "NonCircularGearParameters")
        non_circular_gear = NonCircularGear(gear_obj)
        
        # Assign unique name to the property so gearMath uses it
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return non_circular_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class NonCircularGear():
    """FeaturePython object for parametric non-circular gear."""

    def __init__(self, obj):
        """Initialize non-circular gear with default parameters.

        Args:
            obj: FreeCAD document object
        """
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties (less applicable for non-circular, but keep for consistency)
        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1
        ).Version = version

        # Core gear parameters for non-circular
        obj.addProperty(
            "App::PropertyInteger", "NumberOfLobes", "NonCircularGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of lobes/repetitions in the profile")
        ).NumberOfLobes = 2 # Default to an elliptical-like shape

        obj.addProperty(
            "App::PropertyLength", "MajorRadius", "NonCircularGear",
            QT_TRANSLATE_NOOP("App::Property", "Major radius of the non-circular profile")
        ).MajorRadius = 15.0

        obj.addProperty(
            "App::PropertyLength", "MinorRadius", "NonCircularGear",
            QT_TRANSLATE_NOOP("App::Property", "Minor radius (for elliptical/lobed shapes)")
        ).MinorRadius = 10.0

        obj.addProperty(
            "App::PropertyLength", "Height", "NonCircularGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]
        
        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString", "BodyName", "NonCircularGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = H["body_name"]
        obj.BodyName = "NonCircularGear" # Override default spur gear name

        # Bore parameters (keep for consistency)
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


        self.Type = 'NonCircularGear'
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_body_name = obj.BodyName
        obj.Proxy = self

        # No direct derived read-only properties for non-circular in the same way
        # as involute gears. These will remain 0 unless explicitly set.
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Pitch diameter")).PitchDiameter = 0.0
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Base diameter")).BaseDiameter = 0.0
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Outer diameter")).OuterDiameter = 0.0
        obj.addProperty("App::PropertyLength", "RootDiameter", "read only", QT_TRANSLATE_NOOP("App::Property", "Root diameter")).RootDiameter = 0.0

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

        # For non-circular gears, read-only properties like diameters are not
        # directly calculated in the same way as involute gears.
        # They could be derived from the profile, but for now, they are static.
        
    def GetParameters(self):
        """Get current parameters as dictionary.

        Returns:
            Dictionary of current parameter values
        """
        parameters = {
            "number_of_lobes": int(self.Object.NumberOfLobes),
            "major_radius": float(self.Object.MajorRadius.Value),
            "minor_radius": float(self.Object.MinorRadius.Value),
            "height": float(self.Object.Height.Value),
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
                generateNonCircularGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Non-Circular Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Non-Circular Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Non-Circular Gear Error: {str(e)}\n")
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


class ViewProviderNonCircularGear:
    """View provider for NonCircularGear object."""

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
    FreeCADGui.addCommand('NonCircularGearCreateObject', NonCircularGearCreateObject())
    # App.Console.PrintMessage("NonCircularGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register NonCircularGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())
