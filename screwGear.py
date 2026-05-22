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
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
global mainIcon
mainIcon = os.path.join(smWB_icons_path, "ScrewGear.svg")

version = "Nov 30, 2025"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# GENERATION LOGIC
# ============================================================================


def validateScrewParameters(parameters):
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["num_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Teeth < {gearMath.MIN_TEETH}")
    if parameters["face_width"] <= 0:
        raise gearMath.GearParameterError("Face Width must be positive")
    if parameters["helix_angle"] <= 0:
        raise gearMath.GearParameterError("Helix angle must be positive")


def generateScrewGearPart(doc, parameters):
    """Generate screw gear using the generic screw system.

    Screw gears (crossed-axis helical gears) operate on non-parallel,
    non-intersecting shafts, typically at 90 degrees to each other.
    They use helical teeth that are swept along a cylindrical path.
    """
    validateScrewParameters(parameters)

    # Use the generic screw builder with involute tooth profile
    result = genericScrew.screwGear(
        doc, parameters, profile_func=gearMath.generateToothProfile
    )

    return result


def createScrewGearVarSet(doc, name):
    """Create a VarSet for ScrewGear parameters."""
    vs = doc.addObject("App::VarSet", name)
    vs.addProperty("App::PropertyString","Version","read only","",1).Version = version
    vs.addProperty("App::PropertyInteger","NumberOfTeeth","ScrewGear","Number of teeth").NumberOfTeeth = 20
    vs.addProperty("App::PropertyLength","Module","ScrewGear","Normal module").Module = 1.0
    vs.addProperty("App::PropertyAngle","PressureAngle","ScrewGear","Normal pressure angle").PressureAngle = 20.0
    vs.addProperty("App::PropertyFloat","ProfileShift","ScrewGear","Profile shift").ProfileShift = 0.0
    vs.addProperty("App::PropertyAngle","HelixAngle","ScrewGear","Helix angle").HelixAngle = 30.0
    vs.addProperty("App::PropertyLength","FaceWidth","ScrewGear","Face width").FaceWidth = 10.0
    vs.addProperty("App::PropertyEnumeration","Handedness","ScrewGear","Handedness")
    vs.Handedness = ["Right","Left"]; vs.Handedness = "Right"
    vs.addProperty("App::PropertyLength","BoreDiameter","Bore","Bore diameter").BoreDiameter = 5.0
    vs.addProperty("App::PropertyLength","KeywayWidth","Bore","Keyway width").KeywayWidth = 2.0
    vs.addProperty("App::PropertyLength","KeywayDepth","Bore","Keyway depth").KeywayDepth = 1.0
    vs.addProperty("App::PropertyBool","BoreEnabled","Bore","Enable bore").BoreEnabled = True
    vs.addProperty("App::PropertyBool","KeywayEnabled","Bore","Enable keyway").KeywayEnabled = False
    vs.addProperty("App::PropertyLength","PitchDiameter","read only","Transverse pitch diameter",1)
    vs.setExpression("PitchDiameter","Module / cos(HelixAngle) * NumberOfTeeth")
    vs.addProperty("App::PropertyLength","BaseDiameter","read only","",1)
    vs.setExpression("BaseDiameter","PitchDiameter * cos(PressureAngle)")
    vs.addProperty("App::PropertyLength","OuterDiameter","read only","",1)
    vs.setExpression("OuterDiameter","PitchDiameter + 2 * Module / cos(HelixAngle) * (1 + ProfileShift)")
    vs.addProperty("App::PropertyLength","RootDiameter","read only","",1)
    vs.setExpression("RootDiameter","PitchDiameter - 2 * Module / cos(HelixAngle) * (1.25 - ProfileShift)")
    return vs


