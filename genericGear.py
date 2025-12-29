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


# ============================================================================
# MASTER GEAR BUILDER - HERRINGBONE
# ============================================================================


def genericHerringboneGear(
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

    body_name = parameters.get("body_name", "GenericGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    bore_type = parameters.get("bore_type", "none")

    # Ensure helix_angle is in parameters for profile function
    # Use magnitude of angle1 (for herringbone, angle1 and angle2 are typically opposite)
    if "helix_angle" not in parameters:
        parameters = parameters.copy()
        parameters["helix_angle"] = abs(angle1) if angle1 != 0 else abs(angle2)

    # For dedendum calculation, use transverse module if helical
    helix_angle = parameters.get("helix_angle", 0.0)
    module = parameters["module"]
    if helix_angle != 0:
        beta_rad = helix_angle * util.DEG_TO_RAD
        mt = module / math.cos(beta_rad)  # transverse module
    else:
        mt = module

    dw = mt * num_teeth
    df = dw - 2 * mt * (gearMath.DEDENDUM_FACTOR - profile_shift)

    if profile_func is None:
        profile_func = gearMath.generateHelicalGearProfile

    if angle1 == 0:
        return _createTwoSketchHerringbone(
            body, parameters, height, num_teeth, angle2, df, bore_type, profile_func
        )
    else:
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
    """Create herringbone with 3 sketches (angle1 != 0)."""
    doc = body.Document

    sketch_bottom = util.createSketch(body, "ToothProfile_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    profile_func(sketch_bottom, parameters)

    sketch_middle = util.createSketch(body, "ToothProfile_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(0, 0, height / 2.0), App.Rotation(App.Vector(0, 0, 1), angle1)
    )
    profile_func(sketch_middle, parameters)

    sketch_top = util.createSketch(body, "ToothProfile_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle1 + angle2)
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

    return {"body": body}


# ============================================================================
# SPECIALIZED GEAR FUNCTIONS
# ============================================================================


def genericHelixGear(
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

    # Use two-sketch mode: angle1=0 triggers bottom→top loft without middle sketch
    return genericHerringboneGear(
        doc, params_with_helix, 0.0, total_rotation_deg, profile_func
    )


def genericSpurGear(doc, parameters, profile_func: Optional[Callable] = None):
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

    return genericHerringboneGear(doc, parameters, 0.0, 0.0, profile_func)

# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================

version = "Dec 29, 2025"

class GenericSpurGear:
    """FeaturePython object for parametric generic spur gear."""

    def __init__(self, obj):
        """Initialize generic spur gear with default parameters."""
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
            "App::PropertyInteger", "NumberOfTeeth", "GenericSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength", "Module", "GenericSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength", "Height", "GenericSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "GenericSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "GenericSpurGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyString", "BodyName", "GenericSpurGear",
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

        self.Type = "GenericSpurGear"
        self.Object = obj
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

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
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
                genericSpurGear(App.ActiveDocument, parameters)
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


class GenericHelixGear:
    """FeaturePython object for parametric generic helical gear."""

    def __init__(self, obj):
        """Initialize generic helical gear with default parameters."""
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
            "App::PropertyInteger", "NumberOfTeeth", "GenericHelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength", "Module", "GenericHelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength", "Height", "GenericHelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "GenericHelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "GenericHelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyAngle", "HelixAngle", "GenericHelixGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle in degrees")
        ).HelixAngle = 15.0

        obj.addProperty(
            "App::PropertyString", "BodyName", "GenericHelixGear",
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

        self.Type = "GenericHelixGear"
        self.Object = obj
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

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
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
                helix_angle = float(self.Object.HelixAngle.Value)
                genericHelixGear(App.ActiveDocument, parameters, helix_angle)
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


class GenericHerringboneGear:
    """FeaturePython object for parametric generic herringbone gear."""

    def __init__(self, obj):
        """Initialize generic herringbone gear with default parameters."""
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
            "App::PropertyInteger", "NumberOfTeeth", "GenericHerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth")
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyLength", "Module", "GenericHerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)")
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyLength", "Height", "GenericHerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear thickness/height")
        ).Height = H["height"]

        obj.addProperty(
            "App::PropertyAngle", "PressureAngle", "GenericHerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)")
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat", "ProfileShift", "GenericHerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)")
        ).ProfileShift = H["profile_shift"]

        obj.addProperty(
            "App::PropertyAngle", "Angle1", "GenericHerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "First helix angle (bottom to middle)")
        ).Angle1 = 15.0

        obj.addProperty(
            "App::PropertyAngle", "Angle2", "GenericHerringboneGear",
            QT_TRANSLATE_NOOP("App::Property", "Second helix angle (middle to top)")
        ).Angle2 = -15.0

        obj.addProperty(
            "App::PropertyString", "BodyName", "GenericHerringboneGear",
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

        self.Type = "GenericHerringboneGear"
        self.Object = obj
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

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
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
                angle1 = float(self.Object.Angle1.Value)
                angle2 = float(self.Object.Angle2.Value)
                genericHerringboneGear(App.ActiveDocument, parameters, angle1, angle2)
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
        self.iconfile = iconfile if iconfile else os.path.join(smWB_icons_path, 'spurGear.svg')

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
        if hasattr(self.Object, 'Proxy'):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        """Return object state for serialization."""
        return self.iconfile

    def __setstate__(self, state):
        """Restore object state from serialization."""
        if state:
            self.iconfile = state
        else:
            self.iconfile = os.path.join(smWB_icons_path, 'spurGear.svg')
        return None


# ============================================================================
# FREECAD COMMAND CLASSES
# ============================================================================

class GenericSpurGearCommand:
    """Command to create a new generic spur gear object."""

    def GetResources(self):
        return {
            'Pixmap': os.path.join(smWB_icons_path, 'spurGear.svg'),
            'MenuText': "&Create Generic Spur Gear",
            'ToolTip': "Create parametric involute spur gear using generic framework"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Generate unique body name
        base_name = "GenericSpurGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "GenericSpurGearParameters")
        spur_gear = GenericSpurGear(gear_obj)
        ViewProviderGenericGear(gear_obj.ViewObject, os.path.join(smWB_icons_path, 'spurGear.svg'))

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


class GenericHelixGearCommand:
    """Command to create a new generic helical gear object."""

    def GetResources(self):
        return {
            'Pixmap': os.path.join(smWB_icons_path, 'HelicalGear.svg'),
            'MenuText': "&Create Generic Helical Gear",
            'ToolTip': "Create parametric involute helical gear using generic framework"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Generate unique body name
        base_name = "GenericHelicalGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "GenericHelixGearParameters")
        helix_gear = GenericHelixGear(gear_obj)
        ViewProviderGenericGear(gear_obj.ViewObject, os.path.join(smWB_icons_path, 'HelicalGear.svg'))

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


class GenericHerringboneGearCommand:
    """Command to create a new generic herringbone gear object."""

    def GetResources(self):
        return {
            'Pixmap': os.path.join(smWB_icons_path, 'DoubleHelicalGear.svg'),
            'MenuText': "&Create Generic Herringbone Gear",
            'ToolTip': "Create parametric involute herringbone gear using generic framework"
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Generate unique body name
        base_name = "GenericHerringboneGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "GenericHerringboneGearParameters")
        herringbone_gear = GenericHerringboneGear(gear_obj)
        ViewProviderGenericGear(gear_obj.ViewObject, os.path.join(smWB_icons_path, 'DoubleHelicalGear.svg'))

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
    FreeCADGui.addCommand('GenericSpurGearCommand', GenericSpurGearCommand())
    FreeCADGui.addCommand('GenericHelixGearCommand', GenericHelixGearCommand())
    FreeCADGui.addCommand('GenericHerringboneGearCommand', GenericHerringboneGearCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register generic gear commands: {e}\n")
    import traceback
    App.Console.PrintError(traceback.format_exc())
