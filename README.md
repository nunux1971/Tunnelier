# Tunnelier — client VPN pour CyberGhost sous CachyOS

Petite application GTK4 / libadwaita inspirée de l'app Android CyberGhost :
gros bouton de connexion, carte du serveur choisi, liste des pays avec drapeaux,
favoris, recherche, IP publique, durée de connexion et notifications.

Elle s'appuie sur **NetworkManager** : chaque serveur importé devient une connexion
« Tunnelier · <nom> », que vous retrouvez aussi dans les réglages réseau de KDE.

> Projet indépendant, non affilié à CyberGhost. Il ne remplace pas votre abonnement :
> il utilise les fichiers de configuration manuelle que CyberGhost fournit à ses clients.

## 1. Installation

```bash
cd tunnelier
makepkg -si
```

Dépendances installées automatiquement : `python-gobject gtk4 libadwaita networkmanager networkmanager-openvpn`.
Pour les drapeaux : `sudo pacman -S noto-fonts-emoji` (souvent déjà présent).

Lancement : menu des applications → **Tunnelier**, ou `tunnelier` dans un terminal.

Sans paquet (pour essayer) : `python3 tunnelier.py` depuis ce dossier.

## 2. Récupérer vos fichiers chez CyberGhost

CyberGhost n'a pas d'API publique pour lister ses serveurs : on part donc des fichiers
de configuration manuelle de votre compte.

1. Connectez-vous à votre compte sur le site CyberGhost.
2. Dans la partie configuration manuelle d'appareils, créez un appareil **OpenVPN**
   (ou **WireGuard**), choisissez le pays et le protocole (UDP conseillé).
3. Téléchargez l'archive `.zip` (ou le `.conf` WireGuard).
4. Notez le **nom d'utilisateur** et le **mot de passe générés** pour cet appareil :
   ce ne sont *pas* l'e-mail et le mot de passe de votre compte.

**Une seule configuration suffit.** Les identifiants CyberGhost fonctionnent sur tous les
pays : seul le code pays change dans l'adresse du serveur (`87-1-al.cg-dialup.net`,
`87-1-de.cg-dialup.net`…). Après le premier import, Tunnelier détecte tous les pays
disponibles et les affiche dans l'onglet *Serveurs* ; un clic sur un pays crée sa
connexion automatiquement. La liste se rafraîchit chaque semaine (ou via le menu,
`F5`).

## 3. Utilisation

- **Importer** : bouton `+`, `Ctrl+I`, ou glisser-déposer le `.zip` / `.ovpn` / `.conf`
  dans la fenêtre. Le pays est détecté automatiquement (modifiable).
- **Se connecter** : gros bouton rond (dernier serveur, sinon favori), ou touchez un pays
  dans l'onglet *Serveurs*. Changer de pays déconnecte proprement l'ancien.
- **Favoris** : étoile ; ils passent en tête de liste. Le filtre ★ n'affiche qu'eux.
- **Préférences** (`Ctrl+,`) : connexion automatique au lancement, notifications,
  vérification de l'IP publique (via ipinfo.io).

Couleurs du bouton : gris = non protégé, jaune pulsant = connexion en cours, vert = protégé.

## 4. Bon à savoir

- Le mot de passe OpenVPN est stocké par NetworkManager dans
  `/etc/NetworkManager/system-connections/` (lisible par root uniquement).
- La première connexion peut afficher une fenêtre d'authentification (polkit) selon
  votre configuration.
- Données de l'app : `~/.config/tunnelier/` (liste, réglages) et
  `~/.local/share/tunnelier/profiles/` (fichiers importés).
- Pas encore de *kill switch* ni d'icône dans la barre système.

## 5. Désinstallation

Supprimez d'abord les serveurs dans l'app (cela retire les connexions de NetworkManager), puis :

```bash
sudo pacman -R tunnelier
rm -rf ~/.config/tunnelier ~/.local/share/tunnelier
```

## Tests du moteur

```bash
python3 tests/test_core.py   # utilise un faux nmcli, ne touche pas à votre réseau
```
