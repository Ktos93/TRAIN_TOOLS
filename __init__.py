bl_info = {
    "name": "TRAIN TOOLS",
    "author": "ktos93",
    "version": (0, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Tools",
    "description": "",
    "warning": "",
    "wiki_url": "",
    "category": "Object",
}

from . import main

def register():
    main.register()


def unregister():
    main.unregister()


if __name__ == "__main__":
    register()


   