import json, os, sys, tempfile, zipfile
from pathlib import Path
tmp = Path(tempfile.mkdtemp())
os.environ["XDG_DATA_HOME"] = str(tmp / "data"); os.environ["XDG_CONFIG_HOME"] = str(tmp / "cfg")
os.environ["FAKE_NM_DB"] = str(tmp / "nm.json")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core

# --- détection pays
assert core.detect_country("87-1-fr.cg-dialup.net", "openvpn.ovpn") == "FR"
assert core.detect_country("88-2-de.cg-dialup.net", "x.ovpn") == "DE"
assert core.detect_country("", "CyberGhost-United-States.ovpn") == "US"
assert core.detect_country("", "suisse_udp.ovpn") == "CH"
assert core.detect_country("1.2.3.4", "openvpn.ovpn") is None
assert core.detect_country("uk-lon.example.net", "") == "GB"
assert core.flag("fr") == "🇫🇷" and core.flag(None) == "🌐" and core.country_name("uk") == "Royaume-Uni"

OVPN = """client\nremote 87-1-fr.cg-dialup.net 443\ndev tun\nproto udp\nauth-user-pass\nca ca.crt\ncert client.crt\nkey client.key\n"""
WG = """[Interface]\nPrivateKey = abc\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = xyz\nEndpoint = nl.example.net:51820\nAllowedIPs = 0.0.0.0/0\n"""

src = tmp / "src"; src.mkdir()
z = src / "cg_netherlands.zip"
with zipfile.ZipFile(z, "w") as zf:
    zf.writestr("openvpn/openvpn.ovpn", OVPN.replace("-fr.", "-nl."))
    for f in ("ca.crt", "client.crt", "client.key"): zf.writestr(f"openvpn/{f}", "PEM")
    zf.writestr("../evil.txt", "x")
info = core.inspect_source(z)
assert info.protocol == "openvpn" and info.country == "NL" and info.port == "443", info

(src / "fr.ovpn").write_text(OVPN)
for f in ("ca.crt", "client.crt", "client.key"): (src / f).write_text("PEM")
(src / "pays-bas.conf").write_text(WG)
w = core.inspect_source(src / "pays-bas.conf")
assert w.protocol == "wireguard" and w.host == "nl.example.net" and w.port == "51820" and w.country == "NL"

try: core.inspect_source(src / "ca.crt"); raise SystemExit("devrait échouer")
except core.ConfigError: pass

nm = core.NetworkManager(str(Path(__file__).parent / "fake_nmcli"))
try: nm.import_profile(src / "fr.ovpn", "France", "FR"); raise SystemExit("identifiants requis")
except core.ConfigError: pass

p1 = nm.import_profile(z, "Pays-Bas", "NL", "user1", "p,ss\\w")
d1 = core.PROFILES_DIR / p1.id
assert (d1 / "openvpn/openvpn.ovpn").exists() and (d1 / "openvpn/ca.crt").exists()
assert not (core.PROFILES_DIR / "evil.txt").exists() and not (tmp / "data/tunnelier/evil.txt").exists()
p2 = nm.import_profile(src / "fr.ovpn", "France", "fr", "user2", "pw")
assert (core.PROFILES_DIR / p2.id / "client.key").exists() and p2.country == "FR"
p3 = nm.import_profile(src / "pays-bas.conf", "NL WireGuard", "NL")
assert p3.protocol == "wireguard"
db = json.load(open(os.environ["FAKE_NM_DB"]))
mod1 = db["conns"][p1.nm_uuid]["mod"]
assert "Tunnelier · Pays-Bas" in mod1 and "password=p\\,ss\\\\w" in mod1 and "username=user1" in mod1, mod1
wg_file = Path(db["conns"][p3.nm_uuid]["file"]).name
assert len(Path(wg_file).stem) <= 15, wg_file

st = core.Store(); [st.add(p) for p in (p1, p2, p3)]
st2 = core.Store.load(); assert [p.id for p in st2.profiles] == [p1.id, p2.id, p3.id]
p2.favorite = True; st.save(); assert core.Store.load().preferred().id == p2.id
st.settings["last_server"] = p3.id; st.save(); assert core.Store.load().preferred().id == p3.id

sec = nm.secret_file(p1.id)
assert nm.has_credentials(p1.id) and oct(sec.stat().st_mode & 0o777) == "0o600"
assert not nm.has_credentials(p3.id)
nm.connect(p1.nm_uuid, p1.id); assert nm.active_states() == {p1.nm_uuid: "activated"}
assert json.load(open(os.environ["FAKE_NM_DB"]))["last_pw"] == "vpn.secrets.password:p,ss\\w\n"
nm.set_credentials(p1.id, p1.nm_uuid, "user9", "nouveau")
assert sec.read_text() == "vpn.secrets.password:nouveau\n"
try: nm.set_credentials(p1.id, p1.nm_uuid, "u", ""); raise SystemExit("vide")
except core.ConfigError: pass
nm.disconnect(p1.nm_uuid); assert nm.active_states() == {}
os.environ["FAKE_FAIL"] = "1"
try: nm.connect(p2.nm_uuid); raise SystemExit("devrait échouer")
except core.NMError as e: assert "auth failed" in str(e)
del os.environ["FAKE_FAIL"]
nm.delete(p1); assert not d1.exists() and p1.nm_uuid not in json.load(open(os.environ["FAKE_NM_DB"]))["conns"]
st.remove(p3); assert st.settings["last_server"] is None

# --- catalogue CyberGhost
assert core.cg_host_parts("87-1-al.cg-dialup.net") == ("87-1", "al")
assert core.cg_host_parts("1-de.cg-dialup.net") == ("1", "de")
assert core.cg_host_parts("nl.example.net") is None
import socket
real = socket.getaddrinfo
ok_hosts = {"87-1-de.cg-dialup.net", "87-1-jp.cg-dialup.net", "87-1-uk.cg-dialup.net", "87-1-fr.cg-dialup.net"}
socket.getaddrinfo = lambda h, *a, **k: [(0,)] if h in ok_hosts else (_ for _ in ()).throw(socket.gaierror("nx"))
found = core.scan_cyberghost_countries("87-1")
socket.getaddrinfo = real
assert found == {"DE": "de", "FR": "fr", "GB": "uk", "JP": "jp"}, found

# modèle = profil OpenVPN CyberGhost avec mot de passe (p2 : 87-1-fr)
st = core.Store.load()
tpl = st.template(); assert tpl and tpl.id == p2.id, tpl
st.set_catalog("87-1", found); assert core.Store.load().catalog_is_fresh("87-1")
assert not core.Store.load().catalog_is_fresh("99-1")
jp = nm.clone_for_country(tpl, "JP", "jp")
assert jp.host == "87-1-jp.cg-dialup.net" and jp.name == "Japon" and jp.username == "user2"
jp_cfg = next((core.PROFILES_DIR / jp.id).rglob("*.ovpn")).read_text()
assert "remote 87-1-jp.cg-dialup.net 443" in jp_cfg and "-fr." not in jp_cfg
assert (core.PROFILES_DIR / jp.id / "client.key").exists()
assert core.read_secret(jp.id) == "pw"
db = json.load(open(os.environ["FAKE_NM_DB"]))
assert "Tunnelier · Japon" in db["conns"][jp.nm_uuid]["mod"] and "username=user2" in db["conns"][jp.nm_uuid]["mod"]
uk = nm.clone_for_country(tpl, "GB", "uk"); assert uk.host == "87-1-uk.cg-dialup.net"
st.add(jp); assert st.profile_for_country("JP").id == jp.id
print("Tous les tests du moteur passent ✔")
