import bpy


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
