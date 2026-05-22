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
import genericHypoid
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "HypoidGear.svg")

version = "Nov 30, 2025"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# GENERATION LOGIC
# ============================================================================


def validateHypoidParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["face_width"] <= 0:
        raise gearMath.GearParameterError("Face Width must be positive")
    # For now, allow 0 offset, but eventually hypoid means non-zero.
    # if parameters["offset"] == 0: raise gearMath.GearParameterError("Offset must not be zero for a hypoid gear")


def generateHypoidGearPart(doc, parameters):
    """Generate hypoid gear using the generic hypoid system.

    Hypoid gears are similar to bevel gears but with offset (non-intersecting) axes.
    They are commonly used in automotive differentials for their advantages in
    torque transmission and noise reduction.
    """
    validateHypoidParameters(parameters)

    # Add default pitch angle if not provided (45 degrees for 1:1 ratio)
    if "pitch_angle" not in parameters:
        parameters["pitch_angle"] = 45.0

    # Use the generic hypoid builder with involute tooth profile
    result = genericHypoid.hypoidGear(
        doc, parameters, profile_func=gearMath.generateToothProfile
    )

    return result


def createHypoidGearVarSet(doc, name):
    """Create a VarSet for HypoidGear parameters."""
    var_set = doc.addObject("App::VarSet", name)
    var_set.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
    var_set.addProperty("App::PropertyInteger", "NumberOfTeeth", "HypoidGear", "Number of teeth").NumberOfTeeth = 20
    var_set.addProperty("App::PropertyLength", "Module", "HypoidGear", "Module").Module = 1.0
    var_set.addProperty("App::PropertyAngle", "PressureAngle", "HypoidGear", "Pressure angle").PressureAngle = 20.0
    var_set.addProperty("App::PropertyFloat", "ProfileShift", "HypoidGear", "Profile shift").ProfileShift = 0.0
    var_set.addProperty("App::PropertyLength", "Offset", "HypoidGear", "Axis offset").Offset = 10.0
    var_set.addProperty("App::PropertyAngle", "SpiralAngle", "HypoidGear", "Spiral angle").SpiralAngle = 35.0
    var_set.addProperty("App::PropertyAngle", "PitchAngle", "HypoidGear", "Pitch cone angle").PitchAngle = 45.0
    var_set.addProperty("App::PropertyLength", "FaceWidth", "HypoidGear", "Face width").FaceWidth = 18.0
    var_set.addProperty("App::PropertyLength", "BoreDiameter", "Bore", "Bore diameter").BoreDiameter = 5.0
    var_set.addProperty("App::PropertyLength", "KeywayWidth", "Bore", "Keyway width").KeywayWidth = 2.0
    var_set.addProperty("App::PropertyLength", "KeywayDepth", "Bore", "Keyway depth").KeywayDepth = 1.0
    var_set.addProperty("App::PropertyBool", "BoreEnabled", "Bore", "Enable bore").BoreEnabled = True
    var_set.addProperty("App::PropertyBool", "KeywayEnabled", "Bore", "Enable keyway").KeywayEnabled = False
    var_set.addProperty("App::PropertyLength", "PitchDiameter", "read only", "", 1)
    var_set.setExpression("PitchDiameter", "Module * NumberOfTeeth")
    var_set.addProperty("App::PropertyLength", "BaseDiameter", "read only", "", 1)
    var_set.setExpression("BaseDiameter", "PitchDiameter * cos(PressureAngle)")
    var_set.addProperty("App::PropertyLength", "OuterDiameter", "read only", "", 1)
    var_set.setExpression("OuterDiameter", "PitchDiameter + 2 * Module * (1 + ProfileShift)")
    var_set.addProperty("App::PropertyLength", "RootDiameter", "read only", "", 1)
    var_set.setExpression("RootDiameter", "PitchDiameter - 2 * Module * (1.25 - ProfileShift)")
    return var_set


