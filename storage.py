"""Per-point data storage on the curve datablock.

Blender 4.0 has no custom attributes for curve spline points, so each
track curve carries a `train_points` collection of TrainPoint records,
aligned by index with the curve's bezier control points.

Every control point carries a stable uid (a random uint32) in its
`radius` field, bit-encoded with uint_to_float. The uid never changes:
import assigns one per point and points the user inserts in the
viewport get a fresh one on resync. The depsgraph handler (see
main.py) rebuilds the record list by matching records to points on
this uid, so per-point data follows its point when control points are
inserted or deleted anywhere in the curve.

`track.nodes` is derived data: it is rebuilt from the per-point records
whenever point data changes, so it can never fall out of sync the way
the old manually-managed node list could.
"""
import random
import struct

import bpy
from .dat_format import (KIND_ITEMS, NAMED_KINDS, KIND_LABELS, distance,
                         MARKER_PREFIX)


def float_to_uint(f: float) -> int:
    """Konwertuje float32 na uint32 (bitowo)"""
    return struct.unpack('>I', struct.pack('>f', f))[0]


def uint_to_float(u: int) -> float:
    """Konwertuje uint32 z powrotem na float32"""
    return struct.unpack('>f', struct.pack('>I', u))[0]


# Highest uint32 whose bit pattern is a positive finite float32; uids
# must decode to a value a bezier point radius (float in [0, inf]) can
# store without clamping.
UID_MAX = 0x7F7FFFFF


def generate_uid(taken):
    """A random uint32 not in `taken` that round-trips through a radius.

    uint_to_float/float_to_uint is a bit-level mapping, so any uint in
    1..UID_MAX stores in a radius losslessly; the range only excludes
    bit patterns that would become negative, NaN or infinite floats.
    """
    while True:
        uid = random.randint(1, UID_MAX)
        if uid not in taken:
            return uid


def generate_uids(count, taken=None):
    """`count` fresh unique uids, none of them in `taken` (if given)."""
    taken = set(taken) if taken is not None else set()
    uids = []
    for _ in range(count):
        uid = generate_uid(taken)
        taken.add(uid)
        uids.append(uid)
    return uids


class TrainPoint(bpy.types.PropertyGroup):
    """Per-point data for one bezier control point of a track curve."""
    uid: bpy.props.IntProperty(
        name="UID",
        description="Stable point id, also stored bit-encoded in the "
                    "point's radius",
        default=0,
        min=0,
        max=UID_MAX,
    )
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


class Track_Properties(bpy.types.PropertyGroup):
    """One track entry (a .dat file <-> a bezier curve object)."""
    name: bpy.props.StringProperty(name="Name")
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


def resync_point_records(curve_data):
    """Rebuild the record list against the current bezier control points.

    Points are matched to their old records by the uid stored in the
    point radius, so data follows its point across insertions and
deletions anywhere in the curve. A point whose radius carries no
    matching uid (e.g. just inserted in the viewport) is assigned a
    fresh one.
    """
    spline = get_spline(curve_data)
    if spline is None:
        return
    points = spline.bezier_points
    # Copy the old data to plain Python first: clearing the collection
    # destroys the PropertyGroups, so holding references to them would
    # make every read fall back to property defaults.
    old_data = {}
    for rec in curve_data.train_points:
        if rec.uid and rec.uid not in old_data:
            old_data[rec.uid] = (rec.kind, rec.is_curve, rec.name)
    taken = set(old_data)
    used = set()
    uids = []
    for bp in points:
        uid = float_to_uint(bp.radius) if bp.radius > 0.0 else 0
        if uid not in old_data or uid in used:
            uid = generate_uid(taken)
            taken.add(uid)
            bp.radius = uint_to_float(uid)
        used.add(uid)
        uids.append(uid)
    records = curve_data.train_points
    records.clear()
    for uid in uids:
        rec = records.add()
        rec.uid = uid
        old = old_data.get(uid)
        if old is not None:
            rec.kind, rec.is_curve, rec.name = old


def set_record(curve_data, index, kind, is_curve, name):
    """Write one point's data to its record (list already resynced)."""
    rec = curve_data.train_points[index]
    rec.kind = kind
    rec.is_curve = is_curve
    rec.name = name


def write_points(curve_data, points, uids=None):
    """Replace all records with the given TrainPointData list.

    `uids` (one per point) is the uid to store in each record; when
    omitted, fresh uids are generated.
    """
    if uids is None:
        uids = generate_uids(len(points))
    records = curve_data.train_points
    records.clear()
    for pt, uid in zip(points, uids):
        rec = records.add()
        rec.uid = uid
        rec.kind = pt.kind
        rec.is_curve = pt.is_curve
        rec.name = pt.name


def create_track_curve(track, positions):
    """Build a fresh bezier curve object for `track` from scratch.

    One bezier point per position, each with a fresh uid and a default
    record (kind none, handles enabled). The object is created but not
    linked to any collection.
    """
    curve_data = bpy.data.curves.new('Track-' + track.name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.twist_mode = 'Z_UP'  
    spline = curve_data.splines.new('BEZIER')
    spline.bezier_points.add(len(positions) - 1)
    uids = generate_uids(len(positions))
    for i, pos in enumerate(positions):
        bp = spline.bezier_points[i]
        bp.co = pos
        bp.radius = uint_to_float(uids[i])
    for uid in uids:
        rec = curve_data.train_points.add()
        rec.uid = uid
    return bpy.data.objects.new('Track-' + track.name, curve_data)


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
        item.name = f"{KIND_LABELS[rec.kind]} | {rec.name or 'Unnamed'}"
        item.node_name = rec.name
        item.node_index = index
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
