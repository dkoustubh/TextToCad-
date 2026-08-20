# Core Engineering Skill — ATS Engineering AI

## Purpose
Establishes mechanical engineering standards, unit conversions, geometry normalization, and validation rules across the ATS Engineering AI platform.

## Unit Normalization Standards
All incoming dimensional expressions from engineers or natural language prompts must be normalized to standard SI metric units (millimeters) prior to CAD generation:
- Millimeters (`mm`): Base unit (e.g. `20 mm` -> `20.0`)
- Centimeters (`cm`): Multiply by 10 (e.g. `3 cm` -> `30.0 mm`)
- Meters (`m`): Multiply by 1000 (e.g. `2 m` -> `2000.0 mm`)
- Inches (`in` / `inch`): Multiply by 25.4 (e.g. `2 in` -> `50.8 mm`)

## Geometric Validity Rules
1. **Manifold Solid Requirement**: All exported geometries must be closed, manifold solids with non-zero volume (`Volume > 0`).
2. **OpenCascade BRepCheck**: Every generated B-Rep topology must pass `BRepCheck_Analyzer` with zero topological faults.
3. **Subtractive Feature Integrity**: Hole diameters must be strictly less than the smallest bounding dimension of the parent solid. Hole depths must either be explicit or marked as `through=True`.
4. **Coordinate Consistency**: Relative feature attachments (e.g. "on right side of", "on top of") must compute relative centroid offsets:
   - Right side: `+ (Length_base / 2 + Length_feature / 2)`
   - Left side: `- (Length_base / 2 + Length_feature / 2)`
   - Top: `+ (Height_base / 2 + Height_feature / 2)`
