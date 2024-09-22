import bpy
import math
import os
from mathutils import Vector
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.app.handlers import persistent

from .utils import draw_list_with_add_remove, get_new_item_id, compute_probe_hash


class ParsedData:
    def __init__(self, position, handle_a, handle_b, is_curve, is_station,is_left_station,is_right_station, station_name, is_junction, is_tunnel, is_unk):
        self.position = position
        self.handle_a = handle_a
        self.handle_b = handle_b
        self.is_curve = is_curve
        self.is_station = is_station
        self.is_left_station = is_left_station
        self.is_right_station = is_right_station
        self.station_name = station_name
        self.is_junction = is_junction
        self.is_tunnel = is_tunnel
        self.is_unk = is_unk


    def get_combined_flags(self):
        flags = 0
        flags |= (1 << 0) if self.is_curve else 0  # Bit 0
        flags |= (1 << 1) if self.is_station else 0  # Bit 1
        flags |= (1 << 2) if self.is_left_station else 0  # Bit 1
        flags |= (1 << 3) if self.is_right_station else 0  # Bit 1
        flags |= (1 << 4) if self.is_junction else 0  # Bit 2
        flags |= (1 << 5) if self.is_tunnel else 0  # Bit 3
        flags |= (1 << 6) if self.is_unk else 0  # Bit 4
        
        return flags
    
    def decode_flags(combined_flags):
        combined_flags = int(combined_flags)
        is_curve = bool(combined_flags & (1 << 0))  # Check Bit 0
        is_station = bool(combined_flags & (1 << 1))  # Check Bit 1
        is_left_station = bool(combined_flags & (1 << 2))  # Check Bit 1
        is_right_station = bool(combined_flags & (1 << 3))  # Check Bit 1
        is_junction = bool(combined_flags & (1 << 4))  # Check Bit 2
        is_tunnel = bool(combined_flags & (1 << 5))  # Check Bit 3
        is_unk = bool(combined_flags & (1 << 6))  # Check Bit 4

        return {
            'is_curve': is_curve,
            'is_station': is_station,
            'is_left_station': is_left_station,
            'is_right_station': is_right_station,
            'is_junction': is_junction,
            'is_tunnel': is_tunnel,
            'is_unk': is_unk
        }

    def __repr__(self):
        return (f"Position: {self.position}, Handle A: {self.handle_a}, Handle B: {self.handle_b}, "
                f"Is Curve: {self.is_curve}, Is Station: {self.is_station}, "
                f"Is Junction: {self.is_junction}, Is Tunnel: {self.is_tunnel}, Is Unk: {self.is_unk}")

def parse_line(line):
    tokens = line.split()
    if tokens[0] == 'c':
        is_curve = True
        position = (float(tokens[1]), float(tokens[2]), float(tokens[3]))
        handle_a = (float(tokens[4]), float(tokens[5]), float(tokens[6]))
        handle_b = (float(tokens[7]), float(tokens[8]), float(tokens[9]))
        
        # position = (position[0], position[2], position[1])
        # handle_a = (handle_a[0], handle_a[2], handle_a[1])
        # handle_b = (handle_b[0], handle_b[2], handle_b[1])

        is_station = tokens[11] == "1"
        is_left_station = tokens[11] == "2"
        is_right_station = tokens[11] == "6"
        is_junction = tokens[11] == "8"
        is_tunnel = tokens[11] == "4"
        is_unk = tokens[11] == "32"

        name = tokens[12] if is_station or is_left_station or is_right_station or is_junction else None
    else:
        is_curve = False
        position = (float(tokens[0]), float(tokens[1]), float(tokens[2]))
        
        # position = (position[0], position[1], position[2])
        handle_a = position
        handle_b = position

        is_station = tokens[4] == "1"
        is_left_station = tokens[4] == "2"
        is_right_station = tokens[4] == "6"
        is_junction = tokens[4] == "8"
        is_tunnel = tokens[4] == "4"
        is_unk = tokens[4] == "32"
        
        name = tokens[5] if is_station or is_left_station or is_right_station or is_junction else None
    
    return ParsedData(position, handle_a, handle_b, is_curve, is_station, is_left_station, is_right_station, name, is_junction, is_tunnel, is_unk)

