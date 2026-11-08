"""Tunnelier – moteur : profils VPN, NetworkManager (nmcli), détection du pays.

Aucune dépendance GTK ici, pour pouvoir tester ce module seul.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import unicodedata
import urllib.request
import uuid as uuidlib
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_ID = "io.github.tunnelier.Tunnelier"
APP_NAME = "Tunnelier"
VERSION = "1.1.0"

_HOME = Path.home()
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", _HOME / ".local/share")) / "tunnelier"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", _HOME / ".config")) / "tunnelier"
PROFILES_DIR = DATA_DIR / "profiles"

NM_PREFIX = "Tunnelier"  # préfixe des connexions créées dans NetworkManager

# --------------------------------------------------------------------------- #
# Pays
# --------------------------------------------------------------------------- #
COUNTRIES = {
    "AD": "Andorre", "AE": "Émirats arabes unis", "AL": "Albanie", "AM": "Arménie",
    "AR": "Argentine", "AT": "Autriche", "AU": "Australie", "BA": "Bosnie-Herzégovine",
    "BD": "Bangladesh", "BE": "Belgique", "BG": "Bulgarie", "BR": "Brésil",
    "BS": "Bahamas", "BY": "Biélorussie", "CA": "Canada", "CH": "Suisse",
    "CL": "Chili", "CN": "Chine", "CO": "Colombie", "CR": "Costa Rica",
    "CY": "Chypre", "CZ": "Tchéquie", "DE": "Allemagne", "DK": "Danemark",
    "DZ": "Algérie", "EE": "Estonie", "EG": "Égypte", "ES": "Espagne",
    "FI": "Finlande", "FR": "France", "GB": "Royaume-Uni", "GE": "Géorgie",
    "GL": "Groenland", "GR": "Grèce", "HK": "Hong Kong", "HR": "Croatie",
    "HU": "Hongrie", "ID": "Indonésie", "IE": "Irlande", "IL": "Israël",
    "IM": "Île de Man", "IN": "Inde", "IR": "Iran", "IS": "Islande",
    "IT": "Italie", "JP": "Japon", "KE": "Kenya", "KH": "Cambodge",
    "KR": "Corée du Sud", "KZ": "Kazakhstan", "LI": "Liechtenstein", "LK": "Sri Lanka",
    "LT": "Lituanie", "LU": "Luxembourg", "LV": "Lettonie", "MA": "Maroc",
    "MC": "Monaco", "MD": "Moldavie", "ME": "Monténégro", "MK": "Macédoine du Nord",
    "MN": "Mongolie", "MO": "Macao", "MT": "Malte", "MX": "Mexique",
    "MY": "Malaisie", "NG": "Nigeria", "NL": "Pays-Bas", "NO": "Norvège",
    "NZ": "Nouvelle-Zélande", "PA": "Panama", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Pologne", "PT": "Portugal", "QA": "Qatar", "RO": "Roumanie",
    "RS": "Serbie", "RU": "Russie", "SA": "Arabie saoudite", "SE": "Suède",
    "SG": "Singapour", "SI": "Slovénie", "SK": "Slovaquie", "TH": "Thaïlande",
    "TR": "Turquie", "TW": "Taïwan", "UA": "Ukraine", "US": "États-Unis",
    "VE": "Venezuela", "VN": "Viêt Nam", "ZA": "Afrique du Sud",
    "AO": "Angola", "AZ": "Azerbaïdjan", "BB": "Barbade", "BH": "Bahreïn",
    "BM": "Bermudes", "BN": "Brunei", "BO": "Bolivie", "BT": "Bhoutan",
    "BZ": "Belize", "DO": "République dominicaine", "EC": "Équateur",
    "GH": "Ghana", "GT": "Guatemala", "HN": "Honduras", "JM": "Jamaïque",
    "JO": "Jordanie", "KW": "Koweït", "KG": "Kirghizistan", "KY": "Îles Caïmans",
    "LA": "Laos", "LB": "Liban", "MM": "Birmanie", "MU": "Maurice", "MZ": "Mozambique",
    "NI": "Nicaragua", "NP": "Népal", "OM": "Oman", "PE": "Pérou", "PR": "Porto Rico",
    "PY": "Paraguay", "SV": "Salvador", "TN": "Tunisie", "TT": "Trinité-et-Tobago",
    "UY": "Uruguay", "UZ": "Ouzbékistan", "TJ": "Tadjikistan", "TM": "Turkménistan",
    "SN": "Sénégal", "CI": "Côte d'Ivoire", "CM": "Cameroun", "ET": "Éthiopie",
    "UG": "Ouganda", "TZ": "Tanzanie", "SY": "Syrie", "IQ": "Irak", "AF": "Afghanistan",
    "VA": "Vatican", "SM": "Saint-Marin", "FO": "Îles Féroé", "JE": "Jersey", "GG": "Guernesey",
}
_ALIASES = {"UK": "GB"}

_EN_NAMES = {
    "france": "FR", "germany": "DE", "netherlands": "NL", "holland": "NL",
    "unitedkingdom": "GB", "england": "GB", "unitedstates": "US", "usa": "US",
    "america": "US", "switzerland": "CH", "spain": "ES", "italy": "IT",
    "belgium": "BE", "canada": "CA", "japan": "JP", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI", "poland": "PL",
    "austria": "AT", "ireland": "IE", "portugal": "PT", "romania": "RO",
    "australia": "AU", "brazil": "BR", "singapore": "SG", "hongkong": "HK",
    "luxembourg": "LU", "czechia": "CZ", "czechrepublic": "CZ", "hungary": "HU",
    "greece": "GR", "turkey": "TR", "israel": "IL", "india": "IN",
    "mexico": "MX", "argentina": "AR", "southafrica": "ZA", "iceland": "IS",
    "ukraine": "UA", "bulgaria": "BG", "croatia": "HR", "serbia": "RS",
    "moldova": "MD", "taiwan": "TW", "korea": "KR", "southkorea": "KR",
    "newzealand": "NZ", "monaco": "MC", "andorra": "AD", "malta": "MT",
}


def _fold(text: str) -> str:
    """Minuscules, sans accents ni séparateurs : « États-Unis » -> « etatsunis »."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", text.lower())


