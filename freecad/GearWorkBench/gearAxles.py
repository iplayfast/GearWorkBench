"""Gear Axles for GearWorkBench

Creates a starting-point axle layout for a gearbox: one axle under each
selected gear Body (including Geneva wheels and cranks), joined by a
common base plate. Axle diameters follow each gear's bore diameter so
the axles fit the bores they pass through.

Copyright 2026, Chris Bruner
License LGPL V2.1
"""

import math
import os
import FreeCAD as App
import FreeCADGui
import Part

from .gearStack import ViewProviderGearStack

smWBpath = os.path.dirname(os.path.abspath(__file__))
smWB_icons_path = os.path.join(smWBpath, "icons")


def _axleDiameter(doc, body):
    """Bore diameter of the gear on this body, used as the axle diameter."""
    for obj in doc.Objects:
        if not hasattr(obj, "VarSetName"):
            continue
        vs = doc.getObject(str(obj.VarSetName))
        if vs is None:
            continue
        if getattr(obj, "BodyName", None) == body.Name and hasattr(vs, "BoreDiameter"):
            return float(vs.BoreDiameter.Value)
        if getattr(obj, "CrankBodyName", None) == body.Name and hasattr(vs, "CrankBoreDiameter"):
            return float(vs.CrankBoreDiameter.Value)
        if getattr(obj, "WheelBodyName", None) == body.Name and hasattr(vs, "WheelBoreDiameter"):
            return float(vs.WheelBoreDiameter.Value)
    return 5.0


class GearAxles:
    """Proxy for a Part::FeaturePython holding axles + base for linked gears."""

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty(
            "App::PropertyLinkList", "Gears", "GearAxles",
            "Gear Body objects to create axles for"
        )
        obj.addProperty(
            "App::PropertyLength", "AxleLength", "GearAxles",
            "Axle length below the lowest gear, down to the base plate"
        )
        obj.addProperty(
            "App::PropertyLength", "BaseThickness", "GearAxles",
            "Thickness of the base plate"
        )
        obj.addProperty(
            "App::PropertyLength", "BaseMargin", "GearAxles",
            "Base plate margin around the outermost axles"
        )
        obj.AxleLength = 20.0
        obj.BaseThickness = 5.0
        obj.BaseMargin = 5.0

    def _horizontalAxle(self, g, r, base_top, margin, wall_t):
        """Axle along a horizontal gear axis plus a bearing wall at each end.

        A gear whose axis is not vertical (e.g. the worm of a worm drive)
        cannot drop a post to the floor plate; its axle runs along its own
        axis and is supported at both ends by vertical walls standing on
        the base — the gear's own mounting plane, at 90 deg to the floor.
        """
        axis = g.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        # ponytail: oblique axes (tilted bevel) are flattened to horizontal;
        # axis-true axles with tilted walls if a real need ever shows up.
        axis.z = 0.0
        if axis.Length < 1e-9:
            axis = App.Vector(1, 0, 0)
        axis.normalize()

        p0 = g.Placement.Base
        bb = g.Shape.BoundBox
        corners = [App.Vector(x, y, z)
                   for x in (bb.XMin, bb.XMax)
                   for y in (bb.YMin, bb.YMax)
                   for z in (bb.ZMin, bb.ZMax)]
        ts = [(c - p0).dot(axis) for c in corners]
        t0, t1 = min(ts) - wall_t, max(ts) + wall_t

        axle = Part.makeCylinder(r, t1 - t0, p0 + axis * t0, axis)

        # Bearing walls: vertical plates from the base up over the axle ends
        walls = []
        width = 2.0 * r + 2.0 * margin
        height = (p0.z + r + margin) - base_top
        angle = math.degrees(math.atan2(axis.y, axis.x))
        for t in (t0, t1 - wall_t):
            wall = Part.makeBox(wall_t, width, height,
                                App.Vector(0, -width / 2.0, 0))
            wall.Placement = App.Placement(
                p0 + axis * t + App.Vector(0, 0, base_top - p0.z),
                App.Rotation(App.Vector(0, 0, 1), angle),
            )
            walls.append(wall)
        return [axle] + walls

    def execute(self, obj):
        doc = obj.Document
        gears = [g for g in obj.Gears
                 if g is not None and hasattr(g, "Shape") and not g.Shape.isNull()]
        if not gears:
            obj.Shape = Part.Shape()
            return

        margin = float(obj.BaseMargin.Value)
        thickness = float(obj.BaseThickness.Value)

        # Base plate top sits AxleLength below the lowest gear underside
        base_top = min(g.Shape.BoundBox.ZMin for g in gears) - float(obj.AxleLength.Value)

        solids = []
        for g in gears:
            r = _axleDiameter(doc, g) / 2.0
            axis = g.Placement.Rotation.multVec(App.Vector(0, 0, 1))
            if abs(axis.z) > 0.7:
                # Vertical axis: post from the gear top down to the base
                x, y = g.Placement.Base.x, g.Placement.Base.y
                top = g.Shape.BoundBox.ZMax
                solids.append(Part.makeCylinder(
                    r, top - base_top, App.Vector(x, y, base_top)))
            else:
                solids.extend(self._horizontalAxle(g, r, base_top, margin, thickness))

        # Base plate spans everything standing on it, plus margin
        bb = Part.makeCompound(solids).BoundBox
        base = Part.makeBox(
            bb.XLength + 2 * margin,
            bb.YLength + 2 * margin,
            thickness,
            App.Vector(bb.XMin - margin, bb.YMin - margin, base_top - thickness),
        )

        # Single multiFuse instead of chained pairwise fuses — the chain
        # spams "Not all input shapes are mappable" from the topological
        # naming engine on every recompute.
        obj.Shape = base.multiFuse(solids).removeSplitter()

    def onChanged(self, obj, prop):
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class GearAxlesCommand:
    """FreeCAD command to create a GearAxles object from selected Bodies."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "gearWorkbench.svg"),
            "MenuText": "Create Gear Axles",
            "ToolTip": "Create an axle for each selected gear, joined by a base plate.\n"
                       "Vertical gears get posts; worms and other horizontal gears\n"
                       "get axles with bearing walls. A starting point for gearbox design.\n"
                       "Select 1 or more gears first (any gear type, including Geneva and worms).",
        }

    @staticmethod
    def _selectedGears():
        """Selected objects usable as gears: anything with a solid shape.

        Not restricted to PartDesign::Body — globoid worms are Part::Feature
        or Part::Cut results, and any shape can carry an axle.
        """
        sel = FreeCADGui.Selection.getSelection()
        return [o for o in sel
                if hasattr(o, "Shape") and not o.Shape.isNull()]

    def Activated(self):
        doc = App.ActiveDocument

        bodies = self._selectedGears()
        if not bodies:
            App.Console.PrintError("GearAxles: Select 1 or more gear objects\n")
            return

        doc.openTransaction("Create Gear Axles")
        try:
            obj = doc.addObject("Part::FeaturePython", "GearAxles")
            GearAxles(obj)
            ViewProviderGearStack(obj.ViewObject)
            obj.Gears = bodies
            doc.commitTransaction()
            doc.recompute()
        except Exception as e:
            doc.abortTransaction()
            App.Console.PrintError(f"GearAxles creation failed: {e}\n")

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        return len(self._selectedGears()) >= 1


try:
    FreeCADGui.addCommand("GearAxlesCommand", GearAxlesCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register GearAxles command: {e}\n")
