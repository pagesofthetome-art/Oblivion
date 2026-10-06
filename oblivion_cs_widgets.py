"""Read/drive common Win32 widgets inside the Construction Set (list views, tree views, keys).

Used by oblivion_cs_bridge_server.py. Every function receives an HWND that the caller has
already verified belongs to TESConstructionSet.exe (see get_construction_set_window).

The CS is a 32-bit process. pywinauto reads list/tree items across processes; with 64-bit
Python this normally works for SysListView32/SysTreeView32, but if a call fails with a
memory or structure error, install 32-bit Python and run the bridge with it.
"""

from __future__ import annotations

import time
from typing import Any

from pywinauto import Desktop

MAX_ITEMS = 5000


def _wrapper(hwnd: int):
    spec = Desktop(backend="win32").window(handle=hwnd)
    return spec.wrapper_object()


def listview_rows(hwnd: int, start: int = 0, count: int = 500, columns: bool = True) -> dict[str, Any]:
    lv = _wrapper(hwnd)
    if lv.friendly_class_name() != "ListView":
        raise TypeError(f"HWND {hwnd} is a {lv.friendly_class_name()}, not a ListView (SysListView32)")
    total = lv.item_count()
    ncol = lv.column_count() if columns else 1
    heads = []
    if columns:
        try:
            heads = [c.get("text", "") for c in lv.columns()]
        except Exception:
            heads = []
    count = max(0, min(count, MAX_ITEMS))
    rows = []
    for i in range(start, min(total, start + count)):
        row = []
        for j in range(max(ncol, 1)):
            try:
                row.append(lv.get_item(i, j).text())
            except Exception:
                row.append("")
        sel = False
        try:
            sel = bool(lv.is_selected(i))
        except Exception:
            pass
        rows.append({"index": i, "cells": row, "selected": sel})
    return {"hwnd": hwnd, "total": total, "columns": heads, "start": start, "rows": rows}


def listview_select(hwnd: int, text: str | None, index: int | None, double: bool) -> dict[str, Any]:
    lv = _wrapper(hwnd)
    if lv.friendly_class_name() != "ListView":
        raise TypeError(f"HWND {hwnd} is not a ListView")
    if (text is None) == (index is None):
        raise ValueError("Supply exactly one of text or index")
    if text is not None:
        matches = [i for i in range(lv.item_count()) if lv.get_item(i, 0).text().casefold() == text.casefold()]
        if not matches:
            raise LookupError(f"No list item has the exact first-column text {text!r}")
        if len(matches) > 1:
            raise LookupError(f"{len(matches)} items match {text!r}; use index")
        index = matches[0]
    item = lv.get_item(index)
    item.ensure_visible()
    item.select()
    if double:
        item.click_input(double=True)
    return {"ok": True, "index": index, "text": item.text(), "double_clicked": double}


def _tree_node(item, depth: int, max_depth: int, budget: list[int]) -> dict[str, Any]:
    budget[0] -= 1
    node = {"text": item.text()}
    if depth < max_depth and budget[0] > 0:
        try:
            kids = item.children()
        except Exception:
            kids = []
        if kids:
            node["children"] = [_tree_node(k, depth + 1, max_depth, budget) for k in kids if budget[0] > 0]
    return node


def tree_items(hwnd: int, max_depth: int = 2) -> dict[str, Any]:
    tv = _wrapper(hwnd)
    if tv.friendly_class_name() != "TreeView":
        raise TypeError(f"HWND {hwnd} is a {tv.friendly_class_name()}, not a TreeView (SysTreeView32)")
    budget = [MAX_ITEMS]
    return {"hwnd": hwnd, "roots": [_tree_node(r, 0, max_depth, budget) for r in tv.roots()]}


def tree_select(hwnd: int, path: str) -> dict[str, Any]:
    """path like '\\\\Items\\\\Weapon' (backslash separated, as pywinauto expects)."""
    tv = _wrapper(hwnd)
    if tv.friendly_class_name() != "TreeView":
        raise TypeError(f"HWND {hwnd} is not a TreeView")
    p = path if path.startswith("\\") else "\\" + path
    item = tv.get_item(p)
    item.ensure_visible()
    item.select()
    return {"ok": True, "path": p, "text": item.text()}


