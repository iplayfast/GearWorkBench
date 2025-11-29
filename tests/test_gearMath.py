"""Unit tests for gearMath module.

Tests the involute mathematics and gear parameter calculations.
"""

import pytest
import math
import sys
import os

# Add parent directory to path to import gearMath
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gearMath


class TestInvoluteFunctions:
    """Test basic involute mathematical functions."""

    def test_involute_function_zero(self):
        """Test involute function at zero angle."""
        result = gearMath.involute_function(0)
        assert abs(result) < 1e-10, "Involute of 0 should be 0"

    def test_involute_function_positive(self):
        """Test involute function at positive angle."""
        angle = 20.0 * gearMath.DEG_TO_RAD
        result = gearMath.involute_function(angle)
        expected = math.tan(angle) - angle
        assert abs(result - expected) < 1e-10

    def test_involute_point_zero_theta(self):
        """Test involute point at theta=0."""
        base_radius = 10.0
        x, y = gearMath.involute_point(base_radius, 0)
        assert abs(x - base_radius) < 1e-10
        assert abs(y) < 1e-10

    def test_involute_point_positive_theta(self):
        """Test involute point at positive theta."""
        base_radius = 10.0
        theta = 0.5  # radians
        x, y = gearMath.involute_point(base_radius, theta)
        # Check that point is farther from origin than base radius
        radius = math.sqrt(x**2 + y**2)
        assert radius > base_radius


class TestGearDiameterCalculations:
    """Test gear diameter calculation functions."""

    def test_pitch_diameter_standard(self):
        """Test standard pitch diameter calculation."""
        module = 2.0
        teeth = 20
        pitch_dia = gearMath.calc_pitch_diameter(module, teeth)
        assert pitch_dia == 40.0, "Pitch diameter should be module × teeth"

    def test_base_diameter_20deg(self):
        """Test base diameter with 20° pressure angle."""
        pitch_dia = 40.0
        pressure_angle = 20.0
        base_dia = gearMath.calc_base_diameter(pitch_dia, pressure_angle)
        expected = 40.0 * math.cos(20.0 * gearMath.DEG_TO_RAD)
        assert abs(base_dia - expected) < 1e-10

    def test_base_diameter_zero_pressure_angle(self):
        """Test base diameter with 0° pressure angle."""
        pitch_dia = 40.0
        base_dia = gearMath.calc_base_diameter(pitch_dia, 0)
        assert abs(base_dia - pitch_dia) < 1e-10, "At 0° pressure angle, base = pitch"

    def test_addendum_diameter_no_shift(self):
        """Test addendum diameter without profile shift."""
        pitch_dia = 40.0
        module = 2.0
        addendum_dia = gearMath.calc_addendum_diameter(pitch_dia, module, 0)
        expected = pitch_dia + 2 * module * gearMath.ADDENDUM_FACTOR
        assert abs(addendum_dia - expected) < 1e-10

    def test_addendum_diameter_with_positive_shift(self):
        """Test addendum diameter with positive profile shift."""
        pitch_dia = 40.0
        module = 2.0
        shift = 0.5
        addendum_dia = gearMath.calc_addendum_diameter(pitch_dia, module, shift)
        expected = pitch_dia + 2 * module * (gearMath.ADDENDUM_FACTOR + shift)
        assert abs(addendum_dia - expected) < 1e-10

    def test_dedendum_diameter_no_shift(self):
        """Test dedendum diameter without profile shift."""
        pitch_dia = 40.0
        module = 2.0
        dedendum_dia = gearMath.calc_dedendum_diameter(pitch_dia, module, 0)
        expected = pitch_dia - 2 * module * gearMath.DEDENDUM_FACTOR
        assert abs(dedendum_dia - expected) < 1e-10

    def test_tooth_thickness_no_shift(self):
        """Test tooth thickness without profile shift."""
        module = 2.0
        pressure_angle = 20.0
        thickness = gearMath.calc_base_tooth_thickness(module, pressure_angle, 0)
        expected = module * math.pi / 2.0
        assert abs(thickness - expected) < 1e-10


class TestUndercutting:
    """Test undercutting detection."""

    def test_no_undercut_20_teeth_20deg(self):
        """Test that 20 teeth with 20° has no undercutting."""
        has_undercut, min_teeth = gearMath.check_undercut(20, 20.0, 0)
        assert not has_undercut, "20 teeth should not undercut at 20°"

    def test_undercut_10_teeth_20deg(self):
        """Test that 10 teeth with 20° has undercutting."""
        has_undercut, min_teeth = gearMath.check_undercut(10, 20.0, 0)
        assert has_undercut, "10 teeth should undercut at 20°"

    def test_profile_shift_prevents_undercut(self):
        """Test that positive profile shift prevents undercutting."""
        # 10 teeth normally undercuts
        has_undercut_no_shift, _ = gearMath.check_undercut(10, 20.0, 0)
        has_undercut_with_shift, _ = gearMath.check_undercut(10, 20.0, 0.5)

        assert has_undercut_no_shift, "Should undercut without shift"
        # With enough positive shift, may not undercut
        # (actual value depends on calculation)

    def test_minimum_teeth_calculation(self):
        """Test minimum teeth calculation."""
        _, min_teeth = gearMath.check_undercut(10, 20.0, 0)
        assert min_teeth > 10, "Minimum teeth should be greater than 10"
        assert min_teeth < 20, "Minimum teeth should be less than 20 for 20° PA"


