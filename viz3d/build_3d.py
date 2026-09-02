# -*- coding: utf-8 -*-
"""Build the PHYTO-RECLAIM reference unit as a 3D model, procedurally, in Blender.

    "C:\\Program Files\\Blender Foundation\\Blender 4.5\\blender.exe" ^
        --background --python build_3d.py

WHY IT IS GENERATED RATHER THAN MODELLED BY HAND
Every dimension below is read from the paper, so the model is dimensionally
faithful instead of decorative. Change a number in DIMENSIONS and the geometry
follows. That is what separates this from an artist's impression: it answers
"does this actually fit on 725 m2", which is the first question an operator asks.

  Plot            725 m2 total (Table 1)
  Wetland         575 m2 -> Tier 1 345 m2, Tier 2 230 m2 (Table 1)
  Process + access 150 m2 (Table 1)
  Media depth     0.60 m (Section 2.5)
  EC reactor      0.70 m3 working volume (Table 3)
  Adsorption      2 x 0.52 m3 (Table 3)
  Tubular PBR     10 m3 working volume (Table 3)
  Solar dryer     ~38 m2 collector area (Table 2)

Outputs, into ./renders:
  aerial.png   three-quarter view of the whole plot
  plan.png     orthographic top-down plan
  ground.png   eye-level view from the access road
  anchors.json screen coordinates of each label, for annotate_3d.py
"""
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(bpy.data.filepath or __file__))
if "--" in sys.argv:
    HERE = os.path.dirname(os.path.abspath(sys.argv[sys.argv.index("--") + 1]))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders")
os.makedirs(OUT, exist_ok=True)

# ============================================================ dimensions
DEPTH = 19.3                       # m, plot depth (from the deck: 37.5 x 19.3)
A_PROCESS, A_TIER1, A_TIER2 = 150.0, 345.0, 230.0      # m2, from Table 1
W_PROCESS = A_PROCESS / DEPTH      # 7.772 m
W_TIER1 = A_TIER1 / DEPTH          # 17.876 m
W_TIER2 = A_TIER2 / DEPTH          # 11.917 m
LENGTH = W_PROCESS + W_TIER1 + W_TIER2                  # 37.565 m -> 725.0 m2

MEDIA_DEPTH = 0.60                 # m, Section 2.5
ROAD_W = 4.0                       # m, access road
BERM = 0.35                        # m, basin wall height above media

X_PROC = 0.0
X_T1 = W_PROCESS
X_T2 = W_PROCESS + W_TIER1

# ============================================================ palette
HEX = dict(
    navy="#17365D", teal="#1C8C87", water="#1D6FA5", gas="#A8642B",
    bio="#3B7F4A", steel="#B9C2C6", dark="#4A565B", concrete="#C9CDCB",
    media="#7A6A55", leaf_a="#4E8C3F", leaf_b="#6FA84B", reed="#8FA85B",
    ground="#9AA88C", panel="#2A3D5C", red="#B3352F", white="#EDEFEF",
)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgba(name, alpha=1.0):
    h = HEX[name].lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha)


MATS = {}


def mat(name, rough=0.6, metal=0.0, alpha=1.0, emit=0.0):
    key = (name, rough, metal, alpha, emit)
    if key in MATS:
        return MATS[key]
    m = bpy.data.materials.new(f"m_{name}_{len(MATS)}")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba(name)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
    if emit:
        bsdf.inputs["Emission Color"].default_value = rgba(name)
        bsdf.inputs["Emission Strength"].default_value = emit
    MATS[key] = m
    return m


# ============================================================ primitives
def box(name, size, loc, material, rot=(0, 0, 0)):
    # primitive_cube_add(size=1) is already a 1 m cube, so the scale factor is
    # the edge length itself. Halving it here would make every box half-size.
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = (size[0], size[1], size[2])
    o.data.materials.append(material)
    return o


def cyl(name, radius, height, loc, material, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height,
                                        location=loc, rotation=rot, vertices=verts)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


