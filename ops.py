"""Operators: track management, .dat import/export, point editing."""
import os
import re

import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper

from . import dat_format, helpers, storage


class TRAIN_OT_Add_Track(bpy.types.Operator):
    bl_idname = "train.addtrack"
    bl_label = "Add Track"
    bl_description = "Add a new track with a two-point starting curve"

    def execute(self, context):
        tracks = context.scene.tracks
        tracks.add()
        track = tracks[-1]
        track.name = "New Track %d" % (len(tracks) - 1)
        obj = storage.create_track_curve(
            track, [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)])
        bpy.context.collection.objects.link(obj)
        track.track_object = obj
        track.total_points = len(obj.data.splines[0].bezier_points)
        track.curve_points = sum(
            1 for r in obj.data.train_points if r.is_curve)
        storage.refresh_nodes(track)
        context.scene.track_index = len(tracks) - 1
        # Force the Point Info panel to re-sync from the new records.
        context.scene.train_sync_key = ""
        return {'FINISHED'}


class TRAIN_OT_Delete_Track(bpy.types.Operator):
    bl_idname = "train.deletetrack"
    bl_label = "Delete Track"
    bl_description = "Delete the selected track and its curve object"

    @classmethod
    def poll(cls, context):
        return helpers.get_selected_track(context) is not None

    def execute(self, context):
        track = helpers.get_selected_track(context)
        helpers.remove_track_object(track)
        tracks = context.scene.tracks
        tracks.remove(context.scene.track_index)
        if context.scene.track_index >= len(tracks) and tracks:
            context.scene.track_index = len(tracks) - 1
        return {'FINISHED'}


class TRAIN_OT_Import_Track(bpy.types.Operator, ImportHelper):
    bl_idname = "train.import_dat"
    bl_label = "Import Track (.dat)"
    bl_description = "Import an RDR2 train .dat file into the selected track"
    filename_ext = ".dat"
    filter_glob: bpy.props.StringProperty(default="*.dat", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return helpers.get_selected_track(context) is not None

    def execute(self, context):
        track = helpers.get_selected_track(context)
        ok, message, warning = import_dat_into_track(
            context, track, self.filepath)
        if not ok:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        self.report({'INFO'}, message)
        if warning:
            self.report({'WARNING'}, warning)
        return {'FINISHED'}


def import_dat_into_track(context, track, filepath):
    """Import a single .dat file into a track entry, replacing its curve.

    Returns ``(ok, message, warning)`` where ``warning`` is ``None`` or a
    human-readable string to report alongside a successful import.
    """
    try:
        header, points = dat_format.parse_file(filepath)
    except (OSError, dat_format.DatError) as exc:
        return False, str(exc), None
    if not points:
        return False, "file contains no track points", None

    # Replace any previous curve (and its markers) of this track.
    helpers.remove_track_object(track)

    track.name = os.path.splitext(os.path.basename(filepath))[0]
    track.type = header[2]
    track.total_points = len(points)
    track.curve_points = sum(1 for p in points if p.is_curve)

    curve_data = bpy.data.curves.new('Track-' + track.name, type='CURVE')
    curve_data.dimensions = '3D'
    spline = curve_data.splines.new('BEZIER')
    spline.bezier_points.add(len(points) - 1)
    uids = storage.generate_uids(len(points))
    for i, pt in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = pt.position
        bp.handle_left = pt.handle_a
        bp.handle_right = pt.handle_b
        bp.handle_left_type = 'FREE'
        bp.handle_right_type = 'FREE'
        bp.radius = storage.uint_to_float(uids[i])

    storage.write_points(curve_data, points, uids)

    obj = bpy.data.objects.new('Track-' + track.name, curve_data)
    bpy.context.collection.objects.link(obj)
    track.track_object = obj
    storage.refresh_nodes(track)
    # Force the Point Info panel to re-sync from the new records.
    context.scene.train_sync_key = ""

    message = "Imported %d points (%d curve) from %s" % (
        track.total_points, track.curve_points, os.path.basename(filepath))
    warning = None
    if header[0] != track.total_points or header[1] != track.curve_points:
        warning = ("header says %d/%d points but file has %d/%d"
                   % (header[0], header[1], track.total_points,
                      track.curve_points))
    return True, message, warning


class TRAIN_OT_Import_Folder(bpy.types.Operator):
    bl_idname = "train.import_folder"
    bl_label = "Import Folder (.dat)"
    bl_description = "Import every .dat file in a folder as a new track"
    directory: bpy.props.StringProperty(
        name="Folder",
        description="Folder containing train .dat files",
        subtype='DIR_PATH')

    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "no folder selected")
            return {'CANCELLED'}
        try:
            entries = sorted(os.listdir(self.directory))
        except OSError as exc:
            self.report({'ERROR'}, "cannot read folder: %s" % exc)
            return {'CANCELLED'}
        dat_files = [n for n in entries
                     if n.lower().endswith('.dat')
                     and os.path.isfile(os.path.join(self.directory, n))]
        if not dat_files:
            self.report({'ERROR'}, "no .dat files in %s" % self.directory)
            return {'CANCELLED'}

        tracks = context.scene.tracks
        imported = 0
        for name in dat_files:
            tracks.add()
            track = tracks[-1]
            ok, message, warning = import_dat_into_track(
                context, track, os.path.join(self.directory, name))
            if ok:
                imported += 1
                self.report({'INFO'}, message)
                if warning:
                    self.report({'WARNING'}, "%s: %s" % (name, warning))
            else:
                self.report({'WARNING'}, "skipped %s: %s" % (name, message))
                tracks.remove(len(tracks) - 1)
        self.report({'INFO'}, "Imported %d of %d .dat files"
                    % (imported, len(dat_files)))
        return {'FINISHED'}


