"""
MCP server that bridges AI agents to the running Redot/Godot game.
Communicates with the in-game DebugServer autoload over TCP (localhost:9877).

Provides: input actions, state queries, telemetry, recording/replay, screenshots.
"""

import base64
import io
import json
import socket
import time
from typing import Any

from mcp.server.fastmcp import FastMCP, Image as MCPImage

mcp = FastMCP(
    "game-bridge",
    instructions="Bridge to the running Redot game — send actions, query state, capture telemetry, record/replay macros",
)

GAME_HOST = "127.0.0.1"
GAME_PORT = 9877
SOCKET_TIMEOUT = 5.0


def _send_command(cmd: dict) -> dict:
    """Send a JSON command to the game's debug server and return the response."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((GAME_HOST, GAME_PORT))

        payload = json.dumps(cmd) + "\n"
        sock.sendall(payload.encode("utf-8"))

        # Read response (newline-delimited JSON)
        buffer = ""
        while "\n" not in buffer:
            chunk = sock.recv(4096).decode("utf-8")
            if not chunk:
                break
            buffer += chunk

        sock.close()

        if buffer.strip():
            return json.loads(buffer.strip())
        return {"ok": False, "error": "Empty response from game"}

    except ConnectionRefusedError:
        return {"ok": False, "error": "Game not running or DebugServer not loaded. Start the game with the DebugServer autoload enabled (port 9877)."}
    except socket.timeout:
        return {"ok": False, "error": "Game did not respond within timeout. It may be frozen or the DebugServer is not processing."}
    except Exception as e:
        return {"ok": False, "error": f"Connection error: {e}"}


@mcp.tool()
def game_ping() -> dict:
    """Check if the game is running and the debug server is reachable."""
    return _send_command({"type": "ping"})


@mcp.tool()
def game_action(action: str, pressed: bool = True, strength: float = 1.0, duration: float = 0.0) -> dict:
    """
    Send a game input action (e.g., "jump", "move_left", "attack").
    Actions must be defined in the Godot Input Map.

    Args:
        action: The input action name (e.g., "jump", "move_left")
        pressed: True to press, False to release
        strength: Action strength from 0.0 to 1.0 (for analog inputs)
        duration: If > 0, auto-release after this many seconds
    """
    return _send_command({
        "type": "action",
        "action": action,
        "pressed": pressed,
        "strength": strength,
        "duration": duration,
    })


@mcp.tool()
def game_action_sequence(actions: str) -> list[dict]:
    """
    Send multiple actions in sequence with timing. Pass a JSON array of action objects.
    Each object: {"action": "name", "pressed": true, "duration": 0.5, "wait": 0.2}
    The "wait" field pauses before the next action (seconds).

    Args:
        actions: JSON array string of action objects, e.g. '[{"action":"jump","duration":0.3,"wait":0.5},{"action":"move_right","duration":1.0}]'
    """
    try:
        action_list = json.loads(actions)
    except json.JSONDecodeError as e:
        return [{"ok": False, "error": f"Invalid JSON: {e}"}]

    results = []
    for act in action_list:
        result = _send_command({
            "type": "action",
            "action": act.get("action", ""),
            "pressed": act.get("pressed", True),
            "strength": act.get("strength", 1.0),
            "duration": act.get("duration", 0.0),
        })
        results.append(result)

        wait = act.get("wait", 0.0)
        if wait > 0:
            time.sleep(wait)

    return results


@mcp.tool()
def game_query(path: str, property: str = "") -> dict:
    """
    Query a node in the scene tree. Returns node info or a specific property value.

    Args:
        path: Node path from root (e.g., "/root/Main/Player", "/root/Main/UI/HealthBar")
        property: Optional property name (e.g., "position", "health", "visible"). If empty, returns node info.
    """
    return _send_command({"type": "query", "path": path, "property": property})


@mcp.tool()
def game_query_tree(path: str = "/root", depth: int = 3) -> dict:
    """
    Get the scene tree structure from a given node, showing classes, positions, and children.

    Args:
        path: Starting node path (default "/root")
        depth: How many levels deep to recurse (default 3)
    """
    return _send_command({"type": "query_tree", "path": path, "depth": depth})


@mcp.tool()
def game_set(path: str, property: str, value: Any) -> dict:
    """
    Set a property on a node. Useful for testing scenarios (teleport player, set health, etc.).

    Args:
        path: Node path (e.g., "/root/Main/Player")
        property: Property name (e.g., "position", "health")
        value: New value. Use {"x": 100, "y": 200} for Vector2, plain numbers/strings otherwise.
    """
    return _send_command({"type": "set", "path": path, "property": property, "value": value})


@mcp.tool()
def game_eval(expression: str) -> dict:
    """
    Evaluate a GDScript expression in the context of the current scene.
    Useful for one-off queries or calling functions.

    Args:
        expression: GDScript expression (e.g., "get_node('Player').health", "get_tree().get_node_count()")
    """
    return _send_command({"type": "eval", "expression": expression})


@mcp.tool()
def game_screenshot() -> Any:
    """
    Capture a screenshot from the game's internal viewport.
    This is pixel-perfect and works regardless of window state.
    """
    result = _send_command({"type": "screenshot"})
    if not result.get("ok"):
        return result

    png_data = base64.b64decode(result["data_base64"])
    return MCPImage(data=png_data, format="png")


# --- Telemetry ---

@mcp.tool()
def game_telemetry_snapshot() -> dict:
    """
    Get a single telemetry snapshot of current game state.
    Includes: FPS, frame count, current scene, node count, player position/health (if found).
    """
    return _send_command({"type": "telemetry_snapshot"})


@mcp.tool()
def game_telemetry_history(since: float = 0.0, limit: int = 100) -> dict:
    """
    Get telemetry history — a time series of game state snapshots.
    The game samples telemetry every 0.5 seconds by default.

    Args:
        since: Only return entries after this timestamp (seconds since game start)
        limit: Maximum number of entries to return (default 100, most recent)
    """
    return _send_command({"type": "telemetry_history", "since": since, "limit": limit})


@mcp.tool()
def game_telemetry_clear() -> dict:
    """Clear the telemetry history log in the game."""
    return _send_command({"type": "telemetry_clear"})


@mcp.tool()
def game_telemetry_config(enabled: bool = True, interval: float = 0.5) -> dict:
    """
    Configure telemetry collection.

    Args:
        enabled: Turn telemetry sampling on/off
        interval: Seconds between telemetry samples (default 0.5)
    """
    return _send_command({"type": "telemetry_config", "enabled": enabled, "interval": interval})


# --- Recording & Replay ---

@mcp.tool()
def game_record_start() -> dict:
    """
    Start recording all actions sent through the bridge.
    Recording starts automatically when the game boots — use this to restart a clean recording.
    """
    return _send_command({"type": "record_start"})


@mcp.tool()
def game_record_stop() -> dict:
    """
    Stop recording and return the recorded actions as a replayable macro.
    The returned "actions" array can be passed directly to game_replay().
    Save it to a file to share with other agents or humans.
    """
    return _send_command({"type": "record_stop"})


@mcp.tool()
def game_replay(actions: str) -> dict:
    """
    Replay a recorded macro. Actions are played back with their original timing.
    Pass the "actions" array from game_record_stop() as a JSON string.

    Args:
        actions: JSON array string of recorded actions (from game_record_stop)
    """
    try:
        action_list = json.loads(actions)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid JSON: {e}"}

    return _send_command({"type": "replay", "actions": action_list})


@mcp.tool()
def game_replay_status() -> dict:
    """Check the status of a running replay (in progress, index, total actions)."""
    return _send_command({"type": "replay_status"})


if __name__ == "__main__":
    mcp.run()
