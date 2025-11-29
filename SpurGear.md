# Involute Spur Gear Generation in FreeCAD

## Overview

This document describes the proper method for generating accurate involute spur gears in FreeCAD using Python, based on standard gear theory and CAD best practices.

## Key Principles

### 1. Involute Curve Definition

The involute of a circle is the curve traced by a point on a taut string as it unwinds from a circle (the base circle).

**Parametric Equations:**
```python
# For a base circle of radius rb, at unwrap angle theta:
x = rb * (cos(theta) + theta * sin(theta))
y = rb * (sin(theta) - theta * cos(theta))
```

**Reference:** Dudley's Handbook of Practical Gear Design, Chapter 2

### 2. Key Gear Dimensions

For a spur gear with module `m`, number of teeth `z`, and pressure angle `α`:

```python
# Basic dimensions (ISO 53:1998)
pitch_diameter = m * z
base_diameter = pitch_diameter * cos(α)
addendum_diameter = pitch_diameter + 2 * m
dedendum_diameter = pitch_diameter - 2 * 1.25 * m

# Tooth thickness at pitch circle
tooth_thickness = (π * m) / 2
```

**Standard Values:**
- Pressure angle: 20° (most common), 14.5° (older), 25° (heavy duty)
- Module: 0.5mm to 25mm (depends on application)

### 3. Geometry Construction Method

The proper CAD approach uses **separate geometric entities**, not a single interpolated curve:

#### Method A: Individual Line/Arc Segments (Recommended for CAD)

1. **Right Involute Curve** - Generate as multiple small line segments or as a proper involute equation curve
2. **Tip Land** - Circular arc at addendum radius
3. **Left Involute Curve** - Mirror of right side
4. **Root Fillet** - Circular arc or trochoid curve at dedendum

**Key Insight:** Most CAD systems (SolidWorks, Fusion 360, etc.) build gear teeth using:
- Equations for involute curves (if supported)
- OR many small line segments approximating the involute
- Proper geometric constraints between segments
- Mirror operations for symmetry

#### Method B: Single Spline Through Points (Not Recommended)

Interpolating a single BSpline through all points causes issues:
- BSpline interpolation adds unwanted curvature
- Periodic BSplines have complex mathematical requirements
- Doesn't accurately represent the involute curve

**The involute IS the exact curve - approximating it with a different curve type defeats the purpose.**

## FreeCAD Implementation Strategy

### Recommended Approach: Use Part.makePolygon() for the Profile

```python
import Part
import FreeCAD as App

def createInvoluteToothProfile(module, teeth, pressure_angle_deg):
    """
    Create tooth profile using polygon approximation of involute.
    Returns a closed Wire object.
    """
    # Calculate dimensions
    pitch_dia = module * teeth
    base_dia = pitch_dia * math.cos(math.radians(pressure_angle_deg))
    addendum_dia = pitch_dia + 2 * module
    dedendum_dia = pitch_dia - 2 * 1.25 * module

    # Generate involute points
    points = []

    # Right flank - involute curve
    for i in range(20):
        theta = theta_root + (i/19) * (theta_tip - theta_root)
        x, y = involute_point(base_radius, theta)
        # Rotate to position
        points.append(App.Vector(x_rotated, y_rotated, 0))

    # Tip land - arc
    for i in range(5):
        angle = angle_right_tip + (i/4) * (angle_left_tip - angle_right_tip)
        x = addendum_radius * math.cos(angle)
        y = addendum_radius * math.sin(angle)
        points.append(App.Vector(x, y, 0))

    # Left flank - involute curve (reverse)
    # ... similar to right flank

    # Root land - arc
    # ... close the profile

    # Create wire from points
    wire = Part.makePolygon(points)
    return wire
```

### Alternative: Use Sketcher with Constraints

```python
import Sketcher

def createConstrainedToothSketch(sketch, module, teeth, pressure_angle):
    """
    Create tooth profile using sketcher constraints.
    This is closer to manual CAD modeling.
    """
    # Add construction circle for base circle
    base_circle = sketch.addGeometry(Part.Circle(...), True)

    # Add involute as multiple small line segments
    prev_point_id = -1
    for i in range(20):
        # Calculate involute point
        line = sketch.addGeometry(Part.LineSegment(...))
        if prev_point_id >= 0:
            sketch.addConstraint(Sketcher.Constraint('Coincident',
                                 prev_point_id, 2, line, 1))
        prev_point_id = line

    # Add tip arc
    tip_arc = sketch.addGeometry(Part.ArcOfCircle(...))
    sketch.addConstraint(Sketcher.Constraint('Coincident', ...))
    sketch.addConstraint(Sketcher.Constraint('Radius', tip_arc, addendum_radius))

    # Continue for left side and root...
```

