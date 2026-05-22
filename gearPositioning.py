"""Gear Positioning Tool for GearWorkbench

Positions two gears at the correct center distance for meshing.
User selects exactly 2 PartDesign::Body objects, then clicks Position Gears.
Handles spur/helical (planar), bevel, rack, and mixed gear pairs.

Copyright 2025, Chris Bruner
License LGPL V2.1
"""

import os
import math
import FreeCAD as App
import FreeCADGui
from PySide import QtCore, QtGui

smWBpath = os.path.dirname(os.path.abspath(__file__))
smWB_icons_path = os.path.join(smWBpath, "icons")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def findVarSetForBody(doc, body):
    """Find the VarSet linked to a Body via a Regenerate/Result FeaturePython object."""
    for obj in doc.Objects:
        if (hasattr(obj, "BodyName") and hasattr(obj, "VarSetName")
                and str(obj.BodyName) == body.Name):
            vs = doc.getObject(str(obj.VarSetName))
            if vs is not None:
                return vs
    return None


def isBevelGear(varset):
    """Determine if a VarSet represents a bevel gear."""
    if varset is None:
        return False
    return hasattr(varset, "PitchAngle")


def isInternalGear(varset):
    """Determine if a VarSet represents an internal gear."""
    if varset is None:
        return False
    return "InternalGear" in varset.Name


def isCrownGear(varset):
    """Determine if a VarSet represents a crown gear."""
    if varset is None:
        return False
    return "CrownGear" in varset.Name


def isScrewGear(varset):
    """Determine if a VarSet represents a screw gear."""
    if varset is None:
        return False
    return "ScrewGear" in varset.Name


def isRackGear(varset):
    """Determine if a VarSet represents a rack gear."""
    if varset is None:
        return False
    return "RackGear" in varset.Name or "Rack" in varset.Name


def getGearInfo(doc, body):
    """Get gear info for a body.

    Returns dict with keys:
        pd: pitch diameter (float, mm; 0 for rack gears)
        is_internal: bool
        is_bevel: bool
        is_rack: bool
        pitch_angle: float (degrees, only meaningful for bevel gears; 0 for spur)
        cone_dist: float (mm, only for bevel gears; 0 for others)
        height: float (mm, gear thickness along axis)
        module: float (mm, tooth module)
    Returns None if no gear found.
    """
    vs = findVarSetForBody(doc, body)
    if vs is None:
        return None
    # Rack gears have no PitchDiameter — use 0 so center_dist = PD_pinion/2
    if not hasattr(vs, "PitchDiameter"):
        if hasattr(vs, "Module") and hasattr(vs, "NumberOfTeeth"):
            return {
                "pd": 0.0,
                "is_internal": False,
                "is_bevel": False,
                "is_rack": True,
                "is_crown": False,
                "is_screw": False,
                "pitch_angle": 0.0,
                "cone_dist": 0.0,
                "height": float(vs.Height.Value) if hasattr(vs, "Height") else 10.0,
                "module": float(vs.Module.Value) if hasattr(vs, "Module") else 1.0,
            }
        return None
    info = {
        "pd": float(vs.PitchDiameter),
        "is_internal": isInternalGear(vs),
        "is_bevel": isBevelGear(vs),
        "is_rack": isRackGear(vs),
        "is_crown": isCrownGear(vs),
        "is_screw": isScrewGear(vs),
        "pitch_angle": 0.0,
        "cone_dist": 0.0,
        "height": 0.0,
        "module": float(vs.Module.Value) if hasattr(vs, "Module") else 1.0,
    }
    if info["is_bevel"]:
        info["pitch_angle"] = float(vs.PitchAngle.Value)
        sin_a = math.sin(math.radians(info["pitch_angle"]))
        if sin_a > 0.001:
            info["cone_dist"] = info["pd"] / (2.0 * sin_a)
        if hasattr(vs, "FaceWidth"):
            info["height"] = float(vs.FaceWidth.Value)
    elif info["is_crown"]:
        if hasattr(vs, "FaceWidth"):
            info["height"] = float(vs.FaceWidth.Value)
    elif info["is_screw"]:
        if hasattr(vs, "FaceWidth"):
            info["height"] = float(vs.FaceWidth.Value)
        if hasattr(vs, "HelixAngle"):
            info["helix_angle"] = float(vs.HelixAngle.Value)
    else:
        if hasattr(vs, "Height"):
            info["height"] = float(vs.Height.Value)
    return info


