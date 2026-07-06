#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cycloidal Gearbox Creator

Creates complete cycloidal gearbox systems via a dialog interface,
using VarSet/Result pattern consistent with the rest of GearWorkBench.
Delegates part generation to CycloidGearBox/cycloidFun.py.

Copyright 2025, Chris Bruner
License LGPL V2.1
"""

import math
import os
import sys
import FreeCAD as App

try:
    import FreeCADGui
    from PySide import QtCore, QtGui
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

# Get icons path
smWB_icons_path = os.path.join(os.path.dirname(__file__), "icons")

# Import cycloidFun from sibling CycloidGearBox module
_cycloid_mod_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CycloidGearBox")
if _cycloid_mod_path not in sys.path:
    sys.path.insert(0, _cycloid_mod_path)
import cycloidFun


def QT_TRANSLATE_NOOP(scope, text):
    return text


# ============================================================================
# VarSet Creation
# ============================================================================

def createCycloidGearBoxVarSet(doc, name, params):
    """Create a VarSet (Spreadsheet) for cycloidal gearbox parameters.

    Args:
        doc: FreeCAD document
        name: Name for the VarSet object
        params: Dict with user-chosen parameter values

    Returns:
        The created App::VarSet object
    """
    var_set = doc.addObject("App::VarSet", name)

    # User-editable parameters
    var_set.addProperty(
        "App::PropertyInteger", "ToothCount", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Number of lobes on cycloidal disk"),
    ).ToothCount = params["tooth_count"]

    var_set.addProperty(
        "App::PropertyLength", "RollerDiameter", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of ring rollers"),
    ).RollerDiameter = params["roller_diameter"]

    var_set.addProperty(
        "App::PropertyLength", "RollerCircleDiameter", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "PCD of ring rollers"),
    ).RollerCircleDiameter = params["roller_circle_diameter"]

    var_set.addProperty(
        "App::PropertyLength", "Eccentricity", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Eccentric offset"),
    ).Eccentricity = params["eccentricity"]

    var_set.addProperty(
        "App::PropertyInteger", "DriverPinCount", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Number of output coupling pins"),
    ).DriverPinCount = params["driver_disk_hole_count"]

    var_set.addProperty(
        "App::PropertyLength", "DriverPinDiameter", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Diameter of driver pins"),
    ).DriverPinDiameter = params["driver_hole_diameter"]

    var_set.addProperty(
        "App::PropertyInteger", "LineSegments", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Resolution of cycloidal profile"),
    ).LineSegments = params["line_segment_count"]

    var_set.addProperty(
        "App::PropertyLength", "DiskThickness", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Thickness of cycloidal disk"),
    ).DiskThickness = params["disk_height"]

    var_set.addProperty(
        "App::PropertyFloat", "Backlash", "CycloidGearBox",
        QT_TRANSLATE_NOOP("App::Property", "Clearance between mating parts"),
    ).Backlash = params.get("backlash", 0.25)

    # Auto-calculated read-only properties
    var_set.addProperty(
        "App::PropertyFloat", "GearRatio", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Gear ratio = 1/(ToothCount-1)"), 1,
    )
    tc = params["tooth_count"]
    var_set.GearRatio = 1.0 / (tc - 1) if tc > 1 else 0.0

    var_set.addProperty(
        "App::PropertyInteger", "RollerCount", "read only",
        QT_TRANSLATE_NOOP("App::Property", "Number of ring rollers (ToothCount+1)"), 1,
    ).RollerCount = tc + 1

    var_set.addProperty(
        "App::PropertyLength", "DriverCircleDiameter", "read only",
        QT_TRANSLATE_NOOP("App::Property", "PCD of driver pin holes"), 1,
    )
    # Calculated same way as cycloidFun: midway between rollers and shaft
    defaults = cycloidFun.generate_default_parameters()
    driver_circle = params.get("driver_circle_diameter", defaults["driver_circle_diameter"])
    var_set.DriverCircleDiameter = driver_circle

    return var_set


def _varset_to_parameters(vs):
    """Read a CycloidGearBox VarSet and return cycloidFun-compatible parameter dict."""
    defaults = cycloidFun.generate_default_parameters()

    tooth_count = int(vs.ToothCount)
    roller_diameter = float(vs.RollerDiameter.Value)
    roller_circle_diameter = float(vs.RollerCircleDiameter.Value)
    eccentricity = float(vs.Eccentricity.Value)
    driver_disk_hole_count = int(vs.DriverPinCount)
    driver_hole_diameter = float(vs.DriverPinDiameter.Value)
    line_segment_count = int(vs.LineSegments)
    disk_height = float(vs.DiskThickness.Value)
    backlash = float(vs.Backlash)

    # Derive dependent parameters from the 8 user params + defaults
    shaft_diameter = defaults["shaft_diameter"]
    clearance = backlash

    # Scale the entire gear system proportionally to eccentricity.
    # The default geometry is designed for eccentricity=2 with roller_circle_diameter=80.
    # For larger eccentricity, scale roller_circle_diameter (and roller_diameter) up
    # to maintain proper tooth geometry and prevent hole overlap.
    default_ecc = defaults["eccentricity"]  # 2.0
    default_rcd = defaults["roller_circle_diameter"]  # 80.0
    default_rd = defaults["roller_diameter"]  # 9.4

    # Scale factor: how much larger is eccentricity vs the default design?
    ecc_scale = eccentricity / default_ecc

    # Minimum roller_circle_diameter to maintain geometry at this eccentricity
    min_rcd = default_rcd * ecc_scale
    if roller_circle_diameter < min_rcd:
        scale = min_rcd / roller_circle_diameter
        roller_circle_diameter = min_rcd
        roller_diameter = roller_diameter * scale

    # Compute min/max radii with (potentially scaled) parameters
    temp_params = {
        "roller_circle_diameter": roller_circle_diameter,
        "tooth_count": tooth_count,
        "roller_diameter": roller_diameter,
        "pressure_angle_limit": defaults["pressure_angle_limit"],
        "eccentricity": eccentricity,
    }
    min_rad, max_rad = cycloidFun.calculate_min_max_radii(temp_params)

    # The enlarged driver holes must not overlap on the driver circle.
    # Hole diameter in cycloidal disk = driver_hole_diameter + 2*eccentricity
    # Adjacent hole spacing = 2*r*sin(pi/n); must exceed hole diameter
    enlarged_hole_diam = driver_hole_diameter + 2 * eccentricity
    min_driver_circle_r = enlarged_hole_diam / (2 * math.sin(math.pi / driver_disk_hole_count)) + 1.0

    # Center hole in cycloidal disk extends to:
    center_hole_outer = eccentricity + (shaft_diameter + clearance) / 2
    # Driver holes must also clear the center hole:
    min_driver_circle_r = max(min_driver_circle_r, center_hole_outer + enlarged_hole_diam / 2 + 1.0)

    # Housing diameter: add 2*eccentricity for disk oscillation clearance
    diameter = roller_circle_diameter + 2 * roller_diameter + 2 * eccentricity + 5.0

    # Place driver circle: respect outer limit (disk edge) and overlap limit
    driver_hole_outer_r = enlarged_hole_diam / 2
    outer_limit = (min_rad - driver_hole_outer_r - 1.0) * 2
    inner_limit = (center_hole_outer + driver_hole_outer_r + 1.0) * 2
    overlap_limit = min_driver_circle_r * 2
    driver_circle_diameter = min(outer_limit, max(overlap_limit, inner_limit, (inner_limit + outer_limit) / 2))

    # base_height: use disk_height * 2 as reasonable default
    base_height = disk_height * 2.0

    parameters = {
        "tooth_count": tooth_count,
        "roller_diameter": roller_diameter,
        "roller_circle_diameter": roller_circle_diameter,
        "eccentricity": eccentricity,
        "driver_disk_hole_count": driver_disk_hole_count,
        "driver_hole_diameter": driver_hole_diameter,
        "line_segment_count": line_segment_count,
        "disk_height": disk_height,
        "Diameter": diameter,
        "driver_circle_diameter": driver_circle_diameter,
        "tooth_pitch": defaults["tooth_pitch"],
        "pressure_angle_limit": defaults["pressure_angle_limit"],
        "pressure_angle_offset": defaults["pressure_angle_offset"],
        "base_height": base_height,
        "shaft_diameter": shaft_diameter,
        "key_diameter": defaults["key_diameter"],
        "key_flat_diameter": defaults["key_flat_diameter"],
        "Height": base_height + disk_height * 2,
        "clearance": backlash,
    }
    return parameters


# ============================================================================
# Result Class (FeaturePython proxy)
# ============================================================================

class CycloidGearBoxResult:
    """FeaturePython proxy that rebuilds the cycloidal gearbox when VarSet changes.

    Uses _VarSetWatcher from genericGear pattern for property change monitoring.
    """

    def __init__(self, obj, varset):
        self._varset = varset
        self._rebuilding = False
        self._watcher = None
        self._debounce_timer = None
        self._needs_rebuild = False
        self._last_values = None
        self.Type = "CycloidGearBoxResult"

        obj.addProperty(
            "App::PropertyString", "VarSetName", "CycloidGearBox",
            QT_TRANSLATE_NOOP("App::Property", "Name of parameter VarSet"), 1,
        ).VarSetName = varset.Name

        obj.addProperty(
            "App::PropertyString", "Status", "read only",
            QT_TRANSLATE_NOOP("App::Property", "Regeneration status"), 1,
        )

        obj.Proxy = self
        self.Object = obj
        obj.Status = "Not yet generated"
        self._snapshot_values(varset)
        self._startWatcher(varset.Name)

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state
        self._varset = None
        self._rebuilding = False
        self._watcher = None
        self._needs_rebuild = False
        self._last_values = None

    def onDocumentRestored(self, obj):
        self.Object = obj
        v = self._getVarSet()
        if v:
            self._snapshot_values(v)
            self._startWatcher(v.Name)
            obj.Status = "Up to date"

    def _snapshot_values(self, vs):
        """Take a snapshot of current VarSet values for change detection."""
        try:
            self._last_values = (
                int(vs.ToothCount),
                float(vs.RollerDiameter.Value),
                float(vs.RollerCircleDiameter.Value),
                float(vs.Eccentricity.Value),
                int(vs.DriverPinCount),
                float(vs.DriverPinDiameter.Value),
                int(vs.LineSegments),
                float(vs.DiskThickness.Value),
                float(vs.Backlash),
            )
        except (AttributeError, ReferenceError):
            self._last_values = None

    def _current_values(self, vs):
        """Get current VarSet values as a tuple."""
        return (
            int(vs.ToothCount),
            float(vs.RollerDiameter.Value),
            float(vs.RollerCircleDiameter.Value),
            float(vs.Eccentricity.Value),
            int(vs.DriverPinCount),
            float(vs.DriverPinDiameter.Value),
            int(vs.LineSegments),
            float(vs.DiskThickness.Value),
            float(vs.Backlash),
        )

    def _values_changed(self):
        v = self._getVarSet()
        if not v:
            return False
        if self._last_values is None:
            return True
        try:
            current = self._current_values(v)
        except ReferenceError:
            self._varset = None
            return False
        return current != self._last_values

    def _startWatcher(self, varset_name):
        self._stopWatcher()
        from genericGear import _VarSetWatcher
        self._watcher = _VarSetWatcher(
            self, varset_name,
            watched=frozenset((
                "ToothCount", "RollerDiameter", "RollerCircleDiameter",
                "Eccentricity", "DriverPinCount", "DriverPinDiameter",
                "LineSegments", "DiskThickness", "Backlash",
            )),
        )
        App.addDocumentObserver(self._watcher)

    def _stopWatcher(self):
        if self._watcher:
            try:
                App.removeDocumentObserver(self._watcher)
            except Exception:
                pass
            self._watcher = None

    def _getVarSet(self):
        if self._varset is not None:
            try:
                _ = self._varset.Name
            except ReferenceError:
                self._varset = None
        if self._varset is None:
            try:
                name = self.Object.VarSetName
                self._varset = self.Object.Document.getObject(name)
            except (AttributeError, ReferenceError):
                pass
        return self._varset

    def execute(self, obj):
        pass

    def _set_needs_rebuild(self):
        if self._rebuilding:
            return
        if not self._values_changed():
            return
        self._needs_rebuild = True
        try:
            self.Object.Status = "Regenerating..."
        except Exception:
            pass
        self._restart_debounce()

    def _restart_debounce(self):
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer.deleteLater()
        self._debounce_timer = QtCore.QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._deferred_rebuild)
        self._debounce_timer.start(600)

    def _on_recompute_finished(self):
        if not self._needs_rebuild:
            return
        if self._rebuilding:
            return
        if not self._values_changed():
            self._needs_rebuild = False
            return
        self._needs_rebuild = False
        self._restart_debounce()

    def _deferred_rebuild(self):
        if self._rebuilding:
            return
        if not self._values_changed():
            return
        self._rebuild()

    def _rebuild(self):
        self._rebuilding = True
        varset_name = None
        try:
            v = self._getVarSet()
            if not v:
                return
            varset_name = v.Name

            # Update read-only computed properties
            tc = int(v.ToothCount)
            v.GearRatio = 1.0 / (tc - 1) if tc > 1 else 0.0
            v.RollerCount = tc + 1

            self._snapshot_values(v)
            parameters = _varset_to_parameters(v)

            # Update read-only DriverCircleDiameter to reflect computed value
            v.DriverCircleDiameter = parameters["driver_circle_diameter"]

            self._stopWatcher()

            self.Object.Status = "Generating cycloidal gearbox..."
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()

            doc = self.Object.Document
            cycloidFun.generate_parts(doc, parameters)

            self.Object.Status = "Up to date"
            if App.GuiUp:
                QtCore.QCoreApplication.processEvents()
        except cycloidFun.ParameterValidationError as e:
            App.Console.PrintError(f"Cycloidal Gearbox Parameter Error: {str(e)}\n")
            self.Object.Status = f"Error: {str(e)}"
        except Exception as e:
            import traceback
            App.Console.PrintError(traceback.format_exc())
            self.Object.Status = "Error"
        finally:
            if varset_name:
                self._startWatcher(varset_name)
            self._rebuilding = False

    def force_Recompute(self):
        self._rebuild()


class ViewProviderCycloidGearBoxResult:
    """View provider for CycloidGearBoxResult objects."""

    def __init__(self, obj, iconfile=None):
        obj.Proxy = self
        self.part = obj
        self.iconfile = (
            iconfile if iconfile else os.path.join(smWB_icons_path, "cycloidalGear.svg")
        )

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

    def setupContextMenu(self, vobj, menu):
        action = QtGui.QAction("Regenerate Cycloidal Gearbox", menu)
        action.triggered.connect(lambda: self.regenerate())
        menu.addAction(action)

    def regenerate(self):
        if hasattr(self.Object, "Proxy"):
            self.Object.Proxy.force_Recompute()

    def __getstate__(self):
        return self.iconfile

    def __setstate__(self, state):
        if state:
            self.iconfile = state
        else:
            self.iconfile = os.path.join(smWB_icons_path, "cycloidalGear.svg")
        return None


# ============================================================================
# Dialog Class
# ============================================================================

if GUI_AVAILABLE:
    class CycloidGearBoxDialog(QtGui.QDialog):
        """Dialog for creating cycloidal gearbox systems."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.accepted_params = None
            self.setupUI()

        def setupUI(self):
            self.setWindowTitle("Cycloidal Gearbox Creator")
            self.setMinimumWidth(450)
            self.setModal(True)

            defaults = cycloidFun.generate_default_parameters()

            layout = QtGui.QVBoxLayout()

            # Title
            title_label = QtGui.QLabel("Cycloidal Gearbox Creator")
            title_label.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
            layout.addWidget(title_label)

            # Parameters group
            params_group = QtGui.QGroupBox("Gearbox Parameters")
            params_layout = QtGui.QGridLayout()
            row = 0

            # Tooth Count
            params_layout.addWidget(QtGui.QLabel("Tooth Count:"), row, 0)
            self.tooth_count_spin = QtGui.QSpinBox()
            self.tooth_count_spin.setRange(4, 50)
            self.tooth_count_spin.setValue(defaults["tooth_count"])
            self.tooth_count_spin.setToolTip("Number of lobes on cycloidal disk (ratio = 1/(n-1))")
            params_layout.addWidget(self.tooth_count_spin, row, 1)
            self.ratio_label = QtGui.QLabel()
            params_layout.addWidget(self.ratio_label, row, 2)
            row += 1

            # Roller Diameter
            params_layout.addWidget(QtGui.QLabel("Roller Diameter:"), row, 0)
            self.roller_diameter_spin = QtGui.QDoubleSpinBox()
            self.roller_diameter_spin.setRange(0.5, 100.0)
            self.roller_diameter_spin.setValue(defaults["roller_diameter"])
            self.roller_diameter_spin.setDecimals(2)
            self.roller_diameter_spin.setSuffix(" mm")
            params_layout.addWidget(self.roller_diameter_spin, row, 1)
            row += 1

            # Roller Circle Diameter
            params_layout.addWidget(QtGui.QLabel("Roller Circle Diameter:"), row, 0)
            self.roller_circle_spin = QtGui.QDoubleSpinBox()
            self.roller_circle_spin.setRange(10.0, 500.0)
            self.roller_circle_spin.setValue(defaults["roller_circle_diameter"])
            self.roller_circle_spin.setDecimals(1)
            self.roller_circle_spin.setSuffix(" mm")
            self.roller_circle_spin.setToolTip("Pitch circle diameter of ring rollers")
            params_layout.addWidget(self.roller_circle_spin, row, 1)
            row += 1

            # Eccentricity
            params_layout.addWidget(QtGui.QLabel("Eccentricity:"), row, 0)
            self.eccentricity_spin = QtGui.QDoubleSpinBox()
            self.eccentricity_spin.setRange(0.1, 50.0)
            self.eccentricity_spin.setValue(defaults["eccentricity"])
            self.eccentricity_spin.setDecimals(2)
            self.eccentricity_spin.setSuffix(" mm")
            self.eccentricity_spin.setToolTip("Eccentric offset (should be <= roller_diameter/2)")
            params_layout.addWidget(self.eccentricity_spin, row, 1)
            row += 1

            # Driver Pin Count
            params_layout.addWidget(QtGui.QLabel("Driver Pin Count:"), row, 0)
            self.driver_pin_count_spin = QtGui.QSpinBox()
            self.driver_pin_count_spin.setRange(3, 20)
            self.driver_pin_count_spin.setValue(defaults["driver_disk_hole_count"])
            self.driver_pin_count_spin.setToolTip("Number of output coupling pins")
            params_layout.addWidget(self.driver_pin_count_spin, row, 1)
            row += 1

            # Driver Pin Diameter
            params_layout.addWidget(QtGui.QLabel("Driver Pin Diameter:"), row, 0)
            self.driver_pin_diameter_spin = QtGui.QDoubleSpinBox()
            self.driver_pin_diameter_spin.setRange(1.0, 50.0)
            self.driver_pin_diameter_spin.setValue(defaults["driver_hole_diameter"])
            self.driver_pin_diameter_spin.setDecimals(1)
            self.driver_pin_diameter_spin.setSuffix(" mm")
            params_layout.addWidget(self.driver_pin_diameter_spin, row, 1)
            row += 1

            # Line Segments
            params_layout.addWidget(QtGui.QLabel("Line Segments:"), row, 0)
            self.line_segments_spin = QtGui.QSpinBox()
            self.line_segments_spin.setRange(20, 2000)
            self.line_segments_spin.setValue(400)
            self.line_segments_spin.setToolTip("Resolution of cycloidal profile curve")
            params_layout.addWidget(self.line_segments_spin, row, 1)
            row += 1

            # Disk Thickness
            params_layout.addWidget(QtGui.QLabel("Disk Thickness:"), row, 0)
            self.disk_thickness_spin = QtGui.QDoubleSpinBox()
            self.disk_thickness_spin.setRange(1.0, 100.0)
            self.disk_thickness_spin.setValue(defaults["disk_height"])
            self.disk_thickness_spin.setDecimals(1)
            self.disk_thickness_spin.setSuffix(" mm")
            params_layout.addWidget(self.disk_thickness_spin, row, 1)
            row += 1

            # Backlash
            params_layout.addWidget(QtGui.QLabel("Backlash:"), row, 0)
            self.backlash_spin = QtGui.QDoubleSpinBox()
            self.backlash_spin.setRange(0.0, 2.0)
            self.backlash_spin.setValue(0.25)
            self.backlash_spin.setDecimals(3)
            self.backlash_spin.setSuffix(" mm")
            self.backlash_spin.setToolTip("Clearance between mating parts")
            params_layout.addWidget(self.backlash_spin, row, 1)
            row += 1

            params_group.setLayout(params_layout)
            layout.addWidget(params_group)

            # Computed info group
            info_group = QtGui.QGroupBox("Computed Values")
            info_layout = QtGui.QGridLayout()
            info_layout.addWidget(QtGui.QLabel("Gear Ratio:"), 0, 0)
            self.gear_ratio_label = QtGui.QLabel()
            self.gear_ratio_label.setStyleSheet("font-weight: bold;")
            info_layout.addWidget(self.gear_ratio_label, 0, 1)
            info_layout.addWidget(QtGui.QLabel("Roller Count:"), 1, 0)
            self.roller_count_label = QtGui.QLabel()
            self.roller_count_label.setStyleSheet("font-weight: bold;")
            info_layout.addWidget(self.roller_count_label, 1, 1)
            info_group.setLayout(info_layout)
            layout.addWidget(info_group)

            # Validation label
            self.validation_label = QtGui.QLabel("")
            self.validation_label.setStyleSheet("color: green; font-weight: bold; margin-top: 5px;")
            layout.addWidget(self.validation_label)

            # Buttons
            button_layout = QtGui.QHBoxLayout()
            self.create_btn = QtGui.QPushButton("Create Cycloidal Gearbox")
            self.create_btn.setStyleSheet(
                "background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;"
            )
            self.create_btn.clicked.connect(self.onAccept)
            button_layout.addWidget(self.create_btn)

            cancel_btn = QtGui.QPushButton("Cancel")
            cancel_btn.clicked.connect(self.reject)
            button_layout.addWidget(cancel_btn)

            layout.addLayout(button_layout)
            self.setLayout(layout)

            # Connect signals for live validation
            self.tooth_count_spin.valueChanged.connect(self.updateComputed)
            self.roller_diameter_spin.valueChanged.connect(self.updateComputed)
            self.roller_circle_spin.valueChanged.connect(self.updateComputed)
            self.eccentricity_spin.valueChanged.connect(self.updateComputed)

            # Initial update
            self.updateComputed()

        def updateComputed(self):
            """Update computed labels and validate parameters."""
            tc = self.tooth_count_spin.value()
            ratio = 1.0 / (tc - 1) if tc > 1 else 0.0
            self.gear_ratio_label.setText(f"1:{tc - 1} ({ratio:.4f})")
            self.roller_count_label.setText(str(tc + 1))
            self.ratio_label.setText(f"(ratio 1:{tc - 1})")

            # Basic validation
            ecc = self.eccentricity_spin.value()
            roller_r = self.roller_diameter_spin.value() / 2.0
            roller_circle = self.roller_circle_spin.value()
            roller_d = self.roller_diameter_spin.value()

            errors = []
            if ecc > roller_r:
                errors.append(f"Eccentricity ({ecc}) > roller radius ({roller_r})")
            if roller_circle <= roller_d:
                errors.append("Roller circle diameter must be > roller diameter")

            if errors:
                self.validation_label.setText("\n".join(errors))
                self.validation_label.setStyleSheet("color: red; font-weight: bold;")
                self.create_btn.setEnabled(False)
            else:
                self.validation_label.setText("Parameters OK")
                self.validation_label.setStyleSheet("color: green; font-weight: bold;")
                self.create_btn.setEnabled(True)

        def onAccept(self):
            """Collect parameters and close dialog."""
            defaults = cycloidFun.generate_default_parameters()
            self.accepted_params = {
                "tooth_count": self.tooth_count_spin.value(),
                "roller_diameter": self.roller_diameter_spin.value(),
                "roller_circle_diameter": self.roller_circle_spin.value(),
                "eccentricity": self.eccentricity_spin.value(),
                "driver_disk_hole_count": self.driver_pin_count_spin.value(),
                "driver_hole_diameter": self.driver_pin_diameter_spin.value(),
                "line_segment_count": self.line_segments_spin.value(),
                "disk_height": self.disk_thickness_spin.value(),
                "backlash": self.backlash_spin.value(),
                "driver_circle_diameter": defaults["driver_circle_diameter"],
            }
            self.accept()


