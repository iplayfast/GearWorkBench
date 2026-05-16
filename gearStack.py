"""Gear Stack for GearWorkbench

Creates a coaxial stack of gear Bodies, optionally fused into a single solid
for 3D printing.

Copyright 2025, Chris Bruner
License LGPL V2.1
"""

import os
import FreeCAD as App
import FreeCADGui
import Part

smWBpath = os.path.dirname(os.path.abspath(__file__))
smWB_icons_path = os.path.join(smWBpath, "icons")


class GearStack:
    """Proxy for a Part::FeaturePython that stacks gear Bodies coaxially."""

    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty(
            "App::PropertyLinkList", "Gears", "GearStack",
            "Gear Body objects to stack"
        )
        obj.addProperty(
            "App::PropertyFloatList", "Gaps", "GearStack",
            "Z gap between each adjacent pair of gears"
        )
        obj.addProperty(
            "App::PropertyBool", "Fused", "GearStack",
            "When True, fuse all gears into a single solid"
        )
        obj.addProperty(
            "App::PropertyVector", "StackOrigin", "GearStack",
            "Base position of the stack"
        )
        obj.addProperty(
            "App::PropertyVector", "StackAxis", "GearStack",
            "Axis direction for stacking"
        )

        obj.Fused = False
        obj.StackOrigin = App.Vector(0, 0, 0)
        obj.StackAxis = App.Vector(0, 0, 1)

    def execute(self, obj):
        """Position gears coaxially and optionally fuse them."""
        gears = obj.Gears
        if not gears:
            obj.Shape = Part.Shape()
            return

        gaps = obj.Gaps if obj.Gaps else []
        # Pad gaps with zeros if too short
        while len(gaps) < len(gears) - 1:
            gaps.append(0.0)

        axis = App.Vector(obj.StackAxis)
        if axis.Length < 1e-6:
            axis = App.Vector(0, 0, 1)
        else:
            axis.normalize()

        origin = App.Vector(obj.StackOrigin)
        offset = 0.0

        # Build transformed shapes without mutating source Body placements
        shapes = []
        for i, gear in enumerate(gears):
            if not hasattr(gear, "Shape") or gear.Shape.isNull():
                continue

            # Copy the shape and move it to the stack position
            shape = gear.Shape.copy()
            pos = origin + axis * offset
            shape.Placement = App.Placement(pos, App.Rotation())

            shapes.append(shape)

            # Advance offset by this gear's height along the axis + gap
            bbox = gear.Shape.BoundBox
            height = bbox.ZLength
            offset += height
            if i < len(gaps):
                offset += gaps[i]

        if not shapes:
            obj.Shape = Part.Shape()
            return

        if obj.Fused and len(shapes) > 1:
            try:
                fused = shapes[0]
                for s in shapes[1:]:
                    fused = fused.fuse(s)
                fused = fused.removeSplitter()
                obj.Shape = fused
            except Exception as e:
                App.Console.PrintError(f"GearStack fuse failed: {e}\n")
                obj.Shape = Part.makeCompound(shapes)
        elif len(shapes) == 1:
            obj.Shape = shapes[0]
        else:
            obj.Shape = Part.makeCompound(shapes)

    def onChanged(self, obj, prop):
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class ViewProviderGearStack:
    """View provider for GearStack objects."""

    def __init__(self, obj):
        obj.Proxy = self
        self.iconfile = os.path.join(smWB_icons_path, "gearWorkbench.svg")

    def attach(self, obj):
        self.ViewObject = obj
        self.Object = obj.Object

    def updateData(self, fp, prop):
        return

    def getDisplayModes(self, obj):
        return ["Shaded", "Wireframe", "Flat Lines"]

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def onChanged(self, vobj, prop):
        return

    def getIcon(self):
        return self.iconfile

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class GearStackCommand:
    """FreeCAD command to create a GearStack from selected Bodies."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "gearWorkbench.svg"),
            "MenuText": "Create Gear Stack",
            "ToolTip": "Stack selected gear Bodies coaxially, optionally fused for 3D printing",
        }

    def Activated(self):
        doc = App.ActiveDocument
        sel = FreeCADGui.Selection.getSelection()

        # Filter for Body objects
        bodies = [o for o in sel if o.TypeId == "PartDesign::Body"]
        if len(bodies) < 2:
            App.Console.PrintError("GearStack: Select 2 or more PartDesign::Body objects\n")
            return

        doc.openTransaction("Create Gear Stack")
        try:
            obj = doc.addObject("Part::FeaturePython", "GearStack")
            GearStack(obj)
            ViewProviderGearStack(obj.ViewObject)

            obj.Gears = bodies
            obj.Gaps = [0.0] * (len(bodies) - 1)

            doc.commitTransaction()
            doc.recompute()
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception as e:
            doc.abortTransaction()
            App.Console.PrintError(f"GearStack creation failed: {e}\n")

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        sel = FreeCADGui.Selection.getSelection()
        bodies = [o for o in sel if o.TypeId == "PartDesign::Body"]
        return len(bodies) >= 2


# Register command with FreeCAD
try:
    FreeCADGui.addCommand("GearStackCommand", GearStackCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register GearStack command: {e}\n")
