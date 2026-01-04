"""Internal Gear Framework for FreeCAD

This module provides a unified framework for creating internal (ring) gear types
using a master herringbone gear builder that handles all cases through
helix angle distribution parameters.

Refactored to use Boolean Cut with EXTERNAL TOOTH PROFILE (The Gap).
Fixes:
- Adds clearance epsilon to cutter to prevent coincident face errors.

Copyright 2025, Chris Bruner
Version v1.3.0
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

version = "Dec 31, 2025"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VALIDATION
# ============================================================================


def validateInternalParameters(parameters):
    """Validate common internal gear parameters."""
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["height"] <= 0:
        raise gearMath.GearParameterError("Height must be positive")


# ============================================================================
# PROFILE GENERATORS
# ============================================================================


def generateInternalCutterProfile(sketch, parameters):
    """
    Generates the CUTTER profile.
    For an internal gear, the 'Gap' is the shape of an EXTERNAL tooth.
    So we call the standard external tooth generator here.

    IMPORTANT: We add a small positive profile shift to the cutter to create
    backlash clearance, allowing the external gear to fit into the gap.
    """
    # Add backlash clearance by increasing the cutter's profile shift
    # This makes the tooth gap slightly larger than the mating tooth
    cutter_params = parameters.copy()

    # Use backlash parameter (default 0.15 for 3D printing, typical range 0.05-0.25)
    backlash = parameters.get("backlash", 0.15)
    original_shift = parameters.get("profile_shift", 0.0)
    cutter_params["profile_shift"] = original_shift + backlash

    gearMath.generateToothProfile(sketch, cutter_params)


def generateInternalHelicalCutterProfile(sketch, parameters):
    """
    Generates the Helical CUTTER profile (Transverse conversion).

    IMPORTANT: We add a small positive profile shift to the cutter to create
    backlash clearance, allowing the external gear to fit into the gap.
    """
    helix_angle = parameters.get("helix_angle", 0.0)

    if helix_angle == 0:
        generateInternalCutterProfile(sketch, parameters)
        return

    # Convert to transverse values
    beta_rad = helix_angle * util.DEG_TO_RAD
    cos_beta = math.cos(beta_rad)

    mn = parameters["module"]
    alpha_n = parameters["pressure_angle"]
    alpha_n_rad = alpha_n * util.DEG_TO_RAD

    # Transverse module and pressure angle
    mt = mn / cos_beta
    alpha_t_rad = math.atan(math.tan(alpha_n_rad) / cos_beta)
    alpha_t = alpha_t_rad * util.RAD_TO_DEG

    transverse_params = parameters.copy()
    transverse_params["module"] = mt
    transverse_params["pressure_angle"] = alpha_t

    # Add backlash clearance by increasing the cutter's profile shift
    # This makes the tooth gap slightly larger than the mating tooth
    backlash = parameters.get("backlash", 0.15)
    original_shift = parameters.get("profile_shift", 0.0)
    transverse_params["profile_shift"] = original_shift + backlash

    # Generate the EXTERNAL tooth profile (which is the cutter for the gap)
    gearMath.generateToothProfile(sketch, transverse_params)


# ============================================================================
# MASTER INTERNAL GEAR BUILDER
# ============================================================================


def internalHerringboneGear(
    doc,
    parameters,
    angle1: float,
    angle2: float,
    profile_func: Optional[Callable] = None,
):
    """
    Master builder using Boolean Cut.
    """
    validateInternalParameters(parameters)

    body_name = parameters.get("body_name", "InternalGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)
    backlash = parameters.get("backlash", 0.15)

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

    # CALCULATE DIAMETERS
    # Tip Radius (Inner Hole): where the teeth END.
    ra_internal = dw / 2.0 - mt * (gearMath.ADDENDUM_FACTOR + profile_shift)

    # Root Radius (Bottom of the cut): where the teeth START.
    rf_internal = dw / 2.0 + mt * (gearMath.DEDENDUM_FACTOR - profile_shift)

    # Outer Diameter of the Part
    outer_diameter = rf_internal * 2.0 + 2 * rim_thickness

    if profile_func is None:
        profile_func = generateInternalHelicalCutterProfile

    # CUTTER CONFIGURATION
    # Use a copy of parameters - profile_shift (including backlash) will control cutter size
    cut_params = parameters.copy()
    # Note: We no longer override tip_radius here, allowing backlash to affect cutter dimensions

    # Intelligent gear type detection based on angles:
    # - Both angles equal and non-zero: Internal Helical gear (continuous twist)
    # - Angles different: True internal herringbone (V-shaped chevron)
    # - Both zero: Internal spur gear (straight teeth)
    if angle1 == angle2 and angle1 != 0:
        # Internal Helical gear: two sketches with continuous twist (more efficient)
        return _createTwoSketchInternalGear(
            body,
            cut_params,
            height,
            num_teeth,
            angle2,
            ra_internal,
            outer_diameter,
            profile_func,
        )
    else:
        # Internal Herringbone or spur: three sketches (handles angle1==angle2==0 as spur)
        return _createThreeSketchInternalGear(
            body,
            cut_params,
            height,
            num_teeth,
            angle1,
            angle2,
            ra_internal,
            outer_diameter,
            profile_func,
        )


def _createTwoSketchInternalGear(
    body,
    parameters,
    height,
    num_teeth,
    angle2,
    ra_internal,
    outer_diameter,
    profile_func,
):
    """Create internal gear with 2 sketches (Subtractive).

    Creates full ring, then one tooth gap, then patterns the cut.
    Much faster than patterning ring segments.
    """
    doc = body.Document

    # 1. Create FULL Ring (360-degree annulus)
    ring_sketch = util.createSketch(body, "Ring")

    # Create full circles
    outer_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0)
    inner_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), ra_internal)

    outer_circle_idx = ring_sketch.addGeometry(outer_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle_idx, 3, -1, 1))
    ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", outer_circle_idx, outer_diameter)
    )

    inner_circle_idx = ring_sketch.addGeometry(inner_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle_idx, 3, -1, 1))
    ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", inner_circle_idx, ra_internal * 2.0)
    )

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal gear: Created ring base...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 2. Create Cutters for ONE tooth gap
    sketch_bottom = util.createSketch(body, "ToothGap_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    sketch_bottom.MapMode = "Deactivated"
    profile_func(sketch_bottom, parameters)

    sketch_top = util.createSketch(body, "ToothGap_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle2)
    )
    sketch_top.MapMode = "Deactivated"
    profile_func(sketch_top, parameters)

    # 3. Subtractive Loft for ONE tooth gap
    tooth_cut = body.newObject("PartDesign::SubtractiveLoft", "ToothGapCut")
    tooth_cut.Profile = sketch_bottom
    tooth_cut.Sections = [sketch_top]
    tooth_cut.Ruled = True
    tooth_cut.Refine = False

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal gear: Created tooth gap cut...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 4. Pattern the CUT operation (not the ring)
    App.Console.PrintMessage(f"Internal gear: Creating polar pattern for {num_teeth} teeth (this may take a while)...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]
    gear_teeth.Axis = (z_axis, ["N_Axis"])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [tooth_cut]

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal gear: Polar pattern created, finalizing...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # Cleanup
    ring_sketch.Visibility = False
    sketch_bottom.Visibility = False
    sketch_top.Visibility = False
    tooth_cut.Visibility = False
    ring_pad.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    doc.recompute()

    # Show completion in FreeCAD Report View
    App.Console.PrintMessage(f"✓ Internal gear with {num_teeth} teeth created successfully!\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


def _createThreeSketchInternalGear(
    body,
    parameters,
    height,
    num_teeth,
    angle1,
    angle2,
    ra_internal,
    outer_diameter,
    profile_func,
):
    """
    Create internal herringbone gear as two helical halves joined at midpoint.

    This creates a true herringbone by:
    1. Bottom half: helical gear from Z=0 to Z=height/2 with helix angle = angle1
    2. Top half: helical gear from Z=height/2 to Z=height with helix angle = angle2

    For a symmetric herringbone, angle2 = -angle1.
    """
    doc = body.Document
    half_height = height / 2.0

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

    # 1. Create FULL Ring (360-degree annulus)
    ring_sketch = util.createSketch(body, "Ring")

    # Create full circles
    outer_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0)
    inner_circle_geom = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), ra_internal)

    outer_circle_idx = ring_sketch.addGeometry(outer_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle_idx, 3, -1, 1))
    ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", outer_circle_idx, outer_diameter)
    )

    inner_circle_idx = ring_sketch.addGeometry(inner_circle_geom, False)
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle_idx, 3, -1, 1))
    ring_sketch.addConstraint(
        Sketcher.Constraint("Diameter", inner_circle_idx, ra_internal * 2.0)
    )

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal herringbone: Created ring base...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 2. Create Cutters for ONE tooth gap (The Gap)
    sketch_bottom = util.createSketch(body, "ToothGap_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    sketch_bottom.MapMode = "Deactivated"
    profile_func(sketch_bottom, parameters)

    sketch_middle = util.createSketch(body, "ToothGap_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(0, 0, half_height), App.Rotation(App.Vector(0, 0, 1), rotation_middle_deg)
    )
    sketch_middle.MapMode = "Deactivated"
    profile_func(sketch_middle, parameters)

    sketch_top = util.createSketch(body, "ToothGap_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), rotation_top_deg)
    )
    sketch_top.MapMode = "Deactivated"
    profile_func(sketch_top, parameters)

    # 3. Apply Subtractive Lofts for ONE tooth gap
    cut_lower = body.newObject("PartDesign::SubtractiveLoft", "ToothGapLower")
    cut_lower.Profile = sketch_bottom
    cut_lower.Sections = [sketch_middle]
    cut_lower.Ruled = True
    cut_lower.Refine = False

    cut_upper = body.newObject("PartDesign::SubtractiveLoft", "ToothGapUpper")
    cut_upper.Profile = sketch_middle
    cut_upper.Sections = [sketch_top]
    cut_upper.Ruled = True
    cut_upper.Refine = False

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal herringbone: Created tooth gap cuts...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # 4. Pattern BOTH CUT operations together (faster than separate patterns)
    App.Console.PrintMessage(f"Internal herringbone: Creating polar pattern for {num_teeth} teeth (this may take a while)...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]
    gear_teeth.Axis = (z_axis, ["N_Axis"])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [cut_lower, cut_upper]

    # Show progress in FreeCAD Report View
    App.Console.PrintMessage("Internal herringbone: Polar pattern created, finalizing...\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()

    # Cleanup
    ring_sketch.Visibility = False
    sketch_bottom.Visibility = False
    sketch_middle.Visibility = False
    sketch_top.Visibility = False
    cut_lower.Visibility = False
    cut_upper.Visibility = False
    ring_pad.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    doc.recompute()

    # Show completion in FreeCAD Report View
    App.Console.PrintMessage(f"✓ Internal herringbone gear with {num_teeth} teeth created successfully!\n")
    if App.GuiUp:
        QtCore.QCoreApplication.processEvents()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


# ============================================================================
# SPECIALIZED INTERNAL GEAR FUNCTIONS
# ============================================================================


def internalHelixGear(
    doc, parameters, helix_angle: float, profile_func: Optional[Callable] = None
):
    if profile_func is None:
        profile_func = generateInternalHelicalCutterProfile

    params_with_helix = parameters.copy()
    params_with_helix["helix_angle"] = helix_angle

    mn = parameters["module"]
    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    beta_rad = helix_angle * util.DEG_TO_RAD

    if helix_angle != 0:
        mt = mn / math.cos(beta_rad)
        pitch_radius = mt * num_teeth / 2.0
        total_rotation_rad = height * math.tan(beta_rad) / pitch_radius
        total_rotation_deg = total_rotation_rad * util.RAD_TO_DEG
    else:
        total_rotation_deg = 0.0

    # Pass same angle twice: angle1==angle2 triggers efficient 2-sketch helical mode
    return internalHerringboneGear(
        doc, params_with_helix, total_rotation_deg, total_rotation_deg, profile_func
    )


def internalSpurGear(doc, parameters, profile_func: Optional[Callable] = None):
    if profile_func is None:
        profile_func = generateInternalCutterProfile  # Use External profile as cutter

    return internalHerringboneGear(doc, parameters, 0.0, 0.0, profile_func)


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================


class InternalSpurGear:
    """FeaturePython object for parametric internal spur gear."""

    def __init__(self, obj):
        self.Dirty = False
        self.recomputing = False  # Guard against concurrent recompute calls
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty(
            "App::PropertyString", "Version", "read only", "", 1
        ).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty(
            "App::PropertyLength", "Module", "InternalSpurGear", "Normal module"
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "InternalSpurGear",
            "Number of teeth",
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "InternalSpurGear",
            "Normal pressure angle",
        ).PressureAngle = H["pressure_angle"]
        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "InternalSpurGear",
            "Profile shift coefficient",
        ).ProfileShift = H["profile_shift"]
        obj.addProperty(
            "App::PropertyLength", "Height", "InternalSpurGear", "Gear height"
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyLength", "RimThickness", "InternalSpurGear", "Rim thickness"
        ).RimThickness = H["rim_thickness"]
        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "InternalSpurGear",
            "Backlash clearance (extra profile shift for tooth gaps, 0.1-0.2 for 3D printing)"
        ).Backlash = 0.15
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalSpurGear", "Body name"
        ).BodyName = "InternalSpurGear"

        # Store the actual body name created by gear generator
        self.created_body_name = None
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies

        self.Type = "InternalSpurGear"
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
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
                        doc.removeObject(old_name)  # removeObject expects a string
            self.last_body_name = new_name

        if prop in [
            "Module",
            "NumberOfTeeth",
            "PressureAngle",
            "ProfileShift",
            "RimThickness",
            "Backlash",
        ]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value

                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(
                    pitch_dia, module, profile_shift
                )
                outer_dia = gearMath.calcInternalDedendumDiameter(
                    pitch_dia, module, profile_shift, rim_thickness
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia
            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "backlash": float(self.Object.Backlash),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty and not self.recomputing:
            try:
                self.recomputing = True  # Mark as recomputing
                parameters = self.GetParameters()

                # Get the actual body name that was created (from our stored value)
                actual_body_name = (
                    self.created_body_name
                    if hasattr(self, "created_body_name")
                    else None
                )

                # Use the actual body name to delete the old one
                body_name = (
                    actual_body_name
                    if actual_body_name
                    else parameters.get("body_name", "InternalSpurGear")
                )

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists and has same name
                old_body = doc.getObject(body_name)
                if old_body and old_body.isValid():
                    # Delete all child objects first (features inside the body)
                    if hasattr(old_body, 'Group'):
                        for obj in old_body.Group:
                            if obj and obj.isValid():
                                try:
                                    doc.removeObject(obj.Name)
                                except Exception as e:
                                    App.Console.PrintWarning(f"Could not remove {obj.Name}: {e}\n")

                    # Now delete the body itself
                    try:
                        doc.removeObject(body_name)
                        App.Console.PrintMessage(f"Deleted old body: {body_name}\n")
                    except Exception as e:
                        App.Console.PrintError(f"Failed to delete old body: {e}\n")

                    # Wait for deletion to complete
                    doc.recompute()

                # Create new body with parameters
                internalSpurGear(doc, parameters)

                # Store the newly created body name
                new_body = doc.getObject(
                    parameters.get("body_name", "InternalSpurGear")
                )
                if new_body and new_body.isValid():
                    self.created_body_name = parameters.get(
                        "body_name", "InternalSpurGear"
                    )
                    App.Console.PrintMessage(
                        f"Created new body: {self.created_body_name}\n"
                    )

                    # (recompute is already called at end of internalSpurGear function)

                    self.Dirty = False
                    self.recomputing = False
            except Exception as e:
                self.recomputing = False  # Clear recomputing flag on error
                App.Console.PrintError(f"Internal Spur Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


class InternalHelixGear:
    """FeaturePython object for parametric internal helical gear."""

    def __init__(self, obj):
        self.Dirty = False
        self.recomputing = False  # Guard against concurrent recompute calls
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty(
            "App::PropertyString", "Version", "read only", "", 1
        ).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty(
            "App::PropertyLength", "Module", "InternalHelicalGear", "Normal module"
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "InternalHelicalGear",
            "Number of teeth",
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "InternalHelicalGear",
            "Normal pressure angle",
        ).PressureAngle = H["pressure_angle"]
        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "InternalHelicalGear",
            "Profile shift coefficient",
        ).ProfileShift = H["profile_shift"]
        obj.addProperty(
            "App::PropertyLength", "Height", "InternalHelicalGear", "Gear height"
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyLength",
            "RimThickness",
            "InternalHelicalGear",
            "Rim thickness",
        ).RimThickness = H["rim_thickness"]
        obj.addProperty(
            "App::PropertyAngle",
            "HelixAngle",
            "InternalHelicalGear",
            "Helix angle (must match external gear for meshing)"
        ).HelixAngle = 15.0
        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "InternalHelicalGear",
            "Backlash clearance (extra profile shift for tooth gaps, 0.1-0.2 for 3D printing)"
        ).Backlash = 0.15
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalHelicalGear", "Body name"
        ).BodyName = "InternalHelixGear"

        self.Type = "InternalHelixGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
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
                        doc.removeObject(old_name)  # removeObject expects a string
            self.last_body_name = new_name

        if prop in [
            "Module",
            "NumberOfTeeth",
            "PressureAngle",
            "ProfileShift",
            "RimThickness",
            "HelixAngle",
            "Backlash",
        ]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value
                helix_angle = fp.HelixAngle.Value

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                outer_dia = gearMath.calcInternalDedendumDiameter(
                    pitch_dia, mt, profile_shift, rim_thickness
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia
            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "helix_angle": float(self.Object.HelixAngle.Value),
            "backlash": float(self.Object.Backlash),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty and not self.recomputing:
            try:
                self.recomputing = True  # Mark as recomputing
                parameters = self.GetParameters()

                # Get body name from the actual object, not parameters dict
                body_name_from_prop = (
                    str(self.Object.BodyName)
                    if hasattr(self.Object, "BodyName")
                    else None
                )

                # Use the property value if available
                body_name = (
                    body_name_from_prop
                    if body_name_from_prop
                    else parameters.get("body_name", "InternalHelixGear")
                )

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists and has same name
                old_body = doc.getObject(body_name)
                old_placement = None

                if old_body and old_body.isValid():
                    # Store current placement to reapply
                    old_placement = old_body.Placement

                    # Delete all child objects first (features inside the body)
                    if hasattr(old_body, 'Group'):
                        for obj in old_body.Group:
                            if obj and obj.isValid():
                                try:
                                    doc.removeObject(obj.Name)
                                except Exception as e:
                                    App.Console.PrintWarning(f"Could not remove {obj.Name}: {e}\n")

                    # Now delete the body itself
                    try:
                        doc.removeObject(body_name)
                        App.Console.PrintMessage(f"Deleted old body: {body_name}\n")
                    except Exception as e:
                        App.Console.PrintError(f"Failed to delete old body: {e}\n")

                    # Wait for deletion to complete
                    doc.recompute()

                    # Create new body with parameters
                    internalHelixGear(doc, parameters, parameters["helix_angle"])

                    # Restore placement if possible
                    new_body = doc.getObject(body_name)
                    if new_body and hasattr(old_placement, "Base"):
                        new_body.Placement = old_placement
                        App.Console.PrintMessage(
                            f"Restored placement for {body_name}\n"
                        )

                    # (recompute is already called at end of internalHelixGear function)

                    self.Dirty = False
                    self.recomputing = False
                else:
                    # No old body, just create new one
                    internalHelixGear(doc, parameters, parameters["helix_angle"])
                    self.Dirty = False
                    self.recomputing = False  # Clear recomputing flag
                    App.ActiveDocument.recompute()
            except Exception as e:
                self.recomputing = False  # Clear recomputing flag on error
                App.Console.PrintError(f"Internal Helical Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


class InternalHerringboneGear:
    """FeaturePython object for parametric internal herringbone gear."""

    def __init__(self, obj):
        self.Dirty = False
        self.recomputing = False  # Guard against concurrent recompute calls
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty(
            "App::PropertyString", "Version", "read only", "", 1
        ).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty(
            "App::PropertyLength", "Module", "InternalHerringboneGear", "Normal module"
        ).Module = H["module"]
        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "InternalHerringboneGear",
            "Number of teeth",
        ).NumberOfTeeth = H["num_teeth"]
        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "InternalHerringboneGear",
            "Normal pressure angle",
        ).PressureAngle = H["pressure_angle"]
        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "InternalHerringboneGear",
            "Profile shift coefficient",
        ).ProfileShift = H["profile_shift"]
        obj.addProperty(
            "App::PropertyLength", "Height", "InternalHerringboneGear", "Gear height"
        ).Height = H["height"]
        obj.addProperty(
            "App::PropertyLength",
            "RimThickness",
            "InternalHerringboneGear",
            "Rim thickness",
        ).RimThickness = H["rim_thickness"]
        obj.addProperty(
            "App::PropertyAngle",
            "Angle1",
            "InternalHerringboneGear",
            "First helix angle (bottom to middle)"
        ).Angle1 = 15.0
        obj.addProperty(
            "App::PropertyAngle",
            "Angle2",
            "InternalHerringboneGear",
            "Second helix angle (middle to top)"
        ).Angle2 = -15.0
        obj.addProperty(
            "App::PropertyFloat",
            "Backlash",
            "InternalHerringboneGear",
            "Backlash clearance (extra profile shift for tooth gaps, 0.1-0.2 for 3D printing)"
        ).Backlash = 0.15
        obj.addProperty(
            "App::PropertyString", "BodyName", "InternalHerringboneGear", "Body name"
        ).BodyName = "InternalHerringboneGear"

        self.Type = "InternalHerringboneGear"
        self.Object = obj
        self.last_body_name = None  # Initialize to None to prevent deleting other gears' bodies
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
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
                        doc.removeObject(old_name)  # removeObject expects a string
            self.last_body_name = new_name

        if prop in [
            "Module",
            "NumberOfTeeth",
            "PressureAngle",
            "ProfileShift",
            "RimThickness",
            "Angle1",
            "Angle2",
            "Backlash",
        ]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value
                angle1 = fp.Angle1.Value
                angle2 = fp.Angle2.Value

                # Use magnitude of angle1 for helix angle (like external herringbone)
                helix_angle = abs(angle1) if angle1 != 0 else abs(angle2)

                if helix_angle != 0:
                    mt = module / math.cos(helix_angle * util.DEG_TO_RAD)
                else:
                    mt = module

                pitch_dia = gearMath.calcPitchDiameter(mt, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                inner_dia = gearMath.calcInternalAddendumDiameter(
                    pitch_dia, mt, profile_shift
                )
                outer_dia = gearMath.calcInternalDedendumDiameter(
                    pitch_dia, mt, profile_shift, rim_thickness
                )

                fp.PitchDiameter = pitch_dia
                fp.BaseDiameter = base_dia
                fp.InnerDiameter = inner_dia
                fp.OuterDiameter = outer_dia
            except (AttributeError, TypeError):
                pass

    def GetParameters(self):
        angle1 = float(self.Object.Angle1.Value)
        angle2 = float(self.Object.Angle2.Value)
        # Calculate helix_angle for profile generation (magnitude of angle1)
        helix_angle = abs(angle1) if angle1 != 0 else abs(angle2)

        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "helix_angle": helix_angle,
            "angle1": angle1,
            "angle2": angle2,
            "backlash": float(self.Object.Backlash),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty and not self.recomputing:
            try:
                self.recomputing = True  # Mark as recomputing
                parameters = self.GetParameters()

                # Get body name from the actual object, not parameters dict
                body_name_from_prop = (
                    str(self.Object.BodyName)
                    if hasattr(self.Object, "BodyName")
                    else None
                )

                # Use the property value if available
                body_name = (
                    body_name_from_prop
                    if body_name_from_prop
                    else parameters.get("body_name", "InternalHerringboneGear")
                )

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists
                old_body = doc.getObject(body_name)
                old_placement = None

                if old_body and old_body.isValid():
                    # Store current placement to reapply
                    old_placement = old_body.Placement

                    # Delete all child objects first (features inside the body)
                    if hasattr(old_body, 'Group'):
                        for obj in old_body.Group:
                            if obj and obj.isValid():
                                try:
                                    doc.removeObject(obj.Name)
                                except Exception as e:
                                    App.Console.PrintWarning(f"Could not remove {obj.Name}: {e}\n")

                    # Now delete the body itself
                    try:
                        doc.removeObject(body_name)
                        App.Console.PrintMessage(f"Deleted old body: {body_name}\n")
                    except Exception as e:
                        App.Console.PrintError(f"Failed to delete old body: {e}\n")

                    # Wait for deletion to complete
                    doc.recompute()

                # Create new body with parameters using user-specified angles
                angle1 = parameters.get("angle1", 15.0)
                angle2 = parameters.get("angle2", -15.0)
                internalHerringboneGear(doc, parameters, angle1, angle2)

                # Restore placement if we had an old one
                if old_placement:
                    new_body = doc.getObject(body_name)
                    if new_body and hasattr(old_placement, "Base"):
                        new_body.Placement = old_placement
                        App.Console.PrintMessage(f"Restored placement for {body_name}\n")

                # Mark recomputing as complete
                self.Dirty = False
                self.recomputing = False
            except Exception as e:
                self.recomputing = False  # Clear recomputing flag on error
                App.Console.PrintError(f"Internal Herringbone Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


# ============================================================================
# COMMANDS
# ============================================================================


class InternalSpurGearCommand:
    """Command to create internal spur gear."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "internalSpurGear.svg"),
            "MenuText": "Internal Spur Gear",
            "ToolTip": "Create parametric internal spur gear",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "InternalSpurGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalSpurGearParameters")
        gear = InternalSpurGear(gear_obj)
        gear_obj.BodyName = unique_name

        # Trigger initial gear creation
        gear.recompute()

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


