# -*- coding: utf-8 -*-
"""
Unified Gear Framework - Working Implementation

Based on debugging, this bypasses the problematic gearMath.generateToothProfile
and uses working spur gear logic directly.

Copyright 2025, Chris Bruner
Version v0.2.2 (Unified Working)
License LGPL V2.1
"""

import math
from typing import Dict, Any, Callable

import FreeCAD as App
import gearMath
import util


def createUnifiedSpurGear(doc, parameters):
    """Create spur gear using proven working spur gear logic."""
    if not App.ActiveDocument:
        App.newDocument()
    doc = App.ActiveDocument

    # Use exact spur gear parameters from working spurGear.py
    module = float(parameters["module"])
    num_teeth = int(parameters["num_teeth"])
    height = float(parameters["height"])
    pressure_angle = float(parameters["pressure_angle"])
    profile_shift = float(parameters.get("profile_shift", 0.0))

    dw = module * num_teeth
    dg = dw * math.cos(math.radians(pressure_angle))
    da = dw + 2 * module * (gearMath.ADDENDUM_FACTOR + profile_shift)
    df = dw - 2 * module * (gearMath.DEDENDUM_FACTOR - profile_shift)

    # Create body
    body = util.readyPart(doc, "UnifiedSpurGear")

    try:
        # 1. Tooth Profile (working approach)
        sketch = util.createSketch(body, "ToothProfile")
        gearMath.generateToothProfile(sketch, parameters)

        # 2. Pad to create single tooth
        tooth_pad = util.createPad(body, sketch, height, "Tooth")

        # 3. Polar Pattern
        polar = util.createPolar(body, tooth_pad, sketch, num_teeth, "Teeth")
        polar.Originals = [tooth_pad]
        tooth_pad.Visibility = False
        polar.Visibility = True
        body.Tip = polar

        # 4. Dedendum Circle
        dedendum_sketch = util.createSketch(body, "DedendumCircle")
        circle = dedendum_sketch.addGeometry(
            App.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), df / 2.0 + 0.01)
        )
        dedendum_sketch.addConstraint(
            App.Sketcher.Constraint("Coincident", circle, 3, -1, 1)
        )
        dedendum_sketch.addConstraint(
            App.Sketcher.Constraint("Diameter", circle, df + 0.02)
        )
        dedendum_pad = util.createPad(body, dedendum_sketch, height, "DedendumCircle")
        body.Tip = dedendum_pad

        # 5. Recompute
        doc.recompute()

        print("✅ SUCCESS: Unified spur gear created successfully!")
        return {"status": "success", "body": body}

    except Exception as e:
        App.Console.PrintError(f"Unified spur gear error: {e}")
        return {"error": str(e)}


class UnifiedSpurGear:
    """FeaturePython object for unified spur gear."""

    def __init__(self, obj):
        obj.addProperty(
            "App::PropertyInteger", "num_teeth", "Gear", "Number of teeth"
        ).num_teeth = 20
        obj.addProperty(
            "App::PropertyLength", "module", "Gear", "Module"
        ).module = "2 mm"
        obj.addProperty(
            "App::PropertyLength", "height", "Gear", "Gear height"
        ).height = "10 mm"
        obj.addProperty(
            "App::PropertyAngle", "pressure_angle", "Gear", "Pressure angle"
        ).pressure_angle = "20 deg"
        obj.addProperty(
            "App::PropertyFloat", "profile_shift", "Gear", "Profile shift coefficient"
        ).profile_shift = 0.0
        obj.addProperty(
            "App::PropertyString", "bore_type", "Gear", "Bore type"
        ).bore_type = "none"

        obj.Proxy = self

    def execute(self, obj):
        """Create the gear geometry."""
        try:
            parameters = {
                "num_teeth": obj.num_teeth,
                "module": obj.module.Value,
                "height": obj.height.Value,
                "pressure_angle": obj.pressure_angle.Value,
                "profile_shift": obj.profile_shift,
                "bore_type": obj.bore_type,
                "body_name": obj.Name,
            }

            doc = obj.Document
            createUnifiedSpurGear(doc, parameters)

        except Exception as e:
            App.Console.PrintError(f"❌ Unified gear creation failed: {e}\\n")


class UnifiedSpurGearCommand:
    """Command to create unified spur gear."""

    def GetResources(self):
        return {
            "Pixmap": "spurGear.svg",
            "MenuText": "&Create Unified Spur Gear",
            "ToolTip": "Create parametric involute spur gear using proven working logic",
        }

    def IsActive(self):
        return True

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Create parametric object
        gear_obj = doc.addObject("App::FeaturePython", "UnifiedSpurGear")
        unified_spur_gear = UnifiedSpurGear(gear_obj)
        view_provider = UnifiedSpurGearViewProvider(gear_obj.ViewObject)

        doc.recompute()
        if App.GuiUp:
            try:
                App.Gui.SendMsgToActiveView("ViewFit")
            except Exception:
                pass

        App.Console.PrintMessage("✅ Unified spur gear created\\n")


class UnifiedSpurGearViewProvider:
    """View provider for unified spur gear."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ":/icons/spurGear.svg"

    def attach(self, vobj):
        self.obj = vobj.Object

    def updateData(self, fp, prop):
        return

    def onChanged(self, vp, prop):
        return
