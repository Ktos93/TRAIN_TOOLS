"""Headless round-trip verification for the TRAIN_TOOLS addon.

Runs inside Blender 4.0 (background):
    "blender.exe" --background --python tests/verify_roundtrip.py -- --dat <src.dat> --out <out.dat>

Black-box test: registers the addon, adds a track, imports the .dat,
inspects the created curve object and its per-point records, exports
back to .dat, re-imports, unregisters the addon, and compares the
exported file against the source.

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


def parse_dat(path):
    """Return (header, points). Points: is_curve, position, handle_a,
    handle_b, dist, flag, name."""
    with open(path, "r") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    header = lines[0].split()
    total, curves, track_type = int(header[0]), int(header[1]), header[2]
    points = []
    for ln in lines[1:]:
        t = ln.split()
        if t[0] == "c":
            pts = {
                "is_curve": True,
                "position": tuple(map(float, t[1:4])),
                "handle_a": tuple(map(float, t[4:7])),
                "handle_b": tuple(map(float, t[7:10])),
                "dist": float(t[10]),
                "flag": t[11],
                "name": t[12] if len(t) > 12 else "",
            }
        else:
            pts = {
                "is_curve": False,
                "position": tuple(map(float, t[0:3])),
                "handle_a": None,
                "handle_b": None,
                "dist": float(t[3]),
                "flag": t[4],
                "name": t[5] if len(t) > 5 else "",
            }
        points.append(pts)
    return (total, curves, track_type), points


def compare_dats(src_path, out_path):
    (st, sc, stt), src_pts = parse_dat(src_path)
    (ot, oc, ott), out_pts = parse_dat(out_path)

    check("header.total", st == ot, f"src={st} out={ot}")
    check("header.curves", sc == oc, f"src={sc} out={oc}")
    check("header.type", stt == ott, f"src={stt} out={ott}")
    check("point_count", len(src_pts) == len(out_pts),
          f"src={len(src_pts)} out={len(out_pts)}")
    if len(src_pts) != len(out_pts):
        return

    COORD_EPS = 1.5e-4
    DIST_EPS = 5e-4
    bad = []
    max_coord_dev, max_dist_dev = 0.0, 0.0
    for i, (s, o) in enumerate(zip(src_pts, out_pts)):
        if s["is_curve"] != o["is_curve"]:
            bad.append((i, "kind", s["is_curve"], o["is_curve"]))
            continue
        for coord in ("position", "handle_a", "handle_b"):
            if s[coord] is None:
                continue
            dev = max(abs(a - b) for a, b in zip(s[coord], o[coord]))
            max_coord_dev = max(max_coord_dev, dev)
            if dev > COORD_EPS:
                bad.append((i, coord, s[coord], o[coord]))
        ddev = abs(s["dist"] - o["dist"])
        max_dist_dev = max(max_dist_dev, ddev)
        if ddev > DIST_EPS:
            bad.append((i, "dist", s["dist"], o["dist"]))
        if s["flag"] != o["flag"]:
            bad.append((i, "flag", s["flag"], o["flag"]))
        if s["name"] != o["name"]:
            bad.append((i, "name", s["name"], o["name"]))

    check("points.match", not bad,
          f"first={bad[:3]} count={len(bad)} "
          f"max_coord_dev={max_coord_dev:.6f} max_dist_dev={max_dist_dev:.6f}")


def invoke_op(idname, **kw):
    import bpy
    return getattr(bpy.ops.train, idname)(**kw)


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    dat = out = None
    for i, a in enumerate(argv):
        if a == "--dat" and i + 1 < len(argv):
            dat = argv[i + 1]
        elif a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
    if not dat or not out:
        here = os.path.dirname(os.path.abspath(__file__))
        dat = dat or os.path.join(here, "..", "trains1.dat")
        out = out or os.path.join(here, "last_export.dat")
    dat = os.path.abspath(dat)
    out = os.path.abspath(out)

    import bpy

    addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(addon_dir))
    import TRAIN_TOOLS

    print(f"== verify_roundtrip: {os.path.basename(dat)} ==")
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
    track.name = os.path.splitext(os.path.basename(dat))[0]
    scene.track_index = 0

    try:
        invoke_op("import_dat", filepath=dat)
        check("import.op", True)
    except Exception as e:
        check("import.op", False, repr(e))
        traceback.print_exc()

    (st, sc, stt), src_pts = parse_dat(dat)
    obj = track.track_object
    check("import.object", bool(obj and obj.type == "CURVE"),
          f"obj={getattr(obj, 'name', None)}")
    n_pts = 0
    curve_count_geo = 0
    record_count = 0
    curve_count_rec = 0
    radii = set()
    if obj:
        spline = obj.data.splines[0]
        n_pts = len(spline.bezier_points)
        radii = {round(p.radius, 4) for p in spline.bezier_points}
        curve_count_geo = sum(
            1 for p in spline.bezier_points
            if (abs(p.handle_left.x - p.co.x) > 1e-6
                or abs(p.handle_left.y - p.co.y) > 1e-6
                or abs(p.handle_left.z - p.co.z) > 1e-6
                or abs(p.handle_right.x - p.co.x) > 1e-6
                or abs(p.handle_right.y - p.co.y) > 1e-6
                or abs(p.handle_right.z - p.co.z) > 1e-6)
        )
        record_count = len(obj.data.train_points)
        curve_count_rec = sum(
            1 for r in obj.data.train_points if r.is_curve)
    check("import.point_count", n_pts == st, f"expected={st} got={n_pts}")
    check("import.curve_count_geo", curve_count_geo == sc,
          f"expected={sc} got={curve_count_geo}")
    check("import.record_count", record_count == st,
          f"expected={st} got={record_count}")
    check("import.record_curve_count", curve_count_rec == sc,
          f"expected={sc} got={curve_count_rec}")
    check("import.no_radius_hack", radii == {1.0},
          f"radius values in use: {sorted(radii)}")
    check("import.track_meta",
          track.total_points == st and track.curve_points == sc
          and track.type == stt,
          f"total={track.total_points} curves={track.curve_points} "
          f"type={track.type}")
    check("import.nodes_list", len(track.nodes) == sum(
        1 for p in src_pts if p["flag"] in ("1", "2", "6", "8")),
        f"got={len(track.nodes)}")

    try:
        if os.path.exists(out):
            os.remove(out)
        invoke_op("export_dat", filepath=out)
        check("export.op", os.path.exists(out))
    except Exception as e:
        check("export.op", False, repr(e))
        traceback.print_exc()

    if os.path.exists(out):
        compare_dats(dat, out)
    else:
        check("export.file", False, "missing")

    # Re-importing into the same track must replace the curve cleanly.
    try:
        invoke_op("import_dat", filepath=dat)
        track_objs = [o for o in bpy.data.objects
                      if o.name.startswith('Track-')]
        check("reimport.op", len(track_objs) == 1,
              f"track objects={[o.name for o in track_objs]}")
        check("reimport.records",
              len(track.track_object.data.train_points) == st)
    except Exception as e:
        check("reimport.op", False, repr(e))
        traceback.print_exc()

    try:
        TRAIN_TOOLS.unregister()
        check("unregister",
              not hasattr(bpy.types.Scene, "tracks")
              and not hasattr(bpy.types.Scene, "point_kind")
              and not hasattr(bpy.types.Curve, "train_points"))
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
