"""Globoid Worm Gear V3 — Smooth Torus Approach.

Builds a smooth torus (representing the mating gear envelope) and
boolean-subtracts it from a cylinder blank to create the globoid worm throat.

Algorithm:
  1. Smooth torus (virtual wheel envelope) via Part::Torus
  2. Cylinder blank via PartDesign Body + Pad
  3. Boolean subtract torus from cylinder → globoid worm throat
  4. Shaft ends, bore, keyway cuts
  5. Mating wheel: helical loft teeth + throat groove (same as V2)
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
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
mainIcon = os.path.join(smWB_icons_path, "globoidWormGear.svg")
version = "3.0.0"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VARSET
# ============================================================================

def createGloboidWormGearV3VarSet(doc, name):
    vs = doc.addObject("App::VarSet", name)

    vs.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version

    vs.addProperty("App::PropertyInteger", "NumberOfThreads", "GloboidWorm", "Thread starts").NumberOfThreads = 1
    vs.addProperty("App::PropertyLength", "Module", "GloboidWorm", "Module").Module = 3.0
    vs.addProperty("App::PropertyInteger", "GearTeeth", "GloboidWorm", "Mating gear teeth").GearTeeth = 20
    vs.addProperty("App::PropertyAngle", "PressureAngle", "GloboidWorm", "Pressure angle").PressureAngle = 20.0

    vs.addProperty("App::PropertyLength", "WormPitchDiameter", "GloboidWorm", "Pitch diameter at throat").WormPitchDiameter = 30.0
    vs.addProperty("App::PropertyLength", "ShaftDiameter", "GloboidWorm", "End shaft diameter").ShaftDiameter = 12.0
    vs.addProperty("App::PropertyLength", "ShaftLength", "GloboidWorm", "End shaft length each side").ShaftLength = 8.0
    vs.addProperty("App::PropertyLength", "WormLength", "GloboidWorm", "Threaded section length").WormLength = 60.0
    vs.addProperty("App::PropertyBool", "RightHanded", "GloboidWorm", "Right-handed").RightHanded = True
    vs.addProperty("App::PropertyFloat", "Backlash", "GloboidWorm",
        QT_TRANSLATE_NOOP("App::Property", "Backlash clearance")).Backlash = 0.25

    vs.addProperty("App::PropertyLength", "BoreDiameter", "Bore", "Bore diameter").BoreDiameter = 5.0
    vs.addProperty("App::PropertyBool", "BoreEnabled", "Bore", "Enable bore").BoreEnabled = True
    vs.addProperty("App::PropertyLength", "KeywayWidth", "Bore", "Keyway width").KeywayWidth = 2.0
    vs.addProperty("App::PropertyLength", "KeywayDepth", "Bore", "Keyway depth").KeywayDepth = 1.0
    vs.addProperty("App::PropertyBool", "KeywayEnabled", "Bore", "Enable keyway").KeywayEnabled = False

    vs.addProperty("App::PropertyBool", "CreateMatingGear", "MatingGear", "Create wheel").CreateMatingGear = True
    vs.addProperty("App::PropertyLength", "GearHeight", "MatingGear", "Wheel thickness").GearHeight = 10.0
    vs.addProperty("App::PropertyFloat", "Clearance", "MatingGear", "Clearance factor").Clearance = 0.1
    vs.addProperty("App::PropertyLength", "GearBoreDiameter", "MatingGear", "Wheel bore diameter").GearBoreDiameter = 8.0
    vs.addProperty("App::PropertyBool", "GearBoreEnabled", "MatingGear", "Enable wheel bore").GearBoreEnabled = True
    vs.addProperty("App::PropertyAngle", "WheelPhase", "MatingGear", "Wheel phase offset").WheelPhase = 2.0

    vs.addProperty("App::PropertyLength", "LeadAngle", "read only", "", 1)
    vs.setExpression("LeadAngle", "atan(Module*pi*NumberOfThreads/(WormPitchDiameter*pi))")
    vs.addProperty("App::PropertyLength", "CenterDistance", "read only", "", 1)
    vs.setExpression("CenterDistance", "WormPitchDiameter/2 + Module*GearTeeth/2")
    vs.addProperty("App::PropertyLength", "WheelPitchDiameter", "read only", "", 1)
    vs.setExpression("WheelPitchDiameter", "Module*GearTeeth")
    return vs


# ============================================================================
# TOOTH RING BUILDER (standalone Part.Wire — not a sketch)
# ============================================================================

def _build_tooth_ring_wire(module, num_teeth, pressure_angle_deg, profile_shift=0.0):
    """Build a closed Part.Wire of the full involute tooth ring cross-section.

    The ring is centred at the origin in the XY plane.
    Returns (wire, pitch_radius, outer_radius, root_radius).
    """
    pa = math.radians(pressure_angle_deg)
    dw = module * num_teeth
    rb = dw * math.cos(pa) / 2.0
    ra = dw / 2.0 + module * (gearMath.ADDENDUM_FACTOR + profile_shift)
    rf = dw / 2.0 - module * (gearMath.DEDENDUM_FACTOR - profile_shift)
    gp_r = dw / 2.0

    # Half angular tooth thickness at base circle
    s_pitch = module * (math.pi / 2.0 + 2.0 * profile_shift * math.tan(pa))
    inv_alpha = math.tan(pa) - pa
    theta_base = s_pitch / dw + inv_alpha

    tooth_angle = 2.0 * math.pi / num_teeth
    num_pts = 8  # points per involute curve

    edges = []

    for t_i in range(num_teeth):
        base_angle = t_i * tooth_angle
        rotation = base_angle + math.pi / 2.0 - theta_base

        # Right involute flank points
        start_r = max(rb + 0.001, rf)
        right_pts = []
        for i in range(num_pts):
            frac = i / (num_pts - 1)
            r = start_r + frac * (ra - start_r)
            if r <= rb:
                roll = 0
            else:
                phi = math.acos(min(rb / r, 1.0))
                roll = math.tan(phi)
            x_inv = rb * (math.cos(roll) + roll * math.sin(roll))
            y_inv = rb * (math.sin(roll) - roll * math.cos(roll))
            x_r = x_inv * math.cos(rotation) - y_inv * math.sin(rotation)
            y_r = x_inv * math.sin(rotation) + y_inv * math.cos(rotation)
            right_pts.append(App.Vector(x_r, y_r, 0))

        # Left involute = mirror of right about tooth centre line
        mirror_angle = base_angle + math.pi / 2.0
        left_pts = []
        for p in right_pts:
            dx = p.x; dy = p.y
            ca = math.cos(2 * mirror_angle); sa = math.sin(2 * mirror_angle)
            left_pts.append(App.Vector(dx * ca + dy * sa, dx * sa - dy * ca, 0))
        left_pts.reverse()

        # --- Right involute flank (root → tip) ---
        bsp_r = Part.BSplineCurve()
        bsp_r.interpolate(right_pts)
        edges.append(("right_inv", bsp_r.toShape()))

        # --- Tip arc (right tip → left tip) ---
        p_tip_r = right_pts[-1]
        p_tip_l = left_pts[0]
        a_r = math.atan2(p_tip_r.y, p_tip_r.x)
        a_l = math.atan2(p_tip_l.y, p_tip_l.x)
        if a_l < a_r:
            a_l += 2.0 * math.pi
        mid_tip = (a_r + a_l) / 2.0
        tip_mid_pt = App.Vector(ra * math.cos(mid_tip), ra * math.sin(mid_tip), 0)
        tip_arc = Part.Arc(p_tip_r, tip_mid_pt, p_tip_l)
        edges.append(("tip_arc", tip_arc.toShape()))

        # --- Left involute flank (tip → root) ---
        bsp_l = Part.BSplineCurve()
        bsp_l.interpolate(left_pts)
        edges.append(("left_inv", bsp_l.toShape()))

        # --- Root arc to next tooth ---
        p_root_l = left_pts[-1]
        # Compute root point of next tooth's right involute
        next_i = (t_i + 1) % num_teeth
        next_base = next_i * tooth_angle
        next_rot = next_base + math.pi / 2.0 - theta_base
        nr_start_r = start_r
        if nr_start_r <= rb:
            nr_roll = 0
        else:
            nr_phi = math.acos(min(rb / nr_start_r, 1.0))
            nr_roll = math.tan(nr_phi)
        nx = rb * (math.cos(nr_roll) + nr_roll * math.sin(nr_roll))
        ny = rb * (math.sin(nr_roll) - nr_roll * math.cos(nr_roll))
        p_root_next = App.Vector(
            nx * math.cos(next_rot) - ny * math.sin(next_rot),
            nx * math.sin(next_rot) + ny * math.cos(next_rot), 0)

        a_rl = math.atan2(p_root_l.y, p_root_l.x)
        a_rn = math.atan2(p_root_next.y, p_root_next.x)
        # Ensure we go the short way around through the root
        if a_rn <= a_rl:
            a_rn += 2.0 * math.pi
        mid_root = (a_rl + a_rn) / 2.0
        root_mid_pt = App.Vector(rf * math.cos(mid_root), rf * math.sin(mid_root), 0)
        root_arc = Part.Arc(p_root_l, root_mid_pt, p_root_next)
        edges.append(("root_arc", root_arc.toShape()))

    # Collect just the edge shapes in order
    edge_shapes = [e[1] for e in edges]
    sorted_edges = Part.sortEdges(edge_shapes)
    wire = Part.Wire(sorted_edges[0])
    return wire, gp_r, ra, rf


# ============================================================================
# RESULT (proxy object)
# ============================================================================

class GloboidWormGearV3Result:
    def __init__(self, obj, varset):
        self._varset = varset; self._rebuilding = False
        self._last_m = self._last_nt = self._last_gt = self._last_pa = None
        self._last_wpd = self._last_sd = self._last_sl = self._last_wl = None
        self._last_rh = self._last_cm = self._last_gh = self._last_cl = None
        self._last_gbd = self._last_gbe = self._last_wp = None
        self._last_bl = None
        self._watcher = None; self._needs_rebuild = False
        self.Type = "GloboidWormGearV3Result"
        obj.addProperty("App::PropertyString", "VarSetName", "Gear", "", 1).VarSetName = varset.Name
        obj.addProperty("App::PropertyString", "BodyName", "Gear", "").BodyName = varset.Name.replace("_values", "_Body", 1)
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
            self._startWatcher(v.Name); obj.Status = "Up to date"

    def _startWatcher(self, vn):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(self, vn, watched=frozenset((
            "Module", "NumberOfThreads", "GearTeeth", "PressureAngle", "WormPitchDiameter",
            "ShaftDiameter", "ShaftLength", "WormLength", "RightHanded", "CreateMatingGear",
            "GearHeight", "Clearance", "GearBoreEnabled", "GearBoreDiameter", "WheelPhase",
            "BoreEnabled", "KeywayEnabled", "BoreDiameter", "KeywayWidth", "KeywayDepth", "Backlash")))
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
                    (hasattr(v, "Backlash") and abs(float(v.Backlash) - self._last_bl) > E))
        except ReferenceError:
            self._varset = None; return False

    def _set_needs_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._needs_rebuild = True
        try: self.Object.Status = "Regenerating..."
        except: pass
        QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding: return
        if not self._values_changed(): self._needs_rebuild = False; return
        self._needs_rebuild = False; QtCore.QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed(): return
        self._rebuild()

    # -----------------------------------------------------------------------
    # Core rebuild — boolean conjugate approach (parametric PartDesign tree)
    # -----------------------------------------------------------------------
    def _rebuild(self):
        self._rebuilding = True; vn = None
        try:
            v = self._getVarSet()
            if not v: return
            vn = v.Name; bn = str(self.Object.BodyName); d = self.Object.Document

            # Cache all parameter values
            self._last_m = float(v.Module.Value); self._last_nt = int(v.NumberOfThreads)
            self._last_gt = int(v.GearTeeth); self._last_pa = float(v.PressureAngle.Value)
            self._last_wpd = float(v.WormPitchDiameter.Value)
            self._last_sd = float(v.ShaftDiameter.Value); self._last_sl = float(v.ShaftLength.Value)
            self._last_wl = float(v.WormLength.Value); self._last_rh = bool(v.RightHanded)
            self._last_cm = bool(v.CreateMatingGear); self._last_gh = float(v.GearHeight.Value)
            self._last_cl = float(v.Clearance); self._last_gbe = bool(v.GearBoreEnabled)
            self._last_gbd = float(v.GearBoreDiameter.Value); self._last_wp = float(v.WheelPhase.Value)
            self._last_bl = float(v.Backlash) if hasattr(v, "Backlash") else 0.0

            if self._last_m <= 0: self.Object.Status = "Invalid params"; return

            self._stopWatcher()

            # Remove old objects if they exist
            saved_placement = None
            old = d.getObject(bn)
            if old:
                saved_placement = App.Placement(old.Placement)
                ch = list(old.Group)
                for c in ch:
                    for p in c.PropertiesList:
                        try: c.setExpression(p, None)
                        except: pass
                for c in reversed(ch):
                    try: d.removeObject(c.Name)
                    except: pass
                d.removeObject(bn)

            # Remove old torus and Part::Cut
            for suffix in ["_BooleanCut", "_SmoothTorus", "_ToothTorus"]:
                tn = f"{bn}{suffix}"
                old_t = d.getObject(tn)
                if old_t:
                    if hasattr(old_t, 'removeObjectsFromDocument'):
                        old_t.removeObjectsFromDocument()
                    try: d.removeObject(tn)
                    except: pass

            # Remove old wheel
            gbn = f"{bn}_WormWheel"
            saved_wheel_placement = None
            old_wheel = d.getObject(gbn)
            if old_wheel:
                saved_wheel_placement = App.Placement(old_wheel.Placement)
                if hasattr(old_wheel, 'removeObjectsFromDocument'):
                    old_wheel.removeObjectsFromDocument()
                try: d.removeObject(gbn)
                except: pass

            self.Object.Status = "Generating..."
            if App.GuiUp: QtCore.QCoreApplication.processEvents()

            # === Parameters ===
            m = self._last_m; nt = self._last_nt; pa = self._last_pa
            gt = self._last_gt; rh = self._last_rh
            wp_dia = self._last_wpd

            wp_r = wp_dia / 2.0
            gp_r = m * gt / 2.0
            cd = gp_r + wp_r
            add = m; ded = m * 1.25
            cyl_r = cd

            # ===========================================================
            # STEP 1: Toothed Torus (gear-ring slices tiled around torus)
            #   Replaces the smooth torus with a toothed version so the
            #   boolean cut carves actual thread grooves into the worm.
            # ===========================================================

            torus_name = f"{bn}_ToothTorus"
            torus_obj = d.addObject("Part::Feature", torus_name)
            torus_obj.Shape = self._build_toothed_torus()
            torus_obj.Visibility = False
            d.recompute()

            # ===========================================================
            # STEP 2: Cylinder Blank — PartDesign::Body with Sketch + Pad
            #   One circle sketch at origin, padded symmetrically.
            # ===========================================================

            body = util.readyPart(d, bn)

            # Circle sketch on XY plane (axis = Z)
            sk_cyl = util.createSketch(body, "CylinderProfile")
            xy = None
            if hasattr(body, 'Origin') and body.Origin:
                for f in body.Origin.OriginFeatures:
                    if 'XY' in f.Name or 'XY' in f.Label: xy = f; break
                if not xy and len(body.Origin.OriginFeatures) > 0:
                    xy = body.Origin.OriginFeatures[0]
            if xy:
                sk_cyl.AttachmentSupport = [(xy, '')]
                sk_cyl.MapMode = 'FlatFace'
            else:
                sk_cyl.MapMode = 'Deactivated'
                sk_cyl.Placement = App.Placement(
                    App.Vector(0, 0, 0), App.Rotation(App.Vector(1, 0, 0), 0))

            ci = sk_cyl.addGeometry(
                Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), cyl_r), False)
            sk_cyl.addConstraint(Sketcher.Constraint("Coincident", ci, 3, -1, 1))
            sk_cyl.addConstraint(Sketcher.Constraint("Radius", ci, cyl_r))
            d.recompute()

            # Pad symmetrically
            pad = body.newObject("PartDesign::Pad", "CylinderPad")
            pad.Profile = sk_cyl
            pad.Type = 0
            pad.Length = self._last_wl
            pad.SideType = 2
            body.Tip = pad
            d.recompute()

            # ===========================================================
            # STEP 3: Boolean Cut — Part::Cut (visible in tree)
            #   Subtracts the smooth torus from the cylinder body.
            # ===========================================================

            cut_name = f"{bn}_BooleanCut"
            bool_cut = d.addObject("Part::Cut", cut_name)
            bool_cut.Base = body
            bool_cut.Tool = torus_obj
            d.recompute()

            # Hide inputs — only the boolean result is shown
            body.Visibility = False
            torus_obj.Visibility = False

            # Restore placement
            if saved_placement is not None:
                bool_cut.Placement = saved_placement

            # ===========================================================
            # STEP 4: Mating gear
            # ===========================================================

            if self._last_cm:
                self._make_wheel(d, bn, wp_r)
                if saved_wheel_placement is not None:
                    wb = d.getObject(gbn)
                    if wb: wb.Placement = saved_wheel_placement

            self.Object.Status = "Up to date"
            if App.GuiUp: QtCore.QCoreApplication.processEvents()

        except Exception:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            for name in [f"{bn}_BooleanCut", f"{bn}_ToothTorus", bn]:
                try:
                    obj = d.getObject(name)
                    if obj:
                        if hasattr(obj, 'removeObjectsFromDocument'):
                            obj.removeObjectsFromDocument()
                        d.removeObject(name)
                except: pass
            self.Object.Status = "Error"
        finally:
            if vn: self._startWatcher(vn)
            self._rebuilding = False

    # -----------------------------------------------------------------------
    # Mating wheel (same approach as V2)
    # -----------------------------------------------------------------------
    def _make_wheel(self, doc, body_name, worm_pitch_r):
        """Generate the mating worm wheel (throated helical gear)."""
        v = self._getVarSet()
        if not v: return
        module = self._last_m; num_teeth = self._last_gt; height = self._last_gh
        pa = self._last_pa; nt = self._last_nt; rh = self._last_rh; cl = self._last_cl

        cd = self._last_wpd / 2 + module * num_teeth / 2
        wheel_phase = self._last_wp
        gb_dia = self._last_gbd; gb_en = self._last_gbe

        gbn = f"{body_name}_WormWheel"
        gb = util.readyPart(doc, gbn)

        ded = module * 1.25; add = module * 1.0
        gp_r = module * num_teeth / 2
        wr = worm_pitch_r

        # Helical twist matching worm lead angle
        pitch = math.pi * module; lead = pitch * nt
        lead_rad = math.atan(lead / (math.pi * worm_pitch_r * 2))
        twist_rad = height * math.tan(lead_rad) / gp_r
        twist_deg = twist_rad / math.pi * 180
        if rh: twist_deg = -twist_deg

        # Tooth profiles (bottom and top with twist)
        _bl = float(v.Backlash) if hasattr(v, "Backlash") else 0.0
        _ps = -_bl if _bl != 0.0 else 0.0

        sk_b = util.createSketch(gb, "ToothProfileBottom")
        xy = None
        for f in gb.Origin.OriginFeatures:
            if 'XY' in f.Name or 'XY' in f.Label: xy = f; break
        if xy:
            sk_b.AttachmentSupport = [(xy, '')]; sk_b.MapMode = "FlatFace"
            sk_b.AttachmentOffset = App.Placement(
                App.Vector(0, 0, 0), App.Rotation(App.Vector(0, 0, 1), wheel_phase))
        gearMath.generateToothProfile(sk_b, {"module": module, "num_teeth": num_teeth,
            "pressure_angle": pa, "profile_shift": _ps})

        sk_t = util.createSketch(gb, "ToothProfileTop")
        if xy:
            sk_t.AttachmentSupport = [(xy, '')]; sk_t.MapMode = "FlatFace"
            sk_t.AttachmentOffset = App.Placement(
                App.Vector(0, 0, height),
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

        # Gear body (dedendum cylinder)
        df = (gp_r - ded) * 2
        ds = util.createSketch(gb, "DedendumCircle")
        ci = ds.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2), False)
        ds.addConstraint(Sketcher.Constraint("Diameter", ci, df))
        dp = util.createPad(gb, ds, height, "DedendumPad")
        gb.Tip = dp

        doc.recompute()

        # Throat groove (concave waist matching the worm)
        sk_th = gb.newObject("Sketcher::SketchObject", "ThroatCutSketch")
        xz = None
        for f in gb.Origin.OriginFeatures:
            if 'XZ' in f.Name or 'XZ' in f.Label: xz = f; break
        if xz:
            sk_th.AttachmentSupport = [(xz, '')]; sk_th.MapMode = "ObjectXY"
            sk_th.AttachmentOffset = App.Placement(
                App.Vector(0, height / 2, 0), App.Rotation())

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
        gb.Placement = App.Placement(App.Vector(place_cd, height / 2, 0), r_align)

    def _build_toothed_torus(self):
        """Build a toothed torus by tiling gear-ring slices around the torus path.

        Each slice is an extruded gear cross-section placed and rotated so that
        the teeth form a continuous helical thread when fused together.
        Returns a Part.Shape (fused solid or compound).
        """
        import time
        t0 = time.time()
        log = App.Console.PrintMessage

        m = self._last_m
        gt = self._last_gt
        pa = self._last_pa
        nt = self._last_nt
        rh = self._last_rh
        bl = self._last_bl

        wp_r = self._last_wpd / 2.0
        gp_r = m * gt / 2.0
        cd = gp_r + wp_r
        add = m

        num_slices = 36
        slice_height = 2.0 * math.pi * cd / num_slices * 1.1
        delta = 360.0 / num_slices

        log(f"[GloboidV3] _build_toothed_torus: m={m} gt={gt} nt={nt} cd={cd:.2f} slices={num_slices}\n")

        # Build gear cross-section shape
        ps = -bl if bl != 0.0 else 0.0
        log(f"[GloboidV3]   building tooth ring wire...\n")
        wire, _pr, _ra, _rf = _build_tooth_ring_wire(m, gt, pa, ps)
        log(f"[GloboidV3]   wire done ({time.time()-t0:.2f}s), making face...\n")
        face = Part.Face(wire)
        log(f"[GloboidV3]   face done ({time.time()-t0:.2f}s), extruding (h={slice_height:.2f})...\n")
        solid = face.extrude(App.Vector(0, 0, slice_height))
        # Centre at Z=0
        solid.translate(App.Vector(0, 0, -slice_height / 2.0))
        log(f"[GloboidV3]   base solid done ({time.time()-t0:.2f}s)\n")

        gui_up = App.GuiUp

        shapes = []
        for i in range(num_slices):
            theta = i * delta  # degrees, position on torus
            phase = theta * nt / gt  # tooth rotation for spiral continuity
            if rh:
                phase = -phase

            # Build combined transformation matrix:
            # 1. Rotate by phase around Z (tooth alignment)
            # 2. Rotate 90° around Y (orient from Z-pointing to radial)
            # 3. Translate to (cd, 0, 0)
            # 4. Rotate by theta around Z (angular position on torus)
            rot_phase = App.Rotation(App.Vector(0, 0, 1), phase)
            rot_orient = App.Rotation(App.Vector(1, 0, 0), 90)
            rot_theta = App.Rotation(App.Vector(0, 0, 1), theta)

            m_phase = App.Placement(App.Vector(0, 0, 0), rot_phase).toMatrix()
            m_orient = App.Placement(App.Vector(0, 0, 0), rot_orient).toMatrix()
            m_translate = App.Placement(App.Vector(cd, 0, 0), App.Rotation()).toMatrix()
            m_theta = App.Placement(App.Vector(0, 0, 0), rot_theta).toMatrix()

            mat = m_theta.multiply(m_translate).multiply(m_orient).multiply(m_phase)

            s = solid.copy()
            s = s.transformShape(mat)
            shapes.append(s)

            if i % 6 == 0:
                log(f"[GloboidV3]   slice {i+1}/{num_slices} placed ({time.time()-t0:.2f}s)\n")
                if gui_up:
                    self.Object.Status = f"Building toothed torus… slice {i+1}/{num_slices}"
                    QtCore.QCoreApplication.processEvents()

        log(f"[GloboidV3]   all {num_slices} slices placed ({time.time()-t0:.2f}s), pairwise fusing...\n")

        # Pairwise (binary-tree) fusion: fuse pairs at each level so each
        # individual fuse operates on two shapes of similar complexity.
        # 36 → 18 → 9 → 5 → 3 → 2 → 1  (6 rounds, max 18 fuses per round)
        level = 0
        pool = shapes
        while len(pool) > 1:
            level += 1
            next_pool = []
            for j in range(0, len(pool), 2):
                if j + 1 < len(pool):
                    try:
                        fused = pool[j].fuse(pool[j + 1])
                    except Exception:
                        fused = Part.makeCompound([pool[j], pool[j + 1]])
                    next_pool.append(fused)
                else:
                    next_pool.append(pool[j])  # odd one out
            log(f"[GloboidV3]   fuse level {level}: {len(pool)}→{len(next_pool)} ({time.time()-t0:.2f}s)\n")
            if gui_up:
                self.Object.Status = f"Fusing toothed torus… level {level} ({len(next_pool)} shapes)"
                QtCore.QCoreApplication.processEvents()
            pool = next_pool

        result = pool[0]
        log(f"[GloboidV3]   pairwise fusion done ({time.time()-t0:.2f}s)\n")

        log(f"[GloboidV3] _build_toothed_torus complete ({time.time()-t0:.2f}s)\n")
        return result

    def force_Recompute(self): self._rebuild()


# ============================================================================
# COMMAND
# ============================================================================

class GloboidWormGearV3Command:
    def GetResources(self):
        return {"Pixmap": mainIcon,
                "MenuText": "Create Globoid Worm Gear V3",
                "ToolTip": "Create globoid worm gear (boolean conjugate approach)"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc = App.ActiveDocument
        base = "GloboidWormV3_values"; un = base; c = 1
        while doc.getObject(un): un = f"{base}{c:03d}"; c += 1
        vs = createGloboidWormGearV3VarSet(doc, un)
        gn = "Regenerate"; c = 1
        while doc.getObject(gn): gn = f"Regenerate{c:03d}"; c += 1
        go = doc.addObject("Part::FeaturePython", gn)
        GloboidWormGearV3Result(go, vs)
        ViewProviderGearResult(go.ViewObject, mainIcon)
        go.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewFront()

    def IsActive(self): return True


FreeCADGui.addCommand("GloboidWormGearV3Command", GloboidWormGearV3Command())
