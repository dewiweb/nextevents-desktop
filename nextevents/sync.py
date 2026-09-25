"""Synchro du dossier de sortie vers FTP, partage SMB et/ou dossier
local (disque, lecteur réseau mappé, chemin UNC). Ne supprime à
distance que les .png/.html absents en local.

Chaque destination choisit ce qu'elle reçoit via ses réglages :
`<proto>_send_landscape` (défaut oui — racine) et `<proto>_send_portrait`
(défaut non — sous-dossier distant `portrait/`)."""

import shutil
from pathlib import Path


def _ours(name):
    """Nom de fichier produit par l'app (diapos + diapo du jour). La
    synchro ne supprime à distance que ce qu'elle a elle-même poussé :
    un dossier destination peut contenir des fichiers sans rapport."""
    return name.startswith("slide-") or Path(name).stem in ("index", "qr")


def _dirs(out_dir, cfg, proto):
    """Dossiers locaux à pousser : (sous-chemin distant, chemin local)."""
    out_dir = Path(out_dir)
    dirs = []
    if cfg.get(f"{proto}_send_landscape", 1):
        dirs.append(("", out_dir))
    if cfg.get(f"{proto}_send_portrait") and (out_dir / "portrait").exists():
        dirs.append(("portrait", out_dir / "portrait"))
    return dirs


def _ftp_push_dir(ftp, src, sub):
    """Pousse un dossier local (*.png + html/*.html + manifest.txt) vers
    le dossier courant du FTP, ou son sous-dossier `sub` s'il est donné."""
    depth = 0
    if sub:
        try:
            ftp.mkd(sub)
        except Exception:
            pass
        ftp.cwd(sub)
        depth = 1
    try:
        for pattern, hsub in (("*.png", None), ("*.html", "html")):
            sdir = src if hsub is None else src / hsub
            local = {p.name: p for p in sdir.glob(pattern)}
            if hsub:
                if local:
                    try:
                        ftp.mkd(hsub)
                    except Exception:
                        pass
                    ftp.cwd(hsub)
                    depth += 1
                else:
                    continue
            remote = {n for n in ftp.nlst() if n.endswith(pattern[1:])}
            remote_size = {}
            for n in remote:
                try:
                    remote_size[n] = ftp.size(n)
                except Exception:
                    pass
            for name, p in sorted(local.items()):
                if remote_size.get(name) == p.stat().st_size:
                    continue  # déjà à jour à distance
                with open(p, "rb") as f:
                    ftp.storbinary(f"STOR {name}", f)
                print(f"  ↑ {sub + '/' if sub else ''}{name}")
            for name in sorted(n for n in remote - set(local)
                               if _ours(n)):
                ftp.delete(name)
                print(f"  - distant : {name} supprimé")
            if hsub:
                ftp.cwd("..")
                depth -= 1
        manifest = src / "manifest.txt"
        if manifest.exists():
            with open(manifest, "rb") as f:
                ftp.storbinary("STOR manifest.txt", f)
        remote_pngs = {n for n in ftp.nlst() if n.endswith(".png")}
        expected = {p.name for p in src.glob("*.png")}
        if remote_pngs == expected:
            print(f"  synchro FTP {sub or '.'} vérifiée : "
                  f"{len(expected)} fichiers conformes")
        else:
            print(
                "  ⚠ divergence FTP — manquants : "
                f"{sorted(expected - remote_pngs)} / en trop : {sorted(remote_pngs - expected)}"
            )
    finally:
        for _ in range(depth):
            ftp.cwd("..")