## Common Mistakes to Avoid

### 1. ❌ Trying to Close a Periodic BSpline with Duplicate Points
```python
# WRONG - causes "Standard_ConstructionError"
profile.append(profile[0])  # Duplicate!
bspline.interpolate(profile, PeriodicFlag=True)
```

### 2. ❌ Using BSpline for Involute Curves
```python
# WRONG - BSpline is not an involute!
bspline.interpolate(involute_points)  # Introduces unwanted curvature
```

### 3. ❌ Generating "Tooth + Gap" for Polar Pattern
```python
# WRONG - polar pattern handles spacing
angular_pitch = 2*pi / teeth
profile_covers_full_angular_pitch  # Don't do this!
```

**Correct:** Generate only the tooth outline. The polar pattern creates the gaps.

### 4. ❌ Incorrect Involute Angle Positioning
```python
# WRONG - forgetting the involute function
angle = theta  # Missing inv(α) term!

# CORRECT
angle = theta + inv_alpha - theta_pitch + half_tooth_angle
```

## Proper Implementation Pattern

```python
def generateSpurGear(doc, module, teeth, pressure_angle, height):
    """
    Proper spur gear generation following CAD best practices.
    """
    # 1. Calculate all dimensions first
    dimensions = calculate_gear_dimensions(module, teeth, pressure_angle)

    # 2. Create body
    body = doc.addObject('PartDesign::Body', 'spur_gear')

    # 3. Create sketch
    sketch = doc.addObject('Sketcher::SketchObject', 'ToothProfile')
    body.addObject(sketch)

    # 4. Generate tooth profile as POLYGON (not spline!)
    tooth_points = generate_involute_tooth_points(dimensions)

    # 5. Add polygon to sketch as connected line segments
    add_polygon_to_sketch(sketch, tooth_points)

    # 6. Pad the tooth
    pad = doc.addObject("PartDesign::Pad", "Tooth")
    body.addObject(pad)
    pad.Profile = sketch
    pad.Length = height

    # 7. Polar pattern
    polar = body.newObject('PartDesign::PolarPattern', 'Teeth')
    polar.Originals = [pad]
    polar.Angle = 360
    polar.Occurrences = teeth

    return body
```

## Key Formulas Reference

### Involute Function
```
inv(α) = tan(α) - α    (in radians!)
```

### Roll Angle at Radius r
```
theta = sqrt((r/rb)² - 1)
where rb = base radius
```

### Tooth Thickness Angle at Pitch Circle
```
half_tooth_angle = (π*m/2) / pitch_radius
```

### Positioning the Involute
At the pitch circle, the involute must be positioned such that:
```
angle_at_pitch = ±half_tooth_angle

Since involute has unwrapped by theta_pitch at pitch radius:
rotation_offset = half_tooth_angle + inv(α) - theta_pitch
```

## Testing & Validation

### Visual Checks
1. **Tooth count** - Count teeth = specified number
2. **Pitch circle** - Measure pitch diameter = module × teeth
3. **Tooth thickness** - At pitch circle ≈ π×module/2
4. **Involute curve** - Should be smooth, no kinks
5. **Profile closure** - No gaps in tooth outline

### Meshing Test
```python
# Generate two gears that should mesh
gear1 = generateSpurGear(doc, module=2, teeth=20, ...)
gear2 = generateSpurGear(doc, module=2, teeth=40, ...)

# Position for meshing
center_distance = module * (20 + 40) / 2  # = 60mm for m=2
# Place gear2 at (60mm, 0, 0)
# Rotate gear2 by: 180° / 40 teeth = 4.5°
```

## References

1. **Dudley's Handbook of Practical Gear Design and Manufacture** - Darle W. Dudley
2. **ISO 53:1998** - Cylindrical gears for general and heavy engineering — Standard basic rack tooth profile
3. **ANSI/AGMA 2001-D04** - Fundamental Rating Factors and Calculation Methods for Involute Spur and Helical Gear Teeth
4. **Machinery's Handbook** - Section on Gears

## Next Steps for Implementation



1. **Abandon BSpline approach** - Use Part.makePolygon() instead

2. **Generate accurate involute points** - Use proper formulas

3. **Use Sketcher line segments** - For better CAD compatibility

4. **Add proper geometric constraints** - If using Sketcher

5. **Test with known gear dimensions** - Validate against standards



## Manual Sketching of a Tooth Profile in FreeCAD Sketcher



For users who prefer to have full manual control over the tooth shape, or for creating custom non-involute profiles, it is possible to sketch the tooth profile directly in the Sketcher workbench. This approach provides great flexibility but requires careful application of constraints to ensure a valid and accurate profile.



