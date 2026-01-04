"""Generic Non-Circular Gear generator for FreeCAD

This module provides a generic non-circular gear builder that can work with different
profile generation functions (elliptical, lobed, custom, etc.).

Non-circular gears have varying radius and are used for applications requiring
non-constant velocity ratios, such as pumps, presses, and special mechanisms.

Copyright 2025, Chris Bruner
Version v0.1
License LGPL V2.1
"""

from __future__ import division

import FreeCAD as App
import FreeCADGui
import gearMath
import util
import Part
import Sketcher


def nonCircularGear(doc, parameters, profile_func):
    """Non-circular gear generator that accepts a custom profile function.

    Args:
        doc: FreeCAD document
        parameters: Dictionary of gear parameters including:
            - height: Gear thickness
            - bore_type: Type of bore ("none", "circular", "square", "hexagonal", "keyway")
            - bore_diameter: Diameter of bore
            - body_name: Name for the PartDesign Body
            - Additional parameters specific to the profile function
        profile_func: Function(parameters) that returns a list of App.Vector points
                     defining the non-circular profile

    Returns:
        The PartDesign Body containing the non-circular gear
    """
    body_name = parameters.get("body_name", "NonCircularGear")
    body = util.readyPart(doc, body_name)

    height = parameters["height"]
    bore_type = parameters.get("bore_type", "none")

    # 1. Generate Profile Points using the provided function
    profile_points = profile_func(parameters)

    # Ensure the profile is closed
    if profile_points[0] != profile_points[-1]:
        profile_points.append(profile_points[0])

    # 2. Create Sketch
    sketch = util.createSketch(body, "NonCircularProfile")

    # Create a B-Spline from the points
    bspline = Part.BSplineCurve()
    bspline.interpolate(profile_points, True)  # Periodic/Closed
    sketch.addGeometry(bspline, False)

    # 3. Extrude (Pad)
    pad = util.createPad(body, sketch, height, "GearBody")
    body.Tip = pad

    # 4. Bore
    if bore_type != "none":
        util.createBore(body, parameters, height)

    doc.recompute()
    if App.GuiUp:
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    return body
