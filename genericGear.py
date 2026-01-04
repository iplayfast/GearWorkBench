"""Generic Gear Framework for FreeCAD

This module provides a unified framework for creating different gear types
using a master herringbone gear builder that handles all cases through
helix angle distribution parameters.

Copyright 2025, Chris Bruner
Version v1.0.0
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
from typing import Optional, Callable
from PySide import QtCore

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def validateCommonParameters(parameters):
    """Validate common gear parameters."""
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")


def _applyOriginAndAngle(body, parameters):
    """Apply origin translation and angle rotation to the gear body.

    Args:
        body: FreeCAD body object
        parameters: Gear parameters dict with origin_x, origin_y, origin_z, and angle
    """
    origin_x = parameters.get("origin_x", 0.0)
    origin_y = parameters.get("origin_y", 0.0)
    origin_z = parameters.get("origin_z", 0.0)
    angle = parameters.get("angle", 0.0)

    # Create placement from origin and angle
    # IMPORTANT: Set the placement directly, don't multiply!
    # Multiplying would accumulate transforms on each recompute
    translation = App.Vector(origin_x, origin_y, origin_z)
    rotation = App.Rotation(App.Vector(0, 0, 1), angle)

    body.Placement = App.Placement(translation, rotation)


# ============================================================================
# MASTER GEAR BUILDER - HERRINGBONE
# ============================================================================


def herringboneGear(
    doc,
    parameters,
    angle1: float,
    angle2: float,
    profile_func: Optional[Callable] = None,
):
    """
    Master builder for all gear types using herringbone pattern.

    Creates tooth using up to 3 sketches (bottom, middle, top) based on angles:
    - If angle1 == 0: skips middle sketch, lofts bottom→top directly
    - If angle1 != 0: creates middle sketch at height/2, lofts bottom→middle→top

    Parameters use NORMAL module convention for helical/herringbone gears.

    Args:
        doc: FreeCAD document
        parameters: Gear parameters dict
        angle1: Rotation angle from bottom to middle sketch (degrees)
        angle2: Rotation angle from middle to top sketch (degrees)
        profile_func: Optional tooth profile function (uses default if None)

    Returns:
        Dictionary with 'body' key containing created body object
    """
    validateCommonParameters(parameters)

    # Apply backlash for external gears: subtract from profile shift to make teeth thinner
    backlash = parameters.get("backlash", 0.0)
    if backlash != 0.0:
        parameters = parameters.copy()
        original_shift = parameters.get("profile_shift", 0.0)
        parameters["profile_shift"] = original_shift - backlash

    body_name = parameters.get("body_name", "GenericGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    bore_type = parameters.get("bore_type", "none")

    # For herringbone gears, use helical tooth profile with transverse module
    # Calculate transverse module using the helix angle magnitude
    # For symmetric herringbone (angle2 = -angle1), use magnitude of angle1
    helix_angle_magnitude = abs(angle1) if angle1 != 0 else abs(angle2)

    if "helix_angle" not in parameters:
        parameters = parameters.copy()
        parameters["helix_angle"] = helix_angle_magnitude

    if helix_angle_magnitude != 0:
        beta_rad = helix_angle_magnitude * util.DEG_TO_RAD
        mt = parameters["module"] / math.cos(beta_rad)  # transverse module
    else:
        mt = parameters["module"]

    dw = mt * num_teeth
    # Use custom dedendum factor if provided (for cycloid and other special gears)
    dedendum_factor = parameters.get("dedendum_factor", gearMath.DEDENDUM_FACTOR)
    df = dw - 2 * mt * (dedendum_factor - profile_shift)

    if profile_func is None:
        profile_func = gearMath.generateHelicalGearProfile

    # Intelligent gear type detection based on angles:
    # - Both angles equal and non-zero: Helical gear (continuous twist)
    # - Angles different: True herringbone (V-shaped chevron)
    # - Both zero: Spur gear (straight teeth)
    if angle1 == angle2 and angle1 != 0:
        # Helical gear: two sketches with continuous twist (more efficient)
        return _createTwoSketchHerringbone(
            body, parameters, height, num_teeth, angle2, df, bore_type, profile_func
        )
    else:
        # Herringbone or spur: three sketches (handles angle1==angle2==0 as spur)
        return _createThreeSketchHerringbone(
            body,
            parameters,
            height,
            num_teeth,
            angle1,
            angle2,
            df,
            bore_type,
            profile_func,
        )


def _createTwoSketchHerringbone(
    body,
    parameters,
    height: float,
    num_teeth: int,
    angle2: float,
    df: float,
    bore_type: str,
    profile_func: Callable,
):
    """Create herringbone with 2 sketches (angle1 == 0)."""
    doc = body.Document

    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle2)
    )
    profile_func(sketch_top, parameters)

    tooth_loft = body.newObject("PartDesign::AdditiveLoft", "SingleTooth")
    tooth_loft.Profile = sketch_bottom
    tooth_loft.Sections = [sketch_top]
    tooth_loft.Ruled = True

    gear_teeth = util.createPolar(body, tooth_loft, sketch_bottom, num_teeth, "Teeth")
    gear_teeth.Originals = [tooth_loft]
    tooth_loft.Visibility = False
    sketch_bottom.Visibility = False
    sketch_top.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    dedendum_sketch = util.createSketch(body, "DedendumCircle")
    circle = dedendum_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01), False
    )
    dedendum_sketch.addConstraint(Sketcher.Constraint("Coincident", circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint("Diameter", circle, df + 0.02))

    dedendum_pad = util.createPad(body, dedendum_sketch, height, "DedendumCircle")
    body.Tip = dedendum_pad

    if bore_type != "none":
        util.createBore(body, parameters, height)

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    _applyOriginAndAngle(body, parameters)

    return {"body": body}


def _createThreeSketchHerringbone(
    body,
    parameters,
    height: float,
    num_teeth: int,
    angle1: float,
    angle2: float,
    df: float,
    bore_type: str,
    profile_func: Callable,
):
    """
    Create herringbone with 3 sketches as two helical halves joined at midpoint.

    This creates a true herringbone by:
    1. Bottom half: helical gear from Z=0 to Z=height/2 with helix angle = angle1
    2. Top half: helical gear from Z=height/2 to Z=height with helix angle = angle2

    For a symmetric herringbone, angle2 = -angle1.
    """
    doc = body.Document

    # Calculate sketch rotations based on helical gear math
    # Rotation = (height_segment) * tan(helix_angle) / pitch_radius
    mn = parameters["module"]
    helix_angle1 = angle1  # Helix angle in degrees for bottom half
    helix_angle2 = angle2  # Helix angle in degrees for top half

    # Use transverse module for pitch radius calculation
    if helix_angle1 != 0:
        beta_rad1 = helix_angle1 * util.DEG_TO_RAD
        mt1 = mn / math.cos(beta_rad1)
    else:
        mt1 = mn

    if helix_angle2 != 0:
        beta_rad2 = helix_angle2 * util.DEG_TO_RAD
        mt2 = mn / math.cos(beta_rad2)
    else:
        mt2 = mn

    # Use average transverse module for pitch radius (should be same for both halves)
    mt_avg = (mt1 + mt2) / 2.0
    pitch_radius = mt_avg * num_teeth / 2.0

    # Calculate rotation for each sketch
    # Bottom half: 0 to height/2 with helix_angle1
    half_height = height / 2.0
    if helix_angle1 != 0:
        rotation_middle = half_height * math.tan(helix_angle1 * util.DEG_TO_RAD) / pitch_radius
        rotation_middle_deg = rotation_middle * util.RAD_TO_DEG
    else:
        rotation_middle_deg = 0.0

    # Top half: height/2 to height with helix_angle2
    if helix_angle2 != 0:
        rotation_top_increment = half_height * math.tan(helix_angle2 * util.DEG_TO_RAD) / pitch_radius
        rotation_top_deg = rotation_middle_deg + (rotation_top_increment * util.RAD_TO_DEG)
    else:
        rotation_top_deg = rotation_middle_deg

    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    sketch_middle = util.createSketch(body, "ToothProfile_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(0, 0, half_height), App.Rotation(App.Vector(0, 0, 1), rotation_middle_deg)
    )
    profile_func(sketch_middle, parameters)

    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), rotation_top_deg)
    )
    profile_func(sketch_top, parameters)

    loft_bottom = body.newObject("PartDesign::AdditiveLoft", "BottomHalfTooth")
    loft_bottom.Profile = sketch_bottom
    loft_bottom.Sections = [sketch_middle]
    loft_bottom.Ruled = True

    loft_top = body.newObject("PartDesign::AdditiveLoft", "TopHalfTooth")
    loft_top.Profile = sketch_middle
    loft_top.Sections = [sketch_top]
    loft_top.Ruled = True

    gear_teeth = util.createPolar(body, loft_bottom, sketch_bottom, num_teeth, "Teeth")
    gear_teeth.Originals = [loft_bottom, loft_top]
    loft_bottom.Visibility = False
    loft_top.Visibility = False
    sketch_bottom.Visibility = False
    sketch_middle.Visibility = False
    sketch_top.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    dedendum_sketch = util.createSketch(body, "DedendumCircle")
    circle = dedendum_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01), False
    )
    dedendum_sketch.addConstraint(Sketcher.Constraint("Coincident", circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint("Diameter", circle, df + 0.02))

    dedendum_pad = util.createPad(body, dedendum_sketch, height, "DedendumCircle")
    body.Tip = dedendum_pad

    if bore_type != "none":
        util.createBore(body, parameters, height)

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    _applyOriginAndAngle(body, parameters)

    return {"body": body}


# ============================================================================
# SPECIALIZED GEAR FUNCTIONS
# ============================================================================


def helixGear(
    doc, parameters, helix_angle: float, profile_func: Optional[Callable] = None
):
    """
    Create a helical gear (single helix angle throughout).

    Uses two-sketch mode (angle1=0) with calculated total rotation for top sketch.
    Total rotation = height * tan(helix_angle) / pitch_radius

    Parameters use NORMAL module convention (standard for manufacturing):
    - module: normal module (mn)
    - pressure_angle: normal pressure angle (αn)
    The profile function converts to transverse values internally.

    Args:
        doc: FreeCAD document
        parameters: Gear parameters dict (with normal module)
        helix_angle: Helix angle in degrees
        profile_func: Optional tooth profile function (uses helical default if None)

    Returns:
        Dictionary with 'body' key containing created body object
    """
    if profile_func is None:
        profile_func = gearMath.generateHelicalGearProfile

    # Add helix angle to parameters so profile function can calculate transverse values
    params_with_helix = parameters.copy()
    params_with_helix["helix_angle"] = helix_angle

    # Apply backlash for external gears: subtract from profile shift to make teeth thinner
    backlash = parameters.get("backlash", 0.0)
    if backlash != 0.0:
        original_shift = parameters.get("profile_shift", 0.0)
        params_with_helix["profile_shift"] = original_shift - backlash

    # Calculate total rotation for top sketch
    # Using transverse module for pitch radius calculation
    mn = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    beta_rad = helix_angle * util.DEG_TO_RAD

    if helix_angle != 0:
        mt = mn / math.cos(beta_rad)  # transverse module
        pitch_radius = mt * num_teeth / 2.0
        # Total twist in radians, then convert to degrees
        total_rotation_rad = height * math.tan(beta_rad) / pitch_radius
        total_rotation_deg = total_rotation_rad * util.RAD_TO_DEG
    else:
        total_rotation_deg = 0.0

    # Pass same angle twice: angle1==angle2 triggers efficient 2-sketch helical mode
    return herringboneGear(
        doc, params_with_helix, total_rotation_deg, total_rotation_deg, profile_func
    )


def spurGear(doc, parameters, profile_func: Optional[Callable] = None):
    """
    Create a spur gear (zero helix angle).

    This is implemented as a herringbone gear with zero angles:
    angle1 = 0, angle2 = 0

    Args:
        doc: FreeCAD document
        parameters: Gear parameters dict
        profile_func: Optional tooth profile function (uses spur default if None)

    Returns:
        Dictionary with 'body' key containing created body object
    """
    if profile_func is None:
        profile_func = gearMath.generateSpurGearProfile

    # Apply backlash for external gears: subtract from profile shift to make teeth thinner
    backlash = parameters.get("backlash", 0.0)
    if backlash != 0.0:
        parameters = parameters.copy()
        original_shift = parameters.get("profile_shift", 0.0)
        parameters["profile_shift"] = original_shift - backlash

    return herringboneGear(doc, parameters, 0.0, 0.0, profile_func)


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================

version = "Dec 29, 2025"


class SpurGear:
    """FeaturePython object for parametric spur gear."""

    def __init__(self, obj):
        """Initialize spur gear with default parameters."""
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "BaseDiameter",
            "read only",
            QT_TRANSLATE_NOOP(
                "App::Property", "Base circle diameter (involute origin)"
            ),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
            1,
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "SpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "SpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "SpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "SpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)"),
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "SpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "SpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
        ).Backlash = 0.0

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "SpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = H["body_name"]

        # Bore parameters
        obj.addProperty(
            "App::PropertyEnumeration",
            "BoreType",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole"),
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]

        obj.addProperty(
            "App::PropertyLength",
            "BoreDiameter",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
        ).BoreDiameter = H["bore_diameter"]

        obj.addProperty(
            "App::PropertyLength",
            "SquareCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore"),
        ).SquareCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "HexCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore"),
        ).HexCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "KeywayWidth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
        ).KeywayWidth = 2.0

        obj.addProperty(
            "App::PropertyLength",
            "KeywayDepth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
        ).KeywayDepth = 1.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginX",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "X coordinate of gear origin"),
        ).OriginX = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginY",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Y coordinate of gear origin"),
        ).OriginY = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginZ",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Z coordinate of gear origin"),
        ).OriginZ = 0.0

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Placement",
            QT_TRANSLATE_NOOP(
                "App::Property", "Rotation angle around Z axis (degrees)"
            ),
        ).Angle = 0.0

        self.Type = "SpurGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self

        # Trigger initial calculation
        self.onChanged(obj, "Module")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """Called when a property changes."""
        self.Dirty = True

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        if hasattr(old_body, "removeObjectsFromDocument"):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
            self.last_body_name = new_name

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Backlash", "Height"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(
                    pitch_dia, module, profile_shift
                )
                root_dia = gearMath.calcDedendumDiameter(
                    pitch_dia, module, profile_shift
                )

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
            "backlash": float(self.Object.Backlash),
            "height": float(self.Object.Height.Value),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            "origin_x": float(self.Object.OriginX.Value),
            "origin_y": float(self.Object.OriginY.Value),
            "origin_z": float(self.Object.OriginZ.Value),
            "angle": float(self.Object.Angle.Value),
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
                spurGear(App.ActiveDocument, parameters)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Generic Spur Gear Error: {str(e)}\n")
                import traceback

                App.Console.PrintError(traceback.format_exc())
                raise

    def execute(self, obj):
        """Execute gear generation with delay."""
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class HelixGear:
    """FeaturePython object for parametric helical gear."""

    def __init__(self, obj):
        """Initialize helical gear with default parameters."""
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "BaseDiameter",
            "read only",
            QT_TRANSLATE_NOOP(
                "App::Property", "Base circle diameter (involute origin)"
            ),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
            1,
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)"),
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyAngle",
            "HelixAngle",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle in degrees"),
        ).HelixAngle = 15.0

        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
        ).Backlash = 0.0

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "HelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = "HelicalGear"

        # Bore parameters
        obj.addProperty(
            "App::PropertyEnumeration",
            "BoreType",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole"),
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]

        obj.addProperty(
            "App::PropertyLength",
            "BoreDiameter",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
        ).BoreDiameter = H["bore_diameter"]

        obj.addProperty(
            "App::PropertyLength",
            "SquareCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore"),
        ).SquareCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "HexCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore"),
        ).HexCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "KeywayWidth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
        ).KeywayWidth = 2.0

        obj.addProperty(
            "App::PropertyLength",
            "KeywayDepth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
        ).KeywayDepth = 1.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginX",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "X coordinate of gear origin"),
        ).OriginX = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginY",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Y coordinate of gear origin"),
        ).OriginY = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginZ",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Z coordinate of gear origin"),
        ).OriginZ = 0.0

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Placement",
            QT_TRANSLATE_NOOP(
                "App::Property", "Rotation angle around Z axis (degrees)"
            ),
        ).Angle = 0.0

        self.Type = "HelixGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self

        self.onChanged(obj, "Module")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """Called when a property changes."""
        self.Dirty = True

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        if hasattr(old_body, "removeObjectsFromDocument"):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
            self.last_body_name = new_name

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "HelixAngle", "Backlash", "Height"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                helix_angle = fp.HelixAngle.Value

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                root_dia = gearMath.calcDedendumDiameter(
                    pitch_dia, mt, profile_shift
                )

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
            "backlash": float(self.Object.Backlash),
            "height": float(self.Object.Height.Value),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            "origin_x": float(self.Object.OriginX.Value),
            "origin_y": float(self.Object.OriginY.Value),
            "origin_z": float(self.Object.OriginZ.Value),
            "angle": float(self.Object.Angle.Value),
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
                helix_angle = float(self.Object.HelixAngle.Value)
                helixGear(App.ActiveDocument, parameters, helix_angle)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Generic Helix Gear Error: {str(e)}\n")
                import traceback

                App.Console.PrintError(traceback.format_exc())
                raise

    def execute(self, obj):
        """Execute gear generation with delay."""
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class HerringboneGear:
    """FeaturePython object for parametric herringbone gear."""

    def __init__(self, obj):
        """Initialize herringbone gear with default parameters."""
        self.Dirty = False
        H = gearMath.generateDefaultParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString",
            "Version",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Workbench version"),
            1,
        ).Version = version

        obj.addProperty(
            "App::PropertyLength",
            "PitchDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (where gears mesh)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "BaseDiameter",
            "read only",
            QT_TRANSLATE_NOOP(
                "App::Property", "Base circle diameter (involute origin)"
            ),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (tip of teeth)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (bottom of teeth)"),
            1,
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength",
            "Height",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height"),
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)"),
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyAngle",
            "Angle1",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "First helix angle (bottom to middle)"),
        ).Angle1 = 15.0

        obj.addProperty(
            "App::PropertyAngle",
            "Angle2",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Second helix angle (middle to top)"),
        ).Angle2 = -15.0

        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Backlash clearance for 3D printing (0.0-0.3mm)"),
        ).Backlash = 0.0

        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "HerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = "HerringboneGear"

        # Bore parameters
        obj.addProperty(
            "App::PropertyEnumeration",
            "BoreType",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole"),
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = H["bore_type"]

        obj.addProperty(
            "App::PropertyLength",
            "BoreDiameter",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Diameter of center bore"),
        ).BoreDiameter = H["bore_diameter"]

        obj.addProperty(
            "App::PropertyLength",
            "SquareCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for square bore"),
        ).SquareCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "HexCornerRadius",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Corner radius for hexagonal bore"),
        ).HexCornerRadius = 0.5

        obj.addProperty(
            "App::PropertyLength",
            "KeywayWidth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)"),
        ).KeywayWidth = 2.0

        obj.addProperty(
            "App::PropertyLength",
            "KeywayDepth",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Depth of keyway"),
        ).KeywayDepth = 1.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginX",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "X coordinate of gear origin"),
        ).OriginX = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginY",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Y coordinate of gear origin"),
        ).OriginY = 0.0

        obj.addProperty(
            "App::PropertyDistance",
            "OriginZ",
            "Placement",
            QT_TRANSLATE_NOOP("App::Property", "Z coordinate of gear origin"),
        ).OriginZ = 0.0

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Placement",
            QT_TRANSLATE_NOOP(
                "App::Property", "Rotation angle around Z axis (degrees)"
            ),
        ).Angle = 0.0

        self.Type = "HerringboneGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self

        self.onChanged(obj, "Module")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        """Called when a property changes."""
        self.Dirty = True

        if prop == "BodyName":
            old_name = self.last_body_name
            new_name = fp.BodyName
            # Only delete old body if we had a previous name (not the initial assignment)
            if old_name is not None and old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    old_body = doc.getObject(old_name)
                    if old_body:
                        if hasattr(old_body, "removeObjectsFromDocument"):
                            old_body.removeObjectsFromDocument()
                        doc.removeObject(old_name)
            self.last_body_name = new_name

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "Angle1", "Angle2", "Backlash", "Height"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                angle1 = fp.Angle1.Value
                angle2 = fp.Angle2.Value

                # Use magnitude of angle1 for helix angle (like internal herringbone)
                helix_angle = abs(angle1) if angle1 != 0 else abs(angle2)

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                root_dia = gearMath.calcDedendumDiameter(
                    pitch_dia, mt, profile_shift
                )

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
            "backlash": float(self.Object.Backlash),
            "height": float(self.Object.Height.Value),
            "body_name": str(self.Object.BodyName),
            "bore_type": str(self.Object.BoreType),
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "square_corner_radius": float(self.Object.SquareCornerRadius.Value),
            "hex_corner_radius": float(self.Object.HexCornerRadius.Value),
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            "origin_x": float(self.Object.OriginX.Value),
            "origin_y": float(self.Object.OriginY.Value),
            "origin_z": float(self.Object.OriginZ.Value),
            "angle": float(self.Object.Angle.Value),
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
                angle1 = float(self.Object.Angle1.Value)
                angle2 = float(self.Object.Angle2.Value)
                herringboneGear(App.ActiveDocument, parameters, angle1, angle2)
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Generic Herringbone Gear Error: {str(e)}\n")
                import traceback

                App.Console.PrintError(traceback.format_exc())
                raise

    def execute(self, obj):
        """Execute gear generation with delay."""
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)


class ViewProviderGenericGear:
    """View provider for generic gear objects."""

    def __init__(self, obj, iconfile=None):
        """Initialize view provider."""
        obj.Proxy = self
        self.part = obj
        self.iconfile = (
            iconfile if iconfile else os.path.join(smWB_icons_path, "spurGear.svg")
        )

    def attach(self, obj):
        """Setup the scene sub-graph."""
        self.ViewObject = obj
        self.Object = obj.Object
        return

    def updateData(self, fp, prop):
        """Called when a property of the handled feature has changed."""
        return

    def getDisplayModes(self, obj):
        """Return a list of display modes."""
        modes = ["Shaded", "Wireframe", "Flat Lines"]
        return modes

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode."""
        return "Shaded"

    def setDisplayMode(self, mode):
        """Set the display mode."""
        return mode

    def onChanged(self, vobj, prop):
        """Called when a view property has changed."""
        return

    def getIcon(self):
        """Return the icon in XPM format."""
        return self.iconfile

    def doubleClicked(self, vobj):
        """Called when object is double-clicked."""
        return True

    def setupContextMenu(self, vobj, menu):
        """Setup custom context menu."""
        from PySide import QtGui

        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        """Force regeneration of the gear."""
        if hasattr(self.Object, "Proxy"):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        """Return object state for serialization."""
        return self.iconfile

    def __setstate__(self, state):
        """Restore object state from serialization."""
        if state:
            self.iconfile = state
        else:
            self.iconfile = os.path.join(smWB_icons_path, "spurGear.svg")
        return None