class HypoidGearResult:
    """FeaturePython for auto-regeneration of hypoid gear."""

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last_m = self._last_nt = self._last_pa = self._last_ps = None
        self._last_of = self._last_sa = self._last_pt = self._last_fw = None
        self._watcher = None
        self._needs_rebuild = False
        self.Type = "HypoidGearResult"
        obj.addProperty("App::PropertyString", "VarSetName", "Gear", "", 1).VarSetName = varset.Name
        obj.addProperty("App::PropertyString", "BodyName", "Gear", "Name of generated body").BodyName = varset.Name.replace("_values", "_Body", 1)
        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyString", "Status", "read only", "", 1)
        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self): return self.Type
    def __setstate__(self, state):
        if state: self.Type = state
        self._varset = None; self._rebuilding = False
        self._last_m = self._last_nt = self._last_pa = self._last_ps = None
        self._last_of = self._last_sa = self._last_pt = self._last_fw = None
        self._watcher = None; self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj; v = self._getVarSet()
        if v:
            for a in ["Module", "PressureAngle", "Offset", "SpiralAngle", "PitchAngle", "FaceWidth"]:
                setattr(self, f"_last_{a[0].lower() + ('m' if a[0]=='M' else a[1:])}", float(getattr(v, a).Value))
            self._last_nt = int(v.NumberOfTeeth)
            self._startWatcher(v.Name); obj.Status = "Up to date"

    def _abbrev(self, varname):
        return {"Module":"m","NumberOfTeeth":"nt","PressureAngle":"pa","ProfileShift":"ps",
                "Offset":"of","SpiralAngle":"sa","PitchAngle":"pt","FaceWidth":"fw",
                "BoreDiameter":"bd","KeywayWidth":"kw","KeywayDepth":"kd",
                "BoreEnabled":"be","KeywayEnabled":"ke"}.get(varname, varname[:2].lower())

    def _startWatcher(self, vn):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(self, vn, watched=frozenset((
            "Module","NumberOfTeeth","PressureAngle","ProfileShift","Offset",
            "SpiralAngle","PitchAngle","FaceWidth","BoreEnabled","KeywayEnabled",
            "BoreDiameter","KeywayWidth","KeywayDepth")))
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try: App.removeDocumentObserver(self._watcher)
            except: pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is None:
            try: self._varset = self.Object.Document.getObject(self.Object.VarSetName)
            except: pass
        return self._varset

    def execute(self, obj): pass

    def _values_changed(self):
        v = self._getVarSet()
        if not v or self._last_m is None: return v is not None
        EPS = 1e-9
        return (abs(float(v.Module.Value)-self._last_m)>EPS or int(v.NumberOfTeeth)!=self._last_nt or
                abs(float(v.PressureAngle.Value)-self._last_pa)>EPS or
                abs(float(v.ProfileShift)-self._last_ps)>EPS or
                abs(float(v.Offset.Value)-self._last_of)>EPS or
                abs(float(v.SpiralAngle.Value)-self._last_sa)>EPS or
                abs(float(v.PitchAngle.Value)-self._last_pt)>EPS or
                abs(float(v.FaceWidth.Value)-self._last_fw)>EPS)

    def _set_needs_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._needs_rebuild = True
        try: self.Object.Status = "Regenerating..."
        except: pass
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding: return
        if not self._values_changed(): self._needs_rebuild = False; return
        self._needs_rebuild = False
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding = True
        varset_name = None
        try:
            v = self._getVarSet()
            if not v: return
            varset_name = v.Name
            self._last_m = float(v.Module.Value)
            self._last_nt = int(v.NumberOfTeeth)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_ps = float(v.ProfileShift)
            self._last_of = float(v.Offset.Value)
            self._last_sa = float(v.SpiralAngle.Value)
            self._last_pt = float(v.PitchAngle.Value)
            self._last_fw = float(v.FaceWidth.Value)
            if self._last_m <= 0 or self._last_nt < 3 or self._last_fw <= 0:
                self.Object.Status = "Invalid params"; return
            body_name = str(self.Object.BodyName)
            doc = self.Object.Document
            self._stopWatcher()
            old = doc.getObject(body_name)
            saved_placement = None
            if old:
                saved_placement = App.Placement(old.Placement)
                children = list(old.Group)
                for c in children:
                    for p in c.PropertiesList:
                        try: c.setExpression(p, None)
                        except: pass
                for c in reversed(children):
                    try: doc.removeObject(c.Name)
                    except: pass
                doc.removeObject(body_name)
            self.Object.Status = "Generating gear geometry..."
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
            genericHypoid.hypoidGear(doc, {
                "module":self._last_m, "num_teeth":self._last_nt,
                "pressure_angle":self._last_pa, "profile_shift":self._last_ps,
                "offset":self._last_of, "spiral_angle":self._last_sa,
                "pitch_angle":self._last_pt, "face_width":self._last_fw,
                "bore_type":"none", "bore_diameter":float(v.BoreDiameter.Value),
                "keyway_width":float(v.KeywayWidth.Value),
                "keyway_depth":float(v.KeywayDepth.Value), "body_name":body_name,
            }, gearMath.generateToothProfile)
            body_out = doc.getObject(body_name)
            if body_out:
                if saved_placement:
                    body_out.Placement = saved_placement
                else:
                    # Default: flip so the small end faces the viewer
                    body_out.Placement = App.Placement(
                        App.Vector(0,0,0), App.Rotation(App.Vector(1,0,0), 180))
            body_out = doc.getObject(body_name)
            if body_out:
                sk = util.createSketch(body_out, "Bore")
                c = sk.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),float(v.BoreDiameter.Value)/2), False)
                sk.addConstraint(Sketcher.Constraint("Coincident",c,3,-1,1))
                ci = sk.addConstraint(Sketcher.Constraint("Diameter",c,float(v.BoreDiameter.Value)))
                sk.setExpression(f"Constraints[{ci}]",f"<<{v.Name}>>.BoreDiameter")
                pk = util.createPocket(body_out,sk,100.0,"Bore")
                pk.Reversed = True
                pk.setExpression("Suppressed",f"<<{v.Name}>>.BoreEnabled ? False : True")

                tiny=0.01
                kw=util.createSketch(body_out,"Keyway")
                pts=[App.Vector(-0.5,-0.5,0),App.Vector(0.5,-0.5,0),App.Vector(0.5,0.5,0),App.Vector(-0.5,0.5,0)]
                ls=[]
                for i in range(4):
                    ls.append(kw.addGeometry(Part.LineSegment(pts[i],pts[(i+1)%4]),False))
                for i in range(4):
                    kw.addConstraint(Sketcher.Constraint("Coincident",ls[i],2,ls[(i+1)%4],1))
                kw.addConstraint(Sketcher.Constraint("Horizontal",ls[0]))
                kw.addConstraint(Sketcher.Constraint("Vertical",ls[1]))
                kw.addConstraint(Sketcher.Constraint("Horizontal",ls[2]))
                kw.addConstraint(Sketcher.Constraint("Vertical",ls[3]))
                c=kw.addConstraint(Sketcher.Constraint("DistanceX",ls[0],1,-1,1,-tiny))
                kw.setExpression(f"Constraints[{c}]",f"<<{v.Name}>>.KeywayWidth / -2.0")
                c=kw.addConstraint(Sketcher.Constraint("DistanceY",ls[0],1,-1,1,-tiny))
                kw.setExpression(f"Constraints[{c}]",f"<<{v.Name}>>.BoreDiameter/2 - <<{v.Name}>>.KeywayDepth")
                c=kw.addConstraint(Sketcher.Constraint("DistanceX",ls[0],2,-1,1,tiny))
                kw.setExpression(f"Constraints[{c}]",f"<<{v.Name}>>.KeywayWidth / 2.0")
                c=kw.addConstraint(Sketcher.Constraint("DistanceY",ls[1],2,-1,1,tiny))
                kw.setExpression(f"Constraints[{c}]",f"<<{v.Name}>>.BoreDiameter/2 + <<{v.Name}>>.KeywayDepth")
                kp=util.createPocket(body_out,kw,100.0,"Keyway")
                kp.Reversed = True
                kp.setExpression("Suppressed",f"<<{v.Name}>>.KeywayEnabled ? False : True")
                body_out.Tip = kp
                doc.recompute()
            self.Object.Status = "Up to date"
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
        except Exception as e:
            import traceback; App.Console.PrintError(traceback.format_exc())
            try:
                p=doc.getObject(body_name)
                if p:
                    for c in list(p.Group):
                        try: doc.removeObject(c.Name)
                        except: pass
                    doc.removeObject(body_name)
            except: pass
            self.Object.Status = "Error"
        finally:
            if varset_name: self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self): self._rebuild()


