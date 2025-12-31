"""Generic Internal Gear Framework for FreeCAD

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
    """
    gearMath.generateToothProfile(sketch, parameters)


def generateInternalHelicalCutterProfile(sketch, parameters):
    """
    Generates the Helical CUTTER profile (Transverse conversion).
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

    # Generate the EXTERNAL tooth profile (which is the cutter for the gap)
    gearMath.generateToothProfile(sketch, transverse_params)


# ============================================================================
# MASTER INTERNAL GEAR BUILDER
# ============================================================================

def genericInternalHerringboneGear(
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

    body_name = parameters.get("body_name", "GenericInternalGear")
    body = util.readyPart(doc, body_name)

    num_teeth = parameters["num_teeth"]
    height = parameters["height"]
    profile_shift = parameters.get("profile_shift", 0.0)
    rim_thickness = parameters.get("rim_thickness", 3.0)

    if "helix_angle" not in parameters:
        parameters = parameters.copy()
        parameters["helix_angle"] = abs(angle1) if angle1 != 0 else abs(angle2)

    # Dimensions
    helix_angle = parameters.get("helix_angle", 0.0)
    module = parameters["module"]
    if helix_angle != 0:
        beta_rad = helix_angle * util.DEG_TO_RAD
        mt = module / math.cos(beta_rad)
    else:
        mt = module

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
    # We extend the cutter slightly deeper than the nominal root to ensure clean boolean cuts.
    # This prevents coincident faces at the bottom of the tooth gap.
    cut_params = parameters.copy()
    cut_params["tip_radius"] = rf_internal + (0.01 * module) 

    if angle1 == 0:
        return _createTwoSketchInternalGear(
            body, cut_params, height, num_teeth, angle2, ra_internal, outer_diameter, profile_func
        )
    else:
        return _createThreeSketchInternalGear(
            body, cut_params, height, num_teeth, angle1, angle2, ra_internal, outer_diameter, profile_func
        )


def _createTwoSketchInternalGear(
    body, parameters, height, num_teeth, angle2, ra_internal, outer_diameter, profile_func
):
    """Create internal gear with 2 sketches (Subtractive)."""
    doc = body.Document

    # 1. Base Ring
    ring_sketch = util.createSketch(body, "Ring")
    
    outer_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", outer_circle, outer_diameter))

    inner_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), ra_internal), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", inner_circle, ra_internal * 2.0))

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")
    
    # 2. Cutters (The Gap)
    sketch_bottom = util.createSketch(body, "ToothGap_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    sketch_bottom.MapMode = 'Deactivated'
    profile_func(sketch_bottom, parameters)

    sketch_top = util.createSketch(body, "ToothGap_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle2)
    )
    sketch_top.MapMode = 'Deactivated'
    profile_func(sketch_top, parameters)

    # 3. Subtractive Loft
    tooth_cut = body.newObject("PartDesign::SubtractiveLoft", "ToothGapCut")
    tooth_cut.Profile = sketch_bottom
    tooth_cut.Sections = [sketch_top]
    tooth_cut.Ruled = True
    tooth_cut.Refine = False

    # 4. Pattern
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]
    gear_teeth.Axis = (z_axis, [""])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [tooth_cut]

    # Cleanup
    ring_sketch.Visibility = False
    sketch_bottom.Visibility = False
    sketch_top.Visibility = False
    tooth_cut.Visibility = False
    ring_pad.Visibility = False
    gear_teeth.Visibility = True
    body.Tip = gear_teeth

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


def _createThreeSketchInternalGear(
    body, parameters, height, num_teeth, angle1, angle2, ra_internal, outer_diameter, profile_func
):
    """Create internal herringbone gear (Subtractive)."""
    doc = body.Document
    half_height = height / 2.0

    # 1. Base Ring
    ring_sketch = util.createSketch(body, "Ring")
    
    outer_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_diameter / 2.0), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", outer_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", outer_circle, outer_diameter))

    inner_circle = ring_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), ra_internal), False
    )
    ring_sketch.addConstraint(Sketcher.Constraint("Coincident", inner_circle, 3, -1, 1))
    ring_sketch.addConstraint(Sketcher.Constraint("Diameter", inner_circle, ra_internal * 2.0))

    ring_pad = util.createPad(body, ring_sketch, height, "Ring")

    # 2. Cutters
    sketch_bottom = util.createSketch(body, "ToothGap_Bottom")
    sketch_bottom.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))
    sketch_bottom.MapMode = 'Deactivated'
    profile_func(sketch_bottom, parameters)

    sketch_middle = util.createSketch(body, "ToothGap_Middle")
    sketch_middle.Placement = App.Placement(
        App.Vector(0, 0, half_height), App.Rotation(App.Vector(0, 0, 1), angle1)
    )
    sketch_middle.MapMode = 'Deactivated'
    profile_func(sketch_middle, parameters)

    sketch_top = util.createSketch(body, "ToothGap_Top")
    sketch_top.Placement = App.Placement(
        App.Vector(0, 0, height), App.Rotation(App.Vector(0, 0, 1), angle1 + angle2)
    )
    sketch_top.MapMode = 'Deactivated'
    profile_func(sketch_top, parameters)

    # 3. Cuts
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


    # 4. Pattern
    gear_teeth = body.newObject("PartDesign::PolarPattern", "Teeth")
    origin = body.Origin
    z_axis = origin.OriginFeatures[2]
    gear_teeth.Axis = (z_axis, [""])
    gear_teeth.Angle = 360
    gear_teeth.Occurrences = num_teeth
    gear_teeth.Originals = [cut_lower, cut_upper]

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
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return {"body": body}


# ============================================================================
# SPECIALIZED INTERNAL GEAR FUNCTIONS
# ============================================================================

def genericInternalHelixGear(
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

    return genericInternalHerringboneGear(
        doc, params_with_helix, 0.0, total_rotation_deg, profile_func
    )


def genericInternalSpurGear(doc, parameters, profile_func: Optional[Callable] = None):
    if profile_func is None:
        profile_func = generateInternalCutterProfile  # Use External profile as cutter

    return genericInternalHerringboneGear(doc, parameters, 0.0, 0.0, profile_func)


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================

class GenericInternalSpurGear:
    """FeaturePython object for parametric internal spur gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty("App::PropertyLength", "Module", "InternalSpurGear", "Normal module").Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "InternalSpurGear", "Number of teeth").NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyAngle", "PressureAngle", "InternalSpurGear", "Normal pressure angle").PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyFloat", "ProfileShift", "InternalSpurGear", "Profile shift coefficient").ProfileShift = H["profile_shift"]
        obj.addProperty("App::PropertyLength", "Height", "InternalSpurGear", "Gear height").Height = H["height"]
        obj.addProperty("App::PropertyLength", "RimThickness", "InternalSpurGear", "Rim thickness").RimThickness = H["rim_thickness"]
        obj.addProperty("App::PropertyString", "BodyName", "InternalSpurGear", "Body name").BodyName = "GenericInternalSpurGear"

        # Store the actual body name created by gear generator
        self.created_body_name = None
        self.last_body_name = obj.BodyName

        self.Type = "GenericInternalSpurGear"
        self.Object = obj
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
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

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness"]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                profile_shift = fp.ProfileShift
                rim_thickness = fp.RimThickness.Value

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
        return {
            "module": float(self.Object.Module.Value),
            "num_teeth": int(self.Object.NumberOfTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "profile_shift": float(self.Object.ProfileShift),
            "height": float(self.Object.Height.Value),
            "rim_thickness": float(self.Object.RimThickness.Value),
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()

                # Get the actual body name that was created (from our stored value)
                actual_body_name = self.created_body_name if hasattr(self, "created_body_name") else None

                # Use the actual body name to delete the old one
                body_name = actual_body_name if actual_body_name else parameters.get("body_name", "GenericInternalSpurGear")

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists and has same name
                old_body = doc.getObject(body_name)
                if old_body and old_body.isValid():
                    # Delete the old body (which may have a different name from previous BodyName)
                    doc.removeObject(body_name)
                    App.Console.PrintMessage(f"Deleted old body: {body_name}\n")

                # Create new body with parameters
                genericInternalSpurGear(doc, parameters)

                # Store the newly created body name
                new_body = doc.getObject(parameters.get("body_name", "GenericInternalSpurGear"))
                if new_body and new_body.isValid():
                    self.created_body_name = parameters.get("body_name", "GenericInternalSpurGear")
                    App.Console.PrintMessage(f"Created new body: {self.created_body_name}\n")

                    # Restore placement if possible (only if it's not the first gear creation)
                    # For now, just set the body name and let the gear generator handle placement
                    self.Dirty = False
                    App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Internal Spur Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


class GenericInternalHelixGear:
    """FeaturePython object for parametric internal helical gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty("App::PropertyLength", "Module", "InternalHelicalGear", "Normal module").Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "InternalHelicalGear", "Number of teeth").NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyAngle", "PressureAngle", "InternalHelicalGear", "Normal pressure angle").PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyFloat", "ProfileShift", "InternalHelicalGear", "Profile shift coefficient").ProfileShift = H["profile_shift"]
        obj.addProperty("App::PropertyLength", "Height", "InternalHelicalGear", "Gear height").Height = H["height"]
        obj.addProperty("App::PropertyLength", "RimThickness", "InternalHelicalGear", "Rim thickness").RimThickness = H["rim_thickness"]
        obj.addProperty("App::PropertyAngle", "HelixAngle", "InternalHelicalGear", "Helix angle").HelixAngle = -15.0
        obj.addProperty("App::PropertyString", "BodyName", "InternalHelicalGear", "Body name").BodyName = "GenericInternalHelixGear"

        self.Type = "GenericInternalHelixGear"
        self.Object = obj
        self.last_body_name = obj.BodyName
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
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

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness", "HelixAngle"]:
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
                inner_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, mt, profile_shift)
                outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, mt, profile_shift, rim_thickness)

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
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()

                # Get body name from the actual object, not parameters dict
                body_name_from_prop = str(self.Object.BodyName) if hasattr(self.Object, "BodyName") else None

                # Use the property value if available
                body_name = body_name_from_prop if body_name_from_prop else parameters.get("body_name", "GenericInternalHelixGear")

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists and has same name
                old_body = doc.getObject(body_name)
                if old_body and old_body.isValid():
                    # Store current placement to reapply
                    old_placement = old_body.Placement

                    # Delete the old body
                    doc.removeObject(body_name)
                    App.Console.PrintMessage(f"Deleted old body: {body_name}\n")

                    # Create new body with parameters
                    genericInternalHelixGear(doc, parameters, parameters["helix_angle"])

                    # Restore placement if possible
                    new_body = doc.getObject(body_name)
                    if new_body and hasattr(old_placement, "Base"):
                        new_body.Placement = old_placement
                        App.Console.PrintMessage(f"Restored placement for {body_name}\n")

                    self.Dirty = False
                    App.ActiveDocument.recompute()
                else:
                    # No old body, just create new one
                    genericInternalHelixGear(doc, parameters, parameters["helix_angle"])
                    self.Dirty = False
                    App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Internal Helical Gear Error: {e}\n")
                raise

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


class GenericInternalHerringboneGear:
    """FeaturePython object for parametric internal herringbone gear."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultInternalParameters()

        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "InnerDiameter", "read only", "", 1)
        obj.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)

        obj.addProperty("App::PropertyLength", "Module", "InternalHerringboneGear", "Normal module").Module = H["module"]
        obj.addProperty("App::PropertyInteger", "NumberOfTeeth", "InternalHerringboneGear", "Number of teeth").NumberOfTeeth = H["num_teeth"]
        obj.addProperty("App::PropertyAngle", "PressureAngle", "InternalHerringboneGear", "Normal pressure angle").PressureAngle = H["pressure_angle"]
        obj.addProperty("App::PropertyFloat", "ProfileShift", "InternalHerringboneGear", "Profile shift coefficient").ProfileShift = H["profile_shift"]
        obj.addProperty("App::PropertyLength", "Height", "InternalHerringboneGear", "Gear height").Height = H["height"]
        obj.addProperty("App::PropertyLength", "RimThickness", "InternalHerringboneGear", "Rim thickness").RimThickness = H["rim_thickness"]
        obj.addProperty("App::PropertyAngle", "HelixAngle", "InternalHerringboneGear", "Helix angle").HelixAngle = -30.0
        obj.addProperty("App::PropertyString", "BodyName", "InternalHerringboneGear", "Body name").BodyName = "GenericInternalHerringboneGear"

        self.Type = "GenericInternalHerringboneGear"
        self.Object = obj
        self.last_body_name = obj.BodyName
        obj.Proxy = self
        self.onChanged(obj, "Module")

    def onChanged(self, fp, prop):
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

        if prop in ["Module", "NumberOfTeeth", "PressureAngle", "ProfileShift", "RimThickness", "HelixAngle"]:
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
                inner_dia = gearMath.calcInternalAddendumDiameter(pitch_dia, mt, profile_shift)
                outer_dia = gearMath.calcInternalDedendumDiameter(pitch_dia, mt, profile_shift, rim_thickness)

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
            "body_name": str(self.Object.BodyName),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                parameters = self.GetParameters()

                # Get body name from the actual object, not parameters dict
                body_name_from_prop = str(self.Object.BodyName) if hasattr(self.Object, "BodyName") else None

                # Use the property value if available
                body_name = body_name_from_prop if body_name_from_prop else parameters.get("body_name", "GenericInternalSpurGear")

                doc = App.ActiveDocument
                if not doc:
                    App.Console.PrintError("No active document\n")
                    return

                # Delete old body if it exists and has same name
                old_body = doc.getObject(body_name)
                if old_body and old_body.isValid():
                    # Store current placement to reapply
                    old_placement = old_body.Placement

                    # Delete the old body
                    doc.removeObject(body_name)
                    App.Console.PrintMessage(f"Deleted old body: {body_name}\n")

                    # Create new body with parameters
                    genericInternalHerringboneGear(doc, parameters)

                    # Restore placement if possible
                    new_body = doc.getObject(body_name)
                    if new_body and hasattr(old_placement, "Base"):
                        new_body.Placement = old_placement
                        App.Console.PrintMessage(f"Restored placement for {body_name}\n")

                    self.Dirty = False
                    App.ActiveDocument.recompute()
                else:
                    # No old body, just create new one
                    genericInternalSpurGear(doc, parameters)
                    self.Dirty = False
                    App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Internal Spur Gear Error: {e}\n")
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

class GenericInternalSpurGearCommand:
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

        base_name = "GenericInternalSpurGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalSpurGearParameters")
        gear = GenericInternalSpurGear(gear_obj)
        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


class GenericInternalHelixGearCommand:
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

        base_name = "GenericInternalHelixGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalHelixGearParameters")
        gear = GenericInternalHelixGear(gear_obj)
        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


class GenericInternalHerringboneGearCommand:
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

        base_name = "GenericInternalHerringboneGear"
        unique_name = base_name
        count = 1
        while doc.getObject(unique_name):
            unique_name = f"{base_name}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "InternalHerringboneGearParameters")
        gear = GenericInternalHerringboneGear(gear_obj)
        gear_obj.BodyName = unique_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return gear

    def IsActive(self):
        return True


# Register commands
try:
    FreeCADGui.addCommand("GenericInternalSpurGearCommand", GenericInternalSpurGearCommand())
    FreeCADGui.addCommand("GenericInternalHelixGearCommand", GenericInternalHelixGearCommand())
    FreeCADGui.addCommand("GenericInternalHerringboneGearCommand", GenericInternalHerringboneGearCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register internal gear commands: {e}\n")