def distance(p1, p2):
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    dz = p1[2] - p2[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)

def export_to_text(point, distance, node_name):
        flags = ParsedData.decode_flags(point.radius)

        if flags["is_curve"]:
            pos = f"{point.co[0]:.4f} {point.co[1]:.4f} {point.co[2]:.4f}"
            handle_a = f"{point.handle_left[0]:.4f} {point.handle_left[1]:.4f} {point.handle_left[2]:.4f}"
            handle_b = f"{point.handle_right[0]:.4f} {point.handle_right[1]:.4f} {point.handle_right[2]:.4f}"
            flag = "0"
            station_text = ""
            if flags["is_station"]:
                flag = "1" 
                station_text = node_name
            elif flags["is_left_station"]:
                flag = "2" 
                station_text = node_name
            elif flags["is_right_station"]:
                flag = "6" 
                station_text = node_name
            elif flags["is_junction"]:
                flag = "8" 
                station_text = node_name
            elif flags["is_tunnel"]:
                flag = "4" 
            elif flags["is_unk"]:
                flag = "32" 
            return f"c {pos} {handle_a} {handle_b} {distance:.4f} {flag} {station_text}"
        else:
            pos = f"{point.co[0]:.4f} {point.co[1]:.4f} {point.co[2]:.4f}"
            flag = "0"
            station_text = ""
            if flags["is_station"]:
                flag = "1" 
                station_text = node_name
            elif flags["is_left_station"]:
                flag = "2" 
                station_text = node_name
            elif flags["is_right_station"]:
                flag = "6" 
                station_text = node_name
            elif flags["is_junction"]:
                flag = "8" 
                station_text = node_name
            elif flags["is_tunnel"]:
                flag = "4" 
            elif flags["is_unk"]:
                flag = "32" 
                
            return f"{pos} {distance:.4f} {flag} {station_text}"



class TRAIN_PT_Tools(bpy.types.Panel):
    bl_label = "Train Tools"
    bl_idname = "TRAIN_PT_Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TRAIN'
    bl_order = 1

    def draw(self, context):
        layout = self.layout

        layout.use_property_split = True
        layout.use_property_decorate = True

        list_col, _ = draw_list_with_add_remove(layout, "train.addtrack", "train.deletetrack",
                                                TRAIN_UL_TRACKS_LIST.bl_idname, "", context.scene, "tracks", context.scene, "track_index", rows=3)

        selected_track = get_selected_track(context)
        if not selected_track:
            return

        layout.separator()
        for prop_name in Track_Properties.__annotations__:
            if prop_name in ["id"]:
                continue
            layout.prop(selected_track, prop_name)





        list_col.operator("train.import")
        list_col.operator("train.export")

        layout.label(text="Nodes | If you move station/junction link to list will break!!!")
        list_col, _ = draw_list_with_add_remove(layout, "train.addnode", "train.deletenode",
                                                        TRAIN_UL_NODE_LIST.bl_idname, "", selected_track, "nodes", selected_track, "node_index", rows=3)
        
        selected_node = get_selected_node(context)
        if selected_node:
            layout.separator()
            for prop_name in Node_Properties.__annotations__:
                if prop_name in ["id"]:
                    continue
                layout.prop(selected_node, prop_name)
            

        row = list_col.row()
        pie = row.menu_pie()
        pie.operator("train.show", icon="HIDE_OFF")
        pie.operator("train.hide", icon="HIDE_ON")
       
    


class TRAIN_UL_TRACKS_LIST(bpy.types.UIList):
    bl_idname = "TRAIN_UL_TRACKS_LIST"
    item_icon = "PRESET"

class TRAIN_UL_NODE_LIST(bpy.types.UIList):
    bl_idname = "TRAIN_UL_NODE_LIST"
    item_icon = "PRESET"



class TRAIN_OT_Add_Track(bpy.types.Operator):
    bl_idname = "train.addtrack"
    bl_label = "Add track"

    def execute(self, context):
        tracks = context.scene.tracks
        item_id = get_new_item_id(tracks)
        item = tracks.add()
        item.id = item_id
        item.name = f"track.{item.id}"
        return {'FINISHED'}
    