def sync_ftp(out_dir, cfg):
    """Pousse le dossier de sortie vers un FTP. Supprime à distance les
    fichiers absents en local (mêmes règles de rafraîchissement)."""
    import ftplib

    host = (cfg.get("ftp_host") or "").strip()
    if not host:
        return
    cls = ftplib.FTP_TLS if cfg.get("ftp_tls") else ftplib.FTP
    ftp = cls()
    ftp.connect(host, int(cfg.get("ftp_port") or 21), timeout=30)
    try:
        ftp.login(cfg.get("ftp_user") or "", cfg.get("ftp_pass") or "")
        if cfg.get("ftp_tls"):
            ftp.prot_p()
        for part in [p for p in (cfg.get("ftp_path") or "/").split("/") if p]:
            try:
                ftp.mkd(part)
            except ftplib.error_perm:
                pass
            ftp.cwd(part)
        for sub, src in _dirs(out_dir, cfg, "ftp"):
            _ftp_push_dir(ftp, src, sub)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def _smb_push_dir(src, d):
    """Pousse un dossier local (*.png + html/*.html + manifest.txt) vers
    le chemin SMB `d`."""
    from smbclient import listdir, makedirs, open_file, remove, stat

    for pattern, hsub in (("*.png", None), ("*.html", "html")):
        sdir = src if hsub is None else src / hsub
        local = {p.name: p for p in sdir.glob(pattern)}
        if hsub and not local:
            continue
        dd = d if hsub is None else d + "\\" + hsub
        if hsub:
            makedirs(dd, exist_ok=True)
        remote = {n for n in listdir(dd) if n.endswith(pattern[1:])}
        remote_size = {}
        for n in remote:
            try:
                remote_size[n] = stat(dd + "\\" + n).st_size
            except Exception:
                pass
        for name, p in sorted(local.items()):
            if remote_size.get(name) == p.stat().st_size:
                continue  # déjà à jour à distance
            with open(p, "rb") as f, open_file(dd + "\\" + name, "wb") as dst:
                dst.write(f.read())
            print(f"  ↑ smb {name}")
        for name in sorted(n for n in remote - set(local) if _ours(n)):
            remove(dd + "\\" + name)
            print(f"  - smb : {name} supprimé")
    manifest = src / "manifest.txt"
    if manifest.exists():
        with open(manifest, "rb") as f, open_file(d + "\\manifest.txt", "wb") as dst:
            dst.write(f.read())
    remote_pngs = {n for n in listdir(d) if n.endswith(".png")}
    expected = {p.name for p in src.glob("*.png")}
    if remote_pngs == expected:
        print(f"  synchro SMB {d} vérifiée : "
              f"{len(expected)} fichiers conformes")
    else:
        print(
            "  ⚠ divergence SMB — manquants : "
            f"{sorted(expected - remote_pngs)} / en trop : {sorted(remote_pngs - expected)}"
        )


def sync_smb(out_dir, cfg):
    """Pousse le dossier de sortie vers un partage SMB (poste OBS, NAS…)
    via smbprotocol — aucun montage système requis."""
    host = (cfg.get("smb_host") or "").strip()
    share = (cfg.get("smb_share") or "").strip()
    if not host or not share:
        return
    from smbclient import makedirs, register_session

    register_session(
        host,
        username=cfg.get("smb_user") or "",
        password=cfg.get("smb_pass") or "",
    )
    base = f"\\\\{host}\\{share}"
    if cfg.get("smb_path"):
        base += "\\" + str(cfg["smb_path"]).strip("/\\")
    makedirs(base, exist_ok=True)

    for sub, src in _dirs(out_dir, cfg, "smb"):
        d = base if not sub else base + "\\" + sub
        if sub:
            makedirs(d, exist_ok=True)
        _smb_push_dir(src, d)


def _local_push_dir(src, d):
    """Miroir d'un dossier local (*.png + html/*.html + manifest.txt)
    vers le chemin `d` (disque, lecteur mappé ou UNC \\\\hôte\\partage)."""
    d.mkdir(parents=True, exist_ok=True)
    for pattern, hsub in (("*.png", None), ("*.html", "html")):
        sdir = src if hsub is None else src / hsub
        local = {p.name: p for p in sdir.glob(pattern)}
        if hsub and not local:
            continue
        dd = d if hsub is None else d / hsub
        if hsub:
            dd.mkdir(parents=True, exist_ok=True)
        remote = {p.name: p for p in dd.glob(pattern)}
        for name, p in sorted(local.items()):
            rp = remote.get(name)
            if rp is not None and rp.stat().st_size == p.stat().st_size:
                continue  # déjà à jour à distance
            shutil.copy2(p, dd / name)
            print(f"  ↑ {dd / name}")
        for name in sorted(n for n in set(remote) - set(local)
                           if _ours(n)):
            (dd / name).unlink()
            print(f"  - local : {name} supprimé")
    manifest = src / "manifest.txt"
    if manifest.exists():
        shutil.copy2(manifest, d / "manifest.txt")
    remote_pngs = {p.name for p in d.glob("*.png")}
    expected = {p.name for p in src.glob("*.png")}
    if remote_pngs == expected:
        print(f"  synchro locale {d} vérifiée : "
              f"{len(expected)} fichiers conformes")


def sync_local(out_dir, cfg):
    """Copie miroir de tout ce qui a été généré vers un dossier du
    système de fichiers — lecteur réseau mappé (X:\\…) ou chemin UNC
    (\\\\hôte\\partage) inclus : pas besoin de smbprotocol ni
    d'identifiants, Windows gère l'auth."""
    dest = (cfg.get("local_dir") or "").strip()
    if not dest:
        return
    out_dir = Path(out_dir)
    dirs = [("", out_dir)]
    if (out_dir / "portrait").exists():
        dirs.append(("portrait", out_dir / "portrait"))
    for sub, src in dirs:
        d = Path(dest) / sub if sub else Path(dest)
        _local_push_dir(src, d)