Here is a step-by-step guide to manually sketching a single gear tooth, which can then be padded and patterned.



### Step 1: Create Construction Circles



First, create the key reference circles as construction geometry. These will guide the placement of the tooth profile.



1.  Open the **Sketcher Workbench** and create a new sketch on the XY plane.

2.  Using the **Create Circle** tool, draw four concentric circles centered at the origin (0,0).

3.  Select all four circles and toggle them to **Construction Mode**.

4.  Add **Diameter** constraints to each circle corresponding to the gear's dimensions:

    *   Addendum Circle (Tip Circle)

    *   Pitch Circle

    *   Base Circle

    *   Dedendum Circle (Root Circle)



**Example Python Code:**

```python

import FreeCAD as App

import Sketcher

import math



# Example dimensions for a Module 2, 20-tooth gear

module = 2.0

num_teeth = 20

pressure_angle = 20.0



pitch_dia = module * num_teeth

base_dia = pitch_dia * math.cos(math.radians(pressure_angle))

addendum_dia = pitch_dia + 2 * module

dedendum_dia = pitch_dia - 2 * 1.25 * module



# Get the active sketch

sketch = App.ActiveDocument.ActiveSketch



# Add construction circles

c_add = sketch.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), addendum_dia/2), True)

sketch.addConstraint(Sketcher.Constraint('Diameter', c_add, addendum_dia))



c_pitch = sketch.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), pitch_dia/2), True)

sketch.addConstraint(Sketcher.Constraint('Diameter', c_pitch, pitch_dia))



c_base = sketch.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), base_dia/2), True)

sketch.addConstraint(Sketcher.Constraint('Diameter', c_base, base_dia))



c_ded = sketch.addGeometry(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), dedendum_dia/2), True)

sketch.addConstraint(Sketcher.Constraint('Diameter', c_ded, dedendum_dia))

```



### Step 2: Sketch the Right Flank



The involute curve can be approximated by a 3-point arc or a series of small line segments. For simplicity, we'll use an arc here.



1.  Create a **3-Point Arc**.

2.  Place the start point of the arc on the **Base Circle**.

3.  Place the end point of the arc on the **Addendum Circle**.

4.  Place the third point somewhere between the start and end to give the arc its curve.

5.  Add a **Tangent** constraint between the arc and the **Base Circle** at the start point. This is crucial for a correct involute approximation.



### Step 3: Sketch the Tip Land



1.  Create another **3-Point Arc** for the tooth tip.

2.  Constrain the start point of this arc to be **Coincident** with the end point of the right flank arc.

3.  Constrain the arc to be **tangent** to the **Addendum Circle**. In practice, it's easier to make the arc's endpoints symmetric with respect to the Y-axis and coincident with the addendum circle.



### Step 4: Mirror for the Left Flank



1.  Select the right flank arc.

2.  Use the **Mirror** tool.

3.  Select the Y-axis as the mirror axis.

4.  This creates the left flank of the tooth.



### Step 5: Sketch the Root Fillet



1.  Create a **Fillet** (or a small arc) between the start of the right flank (on the base circle) and the dedendum circle.

2.  Do the same for the left flank.

3.  Alternatively, draw a single arc for the root, connecting the start points of the two flanks, and make it tangent to both.



### Step 6: Add Final Constraints



1.  Ensure all points are connected with **Coincident** constraints to form a closed loop.

2.  Add a **Symmetry** constraint to the start and end points of the tip land arc with respect to the Y-axis.

3.  Add a **Dimension** constraint for the tooth thickness at the pitch circle. A simple way is to add a horizontal distance constraint between the points where the flanks intersect the pitch circle.

    *   `tooth_thickness = (math.pi * module) / 2`



This manual process gives you a fully constrained sketch of a single tooth. You can then exit the sketch, use **Pad** to give it thickness, and finally use a **Polar Pattern** to create the full gear.



## External Resources



### How to Model Accurate Involute Spur Gears in SOLIDWORKS



The article explains how to model accurate involute spur gears in SOLIDWORKS using global variables and parametric equations, which is crucial for simulations or non-traditional manufacturing. It details setting up primary parameters like diametral pitch, pressure angle, and number of teeth, along with secondary parameters for face width and bore diameter. The core steps involve sketching a gear blank, defining the tooth profile with an equation-driven involute curve, and then patterning these features to create a dynamic gear model.



**Source:** [How to Model Accurate Involute Spur Gears in SOLIDWORKS](https://hawkridgesys.com/blog/how-to-model-accurate-involute-spur-gears-in-solidworks)
