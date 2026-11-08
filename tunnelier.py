#!/usr/bin/env python3
"""Tunnelier – client graphique (GTK4 / libadwaita) pour les configurations CyberGhost.

Inspiré de l'app Android : gros bouton de connexion, carte du serveur choisi,
liste des pays avec drapeaux, favoris, IP publique et durée de connexion.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

OFF, CONNECTING, ON, DISCONNECTING = "off", "connecting", "on", "disconnecting"

CSS = """
.power-button {
  min-width: 168px; min-height: 168px; padding: 0;
  border-radius: 9999px;
  transition: background 250ms ease, box-shadow 250ms ease, color 250ms ease;
}
.power-button.state-off {
  background: alpha(currentColor, 0.08);
  box-shadow: 0 6px 22px alpha(black, 0.15);
}
.power-button.state-off:hover { background: alpha(currentColor, 0.14); }
.power-button.state-busy {
  background: #f6d32d; color: #241f31;
  animation: tnl-pulse 1.4s ease-in-out infinite;
}
.power-button.state-on {
  background: #2ec27e; color: white;
  box-shadow: 0 0 0 10px alpha(#2ec27e, 0.20), 0 8px 28px alpha(#2ec27e, 0.45);
}
.power-button.state-on:hover { background: #33d17a; }
@keyframes tnl-pulse {
  0%   { box-shadow: 0 0 0 0 alpha(#f6d32d, 0.60); }
  70%  { box-shadow: 0 0 0 24px alpha(#f6d32d, 0.0); }
  100% { box-shadow: 0 0 0 0 alpha(#f6d32d, 0.0); }
}
.status-off  { color: #e01b24; }
.status-busy { color: #c88800; }
.status-on   { color: #26a269; }
.flag-big { font-size: 34px; }
.flag     { font-size: 24px; }
.server-card { padding: 12px 16px; border-radius: 14px; }
.pill-on {
  background: alpha(#2ec27e, 0.18); color: #26a269;
  border-radius: 999px; padding: 2px 10px; font-weight: bold; font-size: 0.85em;
}
"""

HELP_TEXT = (
    "1. Connectez-vous à votre compte CyberGhost sur le site web.\n"
    "2. Dans la partie configuration manuelle des appareils, créez un appareil "
    "OpenVPN (ou WireGuard), choisissez le pays et le protocole (UDP conseillé).\n"
    "3. Téléchargez l'archive .zip (ou le fichier .conf) et notez le nom "
    "d'utilisateur et le mot de passe générés pour cet appareil — ce ne sont "
    "pas les identifiants de votre compte.\n"
    "4. Importez le fichier ici (bouton +, Ctrl+I ou glisser-déposer).\n\n"
    "Une seule configuration OpenVPN suffit : Tunnelier propose ensuite "
    "automatiquement tous les pays CyberGhost avec les mêmes identifiants."
)


def run_async(fn, *args, on_done=None, on_error=None):
    """Exécute fn dans un thread, puis rappelle l'interface dans la boucle GTK."""
    def worker():
        try:
            result = fn(*args)
        except Exception as exc:  # noqa: BLE001
            if on_error:
                GLib.idle_add(on_error, exc)
            return
        if on_done:
            GLib.idle_add(on_done, result)
    threading.Thread(target=worker, daemon=True).start()


class ServerRow(Adw.ActionRow):
    """Ligne de la liste des serveurs ; la sous-classe garde l'attribut profile."""
    def __init__(self, profile: core.Profile | None = None, code: str | None = None):
        super().__init__()
        self.profile = profile
        self.code = profile.country if profile else code

    @property
    def is_favorite(self) -> bool:
        return bool(self.profile and self.profile.favorite)

    @property
    def sort_name(self) -> str:
        return core._fold(self.profile.name if self.profile else core.country_name(self.code))


class CredentialsDialog(Adw.Dialog):
    """Saisie / modification des identifiants OpenVPN d'un serveur."""
    def __init__(self, window: "MainWindow", profile: core.Profile, then_connect: bool = False):
        super().__init__(title="Identifiants OpenVPN", content_width=420)
        self.window, self.profile, self.then_connect = window, profile, then_connect

        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Annuler")
        cancel.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel)
        self.save_btn = Gtk.Button(label="Se connecter" if then_connect else "Enregistrer",
                                   sensitive=False)
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._on_save)
        header.pack_end(self.save_btn)
        self.spinner = Adw.Spinner(visible=False)
        header.pack_end(self.spinner)

        group = Adw.PreferencesGroup(
            title=f"{profile.flag}  {profile.name}",
            description="Nom d'utilisateur et mot de passe générés par CyberGhost pour "
                        "cette configuration manuelle (« View Configuration »), "
                        "pas ceux de votre compte.")
        self.user_row = Adw.EntryRow(title="Nom d'utilisateur")
        self.user_row.set_text(window.store.settings.get("last_username", ""))
        self.pass_row = Adw.PasswordEntryRow(title="Mot de passe")
        for row in (self.user_row, self.pass_row):
            row.connect("changed", self._validate)
            group.add(row)
        self.pass_row.connect("entry-activated", lambda *_: self.save_btn.get_sensitive() and self._on_save())
        page = Adw.PreferencesPage()
        page.add(group)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(page)
        self.set_child(view)

    def _validate(self, *_):
        self.save_btn.set_sensitive(bool(self.user_row.get_text().strip() and self.pass_row.get_text()))

    def _on_save(self, *_):
        user, password = self.user_row.get_text().strip(), self.pass_row.get_text()
        self.save_btn.set_sensitive(False)
        self.spinner.set_visible(True)

        def done(_):
            self.window.store.settings["last_username"] = user
            self.profile.username = user
            self.window.store.save()
            self.close()
            self.window.refresh_catalog()
            self.window.on_profiles_changed()
            if self.then_connect:
                self.window.connect_to(self.profile)
            else:
                self.window.toast("Identifiants enregistrés")

        def failed(exc):
            self.spinner.set_visible(False)
            self._validate()
            self.window.alert("Enregistrement impossible", str(exc))

        run_async(self.window.nm.set_credentials, self.profile.id, self.profile.nm_uuid, user, password,
                  on_done=done, on_error=failed)


# --------------------------------------------------------------------------- #
# Dialogue d'import
# --------------------------------------------------------------------------- #
class ImportDialog(Adw.Dialog):
    def __init__(self, window: "MainWindow", path: str | None = None):
        super().__init__(title="Importer un serveur", content_width=440)
        self.window = window
        self.path: str | None = None
        self.info: core.ConfigInfo | None = None

        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Annuler")
        cancel.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel)
        self.import_btn = Gtk.Button(label="Importer", sensitive=False)
        self.import_btn.add_css_class("suggested-action")
        self.import_btn.connect("clicked", self._on_import)
        header.pack_end(self.import_btn)
        self.spinner = Adw.Spinner(visible=False)
        header.pack_end(self.spinner)

        page = Adw.PreferencesPage()

        g_file = Adw.PreferencesGroup(
            title="Fichier",
            description="Archive .zip ou fichier .ovpn téléchargé depuis votre compte CyberGhost, "
                        "ou fichier .conf WireGuard.")
        self.file_row = Adw.ActionRow(title="Aucun fichier choisi", subtitle="Cliquez pour parcourir")
        self.file_row.set_activatable(True)
        self.file_row.add_prefix(Gtk.Image(icon_name="document-open-symbolic"))
        self.file_row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        self.file_row.connect("activated", self._choose_file)
        g_file.add(self.file_row)
        page.add(g_file)

        g_srv = Adw.PreferencesGroup(title="Serveur")
        self.name_row = Adw.EntryRow(title="Nom affiché")
        self.name_row.connect("changed", lambda *_: self._validate())
        self.country_row = Adw.EntryRow(title="Code pays (ex. FR, DE, US)")
        self.country_row.connect("changed", self._on_country_changed)
        self.flag_label = Gtk.Label(label="🌐")
        self.flag_label.add_css_class("flag")
        self.country_row.add_suffix(self.flag_label)
        self.proto_row = Adw.ActionRow(title="Protocole", subtitle="—")
        g_srv.add(self.name_row)
        g_srv.add(self.country_row)
        g_srv.add(self.proto_row)
        page.add(g_srv)

        self.g_cred = Adw.PreferencesGroup(
            title="Identifiants OpenVPN",
            description="Ceux générés par CyberGhost pour cet appareil manuel, "
                        "pas l'e-mail et le mot de passe de votre compte.")
        self.user_row = Adw.EntryRow(title="Nom d'utilisateur")
        self.user_row.set_text(window.store.settings.get("last_username", ""))
        self.user_row.connect("changed", lambda *_: self._validate())
        self.pass_row = Adw.PasswordEntryRow(title="Mot de passe")
        self.pass_row.connect("changed", lambda *_: self._validate())
        self.g_cred.add(self.user_row)
        self.g_cred.add(self.pass_row)
        self.g_cred.set_visible(False)
        page.add(self.g_cred)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(page)
        self.set_child(view)

        if path:
            self._load(path)

    # -- fichier --------------------------------------------------------- #
    def _choose_file(self, *_):
        dialog = Gtk.FileDialog(title="Choisir une configuration VPN")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter(name="Configurations VPN (.zip, .ovpn, .conf)")
        for pattern in ("*.zip", "*.ovpn", "*.conf", "*.ZIP", "*.OVPN", "*.CONF"):
            f.add_pattern(pattern)
        filters.append(f)
        dialog.set_filters(filters)
        dialog.set_default_filter(f)

        def done(dlg, result):
            try:
                gfile = dlg.open_finish(result)
            except GLib.Error:
                return
            if gfile and gfile.get_path():
                self._load(gfile.get_path())

        dialog.open(self.window, None, done)

    def _load(self, path: str):
        try:
            info = core.inspect_source(path)
        except core.ConfigError as exc:
            self.window.alert("Fichier non reconnu", str(exc))
            return
        self.path, self.info = path, info
        self.file_row.set_title(Path(path).name)
        self.file_row.set_subtitle(info.host or "Serveur non indiqué")
        self.proto_row.set_subtitle(f"{info.protocol_label}" + (f" · port {info.port}" if info.port else ""))
        if info.country:
            self.country_row.set_text(info.country)
        if not self.name_row.get_text().strip():
            self.name_row.set_text(core.country_name(info.country) if info.country else Path(path).stem)
        self.g_cred.set_visible(info.protocol == "openvpn")
        self._validate()

    def _on_country_changed(self, row):
        code = core.normalize_code(row.get_text())
        self.flag_label.set_label(core.flag(code))
        self._validate()

    def _validate(self):
        ok = bool(self.info and self.name_row.get_text().strip())
        if ok and self.info.protocol == "openvpn":
            ok = bool(self.user_row.get_text().strip() and self.pass_row.get_text())
        self.import_btn.set_sensitive(ok)

    # -- import ---------------------------------------------------------- #
    def _on_import(self, *_):
        name = self.name_row.get_text().strip()
        country = core.normalize_code(self.country_row.get_text())
        user = self.user_row.get_text().strip()
        password = self.pass_row.get_text()
        self.import_btn.set_sensitive(False)
        self.spinner.set_visible(True)

        def done(profile: core.Profile):
            self.spinner.set_visible(False)
            if user:
                self.window.store.settings["last_username"] = user
            self.window.store.add(profile)
            self.window.on_profiles_changed()
            self.window.refresh_catalog()
            self.window.toast(f"{profile.flag}  {profile.name} ajouté")
            self.close()

        def failed(exc: Exception):
            self.spinner.set_visible(False)
            self._validate()
            self.window.alert("Import impossible", str(exc))

        run_async(self.window.nm.import_profile, self.path, name, country, user, password,
                  on_done=done, on_error=failed)


# --------------------------------------------------------------------------- #
# Fenêtre principale
# --------------------------------------------------------------------------- #
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: "TunnelierApp"):
        super().__init__(application=app, title=core.APP_NAME,
                         default_width=440, default_height=780)
        self.app = app
        self.store: core.Store = app.store
        self.nm: core.NetworkManager = app.nm

        self.state = OFF
        self.active: core.Profile | None = None
        self.connected_since: float | None = None
        self.busy = False
        self._preparing: set[str] = set()
        self._scanning = False
        self._polling = False
        self._first_poll = True

        self._build_ui()
        self.on_profiles_changed()
        self._apply_state(OFF)
        self.refresh_ip()
        self.refresh_catalog()

        GLib.timeout_add_seconds(2, self._poll)
        GLib.timeout_add_seconds(1, self._tick)
        self._poll()

    # ================================================================== UI
    def _build_ui(self):
        self.toasts = Adw.ToastOverlay()

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(self._build_home(), "home", "Accueil", "network-vpn-symbolic")
        self.stack.add_titled_with_icon(self._build_servers(), "servers", "Serveurs", "find-location-symbolic")

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE))

        add_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Importer un serveur (Ctrl+I)")
        add_btn.set_action_name("app.import")
        header.pack_start(add_btn)

        menu = Gio.Menu()
        menu.append("Importer un serveur…", "app.import")
        menu.append("Actualiser la liste des pays", "app.refresh_countries")
        menu.append("Obtenir les fichiers CyberGhost", "app.help")
        section = Gio.Menu()
        section.append("Préférences", "app.preferences")
        section.append("À propos de Tunnelier", "app.about")
        menu.append_section(None, section)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                       tooltip_text="Menu principal"))

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        missing = self.nm.missing_components()
        if missing:
            banner = Adw.Banner(
                title=f"Paquet manquant : {', '.join(missing)} — sudo pacman -S {' '.join(missing)}",
                revealed=True)
            view.add_top_bar(banner)
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        # Glisser-déposer d'un fichier de configuration
        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", lambda _t, value, _x, _y: (self.open_import(value.get_path()), True)[1])
        self.add_controller(drop)

    def _build_home(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      margin_top=28, margin_bottom=24, margin_start=16, margin_end=16)

        self.status_title = Gtk.Label()
        self.status_title.add_css_class("title-1")
        self.status_sub = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.status_sub.add_css_class("dim-label")
        box.append(self.status_title)
        box.append(self.status_sub)

        self.power = Gtk.Button(halign=Gtk.Align.CENTER, margin_top=26, margin_bottom=14,
                                tooltip_text="Se connecter / se déconnecter")
        self.power.add_css_class("power-button")
        self.power.set_child(Gtk.Image(icon_name="system-shutdown-symbolic", pixel_size=64))
        self.power.connect("clicked", self._on_power)
        box.append(self.power)

        self.timer = Gtk.Label(label="00:00:00")
        self.timer.add_css_class("title-3")
        self.timer.add_css_class("numeric")
        box.append(self.timer)

        # Carte « serveur choisi », comme sur l'app mobile
        card = Gtk.Button(margin_top=18)
        card.add_css_class("card")
        card.add_css_class("server-card")
        inner = Gtk.Box(spacing=14)
        self.card_flag = Gtk.Label(label="🌐")
        self.card_flag.add_css_class("flag-big")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        self.card_title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.card_title.add_css_class("heading")
        self.card_sub = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.card_sub.add_css_class("dim-label")
        self.card_sub.add_css_class("caption")
        texts.append(self.card_title)
        texts.append(self.card_sub)
        inner.append(self.card_flag)
        inner.append(texts)
        inner.append(Gtk.Image(icon_name="go-next-symbolic"))
        card.set_child(inner)
        card.connect("clicked", self._on_card)
        box.append(card)

        ip_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, margin_top=6)
        ip_list.add_css_class("boxed-list")
        self.ip_row = Adw.ActionRow(title="Adresse IP publique", subtitle="…")
        self.ip_row.add_css_class("property")
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="Actualiser")
        refresh.add_css_class("flat")
        refresh.connect("clicked", lambda *_: self.refresh_ip(force=True))
        self.ip_row.add_suffix(refresh)
        self.loc_row = Adw.ActionRow(title="Localisation apparente", subtitle="…")
        self.loc_row.add_css_class("property")
        ip_list.append(self.ip_row)
        ip_list.append(self.loc_row)
        self.ip_list = ip_list
        box.append(ip_list)

        clamp = Adw.Clamp(maximum_size=460, child=box)
        return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _build_servers(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        bar = Gtk.Box(spacing=8, margin_top=12, margin_bottom=6, margin_start=16, margin_end=16)
        self.search = Gtk.SearchEntry(placeholder_text="Rechercher un pays…", hexpand=True)
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        self.fav_toggle = Gtk.ToggleButton(icon_name="starred-symbolic", tooltip_text="Favoris uniquement")
        self.fav_toggle.connect("toggled", lambda *_: self.listbox.invalidate_filter())
        bar.append(self.search)
        bar.append(self.fav_toggle)
        bar_clamp = Adw.Clamp(maximum_size=600, child=bar)
        outer.append(bar_clamp)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                   margin_top=6, margin_bottom=18, margin_start=16, margin_end=16,
                                   valign=Gtk.Align.START)
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_filter_func(self._filter_row)
        self.listbox.set_sort_func(self._sort_rows)
        self.listbox.set_header_func(self._header_row)
        self.listbox.set_placeholder(Adw.StatusPage(
            title="Aucun résultat", icon_name="edit-find-symbolic"))
        list_scroll = Gtk.ScrolledWindow(
            child=Adw.Clamp(maximum_size=600, child=self.listbox),
            vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)

        import_btn = Gtk.Button(label="Importer une configuration", halign=Gtk.Align.CENTER)
        import_btn.add_css_class("pill")
        import_btn.add_css_class("suggested-action")
        import_btn.set_action_name("app.import")
        help_btn = Gtk.Button(label="Comment obtenir les fichiers ?", halign=Gtk.Align.CENTER)
        help_btn.add_css_class("flat")
        help_btn.set_action_name("app.help")
        btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        btns.append(import_btn)
        btns.append(help_btn)
        empty = Adw.StatusPage(
            icon_name="network-vpn-symbolic", title="Aucun serveur",
            description="Importez une configuration OpenVPN générée depuis votre compte "
                        "CyberGhost : tous les autres pays seront ensuite proposés "
                        "automatiquement.\nVous pouvez aussi glisser-déposer le fichier ici.",
            child=btns)

        self.servers_stack = Gtk.Stack()
        self.servers_stack.add_named(empty, "empty")
        self.servers_stack.add_named(list_scroll, "list")
        self.servers_bar = bar_clamp
        outer.append(self.servers_stack)
        return outer

    # ========================================================= liste serveurs
    def on_profiles_changed(self):
        self.listbox.remove_all()
        for profile in self.store.profiles:
            self.listbox.append(self._make_row(profile))
        if self.store.template():
            covered = {p.country for p in self.store.profiles}
            for code in self.store.catalog():
                if code not in covered:
                    self.listbox.append(self._make_virtual_row(code))
        has = bool(self.store.profiles)
        self.servers_stack.set_visible_child_name("list" if has else "empty")
        self.servers_bar.set_visible(has)
        self._update_card()

    def _make_row(self, profile: core.Profile) -> ServerRow:
        row = ServerRow(profile)
        row.set_title(GLib.markup_escape_text(profile.name))
        row.set_subtitle(GLib.markup_escape_text(
            f"{profile.protocol_label} · {profile.host or 'hôte inconnu'}"))
        row.set_activatable(True)
        flag_lbl = Gtk.Label(label=profile.flag)
        flag_lbl.add_css_class("flag")
        row.add_prefix(flag_lbl)

        if self.active and self.active.id == profile.id and self.state in (ON, CONNECTING):
            pill = Gtk.Label(label="Connecté" if self.state == ON else "Connexion…",
                             valign=Gtk.Align.CENTER)
            pill.add_css_class("pill-on")
            row.add_suffix(pill)

        star = Gtk.ToggleButton(icon_name="starred-symbolic" if profile.favorite else "non-starred-symbolic",
                                active=profile.favorite, valign=Gtk.Align.CENTER,
                                tooltip_text="Favori")
        star.add_css_class("flat")
        star.connect("toggled", self._on_star, profile)
        row.add_suffix(star)

        if profile.protocol == "openvpn":
            key = Gtk.Button(icon_name="dialog-password-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="Identifiants")
            key.add_css_class("flat")
            key.connect("clicked", lambda *_: CredentialsDialog(self, profile).present(self))
            row.add_suffix(key)

        delete = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text="Supprimer")
        delete.add_css_class("flat")
        delete.connect("clicked", lambda *_: self._confirm_delete(profile))
        row.add_suffix(delete)

        row.connect("activated", lambda *_: self.connect_to(profile))
        return row

    def _make_virtual_row(self, code: str) -> ServerRow:
        """Pays CyberGhost disponible, pas encore préparé : créé au premier clic."""
        row = ServerRow(code=code)
        row.set_title(GLib.markup_escape_text(core.country_name(code)))
        row.set_subtitle("OpenVPN · disponible")
        row.set_activatable(True)
        flag_lbl = Gtk.Label(label=core.flag(code))
        flag_lbl.add_css_class("flag")
        row.add_prefix(flag_lbl)
        if code in self._preparing:
            row.add_suffix(Adw.Spinner(valign=Gtk.Align.CENTER))
        star = Gtk.Button(icon_name="non-starred-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text="Ajouter aux favoris")
        star.add_css_class("flat")
        star.connect("clicked", lambda *_: self.prepare_country(code, favorite=True))
        row.add_suffix(star)
        row.connect("activated", lambda *_: self.prepare_country(code, connect=True))
        return row

    def _filter_row(self, row) -> bool:
        if not isinstance(row, ServerRow):
            return True
        if self.fav_toggle.get_active() and not row.is_favorite:
            return False
        query = core._fold(self.search.get_text())
        if not query:
            return True
        p = row.profile
        hay = core._fold(f"{p.name if p else ''} {core.country_name(row.code)} {row.code or ''} {p.host if p else ''}")
        return query in hay

    @staticmethod
    def _sort_rows(a, b) -> int:
        if not isinstance(a, ServerRow) or not isinstance(b, ServerRow):
            return 0
        ka = (not a.is_favorite, a.sort_name)
        kb = (not b.is_favorite, b.sort_name)
        return (ka > kb) - (ka < kb)

    def _header_row(self, row, before):
        if not isinstance(row, ServerRow):
            return
        has_favs = any(p.favorite for p in self.store.profiles)
        first = before is None or not isinstance(before, ServerRow)
        if has_favs and (first or before.is_favorite != row.is_favorite):
            label = Gtk.Label(label="Favoris" if row.is_favorite else "Tous les pays", xalign=0,
                              margin_top=12, margin_bottom=6, margin_start=12)
            label.add_css_class("heading")
            row.set_header(label)
        else:
            row.set_header(None)

    # ------------------------------------------------------- catalogue pays
    def refresh_catalog(self, force: bool = False):
        template = self.store.template()
        if not template:
            return
        prefix = core.cg_host_parts(template.host)[0]
        if not force and self.store.catalog_is_fresh(prefix):
            return
        if self._scanning:
            return
        self._scanning = True
        self.toast("Recherche des pays CyberGhost disponibles…")

        def done(countries):
            self._scanning = False
            if countries:
                self.store.set_catalog(prefix, countries)
                self.on_profiles_changed()
                self.toast(f"{len(countries)} pays disponibles")
            else:
                self.toast("Aucun pays trouvé (pas de connexion Internet ?)")

        def failed(exc):
            self._scanning = False
            self.toast(f"Recherche des pays impossible : {exc}")

        run_async(core.scan_cyberghost_countries, prefix, on_done=done, on_error=failed)

    def prepare_country(self, code: str, connect: bool = False, favorite: bool = False):
        existing = self.store.profile_for_country(code)
        if existing:
            if favorite:
                existing.favorite = True
                self.store.save()
                self.on_profiles_changed()
            if connect:
                self.connect_to(existing)
            return
        template = self.store.template()
        label = self.store.catalog().get(code)
        if not template or not label or code in self._preparing or (connect and self.busy):
            return
        self._preparing.add(code)
        self.on_profiles_changed()

        def done(profile: core.Profile):
            self._preparing.discard(code)
            profile.favorite = favorite
            self.store.add(profile)
            self.on_profiles_changed()
            if connect:
                self.connect_to(profile)

        def failed(exc):
            self._preparing.discard(code)
            self.on_profiles_changed()
            self.alert(f"Impossible de préparer {core.country_name(code)}", str(exc))

        run_async(self.nm.clone_for_country, template, code, label, on_done=done, on_error=failed)

    def _on_star(self, button, profile):
        profile.favorite = button.get_active()
        button.set_icon_name("starred-symbolic" if profile.favorite else "non-starred-symbolic")
        self.store.save()
        self.listbox.invalidate_sort()
        self.listbox.invalidate_filter()

    def _confirm_delete(self, profile):
        dialog = Adw.AlertDialog(
            heading=f"Supprimer « {profile.name} » ?",
            body="La connexion sera retirée de NetworkManager. Vous pourrez la réimporter plus tard.")
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("delete", "Supprimer")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        def on_response(_d, response):
            if response != "delete":
                return

            def job():
                if self.active and self.active.id == profile.id:
                    try:
                        self.nm.disconnect(profile.nm_uuid)
                    except core.NMError:
                        pass
                self.nm.delete(profile)

            def done(_):
                if self.active and self.active.id == profile.id:
                    self.active = None
                    self._apply_state(OFF)
                self.store.remove(profile)
                self.on_profiles_changed()
                self.toast(f"{profile.name} supprimé")

            run_async(job, on_done=done, on_error=lambda e: self.alert("Suppression impossible", str(e)))

        dialog.connect("response", on_response)
        dialog.present(self)

    # ============================================================ connexion
    def _on_power(self, *_):
        if self.busy:
            return
        if self.state in (ON, CONNECTING) and self.active:
            self.disconnect()
            return
        profile = self.store.preferred()
        if not profile:
            self.open_import()
            return
        self.connect_to(profile)

    def _on_card(self, *_):
        if self.store.profiles:
            self.stack.set_visible_child_name("servers")
        else:
            self.open_import()

    def connect_to(self, profile: core.Profile):
        if self.busy:
            return
        if self.state == ON and self.active and self.active.id == profile.id:
            self.stack.set_visible_child_name("home")
            return
        if profile.protocol == "openvpn" and not self.nm.has_credentials(profile.id):
            CredentialsDialog(self, profile, then_connect=True).present(self)
            return
        previous = self.active if self.state in (ON, CONNECTING) else None
        self.busy = True
        self.active = profile
        self.store.settings["last_server"] = profile.id
        self.store.save()
        self.stack.set_visible_child_name("home")
        self._apply_state(CONNECTING)

        def job():
            if previous and previous.nm_uuid != profile.nm_uuid:
                try:
                    self.nm.disconnect(previous.nm_uuid)
                except core.NMError:
                    pass
            self.nm.connect(profile.nm_uuid, profile.id)

        def done(_):
            self.busy = False
            self.connected_since = time.monotonic()
            self._apply_state(ON)
            self.notify("VPN connecté", f"{profile.flag} {profile.name} — votre trafic est protégé.")
            GLib.timeout_add_seconds(2, lambda: self.refresh_ip(force=True) and False)

        def failed(exc):
            self.busy = False
            self.active = None
            self._apply_state(OFF)
            self.alert("Échec de la connexion",
                       f"{exc}\n\nVérifiez les identifiants de l'appareil manuel CyberGhost "
                       "et que le paquet networkmanager-openvpn est installé.")

        run_async(job, on_done=done, on_error=failed)

    def disconnect(self):
        if not self.active:
            return
        profile = self.active
        self.busy = True
        self._apply_state(DISCONNECTING)

        def done(_):
            self.busy = False
            self.active = None
            self.connected_since = None
            self._apply_state(OFF)
            self.notify("VPN déconnecté", "Votre connexion n'est plus protégée.")
            GLib.timeout_add_seconds(1, lambda: self.refresh_ip(force=True) and False)

        def failed(exc):
            self.busy = False
            self.toast(f"Déconnexion impossible : {exc}")
            self._poll()

        run_async(self.nm.disconnect, profile.nm_uuid, on_done=done, on_error=failed)

    # ================================================================ état
    def _poll(self):
        if self.busy or self._polling:
            return True
        self._polling = True

        def done(states):
            self._polling = False
            if not self.busy:
                self._sync_from_nm(states)

        def failed(_exc):
            self._polling = False

        run_async(self.nm.active_states, on_done=done, on_error=failed)
        return True

    def _sync_from_nm(self, states: dict[str, str]):
        found = None
        for uid, st in states.items():
            profile = self.store.by_nm_uuid(uid)
            if profile:
                found = (profile, st)
                break

        was_on = self.state == ON
        if found:
            profile, st = found
            self.active = profile
            if st == "activated":
                if not was_on:
                    self.connected_since = self.connected_since or time.monotonic()
                self._apply_state(ON)
            elif st == "activating":
                self._apply_state(CONNECTING)
            else:
                self._apply_state(DISCONNECTING)
        else:
            if was_on:
                self.notify("VPN déconnecté", "La connexion VPN s'est interrompue.")
                self.refresh_ip(force=True)
            self.active = None
            self.connected_since = None
            self._apply_state(OFF)

        if self._first_poll:
            self._first_poll = False
            if not found and self.store.settings.get("auto_connect"):
                profile = self.store.preferred()
                if profile:
                    self.connect_to(profile)

    def _apply_state(self, state: str):
        changed = state != self.state
        self.state = state
        for cls in ("state-off", "state-busy", "state-on"):
            self.power.remove_css_class(cls)
        for cls in ("status-off", "status-busy", "status-on"):
            self.status_title.remove_css_class(cls)

        name = self.active.name if self.active else ""
        if state == ON:
            self.power.add_css_class("state-on")
            self.status_title.add_css_class("status-on")
            self.status_title.set_label("Protégé")
            self.status_sub.set_label(f"Connecté à {name}")
        elif state in (CONNECTING, DISCONNECTING):
            self.power.add_css_class("state-busy")
            self.status_title.add_css_class("status-busy")
            self.status_title.set_label("Connexion…" if state == CONNECTING else "Déconnexion…")
            self.status_sub.set_label(f"{'Vers' if state == CONNECTING else 'De'} {name}")
        else:
            self.power.add_css_class("state-off")
            self.status_title.add_css_class("status-off")
            self.status_title.set_label("Non protégé")
            self.status_sub.set_label("Votre connexion n'est pas chiffrée")
            self.timer.set_label("00:00:00")

        self.timer.set_opacity(1.0 if state == ON else 0.35)
        self._update_card()
        if changed:
            self.on_profiles_changed()

    def _update_card(self):
        profile = self.active if self.state != OFF and self.active else self.store.preferred()
        if profile:
            self.card_flag.set_label(profile.flag)
            self.card_title.set_label(profile.name)
            prefix = "Serveur actuel" if self.state != OFF else "Serveur choisi"
            self.card_sub.set_label(f"{prefix} · {profile.protocol_label}")
        else:
            self.card_flag.set_label("🌐")
            self.card_title.set_label("Aucun serveur")
            self.card_sub.set_label("Touchez pour importer une configuration")

    def _tick(self):
        if self.state == ON and self.connected_since:
            s = int(time.monotonic() - self.connected_since)
            self.timer.set_label(f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}")
        return True

    # ============================================================== divers
    def refresh_ip(self, force: bool = False):
        enabled = self.store.settings.get("check_ip", True)
        self.ip_list.set_visible(enabled)
        if not enabled:
            return False
        self.ip_row.set_subtitle("Vérification…")

        def done(data):
            self.ip_row.set_subtitle(data.get("ip") or "Inconnue")
            parts = [p for p in (data.get("city"), core.country_name(data.get("country")) if data.get("country") else "") if p]
            loc = ", ".join(parts) or "Inconnue"
            self.loc_row.set_subtitle(f"{core.flag(data.get('country'))}  {loc}" if data.get("country") else loc)

        def failed(_):
            self.ip_row.set_subtitle("Indisponible (hors ligne ?)")
            self.loc_row.set_subtitle("—")

        run_async(core.public_ip, on_done=done, on_error=failed)
        return True

    def open_import(self, path: str | None = None):
        ImportDialog(self, path).present(self)

    def toast(self, text: str):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=3))

    def alert(self, heading: str, body: str):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.present(self)

    def notify(self, title: str, body: str):
        if not self.store.settings.get("notifications", True):
            return
        n = Gio.Notification.new(title)
        n.set_body(body)
        n.set_icon(Gio.ThemedIcon.new("network-vpn-symbolic"))
        self.app.send_notification("vpn-state", n)


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class TunnelierApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=core.APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.store = core.Store.load()
        self.nm = core.NetworkManager()
        self.window: MainWindow | None = None
        GLib.set_application_name(core.APP_NAME)

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        try:
            provider.load_from_string(CSS)
        except AttributeError:  # GTK < 4.12
            provider.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        for name, cb, accels in (
            ("import", lambda *_: self.window.open_import(), ["<Ctrl>i"]),
            ("help", self._on_help, ["F1"]),
            ("refresh_countries", lambda *_: self.window.refresh_catalog(force=True), ["F5"]),
            ("preferences", self._on_prefs, ["<Ctrl>comma"]),
            ("about", self._on_about, []),
            ("quit", lambda *_: self.quit(), ["<Ctrl>q"]),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)

    def do_activate(self):
        if not self.window:
            self.window = MainWindow(self)
        self.window.present()

    def do_open(self, files, _n_files, _hint):
        self.do_activate()
        for f in files:
            if f.get_path():
                self.window.open_import(f.get_path())
                break

    def _on_help(self, *_):
        self.window.alert("Obtenir vos fichiers CyberGhost", HELP_TEXT)

    def _on_prefs(self, *_):
        s = self.store.settings
        dialog = Adw.PreferencesDialog(title="Préférences")
        page = Adw.PreferencesPage(title="Général", icon_name="preferences-system-symbolic")
        group = Adw.PreferencesGroup(title="Comportement")

        def switch(title, subtitle, key, after=None):
            row = Adw.SwitchRow(title=title, subtitle=subtitle, active=bool(s.get(key)))

            def toggled(r, _pspec):
                s[key] = r.get_active()
                self.store.save()
                if after:
                    after()
            row.connect("notify::active", toggled)
            group.add(row)

        switch("Connexion automatique", "Se connecter au dernier serveur au lancement", "auto_connect")
        switch("Notifications", "Prévenir lors des connexions et déconnexions", "notifications")
        switch("Afficher l'IP publique", "Interroge ipinfo.io pour vérifier l'adresse visible",
               "check_ip", lambda: self.window.refresh_ip(force=True))
        page.add(group)

        info = Adw.PreferencesGroup(
            title="Connexions NetworkManager",
            description="Les serveurs importés apparaissent aussi dans les réglages réseau de KDE / GNOME "
                        f"sous le nom « {core.NM_PREFIX} · … ».")
        page.add(info)
        dialog.add(page)
        dialog.present(self.window)

    def _on_about(self, *_):
        about = Adw.AboutDialog(
            application_name=core.APP_NAME, application_icon=core.APP_ID,
            version=core.VERSION, developer_name="Tunnelier",
            comments="Client VPN pour vos configurations CyberGhost (OpenVPN / WireGuard), "
                     "basé sur NetworkManager.\n\nProjet indépendant, non affilié à CyberGhost.",
            license_type=Gtk.License.MIT_X11)
        about.present(self.window)


def main() -> int:
    return TunnelierApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
