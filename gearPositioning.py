"""Gear Positioning Tool for GearWorkbench

This module provides a dialog-based tool to position two gears beside each other
for proper meshing.

Copyright 2025, Chris Bruner
License LGPL V2.1
"""

import os
import math
import FreeCAD as App
import FreeCADGui
import Part
import Sketcher
import util
from PySide import QtCore, QtGui
from typing import List, Dict, Optional

smWBpath = os.path.dirname(os.path.abspath(__file__))
smWB_icons_path = os.path.join(smWBpath, "icons")


class GearPositionDialog(QtGui.QDialog):
    """Dialog for selecting and positioning two gears."""

    def __init__(self, gears: List[Dict], parent=None):
        super().__init__(parent)
        self.gears = gears
        self.preview_body = None
        self.preview_objects = []
        self.original_gear2_positions = {}
        self.preview_counter = 0
        self.preview_prefix = "Preview"
        self.setupUI()
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

    def getGearSpecs(self, gear_info: Dict) -> Dict:
        """Get gear specifications from parameter object.

        Args:
            gear_info: Dictionary containing gear information

        Returns:
            Dictionary with module, pressure_angle, helix_angle, and gear_type
        """
        # Use the module-level function
        return getGearSpecs(gear_info)

    def areGearsCompatible(self, gear1_info: Dict, gear2_info: Dict) -> bool:
        """Check if two gears are compatible for meshing.

        Args:
            gear1_info: First gear information
            gear2_info: Second gear information

        Returns:
            True if gears are compatible, False otherwise
        """
        specs1 = self.getGearSpecs(gear1_info)
        specs2 = self.getGearSpecs(gear2_info)

        module_diff = abs(specs1["module"] - specs2["module"])
        pressure_diff = abs(specs1["pressure_angle"] - specs2["pressure_angle"])

        module_compatible = module_diff < 0.001
        pressure_compatible = pressure_diff < 0.001

        if not (module_compatible and pressure_compatible):
            return False

        type1 = specs1["gear_type"]
        type2 = specs2["gear_type"]
        helix1 = specs1["helix_angle"]
        helix2 = specs2["helix_angle"]

        if type1 == "spur" and type2 == "spur":
            return True

        if type1 == "helical" and type2 == "helical":
            # Compare magnitudes since gears can be used upside down or right-side up
            helix_diff = abs(abs(helix1) - abs(helix2))
            return helix_diff < 1.0

        if type1 == "herringbone" and type2 == "herringbone":
            # Compare magnitudes since gears can be used upside down or right-side up
            helix_diff = abs(abs(helix1) - abs(helix2))
            return helix_diff < 1.0

        if (type1 == "spur" or type2 == "spur") and (
            type1 != "spur" or type2 != "spur"
        ):
            return False

        if (type1 == "helical" or type2 == "helical") and (
            type1 != "helical" or type2 != "helical"
        ):
            return False

        if (type1 == "herringbone" or type2 == "herringbone") and (
            type1 != "herringbone" or type2 != "herringbone"
        ):
            return False

        return False

    def moveAndFinalize(self):
        """Move gear 1 to final position and delete preview."""
        idx1 = self.gear1_combo.currentIndex()
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())

        if idx1 < 0 or idx2_data is None:
            App.Console.PrintError("Invalid gear selection\n")
            return

        gear1_info = self.gears[idx1]
        gear2_info = self.gears[idx2_data]

        # Re-fetch bodies from document to ensure they're valid
        doc = App.ActiveDocument
        if not doc:
            App.Console.PrintError("No active document\n")
            return

        gear1_param = gear1_info["param_obj"]
        gear2_param = gear2_info["param_obj"]

        gear1_body_name = gear1_param.BodyName if hasattr(gear1_param, "BodyName") else None
        gear2_body_name = gear2_param.BodyName if hasattr(gear2_param, "BodyName") else None

        if not gear1_body_name or not gear2_body_name:
            App.Console.PrintError("Cannot determine gear body names\n")
            return

        gear1_body = doc.getObject(gear1_body_name)
        gear2_body = doc.getObject(gear2_body_name)

        gear1_valid = gear1_body is not None
        if gear1_valid:
            try:
                gear1_valid = gear1_body.isValid()
            except Exception:
                gear1_valid = False

        gear2_valid = gear2_body is not None
        if gear2_valid:
            try:
                gear2_valid = gear2_body.isValid()
            except Exception:
                gear2_valid = False

        if not gear1_valid:
            App.Console.PrintError(f"Gear 1 body '{gear1_body_name}' not valid\n")
            return

        if not gear2_valid:
            App.Console.PrintError(f"Gear 2 body '{gear2_body_name}' not valid\n")
            return

        rotation_angle = self.angle_spinbox.value()

        # Check if there's a preview to use
        if self.preview_objects and App.ActiveDocument:
            # Get the latest preview object
            latest_preview_name = self.preview_objects[-1]
            preview_obj = doc.getObject(latest_preview_name)

            preview_valid = preview_obj is not None
            if preview_valid:
                try:
                    preview_valid = preview_obj.isValid()
                except Exception:
                    preview_valid = False

            if preview_valid:
                # Use the preview's placement
                gear1_body.Placement = preview_obj.Placement
            else:
                # No valid preview, recalculate position from angle
                self._calculateAndApplyPosition(gear1_info, gear2_info, rotation_angle, gear2_body, gear1_body)
        else:
            # No preview exists, recalculate position from angle
            self._calculateAndApplyPosition(gear1_info, gear2_info, rotation_angle, gear2_body, gear1_body)

        # Update gear 1 parameter object properties (gear 1 moved, gear 2 is reference)
        if hasattr(gear1_param, "OriginX"):
            gear1_param.OriginX = gear1_body.Placement.Base.x
        if hasattr(gear1_param, "OriginY"):
            gear1_param.OriginY = gear1_body.Placement.Base.y
        if hasattr(gear1_param, "OriginZ"):
            gear1_param.OriginZ = gear1_body.Placement.Base.z
        if hasattr(gear1_param, "Angle"):
            gear1_param.Angle = rotation_angle

        gear1_param.Document.recompute()

        # Clean up all previews
        self.cleanupPreview()

        App.Console.PrintMessage(
            f"Moved '{gear1_body.Name}' to final position at {rotation_angle:.1f}° around '{gear2_body.Name}'\n"
        )

    def _calculateAndApplyPosition(self, gear1_info, gear2_info, rotation_angle, gear1_body, gear2_body):
        """Calculate and apply position for gear1 around gear2 (reference)."""
        import math

        # Validate that bodies still exist
        if not gear1_body or not hasattr(gear1_body, "Placement"):
            App.Console.PrintError("Error: Gear 1 body no longer exists\n")
            return
        if not gear2_body or not hasattr(gear2_body, "Placement"):
            App.Console.PrintError("Error: Gear 2 body no longer exists\n")
            return

        # Gear 2 is center/reference (fixed), Gear 1 moves around it
        center_origin = gear2_body.Placement.Base

        # Get gear specs for center distance calculation
        gear1_specs = self.getGearSpecs(gear1_info)
        gear2_specs = self.getGearSpecs(gear2_info)

        # Calculate center distance
        center_distance = calculateCenterDistance(gear1_info, gear2_info, gear1_specs, gear2_specs)

        # Calculate new position
        angle_rad = rotation_angle * math.pi / 180.0

        dx = center_distance * math.cos(angle_rad)
        dy = center_distance * math.sin(angle_rad)

        new_x = center_origin.x + dx
        new_y = center_origin.y + dy
        new_z = center_origin.z

        # Directly set rotation to angle spinbox value (no complex calculation)
        new_placement = App.Placement(
            App.Vector(new_x, new_y, new_z),
            App.Rotation(App.Vector(0, 0, 1), rotation_angle),
        )

        # Apply to gear1 (the moving gear)
        gear1_body.Placement = new_placement

    def getCompatibleGears(self, selected_gear_idx: int) -> List[int]:
        """Get list of compatible gear indices.

        Args:
            selected_gear_idx: Index of first selected gear

        Returns:
            List of compatible gear indices (excluding selected gear)
        """
        if selected_gear_idx < 0 or selected_gear_idx >= len(self.gears):
            return []

        selected_gear = self.gears[selected_gear_idx]
        compatible_indices = []

        for idx, gear in enumerate(self.gears):
            if idx != selected_gear_idx and self.areGearsCompatible(
                selected_gear, gear
            ):
                compatible_indices.append(idx)

        return compatible_indices

    def updateSecondGearOptions(self):
        """Update second gear dropdown based on first gear selection."""
        gear1_idx = self.gear1_combo.currentIndex()

        self.gear2_combo.clear()

        compatible_indices = self.getCompatibleGears(gear1_idx)

        if not compatible_indices:
            self.gear2_combo.addItem("No compatible gears")
            self.gear2_combo.setEnabled(False)
            self.center_distance_label.setText("Center Distance: N/A")
            self.position_btn.setEnabled(False)

            gear1_specs = self.getGearSpecs(self.gears[gear1_idx])
            type1 = gear1_specs["gear_type"].capitalize()

            message = f"⚠ No compatible gears found. Gear type: {type1}\n"
            message += "Compatible gears must have:\n"
            message += f"- Same module ({gear1_specs['module']:.3f} mm)\n"
            message += f"- Same pressure angle ({gear1_specs['pressure_angle']:.1f}°)\n"

            if type1 == "Spur":
                message += "- Same gear type (only with spur gears)"
            elif type1 == "Helical":
                message += "- Same gear type (only with helical gears)"
            elif type1 == "Herringbone":
                message += "- Same gear type (only with herringbone gears)"

            self.compatibility_label.setText(message)
        else:
            for idx in compatible_indices:
                self.gear2_combo.addItem(self.gears[idx]["label"], idx)

            self.gear2_combo.setEnabled(True)
            self.position_btn.setEnabled(True)

            gear1_specs = self.getGearSpecs(self.gears[gear1_idx])
            type1 = gear1_specs["gear_type"].capitalize()

            self.compatibility_label.setText(
                f"✓ {len(compatible_indices)} compatible {type1} gear(s) found"
            )

            if len(compatible_indices) > 0:
                self.gear2_combo.setCurrentIndex(0)
                self.updateDistance()

    def setupUI(self):
        """Setup dialog UI."""
        self.setWindowTitle("Gear Positioning Tool")
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)
        self.setModal(True)

        layout = QtGui.QVBoxLayout()

        title_label = QtGui.QLabel("Position first gear beside second gear")
        title_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; margin-bottom: 10px;"
        )
        layout.addWidget(title_label)

        gear_label = QtGui.QLabel(f"Found {len(self.gears)} gears in document")
        layout.addWidget(gear_label)

        layout.addSpacing(20)

        gear_names = [g["label"] for g in self.gears]

        layout.addWidget(QtGui.QLabel("First Gear (to be moved):"))
        self.gear1_combo = QtGui.QComboBox()
        self.gear1_combo.addItems(gear_names)
        layout.addWidget(self.gear1_combo)

        layout.addSpacing(10)

        layout.addWidget(QtGui.QLabel("Second Gear (reference):"))
        self.gear2_combo = QtGui.QComboBox()
        layout.addWidget(self.gear2_combo)

        self.compatibility_label = QtGui.QLabel("")
        self.compatibility_label.setStyleSheet(
            "color: #e67e22; font-style: italic; font-size: 11px;"
        )
        layout.addWidget(self.compatibility_label)

        layout.addSpacing(10)

        options_group = QtGui.QGroupBox("Positioning Options")
        options_layout = QtGui.QVBoxLayout()

        self.center_distance_label = QtGui.QLabel("Center Distance: 0.00 mm")
        self.center_distance_label.setStyleSheet("font-weight: bold; color: #0066cc;")
        options_layout.addWidget(self.center_distance_label)

        angle_label = QtGui.QLabel("Position at angle (degrees):")
        self.angle_spinbox = QtGui.QDoubleSpinBox()
        self.angle_spinbox.setRange(0, 360)
        self.angle_spinbox.setValue(0.0)
        self.angle_spinbox.setSuffix("°")
        options_layout.addWidget(angle_label)
        options_layout.addWidget(self.angle_spinbox)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        preview_group = QtGui.QGroupBox("Preview (rotated gear)")
        preview_layout = QtGui.QVBoxLayout()

        self.preview_label = QtGui.QLabel(
            "Semi-transparent copy of gear 2 shows where it would be positioned"
        )
        self.preview_label.setStyleSheet("font-size: 11px; color: #666;")
        preview_layout.addWidget(self.preview_label)

        layout.addSpacing(10)

        info_label = QtGui.QLabel(
            "Gears must have matching module and pressure angle to mesh correctly"
        )
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info_label)

        layout.addStretch()

        button_layout = QtGui.QHBoxLayout()

        self.position_btn = QtGui.QPushButton("Position Gears")
        self.position_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;"
        )
        self.position_btn.clicked.connect(self.positionFirstGear)
        button_layout.addWidget(self.position_btn)

        self.done_btn = QtGui.QPushButton("Done")
        self.done_btn.setStyleSheet(
            "background-color: #007ACC; color: white; font-weight: bold; padding: 8px;"
        )
        self.done_btn.clicked.connect(self.moveAndFinalize)
        button_layout.addWidget(self.done_btn)

        scaffold_btn = QtGui.QPushButton("Create Scaffolding")
        scaffold_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;"
        )
        scaffold_btn.clicked.connect(self.createScaffolding)
        button_layout.addWidget(scaffold_btn)

        cancel_btn = QtGui.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.gear1_combo.currentIndexChanged.connect(self.updateSecondGearOptions)
        self.gear2_combo.currentIndexChanged.connect(self.updateDistance)
        self.angle_spinbox.valueChanged.connect(self.updateRotationPreview)

        self.updateSecondGearOptions()

    def updateDistance(self):
        """Update calculated center distance based on selected gears."""
        idx1 = self.gear1_combo.currentIndex()
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())

        if idx1 >= 0 and idx2_data is not None:
            gear1 = self.gears[idx1]
            gear2 = self.gears[idx2_data]

            # Get gear specs for internal gear detection
            gear1_specs = self.getGearSpecs(gear1)
            gear2_specs = self.getGearSpecs(gear2)

            try:
                center_distance = calculateCenterDistance(gear1, gear2, gear1_specs, gear2_specs)
                self.center_distance_label.setText(
                    f"Center Distance: {center_distance:.3f} mm"
                )
            except Exception as e:
                self.center_distance_label.setText(
                    f"Center Distance: Error - {str(e)}"
                )

    def positionFirstGear(self):
        """Position first gear beside second gear at specified angle."""
        idx1 = self.gear1_combo.currentIndex()
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())
        angle = self.angle_spinbox.value()

        if idx1 >= 0 and idx2_data is not None:
            gear1_info = self.gears[idx1]
            gear2_info = self.gears[idx2_data]

            try:
                positionGearBeside(
                    gear1_info["param_obj"],
                    gear1_info,
                    gear2_info["param_obj"],
                    gear2_info,
                    angle,
                )
            except Exception as e:
                App.Console.PrintError(f"Error moving gear: {e}\n")
                QtGui.QMessageBox.critical(
                    None, "Positioning Error", f"Failed to position gears:\n{str(e)}"
                )

    def updateRotationPreview(self):
        """Update preview gear showing where gear 1 would be positioned."""
        idx1 = self.gear1_combo.currentIndex()
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())
        rotation_angle = self.angle_spinbox.value()

        self.cleanupPreview()

        if idx1 >= 0 and idx2_data is not None:
            try:
                gear1_info = self.gears[idx1]
                gear2_info = self.gears[idx2_data]

                # Gear 2 is center/reference (fixed), Gear 1 moves around it
                center_body_name = gear2_info["param_obj"].BodyName
                center_body = gear2_info["param_obj"].Document.getObject(
                    center_body_name
                )

                # Refresh gear1_body reference from document (cached reference may be stale if BodyName changed)
                gear1_body_name = gear1_info["label"]
                gear1_body = App.ActiveDocument.getObject(gear1_body_name)

                gear1_valid = gear1_body is not None
                if gear1_valid:
                    try:
                        gear1_valid = gear1_body.isValid()
                    except Exception:
                        gear1_valid = False

                if center_body and gear1_valid:
                    center_origin = center_body.Placement.Base
                    gear1_body_name = gear1_body.Name

                    if gear1_body_name not in self.original_gear2_positions:
                        self.original_gear2_positions[gear1_body_name] = (
                            gear1_body.Placement.Base
                        )

                    # Always calculate center distance using gear specs for internal gear support
                    gear1_specs = self.getGearSpecs(gear1_info)
                    gear2_specs = self.getGearSpecs(gear2_info)
                    distance = calculateCenterDistance(gear1_info, gear2_info, gear1_specs, gear2_specs)

                    angle_rad = rotation_angle * math.pi / 180.0

                    dx = distance * math.cos(angle_rad)
                    dy = distance * math.sin(angle_rad)

                    new_x = center_origin.x + dx
                    new_y = center_origin.y + dy
                    new_z = center_origin.z

                    # Directly set rotation to angle spinbox value (no complex calculation)
                    new_placement = App.Placement(
                        App.Vector(new_x, new_y, new_z),
                        App.Rotation(App.Vector(0, 0, 1), rotation_angle),
                    )

                    self.preview_counter += 1
                    preview_name = f"{self.preview_prefix}_{self.preview_counter}"

                    preview_body = App.ActiveDocument.addObject(
                        "Part::Feature", preview_name
                    )

                    try:
                        preview_body.Shape = gear1_body.Shape.copy()
                        preview_body.Placement = new_placement

                        if preview_body.ViewObject:
                            preview_body.ViewObject.Transparency = 50
                            preview_body.ViewObject.Visibility = True
                    except Exception as shape_error:
                        App.Console.PrintError(f"Error copying gear shape: {shape_error}\n")

                    self.preview_objects.append(preview_name)

                    App.ActiveDocument.recompute()
                else:
                    App.Console.PrintError("Center body or gear 1 body not valid\n")
            except Exception as e:
                App.Console.PrintError(f"Error creating preview: {e}\n")

    def cleanupPreview(self):
        """Remove all preview objects created by this dialog."""
        if not App.ActiveDocument:
            return

        for obj_name in self.preview_objects[:]:
            try:
                obj = App.ActiveDocument.getObject(obj_name)
                obj_valid = obj is not None
                if obj_valid:
                    try:
                        obj_valid = obj.isValid()
                    except Exception:
                        obj_valid = False

                if obj_valid:
                    App.ActiveDocument.removeObject(obj.Name)
            except Exception as e:
                App.Console.PrintError(
                    f"Error removing preview object {obj_name}: {e}\n"
                )

        self.preview_objects = []

    def rotateSecondGear(self):
        """Rotate second gear around first gear (preview only)."""
        self.updateRotationPreview()

    def moveSecondGear(self):
        """Actually move second gear to rotated position."""
        idx1 = self.gear1_combo.currentIndex()
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())
        rotation_angle = self.angle_spinbox.value()

        if idx1 >= 0 and idx2_data is not None:
            gear1_info = self.gears[idx1]
            gear2_info = self.gears[idx2_data]

            try:
                self.cleanupPreview()

                gear2_body = gear2_info["body_obj"]
                center_body = gear1_info["body_obj"]

                center_origin = center_body.Placement.Base
                gear2_body_name = gear2_body.Name

                original_gear2_origin = self.original_gear2_positions.get(
                    gear2_body_name
                )

                if not original_gear2_origin:
                    self.original_gear2_positions[gear2_body_name] = (
                        gear2_body.Placement.Base
                    )
                    original_gear2_origin = self.original_gear2_positions[
                        gear2_body_name
                    ]

                # Calculate center distance using gear specs for internal gear support
                gear1_specs = self.getGearSpecs(gear1_info)
                gear2_specs = self.getGearSpecs(gear2_info)
                center_distance = calculateCenterDistance(gear1_info, gear2_info, gear1_specs, gear2_specs)

                angle_rad = rotation_angle * math.pi / 180.0

                dx = center_distance * math.cos(angle_rad)
                dy = center_distance * math.sin(angle_rad)

                new_x = center_origin.x + dx
                new_y = center_origin.y + dy
                new_z = center_origin.z

                current_rotation = gear2_body.Placement.Rotation
                current_angle = math.degrees(
                    math.atan2(
                        current_rotation.Axis.y
                        * math.sin(math.radians(current_rotation.Angle)),
                        current_rotation.Axis.x
                        * math.sin(math.radians(current_rotation.Angle)),
                    )
                )

                new_rotation_angle = current_angle + rotation_angle

                new_placement = App.Placement(
                    App.Vector(new_x, new_y, new_z),
                    App.Rotation(App.Vector(0, 0, 1), new_rotation_angle),
                )

                gear2_body.Placement = new_placement

                gear2_param = gear2_info["param_obj"]
                gear2_param.OriginX = new_x
                gear2_param.OriginY = new_y
                gear2_param.OriginZ = new_z
                gear2_param.Angle = new_rotation_angle

                gear2_param.Document.recompute()
                App.Console.PrintMessage(
                    f"Moved '{gear2_param.BodyName}' by {rotation_angle:.1f}° around '{gear1_info['param_obj'].BodyName}'\n"
                )
            except Exception as e:
                App.Console.PrintError(f"Error moving gear: {e}\n")
                QtGui.QMessageBox.critical(
                    None, "Move Error", f"Failed to move gear:\n{str(e)}"
                )

    def createScaffolding(self):
        """Create scaffolding body with gear axis circles as reference points."""
        idx1 = self.gear1_combo.currentIndex()
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())

        if idx1 < 0 or idx2_data is None:
            QtGui.QMessageBox.warning(
                None, "Invalid Selection", "Please select two different gears."
            )
            return

        gear1_info = self.gears[idx1]
        gear2_info = self.gears[idx2_data]

        try:
            doc = App.ActiveDocument
            if not doc:
                QtGui.QMessageBox.warning(
                    None, "No Document", "Please create or open a FreeCAD document first."
                )
                return

            # Re-fetch bodies from document by name (not from cached references)
            gear1_param = gear1_info["param_obj"]
            gear2_param = gear2_info["param_obj"]

            gear1_body_name = gear1_param.BodyName if hasattr(gear1_param, "BodyName") else None
            gear2_body_name = gear2_param.BodyName if hasattr(gear2_param, "BodyName") else None

            if not gear1_body_name or not gear2_body_name:
                App.Console.PrintError("Cannot determine gear body names\n")
                return

            gear1_body = doc.getObject(gear1_body_name)
            gear2_body = doc.getObject(gear2_body_name)

            gear1_valid = gear1_body is not None
            if gear1_valid:
                try:
                    gear1_valid = gear1_body.isValid()
                except Exception:
                    gear1_valid = False

            gear2_valid = gear2_body is not None
            if gear2_valid:
                try:
                    gear2_valid = gear2_body.isValid()
                except Exception:
                    gear2_valid = False

            if not gear1_valid:
                App.Console.PrintError(f"Gear 1 body '{gear1_body_name}' not valid\n")
                return

            if not gear2_valid:
                App.Console.PrintError(f"Gear 2 body '{gear2_body_name}' not valid\n")
                return

            # Create new body for scaffolding
            scaffold_body_name = "GearScaffolding"
            existing = doc.getObject(scaffold_body_name)
            if existing:
                counter = 1
                while doc.getObject(f"{scaffold_body_name}{counter:03d}"):
                    counter += 1
                scaffold_body_name = f"{scaffold_body_name}{counter:03d}"

            scaffold_body = util.readyPart(doc, scaffold_body_name)

            gear1_placement = gear1_body.Placement.Base
            gear2_placement = gear2_body.Placement.Base

            # Calculate gear center positions
            p1 = App.Vector(gear1_placement.x, gear1_placement.y, gear1_placement.z)
            p2 = App.Vector(gear2_placement.x, gear2_placement.y, gear2_placement.z)

            # Calculate direction vector from p1 to p2
            direction = p2 - p1
            distance = direction.Length

            # Calculate midpoint
            midpoint = (p1 + p2) / 2.0

            # Calculate oval/plate dimensions
            major_radius = distance / 2.0 + 5.0
            minor_radius = distance / 2.0 + 5.0

            # Calculate axle radius and height
            axle_radius = 2.0
            axle_height = 20.0

            # Create sketch for oval plate (no holes in sketch)
            sketch = util.createSketch(scaffold_body, "ScaffoldingPlate")
            sketch.Placement = App.Placement(
                App.Vector(0, 0, 0), App.Rotation(0, 0, 0)
            )

            # Add outer oval (plate boundary only, no holes in this sketch)
            ellipse = sketch.addGeometry(
                Part.Ellipse(
                    App.Vector(0, 0, 0),
                    App.Vector(major_radius, 0, 0),
                    App.Vector(0, minor_radius, 0),
                    App.Vector(0, 0, 1)
                ),
                False
            )
            sketch.addConstraint(Sketcher.Constraint("Coincident", ellipse, 3, -1, 1))
            sketch.addConstraint(Sketcher.Constraint("RadiusX", ellipse, major_radius))
            sketch.addConstraint(Sketcher.Constraint("RadiusY", ellipse, minor_radius))

            # Pad the oval sketch to create the plate (5mm thickness)
            plate_pad = util.createPad(scaffold_body, sketch, 5.0, "ScaffoldingPlate")
            sketch.Visibility = False

            # Calculate rotation to align plate with gear axes
            angle_rad = math.atan2(direction.y, direction.x)
            angle_deg = angle_rad * 180.0 / math.pi

            # Position the plate at midpoint
            plate_pad.Placement = App.Placement(
                midpoint,
                App.Rotation(App.Vector(0, 0, 1), angle_deg)
            )

            # Create sketch for axle 1
            sketch_axle1 = util.createSketch(scaffold_body, "Axle1Sketch")
            sketch_axle1.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))

            circle_axle1 = sketch_axle1.addGeometry(
                Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), axle_radius),
                False
            )
            sketch_axle1.addConstraint(Sketcher.Constraint("Coincident", circle_axle1, 3, -1, 1))
            sketch_axle1.addConstraint(Sketcher.Constraint("Diameter", circle_axle1, axle_radius * 2.0))

            # Pad axle 1 sketch (20mm height)
            axle1_pad = util.createPad(scaffold_body, sketch_axle1, axle_height, "Axle1")
            sketch_axle1.Visibility = False

            # Position axle 1 at gear 1 center
            axle1_pad.Placement = App.Placement(p1, App.Rotation(0, 0, 0))

            # Create sketch for axle 2
            sketch_axle2 = util.createSketch(scaffold_body, "Axle2Sketch")
            sketch_axle2.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(0, 0, 0))

            circle_axle2 = sketch_axle2.addGeometry(
                Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), axle_radius),
                False
            )
            sketch_axle2.addConstraint(Sketcher.Constraint("Coincident", circle_axle2, 3, -1, 1))
            sketch_axle2.addConstraint(Sketcher.Constraint("Diameter", circle_axle2, axle_radius * 2.0))

            # Pad axle 2 sketch (20mm height)
            axle2_pad = util.createPad(scaffold_body, sketch_axle2, axle_height, "Axle2")
            sketch_axle2.Visibility = False

            # Position axle 2 at gear 2 center
            axle2_pad.Placement = App.Placement(p2, App.Rotation(0, 0, 0))

            # Set visibility and appearance
            if plate_pad.ViewObject:
                plate_pad.ViewObject.Transparency = 40
                plate_pad.ViewObject.ShapeColor = (0.7, 0.7, 0.7)
            if axle1_pad.ViewObject:
                axle1_pad.ViewObject.Transparency = 30
                axle1_pad.ViewObject.ShapeColor = (0.6, 0.4, 0.2)
            if axle2_pad.ViewObject:
                axle2_pad.ViewObject.Transparency = 30
                axle2_pad.ViewObject.ShapeColor = (0.6, 0.4, 0.2)

            doc.recompute()

            App.Console.PrintMessage(
                f"Created scaffolding body '{scaffold_body_name}'\n"
            )
            App.Console.PrintMessage(
                f"  Plate: oval, padded 5mm\n"
            )
            App.Console.PrintMessage(
                f"  Axle 1 sketch: circle, padded 20mm at {gear1_body_name}\n"
            )
            App.Console.PrintMessage(
                f"  Axle 2 sketch: circle, padded 20mm at {gear2_body_name}\n"
            )

            # Add outer oval (plate boundary)
            ellipse = sketch.addGeometry(
                Part.Ellipse(
                    App.Vector(0, 0, 0),
                    App.Vector(major_radius, 0, 0),
                    App.Vector(0, minor_radius, 0),
                    App.Vector(0, 0, 1)
                ),
                False
            )
            sketch.addConstraint(Sketcher.Constraint("Coincident", ellipse, 3, -1, 1))
            sketch.addConstraint(Sketcher.Constraint("RadiusX", ellipse, major_radius))
            sketch.addConstraint(Sketcher.Constraint("RadiusY", ellipse, minor_radius))

            # Add hole for gear 1 axle (relative to ellipse center)
            # Position holes on the major axis, offset from center
            hole1_x = -distance / 2.0
            hole1_y = 0.0

            circle1 = sketch.addGeometry(
                Part.Circle(App.Vector(hole1_x, hole1_y, 0), App.Vector(0, 0, 1), hole_radius),
                False
            )
            sketch.addConstraint(Sketcher.Constraint("Coincident", circle1, 3, -1, 1))
            sketch.addConstraint(Sketcher.Constraint("Diameter", circle1, hole_radius * 2.0))

            # Add hole for gear 2 axle
            hole2_x = distance / 2.0
            hole2_y = 0.0

            circle2 = sketch.addGeometry(
                Part.Circle(App.Vector(hole2_x, hole2_y, 0), App.Vector(0, 0, 1), hole_radius),
                False
            )
            sketch.addConstraint(Sketcher.Constraint("Coincident", circle2, 3, -1, 1))
            sketch.addConstraint(Sketcher.Constraint("Diameter", circle2, hole_radius * 2.0))

            # Constrain holes to be on major axis
            sketch.addConstraint(Sketcher.Constraint("Vertical", circle1, 3, ellipse, 3))
            sketch.addConstraint(Sketcher.Constraint("Vertical", circle2, 3, ellipse, 3))

            # Constrain holes to be at specific distances from center
            sketch.addConstraint(Sketcher.Constraint("DistanceX", circle1, 3, -1, 1, abs(hole1_x)))
            sketch.addConstraint(Sketcher.Constraint("DistanceX", circle2, 3, -1, 1, abs(hole2_x)))

            # Pad the sketch to create the plate (5mm thickness)
            plate_pad = util.createPad(scaffold_body, sketch, 5.0, "ScaffoldingPlate")
            sketch.Visibility = False

            # Calculate rotation to align plate with gear axes
            angle_rad = math.atan2(direction.y, direction.x)
            angle_deg = angle_rad * 180.0 / math.pi

            # Position the plate at midpoint
            plate_pad.Placement = App.Placement(
                midpoint,
                App.Rotation(App.Vector(0, 0, 1), angle_deg)
            )

            # Create axles as separate objects (20mm height)
            axle_radius = 2.0
            axle_height = 20.0

            axle1 = Part.makeCylinder(axle_radius, axle_height, App.Vector(0, 0, 0), App.Vector(0, 0, 1), 360)
            axle1_obj = doc.addObject("Part::Feature", f"Axle_{gear1_body_name}")
            axle1_obj.Shape = axle1
            axle1_obj.Placement = App.Placement(p1, App.Rotation(0, 0, 0))

            axle2 = Part.makeCylinder(axle_radius, axle_height, App.Vector(0, 0, 0), App.Vector(0, 0, 1), 360)
            axle2_obj = doc.addObject("Part::Feature", f"Axle_{gear2_body_name}")
            axle2_obj.Shape = axle2
            axle2_obj.Placement = App.Placement(p2, App.Rotation(0, 0, 0))

            # Set visibility and appearance
            if plate_pad.ViewObject:
                plate_pad.ViewObject.Transparency = 40
                plate_pad.ViewObject.ShapeColor = (0.7, 0.7, 0.7)
            if axle1_obj.ViewObject:
                axle1_obj.ViewObject.Transparency = 30
                axle1_obj.ViewObject.ShapeColor = (0.6, 0.4, 0.2)
            if axle2_obj.ViewObject:
                axle2_obj.ViewObject.Transparency = 30
                axle2_obj.ViewObject.ShapeColor = (0.6, 0.4, 0.2)

            doc.recompute()

            App.Console.PrintMessage(
                f"Created scaffolding body '{scaffold_body_name}'\n"
            )
            App.Console.PrintMessage(
                f"  Plate: oval with 2 holes, padded 5mm\n"
            )
            App.Console.PrintMessage(
                f"  Axle 1: radius={axle_radius}mm, height={axle_height}mm\n"
            )
            App.Console.PrintMessage(
                f"  Axle 2: radius={axle_radius}mm, height={axle_height}mm\n"
            )

            # Set visibility and appearance
            if axle1_obj.ViewObject:
                axle1_obj.ViewObject.Transparency = 30
                axle1_obj.ViewObject.ShapeColor = (0.8, 0.8, 0.0)
            if axle2_obj.ViewObject:
                axle2_obj.ViewObject.Transparency = 30
                axle2_obj.ViewObject.ShapeColor = (0.8, 0.8, 0.0)
            if oval_obj.ViewObject:
                oval_obj.ViewObject.Transparency = 50
                oval_obj.ViewObject.ShapeColor = (0.5, 0.5, 0.5)

            doc.recompute()

            App.Console.PrintMessage(
                f"Created scaffolding with axles and connecting oval\n"
            )
            App.Console.PrintMessage(
                f"  Gear 1 axle '{axle1_name}': ({gear1_placement.x:.3f}, {gear1_placement.y:.3f}, {gear1_placement.z:.3f})\n"
            )
            App.Console.PrintMessage(
                f"  Gear 2 axle '{axle2_name}': ({gear2_placement.x:.3f}, {gear2_placement.y:.3f}, {gear2_placement.z:.3f})\n"
            )
            App.Console.PrintMessage(
                f"  Connecting oval '{oval_name}': length={distance:.3f}, major_radius={major_radius:.3f}\n"
            )

            # Constrain ellipse
            oval_sketch.addConstraint(Sketcher.Constraint("Coincident", ellipse, 3, -1, 1))
            oval_sketch.addConstraint(Sketcher.Constraint("RadiusX", ellipse, major_radius))
            oval_sketch.addConstraint(Sketcher.Constraint("RadiusY", ellipse, minor_radius))

            # Calculate rotation to align ellipse with gear axes
            angle_rad = math.atan2(direction.y, direction.x)
            angle_deg = angle_rad * 180.0 / math.pi

            # Position and rotate the sketch
            oval_sketch.Placement = App.Placement(
                midpoint,
                App.Rotation(App.Vector(0, 0, 1), angle_deg)
            )

            # Pad the oval to give it thickness
            oval_pad = util.createPad(scaffold_body, oval_sketch, axle_height, "ConnectingOval")
            oval_sketch.Visibility = False

            # Set visibility
            if axle1_obj.ViewObject:
                axle1_obj.ViewObject.Transparency = 30
                axle1_obj.ViewObject.LineWidth = 2
            if axle2_obj.ViewObject:
                axle2_obj.ViewObject.Transparency = 30
                axle2_obj.ViewObject.LineWidth = 2
            if oval_pad.ViewObject:
                oval_pad.ViewObject.Transparency = 50
                oval_pad.ViewObject.LineWidth = 1

            doc.recompute()

            App.Console.PrintMessage(
                f"Created scaffolding body '{scaffold_body_name}' with axles and connecting oval\n"
            )
            App.Console.PrintMessage(
                f"  Gear 1 axle: ({gear1_placement.x:.3f}, {gear1_placement.y:.3f}, {gear1_placement.z:.3f})\n"
            )
            App.Console.PrintMessage(
                f"  Gear 2 axle: ({gear2_placement.x:.3f}, {gear2_placement.y:.3f}, {gear2_placement.z:.3f})\n"
            )
            App.Console.PrintMessage(
                f"  Connecting oval: length={distance:.3f}, major_radius={major_radius:.3f}\n"
            )

            if App.GuiUp:
                try:
                    FreeCADGui.SendMsgToActiveView("ViewFit")
                except Exception:
                    pass

        except Exception as e:
            App.Console.PrintError(f"Error creating scaffolding: {e}\n")
            QtGui.QMessageBox.critical(
                None, "Scaffolding Error", f"Failed to create scaffolding:\n{str(e)}"
            )

    def closeEvent(self, event):
        """Handle dialog close event - cleanup preview objects."""
        self.cleanupPreview()
        super().closeEvent(event)


