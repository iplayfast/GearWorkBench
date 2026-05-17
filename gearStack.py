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
from PySide import QtGui, QtCore

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
            "App::PropertyBool", "PrePositioned", "GearStack",
            "When True, use bodies' existing placements instead of restacking"
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
        obj.PrePositioned = False
        obj.StackOrigin = App.Vector(0, 0, 0)
        obj.StackAxis = App.Vector(0, 0, 1)

    def execute(self, obj):
        """Position gears coaxially and optionally fuse them."""
        gears = obj.Gears
        if not gears:
            obj.Shape = Part.Shape()
            return

        # PrePositioned mode: use bodies' current world placements as-is
        if obj.PrePositioned:
            shapes = []
            for gear in gears:
                if not hasattr(gear, "Shape") or gear.Shape.isNull():
                    continue
                shapes.append(gear.Shape.copy())
        else:
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


def _find_geneva_info(doc, bodies):
    """Check if any selected bodies belong to a Geneva wheel mechanism.

    Returns a dict with crank/wheel body names, geneva bodies, and other bodies,
    or None if no Geneva component is detected.
    """
    body_names = {b.Name for b in bodies}

    # Search for Geneva result objects that reference any of our selected bodies
    for obj in doc.Objects:
        crank_name = getattr(obj, "CrankBodyName", None)
        wheel_name = getattr(obj, "WheelBodyName", None)
        if crank_name is None or wheel_name is None:
            continue

        # Check if any selected body matches a Geneva component
        if crank_name in body_names or wheel_name in body_names:
            geneva_bodies = []
            other_bodies = []
            for b in bodies:
                if b.Name in (crank_name, wheel_name):
                    geneva_bodies.append(b)
                else:
                    other_bodies.append(b)

            if not other_bodies:
                # All selected bodies are Geneva components, no extra gear to stack
                return None

            return {
                "crank_body_name": crank_name,
                "wheel_body_name": wheel_name,
                "geneva_bodies": geneva_bodies,
                "other_bodies": other_bodies,
            }

    return None


def _position_gear_on_geneva(doc, gear, target_body, on_top):
    """Position a gear coaxially on top or bottom of a Geneva component body.

    Only moves the gear — never touches Geneva bodies.
    """
    target_base = target_body.Placement.Base
    target_bbox = target_body.Shape.BoundBox
    gear_bbox = gear.Shape.BoundBox
    gear_height = gear_bbox.ZLength

    if on_top:
        z = target_bbox.ZMax
    else:
        z = target_bbox.ZMin - gear_height

    gear.Placement = App.Placement(
        App.Vector(target_base.x, target_base.y, z),
        gear.Placement.Rotation,
    )


class GenevaStackLocationDialog(QtGui.QDialog):
    """Dialog to choose where to position an extra gear relative to Geneva components.

    Provides live preview — the gear moves in the 3D view as the user
    scrolls through options.
    """

    LOCATIONS = [
        "Top of Wheel",
        "Bottom of Wheel",
        "Top of Crank",
        "Bottom of Crank",
    ]

    def __init__(self, doc, geneva_info, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.geneva_info = geneva_info
        # Save original placements of the extra gears so we can restore on Cancel
        self._orig_placements = {
            g.Name: App.Placement(g.Placement)
            for g in geneva_info["other_bodies"]
        }
        self.setWindowTitle("Geneva Gear Stack Location")

        layout = QtGui.QVBoxLayout(self)

        label = QtGui.QLabel("Position the gear relative to:")
        layout.addWidget(label)

        self.combo = QtGui.QComboBox()
        self.combo.addItems(self.LOCATIONS)
        self.combo.currentIndexChanged.connect(self._preview)
        layout.addWidget(self.combo)

        buttons = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self._cancel)
        layout.addWidget(buttons)

        # Show initial preview
        self._preview()

    def _preview(self):
        """Move the extra gear(s) to the currently selected location."""
        location = self.combo.currentText()
        if "Wheel" in location:
            target_name = self.geneva_info["wheel_body_name"]
        else:
            target_name = self.geneva_info["crank_body_name"]

        target_body = self.doc.getObject(target_name)
        if target_body is None:
            return

        on_top = location.startswith("Top")

        for gear in self.geneva_info["other_bodies"]:
            _position_gear_on_geneva(self.doc, gear, target_body, on_top)

        self.doc.recompute()

    def _cancel(self):
        """Restore original gear placements and reject."""
        for gear in self.geneva_info["other_bodies"]:
            orig = self._orig_placements.get(gear.Name)
            if orig:
                gear.Placement = orig
        self.doc.recompute()
        self.reject()

    def selected_location(self):
        return self.combo.currentText()


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

        geneva_info = _find_geneva_info(doc, bodies)

        if geneva_info:
            # Show live-preview location dialog (only moves extra gears, never Geneva bodies)
            dlg = GenevaStackLocationDialog(doc, geneva_info, FreeCADGui.getMainWindow())
            if dlg.exec_() != QtGui.QDialog.Accepted:
                return

        doc.openTransaction("Create Gear Stack")
        try:
            obj = doc.addObject("Part::FeaturePython", "GearStack")
            GearStack(obj)
            ViewProviderGearStack(obj.ViewObject)

            obj.Gears = bodies
            obj.Gaps = [0.0] * (len(bodies) - 1)

            # Geneva stacks are pre-positioned — don't restack them
            if geneva_info:
                obj.PrePositioned = True

            # Hide source Bodies so only the stack is visible
            for body in bodies:
                body.ViewObject.Visibility = False

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
