"""Gear Workbench Action Logger

Logs all user actions (gear creation, parameter changes, positioning, stacking)
to a timestamped file for test case documentation.

Usage: Import this module after the workbench is loaded. It patches the relevant
command and result classes to emit log entries.

Log file: ~/GearWorkbench_actions.log

Copyright 2025, Chris Bruner
License LGPL V2.1
"""

import os
import time
import functools
import FreeCAD as App

LOG_FILE = os.path.expanduser("~/GearWorkbench_actions.log")

_session_started = False

VERBOSE = False


def log(msg):
    """Write a timestamped message to the log file and FreeCAD console."""
    global _session_started
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a") as f:
        if not _session_started:
            _session_started = True
            f.write(f"\n{'='*72}\n")
            f.write(f"SESSION START: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*72}\n\n")
        f.write(line + "\n")
    if VERBOSE:
        App.Console.PrintMessage(f"LOG: {line}\n")


def _placement_str(placement):
    """Format a Placement as a short string."""
    b = placement.Base
    r = placement.Rotation
    angles = r.toEuler()
    pos = f"({b.x:.2f}, {b.y:.2f}, {b.z:.2f})"
    if abs(angles[0]) < 0.01 and abs(angles[1]) < 0.01 and abs(angles[2]) < 0.01:
        return f"pos={pos}"
    return f"pos={pos} rot=({angles[0]:.1f}, {angles[1]:.1f}, {angles[2]:.1f})"


