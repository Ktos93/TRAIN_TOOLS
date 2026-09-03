"""Small context/selection helpers shared by operators and UI panels."""
import bpy


def get_selected_track(context):
    """The track entry selected in the Track List, or None."""
    tracks = context.scene.tracks
    index = context.scene.track_index
    if 0 <= index < len(tracks):
        return tracks[index]
    return None


def get_selected_node(context):
    """The node entry selected in the node list of the selected track."""
    track = get_selected_track(context)
    if track is None:
        return None
    index = track.node_index
    if 0 <= index < len(track.nodes):
        return track.nodes[index]
    return None


def track_object_or_none(track):
    """The track's curve object, or None.

    A null PointerProperty on a freshly created PropertyGroup item can
    come back as an unresolvable _PropertyDeferred proxy instead of None
    depending on context, so verify it resolves before use.
    """
    obj = track.track_object
    if obj is None:
        return None
    if not hasattr(obj, "type") or not hasattr(obj, "data"):
        return None
    return obj


def track_for_object(context, obj):
    """The track entry whose curve object is `obj`, or None."""
    for track in context.scene.tracks:
        if track_object_or_none(track) == obj:
            return track
    return None


def selected_point_index(curve_data):
    """Index of the selected bezier control point, or None."""
    spline = None
    for s in curve_data.splines:
        if s.type == 'BEZIER':
            spline = s
            break
    if spline is None:
        return None
    for index, point in enumerate(spline.bezier_points):
        if point.select_control_point:
            return index
    return None


def remove_track_object(track):
    """Delete the curve object of a track and its orphaned curve data.

    Prefers the track_object pointer, falls back to the object name
    used at import time ('Track-<track name>').
    """
    obj = track_object_or_none(track)
    if obj is None:
        obj = bpy.data.objects.get('Track-' + track.name)
    if obj is None:
        return
    curve_data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if curve_data is not None and curve_data.users == 0:
        bpy.data.curves.remove(curve_data)
