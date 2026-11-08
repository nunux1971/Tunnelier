# Paquet local pour Arch / CachyOS — installation : makepkg -si
pkgname=tunnelier
pkgver=1.1.0
pkgrel=1
pkgdesc="Client VPN GTK4 pour les configurations CyberGhost (OpenVPN / WireGuard) via NetworkManager"
arch=('any')
license=('MIT')
depends=('python' 'python-gobject' 'gtk4' 'libadwaita' 'networkmanager' 'networkmanager-openvpn')
optdepends=('wireguard-tools: outils WireGuard en ligne de commande (wg)'
            'noto-fonts-emoji: affichage des drapeaux')
source=('core.py' 'tunnelier.py' 'io.github.tunnelier.Tunnelier.desktop' 'io.github.tunnelier.Tunnelier.svg')
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP')

package() {
  install -Dm644 core.py      "$pkgdir/usr/lib/tunnelier/core.py"
  install -Dm755 tunnelier.py "$pkgdir/usr/lib/tunnelier/tunnelier.py"
  install -dm755 "$pkgdir/usr/bin"
  printf '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/tunnelier/tunnelier.py "$@"\n' > "$pkgdir/usr/bin/tunnelier"
  chmod 755 "$pkgdir/usr/bin/tunnelier"
  install -Dm644 io.github.tunnelier.Tunnelier.desktop \
    "$pkgdir/usr/share/applications/io.github.tunnelier.Tunnelier.desktop"
  install -Dm644 io.github.tunnelier.Tunnelier.svg \
    "$pkgdir/usr/share/icons/hicolor/scalable/apps/io.github.tunnelier.Tunnelier.svg"
}
