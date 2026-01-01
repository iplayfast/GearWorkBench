import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher
import os
import math
from PySide import QtCore
import genericScrew

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'ScrewGear.svg') 

version = 'Nov 30, 2025'

def QT_TRANSLATE_NOOP(scope, text): return text

# ============================================================================
# GENERATION LOGIC
# ============================================================================

def validateScrewParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH: raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["face_width"] <= 0: raise gearMath.GearParameterError("Face Width must be positive")
    if parameters["helix_angle"] <= 0: raise gearMath.GearParameterError("Helix angle must be positive")

def generateScrewGearPart(doc, parameters):
    """Generate screw gear using the generic screw system.

    Screw gears (crossed-axis helical gears) operate on non-parallel,
    non-intersecting shafts, typically at 90 degrees to each other.
    They use helical teeth that are swept along a cylindrical path.
    """
    validateScrewParameters(parameters)

    # Use the generic screw builder with involute tooth profile
    result = genericScrew.genericScrewGear(
        doc,
        parameters,
        profile_func=gearMath.generateToothProfile
    )

    return result

class ScrewGearCreateObject():
    """Command to create a new screw gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Screw Gear",
            'ToolTip': "Create parametric screw (crossed-helical) gear"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # --- Generate Unique Body Name ---
        base_name = "ScrewGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "ScrewGearParameters")
        screw_gear = ScrewGear(gear_obj)
        
        # Assign unique name to the property so gearMath uses it
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return screw_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class ScrewGear():
    """FeaturePython object for parametric screw gear."""

    def __init__(self, obj):
        """Initialize screw gear with default parameters.

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
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (transverse)"),
            1
        )

        obj.addProperty(
            "App::PropertyLength", "BaseDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Base circle diameter (transverse)"),
            1
        )

        obj.addProperty(
            "App::PropertyLength", "OuterDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (transverse)"),
            1
        )

        obj.addProperty(
            "App::PropertyLength", "RootDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (transverse)"),
            1
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyLength", "Module", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Normal module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger", "NumberOfTeeth", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Normal pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Normal profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        # Screw Gear specific properties
        obj.addProperty(
            "App::PropertyAngle", "HelixAngle", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle of the teeth")
        ).HelixAngle = 30.0 # Default helix angle

        obj.addProperty(
            "App::PropertyLength", "FaceWidth", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of the gear face")
        ).FaceWidth = 10.0

        obj.addProperty(
            "App::PropertyEnumeration", "Handedness", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Handedness of helix")
        )
        obj.Handedness = ["Right", "Left"]
        obj.Handedness = "Right"

        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString", "BodyName", "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = H["body_name"]
        obj.BodyName = "ScrewGear"

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


        self.Type = 'ScrewGear'
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_body_name = obj.BodyName
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
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "HelixAngle", "FaceWidth"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                helix_angle = fp.HelixAngle.Value

                # Calculations for screw gear often involve transverse plane
                # First, get transverse module and pressure angle
                transverse_module = gearMath.transverse_module(module, helix_angle)
                
                # Pitch diameter in transverse plane
                pitch_dia = gearMath.pitch_diameter(transverse_module, num_teeth)
                
                # Base diameter in transverse plane (using transverse pressure angle, which can be derived)
                # For simplicity, using normal pressure angle for now, this needs to be revisited for accuracy
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle) 

                # Outer and Root diameters also in transverse plane
                outer_dia = gearMath.calcAddendumDiameter(pitch_dia, transverse_module)
                root_dia = gearMath.calcDedendumDiameter(pitch_dia, transverse_module)

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
            "helix_angle": float(self.Object.HelixAngle.Value),
            "face_width": float(self.Object.FaceWidth.Value),
            "handedness": str(self.Object.Handedness),
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
                generateScrewGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Screw Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Screw Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Screw Gear Error: {str(e)}\n")
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


class ViewProviderScrewGear:
    """View provider for ScrewGear object."""

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
    FreeCADGui.addCommand('ScrewGearCreateObject', ScrewGearCreateObject())
    # App.Console.PrintMessage("ScrewGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register ScrewGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())
