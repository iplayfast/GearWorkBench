#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Planetary Gear System Creator

Creates complete planetary gear systems with automatic positioning.
Supports spur, helical, and herringbone gear types.

Copyright 2025, Chris Bruner
License LGPL V2.1
"""

import math
import os
from typing import Dict, Tuple, Optional
import FreeCAD as App

try:
    import FreeCADGui
    from PySide import QtCore, QtGui
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

# Import gear creation functions and feature classes
from genericGear import spurGear, helixGear, herringboneGear
from genericGear import SpurGear, HelixGear, HerringboneGear, ViewProviderGenericGear
from genericInternalGear import internalSpurGear, internalHelixGear, internalHerringboneGear
from genericInternalGear import InternalSpurGear, InternalHelixGear, InternalHerringboneGear
import util

# Get icons path
smWB_icons_path = os.path.join(os.path.dirname(__file__), "Resources", "icons")


# ============================================================================
# Mathematical Helper Functions
# ============================================================================

def calculateRingTeeth(sun: int, planet: int) -> int:
    """Calculate ring teeth from sun and planet teeth.

    Formula: Ring = Sun + 2 × Planet

    Args:
        sun: Number of sun gear teeth
        planet: Number of planet gear teeth

    Returns:
        Number of ring gear teeth
    """
    return sun + 2 * planet


def calculatePlanetTeeth(sun: int, ring: int) -> Optional[int]:
    """Calculate planet teeth from sun and ring teeth.

    Formula: Planet = (Ring - Sun) / 2

    Args:
        sun: Number of sun gear teeth
        ring: Number of ring gear teeth

    Returns:
        Number of planet gear teeth, or None if (Ring - Sun) is not even
    """
    if (ring - sun) % 2 != 0:
        return None  # Not divisible by 2
    return (ring - sun) // 2


def calculateSunTeeth(planet: int, ring: int) -> int:
    """Calculate sun teeth from planet and ring teeth.

    Formula: Sun = Ring - 2 × Planet

    Args:
        planet: Number of planet gear teeth
        ring: Number of ring gear teeth

    Returns:
        Number of sun gear teeth
    """
    return ring - 2 * planet


def validatePlanetInterference(sun_teeth: int, planet_teeth: int, num_planets: int,
                                module: float, helix_angle: float = 0.0) -> Tuple[bool, str]:
    """Check that planet gears don't interfere with each other.

    Args:
        sun_teeth: Number of sun gear teeth
        planet_teeth: Number of planet gear teeth
        num_planets: Number of planet gears
        module: Gear module (normal module for helical)
        helix_angle: Helix angle in degrees (0 for spur)

    Returns:
        (is_valid, error_message) tuple
    """
    # Use transverse module for helical gears
    if helix_angle != 0.0:
        beta_rad = math.radians(helix_angle)
        mt = module / math.cos(beta_rad)
    else:
        mt = module

    # Calculate center distance (sun to planet)
    sun_pitch_dia = mt * sun_teeth
    planet_pitch_dia = mt * planet_teeth
    center_distance = (sun_pitch_dia + planet_pitch_dia) / 2.0

    # Planet tip diameter (addendum = 1.0 * module)
    planet_tip_dia = planet_pitch_dia + 2.0 * mt

    # Minimum spacing between adjacent planets
    min_angle = 360.0 / num_planets
    planet_spacing_distance = 2 * center_distance * math.sin(math.radians(min_angle / 2))

    # Check if planets would overlap (with 10% safety margin)
    if planet_spacing_distance < planet_tip_dia * 1.1:
        return False, f"Planets too close (spacing={planet_spacing_distance:.1f}mm, diameter={planet_tip_dia:.1f}mm)"

    return True, "Planet spacing OK"


def validatePlanetarySystem(sun: int, planet: int, ring: int, num_planets: int,
                             module: float = 1.0, helix_angle: float = 0.0) -> Tuple[bool, str]:
    """Validate planetary gear system constraints.

    Args:
        sun: Number of sun gear teeth
        planet: Number of planet gear teeth
        ring: Number of ring gear teeth
        num_planets: Number of planet gears
        module: Gear module
        helix_angle: Helix angle in degrees

    Returns:
        (is_valid, error_message) tuple
    """
    # Check main constraint
    if ring != sun + 2 * planet:
        return False, f"Ring ({ring}) ≠ Sun ({sun}) + 2×Planet ({planet})"

    # Check divisibility for even spacing
    if (sun + ring) % num_planets != 0:
        return False, f"(Sun + Ring) = {sun + ring} not divisible by {num_planets} planets"

    # Check minimum teeth
    if sun < 6 or planet < 6 or ring < 20:
        return False, "Teeth count too low (Sun≥6, Planet≥6, Ring≥20)"

    # Check helix angle limits
    if abs(helix_angle) > 30.0:
        return False, f"Helix angle too high ({helix_angle}°, max ±30°)"

    # Check planet interference
    interference_ok, interference_msg = validatePlanetInterference(
        sun, planet, num_planets, module, helix_angle
    )
    if not interference_ok:
        return False, interference_msg

    return True, "✓ All constraints satisfied"


def calculatePlanetaryPositions(sun_teeth: int, planet_teeth: int, ring_teeth: int,
                                 num_planets: int, module: float, helix_angle: float = 0.0) -> Dict:
    """Calculate positions for all gears in planetary system.

    Args:
        sun_teeth: Number of sun gear teeth
        planet_teeth: Number of planet gear teeth
        ring_teeth: Number of ring gear teeth
        num_planets: Number of planet gears
        module: Gear module (normal module for helical)
        helix_angle: Helix angle in degrees (0 for spur)

    Returns:
        Dictionary with:
          - sun_position: (x, y, z, angle)
          - planet_positions: [(x1, y1, z1, angle1), ...]
          - ring_position: (x, y, z, angle)
          - center_distance: float (sun center to planet center)
    """
    # For helical gears, use transverse module for pitch diameter
    if helix_angle != 0.0:
        beta_rad = math.radians(helix_angle)
        mt = module / math.cos(beta_rad)  # transverse module
    else:
        mt = module

    sun_pitch_dia = mt * sun_teeth
    planet_pitch_dia = mt * planet_teeth
    center_distance = (sun_pitch_dia + planet_pitch_dia) / 2.0

    # Sun at origin
    sun_position = (0.0, 0.0, 0.0, 0.0)

    # Planets evenly spaced around sun
    planet_positions = []
    angle_step = 360.0 / num_planets
    for i in range(num_planets):
        angle_deg = i * angle_step
        angle_rad = math.radians(angle_deg)

        # Position planet at calculated distance
        x = center_distance * math.cos(angle_rad)
        y = center_distance * math.sin(angle_rad)
        z = 0.0

        # Calculate rotation for proper tooth meshing
        # For external gears meshing, the planet rotates proportional to the gear ratio
        # as it moves around the sun
        planet_angle = -angle_deg * (sun_teeth / planet_teeth)

        planet_positions.append((x, y, z, planet_angle))

    # Ring at origin with no rotation
    # The ring will automatically mesh with planets when they mesh with sun
    # due to the planetary constraint: Ring = Sun + 2*Planet
    ring_position = (0.0, 0.0, 0.0, 0.0)

    return {
        "sun_position": sun_position,
        "planet_positions": planet_positions,
        "ring_position": ring_position,
        "center_distance": center_distance
    }


# ============================================================================
# Gear Creation Function
# ============================================================================

def createPlanetarySystem(doc, gear_type: str, sun_teeth: int, planet_teeth: int,
                          ring_teeth: int, num_planets: int, module: float,
                          pressure_angle: float, height: float, profile_shift: float,
                          backlash: float, helix_angle: float = 0.0,
                          angle2: float = None) -> Dict:
    """Create complete planetary gear system with all gears positioned.

    Creates FeaturePython objects with editable properties for each gear.

    Args:
        doc: FreeCAD document
        gear_type: "Spur", "Helix", or "Herringbone"
        sun_teeth: Number of sun gear teeth
        planet_teeth: Number of planet gear teeth
        ring_teeth: Number of ring gear teeth
        num_planets: Number of planet gears (2-6)
        module: Gear module
        pressure_angle: Pressure angle in degrees
        height: Gear height
        profile_shift: Profile shift coefficient
        backlash: Backlash clearance
        helix_angle: Helix angle in degrees (for Helix/Herringbone)
        angle2: Second angle for herringbone (typically -helix_angle)

    Returns:
        Dictionary with created gear parameter objects
    """
    # Select appropriate feature classes and icons
    if gear_type == "Spur":
        ExternalGearClass = SpurGear
        InternalGearClass = InternalSpurGear
        external_icon = "spurGear.svg"
        internal_icon = "internalSpurGear.svg"
    elif gear_type == "Helix":
        ExternalGearClass = HelixGear
        InternalGearClass = InternalHelixGear
        external_icon = "HelicalGear.svg"
        internal_icon = "internalHelicalGear.svg"
    elif gear_type == "Herringbone":
        ExternalGearClass = HerringboneGear
        InternalGearClass = InternalHerringboneGear
        external_icon = "herringboneGear.svg"
        internal_icon = "internalHerringboneGear.svg"
    else:
        raise ValueError(f"Unknown gear type: {gear_type}")

    # Calculate positions
    positions = calculatePlanetaryPositions(sun_teeth, planet_teeth, ring_teeth,
                                           num_planets, module, helix_angle)

    # CRITICAL: For helical/herringbone gears, planets have OPPOSITE helix angle from sun/ring
    planet_helix_angle = -helix_angle if helix_angle != 0.0 else 0.0
    planet_angle2 = -angle2 if angle2 is not None else None

    # ===== CREATE SUN GEAR =====
    sun_obj = doc.addObject("Part::FeaturePython", "SunGearParameters")
    sun_gear = ExternalGearClass(sun_obj)
    ViewProviderGenericGear(sun_obj.ViewObject, os.path.join(smWB_icons_path, external_icon))

    # Set sun gear properties
    # Set BodyName first before other properties to ensure body is created with correct name
    sun_obj.BodyName = "Sun_Gear"
    sun_obj.Module = module
    sun_obj.NumberOfTeeth = sun_teeth
    sun_obj.PressureAngle = pressure_angle
    sun_obj.Height = height
    sun_obj.ProfileShift = profile_shift
    sun_obj.Backlash = backlash
    sun_obj.OriginX = 0.0
    sun_obj.OriginY = 0.0
    sun_obj.OriginZ = 0.0
    sun_obj.Angle = 0.0
    sun_obj.BoreType = "none"

    if gear_type == "Helix":
        sun_obj.HelixAngle = helix_angle
    elif gear_type == "Herringbone":
        sun_obj.Angle1 = helix_angle
        sun_obj.Angle2 = angle2

    App.Console.PrintMessage(f"Created sun gear with {sun_teeth} teeth\n")

    # ===== CREATE PLANET GEARS =====
    planet_objs = []
    for i, (x, y, z, angle) in enumerate(positions["planet_positions"]):
        planet_obj = doc.addObject("Part::FeaturePython", f"Planet{i+1}GearParameters")
        planet_gear = ExternalGearClass(planet_obj)
        ViewProviderGenericGear(planet_obj.ViewObject, os.path.join(smWB_icons_path, external_icon))

        # Set planet gear properties
        planet_obj.BodyName = f"Planet_Gear_{i+1}"
        planet_obj.Module = module
        planet_obj.NumberOfTeeth = planet_teeth
        planet_obj.PressureAngle = pressure_angle
        planet_obj.Height = height
        planet_obj.ProfileShift = profile_shift
        planet_obj.Backlash = backlash
        planet_obj.OriginX = x
        planet_obj.OriginY = y
        planet_obj.OriginZ = z
        planet_obj.Angle = angle
        planet_obj.BoreType = "none"

        if gear_type == "Helix":
            planet_obj.HelixAngle = planet_helix_angle  # OPPOSITE angle
        elif gear_type == "Herringbone":
            planet_obj.Angle1 = planet_helix_angle  # OPPOSITE angles
            planet_obj.Angle2 = planet_angle2

        planet_objs.append(planet_obj)
        App.Console.PrintMessage(f"Created planet gear {i+1} with {planet_teeth} teeth at ({x:.1f}, {y:.1f})\n")

    # ===== CREATE RING GEAR =====
    ring_obj = doc.addObject("Part::FeaturePython", "RingGearParameters")
    ring_gear = InternalGearClass(ring_obj)
    ViewProviderGenericGear(ring_obj.ViewObject, os.path.join(smWB_icons_path, internal_icon))

    # Set ring gear properties
    # NOTE: Internal gears don't have OriginX/Y/Z or Angle properties
    # They are always created at origin and must be moved manually if needed
    ring_obj.BodyName = "Ring_Gear"
    ring_obj.Module = module
    ring_obj.NumberOfTeeth = ring_teeth
    ring_obj.PressureAngle = pressure_angle
    ring_obj.Height = height
    ring_obj.ProfileShift = profile_shift
    ring_obj.Backlash = backlash
    ring_obj.RimThickness = 3.0

    if gear_type == "Helix":
        ring_obj.HelixAngle = helix_angle  # Same as sun
    elif gear_type == "Herringbone":
        ring_obj.Angle1 = helix_angle  # Same as sun
        ring_obj.Angle2 = angle2

    App.Console.PrintMessage(f"Created ring gear with {ring_teeth} teeth\n")
    App.Console.PrintMessage(f"Planetary system complete: {num_planets} planets, center distance = {positions['center_distance']:.2f}mm\n")

    # Let FreeCAD handle recomputation naturally after all properties are set
    # Calling recompute() manually causes deleted object errors

    return {
        "sun": sun_obj,
        "planets": planet_objs,
        "ring": ring_obj
    }


# ============================================================================
# Dialog Class
# ============================================================================

if GUI_AVAILABLE:
    class PlanetaryGearDialog(QtGui.QDialog):
        """Dialog for creating planetary gear systems."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.sun_teeth_value = 20
            self.planet_teeth_value = 15
            self.ring_teeth_value = 50

            # Store dialog result values
            self.result_gear_type = "Spur"
            self.result_num_planets = 3
            self.result_module = 1.0
            self.result_pressure_angle = 20.0
            self.result_height = 10.0
            self.result_profile_shift = 0.0
            self.result_backlash = 0.0
            self.result_helix_angle = 0.0
            self.result_angle2 = None

            self.setupUI()
            # Don't use WA_DeleteOnClose - we need to read values after close
            # self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        def setupUI(self):
            """Setup dialog UI."""
            self.setWindowTitle("Planetary Gear System Creator")
            self.setMinimumWidth(550)
            self.setMinimumHeight(650)
            self.setModal(True)

            layout = QtGui.QVBoxLayout()

            # Title
            title_label = QtGui.QLabel("Planetary Gear System Creator")
            title_label.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
            layout.addWidget(title_label)

            # Gear type selection
            type_layout = QtGui.QHBoxLayout()
            type_layout.addWidget(QtGui.QLabel("Gear Type:"))
            self.gear_type_combo = QtGui.QComboBox()
            self.gear_type_combo.addItems(["Spur", "Helix", "Herringbone"])
            type_layout.addWidget(self.gear_type_combo)
            type_layout.addStretch()
            layout.addLayout(type_layout)

            # Number of planets
            planets_layout = QtGui.QHBoxLayout()
            planets_layout.addWidget(QtGui.QLabel("Number of Planets:"))
            self.num_planets_spin = QtGui.QSpinBox()
            self.num_planets_spin.setRange(2, 6)
            self.num_planets_spin.setValue(3)
            planets_layout.addWidget(self.num_planets_spin)
            planets_layout.addStretch()
            layout.addLayout(planets_layout)

            layout.addWidget(QtGui.QLabel(""))  # Spacer

            # Gear teeth configuration group
            teeth_group = QtGui.QGroupBox("Gear Teeth Configuration")
            teeth_layout = QtGui.QVBoxLayout()

            # Radio buttons for lock modes
            self.lock_sun_planet_radio = QtGui.QRadioButton("Lock Sun & Planet (calculate Ring)")
            self.lock_sun_ring_radio = QtGui.QRadioButton("Lock Sun & Ring (calculate Planet)")
            self.lock_planet_ring_radio = QtGui.QRadioButton("Lock Planet & Ring (calculate Sun)")
            self.lock_sun_planet_radio.setChecked(True)

            teeth_layout.addWidget(self.lock_sun_planet_radio)

            # Sun teeth
            sun_layout = QtGui.QHBoxLayout()
            sun_layout.addWidget(QtGui.QLabel("  Sun Teeth:"))
            self.sun_teeth_spin = QtGui.QSpinBox()
            self.sun_teeth_spin.setRange(6, 200)
            self.sun_teeth_spin.setValue(20)
            sun_layout.addWidget(self.sun_teeth_spin)
            self.sun_teeth_label = QtGui.QLabel("")
            self.sun_teeth_label.setStyleSheet("color: blue; font-weight: bold;")
            sun_layout.addWidget(self.sun_teeth_label)
            sun_layout.addStretch()
            teeth_layout.addLayout(sun_layout)

            # Planet teeth
            planet_layout = QtGui.QHBoxLayout()
            planet_layout.addWidget(QtGui.QLabel("  Planet Teeth:"))
            self.planet_teeth_spin = QtGui.QSpinBox()
            self.planet_teeth_spin.setRange(6, 200)
            self.planet_teeth_spin.setValue(15)
            planet_layout.addWidget(self.planet_teeth_spin)
            self.planet_teeth_label = QtGui.QLabel("")
            self.planet_teeth_label.setStyleSheet("color: blue; font-weight: bold;")
            planet_layout.addWidget(self.planet_teeth_label)
            planet_layout.addStretch()
            teeth_layout.addLayout(planet_layout)

            # Ring teeth
            ring_layout = QtGui.QHBoxLayout()
            ring_layout.addWidget(QtGui.QLabel("  Ring Teeth:"))
            self.ring_teeth_spin = QtGui.QSpinBox()
            self.ring_teeth_spin.setRange(20, 400)
            self.ring_teeth_spin.setValue(50)
            ring_layout.addWidget(self.ring_teeth_spin)
            self.ring_teeth_label = QtGui.QLabel("50 (calculated)")
            self.ring_teeth_label.setStyleSheet("color: blue; font-weight: bold;")
            ring_layout.addWidget(self.ring_teeth_label)
            ring_layout.addStretch()
            teeth_layout.addLayout(ring_layout)

            teeth_layout.addWidget(QtGui.QLabel(""))  # Spacer
            teeth_layout.addWidget(self.lock_sun_ring_radio)
            teeth_layout.addWidget(self.lock_planet_ring_radio)

            teeth_group.setLayout(teeth_layout)
            layout.addWidget(teeth_group)

            # Common parameters group
            params_group = QtGui.QGroupBox("Common Parameters")
            params_layout = QtGui.QGridLayout()

            # Module
            params_layout.addWidget(QtGui.QLabel("Module:"), 0, 0)
            self.module_spin = QtGui.QDoubleSpinBox()
            self.module_spin.setRange(0.1, 50.0)
            self.module_spin.setValue(1.0)
            self.module_spin.setDecimals(2)
            self.module_spin.setSuffix(" mm")
            params_layout.addWidget(self.module_spin, 0, 1)

            # Pressure angle
            params_layout.addWidget(QtGui.QLabel("Pressure Angle:"), 1, 0)
            self.pressure_angle_spin = QtGui.QDoubleSpinBox()
            self.pressure_angle_spin.setRange(10.0, 30.0)
            self.pressure_angle_spin.setValue(20.0)
            self.pressure_angle_spin.setDecimals(1)
            self.pressure_angle_spin.setSuffix("°")
            params_layout.addWidget(self.pressure_angle_spin, 1, 1)

            # Height
            params_layout.addWidget(QtGui.QLabel("Height:"), 2, 0)
            self.height_spin = QtGui.QDoubleSpinBox()
            self.height_spin.setRange(1.0, 500.0)
            self.height_spin.setValue(10.0)
            self.height_spin.setDecimals(1)
            self.height_spin.setSuffix(" mm")
            params_layout.addWidget(self.height_spin, 2, 1)

            # Profile shift
            params_layout.addWidget(QtGui.QLabel("Profile Shift:"), 3, 0)
            self.profile_shift_spin = QtGui.QDoubleSpinBox()
            self.profile_shift_spin.setRange(-1.0, 1.0)
            self.profile_shift_spin.setValue(0.0)
            self.profile_shift_spin.setDecimals(3)
            params_layout.addWidget(self.profile_shift_spin, 3, 1)

            # Backlash
            params_layout.addWidget(QtGui.QLabel("Backlash:"), 4, 0)
            self.backlash_spin = QtGui.QDoubleSpinBox()
            self.backlash_spin.setRange(0.0, 0.5)
            self.backlash_spin.setValue(0.0)
            self.backlash_spin.setDecimals(3)
            self.backlash_spin.setSuffix(" mm")
            params_layout.addWidget(self.backlash_spin, 4, 1)

            params_group.setLayout(params_layout)
            layout.addWidget(params_group)

            # Helix/Herringbone parameters group
            self.helix_group = QtGui.QGroupBox("Helix/Herringbone Parameters")
            helix_layout = QtGui.QGridLayout()

            helix_layout.addWidget(QtGui.QLabel("Helix Angle:"), 0, 0)
            self.helix_angle_spin = QtGui.QDoubleSpinBox()
            self.helix_angle_spin.setRange(-30.0, 30.0)
            self.helix_angle_spin.setValue(15.0)
            self.helix_angle_spin.setDecimals(1)
            self.helix_angle_spin.setSuffix("°")
            helix_layout.addWidget(self.helix_angle_spin, 0, 1)

            helix_layout.addWidget(QtGui.QLabel("Angle2 (Herringbone):"), 1, 0)
            self.angle2_spin = QtGui.QDoubleSpinBox()
            self.angle2_spin.setRange(-30.0, 30.0)
            self.angle2_spin.setValue(-15.0)
            self.angle2_spin.setDecimals(1)
            self.angle2_spin.setSuffix("°")
            helix_layout.addWidget(self.angle2_spin, 1, 1)

            self.helix_group.setLayout(helix_layout)
            self.helix_group.setEnabled(False)  # Disabled by default
            layout.addWidget(self.helix_group)

            # Validation label
            self.validation_label = QtGui.QLabel("✓ All constraints satisfied")
            self.validation_label.setStyleSheet("color: green; font-weight: bold; margin-top: 10px;")
            layout.addWidget(self.validation_label)

            # Buttons
            button_layout = QtGui.QHBoxLayout()

            self.create_btn = QtGui.QPushButton("Create Planetary System")
            self.create_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
            self.create_btn.clicked.connect(self.onAccept)
            button_layout.addWidget(self.create_btn)

            cancel_btn = QtGui.QPushButton("Cancel")
            cancel_btn.clicked.connect(self.reject)
            button_layout.addWidget(cancel_btn)

            layout.addLayout(button_layout)
            self.setLayout(layout)

            # Connect signals
            self.gear_type_combo.currentIndexChanged.connect(self.onGearTypeChanged)
            self.lock_sun_planet_radio.toggled.connect(self.onLockModeChanged)
            self.lock_sun_ring_radio.toggled.connect(self.onLockModeChanged)
            self.lock_planet_ring_radio.toggled.connect(self.onLockModeChanged)
            self.sun_teeth_spin.valueChanged.connect(self.recalculateAndValidate)
            self.planet_teeth_spin.valueChanged.connect(self.recalculateAndValidate)
            self.ring_teeth_spin.valueChanged.connect(self.recalculateAndValidate)
            self.num_planets_spin.valueChanged.connect(self.recalculateAndValidate)
            self.module_spin.valueChanged.connect(self.recalculateAndValidate)
            self.helix_angle_spin.valueChanged.connect(self.recalculateAndValidate)

            # Initial setup
            self.onLockModeChanged()
            self.recalculateAndValidate()

        def onGearTypeChanged(self):
            """Called when gear type changes."""
            gear_type = self.gear_type_combo.currentText()
            self.helix_group.setEnabled(gear_type in ["Helix", "Herringbone"])
            self.recalculateAndValidate()

        def onLockModeChanged(self):
            """Called when lock mode changes."""
            # Enable/disable spinboxes based on lock mode
            if self.lock_sun_planet_radio.isChecked():
                self.sun_teeth_spin.setEnabled(True)
                self.planet_teeth_spin.setEnabled(True)
                self.ring_teeth_spin.setEnabled(False)
                self.sun_teeth_label.setText("")
                self.planet_teeth_label.setText("")
            elif self.lock_sun_ring_radio.isChecked():
                self.sun_teeth_spin.setEnabled(True)
                self.planet_teeth_spin.setEnabled(False)
                self.ring_teeth_spin.setEnabled(True)
                self.sun_teeth_label.setText("")
                self.ring_teeth_label.setText("")
            else:  # lock_planet_ring
                self.sun_teeth_spin.setEnabled(False)
                self.planet_teeth_spin.setEnabled(True)
                self.ring_teeth_spin.setEnabled(True)
                self.planet_teeth_label.setText("")
                self.ring_teeth_label.setText("")

            self.recalculateAndValidate()

        def recalculateAndValidate(self):
            """Recalculate dependent values and validate system."""
            # Get current values and calculate dependent value
            if self.lock_sun_planet_radio.isChecked():
                sun = self.sun_teeth_spin.value()
                planet = self.planet_teeth_spin.value()
                ring = calculateRingTeeth(sun, planet)
                self.ring_teeth_label.setText(f"{ring} (calculated)")
                self.sun_teeth_value = sun
                self.planet_teeth_value = planet
                self.ring_teeth_value = ring
            elif self.lock_sun_ring_radio.isChecked():
                sun = self.sun_teeth_spin.value()
                ring = self.ring_teeth_spin.value()
                planet = calculatePlanetTeeth(sun, ring)
                if planet is None:
                    self.planet_teeth_label.setText("Invalid")
                    self.validation_label.setText("✗ (Ring-Sun) must be even")
                    self.validation_label.setStyleSheet("color: red; font-weight: bold;")
                    self.create_btn.setEnabled(False)
                    return
                self.planet_teeth_label.setText(f"{planet} (calculated)")
                self.sun_teeth_value = sun
                self.planet_teeth_value = planet
                self.ring_teeth_value = ring
            else:  # lock_planet_ring
                planet = self.planet_teeth_spin.value()
                ring = self.ring_teeth_spin.value()
                sun = calculateSunTeeth(planet, ring)
                self.sun_teeth_label.setText(f"{sun} (calculated)")
                self.sun_teeth_value = sun
                self.planet_teeth_value = planet
                self.ring_teeth_value = ring

            # Validate full system
            num_planets = self.num_planets_spin.value()
            module = self.module_spin.value()
            helix_angle = self.helix_angle_spin.value() if self.gear_type_combo.currentText() != "Spur" else 0.0

            is_valid, message = validatePlanetarySystem(
                self.sun_teeth_value,
                self.planet_teeth_value,
                self.ring_teeth_value,
                num_planets,
                module,
                helix_angle
            )

            if is_valid:
                self.validation_label.setText(message)
                self.validation_label.setStyleSheet("color: green; font-weight: bold;")
                self.create_btn.setEnabled(True)
            else:
                self.validation_label.setText(f"✗ {message}")
                self.validation_label.setStyleSheet("color: red; font-weight: bold;")
                self.create_btn.setEnabled(False)

        def onAccept(self):
            """Store all values before closing dialog."""
            # Store all values in instance variables
            self.result_gear_type = self.gear_type_combo.currentText()
            self.result_num_planets = self.num_planets_spin.value()
            self.result_module = self.module_spin.value()
            self.result_pressure_angle = self.pressure_angle_spin.value()
            self.result_height = self.height_spin.value()
            self.result_profile_shift = self.profile_shift_spin.value()
            self.result_backlash = self.backlash_spin.value()

            # Helix parameters
            if self.result_gear_type != "Spur":
                self.result_helix_angle = self.helix_angle_spin.value()
                if self.result_gear_type == "Herringbone":
                    self.result_angle2 = self.angle2_spin.value()

            # Close dialog
            self.accept()


