"""Host the redesigned workspace in a native Windows window."""

import os

import webview
from webview.menu import Menu, MenuAction

from app_paths import FROZEN


def run_workspace(workspace_url, show_desktop_controls):
    local_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    profile = os.path.join(local_data, "Pianissimo", "WebView" if FROZEN else "WebView-source")
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["ALLOW_FILE_URLS"] = False

    window = webview.create_window(
        "Pianissimo",
        url=workspace_url,
        width=1280,
        height=860,
        min_size=(640, 460),
        background_color="#111211",
        text_select=True,
    )
    window.events.initialized += lambda renderer: renderer == "edgechromium"
    tools = Menu("&Tools", [MenuAction("Desktop controls", show_desktop_controls)])
    webview.start(gui="edgechromium", private_mode=False, storage_path=profile, menu=[tools])
    if window.gui.renderer != "edgechromium":
        raise RuntimeError("Pianissimo needs the Microsoft Edge WebView2 Runtime to open its desktop workspace.")
