"""Globoid Worm Gear V2 — clean PartDesign-only builder.

Design:
1. Straight shaft cylinder (Pad)
2. Thread via AdditiveHelix on the shaft
3. Globoid waist carved by a subtractive Groove (revolve cut)
4. Mating wheel as a throated helical gear

This avoids mixing Part/PartDesign operations and the fragile
loft+bcolean-cut approach of V1.
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
    vs.setExpression("CenterDistance","WormPitchDiameter/2 + Module*GearTeeth/2 + pi*Module/4")
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

            # === BUILD WORM ===
            m=self._last_m; nt=self._last_nt; pa=self._last_pa
            wp_dia=self._last_wpd; s_dia=self._last_sd; s_len=self._last_sl
            wl=self._last_wl; rh=self._last_rh

            wp_r=wp_dia/2.0
            wpr=wp_r  # worm pitch radius
            wr=wp_r-m*1.25  # worm root radius

            body=util.readyPart(d, bn)

            # 1. Thin shaft + thread base cylinder (one revolve profile)
            total_len=wl+2*s_len
            half=total_len/2.0
            sk_shaft=util.createSketch(body,"ShaftProfile")
            sk_shaft.MapMode="Deactivated"
            p0=App.Vector(0,-half,0); p1=App.Vector(0,half,0)    # axis
            p2=App.Vector(s_dia/2,half,0); p3=App.Vector(s_dia/2,wl/2,0)  # shaft OD
            p4=App.Vector(wpr+m*1.25,wl/2,0)  # thread OD step outward
            p5=App.Vector(wpr+m*1.25,-wl/2,0)  # thread OD step inward
            p6=App.Vector(s_dia/2,-wl/2,0); p7=App.Vector(s_dia/2,-half,0)  # other side

            geo=[Part.LineSegment(p0,p1),Part.LineSegment(p1,p2),Part.LineSegment(p2,p3),
                 Part.LineSegment(p3,p4),Part.LineSegment(p4,p5),Part.LineSegment(p5,p6),
                 Part.LineSegment(p6,p7),Part.LineSegment(p7,p0)]
            for g in geo: sk_shaft.addGeometry(g,False)
            # Constraints: coincident chain
            for i in range(8):
                sk_shaft.addConstraint(Sketcher.Constraint("Coincident",i,2,(i+1)%8,1))
            # Vertical/horizontal
            sk_shaft.addConstraint(Sketcher.Constraint("Vertical",0))
            sk_shaft.addConstraint(Sketcher.Constraint("Horizontal",1))
            sk_shaft.addConstraint(Sketcher.Constraint("Vertical",2))
            sk_shaft.addConstraint(Sketcher.Constraint("Horizontal",3))
            sk_shaft.addConstraint(Sketcher.Constraint("Horizontal",5))
            sk_shaft.addConstraint(Sketcher.Constraint("Vertical",6))
            sk_shaft.addConstraint(Sketcher.Constraint("Horizontal",7))
            # Dimensions
            sk_shaft.addConstraint(Sketcher.Constraint("DistanceY",0,1,0,2,total_len))
            sk_shaft.addConstraint(Sketcher.Constraint("DistanceX",1,1,1,2,s_dia/2))
            sk_shaft.addConstraint(Sketcher.Constraint("DistanceY",2,1,2,2,wl))
            sk_shaft.addConstraint(Sketcher.Constraint("DistanceX",3,1,3,2,wpr+m*1.25))
            sk_shaft.addConstraint(Sketcher.Constraint("DistanceX",4,1,4,2,wpr+m*1.25))
            sk_shaft.addConstraint(Sketcher.Constraint("Symmetric",0,1,0,2,-1,1))

            # Revolve the profile
            rev=body.newObject("PartDesign::Revolution","BaseCylinder")
            rev.Profile=sk_shaft
            rev.ReferenceAxis=(sk_shaft,["V_Axis"])
            rev.Angle=360
            body.Tip=rev

            # 2. Thread via AdditiveHelix
            sk_thread=util.createSketch(body,"ThreadProfile")
            sk_thread.MapMode="Deactivated"
            # Trapezoidal thread profile (gap shape)
            tan_pa=math.tan(pa*math.pi/180)
            hw_pitch=m*math.pi/4
            add=m; ded=m*1.25
            h=add+ded  # total thread height
            wr_root=hw_pitch-ded*tan_pa
            wr_tip=hw_pitch+add*tan_pa
            pts=[App.Vector(0,-wr_root,0),App.Vector(h,-wr_tip,0),
                 App.Vector(h,wr_tip,0),App.Vector(0,wr_root,0)]
            for i in range(4):
                sk_thread.addGeometry(Part.LineSegment(pts[i],pts[(i+1)%4]),False)
            sk_thread.Placement=App.Placement(App.Vector(wp_r,0,wl/2),App.Rotation(App.Vector(0,1,0),90))
            # Note: placement positions the thread profile at the worm surface,
            # oriented so the helix advances along the worm axis (Z)

            d.recompute()

            thread_pitch=m*math.pi
            helix=body.newObject("PartDesign::AdditiveHelix","WormThread")
            helix.Profile=sk_thread
            helix.Pitch=thread_pitch*nt
            helix.Height=wl
            helix.Reversed=rh
            helix.LeftHanded=False
            helix.ReferenceAxis=(sk_thread,["N_Axis"])
            body.Tip=helix

            d.recompute()

            # 3. Globoid waist cut (Groove)
            gt=self._last_gt
            gp_r=m*gt/2.0  # gear pitch radius
            cd=gp_r+wp_r  # center distance
            arc_r=gp_r*0.9
            half_wl=wl/2
            arc_top_y=arc_r*math.sin(math.asin(half_wl/arc_r))
            # Waist cut sketch on XZ plane
            xz=None
            for f in body.Origin.OriginFeatures:
                if 'XZ' in f.Name or 'XZ' in f.Label: xz=f; break
            sk_groove=util.createSketch(body,"WaistGroove")
            if xz:
                sk_groove.AttachmentSupport=[(xz,'')]; sk_groove.MapMode="FlatFace"
            else:
                sk_groove.MapMode="Deactivated"
                sk_groove.Placement=App.Placement(App.Vector(0,0,0),App.Rotation(App.Vector(1,0,0),90))
            # Circular arc cutting the globoid waist
            arc_center=App.Vector(-cd,0,0)
            half_a=math.asin(half_wl/arc_r)
            sa=-half_a; ea=half_a
            circ=Part.Circle(arc_center,App.Vector(0,0,1),arc_r)
            arc_g=Part.ArcOfCircle(circ,sa,ea)
            sk_groove.addGeometry(arc_g,False)
            # Close the cut profile — connect arc ends via the axis so the
            # Groove can revolve properly.
            arc_top=App.Vector(-cd+arc_r*math.cos(ea),arc_r*math.sin(ea),0)
            arc_bot=App.Vector(-cd+arc_r*math.cos(sa),arc_r*math.sin(sa),0)
            sk_groove.addGeometry(Part.LineSegment(arc_top,App.Vector(arc_top.x*0.05,arc_top.y,0)),False)
            sk_groove.addGeometry(Part.LineSegment(App.Vector(arc_top.x*0.05,arc_top.y,0),App.Vector(arc_bot.x*0.05,arc_bot.y,0)),False)
            sk_groove.addGeometry(Part.LineSegment(App.Vector(arc_bot.x*0.05,arc_bot.y,0),arc_bot),False)
            # Connect the chain: arc top → line1 → line2 → arc bottom → arc top
            sk_groove.addConstraint(Sketcher.Constraint("Coincident",1,1,0,2))  # line1 start → arc end
            sk_groove.addConstraint(Sketcher.Constraint("Coincident",1,2,2,1))  # line1 end → line2 start
            sk_groove.addConstraint(Sketcher.Constraint("Coincident",2,2,3,1))  # line2 end → line3 start
            sk_groove.addConstraint(Sketcher.Constraint("Coincident",3,2,0,1))  # line3 end → arc start

            groove=body.newObject("PartDesign::Groove","WaistGroove")
            groove.Profile=sk_groove
            groove.ReferenceAxis=(sk_groove,["V_Axis"])
            groove.Angle=360
            body.Tip=groove

            d.recompute()

            # 4. Bore & keyway
            bd=float(v.BoreDiameter.Value)
            if bool(v.BoreEnabled):
                bore_sk=util.createSketch(body,"Bore")
                ci=bore_sk.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),bd/2),False)
                bore_sk.addConstraint(Sketcher.Constraint("Coincident",ci,3,-1,1))
                bore_sk.addConstraint(Sketcher.Constraint("Diameter",ci,bd))
                bore_sk.Placement=App.Placement(App.Vector(0,0,half),App.Rotation())
                bore_sk.MapMode="Deactivated"
                bp=util.createPocket(body,bore_sk,total_len)
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
                    kws.Placement=App.Placement(App.Vector(0,0,half),App.Rotation())
                    kws.MapMode="Deactivated"
                    kp=util.createPocket(body,kws,total_len)
                    kp.Reversed=True
                    body.Tip=kp

            # 5. Mating gear
            if self._last_cm:
                self._make_wheel(d,bn,wp_r)

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
        cd=self._last_wpd/2 + module*num_teeth/2 + math.pi*module/4
        wheel_phase=self._last_wp
        gb_dia=self._last_gbd; gb_en=self._last_gbe

        gbn=f"{body_name}_WormWheel"
        gb=util.readyPart(doc,gbn)

        ded=module*1.25; add=module*1.0
        gp_r=module*num_teeth/2
        wr=worm_pitch_r-ded

        # Helical twist
        pitch=math.pi*module; lead=pitch*nt
        lead_rad=math.atan(lead/(math.pi*worm_pitch_r*2))
        twist_rad=height*math.tan(lead_rad)/gp_r
        twist_deg=twist_rad/math.pi*180
        if rh: twist_deg=-twist_deg

        # Tooth profile (bottom)
        sk_b=util.createSketch(gb,"ToothProfileBottom")
        gearMath.generateToothProfile(sk_b,{"module":module,"num_teeth":num_teeth,
            "pressure_angle":pa,"profile_shift":0.0})

        # Top (twisted)
        sk_t=util.createSketch(gb,"ToothProfileTop")
        xy=None
        for f in gb.Origin.OriginFeatures:
            if 'XY' in f.Name or 'XY' in f.Label: xy=f; break
        if xy:
            sk_t.AttachmentSupport=[(xy,'')]; sk_t.MapMode="FlatFace"
            sk_t.AttachmentOffset=App.Placement(App.Vector(0,0,height),App.Rotation(App.Vector(0,0,1),twist_deg))
        gearMath.generateToothProfile(sk_t,{"module":module,"num_teeth":num_teeth,
            "pressure_angle":pa,"profile_shift":0.0})

        # Loft
        loft=gb.newObject("PartDesign::AdditiveLoft","HelicalTooth")
        loft.Profile=sk_b; loft.Sections=[sk_t]; loft.Ruled=True
        gb.Tip=loft

        # Polar pattern
        polar=util.createPolar(gb,loft,sk_b,num_teeth,"Teeth")
        polar.Originals=[loft]
        gb.Tip=polar

        # Dedendum
        df=gp_r*2
        ds=util.createSketch(gb,"DedendumCircle")
        ci=ds.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),df/2),False)
        ds.addConstraint(Sketcher.Constraint("Diameter",ci,df))
        dp=util.createPad(gb,ds,height,"DedendumPad")
        gb.Tip=dp

        doc.recompute()

        # Throat groove
        sk_th=gb.newObject("Sketcher::SketchObject","ThroatCutSketch")
        xz=None
        for f in gb.Origin.OriginFeatures:
            if 'XZ' in f.Name or 'XZ' in f.Label: xz=f; break
        if xz:
            sk_th.AttachmentSupport=[(xz,'')]; sk_th.MapMode="ObjectXY"
            sk_th.AttachmentOffset=App.Placement(App.Vector(0,height/2,0),App.Rotation())
        cut_r=wr+module*cl
        groove_pos=-(cd-1.85)
        ci=sk_th.addGeometry(Part.Circle(App.Vector(groove_pos,0,0),App.Vector(0,0,1),cut_r),False)
        sk_th.addConstraint(Sketcher.Constraint("PointOnObject",ci,3,-1))
        sk_th.addConstraint(Sketcher.Constraint("Radius",ci,cut_r))
        sk_th.addConstraint(Sketcher.Constraint("DistanceX",ci,3,-1,1,groove_pos))
        groove=gb.newObject("PartDesign::Groove","ThroatGroove")
        groove.Profile=sk_th; groove.ReferenceAxis=(sk_th,["V_Axis"])
        groove.Angle=360
        gb.Tip=groove

        doc.recompute()

        # Bore
        if gb_en:
            gbs=util.createSketch(gb,"Bore")
            gci=gbs.addGeometry(Part.Circle(App.Vector(0,0,0),App.Vector(0,0,1),gb_dia/2),False)
            gbs.addConstraint(Sketcher.Constraint("Coincident",gci,3,-1,1))
            gbs.addConstraint(Sketcher.Constraint("Diameter",gci,gb_dia))
            gbp=util.createPocket(gb,gbs,height+10,"Bore")
            gbp.Reversed=True
            gb.Tip=gbp

        doc.recompute()

        # Placement
        wc=math.pi*module/4
        r_align=App.Rotation(App.Vector(1,0,0),90)*App.Rotation(App.Vector(0,0,1),wheel_phase)
        gb.Placement=App.Placement(App.Vector(cd+wc,height/2,0),r_align)

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

    def IsActive(self): return True


try:
    FreeCADGui.addCommand("GloboidWormGearV2Command",GloboidWormGearV2Command())
except Exception:
    pass
