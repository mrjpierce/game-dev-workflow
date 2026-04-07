"""
MCP server for 3D model viewing and validation.
Renders models from multiple angles using pyrender (offline, no GPU required).
Inspired by the loot-flavor validation pipeline.

Supports: GLB, GLTF, OBJ, PLY, STL
"""

import io
import os
from typing import Any

import numpy as np
import trimesh
import pyrender
from PIL import Image, ImageDraw
from mcp.server.fastmcp import FastMCP, Image as MCPImage

mcp = FastMCP(
    "model-viewer",
    instructions="Render 3D models from multiple angles for AI agent inspection",
)

RENDER_SIZE = 512
BG_COLOR = [0.12, 0.12, 0.12, 1.0]


def _load_mesh(model_path: str) -> trimesh.Trimesh:
    """Load a 3D model and return a single concatenated mesh."""
    loaded = trimesh.load(model_path)
    if isinstance(loaded, trimesh.Scene):
        if len(loaded.geometry) == 0:
            raise ValueError(f"Model has no geometry: {model_path}")
        mesh = loaded.dump(concatenate=True)
    else:
        mesh = loaded
    return mesh


def _build_scene(
    mesh: trimesh.Trimesh,
    show_axes: bool = False,
    show_grid: bool = False,
    use_textures: bool = True,
) -> pyrender.Scene:
    """Build a pyrender scene with lighting and optional overlays."""
    scene = pyrender.Scene(
        bg_color=BG_COLOR,
        ambient_light=[0.3, 0.3, 0.3],
    )

    # Add the model
    if use_textures and hasattr(mesh.visual, "material"):
        try:
            render_mesh = pyrender.Mesh.from_trimesh(mesh, smooth=True)
        except Exception:
            # Fallback if texture loading fails
            mesh.visual = trimesh.visual.ColorVisuals()
            mat = pyrender.MetallicRoughnessMaterial(
                baseColorFactor=[0.6, 0.6, 0.6, 1.0],
                metallicFactor=0.3,
                roughnessFactor=0.7,
            )
            render_mesh = pyrender.Mesh.from_trimesh(mesh, material=mat, smooth=True)
    else:
        mesh.visual = trimesh.visual.ColorVisuals()
        mat = pyrender.MetallicRoughnessMaterial(
            baseColorFactor=[0.6, 0.6, 0.6, 1.0],
            metallicFactor=0.3,
            roughnessFactor=0.7,
        )
        render_mesh = pyrender.Mesh.from_trimesh(mesh, material=mat, smooth=True)

    scene.add(render_mesh)

    # Axis indicators at origin
    if show_axes:
        axis_length = 0.3
        axis_radius = 0.008
        for axis_idx, color in enumerate([(1, 0, 0), (0, 1, 0), (0, 0, 1)]):
            cyl = trimesh.creation.cylinder(radius=axis_radius, height=axis_length)
            if axis_idx == 0:  # X — red
                rot = trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
                cyl.apply_transform(rot)
                cyl.apply_translation([axis_length / 2, 0, 0])
            elif axis_idx == 1:  # Y — green
                rot = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
                cyl.apply_transform(rot)
                cyl.apply_translation([0, axis_length / 2, 0])
            else:  # Z — blue
                cyl.apply_translation([0, 0, axis_length / 2])
            cyl.visual = trimesh.visual.ColorVisuals()
            axis_mat = pyrender.MetallicRoughnessMaterial(
                baseColorFactor=[*color, 1.0],
                metallicFactor=0.0,
                roughnessFactor=1.0,
                emissiveFactor=list(color),
            )
            scene.add(pyrender.Mesh.from_trimesh(cyl, material=axis_mat))

    # Grid floor at Z=0
    if show_grid:
        grid_size = 2.0
        grid_lines = 10
        for i in range(grid_lines + 1):
            t = -grid_size / 2 + i * grid_size / grid_lines
            for start, end in [
                ([t, -grid_size / 2, 0], [t, grid_size / 2, 0]),
                ([-grid_size / 2, t, 0], [grid_size / 2, t, 0]),
            ]:
                seg = trimesh.creation.cylinder(
                    radius=0.003,
                    segment=[start, end],
                )
                seg.visual = trimesh.visual.ColorVisuals()
                grid_mat = pyrender.MetallicRoughnessMaterial(
                    baseColorFactor=[0.3, 0.3, 0.3, 1.0],
                    metallicFactor=0.0,
                    roughnessFactor=1.0,
                )
                scene.add(pyrender.Mesh.from_trimesh(seg, material=grid_mat))

    # Key light — warm, from upper right
    key = pyrender.DirectionalLight(color=[1.0, 0.95, 0.9], intensity=4.0)
    key_pose = np.array([
        [0.866, 0.0, -0.5, 0.0],
        [0.25, 0.866, 0.433, 2.0],
        [0.433, -0.5, 0.75, 2.0],
        [0.0, 0.0, 0.0, 1.0],
    ])
    scene.add(key, pose=key_pose)

    # Fill light — cool blue, from opposite side
    fill = pyrender.DirectionalLight(color=[0.6, 0.7, 1.0], intensity=2.0)
    fill_pose = np.array([
        [0.866, 0.0, 0.5, 0.0],
        [-0.25, 0.866, 0.433, 0.0],
        [-0.433, -0.5, 0.75, -2.0],
        [0.0, 0.0, 0.0, 1.0],
    ])
    scene.add(fill, pose=fill_pose)

    return scene


