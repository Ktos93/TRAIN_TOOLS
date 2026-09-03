# TRAIN TOOLS

Blender addon for editing RDR2 train track `.dat` files as bezier curves.

## Usage

1. Open the sidebar (N key) > **TRAIN** tab.
2. **Add Track**, then **Import .dat** to load a train file into the
   selected track. The file becomes a bezier curve object named
   `Track-<name>`.
3. Edit the curve like any other bezier curve. The **Point Info** panel
   shows the selected control point's data:
   - **Kind** – the `.dat` flag value: None, Station (1), Left Station (2),
     Tunnel (4), Right Station (6), Junction (8), Unknown (32).
   - **Has Handles** – whether the point is exported with explicit handles
     (`c ...` line) or with handles equal to the position.
   - **Name** – station/junction name (only written for named kinds).
   Click **Apply to Point** to write the values.
4. The **Stations & Junctions** list is rebuilt automatically from the
   per-point data; use it to look up a station's game ID (probe hash) or
   to jump to its control point.
5. **Export .dat** writes the curve back to the file format. Distances are
   recomputed from the current point positions.

## Data storage

Per-point data (kind, has handles, name) is stored in a `train_points`
collection of typed records on the curve datablock, aligned by index with
the curve's bezier control points. Blender 4.0 has no custom attributes
for curve spline points, so point radii are left at their default value
and never reused as a data channel.

The record list is kept in sync automatically: adding/removing control
points pads or truncates the list. Note that inserting a point in the
middle of the curve shifts the records of the following points (Blender
4.0 has no stable point IDs), so re-apply flags after restructuring a
curve.

The station/junction list on a track entry is derived data, rebuilt from
the per-point records, so it cannot fall out of sync with the curve.

## File format

```
<total_points> <curve_points> <track_type>
c <x> <y> <z> <hax> <hay> <haz> <hbx> <hby> <hbz> <dist> <flag> [<name>]
<x> <y> <z> <dist> <flag> [<name>]
```

`<dist>` is the distance to the next point (the last point wraps to the
first) and is recomputed on export. Unknown flag values are rejected on
import with a line number.

## Modules

| Module         | Contents                                              |
|----------------|-------------------------------------------------------|
| `dat_format.py`| Pure .dat parsing/formatting (no bpy, unit-testable)  |
| `storage.py`   | Per-point records, derived node list, curve helpers   |
| `helpers.py`   | Selection/context helpers shared by ops and UI        |
| `ops.py`       | Operators (track mgmt, import/export, point editing)  |
| `ui.py`        | N-panel panels and UI lists                           |
| `main.py`      | Scene properties, depsgraph sync, register/unregister |
| `utils.py`     | Game probe hash + shared UI list helper (Sollumz)     |

## Tests

Both tests run inside headless Blender (`blender --background --python`).
Use an isolated user config so unrelated user addons can't interfere:

```
# Windows (git bash) — inline env assignment form required:
BLENDER_USER_CONFIG=<empty-dir> BLENDER_USER_SCRIPTS=<empty-dir>/scripts \
  blender.exe --background \
  --python tests/verify_roundtrip.py -- --dat <file.dat> --out <tmp.dat>

BLENDER_USER_CONFIG=<empty-dir> BLENDER_USER_SCRIPTS=<empty-dir>/scripts \
  blender.exe --background \
  --python tests/verify_editing.py -- --dat <file.dat> --tmp <tmp-dir>

BLENDER_USER_CONFIG=<empty-dir> BLENDER_USER_SCRIPTS=<empty-dir>/scripts \
  blender.exe --background \
  --python tests/verify_ui.py -- --dat <file.dat>
```

`tests/verify_roundtrip.py` is a black-box import/export round trip: curve
geometry, per-point metadata, derived node list, file content (header,
point lines, distances), a re-import, and a clean unregister.

`tests/verify_editing.py` covers the editing workflows: the Apply-to-Point
operator (including the point-selection sync), distance recomputation on
export after moving a point, record padding/truncation on control point
add/remove, corrupt-file rejection, and .blend save/reload persistence.

`tests/verify_ui.py` is a UI smoke test: it drives both N-panel `draw()`
methods and the two `UIList.draw_item()` methods against a mock layout to
catch runtime errors that class registration cannot.