# ============================================================================
# Command Class
# ============================================================================

class PlanetaryGearCreatorCommand:
    """Command to create planetary gear systems."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "planetaryGear.svg"),
            "MenuText": "&Create Planetary Gear System",
            "ToolTip": "Create a complete planetary gear system with sun, planets, and ring gear",
        }

    def __init__(self):
        pass

    def Activated(self):
        """Called when command is activated."""
        doc = App.ActiveDocument
        if not doc:
            doc = App.newDocument()

        if not GUI_AVAILABLE:
            App.Console.PrintError("GUI not available. Cannot show dialog.\n")
            return

        # Show dialog
        dialog = PlanetaryGearDialog(FreeCADGui.getMainWindow())

        if dialog.exec_() == QtGui.QDialog.Accepted:
            # Get parameters from dialog (stored in result_ variables)
            gear_type = dialog.result_gear_type
            num_planets = dialog.result_num_planets
            sun_teeth = dialog.sun_teeth_value
            planet_teeth = dialog.planet_teeth_value
            ring_teeth = dialog.ring_teeth_value

            # Common parameters
            module = dialog.result_module
            pressure_angle = dialog.result_pressure_angle
            height = dialog.result_height
            profile_shift = dialog.result_profile_shift
            backlash = dialog.result_backlash

            # Helix parameters
            helix_angle = dialog.result_helix_angle
            angle2 = dialog.result_angle2

            # Create gears
            try:
                createPlanetarySystem(
                    doc=doc,
                    gear_type=gear_type,
                    sun_teeth=sun_teeth,
                    planet_teeth=planet_teeth,
                    ring_teeth=ring_teeth,
                    num_planets=num_planets,
                    module=module,
                    pressure_angle=pressure_angle,
                    height=height,
                    profile_shift=profile_shift,
                    backlash=backlash,
                    helix_angle=helix_angle,
                    angle2=angle2
                )
                # Recompute now that all gears have properties set
                doc.recompute()
                if GUI_AVAILABLE:
                    FreeCADGui.SendMsgToActiveView("ViewFit")
                    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
                App.Console.PrintMessage("Planetary gear system created successfully!\n")
            except Exception as e:
                App.Console.PrintError(f"Failed to create planetary system: {str(e)}\n")
                import traceback
                App.Console.PrintError(traceback.format_exc())
                if GUI_AVAILABLE:
                    QtGui.QMessageBox.critical(None, "Error", f"Failed to create system:\n\n{str(e)}")

    def IsActive(self):
        """Return True if command can be activated."""
        return True

    def Deactivated(self):
        """Called when workbench is deactivated."""
        pass

    def execute(self, obj):
        """Execute the feature."""
        pass


# Register command
if GUI_AVAILABLE:
    try:
        FreeCADGui.addCommand("PlanetaryGearCreatorCommand", PlanetaryGearCreatorCommand())
    except Exception:
        pass