# ---------------------------------------------------------------------------
# Gear Position Dialog — handles all gear type combinations
# ---------------------------------------------------------------------------

class GearPositionDialog(QtGui.QDialog):
    """Unified dialog for positioning two gears.

    Handles:
    - Spur/helical + spur/helical: planar positioning at center distance
    - Bevel + bevel: apex-coincident positioning at shaft angle
    - Bevel + spur (mixed): parallel axes, bevel shifted to align teeth heights
    - Rack + pinion: linear translation along rack
    """

    def __init__(self, doc, body1, body2, info1, info2, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.body1 = body1  # fixed (reference)
        self.body2 = body2  # moving
        self.info1 = info1
        self.info2 = info2
        # Save original placements so swap doesn't cascade positions
        self._orig_placement1 = App.Placement(body1.Placement)
        self._orig_placement2 = App.Placement(body2.Placement)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._setupUI()

    @property
    def _mode(self):
        """Determine positioning mode based on gear types."""
        if self.info1.get("is_rack") or self.info2.get("is_rack"):
            return "rack"
        if self.info1.get("is_crown") or self.info2.get("is_crown"):
            return "crown"
        if self.info1["is_bevel"] and self.info2["is_bevel"]:
            return "bevel_bevel"
        elif self.info1["is_bevel"] or self.info2["is_bevel"]:
            return "mixed"
        else:
            return "planar"

    def _setupUI(self):
        self.setWindowTitle("Position Gears")
        self.setMinimumWidth(340)
        layout = QtGui.QVBoxLayout(self)

        # Gear info
        info_group = QtGui.QGroupBox("Gears")
        info_layout = QtGui.QFormLayout(info_group)
        self.fixed_label = QtGui.QLabel(self._gear_text(self.body1, self.info1))
        self.moving_label = QtGui.QLabel(self._gear_text(self.body2, self.info2))
        info_layout.addRow("Fixed:", self.fixed_label)
        info_layout.addRow("Moving:", self.moving_label)

        swap_btn = QtGui.QPushButton("Swap")
        swap_btn.clicked.connect(self._swap)
        info_layout.addRow("", swap_btn)
        layout.addWidget(info_group)

        # Info labels depending on mode
        info2_layout = QtGui.QFormLayout()
        if self._mode == "bevel_bevel":
            shaft_angle = self.info1["pitch_angle"] + self.info2["pitch_angle"]
            self.info_label = QtGui.QLabel(f"{shaft_angle:.2f}\u00b0")
            info2_layout.addRow("Shaft angle:", self.info_label)
        else:
            cd = self._compute_center_distance()
            self.info_label = QtGui.QLabel(f"{cd:.4f} mm")
            info2_layout.addRow("Center distance:", self.info_label)
        layout.addLayout(info2_layout)

        # Angle (orbit around fixed gear, or slide along rack)
        angle_layout = QtGui.QFormLayout()
        self.angle_spin = QtGui.QDoubleSpinBox()
        self.angle_spin.setRange(0.0, 360.0)
        self.angle_spin.setDecimals(2)
        self.angle_spin.setSingleStep(5.0)
        self.angle_spin.setSuffix("\u00b0")
        self.angle_spin.setValue(0.0)
        self.angle_spin.valueChanged.connect(self._apply)
        if self._mode == "rack":
            angle_layout.addRow("Slide:", self.angle_spin)
        else:
            angle_layout.addRow("Angle:", self.angle_spin)
        layout.addLayout(angle_layout)

        # Phase (rotate moving gear around its own axis to mesh teeth)
        phase_layout = QtGui.QFormLayout()
        self.phase_spin = QtGui.QDoubleSpinBox()
        self.phase_spin.setRange(-180.0, 180.0)
        self.phase_spin.setDecimals(2)
        self.phase_spin.setSingleStep(0.5)
        self.phase_spin.setSuffix("\u00b0")
        self.phase_spin.setValue(0.0)
        self.phase_spin.valueChanged.connect(self._apply)
        phase_layout.addRow("Phase:", self.phase_spin)
        layout.addLayout(phase_layout)

        # Flip (rotate moving gear 180° around X axis)
        self.flip_check = QtGui.QCheckBox("Flip moving gear 180\u00b0")
        self.flip_check.stateChanged.connect(self._apply)
        layout.addWidget(self.flip_check)

        # Close button
        btn_layout = QtGui.QHBoxLayout()
        close_btn = QtGui.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        # Apply initial positioning immediately
        self._apply()

    def _gear_text(self, body, info):
        if info.get("is_rack"):
            return f"{body.Label}  (Rack)"
        txt = f"{body.Label}  (PD: {info['pd']:.3f} mm"
        if info["is_bevel"]:
            txt += f", \u03b4: {info['pitch_angle']:.1f}\u00b0"
        txt += ")"
        return txt

    def _compute_center_distance(self):
        """Compute center distance for display in the info label."""
        pd1 = self.info1["pd"]
        pd2 = self.info2["pd"]
        if self.info1["is_internal"] or self.info2["is_internal"]:
            return abs(pd1 - pd2) / 2.0
        return (pd1 + pd2) / 2.0

    def _swap(self):
        """Swap fixed and moving gears, restoring fixed gear to its original position."""
        # Restore both gears to their original placements before swapping roles
        self.body1.Placement = self._orig_placement1
        self.body2.Placement = self._orig_placement2
        # Swap roles
        self.body1, self.body2 = self.body2, self.body1
        self.info1, self.info2 = self.info2, self.info1
        self._orig_placement1, self._orig_placement2 = self._orig_placement2, self._orig_placement1
        # Update UI
        self.fixed_label.setText(self._gear_text(self.body1, self.info1))
        self.moving_label.setText(self._gear_text(self.body2, self.info2))
        if self._mode == "bevel_bevel":
            shaft_angle = self.info1["pitch_angle"] + self.info2["pitch_angle"]
            self.info_label.setText(f"{shaft_angle:.2f}\u00b0")
        elif self._mode == "crown":
            self.info_label.setText("90.00\u00b0")
        else:
            cd = self._compute_center_distance()
            self.info_label.setText(f"{cd:.4f} mm")
        self._apply()

    def _apply_flip(self, base, rotation):
        """Apply flip around the gear's center if flip is checked.

        When flipped, the gear rotates 180° around its local X-axis through
        its center (at height/2 along its Z-axis), not through its base.

        Returns (adjusted_base, adjusted_rotation).
        """
        if not self.flip_check.isChecked():
            return base, rotation
        height = self.info2["height"]
        # Offset base so the flip pivots around the gear's midpoint.
        # Without flip, center = base + R*(0,0,h/2).
        # With flip (R' = R * Rot(X,180)), center = base' + R'*(0,0,h/2)
        #   = base' + R*(0,0,-h/2).
        # Equating: base' = base + R*(0,0,h).
        base = base + rotation.multVec(App.Vector(0, 0, height))
        rotation = rotation.multiply(App.Rotation(App.Vector(1, 0, 0), 180))
        return base, rotation

    def _apply(self):
        """Position the moving gear based on gear type combination."""
        mode = self._mode
        if mode == "rack":
            self._apply_rack()
        elif mode == "crown":
            self._apply_crown_spur()
        elif mode == "planar":
            self._apply_planar()
        elif mode == "bevel_bevel":
            self._apply_bevel_bevel()
        else:
            self._apply_mixed()

    def _apply_planar(self):
        """Position two planar gears (spur, helical, herringbone, internal)."""
        angle_rad = math.radians(self.angle_spin.value())
        center_dist = self._compute_center_distance()

        fixed_base = self.body1.Placement.Base
        dx = center_dist * math.cos(angle_rad)
        dy = center_dist * math.sin(angle_rad)
        new_base = App.Vector(
            fixed_base.x + dx,
            fixed_base.y + dy,
            fixed_base.z,
        )

        phase_deg = self.phase_spin.value()
        rotation = App.Rotation(App.Vector(0, 0, 1), phase_deg)
        new_base, rotation = self._apply_flip(new_base, rotation)
        self.body2.Placement = App.Placement(new_base, rotation)

    def _apply_rack(self):
        """Position a pinion gear rolling along a rack gear.

        Rack geometry: teeth along X-axis, pointing in -Y direction.
        Pitch line at Y=0 in rack body local coords.
        360 degrees of slide = one full pinion revolution = pi * PD travel.
        """
        slide_deg = self.angle_spin.value()
        phase_deg = self.phase_spin.value()

        # Determine which is rack and which is pinion
        if self.info1.get("is_rack"):
            # Rack is fixed (body1), pinion moves (body2)
            pd_pinion = self.info2["pd"]
            if pd_pinion <= 0:
                pd_pinion = 20.0
            travel = slide_deg / 360.0 * math.pi * pd_pinion

            R_rack = self.body1.Placement.Rotation
            rack_base = self.body1.Placement.Base

            # Pinion at Y = -PD/2 from rack pitch line (on the teeth side)
            offset_local = App.Vector(travel, -pd_pinion / 2.0, 0)
            offset_world = R_rack.multVec(offset_local)
            new_base = rack_base + offset_world

            # Rolling: positive travel (move in +X) → CCW rotation (positive angle)
            roll_deg = slide_deg + phase_deg
            rotation = App.Rotation(App.Vector(0, 0, 1), roll_deg)
            new_base, rotation = self._apply_flip(new_base, rotation)
            self.body2.Placement = App.Placement(new_base, rotation)
        else:
            # Pinion is fixed (body1), rack moves (body2)
            # Use the ORIGINAL placement as the stable reference frame,
            # since body1's rotation gets modified each slider update.
            pd_pinion = self.info1["pd"]
            if pd_pinion <= 0:
                pd_pinion = 20.0
            travel = slide_deg / 360.0 * math.pi * pd_pinion

            pinion_base = self._orig_placement1.Base
            R_frame = self._orig_placement1.Rotation

            # Rack slides along X in pinion's original frame, offset by pd/2 in Y
            offset_local = App.Vector(-travel, pd_pinion / 2.0, 0)
            offset_world = R_frame.multVec(offset_local)
            new_base = pinion_base + offset_world

            # Rack doesn't rotate, stays aligned with pinion's original frame
            self.body2.Placement = App.Placement(new_base, R_frame)

            # Rotate pinion in place to show meshing
            roll_deg = slide_deg + phase_deg
            pinion_rot = R_frame.multiply(App.Rotation(App.Vector(0, 0, 1), roll_deg))
            self.body1.Placement = App.Placement(pinion_base, pinion_rot)

    def _apply_bevel_bevel(self):
        """Position two bevel gears so their inner circle edges touch at one point.

        Both bevel gear bodies have apex at their local origin, flipped 180 deg
        around X. The inner sketch (CoreCircle_Inner) is at local Z = cone_dist_inner
        with radius ~ cdi * sin(pitch_angle).

        Orientation: R_fixed * orbit * tilt * phase (unchanged).
        Position: translate gear2 so the edge of its inner circle just touches
        the edge of gear1's inner circle — one contact point, no intersection.
        """
        shaft_angle = self.info1["pitch_angle"] + self.info2["pitch_angle"]
        orbit_deg = self.angle_spin.value()
        phase_deg = self.phase_spin.value()

        # Fixed gear's orientation (includes its creation flip)
        R_fixed = self.body1.Placement.Rotation

        orbit = App.Rotation(App.Vector(0, 0, 1), orbit_deg)
        tilt = App.Rotation(App.Vector(0, 1, 0), shaft_angle)
        phase = App.Rotation(App.Vector(0, 0, 1), phase_deg)

        # Rotation: R_fixed * orbit * tilt * phase
        rotation = R_fixed.multiply(orbit).multiply(tilt).multiply(phase)

        # --- Compute the touching point between inner circle edges ---
        cone_dist1 = self.info1["cone_dist"]
        cone_dist2 = self.info2["cone_dist"]
        face_width1 = self.info1["height"]
        face_width2 = self.info2["height"]
        pa1_rad = math.radians(self.info1["pitch_angle"])
        pa2_rad = math.radians(self.info2["pitch_angle"])

        cdi1 = cone_dist1 - face_width1
        cdi2 = cone_dist2 - face_width2

        # Inner circle radii (pitch radius at inner cross-section)
        r_inner1 = cdi1 * math.sin(pa1_rad)
        r_inner2 = cdi2 * math.sin(pa2_rad)

        # Axial Z positions of inner circles (slant * cos(pitch_angle))
        z_inner1 = cdi1 * math.cos(pa1_rad)
        z_inner2 = cdi2 * math.cos(pa2_rad)

        # Cone axis directions (local +Z transformed to world by each body's rotation)
        N1 = R_fixed.multVec(App.Vector(0, 0, 1))
        N2 = rotation.multVec(App.Vector(0, 0, 1))

        # Inner circle centers (in world, relative to body base at apex)
        fixed_base = self.body1.Placement.Base
        C1 = fixed_base + R_fixed.multVec(App.Vector(0, 0, z_inner1))

        # Direction on circle 1's plane toward gear2: project gear2's axis onto circle1's plane
        d1 = N2 - N1 * (N2.dot(N1))
        if d1.Length > 1e-9:
            d1.normalize()
        else:
            d1 = App.Vector(1, 0, 0)

        # Direction on circle 2's plane toward gear1: project gear1's axis onto circle2's plane
        d2 = N1 - N2 * (N1.dot(N2))
        if d2.Length > 1e-9:
            d2.normalize()
        else:
            d2 = App.Vector(0, 0, 1)

        # Touch point: edge of circle 1 toward gear2
        P1 = C1 + d1 * r_inner1

        # Offset from gear2's base to its touching edge point
        # = circle2 center offset (axial Z) + radius in direction toward gear1
        P2_from_base = rotation.multVec(App.Vector(0, 0, z_inner2)) + d2 * r_inner2

        # Solve: P1 = new_base + P2_from_base
        new_base = P1 - P2_from_base

        new_base, rotation = self._apply_flip(new_base, rotation)
        self.body2.Placement = App.Placement(new_base, rotation)

    def _apply_crown_spur(self):
        """Position a spur gear meshing with a crown gear at 90 degrees.

        Crown gear: flat disc, teeth pointing up (+Z), axis = Z.
        Spur gear: axis perpendicular to crown's axis (horizontal), positioned
        at the crown's pitch radius with teeth meshing from the side.

        The orbit angle rotates the spur around the crown's axis.
        Phase adjusts mesh engagement rotation.
        """
        orbit_deg = self.angle_spin.value()
        phase_deg = self.phase_spin.value()

        # Identify which is crown and which is spur
        if self.info1.get("is_crown"):
            crown_info = self.info1
            spur_info = self.info2
            crown_body = self.body1
            spur_body = self.body2
            crown_is_fixed = True
        else:
            crown_info = self.info2
            spur_info = self.info1
            crown_body = self.body2
            spur_body = self.body1
            crown_is_fixed = False

        pd_crown = crown_info["pd"]
        pd_spur = spur_info["pd"]
        r_crown = pd_crown / 2.0
        spur_height = spur_info["height"]
        module = crown_info["module"]

        # Crown gear's position and orientation
        R_crown = crown_body.Placement.Rotation
        crown_base = crown_body.Placement.Base

        # Crown's Z axis (teeth point direction) in world
        crown_axis = R_crown.multVec(App.Vector(0, 0, 1))

        # Orbit: spur gear position around the crown's axis
        orbit_rad = math.radians(orbit_deg)
        # Radial direction in crown's local XY plane
        radial_local = App.Vector(math.cos(orbit_rad), math.sin(orbit_rad), 0)
        radial_world = R_crown.multVec(radial_local)

        # Tangent direction (perpendicular to radial, in crown's XY plane)
        tangent_local = App.Vector(-math.sin(orbit_rad), math.cos(orbit_rad), 0)
        tangent_world = R_crown.multVec(tangent_local)

        # Spur gear center at crown's pitch radius along radial direction
        # The spur's axis is along the tangent direction (perpendicular to crown axis
        # and perpendicular to radial — so it meshes from the side)
        spur_center = crown_base + radial_world * r_crown

        # Spur gear rotation: axis along tangent direction, with phase
        # Build rotation that aligns spur's Z axis with tangent_world
        spur_rot = App.Rotation(App.Vector(0, 0, 1), tangent_world)
        phase_rot = App.Rotation(App.Vector(0, 0, 1), phase_deg)
        final_rot = spur_rot.multiply(phase_rot)

        # Offset spur so its mid-height aligns with crown teeth (Z ~ 0 in crown frame)
        # Spur center needs to shift along its own axis (tangent) by half its height
        # to center it on the crown's tooth face
        spur_center = spur_center - tangent_world * (spur_height / 2.0)

        if crown_is_fixed:
            spur_center, final_rot = self._apply_flip(spur_center, final_rot)
            spur_body.Placement = App.Placement(spur_center, final_rot)
        else:
            # Spur is fixed (body1), crown is moving (body2)
            # Position crown so its pitch radius meets the spur's teeth
            spur_base = self._orig_placement1.Base
            R_spur = self._orig_placement1.Rotation

            # Spur's axis is its local Z in world
            spur_axis = R_spur.multVec(App.Vector(0, 0, 1))

            # Crown axis should be perpendicular to spur axis
            # Use orbit to determine the approach direction
            # The "radial" direction from crown center to spur is perpendicular
            # to both crown axis and spur axis. Crown axis = cross(spur_axis, up-ish)
            # For simplicity: crown axis = radial cross spur_axis direction
            # Actually: crown's Z perpendicular to spur's Z, offset by r_crown in radial dir

            # Pick a radial direction perpendicular to spur_axis for the orbit
            # Start with world X, orthogonalize against spur_axis
            ref = App.Vector(1, 0, 0)
            if abs(spur_axis.dot(ref)) > 0.9:
                ref = App.Vector(0, 1, 0)
            perp1 = spur_axis.cross(ref)
            perp1.normalize()
            perp2 = spur_axis.cross(perp1)
            perp2.normalize()

            # Orbit in the plane perpendicular to spur axis
            radial_dir = perp1 * math.cos(orbit_rad) + perp2 * math.sin(orbit_rad)

            # Crown center at r_crown away from spur along radial
            crown_center = spur_base + radial_dir * r_crown

            # Crown axis is perpendicular to spur axis and perpendicular to radial
            crown_z = radial_dir.cross(spur_axis)
            crown_z.normalize()

            crown_rot = App.Rotation(App.Vector(0, 0, 1), crown_z)
            crown_body.Placement = App.Placement(crown_center, crown_rot)

            # Rotate spur in place for phase
            phase_rotation = R_spur.multiply(phase_rot)
            spur_body.Placement = App.Placement(spur_base, phase_rotation)

    def _apply_mixed(self):
        """Position a bevel gear meshing with a spur/helical gear.

        The bevel is tilted by its pitch_angle so its outer tooth face
        is approximately parallel to the spur's teeth. This allows the
        teeth to face each other for meshing.
        """
        orbit_deg = self.angle_spin.value()
        phase_deg = self.phase_spin.value()

        # Determine which is bevel and which is spur
        if self.info2["is_bevel"]:
            self._apply_mixed_bevel_moves(orbit_deg, phase_deg)
        else:
            self._apply_mixed_spur_moves(orbit_deg, phase_deg)

    def _apply_mixed_bevel_moves(self, orbit_deg, phase_deg):
        """Position bevel gear (moving) relative to spur gear (fixed).

        Tilt the bevel by its pitch_angle so the tooth faces are
        approximately parallel to the spur teeth. Position at center
        distance with Z offset to align teeth heights.
        """
        bevel_info = self.info2
        spur_info = self.info1
        cone_dist = bevel_info["cone_dist"]
        pitch_angle = bevel_info["pitch_angle"]
        face_width = bevel_info["height"]
        pd_bevel = bevel_info["pd"]
        pd_spur = spur_info["pd"]
        spur_height = spur_info["height"]
        center_dist = (pd_bevel + pd_spur) / 2.0

        # Fixed (spur) gear's position
        fixed_base = self.body1.Placement.Base

        # Orbit: position around spur in the XY plane
        orbit_rad = math.radians(orbit_deg)
        dx = center_dist * math.cos(orbit_rad)
        dy = center_dist * math.sin(orbit_rad)

        # Z offset: bring bevel teeth to spur mid-height
        # After tilting and flipping, the teeth center is approximately at
        # Z = -cone_dist * cos(pitch_angle) from the bevel apex.
        # Place bevel so its teeth align with spur's mid-height.
        pitch_rad = math.radians(pitch_angle)
        z_teeth = cone_dist * math.cos(pitch_rad)
        z_offset = spur_height / 2.0 - z_teeth

        new_base = App.Vector(
            fixed_base.x + dx,
            fixed_base.y + dy,
            fixed_base.z + z_offset,
        )

        # Bevel rotation: creation flip + tilt by pitch_angle + phase
        flip = App.Rotation(App.Vector(1, 0, 0), 180)
        tilt = App.Rotation(App.Vector(0, 1, 0), pitch_angle)
        phase = App.Rotation(App.Vector(0, 0, 1), phase_deg)
        rotation = flip.multiply(tilt).multiply(phase)
        new_base, rotation = self._apply_flip(new_base, rotation)

        self.body2.Placement = App.Placement(new_base, rotation)

    def _apply_mixed_spur_moves(self, orbit_deg, phase_deg):
        """Position spur gear (moving) relative to bevel gear (fixed).

        The bevel is fixed (already tilted via its Placement). Position
        the spur at center distance from the bevel, at the height where
        the bevel's outer teeth are.
        """
        bevel_info = self.info1
        spur_info = self.info2
        cone_dist = bevel_info["cone_dist"]
        pitch_angle = bevel_info["pitch_angle"]
        pd_bevel = bevel_info["pd"]
        pd_spur = spur_info["pd"]
        spur_height = spur_info["height"]
        center_dist = (pd_bevel + pd_spur) / 2.0

        # Fixed (bevel) gear's position and orientation
        R_fixed = self.body1.Placement.Rotation
        fixed_base = self.body1.Placement.Base

        # The bevel's outer tooth ring is at local Z = cone_dist * cos(pitch_angle).
        # In world, that's at fixed_base + R_fixed * (0, 0, z_outer).
        # The spur should be centered at that height.
        z_outer = cone_dist * math.cos(math.radians(pitch_angle))
        tooth_point_world = R_fixed.multVec(App.Vector(0, 0, z_outer))

        # Radial offset: orbit around the bevel's axis
        orbit_rad = math.radians(orbit_deg)
        # Use the bevel's local XY plane for the orbit
        offset_local = App.Vector(
            center_dist * math.cos(orbit_rad),
            center_dist * math.sin(orbit_rad),
            0,
        )
        offset_world = R_fixed.multVec(offset_local)

        # Spur base: at the bevel tooth level, offset radially
        new_base = fixed_base + tooth_point_world + offset_world
        # Adjust so spur mid-height aligns with bevel teeth
        new_base.z -= spur_height / 2.0

        # Spur gear: just phase rotation
        phase = App.Rotation(App.Vector(0, 0, 1), phase_deg)
        new_base, phase = self._apply_flip(new_base, phase)
        self.body2.Placement = App.Placement(new_base, phase)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class GearPositioningCommand:
    """Command to position two gears beside each other."""

    def GetResources(self):
        return {
            "Pixmap": os.path.join(smWB_icons_path, "positionGears.svg"),
            "MenuText": "&Position Gears",
            "ToolTip": "Position two gears beside each other for proper meshing.\nSelect exactly 2 Bodies first.",
        }

    def IsActive(self):
        sel = FreeCADGui.Selection.getSelection()
        if len(sel) != 2:
            return False
        return all(hasattr(obj, "TypeId") and obj.TypeId == "PartDesign::Body" for obj in sel)

    def Activated(self):
        doc = App.ActiveDocument
        if not doc:
            return

        sel = FreeCADGui.Selection.getSelection()
        if len(sel) != 2:
            QtGui.QMessageBox.warning(
                None, "Selection Error",
                "Please select exactly 2 PartDesign::Body objects.")
            return

        body1, body2 = sel[0], sel[1]

        info1 = getGearInfo(doc, body1)
        info2 = getGearInfo(doc, body2)

        if info1 is None:
            QtGui.QMessageBox.warning(
                None, "Gear Not Found",
                f"Could not find gear parameters for '{body1.Label}'.\n"
                "No Regenerate object links this Body to a VarSet with PitchDiameter.")
            return
        if info2 is None:
            QtGui.QMessageBox.warning(
                None, "Gear Not Found",
                f"Could not find gear parameters for '{body2.Label}'.\n"
                "No Regenerate object links this Body to a VarSet with PitchDiameter.")
            return

        dlg = GearPositionDialog(doc, body1, body2, info1, info2,
                                 parent=FreeCADGui.getMainWindow())
        dlg.show()


FreeCADGui.addCommand("GearPositioningCommand", GearPositioningCommand())