# ============================================================================
# FREECAD COMMAND CLASSES
# ============================================================================


class SpurGearCommand:
    """Command to create a new spur gear object."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "spurGear.svg"),
            "MenuText": "&Create Spur Gear",
            "ToolTip": "Create parametric involute spur gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Generate unique body name
        base_name = "SpurGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "SpurGearParameters")
        spur_gear = SpurGear(gear_obj)
        ViewProviderGenericGear(
            gear_obj.ViewObject, os.path.join(smWB_icons_path, "spurGear.svg")
        )

        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class HelixGearCommand:
    """Command to create a new helical gear object."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "HelicalGear.svg"),
            "MenuText": "&Create Helical Gear",
            "ToolTip": "Create parametric involute helical gear",
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

        gear_obj = doc.addObject("Part::FeaturePython", "HelixGearParameters")
        helix_gear = HelixGear(gear_obj)
        ViewProviderGenericGear(
            gear_obj.ViewObject, os.path.join(smWB_icons_path, "HelicalGear.svg")
        )

        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class HerringboneGearCommand:
    """Command to create a new herringbone gear object."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "DoubleHelicalGear.svg"),
            "MenuText": "&Create Herringbone Gear",
            "ToolTip": "Create parametric involute herringbone gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Generate unique body name
        base_name = "HerringboneGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "HerringboneGearParameters")
        herringbone_gear = HerringboneGear(gear_obj)
        ViewProviderGenericGear(
            gear_obj.ViewObject, os.path.join(smWB_icons_path, "DoubleHelicalGear.svg")
        )

        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


# Register commands with FreeCAD
try:
    FreeCADGui.addCommand("SpurGearCommand", SpurGearCommand())
    FreeCADGui.addCommand("HelixGearCommand", HelixGearCommand())
    FreeCADGui.addCommand("HerringboneGearCommand", HerringboneGearCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register generic gear commands: {e}\n")
    import traceback

    App.Console.PrintError(traceback.format_exc())