def rotateGearAround(gear_to_rotate_param, center_gear_param, angle_deg: float):
    """Rotate gear around another gear at specified angle.

    Args:
        gear_to_rotate_param: Parameter object of gear to rotate
        center_gear_param: Parameter object of center gear (stays in place)
        angle_deg: Angle in degrees to rotate around center gear
    """
    import math

    center_body_name = (
        center_gear_param.BodyName if hasattr(center_gear_param, "BodyName") else None
    )
    center_body = None
    if center_body_name:
        center_body = center_gear_param.Document.getObject(center_body_name)

    if not center_body:
        raise Exception("Center gear body not found")

    center_origin = center_body.Placement.Base

    rotate_body_name = (
        gear_to_rotate_param.BodyName
        if hasattr(gear_to_rotate_param, "BodyName")
        else None
    )
    rotate_body = None
    if rotate_body_name:
        rotate_body = gear_to_rotate_param.Document.getObject(rotate_body_name)

    if not rotate_body:
        raise Exception("Gear to rotate body not found")

    current_distance = rotate_body.Placement.Base.sub(center_origin)

    distance = (current_distance.x**2 + current_distance.y**2) ** 0.5

    angle_rad = angle_deg * math.pi / 180.0

    dx = distance * math.cos(angle_rad)
    dy = distance * math.sin(angle_rad)

    new_x = center_origin.x + dx
    new_y = center_origin.y + dy
    new_z = center_origin.z

    current_rotation = rotate_body.Placement.Rotation
    current_angle = math.degrees(
        math.atan2(
            current_rotation.Axis.y * math.sin(math.radians(current_rotation.Angle)),
            current_rotation.Axis.x * math.sin(math.radians(current_rotation.Angle)),
        )
    )

    new_rotation_angle = current_angle + angle_deg

    new_placement = App.Placement(
        App.Vector(new_x, new_y, new_z),
        App.Rotation(App.Vector(0, 0, 1), new_rotation_angle),
    )

    rotate_body.Placement = new_placement

    gear_to_rotate_param.OriginX = new_x
    gear_to_rotate_param.OriginY = new_y
    gear_to_rotate_param.OriginZ = new_z
    gear_to_rotate_param.Angle = new_rotation_angle

    gear_to_rotate_param.Document.recompute()
    App.Console.PrintMessage(
        f"Rotated '{rotate_body_name}' around '{center_body_name}' by {angle_deg:.1f}°\n"
    )