# ============================================================================
# Command Class
# ============================================================================

class CycloidalGearBoxCreatorCommand:
    """Command to create cycloidal gearbox systems."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "cycloidalGear.svg"),
            "MenuText": "&Cycloidal Gearbox",
            "ToolTip": "Create a complete cycloidal gearbox system",
        }

    def __init__(self):
        pass

    def Activated(self):
        doc = App.ActiveDocument
        if not doc:
            doc = App.newDocument()

        if not GUI_AVAILABLE:
            App.Console.PrintError("GUI not available. Cannot show dialog.\n")
            return

        dialog = CycloidGearBoxDialog(FreeCADGui.getMainWindow())

        if dialog.exec_() == QtGui.QDialog.Accepted and dialog.accepted_params:
            params = dialog.accepted_params
            try:
                # Create VarSet
                vs_name = "CycloidGearBox_values"
                count = 1
                while doc.getObject(vs_name):
                    vs_name = f"CycloidGearBox_values{count:03d}"
                    count += 1
                varset = createCycloidGearBoxVarSet(doc, vs_name, params)

                # Create Result FeaturePython
                gen_name = "Regenerate_CycloidGearBox"
                count = 1
                while doc.getObject(gen_name):
                    gen_name = f"Regenerate_CycloidGearBox{count:03d}"
                    count += 1
                result_obj = doc.addObject("Part::FeaturePython", gen_name)
                CycloidGearBoxResult(result_obj, varset)
                ViewProviderCycloidGearBoxResult(
                    result_obj.ViewObject,
                    os.path.join(smWB_icons_path, "cycloidalGear.svg"),
                )

                # Generate the gearbox
                result_obj.Proxy.force_Recompute()

                doc.recompute()
                if GUI_AVAILABLE:
                    FreeCADGui.SendMsgToActiveView("ViewFit")
                    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
                App.Console.PrintMessage("Cycloidal gearbox created successfully!\n")
            except Exception as e:
                App.Console.PrintError(f"Failed to create cycloidal gearbox: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())
                if GUI_AVAILABLE:
                    QtGui.QMessageBox.critical(
                        None, "Error",
                        f"Failed to create cycloidal gearbox:\n\n{str(e)}"
                    )

    def IsActive(self):
        return True

    def Deactivated(self):
        pass

    def execute(self, obj):
        pass


# Register command
if GUI_AVAILABLE:
    try:
        FreeCADGui.addCommand("CycloidalGearBoxCreatorCommand", CycloidalGearBoxCreatorCommand())
    except Exception:
        pass