_NAME_TO_CODE = {**_EN_NAMES, **{_fold(n): c for c, n in COUNTRIES.items()}}


def normalize_code(code: str | None) -> str | None:
    if not code:
        return None
    code = code.strip().upper()
    code = _ALIASES.get(code, code)
    return code if len(code) == 2 and code.isalpha() else None


def country_name(code: str | None) -> str:
    code = normalize_code(code)
    if not code:
        return "Emplacement inconnu"
    return COUNTRIES.get(code, code)


def flag(code: str | None) -> str:
    code = normalize_code(code)
    if not code:
        return "🌐"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def detect_country(host: str | None, filename: str | None) -> str | None:
    """Devine le code pays à partir du serveur distant puis du nom de fichier."""
    host = (host or "").lower()
    stem = Path(filename or "").stem

    # 1. Format des serveurs CyberGhost : « 87-1-fr.cg-dialup.net »
    m = re.search(r"(?:^|[-.])([a-z]{2})\.cg-dialup\.net$", host)
    if m and normalize_code(m.group(1)) in COUNTRIES:
        return normalize_code(m.group(1))

    # 2. Nom complet de pays dans le nom de fichier (« France », « United-States »…)
    folded = _fold(stem)
    for name in sorted(_NAME_TO_CODE, key=len, reverse=True):
        if len(name) >= 4 and name in folded:
            return _NAME_TO_CODE[name]

    # 3. Code à 2 lettres dans le premier libellé de l'hôte, puis dans le fichier
    first_label = host.split(".")[0] if host and not re.match(r"^[\d.:\[\]]+$", host) else ""
    for source in (first_label, stem.lower()):
        for token in re.split(r"[^a-z]+", source.lower()):
            code = normalize_code(token)
            if code and code in COUNTRIES:
                return code
    return None