def pipe(name, p0, p1, radius, material):
    """A straight pipe between two points."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    o = cyl(name, radius, d.length, (a + b) / 2, material, verts=12)
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = d.to_track_quat("Z", "Y")
    return o


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                  bpy.data.cameras, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


# ============================================================ vegetation
def make_clump(kind):
    """One plant clump, built once and then linked-duplicated across the basin."""
    if kind == "reed":
        n, h, r, colour = 7, 2.1, 0.030, "reed"
    elif kind == "typha":
        n, h, r, colour = 6, 1.9, 0.035, "leaf_a"
    else:                       # vetiver
        n, h, r, colour = 9, 1.3, 0.022, "leaf_b"

    bm = bmesh.new()
    for i in range(n):
        ang = i * (2 * math.pi / n) + (i % 3) * 0.4
        lean = 0.16 + 0.10 * ((i % 4) / 3)
        hh = h * (0.75 + 0.3 * ((i * 7) % 5) / 4)
        blade = bmesh.new()
        bmesh.ops.create_cone(blade, cap_ends=True, segments=4,
                              radius1=r, radius2=r * 0.12, depth=hh)
        bmesh.ops.translate(blade, verts=blade.verts, vec=(0, 0, hh / 2))
        bmesh.ops.rotate(
            blade, verts=blade.verts, cent=(0, 0, 0),
            matrix=(Vector((0, 0, 1)).rotation_difference(
                Vector((math.cos(ang) * lean, math.sin(ang) * lean, 1)).normalized()
            ).to_matrix()))
        bmesh.ops.translate(blade, verts=blade.verts,
                            vec=(math.cos(ang) * 0.05, math.sin(ang) * 0.05, 0))
        tmp = bpy.data.meshes.new("tmp")
        blade.to_mesh(tmp); blade.free()
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)

    me = bpy.data.meshes.new(f"clump_{kind}")
    bm.to_mesh(me); bm.free()
    me.materials.append(mat(colour, rough=0.85))
    obj = bpy.data.objects.new(f"clump_{kind}", me)
    bpy.context.collection.objects.link(obj)
    return obj


def plant_basin(source, x0, x1, y0, y1, z, spacing, jitter=0.22):
    """Scatter linked duplicates of one clump across a rectangle."""
    made = []
    nx = max(1, int((x1 - x0) / spacing))
    ny = max(1, int((y1 - y0) / spacing))
    for i in range(nx):
        for j in range(ny):
            h = (i * 928371 + j * 1237) % 1000 / 1000.0
            k = (i * 15731 + j * 789221) % 1000 / 1000.0
            x = x0 + (i + 0.5) * (x1 - x0) / nx + (h - 0.5) * jitter * 2
            y = y0 + (j + 0.5) * (y1 - y0) / ny + (k - 0.5) * jitter * 2
            d = source.copy()                 # linked duplicate: shares mesh data
            d.location = (x, y, z)
            d.rotation_euler = (0, 0, h * 6.28)
            d.scale = (1.15 + 0.45 * k,) * 3
            bpy.context.collection.objects.link(d)
            made.append(d)
    source.hide_render = True
    source.hide_viewport = True
    return made


# ============================================================ the plant
def build():
    clear_scene()
    anchors = {}

    # ---------- ground and plot ----------
    box("terrain", (LENGTH + 34, DEPTH + 26, 0.4),
        (LENGTH / 2, DEPTH / 2, -0.2), mat("ground", rough=0.95))
    box("plot_pad", (LENGTH, DEPTH, 0.12),
        (LENGTH / 2, DEPTH / 2, 0.06), mat("concrete", rough=0.9))

    # ---------- access road along the north edge of the process strip ----------
    box("access_road", (LENGTH, ROAD_W, 0.06),
        (LENGTH / 2, DEPTH - ROAD_W / 2, 0.15), mat("dark", rough=0.95))
    anchors["Access road, 4 m wide"] = (LENGTH * 0.62, DEPTH - ROAD_W / 2, 0.2)

    # ---------- wetland basins ----------
    def basin(name, x0, w, kind, spacing, label):
        cx = x0 + w / 2
        yb0, yb1 = 0.35, DEPTH - ROAD_W - 0.35
        d = yb1 - yb0
        # retaining walls
        for nm, sz, lc in (
            (f"{name}_wall_s", (w, 0.30, MEDIA_DEPTH + BERM), (cx, yb0, (MEDIA_DEPTH + BERM) / 2)),
            (f"{name}_wall_n", (w, 0.30, MEDIA_DEPTH + BERM), (cx, yb1, (MEDIA_DEPTH + BERM) / 2)),
            (f"{name}_wall_w", (0.30, d, MEDIA_DEPTH + BERM), (x0, (yb0 + yb1) / 2, (MEDIA_DEPTH + BERM) / 2)),
            (f"{name}_wall_e", (0.30, d, MEDIA_DEPTH + BERM), (x0 + w, (yb0 + yb1) / 2, (MEDIA_DEPTH + BERM) / 2)),
        ):
            box(nm, sz, lc, mat("concrete", rough=0.9))
        # Media bed, 0.60 m deep. This is a SUBSURFACE-FLOW wetland: the water
        # table sits inside the gravel, so the visible surface is media, not
        # open water. Showing open water would depict a free-water-surface
        # wetland - a different design, with a different footprint and its own
        # odour and mosquito issues. The paper specifies subsurface flow.
        box(f"{name}_media", (w - 0.3, d - 0.3, MEDIA_DEPTH),
            (cx, (yb0 + yb1) / 2, MEDIA_DEPTH / 2), mat("media", rough=1.0))
        # saturated zone, buried inside the media and only visible in section
        box(f"{name}_saturated", (w - 0.5, d - 0.5, MEDIA_DEPTH * 0.62),
            (cx, (yb0 + yb1) / 2, MEDIA_DEPTH * 0.31),
            mat("water", rough=0.2, alpha=0.55))
        clump = make_clump(kind)
        plant_basin(clump, x0 + 0.45, x0 + w - 0.45, yb0 + 0.45, yb1 - 0.45,
                    MEDIA_DEPTH, spacing)
        anchors[label] = (cx, (yb0 + yb1) / 2, MEDIA_DEPTH + 1.7)

    basin("tier1", X_T1, W_TIER1, "typha", 0.62,
          "Tier 1 - vertical flow, 345 m2\nvetiver + typha")
    basin("tier2", X_T2, W_TIER2, "reed", 0.62,
          "Tier 2 - horizontal flow, 230 m2\nphragmites")

    # ---------- process area, 150 m2 ----------
    # Laid out as a single service aisle running north, so nothing blocks
    # access to anything else. Usable footprint is about 7.1 x 14.6 m.
    px = X_PROC
    pad_y0, pad_y1 = 0.35, DEPTH - ROAD_W - 0.35
    box("process_pad", (W_PROCESS - 0.4, pad_y1 - pad_y0, 0.14),
        (px + W_PROCESS / 2, (pad_y0 + pad_y1) / 2, 0.14), mat("concrete", rough=0.85))

    steel = mat("steel", rough=0.35, metal=0.7)
    dark = mat("dark", rough=0.5)
    WEST, EAST = px + 1.6, px + 5.6          # two equipment rows

    # EC reactor: 0.70 m3 working volume -> 0.80 m dia x 1.40 m
    cyl("ec_reactor", 0.40, 1.40, (WEST, 1.9, 0.14 + 0.70), steel)
    box("ec_skid", (1.5, 1.5, 0.25), (WEST, 1.9, 0.20), dark)
    anchors["Electrocoagulation reactor\n0.70 m3, Al-Fe electrodes"] = (WEST, 1.9, 2.4)

    # Reclaimed water tank, opposite the reactor
    cyl("water_tank", 1.4, 3.0, (EAST, 2.2, 0.14 + 1.5), mat("teal", rough=0.4))
    anchors["Reclaimed water tank\n38 m3/day to reuse"] = (EAST, 2.2, 3.9)

    # Adsorption: 2 x 0.52 m3 -> 0.70 m dia x 1.35 m
    for i, y in enumerate((4.3, 5.3)):
        cyl(f"adsorb_{i}", 0.35, 1.35, (WEST, y, 0.14 + 0.675), steel)
    anchors["Adsorption polishing\n2 x 0.52 m3 bentonite-zeolite"] = (WEST, 4.8, 2.3)

    # Flue-gas conditioning: heat exchanger then scrubber
    box("heat_exch", (1.3, 0.9, 1.0), (EAST, 4.6, 0.14 + 0.5), steel)
    cyl("scrubber", 0.50, 2.6, (EAST, 6.0, 0.14 + 1.3), mat("gas", rough=0.5))
    anchors["Flue-gas conditioning\n120-180 C cooled to ~30 C"] = (EAST, 5.4, 3.2)

    # Tubular PBR, 10 m3 working volume, racked vertically.
    # Tubes run north-south so the rack reads as a reactor, not loose pipework.
    rack_x, rack_y = px + 3.4, 8.6
    rack_w, rack_l, rack_h = 3.0, 4.2, 2.4
    for sx in (-rack_w / 2, rack_w / 2):                 # end frames
        box("pbr_frame", (0.10, rack_l, rack_h),
            (rack_x + sx, rack_y, 0.14 + rack_h / 2), dark)
        for sy in (-rack_l / 2, rack_l / 2):
            box("pbr_post", (0.14, 0.14, rack_h),
                (rack_x + sx, rack_y + sy, 0.14 + rack_h / 2), dark)
    tube_mat = mat("bio", rough=0.25, alpha=0.92)
    for layer in range(7):
        z = 0.34 + layer * 0.30
        for t in range(6):
            xx = rack_x - rack_w / 2 + 0.32 + t * (rack_w - 0.64) / 5
            cyl(f"pbr_tube_{layer}_{t}", 0.058, rack_l - 0.1,
                (xx, rack_y, 0.14 + z), tube_mat,
                rot=(math.pi / 2, 0, 0), verts=10)
    anchors["Tubular photobioreactor\n10 m3 working volume"] = (rack_x, rack_y, 0.14 + rack_h + 0.8)

    # Decanter centrifuge and formulation skid
    box("centrifuge", (1.4, 0.9, 0.9), (WEST, 11.3, 0.14 + 0.45), steel)
    anchors["Decanter centrifuge\n0.5 m3/h"] = (WEST, 11.3, 1.5)
    box("formulation", (1.7, 1.9, 1.7), (EAST - 0.3, 11.4, 0.14 + 0.85), mat("white", rough=0.6))
    anchors["Formulation + QC skid\n8,870 L/yr QC-released"] = (EAST - 0.3, 11.4, 2.5)

    # Certified control cabinet - the Module III hardware
    box("control_plinth", (1.3, 1.9, 0.2), (WEST - 0.2, 13.9, 0.20), dark)
    box("control_cabinet", (1.0, 1.6, 2.1), (WEST - 0.2, 13.9, 0.30 + 1.05), mat("navy", rough=0.45))
    anchors["Certified control cabinet\nhazardous-area rated, ESD, SCADA"] = (WEST - 0.2, 13.9, 3.0)

    # Storage and utilities
    box("store", (2.6, 2.2, 2.3), (EAST, 13.8, 0.14 + 1.15), mat("white", rough=0.7))
    box("store_roof", (2.9, 2.5, 0.12), (EAST, 13.8, 0.14 + 2.36), dark)

    # Hybrid solar dryer, ~38 m2 collector, on a canopy frame over the northern
    # third only - it must not shade the photobioreactor below it.
    dry_w, dry_l = 6.5, 5.9            # 38.4 m2
    dry_x, dry_y, dry_z = px + 3.6, 12.6, 3.35
    box("dryer_panel", (dry_w, dry_l, 0.10), (dry_x, dry_y, dry_z),
        mat("panel", rough=0.2, metal=0.3), rot=(math.radians(-12), 0, 0))
    for sx in (-dry_w / 2 + 0.25, dry_w / 2 - 0.25):
        for sy, hh in ((-dry_l / 2, dry_z - 0.5), (dry_l / 2, dry_z + 0.5)):
            box("dryer_leg", (0.12, 0.12, hh),
                (dry_x + sx, dry_y + sy, hh / 2), dark)
    anchors["Hybrid solar dryer\n~38 m2 collector, ~92% of dryer duty"] = (dry_x, dry_y, dry_z + 1.1)

    # ---------- piping, colour-coded by stream ----------
    w_mat = mat("water", rough=0.35, metal=0.2)
    g_mat = mat("gas", rough=0.4, metal=0.2)
    b_mat = mat("bio", rough=0.4, metal=0.2)

    pipe("inlet", (-3.4, 1.9, 0.9), (px + 1.1, 1.9, 0.9), 0.09, w_mat)
    pipe("ec_to_ads", (WEST, 2.7, 1.1), (WEST, 3.9, 1.1), 0.07, w_mat)
    pipe("ads_to_wetland", (WEST + 0.4, 4.8, 1.1), (X_T1 + 0.5, 4.8, 1.1), 0.07, w_mat)
    pipe("tier1_to_tier2", (X_T2 - 0.5, 9.0, 0.85), (X_T2 + 0.6, 9.0, 0.85), 0.07, w_mat)
    pipe("wetland_to_tank", (X_T1 + 0.8, 2.2, 0.85), (EAST + 1.2, 2.2, 0.85), 0.07, w_mat)
    pipe("side_stream", (EAST, 3.8, 1.7), (rack_x + 1.5, 7.2, 1.7), 0.05, w_mat)
    pipe("gas_in", (EAST, 19.8, 1.5), (EAST, 5.2, 1.5), 0.06, g_mat)
    pipe("gas_to_pbr", (EAST - 0.5, 6.3, 1.3), (rack_x + 1.5, 8.0, 1.3), 0.05, g_mat)
    pipe("pbr_to_centrifuge", (rack_x - 1.5, 10.4, 1.0), (WEST, 10.9, 1.0), 0.05, b_mat)
    pipe("centrifuge_to_dryer", (WEST, 11.8, 1.2), (WEST + 0.6, 12.4, 1.2), 0.05, b_mat)
    pipe("dryer_to_formulation", (dry_x, 12.0, 2.3), (EAST - 0.3, 11.9, 2.3), 0.05, b_mat)

    return anchors


# ============================================================ camera, light, render
def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def setup_world():
    w = bpy.data.worlds.new("w")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.62, 0.72, 0.82, 1.0)
    bg.inputs[1].default_value = 1.15

    bpy.ops.object.light_add(type="SUN", location=(-16, -12, 26))
    sun = bpy.context.object
    sun.data.energy = 4.2
    sun.data.angle = math.radians(2.5)
    look_at(sun, (LENGTH * 0.45, DEPTH * 0.45, 0))

    bpy.ops.object.light_add(type="AREA", location=(LENGTH + 16, DEPTH + 14, 18))
    fill = bpy.context.object
    fill.data.energy = 900
    fill.data.size = 24
    look_at(fill, (LENGTH / 2, DEPTH / 2, 1))


def render(name, loc, target, ortho=None, res=(2400, 1350), samples=48,
           do_render=True):
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = loc
    look_at(cam, target)
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    else:
        cam_data.lens = 40
    bpy.context.scene.camera = cam

    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.eevee.taa_render_samples = samples
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = os.path.join(OUT, name + ".png")
    if do_render:
        bpy.ops.render.render(write_still=True)
        print(f"  rendered {name}.png")
    else:
        print(f"  skipped {name}.png")
    return cam


def project(cam, anchors, res):
    """Screen-space position of every label anchor, for annotate_3d.py."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    out = {}
    for label, p in anchors.items():
        co = world_to_camera_view(sc, cam, Vector(p))
        out[label] = {"x": round(co.x * res[0], 1),
                      "y": round((1 - co.y) * res[1], 1),
                      "visible": bool(0 <= co.x <= 1 and 0 <= co.y <= 1 and co.z > 0)}
    return out


