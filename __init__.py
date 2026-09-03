bl_info = {
    "name": "TRAIN TOOLS",
    "author": "ktos93",
    "version": (0, 9),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > TRAIN",
    "description": "Import/export RDR2 train track .dat files as bezier "
                   "curves with per-point flags and station data",
    "category": "Object",
}


def register():
    from . import main
    main.register()


def unregister():
    from . import main
    main.unregister()
