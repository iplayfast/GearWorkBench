"""
Globoid Worm Gear — Direct Toroidal-Spiral Construction
=======================================================

Builds the worm thread DIRECTLY from its closed-form parametric equations —
the toroidal-spiral model used by the OTVINTA globoid calculator
(https://www.otvinta.com/globoid.html).

A globoid worm thread is a helix wrapped on an hourglass surface whose axis is
the worm axis (Z) and whose throat radius follows an arc around the mating
wheel.  The thread groove for the whole worm is bounded by four such spirals —
the two flanks at the tooth tip and the two at the root.  Because the OTVINTA
tooth has straight flanks, each flank is EXACTLY a ruled surface between two of
those four curves, so the whole thread is 4 ruled faces + 2 end caps, sewn into
a solid.  This needs no profile-sweep along a 3D path (which FreeCAD/OCCT does
not do reliably) and no boolean chain.

Construction per rebuild:
    1. four boundary B-spline curves               (tip/root x top/bottom flank)
    2. four ruled side faces + two triangulated caps -> sewn solid thread
    3. (multi-start) nt copies of the thread, rotated 360/nt about Z, fused
    4. hourglass core: revolve the root meridian about Z
    5. fuse core + thread, add shaft stubs, cut the bore

The shape is rebuilt with the Part API inside the VarSet-driven proxy: it is
"parametric" in the operative sense — any VarSet edit regenerates the worm —
even though the result is a computed solid rather than a tree of GUI features.
That tree-of-features route is exactly what the 3D-loft limitation forbids for
this geometry.

NOTE: This builds the WORM only.  The matching wheel is the next phase (the
full-height worm surface is itself the correct generating tool for it).
"""

import FreeCAD as App
import FreeCADGui
import gearMath          # helical gear profile + workbench icon directory
import util              # readyPart / createSketch / createPad / createPolar
import Part
import Sketcher
import os
import math
from PySide import QtCore
from genericGear import _VarSetWatcher, ViewProviderGearResult

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
mainIcon = os.path.join(smWB_icons_path, "globoidWormGear.svg")
version = "2.0.0"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VARSET
# ============================================================================