def organise_collections():
    """Sort objects into named collections so the outliner is navigable.

    Matters only when the .blend is opened in the GUI - with ~1,000 objects a
    flat outliner is unusable.
    """
    groups = {
        "Site": ("terrain", "plot_pad", "access_road", "process_pad"),
        "Wetland Tier 1": ("tier1",),
        "Wetland Tier 2": ("tier2",),
        "Process equipment": ("ec_", "adsorb", "pbr_", "centrifuge", "dryer",
                              "water_tank", "scrubber", "heat_exch",
                              "formulation", "control_", "store"),
        "Piping": ("inlet", "ec_to", "ads_to", "tier1_to", "wetland_to",
                   "side_stream", "gas_", "pbr_to", "centrifuge_to",
                   "dryer_to"),
        "Planting": ("clump_",),
        "Cameras and lights": (),
    }
    made = {}
    for name in groups:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        made[name] = c

    for obj in list(bpy.data.objects):
        target = None
        if obj.type in {"CAMERA", "LIGHT"}:
            target = "Cameras and lights"
        else:
            for gname, prefixes in groups.items():
                if any(obj.name.startswith(p) for p in prefixes):
                    target = gname
                    break
        if target is None:
            target = "Process equipment"
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        made[target].objects.link(obj)
    # drop Blender's default empty collection so the outliner opens tidy
    for c in list(bpy.context.scene.collection.children):
        if c.name not in made and not c.objects and not c.children:
            bpy.context.scene.collection.children.unlink(c)
            bpy.data.collections.remove(c)
    for name, c in made.items():
        print(f"  collection {name}: {len(c.objects)} objects")


