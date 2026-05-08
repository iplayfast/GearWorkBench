"""Globoid Worm Gear generator for FreeCAD

This module provides the FreeCAD command and FeaturePython object for
creating parametric Globoid (Double-Throated) Worm Gears.

Copyright 2025, Chris Bruner
Version v0.1
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
from math import pi
from PySide import QtCore
from genericGear import _VarSetWatcher, ViewProviderGearResult

vec2 = App.Base.Vector2d

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, 'icons')
global mainIcon
mainIcon = os.path.join(smWB_icons_path, 'globoidWormGear.svg') 

def QT_TRANSLATE_NOOP(scope, text): return text


def createGloboidWormGearVarSet(doc, name):
    """VarSet for GloboidWormGear parameters."""
    vs = doc.addObject("App::VarSet", name)

    vs.addProperty("App::PropertyString","Version","read only","",1).Version = "0.1"
    vs.addProperty("App::PropertyLength","Module","GloboidWorm","Module").Module = 2.0
    vs.addProperty("App::PropertyInteger","NumberOfThreads","GloboidWorm","Thread starts").NumberOfThreads = 1
    vs.addProperty("App::PropertyInteger","GearTeeth","GloboidWorm","Mating gear teeth").GearTeeth = 20
    vs.addProperty("App::PropertyLength","WormPitchDiameter","GloboidWorm","Pitch diameter at throat").WormPitchDiameter = 30.0
    vs.addProperty("App::PropertyLength","CylinderDiameter","GloboidWorm","Outer diameter of cylinder (0=auto)").CylinderDiameter = 0.0
    vs.addProperty("App::PropertyAngle","PressureAngle","GloboidWorm","Pressure angle").PressureAngle = 20.0
    vs.addProperty("App::PropertyAngle","ArcAngle","GloboidWorm","Engagement angle (60-90)").ArcAngle = 70.0
    vs.addProperty("App::PropertyLength","WormLength","GloboidWorm","Thread length (0=auto)").WormLength = 0.0
    vs.addProperty("App::PropertyLength","CylinderLength","GloboidWorm","Total cylinder length").CylinderLength = 50.0
    vs.addProperty("App::PropertyBool","RightHanded","GloboidWorm","Right-handed").RightHanded = True
    vs.addProperty("App::PropertyBool","BoreEnabled","Bore","Enable bore").BoreEnabled = True
    vs.addProperty("App::PropertyLength","BoreDiameter","Bore","Bore diameter").BoreDiameter = 5.0
    vs.addProperty("App::PropertyBool","KeywayEnabled","Bore","Enable keyway").KeywayEnabled = False
    vs.addProperty("App::PropertyLength","KeywayWidth","Bore","Keyway width").KeywayWidth = 2.0
    vs.addProperty("App::PropertyLength","KeywayDepth","Bore","Keyway depth").KeywayDepth = 1.0

    vs.addProperty("App::PropertyBool","CreateMatingGear","MatingGear","Create wheel").CreateMatingGear = True
    vs.addProperty("App::PropertyLength","GearHeight","MatingGear","Wheel thickness").GearHeight = 10.0
    vs.addProperty("App::PropertyFloat","Clearance","MatingGear","Clearance factor").Clearance = 0.1
    vs.addProperty("App::PropertyBool","GearBoreEnabled","MatingGear","Enable wheel bore").GearBoreEnabled = True
    vs.addProperty("App::PropertyLength","GearBoreDiameter","MatingGear","Wheel bore diameter").GearBoreDiameter = 8.0
    vs.addProperty("App::PropertyBool","GearKeywayEnabled","MatingGear","Enable wheel keyway").GearKeywayEnabled = False

    vs.addProperty("App::PropertyAngle","LeadAngle","read only","",1)
    vs.setExpression("LeadAngle","atan(Module*pi*NumberOfThreads/(WormPitchDiameter*pi))")
    vs.addProperty("App::PropertyLength","CenterDistance","read only","",1)
    vs.setExpression("CenterDistance","WormPitchDiameter/2+Module*GearTeeth/2")
    vs.addProperty("App::PropertyLength","WheelPitchDiameter","read only","",1)
    vs.setExpression("WheelPitchDiameter","Module*GearTeeth")
    return vs


class GloboidWormGearResult:
    """FeaturePython for auto-regeneration of globoid worm gear (VarSet)."""

    def __init__(self, obj, vs):
        self._vs=vs; self._rebuilding=False; self._pending_rebuild=False; self._lk={}; self._watcher=None; self._needs_rebuild=False
        self._debounce=None; self.Type="GloboidWormGearResult"
        obj.addProperty("App::PropertyString","VarSetName","Gear","",1).VarSetName=vs.Name
        obj.addProperty("App::PropertyString","BodyName","Gear","").BodyName=vs.Name.replace("_values","_Body",1)
        obj.addProperty("App::PropertyString","Version","read only","",1).Version="0.1"
        obj.addProperty("App::PropertyString","Status","read only","",1)
        obj.addProperty("App::PropertyAngle","WheelPhase","Gear",
            QT_TRANSLATE_NOOP("App::Property","Wheel tooth phase offset (tweak for meshing)")).WheelPhase = 2.0
        obj.Proxy=self; self.Object=obj; obj.Status="Not yet generated"
        self._sw(vs.Name)

    def __getstate__(self): return self.Type
    def __setstate__(self,s):
        if s:self.Type=s
        self._vs=None; self._rebuilding=False; self._pending_rebuild=False; self._lk={}; self._watcher=None; self._needs_rebuild=False; self._debounce=None

    def _gv(self):
        if self._vs is None:
            try: self._vs=self.Object.Document.getObject(self.Object.VarSetName)
            except: pass
        return self._vs

    def _rd(self,p):
        v=self._gv()
        if not v: return
        if hasattr(v,p):
            pr=getattr(v,p)
            if isinstance(pr,bool): return pr
            if isinstance(pr,int): return float(pr)
            if hasattr(pr,"Value"): return float(pr.Value)
            return float(pr)
        return None

    def _lt(self):
        """Load current VarSet values into _lk (last known)."""
        v=self._gv()
        if not v: return
        for p in ["Module","NumberOfThreads","GearTeeth","PressureAngle","WormPitchDiameter",
                  "CylinderDiameter","ArcAngle","WormLength","CylinderLength","RightHanded",
                  "BoreEnabled","BoreDiameter","KeywayEnabled","KeywayWidth","KeywayDepth",
                  "CreateMatingGear","GearHeight","Clearance","GearBoreEnabled","GearBoreDiameter",
                  "GearKeywayEnabled"]:
            self._lk[p]=self._rd(p)

    def _vc(self):
        """Values changed since last rebuild?"""
        v=self._gv()
        if not v or not self._lk: return v is not None
        E=1e-9
        for p,last in self._lk.items():
            cur=self._rd(p)
            if cur is None and last is None: continue
            if cur is None or last is None: return True
            if isinstance(cur,bool):
                if cur!=last: return True
            elif abs(cur-last)>E: return True
        return False

    def _sw(self,vn):
        self._st()
        self._watcher=_VarSetWatcher(self,vn,watched=frozenset(self._lk.keys()))
        App.addDocumentObserver(self._watcher)

    def _st(self):
        if self._watcher:
            try: App.removeDocumentObserver(self._watcher)
            except: pass
            self._watcher=None

    def execute(self,obj): pass

    def onChanged(self, fp, prop):
        """Rotate the wheel in-place when WheelPhase is tweaked — no rebuild."""
        if prop == "WheelPhase" and not self._rebuilding:
            try:
                bn = str(self.Object.BodyName)
                wb = fp.Document.getObject(f"{bn}_WormWheel")
                if wb:
                    wp = fp.WheelPhase.Value
                    base = wb.Placement.Base
                    r = App.Rotation(App.Vector(1,0,0),90) * App.Rotation(App.Vector(0,0,1), wp)
                    wb.Placement = App.Placement(base, r)
            except Exception:
                pass

    def _set_needs_rebuild(self):
        if self._rebuilding:
            self._pending_rebuild = True
            return
        if not self._vc(): return
        if self._debounce is None:
            self._debounce = QtCore.QTimer()
            self._debounce.setSingleShot(True)
            self._debounce.timeout.connect(self._dr)
        self._debounce.start(500)

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding: return
        if not self._vc(): self._needs_rebuild=False; return
        self._needs_rebuild=False; QtCore.QTimer.singleShot(0,self._dr)

    def _dr(self):
        self._debounce = None
        if self._rebuilding or not self._vc(): return
        try: self.Object.Status="Regenerating..."
        except: pass
        self._rb()

    def _rb(self):
        self._rebuilding=True; vn=None
        try:
            v=self._gv()
            if not v: return
            vn=v.Name; bn=str(self.Object.BodyName); d=self.Object.Document
            self._lt()

            # Build parameters dict matching what generateGloboidWormGearPart expects
            def g(key,conv=None):
                val=self._lk.get(key)
                if conv: return conv(val) if val is not None else None
                return val

            params={
                "module":g("Module"),"num_threads":int(g("NumberOfThreads")),
                "gear_teeth":int(g("GearTeeth")),"pressure_angle":g("PressureAngle"),
                "worm_pitch_diameter":g("WormPitchDiameter"),
                "cylinder_diameter":g("CylinderDiameter"),"arc_angle":g("ArcAngle"),
                "worm_length":g("WormLength"),"cylinder_length":g("CylinderLength"),
                "right_handed":bool(g("RightHanded")),"body_name":bn,
                "bore_type":"circular" if bool(g("BoreEnabled")) else "none",
                "bore_diameter":g("BoreDiameter"),
                "keyway_enabled":bool(g("KeywayEnabled")),
                "keyway_width":g("KeywayWidth"),"keyway_depth":g("KeywayDepth"),
                "create_mating_gear":bool(g("CreateMatingGear")),
                "gear_height":g("GearHeight"),"clearance":g("Clearance"),
                "gear_bore_type":"circular" if bool(g("GearBoreEnabled")) else "none",
                "gear_bore_diameter":g("GearBoreDiameter"),
                "gear_keyway_enabled":bool(g("GearKeywayEnabled")),
                "wheel_phase": 0.0,  # built at 0; onChanged applies the stored phase
                "varset_name": v.Name,
            }

            self._st()
            old=d.getObject(bn)
            if old:
                ch=list(old.Group)
                for c in ch:
                    for p in c.PropertiesList:
                        try: c.setExpression(p,None)
                        except: pass
                for c in reversed(ch):
                    try: d.removeObject(c.Name)
                    except: pass
                d.removeObject(bn)

            self.Object.Status="Generating..."
            if App.GuiUp: QtCore.QCoreApplication.processEvents()
            generateGloboidWormGearPart(d,params)
            # Apply the stored WheelPhase rotation to the wheel body
            try:
                wp = self.Object.WheelPhase.Value
                if abs(wp) > 0.001:
                    wb = d.getObject(f"{bn}_WormWheel")
                    if wb:
                        base = wb.Placement.Base
                        r = App.Rotation(App.Vector(1,0,0),90) * App.Rotation(App.Vector(0,0,1), wp)
                        wb.Placement = App.Placement(base, r)
            except Exception:
                pass
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
            if vn: self._sw(vn)
            self._rebuilding=False
            if self._pending_rebuild:
                self._pending_rebuild = False
                if self._vc():
                    QtCore.QTimer.singleShot(50, self._dr)

    def force_Recompute(self): self._rb()


class GloboidWormGearCreateObject():
    def GetResources(self):
        return {'Pixmap': mainIcon, 'MenuText': "&Create Globoid Worm Gear", 'ToolTip': "Create parametric globoid (double-throated) worm gear"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        base = "GloboidWormGear_values"; un = base; c = 1
        while doc.getObject(un): un = f"{base}{c:03d}"; c += 1
        vs = createGloboidWormGearVarSet(doc, un)
        gn = "Regenerate"; c = 1
        while doc.getObject(gn): gn = f"Regenerate{c:03d}"; c += 1
        go = doc.addObject("Part::FeaturePython", gn)
        GloboidWormGearResult(go, vs)
        ViewProviderGearResult(go.ViewObject, mainIcon)
        go.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

    def IsActive(self): return True

class GloboidWormGear():
    def __init__(self, obj):
        self.Dirty = False
        obj.addProperty("App::PropertyString", "Version", "read only", QT_TRANSLATE_NOOP("App::Property", "Version"), 1).Version = "0.1"

        # Read-only calculated properties
        obj.addProperty("App::PropertyAngle", "LeadAngle", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Calculated lead angle of worm thread"), 1)
        obj.addProperty("App::PropertyLength", "CenterDistance", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Distance between worm and wheel axes"), 1)
        obj.addProperty("App::PropertyLength", "WheelPitchDiameter", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter of mating wheel"), 1)

        # Globoid Specific: Needs Gear Parameters to define curvature
        obj.addProperty("App::PropertyLength", "Module", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Module")).Module = 2.0
        obj.addProperty("App::PropertyInteger", "NumberOfThreads", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Number of threads (starts)")).NumberOfThreads = 1
        obj.addProperty("App::PropertyInteger", "GearTeeth", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Number of teeth on mating gear")).GearTeeth = 20

        # Worm geometry - pitch diameter at throat (50% larger default for better meshing)
        obj.addProperty("App::PropertyLength", "WormPitchDiameter", "GloboidWorm",
            QT_TRANSLATE_NOOP("App::Property", "Pitch diameter at worm throat")).WormPitchDiameter = 30.0
        obj.addProperty("App::PropertyLength", "CylinderDiameter", "GloboidWorm",
            QT_TRANSLATE_NOOP("App::Property", "Outer diameter of worm cylinder (0 = auto from pitch + threads)")).CylinderDiameter = 0.0
        obj.addProperty("App::PropertyAngle", "PressureAngle", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Pressure angle")).PressureAngle = 20.0

        # The worm length is defined by the wrap angle around the gear
        obj.addProperty("App::PropertyAngle", "ArcAngle", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Engagement angle (typically 60-70)")).ArcAngle = 70.0
        obj.addProperty("App::PropertyLength", "WormLength", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Length of the threaded section (0 = defined by ArcAngle)")).WormLength = 0.0
        obj.addProperty("App::PropertyLength", "CylinderLength", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Total length of the worm cylinder")    ).CylinderLength = 50.0
        obj.addProperty("App::PropertyBool", "RightHanded", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "True for Right-handed")).RightHanded = True
        obj.addProperty("App::PropertyString", "BodyName", "GloboidWorm", QT_TRANSLATE_NOOP("App::Property", "Body Name")).BodyName = "GloboidWorm"
        
        # Bore (circular only, controlled by boolean)
        obj.addProperty("App::PropertyBool", "BoreEnabled", "Bore", QT_TRANSLATE_NOOP("App::Property", "Enable center bore")).BoreEnabled = True
        obj.addProperty("App::PropertyLength", "BoreDiameter", "Bore", QT_TRANSLATE_NOOP("App::Property", "Bore diameter")).BoreDiameter = 5.0
        obj.addProperty("App::PropertyBool", "KeywayEnabled", "Bore", QT_TRANSLATE_NOOP("App::Property", "Enable keyway")).KeywayEnabled = False
        obj.addProperty("App::PropertyLength", "KeywayWidth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Width of keyway (DIN 6885)")).KeywayWidth = 2.0
        obj.addProperty("App::PropertyLength", "KeywayDepth", "Bore", QT_TRANSLATE_NOOP("App::Property", "Depth of keyway")).KeywayDepth = 1.0

        # Mating Gear
        obj.addProperty("App::PropertyBool", "CreateMatingGear", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Create the mating worm wheel")).CreateMatingGear = True
        obj.addProperty("App::PropertyLength", "GearHeight", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Height/thickness of mating gear")).GearHeight = 10.0
        obj.addProperty("App::PropertyFloat", "Clearance", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Clearance factor for backlash (multiplied by module)")).Clearance = 0.1
        obj.addProperty("App::PropertyBool", "GearBoreEnabled", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Enable bore in mating gear")).GearBoreEnabled = True
        obj.addProperty("App::PropertyLength", "GearBoreDiameter", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Bore diameter for mating gear")).GearBoreDiameter = 8.0
        obj.addProperty("App::PropertyBool", "GearKeywayEnabled", "MatingGear", QT_TRANSLATE_NOOP("App::Property", "Enable keyway in mating gear")).GearKeywayEnabled = False

        obj.addProperty("App::PropertyAngle", "WheelPhase", "MatingGear",
            QT_TRANSLATE_NOOP("App::Property", "Wheel tooth phase offset (tweak for meshing)")).WheelPhase = 2.0

        self.Type = 'GloboidWormGear'
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

        # Update calculated read-only properties
        if prop in ["Module", "NumberOfThreads", "GearTeeth", "WormPitchDiameter"]:
            try:
                module = fp.Module.Value
                num_threads = fp.NumberOfThreads
                gear_teeth = fp.GearTeeth
                worm_pitch_dia = fp.WormPitchDiameter.Value

                # Wheel pitch diameter = module * teeth
                wheel_pitch_dia = module * gear_teeth
                fp.WheelPitchDiameter = wheel_pitch_dia

                # Center distance = (worm_pitch + wheel_pitch) / 2
                center_dist = (worm_pitch_dia + wheel_pitch_dia) / 2.0
                fp.CenterDistance = center_dist

                # Lead angle: tan(γ) = lead / (π × d1)
                # where lead = π × module × num_threads
                lead = math.pi * module * num_threads
                if worm_pitch_dia > 0:
                    lead_angle_rad = math.atan(lead / (math.pi * worm_pitch_dia))
                    fp.LeadAngle = math.degrees(lead_angle_rad)
            except (AttributeError, TypeError, ZeroDivisionError):
                pass

    def GetParameters(self):
        return {
            "module": float(self.Object.Module.Value),
            "num_threads": int(self.Object.NumberOfThreads),
            "gear_teeth": int(self.Object.GearTeeth),
            "pressure_angle": float(self.Object.PressureAngle.Value),
            "worm_pitch_diameter": float(self.Object.WormPitchDiameter.Value),
            "cylinder_diameter": float(self.Object.CylinderDiameter.Value),
            "arc_angle": float(self.Object.ArcAngle.Value),
            "worm_length": float(self.Object.WormLength.Value),
            "cylinder_length": float(self.Object.CylinderLength.Value),
            "right_handed": bool(self.Object.RightHanded),
            "body_name": str(self.Object.BodyName),
            "bore_type": "circular" if bool(self.Object.BoreEnabled) else "none",
            "bore_diameter": float(self.Object.BoreDiameter.Value),
            "keyway_enabled": bool(self.Object.KeywayEnabled) if hasattr(self.Object, "KeywayEnabled") else False,
            "keyway_width": float(self.Object.KeywayWidth.Value),
            "keyway_depth": float(self.Object.KeywayDepth.Value),
            # Mating gear parameters
            "create_mating_gear": bool(self.Object.CreateMatingGear),
            "gear_height": float(self.Object.GearHeight.Value),
            "clearance": float(self.Object.Clearance),
            "gear_bore_type": "circular" if bool(self.Object.GearBoreEnabled) else "none",
            "gear_bore_diameter": float(self.Object.GearBoreDiameter.Value),
            "gear_keyway_enabled": bool(self.Object.GearKeywayEnabled) if hasattr(self.Object, "GearKeywayEnabled") else False,
            "gear_keyway_width": float(self.Object.KeywayWidth.Value),
            "gear_keyway_depth": float(self.Object.KeywayDepth.Value),
            "wheel_phase": float(self.Object.WheelPhase.Value) if hasattr(self.Object, "WheelPhase") else 0.0,
        }

    def force_Recompute(self):
        self.Dirty = True
        self.recompute()

    def recompute(self):
        if self.Dirty:
            try:
                generateGloboidWormGearPart(App.ActiveDocument, self.GetParameters())
                self.Dirty = False
                App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Globoid Worm Error: {e}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())

    def execute(self, obj):
        t = QtCore.QTimer()
        t.singleShot(50, self.recompute)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state

class ViewProviderGloboidWormGear:
    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.iconfile = iconfile if iconfile else mainIcon
    def attach(self, obj): self.Object = obj.Object
    def getDisplayModes(self, obj): return ["Shaded", "Wireframe"]
    def getDefaultDisplayMode(self):
        return "Shaded"
    def getIcon(self):
        return self.iconfile
    def doubleClicked(self, vobj): return True
    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui
        action = QtGui.QAction("Regenerate Gear", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)
    def regenerate(self):
        if hasattr(self.Object, 'Proxy'): self.Object.Proxy.force_Recompute()
    def __getstate__(self):
        return self.iconfile
    def __setstate__(self, state):
        self.iconfile = state if state else mainIcon

# ============================================================================
# GENERATION LOGIC
# ============================================================================

def _make_toroidal_spiral(center_distance, minor_r, half_angle, total_v, right_handed):
    """Create a toroidal spiral edge by projecting a 2D line onto a torus.

    Adapted from Curves WB HelicalSweepFP.py — a straight line in torus
    (U,V) parameter space traces a toroidal spiral in 3D.

    Part.Toroid() parametrisation (OCCT Geom_ToroidalSurface):
      x(u,v) = (R + r·cos(u)) · cos(v)
      y(u,v) = (R + r·cos(u)) · sin(v)
      z(u,v) = r · sin(u)
    U=0 → outer equator, U=π → inner equator (throat of hourglass).

    Args:
        center_distance: torus MajorRadius (R)
        minor_r: torus MinorRadius (r) — pitch, root, or tip
        half_angle: half of the U-span on the minor circle (radians)
        total_v: total V-span (ring angle, radians)
        right_handed: thread handedness

    Returns:
        Part.Edge — the 3D toroidal spiral
    """
    torus = Part.Toroid()
    torus.MajorRadius = center_distance
    torus.MinorRadius = minor_r

    u_start = pi - half_angle
    u_end = pi + half_angle
    v_start = -total_v / 2.0
    v_end = total_v / 2.0
    if not right_handed:
        v_start, v_end = -v_start, -v_end

    line2d = Part.Geom2d.Line2dSegment(vec2(u_start, v_start),
                                        vec2(u_end, v_end))
    return line2d.toShape(torus)


def _make_thread_groove_solid(
    center_distance, arc_radius, worm_pitch_radius,
    addendum, dedendum, module, num_threads, pressure_angle,
    effective_worm_length, cylinder_length, right_handed,
    shoulder_radius, outer_throat_radius,
):
    """Build a solid thread-groove tool using the HelicalSweep technique on a torus.

    Math follows the Otvinta GloboidCalculator:
      Base torus: MajorRadius R = center_distance, MinorRadius r_base = gear_pitch_radius
      Tip edges (narrow):  minor_r = r_base - module     (= arc_radius)
      Root edges (wide):   minor_r = r_base + dedendum
      Gap widths:  fTop    = m*(π/2 - 2*tan α)   — full width at tool tip (near worm axis)
                   fBottom = fTop + 2*m*(a+d)*tan α — full width at tool root (near worm surface)
      Angular offsets: δ_tip  = atan(fTop/2 / (r_base - m))
                       δ_root = atan(fBottom/2 / (r_base + d))

    For multi-start threads, only one groove is built; PolarPattern copies it.
    """
    tan_pa = math.tan(pressure_angle * util.DEG_TO_RAD)
    pitch = pi * module
    lead = pitch * num_threads

    # GloboidCalculator: gear pitch radius is the torus base minor radius
    gear_pitch_radius = center_distance - worm_pitch_radius

    # Gap widths — full widths at the two extreme torus surfaces
    fTop = module * (pi / 2.0 - 2.0 * tan_pa)
    fBottom = fTop + 2.0 * module * (addendum + dedendum) * tan_pa

    # Minor radii for trapezoid corners (GloboidCalculator)
    # base = gear_pitch_radius, offsets from base
    minor_r_tip = gear_pitch_radius - module       # addendum surface (= arc_radius)
    minor_r_root = gear_pitch_radius + dedendum    # dedendum surface

    # Extend tool tip slightly beyond the worm body surface for clean cut
    tool_overcut = module * 0.1
    minor_r_tip_ext = minor_r_tip - tool_overcut
    if minor_r_tip_ext < module:
        minor_r_tip_ext = module

    # V span: total ring-angle travel for the threaded section
    turns = effective_worm_length / lead
    total_v = 2.0 * pi * turns

    half_length = effective_worm_length / 2.0

    # Half-angle on the minor circle covering half_length along Z
    def u_half(mr):
        ratio = half_length / mr
        if ratio >= 1.0:
            return pi * 0.48
        return math.asin(ratio)

    # Reference u_half at the gear_pitch_radius, for V-scaling
    hu_ref = u_half(gear_pitch_radius)

    # Angular offsets (GloboidCalculator delta values)
    delta_tip = math.atan((fTop / 2.0) / minor_r_tip_ext)
    delta_root = math.atan((fBottom / 2.0) / minor_r_root)

    # --- Build 4 toroidal spiral edges (trapezoid corners) ---
    # Corner naming (from GloboidCalculator):
    #   1: Tip, Top    (tip radius, -delta_tip)   — left flank top
    #   2: Tip, Bottom (tip radius, +delta_tip)   — right flank top
    #   3: Root, Top   (root radius, -delta_root) — left flank bottom
    #   4: Root, Bottom (root radius, +delta_root) — right flank bottom
    # The delta adds to the v-coordinate (angular position around the major
    # circle), and π offset places the spiral on the worm side (v ≈ π).

    def make_spiral(minor_r, delta):
        hu = u_half(minor_r)
        torus = Part.Toroid()
        torus.MajorRadius = center_distance
        torus.MinorRadius = minor_r

        u_start = pi - hu
        u_end = pi + hu
        v_scale = hu / hu_ref if hu_ref > 0 else 1.0
        v_span = total_v * v_scale
        v_start = pi - v_span / 2.0 + delta
        v_end = pi + v_span / 2.0 + delta
        if not right_handed:
            v_start, v_end = -v_end + 2.0*pi, -v_start + 2.0*pi

        line2d = Part.Geom2d.Line2dSegment(vec2(u_start, v_start),
                                            vec2(u_end, v_end))
        return line2d.toShape(torus)

    edge_tip_t = make_spiral(minor_r_tip_ext, -delta_tip)
    edge_tip_b = make_spiral(minor_r_tip_ext, delta_tip)
    edge_root_t = make_spiral(minor_r_root, -delta_root)
    edge_root_b = make_spiral(minor_r_root, delta_root)

    # --- Build ruled surfaces between adjacent spiral edges ---
    # Groove cross-section (looking along the spiral):
    #   root_t ---- tip_t      (left flank)
    #      |           |
    #   root_b ---- tip_b      (right flank)
    # 4 faces: left flank, right flank, root (bottom), tip (top)

    face_left = Part.makeRuledSurface(edge_root_t, edge_tip_t)
    face_right = Part.makeRuledSurface(edge_root_b, edge_tip_b)
    face_root = Part.makeRuledSurface(edge_root_t, edge_root_b)
    face_tip = Part.makeRuledSurface(edge_tip_t, edge_tip_b)

    faces = [face_left, face_right, face_root, face_tip]
    shell = Part.Shell(faces)
    shell.sewShape()

    # Cap the ends to make a solid
    try:
        free_edges = shell.FreeBound
        cap_faces = []
        for wire_edges in free_edges:
            if isinstance(wire_edges, Part.Wire):
                cap_faces.append(Part.Face(wire_edges))
            else:
                w = Part.Wire(wire_edges)
                cap_faces.append(Part.Face(w))

        all_faces = list(shell.Faces) + cap_faces
        closed_shell = Part.Shell(all_faces)
        closed_shell.sewShape()
        solid = Part.Solid(closed_shell)
    except Exception as e:
        App.Console.PrintWarning(f"Thread solid capping failed ({e}), using shell\n")
        solid = Part.makeSolid(shell)

    App.Console.PrintMessage(
        f"Toroidal thread tool: turns={turns:.2f}, "
        f"minor_r_root={minor_r_root:.2f}, minor_r_tip={minor_r_tip_ext:.2f}, "
        f"fTop={fTop:.3f}, fBottom={fBottom:.3f}\n"
    )
    return solid


def validateGloboidParameters(parameters):
    """Validate globoid worm gear parameters.

    Args:
        parameters: Dictionary of gear parameters

    Raises:
        gearMath.GearParameterError: If parameters are invalid
    """
    if parameters["module"] < gearMath.MIN_MODULE:
        raise gearMath.GearParameterError(f"Module < {gearMath.MIN_MODULE}")
    if parameters["module"] > gearMath.MAX_MODULE:
        raise gearMath.GearParameterError(f"Module > {gearMath.MAX_MODULE}")
    if parameters["worm_pitch_diameter"] <= 0:
        raise gearMath.GearParameterError("Worm Pitch Diameter must be positive")
    if parameters["gear_teeth"] < gearMath.MIN_TEETH:
        raise gearMath.GearParameterError(f"Gear Teeth must be >= {gearMath.MIN_TEETH}")
    if parameters["cylinder_length"] <= 0:
        raise gearMath.GearParameterError("Cylinder Length must be positive")
    if parameters["arc_angle"] <= 0 or parameters["arc_angle"] > 180:
        raise gearMath.GearParameterError("Arc Angle must be between 0 and 180 degrees")

def generateGloboidWormGearPart(doc, parameters):
    """Generate a globoid (double-throated) worm gear.

    A globoid worm has a concave throat that wraps around the mating gear,
    providing greater contact area and load capacity than a standard worm.

    Args:
        doc: FreeCAD document object
        parameters: Dictionary containing gear parameters

    The geometry consists of:
    1. PartDesign::Revolution creating hourglass base cylinder
    2. Toroidal-sweep loft tool + PartDesign::Boolean cutting thread grooves
    3. PartDesign::PolarPattern for multi-start threads
    4. Optional bore
    """
    validateGloboidParameters(parameters)
    body_name = parameters.get("body_name", "GloboidWorm")
    body = util.readyPart(doc, body_name)

    # Clear the BaseFeature if set (from previous generation)
    if hasattr(body, 'BaseFeature') and body.BaseFeature:
        body.BaseFeature = None

    # Clean up old intermediate objects from previous generation attempts
    old_objects = [
        f"{body_name}_ToolBody",
        f"{body_name}_ToolBox",
        f"{body_name}_ThreadCut",
        f"{body_name}_CutResult",
        f"{body_name}_ThreadTool",
        f"{body_name}_WormWheel_Final",  # legacy boolean cut result
        f"{body_name}_ThreadSpine",
    ]
    for obj_name in old_objects:
        old_obj = doc.getObject(obj_name)
        if old_obj:
            try:
                doc.removeObject(obj_name)
            except Exception:
                pass

    # Extract parameters
    module = parameters["module"]
    num_threads = parameters["num_threads"]
    num_gear_teeth = parameters["gear_teeth"]
    worm_pitch_diameter = parameters["worm_pitch_diameter"]
    cylinder_diameter = parameters["cylinder_diameter"]
    pressure_angle = parameters["pressure_angle"]
    arc_angle = parameters["arc_angle"]
    worm_length = parameters["worm_length"]
    cylinder_length = parameters["cylinder_length"]
    right_handed = parameters["right_handed"]

    # Calculate geometry
    addendum = module * gearMath.ADDENDUM_FACTOR
    dedendum = module * gearMath.DEDENDUM_FACTOR

    # Gear pitch radius (mating gear)
    gear_pitch_radius = (module * num_gear_teeth) / 2.0
    # Worm pitch radius at throat
    worm_pitch_radius = worm_pitch_diameter / 2.0
    # Center distance between worm and gear axes
    center_distance = gear_pitch_radius + worm_pitch_radius

    # 1. PARAMETRIC BASE (Sketch + Revolve)
    # Outer radius at throat (where teeth tips are)
    outer_throat_radius = worm_pitch_radius + addendum

    # Cylinder diameter: if specified use it, otherwise auto-calculate
    # The cylinder outer diameter should be at least pitch + addendum
    if cylinder_diameter > 0.01:
        # User specified cylinder diameter
        actual_cylinder_radius = cylinder_diameter / 2.0
        # Ensure it's at least as big as the thread tips
        if actual_cylinder_radius < outer_throat_radius:
            App.Console.PrintWarning(
                f"CylinderDiameter ({cylinder_diameter:.2f}) is smaller than thread tips. "
                f"Using minimum: {outer_throat_radius * 2:.2f}\n"
            )
            actual_cylinder_radius = outer_throat_radius
    else:
        # Auto-calculate: use outer throat radius (pitch + addendum)
        actual_cylinder_radius = outer_throat_radius

    # Arc radius for globoid curve (centered at gear center)
    # The arc defines the hourglass concavity. Its minimum radius (at z=0) must
    # equal outer_throat_radius so the thread tool intersects the revolve surface
    # correctly: center_distance - arc_radius = outer_throat_radius
    arc_radius = center_distance - outer_throat_radius

    # Validate arc_radius is positive
    if arc_radius <= 0:
        raise gearMath.GearParameterError(
            f"Invalid geometry: arc_radius ({arc_radius:.2f}) must be positive. "
            f"Try increasing module or gear teeth, or decreasing worm diameter."
        )

    # Maximum worm length is limited by arc geometry (cannot exceed 2 * arc_radius)
    max_worm_length = arc_radius * 2.0 * 0.98  # 98% of max to avoid edge cases

    # Determine threaded section span
    # Thread must be long enough to cover the wheel height plus margin
    gear_height = parameters.get("gear_height", 10.0)
    min_thread_length = (gear_height + 4 * module) * 1.2

    if worm_length > 0.01:
        # If specified worm_length exceeds max, warn and clamp
        effective_worm_length = worm_length
        if worm_length > max_worm_length:
            App.Console.PrintWarning(
                f"Worm length ({worm_length:.2f}mm) exceeds max ({max_worm_length:.2f}mm) for current geometry.\n"
            )
            App.Console.PrintWarning(
                f"  To increase max length: increase GearTeeth or decrease WormDiameter.\n"
            )
            App.Console.PrintWarning(
                f"  Using effective worm length: {max_worm_length:.2f}mm\n"
            )
            effective_worm_length = max_worm_length

        # Calculate angle from specified length
        tooth_half_length = effective_worm_length / 2.0
        half_angle_rad = math.asin(tooth_half_length / arc_radius)
        # Update effective arc_angle for thread generation
        arc_angle = (half_angle_rad * 2.0) / util.DEG_TO_RAD
    else:
        # Calculate length from arc angle
        half_angle_rad = (arc_angle / 2.0) * util.DEG_TO_RAD
        tooth_half_length = arc_radius * math.sin(half_angle_rad)
        effective_worm_length = tooth_half_length * 2.0

    # Ensure thread is long enough to cover the wheel
    if effective_worm_length < min_thread_length:
        if min_thread_length <= max_worm_length:
            App.Console.PrintMessage(
                f"Extending thread length from {effective_worm_length:.2f}mm to {min_thread_length:.2f}mm to cover wheel.\n"
            )
            effective_worm_length = min_thread_length
            tooth_half_length = effective_worm_length / 2.0
            half_angle_rad = math.asin(tooth_half_length / arc_radius)
        else:
            App.Console.PrintWarning(
                f"Warning: Wheel height ({gear_height:.2f}mm) may exceed thread coverage.\n"
            )

    # Auto-extend cylinder so the thread + shoulder relief always fits
    cyl_extended = False
    min_cylinder = effective_worm_length + 2.0 * max(gear_height, 5.0)
    if cylinder_length < min_cylinder:
        App.Console.PrintMessage(
            f"Extending CylinderLength from {cylinder_length:.1f} to {min_cylinder:.1f}mm "
            f"to accommodate thread ({effective_worm_length:.1f}mm).\n"
        )
        cylinder_length = min_cylinder
        cyl_extended = True

    # Total half-length (including shoulders if any)
    total_half_length = max(cylinder_length / 2.0, tooth_half_length + 0.01)

    # Radius at edge of threaded area (for shoulders)
    shoulder_radius = center_distance - arc_radius * math.cos(half_angle_rad)
    
    # Shaft/bore radius (for sketch construction)
    bore_type = parameters.get("bore_type", "none")
    if bore_type == "none":
        shaft_radius = 0.0
    else:
        shaft_radius = parameters["bore_diameter"] / 2.0
        if shaft_radius >= outer_throat_radius - module:
            shaft_radius = outer_throat_radius - module

    # Create base sketch for revolution - Explicit Profile
    sk_base = util.createSketch(body, 'GloboidCylinder')
    
    # Find XZ Plane for Z-axis orientation
    xz_plane = None
    if hasattr(body, 'Origin') and body.Origin:
        for child in body.Origin.Group:
            if 'XZ' in child.Name or 'XZ' in child.Label:
                xz_plane = child
                break
        # Fallback
        if not xz_plane and len(body.Origin.Group) > 1:
             xz_plane = body.Origin.Group[1]

    if xz_plane:
        sk_base.AttachmentSupport = [(xz_plane, '')]
        sk_base.MapMode = 'FlatFace'
    else:
        # Fallback: Manual Placement (Rotate 90 deg around X to align Y with Global Z)
        sk_base.MapMode = 'Deactivated'
        sk_base.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(App.Vector(1,0,0), 90))

    # Dimensions
    half_cylinder_length = cylinder_length / 2.0
    half_worm_length = effective_worm_length / 2.0  # Use already-clamped effective length
    rect_outer_radius = outer_throat_radius

    # Calculate Arc Geometry
    arc_center = App.Vector(-center_distance, 0.0, 0)
    angle_span = 2.0 * half_angle_rad  # Already calculated from effective_worm_length
    # Angles for Part.ArcOfCircle (counter-clockwise from X-axis)
    # We want a curve to the left. Center is at -CD.
    # The arc bulges towards +X.
    # Actually, let's stick to the previous correct geometry:
    # Center at -CD. Radius R.
    # We want the arc segment that is closest to the axis (smallest X).
    # That is around angle 0.
    start_angle = -angle_span / 2.0
    end_angle = angle_span / 2.0

    # GEOMETRY CREATION (Counter-clockwise loop)
    geoList = []
    
    # 1. Right Line (Axis) - Upwards
    # From (0, -Len/2) to (0, Len/2)
    p_br_axis = App.Vector(0, -half_cylinder_length, 0)
    p_tr_axis = App.Vector(0, half_cylinder_length, 0)
    geoList.append(Part.LineSegment(p_br_axis, p_tr_axis))
    
    # 2. Top Line - Leftwards
    # From (0, Len/2) to (-OuterR, Len/2)
    p_tl_corner = App.Vector(-rect_outer_radius, half_cylinder_length, 0)
    geoList.append(Part.LineSegment(p_tr_axis, p_tl_corner))

    # 3. Top-Left Vertical Line - Downwards
    # From (-OuterR, Len/2) to Arc Start (-OuterR, WormLen/2) ??
    # Wait, the Arc is curved. The vertical line connects to the Arc EndPoint.
    # The Arc EndPoint X is determined by the arc radius and angle.
    # X = -CD + R*cos(end_angle). Y = R*sin(end_angle) = WormLen/2
    # So the vertical line goes from Top Corner to Arc Top.
    
    # Calculate Arc End Points
    # Top Point (End of Arc)
    arc_top_y = arc_radius * math.sin(end_angle)
    arc_top_x = -center_distance + arc_radius * math.cos(end_angle)
    p_arc_top = App.Vector(arc_top_x, arc_top_y, 0)
    
    # Bottom Point (Start of Arc)
    arc_bot_y = arc_radius * math.sin(start_angle)
    arc_bot_x = -center_distance + arc_radius * math.cos(start_angle)
    p_arc_bot = App.Vector(arc_bot_x, arc_bot_y, 0)
    
    # Line 3: From Top Corner to Arc Top
    geoList.append(Part.LineSegment(p_tl_corner, p_arc_top))
    
    # 4. The Arc - Downwards?
    # Sketcher arcs usually go CCW. 
    # If we want a contiguous loop, we need to order points carefully.
    # Current loop: Axis(Up) -> Top(Left) -> TL_Vert(Down) -> Arc(Down) -> BL_Vert(Down) -> Bot(Right)
    # Arc needs to go from Top to Bottom.
    # Part.ArcOfCircle(circle, start, end) goes CCW from start to end.
    # Start(-ang) is Bottom. End(+ang) is Top.
    # So ArcOfCircle goes Bottom -> Top.
    # We need Top -> Bottom.
    # We can add the curve, but we need to constrain it correctly.
    # Let's add it as is (Bottom->Top) but constrain the endpoints to match the loop direction.
    circle_base = Part.Circle(arc_center, App.Vector(0, 0, 1), arc_radius)
    arc_geo = Part.ArcOfCircle(circle_base, start_angle, end_angle)
    geoList.append(arc_geo)
    
    # 5. Bottom-Left Vertical Line
    # From Arc Bottom to Bottom Corner
    p_bl_corner = App.Vector(-rect_outer_radius, -half_cylinder_length, 0)
    geoList.append(Part.LineSegment(p_arc_bot, p_bl_corner))
    
    # 6. Bottom Line - Rightwards
    # From Bottom Corner to Axis Bottom
    geoList.append(Part.LineSegment(p_bl_corner, p_br_axis))
    
    # Add all geometry
    # Indices:
    # 0: Right Line (Axis)
    # 1: Top Line
    # 2: Top-Left Vertical
    # 3: Arc (Start=Bot, End=Top)
    # 4: Bot-Left Vertical
    # 5: Bottom Line
    idx_right = 0
    idx_top = 1
    idx_tl = 2
    idx_arc = 3
    idx_bl = 4
    idx_bot = 5
    
    sk_base.addGeometry(geoList, False)
    
    # CONSTRAINTS
    
    # 1. Coincident Connections
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_right, 2, idx_top, 1))
    # Top End -> TL Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_top, 2, idx_tl, 1))
    # TL End -> Arc End (Top)
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_tl, 2, idx_arc, 2))
    # Arc Start (Bot) -> BL Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_arc, 1, idx_bl, 1))
    # BL End -> Bot Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_bl, 2, idx_bot, 1))
    # Bot End -> Right Start
    sk_base.addConstraint(Sketcher.Constraint('Coincident', idx_bot, 2, idx_right, 1))
    
    # 2. Geometric Constraints
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_right))
    sk_base.addConstraint(Sketcher.Constraint('Horizontal', idx_top))
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_tl))
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_bl))
    sk_base.addConstraint(Sketcher.Constraint('Horizontal', idx_bot))
    
    # 3. Placement Constraints
    # Right Line on Y Axis - REMOVED (Redundant with Symmetry/Vertical?)
    # sk_base.addConstraint(Sketcher.Constraint('PointOnObject', idx_right, 1, -2)) 
    
    # Arc Center on X Axis (Horizontal alignment with Origin) - ADDED per Option A
    sk_base.addConstraint(Sketcher.Constraint('PointOnObject', idx_arc, 3, -1))
    
    # 4. Dimensional Constraints
    # Cylinder Length (Right Line Length)
    cst_len = sk_base.addConstraint(Sketcher.Constraint('DistanceY', idx_right, 1, idx_right, 2, cylinder_length))
    vs_name = parameters.get("varset_name", "GloboidWormGearParameters")
    if not cyl_extended:
        sk_base.setExpression(f'Constraints[{cst_len}]', f'<<{vs_name}>>.CylinderLength')
    
    # Symmetry for Cylinder (Right Line midpoint on Origin)
    sk_base.addConstraint(Sketcher.Constraint('Symmetric', idx_right, 1, idx_right, 2, -1, 1))
    
    # Constrain Arc Radius.
    cst_rad = sk_base.addConstraint(Sketcher.Constraint('Radius', idx_arc, arc_radius))
    
    # Constrain Arc Center Distance
    cst_cd = sk_base.addConstraint(Sketcher.Constraint('DistanceX', idx_arc, 3, idx_right, 1, center_distance))
    
    # Worm Length (Vertical Span of Arc) - use effective_worm_length which is clamped to valid range
    cst_worm_len = sk_base.addConstraint(Sketcher.Constraint('DistanceY', idx_arc, 1, idx_arc, 2, effective_worm_length))
    # Only link to property if worm_length wasn't clamped (otherwise expression would override our clamping)
    if worm_length > 0.01 and worm_length <= max_worm_length:
        vs_name = parameters.get("varset_name", "GloboidWormGearParameters")
        sk_base.setExpression(f'Constraints[{cst_worm_len}]', f'<<{vs_name}>>.WormLength')
    
    # Vertical Alignment for Arc Endpoints (Ensures symmetry about X-axis without overconstraining)
    sk_base.addConstraint(Sketcher.Constraint('Vertical', idx_arc, 1, idx_arc, 2))

    # Removed: Symmetry for Arc - redundant with explicit arc center position + worm length span
    # Arc endpoints are fully determined by: center position, radius, and vertical span

    # Removed: Block constraint - not parametric, causes overconstraint

    doc.recompute()

    # Check if sketch solved successfully
    if sk_base.Shape.isNull():
        App.Console.PrintError(f"GloboidCylinder sketch failed to solve. Geometry params:\n")
        App.Console.PrintError(f"  arc_radius={arc_radius:.2f}, effective_worm_length={effective_worm_length:.2f}\n")
        App.Console.PrintError(f"  half_angle_rad={half_angle_rad:.4f}, angle_span={angle_span:.4f}\n")
        App.Console.PrintError(f"  center_distance={center_distance:.2f}, outer_throat_radius={outer_throat_radius:.2f}\n")
        raise gearMath.GearParameterError("Sketch failed to solve - check parameter combination")

    # 1. REVOLUTION - Create hourglass body using PartDesign::Revolution
    rev = body.newObject("PartDesign::Revolution", "HourglassBody")
    rev.Profile = sk_base
    rev.ReferenceAxis = (sk_base, ["V_Axis"])
    rev.Angle = 360
    body.Tip = rev
    doc.recompute()

    # 2. THREAD GAPS — Toroidal spiral + SubtractivePipe
    #
    # The hourglass surface is a torus (MajorRadius=center_distance,
    # MinorRadius=arc_radius).  A straight line in torus (U,V) parameter
    # space, projected via Geom2d.Line2dSegment.toShape(torus), traces
    # a toroidal spiral — the mathematically correct thread path.
    #
    # We build the groove solid from 4 toroidal spiral edges (the corners
    # of the trapezoidal thread gap profile) using the HelicalSweep
    # technique from the Curves WB, then cut it from the body.
    #
    # Adapted from Curves WB HelicalSweepFP.py (Chris_G, LGPL 2.1)
    # and Otvinta GloboidCalculator math.

    thread_pitch = math.pi * module
    lead = thread_pitch * num_threads
    turns = effective_worm_length / lead

    # 2. THREAD GAPS — PartDesign::SubtractivePipe with toroidal spiral spine
    #
    # A single toroidal spiral on the gear-pitch torus serves as the spine.
    # A trapezoidal profile sketch is swept along it with Frenet orientation,
    # cutting a thread groove with GloboidCalculator-correct dimensions.
    # For multi-start worms: PartDesign::PolarPattern.
    #
    # geometry is fully contained within the PartDesign Body — no external
    # parts or shape-replacement hacks.

    # GloboidCalculator math
    gear_pitch_radius = center_distance - worm_pitch_radius
    tan_pa = math.tan(pressure_angle * util.DEG_TO_RAD)

    fTop = module * (pi / 2.0 - 2.0 * tan_pa)
    fBottom = fTop + 2.0 * module * (addendum + dedendum) * tan_pa

    # Build toroidal spiral spine on the gear-pitch-radius torus
    turns = effective_worm_length / lead
    total_v = 2.0 * pi * turns
    half_len = effective_worm_length / 2.0
    hu_spine = math.asin(min(half_len / gear_pitch_radius, 1.0))

    torus_spine = Part.Toroid()
    torus_spine.MajorRadius = center_distance
    torus_spine.MinorRadius = gear_pitch_radius

    u_start = pi - hu_spine
    u_end = pi + hu_spine
    v_start = pi - total_v / 2.0
    v_end = pi + total_v / 2.0
    if not right_handed:
        v_start, v_end = -v_end + 2.0*pi, -v_start + 2.0*pi

    line2d = Part.Geom2d.Line2dSegment(vec2(u_start, v_start), vec2(u_end, v_end))
    spiral_edge = line2d.toShape(torus_spine)
    spiral_wire = Part.Wire([spiral_edge])

    spine_obj_name = f"{body_name}_ThreadSpine"
    spine_obj = doc.addObject("Part::Feature", spine_obj_name)
    spine_obj.Shape = spiral_wire
    spine_obj.Visibility = False

    # Trapezoidal groove profile sketch — manually placed at the spine start
    # with the sketch plane normal (= sweep direction) aligned to the spine
    # tangent T, and depth direction aligned to the torus SURFACE normal.
    # (FrenetNB uses the CURVE Frenet normal, which points out of the body.)
    sk_groove = util.createSketch(body, 'ThreadGrooveProfile')
    sk_groove.MapMode = "Deactivated"

    # Point and surface normal at the start of the spine
    R = center_distance
    r = gear_pitch_radius
    u0 = u_start
    v0 = v_start
    cu = math.cos(u0); su = math.sin(u0)
    cv = math.cos(v0); sv = math.sin(v0)
    R_plus_r_cu = R + r * cu
    start_pt = App.Vector(R_plus_r_cu * cv, R_plus_r_cu * sv, r * su)

    # Tangent T = Su*Δu + Sv*Δv along the spine
    Su = App.Vector(-r * su * cv, -r * su * sv, r * cu)
    Sv = App.Vector(-R_plus_r_cu * sv, R_plus_r_cu * cv, 0.0)
    du = u_end - u_start
    dv = v_end - v_start
    T = (Su * du + Sv * dv).normalize()

    # Surface normal N_surf = S_u × S_v (points into the body at u≈π)
    N_surf = Su.cross(Sv)
    if N_surf.Length > 1e-9:
        N_surf = N_surf.normalize()
    else:
        N_surf = App.Vector(1, 0, 0)

    # Binormal B = T × N_surf (circumferential / along the surface)
    B = T.cross(N_surf)
    if B.Length > 1e-9:
        B = B.normalize()
    else:
        B = App.Vector(0, 1, 0)

    # Re-orthogonalise: N' = B × T (ensure orthonormal right-handed frame)
    N = B.cross(T)

    # Build rotation: sketch Z → T, sketch Y → N (into body), sketch X → B
    rot_align = App.Rotation(App.Vector(0, 0, 1), T)
    Y_intermediate = rot_align.multVec(App.Vector(0, 1, 0))
    angle = math.atan2(T.dot(Y_intermediate.cross(N)), Y_intermediate.dot(N))
    rot = App.Rotation(T, angle) * rot_align
    sk_groove.Placement = App.Placement(start_pt, rot)

    hw_narrow = fTop / 2.0
    hw_wide = fBottom / 2.0

    # Rotation: sketch X → binormal (circumferential / groove width)
    #           sketch Y → surface normal (into body / groove depth)
    #           sketch Z → tangent (sweep direction along spine)
    pts = [
        App.Vector(-hw_narrow, +dedendum, 0),   # left,  deep (narrow)
        App.Vector(+hw_narrow, +dedendum, 0),   # right, deep (narrow)
        App.Vector(+hw_wide, -addendum, 0),     # right, shallow (wide)
        App.Vector(-hw_wide, -addendum, 0),     # left,  shallow (wide)
    ]
    lines = []
    for i in range(4):
        lines.append(sk_groove.addGeometry(Part.LineSegment(pts[i], pts[(i+1)%4]), False))
    for i in range(4):
        sk_groove.addConstraint(Sketcher.Constraint("Coincident", lines[i], 2, lines[(i+1)%4], 1))
    # Symmetric about Y axis: top edge endpoints have opposite X, same Y
    sk_groove.addConstraint(Sketcher.Constraint("Symmetric", lines[0], 1, lines[0], 2, -2, 1))

    doc.recompute()

    spipe = body.newObject("PartDesign::SubtractivePipe", "ThreadGroove")
    spipe.Profile = sk_groove
    spipe.Spine = (spine_obj, ['Edge1'])
    # Frenet orientation keeps the profile aligned to the curve's normal/binormal
    if hasattr(spipe, 'Transformation'):
        spipe.Transformation = 1  # 0=Constant, 1=Frenet, 2=Auxiliary, 3=Binormal
    body.Tip = spipe

    # Multi-start: PartDesign::PolarPattern
    if num_threads > 1:
        polar = util.createPolar(body, spipe, sk_groove, num_threads, "MultiStartThreads")
        polar.Originals = [spipe]
        body.Tip = polar

    doc.recompute()

    App.Console.PrintMessage(
        f"Thread (toroidal): pitch={thread_pitch:.2f}, lead={lead:.2f}, "
        f"turns={turns:.2f}, starts={num_threads}, "
        f"spine_minor_r={gear_pitch_radius:.2f}, fTop={fTop:.3f}, fBottom={fBottom:.3f}\n"
    )

    body.ViewObject.Visibility = True

    # 5. SHOULDER RELIEF — pocket away the shoulder at each end so the
    #     mating gear teeth don't hit the flared cylinder ends.
    #     Sketch an annular ring (outer = clearance hole, inner = shaft)
    #     and pocket it from the end face inward past the thread region.
    try:
        pocket_depth = max(0.0, cylinder_length / 2.0 - effective_worm_length / 2.0 + 1.0)
        shaft_clear_r = outer_throat_radius * 0.4  # shaft diameter after relief
        for sign in (1.0, -1.0):
            sk = util.createSketch(body, f"ShoulderRelief{'+' if sign>0 else '-'}")
            sk.MapMode = "Deactivated"
            z_pos = sign * half_cylinder_length
            sk.Placement = App.Placement(App.Vector(0, 0, z_pos), App.Rotation())
            # Outer circle — larger than any shoulder feature
            oc = sk.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1),
                                            rect_outer_radius * 2.0), False)
            sk.addConstraint(Sketcher.Constraint("Coincident", oc, 3, -1, 1))
            # Inner circle — the thin shaft we want to keep
            ic = sk.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1),
                                            shaft_clear_r), False)
            sk.addConstraint(Sketcher.Constraint("Coincident", ic, 3, -1, 1))
            pk = util.createPocket(body, sk, pocket_depth)
            pk.Reversed = (sign < 0)  # Top: pocket +Z? Bottom: pocket -Z?
            body.Tip = pk
        App.Console.PrintMessage("Shoulder relief pockets created\n")
    except Exception as e:
        App.Console.PrintWarning(f"Shoulder relief failed: {e}\n")

    # 6. MATING GEAR (Worm Wheel)
    create_mating_gear = parameters.get("create_mating_gear", True)
    if create_mating_gear:
        try:
            # Pass worm pitch radius for groove calculation
            # The wheel teeth should extend to the worm's pitch circle
            generateMatingGear(doc, parameters, center_distance, worm_pitch_radius, addendum, dedendum)
        except Exception as e:
            App.Console.PrintWarning(f"Could not create mating gear: {e}\n")
            import traceback
            App.Console.PrintWarning(traceback.format_exc())

    doc.recompute()

    # 7. BORE & KEYWAY (worm body) — created last so the body is stable
    if bore_type != "none":
        try:
            bd = parameters["bore_diameter"]
            z_place = cylinder_length / 2.0
            bore_sk = util.createSketch(body, "Bore")
            ci = bore_sk.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), bd/2), False)
            bore_sk.addConstraint(Sketcher.Constraint("Coincident", ci, 3, -1, 1))
            bore_sk.addConstraint(Sketcher.Constraint("Diameter", ci, bd))
            bore_sk.Placement = App.Placement(App.Vector(0, 0, z_place), App.Rotation())
            bore_sk.MapMode = "Deactivated"
            bp = util.createPocket(body, bore_sk, cylinder_length)
            bp.Reversed = False
            kw = parameters.get("keyway_width", 2.0)
            kd = parameters.get("keyway_depth", 1.0)
            if parameters.get("keyway_enabled", False):
                tiny = 0.01
                kw_sk = util.createSketch(body, "Keyway")
                pts = [App.Vector(-0.5,-0.5,0), App.Vector(0.5,-0.5,0),
                       App.Vector(0.5,0.5,0), App.Vector(-0.5,0.5,0)]
                kls = []
                for i in range(4):
                    kls.append(kw_sk.addGeometry(Part.LineSegment(pts[i],pts[(i+1)%4]), False))
                for i in range(4):
                    kw_sk.addConstraint(Sketcher.Constraint("Coincident", kls[i],2,kls[(i+1)%4],1))
                kw_sk.addConstraint(Sketcher.Constraint("Horizontal", kls[0]))
                kw_sk.addConstraint(Sketcher.Constraint("Vertical", kls[1]))
                kw_sk.addConstraint(Sketcher.Constraint("Horizontal", kls[2]))
                kw_sk.addConstraint(Sketcher.Constraint("Vertical", kls[3]))
                c = kw_sk.addConstraint(Sketcher.Constraint("DistanceX", kls[0],1,-1,1,-kw/2))
                kw_sk.addConstraint(Sketcher.Constraint("DistanceY", kls[0],1,-1,1,bd/2-kd))
                c = kw_sk.addConstraint(Sketcher.Constraint("DistanceX", kls[0],2,-1,1,kw/2))
                c = kw_sk.addConstraint(Sketcher.Constraint("DistanceY", kls[1],2,-1,1,tiny))
                kw_sk.setExpression(f"Constraints[{c}]", f"{bd/2+kd}")
                kw_sk.Placement = App.Placement(App.Vector(0,0,z_place), App.Rotation())
                kw_sk.MapMode = "Deactivated"
                kp = util.createPocket(body, kw_sk, cylinder_length)
                kp.Reversed = False
                body.Tip = kp
            doc.recompute()
        except Exception as e:
            App.Console.PrintWarning(f"Bore/keyway creation failed: {e}\n")

    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass


def generateMatingGear(doc, parameters, center_distance, worm_pitch_radius, worm_addendum, worm_dedendum):
    """Generate the mating worm wheel (gear) for the globoid worm.

    Creates a Throated Helical Gear using parametric PartDesign operations:
    1. Creates tooth profile sketch at bottom
    2. Creates rotated tooth profile sketch at top
    3. Uses AdditiveLoft between sketches for helical tooth
    4. Polar pattern for all teeth
    5. Cuts concave throat groove

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters
        center_distance: Distance between worm and gear axes
        worm_pitch_radius: Pitch radius of worm at throat
        worm_addendum: Worm tooth addendum (tip extension above pitch)
        worm_dedendum: Worm tooth dedendum (root depth below pitch)
    """
    """Generate the mating worm wheel (gear) for the globoid worm.

    Creates a Throated Helical Gear using parametric PartDesign operations:
    1. Creates tooth profile sketch at bottom
    2. Creates rotated tooth profile sketch at top
    3. Uses AdditiveLoft between sketches for helical tooth
    4. Polar pattern for all teeth
    5. Cuts concave throat groove

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters
        center_distance: Distance between worm and gear axes
        worm_pitch_radius: Pitch radius of the worm at throat
        worm_addendum: Worm tooth addendum (tip extension above pitch)
        worm_dedendum: Worm tooth dedendum (root depth below pitch)
    """
    body_name = parameters.get("body_name", "GloboidWorm")
    gear_body_name = f"{body_name}_WormWheel"

    # Extract parameters
    module = parameters["module"]
    num_teeth = parameters["gear_teeth"]
    height = parameters["gear_height"]
    pressure_angle = parameters["pressure_angle"]
    num_threads = parameters["num_threads"]
    right_handed = parameters["right_handed"]

    # Calculate worm lead angle - this is the helix angle for the wheel
    thread_pitch = math.pi * module
    lead = thread_pitch * num_threads
    worm_pitch_diameter = worm_pitch_radius * 2.0

    # Lead angle: tan(lead_angle) = lead / (pi * worm_pitch_diameter)
    lead_angle_rad = math.atan(lead / (math.pi * worm_pitch_diameter))
    lead_angle_deg = lead_angle_rad / util.DEG_TO_RAD

    App.Console.PrintMessage(f"Worm wheel: lead_angle={lead_angle_deg:.2f}°, num_teeth={num_teeth}\n")
    App.Console.PrintMessage(f"Worm: thread_pitch={thread_pitch:.2f}, lead={lead:.2f}, worm_pitch_dia={worm_pitch_diameter:.2f}\n")

    # Clean up existing gear body
    gear_body = util.readyPart(doc, gear_body_name)

# Calculate gear geometry
    pitch_diameter = module * num_teeth
    gear_pitch_radius = pitch_diameter / 2.0
    base_diameter = pitch_diameter * math.cos(pressure_angle * util.DEG_TO_RAD)
    base_radius = base_diameter / 2.0
    addendum = module * gearMath.ADDENDUM_FACTOR
    dedendum = module * gearMath.DEDENDUM_FACTOR
    outer_radius = gear_pitch_radius + addendum
    root_radius = gear_pitch_radius - dedendum

    # Helical twist over gear height
    # twist_angle = height * tan(helix_angle) / pitch_radius
    helix_angle_rad = lead_angle_rad
    twist_total_rad = (height * math.tan(helix_angle_rad)) / gear_pitch_radius
    twist_total_deg_before_handedness = twist_total_rad / util.DEG_TO_RAD

    # Handedness: right-handed worm meshes with left-handed wheel
    if right_handed:
        twist_total_deg = -twist_total_deg_before_handedness
    else:
        twist_total_deg = twist_total_deg_before_handedness

    App.Console.PrintMessage(f"Helix angle: {math.degrees(helix_angle_rad):.2f}°, twist before handedness: {twist_total_deg_before_handedness:.2f}°\n")
    App.Console.PrintMessage(f"Final twist: {twist_total_deg:.2f}° over height {height:.2f}mm (right_handed={right_handed})\n")

    # =========================================================================
    # STEP 1: Tooth Profile Sketch
    # =========================================================================

    sk_tooth = util.createSketch(gear_body, 'ToothProfile')

    tooth_params = {
        "module": module,
        "num_teeth": num_teeth,
        "pressure_angle": pressure_angle,
        "profile_shift": 0.0,
        "tip_radius": gear_pitch_radius + addendum,
    }
    gearMath.generateToothProfile(sk_tooth, tooth_params)

    doc.recompute()

    # =========================================================================
    # STEP 2: Helical Tooth Sweep
    # =========================================================================

    helix = gear_body.newObject('PartDesign::AdditiveHelix', 'HelicalTooth')
    helix.Profile = sk_tooth
    helix.Height = height

    # Reference axis = body Z axis (wheel axis)
    origin = gear_body.Origin
    z_axis = origin.OriginFeatures[2]  # Z_Axis
    helix.ReferenceAxis = (z_axis, [''])

    # Helix pitch: distance along axis per full revolution
    # pitch = (π × pitch_diameter) / tan(helix_angle)
    helix_pitch = abs(
        (math.pi * pitch_diameter) / math.tan(helix_angle_rad)
    )
    helix.Pitch = helix_pitch

    # Handedness: right-handed worm meshes with left-handed wheel
    helix.LeftHanded = right_handed

    sk_tooth.Visibility = False
    gear_body.Tip = helix

    App.Console.PrintMessage(
        f"Helix tooth: pitch={helix_pitch:.2f}mm, height={height:.2f}mm, "
        f"left_handed={right_handed}\n"
    )

    doc.recompute()

    # =========================================================================
    # STEP 3: Polar Pattern for All Teeth
    # =========================================================================

    polar = util.createPolar(gear_body, helix, sk_tooth, num_teeth, 'Teeth')
    polar.Originals = [helix]
    helix.Visibility = False
    polar.Visibility = True
    gear_body.Tip = polar

    doc.recompute()

    # =========================================================================
    # STEP 5: Dedendum Circle (Fills the center)
    # =========================================================================

    df = root_radius * 2.0  # Root diameter
    dedendum_sketch = util.createSketch(gear_body, 'DedendumCircle')
    circle = dedendum_sketch.addGeometry(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01),
        False
    )
    dedendum_sketch.addConstraint(Sketcher.Constraint('Coincident', circle, 3, -1, 1))
    dedendum_sketch.addConstraint(Sketcher.Constraint('Diameter', circle, df + 0.02))

    dedendum_pad = util.createPad(gear_body, dedendum_sketch, height, 'DedendumPad')
    gear_body.Tip = dedendum_pad

    doc.recompute()

    # =========================================================================
    # STEP 6: Throat shaping (reserved)
    # =========================================================================
    # For a globoid worm, the wheel teeth sit in the worm thread valleys.
    # The worm flare at the wheel edges is small (~0.2mm for typical params)
    # and doesn't require a throat groove.  If a specific parameter
    # combination causes visible intersection, the user can reduce GearHeight
    # or increase GearTeeth to increase arc_radius.

    # =========================================================================
    # STEP 7: Mating Gear Bore & Keyway
    # =========================================================================
    gear_bore_type = parameters.get("gear_bore_type", "none")
    if gear_bore_type != "none":
        try:
            gbd = parameters["gear_bore_diameter"]
            gkw = parameters.get("gear_keyway_width", 2.0)
            gkd = parameters.get("gear_keyway_depth", 1.0)
            gkey = parameters.get("gear_keyway_enabled", False)

            gbore_sk = util.createSketch(gear_body, "Bore")
            gci = gbore_sk.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), gbd/2), False)
            gbore_sk.addConstraint(Sketcher.Constraint("Coincident", gci, 3, -1, 1))
            gbore_sk.addConstraint(Sketcher.Constraint("Diameter", gci, gbd))
            gbp = util.createPocket(gear_body, gbore_sk, height + 10.0, "Bore")
            gbp.Reversed = True

            if gkey:
                tiny = 0.01
                gkw_sk = util.createSketch(gear_body, "Keyway")
                gpts = [App.Vector(-0.5,-0.5,0), App.Vector(0.5,-0.5,0),
                        App.Vector(0.5,0.5,0), App.Vector(-0.5,0.5,0)]
                gkls = []
                for i in range(4):
                    gkls.append(gkw_sk.addGeometry(Part.LineSegment(gpts[i],gpts[(i+1)%4]), False))
                for i in range(4):
                    gkw_sk.addConstraint(Sketcher.Constraint("Coincident", gkls[i],2,gkls[(i+1)%4],1))
                gkw_sk.addConstraint(Sketcher.Constraint("Horizontal", gkls[0]))
                gkw_sk.addConstraint(Sketcher.Constraint("Vertical", gkls[1]))
                gkw_sk.addConstraint(Sketcher.Constraint("Horizontal", gkls[2]))
                gkw_sk.addConstraint(Sketcher.Constraint("Vertical", gkls[3]))
                c = gkw_sk.addConstraint(Sketcher.Constraint("DistanceX", gkls[0],1,-1,1,-gkw/2))
                gkw_sk.addConstraint(Sketcher.Constraint("DistanceY", gkls[0],1,-1,1,gbd/2-gkd))
                c = gkw_sk.addConstraint(Sketcher.Constraint("DistanceX", gkls[0],2,-1,1,gkw/2))
                c = gkw_sk.addConstraint(Sketcher.Constraint("DistanceY", gkls[1],2,-1,1,tiny))
                gkw_sk.setExpression(f"Constraints[{c}]", f"{gbd/2+gkd}")
                gkp = util.createPocket(gear_body, gkw_sk, height + 10.0, "Keyway")
                gkp.Reversed = True
                gear_body.Tip = gkp
            else:
                gear_body.Tip = gbp
        except Exception as e:
            App.Console.PrintWarning(f"Mating gear bore/keyway failed: {e}\n")

    # =========================================================================
    # STEP 8: Alignment & Placement
    # =========================================================================

    wheel_phase = parameters.get("wheel_phase", 0.0)
    r_align = App.Rotation(App.Vector(1, 0, 0), 90) * App.Rotation(App.Vector(0, 0, 1), wheel_phase)

    gear_body.Placement = App.Placement(
        App.Vector(center_distance, height / 2.0, 0),
        r_align
    )

    doc.recompute()
    doc.recompute()

    App.Console.PrintMessage(f"Helical Worm Wheel created: {gear_body_name} (helix angle={lead_angle_deg:.2f}°)\n")


try: FreeCADGui.addCommand('GloboidWormGearCreateObject', GloboidWormGearCreateObject())
except Exception: pass