def createGloboidWormGearVarSet(doc, name):
    vs = doc.addObject("App::VarSet", name)

    vs.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version

    # --- Worm ---------------------------------------------------------------
    vs.addProperty("App::PropertyLength", "Module", "Worm", "Module").Module = 3.0
    vs.addProperty("App::PropertyInteger", "NumberOfThreads", "Worm",
        "Thread starts (1 = single-start)").NumberOfThreads = 1
    vs.addProperty("App::PropertyInteger", "GearTeeth", "Worm",
        "Total teeth of the mating wheel").GearTeeth = 20
    vs.addProperty("App::PropertyInteger", "TeethInArc", "Worm",
        "Teeth the worm wraps (sets wrap arc & length): arc = 360*TeethInArc/GearTeeth"
        ).TeethInArc = 5
    vs.addProperty("App::PropertyAngle", "PressureAngle", "Worm",
        "Pressure angle").PressureAngle = 20.0
    vs.addProperty("App::PropertyLength", "WormPitchDiameter", "Worm",
        "Pitch diameter at the throat (>= 4*Module)").WormPitchDiameter = 30.0
    vs.addProperty("App::PropertyBool", "RightHanded", "Worm",
        "Right-handed thread").RightHanded = True
    vs.addProperty("App::PropertyFloat", "Backlash", "Worm",
        QT_TRANSLATE_NOOP("App::Property", "Flank thinning per side (mm)")).Backlash = 0.25

    # --- Shaft / Bore -------------------------------------------------------
    vs.addProperty("App::PropertyLength", "ShaftDiameter", "ShaftBore",
        "End shaft diameter").ShaftDiameter = 12.0
    vs.addProperty("App::PropertyLength", "ShaftLength", "ShaftBore",
        "End shaft length each side").ShaftLength = 8.0
    vs.addProperty("App::PropertyBool", "BoreEnabled", "ShaftBore",
        "Cut an axial bore").BoreEnabled = True
    vs.addProperty("App::PropertyLength", "BoreDiameter", "ShaftBore",
        "Bore diameter").BoreDiameter = 5.0

    # --- Quality ------------------------------------------------------------
    vs.addProperty("App::PropertyInteger", "Samples", "Quality",
        "Points sampled along each boundary curve (smoothness vs speed)").Samples = 200

    # --- Mating wheel -------------------------------------------------------
    vs.addProperty("App::PropertyBool", "CreateMatingGear", "Wheel",
        "Build the mating wheel").CreateMatingGear = True
    vs.addProperty("App::PropertyLength", "GearHeight", "Wheel",
        "Wheel face width").GearHeight = 10.0
    vs.addProperty("App::PropertyAngle", "WheelPhase", "Wheel",
        "Wheel angular phase offset for tooth alignment").WheelPhase = 2.0
    vs.addProperty("App::PropertyFloat", "Clearance", "Wheel",
        "Throat clearance factor (x module)").Clearance = 0.1
    vs.addProperty("App::PropertyBool", "WheelBoreEnabled", "Wheel",
        "Cut a wheel bore").WheelBoreEnabled = True
    vs.addProperty("App::PropertyLength", "WheelBoreDiameter", "Wheel",
        "Wheel bore diameter").WheelBoreDiameter = 8.0

    # --- Read-only derived --------------------------------------------------
    vs.addProperty("App::PropertyLength", "CenterDistance", "read only", "", 1)
    vs.setExpression("CenterDistance", "WormPitchDiameter/2 + Module*GearTeeth/2")
    vs.addProperty("App::PropertyLength", "WheelPitchDiameter", "read only", "", 1)
    vs.setExpression("WheelPitchDiameter", "Module*GearTeeth")
    vs.addProperty("App::PropertyAngle", "ArcAngle", "read only", "", 1)
    vs.setExpression("ArcAngle", "360 * TeethInArc / GearTeeth")
    vs.addProperty("App::PropertyAngle", "LeadAngle", "read only", "", 1)
    vs.setExpression("LeadAngle",
        "atan(Module*NumberOfThreads/WormPitchDiameter)")

    return vs


# ============================================================================
# RESULT OBJECT
# ============================================================================

