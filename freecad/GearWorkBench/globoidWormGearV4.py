"""
Globoid Worm Gear V4 — Full Parametric Hobbing Tree
====================================================

Simulates the hobbing of a globoid worm gear by building a chain of
boolean cuts in the FreeCAD document tree.  Each cut corresponds to one
angular step of the worm blank as it would rotate past a stationary hob
(cutter).

IMPORTANT: The system must be completely parametric.  Every geometric
object in the document tree (cylinder blank, cutter links, boolean cuts)
must be built from parametric FreeCAD features — never from raw
Part.make* shapes injected into Part::Feature objects.

Tree layout (all hidden except the final Cut):

  Cutter            — Part::Feature  — gear-wheel shape at origin
  WormCylinder      — PartDesign::Body — Sketch + Pad cylinder blank
  Hob_000           — App::Link      — Cutter positioned + tilted (step 0)
  Cut_000           — Part::Cut      — WormCylinder minus Hob_000
  Roll_001          — App::Link      — Cut_000 rotated by Δoa around Z
  Hob_001           — App::Link      — Cutter rotated by Δφ + positioned (step 1)
  Cut_001           — Part::Cut      — Roll_001 minus Hob_001
  ...
"""

import FreeCAD as App
import FreeCADGui
from . import gearMath
from . import util
import Part
import Sketcher
import os
import math
from PySide import QtCore
from .genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
mainIcon = os.path.join(smWB_icons_path, "globoidWormGear.svg")
version = "4.0.0"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VARSET
# ============================================================================

