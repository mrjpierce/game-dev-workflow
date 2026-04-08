"""
MCP server for AI-powered media asset creation.
Wraps Stability AI (image generation) and Meshy AI (image-to-3D model).

Requires API keys in a .env file at the project root:
  STABILITY_API_KEY=sk-...
  MESHY_API_KEY=msy_...
"""

import base64
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Image as MCPImage

# Load .env from project root (two levels up from tools/media-mcp/)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_project_root, ".env"))

mcp = FastMCP(
    "media",
    instructions="Generate 2D images via Stability AI and 3D models via Meshy AI",
)

STABILITY_API_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"
MESHY_API_BASE = "https://api.meshy.ai/openapi/v1/image-to-3d"


def _get_key(name: str) -> str:
    key = os.environ.get(name)
    if not key:
        raise ValueError(f"{name} not set. Add it to .env in the project root.")
    return key


# =============================================================================
# Stability AI — Image Generation
# =============================================================================

@mcp.tool()
def generate_image(
    prompt: str,
    output_path: str,
    negative_prompt: str = "",
    aspect_ratio: str = "1:1",
    style_preset: str = "",
) -> Any:
    """
    Generate a 2D image using Stability AI and save it to disk.
    Returns the image for visual inspection.

    Args:
        prompt: What to generate. Be specific about subject, style, lighting, background.
        output_path: Absolute path to save the PNG (e.g., "C:/Projects/my-game/game/assets/sprites/player.png")
        negative_prompt: What to avoid (e.g., "blurry, low quality, text, watermark")
        aspect_ratio: Image aspect ratio — "1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21"
        style_preset: Optional style — "3d-model", "analog-film", "anime", "cinematic", "comic-book", "digital-art", "fantasy-art", "isometric", "line-art", "neon-punk", "origami", "pixel-art", "tile-texture"
    """
    api_key = _get_key("STABILITY_API_KEY")

    if not os.path.isabs(output_path):
        return {"ok": False, "error": "output_path must be an absolute path"}

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data = {
        "prompt": prompt,
        "output_format": "png",
        "aspect_ratio": aspect_ratio,
    }
    if negative_prompt:
        data["negative_prompt"] = negative_prompt
    if style_preset:
        data["style_preset"] = style_preset

    response = httpx.post(
        STABILITY_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "image/*",
        },
        files={"none": ""},
        data=data,
        timeout=120.0,
    )

    if response.status_code != 200:
        return {"ok": False, "error": f"Stability API error {response.status_code}: {response.text}"}

    with open(output_path, "wb") as f:
        f.write(response.content)

    return MCPImage(data=response.content, format="png")


@mcp.tool()
def generate_sprite(
    prompt: str,
    output_path: str,
    style: str = "pixel-art",
) -> Any:
    """
    Generate a game sprite with transparent-friendly settings.
    Automatically adds game-asset-specific prompt engineering.

    Args:
        prompt: What the sprite should be (e.g., "a small red slime enemy", "a golden coin pickup")
        output_path: Absolute path to save the PNG
        style: Art style — "pixel-art", "digital-art", "anime", "comic-book", "fantasy-art", "line-art"
    """
    full_prompt = (
        f"{prompt}. "
        f"Single game sprite, centered, plain solid color background, "
        f"clean edges, no shadow on ground, suitable for 2D game engine import. "
        f"Style: {style}, game asset."
    )
    negative_prompt = (
        "multiple objects, busy background, gradient background, text, watermark, "
        "blurry, low quality, cropped, partial, cut off edges"
    )

    return generate_image(
        prompt=full_prompt,
        output_path=output_path,
        negative_prompt=negative_prompt,
        aspect_ratio="1:1",
        style_preset=style if style in [
            "pixel-art", "digital-art", "anime", "comic-book",
            "fantasy-art", "line-art", "3d-model", "isometric",
        ] else "",
    )


@mcp.tool()
def generate_texture(
    prompt: str,
    output_path: str,
    seamless: bool = True,
) -> Any:
    """
    Generate a tileable texture for use as a material or background.

    Args:
        prompt: What the texture should look like (e.g., "mossy stone wall", "wooden floor planks")
        output_path: Absolute path to save the PNG
        seamless: If True, adds seamless/tileable to the prompt
    """
    tile_hint = "seamless tileable repeating pattern, " if seamless else ""
    full_prompt = (
        f"{tile_hint}{prompt}. "
        f"Flat texture, top-down view, even lighting, no perspective, "
        f"suitable for game engine material."
    )
    negative_prompt = (
        "3d perspective, objects, characters, text, watermark, "
        "vignette, uneven lighting, shadows from objects"
    )

    return generate_image(
        prompt=full_prompt,
        output_path=output_path,
        negative_prompt=negative_prompt,
        aspect_ratio="1:1",
        style_preset="tile-texture",
    )