def save_blend():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "phyto_reclaim.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print(f"  saved {os.path.basename(path)}")
    return path


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    do_render = "--no-render" not in argv

    print("Building PHYTO-RECLAIM reference unit")
    print(f"  plot   {LENGTH:.2f} x {DEPTH:.2f} m = {LENGTH * DEPTH:.1f} m2")
    print(f"  tier 1 {W_TIER1:.2f} m wide = {W_TIER1 * DEPTH:.0f} m2")
    print(f"  tier 2 {W_TIER2:.2f} m wide = {W_TIER2 * DEPTH:.0f} m2")
    print(f"  process {W_PROCESS:.2f} m wide = {W_PROCESS * DEPTH:.0f} m2")

    anchors = build()
    setup_world()
    print(f"  objects: {len(bpy.data.objects)}")

    RES = (2400, 1350)
    cam_a = render("aerial", (-17, -29, 25), (LENGTH * 0.42, DEPTH * 0.48, 1.2),
                   res=RES, do_render=do_render)
    meta = {"aerial": project(cam_a, anchors, RES)}

    render("plan", (LENGTH / 2, DEPTH / 2, 60), (LENGTH / 2, DEPTH / 2, 0),
           ortho=LENGTH + 5, res=(2400, 1350), do_render=do_render)
    render("ground", (-7.5, 25.0, 2.4), (LENGTH * 0.40, DEPTH * 0.35, 1.5),
           res=(2400, 1100), do_render=do_render)
    render("process", (-11.5, -9.0, 9.5), (W_PROCESS * 0.5, 8.6, 1.6),
           res=(2000, 1400), samples=56, do_render=do_render)

    with open(os.path.join(OUT, "anchors.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print("  wrote anchors.json")

    # The aerial camera is the one worth landing on when the file is opened.
    bpy.context.scene.camera = cam_a
    organise_collections()
    save_blend()
    print("done")
