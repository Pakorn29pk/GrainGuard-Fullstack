#!/usr/bin/env python3
"""Windowed GrainGuard client for the local Pi dashboard."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2


APP_ID = "org.grainguard.Desktop"
DASHBOARD = "http://127.0.0.1:8080/"


class DashboardWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="GrainGuard")
        self.set_default_size(1360, 850)
        self.set_icon_name("grainguard")
        self.is_fullscreen = False

        header = Gtk.HeaderBar(title="GrainGuard", show_close_button=True)
        header.set_decoration_layout(":minimize,maximize,close")
        header.pack_end(self.icon_button("view-fullscreen-symbolic", "เต็มจอ (F11)", self.toggle_fullscreen))
        self.set_titlebar(header)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.fullscreen_controls = Gtk.Box()
        self.fullscreen_controls.set_no_show_all(True)
        self.fullscreen_controls.pack_end(
            self.icon_button("view-restore-symbolic", "ออกจากเต็มจอ (Esc)", self.exit_fullscreen),
            False, False, 4,
        )
        layout.pack_start(self.fullscreen_controls, False, False, 0)
        self.pages = Gtk.Stack()
        layout.pack_start(self.pages, True, True, 0)
        self.add(layout)

        offline = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        offline.set_halign(Gtk.Align.CENTER)
        offline.set_valign(Gtk.Align.CENTER)
        offline.pack_start(Gtk.Label(label="เชื่อมต่อ GrainGuard ไม่ได้"), False, False, 0)
        retry = Gtk.Button(label="ลองใหม่")
        retry.connect("clicked", lambda *_: self.browser.load_uri(DASHBOARD))
        offline.pack_start(retry, False, False, 0)
        self.pages.add_named(offline, "offline")

        data = Path(GLib.get_user_data_dir()) / "grainguard"
        cache = Path(GLib.get_user_cache_dir()) / "grainguard"
        data.mkdir(mode=0o700, parents=True, exist_ok=True)
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        manager = WebKit2.WebsiteDataManager(base_data_directory=str(data), base_cache_directory=str(cache))
        context = WebKit2.WebContext.new_with_website_data_manager(manager)
        context.get_cookie_manager().set_persistent_storage(
            str(data / "cookies.sqlite"), WebKit2.CookiePersistentStorage.SQLITE
        )
        self.browser = WebKit2.WebView.new_with_context(context)
        self.browser.get_settings().set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        self.browser.connect("decide-policy", self.on_navigation)
        self.browser.connect("load-failed", self.on_load_failed)
        self.browser.connect("load-changed", self.on_load_changed)
        self.browser.connect("web-process-terminated", lambda *_: self.show_offline())
        self.pages.add_named(self.browser, "dashboard")
        self.pages.set_visible_child_name("dashboard")
        self.connect("window-state-event", self.on_window_state)
        self.connect("key-press-event", self.on_key_press)
        self.show_all()
        self.browser.load_uri(DASHBOARD)

    @staticmethod
    def icon_button(icon, label, callback):
        button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
        button.set_tooltip_text(label)
        button.get_accessible().set_name(label)
        button.connect("clicked", callback)
        return button

    def toggle_fullscreen(self, *_):
        if self.is_fullscreen:
            self.unfullscreen()
        else:
            self.fullscreen()

    def exit_fullscreen(self, *_):
        self.unfullscreen()

    def on_window_state(self, _window, event):
        self.is_fullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
        self.fullscreen_controls.set_visible(self.is_fullscreen)
        return False

    def on_key_press(self, _window, event):
        if event.keyval == Gdk.KEY_F5 or (
            event.keyval in (Gdk.KEY_r, Gdk.KEY_R) and event.state & Gdk.ModifierType.CONTROL_MASK
        ):
            self.browser.reload()
            return True
        if event.keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        if event.keyval == Gdk.KEY_Escape and self.is_fullscreen:
            self.exit_fullscreen()
            return True
        return False

    def show_offline(self):
        self.pages.set_visible_child_name("offline")

    def on_load_failed(self, *_):
        self.show_offline()
        return True

    def on_load_changed(self, _view, event):
        if event == WebKit2.LoadEvent.STARTED:
            self.pages.set_visible_child_name("dashboard")

    @staticmethod
    def on_navigation(_view, decision, kind):
        if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            decision.ignore()
            return True
        if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            url = urlsplit(decision.get_navigation_action().get_request().get_uri())
            if url.scheme != "http" or url.netloc != "127.0.0.1:8080":
                decision.ignore()
                return True
        return False


class GrainGuard(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        window = self.get_active_window() or DashboardWindow(self)
        window.present()


if __name__ == "__main__":
    os.umask(0o077)
    GLib.set_prgname("grainguard")
    raise SystemExit(GrainGuard().run())