class TRAIN_OT_Add_Node(bpy.types.Operator):
    bl_idname = "train.addnode"
    bl_label = "Add Node"

    def execute(self, context):

        obj = context.active_object
        
        if not obj or obj.type != 'CURVE':
            return  {"CANCELLED"}
        
        spline = obj.data.splines.active
        if not spline:
            return  {"CANCELLED"}
        
        point = spline.bezier_points[context.scene.curve_point_index]
        
        if not point.select_control_point:
            return {"CANCELLED"}
        
        flags = ParsedData.decode_flags(point.radius)

        if not flags["is_station"] and not flags["is_left_station"] and not flags["is_right_station"] and not flags["is_junction"]:
             return {"CANCELLED"}


        track = get_selected_track(context) 
        nodes = track.nodes


        data = {}
        data[0] = int(point.co[0] * 100.0)& 0xFFFFFFFF
        data[1] = int(point.co[1] * 100.0) & 0xFFFFFFFF
        data[2] = int(point.co[2] * 100.0) & 0xFFFFFFFF
        new_id = compute_probe_hash(data, 0)   
        item = nodes.add()
        item.id = new_id
        item.node_index = context.scene.curve_point_index
        item.name = f"{('STATION' if flags['is_station'] else 'LEFT STATION' if flags['is_left_station'] else 'RIGHT STATION' if flags['is_right_station'] else 'JUNCTION' if flags['is_junction'] else 'UNKNOWN')} | {item.id}"
        return {'FINISHED'}
    

class TRAIN_OT_Delete_Track(bpy.types.Operator):
    bl_idname = "train.deletetrack"
    bl_label = "Delete track"

    @classmethod
    def poll(cls, context):
        return get_selected_track(context) is not None
    
    def execute(self, context):
       
        track = get_selected_track(context) 
        object_name = 'Track-' + track.name
        if object_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[object_name], do_unlink=True)
            
        tracks = context.scene.tracks
        track_index = context.scene.track_index 
        tracks.remove(track_index)   
        context.space_data.show_gizmo = context.space_data.show_gizmo
        return {'FINISHED'}
    


class TRAIN_OT_Delete_Node(bpy.types.Operator):
    bl_idname = "train.deletenode"
    bl_label = "Delete Node"

    @classmethod
    def poll(cls, context):
        return get_selected_track(context) is not None
    
    def execute(self, context):

        track = get_selected_track(context) 
        nodes = track.nodes
        node_index = track.node_index 
        nodes.remove(node_index)   
        context.space_data.show_gizmo = context.space_data.show_gizmo
        return {'FINISHED'}
    

class TRAIN_OT_Import_Track(bpy.types.Operator, ImportHelper):
    bl_idname = "train.import"
    bl_label = "Import track"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(
        default="*.dat",
        options={'HIDDEN'}
    )

    @classmethod
    def poll(cls, context):
        return get_selected_track(context) is not None

    def execute(self, context):
       file_path = self.filepath
       try:
           parsed_data = []
           with open(file_path, 'r') as file:
                type = next(file).strip().split()[2]
    
                for line in file:
                    parsed_line = parse_line(line.strip())
                    if parsed_line is not None:
                        parsed_data.append(parsed_line)

                track = get_selected_track(context)

                object_name = 'Track-' + track.name
                if object_name in bpy.data.objects:
                    bpy.data.objects.remove(bpy.data.objects[object_name], do_unlink=True)

                track.name = os.path.splitext(os.path.basename(file_path))[0]
                track.type = type 
                track.total_points = len(parsed_data)
                track.curve_points = sum(1 for data in parsed_data if data.is_curve)
                curve_data = bpy.data.curves.new('BezierCurve', type='CURVE')
                curve_data.dimensions = '3D'  
                curve_data.twist_mode = 'Z_UP'  
                
                spline = curve_data.splines.new('BEZIER')
                spline.bezier_points.add(len(parsed_data) - 1 ) 
                nodes = track.nodes
                for i, point in enumerate(parsed_data):
                    bp = spline.bezier_points[i]
                    bp.co = Vector(point.position)
                    bp.handle_left = Vector(point.handle_a)
                    bp.handle_right = Vector(point.handle_b)
                    bp.radius = point.get_combined_flags() 
                    bp.handle_left_type = 'FREE'
                    bp.handle_right_type = 'FREE' 

                    if point.is_station or point.is_left_station or point.is_right_station or point.is_junction:
                        data = {}
                        data[0] = int(bp.co[0] * 100.0) & 0xFFFFFFFF
                        data[1] = int(bp.co[1] * 100.0) & 0xFFFFFFFF
                        data[2] = int(bp.co[2] * 100.0) & 0xFFFFFFFF
                        new_id = compute_probe_hash(data, 0)   
                        item = nodes.add()
                        item.id = new_id
                        item.node_index = i
                        item.node_name = point.station_name
                        item.name = f"{('STATION' if point.is_station else 'LEFT STATION' if point.is_left_station else 'RIGHT STATION' if point.is_right_station else 'JUNCTION' if point.is_junction else 'UNKNOWN')} | {point.station_name}"



                curve_object = bpy.data.objects.new('BezierCurveObject', curve_data)
                curve_object.name = 'Track-' + track.name
                bpy.context.collection.objects.link(curve_object)
                

               
                track.track_object = curve_object
                self.report({'INFO'}, "File imported successfully")
       except Exception as e:
           self.report({'ERROR'}, f"Failed to import file: {e}")
       return {'FINISHED'}



