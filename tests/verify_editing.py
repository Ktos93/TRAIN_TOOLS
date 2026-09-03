"""Headless editing-workflow verification for the TRAIN_TOOLS addon.

Runs inside Blender 4.0 (background):
    "blender.exe" --background --python tests/verify_editing.py -- --dat <src.dat>

Covers: applying point data through the operator path (node list sync),
moving a point and verifying export distance recompute, reverting point
data, uid-stable record resync on middle point add/remove, corrupt-file
rejection, and data persistence across .blend save/reload.

Exit code 0 = all checks passed, 1 = failure.
"""
import os
import sys
import traceback

FAILURES = []


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" :: {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def invoke_op(idname, **kw):
    import bpy
    return getattr(bpy.ops.train, idname)(**kw)


def parse_dat(path):
    with open(path, "r") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    header = lines[0].split()
    points = []
    for ln in lines[1:]:
        t = ln.split()
        if t[0] == "c":
            points.append({"is_curve": True,
                           "position": tuple(map(float, t[1:4])),
                           "dist": float(t[10]), "flag": t[11],
                           "name": t[12] if len(t) > 12 else ""})
        else:
            points.append({"is_curve": False,
                           "position": tuple(map(float, t[0:3])),
                           "dist": float(t[3]), "flag": t[4],
                           "name": t[5] if len(t) > 5 else ""})
    return (int(header[0]), int(header[1]), header[2]), points


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    dat = tmp = None
    for i, a in enumerate(argv):
        if a == "--dat" and i + 1 < len(argv):
            dat = argv[i + 1]
        elif a == "--tmp" and i + 1 < len(argv):
            tmp = argv[i + 1]
    here = os.path.dirname(os.path.abspath(__file__))
    dat = os.path.abspath(dat or os.path.join(here, "..", "trains1.dat"))
    tmp = os.path.abspath(tmp or os.path.join(here, "tmp_edit"))
    os.makedirs(tmp, exist_ok=True)
    out1 = os.path.join(tmp, "edited.dat")
    out2 = os.path.join(tmp, "resync.dat")
    bad = os.path.join(tmp, "bad.dat")
    blend = os.path.join(tmp, "persist.blend")

    import bpy
    sys.path.insert(0, os.path.dirname(os.path.dirname(here)))
    import TRAIN_TOOLS
    sys.path.insert(0, here)
    import verify_roundtrip as vr

    print(f"== verify_editing: {os.path.basename(dat)} ==")
    try:
        TRAIN_TOOLS.register()
        check("register", True)
    except Exception as e:
        check("register", False, repr(e))
        traceback.print_exc()
        return 1

    scene = bpy.context.scene
    scene.tracks.clear()
    track = scene.tracks.add()
    track.name = "editme"
    scene.track_index = 0

    try:
        invoke_op("import_dat", filepath=dat)
        check("import.op", True)
    except Exception as e:
        check("import.op", False, repr(e))
        traceback.print_exc()

    (st, sc, stt), src_pts = parse_dat(dat)
    obj = track.track_object
    spline = obj.data.splines[0]
    points = spline.bezier_points
    base_nodes = len(track.nodes)
    idx = 400

    # 1) Apply station data to a point through the operator path.
    #    Mirror the real UI order: curve active, then point selected,
    #    then the panel is edited. The depsgraph handler syncs the
    #    panel from the record on selection change.
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    orig_kind = obj.data.train_points[idx].kind
    for p in points:
        p.select_control_point = False
    points[idx].select_control_point = True
    bpy.context.view_layer.update()
    check("apply.panel_sync", scene.point_kind == orig_kind
          and scene.curve_point_index == idx,
          f"got kind={scene.point_kind} idx={scene.curve_point_index}")
    scene.point_kind = "1"
    scene.point_is_curve = True
    scene.point_name = "test_station"
    try:
        invoke_op("apply_point_data")
        rec = obj.data.train_points[idx]
        check("apply.record", rec.kind == "1" and rec.name == "test_station",
              f"got kind={rec.kind} name={rec.name!r}")
        check("apply.nodes_grew", len(track.nodes) == base_nodes + 1,
              f"got {len(track.nodes)}")
        check("apply.node_entry",
              any(n.node_name == "test_station" for n in track.nodes))
    except Exception as e:
        check("apply.record", False, repr(e))
        traceback.print_exc()

    # 2) Move the point, export, verify changed line and distances.
    co = points[idx].co
    points[idx].co = (co.x + 1.0, co.y + 2.0, co.z + 3.0)
    try:
        invoke_op("export_dat", filepath=out1)
        check("export1.op", os.path.exists(out1))
        (ot, oc, ott), out_pts = parse_dat(out1)
        o = out_pts[idx]
        s = src_pts[idx]
        ok_pos = all(abs(a - b) < 1.5e-4
                     for a, b in zip(o["position"],
                                     (s["position"][0] + 1.0,
                                      s["position"][1] + 2.0,
                                      s["position"][2] + 3.0)))
        check("export1.position", ok_pos, f"got {o['position']}")
        check("export1.flag_name", o["flag"] == "1"
              and o["name"] == "test_station",
              f"got flag={o['flag']} name={o['name']!r}")
        d_next = abs(o["dist"] - s["dist"])
        d_prev = abs(out_pts[idx - 1]["dist"] - src_pts[idx - 1]["dist"])
        check("export1.dist_next", d_next > 1e-3, f"dev={d_next:.4f}")
        check("export1.dist_prev", d_prev > 1e-3, f"dev={d_prev:.4f}")
        others = sum(
            1 for i in range(st)
            if i not in (idx - 1, idx) and
            (out_pts[i]["position"] != src_pts[i]["position"] or
             out_pts[i]["flag"] != src_pts[i]["flag"] or
             out_pts[i]["name"] != src_pts[i]["name"]))
        check("export1.others_unchanged", others == 0, f"changed={others}")
    except Exception as e:
        check("export1.op", False, repr(e))
        traceback.print_exc()

    # 3) Revert the point data; node list must shrink back.
    points[idx].co = co
    scene.point_kind = "0"
    scene.point_name = ""
    try:
        invoke_op("apply_point_data")
        rec = obj.data.train_points[idx]
        check("revert.record", rec.kind == "0" and rec.name == "",
              f"got kind={rec.kind} name={rec.name!r}")
        check("revert.nodes_back", len(track.nodes) == base_nodes,
              f"got {len(track.nodes)}")
    except Exception as e:
        check("revert.record", False, repr(e))
        traceback.print_exc()

    # 4) uid stability: deleting a point in the MIDDLE of the curve must
    #    keep every other point's uid (radius) and per-point data with the
    #    right point (real depsgraph handler), and inserting a point must
    #    hand the new point a fresh unique uid while the rest keep theirs.
    try:
        from TRAIN_TOOLS import storage
        radius_uids = lambda: [storage.float_to_uint(p.radius)
                               for p in points]
        uids0 = radius_uids()
        check("uid.assigned",
              len(set(uids0)) == st and all(u > 0 for u in uids0),
              "unique=%d of %d" % (len(set(uids0)), st))

        named_idx = track.nodes[0].node_index
        named_kind = obj.data.train_points[named_idx].kind
        named_name = obj.data.train_points[named_idx].name

        # Delete a plain (kind '0') point away from the named one.
        # The edit-mode removal operator cannot run in a background
        # session (no 3D viewport for its poll), so rebuild the spline
        # without the point instead: same curve data and the same
        # radii (uids) for every other point - exactly the state a real
        # deletion leaves behind, which is what the handler resyncs.
        mid = next(i for i in range(st)
                   if i != named_idx
                   and obj.data.train_points[i].kind == "0")
        kept = [(bp.co[:], bp.handle_left[:], bp.handle_right[:],
                 bp.handle_left_type, bp.handle_right_type, bp.radius)
                for i, bp in enumerate(points) if i != mid]
        new_spline = obj.data.splines.new('BEZIER')
        new_spline.bezier_points.add(len(kept) - 1)
        for i, (co, hl, hr, hlt, hrt, r) in enumerate(kept):
            bp = new_spline.bezier_points[i]
            bp.co = co
            bp.handle_left = hl
            bp.handle_right = hr
            bp.handle_left_type = hlt
            bp.handle_right_type = hrt
            bp.radius = r
        obj.data.splines.remove(spline)
        spline = new_spline
        points = spline.bezier_points
        bpy.context.view_layer.update()
        recs1 = obj.data.train_points
        check("resync.after_mid_delete", len(recs1) == st - 1,
              f"got {len(recs1)}")
        radii1 = radius_uids()
        expected = [u for i, u in enumerate(uids0) if i != mid]
        check("uid.mid_delete_radii", radii1 == expected,
              "len=%d/%d" % (len(radii1), len(expected)))
        named_idx1 = radii1.index(uids0[named_idx])
        check("uid.mid_delete_data",
              named_idx1 == named_idx - (1 if mid < named_idx else 0)
              and recs1[named_idx1].kind == named_kind
              and recs1[named_idx1].name == named_name,
              "idx=%d kind=%s name=%r"
              % (named_idx1, recs1[named_idx1].kind,
                 recs1[named_idx1].name))
        check("resync.nodes_unchanged", len(track.nodes) == base_nodes,
              f"got {len(track.nodes)}")

        # Insert a point at the end; it must get a fresh unique uid and
        # a default record, every other uid stays put.
        last = points[st - 2]
        points.add(1)
        points[st - 1].co = (last.co.x + 5.0, last.co.y, last.co.z)
        bpy.context.view_layer.update()
        recs2 = obj.data.train_points
        check("resync.after_add", len(recs2) == st,
              f"got {len(recs2)}")
        radii2 = radius_uids()
        check("uid.add_kept", radii2[:st - 1] == radii1,
              "len=%d" % len(radii2))
        fresh = radii2[st - 1]
        check("uid.add_fresh",
              fresh > 0 and fresh not in radii1
              and len(set(radii2)) == st,
              f"fresh={fresh}")
        check("uid.add_record",
              recs2[st - 1].uid == fresh and recs2[st - 1].kind == "0",
              f"uid={recs2[st - 1].uid} kind={recs2[st - 1].kind}")
        check("uid.add_data",
              recs2[named_idx1].kind == named_kind
              and recs2[named_idx1].name == named_name)
    except Exception as e:
        check("uid.stability", False, repr(e))
        traceback.print_exc()

    # 5) Corrupt file (unknown flag) must be rejected, track untouched.
    with open(bad, "w") as f:
        f.write("3 2 close\n")
        f.write("c 1.0 2.0 3.0 1.5 2.0 3.0 0.5 2.0 3.0 0.7 0\n")
        f.write("4.0 5.0 6.0 1.0 16 station_bad\n")
        f.write("c 7.0 8.0 9.0 7.5 8.0 9.0 6.5 8.0 9.0 0.9 8\n")
    obj_before = track.track_object
    try:
        invoke_op("import_dat", filepath=bad)
        check("corrupt.rejected", False, "import did not cancel")
    except RuntimeError as e:
        # bpy.ops re-raises a cancelled operator; 4.0 puts the reported
        # error message into the RuntimeError.
        check("corrupt.rejected", "unknown flag" in str(e)
              or "cancel" in str(e).lower(), str(e)[:80])
    except Exception as e:
        check("corrupt.rejected", False, repr(e))
    check("corrupt.track_untouched", track.track_object is obj_before)

    # 6) Re-import resets the curve; the export must match the source.
    try:
        invoke_op("import_dat", filepath=dat)
        invoke_op("export_dat", filepath=out2)
        before = len(vr.FAILURES)
        vr.compare_dats(dat, out2)
        check("final.roundtrip", len(vr.FAILURES) == before,
              f"new failures={vr.FAILURES[before:]}")
    except Exception as e:
        check("final.roundtrip", False, repr(e))
        traceback.print_exc()

    # 7) Persistence: save .blend, reload, records and nodes survive.
    try:
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        track2 = bpy.context.scene.tracks[0]
        obj2 = track2.track_object
        check("persist.object", obj2 is not None and obj2.type == 'CURVE')
        recs = obj2.data.train_points
        check("persist.records", len(recs) == st, f"got {len(recs)}")
        check("persist.uids",
              all(r.uid > 0 and r.uid == storage.float_to_uint(bp.radius)
                  for r, bp in zip(recs,
                                   obj2.data.splines[0].bezier_points)))
        check("persist.curve_count",
              sum(1 for r in recs if r.is_curve) == sc,
              f"got {sum(1 for r in recs if r.is_curve)}")
        check("persist.nodes", len(track2.nodes) == base_nodes,
              f"got {len(track2.nodes)}")
    except Exception as e:
        check("persist.object", False, repr(e))
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