def send_keys(w, keys: str) -> None:
    """pywinauto key syntax: {ENTER} {ESC} {TAB} ^s (Ctrl+S) %f (Alt+F) +{TAB} etc."""
    try:
        w.set_focus()
    except Exception:
        pass
    w.type_keys(keys, set_foreground=True, with_spaces=True, pause=0.03)


def wait_for_title(enum_fn, title: str, timeout: float, exact: bool) -> dict[str, Any] | None:
    """Poll Construction Set windows until one has the given title (case-insensitive)."""
    end = time.time() + max(0.0, min(timeout, 120.0))
    t = title.casefold()
    while True:
        for row in enum_fn():
            name = str(row.get("title", "")).casefold()
            if (name == t) if exact else (t in name):
                return row
        if time.time() >= end:
            return None
        time.sleep(0.25)


def capture_printwindow(hwnd: int):
    """Capture a window with PrintWindow(PW_RENDERFULLCONTENT).

    Works when the window is covered by other windows (e.g. a remote-desktop or agent
    surface on top), unlike screen-grab captures. The Direct3D Render Window may still
    come out black; dialogs, lists and the Object Window capture fine.
    """
    import ctypes
    from ctypes import wintypes
    from PIL import Image

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT]

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetWindowRect failed")
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise OSError("window has no visible area (minimized?)")
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    try:
        if not user32.PrintWindow(hwnd, mem, 2):  # PW_RENDERFULLCONTENT
            user32.PrintWindow(hwnd, mem, 0)
        bih = BITMAPINFOHEADER()
        bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bih.biWidth, bih.biHeight, bih.biPlanes, bih.biBitCount = w, -h, 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0):
            raise OSError("GetDIBits failed")
        return Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)


# --------------------------------------------------------------------------- toolbars and menus
# The CS is 32-bit and the bridge may run 64-bit Python, so toolbar buttons are read with
# TB_GETBUTTON into memory allocated inside the CS process, parsed with the CS's own TBBUTTON
# layout (20 bytes on 32-bit, 32 on 64-bit). Buttons are pressed by posting WM_COMMAND with the
# button's command id to the toolbar's owner: no mouse movement.

TB_BUTTONCOUNT = 0x0418
TB_GETBUTTON = 0x0417
WM_COMMAND = 0x0111
TBSTYLE_SEP = 0x01
TBSTATE_ENABLED = 0x04
TBSTATE_CHECKED = 0x01
TBSTATE_HIDDEN = 0x08


def _user32():
    import ctypes
    from ctypes import wintypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SendMessageW.restype = ctypes.c_ssize_t
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    u.GetParent.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    return u


def _is_32bit_process(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return True
    try:
        wow = wintypes.BOOL()
        k.IsWow64Process(h, ctypes.byref(wow))
        return bool(wow.value)                    # 32-bit process on 64-bit Windows
    finally:
        k.CloseHandle(h)


def toolbar_buttons(hwnd: int) -> dict[str, Any]:
    import ctypes
    import struct
    from ctypes import wintypes
    u = _user32()
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.VirtualAllocEx.restype = ctypes.c_void_p
    k.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
    k.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
    k.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_size_t)]
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    is32 = _is_32bit_process(pid.value)
    size = 20 if is32 else 32
    count = int(u.SendMessageW(hwnd, TB_BUTTONCOUNT, 0, 0))
    proc = k.OpenProcess(0x0008 | 0x0010 | 0x0020 | 0x0400, False, pid.value)   # VM_OPERATION|READ|WRITE|QUERY
    if not proc:
        raise OSError(f"OpenProcess failed ({ctypes.get_last_error()})")
    buttons = []
    try:
        remote = k.VirtualAllocEx(proc, None, size, 0x3000, 0x04)               # MEM_COMMIT|RESERVE, RW
        if not remote:
            raise OSError(f"VirtualAllocEx failed ({ctypes.get_last_error()})")
        try:
            buf = ctypes.create_string_buffer(size)
            for i in range(min(count, 200)):
                if not u.SendMessageW(hwnd, TB_GETBUTTON, i, remote):
                    continue
                k.ReadProcessMemory(proc, remote, buf, size, None)
                raw = buf.raw
                bitmap, cmd = struct.unpack_from("<ii", raw, 0)
                state, style = raw[8], raw[9]
                buttons.append({"index": i, "command": cmd, "bitmap": bitmap,
                                "separator": bool(style & TBSTYLE_SEP),
                                "enabled": bool(state & TBSTATE_ENABLED), "checked": bool(state & TBSTATE_CHECKED),
                                "hidden": bool(state & TBSTATE_HIDDEN)})
        finally:
            k.VirtualFreeEx(proc, remote, 0, 0x8000)                             # MEM_RELEASE
    finally:
        k.CloseHandle(proc)
    return {"hwnd": hwnd, "count": count, "process_32bit": is32, "buttons": buttons}