def createGloboidWormGearV4VarSet(doc, name):
    vs = doc.addObject("App::VarSet", name)

    vs.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version

    vs.addProperty("App::PropertyInteger", "NumberOfThreads", "GloboidWorm", "Thread starts").NumberOfThreads = 1
    vs.addProperty("App::PropertyLength", "Module", "GloboidWorm", "Module").Module = 3.0
    vs.addProperty("App::PropertyInteger", "GearTeeth", "GloboidWorm", "Mating gear teeth").GearTeeth = 20
    vs.addProperty("App::PropertyAngle", "PressureAngle", "GloboidWorm", "Pressure angle").PressureAngle = 20.0

    vs.addProperty("App::PropertyLength", "WormPitchDiameter", "GloboidWorm", "Pitch diameter at throat").WormPitchDiameter = 30.0
    vs.addProperty("App::PropertyLength", "ShaftDiameter", "GloboidWorm", "End shaft diameter").ShaftDiameter = 12.0
    vs.addProperty("App::PropertyLength", "ShaftLength", "GloboidWorm", "End shaft length each side").ShaftLength = 8.0
    vs.addProperty("App::PropertyLength", "WormLength", "GloboidWorm", "Threaded section length").WormLength = 35.0
    vs.addProperty("App::PropertyBool", "RightHanded", "GloboidWorm", "Right-handed").RightHanded = True
    vs.addProperty("App::PropertyFloat", "Backlash", "GloboidWorm",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance")).Backlash = 0.25

    vs.addProperty("App::PropertyInteger", "HobbingSteps", "GloboidWorm",
        "Number of hobbing cuts (0 = auto from geometry)").HobbingSteps = 0

    vs.addProperty("App::PropertyLength", "BoreDiameter", "Bore", "Bore diameter").BoreDiameter = 5.0
    vs.addProperty("App::PropertyBool", "BoreEnabled", "Bore", "Enable bore").BoreEnabled = True
    vs.addProperty("App::PropertyLength", "KeywayWidth", "Bore", "Keyway width").KeywayWidth = 2.0
    vs.addProperty("App::PropertyLength", "KeywayDepth", "Bore", "Keyway depth").KeywayDepth = 1.0
    vs.addProperty("App::PropertyBool", "KeywayEnabled", "Bore", "Enable keyway").KeywayEnabled = False

    vs.addProperty("App::PropertyBool", "CreateMatingGear", "MatingGear", "Create wheel").CreateMatingGear = True
    vs.addProperty("App::PropertyLength", "GearHeight", "MatingGear", "Wheel thickness").GearHeight = 10.0
    vs.addProperty("App::PropertyAngle", "WheelHelixAngle", "MatingGear",
        "Helix twist of wheel teeth (0 = auto from lead angle)").WheelHelixAngle = 30.0
    vs.addProperty("App::PropertyFloat", "Clearance", "MatingGear", "Clearance factor").Clearance = 0.1
    vs.addProperty("App::PropertyLength", "GearBoreDiameter", "MatingGear", "Wheel bore diameter").GearBoreDiameter = 8.0
    vs.addProperty("App::PropertyBool", "GearBoreEnabled", "MatingGear", "Enable wheel bore").GearBoreEnabled = True
    vs.addProperty("App::PropertyAngle", "WheelPhase", "MatingGear", "Wheel phase offset").WheelPhase = 2.0

    vs.addProperty("App::PropertyAngle", "WormStepAngle", "Hobbing",
        "Cylinder rotation per cut (0 = auto from tooth geometry)").WormStepAngle = 0
    vs.addProperty("App::PropertyAngle", "WheelStepAngle", "Hobbing",
        "Cutter rotation per cut (0 = auto from tooth geometry)").WheelStepAngle = 0

    vs.addProperty("App::PropertyLength", "LeadAngle", "read only", "", 1)
    vs.setExpression("LeadAngle", "atan(Module*pi*NumberOfThreads/(WormPitchDiameter*pi))")
    vs.addProperty("App::PropertyLength", "CenterDistance", "read only", "", 1)
    vs.setExpression("CenterDistance", "WormPitchDiameter/2 + Module*GearTeeth/2")
    vs.addProperty("App::PropertyLength", "WheelPitchDiameter", "read only", "", 1)
    vs.setExpression("WheelPitchDiameter", "Module*GearTeeth")

    vs.addProperty("App::PropertyAngle", "ComputedHelixAngle", "read only", "", 1)
    vs.setExpression(
        "ComputedHelixAngle",
        "atan(GearHeight * tan(atan(Module*pi*NumberOfThreads/(WormPitchDiameter*pi)))"
        " / (Module*GearTeeth/2))")

    return vs


# ============================================================================
# RESULT OBJECT
# ============================================================================

class GloboidWormGearV4Result:
    def __init__(self, obj, varset):
        self._varset = varset; self._rebuilding = False
        self._last_m = self._last_nt = self._last_gt = self._last_pa = None
        self._last_wpd = self._last_sd = self._last_sl = self._last_wl = None
        self._last_rh = self._last_cm = self._last_gh = self._last_cl = None
        self._last_gbd = self._last_gbe = self._last_wp = None
        self._last_bl = None
        self._last_hs = None
        self._last_wha = None
        self._last_wsa = None
        self._last_wssa = None
        self._watcher = None; self._needs_rebuild = False
        self.Type = "GloboidWormGearV4Result"
        obj.addProperty("App::PropertyString", "VarSetName", "Gear", "", 1).VarSetName = varset.Name
        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyString", "Status", "read only", "", 1)
        obj.Proxy = self; self.Object = obj; obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self): return self.Type

    def __setstate__(self, s):
        if s: self.Type = s
        self._varset = None; self._rebuilding = False
        self._last_m = self._last_nt = self._last_gt = self._last_pa = None
        self._last_wpd = self._last_sd = self._last_sl = self._last_wl = None
        self._last_rh = self._last_cm = self._last_gh = self._last_cl = None
        self._last_gbd = self._last_gbe = self._last_wp = None
        self._last_bl = None
        self._last_hs = None
        self._last_wha = None
        self._last_wsa = None
        self._last_wssa = None
        self._watcher = None; self._needs_rebuild = False

    def onDocumentRestored(self, obj):
        self.Object = obj; v = self._getVarSet()
        if v:
            for a in ["Module", "WormPitchDiameter", "ShaftDiameter", "ShaftLength", "WormLength",
                       "GearHeight", "Clearance", "GearBoreDiameter", "WheelPhase"]:
                setattr(self, f"_last_{a[0].lower()+a[1:]}", float(getattr(v, a).Value))
            self._last_nt = int(v.NumberOfThreads); self._last_gt = int(v.GearTeeth)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_rh = bool(v.RightHanded); self._last_cm = bool(v.CreateMatingGear)
            self._last_gbe = bool(v.GearBoreEnabled)
            self._last_bl = float(v.Backlash) if hasattr(v, "Backlash") else 0.0
            self._last_hs = int(v.HobbingSteps) if hasattr(v, "HobbingSteps") else 8
            self._last_wha = float(v.WheelHelixAngle.Value) if hasattr(v, "WheelHelixAngle") else 0.0
            self._last_wsa = float(v.WormStepAngle.Value) if hasattr(v, "WormStepAngle") else 0.0
            self._last_wssa = float(v.WheelStepAngle.Value) if hasattr(v, "WheelStepAngle") else 0.0
            self._startWatcher(v.Name); obj.Status = "Up to date"

    def _startWatcher(self, vn):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(self, vn, watched=frozenset((
            "Module", "NumberOfThreads", "GearTeeth", "PressureAngle", "WormPitchDiameter",
            "ShaftDiameter", "ShaftLength", "WormLength", "RightHanded", "CreateMatingGear",
            "GearHeight", "Clearance", "GearBoreEnabled", "GearBoreDiameter", "WheelPhase",
            "BoreEnabled", "KeywayEnabled", "BoreDiameter", "KeywayWidth", "KeywayDepth",
            "Backlash", "HobbingSteps", "WheelHelixAngle",
            "WormStepAngle", "WheelStepAngle")))
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
        try:
            v = self._getVarSet()
            if not v or self._last_m is None: return v is not None
            E = 1e-9
            return (abs(float(v.Module.Value) - self._last_m) > E or
                    int(v.NumberOfThreads) != self._last_nt or
                    int(v.GearTeeth) != self._last_gt or
                    abs(float(v.PressureAngle.Value) - self._last_pa) > E or
                    abs(float(v.WormPitchDiameter.Value) - self._last_wpd) > E or
                    abs(float(v.ShaftDiameter.Value) - self._last_sd) > E or
                    abs(float(v.ShaftLength.Value) - self._last_sl) > E or
                    abs(float(v.WormLength.Value) - self._last_wl) > E or
                    bool(v.RightHanded) != self._last_rh or
                    bool(v.CreateMatingGear) != self._last_cm or
                    abs(float(v.GearHeight.Value) - self._last_gh) > E or
                    abs(float(v.Clearance) - self._last_cl) > E or
                    bool(v.GearBoreEnabled) != self._last_gbe or
                    abs(float(v.GearBoreDiameter.Value) - self._last_gbd) > E or
                    abs(float(v.WheelPhase.Value) - self._last_wp) > E or
                    (hasattr(v, "Backlash") and abs(float(v.Backlash) - self._last_bl) > E) or
                    (hasattr(v, "HobbingSteps") and int(v.HobbingSteps) != self._last_hs) or
                    (hasattr(v, "WheelHelixAngle") and abs(float(v.WheelHelixAngle.Value) - self._last_wha) > E) or
                    (hasattr(v, "WormStepAngle") and abs(float(v.WormStepAngle.Value) - self._last_wsa) > E) or
                    (hasattr(v, "WheelStepAngle") and abs(float(v.WheelStepAngle.Value) - self._last_wssa) > E))
        except ReferenceError:
            self._varset = None; return False

    _DEBOUNCE_MS = 800  # ms to wait after last change before rebuilding

    def _set_needs_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._needs_rebuild = True
        try: self.Object.Status = "Waiting for input..."
        except: pass
        # (Re)start debounce timer — each keystroke resets the countdown.
        if not hasattr(self, "_debounce_timer") or self._debounce_timer is None:
            self._debounce_timer = QtCore.QTimer()
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._deferred_rebuild)
        self._debounce_timer.start(self._DEBOUNCE_MS)

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding: return
        if not self._values_changed(): self._needs_rebuild = False; return
        self._needs_rebuild = False
        if not hasattr(self, "_debounce_timer") or self._debounce_timer is None:
            self._debounce_timer = QtCore.QTimer()
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._deferred_rebuild)
        self._debounce_timer.start(self._DEBOUNCE_MS)

    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._rebuild()


    # -----------------------------------------------------------------------
    # Core rebuild — full parametric chain
    # -----------------------------------------------------------------------

    def _rebuild(self):
        self._rebuilding = True
        vn = None
        try:
            v = self._getVarSet()
            if not v:
                return
            vn = v.Name
            d = self.Object.Document

            # Cache all parameter values
            self._last_m = float(v.Module.Value)
            self._last_nt = int(v.NumberOfThreads)
            self._last_gt = int(v.GearTeeth)
            self._last_pa = float(v.PressureAngle.Value)
            self._last_wpd = float(v.WormPitchDiameter.Value)
            self._last_sd = float(v.ShaftDiameter.Value)
            self._last_sl = float(v.ShaftLength.Value)
            self._last_wl = float(v.WormLength.Value)
            self._last_rh = bool(v.RightHanded)
            self._last_cm = bool(v.CreateMatingGear)
            self._last_gh = float(v.GearHeight.Value)
            self._last_cl = float(v.Clearance)
            self._last_gbe = bool(v.GearBoreEnabled)
            self._last_gbd = float(v.GearBoreDiameter.Value)
            self._last_wp = float(v.WheelPhase.Value)
            self._last_bl = float(v.Backlash) if hasattr(v, "Backlash") else 0.0
            self._last_hs = int(v.HobbingSteps) if hasattr(v, "HobbingSteps") else 8
            self._last_wha = float(v.WheelHelixAngle.Value) if hasattr(v, "WheelHelixAngle") else 0.0
            self._last_wsa = float(v.WormStepAngle.Value) if hasattr(v, "WormStepAngle") else 0.0
            self._last_wssa = float(v.WheelStepAngle.Value) if hasattr(v, "WheelStepAngle") else 0.0

            if self._last_m <= 0:
                self.Object.Status = "Invalid params"
                return

            self._stopWatcher()

            # ---------------------------------------------------------------
            # Cleanup — destroy every object created by a previous rebuild
            # ---------------------------------------------------------------
            saved_wheel_placement = None

            old_wheel = d.getObject("WormWheel")
            if old_wheel:
                saved_wheel_placement = App.Placement(old_wheel.Placement)
                if hasattr(old_wheel, 'removeObjectsFromDocument'):
                    old_wheel.removeObjectsFromDocument()
                try:
                    d.removeObject(old_wheel.Name)
                except Exception:
                    pass

            # Remove WormCylinder Body (with children) if it exists
            old_cyl = d.getObject("WormCylinder")
            if old_cyl:
                if hasattr(old_cyl, 'Group'):
                    for c in reversed(list(old_cyl.Group)):
                        try:
                            d.removeObject(c.Name)
                        except Exception:
                            pass
                try:
                    d.removeObject("WormCylinder")
                except Exception:
                    pass

            # Collect all other objects from our naming convention and delete.
            to_remove = []
            for obj in list(d.Objects):
                n = obj.Name
                if (n == "Cutter" or n == "__TmpHobWheel__" or
                        n.startswith("Roll_") or n.startswith("Cut_") or
                        n.startswith("Hob_")):
                    to_remove.append(obj)

            for obj in reversed(to_remove):
                try:
                    d.removeObject(obj.Name)
                except Exception:
                    pass

            # Also clean up legacy V4 objects from previous versions
            for name in ["BooleanCut", "HobbingCutter", "WormBlank"]:
                old = d.getObject(name)
                if old:
                    if hasattr(old, 'Group'):
                        for c in reversed(list(old.Group)):
                            try:
                                d.removeObject(c.Name)
                            except Exception:
                                pass
                    if hasattr(old, 'removeObjectsFromDocument'):
                        old.removeObjectsFromDocument()
                    try:
                        d.removeObject(name)
                    except Exception:
                        pass

            self.Object.Status = "Generating..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            # ---------------------------------------------------------------
            # Geometry parameters
            # ---------------------------------------------------------------
            m = self._last_m
            nt = self._last_nt
            gt = self._last_gt
            pa = self._last_pa
            rh = self._last_rh

            wp_r = self._last_wpd / 2.0
            gp_r = m * gt / 2.0
            cd = gp_r + wp_r
            add = m
            ded = m * 1.25
            cl = self._last_cl
            cyl_r = wp_r + ded + gp_r * 0.4  # into cutter teeth for hourglass depth
            height = self._last_gh
            wl = self._last_wl

            # Lead angle and wheel twist
            pitch = math.pi * m
            lead = pitch * nt
            lead_rad = math.atan(lead / (math.pi * wp_r * 2))
            twist_rad = height * math.tan(lead_rad) / gp_r
            twist_deg = twist_rad * 180.0 / math.pi

            # Configurable helix override
            wha = self._last_wha
            if abs(wha) > 1e-9:
                twist_deg = wha

            # Small clearance so the cutter teeth clear the cylinder surface
            tip_clearance = 0.25 * m

            # Cylinder rotation per step — computed below after tooth geometry,
            # or overridden from VarSet if WormStepAngle > 0.
            wsa_override = self._last_wsa

            # num_cuts computed below after tooth geometry determines dtheta_worm.

            import time
            t0 = time.time()

            if App.GuiUp:
                self.Object.Status = "Building cutter shape..."
                QtCore.QCoreApplication.processEvents()

            # ---------------------------------------------------------------
            # Cutter — Part::Feature with the gear-wheel shape at origin
            # ---------------------------------------------------------------
            # Build the WormWheel body first — it doubles as the cutter.
            # Bore and final placement are added AFTER the hobbing chain.
            # ---------------------------------------------------------------
            App.Console.PrintMessage("[GloboidV4] Building wheel (cutter)...\n")
            self._make_wheel_base(d, wp_r)
            cutter_obj = d.getObject("WormWheel")
            cutter_obj.Visibility = False
            App.Console.PrintMessage(
                f"[GloboidV4] Wheel built ({time.time()-t0:.1f}s)\n")

            # ---------------------------------------------------------------
            # Cylinder blank — parametric PartDesign Body (Sketch + Pad)
            # ---------------------------------------------------------------
            App.Console.PrintMessage("[GloboidV4] Creating cylinder blank...\n")
            cyl_body = util.readyPart(d, "WormCylinder")
            sk_cyl = util.createSketch(cyl_body, "CylinderProfile")
            xy = None
            if hasattr(cyl_body, 'Origin') and cyl_body.Origin:
                for f in cyl_body.Origin.OriginFeatures:
                    if 'XY' in f.Name or 'XY' in f.Label:
                        xy = f
                        break
            if xy:
                sk_cyl.AttachmentSupport = [(xy, '')]
                sk_cyl.MapMode = 'FlatFace'
            ci = sk_cyl.addGeometry(
                Part.Circle(App.Vector(0, 0, 0),
                            App.Vector(0, 0, 1), cyl_r), False)
            sk_cyl.addConstraint(
                Sketcher.Constraint("Coincident", ci, 3, -1, 1))
            sk_cyl.addConstraint(
                Sketcher.Constraint("Radius", ci, cyl_r))

            pad = cyl_body.newObject("PartDesign::Pad", "CylinderPad")
            pad.Profile = sk_cyl
            pad.Type = 0
            pad.Length = wl
            pad.SideType = 2
            cyl_body.Tip = pad
            cyl_body.Visibility = False
            d.recompute()
            App.Console.PrintMessage(
                f"[GloboidV4] Cylinder ready ({time.time()-t0:.1f}s)\n")

            # ---------------------------------------------------------------
            # Hobbing chain — cylinder rotates AND cutter rotates
            # ---------------------------------------------------------------
            r_tilt = App.Rotation(App.Vector(1, 0, 0), 90)
            rc = cd + tip_clearance
            sign = -1.0 if rh else 1.0

            # --- Compute step angles from involute tooth geometry --------
            # Tooth thickness at the addendum circle (tip), measured as
            # an angle on the wheel.
            ra = gp_r + add
            inv_pa = math.tan(math.radians(pa)) - math.radians(pa)
            alpha_a = math.acos(gp_r * math.cos(math.radians(pa)) / ra)
            inv_aa = math.tan(alpha_a) - alpha_a
            # Angular thickness of one tooth at the tip (degrees)
            tooth_tip_deg = math.degrees(
                math.pi / gt + 2.0 * (inv_pa - inv_aa))
            # Full angular pitch = one tooth + one gap (degrees)
            tooth_pitch_deg = 360.0 / gt
            # Angular gap between teeth at the tip
            gap_tip_deg = tooth_pitch_deg - tooth_tip_deg

            App.Console.PrintMessage(
                f"[GloboidV4] Tooth geometry: pitch={tooth_pitch_deg:.3f} deg, "
                f"tip={tooth_tip_deg:.3f} deg, "
                f"gap={gap_tip_deg:.3f} deg\n")

            # dtheta_worm: how far the cylinder rotates per cut.
            # Default = tooth pitch (360/gt) so each cut carves one
            # groove per tooth position.
            if wsa_override > 0:
                dtheta_worm = wsa_override
            else:
                dtheta_worm = tooth_pitch_deg

            # dtheta_wheel: how far the cutter self-rotates per step
            # for helical alignment.
            # Default = tooth tip width so the opposite edge of a tooth
            # lands where the first edge was.
            if self._last_wssa > 0:
                dtheta_wheel = self._last_wssa
            else:
                dtheta_wheel = tooth_tip_deg

            # Number of cuts to cover the full cylinder.
            num_rev_steps = max(4, int(math.ceil(360.0 / dtheta_worm)))
            if self._last_hs > 0:
                num_cuts = self._last_hs
            else:
                num_cuts = num_rev_steps

            App.Console.PrintMessage(
                f"[GloboidV4] {num_cuts} cuts, "
                f"cyl_r={cyl_r:.2f}, "
                f"worm step={dtheta_worm:.4f} deg, "
                f"wheel step={dtheta_wheel:.4f} deg, "
                f"twist={twist_deg:.4f} deg\n")
            App.Console.PrintMessage(
                f"[GloboidV4] Building {num_cuts} cuts (limited to 4 for testing)...\n")

            prev_name = "WormCylinder"
            for i in range(num_cuts):
                t_cut = time.time()
                if App.GuiUp:
                    self.Object.Status = f"Cut {i+1}/{num_cuts}..."
                    QtCore.QCoreApplication.processEvents()

                # Orbit angle: how far around Z the cylinder has rotated
                # at this step.  Step 0 = no rotation.
                oa = dtheta_worm * i
                # Wheel self-rotation for helical alignment.
                phi = dtheta_wheel * i * sign

                # --- Cutter placement for this step ---
                # The Hob stays at a FIXED position (like V5's stationary
                # cutter).  The Roll link rotates the cylinder to present
                # fresh material.  Only the wheel self-rotation (phi)
                # changes per step — for helical tooth alignment.
                r_self = App.Rotation(App.Vector(0, 0, 1), phi)
                r_combined = r_tilt.multiply(r_self)
                hob = d.addObject("App::Link", f"Hob_{i:03d}")
                hob.LinkedObject = cutter_obj
                hob.Placement = App.Placement(
                    App.Vector(rc, 0, 0), r_combined)
                hob.Visibility = False

                # --- Base: rotate previous result around Z ---
                if i > 0:
                    # Each Roll applies ONE increment of rotation on top
                    # of the previous Cut (which already carries all prior
                    # rotations from its own Roll).
                    r_orbit = App.Rotation(
                        App.Vector(0, 0, 1), dtheta_worm)
                    roll = d.addObject("App::Link", f"Roll_{i:03d}")
                    roll.LinkedObject = d.getObject(prev_name)
                    roll.Placement = App.Placement(
                        App.Vector(0, 0, 0), r_orbit)
                    roll.Visibility = False
                    base_name = roll.Name
                else:
                    base_name = prev_name

                # --- Boolean cut ---
                cut = d.addObject("Part::Cut", f"Cut_{i:03d}")
                cut.Base = d.getObject(base_name)
                cut.Tool = hob
                cut.Visibility = (i == num_cuts - 1) or (i == 3)
                prev_name = cut.Name

                # Recompute incrementally
                d.recompute()

                App.Console.PrintMessage(
                    f"  Cut_{i:03d}: "
                    f"orbit={oa:.2f} deg, "
                    f"wheel_self={phi:.4f} deg, "
                    f"({time.time()-t_cut:.1f}s)\n")

                # Early exit for testing
                if i >= 3:
                    App.Console.PrintMessage(
                        f"[GloboidV4] Stopped after 4 cuts for testing "
                        f"({time.time()-t0:.1f}s)\n")
                    break

            # ---------------------------------------------------------------
            # Finish the wheel (bore + placement) — it was already built
            # above as the cutter for the hobbing chain.
            # ---------------------------------------------------------------
            if self._last_cm:
                self._finish_wheel(d, wp_r)
                if saved_wheel_placement is not None:
                    wb = d.getObject("WormWheel")
                    if wb:
                        wb.Placement = saved_wheel_placement

            self.Object.Status = "Up to date"
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            # Clean up on error — handle Body-type objects with children
            for bname in ["WormCylinder", "WormWheel"]:
                bobj = d.getObject(bname)
                if bobj:
                    if hasattr(bobj, 'Group'):
                        for c in reversed(list(bobj.Group)):
                            try:
                                d.removeObject(c.Name)
                            except Exception:
                                pass
                    if hasattr(bobj, 'removeObjectsFromDocument'):
                        bobj.removeObjectsFromDocument()
                    try:
                        d.removeObject(bname)
                    except Exception:
                        pass
            to_remove = []
            for obj in d.Objects:
                n = obj.Name
                if (n == "Cutter" or n == "__TmpHobWheel__" or
                        n.startswith("Roll_") or n.startswith("Cut_") or
                        n.startswith("Hob_")):
                    to_remove.append(obj)
            for obj in reversed(to_remove):
                try:
                    d.removeObject(obj.Name)
                except Exception:
                    pass
            self.Object.Status = "Error"
        finally:
            if vn:
                self._startWatcher(vn)
            self._rebuilding = False

    # -----------------------------------------------------------------------
    # Mating wheel — built in two phases so it can serve as the cutter.
    # Phase 1 (_make_wheel_base): teeth + dedendum + throat at origin.
    # Phase 2 (_finish_wheel): bore + final placement after hobbing.
    # -----------------------------------------------------------------------
    def _make_wheel_base(self, doc, worm_pitch_r):
        """Build WormWheel body (teeth, dedendum, throat) at origin."""
        v = self._getVarSet()
        if not v: return
        module = self._last_m; num_teeth = self._last_gt; height = self._last_gh
        pa = self._last_pa; nt = self._last_nt; rh = self._last_rh; cl = self._last_cl

        cd = self._last_wpd / 2 + module * num_teeth / 2
        wheel_phase = self._last_wp

        gbn = "WormWheel"
        gb = util.readyPart(doc, gbn)

        ded = module * 1.25; add = module * 1.0
        gp_r = module * num_teeth / 2
        wr = worm_pitch_r

        # Helical twist: use configurable value or auto-calculate from lead angle
        wha = self._last_wha
        if abs(wha) > 1e-9:
            twist_deg = wha
            if rh: twist_deg = -twist_deg
        else:
            pitch = math.pi * module; lead = pitch * nt
            lead_rad = math.atan(lead / (math.pi * worm_pitch_r * 2))
            twist_rad = height * math.tan(lead_rad) / gp_r
            twist_deg = twist_rad / math.pi * 180
            if rh: twist_deg = -twist_deg

        # Tooth profiles (bottom and top with twist)
        _bl = float(v.Backlash) if hasattr(v, "Backlash") else 0.0
        _ps = -_bl if _bl != 0.0 else 0.0

        # Centered: bottom at Z=-height/2, top at Z=+height/2
        h2 = height / 2.0

        sk_b = util.createSketch(gb, "ToothProfileBottom")
        xy = None
        for f in gb.Origin.OriginFeatures:
            if 'XY' in f.Name or 'XY' in f.Label: xy = f; break
        if xy:
            sk_b.AttachmentSupport = [(xy, '')]; sk_b.MapMode = "FlatFace"
            sk_b.AttachmentOffset = App.Placement(
                App.Vector(0, 0, -h2), App.Rotation(App.Vector(0, 0, 1), wheel_phase))
        gearMath.generateToothProfile(sk_b, {"module": module, "num_teeth": num_teeth,
            "pressure_angle": pa, "profile_shift": _ps})

        sk_t = util.createSketch(gb, "ToothProfileTop")
        if xy:
            sk_t.AttachmentSupport = [(xy, '')]; sk_t.MapMode = "FlatFace"
            sk_t.AttachmentOffset = App.Placement(
                App.Vector(0, 0, h2),
                App.Rotation(App.Vector(0, 0, 1), twist_deg + wheel_phase))
        gearMath.generateToothProfile(sk_t, {"module": module, "num_teeth": num_teeth,
            "pressure_angle": pa, "profile_shift": _ps})

        loft = gb.newObject("PartDesign::AdditiveLoft", "HelicalTooth")
        loft.Profile = sk_b; loft.Sections = [sk_t]; loft.Ruled = True
        gb.Tip = loft

        # Pattern teeth
        polar = util.createPolar(gb, loft, sk_b, num_teeth, "Teeth")
        polar.Originals = [loft]
        gb.Tip = polar

        # Gear body (dedendum cylinder) — centered with SideType=2
        df = (gp_r - ded) * 2
        ds = util.createSketch(gb, "DedendumCircle")
        ci = ds.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2), False)
        ds.addConstraint(Sketcher.Constraint("Diameter", ci, df))
        dp = util.createPad(gb, ds, height, "DedendumPad")
        dp.SideType = 2  # symmetric/midplane
        gb.Tip = dp

        doc.recompute()

        # Throat groove (concave waist matching the worm) — already at Z=0
        sk_th = gb.newObject("Sketcher::SketchObject", "ThroatCutSketch")
        xz = None
        for f in gb.Origin.OriginFeatures:
            if 'XZ' in f.Name or 'XZ' in f.Label: xz = f; break
        if xz:
            sk_th.AttachmentSupport = [(xz, '')]; sk_th.MapMode = "ObjectXY"
            sk_th.AttachmentOffset = App.Placement(
                App.Vector(0, 0, 0), App.Rotation())

        cut_r = wr + module * cl
        groove_pos = -cd

        ci = sk_th.addGeometry(Part.Circle(
            App.Vector(groove_pos, 0, 0), App.Vector(0, 0, 1), cut_r), False)
        sk_th.addConstraint(Sketcher.Constraint("PointOnObject", ci, 3, -1))
        sk_th.addConstraint(Sketcher.Constraint("Radius", ci, cut_r))
        sk_th.addConstraint(Sketcher.Constraint("DistanceX", ci, 3, -1, 1, groove_pos))
        sk_th.Visibility = False

        groove = gb.newObject("PartDesign::Groove", "ThroatGroove")
        groove.Profile = sk_th; groove.ReferenceAxis = (sk_th, ["V_Axis"])
        groove.Angle = 360.0
        gb.Tip = groove

        doc.recompute()

    def _finish_wheel(self, doc, worm_pitch_r):
        """Add bore and final placement to the WormWheel after hobbing."""
        module = self._last_m; num_teeth = self._last_gt; height = self._last_gh
        ded = module * 1.25; add = module * 1.0
        cd = self._last_wpd / 2 + module * num_teeth / 2
        gb_dia = self._last_gbd; gb_en = self._last_gbe

        gb = doc.getObject("WormWheel")
        if not gb: return

        # Bore
        if gb_en:
            gbs = util.createSketch(gb, "Bore")
            gci = gbs.addGeometry(Part.Circle(
                App.Vector(0, 0, 0), App.Vector(0, 0, 1), gb_dia / 2), False)
            gbs.addConstraint(Sketcher.Constraint("Coincident", gci, 3, -1, 1))
            gbs.addConstraint(Sketcher.Constraint("Diameter", gci, gb_dia))
            gbp = util.createPocket(gb, gbs, height + 10, "Bore")
            gbp.Reversed = True
            gb.Tip = gbp

        doc.recompute()

        # Final placement: tilt 90° around X, offset to center distance
        r_align = App.Rotation(App.Vector(1, 0, 0), 90)
        tip_clearance = ded - add  # 0.25 * module
        place_cd = cd + tip_clearance
        gb.Placement = App.Placement(App.Vector(place_cd, 0, 0), r_align)
        gb.Visibility = True

    def force_Recompute(self): self._rebuild()


# ============================================================================
# COMMAND
# ============================================================================

class GloboidWormGearV4Command:
    def GetResources(self):
        return {"Pixmap": mainIcon,
                "MenuText": "Create Globoid Worm Gear V4",
                "ToolTip": "Create globoid worm gear (hobbing simulation)"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        base = "GloboidWormV4_values"; un = base; c = 1
        while doc.getObject(un): un = f"{base}{c:03d}"; c += 1
        vs = createGloboidWormGearV4VarSet(doc, un)
        gn = "Regenerate"; c = 1
        while doc.getObject(gn): gn = f"Regenerate{c:03d}"; c += 1
        go = doc.addObject("Part::FeaturePython", gn)
        GloboidWormGearV4Result(go, vs)
        ViewProviderGearResult(go.ViewObject, mainIcon)
        go.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewFront()

    def IsActive(self): return True


FreeCADGui.addCommand("GloboidWormGearV4Command", GloboidWormGearV4Command())