def getGearSpecs(gear_info: Dict) -> Dict:
    """Get gear specifications from gear info dict.

    Args:
        gear_info: Dictionary containing gear information (must have 'param_obj' and 'name')

    Returns:
        Dictionary with module, pressure_angle, helix_angle, gear_type, and is_internal
    """
    param_obj = gear_info["param_obj"]
    specs = {
        "module": 0.0,
        "pressure_angle": 0.0,
        "helix_angle": 0.0,
        "gear_type": "unknown",
        "is_internal": False,
    }

    try:
        if hasattr(param_obj, "Module"):
            specs["module"] = float(
                param_obj.Module.Value
                if hasattr(param_obj.Module, "Value")
                else param_obj.Module
            )
        if hasattr(param_obj, "PressureAngle"):
            specs["pressure_angle"] = float(
                param_obj.PressureAngle.Value
                if hasattr(param_obj.PressureAngle, "Value")
                else param_obj.PressureAngle
            )

        obj_name = gear_info["name"]

        # Check for internal gears first
        if "Internal" in obj_name:
            specs["is_internal"] = True
            if "Spur" in obj_name:
                specs["gear_type"] = "spur"
                specs["helix_angle"] = 0.0
            elif "Herringbone" in obj_name:
                specs["gear_type"] = "herringbone"
                if hasattr(param_obj, "HelixAngle"):
                    specs["helix_angle"] = float(
                        param_obj.HelixAngle.Value
                        if hasattr(param_obj.HelixAngle, "Value")
                        else param_obj.HelixAngle
                    )
            elif "Helix" in obj_name:
                specs["gear_type"] = "helical"
                if hasattr(param_obj, "HelixAngle"):
                    specs["helix_angle"] = float(
                        param_obj.HelixAngle.Value
                        if hasattr(param_obj.HelixAngle, "Value")
                        else param_obj.HelixAngle
                    )
        # External gears
        elif "GenericSpur" in obj_name:
            specs["gear_type"] = "spur"
            specs["helix_angle"] = 0.0
        elif "GenericHerringbone" in obj_name:
            specs["gear_type"] = "herringbone"
            if hasattr(param_obj, "Angle1"):
                specs["helix_angle"] = float(
                    param_obj.Angle1.Value
                    if hasattr(param_obj.Angle1, "Value")
                    else param_obj.Angle1
                )
        elif "GenericHelix" in obj_name:
            specs["gear_type"] = "helical"
            if hasattr(param_obj, "HelixAngle"):
                specs["helix_angle"] = float(
                    param_obj.HelixAngle.Value
                    if hasattr(param_obj.HelixAngle, "Value")
                    else param_obj.HelixAngle
                )
    except Exception:
        pass

    return specs