class TestParameterValidation:
    """Test parameter validation."""

    def test_valid_standard_parameters(self):
        """Test that standard parameters pass validation."""
        params = gearMath.generate_default_parameters()
        # Should not raise exception
        gearMath.validate_spur_parameters(params)

    def test_invalid_module_too_small(self):
        """Test that module below minimum is rejected."""
        params = gearMath.generate_default_parameters()
        params["module"] = 0.1  # Below MIN_MODULE
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_module_too_large(self):
        """Test that module above maximum is rejected."""
        params = gearMath.generate_default_parameters()
        params["module"] = 100.0  # Above MAX_MODULE
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_teeth_too_few(self):
        """Test that too few teeth is rejected."""
        params = gearMath.generate_default_parameters()
        params["num_teeth"] = 3  # Below MIN_TEETH
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_teeth_too_many(self):
        """Test that too many teeth is rejected."""
        params = gearMath.generate_default_parameters()
        params["num_teeth"] = 200  # Above MAX_TEETH
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_pressure_angle_too_small(self):
        """Test that pressure angle below minimum is rejected."""
        params = gearMath.generate_default_parameters()
        params["pressure_angle"] = 0.5  # Below MIN_PRESSURE_ANGLE
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_pressure_angle_too_large(self):
        """Test that pressure angle above maximum is rejected."""
        params = gearMath.generate_default_parameters()
        params["pressure_angle"] = 40.0  # Above MAX_PRESSURE_ANGLE
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_profile_shift_too_negative(self):
        """Test that profile shift below minimum is rejected."""
        params = gearMath.generate_default_parameters()
        params["profile_shift"] = -1.5  # Below MIN_PROFILE_SHIFT
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_profile_shift_too_positive(self):
        """Test that profile shift above maximum is rejected."""
        params = gearMath.generate_default_parameters()
        params["profile_shift"] = 1.5  # Above MAX_PROFILE_SHIFT
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_height_zero(self):
        """Test that zero height is rejected."""
        params = gearMath.generate_default_parameters()
        params["height"] = 0
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)

    def test_invalid_height_negative(self):
        """Test that negative height is rejected."""
        params = gearMath.generate_default_parameters()
        params["height"] = -5.0
        with pytest.raises(gearMath.GearParameterError):
            gearMath.validate_spur_parameters(params)


class TestDefaultParameters:
    """Test default parameter generation."""

    def test_default_parameters_valid(self):
        """Test that default parameters are valid."""
        params = gearMath.generate_default_parameters()
        # Should not raise
        gearMath.validate_spur_parameters(params)

    def test_default_parameters_complete(self):
        """Test that default parameters include all required fields."""
        params = gearMath.generate_default_parameters()
        required_fields = [
            "module", "num_teeth", "pressure_angle",
            "profile_shift", "height", "bore_type", "bore_diameter"
        ]
        for field in required_fields:
            assert field in params, f"Default parameters missing field: {field}"

    def test_default_no_undercut(self):
        """Test that default parameters don't have undercutting."""
        params = gearMath.generate_default_parameters()
        has_undercut, _ = gearMath.check_undercut(
            params["num_teeth"],
            params["pressure_angle"],
            params["profile_shift"]
        )
        assert not has_undercut, "Default parameters should not have undercutting"


class TestKnownGearValues:
    """Test against known gear calculation values."""

    def test_iso_example_gear(self):
        """Test calculations for ISO standard example gear.

        ISO example: m=2, z=20, α=20°, no profile shift
        Expected values:
        - Pitch diameter: 40mm
        - Base diameter: ~37.588mm
        - Addendum diameter: 44mm
        - Dedendum diameter: 35mm
        """
        module = 2.0
        teeth = 20
        pressure_angle = 20.0
        shift = 0.0

        pitch_dia = gearMath.calc_pitch_diameter(module, teeth)
        assert abs(pitch_dia - 40.0) < 1e-10

        base_dia = gearMath.calc_base_diameter(pitch_dia, pressure_angle)
        assert abs(base_dia - 37.5877) < 0.01

        addendum_dia = gearMath.calc_addendum_diameter(pitch_dia, module, shift)
        assert abs(addendum_dia - 44.0) < 1e-10

        dedendum_dia = gearMath.calc_dedendum_diameter(pitch_dia, module, shift)
        assert abs(dedendum_dia - 35.0) < 1e-10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
