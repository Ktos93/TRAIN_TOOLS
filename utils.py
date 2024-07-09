import bpy
import numpy as np

######################################################
################ SOLLUMZ CODE <3 <3 ###################
######################################################

def draw_list_with_add_remove(layout: bpy.types.UILayout, add_operator: str, remove_operator: str, *temp_list_args, **temp_list_kwargs):
    """Draw a UIList with an add and remove button on the right column. Returns the left column."""
    row = layout.row()
    list_col = row.column()
    list_col.template_list(*temp_list_args, **temp_list_kwargs)
    side_col = row.column()
    col = side_col.column(align=True)
    col.operator(add_operator, text="", icon="ADD")
    col.operator(remove_operator, text="", icon="REMOVE")
    return list_col, side_col


def get_new_item_id(collection: bpy.types.bpy_prop_collection) -> int:
    ids = sorted({item.id for item in collection})
    if not ids:
        return 1
    for i, item_id in enumerate(ids):
        new_id = item_id + 1
        if new_id in ids:
            continue
        if i + 1 >= len(ids):
            return new_id
        next_item = ids[i + 1]
        if next_item > new_id:
            return new_id
    # Max id + 1
    return ids[-1] + 1