class TRAIN_OT_Export_Track(bpy.types.Operator, ExportHelper):
    bl_idname = "train.export"
    bl_label = "Export track"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".dat"

    @classmethod
    def poll(cls, context):
        return get_selected_track(context) is not None

    def execute(self, context):
        file_path = self.filepath
        try:
            track = get_selected_track(context)

            # Gather data to export (example: track type, total points, curve points)
            track_type = track.type
            total_points = track.total_points
            curve_points = track.curve_points
            nodes = track.nodes

            # Get curve object data (example: Bezier points)
            curve_object = track.track_object
            if not curve_object:
                return
            
            curve_data = curve_object.data.splines.active
            
            export_data = []
            export_data.append(f"{total_points} {curve_points} {track_type}")
            if curve_data.bezier_points:
                for i in range(len(curve_data.bezier_points)):
                    point = curve_data.bezier_points[i]


                    data = {}
                    data[0] = int(point.co[0] * 100.0)& 0xFFFFFFFF
                    data[1] = int(point.co[1] * 100.0) & 0xFFFFFFFF
                    data[2] = int(point.co[2] * 100.0) & 0xFFFFFFFF
                    index = compute_probe_hash(data, 0)   
                  
                    found_node = None
                    for node in nodes:
                        if node.id == index:
                            found_node = node
                            break
                    node_name = ""
                    if found_node:
                        node_name = node.node_name
                    

                    if i < len(curve_data.bezier_points) - 1:
                        next_point = curve_data.bezier_points[i + 1]
                        dist_to_next = distance(point.co, next_point.co)
                    else:
                        next_point = curve_data.bezier_points[0]
                        dist_to_next = distance(point.co, next_point.co)
                    
                    export_data.append(export_to_text(point, dist_to_next, node_name))

            # Write data to file
            with open(file_path, 'w') as file:
                for line in export_data:
                    file.write(f"{line}\n")

            self.report({'INFO'}, f"File exported successfully: {file_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to export file: {e}")

        return {'FINISHED'}



class TRAIN_OT_Show(bpy.types.Operator):
    bl_idname = "train.show"
    bl_label = "Show Track"

    @classmethod
    def poll(cls, context):
        track = get_selected_track(context)
        if track is None:
            return False   
        if not track.track_object:
            return False
        if not track.track_object.hide_viewport:
            return False
        return True


    def execute(self, context):

        track = get_selected_track(context) 
        track.track_object.hide_viewport = False

     
        return {'FINISHED'}
    

class TRAIN_OT_Hide(bpy.types.Operator):
    bl_idname = "train.hide"
    bl_label = "Hide track"

    @classmethod
    def poll(cls, context):
        track = get_selected_track(context)
        if track is None:
            return False   
        if not track.track_object:
            return False
        if track.track_object.hide_viewport:
            return False
        return True

    def execute(self, context):

        track = get_selected_track(context) 
        track.track_object.hide_viewport = True

        return {'FINISHED'}