class TRAIN_OT_Export_Track(bpy.types.Operator, ExportHelper):
    bl_idname = "train.export_dat"
    bl_label = "Export Track (.dat)"
    bl_description = "Export the selected track curve to an RDR2 train " \
                     ".dat file"
    filename_ext = ".dat"
    filter_glob: bpy.props.StringProperty(default="*.dat", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return helpers.get_selected_track(context) is not None

    def execute(self, context):
        track = helpers.get_selected_track(context)
        ok, message = export_track_to_file(track, self.filepath)
        if not ok:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        self.report({'INFO'}, message)
        return {'FINISHED'}


def export_track_to_file(track, filepath):
    """Write a track's curve to a .dat file.

    Returns ``(ok, message)``.
    """
    obj = helpers.track_object_or_none(track)
    if obj is None or obj.type != 'CURVE':
        return False, "track '%s' has no curve object" % track.name
    curve_data = obj.data
    spline = storage.get_spline(curve_data)
    if spline is None or not spline.bezier_points:
        return False, "track '%s' has no bezier points" % track.name

    points = spline.bezier_points
    storage.resync_point_records(curve_data)
    records = curve_data.train_points

    total = len(points)
    curve_count = sum(1 for r in records if r.is_curve)
    lines = ["%d %d %s" % (total, curve_count, track.type)]
    for i, bp in enumerate(points):
        rec = records[i]
        dist = dat_format.distance(bp.co, points[(i + 1) % total].co)
        lines.append(dat_format.format_point(
            rec.is_curve, bp.co, bp.handle_left, bp.handle_right,
            dist, rec.kind, rec.name))

    try:
        with open(filepath, "w") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        return False, "cannot write file: %s" % exc
    return True, "Exported %d points (%d curve) to %s" % (
        total, curve_count, os.path.basename(filepath))


def safe_filename(name):
    """Replace characters that are invalid in Windows file names."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "track"


class TRAIN_OT_Export_All(bpy.types.Operator):
    bl_idname = "train.export_all"
    bl_label = "Export All Tracks (.dat)"
    bl_description = "Export every track with a curve into a folder, one " \
                     ".dat file per track"
    directory: bpy.props.StringProperty(
        name="Folder",
        description="Folder to write the .dat files to",
        subtype='DIR_PATH')

    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "no folder selected")
            return {'CANCELLED'}
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError as exc:
            self.report({'ERROR'}, "cannot create folder: %s" % exc)
            return {'CANCELLED'}

        exported = 0
        skipped = 0
        for track in context.scene.tracks:
            ok, message = export_track_to_file(
                track, os.path.join(self.directory,
                                     safe_filename(track.name) + ".dat"))
            if ok:
                exported += 1
                self.report({'INFO'}, message)
            else:
                skipped += 1
                self.report({'WARNING'}, "skipped: %s" % message)
        self.report({'INFO'}, "Exported %d track(s), skipped %d"
                    % (exported, skipped))
        return {'FINISHED'}


class TRAIN_OT_Apply_Point_Data(bpy.types.Operator):
    bl_idname = "train.apply_point_data"
    bl_label = "Apply to Selected"
    bl_description = "Write the Point Info values to all selected curve " \
                     "points; the name is written when exactly one point " \
                     "is selected"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'CURVE'
                and helpers.selected_point_index(obj.data) is not None)

    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        spline = storage.get_spline(obj.data)
        storage.resync_point_records(obj.data)
        selected = [i for i, bp in enumerate(spline.bezier_points)
                    if bp.select_control_point]
        name = scene.point_name if len(selected) == 1 else ""
        for index in selected:
            storage.set_record(obj.data, index, scene.point_kind,
                               scene.point_is_curve, name)
        track = helpers.track_for_object(context, obj)
        if track is not None:
            storage.refresh_nodes(track)
        self.report({'INFO'}, "Updated %d point(s)" % len(selected))
        return {'FINISHED'}


class TRAIN_OT_Select_Points_Kind(bpy.types.Operator):
    bl_idname = "train.select_points_kind"
    bl_label = "Select Points by Kind"
    bl_description = "Select all control points of the given kind on the " \
                     "selected track's curve (kind taken from the scene " \
                     "property set in the Point Tools panel)"

    @classmethod
    def poll(cls, context):
        track = helpers.get_selected_track(context)
        obj = helpers.track_object_or_none(track) if track else None
        return (obj is not None and obj.type == 'CURVE'
                and storage.get_spline(obj.data) is not None)

    def execute(self, context):
        track = helpers.get_selected_track(context)
        obj = helpers.track_object_or_none(track)
        spline = storage.get_spline(obj.data)
        storage.resync_point_records(obj.data)
        records = obj.data.train_points
        kind = context.scene.train_select_kind
        count = 0
        for i, bp in enumerate(spline.bezier_points):
            selected = records[i].kind == kind
            bp.select_control_point = selected
            if selected:
                count += 1
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        self.report({'INFO'},
                    "Selected %d point(s) with kind %s"
                    % (count, dat_format.KIND_LABELS[kind]))
        return {'FINISHED'}


class TRAIN_OT_Smooth_Handles(bpy.types.Operator):
    bl_idname = "train.smooth_handles"
    bl_label = "Smooth Handles"
    bl_description = "Set every bezier handle on the selected track's curve " \
                     "to AUTO so the whole curve is smooth"

    @classmethod
    def poll(cls, context):
        track = helpers.get_selected_track(context)
        obj = helpers.track_object_or_none(track) if track else None
        return (obj is not None and obj.type == 'CURVE'
                and storage.get_spline(obj.data) is not None)

    def execute(self, context):
        track = helpers.get_selected_track(context)
        obj = helpers.track_object_or_none(track)
        spline = storage.get_spline(obj.data)
        for bp in spline.bezier_points:
            bp.handle_left_type = 'AUTO'
            bp.handle_right_type = 'AUTO'
        # Force Blender to recompute the auto handle positions.
        bpy.context.view_layer.update()
        self.report({'INFO'}, "Smoothed handles on %d point(s)"
                    % len(spline.bezier_points))
        return {'FINISHED'}


class TRAIN_OT_Toggle_Markers(bpy.types.Operator):
    bl_idname = "train.toggle_markers"
    bl_label = "Toggle Markers"
    bl_description = "Create or remove text markers at all named points of " \
                     "the selected track"

    @classmethod
    def poll(cls, context):
        track = helpers.get_selected_track(context)
        obj = helpers.track_object_or_none(track) if track else None
        return (obj is not None and obj.type == 'CURVE'
                and storage.get_spline(obj.data) is not None)

    def execute(self, context):
        track = helpers.get_selected_track(context)
        obj = helpers.track_object_or_none(track)
        prefix = storage.marker_prefix(track)
        existing = helpers.objects_with_prefix(prefix)
        if existing:
            helpers.remove_objects(existing)
            self.report({'INFO'}, "Removed %d marker(s)" % len(existing))
            return {'FINISHED'}

        spline = storage.get_spline(obj.data)
        records = obj.data.train_points
        count = 0
        for i, bp in enumerate(spline.bezier_points):
            rec = records[i] if i < len(records) else None
            if rec is None or rec.kind not in dat_format.NAMED_KINDS:
                continue
            text = rec.name or "Unnamed"
            name = "%s%d" % (prefix, i)
            marker = bpy.data.objects.new(name,
                                          bpy.data.curves.new(name,
                                                              type='FONT'))
            marker.data.body = text
            marker.data.size = 3.0
            marker.location = bp.co
            marker.parent = obj
            bpy.context.collection.objects.link(marker)
            count += 1
        self.report({'INFO'}, "Created %d marker(s)" % count)
        return {'FINISHED'}


class TRAIN_OT_Select_Node_Point(bpy.types.Operator):
    bl_idname = "train.select_node_point"
    bl_label = "Select Point in Curve"
    bl_description = "Select the control point of the selected node"

    @classmethod
    def poll(cls, context):
        return helpers.get_selected_node(context) is not None

    def execute(self, context):
        node = helpers.get_selected_node(context)
        track = helpers.get_selected_track(context)
        obj = helpers.track_object_or_none(track)
        if obj is None:
            self.report({'ERROR'}, "track has no curve object")
            return {'CANCELLED'}
        spline = storage.get_spline(obj.data)
        if spline is None:
            self.report({'ERROR'}, "track curve has no bezier points")
            return {'CANCELLED'}
        index = node.node_index
        if index >= len(spline.bezier_points):
            self.report({'ERROR'}, "point index %d out of range" % index)
            return {'CANCELLED'}
        for point in spline.bezier_points:
            point.select_control_point = False
        spline.bezier_points[index].select_control_point = True
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        return {'FINISHED'}


class TRAIN_OT_Show(bpy.types.Operator):
    bl_idname = "train.show"
    bl_label = "Show"
    bl_description = "Make the selected track object visible"

    @classmethod
    def poll(cls, context):
        track = helpers.get_selected_track(context)
        return helpers.track_object_or_none(track) is not None

    def execute(self, context):
        obj = helpers.track_object_or_none(
            helpers.get_selected_track(context))
        obj.hide_set(False)
        obj.hide_select = False
        return {'FINISHED'}


class TRAIN_OT_Hide(bpy.types.Operator):
    bl_idname = "train.hide"
    bl_label = "Hide"
    bl_description = "Hide the selected track object from the viewport"

    @classmethod
    def poll(cls, context):
        track = helpers.get_selected_track(context)
        return helpers.track_object_or_none(track) is not None

    def execute(self, context):
        obj = helpers.track_object_or_none(
            helpers.get_selected_track(context))
        obj.hide_set(True)
        obj.hide_select = True
        return {'FINISHED'}