@mcp.tool()
def generate_concept_art(
    prompt: str,
    output_path: str,
    aspect_ratio: str = "16:9",
) -> Any:
    """
    Generate concept art for visual reference and design exploration.

    Args:
        prompt: Detailed description of the scene, character, or environment
        output_path: Absolute path to save the PNG
        aspect_ratio: "16:9" for landscapes, "9:16" for characters/items, "1:1" for icons
    """
    full_prompt = (
        f"{prompt}. "
        f"Professional concept art, detailed, painterly style, "
        f"dramatic lighting, rich colors."
    )
    negative_prompt = "photo, photograph, blurry, low quality, text, watermark, UI elements"

    return generate_image(
        prompt=full_prompt,
        output_path=output_path,
        negative_prompt=negative_prompt,
        aspect_ratio=aspect_ratio,
        style_preset="fantasy-art",
    )


# =============================================================================
# Meshy AI — Image to 3D Model
# =============================================================================

def _image_to_data_uri(image_path: str) -> str:
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64,{image_data}"


def _poll_meshy_task(api_key: str, task_id: str, timeout: int = 600) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"}
    start = time.time()

    while time.time() - start < timeout:
        response = httpx.get(
            f"{MESHY_API_BASE}/{task_id}",
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        task = response.json()
        status = task.get("status")

        if status == "SUCCEEDED":
            return task
        elif status == "FAILED":
            error_msg = task.get("task_error", {}).get("message", "unknown")
            raise RuntimeError(f"Meshy task failed: {error_msg}")

        time.sleep(5)

    raise TimeoutError(f"Meshy task {task_id} timed out after {timeout}s")


@mcp.tool()
def generate_3d_model(
    image_path: str,
    output_path: str,
    polycount: int = 30000,
    texture: bool = True,
    remesh: bool = True,
) -> dict:
    """
    Generate a 3D model from a reference image using Meshy AI (image-to-3D).
    This is an async operation that typically takes 2-10 minutes.

    Args:
        image_path: Absolute path to the input image (PNG or JPG)
        output_path: Absolute path for the output GLB file (e.g., "C:/.../model.glb")
        polycount: Target polygon count (default 30000)
        texture: Generate PBR textures (default True)
        remesh: Optimize mesh topology (default True)
    """
    api_key = _get_key("MESHY_API_KEY")

    if not os.path.isabs(image_path):
        return {"ok": False, "error": "image_path must be an absolute path"}
    if not os.path.isabs(output_path):
        return {"ok": False, "error": "output_path must be an absolute path"}
    if not os.path.exists(image_path):
        return {"ok": False, "error": f"Image not found: {image_path}"}

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data_uri = _image_to_data_uri(image_path)

    # Create task
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = httpx.post(
        MESHY_API_BASE,
        headers=headers,
        json={
            "image_url": data_uri,
            "ai_model": "meshy-6",
            "enable_pbr": texture,
            "should_remesh": remesh,
            "should_texture": texture,
            "target_formats": ["glb"],
            "topology": "triangle",
            "target_polycount": polycount,
        },
        timeout=120.0,
    )

    if response.status_code not in (200, 201, 202):
        return {"ok": False, "error": f"Meshy API error {response.status_code}: {response.text}"}

    task_data = response.json()
    task_id = task_data.get("result")
    if not task_id:
        return {"ok": False, "error": f"No task ID in Meshy response: {task_data}"}

    # Poll for completion
    try:
        result = _poll_meshy_task(api_key, task_id)
    except (RuntimeError, TimeoutError) as e:
        return {"ok": False, "error": str(e), "task_id": task_id}

    # Download GLB
    model_urls = result.get("model_urls", {})
    model_url = model_urls.get("glb") or model_urls.get("obj")
    if not model_url:
        return {"ok": False, "error": f"No model URL in result: {model_urls}"}

    model_response = httpx.get(model_url, timeout=120.0)
    model_response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(model_response.content)

    # Download thumbnail
    thumbnail_path = None
    thumbnail_url = result.get("thumbnail_url")
    if thumbnail_url:
        thumbnail_path = output_path.rsplit(".", 1)[0] + "_thumbnail.png"
        thumb_response = httpx.get(thumbnail_url, timeout=60.0)
        if thumb_response.status_code == 200:
            with open(thumbnail_path, "wb") as f:
                f.write(thumb_response.content)

    return {
        "ok": True,
        "model_path": output_path,
        "thumbnail_path": thumbnail_path,
        "task_id": task_id,
        "polycount": polycount,
    }


@mcp.tool()
def check_meshy_task(task_id: str) -> dict:
    """
    Check the status of a Meshy 3D generation task.
    Useful if you started a task and want to check on it later.

    Args:
        task_id: The Meshy task ID returned by generate_3d_model
    """
    api_key = _get_key("MESHY_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    response = httpx.get(
        f"{MESHY_API_BASE}/{task_id}",
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()
    task = response.json()

    return {
        "ok": True,
        "task_id": task_id,
        "status": task.get("status"),
        "progress": task.get("progress", 0),
        "model_urls": task.get("model_urls"),
        "thumbnail_url": task.get("thumbnail_url"),
    }


if __name__ == "__main__":
    mcp.run()
