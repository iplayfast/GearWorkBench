"""Globoid Worm Gear V2 — clean PartDesign-only builder.

Reference: Otvinta.com Globoid Worm Shaft Calculator
  https://www.otvinta.com/globoid.html
  (local copy: GloboidCalculator/GloboidCalculator.html)

FORMULAS (from Otvinta calculator JavaScript — Calculate()):

  Inputs:
    m  = module
    β  = arc angle (degrees, 0<β<180)
    zβ = gear teeth within the arc
    r  = worm reference (pitch) radius at throat (narrowest point)
    α  = pressure angle (fixed at 20°)

  Derived:
    z_total = 360/β * zβ              # total gear teeth in wheel
    d       = r + m*z_total/2         # center distance (worm axis to gear axis)
    R       = d                       # torus MajorRadius
    r_torus = m*z_total/2 = gp_r     # torus MinorRadius = gear pitch radius

  Thread gap widths (trapezoidal):
    fTop    = m * (π/2 - 2*tan(α))    # gap at tip (narrow, near worm surface)
    fBottom = fTop + 2 * m * 2.25 * tan(α)   # gap at root (wide)
             = m*(π/2 + 2.5*tan(α))
    NOTE: 2.25 = addendum_factor + dedendum_factor = 1.0 + 1.25

  Angular offsets (angular half-width of thread gap in torus V-coordinate):
    δ_tip  = atan((fTop/2)    / (r_torus - m))         # tip gap half-angle
    δ_root = atan((fBottom/2) / (r_torus + 1.25*m))    # root gap half-angle

  Toroidal spiral parametric equations (4 corners of trapezoid):
    Base torus:  x = (R + r_minor*cos(u)) * cos(v)
                 y = (R + r_minor*cos(u)) * sin(v)
                 z = r_minor * sin(u)

    4 edges (minor radii, delta offsets):
      Edge 1 (tip, top):    r_minor = r_torus - m,       offset = -δ_tip
      Edge 2 (tip, bottom): r_minor = r_torus - m,       offset = +δ_tip
      Edge 3 (root, top):   r_minor = r_torus + 1.25*m,  offset = -δ_root
      Edge 4 (root, bottom):r_minor = r_torus + 1.25*m,  offset = +δ_root

    Parameter ranges:
      u ∈ [π - β/2,  π + β/2]    # minor circle arc (β in radians)
      v ∈ [π - π*zβ, π + π*zβ]   # major circle rotation (zβ full turns)

    Each edge: line in (u,v) space from (u_start, v_start+δ) to
    (u_end, v_end+δ), projected onto torus via Geom2d.Line2dSegment.toShape()

  Tooth height falloff (optional):
    r_minor(u) = r_torus - m + (m+1.25*m)*6*(u'²/2 - u'³/3) where u'=u^n
    (Not implemented in this file — all V2/V3 variants use constant-height threads)

  Wheel geometry:
    Gear pitch radius: gp_r = m * z_total / 2
    Lead angle:        γ = atan(m*π*nt / (π * 2*wp_r)) = atan(m*nt / (2*wp_r))
    Wheel twist:       θ = h * tan(γ) / gp_r  (over gear height h)
    Wheel handedness:  opposite to worm (right-handed worm → left-handed wheel)

Design:
1. Hourglass body via PartDesign::Revolution of a circular-arc profile
2. Thread grooves via PartDesign::SubtractivePipe with toroidal-spiral spine
3. Bore & keyway via PartDesign::Pocket
4. Mating wheel as helical gear via AdditiveLoft or AdditiveHelix

Reference image: GloboidCalculator/GloboidCalculator_files/globscheme.png

CHANGE LOG:
  - Fixed u/v parameter swap in Line2dSegment: OpenCASCADE Toroid uses
    (v,u) order in Geom2d, changed from vec2(us,vs) to vec2(vs,us).
  - Fixed fBottom formula: removed extra 'm' factor. add/ded are already in mm,
    so fBottom = fTop + 2*(add+ded)*tan(α), not fTop + 2*m*(add+ded)*tan(α).
  - Fixed profile Y-coordinates: narrow end at -ded (inward/root), wide end at
    +add (outward/surface). Was inverted, causing groove to miss body.
  - Fixed dedendum pad: root diameter (gp_r-ded)*2, not pitch diameter gp_r*2.
  - Fixed SubtractivePipe: Transformation=0 (Constant, single profile),
    Mode=2 (Frenet, profile tracks spine curvature). Was Transformation=1
    (Multisection) + Mode=0 (Standard), causing asymmetric groove flanks.
  - Fixed Groove.Midplane=True (not .Symmetric which doesn't exist).
  - REVERTED: Moving spine to gp_r (pitch surface) made grooves barely cut.
    Spine stays at arc_r (body surface) with start_pt - N*add offset.
  - Fixed wheel ThroatGroove: set angle to 360° (was ~93° due to engagement
    angle limit). Groove must carve into teeth to shape them around the worm.
  - Fixed ThroatGroove cut_r: removed addendum from radius (wr+m*cl, not
    wr+add+m*cl). Old formula cut past the gear root, destroying teeth.
  - Added tip_clearance (ded-add = 0.25*m) to wheel placement distance.
    Compensates for straight-lofted teeth not matching curved worm groove.
  - WheelPhase applied to tooth profile sketches instead of body Placement,
    giving a clean 90°/(1,0,0) Placement rotation.
  - Fixed turns formula: turns = gt*half_angle_rad/(π*nt) (Otvinta's zβ/nt).
    Old formula (eff_wl/lead) treated worm as cylinder, giving ~5 turns
    instead of the correct ~6.67 for the engagement arc.
  - Implemented WormLength: half_angle_rad = asin(wl/2/arc_r) instead of
    hardcoded 60°. Removed dead wl variable. WormLength now controls the
    threaded section length and engagement arc.

REMAINING ISSUES:
  - Profile trapezoid may have narrow/wide ends swapped vs gear convention.
    Current: narrow(fTop) at -ded (inward/root), wide(fBottom) at +add (surface).
    Convention: narrow at surface, wide at root. But current orientation produces
    visible grooves while the "correct" orientation didn't cut properly.
    Root cause unclear — may be related to N direction at spine start point.
  - Threads taper toward the ends due to single-spine sweep vs Otvinta's
    4-edge method where each trapezoid corner traces its own torus.
  - half_angle_rad now derived from WormLength (was hardcoded to 60°).
  - ShaftDiameter VarSet parameter ignored (s_r = outer_throat_r always).
  - Handedness may be inverted vs conventional right-hand rule.
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

vec2 = App.Base.Vector2d

smWBpath = os.path.dirname(gearMath.__file__)
smWB_icons_path = os.path.join(smWBpath, "icons")
mainIcon = os.path.join(smWB_icons_path, "globoidWormGear.svg")
version = "0.2"


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VARSET
# ============================================================================


def createGloboidWormGearV2VarSet(doc, name):
    vs = doc.addObject("App::VarSet", name)
    H = gearMath.generateDefaultParameters()

    vs.addProperty("App::PropertyString","Version","read only","",1).Version = version

    vs.addProperty("App::PropertyInteger","NumberOfThreads","GloboidWorm","Thread starts").NumberOfThreads = 1
    vs.addProperty("App::PropertyLength","Module","GloboidWorm","Module").Module = 2.0
    vs.addProperty("App::PropertyInteger","GearTeeth","GloboidWorm","Mating gear teeth").GearTeeth = 20
    vs.addProperty("App::PropertyAngle","PressureAngle","GloboidWorm","Pressure angle").PressureAngle = 20.0

    vs.addProperty("App::PropertyLength","WormPitchDiameter","GloboidWorm","Pitch diameter at throat").WormPitchDiameter = 30.0
    vs.addProperty("App::PropertyLength","ShaftDiameter","GloboidWorm","End shaft diameter (thin)").ShaftDiameter = 12.0
    vs.addProperty("App::PropertyLength","ShaftLength","GloboidWorm","End shaft length each side").ShaftLength = 8.0
    vs.addProperty("App::PropertyLength","WormLength","GloboidWorm","Threaded section length").WormLength = 30.0
    vs.addProperty("App::PropertyBool","RightHanded","GloboidWorm","Right-handed").RightHanded = True

    vs.addProperty("App::PropertyLength","BoreDiameter","Bore","Bore diameter").BoreDiameter = 5.0
    vs.addProperty("App::PropertyBool","BoreEnabled","Bore","Enable bore").BoreEnabled = True
    vs.addProperty("App::PropertyLength","KeywayWidth","Bore","Keyway width").KeywayWidth = 2.0
    vs.addProperty("App::PropertyLength","KeywayDepth","Bore","Keyway depth").KeywayDepth = 1.0
    vs.addProperty("App::PropertyBool","KeywayEnabled","Bore","Enable keyway").KeywayEnabled = False

    vs.addProperty("App::PropertyBool","CreateMatingGear","MatingGear","Create wheel").CreateMatingGear = True
    vs.addProperty("App::PropertyLength","GearHeight","MatingGear","Wheel thickness").GearHeight = 10.0
    vs.addProperty("App::PropertyFloat","Clearance","MatingGear","Clearance factor").Clearance = 0.1
    vs.addProperty("App::PropertyLength","GearBoreDiameter","MatingGear","Wheel bore diameter").GearBoreDiameter = 8.0
    vs.addProperty("App::PropertyBool","GearBoreEnabled","MatingGear","Enable wheel bore").GearBoreEnabled = True
    vs.addProperty("App::PropertyAngle","WheelPhase","MatingGear","Wheel phase offset").WheelPhase = 2.0

    vs.addProperty("App::PropertyLength","LeadAngle","read only","",1)
    vs.setExpression("LeadAngle","atan(Module*pi*NumberOfThreads/(WormPitchDiameter*pi))")
    vs.addProperty("App::PropertyLength","CenterDistance","read only","",1)
    vs.setExpression("CenterDistance","WormPitchDiameter/2 + Module*GearTeeth/2")
    vs.addProperty("App::PropertyLength","WheelPitchDiameter","read only","",1)
    vs.setExpression("WheelPitchDiameter","Module*GearTeeth")
    return vs


# ============================================================================
# RESULT
# ============================================================================


class GloboidWormGearV2Result:
    def __init__(self, obj, varset):
        self._varset=varset; self._rebuilding=False
        self._last_m=self._last_nt=self._last_gt=self._last_pa=None
        self._last_wpd=self._last_sd=self._last_sl=self._last_wl=None
        self._last_rh=self._last_cm=self._last_gh=self._last_cl=None
        self._last_gbd=self._last_gbe=self._last_wp=None
        self._watcher=None; self._needs_rebuild=False; self.Type="GloboidWormGearV2Result"
        obj.addProperty("App::PropertyString","VarSetName","Gear","",1).VarSetName=varset.Name
        obj.addProperty("App::PropertyString","BodyName","Gear","").BodyName=varset.Name.replace("_values","_Body",1)
        obj.addProperty("App::PropertyString","Version","read only","",1).Version=version
        obj.addProperty("App::PropertyString","Status","read only","",1)
        obj.Proxy=self; self.Object=obj; obj.Status="Not yet generated"
        self._startWatcher(varset.Name)

    def __getstate__(self): return self.Type
    def __setstate__(self,s):
        if s:self.Type=s
        self._varset=None; self._rebuilding=False
        self._last_m=self._last_nt=self._last_gt=self._last_pa=None
        self._last_wpd=self._last_sd=self._last_sl=self._last_wl=None
        self._last_rh=self._last_cm=self._last_gh=self._last_cl=None
        self._last_gbd=self._last_gbe=self._last_wp=None
        self._watcher=None; self._needs_rebuild=False

    def onDocumentRestored(self,obj):
        self.Object=obj; v=self._getVarSet()
        if v:
            for a in ["Module","WormPitchDiameter","ShaftDiameter","ShaftLength","WormLength",
                      "GearHeight","Clearance","GearBoreDiameter","WheelPhase"]:
                setattr(self,f"_last_{a[0].lower()+a[1:]}",float(getattr(v,a).Value))
            self._last_nt=int(v.NumberOfThreads); self._last_gt=int(v.GearTeeth)
            self._last_pa=float(v.PressureAngle.Value)
            self._last_rh=bool(v.RightHanded); self._last_cm=bool(v.CreateMatingGear)
            self._last_gbe=bool(v.GearBoreEnabled)
            self._startWatcher(v.Name); obj.Status="Up to date"

    def _startWatcher(self,vn):
        self._stopWatcher(); self._watcher=_VarSetWatcher(self,vn,watched=frozenset((
            "Module","NumberOfThreads","GearTeeth","PressureAngle","WormPitchDiameter",
            "ShaftDiameter","ShaftLength","WormLength","RightHanded","CreateMatingGear",
            "GearHeight","Clearance","GearBoreEnabled","GearBoreDiameter","WheelPhase",
            "BoreEnabled","KeywayEnabled","BoreDiameter","KeywayWidth","KeywayDepth")))
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
            return (abs(float(v.Module.Value)-self._last_m)>E or
                    int(v.NumberOfThreads)!=self._last_nt or
                    int(v.GearTeeth)!=self._last_gt or
                    abs(float(v.PressureAngle.Value)-self._last_pa)>E or
                    abs(float(v.WormPitchDiameter.Value)-self._last_wpd)>E or
                    abs(float(v.ShaftDiameter.Value)-self._last_sd)>E or
                    abs(float(v.ShaftLength.Value)-self._last_sl)>E or
                    abs(float(v.WormLength.Value)-self._last_wl)>E or
                    bool(v.RightHanded)!=self._last_rh or
                    bool(v.CreateMatingGear)!=self._last_cm or
                    abs(float(v.GearHeight.Value)-self._last_gh)>E or
                    abs(float(v.Clearance)-self._last_cl)>E or
                    bool(v.GearBoreEnabled)!=self._last_gbe or
                    abs(float(v.GearBoreDiameter.Value)-self._last_gbd)>E or
                    abs(float(v.WheelPhase.Value)-self._last_wp)>E)
        except ReferenceError:
            self._varset=None; return False

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

            self._last_m=float(v.Module.Value); self._last_nt=int(v.NumberOfThreads)
            self._last_gt=int(v.GearTeeth); self._last_pa=float(v.PressureAngle.Value)
            self._last_wpd=float(v.WormPitchDiameter.Value)
            self._last_sd=float(v.ShaftDiameter.Value); self._last_sl=float(v.ShaftLength.Value)
            self._last_wl=float(v.WormLength.Value); self._last_rh=bool(v.RightHanded)
            self._last_cm=bool(v.CreateMatingGear); self._last_gh=float(v.GearHeight.Value)
            self._last_cl=float(v.Clearance); self._last_gbe=bool(v.GearBoreEnabled)
            self._last_gbd=float(v.GearBoreDiameter.Value); self._last_wp=float(v.WheelPhase.Value)

            if self._last_m<=0: self.Object.Status="Invalid params"; return

            self._stopWatcher()
            saved_placement=None
            old=d.getObject(bn)
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

            self.Object.Status="Generating..."
            if App.GuiUp: QtCore.QCoreApplication.processEvents()

            # === BUILD WORM ===
            # The globoid worm (double-throated) has an hourglass shape that matches 
            # the curvature of the mating gear's pitch circle.
            m=self._last_m; nt=self._last_nt; pa=self._last_pa
            wp_dia=self._last_wpd; s_dia=self._last_sd; s_len=self._last_sl
            rh=self._last_rh
            gt=self._last_gt

            wp_r=wp_dia/2.0   # Worm pitch radius at the narrowest point (the throat)
            gp_r=m*gt/2.0     # Mating gear pitch radius
            cd=gp_r+wp_r       # Center distance: sum of pitch radii
            add=m; ded=m*1.25 # Standard addendum and dedendum
            
            # The hourglass body is defined by an arc centered at the mating gear's axis.
            # outer_throat_r is the radius from the worm axis to its outer tips at the throat.
            outer_throat_r=wp_r+add
            
            # arc_r is the radius of the circular arc that defines the hourglass "waist".
            # It must be centered at the gear axis (distance 'cd' away).
            arc_r=cd-outer_throat_r

            if arc_r<=0: self.Object.Status="Geometry error"; return

            # arc_r = gp_r - m = cd - outer_throat_r.
            # This is the hourglass arc radius. The spine torus uses arc_r (body surface)
            # rather than Otvinta's gp_r (pitch surface) — see CHANGE LOG for rationale.

            # Derive half_angle_rad from the user's WormLength parameter.
            # The worm length is the chord of the hourglass arc (radius arc_r).
            # half_angle_rad = asin(worm_length/2 / arc_r), clamped to max arc.
            # Matches back/globoidWormGear.py:235 approach.
            max_wl=arc_r*2.0*0.98  # max chord ~98% of diameter
            wl=min(self._last_wl,max_wl) if self._last_wl>0 else max_wl
            half_angle_rad=math.asin(min(wl/2.0/arc_r,1.0))
            eff_wl=2.0*arc_r*math.sin(half_angle_rad)

            body=util.readyPart(d,bn)

            # STEP 1: Create the Hourglass Body (Revolution of a curved profile)
            # We sketch on the XZ plane so the revolution around the V-axis (Z in global) 
            # creates a vertical worm.
            half_cyl=eff_wl/2.0+s_len # Total length including end shafts
            sk_base=util.createSketch(body,"GloboidCylinder")
            xz=None
            if hasattr(body,'Origin') and body.Origin:
                for f in body.Origin.OriginFeatures:
                    if 'XZ' in f.Name or 'XZ' in f.Label: xz=f; break
                if not xz and len(body.Origin.OriginFeatures)>1: xz=body.Origin.OriginFeatures[1]
            if xz: sk_base.AttachmentSupport=[(xz,'')]; sk_base.MapMode='FlatFace'
            else: sk_base.MapMode='Deactivated'; sk_base.Placement=App.Placement(
                App.Vector(0,0,0),App.Rotation(App.Vector(1,0,0),90))

            # WARNING: ShaftDiameter VarSet parameter is IGNORED.
            # s_r is set to outer_throat_r instead of s_dia/2.
            # The ShaftDiameter (default 12mm) is exposed in the UI but has no effect —
            # the end sections are always the same diameter as the throat.
            # This creates a cylindrical body with no necked-down shaft.
            # Compare with back/globoidWormGear.py:252 which uses s_dia/2 for the shaft
            # and a step outward to the thread OD.
            s_r=outer_throat_r

            # Geometric parameters for the hourglass profile sketch
            ha=half_angle_rad; sar=-ha; ear=ha
            hc=half_cyl

            # Calculate start/end points of the waist arc
            arc_top_y=arc_r*math.sin(ear)
            arc_top_x=-cd+arc_r*math.cos(ear)
            arc_bot_y=arc_r*math.sin(sar)
            arc_bot_x=-cd+arc_r*math.cos(sar)

            # Build the profile: end shafts connected to the central waist arc.
            idx_right=0; idx_top=1; idx_tl=2; idx_arc=3; idx_bl=4; idx_bot=5
            geo=[]
            geo.append(Part.LineSegment(App.Vector(0,-hc,0),App.Vector(0,hc,0))) # Axis of revolution
            geo.append(Part.LineSegment(App.Vector(0,hc,0),
                         App.Vector(-s_r,hc,0))) # Top end shaft flat
            geo.append(Part.LineSegment(App.Vector(-s_r,hc,0),
                         App.Vector(arc_top_x,arc_top_y,0))) # Transition to waist
            # The waist arc: centered at (-cd, 0), radius arc_r.
            circ=Part.Circle(App.Vector(-cd,0,0),App.Vector(0,0,1),arc_r)
            geo.append(Part.ArcOfCircle(circ,sar,ear))
            geo.append(Part.LineSegment(App.Vector(arc_bot_x,arc_bot_y,0),
                         App.Vector(-s_r,-hc,0))) # Transition from waist
            geo.append(Part.LineSegment(App.Vector(-s_r,-hc,0),
                         App.Vector(0,-hc,0))) # Bottom end shaft flat
            sk_base.addGeometry(geo,False)

            # Constraints to ensure a watertight profile for the revolution
            sk_base.addConstraint(Sketcher.Constraint("Coincident",idx_right,2,idx_top,1))
            sk_base.addConstraint(Sketcher.Constraint("Coincident",idx_top,2,idx_tl,1))
            sk_base.addConstraint(Sketcher.Constraint("Coincident",idx_tl,2,idx_arc,2))
            sk_base.addConstraint(Sketcher.Constraint("Coincident",idx_arc,1,idx_bl,1))
            sk_base.addConstraint(Sketcher.Constraint("Coincident",idx_bl,2,idx_bot,1))
            sk_base.addConstraint(Sketcher.Constraint("Coincident",idx_bot,2,idx_right,1))
            sk_base.addConstraint(Sketcher.Constraint("Vertical",idx_right))
            sk_base.addConstraint(Sketcher.Constraint("Horizontal",idx_top))
            # idx_tl and idx_bl are transitions and should NOT be vertical.
            sk_base.addConstraint(Sketcher.Constraint("Horizontal",idx_bot))
            sk_base.addConstraint(Sketcher.Constraint("PointOnObject",idx_arc,3,-1))
            sk_base.addConstraint(Sketcher.Constraint("DistanceY",idx_right,1,idx_right,2,2.0*hc))
            sk_base.addConstraint(Sketcher.Constraint("Symmetric",idx_right,1,idx_right,2,-1,1))
            sk_base.addConstraint(Sketcher.Constraint("Radius",idx_arc,arc_r))
            sk_base.addConstraint(Sketcher.Constraint("DistanceX",idx_arc,3,idx_right,1,cd))
            sk_base.addConstraint(Sketcher.Constraint("DistanceY",idx_arc,1,idx_arc,2,2.0*arc_top_y))
            sk_base.addConstraint(Sketcher.Constraint("Vertical",idx_arc,1,idx_arc,2))

            d.recompute()
            if sk_base.Shape.isNull(): self.Object.Status="Sketch failed"; return

            # Revolution creates the hourglass blank
            rev=body.newObject("PartDesign::Revolution","HourglassBody")
            rev.Profile=sk_base
            rev.ReferenceAxis=(sk_base,["V_Axis"])
            rev.Angle=360
            body.Tip=rev
            d.recompute()

            # STEP 2: Create the Thread Grooves
            # We use a SubtractivePipe where the spine is a spiral wrapped onto a toroid.
            # This ensures the thread maintains constant depth relative to the hourglass surface.

            # WARNING: hu_spine uses the hardcoded half_angle_rad (60°), NOT the
            # geometry-derived value needed to cover the full body.
            # Otvinta formula: u_half = β/2 (where β is the arc angle input).
            # The back/globoidWormGear.py computes: hu_spine = asin(half_len/gp_r).
            # With this hardcoded value, the thread groove only covers the arc region
            # of the hourglass and does NOT extend into the shoulder transition zones.
            hu_spine=half_angle_rad

            # Number of thread turns = teeth in engagement arc / thread starts.
            # Otvinta: zβ = gt * β/(2π) = gt * half_angle_rad/π (teeth in arc).
            # For multi-start, each start covers every nt-th tooth.
            # Old formula (eff_wl/lead) treated worm as cylinder — gave ~5 turns
            # instead of ~6.67, producing too few grooves for the engaging teeth.
            turns=gt*half_angle_rad/(math.pi*nt)
            total_v=2.0*math.pi*turns

            # Gap widths from Otvinta formula:
            #   fTop    = m*(π/2 - 2*tan(α))          — narrow end (at worm surface)
            #   fBottom = fTop + 2*(add+ded)*tan(α)    — wide end (at root)
            # add and ded are already in mm, so no extra m factor.
            tan_pa=math.tan(pa*math.pi/180)
            fTop=m*(math.pi/2.0 - 2.0*tan_pa)
            fBottom=fTop + 2.0*(add+ded)*tan_pa

            # Spine torus at the body surface (MinorRadius = arc_r = gp_r - m).
            # The profile is offset inward by 'add' so it cuts from the surface down to root.
            # NOTE: Otvinta uses gp_r (pitch surface) with its 4-edge method, but the
            # single-spine sweep works better with arc_r because the Frenet frame then
            # tracks the body surface curvature directly.
            torus_spine=Part.Toroid()
            torus_spine.MajorRadius=cd
            torus_spine.MinorRadius=arc_r

            # Parametric coordinates (u, v) on the torus.
            # u: Minor rotation (around the hourglass curve), v: Major rotation (around the worm axis).
            us=math.pi-hu_spine; ue=math.pi+hu_spine
            vs=math.pi-total_v/2.0; ve=math.pi+total_v/2.0
            # WARNING: handedness may be inverted vs conventional right-hand rule.
            # For rh=True: v increases (CCW looking from +z) while u increases (z goes + to -).
            # This gives a thread that goes downward with CCW rotation = LEFT-handed.
            # The back/globoidWormGear.py:326 has the same formula.
            # If correct, the fix would be to remove the 'not' so LeftHanded triggers the swap.
            if not rh: vs,ve=-ve+2*math.pi,-vs+2*math.pi

            # Map a 2D line in (u,v) space onto the 3D torus surface to get a toroidal spiral.
            line2d=Part.Geom2d.Line2dSegment(vec2(vs,us),vec2(ve,ue))
            spiral_edge=line2d.toShape(torus_spine)
            if spiral_edge.isNull(): self.Object.Status="Spiral edge null"; return
            spiral_wire=Part.Wire([spiral_edge])

            # Use a SubShapeBinder to bring the spiral spine into the PartDesign Body.
            tmp_name=f"{bn}_TmpSpine"
            old=d.getObject(tmp_name)
            if old: d.removeObject(tmp_name)
            tmp_obj=d.addObject("Part::Feature",tmp_name)
            tmp_obj.Shape=spiral_wire; tmp_obj.Visibility=False
            d.recompute()

            binder=body.newObject("PartDesign::SubShapeBinder","ThreadSpineBinder")
            binder.Support=[(tmp_obj,['Edge1'])]
            binder.Relative=False
            d.recompute()
            d.removeObject(tmp_name)
            d.recompute()

            # Place the profile ON the body surface (no offset) with an initial
            # rotation that aligns sketch Y with the surface normal (radially
            # into the body).  The pipe's Frenet frame (Mode=2) then evolves
            # from this starting orientation along the sweep.
            R_=cd; r_=arc_r; u0=us; v0=vs
            cu=math.cos(u0); su=math.sin(u0)
            cv=math.cos(v0); sv=math.sin(v0)
            Rrc=R_+r_*cu
            start_pt=App.Vector(Rrc*cv,Rrc*sv,r_*su)

            # TNB frame at the start point — initial orientation for the pipe's
            # Frenet evolution.  Y (=groove depth) → surface normal (into body).
            Su=App.Vector(-r_*su*cv,-r_*su*sv,r_*cu)
            Sv=App.Vector(-Rrc*sv,Rrc*cv,0.0)
            T=(Su*(ue-us)+Sv*(ve-vs)).normalize()
            N_surf=Su.cross(Sv).normalize()
            B=T.cross(N_surf).normalize()
            N=B.cross(T)

            rot_a=App.Rotation(App.Vector(0,0,1),T)
            Yi=rot_a.multVec(App.Vector(0,1,0))
            ang=math.atan2(T.dot(Yi.cross(N)),Yi.dot(N))
            rot=App.Rotation(T,ang)*rot_a

            # Trapezoid: narrow at surface (fTop, Y=0), wide at root
            # (fBottom, Y = -(add+ded)).  Y extends into the body.
            hw_n=fTop/2.0; hw_w=fBottom/2.0
            gdepth=add+ded
            gpts=[App.Vector(-hw_n,0,0),App.Vector(+hw_n,0,0),
                  App.Vector(+hw_w,-gdepth,0),App.Vector(-hw_w,-gdepth,0)]
            sk_groove=util.createSketch(body,"ThreadGrooveProfile")
            sk_groove.MapMode="Deactivated"
            sk_groove.Placement=App.Placement(start_pt,rot)
            for i in range(4):
                sk_groove.addGeometry(Part.LineSegment(gpts[i],gpts[(i+1)%4]),False)
            for i in range(4):
                sk_groove.addConstraint(Sketcher.Constraint("Coincident",i,2,(i+1)%4,1))
            sk_groove.addConstraint(Sketcher.Constraint("Symmetric",0,1,0,2,-2,1))

            d.recompute()

            # SubtractivePipe cuts the thread groove along the spiral spine
            spipe=body.newObject("PartDesign::SubtractivePipe","ThreadGroove")
            spipe.Profile=sk_groove
            spipe.Spine=(binder,['Edge1'])
            if hasattr(spipe,'Transformation'): spipe.Transformation=0
            if hasattr(spipe,'Mode'): spipe.Mode=2  # Frenet
            body.Tip=spipe

            # Create multiple starts if NumberOfThreads > 1
            if nt>1:
                polar=util.createPolar(body,spipe,sk_groove,nt,"MultiStart")
                polar.Originals=[spipe]
                body.Tip=polar

            d.recompute()

            # STEP 3: Bore & keyway
            body_len=eff_wl+2.0*s_len+4.0
            bd=float(v.BoreDiameter.Value)
            if bool(v.BoreEnabled):
                bore_sk=util.createSketch(body,"Bore")
                ci=bore_sk.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),bd/2),False)
                bore_sk.addConstraint(Sketcher.Constraint("Coincident",ci,3,-1,1))
                bore_sk.addConstraint(Sketcher.Constraint("Diameter",ci,bd))
                bore_sk.Placement=App.Placement(App.Vector(0,0,body_len/2),App.Rotation())
                bore_sk.MapMode="Deactivated"
                bp=util.createPocket(body,bore_sk,body_len)
                bp.Reversed=True
                body.Tip=bp

                kw=float(v.KeywayWidth.Value); kd=float(v.KeywayDepth.Value)
                if bool(v.KeywayEnabled):
                    tiny=0.01
                    kws=util.createSketch(body,"Keyway")
                    pts=[App.Vector(-0.5,-0.5,0),App.Vector(0.5,-0.5,0),
                         App.Vector(0.5,0.5,0),App.Vector(-0.5,0.5,0)]
                    kls=[]
                    for i in range(4):
                        kls.append(kws.addGeometry(Part.LineSegment(pts[i],pts[(i+1)%4]),False))
                    for i in range(4):
                        kws.addConstraint(Sketcher.Constraint("Coincident",kls[i],2,kls[(i+1)%4],1))
                    kws.addConstraint(Sketcher.Constraint("Horizontal",kls[0]))
                    kws.addConstraint(Sketcher.Constraint("Vertical",kls[1]))
                    kws.addConstraint(Sketcher.Constraint("Horizontal",kls[2]))
                    kws.addConstraint(Sketcher.Constraint("Vertical",kls[3]))
                    kws.addConstraint(Sketcher.Constraint("DistanceX",kls[0],1,-1,1,-kw/2))
                    kws.addConstraint(Sketcher.Constraint("DistanceY",kls[0],1,-1,1,bd/2-kd))
                    c=kws.addConstraint(Sketcher.Constraint("DistanceX",kls[0],2,-1,1,kw/2))
                    c=kws.addConstraint(Sketcher.Constraint("DistanceY",kls[1],2,-1,1,tiny))
                    kws.setExpression(f"Constraints[{c}]",f"{bd/2+kd}")
                    kws.Placement=App.Placement(App.Vector(0,0,body_len/2),App.Rotation())
                    kws.MapMode="Deactivated"
                    kp=util.createPocket(body,kws,body_len)
                    kp.Reversed=True
                    body.Tip=kp

            # Restore worm body placement
            if saved_placement is not None:
                body.Placement=saved_placement

            # STEP 4: Mating gear
            saved_wheel_placement=None
            if self._last_cm:
                gbn=f"{bn}_WormWheel"
                old_wheel=d.getObject(gbn)
                if old_wheel:
                    saved_wheel_placement=App.Placement(old_wheel.Placement)
                self._make_wheel(d,bn,wp_r)
                if saved_wheel_placement is not None:
                    wb=d.getObject(gbn)
                    if wb: wb.Placement=saved_wheel_placement

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

    def _make_wheel(self,doc,body_name,worm_pitch_r):
        """Generate the mating worm wheel (throated helical gear)."""
        v=self._getVarSet()
        if not v: return
        module=self._last_m; num_teeth=self._last_gt; height=self._last_gh
        pa=self._last_pa; nt=self._last_nt; rh=self._last_rh; cl=self._last_cl
        
        # Center Distance must match the worm's pitch radii sum exactly.
        cd=self._last_wpd/2 + module*num_teeth/2
        wheel_phase=self._last_wp
        gb_dia=self._last_gbd; gb_en=self._last_gbe

        gbn=f"{body_name}_WormWheel"
        gb=util.readyPart(doc,gbn)

        ded=module*1.25; add=module*1.0
        gp_r=module*num_teeth/2
        
        # wr is the radius of the worm's pitch circle.
        wr=worm_pitch_r

        # STEP 1: Calculate Helical Twist
        # A worm wheel is essentially a helical gear where the helix angle matches the worm's lead angle.
        pitch=math.pi*module; lead=pitch*nt
        lead_rad=math.atan(lead/(math.pi*worm_pitch_r*2))
        twist_rad=height*math.tan(lead_rad)/gp_r
        twist_deg=twist_rad/math.pi*180
        if rh: twist_deg=-twist_deg

        # STEP 2: Create the Helical Tooth Profile (Loft between base and twisted top)
        # WheelPhase is applied here (rotating tooth profiles) rather than in the
        # body Placement, so the Placement stays a clean 90° around X.
        sk_b=util.createSketch(gb,"ToothProfileBottom")
        xy=None
        for f in gb.Origin.OriginFeatures:
            if 'XY' in f.Name or 'XY' in f.Label: xy=f; break
        if xy:
            sk_b.AttachmentSupport=[(xy,'')]; sk_b.MapMode="FlatFace"
            sk_b.AttachmentOffset=App.Placement(App.Vector(0,0,0),App.Rotation(App.Vector(0,0,1),wheel_phase))
        gearMath.generateToothProfile(sk_b,{"module":module,"num_teeth":num_teeth,
            "pressure_angle":pa,"profile_shift":0.0})

        sk_t=util.createSketch(gb,"ToothProfileTop")
        if xy:
            sk_t.AttachmentSupport=[(xy,'')]; sk_t.MapMode="FlatFace"
            sk_t.AttachmentOffset=App.Placement(App.Vector(0,0,height),App.Rotation(App.Vector(0,0,1),twist_deg+wheel_phase))
        gearMath.generateToothProfile(sk_t,{"module":module,"num_teeth":num_teeth,
            "pressure_angle":pa,"profile_shift":0.0})

        loft=gb.newObject("PartDesign::AdditiveLoft","HelicalTooth")
        loft.Profile=sk_b; loft.Sections=[sk_t]; loft.Ruled=True
        gb.Tip=loft

        # STEP 3: Pattern the Teeth
        polar=util.createPolar(gb,loft,sk_b,num_teeth,"Teeth")
        polar.Originals=[loft]
        gb.Tip=polar

        # STEP 4: Add the Gear Body (Dedendum Cylinder)
        df=(gp_r-ded)*2
        ds=util.createSketch(gb,"DedendumCircle")
        ci=ds.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),df/2),False)
        ds.addConstraint(Sketcher.Constraint("Diameter",ci,df))
        dp=util.createPad(gb,ds,height,"DedendumPad")
        gb.Tip=dp

        doc.recompute()

        # STEP 5: Carve the Throat (Concave waist matching the worm)
        # The cutting circle is centered at the worm axis (distance cd from gear center)
        # with radius = worm outer radius + clearance. Full 360° revolution creates
        # a smooth concavity all around the wheel, shortening teeth in the meshing zone.
        sk_th=gb.newObject("Sketcher::SketchObject","ThroatCutSketch")
        xz=None
        for f in gb.Origin.OriginFeatures:
            if 'XZ' in f.Name or 'XZ' in f.Label: xz=f; break
        if xz:
            sk_th.AttachmentSupport=[(xz,'')]; sk_th.MapMode="ObjectXY"
            sk_th.AttachmentOffset=App.Placement(App.Vector(0,height/2,0),App.Rotation())

        # cut_r = worm pitch radius + clearance (NOT outer radius).
        # The wheel teeth extend beyond the pitch circle into the worm thread
        # grooves, so the throat groove only clears the worm's pitch surface.
        # Old formula (wr+add+module*cl) included the worm addendum, which made
        # the closest approach (cd-cut_r) fall below the gear root circle,
        # destroying entire teeth at the meshing center.
        cut_r=wr+module*cl
        groove_pos=-cd

        ci=sk_th.addGeometry(Part.Circle(App.Vector(groove_pos,0,0),App.Vector(0,0,1),cut_r),False)
        sk_th.addConstraint(Sketcher.Constraint("PointOnObject",ci,3,-1))
        sk_th.addConstraint(Sketcher.Constraint("Radius",ci,cut_r))
        sk_th.addConstraint(Sketcher.Constraint("DistanceX",ci,3,-1,1,groove_pos))
        sk_th.Visibility=False

        groove=gb.newObject("PartDesign::Groove","ThroatGroove")
        groove.Profile=sk_th; groove.ReferenceAxis=(sk_th,["V_Axis"])
        groove.Angle=360.0
        gb.Tip=groove

        doc.recompute()

        # STEP 6: Bore
        if gb_en:
            gbs=util.createSketch(gb,"Bore")
            gci=gbs.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),gb_dia/2),False)
            gbs.addConstraint(Sketcher.Constraint("Coincident",gci,3,-1,1))
            gbs.addConstraint(Sketcher.Constraint("Diameter",gci,gb_dia))
            gbp=util.createPocket(gb,gbs,height+10,"Bore")
            gbp.Reversed=True
            gb.Tip=gbp

        doc.recompute()

        # STEP 7: Final Placement
        # Tilt 90° around X so gear axis (local Z) becomes global Y.
        # WheelPhase is applied to the tooth profile sketches (STEP 2), not here,
        # so the Placement is a clean 90° / (1,0,0).
        r_align=App.Rotation(App.Vector(1,0,0),90)

        # Standard tip clearance = ded - add = 0.25*module.
        # Without this, wheel tooth tips are only 0.5mm from worm root —
        # not enough given the straight-loft teeth vs curved worm groove.
        tip_clearance=ded-add  # 0.25 * module
        place_cd=cd+tip_clearance

        # Shift by +height/2 in Y because the 90° X-tilt maps local Z to global Y.
        gb.Placement=App.Placement(App.Vector(place_cd,height/2,0),r_align)

    def force_Recompute(self): self._rebuild()


# ============================================================================
# COMMAND
# ============================================================================


class GloboidWormGearV2Command:
    def GetResources(self):
        return {"Pixmap":mainIcon,"MenuText":"Create Globoid Worm Gear V2",
                "ToolTip":"Create globoid worm gear (clean PartDesign-only builder)"}

    def Activated(self):
        if not App.ActiveDocument: App.newDocument()
        doc=App.ActiveDocument
        base="GloboidWormV2_values"; un=base; c=1
        while doc.getObject(un): un=f"{base}{c:03d}"; c+=1
        vs=createGloboidWormGearV2VarSet(doc,un)
        gn="Regenerate"; c=1
        while doc.getObject(gn): gn=f"Regenerate{c:03d}"; c+=1
        go=doc.addObject("Part::FeaturePython",gn)
        GloboidWormGearV2Result(go,vs)
        ViewProviderGearResult(go.ViewObject,mainIcon)
        go.Proxy.force_Recompute()
        FreeCADGui.SendMsgToActiveView("ViewFit")
        FreeCADGui.ActiveDocument.ActiveView.viewFront()

    def IsActive(self): return True


try:
    FreeCADGui.addCommand("GloboidWormGearV2Command",GloboidWormGearV2Command())
except Exception:
    pass