def _render_view(
    scene: pyrender.Scene,
    angle_deg: float,
    elevation_deg: float = 20.0,
    distance: float = 3.0,
    ortho_scale: float = 1.2,
    size: int = RENDER_SIZE,
) -> np.ndarray:
    """Render the scene from a given angle with orthographic camera."""
    h_rad = np.radians(angle_deg)
    e_rad = np.radians(elevation_deg)

    eye = np.array([
        distance * np.cos(e_rad) * np.sin(h_rad),
        distance * np.cos(e_rad) * np.cos(h_rad),
        distance * np.sin(e_rad),
    ])

    forward = -eye / np.linalg.norm(eye)
    world_up = np.array([0, 0, 1])
    right = np.cross(forward, world_up)
    norm = np.linalg.norm(right)
    if norm < 1e-6:
        right = np.array([1, 0, 0])
    else:
        right = right / norm
    up = np.cross(right, forward)

    camera_pose = np.eye(4)
    camera_pose[:3, 0] = right
    camera_pose[:3, 1] = up
    camera_pose[:3, 2] = -forward
    camera_pose[:3, 3] = eye

    camera = pyrender.OrthographicCamera(xmag=ortho_scale, ymag=ortho_scale)
    cam_node = scene.add(camera, pose=camera_pose)

    renderer = pyrender.OffscreenRenderer(size, size)
    color, _ = renderer.render(scene, flags=pyrender.RenderFlags.RGBA)
    renderer.delete()

    scene.remove_node(cam_node)
    return color


