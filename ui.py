"""N-panel UI for TRAIN TOOLS."""
import bpy

from . import helpers, storage
from .utils import draw_list_with_add_remove


class TRAIN_PT_Tools(bpy.types.Panel):
    bl_label = "Train Tools"
    bl_idname = "TRAIN_PT_Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "TRAIN"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = True

        tracks = context.scene.tracks
        draw_list_with_add_remove(
            layout,
            "train.addtrack",
            "train.deletetrack",
            TRAIN_UL_TRACKS_LIST.bl_idname,
            "",
            context.scene, "tracks",
            context.scene, "track_index",
            rows=3,
        )

        track = helpers.get_selected_track(context)
        if track is None:
            layout.label(text="No track selected", icon='INFO')
            return

        layout.separator()
        layout.prop(track, "name", text="Name")
        layout.prop(track, "type", text="Type")
        layout.label(text="Points: %d (%d curve)"
                     % (track.total_points, track.curve_points))

        layout.separator()
        row = layout.row()
        row.operator("train.import_dat", text="Import .dat")
        row.operator("train.export_dat", text="Export .dat")

        row = layout.row()
        row.operator("train.show", text="Show", icon='RESTRICT_VIEW_OFF')
        row.operator("train.hide", text="Hide", icon='RESTRICT_VIEW_ON')

        layout.separator()
        layout.label(text="Stations & Junctions", icon='PIVOT_POINT')
        node_row = layout.row()
        node_col = node_row.column()
        node_col.template_list(
            TRAIN_UL_NODE_LIST.bl_idname,
            "",
            track, "nodes",
            track, "node_index",
            rows=4,
        )
        side = node_row.column(align=True)
        side.operator("train.refresh_nodes", text="", icon='REFRESH')

        node = helpers.get_selected_node(context)
        if node is not None:
            layout.separator()
            layout.label(text="ID: " + node.id)
            layout.label(text="Point index: %d" % node.node_index)
            layout.operator("train.select_node_point",
                            text="Select Point", icon='RESTRICT_SELECT_OFF')


class TRAIN_PT_Point_Info(bpy.types.Panel):
    bl_label = "Point Info"
    bl_idname = "TRAIN_PT_Point_Info"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "TRAIN"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = True

        obj = context.active_object
        if obj is None or obj.type != 'CURVE':
            layout.label(text="Select a curve point", icon='INFO')
            return
        index = helpers.selected_point_index(obj.data)
        if index is None:
            layout.label(text="Select a control point", icon='INFO')
            return

        scene = context.scene
        layout.label(text="Point %d" % index)
        column = layout.column()
        column.prop(scene, "point_kind", text="Kind")
        column.prop(scene, "point_is_curve", text="Has Handles")
        column.prop(scene, "point_name", text="Name")
        layout.operator("train.apply_point_data", text="Apply to Point")


class TRAIN_UL_TRACKS_LIST(bpy.types.UIList):
    bl_idname = "TRAIN_UL_TRACKS_LIST"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_property, index, flt_flag):
        layout.label(text=item.name, icon_value=icon)


class TRAIN_UL_NODE_LIST(bpy.types.UIList):
    bl_idname = "TRAIN_UL_NODE_LIST"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_property, index, flt_flag):
        layout.label(text=item.name, icon_value=icon)
        layout.label(text="ID %s" % item.id, icon='PIVOT_POINT')