def findGearsInDocument(doc) -> List[Dict]:
    """Find all gear parameter objects in document and map to their bodies.

    Args:
        doc: FreeCAD document object

    Returns:
        List of dictionaries with gear information
    """
    gears = []

    for obj in doc.Objects:
        obj_name = obj.Name

        if "Parameters" in obj_name and hasattr(obj, "BodyName"):
            try:
                body_name = str(obj.BodyName)
                body_obj = doc.getObject(body_name)

                if (
                    body_obj
                    and hasattr(body_obj, "TypeId")
                    and "Body" in body_obj.TypeId
                ):
                    gear_info = {
                        "param_obj": obj,
                        "body_obj": body_obj,
                        "name": obj_name,
                        "label": body_name,
                        "pitch_diameter": 0.0,
                    }

                    try:
                        if hasattr(obj, "PitchDiameter"):
                            gear_info["pitch_diameter"] = obj.PitchDiameter.Value
                        elif hasattr(obj, "Module") and hasattr(obj, "NumberOfTeeth"):
                            module = (
                                obj.Module.Value
                                if hasattr(obj.Module, "Value")
                                else obj.Module
                            )
                            num_teeth = obj.NumberOfTeeth
                            gear_info["pitch_diameter"] = float(module) * int(num_teeth)
                    except Exception:
                        pass

                    gears.append(gear_info)
            except Exception:
                pass

    return gears


