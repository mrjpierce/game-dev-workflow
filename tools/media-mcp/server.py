"""
MCP server for AI-powered 2D image generation via Stability AI.
3D model generation is handled by the official Meshy skill (meshy-3d-agent).

Requires API key in a .env file at the project root:
  STABILITY_API_KEY=sk-...
"""

import os
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Image as MCPImage

# Load .env from project root (two levels up from tools/media-mcp/)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_project_root, ".env"))

mcp = FastMCP(
    "media",
    instructions="Generate 2D images via Stability AI. For 3D models, use the Meshy skill instead.",
)

STABILITY_API_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"


def _get_key(name: str) -> str:
    key = os.environ.get(name)
    if not key:
        raise ValueError(f"{name} not set. Add it to .env in the project root.")
    return key

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



if __name__ == "__main__":
    mcp.run()
