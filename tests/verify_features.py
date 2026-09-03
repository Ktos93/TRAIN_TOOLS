"""Headless verification of the TRAIN_TOOLS QoL feature set.

Runs inside Blender 4.0 (background):
    "blender.exe" --background --python tests/verify_features.py -- --dat <src.dat>

Covers: batch import from a folder (with corrupt-file continuation),
export-all with empty-track skipping and file-name sanitizing, point
selection by kind, batch apply to all selected points, handle smoothing,
the node list name filter, viewport text markers (create/toggle/cleanup)
and track statistics.

Exit code 0 = all checks passed, 1 = failure.
"""
import os
import shutil
import sys
import traceback

FAILURES = []


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" :: {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    dat = None
    for i, a in enumerate(argv):
        if a == "--dat" and i + 1 < len(argv):
            dat = argv[i + 1]
    here = os.path.dirname(os.path.abspath(__file__))
    dat = os.path.abspath(dat or os.path.join(here, "..", "trains1.dat"))
    tmp = os.path.join(here, "tmp_features")
    src_dir = os.path.join(tmp, "src")
    out_dir = os.path.join(tmp, "out")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(src_dir)
    os.makedirs(out_dir)

    import bpy
    sys.path.insert(0, os.path.dirname(os.path.dirname(here)))
    import TRAIN_TOOLS
    sys.path.insert(0, here)
    import verify_roundtrip as vr
    from TRAIN_TOOLS import dat_format, storage, ui

    print(f"== verify_features: {os.path.basename(dat)} ==")
    try:
        TRAIN_TOOLS.register()
        check("register", True)
    except Exception as e:
        check("register", False, repr(e))
        traceback.print_exc()
        return 1

    scene = bpy.context.scene
    scene.tracks.clear()
    scene.track_index = 0

    (st, sc, stt), src_pts = vr.parse_dat(dat)
    expected_named = sum(1 for p in src_pts if p["flag"] in
                         dat_format.NAMED_KINDS)
    expected_kinds = {}
    for p in src_pts:
        expected_kinds[p["flag"]] = expected_kinds.get(p["flag"], 0) + 1

    # --- 1) Batch import from a folder -------------------------------
    # alpha.dat / beta.dat are copies of the source, bad.dat is corrupt
    # (unknown flag) and notes.txt must be ignored.
    for name in ("alpha.dat", "beta.dat"):
        shutil.copyfile(dat, os.path.join(src_dir, name))
    with open(os.path.join(src_dir, "bad.dat"), "w") as f:
        f.write("2 1 close\n")
        f.write("c 1.0 2.0 3.0 1.5 2.0 3.0 0.5 2.0 3.0 0.7 0\n")
        f.write("4.0 5.0 6.0 1.0 16 station_bad\n")
    with open(os.path.join(src_dir, "notes.txt"), "w") as f:
        f.write("not a track file\n")
    try:
        bpy.ops.train.import_folder(directory=src_dir)
        check("import_folder.op", True)
    except Exception as e:
        check("import_folder.op", False, repr(e))
        traceback.print_exc()
    check("import_folder.count", len(scene.tracks) == 2,
          f"got {len(scene.tracks)}")
    names = [t.name for t in scene.tracks]
    check("import_folder.names", names == ["alpha", "beta"], str(names))
    ok_curves = all(t.track_object is not None
                    and t.track_object.type == 'CURVE'
                    and len(t.track_object.data.splines[0].bezier_points) == st
                    for t in scene.tracks)
    check("import_folder.curves", ok_curves)

    # --- 2) Track statistics ------------------------------------------
    try:
        alpha = scene.tracks[0]
        length, kind_counts = storage.track_stats(alpha)
        check("stats.length", length > 0, f"got {length:.2f}")
        check("stats.kind_sum",
              sum(kind_counts.values()) == st,
              f"got {sum(kind_counts.values())}")
        check("stats.kinds_match", kind_counts == expected_kinds,
              f"got {kind_counts}")
    except Exception as e:
        check("stats.length", False, repr(e))
        traceback.print_exc()

    # --- 3) Export all --------------------------------------------------
    scene.tracks.add()
    scene.tracks[-1].name = "gamma"  # empty track, no curve
    try:
        bpy.ops.train.export_all(directory=out_dir)
        check("export_all.op", True)
    except Exception as e:
        check("export_all.op", False, repr(e))
        traceback.print_exc()
    check("export_all.files",
          os.path.exists(os.path.join(out_dir, "alpha.dat"))
          and os.path.exists(os.path.join(out_dir, "beta.dat"))
          and not os.path.exists(os.path.join(out_dir, "gamma.dat")))
    before = len(vr.FAILURES)
    vr.compare_dats(dat, os.path.join(out_dir, "alpha.dat"))
    check("export_all.alpha_roundtrip", len(vr.FAILURES) == before,
          f"new failures={vr.FAILURES[before:]}")
    # File-name sanitizing: an invalid track name must not crash the
    # export and must produce a usable file name.
    alpha.name = "bad/name:q"
    try:
        bpy.ops.train.export_all(directory=out_dir)
        check("export_all.sanitized",
              os.path.exists(os.path.join(out_dir, "bad_name_q.dat")))
    except Exception as e:
        check("export_all.sanitized", False, repr(e))
        traceback.print_exc()
    alpha.name = "alpha"
    scene.tracks.remove(2)  # drop the empty gamma track

    # --- 4) Select points by kind ---------------------------------------
    scene.track_index = 0
    try:
        scene.train_select_kind = "8"
        bpy.ops.train.select_points_kind()
        bpy.context.view_layer.update()
        points = alpha.track_object.data.splines[0].bezier_points
        records = alpha.track_object.data.train_points
        sel = [i for i, bp in enumerate(points) if bp.select_control_point]
        junction_idx = list(sel)
        check("select_kind.count", len(sel) == expected_kinds.get("8", 0),
              f"got {len(sel)}")
        check("select_kind.right_points",
              all(records[i].kind == "8" for i in sel))
    except Exception as e:
        check("select_kind.count", False, repr(e))
        traceback.print_exc()

    # --- 5) Batch apply to all selected points ---------------------------
    # The 20 selected junctions become tunnels; the name must NOT be
    # written because more than one point is selected.
    try:
        scene.point_kind = "4"
        scene.point_name = "SHOULD_NOT_APPLY"
        bpy.ops.train.apply_point_data()
        tunnels = [i for i, r in enumerate(records) if r.kind == "4"]
        check("apply_batch.junctions_converted",
              all(records[i].kind == "4" for i in junction_idx))
        check("apply_batch.count",
              len(tunnels) == expected_kinds.get("4", 0)
              + len(junction_idx),
              f"got {len(tunnels)}")
        check("apply_batch.name_cleared",
              all(records[i].name == "" for i in junction_idx))
        check("apply_batch.nodes_shrank",
              len(alpha.nodes) == expected_named - expected_kinds.get("8", 0),
              f"got {len(alpha.nodes)}")
        # Single-point apply: the name IS written.
        single = next(i for i, r in enumerate(records) if r.kind == "0")
        for bp in points:
            bp.select_control_point = False
        points[single].select_control_point = True
        bpy.context.view_layer.update()
        scene.point_kind = "1"
        scene.point_name = "BatchStation"
        bpy.ops.train.apply_point_data()
        rec = records[single]
        check("apply_single.record", rec.kind == "1"
              and rec.name == "BatchStation",
              f"got kind={rec.kind} name={rec.name!r}")
        check("apply_single.node_added",
              any(n.node_name == "BatchStation" for n in alpha.nodes))
    except Exception as e:
        check("apply_batch.count", False, repr(e))
        traceback.print_exc()

    # --- 6) Smooth handles ------------------------------------------------
    obj = alpha.track_object
    spline = obj.data.splines[0]
    before_types = set()
    before_handles = []
    for bp in spline.bezier_points:
        before_types.add(bp.handle_left_type)
        before_handles.append(tuple(bp.handle_left[:]))
    check("smooth.precondition", before_types == {"FREE"}, str(before_types))
    try:
        bpy.ops.train.smooth_handles()
        after_types = {bp.handle_left_type for bp in spline.bezier_points
                       } | {bp.handle_right_type
                            for bp in spline.bezier_points}
        check("smooth.types", after_types == {"AUTO"}, str(after_types))
        moved = sum(1 for a, b in zip(before_handles,
                                      [tuple(bp.handle_left[:])
                                       for bp in spline.bezier_points])
                    if any(abs(x - y) > 1e-6 for x, y in zip(a, b)))
        check("smooth.moves_handles", moved > 0, f"moved={moved}")
    except Exception as e:
        check("smooth.types", False, repr(e))
        traceback.print_exc()

    # --- 7) Node list filter -----------------------------------------------
    try:
        class MockUL:
            bitflag_filter_item = 1 << 31

        class MockLayout:
            def __init__(self):
                self.calls = []

            def row(self):
                return self

            def prop(self, data, propname, **kw):
                self.calls.append(("prop", propname))

            def label(self, **kw):
                self.calls.append(("label", kw.get("text")))

        def run_filter(needle):
            mock = MockUL()
            mock.filter_name = needle
            flags, neworder = ui.TRAIN_UL_NODE_LIST.filter_items(
                mock, bpy.context, alpha, "nodes")
            return flags, neworder

        nodes = alpha.nodes
        n0 = nodes[0]
        needle = (n0.node_name or n0.id)[:5].lower()
        flags, neworder = run_filter(needle)
        expected_match = [
            i for i, n in enumerate(nodes)
            if needle in (n.name + " " + n.node_name).lower()]
        got_match = [i for i, f in enumerate(flags)
                     if f & MockUL.bitflag_filter_item]
        check("filter.flags", got_match == expected_match
              and 0 < len(got_match) < len(nodes),
              f"got {got_match} want {expected_match}")
        check("filter.neworder", neworder == [])
        flags_all, _ = run_filter("")
        check("filter.empty_all_visible",
              all(f & MockUL.bitflag_filter_item for f in flags_all))
        flags_none, _ = run_filter("zzz_no_match_zzz")
        check("filter.no_match",
              not any(f & MockUL.bitflag_filter_item for f in flags_none))
        ml = MockLayout()
        mock = MockUL()
        mock.filter_name = "x"
        ui.TRAIN_UL_NODE_LIST.draw_filter(mock, bpy.context, ml)
        check("filter.draw", ("prop", "filter_name") in ml.calls,
              str(ml.calls))
    except Exception as e:
        check("filter.flags", False, repr(e))
        traceback.print_exc()

    # --- 8) Viewport text markers ------------------------------------------
    try:
        named = [i for i, r in enumerate(records)
                 if r.kind in dat_format.NAMED_KINDS]
        bpy.ops.train.toggle_markers()
        prefix = storage.marker_prefix(alpha)
        markers = [o for o in bpy.data.objects
                   if o.name.startswith(prefix)]
        check("markers.created", len(markers) == len(named),
              f"got {len(markers)} want {len(named)}")
        if markers:
            mk = markers[0]
            mk_idx = int(mk.name.rsplit("-", 1)[1])
            bp = points[mk_idx]
            rec = records[mk_idx]
            want_body = rec.name if rec.name else storage.point_node_id(bp.co)
            check("markers.font", mk.type == 'FONT', f"got {mk.type}")
            check("markers.parented", mk.parent == obj)
            check("markers.location",
                  all(abs(mk.location[i] - bp.co[i]) < 1e-5
                      for i in range(3)),
                  f"got {tuple(mk.location)} want {tuple(bp.co)}")
            check("markers.body", mk.data.body == want_body,
                  f"got {mk.data.body!r} want {want_body!r}")
        bpy.ops.train.toggle_markers()
        markers = [o for o in bpy.data.objects
                   if o.name.startswith(prefix)]
        check("markers.toggled_off", len(markers) == 0,
              f"got {len(markers)}")
        # Re-create, then delete the track: markers must go with it.
        bpy.ops.train.toggle_markers()
        markers = [o for o in bpy.data.objects
                   if o.name.startswith(prefix)]
        check("markers.recreated", len(markers) == len(named),
              f"got {len(markers)}")
        scene.track_index = 0
        bpy.ops.train.deletetrack()
        markers = [o for o in bpy.data.objects
                   if o.name.startswith(prefix)]
        check("markers.cleaned_on_delete", len(markers) == 0,
              f"got {len(markers)}")
        check("markers.track_gone", len(scene.tracks) == 1)
    except Exception as e:
        check("markers.created", False, repr(e))
        traceback.print_exc()

    try:
        TRAIN_TOOLS.unregister()
        check("unregister", True)
    except Exception as e:
        check("unregister", False, repr(e))
        traceback.print_exc()

    verdict = "ALL CHECKS PASSED" if not FAILURES else f"FAILED: {len(FAILURES)}"
    print(f"== {verdict} ==")
    for f in FAILURES:
        print(f"   - {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