def calculateCenterDistance(gear1_params: Dict, gear2_params: Dict, gear1_specs: Dict = None, gear2_specs: Dict = None) -> float:
    """Calculate center distance between two gears.

    Args:
        gear1_params: First gear parameters dict
        gear2_params: Second gear parameters dict
        gear1_specs: First gear specifications (with is_internal flag)
        gear2_specs: Second gear specifications (with is_internal flag)

    Returns:
        Center distance in mm
    """
    pitch1 = gear1_params.get("pitch_diameter", 0.0)
    pitch2 = gear2_params.get("pitch_diameter", 0.0)

    # Check if either gear is internal
    is_internal1 = gear1_specs.get("is_internal", False) if gear1_specs else False
    is_internal2 = gear2_specs.get("is_internal", False) if gear2_specs else False

    # Calculate based on gear types
    if is_internal1 and is_internal2:
        # Internal + Internal doesn't make physical sense
        raise Exception("Cannot mesh two internal gears together")
    elif is_internal1 and not is_internal2:
        # Internal + External: center distance = (pitch_internal - pitch_external) / 2
        return (pitch1 - pitch2) / 2.0
    elif not is_internal1 and is_internal2:
        # External + Internal: center distance = (pitch_internal - pitch_external) / 2
        return (pitch2 - pitch1) / 2.0
    else:
        # External + External: center distance = (pitch1 + pitch2) / 2
        return (pitch1 + pitch2) / 2.0