# --------------------------------------------------------------------------- #
# Lecture des fichiers de configuration
# --------------------------------------------------------------------------- #
class ConfigError(Exception):
    pass


@dataclass
class ConfigInfo:
    protocol: str          # "openvpn" ou "wireguard"
    host: str
    port: str
    text: str
    member: str            # nom du fichier (dans l'archive le cas échéant)
    country: str | None

    @property
    def protocol_label(self) -> str:
        return "OpenVPN" if self.protocol == "openvpn" else "WireGuard"


def parse_config_text(text: str, name: str) -> ConfigInfo:
    if re.search(r"^\s*\[Interface\]", text, re.M | re.I):
        m = re.search(r"^\s*Endpoint\s*=\s*(\S+)", text, re.M | re.I)
        host, port = "", ""
        if m:
            ep = m.group(1)
            m6 = re.match(r"^\[(.+)\]:(\d+)$", ep)
            if m6:
                host, port = m6.groups()
            elif ":" in ep:
                host, port = ep.rsplit(":", 1)
            else:
                host = ep
        protocol = "wireguard"
    elif re.search(r"^\s*(client|remote|dev\s+tun)\b", text, re.M):
        m = re.search(r"^\s*remote\s+(\S+)(?:\s+(\d+))?", text, re.M)
        host, port = (m.group(1), m.group(2) or "1194") if m else ("", "")
        protocol = "openvpn"
    else:
        raise ConfigError(f"« {name} » n'est ni une configuration OpenVPN ni WireGuard.")
    return ConfigInfo(protocol, host, port, text, name, detect_country(host, name))


def _pick_member(names: list[str]) -> str:
    candidates = [n for n in names if n.lower().endswith((".ovpn", ".conf")) and not n.endswith("/")]
    if not candidates:
        raise ConfigError("L'archive ne contient aucun fichier .ovpn ou .conf.")
    candidates.sort(key=lambda n: (not n.lower().endswith(".ovpn"), n.count("/"), n))
    return candidates[0]


