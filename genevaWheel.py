"""Geneva Wheel (Maltese Cross) mechanism generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating a parametric Geneva wheel mechanism. The Geneva wheel converts
continuous rotation into intermittent motion.

Based on the Geneva_Wheel_GUI.FCMacro by Isaac Ayala (drei) & Mark Stephen (quick61).

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""

import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import os
import math
from PySide import QtCore

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "genevaWheel.svg")

version = "0.1"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VALIDATION & MATH
# ============================================================================


def validateGenevaParameters(params):
    """Validate Geneva wheel parameters.

    Args:
        params: Dictionary with keys: num_slots, crank_radius, pin_radius, tolerance, height

    Raises:
        gearMath.GearParameterError: If parameters are invalid
    """
    n = params["num_slots"]
    a = params["crank_radius"]
    p = params["pin_radius"]
    t = params["tolerance"]
    h = params["height"]

    if n < 3:
        raise gearMath.GearParameterError("Number of slots must be >= 3")
    if a <= 0:
        raise gearMath.GearParameterError("Crank radius must be positive")
    if p <= 0:
        raise gearMath.GearParameterError("Pin radius must be positive")
    if t < 0:
        raise gearMath.GearParameterError("Tolerance must be >= 0")
    if h <= 0:
        raise gearMath.GearParameterError("Height must be positive")
    if a <= 3 * p + t:
        raise gearMath.GearParameterError(
            f"Crank radius ({a}) must be > 3*pin_radius + tolerance ({3*p + t})"
        )


def calculateGenevaGeometry(params):
    """Calculate derived Geneva wheel geometry from input parameters.

    Args:
        params: Dictionary with keys: num_slots, crank_radius, pin_radius, tolerance

    Returns:
        Dictionary with derived values: c, b, s, w, y, z, v, m
    """
    n = params["num_slots"]
    a = params["crank_radius"]
    p = params["pin_radius"]
    t = params["tolerance"]

    c = a / math.sin(math.pi / n)  # Center distance
    b = math.sqrt(c**2 - a**2)  # Wheel radius
    s = a + b - c  # Slot center width
    w = p + t  # Slot width
    y = a - 3 * p  # Stop arc radius
    z = y - t  # Stop disc radius
    v = (b * z) / a  # Clearance arc radius
    m = math.sqrt(v**2 + z**2)  # Clearance cut axis offset

    return {"c": c, "b": b, "s": s, "w": w, "y": y, "z": z, "v": v, "m": m}


# ============================================================================
# SHAPE GENERATION (Part Booleans)
# ============================================================================


def generateDriveCrankShape(params, geo):
    """Generate the drive crank shape using Part Boolean operations.

    The drive crank consists of:
    - A locking disc (cylinder of radius z)
    - A clearance cut (so the Geneva wheel can rotate freely)
    - A base disc (below, radius a+2p)
    - A drive pin (at radius a from center)

    Args:
        params: Input parameters dict
        geo: Derived geometry dict from calculateGenevaGeometry()

    Returns:
        Part.Shape: The drive crank solid
    """
    a = params["crank_radius"]
    p = params["pin_radius"]
    h = params["height"]
    z = geo["z"]
    v = geo["v"]
    m = geo["m"]

    # Locking disc
    driveCrank = Part.makeCylinder(z, h)

    # Clearance cut for Geneva wheel
    clearanceCut = Part.makeCylinder(v, h)
    clearanceCut.translate(App.Vector(-m, 0, 0))
    driveCrank = driveCrank.cut(clearanceCut)

    # Base disc (below locking disc)
    base = Part.makeCylinder(a + 2 * p, h)
    base.translate(App.Vector(0, 0, -h))
    driveCrank = driveCrank.fuse(base)

    # Drive pin
    pin = Part.makeCylinder(p, h)
    pin.translate(App.Vector(-a, 0, 0))
    driveCrank = driveCrank.fuse(pin)

    return driveCrank


def generateGenevaWheelShape(params, geo):
    """Generate the Geneva wheel shape using Part Boolean operations.

    The Geneva wheel consists of:
    - A base disc (cylinder of radius b, centered at -c on X)
    - Stop arc cuts (so the locking disc can engage)
    - Radial slot cuts (for the drive pin)

    Args:
        params: Input parameters dict
        geo: Derived geometry dict from calculateGenevaGeometry()

    Returns:
        Part.Shape: The Geneva wheel solid
    """
    n = params["num_slots"]
    a = params["crank_radius"]
    h = params["height"]
    c = geo["c"]
    b = geo["b"]
    s = geo["s"]
    w = geo["w"]
    y = geo["y"]

    # Base wheel disc centered at (-c, 0, 0)
    wheel = Part.makeCylinder(b, h)
    wheel.translate(App.Vector(-c, 0, 0))

    # Stop arc cuts
    stopArc = Part.makeCylinder(y, h)
    stopArc.rotate(App.Vector(-c, 0, 0), App.Vector(0, 0, 1), 180.0 / n)

    for i in range(int(n)):
        stopArc.rotate(App.Vector(-c, 0, 0), App.Vector(0, 0, 1), 360.0 / n)
        wheel = wheel.cut(stopArc)

    # Slot cuts (box + cylinder for rounded end)
    slotBox = Part.makeBox(s, 2 * w, h)
    slotBox.translate(App.Vector(-a, -w, 0))

    slotCap = Part.makeCylinder(w, h)
    slotCap.translate(App.Vector(-a, 0, 0))

    slot = slotBox.fuse(slotCap)

    for i in range(int(n)):
        slot.rotate(App.Vector(-c, 0, 0), App.Vector(0, 0, 1), 360.0 / n)
        wheel = wheel.cut(slot)

    return wheel


# ============================================================================
# PART GENERATION (BaseFeature pattern)
# ============================================================================


def _removeBody(doc, body_name):
    """Remove a body and its associated _ShapeResult object."""
    result_name = f"{body_name}_ShapeResult"
    for name in [body_name, result_name]:
        obj = doc.getObject(name)
        if obj:
            if hasattr(obj, "removeObjectsFromDocument"):
                obj.removeObjectsFromDocument()
            doc.removeObject(name)


def _createBodyWithShape(doc, body_name, shape, bore_params=None, bore_placement=None):
    """Create a PartDesign::Body with a Part::Feature as BaseFeature.

    Args:
        doc: FreeCAD document
        body_name: Name for the body
        shape: Part.Shape to use as base
        bore_params: Optional bore parameters dict
        bore_placement: Optional App.Placement for bore
    """
    body = util.readyPart(doc, body_name)

    # Clear BaseFeature if set from previous generation
    if hasattr(body, "BaseFeature") and body.BaseFeature:
        body.BaseFeature = None

    # Store shape in a Part::Feature (outside the body)
    result_name = f"{body_name}_ShapeResult"
    result_obj = doc.getObject(result_name)
    if not result_obj:
        result_obj = doc.addObject("Part::Feature", result_name)
    result_obj.Shape = shape
    result_obj.Visibility = False

    # Set as BaseFeature
    body.BaseFeature = result_obj
    body.ViewObject.Visibility = True

    # Optional bore
    if bore_params and bore_params.get("bore_type", "none") != "none":
        try:
            util.createBore(body, bore_params, bore_params["bore_height"],
                            placement=bore_placement, reversed=False)
        except Exception as e:
            App.Console.PrintWarning(f"Could not add bore to {body_name}: {e}\n")


def generateGenevaWheelPart(doc, params):
    """Orchestrate creation of both Geneva wheel bodies.

    Creates two PartDesign::Body objects:
    - Drive crank at origin
    - Geneva wheel offset to (-c, 0, 0)

    Args:
        doc: FreeCAD document
        params: Full parameters dictionary
    """
    validateGenevaParameters(params)
    geo = calculateGenevaGeometry(params)

    crank_body_name = params.get("crank_body_name", "GenevaCrank")
    wheel_body_name = params.get("wheel_body_name", "GenevaWheel")
    h = params["height"]

    # Generate shapes
    crank_shape = generateDriveCrankShape(params, geo)
    wheel_shape = generateGenevaWheelShape(params, geo)

    # Crank body (at origin)
    crank_bore = {
        "bore_type": params.get("crank_bore_type", "none"),
        "bore_diameter": params.get("crank_bore_diameter", 5.0),
        "bore_height": 2 * h,  # Spans both halves
    }
    crank_bore_placement = App.Placement(
        App.Vector(0, 0, -h), App.Rotation()
    )
    _createBodyWithShape(doc, crank_body_name, crank_shape,
                         crank_bore, crank_bore_placement)

    # Wheel body (offset to -c on X)
    c = geo["c"]
    wheel_bore = {
        "bore_type": params.get("wheel_bore_type", "none"),
        "bore_diameter": params.get("wheel_bore_diameter", 5.0),
        "bore_height": h,
    }
    wheel_bore_placement = App.Placement(
        App.Vector(-c, 0, 0), App.Rotation()
    )
    _createBodyWithShape(doc, wheel_body_name, wheel_shape,
                         wheel_bore, wheel_bore_placement)

    doc.recompute()


# ============================================================================
# FEATUREPYTHON CLASSES
# ============================================================================


class GenevaWheelCreateObject:
    """Command to create a new Geneva wheel mechanism."""

    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Geneva Wheel",
            "ToolTip": "Create parametric Geneva wheel (Maltese cross) mechanism.\n"
            "Converts continuous rotation to intermittent motion.\n"
            "Creates drive crank and Geneva wheel as separate bodies.",
        }

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Unique body names for crank
        crank_base = "GenevaCrank"
        crank_name = crank_base
        count = 1
        while doc.getObject(crank_name):
            crank_name = f"{crank_base}{count:03d}"
            count += 1

        # Unique body names for wheel
        wheel_base = "GenevaWheel"
        wheel_name = wheel_base
        count = 1
        while doc.getObject(wheel_name):
            wheel_name = f"{wheel_base}{count:03d}"
            count += 1

        gear_obj = doc.addObject("Part::FeaturePython", "GenevaWheelParameters")
        geneva = GenevaWheel(gear_obj)
        ViewProviderGenevaWheel(gear_obj.ViewObject)

        gear_obj.CrankBodyName = crank_name
        gear_obj.WheelBodyName = wheel_name

        doc.recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        return geneva

    def IsActive(self):
        return True


class GenevaWheel:
    """FeaturePython object for parametric Geneva wheel mechanism."""

    def __init__(self, obj):
        self.Dirty = False
        H = gearMath.generateDefaultGenevaParameters()

        # Read-only properties
        obj.addProperty(
            "App::PropertyString", "Version", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Version"), 1,
        ).Version = version
        obj.addProperty(
            "App::PropertyLength", "WheelRadius", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Geneva wheel radius (b)"), 1,
        )
        obj.addProperty(
            "App::PropertyLength", "CenterDistance", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Distance between crank and wheel centers (c)"), 1,
        )
        obj.addProperty(
            "App::PropertyLength", "SlotCenterWidth", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Width of slot at center (s)"), 1,
        )

        # Editable parameters
        obj.addProperty(
            "App::PropertyInteger", "NumberOfSlots", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Number of slots (driven positions per revolution)"),
        ).NumberOfSlots = H["num_slots"]
        obj.addProperty(
            "App::PropertyLength", "CrankRadius", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Radius of the drive crank arm"),
        ).CrankRadius = H["crank_radius"]
        obj.addProperty(
            "App::PropertyLength", "PinRadius", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Radius of the drive pin"),
        ).PinRadius = H["pin_radius"]
        obj.addProperty(
            "App::PropertyLength", "Tolerance", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Clearance tolerance"),
        ).Tolerance = H["tolerance"]
        obj.addProperty(
            "App::PropertyLength", "Height", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Thickness of the mechanism"),
        ).Height = H["height"]

        # Body names
        obj.addProperty(
            "App::PropertyString", "CrankBodyName", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Name of the drive crank body"),
        ).CrankBodyName = H["crank_body_name"]
        obj.addProperty(
            "App::PropertyString", "WheelBodyName", "GenevaWheel",
            QT_TRANSLATE_NOOP("App::Property", "Name of the Geneva wheel body"),
        ).WheelBodyName = H["wheel_body_name"]

        # Crank bore
        obj.addProperty(
            "App::PropertyEnumeration", "CrankBoreType", "CrankBore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole for crank"),
        )
        obj.CrankBoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.CrankBoreType = H["bore_type"]
        obj.addProperty(
            "App::PropertyLength", "CrankBoreDiameter", "CrankBore",
            QT_TRANSLATE_NOOP("App::Property", "Bore diameter for crank"),
        ).CrankBoreDiameter = H["bore_diameter"]

        # Wheel bore
        obj.addProperty(
            "App::PropertyEnumeration", "WheelBoreType", "WheelBore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole for wheel"),
        )
        obj.WheelBoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.WheelBoreType = H["bore_type"]
        obj.addProperty(
            "App::PropertyLength", "WheelBoreDiameter", "WheelBore",
            QT_TRANSLATE_NOOP("App::Property", "Bore diameter for wheel"),
        ).WheelBoreDiameter = H["bore_diameter"]

        self.Type = "GenevaWheel"
        self.Object = obj
        self.doc = App.ActiveDocument
        self.last_crank_name = obj.CrankBodyName
        self.last_wheel_name = obj.WheelBodyName
        obj.Proxy = self

        self.onChanged(obj, "NumberOfSlots")

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

    def onChanged(self, fp, prop):
        self.Dirty = True

        if prop == "CrankBodyName":
            old_name = self.last_crank_name
            new_name = fp.CrankBodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    _removeBody(doc, old_name)
                self.last_crank_name = new_name

        if prop == "WheelBodyName":
            old_name = self.last_wheel_name
            new_name = fp.WheelBodyName
            if old_name != new_name:
                doc = App.ActiveDocument
                if doc:
                    _removeBody(doc, old_name)
                self.last_wheel_name = new_name

        # Update read-only calculated properties
        if prop in ["NumberOfSlots", "CrankRadius", "PinRadius", "Tolerance"]:
            try:
                n = fp.NumberOfSlots
                a = fp.CrankRadius.Value
                p = fp.PinRadius.Value
                t = fp.Tolerance.Value
                if n >= 3 and a > 0:
                    c = a / math.sin(math.pi / n)
                    b = math.sqrt(c**2 - a**2)
                    s = a + b - c
                    fp.WheelRadius = b
                    fp.CenterDistance = c
                    fp.SlotCenterWidth = s
            except (AttributeError, TypeError, ZeroDivisionError, ValueError):
                pass

    def GetParameters(self):
        return {
            "num_slots": int(self.Object.NumberOfSlots),
            "crank_radius": float(self.Object.CrankRadius.Value),
            "pin_radius": float(self.Object.PinRadius.Value),
            "tolerance": float(self.Object.Tolerance.Value),
            "height": float(self.Object.Height.Value),
            "crank_body_name": str(self.Object.CrankBodyName),
            "wheel_body_name": str(self.Object.WheelBodyName),
            "crank_bore_type": str(self.Object.CrankBoreType),
            "crank_bore_diameter": float(self.Object.CrankBoreDiameter.Value),
            "wheel_bore_type": str(self.Object.WheelBoreType),
            "wheel_bore_diameter": float(self.Object.WheelBoreDiameter.Value),
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                generateGenevaWheelPart(App.ActiveDocument, self.GetParameters())
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Geneva Wheel Error: {e}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())

    def execute(self, obj):
        QtCore.QTimer.singleShot(50, self.recompute)


class ViewProviderGenevaWheel:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.iconfile = iconfile if iconfile else mainIcon

    def attach(self, obj):
        self.ViewObject = obj
        self.Object = obj.Object

    def updateData(self, fp, prop):
        return

    def getDisplayModes(self, obj):
        return ["Shaded", "Wireframe", "Flat Lines"]

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def onChanged(self, vobj, prop):
        return

    def getIcon(self):
        return self.iconfile

    def doubleClicked(self, vobj):
        return True

    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui
        action = QtGui.QAction("Regenerate Geneva Wheel", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        if hasattr(self.Object, "Proxy"):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        return self.iconfile

    def __setstate__(self, state):
        self.iconfile = state if state else mainIcon


try:
    FreeCADGui.addCommand("GenevaWheelCreateObject", GenevaWheelCreateObject())
except Exception:
    pass
