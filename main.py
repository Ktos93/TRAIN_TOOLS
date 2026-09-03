"""Scene properties, depsgraph sync handler and registration.

The depsgraph handler keeps per-point records in sync with the curve's
bezier control points (rebuilding the list by point uid when the point
count changes, so data follows its point across insertions/deletions)
and refreshes the Point Info panel whenever the selected point changes.
"""
import bpy
from bpy.app.handlers import persistent

from . import helpers, storage
from .ops import (
    TRAIN_OT_Add_Track,
    TRAIN_OT_Delete_Track,
    TRAIN_OT_Import_Track,
    TRAIN_OT_Import_Folder,
    TRAIN_OT_Export_Track,
    TRAIN_OT_Export_All,
    TRAIN_OT_Apply_Point_Data,
    TRAIN_OT_Select_Points_Kind,
    TRAIN_OT_Smooth_Handles,
    TRAIN_OT_Toggle_Markers,
    TRAIN_OT_Refresh_Nodes,
    TRAIN_OT_Select_Node_Point,
    TRAIN_OT_Show,
    TRAIN_OT_Hide,
)
from .ui import (
    TRAIN_PT_Tools,
    TRAIN_PT_Point_Info,
    TRAIN_PT_Point_Tools,
    TRAIN_UL_TRACKS_LIST,
    TRAIN_UL_NODE_LIST,
)


@persistent
def depsgraph_update_post(scene, depsgraph):
    obj = bpy.context.active_object
    if obj is None or obj.type != 'CURVE':
        # Fall back to the selected track's curve so panel sync still
        # happens when the active object lags behind the selection.
        track = helpers.get_selected_track(bpy.context)
        obj = helpers.track_object_or_none(track) if track is not None else None
        if obj is None or obj.type != 'CURVE':
            return
    curve_data = obj.data
    spline = storage.get_spline(curve_data)
    if spline is None:
        return

    # Rebuild the per-point records when the control point count
    # changed (uid matching keeps each point's own data with it).
    total = len(spline.bezier_points)
    if len(curve_data.train_points) != total:
        storage.resync_point_records(curve_data)
        for track in scene.tracks:
            if helpers.track_object_or_none(track) == obj:
                storage.refresh_nodes(track)

    # Refresh the Point Info panel when the selection changed.
    index = helpers.selected_point_index(curve_data)
    if index is None:
        scene.train_sync_key = ""
        return
    key = "%s:%d" % (obj.name, index)
    if scene.train_sync_key == key:
        return
    scene.train_sync_key = key
    scene.curve_point_index = index
    rec = curve_data.train_points[index]
    scene.point_kind = rec.kind
    scene.point_is_curve = rec.is_curve
    scene.point_name = rec.name


def register():
    storage.register()
    for cls in (TRAIN_OT_Add_Track,
                TRAIN_OT_Delete_Track,
                TRAIN_OT_Import_Track,
                TRAIN_OT_Import_Folder,
                TRAIN_OT_Export_Track,
                TRAIN_OT_Export_All,
                TRAIN_OT_Apply_Point_Data,
                TRAIN_OT_Select_Points_Kind,
                TRAIN_OT_Smooth_Handles,
                TRAIN_OT_Toggle_Markers,
                TRAIN_OT_Refresh_Nodes,
                TRAIN_OT_Select_Node_Point,
                TRAIN_OT_Show,
                TRAIN_OT_Hide,
                TRAIN_PT_Tools,
                TRAIN_PT_Point_Info,
                TRAIN_PT_Point_Tools,
                TRAIN_UL_TRACKS_LIST,
                TRAIN_UL_NODE_LIST):
        bpy.utils.register_class(cls)

    if not hasattr(bpy.types.Scene, "tracks"):
        bpy.types.Scene.tracks = bpy.props.CollectionProperty(
            type=storage.Track_Properties, name="Tracks")
    if not hasattr(bpy.types.Scene, "track_index"):
        bpy.types.Scene.track_index = bpy.props.IntProperty(
            name="Selected Track Index")
    if not hasattr(bpy.types.Scene, "curve_point_index"):
        bpy.types.Scene.curve_point_index = bpy.props.IntProperty(
            name="Selected Curve Point Index")
    if not hasattr(bpy.types.Scene, "point_kind"):
        bpy.types.Scene.point_kind = bpy.props.EnumProperty(
            name="Point Kind", default="0", items=storage.KIND_ITEMS)
    if not hasattr(bpy.types.Scene, "point_is_curve"):
        bpy.types.Scene.point_is_curve = bpy.props.BoolProperty(
            name="Has Handles", default=True)
    if not hasattr(bpy.types.Scene, "point_name"):
        bpy.types.Scene.point_name = bpy.props.StringProperty(
            name="Point Name")
    if not hasattr(bpy.types.Scene, "train_select_kind"):
        bpy.types.Scene.train_select_kind = bpy.props.EnumProperty(
            name="Select Kind",
            description="Kind of points to select with 'Select Points'",
            default="0",
            items=storage.KIND_ITEMS)
    if not hasattr(bpy.types.Scene, "train_sync_key"):
        bpy.types.Scene.train_sync_key = bpy.props.StringProperty(
            name="Train Sync Key", description="Internal sync key")

    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_post)


def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_post)

    for prop in ("tracks", "track_index", "curve_point_index",
                 "point_kind", "point_is_curve", "point_name",
                 "train_select_kind", "train_sync_key"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)

    for cls in (TRAIN_UL_NODE_LIST,
                TRAIN_UL_TRACKS_LIST,
                TRAIN_PT_Point_Tools,
                TRAIN_PT_Point_Info,
                TRAIN_PT_Tools,
                TRAIN_OT_Hide,
                TRAIN_OT_Show,
                TRAIN_OT_Select_Node_Point,
                TRAIN_OT_Toggle_Markers,
                TRAIN_OT_Smooth_Handles,
                TRAIN_OT_Select_Points_Kind,
                TRAIN_OT_Apply_Point_Data,
                TRAIN_OT_Export_All,
                TRAIN_OT_Export_Track,
                TRAIN_OT_Import_Folder,
                TRAIN_OT_Import_Track,
                TRAIN_OT_Delete_Track,
                TRAIN_OT_Add_Track):
        bpy.utils.unregister_class(cls)

    storage.unregister()

