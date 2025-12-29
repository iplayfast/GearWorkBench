# -*- coding: utf-8 -*-
"""
Minimal Generic Gear Framework - Working Version

Copyright 2025, Chris Bruner
Version v0.2.2 (Minimal Working)
License LGPL V2.1
"""

import math
from typing import Dict, Any, Callable

import FreeCAD as App
import gearMath
import util


def createGenericGear(doc, parameters, tooth_profile_func, gear_type="spur"):
    """
    Minimal unified gear creation function.
    """
    if not App.ActiveDocument:
        App.newDocument()
    doc = App.ActiveDocument

    # Create body using utility
    body = util.createBody(doc, f"Generic{gear_type.capitalize()}Gear")

    try:
        # Route to appropriate creation function based on gear type
        if gear_type == "spur":
            return _createSpurGear(body, parameters, tooth_profile_func)
        elif gear_type == "helical":
            return _createHelicalGear(body, parameters, tooth_profile_func)
        else:
            raise ValueError(f"Unsupported gear type: {gear_type}")

    except Exception as e:
        App.Console.PrintError(f"Generic gear error: {e}")
        return {"error": str(e)}


def _createSpurGear(body, parameters, tooth_profile_func):
    """Create spur gear using simplified approach."""
    module = float(parameters["module"])
    num_teeth = int(parameters["num_teeth"])
    height = float(parameters["height"])

    # 1. Single tooth profile at origin
    sketch = util.createSketch(body, "ToothProfile")
    tooth_profile_func(sketch, parameters)

    # 2. Pad to create single tooth
    tooth_pad = util.createPad(body, sketch, height, "Tooth")

    # 3. Polar array
    polar = util.createPolar(body, tooth_pad, sketch, num_teeth, "Teeth")
    polar.Originals = [tooth_pad]
    tooth_pad.Visibility = False
    polar.Visibility = True
    body.Tip = polar

    # 4. Dedendum cylinder
    dedendum_radius = (num_teeth - 2.5) * module / 2.0
    dedendum_sketch = util.createSketch(body, "DedendumCylinder")
    circle = dedendum_sketch.addGeometry(
        App.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), dedendum_radius + 0.01)
    )
    dedendum_sketch.addConstraint(
        App.Sketcher.Constraint("Coincident", circle, 3, -1, 1)
    )
    dedendum_sketch.addConstraint(
        App.Sketcher.Constraint("Diameter", circle, (dedendum_radius + 0.01) * 2)
    )
    dedendum_pad = util.createPad(body, dedendum_sketch, height, "DedendumCylinder")
    body.Tip = dedendum_pad

    # 5. Recompute
    try:
        body.Document.recompute()
    except Exception:
        pass

    return {
        "status": "success",
        "tooth_pad": tooth_pad,
        "polar": polar,
        "dedendum_pad": dedendum_pad,
    }


def _createHelicalGear(body, parameters, tooth_profile_func):
    """Create helical gear using spur gear logic."""
    # For now, use same logic as spur gear
    return _createSpurGear(body, parameters, tooth_profile_func)


class GenericSpurGearCommand:
    """Command to create generic spur gear."""

    def GetResources(self):
        return {
            "Pixmap": "spurGear.svg",
            "MenuText": "&Create Generic Spur Gear",
            "ToolTip": "Create parametric involute spur gear using unified framework",
        }

    def IsActive(self):
        return True

    def Activated(self):
        """Called when command is activated."""
        if not App.ActiveDocument:
            App.newDocument()
        doc = App.ActiveDocument

        # Create parametric object
        gear_obj = doc.addObject("App::FeaturePython", "GenericSpurGearParameters")

        # Import and use the minimal implementation
        from genericGearMinimal import createSpurGearWithProfile

        result = createSpurGearWithProfile(doc, gearMath.generateDefaultParameters())

        doc.recompute()
        if App.GuiUp:
            try:
                App.Gui.SendMsgToActiveView("ViewFit")
            except Exception:
                pass

        App.Console.PrintMessage("✓ Generic spur gear with parameters created\n")

    def IsActive(self):
        return True