class ScrewGearResult:
    """FeaturePython for auto-regeneration of screw gear."""

    def __init__(self, obj, varset):
        self._varset = varset; self._rebuilding = False
        self._last_m=self._last_nt=self._last_pa=self._last_ps=self._last_ha=self._last_fw=self._last_hd=None
        self._watcher=None; self._needs_rebuild=False; self.Type = "ScrewGearResult"
        obj.addProperty("App::PropertyString","VarSetName","Gear","",1).VarSetName = varset.Name
        obj.addProperty("App::PropertyString","BodyName","Gear","").BodyName = varset.Name.replace("_values","_Body",1)
        obj.addProperty("App::PropertyString","Version","read only","",1).Version = version
        obj.addProperty("App::PropertyString","Status","read only","",1)
        obj.Proxy = self; self.Object = obj; obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self): return self.Type
    def __setstate__(self,s):
        if s: self.Type = s
        self._varset=None; self._rebuilding=False
        self._last_m=self._last_nt=self._last_pa=self._last_ps=self._last_ha=self._last_fw=self._last_hd=None
        self._watcher=None; self._needs_rebuild=False

    def onDocumentRestored(self,obj):
        self.Object=obj; v=self._getVarSet()
        if v:
            self._last_m=float(v.Module.Value); self._last_nt=int(v.NumberOfTeeth); self._last_pa=float(v.PressureAngle.Value)
            self._last_ps=float(v.ProfileShift); self._last_ha=float(v.HelixAngle.Value); self._last_fw=float(v.FaceWidth.Value)
            self._last_hd=str(v.Handedness)
            self._startWatcher(v.Name); obj.Status="Up to date"

    def _startWatcher(self,vn):
        self._stopWatcher(); self._watcher=_VarSetWatcher(self,vn,watched=frozenset((
            "Module","NumberOfTeeth","PressureAngle","ProfileShift","HelixAngle",
            "FaceWidth","Handedness","BoreEnabled","KeywayEnabled","BoreDiameter",
            "KeywayWidth","KeywayDepth")))
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try: App.removeDocumentObserver(self._watcher)
            except: pass
            self._watcher=None

    def _getVarSet(self):
        if self._varset is None:
            try: self._varset=self.Object.Document.getObject(self.Object.VarSetName)
            except: pass
        return self._varset

    def execute(self,obj): pass

    def _values_changed(self):
        try:
            v=self._getVarSet()
            if not v or self._last_m is None: return v is not None
            E=1e-9
            return (abs(float(v.Module.Value)-self._last_m)>E or int(v.NumberOfTeeth)!=self._last_nt or
                    abs(float(v.PressureAngle.Value)-self._last_pa)>E or abs(float(v.ProfileShift)-self._last_ps)>E or
                    abs(float(v.HelixAngle.Value)-self._last_ha)>E or abs(float(v.FaceWidth.Value)-self._last_fw)>E or
                    str(v.Handedness)!=self._last_hd)
        except ReferenceError:
            self._varset=None
            return False

    def _set_needs_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._needs_rebuild=True
        try: self.Object.Status="Regenerating..."
        except: pass
        QtCore.QTimer.singleShot(0,self._deferred_rebuild)

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding: return
        if not self._values_changed(): self._needs_rebuild=False; return
        self._needs_rebuild=False; QtCore.QTimer.singleShot(0,self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding=True; vn=None
        try:
            v=self._getVarSet()
            if not v: return
            vn=v.Name; bn=str(self.Object.BodyName); d=self.Object.Document
            self._last_m=float(v.Module.Value); self._last_nt=int(v.NumberOfTeeth); self._last_pa=float(v.PressureAngle.Value)
            self._last_ps=float(v.ProfileShift); self._last_ha=float(v.HelixAngle.Value); self._last_fw=float(v.FaceWidth.Value)
            self._last_hd=str(v.Handedness)
            if self._last_m<=0 or self._last_nt<3 or self._last_fw<=0: self.Object.Status="Invalid params"; return
            self._stopWatcher()
            old=d.getObject(bn)
            saved_placement=None
            if old:
                saved_placement=App.Placement(old.Placement)
                ch=list(old.Group)
                for c in ch:
                    for p in c.PropertiesList:
                        try: c.setExpression(p,None)
                        except: pass
                for c in reversed(ch):
                    try: d.removeObject(c.Name)
                    except: pass
                d.removeObject(bn)
            self.Object.Status="Generating...";
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
            genericScrew.screwGear(d,{
                "module":self._last_m,"num_teeth":self._last_nt,"pressure_angle":self._last_pa,
                "profile_shift":self._last_ps,"helix_angle":self._last_ha,"face_width":self._last_fw,
                "handedness":self._last_hd,"bore_type":"none",
                "bore_diameter":float(v.BoreDiameter.Value),
                "keyway_width":float(v.KeywayWidth.Value),
                "keyway_depth":float(v.KeywayDepth.Value),"body_name":bn,
            },gearMath.generateHelicalGearProfile)
            bo=d.getObject(bn)
            if bo:
                sk=util.createSketch(bo,"Bore")
                ci=sk.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),float(v.BoreDiameter.Value)/2),False)
                sk.addConstraint(Sketcher.Constraint("Coincident",ci,3,-1,1))
                cst=sk.addConstraint(Sketcher.Constraint("Diameter",ci,float(v.BoreDiameter.Value)))
                sk.setExpression(f"Constraints[{cst}]",f"<<{v.Name}>>.BoreDiameter")
                pk=util.createPocket(bo,sk,100.0,"Bore"); pk.Reversed=True
                pk.setExpression("Suppressed",f"<<{v.Name}>>.BoreEnabled ? False : True")
                tiny=0.01; kw=util.createSketch(bo,"Keyway")
                pts=[App.Vector(-0.5,-0.5,0),App.Vector(0.5,-0.5,0),App.Vector(0.5,0.5,0),App.Vector(-0.5,0.5,0)]
                ls=[]
                for i in range(4): ls.append(kw.addGeometry(Part.LineSegment(pts[i],pts[(i+1)%4]),False))
                for i in range(4): kw.addConstraint(Sketcher.Constraint("Coincident",ls[i],2,ls[(i+1)%4],1))
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
                kp=util.createPocket(bo,kw,100.0,"Keyway"); kp.Reversed=True
                kp.setExpression("Suppressed",f"<<{v.Name}>>.KeywayEnabled ? False : True")
                bo.Tip=kp; d.recompute()
            if saved_placement:
                bo=d.getObject(bn)
                if bo: bo.Placement=saved_placement
            self.Object.Status="Up to date"
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
        except Exception as e:
            import traceback; App.Console.PrintError(traceback.format_exc())
            try:
                p=d.getObject(bn)
                if p:
                    for c in list(p.Group):
                        try: d.removeObject(c.Name)
                        except: pass
                    d.removeObject(bn)
            except: pass
            self.Object.Status="Error"
        finally:
            if vn: self._startWatcher(vn)
            self._rebuilding=False

    def force_Recompute(self): self._rebuild()


