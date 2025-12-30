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
            helix_diff = abs(helix1 - helix2)
            return helix_diff < 1.0

        if type1 == "herringbone" and type2 == "herringbone":
            helix_diff = abs(helix1 - helix2)
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
        """Move gear 2 to final position and delete preview."""
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())
        if not self.preview_body or idx2_data is None:
            return

        gear2_info = self.gears[idx2_data]
        gear2_body_name = self.preview_body.Name
        real_gear2_body = gear2_info["body_obj"]

        real_gear2_body.Placement = self.preview_body.Placement
        real_gear2_body.Document.recompute()

        self.preview_body.Document.removeObject(gear2_body_name)
        self.preview_body = None

        gear2_param = gear2_info["param_obj"]
        gear2_param.OriginX = real_gear2_body.Placement.Base.x
        gear2_param.OriginY = real_gear2_body.Placement.Base.y
        gear2_param.OriginZ = real_gear2_body.Placement.Base.z
        gear2_param.Angle = real_gear2_body.Placement.Rotation.Angle

        gear2_param.Document.recompute()
        App.Console.PrintMessage(
            f"Moved '{real_gear2_body.Name}' to final position\n"
        )

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
        idx2 = self.gear2_combo.currentIndex()

        if idx1 >= 0 and idx2 >= 0:
            gear1 = self.gears[idx1]
            gear2 = self.gears[idx2]

            pitch1 = gear1.get("pitch_diameter", 0.0)
            pitch2 = gear2.get("pitch_diameter", 0.0)

            center_distance = (pitch1 + pitch2) / 2.0
            self.center_distance_label.setText(
                f"Center Distance: {center_distance:.3f} mm"
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
        """Update preview gear showing where gear 2 would be positioned."""
        idx1 = self.gear1_combo.currentIndex()
        idx2_data = self.gear2_combo.itemData(self.gear2_combo.currentIndex())
        rotation_angle = self.angle_spinbox.value()

        self.cleanupPreview()

        if idx1 >= 0 and idx2_data is not None:
            try:
                gear1_info = self.gears[idx1]
                gear2_info = self.gears[idx2_data]

                center_body_name = gear1_info["param_obj"].BodyName
                center_body = gear1_info["param_obj"].Document.getObject(
                    center_body_name
                )
                gear2_body = gear2_info["body_obj"]

                if center_body and gear2_body:
                    center_origin = center_body.Placement.Base
                    gear2_body_name = gear2_body.Name

                    if gear2_body_name not in self.original_gear2_positions:
                        self.original_gear2_positions[gear2_body_name] = (
                            gear2_body.Placement.Base
                        )

                    original_gear2_origin = self.original_gear2_positions.get(
                        gear2_body_name
                    )

                    if original_gear2_origin:
                        current_distance = original_gear2_origin.sub(center_origin)
                        distance = (
                            current_distance.x**2 + current_distance.y**2
                        ) ** 0.5
                    else:
                        self.current_center_distance = (
                            gear1_info.get("pitch_diameter", 0.0)
                            + gear2_info.get("pitch_diameter", 0.0)
                        ) / 2.0
                        distance = self.current_center_distance

                    angle_rad = rotation_angle * math.pi / 180.0

                    dx = distance * math.cos(angle_rad)
                    dy = distance * math.sin(angle_rad)

                    new_x = center_origin.x + dx
                    new_y = center_origin.y + dy
                    new_z = center_origin.z

                    new_placement = App.Placement(
                        App.Vector(new_x, new_y, new_z),
                        App.Rotation(App.Vector(0, 0, 1), rotation_angle),
                    )

                    self.preview_counter += 1
                    preview_name = f"{self.preview_prefix}_{self.preview_counter}"

                    preview_body = App.ActiveDocument.addObject(
                        "Part::Feature", preview_name
                    )
                    preview_body.Shape = gear2_body.Shape.copy()
                    preview_body.Placement = new_placement

                    if preview_body.ViewObject:
                        preview_body.ViewObject.Transparency = 50

                    self.preview_objects.append(preview_name)

                    App.ActiveDocument.recompute()
            except Exception as e:
                App.Console.PrintError(f"Error creating preview: {e}\n")

    def cleanupPreview(self):
        """Remove all preview objects created by this dialog."""
        if not App.ActiveDocument:
            return

        for obj_name in self.preview_objects[:]:
            try:
                obj = App.ActiveDocument.getObject(obj_name)
                if obj and obj.isValid():
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

                self.current_center_distance = (
                    gear1_info.get("pitch_diameter", 0.0)
                    + gear2_info.get("pitch_diameter", 0.0)
                ) / 2.0

                angle_rad = rotation_angle * math.pi / 180.0

                dx = self.current_center_distance * math.cos(angle_rad)
                dy = self.current_center_distance * math.sin(angle_rad)

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


def calculateCenterDistance(gear1_params: Dict, gear2_params: Dict) -> float:
    """Calculate center distance between two gears.

    Args:
        gear1_params: First gear parameters dict
        gear2_params: Second gear parameters dict

    Returns:
        Center distance in mm
    """
    pitch1 = gear1_params.get("pitch_diameter", 0.0)
    pitch2 = gear2_params.get("pitch_diameter", 0.0)
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

    # Use the calculateCenterDistance method for proper center distance calculation
    center_distance = calculateCenterDistance(gear1_params, gear2_params)

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

        gear1_param_obj.OriginX = new_origin_x
        gear1_param_obj.OriginY = new_origin_y
        gear1_param_obj.OriginZ = new_origin_z
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
