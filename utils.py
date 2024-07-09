import bpy
import numpy as np


def rot(x, k):
    return ((x << k) & 0xFFFFFFFF) | (x >> (32 - k))

def mix(a, b, c):
    a = (a - c) & 0xFFFFFFFF; a ^= rot(c, 4); c = (c + b) & 0xFFFFFFFF
    b = (b - a) & 0xFFFFFFFF; b ^= rot(a, 6); a = (a + c) & 0xFFFFFFFF
    c = (c - b) & 0xFFFFFFFF; c ^= rot(b, 8); b = (b + a) & 0xFFFFFFFF
    a = (a - c) & 0xFFFFFFFF; a ^= rot(c, 16); c = (c + b) & 0xFFFFFFFF
    b = (b - a) & 0xFFFFFFFF; b ^= rot(a, 19); a = (a + c) & 0xFFFFFFFF
    c = (c - b) & 0xFFFFFFFF; c ^= rot(b, 4); b = (b + a) & 0xFFFFFFFF
    return a, b, c

def final(a, b, c):
    c ^= b; c = (c - rot(b, 14)) & 0xFFFFFFFF
    a ^= c; a = (a - rot(c, 11)) & 0xFFFFFFFF
    b ^= a; b = (b - rot(a, 25)) & 0xFFFFFFFF
    c ^= b; c = (c - rot(b, 16)) & 0xFFFFFFFF
    a ^= c; a = (a - rot(c, 4)) & 0xFFFFFFFF
    b ^= a; b = (b - rot(a, 14)) & 0xFFFFFFFF
    c ^= b; c = (c - rot(b, 24)) & 0xFFFFFFFF
    return a, b, c

def compute_probe_hash(k, initval = 0):
    length = len(k)
    a = b = c = (0xdeadbeef + (length << 2) + initval) & 0xFFFFFFFF

    while length > 3:
        a = (a + k[0]) & 0xFFFFFFFF
        b = (b + k[1]) & 0xFFFFFFFF
        c = (c + k[2]) & 0xFFFFFFFF
        a, b, c = mix(a, b, c)
        length -= 3
        k = k[3:]

    if length == 3:
        c = (c + k[2]) & 0xFFFFFFFF
    if length >= 2:
        b = (b + k[1]) & 0xFFFFFFFF
    if length >= 1:
        a = (a + k[0]) & 0xFFFFFFFF
        a, b, c = final(a, b, c)

    return str(c)






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
