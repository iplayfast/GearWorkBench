#!/usr/bin/env python3
"""
Quick test script for internal gear generation.
Run this from FreeCAD's Python console to test the internal gear.
"""

import FreeCAD as App
import gearMath

# Create a new document if needed
if not App.ActiveDocument:
    App.newDocument("InternalSpurGearTest")
doc = App.ActiveDocument

# Use simpler default parameters for testing
parameters = gearMath.generateDefaultInternalParameters()
print(f"\nTesting internal gear with parameters:")
print(f"  Module: {parameters['module']}")
print(f"  Teeth: {parameters['num_teeth']}")
print(f"  Pressure angle: {parameters['pressure_angle']}°")
print(f"  Profile shift: {parameters['profile_shift']}")
print(f"  Height: {parameters['height']}")
print(f"  Rim thickness: {parameters['rim_thickness']}")

# Generate the internal gear
try:
    print("\n" + "=" * 60)
    print("Starting internal gear generation...")
    print("=" * 60)
    gearMath.generateInternalSpurGearPart(doc, parameters)
    doc.recompute()
    print("\n" + "=" * 60)
    print("✓ Internal gear generated successfully!")
    print("=" * 60)
    print("\nCheck the FreeCAD window to view the gear.")
    print("Look for:")
    print("  1. Tooth profile at 12 o'clock position")
    print("  2. Teeth pointing INWARD (toward center)")
    print("  3. All arcs should connect smoothly")
    print("  4. Polar pattern should work without freezing")
except Exception as e:
    print("\n" + "=" * 60)
    print(f"✗ Error generating internal gear: {e}")
    print("=" * 60)
    import traceback
    traceback.print_exc()