class GloboidWormGearResult:
    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._last = None            # snapshot tuple of watched params
        self._watcher = None
        self._needs_rebuild = False
        self._debounce_timer = None
        self.Type = "GloboidWormGearResult"
        obj.addProperty("App::PropertyString", "VarSetName", "Gear", "", 1).VarSetName = varset.Name
        obj.addProperty("App::PropertyString", "Version", "read only", "", 1).Version = version
        obj.addProperty("App::PropertyString", "Status", "read only", "")
        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._startWatcher(varset.Name)

    # --- persistence --------------------------------------------------------
    def __getstate__(self):
        return self.Type

    def __setstate__(self, s):
        if s:
            self.Type = s
        self._varset = None
        self._rebuilding = False
        self._last = None
        self._watcher = None
        self._needs_rebuild = False
        self._debounce_timer = None

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._last = self._snapshot(v)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    # --- watcher / debounce (same machinery as V1) --------------------------
    def _startWatcher(self, vn):
        self._stopWatcher()
        self._watcher = _VarSetWatcher(self, vn, watched=frozenset((
            "Module", "NumberOfThreads", "GearTeeth", "TeethInArc",
            "PressureAngle", "WormPitchDiameter", "RightHanded", "Backlash",
            "ShaftDiameter", "ShaftLength", "BoreEnabled", "BoreDiameter",
            "Samples", "CreateMatingGear", "GearHeight", "WheelPhase",
            "Clearance", "WheelBoreEnabled", "WheelBoreDiameter")))
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try:
                App.removeDocumentObserver(self._watcher)
            except Exception:
                pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is None:
            try:
                self._varset = self.Object.Document.getObject(self.Object.VarSetName)
            except Exception:
                pass
        return self._varset

    def execute(self, obj):
        pass

    def _snapshot(self, v):
        return (float(v.Module.Value), int(v.NumberOfThreads), int(v.GearTeeth),
                int(v.TeethInArc), float(v.PressureAngle.Value),
                float(v.WormPitchDiameter.Value), bool(v.RightHanded),
                float(v.Backlash), float(v.ShaftDiameter.Value),
                float(v.ShaftLength.Value), bool(v.BoreEnabled),
                float(v.BoreDiameter.Value), int(v.Samples),
                bool(v.CreateMatingGear), float(v.GearHeight.Value),
                float(v.WheelPhase.Value), float(v.Clearance),
                bool(v.WheelBoreEnabled), float(v.WheelBoreDiameter.Value))

    def _values_changed(self):
        try:
            v = self._getVarSet()
            if not v:
                return False
            if self._last is None:
                return True
            return self._snapshot(v) != self._last
        except ReferenceError:
            self._varset = None
            return False

    _DEBOUNCE_MS = 800

    def _arm_timer(self):
        if self._debounce_timer is None:
            self._debounce_timer = QtCore.QTimer()
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._deferred_rebuild)
        self._debounce_timer.start(self._DEBOUNCE_MS)

    def _set_needs_rebuild(self):
        if self._rebuilding or not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Waiting for input..."
        except Exception:
            pass
        self._arm_timer()

    def _on_recompute_finished(self):
        if not self._needs_rebuild or self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        self._arm_timer()

    def _deferred_rebuild(self):
        if self._rebuilding or not self._values_changed():
            return
        self._rebuild()

    def force_Recompute(self):
        self._rebuild()

    # -----------------------------------------------------------------------
    # Geometry
    # -----------------------------------------------------------------------
    def _build_worm_shape(self, p):
        """Build and return the worm Part.Solid from a params dict `p`."""
        m   = p["m"];   gt = p["gt"]; nt = p["nt"]; tia = p["tia"]
        wpd = p["wpd"]; pa = p["pa"]; rh = p["rh"];  bl  = p["bl"]
        sd  = p["sd"];  sl = p["sl"]; be = p["be"];  bd  = p["bd"]
        N   = max(40, p["ns"])

        refR = wpd / 2.0
        z = gt
        beta = 360.0 * tia / float(z)
        r = m * z / 2.0
        R = refR + r
        alpha = math.radians(pa)
        fTop = m * (math.pi / 2.0 - 2.0 * math.tan(alpha))
        fBottom = fTop + 2.0 * m * 2.25 * math.tan(alpha)
        fTop = max(0.10, fTop - bl)
        fBottom = max(0.20, fBottom - bl)
        tipR = r - m
        rootR = r + 1.25 * m
        fDelta1 = math.atan(fTop / 2.0 / (r - m))
        fDelta2 = math.atan(fBottom / 2.0 / (r + 1.25 * m))
        angleCoef = 360.0 / beta
        hand = 1.0 if rh else -1.0
        z_end = rootR * math.sin(math.radians(beta / 2.0))

        App.Console.PrintMessage(
            "[GloboidWorm] arc=%.2f deg  R=%.2f  tip/root@waist=%.2f/%.2f  "
            "length~%.2f  starts=%d  N=%d\n"
            % (beta, R, R - tipR, R - rootR, 2 * z_end, nt, N))

        def vec(radius, delta, u):
            a = u * math.pi / angleCoef + delta
            d = R - radius * math.cos(a)
            th = hand * u * math.pi * tia
            return App.Vector(-d * math.cos(th), -d * math.sin(th), -radius * math.sin(a))

        us = [-1.0 + 2.0 * i / N for i in range(N + 1)]

        # Thread solid.  makeLoft over CLOSED quad cross-sections (one per u)
        # gives us both fixes at once: the sections are paired explicitly so
        # there is no parametrization skew (no crest indent), AND ThruSections
        # returns a properly closed, correctly-oriented solid so the core
        # fuses (the manual face-sew was producing an inside-out shell, which
        # is why the body vanished).  ruled=True => straight transitions,
        # matching the OTVINTA straight-flank tooth.
        def section(u):
            q = [vec(tipR,  -fDelta1, u),
                 vec(rootR, -fDelta2, u),
                 vec(rootR, +fDelta2, u),
                 vec(tipR,  +fDelta1, u)]
            return Part.makePolygon(q + [q[0]])

        wires = [section(u) for u in us]

        try:
            thread = Part.makeLoft(wires, True, True)   # solid=True, ruled=True
        except Exception as e:
            App.Console.PrintWarning(
                "[GloboidWorm] makeLoft failed (%s); using ruled-surface fallback\n" % e)

            def edge(radius, delta):
                c = Part.BSplineCurve()
                c.interpolate([vec(radius, delta, u) for u in us])
                return c.toShape()

            e_tt = edge(tipR,  -fDelta1)
            e_rt = edge(rootR, -fDelta2)
            e_rb = edge(rootR, +fDelta2)
            e_tb = edge(tipR,  +fDelta1)
            faces = []
            for a_e, b_e in ((e_tt, e_rt), (e_rt, e_rb), (e_rb, e_tb), (e_tb, e_tt)):
                faces.extend(Part.makeRuledSurface(a_e, b_e).Faces)

            def cap(u):
                p0 = vec(tipR,  -fDelta1, u)
                p1 = vec(rootR, -fDelta2, u)
                p2 = vec(rootR, +fDelta2, u)
                p3 = vec(tipR,  +fDelta1, u)
                return [Part.Face(Part.makePolygon([p0, p1, p2, p0])),
                        Part.Face(Part.makePolygon([p0, p2, p3, p0]))]

            faces += cap(us[0]) + cap(us[-1])
            shell = Part.makeShell(faces)
            try:
                shell.sewShape()
            except Exception:
                pass
            thread = Part.makeSolid(shell)

        try:
            thread = thread.removeSplitter()
        except Exception:
            pass
        App.Console.PrintMessage(
            "[GloboidWorm] thread valid=%s vol=%.1f\n" % (thread.isValid(), thread.Volume))

        # Multi-start: nt identical threads equally spaced around Z.
        if nt > 1:
            combined = thread
            for k in range(1, nt):
                c = thread.copy()
                c.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), k * 360.0 / nt)
                combined = combined.fuse(c)
            thread = combined

        # Hourglass core: revolve the root meridian (slightly oversized so the
        # thread root embeds for a clean fuse) about the worm axis Z.
        M = max(40, N // 4)
        mer = []
        for i in range(M + 1):
            a = math.radians(-beta / 2.0 + beta * i / M)
            rad = (R - rootR * math.cos(a)) + 0.05
            mer.append(App.Vector(rad, 0.0, -rootR * math.sin(a)))
        z_hi = mer[0].z
        z_lo = mer[-1].z
        mer = [App.Vector(0, 0, z_hi)] + mer + [App.Vector(0, 0, z_lo)]
        core_face = Part.Face(Part.makePolygon(mer + [mer[0]]))
        core = core_face.revolve(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 360.0)

        worm = core.fuse(thread)

        # Shaft stubs along Z beyond each end.
        if sl > 1e-6 and sd > 1e-6:
            top = Part.makeCylinder(sd / 2.0, sl, App.Vector(0, 0, z_hi), App.Vector(0, 0, 1))
            bot = Part.makeCylinder(sd / 2.0, sl, App.Vector(0, 0, z_lo), App.Vector(0, 0, -1))
            worm = worm.fuse([top, bot])

        # Axial bore through everything.
        if be and bd > 1e-6:
            ztot = z_hi + sl + 2.0
            bore = Part.makeCylinder(bd / 2.0, 2.0 * ztot,
                                     App.Vector(0, 0, -ztot), App.Vector(0, 0, 1))
            worm = worm.cut(bore)

        try:
            worm = worm.removeSplitter()
        except Exception:
            pass
        return worm

    # -----------------------------------------------------------------------
    # Rebuild
    # -----------------------------------------------------------------------
    def _rebuild(self):
        self._rebuilding = True
        try:
            v = self._getVarSet()
            if not v:
                return
            d = self.Object.Document

            snap = self._snapshot(v)
            self._last = snap
            (m, nt, gt, tia, pa, wpd, rh, bl, sd, sl, be, bd, ns,
             cm, gh, wph, cl, wbe, wbd) = snap

            # Cache the values the wheel builders read off self.
            self._last_m = m; self._last_nt = nt; self._last_gt = gt
            self._last_pa = pa; self._last_wpd = wpd; self._last_rh = rh
            self._last_bl = bl; self._last_gh = gh; self._last_wp = wph
            self._last_cl = cl; self._last_wbe = wbe; self._last_wbd = wbd

            # --- validation -------------------------------------------------
            beta = 360.0 * tia / float(gt) if gt else 999.0
            problems = []
            if m <= 0:
                problems.append("Module must be > 0")
            if gt < 1:
                problems.append("GearTeeth must be >= 1")
            if tia < 1:
                problems.append("TeethInArc must be >= 1")
            if not (0 < beta < 180):
                problems.append("arc 360*TeethInArc/GearTeeth must be < 180 deg")
            if wpd / 2.0 < 2 * m:
                problems.append("WormPitchDiameter/2 must be >= 2*Module")
            if nt < 1:
                problems.append("NumberOfThreads must be >= 1")
            if cm and gh <= 0:
                problems.append("GearHeight must be > 0")
            if problems:
                self.Object.Status = "Invalid: " + "; ".join(problems)
                App.Console.PrintError("[GloboidWorm] " + "; ".join(problems) + "\n")
                return

            self._stopWatcher()
            self.Object.Status = "Building worm..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            # --- cleanup previous result -----------------------------------
            old = d.getObject("GloboidWorm")
            if old:
                try:
                    d.removeObject(old.Name)
                except Exception:
                    pass
            old_w = d.getObject("WormWheel")
            if old_w:
                if hasattr(old_w, "removeObjectsFromDocument"):
                    try:
                        old_w.removeObjectsFromDocument()
                    except Exception:
                        pass
                try:
                    d.removeObject(old_w.Name)
                except Exception:
                    pass

            # --- build worm -------------------------------------------------
            params = dict(m=m, gt=gt, nt=nt, tia=tia, wpd=wpd, pa=pa, rh=rh,
                          bl=bl, sd=sd, sl=sl, be=be, bd=bd, ns=ns)
            shape = self._build_worm_shape(params)

            feat = d.addObject("Part::Feature", "GloboidWorm")
            feat.Shape = shape
            feat.Label = "GloboidWorm"
            feat.Visibility = True

            # --- build mating wheel ----------------------------------------
            if cm:
                self.Object.Status = "Building wheel..."
                if App.GuiUp:
                    QtCore.QCoreApplication.processEvents()
                # Conjugate helix = worm lead angle (the lesson from V1:
                # the wheel helix is NOT free, it must equal the lead angle).
                self._twist_deg = math.degrees(math.atan(m * nt / wpd))
                self._make_wheel_base(d)
                self._finish_wheel(d)

            d.recompute()
            self.Object.Status = ("Up to date" if shape.isValid()
                                  else "Built, but shape is invalid — check console")
            App.Console.PrintMessage("[GloboidWorm] done (valid=%s)\n" % shape.isValid())

        except Exception:
            import traceback
            App.Console.PrintError("[GloboidWorm] rebuild failed:\n" + traceback.format_exc())
            try:
                self.Object.Status = "Error — see report view"
            except Exception:
                pass
        finally:
            self._rebuilding = False
            v = self._getVarSet()
            if v:
                self._startWatcher(v.Name)
    # -----------------------------------------------------------------------
    # Mating wheel  (ported from globoidWormGear.py; helix = lead angle,
    # throat sized to the worm tip radius, no hobbing extension pads)
    # -----------------------------------------------------------------------
    def _make_wheel_base(self, doc):
        """Helical gear body (teeth + dedendum) at the origin."""
        module = self._last_m
        num_teeth = self._last_gt
        height = self._last_gh
        pa = self._last_pa
        rh = self._last_rh
        wheel_phase = self._last_wp
        _ps = -self._last_bl if self._last_bl != 0.0 else 0.0
        ded = module * 1.25
        h2 = height / 2.0
        twist_deg = getattr(self, "_twist_deg", 0.0)

        gb = util.readyPart(doc, "WormWheel")

        if abs(twist_deg) > 1e-9:
            beta_rad = abs(twist_deg) * math.pi / 180.0
            mt = module / math.cos(beta_rad)
            pitch_r_t = mt * num_teeth / 2.0
            total_rot_deg = math.degrees(height * math.tan(beta_rad) / pitch_r_t)
            if rh:
                total_rot_deg = -total_rot_deg
        else:
            total_rot_deg = 0.0
            mt = module

        profile_params = {
            "module": module, "num_teeth": num_teeth,
            "pressure_angle": pa, "profile_shift": _ps,
            "helix_angle": abs(twist_deg),
        }

        xy = None
        for f in gb.Origin.OriginFeatures:
            if "XY" in f.Name or "XY" in f.Label:
                xy = f
                break

        sk_b = util.createSketch(gb, "ToothProfileBottom")
        if xy:
            sk_b.AttachmentSupport = [(xy, "")]
            sk_b.MapMode = "FlatFace"
            sk_b.AttachmentOffset = App.Placement(
                App.Vector(0, 0, -h2),
                App.Rotation(App.Vector(0, 0, 1), wheel_phase))
        gearMath.generateHelicalGearProfile(sk_b, profile_params)

        sk_t = util.createSketch(gb, "ToothProfileTop")
        if xy:
            sk_t.AttachmentSupport = [(xy, "")]
            sk_t.MapMode = "FlatFace"
            sk_t.AttachmentOffset = App.Placement(
                App.Vector(0, 0, h2),
                App.Rotation(App.Vector(0, 0, 1), total_rot_deg + wheel_phase))
        gearMath.generateHelicalGearProfile(sk_t, profile_params)

        App.Console.PrintMessage(
            "[GloboidWorm] wheel helix=%.2f deg (=lead), sketch rot=%.3f deg\n"
            % (twist_deg, total_rot_deg))

        loft = gb.newObject("PartDesign::AdditiveLoft", "ToothLoft")
        loft.Profile = sk_b
        loft.Sections = [sk_t]
        loft.Ruled = True
        gb.Tip = loft

        polar = util.createPolar(gb, loft, sk_b, num_teeth, "Teeth")
        polar.Originals = [loft]
        gb.Tip = polar

        gp_r_t = mt * num_teeth / 2.0
        df = (gp_r_t - ded) * 2
        ds = util.createSketch(gb, "DedendumCircle")
        ci = ds.addGeometry(
            Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2), False)
        ds.addConstraint(Sketcher.Constraint("Diameter", ci, df))
        dp = util.createPad(gb, ds, height, "DedendumPad")
        dp.SideType = 2  # symmetric about midplane
        gb.Tip = dp

        doc.recompute()

    def _finish_wheel(self, doc):
        """Throat groove (sized to clear the worm tips), bore, placement."""
        module = self._last_m
        num_teeth = self._last_gt
        height = self._last_gh
        cl = self._last_cl
        add = module
        ded = module * 1.25
        cd = self._last_wpd / 2.0 + module * num_teeth / 2.0

        gb = doc.getObject("WormWheel")
        if not gb:
            return

        # Throat groove: relieve only the TOP of the wheel teeth (the
        # addendum band) so the teeth stay full and the worm body nests
        # against them.  The groove radius follows the worm PITCH cylinder
        # (wpd/2); using the worm TIP radius cut ~3 mm deeper and shaved the
        # teeth down to stubs.
        worm_pitch_r = self._last_wpd / 2.0
        cut_r = worm_pitch_r + module * cl
        groove_pos = -cd

        sk_th = gb.newObject("Sketcher::SketchObject", "ThroatCutSketch")
        xz = None
        for f in gb.Origin.OriginFeatures:
            if "XZ" in f.Name or "XZ" in f.Label:
                xz = f
                break
        if xz:
            sk_th.AttachmentSupport = [(xz, "")]
            sk_th.MapMode = "ObjectXY"
            sk_th.AttachmentOffset = App.Placement(App.Vector(0, 0, 0), App.Rotation())
        ci = sk_th.addGeometry(
            Part.Circle(App.Vector(groove_pos, 0, 0), App.Vector(0, 0, 1), cut_r), False)
        sk_th.addConstraint(Sketcher.Constraint("PointOnObject", ci, 3, -1))
        sk_th.addConstraint(Sketcher.Constraint("Radius", ci, cut_r))
        sk_th.addConstraint(Sketcher.Constraint("DistanceX", ci, 3, -1, 1, groove_pos))
        sk_th.Visibility = False

        groove = gb.newObject("PartDesign::Groove", "ThroatGroove")
        groove.Profile = sk_th
        groove.ReferenceAxis = (sk_th, ["V_Axis"])
        groove.Angle = 360.0
        gb.Tip = groove

        if self._last_wbe:
            wbd = self._last_wbd
            gbs = util.createSketch(gb, "WheelBore")
            gci = gbs.addGeometry(
                Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), wbd / 2), False)
            gbs.addConstraint(Sketcher.Constraint("Coincident", gci, 3, -1, 1))
            gbs.addConstraint(Sketcher.Constraint("Diameter", gci, wbd))
            gbp = util.createPocket(gb, gbs, height + 10, "WheelBore")
            gbp.Type = 1  # Through All
            gbp.Midplane = True
            gb.Tip = gbp

        doc.recompute()

        # Place beside the worm (worm axis = Z at origin): tilt 90 deg about X
        # so the wheel axis is horizontal, offset to the center distance.
        r_align = App.Rotation(App.Vector(1, 0, 0), 90)
        tip_clearance = ded - add  # 0.25 * module
        place_cd = cd + tip_clearance
        gb.Placement = App.Placement(App.Vector(place_cd, 0, 0), r_align)
        gb.Visibility = True


# ============================================================================
# COMMAND
# ============================================================================

class GloboidWormGearCommand:
    def GetResources(self):
        return {"Pixmap": mainIcon,
                "MenuText": "Create Globoid Worm Gear",
                "ToolTip": "Create globoid worm (direct toroidal-spiral surface)"}

    def Activated(self):
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument
        base = "GloboidWorm_values"; un = base; c = 1
        while doc.getObject(un):
            un = f"{base}{c:03d}"; c += 1
        vs = createGloboidWormGearVarSet(doc, un)
        gn = "Regenerate"; c = 1
        while doc.getObject(gn):
            gn = f"Regenerate{c:03d}"; c += 1
        go = doc.addObject("Part::FeaturePython", gn)
        GloboidWormGearResult(go, vs)
        ViewProviderGearResult(go.ViewObject, mainIcon)
        go.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewFront()

    def IsActive(self):
        return True


FreeCADGui.addCommand("GloboidWormGearCommand", GloboidWormGearCommand())
