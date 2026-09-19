"""
install_hashcat.py

Cross-platform hashcat installer for Windows, Linux, and macOS.

- Detects OS and picks the right install method automatically
- Windows: downloads the official portable binary and adds it to PATH
- Linux: uses apt/dnf/pacman if available, else downloads the portable binary
- macOS: uses Homebrew if available, else downloads the portable binary
- Verifies the install actually works before declaring success
- Safe to re-run: skips work if a working install is already found

Usage:
    python install_hashcat.py
    python install_hashcat.py --dest /custom/path
    python install_hashcat.py --version 7.1.2
    python install_hashcat.py --url https://example.com/hashcat.zip
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "https://github.com/devtint/install_hashcat"
SOURCEFORGE_WIN_TMPL = (
    "https://sourceforge.net/projects/hashcat.mirror/files/v{tag}/hashcat-{tag}.7z/download"
)
GITHUB_LATEST_API = "https://api.github.com/repos/hashcat/hashcat/releases/latest"


def log(msg):
    print(f"[install_hashcat] {msg}")


def default_dest():
    """Pick a sane default install directory per OS, no single hardcoded path."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "hashcat"
    if system == "Darwin":
        return Path.home() / ".local" / "share" / "hashcat"
    return Path.home() / ".local" / "share" / "hashcat"


