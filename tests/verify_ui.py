"""UI smoke test: exercise the N-panel draw() and the UIList draw_item()
against a mock layout, catching runtime errors that registration cannot.

Run inside headless Blender (see the other verify_*.py for the exact
invocation) after import:

    blender --background --python tests/verify_ui.py -- --dat <file.dat>
"""
import os
import sys
import traceback

import bpy

FAILURES = []

# Valid icon identifiers of the running Blender, taken from the UILayout
# RNA so the mock raises on the same things the real layout would.
# (Populated in main() before any draw runs.)
VALID_ICONS = set()


def load_valid_icons():
    for fn_name in ("operator", "label"):
        fn = bpy.types.UILayout.bl_rna.functions[fn_name]
        for p in fn.parameters:
            if p.identifier == "icon":
                VALID_ICONS.update(i.identifier for i in p.enum_items)


def check_icon(icon, where):
    if icon and icon not in VALID_ICONS:
        raise ValueError("invalid icon %r in %s" % (icon, where))


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print("[%s] %s%s" % (status, name, (" :: " + detail) if detail else ""))
    if not ok:
        FAILURES.append(name)


class MockLayout:
    """Just enough of a UILayout for the panel/list draw code."""

    def __init__(self):
        self.labels = []
        self.operators = []
        self.props = []
        self.template_lists = []
        self.use_property_split = False
        self.use_property_decorate = False

    def label(self, text=None, icon=None, icon_value=0):
        check_icon(icon, "label %r" % text)
        self.labels.append(text if text is not None else icon)
        return self

    def operator(self, idname, text="", icon="", **kw):
        check_icon(icon, "operator %s" % idname)
        self.operators.append((idname, text))
        return self

    def prop(self, data, propname, **kw):
        self.props.append((getattr(data, propname, None), propname))
        return self

    def separator(self):
        return self

    def row(self, **kw):
        return self

    def column(self, **kw):
        return self

    def template_list(self, idname, *args, **kw):
        self.template_lists.append((idname, args, kw))
        return self

    def __getattr__(self, name):
        # Any other layout call is a no-op that returns self.
        return lambda *a, **k: self


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    addon_dir = os.path.dirname(here)
    sys.path.insert(0, os.path.dirname(addon_dir))
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    opts = dict(zip(argv[::2], argv[1::2]))
    dat = opts.get("--dat")

    load_valid_icons()
    check("valid_icons_loaded", len(VALID_ICONS) > 800,
          "count=%d" % len(VALID_ICONS))

    import TRAIN_TOOLS
    TRAIN_TOOLS.register()
    check("register", "tracks" in dir(bpy.types.Scene))

    from TRAIN_TOOLS import helpers, storage, ui

    # Import a track so the lists have content.
    tracks = bpy.context.scene.tracks
    tracks.add()
    track = tracks[-1]
    track.name = "Smoke"
    bpy.context.scene.track_index = len(tracks) - 1
    import TRAIN_TOOLS.dat_format as dat_format
    _, points = dat_format.parse_file(dat)
    curve_data = bpy.data.curves.new("Track-Smoke", type="CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for i, pt in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = pt.position
        bp.handle_left = pt.handle_a
        bp.handle_right = pt.handle_b
        bp.handle_left_type = "FREE"
        bp.handle_right_type = "FREE"
    storage.write_points(curve_data, points)
    obj = bpy.data.objects.new("Track-Smoke", curve_data)
    bpy.context.collection.objects.link(obj)
    track.track_object = obj
    storage.refresh_nodes(track)
    check("import", len(points) > 0, "points=%d" % len(points))

    class MockPanel:
        """Stands in for a bpy_struct panel instance (which cannot be
        constructed directly). draw() is called unbound against it."""

        def __init__(self, layout):
            self.layout = layout

    # --- Train Tools panel draw -------------------------------------
    mock = MockLayout()
    try:
        ui.TRAIN_PT_Tools.draw(MockPanel(mock), bpy.context)
        check("panel.tools_draw", True)
        check("panel.shows_nodes_list",
              any(t[0] == ui.TRAIN_UL_NODE_LIST.bl_idname
                  for t in mock.template_lists),
              "template_lists=%r" % mock.template_lists)
        check("panel.tools_folder_ops",
              ("train.import_folder", "Import Folder") in mock.operators and
              ("train.export_all", "Export All") in mock.operators,
              "ops=%r" % mock.operators)
        check("panel.tools_stats",
              any(l is not None and str(l).startswith("Length:")
                  for l in mock.labels),
              "labels=%r" % mock.labels)
    except Exception:
        check("panel.tools_draw", False, traceback.format_exc())

    # --- Point Info panel (no curve active) -------------------------
    mock = MockLayout()
    try:
        ui.TRAIN_PT_Point_Info.draw(MockPanel(mock), bpy.context)
        check("panel.point_info_empty", True)
    except Exception:
        check("panel.point_info_empty", False, traceback.format_exc())

    # --- Point Info panel with a selected curve point ---------------
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    pts = obj.data.splines[0].bezier_points
    for p in pts:
        p.select_control_point = False
    pts[400].select_control_point = True
    bpy.context.view_layer.update()  # let the handler sync the panel
    mock = MockLayout()
    try:
        ui.TRAIN_PT_Point_Info.draw(MockPanel(mock), bpy.context)
        check("panel.point_info_draw", True)
        check("panel.point_info_kind_prop",
              any(pn == "point_kind" for _, pn in mock.props),
              "props=%r" % [pn for _, pn in mock.props])
        check("panel.point_info_uid",
              any(l is not None and str(l).startswith("Point 400  (UID")
                  for l in mock.labels),
              "labels=%r" % [l for l in mock.labels if l])
        check("panel.point_info_apply",
              ("train.apply_point_data", "Apply to Selected") in mock.operators,
              "ops=%r" % mock.operators)
    except Exception:
        check("panel.point_info_draw", False, traceback.format_exc())

    # --- Point Tools panel (no track / with track) --------------------
    saved_index = bpy.context.scene.track_index
    bpy.context.scene.track_index = 10**6  # out of range: no track
    mock = MockLayout()
    try:
        ui.TRAIN_PT_Point_Tools.draw(MockPanel(mock), bpy.context)
        check("panel.point_tools_empty", True)
    except Exception:
        check("panel.point_tools_empty", False, traceback.format_exc())
    bpy.context.scene.track_index = saved_index
    mock = MockLayout()
    try:
        ui.TRAIN_PT_Point_Tools.draw(MockPanel(mock), bpy.context)
        check("panel.point_tools_draw", True)
        check("panel.point_tools_ops",
              ("train.select_points_kind", "Select Points") in mock.operators
              and ("train.smooth_handles", "Smooth Handles")
              in mock.operators
              and ("train.toggle_markers", "Toggle Markers") in mock.operators,
              "ops=%r" % mock.operators)
        check("panel.point_tools_kind",
              "train_select_kind" in {pn for _, pn in mock.props},
              "props=%r" % [pn for _, pn in mock.props])
    except Exception:
        check("panel.point_tools_draw", False, traceback.format_exc())

    # --- Node list filter box ----------------------------------------
    mock = MockLayout()
    try:
        class MockUL:
            filter_name = ""        # prop() just records, no access needed

        ui.TRAIN_UL_NODE_LIST.draw_filter(MockUL(), bpy.context, mock)
        check("uilist.nodes_filter_draw",
              any(pn == "filter_name" for _, pn in mock.props),
              "props=%r" % [pn for _, pn in mock.props])
    except Exception:
        check("uilist.nodes_filter_draw", False, traceback.format_exc())

    # --- UIList draw_item (both lists) ------------------------------
    # Signature must match the 4.0.1 calling convention exactly.
    ctx = bpy.context
    icon = 0
    active_data = ctx.scene
    active_property = "track_index"

    mock = MockLayout()
    try:
        ui.TRAIN_UL_TRACKS_LIST.draw_item(
            object(), ctx, mock, ctx.scene, track, icon,
            active_data, active_property, 0, 0)
        check("uilist.tracks_draw_item", "Smoke" in mock.labels,
              "labels=%r" % mock.labels)
    except Exception:
        check("uilist.tracks_draw_item", False, traceback.format_exc())

    node = track.nodes[0]
    mock = MockLayout()
    try:
        ui.TRAIN_UL_NODE_LIST.draw_item(
            object(), ctx, mock, track, node, icon,
            track, "node_index", 0, 0)
        check("uilist.nodes_draw_item", node.name in mock.labels,
              "labels=%r" % mock.labels)
    except Exception:
        check("uilist.nodes_draw_item", False, traceback.format_exc())

    # --- unregister -------------------------------------------------
    TRAIN_TOOLS.unregister()
    check("unregister", not hasattr(bpy.types.Scene, "tracks"))

    print("== %s ==" % ("ALL CHECKS PASSED" if not FAILURES
                        else "FAILURES: %s" % FAILURES))
    sys.exit(0 if not FAILURES else 1)


if __name__ == "__main__":
    main()