class InternalHelixGearCommand:
    """Command to create internal helical gear."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "internalSpurGear.svg"),
            "MenuText": "Internal Helical Gear",
            "ToolTip": "Create parametric internal helical gear (normal module)",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "InternalHelixGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalHelixGearParameters")
        gear = InternalHelixGear(gear_obj)
        gear_obj.BodyName = unique_name

        # Trigger initial gear creation
        gear.recompute()

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


class InternalHerringboneGearCommand:
    """Command to create internal herringbone gear."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "InternalDoubleHelicalGear.svg"),
            "MenuText": "Internal Herringbone Gear",
            "ToolTip": "Create parametric internal herringbone gear (normal module)",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        base_name = "InternalHerringboneGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject(
            "Part::FeaturePython", "InternalHerringboneGearParameters"
        )
        gear = InternalHerringboneGear(gear_obj)
        gear_obj.BodyName = unique_name

        # Trigger initial gear creation
        gear.recompute()

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


# Register commands
try:
    FreeCADGui.addCommand("InternalSpurGearCommand", InternalSpurGearCommand())
    FreeCADGui.addCommand("InternalHelixGearCommand", InternalHelixGearCommand())
    FreeCADGui.addCommand(
        "InternalHerringboneGearCommand", InternalHerringboneGearCommand()
    )
except Exception as e:
    App.Console.PrintError(f"Failed to register internal gear commands: {e}\n")