def positionGearBeside(
    gear1_param_obj, gear1_params, gear2_param_obj, gear2_params, angle_deg: float = 0.0
):
    """Position gear1 beside gear2 for proper meshing.

    Args:
        gear1_param_obj: First gear parameter object (to be updated)
        gear1_params: First gear parameters dict
        gear2_param_obj: Second gear parameter object (reference)
        gear2_params: Second gear parameters dict
        angle_deg: Angle in degrees to position gear1 (0 = to right)
    """
    import math

    pitch1 = gear1_params.get("pitch_diameter", 0.0)
    pitch2 = gear2_params.get("pitch_diameter", 0.0)

    # Get gear specs to determine if internal
    gear1_specs = getGearSpecs(gear1_params)
    gear2_specs = getGearSpecs(gear2_params)

    # Use the calculateCenterDistance method for proper center distance calculation
    center_distance = calculateCenterDistance(gear1_params, gear2_params, gear1_specs, gear2_specs)

    angle_rad = angle_deg * math.pi / 180.0

    dx = center_distance * math.cos(angle_rad)
    dy = center_distance * math.sin(angle_rad)

    gear2_body_name = (
        gear2_param_obj.BodyName if hasattr(gear2_param_obj, "BodyName") else None
    )
    gear2_body = None
    if gear2_body_name:
        gear2_body = gear2_param_obj.Document.getObject(gear2_body_name)

    gear2_origin = App.Vector(0, 0, 0)
    gear2_angle = 0.0

    if gear2_body:
        gear2_placement = gear2_body.Placement
        gear2_origin = gear2_placement.Base
        rotation = gear2_placement.Rotation
        gear2_angle = math.degrees(
            math.atan2(
                rotation.Axis.y * math.sin(math.radians(rotation.Angle)),
                rotation.Axis.x * math.sin(math.radians(rotation.Angle)),
            )
        )

    new_origin_x = gear2_origin.x + dx
    new_origin_y = gear2_origin.y + dy
    new_origin_z = gear2_origin.z

    gear1_body = gear1_params.get("body_obj")

    if gear1_body:
        current_placement = gear1_body.Placement
        new_rotation_angle = angle_deg + gear2_angle

        new_placement = App.Placement(
            App.Vector(new_origin_x, new_origin_y, new_origin_z),
            App.Rotation(App.Vector(0, 0, 1), new_rotation_angle),
        )

        gear1_body.Placement = new_placement

        # Update parameter object properties if they exist
        if hasattr(gear1_param_obj, "OriginX"):
            gear1_param_obj.OriginX = new_origin_x
        if hasattr(gear1_param_obj, "OriginY"):
            gear1_param_obj.OriginY = new_origin_y
        if hasattr(gear1_param_obj, "OriginZ"):
            gear1_param_obj.OriginZ = new_origin_z
        if hasattr(gear1_param_obj, "Angle"):
            gear1_param_obj.Angle = new_rotation_angle

        gear1_param_obj.Document.recompute()
        App.Console.PrintMessage(
            f"Positioned '{gear1_param_obj.BodyName}' beside '{gear2_param_obj.BodyName}' at center distance {center_distance:.3f} mm\n"
        )