def _varset_summary(varset):
    """Summarize key properties of a VarSet."""
    parts = []
    for prop in ["NumberOfTeeth", "Module", "PressureAngle", "PitchAngle",
                 "HelixAngle", "SpiralAngle", "GearType", "FaceWidth",
                 "Height", "PitchDiameter"]:
        if hasattr(varset, prop):
            val = getattr(varset, prop)
            if hasattr(val, "Value"):
                val = val.Value
            parts.append(f"{prop}={val}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Patch gear creation commands
# ---------------------------------------------------------------------------

def _patch_command_activated(command_class, gear_type_name):
    """Wrap a command's Activated method to log gear creation."""
    original = command_class.Activated

    @functools.wraps(original)
    def wrapped(self):
        original(self)
        # After creation, find the most recently created VarSet
        doc = App.ActiveDocument
        if doc:
            # Find the latest varset and body
            varset = None
            body_name = None
            for obj in reversed(doc.Objects):
                if hasattr(obj, "VarSetName") and hasattr(obj, "BodyName"):
                    varset = doc.getObject(str(obj.VarSetName))
                    body_name = str(obj.BodyName)
                    break
            if varset:
                body = doc.getObject(body_name) if body_name else None
                placement = _placement_str(body.Placement) if body else "unknown"
                log(f"CREATE {gear_type_name}: VarSet={varset.Name}, "
                    f"Body={body_name}, {placement}, "
                    f"{_varset_summary(varset)}")
            else:
                log(f"CREATE {gear_type_name}: (could not find VarSet)")

    command_class.Activated = wrapped


def _patch_result_onchanged(result_class, gear_type_name):
    """Wrap a Result class's onChanged to log parameter modifications."""
    if not hasattr(result_class, "onChanged"):
        return  # Newer classes use _VarSetWatcher instead
    original = result_class.onChanged

    @functools.wraps(original)
    def wrapped(self, fp, prop):
        # Skip internal/read-only property changes
        skip_props = {"Shape", "Placement", "Visibility", "Label2",
                      "ExpressionEngine", "Version"}
        if prop not in skip_props:
            # Get the varset to read the new value
            varset = None
            if hasattr(self, "_varset") and self._varset:
                varset = self._varset
            elif hasattr(fp, "VarSetName"):
                doc = fp.Document
                if doc:
                    varset = doc.getObject(str(fp.VarSetName))

            body_name = str(fp.BodyName) if hasattr(fp, "BodyName") else "?"

            if varset and hasattr(varset, prop):
                val = getattr(varset, prop)
                if hasattr(val, "Value"):
                    val = val.Value
                log(f"MODIFY {gear_type_name} ({body_name}): {prop} = {val}")
            elif prop == "BodyName":
                log(f"RENAME {gear_type_name}: BodyName = {body_name}")

        original(self, fp, prop)

    result_class.onChanged = wrapped


# ---------------------------------------------------------------------------
# Patch positioning command
# ---------------------------------------------------------------------------

def _patch_positioning():
    """Patch GearPositioningCommand to log positioning actions."""
    try:
        from . import gearPositioning
        original = gearPositioning.GearPositioningCommand.Activated

        @functools.wraps(original)
        def wrapped(self):
            import FreeCADGui
            sel = FreeCADGui.Selection.getSelection()
            if len(sel) == 2:
                doc = App.ActiveDocument
                info1 = gearPositioning.getGearInfo(doc, sel[0])
                info2 = gearPositioning.getGearInfo(doc, sel[1])
                if info1 and info2:
                    log(f"POSITION requested: Body1={sel[0].Name} "
                        f"(PD={info1['pd']:.3f}, bevel={info1['is_bevel']}, "
                        f"pitch_angle={info1['pitch_angle']:.1f}), "
                        f"Body2={sel[1].Name} "
                        f"(PD={info2['pd']:.3f}, bevel={info2['is_bevel']}, "
                        f"pitch_angle={info2['pitch_angle']:.1f})")
                else:
                    log(f"POSITION requested: Body1={sel[0].Name}, Body2={sel[1].Name}")
            original(self)

        gearPositioning.GearPositioningCommand.Activated = wrapped

        # Patch the dialog's close to log final position state
        original_close = gearPositioning.GearPositionDialog.close

        @functools.wraps(original_close)
        def wrapped_close(self):
            mode = self._mode
            angle = self.angle_spin.value()
            phase = self.phase_spin.value()
            placement = _placement_str(self.body2.Placement)
            log(f"POSITION final ({mode}): fixed={self.body1.Name}, "
                f"moving={self.body2.Name}, angle={angle:.2f}, "
                f"phase={phase:.2f}, {placement}")
            return original_close(self)

        gearPositioning.GearPositionDialog.close = wrapped_close
    except Exception as e:
        App.Console.PrintWarning(f"gearLog: Could not patch positioning: {e}\n")


# ---------------------------------------------------------------------------
# Patch gear stack command
# ---------------------------------------------------------------------------

def _patch_gearstack():
    """Patch GearStackCommand to log stacking actions."""
    try:
        from . import gearStack
        if hasattr(gearStack, "GearStackCommand"):
            original = gearStack.GearStackCommand.Activated

            @functools.wraps(original)
            def wrapped(self):
                import FreeCADGui
                sel = FreeCADGui.Selection.getSelection()
                body_names = [obj.Name for obj in sel
                              if hasattr(obj, "TypeId") and obj.TypeId == "PartDesign::Body"]
                log(f"GEARSTACK requested: Bodies={body_names}")
                original(self)
                log(f"GEARSTACK created with {len(body_names)} gears")

            gearStack.GearStackCommand.Activated = wrapped
    except Exception as e:
        App.Console.PrintWarning(f"gearLog: Could not patch gearStack: {e}\n")


# ---------------------------------------------------------------------------
# Install all patches
# ---------------------------------------------------------------------------

def install():
    """Install logging patches on all gear commands and result classes."""
    # Install logging patches silently; only log failures.

    try:
        from . import genericGear
        _patch_command_activated(genericGear.GearCommand, "Gear")
        _patch_result_onchanged(genericGear.GearResult, "Gear")
        if hasattr(genericGear, "SpurGearCommand"):
            _patch_command_activated(genericGear.SpurGearCommand, "SpurGear")
        if hasattr(genericGear, "HelixGearCommand"):
            _patch_command_activated(genericGear.HelixGearCommand, "HelixGear")
        if hasattr(genericGear, "HerringboneGearCommand"):
            _patch_command_activated(genericGear.HerringboneGearCommand, "HerringboneGear")
        pass
    except Exception as e:
        log(f"  FAILED genericGear: {e}")

    try:
        from . import bevelGear
        _patch_command_activated(bevelGear.BevelGearCreateObject, "BevelGear")
        _patch_result_onchanged(bevelGear.BevelGearResult, "BevelGear")
        pass
    except Exception as e:
        log(f"  FAILED bevelGear: {e}")

    try:
        from . import genericInternalGear
        if hasattr(genericInternalGear, "InternalGearCommand"):
            _patch_command_activated(genericInternalGear.InternalGearCommand, "InternalGear")
        if hasattr(genericInternalGear, "InternalGearResult"):
            _patch_result_onchanged(genericInternalGear.InternalGearResult, "InternalGear")
        pass
    except Exception as e:
        log(f"  FAILED genericInternalGear: {e}")

    try:
        from . import cycloidGear
        _patch_command_activated(cycloidGear.CycloidGearCreateObject, "CycloidGear")
        _patch_result_onchanged(cycloidGear.CycloidGearResult, "CycloidGear")
        pass
    except Exception as e:
        log(f"  FAILED cycloidGear: {e}")

    try:
        from . import crownGear
        _patch_command_activated(crownGear.CrownGearCreateObject, "CrownGear")
        _patch_result_onchanged(crownGear.CrownGearResult, "CrownGear")
        pass
    except Exception as e:
        log(f"  FAILED crownGear: {e}")

    try:
        from . import screwGear
        _patch_command_activated(screwGear.ScrewGearCreateObject, "ScrewGear")
        _patch_result_onchanged(screwGear.ScrewGearResult, "ScrewGear")
        pass
    except Exception as e:
        log(f"  FAILED screwGear: {e}")

    try:
        from . import hypoidGear
        _patch_command_activated(hypoidGear.HypoidGearCreateObject, "HypoidGear")
        _patch_result_onchanged(hypoidGear.HypoidGearResult, "HypoidGear")
        pass
    except Exception as e:
        log(f"  FAILED hypoidGear: {e}")

    try:
        from . import nonCircularGear
        _patch_command_activated(nonCircularGear.NonCircularGearCreateObject, "NonCircularGear")
        _patch_result_onchanged(nonCircularGear.NonCircularGearResult, "NonCircularGear")
        pass
    except Exception as e:
        log(f"  FAILED nonCircularGear: {e}")

    # Patch the central _VarSetWatcher to log all parameter changes
    try:
        from . import genericGear
        watcher_cls = genericGear._VarSetWatcher
        original_slot = watcher_cls.slotChangedObject

        @functools.wraps(original_slot)
        def wrapped_slot(self, obj, prop):
            if obj.Name == self._varset_name and prop in self._watched:
                try:
                    val = getattr(obj, prop, "?")
                    if hasattr(val, "Value"):
                        val = val.Value
                    # Find body name from the generator
                    body_name = "?"
                    gen = self._generator
                    try:
                        if hasattr(gen, "Object") and gen.Object is not None:
                            body_name = str(gen.Object.BodyName)
                    except (ReferenceError, AttributeError):
                        pass
                    log(f"MODIFY ({body_name}): {prop} = {val}")
                except (ReferenceError, RuntimeError):
                    pass
            original_slot(self, obj, prop)

        watcher_cls.slotChangedObject = wrapped_slot
        pass
    except Exception as e:
        log(f"  FAILED _VarSetWatcher: {e}")

    _patch_positioning()
    _patch_gearstack()


# Auto-install when imported
install()