class ScrewGearCreateObject:
    """Command to create a new screw gear object."""

    def GetResources(self):
        return {
            "Pixmap": mainIcon,
            "MenuText": "&Create Screw Gear",
            "ToolTip": "Create parametric screw (crossed-helical) gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        base="ScrewGear_values"; un=base; c=1
        while doc.getObject(un): un=f"{base}{c:03d}"; c+=1
        vs=createScrewGearVarSet(doc,un)
        gn="Regenerate"; c=1
        while doc.getObject(gn): gn=f"Regenerate{c:03d}"; c+=1
        go=doc.addObject("Part::FeaturePython",gn)
        ScrewGearResult(go,vs)
        ViewProviderGearResult(go.ViewObject,mainIcon)
        go.Proxy.force_Recompute()
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


class ScrewGear:
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
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter (transverse)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "BaseDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Base circle diameter (transverse)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "OuterDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter (transverse)"),
            1,
        )

        obj.addProperty(
            "App::PropertyLength",
            "RootDiameter",
            "read only",
            QT_TRANSLATE_NOOP("App::Property", "Root diameter (transverse)"),
            1,
        )

        # Core gear parameters
        obj.addProperty(
            "App::PropertyLength",
            "Module",
            "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Normal module (tooth size)"),
        ).Module = H["module"]

        obj.addProperty(
            "App::PropertyInteger",
            "NumberOfTeeth",
            "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Number of teeth"),
        ).NumberOfTeeth = H["num_teeth"]

        obj.addProperty(
            "App::PropertyAngle",
            "PressureAngle",
            "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Normal pressure angle (normally 20°)"),
        ).PressureAngle = H["pressure_angle"]

        obj.addProperty(
            "App::PropertyFloat",
            "ProfileShift",
            "ScrewGear",
            QT_TRANSLATE_NOOP(
                "App::Property", "Normal profile shift coefficient (-1 to +1)"
            ),
        ).ProfileShift = H["profile_shift"]

        # Screw Gear specific properties
        obj.addProperty(
            "App::PropertyAngle",
            "HelixAngle",
            "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Helix angle of the teeth"),
        ).HelixAngle = 30.0  # Default helix angle

        obj.addProperty(
            "App::PropertyLength",
            "FaceWidth",
            "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Width of the gear face"),
        ).FaceWidth = 10.0

        obj.addProperty(
            "App::PropertyEnumeration",
            "Handedness",
            "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Handedness of helix"),
        )
        obj.Handedness = ["Right", "Left"]
        obj.Handedness = "Right"

        # --- NEW: Body Name Property ---
        obj.addProperty(
            "App::PropertyString",
            "BodyName",
            "ScrewGear",
            QT_TRANSLATE_NOOP("App::Property", "Name of the generated body"),
        ).BodyName = H["body_name"]
        obj.BodyName = "ScrewGear"

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

        self.Type = "ScrewGear"
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
            "HelixAngle",
            "FaceWidth",
        ]:
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
    FreeCADGui.addCommand("ScrewGearCreateObject", ScrewGearCreateObject())
    # App.Console.PrintMessage("ScrewGearCreateObject command registered successfully\n")
except Exception as e:
    App.Console.PrintError(f"Failed to register ScrewGearCreateObject: {e}\n")
    import traceback

    App.Console.PrintError(traceback.format_exc())
