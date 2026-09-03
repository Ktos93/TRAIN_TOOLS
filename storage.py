"""Per-point data storage on the curve datablock.

Blender 4.0 has no custom attributes for curve spline points, so each
track curve carries a `train_points` collection of TrainPoint records,
aligned by index with the curve's bezier control points. Records are
kept in sync by the depsgraph handler (see main.py) and re-validated on
import/export.

`track.nodes` is derived data: it is rebuilt from the per-point records
whenever point data changes, so it can never fall out of sync the way
the old manually-managed node list could.
"""
import bpy
from .dat_format import (KIND_ITEMS, NAMED_KINDS, KIND_LABELS, distance,
                         MARKER_PREFIX)
from .utils import compute_probe_hash


class TrainPoint(bpy.types.PropertyGroup):
    """Per-point data for one bezier control point of a track curve."""
    kind: bpy.props.EnumProperty(
        name="Kind",
        description="Special data stored in the .dat flag column",
        default="0",
        items=KIND_ITEMS,
    )
    is_curve: bpy.props.BoolProperty(
        name="Has Handles",
        description="Export this point with explicit bezier handles 'c' "
                    "line; otherwise the handles equal the position",
        default=True,
    )
    name: bpy.props.StringProperty(
        name="Name",
        description="Station/junction name written after the flag",
    )


class Node_Properties(bpy.types.PropertyGroup):
    """Derived display entry for a station/junction point."""
    name: bpy.props.StringProperty(name="Display",
                                   description="Kind | station name")
    node_name: bpy.props.StringProperty(name="Station")
    node_index: bpy.props.IntProperty(name="Point Index",
                                      description="Index of the control "
                                                  "point in the curve")
    id: bpy.props.StringProperty(name="Game ID",
                                 description="Probe hash computed from the "
                                             "point position")


class Track_Properties(bpy.types.PropertyGroup):
    """One track entry (a .dat file <-> a bezier curve object)."""
    name: bpy.props.StringProperty(name="Name")
    id: bpy.props.IntProperty(name="ID", default=0)
    total_points: bpy.props.IntProperty(name="Total Points")
    curve_points: bpy.props.IntProperty(name="Curve Points")
    type: bpy.props.StringProperty(name="Type", default="close")
    nodes: bpy.props.CollectionProperty(type=Node_Properties)
    node_index: bpy.props.IntProperty(name="Node List Index")
    track_object: bpy.props.PointerProperty(type=bpy.types.Object)


def register():
    bpy.utils.register_class(TrainPoint)
    bpy.utils.register_class(Node_Properties)
    bpy.utils.register_class(Track_Properties)
    bpy.types.Curve.train_points = bpy.props.CollectionProperty(
        type=TrainPoint,
        name="Train Points",
        description="Per-point train data, aligned with bezier control "
                    "points",
    )


def unregister():
    if hasattr(bpy.types.Curve, "train_points"):
        del bpy.types.Curve.train_points
    bpy.utils.unregister_class(Track_Properties)
    bpy.utils.unregister_class(Node_Properties)
    bpy.utils.unregister_class(TrainPoint)


def get_spline(curve_data):
    """The first BEZIER spline of a curve datablock, or None."""
    if curve_data is None or not isinstance(curve_data, bpy.types.Curve):
        return None
    for spline in curve_data.splines:
        if spline.type == 'BEZIER':
            return spline
    return None


def point_count(curve_data):
    spline = get_spline(curve_data)
    if spline is None:
        return 0
    return len(spline.bezier_points)


def ensure_point_records(curve_data, count):
    """Pad or truncate the record list to `count` points.

    Padding appends default records (kind '0', has handles). If points
    were removed, trailing records are dropped. Returns True if the
    collection was modified.
    """
    records = curve_data.train_points
    changed = False
    while len(records) < count:
        records.add()
        changed = True
    while len(records) > count:
        records.remove(len(records) - 1)
        changed = True
    return changed


def set_record(curve_data, index, kind, is_curve, name):
    """Write one point's data (auto-pads the record list if needed).

    Padding only: the list is never truncated here, so writing one
    point cannot destroy the records of the other points.
    """
    records = curve_data.train_points
    while len(records) <= index:
        records.add()
    rec = records[index]
    rec.kind = kind
    rec.is_curve = is_curve
    rec.name = name


def write_points(curve_data, points):
    """Replace all records with the given TrainPointData list."""
    records = curve_data.train_points
    records.clear()
    for pt in points:
        rec = records.add()
        rec.kind = pt.kind
        rec.is_curve = pt.is_curve
        rec.name = pt.name


def point_node_id(position):
    """Game probe hash for a point position (same math as the game)."""
    data = [int(position[0] * 100.0) & 0xFFFFFFFF,
            int(position[1] * 100.0) & 0xFFFFFFFF,
            int(position[2] * 100.0) & 0xFFFFFFFF]
    return compute_probe_hash(data, 0)


def refresh_nodes(track):
    """Rebuild a track's derived node list from its per-point records.

    Returns the number of nodes in the new list.
    """
    nodes = track.nodes
    nodes.clear()
    obj = track.track_object
    if obj is None or not hasattr(obj, "type") or obj.type != 'CURVE':
        return 0
    spline = get_spline(obj.data)
    if spline is None:
        return 0
    records = obj.data.train_points
    for index, bp in enumerate(spline.bezier_points):
        rec = records[index] if index < len(records) else None
        if rec is None or rec.kind not in NAMED_KINDS:
            continue
        item = nodes.add()
        display = rec.name if rec.name else point_node_id(bp.co)
        item.name = f"{KIND_LABELS[rec.kind]} | {display}"
        item.node_name = rec.name
        item.node_index = index
        item.id = point_node_id(bp.co)
    return len(nodes)


def marker_prefix(track):
    """Object-name prefix for the viewport markers of one track.

    Markers are text objects named ``TrainMarker-<track name>-<index>``
    so a track's markers can be found and removed by prefix.
    """
    return MARKER_PREFIX + track.name + "-"


def track_stats(track):
    """Return ``(total_length, kind_counts)`` for a track's curve.

    ``total_length`` is the sum of the straight-line distances between
    consecutive control points, wrapping the last point back to the first
    (the same segments written to the .dat on export). ``kind_counts`` is
    a dict mapping each point kind (string) to how many points have it.
    Returns ``(0.0, {})`` when the track has no curve or no points.
    """
    obj = track.track_object
    if obj is None or not hasattr(obj, "type") or obj.type != 'CURVE':
        return 0.0, {}
    spline = get_spline(obj.data)
    if spline is None:
        return 0.0, {}
    points = spline.bezier_points
    count = len(points)
    if count == 0:
        return 0.0, {}
    records = obj.data.train_points
    total = 0.0
    kind_counts = {}
    for i, bp in enumerate(points):
        total += distance(bp.co, points[(i + 1) % count].co)
        rec = records[i] if i < len(records) else None
        kind = rec.kind if rec is not None else "0"
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    return total, kind_counts
