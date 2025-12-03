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
mainIcon = os.path.join(smWB_icons_path, 'internalSpurGear.svg')

# Debug: print icon path
# App.Console.PrintMessage(f"Internal Gear icon path: {mainIcon}\n")
if not os.path.exists(mainIcon):
    App.Console.PrintWarning(f"Internal Gear icon not found at: {mainIcon}\n")

version = 'Nov 30, 2025'


def QT_TRANSLATE_NOOP(scope, text):
    """Qt translation placeholder."""
    return text

# ============================================================================
# GENERATION LOGIC (Moved from gearMath.py)
# ============================================================================

def validateInternalParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH: raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0: raise gearMath.GearParameterError("Height must be positive")

def generateInternalToothProfile(sketch, parameters):
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

    num_inv_points = 5 
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

def generateInternalSpurGearPart(doc, parameters):
    validateInternalParameters(parameters)
    body_name = parameters.get("body_name", "InternalSpurGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    module = parameters["module"]
    profile_shift = parameters.get("profile_shift", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)

    dw = module * num_teeth
    df_internal = dw + 2 * module * (gearMath.DEDENDUM_FACTOR - profile_shift)
    outer_diameter = df_internal + 2 * rim_thickness

    tooth_sketch = util.createSketch(body, 'Tooth')
    generateInternalToothProfile(tooth_sketch, parameters)

    tooth_pad = util.createPad(body, tooth_sketch, height, 'Tooth')
    polar = util.createPolar(body, tooth_pad, tooth_sketch, num_teeth, 'Teeth')
    polar.Originals = [tooth_pad]
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar

    ring_sketch = util.createSketch(body, 'Ring')
    outer_circle = ring_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2), False)
    ring_sketch.addConstraint(Sketcher.Constraint('Coincident', outer_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint('Diameter', outer_circle, outer_diameter))

    inner_hole = ring_sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df_internal / 2), False)
    ring_sketch.addConstraint(Sketcher.Constraint('Coincident', inner_hole, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint('Diameter', inner_hole, df_internal))

    ring_pad = util.createPad(body, ring_sketch, height, 'Ring')
    polar.Visibility = False 
    ring_pad.Visibility = True 
    body.Tip = ring_pad

    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass

class InternalSpurGearCreateObject():
    """Command to create a new internal gear object."""

    def GetResources(self):
        return {
            'Pixmap': mainIcon,
            'MenuText': "&Create Internal Spur Gear",
            'ToolTip': "Create parametric involute internal (ring) spur gear"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        
        # --- Generate Unique Body Name ---
        base_name = "InternalSpurGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1
            
        gear_obj = doc.addObject("Part::FeaturePython", "InternalSpurGearParameters")
        internal_gear = InternalSpurGear(gear_obj)
        
        # Assign unique name
        gear_obj.BodyName = unique_name
        
        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return internal_gear

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class InternalSpurGear():
    """FeaturePython object for parametric internal gear."""

    def __init__(self, obj):
        """Initialize internal gear with default parameters.

        Args:
            obj: FreeCAD document object
        """
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
            "App::PropertyLength", "Module", "InternalSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger", "NumberOfTeeth", "InternalSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "InternalSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "InternalSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyLength", "Height", "InternalSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyLength", "RimThickness", "InternalSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Thickness of outer rim beyond tooth roots")
        ).RimThickness = H["rim_thickness"]
        
        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body")
        ).BodyName = H["body_name"]

        self.Type = 'InternalSpurGear'
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
        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value

                # Calculate derived dimensions (inverted for internal gear)
                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)

                # For internal gears: addendum is INWARD (smaller), dedendum is OUTWARD (larger)
                inner_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, module, profile_shift)
                outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, module, profile_shift, rim_thickness)

                # Update read-only properties
                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia

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
            "rim_thickness": float(self.Object.RimThickness.Value),
            "body_name": str(self.Object.BodyName), # Pass body name
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
                generateInternalSpurGearPart(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except gearMath.GearParameterError as e:
                App.Console.PrintError(f"Internal Gear Parameter Error: {str(e)}\n")
                App.Console.PrintError("Please adjust the parameters and try again.\n")
                raise
            except ValueError as e:
                App.Console.PrintError(f"Internal Gear Math Error: {str(e)}\n")
                raise
            except Exception as e:
                App.Console.PrintError(f"Internal Gear Error: {str(e)}\n")
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


class ViewProviderInternalSpurGear:
    """View provider for InternalSpurGear object."""

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
    FreeCADGui.addCommand('InternalSpurGearCreateObject', InternalSpurGearCreateObject())
    # App.Console.PrintMessage("InternalSpurGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register InternalSpurGearCreateObject: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())