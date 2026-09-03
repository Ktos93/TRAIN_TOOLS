"""Pure parsing/formatting for RDR2 train track .dat files.

No bpy imports in this module so it can be tested without Blender.

File format: one line per track point, preceded by a header line.

    <total_points> <curve_points> <track_type>
    c <x> <y> <z> <hax> <hay> <haz> <hbx> <hby> <hbz> <dist> <flag> [<name>]
    <x> <y> <z> <dist> <flag> [<name>]

Lines starting with 'c' are bezier points with explicit handles; plain
lines are points whose handles coincide with the position. <flag> is a
single enum value: 0 none, 1 station, 2 left station, 4 tunnel,
6 right station, 8 junction, 32 unknown. <name> is only present for
named points (stations/junctions). <dist> is the distance to the next
point (the last point wraps to the first) and is recomputed on export.
"""


class DatError(ValueError):
    """Malformed .dat content. Carries a 1-based line number when known."""

    def __init__(self, message, line=None):
        self.line = line
        super().__init__(f"line {line}: {message}" if line else message)


# Flag values, kept identical to the values in the .dat file so the
# mapping between the file and the Blender data is 1:1.
KIND_NONE = "0"
KIND_STATION = "1"
KIND_LEFT_STATION = "2"
KIND_TUNNEL = "4"
KIND_RIGHT_STATION = "6"
KIND_JUNCTION = "8"
KIND_UNKNOWN = "32"

# (value, label, tooltip) -- used for Blender enum properties.
KIND_ITEMS = (
    (KIND_NONE, "None", "No special data"),
    (KIND_STATION, "Station", "Named station (flag 1)"),
    (KIND_LEFT_STATION, "Left Station", "Left-side station (flag 2)"),
    (KIND_TUNNEL, "Tunnel", "Tunnel marker (flag 4)"),
    (KIND_RIGHT_STATION, "Right Station", "Right-side station (flag 6)"),
    (KIND_JUNCTION, "Junction", "Track junction (flag 8)"),
    (KIND_UNKNOWN, "Unknown", "Unrecognized flag (32)"),
)
KIND_VALUES = tuple(v for v, _, _ in KIND_ITEMS)
KIND_LABELS = dict((v, label) for v, label, _ in KIND_ITEMS)
# Kinds that carry a name in the .dat file and appear in the node list.
NAMED_KINDS = (KIND_STATION, KIND_LEFT_STATION, KIND_RIGHT_STATION,
               KIND_JUNCTION)

# Object-name prefix for the optional viewport text markers that are
# created at a track's named points (see storage.marker_prefix).
MARKER_PREFIX = "TrainMarker-"


class TrainPointData(object):
    """A single parsed track point."""

    __slots__ = ("is_curve", "position", "handle_a", "handle_b",
                 "dist", "kind", "name")

    def __init__(self, is_curve, position, handle_a, handle_b,
                 dist, kind, name):
        self.is_curve = is_curve
        self.position = position  # (x, y, z)
        self.handle_a = handle_a  # (x, y, z)
        self.handle_b = handle_b  # (x, y, z)
        self.dist = dist          # distance to next point (from file)
        self.kind = kind          # one of KIND_VALUES
        self.name = name          # station/junction name or ""

    def __repr__(self):
        return (f"TrainPointData(kind={self.kind}, pos={self.position}, "
                f"curve={self.is_curve}, name={self.name!r})")


def parse_header(line, line_no=1):
    """Parse the header line, return (total, curve_count, track_type)."""
    tokens = line.split()
    if len(tokens) < 3:
        raise DatError("header must be '<total> <curves> <type>'", line_no)
    try:
        total = int(tokens[0])
        curve_count = int(tokens[1])
    except ValueError:
        raise DatError("header point counts must be integers", line_no)
    return total, curve_count, tokens[2]


def parse_point_line(line, line_no=None):
    """Parse one point line into a TrainPointData."""
    tokens = line.split()
    if not tokens:
        raise DatError("empty point line", line_no)
    try:
        if tokens[0] == "c":
            if len(tokens) < 12:
                raise DatError("curve point needs at least 12 tokens",
                                line_no)
            is_curve = True
            position = _vec3(tokens, 1)
            handle_a = _vec3(tokens, 4)
            handle_b = _vec3(tokens, 7)
            dist = float(tokens[10])
            kind = tokens[11]
            name = tokens[12] if len(tokens) > 12 else ""
        else:
            if len(tokens) < 5:
                raise DatError("point needs at least 5 tokens", line_no)
            is_curve = False
            position = _vec3(tokens, 0)
            handle_a = position
            handle_b = position
            dist = float(tokens[3])
            kind = tokens[4]
            name = tokens[5] if len(tokens) > 5 else ""
    except DatError:
        raise
    except (ValueError, IndexError) as exc:
        raise DatError(f"malformed numbers: {exc}", line_no)
    if kind not in KIND_VALUES:
        raise DatError(f"unknown flag {kind!r} (expected one of "
                       f"{', '.join(KIND_VALUES)})", line_no)
    return TrainPointData(is_curve, position, handle_a, handle_b,
                          dist, kind, name)


def parse_file(path):
    """Parse a whole .dat file. Return (header, [TrainPointData])."""
    with open(path, "r") as fh:
        lines = fh.read().splitlines()
    if not lines or not lines[0].strip():
        raise DatError("file is empty", 1)
    header = parse_header(lines[0].strip(), 1)
    points = []
    for line_no, raw in enumerate(lines[1:], start=2):
        line = raw.strip()
        if not line:
            continue
        points.append(parse_point_line(line, line_no))
    return header, points


def format_point(is_curve, position, handle_a, handle_b, dist, kind, name):
    """Format one point line (no newline)."""
    name_part = f" {name}" if (kind in NAMED_KINDS and name) else ""
    if is_curve:
        return (f"c {_v3(position)} {_v3(handle_a)} {_v3(handle_b)} "
                f"{dist:.4f} {kind}{name_part}")
    return f"{_v3(position)} {dist:.4f} {kind}{name_part}"


def _v3(vec):
    return f"{vec[0]:.4f} {vec[1]:.4f} {vec[2]:.4f}"


def _vec3(tokens, offset):
    return (float(tokens[offset]), float(tokens[offset + 1]),
            float(tokens[offset + 2]))


def distance(p1, p2):
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    dz = p1[2] - p2[2]
    return (dx * dx + dy * dy + dz * dz) ** 0.5