def get_selected_track(context) -> 'Track_Properties':
    tracks = context.scene.tracks
    track_index = context.scene.track_index
    if 0 <= track_index < len(tracks):
        return tracks[track_index]
    else:
        return None
    
def get_selected_node(context) -> 'Node_Properties':
    tracks = context.scene.tracks
    track_index = context.scene.track_index
    if 0 <= track_index < len(tracks):
        nodes = tracks[track_index].nodes
        node_index = tracks[track_index].node_index
        if 0 <= node_index < len(nodes):
            return nodes[node_index]
        else:
            return None
    else:
        return None

class Node_Properties(bpy.types.PropertyGroup):

    name: bpy.props.StringProperty(name="List")
    node_name: bpy.props.StringProperty(name="Node Name")
    node_index: bpy.props.IntProperty(name="Node Index")
    id: bpy.props.StringProperty(name="Id")

class Track_Properties(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
   
    id: bpy.props.IntProperty(name="Id")

    total_points: bpy.props.IntProperty(name="Total Points")

    curve_points: bpy.props.IntProperty(name="Curve Points")

    type: bpy.props.StringProperty(name="Type")

    nodes: bpy.props.CollectionProperty(type=Node_Properties, name="Nodes")

    node_index: bpy.props.IntProperty(name="Curve Points")

    track_object: bpy.props.PointerProperty(
        name="Target Object",
        type=bpy.types.Object,
        description="Reference to a target object"
    )



  
   


class TRAIN_OT_Set_Point_Data(bpy.types.Operator):
    bl_idname = "train.set_point_data"
    bl_label = "Set Flags"

    @classmethod
    def poll(cls, context):
        return get_selected_track(context) is not None

    def execute(self, context):

        obj = context.active_object
        
        if not obj or obj.type != 'CURVE':
            return
        
        spline = obj.data.splines.active
        if not spline:
            return
        
        flags = 0
        flags |= (1 << 0) if context.scene.is_curve else 0  # Bit 0
        flags |= (1 << 1) if context.scene.is_station else 0  # Bit 1
        flags |= (1 << 2) if context.scene.is_left_station else 0  # Bit 1
        flags |= (1 << 3) if context.scene.is_right_station else 0  # Bit 1
        flags |= (1 << 4) if context.scene.is_junction else 0  # Bit 2
        flags |= (1 << 5) if context.scene.is_tunnel else 0  # Bit 3
        flags |= (1 << 6) if context.scene.is_unk else 0  # Bit 4

        point = spline.bezier_points[context.scene.curve_point_index]
        
        if point:
            if point.select_control_point:
                point.radius = flags
      

        return {'FINISHED'}


class TRAIN_PT_Location_Tools(bpy.types.Panel):
    bl_label = "Selected Point Info"
    bl_idname = "TRAIN_PT_Location_Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TRAIN'
    bl_order = 2

    def draw(self, context):
        layout = self.layout


        obj = context.active_object
        
        if not obj or obj.type != 'CURVE':
            layout.label(text="Nothing Selected")
            return

        spline = obj.data.splines.active
        if not spline:
            layout.label(text="Nothing Selected")
            return

        point_index = None
        if spline.bezier_points:
            selected_point = None
            for i, point in enumerate(spline.bezier_points):
                if point.select_control_point:
                    point_index = i
                    break

        if point_index is None:
            layout.label(text="Nothing Selected")
            return
        
        layout.label(text=f"Point Index: {context.scene.curve_point_index}")

        row = layout.row()
        row.operator("train.set_point_data")
       
        column = layout.column()
        column.prop(context.scene, "is_curve")
        column.prop(context.scene, "is_station")
        column.prop(context.scene, "is_left_station")
        column.prop(context.scene, "is_right_station")
        column.prop(context.scene, "is_junction")
        column.prop(context.scene, "is_tunnel")
        column.prop(context.scene, "is_unk")
       

@persistent
def update_custom_properties(scene, depsgraph):
    obj = bpy.context.active_object

    if obj and obj.type == 'CURVE': 

        for spline in obj.data.splines:
            for point in spline.bezier_points:
                if point.select_control_point:
                    
                    point_index = spline.bezier_points[:].index(point)
                    
                    if scene.curve_point_index == point_index:
                        return
                    
                    scene.curve_point_index = point_index

                    flags = ParsedData.decode_flags(spline.bezier_points[point_index].radius)
                    scene.is_curve = flags['is_curve']
                    scene.is_station = flags['is_station']
                    scene.is_left_station = flags['is_left_station']
                    scene.is_right_station = flags['is_right_station']
                    scene.is_junction = flags['is_junction']
                    scene.is_tunnel = flags['is_tunnel']
                    scene.is_unk = flags['is_unk']
                    return

    

classes = (
    TRAIN_PT_Tools,
    TRAIN_PT_Location_Tools,
    TRAIN_OT_Set_Point_Data,
    TRAIN_OT_Add_Track,
    TRAIN_OT_Delete_Track,
    TRAIN_OT_Hide,
    TRAIN_OT_Show,
    TRAIN_OT_Import_Track,
    TRAIN_OT_Export_Track,
    Node_Properties,
    Track_Properties,
    TRAIN_UL_TRACKS_LIST,
    TRAIN_UL_NODE_LIST,
    TRAIN_OT_Add_Node,
    TRAIN_OT_Delete_Node
)

def on_update(self, context, flag_name):
    return
    if flag_name == "is_curve":
        return
    if getattr(context.scene, "updating_flags", False):
        return 
    flags = ['is_station', 'is_left_station', 'is_right_station', 'is_junction', 'is_tunnel', 'is_unk']

    setattr(context.scene, "updating_flags", True)

    for flag in flags:
        if flag != flag_name:
          setattr(context.scene, flag, False)

    setattr(context.scene, "updating_flags", False)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.app.handlers.depsgraph_update_post.append(update_custom_properties)
    bpy.types.Scene.tracks = bpy.props.CollectionProperty(type=Track_Properties, name="Tracks")
    bpy.types.Scene.track_index = bpy.props.IntProperty(name="Track Index", default=0)
    bpy.types.Scene.curve_point_index = bpy.props.IntProperty(name="Track Index", default=0)

    bpy.types.Scene.is_curve = bpy.props.BoolProperty(name="Is Curve", default=False ,update=lambda self, context: on_update(self, context, 'is_curve'))
    bpy.types.Scene.is_station = bpy.props.BoolProperty(name="Is Station", default=False,update=lambda self, context: on_update(self, context, 'is_station'))
    bpy.types.Scene.is_left_station = bpy.props.BoolProperty(name="Is Left Station", default=False,update=lambda self, context: on_update(self, context, 'is_left_station'))
    bpy.types.Scene.is_right_station = bpy.props.BoolProperty(name="Is Right Station", default=False,update=lambda self, context: on_update(self, context, 'is_right_station'))
    bpy.types.Scene.is_junction = bpy.props.BoolProperty(name="Is Junction", default=False,update=lambda self, context: on_update(self, context, 'is_junction'))
    bpy.types.Scene.is_tunnel = bpy.props.BoolProperty(name="Is Tunnel", default=False,update=lambda self, context: on_update(self, context, 'is_tunnel'))
    bpy.types.Scene.is_unk = bpy.props.BoolProperty(name="Is Unk", default=False,update=lambda self, context: on_update(self, context, 'is_unk'))
    bpy.types.Scene.updating_flags = bpy.props.BoolProperty(default=False)
    

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    bpy.app.handlers.depsgraph_update_post.remove(update_custom_properties)
    del bpy.types.Scene.tracks
    del bpy.types.Scene.track_index
    del bpy.types.Scene.curve_point_index

    del bpy.types.Scene.is_curve
    del bpy.types.Scene.is_station
    del bpy.types.Scene.is_left_station
    del bpy.types.Scene.is_left_station
    del bpy.types.Scene.is_junction
    del bpy.types.Scene.is_tunnel
    del bpy.types.Scene.is_unk

    del bpy.types.Scene.updating_flags


if __name__ == "__main__":
    register()