class GearPositioningCommand:
    """Command to position two gears beside each other."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "positionGears.svg"),
            "MenuText": "&Position Gears",
            "ToolTip": "Position two gears beside each other for proper meshing",
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        doc = App.ActiveDocument

        if not doc:
            QtGui.QMessageBox.warning(
                None, "No Document", "Please create or open a FreeCAD document first."
            )
            return

        gears = findGearsInDocument(doc)

        if len(gears) < 2:
            QtGui.QMessageBox.warning(
                None,
                "Not Enough Gears",
                f"Found {len(gears)} gear(s). Need at least 2 gears to position them.\n"
                "Please create at least 2 gears using the GearWorkbench tools.",
            )
            return

        dialog = GearPositionDialog(gears, FreeCADGui.getMainWindow())

        if dialog.exec_() == QtGui.QDialog.Accepted:
            idx1 = dialog.gear1_combo.currentIndex()
            idx2_data = dialog.gear2_combo.itemData(dialog.gear2_combo.currentIndex())
            angle = dialog.angle_spinbox.value()

            if idx1 >= 0 and idx2_data is not None:
                gear1_info = gears[idx1]
                gear2_info = gears[idx2_data]

                try:
                    positionGearBeside(
                        gear1_info["param_obj"],
                        gear1_info,
                        gear2_info["param_obj"],
                        gear2_info,
                        angle,
                    )
                except Exception as e:
                    QtGui.QMessageBox.critical(
                        None,
                        "Positioning Error",
                        f"Failed to position gears:\n{str(e)}",
                    )
                    App.Console.PrintError(f"Gear positioning error: {e}\n")
            else:
                QtGui.QMessageBox.warning(
                    None, "Invalid Selection", "Please select two different gears."
                )

    def IsActive(self):
        """Return True if command can be activated."""
        return App.ActiveDocument is not None

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


# Register command with FreeCAD
try:
    FreeCADGui.addCommand("GearPositioningCommand", GearPositioningCommand())
except Exception as e:
    App.Console.PrintError(f"Failed to register gear positioning command: {e}\n")
