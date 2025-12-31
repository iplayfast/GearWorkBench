import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher
import os
import math
from PySide import QtCore
from typing import List, Tuple # Added for type hints in new functions

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'ScrewGear.svg') 

version = 'Nov 30, 2025'

def QT_TRANSLATE_NOOP(scope, text): return text

# --- Helper functions adapted from samplecode/screw_gears.py (without numpy) ---

def involute_profile_2d_points(module: float, z: int, pressure_angle_deg: float, flank_steps: int = 40, add_tip_radius: float = 0.1) -> List[Tuple[float, float]]:
    """Generate a single tooth involute profile in 2D transverse plane (points only)."""
    # Use transverse module if a normal module is passed, but here we expect the effective module
    # or it will be calculated from m_n / cos(beta) in the calling context.
    # For now, this expects the module for the transverse plane.

    pitch_d = module * z
    r_pitch = pitch_d / 2.0
    r_base = gearMath.base_radius(pitch_d, pressure_angle_deg)
    r_tip = r_pitch + add_tip_radius * module # Using module for addendum
    
    if r_tip <= r_base:
        phi_max = 0.01
    else:
        # phi is the roll angle parameter 't' in involute_point
        phi_max = math.sqrt(max(0.0, (r_tip / r_base) ** 2 - 1.0))

    # Generate points along the involute curve for one flank
    phis = [i * phi_max / (flank_steps - 1) for i in range(flank_steps)]
    pts = [gearMath.involute_point(r_base, p) for p in phis]

    # Add root point (simple radial line from center)
    # The sample code adds a root point at (root_radius, 0.0) which assumes a specific orientation.
    # We will simplify by just adding the innermost point based on base_r or a calculated root_r
    
    # For a full tooth profile, we need two flanks + root connection.
    # This function is meant for a single involute flank.
    # The sample code adds a root point to close it, but for our purposes,
    # it's just the curve points.
    
    # Let's add a simplified root point if we really need to close the profile for a wire.
    # For sweeping, we typically need a profile to sweep.
    # We'll use this list of points as one flank of the tooth.
    
    # Add tip edge point (radial from center to outer_r)
    # The original sample code just gives points on the involute and a root point.
    # It does not explicitly close the profile with a tip arc or root arc.
    # For FreeCAD sketch, we need a closed contour, or just a single line if sweeping.
    
    # If we are to sweep this profile, we need a wire.
    # The points represent one flank. To make a full profile for sweeping, we need:
    # 1. The involute flank points.
    # 2. Mirrored involute flank points.
    # 3. An arc connecting the tip points.
    # 4. A line connecting the root points (or an arc, depending on geometry).
    
    # Given that gearMath.generateToothProfile already makes a closed profile,
    # it is likely better to adapt that for the base profile and then sweep.
    # However, the sample code uses this involute_profile_2d.
    
    # For now, let this function return points for ONE FLANK.
    return pts


def sweep_profile_helical_points(profile2d: List[Tuple[float, float]], helix_angle_deg: float, radius: float, face_width: float, steps_axial: int = 8, handed: int = 1) -> List[App.Vector]:
    """Sweeps a 2D profile (x,y) points around a cylinder of given radius along a helix."""
    beta = helix_angle_deg * util.DEG_TO_RAD
    axial_positions = [i * face_width / (steps_axial - 1) - face_width / 2.0 for i in range(steps_axial)]
    if steps_axial == 1: # Handle case of single slice
        axial_positions = [0.0]

    out_pts = []

    for z_axial in axial_positions:
        # Calculate twist for this axial position
        # theta = (z_axial * tan(beta)) / (radius if radius != 0 else 1e-9) - This formula seems to be for cylindrical gears
        # For sweep_profile_helical, it's relative twist.
        # Let's derive it from tangential movement along the helix.
        
        # d_tangential = z * tan(beta)
        # angle = d_tangential / r
        
        # Original from sample:
        theta_twist = (z_axial * math.tan(beta)) / (radius if radius != 0 else 1e-9)
        theta_twist *= handed # Apply handedness
        
        for x_2d, y_2d in profile2d:
            # Reconstruct original radius and angle from 2d profile points
            r_from_profile = math.hypot(x_2d, y_2d)
            angle_from_profile = math.atan2(y_2d, x_2d)
            
            # Apply helical twist
            final_angle = angle_from_profile + theta_twist
            
            # Reconstruct 3D point
            x = r_from_profile * math.cos(final_angle)
            y = r_from_profile * math.sin(final_angle)
            z = z_axial
            out_pts.append(App.Vector(x, y, z))

    return out_pts


# ============================================================================
# GENERATION LOGIC 
# ============================================================================

def validateScrewParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE: raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH: raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["face_width"] <= 0: raise gearMath.GearParameterError("Face Width must be positive")
    if parameters["helix_angle"] <= 0: raise gearMath.GearParameterError("Helix angle must be positive")