def get_latest_tag():
    log("Checking latest hashcat version on GitHub...")
    req = urllib.request.Request(
        GITHUB_LATEST_API, headers={"User-Agent": "hashcat-installer-script"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return data["tag_name"].lstrip("v")


def fmt_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def fmt_time(seconds):
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def download(url, dest_path):
    log(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "hashcat-installer-script"})
    chunk_size = 64 * 1024

    with urllib.request.urlopen(req, timeout=120) as resp, open(dest_path, "wb") as out:
        total = resp.headers.get("Content-Length")
        total = int(total) if total and total.isdigit() else None

        downloaded = 0
        start = time.time()
        last_print = 0.0

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if now - last_print < 0.2:
                continue
            last_print = now

            elapsed = max(now - start, 0.001)
            speed = downloaded / elapsed

            if total:
                pct = downloaded / total * 100
                remaining = (total - downloaded) / speed if speed > 0 else 0
                bar_len = 30
                filled = int(bar_len * downloaded / total)
                bar = "#" * filled + "-" * (bar_len - filled)
                line = (
                    f"\r[{bar}] {pct:5.1f}%  "
                    f"{fmt_size(downloaded)} / {fmt_size(total)}  "
                    f"{fmt_size(speed)}/s  ETA {fmt_time(remaining)}   "
                )
            else:
                line = (
                    f"\r{fmt_size(downloaded)} downloaded  "
                    f"{fmt_size(speed)}/s  elapsed {fmt_time(elapsed)}   "
                )
            sys.stdout.write(line)
            sys.stdout.flush()

    elapsed = max(time.time() - start, 0.001)
    sys.stdout.write(f"\r{' ' * 100}\r")
    log(
        f"Saved to {dest_path} ({fmt_size(downloaded)} in {fmt_time(elapsed)}, "
        f"avg {fmt_size(downloaded / elapsed)}/s)"
    )
    return downloaded


def find_7z_exe():
    candidates = [
        shutil.which("7z"),
        shutil.which("7za"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def ensure_7zip_windows():
    exe = find_7z_exe()
    if exe:
        return exe

    log("7-Zip not found, installing it via winget...")
    result = subprocess.run(
        ["winget", "install", "-e", "--id", "7zip.7zip",
         "--accept-source-agreements", "--accept-package-agreements"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(result.stdout)
        log(result.stderr)
        raise RuntimeError(
            "Could not install 7-Zip automatically. Install it manually from "
            "https://www.7-zip.org/ and re-run this script."
        )

    exe = find_7z_exe()
    if not exe:
        raise RuntimeError(
            "7-Zip installed but 7z.exe was not found. Open a new terminal and re-run."
        )
    return exe


def extract_archive(archive_path: Path, extract_to: Path):
    ext = archive_path.suffix.lower()
    extract_to.mkdir(parents=True, exist_ok=True)

    if ext == ".7z":
        if platform.system() == "Windows":
            sevenzip = ensure_7zip_windows()
        else:
            sevenzip = shutil.which("7z") or shutil.which("7za") or shutil.which("p7zip")
            if not sevenzip:
                raise RuntimeError(
                    "7z is required to extract .7z archives. Install it with your "
                    "package manager, e.g. 'sudo apt install p7zip-full' or "
                    "'brew install p7zip', then re-run."
                )
        log(f"Extracting {archive_path} -> {extract_to}")
        result = subprocess.run(
            [sevenzip, "x", str(archive_path), f"-o{extract_to}", "-y"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            log(result.stdout)
            log(result.stderr)
            raise RuntimeError("7-Zip extraction failed.")
        return

    if ext == ".zip":
        if not zipfile.is_zipfile(archive_path):
            size = os.path.getsize(archive_path)
            with open(archive_path, "rb") as f:
                head = f.read(200)
            raise RuntimeError(
                f"Downloaded file is not a valid zip (size={size} bytes). "
                f"First bytes: {head!r}"
            )
        log(f"Extracting {archive_path} -> {extract_to}")
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_to)
        return

    if ext in (".xz", ".gz", ".tgz", ".bz2") or archive_path.name.endswith(
        (".tar.xz", ".tar.gz", ".tar.bz2")
    ):
        log(f"Extracting {archive_path} -> {extract_to}")
        result = subprocess.run(
            ["tar", "-xf", str(archive_path), "-C", str(extract_to)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            log(result.stdout)
            log(result.stderr)
            raise RuntimeError("tar extraction failed.")
        return

    raise RuntimeError(f"Don't know how to extract archive type: {archive_path.name}")


def find_hashcat_binary(root: Path):
    name = "hashcat.exe" if platform.system() == "Windows" else "hashcat"
    for p in root.rglob(name):
        if p.is_file():
            return p
    return None


def flatten_into_dest(bin_path: Path, dest: Path):
    src_folder = bin_path.parent
    dest.mkdir(parents=True, exist_ok=True)
    for item in src_folder.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def which_hashcat(dest: Path):
    """Return a path to a working hashcat binary: prefer dest, fall back to PATH."""
    name = "hashcat.exe" if platform.system() == "Windows" else "hashcat"
    candidate = dest / name
    if candidate.exists():
        return candidate
    on_path = shutil.which("hashcat")
    return Path(on_path) if on_path else None


def verify_install(dest: Path):
    """Actually run the binary and confirm it reports a version. This is the
    real check, not just a file-existence check."""
    exe = which_hashcat(dest)
    if not exe:
        return False, None
    try:
        result = subprocess.run(
            [str(exe), "--version"], capture_output=True, text=True, timeout=30
        )
        version = (result.stdout.strip() or result.stderr.strip())
        looks_valid = result.returncode == 0 and bool(re.search(r"\d+\.\d+\.\d+", version))
        return looks_valid, version
    except Exception as e:
        log(f"Verification failed: {e}")
        return False, None


# ---------- PATH handling ----------

def get_windows_user_path():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, "Path")
            return value
    except FileNotFoundError:
        return ""


def set_windows_user_path(new_path):
    import winreg
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
    # Tell running apps (Explorer, new terminals) that the environment changed
    try:
        import ctypes
        HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 2, 5000, None
        )
    except Exception:
        pass


def ensure_on_path_windows(dest: Path):
    dest_str = str(dest)
    current = get_windows_user_path()
    parts = [p for p in current.split(";") if p]
    if any(p.lower() == dest_str.lower() for p in parts):
        log("Destination already on PATH, skipping.")
        return
    parts.append(dest_str)
    new_path = ";".join(parts)
    set_windows_user_path(new_path)
    os.environ["PATH"] = os.environ.get("PATH", "") + ";" + dest_str
    log(f"Added {dest_str} to user PATH. Open a NEW terminal for it to take effect.")


def ensure_on_path_unix(dest: Path):
    dest_str = str(dest)
    if os.environ.get("PATH", "") and dest_str in os.environ["PATH"].split(":"):
        log("Destination already on PATH for this session.")
    else:
        os.environ["PATH"] = os.environ.get("PATH", "") + ":" + dest_str

    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        rc_file = Path.home() / ".zshrc"
    elif "bash" in shell:
        rc_file = Path.home() / ".bashrc"
    else:
        rc_file = Path.home() / ".profile"

    line = f'export PATH="$PATH:{dest_str}"\n'
    existing = rc_file.read_text() if rc_file.exists() else ""
    if dest_str in existing:
        log(f"{rc_file} already references the install directory, skipping.")
        return

    with open(rc_file, "a") as f:
        f.write(f"\n# Added by install_hashcat.py ({REPO})\n{line}")
    log(f"Added {dest_str} to PATH via {rc_file}. Restart your shell or run: source {rc_file}")


# ---------- Package manager installs (Linux / macOS) ----------

def try_package_manager_install():
    system = platform.system()

    if system == "Darwin" and shutil.which("brew"):
        log("Homebrew detected, installing hashcat via brew...")
        result = subprocess.run(["brew", "install", "hashcat"], capture_output=True, text=True)
        if result.returncode == 0:
            return True
        log(result.stdout)
        log(result.stderr)
        log("brew install failed, falling back to manual download.")
        return False

    if system == "Linux":
        for mgr, cmd in [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "hashcat"]),
            ("dnf", ["sudo", "dnf", "install", "-y", "hashcat"]),
            ("pacman", ["sudo", "pacman", "-S", "--noconfirm", "hashcat"]),
        ]:
            if shutil.which(mgr):
                log(f"{mgr} detected, installing hashcat via {mgr}...")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return True
                log(result.stdout)
                log(result.stderr)
                log(f"{mgr} install failed, falling back to manual download.")
                return False

    return False


# ---------- Download-based install (used when no package manager fits) ----------

def build_download_url(tag: str, override_url: str = None):
    if override_url:
        return override_url

    system = platform.system()
    if system == "Windows":
        return SOURCEFORGE_WIN_TMPL.format(tag=tag)

    # Linux/macOS: official GitHub release, portable build
    return f"https://github.com/hashcat/hashcat/releases/download/v{tag}/hashcat-{tag}.7z"


def guess_extension(url: str):
    m = re.search(r"\.([a-zA-Z0-9]+)/download/?$", url) or re.search(r"\.([a-zA-Z0-9]+)$", url)
    return f".{m.group(1)}" if m else ".7z"


def manual_download_install(dest: Path, tag: str, override_url: str = None):
    archive_url = build_download_url(tag, override_url)
    work_dir = (
        Path(os.environ.get("TEMP", str(Path.home()))) / "hashcat_install"
        if platform.system() == "Windows"
        else Path.home() / ".cache" / "hashcat_install"
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    ext = guess_extension(archive_url)
    archive_path = work_dir / f"hashcat-{tag}{ext}"
    extract_dir = work_dir / "extracted"

    download(archive_url, archive_path)
    extract_archive(archive_path, extract_dir)

    binary = find_hashcat_binary(extract_dir)
    if not binary:
        raise RuntimeError(
            "Could not find a hashcat binary after extraction. "
            "Pass --url to point at a known-good archive for your platform."
        )

    flatten_into_dest(binary, dest)

    if platform.system() != "Windows":
        target = dest / "hashcat"
        if target.exists():
            os.chmod(target, 0o755)

    shutil.rmtree(work_dir, ignore_errors=True)


def report_usage(dest: Path):
    exe = which_hashcat(dest)
    system = platform.system()

    if exe is None:
        # Should not normally happen since verify_install already passed,
        # but search a bit wider so we never leave the user guessing.
        found = find_hashcat_binary(dest.parent) if dest.parent.exists() else None
        exe = found or (dest / ("hashcat.exe" if system == "Windows" else "hashcat"))
        log(f"Could not confirm the exact binary location, best guess: {exe}")

    if system == "Windows":
        persisted = any(
            part.lower().rstrip("\\") == str(dest).lower().rstrip("\\")
            for part in get_windows_user_path().split(";") if part
        )
        on_path_now = shutil.which("hashcat") is not None
        if persisted and on_path_now:
            log("PATH check: install folder is saved and already usable in this window.")
        elif persisted:
            log("PATH check: install folder is saved in your user PATH.")
            log("This terminal window was opened before the install, so it has not picked it up yet.")
        else:
            log("PATH check FAILED: install folder is not in your user PATH.")
        log("Close ALL terminals/editors and open a new one, then run: hashcat --version")
        log(f"To use it right now in this window: & \"{exe}\" --version")
    else:
        on_path_now = shutil.which("hashcat") is not None
        if on_path_now:
            log("PATH check: hashcat is already usable in this shell.")
        else:
            log("Open a new terminal (or run: source your shell rc file), then run: hashcat --version")
        log(f"To use it right now: {exe} --version")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dest", default=None,
        help="Install directory. Defaults to a per-OS user directory, no admin rights needed."
    )
    parser.add_argument(
        "--version", default=None,
        help="Specific hashcat version, e.g. 7.1.2. Default: latest from GitHub."
    )
    parser.add_argument(
        "--url", default=None,
        help="Direct download URL for the hashcat archive, bypasses auto-detection."
    )
    parser.add_argument(
        "--no-package-manager", action="store_true",
        help="Skip apt/dnf/pacman/brew and always do a manual portable install."
    )
    args = parser.parse_args()

    dest = Path(args.dest) if args.dest else default_dest()

    ok, version = verify_install(dest)
    if ok:
        log(f"hashcat already installed and verified: {version}")
        if platform.system() == "Windows":
            ensure_on_path_windows(dest)
        else:
            ensure_on_path_unix(dest)
        report_usage(dest)
        log(f"Installed with install_hashcat.py -> {REPO}")
        return

    used_package_manager = False
    if not args.no_package_manager and not args.url:
        used_package_manager = try_package_manager_install()

    if not used_package_manager:
        tag = args.version or get_latest_tag()
        log(f"Target version: {tag}")
        manual_download_install(dest, tag, args.url)

        if platform.system() == "Windows":
            ensure_on_path_windows(dest)
        else:
            ensure_on_path_unix(dest)

    ok, version = verify_install(dest)
    if not ok:
        log("Install finished but verification failed. Check the destination folder manually.")
        sys.exit(1)

    log(f"hashcat installed and verified: {version}")
    report_usage(dest)
    log(f"Installed with install_hashcat.py -> {REPO}")


if __name__ == "__main__":
    main()