def _auto_scale_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Center and scale mesh to fit within a unit sphere."""
    mesh.apply_translation(-mesh.centroid)
    extent = mesh.extents.max()
    if extent > 0:
        mesh.apply_scale(1.8 / extent)
    return mesh


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@mcp.tool()
def view_model(
    model_path: str,
    angle: float = 45.0,
    elevation: float = 20.0,
    show_axes: bool = False,
    show_grid: bool = False,
) -> Any:
    """
    Render a 3D model from a single angle and return the image.

    Args:
        model_path: Absolute path to the model file (GLB, GLTF, OBJ, PLY, STL)
        angle: Horizontal rotation in degrees (0=front, 90=right, 180=back, 270=left)
        elevation: Vertical angle in degrees (0=eye level, 90=top down)
        show_axes: Show RGB axis indicators at origin (R=X, G=Y, B=Z)
        show_grid: Show a grid floor at Z=0
    """
    if not os.path.isabs(model_path):
        return "Error: model_path must be an absolute path"
    if not os.path.exists(model_path):
        return f"Error: file not found: {model_path}"

    mesh = _load_mesh(model_path)
    mesh = _auto_scale_mesh(mesh)
    scene = _build_scene(mesh, show_axes=show_axes, show_grid=show_grid)
    color = _render_view(scene, angle, elevation)
    img = Image.fromarray(color, "RGBA")

    return MCPImage(data=_to_png_bytes(img), format="png")


@mcp.tool()
def view_model_multi(
    model_path: str,
    angles: str = "0,90,180,45",
    elevation: float = 20.0,
    show_axes: bool = True,
    show_grid: bool = False,
    labels: str = "Front,Right,Back,3/4",
) -> Any:
    """
    Render a 3D model from multiple angles as a composite grid image.

    Args:
        model_path: Absolute path to the model file (GLB, GLTF, OBJ, PLY, STL)
        angles: Comma-separated horizontal angles in degrees (e.g. "0,90,180,270")
        elevation: Vertical angle in degrees (0=eye level, 90=top down)
        show_axes: Show RGB axis indicators at origin
        show_grid: Show a grid floor at Z=0
        labels: Comma-separated labels for each view (must match number of angles)
    """
    if not os.path.isabs(model_path):
        return "Error: model_path must be an absolute path"
    if not os.path.exists(model_path):
        return f"Error: file not found: {model_path}"

    angle_list = [float(a.strip()) for a in angles.split(",")]
    label_list = [l.strip() for l in labels.split(",")]

    # Pad labels if needed
    while len(label_list) < len(angle_list):
        label_list.append(f"{angle_list[len(label_list)]}°")

    mesh = _load_mesh(model_path)
    mesh = _auto_scale_mesh(mesh)
    scene = _build_scene(mesh, show_axes=show_axes, show_grid=show_grid)

    images = []
    for angle, label in zip(angle_list, label_list):
        color = _render_view(scene, angle, elevation)
        img = Image.fromarray(color, "RGBA")

        draw = ImageDraw.Draw(img)
        draw.text((10, 10), label, fill=(255, 255, 255, 255))
        if show_axes:
            draw.text((10, 28), "R=+X  G=+Y  B=+Z", fill=(180, 180, 180, 255))

        images.append(img)

    # Compose into grid (2 columns)
    cols = 2
    rows = (len(images) + cols - 1) // cols
    composite = Image.new("RGBA", (RENDER_SIZE * cols, RENDER_SIZE * rows), (30, 30, 30, 255))
    for i, img in enumerate(images):
        x = (i % cols) * RENDER_SIZE
        y = (i // cols) * RENDER_SIZE
        composite.paste(img, (x, y))

    # Add filename at bottom
    draw = ImageDraw.Draw(composite)
    name = os.path.basename(model_path)
    draw.text((10, composite.height - 20), name, fill=(150, 150, 150, 255))

    return MCPImage(data=_to_png_bytes(composite), format="png")


@mcp.tool()
def inspect_model(model_path: str) -> dict[str, Any]:
    """
    Inspect a 3D model's geometry without rendering. Returns mesh statistics.

    Args:
        model_path: Absolute path to the model file (GLB, GLTF, OBJ, PLY, STL)
    """
    if not os.path.isabs(model_path):
        return {"error": "model_path must be an absolute path"}
    if not os.path.exists(model_path):
        return {"error": f"file not found: {model_path}"}

    mesh = _load_mesh(model_path)
    extents = mesh.extents.tolist()
    bbox_min = mesh.bounds[0].tolist()
    bbox_max = mesh.bounds[1].tolist()

    # Elongation ratio
    sorted_extents = sorted(extents, reverse=True)
    elongation = sorted_extents[0] / sorted_extents[-1] if sorted_extents[-1] > 1e-6 else float("inf")

    # Check for degenerate faces
    areas = mesh.area_faces
    degenerate = int(np.sum(areas < 1e-10))

    # Check for watertight (closed mesh)
    is_watertight = bool(mesh.is_watertight)

    return {
        "file": os.path.basename(model_path),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "extents": {
            "x": round(extents[0], 4),
            "y": round(extents[1], 4),
            "z": round(extents[2], 4),
        },
        "bounding_box": {
            "min": [round(v, 4) for v in bbox_min],
            "max": [round(v, 4) for v in bbox_max],
        },
        "elongation_ratio": round(elongation, 2),
        "degenerate_faces": degenerate,
        "degenerate_pct": round(degenerate / max(len(mesh.faces), 1) * 100, 2),
        "is_watertight": is_watertight,
        "centroid": [round(v, 4) for v in mesh.centroid.tolist()],
    }


@mcp.tool()
def view_model_turntable(
    model_path: str,
    frames: int = 8,
    elevation: float = 20.0,
    show_axes: bool = False,
) -> Any:
    """
    Render a model from evenly-spaced angles around a full 360° rotation.
    Returns a horizontal strip of all frames composited together.

    Args:
        model_path: Absolute path to the model file
        frames: Number of frames around the turntable (default 8 = every 45°)
        elevation: Vertical angle in degrees
        show_axes: Show RGB axis indicators at origin
    """
    if not os.path.isabs(model_path):
        return "Error: model_path must be an absolute path"
    if not os.path.exists(model_path):
        return f"Error: file not found: {model_path}"

    frames = min(frames, 16)  # Cap to avoid huge images
    frame_size = 256  # Smaller per-frame for strip layout

    mesh = _load_mesh(model_path)
    mesh = _auto_scale_mesh(mesh)
    scene = _build_scene(mesh, show_axes=show_axes)

    images = []
    for i in range(frames):
        angle = i * (360.0 / frames)
        color = _render_view(scene, angle, elevation, size=frame_size)
        img = Image.fromarray(color, "RGBA")

        draw = ImageDraw.Draw(img)
        draw.text((4, 4), f"{int(angle)}°", fill=(200, 200, 200, 255))
        images.append(img)

    # Compose as a grid (4 columns max)
    cols = min(4, frames)
    rows = (frames + cols - 1) // cols
    composite = Image.new("RGBA", (frame_size * cols, frame_size * rows), (30, 30, 30, 255))
    for i, img in enumerate(images):
        x = (i % cols) * frame_size
        y = (i // cols) * frame_size
        composite.paste(img, (x, y))

    return MCPImage(data=_to_png_bytes(composite), format="png")


if __name__ == "__main__":
    mcp.run()
