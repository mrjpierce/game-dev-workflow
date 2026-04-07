"""
MCP server for capturing Windows window screenshots.
Supports capturing windows even when they're behind other windows.
Uses Win32 PrintWindow API with PW_RENDERFULLCONTENT flag.
"""

import ctypes
import ctypes.wintypes
import io
from typing import Any

import win32gui
import win32ui
import win32con
import win32process
import win32api
from PIL import Image
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "screenshot-server",
    description="Capture screenshots of Windows windows, even when occluded",
)

# Win32 constants
PW_RENDERFULLCONTENT = 0x00000002
DWMWA_CLOAKED = 14
WS_EX_TOOLWINDOW = 0x00000080


def _is_real_window(hwnd: int) -> bool:
    """Filter to only real, visible application windows."""
    if not win32gui.IsWindowVisible(hwnd):
        return False

    # Skip tool windows (tooltips, floating palettes)
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex_style & WS_EX_TOOLWINDOW:
        return False

    # Skip cloaked windows (UWP hidden windows, virtual desktop)
    cloaked = ctypes.c_int(0)
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    )
    if cloaked.value != 0:
        return False

    # Must have a title
    title = win32gui.GetWindowText(hwnd)
    if not title:
        return False

    return True


def _get_process_name(hwnd: int) -> str:
    """Get the process name for a window handle."""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = win32api.OpenProcess(0x0410, False, pid)  # QUERY_INFO | VM_READ
        exe = win32process.GetModuleFileNameEx(handle, 0)
        win32api.CloseHandle(handle)
        return exe.rsplit("\\", 1)[-1]
    except Exception:
        return "unknown"


def _capture_window(hwnd: int) -> bytes:
    """Capture a window screenshot using PrintWindow, even if occluded."""
    # Get window dimensions
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    if width <= 0 or height <= 0:
        raise ValueError(f"Window has invalid dimensions: {width}x{height}")

    # Create device contexts and bitmap
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)

    # PrintWindow captures even when window is behind others
    result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), PW_RENDERFULLCONTENT)

    if not result:
        # Fallback to BitBlt (works for foreground windows)
        save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)

    # Convert bitmap to PNG bytes
    bmp_info = bitmap.GetInfo()
    bmp_bits = bitmap.GetBitmapBits(True)

    img = Image.frombuffer("RGBA", (bmp_info["bmWidth"], bmp_info["bmHeight"]), bmp_bits, "raw", "BGRA", 0, 1)

    # Clean up GDI resources
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32gui.DeleteObject(bitmap.GetHandle())

    # Convert to PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@mcp.tool()
def list_windows() -> list[dict[str, Any]]:
    """List all visible application windows with their handles, titles, and process names."""
    windows = []

    def enum_callback(hwnd: int, _: Any) -> bool:
        if _is_real_window(hwnd):
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            windows.append({
                "hwnd": hwnd,
                "title": win32gui.GetWindowText(hwnd),
                "process": _get_process_name(hwnd),
                "size": f"{right - left}x{bottom - top}",
            })
        return True

    win32gui.EnumWindows(enum_callback, None)
    return windows


@mcp.tool()
def screenshot_window(title: str) -> Any:
    """
    Take a screenshot of a window by title (partial match, case-insensitive).
    Works even when the window is behind other windows.

    Args:
        title: Full or partial window title to match (case-insensitive)
    """
    title_lower = title.lower()
    target_hwnd = None

    def enum_callback(hwnd: int, _: Any) -> bool:
        nonlocal target_hwnd
        if _is_real_window(hwnd):
            wnd_title = win32gui.GetWindowText(hwnd)
            if title_lower in wnd_title.lower():
                target_hwnd = hwnd
                return False  # Stop enumeration
        return True

    win32gui.EnumWindows(enum_callback, None)

    if target_hwnd is None:
        return f"No window found matching '{title}'. Use list_windows to see available windows."

    png_bytes = _capture_window(target_hwnd)
    actual_title = win32gui.GetWindowText(target_hwnd)

    from mcp.server.fastmcp import Image as MCPImage
    return MCPImage(data=png_bytes, format="png")


@mcp.tool()
def screenshot_window_by_hwnd(hwnd: int) -> Any:
    """
    Take a screenshot of a window by its handle (hwnd).
    Works even when the window is behind other windows.
    Use list_windows to get window handles.

    Args:
        hwnd: The window handle (integer)
    """
    if not win32gui.IsWindow(hwnd):
        return f"Invalid window handle: {hwnd}"

    png_bytes = _capture_window(hwnd)

    from mcp.server.fastmcp import Image as MCPImage
    return MCPImage(data=png_bytes, format="png")


if __name__ == "__main__":
    mcp.run()
