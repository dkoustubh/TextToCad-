# Autodesk Inventor Part Design Skill

## Scope
Defines the tool calling schemas, supported parametric CAD operations, and execution workflows for Autodesk Inventor workstations connected to ATS Engineering AI.

## Supported Inventor CAD Operations
1. `inventor.create_box`:
   - Parameters: `length_mm` (float), `width_mm` (float), `height_mm` (float)
   - Description: Parametric extruded prismatic solid.

2. `inventor.create_box_with_holes`:
   - Parameters: `length_mm`, `width_mm`, `height_mm`, `holes` (list of `HoleDefinition`), `hole_diameter_mm` (float), `hole_count` (int)
   - Description: Prismatic block with subtractive through or blind drilled holes.

3. `inventor.create_cylinder`:
   - Parameters: `diameter_mm` (float), `height_mm` (float), `bore_diameter_mm` (optional float)
   - Description: Cylindrical shaft/tube solid with optional center through bore.

4. `inventor.create_bracket`:
   - Parameters: `length_mm`, `width_mm`, `height_mm`, `flange_thickness_mm`, `rib_thickness_mm`, `hole_diameter_mm`
   - Description: Structural angle bracket with stiffener rib and base mounting holes.

5. `inventor.create_compound`:
   - Parameters: `length_mm`, `width_mm`, `height_mm`, `features` (list of relative offset shapes)
   - Description: Composite multi-feature spatial solid assembly.

## Workstation Routing
- Target Workstation: `192.168.11.150` (Engineer: Koustubh Deodhar)
- Outbound Persistent Connection: Secure WebSocket / HTTP
- Queue Key: `queue:autodesk:192.168.11.150`
- Safe Sequential Execution: Exactly one active CAD operation per workstation at any time.