def inspect_source(path: str | Path) -> ConfigInfo:
    """Analyse un .ovpn, un .conf WireGuard ou une archive .zip CyberGhost."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Fichier introuvable : {path}")
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            member = _pick_member(zf.namelist())
            text = zf.read(member).decode("utf-8", "replace")
        info = parse_config_text(text, Path(member).name)
        if not info.country:
            info.country = detect_country(info.host, path.name)
        return info
    text = path.read_text("utf-8", "replace")
    return parse_config_text(text, path.name)


_OVPN_FILE_DIRECTIVES = ("ca", "cert", "key", "tls-auth", "tls-crypt", "tls-crypt-v2",
                         "pkcs12", "crl-verify", "auth-user-pass", "secret")


def _referenced_files(text: str) -> list[str]:
    files = []
    for directive in _OVPN_FILE_DIRECTIVES:
        for m in re.finditer(rf"^\s*{re.escape(directive)}\s+(\S+)", text, re.M):
            value = m.group(1).strip("\"'")
            if value and value != "[inline]":
                files.append(value)
    return files


# --------------------------------------------------------------------------- #
# Profils enregistrés
# --------------------------------------------------------------------------- #
@dataclass
class Profile:
    id: str
    name: str
    country: str | None
    protocol: str
    host: str
    nm_uuid: str
    favorite: bool = False
    created: float = 0.0
    username: str = ""

    @property
    def protocol_label(self) -> str:
        return "OpenVPN" if self.protocol == "openvpn" else "WireGuard"

    @property
    def flag(self) -> str:
        return flag(self.country)


DEFAULT_SETTINGS = {
    "last_server": None,
    "auto_connect": False,
    "notifications": True,
    "check_ip": True,
    "last_username": "",
}


@dataclass
class Store:
    profiles: list[Profile] = field(default_factory=list)
    settings: dict = field(default_factory=lambda: dict(DEFAULT_SETTINGS))

    @property
    def _profiles_file(self) -> Path:
        return CONFIG_DIR / "profiles.json"

    @property
    def _settings_file(self) -> Path:
        return CONFIG_DIR / "settings.json"

    @classmethod
    def load(cls) -> "Store":
        store = cls()
        try:
            raw = json.loads(store._profiles_file.read_text())
            store.profiles = [Profile(**p) for p in raw]
        except (OSError, ValueError, TypeError):
            pass
        try:
            store.settings.update(json.loads(store._settings_file.read_text()))
        except (OSError, ValueError):
            pass
        return store

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._profiles_file.write_text(json.dumps([asdict(p) for p in self.profiles], indent=2, ensure_ascii=False))
        self._settings_file.write_text(json.dumps(self.settings, indent=2, ensure_ascii=False))

    def get(self, profile_id: str | None) -> Profile | None:
        return next((p for p in self.profiles if p.id == profile_id), None)

    def by_nm_uuid(self, nm_uuid: str) -> Profile | None:
        return next((p for p in self.profiles if p.nm_uuid == nm_uuid), None)

    def add(self, profile: Profile) -> None:
        self.profiles.append(profile)
        self.save()

    def remove(self, profile: Profile) -> None:
        self.profiles = [p for p in self.profiles if p.id != profile.id]
        if self.settings.get("last_server") == profile.id:
            self.settings["last_server"] = None
        self.save()

    def template(self) -> Profile | None:
        """Profil OpenVPN CyberGhost avec identifiants, servant de modèle pour tous les pays."""
        candidates = [p for p in self.profiles
                      if p.protocol == "openvpn" and cg_host_parts(p.host) and has_secret(p.id)]
        last = self.get(self.settings.get("last_server"))
        return last if last in candidates else (candidates[0] if candidates else None)

    def catalog(self) -> dict[str, str]:
        """{code pays: libellé DNS} des pays CyberGhost détectés."""
        cat = self.settings.get("catalog") or {}
        return dict(cat.get("countries") or {})

    def catalog_is_fresh(self, prefix: str, max_age: float = 7 * 86400) -> bool:
        cat = self.settings.get("catalog") or {}
        return (cat.get("prefix") == prefix and bool(cat.get("countries"))
                and time.time() - float(cat.get("ts", 0)) < max_age)

    def set_catalog(self, prefix: str, countries: dict[str, str]) -> None:
        self.settings["catalog"] = {"prefix": prefix, "countries": countries, "ts": time.time()}
        self.save()

    def profile_for_country(self, code: str) -> Profile | None:
        return next((p for p in self.profiles if p.country == code), None)

    def preferred(self) -> Profile | None:
        """Serveur utilisé par le bouton principal : dernier, sinon favori, sinon premier."""
        return (self.get(self.settings.get("last_server"))
                or next((p for p in self.profiles if p.favorite), None)
                or (self.profiles[0] if self.profiles else None))


# --------------------------------------------------------------------------- #
# Catalogue CyberGhost : un même identifiant fonctionne pour tous les pays,
# seul le code pays change dans l'adresse « <groupe>-<pays>.cg-dialup.net ».
# --------------------------------------------------------------------------- #
_CG_HOST_RE = re.compile(r"^(?P<prefix>[a-z0-9-]+)-(?P<cc>[a-z]{2})\.cg-dialup\.net$", re.I)


def cg_host_parts(host: str | None) -> tuple[str, str] | None:
    m = _CG_HOST_RE.match(host or "")
    return (m.group("prefix").lower(), m.group("cc").lower()) if m else None


def cg_host(prefix: str, label: str) -> str:
    return f"{prefix}-{label.lower()}.cg-dialup.net"


def _resolves(host: str) -> bool:
    try:
        return bool(socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP))
    except OSError:
        return False


def scan_cyberghost_countries(prefix: str, workers: int = 32) -> dict[str, str]:
    """Teste par DNS quels pays existent pour ce groupe de serveurs."""
    candidates: list[tuple[str, str]] = []
    for code in COUNTRIES:
        labels = [code.lower()] + (["uk"] if code == "GB" else [])
        candidates += [(code, label) for label in labels]
    found: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda c: (c, _resolves(cg_host(prefix, c[1]))), candidates)
        for (code, label), ok in results:
            if ok and code not in found:
                found[code] = label
    return dict(sorted(found.items()))


def has_secret(pid: str) -> bool:
    return (PROFILES_DIR / pid / ".secret").is_file()


def read_secret(pid: str) -> str:
    for line in (PROFILES_DIR / pid / ".secret").read_text().splitlines():
        if line.startswith("vpn.secrets.password:"):
            return line.split(":", 1)[1]
    raise ConfigError("Mot de passe introuvable pour le serveur modèle.")


# --------------------------------------------------------------------------- #
# NetworkManager
# --------------------------------------------------------------------------- #
class NMError(Exception):
    pass


_UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_OPENVPN_PLUGIN_PATHS = (
    "/usr/lib/NetworkManager/VPN/nm-openvpn-service.name",
    "/etc/NetworkManager/VPN/nm-openvpn-service.name",
    "/usr/lib/x86_64-linux-gnu/NetworkManager/VPN/nm-openvpn-service.name",
)


def _escape_nm(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,")


class NetworkManager:
    def __init__(self, nmcli: str = "nmcli"):
        self.nmcli = nmcli

    # -- outils ---------------------------------------------------------- #
    def run(self, *args: str, timeout: int = 60) -> str:
        env = dict(os.environ, LC_ALL="C", LANG="C")
        try:
            proc = subprocess.run([self.nmcli, *args], capture_output=True, text=True,
                                  timeout=timeout, env=env)
        except FileNotFoundError as exc:
            raise NMError("nmcli est introuvable : NetworkManager est-il installé ?") from exc
        except subprocess.TimeoutExpired as exc:
            raise NMError("NetworkManager ne répond pas (délai dépassé).") from exc
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout).strip().splitlines()
            raise NMError(msg[-1] if msg else f"nmcli a échoué (code {proc.returncode}).")
        return proc.stdout

    def missing_components(self) -> list[str]:
        missing = []
        if not shutil.which(self.nmcli):
            missing.append("networkmanager")
        if not any(os.path.exists(p) for p in _OPENVPN_PLUGIN_PATHS):
            missing.append("networkmanager-openvpn")
        return missing

    # -- import ---------------------------------------------------------- #
    def import_profile(self, source: str | Path, name: str, country: str | None,
                       username: str = "", password: str = "") -> Profile:
        source = Path(source)
        info = inspect_source(source)
        if info.protocol == "openvpn" and not (username and password):
            raise ConfigError("Les identifiants OpenVPN sont requis (nom d'utilisateur et mot de passe).")

        pid = uuidlib.uuid4().hex[:8]
        dest = PROFILES_DIR / pid
        dest.mkdir(parents=True, exist_ok=True)

        try:
            config_path = self._stage_files(source, info, dest, pid)
            out = self.run("connection", "import", "type", info.protocol, "file", str(config_path))
            m = _UUID_RE.search(out)
            if not m:
                raise NMError("Import réussi mais identifiant de connexion introuvable.")
            nm_uuid = m.group(1)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise

        conn_name = f"{NM_PREFIX} · {name}"
        try:
            self.run("connection", "modify", "uuid", nm_uuid,
                     "connection.id", conn_name, "connection.autoconnect", "no")
            if info.protocol == "openvpn":
                self.set_credentials(pid, nm_uuid, username, password)
            if info.protocol == "wireguard":
                # Une connexion WireGuard importée peut s'activer d'elle-même.
                try:
                    self.run("connection", "down", "uuid", nm_uuid)
                except NMError:
                    pass
        except Exception:
            try:
                self.run("connection", "delete", "uuid", nm_uuid)
            except NMError:
                pass
            shutil.rmtree(dest, ignore_errors=True)
            raise

        return Profile(id=pid, name=name, country=normalize_code(country), protocol=info.protocol,
                       host=info.host, nm_uuid=nm_uuid, created=time.time(),
                       username=username if info.protocol == "openvpn" else "")

    def _stage_files(self, source: Path, info: ConfigInfo, dest: Path, pid: str) -> Path:
        """Copie la configuration (et ses certificats) dans le dossier du profil."""
        if info.protocol == "wireguard":
            # Le nom du fichier devient le nom d'interface : 15 caractères max.
            target = dest / f"tnl{pid}.conf"
            target.write_text(info.text)
            target.chmod(0o600)
            return target

        if zipfile.is_zipfile(source):
            base = dest.resolve()
            with zipfile.ZipFile(source) as zf:
                member_path = _pick_member(zf.namelist())
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    out = (dest / member).resolve()
                    if base not in out.parents:
                        continue  # protection contre les chemins « ../ »
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(zf.read(member))
            target = dest / member_path
        else:
            target = dest / source.name
            shutil.copy2(source, target)
            for ref in _referenced_files(info.text):
                ref_path = (source.parent / ref)
                if ref_path.is_file() and not (dest / ref).exists():
                    (dest / ref).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ref_path, dest / ref)
        for f in dest.rglob("*"):
            if f.is_file():
                f.chmod(0o600)
        return target

    # -- identifiants ---------------------------------------------------- #
    @staticmethod
    def secret_file(pid: str) -> Path:
        return PROFILES_DIR / pid / ".secret"

    def has_credentials(self, pid: str) -> bool:
        return has_secret(pid)

    def username_of(self, profile: Profile) -> str:
        if profile.username:
            return profile.username
        out = self.run("-g", "vpn.data", "connection", "show", "uuid", profile.nm_uuid)
        m = re.search(r"(?:^|,)\s*username\s*=\s*([^,]*)", out)
        if not m or not m.group(1).strip():
            raise ConfigError("Nom d'utilisateur introuvable : renseignez les identifiants du serveur modèle.")
        return m.group(1).strip()

    def clone_for_country(self, template: Profile, code: str, label: str) -> Profile:
        """Crée le profil d'un autre pays à partir du serveur modèle."""
        parts = cg_host_parts(template.host)
        if not parts:
            raise ConfigError("Le serveur modèle n'est pas un serveur CyberGhost.")
        new_host = cg_host(parts[0], label)
        src = PROFILES_DIR / template.id
        config = next((f for f in sorted(src.rglob("*.ovpn"))
                       if re.search(rf"^\s*remote\s+{re.escape(template.host)}\b",
                                    f.read_text("utf-8", "replace"), re.M)), None)
        if not config:
            raise ConfigError("Fichier .ovpn du serveur modèle introuvable.")
        username = self.username_of(template)
        password = read_secret(template.id)

        pid = uuidlib.uuid4().hex[:8]
        dest = PROFILES_DIR / pid
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".secret"))
        target = dest / config.relative_to(src)
        text = target.read_text("utf-8", "replace")
        text = re.sub(rf"^(\s*remote\s+){re.escape(template.host)}\b",
                      lambda m: m.group(1) + new_host, text, flags=re.M)
        target.write_text(text)
        target.chmod(0o600)

        try:
            out = self.run("connection", "import", "type", "openvpn", "file", str(target))
            m = _UUID_RE.search(out)
            if not m:
                raise NMError("Import réussi mais identifiant de connexion introuvable.")
            nm_uuid = m.group(1)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        name = country_name(code)
        try:
            self.run("connection", "modify", "uuid", nm_uuid,
                     "connection.id", f"{NM_PREFIX} · {name}", "connection.autoconnect", "no")
            self.set_credentials(pid, nm_uuid, username, password)
        except Exception:
            try:
                self.run("connection", "delete", "uuid", nm_uuid)
            except NMError:
                pass
            shutil.rmtree(dest, ignore_errors=True)
            raise
        return Profile(id=pid, name=name, country=code, protocol="openvpn", host=new_host,
                       nm_uuid=nm_uuid, created=time.time(), username=username)

    def set_credentials(self, pid: str, nm_uuid: str, username: str, password: str) -> None:
        """Enregistre les identifiants OpenVPN.

        Le mot de passe est conservé dans un fichier privé (0600) et transmis à
        chaque connexion via « nmcli … passwd-file » : NetworkManager ne le
        redemande donc plus, même s'il ne l'a pas mémorisé lui-même.
        """
        if not username or not password:
            raise ConfigError("Nom d'utilisateur et mot de passe requis.")
        if "\n" in password or "\r" in password:
            raise ConfigError("Le mot de passe ne peut pas contenir de retour à la ligne.")
        try:
            self.run("connection", "modify", "uuid", nm_uuid, "-vpn.data", "password-flags")
        except NMError:
            pass
        self.run("connection", "modify", "uuid", nm_uuid,
                 "+vpn.data", f"username={_escape_nm(username)}",
                 "+vpn.data", "password-flags=0")
        try:
            self.run("connection", "modify", "uuid", nm_uuid,
                     "vpn.secrets", f"password={_escape_nm(password)}")
        except NMError:
            pass  # le fichier ci-dessous suffit
        path = self.secret_file(pid)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"vpn.secrets.password:{password}\n")
        path.chmod(0o600)

    # -- pilotage -------------------------------------------------------- #
    def connect(self, nm_uuid: str, pid: str | None = None) -> None:
        args = ["connection", "up", "uuid", nm_uuid]
        if pid and self.has_credentials(pid):
            args += ["passwd-file", str(self.secret_file(pid))]
        self.run(*args, timeout=120)

    def disconnect(self, nm_uuid: str) -> None:
        self.run("connection", "down", "uuid", nm_uuid)

    def delete(self, profile: Profile) -> None:
        try:
            self.run("connection", "delete", "uuid", profile.nm_uuid)
        except NMError as exc:
            if "unknown connection" not in str(exc).lower() and "not found" not in str(exc).lower():
                raise
        shutil.rmtree(PROFILES_DIR / profile.id, ignore_errors=True)

    def exists(self, nm_uuid: str) -> bool:
        try:
            self.run("-t", "-f", "connection.uuid", "connection", "show", "uuid", nm_uuid)
            return True
        except NMError:
            return False

    def active_states(self) -> dict[str, str]:
        """{uuid: état} des connexions actives (activating / activated / deactivating)."""
        out = self.run("-t", "-f", "UUID,STATE", "connection", "show", "--active", timeout=15)
        states = {}
        for line in out.splitlines():
            if ":" in line:
                uid, state = line.split(":", 1)
                states[uid.strip()] = state.strip()
        return states


# --------------------------------------------------------------------------- #
# IP publique
# --------------------------------------------------------------------------- #
def public_ip(timeout: float = 6.0) -> dict:
    """Renvoie {'ip', 'city', 'country'} (champs éventuellement vides)."""
    headers = {"User-Agent": f"{APP_NAME}/{VERSION}", "Accept": "application/json"}
    try:
        req = urllib.request.Request("https://ipinfo.io/json", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        return {"ip": data.get("ip", ""), "city": data.get("city", ""),
                "country": normalize_code(data.get("country")) or ""}
    except Exception:
        req = urllib.request.Request("https://api.ipify.org?format=json", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        return {"ip": data.get("ip", ""), "city": "", "country": ""}