def toolbar_press(hwnd: int, index: int | None = None, command: int | None = None) -> dict[str, Any]:
    info = toolbar_buttons(hwnd)
    if (index is None) == (command is None):
        raise ValueError("Supply exactly one of index or command")
    btn = next((b for b in info["buttons"] if (b["index"] == index if index is not None else b["command"] == command)),
               None)
    if btn is None:
        raise LookupError(f"No toolbar button with {'index ' + str(index) if index is not None else 'command ' + str(command)}")
    if btn["separator"] or btn["hidden"] or not btn["enabled"]:
        raise RuntimeError(f"Refusing to press a separator, hidden or disabled button: {btn}")
    u = _user32()
    owner = u.GetParent(hwnd)
    if not u.PostMessageW(owner, WM_COMMAND, btn["command"] & 0xFFFF, hwnd):
        raise OSError("PostMessage WM_COMMAND failed")
    return {"ok": True, "action": "toolbar-press", "button": btn, "owner": owner}


def menu_tree(hwnd: int, max_items: int = 400) -> dict[str, Any]:
    """The window's menu bar (GetMenu), as a tree of {text, id, enabled, items}."""
    import ctypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.GetMenu.restype = ctypes.c_void_p
    u.GetSubMenu.restype = ctypes.c_void_p
    u.GetSubMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.GetMenuItemCount.argtypes = [ctypes.c_void_p]
    u.GetMenuItemID.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.GetMenuItemID.restype = ctypes.c_uint
    u.GetMenuStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint]
    u.GetMenuState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    u.GetMenuState.restype = ctypes.c_uint
    budget = [max_items]

    def walk(h, depth):
        out = []
        n = u.GetMenuItemCount(h)
        for i in range(max(0, n)):
            if budget[0] <= 0:
                break
            budget[0] -= 1
            buf = ctypes.create_unicode_buffer(256)
            u.GetMenuStringW(h, i, buf, 256, 0x400)                 # MF_BYPOSITION
            state = u.GetMenuState(h, i, 0x400)
            sub = u.GetSubMenu(h, i)
            item = {"text": buf.value, "id": None if sub else u.GetMenuItemID(h, i),
                    "enabled": not (state & 0x3), "separator": bool(state & 0x800)}
            if sub and depth < 4:
                item["items"] = walk(sub, depth + 1)
            out.append(item)
        return out

    m = u.GetMenu(hwnd)
    return {"hwnd": hwnd, "has_menu": bool(m), "items": walk(m, 0) if m else []}


def menu_command(hwnd: int, command: int) -> dict[str, Any]:
    """Post WM_COMMAND for a menu item id found with menu_tree (no mouse, no focus needed)."""
    u = _user32()
    if not u.PostMessageW(hwnd, WM_COMMAND, command & 0xFFFF, 0):
        raise OSError("PostMessage WM_COMMAND failed")
    return {"ok": True, "action": "menu-command", "command": command}