def generateScrewGearPart(doc, parameters):
    validateScrewParameters(parameters)
    
    body_name = parameters.get("body_name", "ScrewGear")
    body = util.readyPart(doc, body_name)
    
    module = parameters["module"] # Normal module
    num_teeth = parameters["num_teeth"]
    pressure_angle_deg = parameters["pressure_angle"]
    helix_angle_deg = parameters["helix_angle"]
    face_width = parameters["face_width"]
    handedness = parameters["handedness"]
    bore_type = parameters.get("bore_type", "none")

    # Calculate effective transverse module and pitch diameter
    transverse_mod = gearMath.transverse_module(module, helix_angle_deg)
    pitch_dia = gearMath.pitch_diameter(transverse_mod, num_teeth)
    
    # Calculate Transverse Pressure Angle
    # tan(alpha_t) = tan(alpha_n) / cos(beta)
    alpha_n_rad = pressure_angle_deg * util.DEG_TO_RAD
    beta_rad = helix_angle_deg * util.DEG_TO_RAD
    alpha_t_rad = math.atan(math.tan(alpha_n_rad) / math.cos(beta_rad))
    pressure_angle_t_deg = alpha_t_rad * util.RAD_TO_DEG
    
    r_pitch = pitch_dia / 2.0
    root_dia = gearMath.root_radius(pitch_dia, transverse_mod) * 2.0 # Dedendum diameter from transverse module

    # Determine handedness for sweep function
    handed_sign = 1 if handedness == "Right" else -1

    # Generate a single tooth 2D profile using gearMath.generateToothProfile
    # We must use Transverse parameters for the profile sketch!
    tooth_profile_sketch = util.createSketch(body, 'ToothProfile2D')
    
    profile_params = parameters.copy()
    profile_params["module"] = transverse_mod
    profile_params["pressure_angle"] = pressure_angle_t_deg
    
    gearMath.generateToothProfile(tooth_profile_sketch, profile_params)

    # Create a Datum Line for the Z-axis
    z_axis_line = body.newObject("PartDesign::Line", "Z_Axis_DatumLine")
    z_axis_line.MapMode = "Deactivated"

    # 1. Dedendum Cylinder (Base Feature)
    # The radius should precisely match the root of the tooth profile for clean fusion.
    dedendum_radius = root_dia / 2.0
    
    # Create an AdditiveCylinder directly to form the base feature
    dedendum_cylinder_feature = body.newObject("PartDesign::AdditiveCylinder", "DedendumCylinderFeature")
    dedendum_cylinder_feature.Radius = dedendum_radius
    dedendum_cylinder_feature.Height = face_width
    dedendum_cylinder_feature.Placement = App.Placement(App.Vector(0,0, -face_width/2.0), App.Rotation(0,0,0,1)) # Center the cylinder
    # This AdditiveCylinder should implicitly become the BaseFeature of the body.
    
    # 2. Tooth Profile Sketch (Centered at Z=0)
    screw_helix = body.newObject("PartDesign::AdditiveHelix", "ScrewToothHelix")
    screw_helix.Profile = tooth_profile_sketch # Link directly to the sketch
    screw_helix.Height = face_width
    screw_helix.ReferenceAxis = (z_axis_line, ['']) # Link to the datum line object
    
    # Pitch for screw gear, taking handedness into account
    # Pitch calculation from transverse geometry
    # The pitch of the helix for one full rotation is (pi * pitch_diameter) / tan(helix_angle)
    helix_pitch_val = abs((math.pi * pitch_dia) / math.tan(helix_angle_deg * util.DEG_TO_RAD))
    screw_helix.Pitch = helix_pitch_val
    if handedness == "Left":
        screw_helix.LeftHanded = True

    # Explicitly fuse the single helix with the dedendum cylinder to ensure it forms a single solid
    # before patterning. This addresses the "multiple solids" error.
    fused_single_tooth = body.newObject("PartDesign::Boolean", "SingleToothOnHub")
    fused_single_tooth.Type = "Fuse"
    fused_single_tooth.addObjects([dedendum_cylinder_feature, screw_helix])
    
    dedendum_cylinder_feature.Visibility = False
    screw_helix.Visibility = False
    
    # Use the generated helix (now fused with hub) as the base for a polar pattern
    polar = body.newObject('PartDesign::PolarPattern', 'ScrewTeethPolar')
    # Explicitly set the polar pattern's axis to the body's Z-axis (from Origin)
    origin = body.Origin
    z_axis = origin.OriginFeatures[2] # Z_Axis from body's Origin
    polar.Axis = (z_axis, [''])
    polar.Angle = 360
    polar.Occurrences = num_teeth
    polar.Originals = [fused_single_tooth] # Pattern the fused single tooth
    fused_single_tooth.Visibility = False
    polar.Visibility = True
    body.Tip = polar
    
    # Now, all subsequent Additive features will build on this cylinder.
    
    # Create the screw_helix. Profile sketch is already generated.
    
    # After dedendum_pad and polar, the tip is automatically the last one.
    # No need for explicit fuse (PartDesign::Boolean) if additive features are used correctly.
    # The body's tip will automatically be the polar pattern, fused with dedendum_pad.
    
    # Add bore
    if bore_type != "none":
        util.createBore(body, parameters, face_width)
        
    doc.recompute()
    if App.GuiUp:
        try: FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception: pass

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
