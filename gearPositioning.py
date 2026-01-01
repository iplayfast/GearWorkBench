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

        Now simplified to only check if modules match. This allows users to
        experiment with different gear type combinations and decide if they work.

        Args:
            gear1_info: First gear information
            gear2_info: Second gear information

        Returns:
            True if gears have matching module, False otherwise
        """
        specs1 = self.getGearSpecs(gear1_info)
        specs2 = self.getGearSpecs(gear2_info)

        module_diff = abs(specs1["module"] - specs2["module"])
        module_compatible = module_diff < 0.001

        # Only require matching module - let user decide if the combination works
        return module_compatible

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

    def findExistingScaffold(self, gear_position, tolerance=1.0):
        """Find existing scaffold that contains an axle at the given position.

        Args:
            gear_position: App.Vector position to check
            tolerance: Distance tolerance in mm

        Returns:
            Tuple of (scaffold_body, axle_positions_list) or (None, None)
        """
        doc = App.ActiveDocument
        if not doc:
            return None, None

        # Find all scaffold bodies
        for obj in doc.Objects:
            if obj.Name.startswith("GearScaffolding") and hasattr(obj, "Group"):
                # This is a scaffold body, check its axles
                axle_positions = []
                for feature in obj.Group:
                    if feature.Name.startswith("Axle") and hasattr(feature, "Placement"):
                        axle_pos = feature.Placement.Base
                        axle_positions.append(axle_pos)

                        # Check if this axle is at the gear position
                        distance = (App.Vector(axle_pos.x, axle_pos.y, 0) -
                                  App.Vector(gear_position.x, gear_position.y, 0)).Length
                        if distance < tolerance:
                            return obj, axle_positions

        return None, None

    def createScaffolding(self):
        """Create scaffolding with axles extending down from gears and oval surrounding them."""
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

            # Re-fetch bodies from document by name
            gear1_param = gear1_info["param_obj"]
            gear2_param = gear2_info["param_obj"]

            gear1_body_name = gear1_param.BodyName if hasattr(gear1_param, "BodyName") else None
            gear2_body_name = gear2_param.BodyName if hasattr(gear2_param, "BodyName") else None

            if not gear1_body_name or not gear2_body_name:
                App.Console.PrintError("Cannot determine gear body names\n")
                return

            gear1_body = doc.getObject(gear1_body_name)
            gear2_body = doc.getObject(gear2_body_name)

            if not gear1_body or not gear2_body:
                App.Console.PrintError("Cannot find gear bodies\n")
                return

            # Get gear positions
            p1 = gear1_body.Placement.Base
            p2 = gear2_body.Placement.Base

            App.Console.PrintMessage(f"Gear 1 at: ({p1.x:.2f}, {p1.y:.2f}, {p1.z:.2f})\n")
            App.Console.PrintMessage(f"Gear 2 at: ({p2.x:.2f}, {p2.y:.2f}, {p2.z:.2f})\n")

            # Get gear specs to detect internal gears
            gear1_specs = self.getGearSpecs(gear1_info)
            gear2_specs = self.getGearSpecs(gear2_info)

            # Create PartDesign Body
            scaffold_body_name = "GearScaffolding"
            existing = doc.getObject(scaffold_body_name)
            if existing:
                counter = 1
                while doc.getObject(f"{scaffold_body_name}{counter:03d}"):
                    counter += 1
                scaffold_body_name = f"{scaffold_body_name}{counter:03d}"

            scaffold_body = util.readyPart(doc, scaffold_body_name)

            # Constants
            axle_radius = 5.0
            axle_height = 30.0
            shell_wall_thickness = 5.0

            # Calculate dimensions
            direction = p2 - p1
            distance = math.sqrt(direction.x**2 + direction.y**2)

            # Oval dimensions
            major_radius = distance / 2.0 + 40.0
            minor_radius = 40.0
            plate_thickness = 5.0

            # Positions
            center_x = (p1.x + p2.x) / 2.0
            center_y = (p1.y + p2.y) / 2.0
            plate_z = min(p1.z, p2.z) - axle_height - 5.0

            # Rotation angle
            angle_rad = math.atan2(direction.y, direction.x)
            angle_deg = angle_rad * 180.0 / math.pi

            # --- CREATE OVAL SKETCH AND PAD ---
            oval_sketch = util.createSketch(scaffold_body, "OvalSketch")
            # Position sketch at oval location with rotation
            oval_sketch.Placement = App.Placement(
                App.Vector(center_x, center_y, plate_z),
                App.Rotation(App.Vector(0, 0, 1), angle_deg)
            )

            # Add ellipse to sketch
            ellipse = oval_sketch.addGeometry(
                Part.Ellipse(
                    App.Vector(major_radius, 0, 0),
                    App.Vector(0, minor_radius, 0),
                    App.Vector(0, 0, 0)
                ),
                False
            )
            oval_sketch.addConstraint(Sketcher.Constraint("Coincident", ellipse, 3, -1, 1))

            # Pad the oval
            oval_pad = util.createPad(scaffold_body, oval_sketch, plate_thickness, "OvalPlate")
            oval_sketch.Visibility = False

            App.Console.PrintMessage(f"Created oval at ({center_x:.2f}, {center_y:.2f}, {plate_z:.2f})\n")

            # --- CREATE AXLE 1 SKETCH AND PAD ---
            axle1_sketch = util.createSketch(scaffold_body, "Axle1Sketch")
            axle1_position = App.Vector(p1.x, p1.y, p1.z - axle_height)
            axle1_sketch.Placement = App.Placement(axle1_position, App.Rotation(0, 0, 0))

            if gear1_specs["is_internal"]:
                outer_radius = gear1_info.get("pitch_diameter", 0.0) / 2.0
                inner_radius = outer_radius + 2.0
                outer_shell_radius = inner_radius + shell_wall_thickness

                circle_outer = axle1_sketch.addGeometry(
                    Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_shell_radius),
                    False
                )
                axle1_sketch.addConstraint(Sketcher.Constraint("Coincident", circle_outer, 3, -1, 1))

                circle_inner = axle1_sketch.addGeometry(
                    Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), inner_radius),
                    False
                )
                axle1_sketch.addConstraint(Sketcher.Constraint("Coincident", circle_inner, 3, -1, 1))
            else:
                circle = axle1_sketch.addGeometry(
                    Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), axle_radius),
                    False
                )
                axle1_sketch.addConstraint(Sketcher.Constraint("Coincident", circle, 3, -1, 1))

            axle1_pad = util.createPad(scaffold_body, axle1_sketch, axle_height, "Axle1")
            axle1_sketch.Visibility = False

            App.Console.PrintMessage(f"Created Axle1 at ({axle1_position.x:.2f}, {axle1_position.y:.2f}, {axle1_position.z:.2f})\n")

            # --- CREATE AXLE 2 SKETCH AND PAD ---
            axle2_sketch = util.createSketch(scaffold_body, "Axle2Sketch")
            axle2_position = App.Vector(p2.x, p2.y, p2.z - axle_height)
            axle2_sketch.Placement = App.Placement(axle2_position, App.Rotation(0, 0, 0))

            if gear2_specs["is_internal"]:
                outer_radius = gear2_info.get("pitch_diameter", 0.0) / 2.0
                inner_radius = outer_radius + 2.0
                outer_shell_radius = inner_radius + shell_wall_thickness

                circle_outer = axle2_sketch.addGeometry(
                    Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), outer_shell_radius),
                    False
                )
                axle2_sketch.addConstraint(Sketcher.Constraint("Coincident", circle_outer, 3, -1, 1))

                circle_inner = axle2_sketch.addGeometry(
                    Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), inner_radius),
                    False
                )
                axle2_sketch.addConstraint(Sketcher.Constraint("Coincident", circle_inner, 3, -1, 1))
            else:
                circle = axle2_sketch.addGeometry(
                    Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), axle_radius),
                    False
                )
                axle2_sketch.addConstraint(Sketcher.Constraint("Coincident", circle, 3, -1, 1))

            axle2_pad = util.createPad(scaffold_body, axle2_sketch, axle_height, "Axle2")
            axle2_sketch.Visibility = False

            App.Console.PrintMessage(f"Created Axle2 at ({axle2_position.x:.2f}, {axle2_position.y:.2f}, {axle2_position.z:.2f})\n")

            # Set appearance
            if oval_pad.ViewObject:
                oval_pad.ViewObject.Transparency = 50
                oval_pad.ViewObject.ShapeColor = (0.0, 1.0, 0.0)
            if axle1_pad.ViewObject:
                axle1_pad.ViewObject.Transparency = 0
                axle1_pad.ViewObject.ShapeColor = (1.0, 0.0, 0.0)
            if axle2_pad.ViewObject:
                axle2_pad.ViewObject.Transparency = 0
                axle2_pad.ViewObject.ShapeColor = (0.0, 0.0, 1.0)

            doc.recompute()

            # Verify all objects are in the scaffold
            App.Console.PrintMessage(f"\nScaffold '{scaffold_body_name}' contains:\n")
            for obj in scaffold_body.Group:
                visibility = "VISIBLE" if (obj.ViewObject and obj.ViewObject.Visibility) else "HIDDEN"
                has_shape = "HAS SHAPE" if (hasattr(obj, "Shape") and obj.Shape and not obj.Shape.isNull()) else "NO SHAPE"
                App.Console.PrintMessage(f"  - {obj.Name}: {visibility}, {has_shape}\n")
                if hasattr(obj, "Placement"):
                    App.Console.PrintMessage(f"      Placement: {obj.Placement.Base}\n")

            App.Console.PrintMessage(f"\nCreated scaffolding '{scaffold_body_name}' using PartDesign\n")
            App.Console.PrintMessage(f"  Oval: GREEN, semi-transparent\n")
            App.Console.PrintMessage(f"  Axle 1: RED at gear 1\n")
            App.Console.PrintMessage(f"  Axle 2: BLUE at gear 2\n")

            if App.GuiUp:
                try:
                    FreeCADGui.SendMsgToActiveView("ViewFit")
                except Exception:
                    pass

        except Exception as e:
            App.Console.PrintError(f"Error creating scaffolding: {e}\n")
            import traceback
            App.Console.PrintError(traceback.format_exc())
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
