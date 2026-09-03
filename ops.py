"""Operators: track management, .dat import/export, point editing."""
import os

import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper

from . import dat_format, helpers, storage


class TRAIN_OT_Add_Track(bpy.types.Operator):
    bl_idname = "train.addtrack"
    bl_label = "Add Track"
    bl_description = "Add a new empty track entry"

    def execute(self, context):
        tracks = context.scene.tracks
        tracks.add()
        track = tracks[-1]
        track.name = "New Track %d" % (len(tracks) - 1)
        track.id = 0
        context.scene.track_index = len(tracks) - 1
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
        try:
            header, points = dat_format.parse_file(self.filepath)
        except (OSError, dat_format.DatError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if not points:
            self.report({'ERROR'}, "file contains no track points")
            return {'CANCELLED'}

        # Replace any previous curve of this track.
        helpers.remove_track_object(track)

        track.name = os.path.splitext(os.path.basename(self.filepath))[0]
        track.type = header[2]
        track.total_points = len(points)
        track.curve_points = sum(1 for p in points if p.is_curve)

        curve_data = bpy.data.curves.new('Track-' + track.name, type='CURVE')
        curve_data.dimensions = '3D'
        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(len(points) - 1)
        for i, pt in enumerate(points):
            bp = spline.bezier_points[i]
            bp.co = pt.position
            bp.handle_left = pt.handle_a
            bp.handle_right = pt.handle_b
            bp.handle_left_type = 'FREE'
            bp.handle_right_type = 'FREE'

        storage.write_points(curve_data, points)

        obj = bpy.data.objects.new('Track-' + track.name, curve_data)
        bpy.context.collection.objects.link(obj)
        track.track_object = obj
        storage.refresh_nodes(track)
        # Force the Point Info panel to re-sync from the new records.
        context.scene.train_sync_key = ""

        self.report({'INFO'},
                    "Imported %d points (%d curve) from %s"
                    % (track.total_points, track.curve_points,
                       os.path.basename(self.filepath)))
        if header[0] != len(points) or header[1] != track.curve_points:
            self.report({'WARNING'},
                        "header says %d/%d points but file has %d/%d"
                        % (header[0], header[1], len(points),
                           track.curve_points))
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
        obj = helpers.track_object_or_none(track)
        if obj is None or obj.type != 'CURVE':
            self.report({'ERROR'}, "track '%s' has no curve object"
                        % track.name)
            return {'CANCELLED'}
        curve_data = obj.data
        spline = storage.get_spline(curve_data)
        if spline is None or not spline.bezier_points:
            self.report({'ERROR'}, "track curve has no bezier points")
            return {'CANCELLED'}

        points = spline.bezier_points
        storage.ensure_point_records(curve_data, len(points))
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
            with open(self.filepath, "w") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError as exc:
            self.report({'ERROR'}, "cannot write file: %s" % exc)
            return {'CANCELLED'}

        self.report({'INFO'},
                    "Exported %d points (%d curve) to %s"
                    % (total, curve_count, os.path.basename(self.filepath)))
        return {'FINISHED'}


class TRAIN_OT_Apply_Point_Data(bpy.types.Operator):
    bl_idname = "train.apply_point_data"
    bl_label = "Apply to Point"
    bl_description = "Write the Point Info panel values to the selected " \
                     "curve point"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'CURVE'
                and helpers.selected_point_index(obj.data) is not None)

    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        index = helpers.selected_point_index(obj.data)
        storage.set_record(obj.data, index, scene.point_kind,
                           scene.point_is_curve, scene.point_name)
        track = helpers.track_for_object(context, obj)
        if track is not None:
            storage.refresh_nodes(track)
        self.report({'INFO'}, "Updated point %d" % index)
        return {'FINISHED'}


class TRAIN_OT_Refresh_Nodes(bpy.types.Operator):
    bl_idname = "train.refresh_nodes"
    bl_label = "Refresh Nodes"
    bl_description = "Rebuild the station/junction list from the curve's " \
                     "point data"

    @classmethod
    def poll(cls, context):
        return helpers.get_selected_track(context) is not None

    def execute(self, context):
        track = helpers.get_selected_track(context)
        count = storage.refresh_nodes(track)
        self.report({'INFO'}, "Node list rebuilt: %d entries" % count)
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
        context.scene.curve_point_index = index
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