class HypoidGearCreateObject:
    """Command to create a new hypoid gear object."""

    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Hypoid Gear",
            "ToolTip": "Create parametric hypoid gear (offset bevel gear)",
        }

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        base = "HypoidGear_values"; uname = base; c = 1
        while doc.getObject(uname): uname = f"{base}{c:03d}"; c += 1
        vs = createHypoidGearVarSet(doc, uname)
        gn = "Regenerate"; c = 1
        while doc.getObject(gn): gn = f"Regenerate{c:03d}"; c += 1
        go = doc.addObject("Part::FeaturePython", gn)
        HypoidGearResult(go, vs)
        ViewProviderGearResult(go.ViewObject, mainIcon)
        go.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")

    def IsActive(self): return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


class HypoidGear:
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
            "App::PropertyLength",
            "Module",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Gear module (tooth size)"),
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Pressure angle (normally 20°)"),
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Profile shift coefficient (-1 to +1)"),
        ).ProfileShift = H["profile_shift"]  # Profile shift might be applicable

        # Hypoid specific properties
        obj.addProperty(
            "App::PropertyLength",
            "Offset",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Offset between gear axes"),
        ).Offset = 10.0

        obj.addProperty(
            "App::PropertyAngle",
            "SpiralAngle",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Spiral angle of the teeth"),
        ).SpiralAngle = 35.0

        obj.addProperty(
            "App::PropertyAngle",
            "PitchAngle",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Pitch cone angle (45° for 1:1 ratio)"),
        ).PitchAngle = 45.0

        obj.addProperty(
            "App::PropertyLength",
            "FaceWidth",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of the gear face"),
        ).FaceWidth = 18.0

        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "HypoidGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = H["body_name"]
        obj.BodyName = "HypoidGear"  # Override default spur gear name

        # Bore parameters (hypoid gears typically don't have standard bores like this)
        obj.addProperty(
            "App::PropertyEnumeration",
            "BoreType",
            "Bore",
            QT_TRANSLATE_NOOP("App::Property", "Type of center hole"),
        )
        obj.BoreType = ["none", "circular", "square", "hexagonal", "keyway"]
        obj.BoreType = "none"  # Default to none for hypoid

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

        self.Type = "HypoidGear"
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
        if prop in [
            "Module",
            "NumberOfTeeth",
            "PressureAngle",
            "Offset",
            "SpiralAngle",
            "PitchAngle",
            "FaceWidth",
        ]:
            try:
                module = fp.Module.Value
                num_teeth = fp.NumberOfTeeth
                pressure_angle = fp.PressureAngle.Value
                # offset = fp.Offset.Value # Not directly used in these calculations
                # spiral_angle = fp.SpiralAngle.Value # Not directly used in these calculations

                # These calculations are for a spur gear, may need adjustment for hypoid
                pitch_dia = gearMath.calcPitchDiameter(module, num_teeth)
                base_dia = gearMath.calcBaseDiameter(pitch_dia, pressure_angle)
                outer_dia = gearMath.calcAddendumDiameter(
                    pitch_dia, module
                )  # Profile shift might be less relevant for hypoid
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
            "pitch_angle": float(self.Object.PitchAngle.Value),
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
        if hasattr(self.Object, "Proxy"):
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
    FreeCADGui.addCommand("HypoidGearCreateObject", HypoidGearCreateObject())
    # App.Console.PrintMessage("HypoidGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register HypoidGearCreateObject: {e}\n")
    import traceback

    App.Console.PrintError(traceback.format_exc())
