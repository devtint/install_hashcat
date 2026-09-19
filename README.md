# install_hashcat

A single Python script that installs [hashcat](https://hashcat.net/hashcat/) on Windows, Linux, or macOS, no manual downloading, extracting, or PATH editing required.

## Quick install (one command)

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/devtint/install_hashcat/main/install_hashcat.py | python -
```

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/devtint/install_hashcat/main/install_hashcat.py | python3 -
```

This downloads the script and runs it immediately, nothing is saved to disk. To pass options, add them after the dash, for example `| python - --version 7.1.2`.

Prefer to read the script before running it? Download `install_hashcat.py` first, review it, then run `python install_hashcat.py`.

## What it does

- Detects your OS automatically and picks the right install method
- Windows: downloads the official portable binary and adds it to your user PATH
- Linux: tries `apt`, `dnf`, or `pacman` first, falls back to a portable download if none apply
- macOS: tries Homebrew first, falls back to a portable download if it's not available
- Verifies the install by actually running `hashcat --version`, not just checking the file exists
- Safe to re-run: if a working install is already found, it skips straight to a PATH check
- No hardcoded install paths, the destination is picked per OS (or you can set your own with `--dest`)
- Shows live download progress with speed and ETA

## Requirements

- Python 3.8+
- Internet access
- Windows: `winget` (comes preinstalled on modern Windows) for installing 7-Zip if needed
- Linux/macOS: `7z` (or `p7zip`) available if a package manager install isn't possible

## Usage

```bash
python install_hashcat.py
```

That's it. It installs the latest version to a sensible default location for your OS.

### Options

```bash
# Install to a custom directory
python install_hashcat.py --dest /custom/path

# Install a specific version instead of latest
python install_hashcat.py --version 7.1.2

# Use a specific download URL instead of auto-detecting
python install_hashcat.py --url https://example.com/hashcat.7z

# Skip package managers and always do a manual portable install
python install_hashcat.py --no-package-manager
```

## Default install locations

| OS | Default path |
|---|---|
| Windows | `C:\Users\<you>\tools\hashcat` |
| macOS | `~/.local/share/hashcat` |
| Linux | `~/.local/share/hashcat` |

No admin/root rights are needed for the default install.

On Windows the default is deliberately outside `AppData`. Python installed from the Microsoft Store hides files written to `AppData` in a private sandbox, which makes the install invisible to PowerShell.

## After install

Open a new terminal and run:

```bash
hashcat --version
```

If that prints a version number, you're good to go.

## Troubleshooting

**"hashcat is not recognized" right after installing**

1. Close every terminal and editor completely, then open a new one. PATH changes only apply to newly started programs.
2. Check the file exists: `Test-Path "$HOME\tools\hashcat\hashcat.exe"`
3. Run it by full path to confirm it works: `& "$HOME\tools\hashcat\hashcat.exe" --version`

**Using Python from the Microsoft Store**

Check with `python -c "import sys; print(sys.executable)"`. If the path contains `WindowsApps` or `PythonSoftwareFoundation`, the script detects this and installs outside `AppData` automatically. A python.org install avoids the issue entirely.

## How verification works

The script doesn't just check that a `hashcat` file exists. It actually runs `hashcat --version` and checks the output for a valid version number before declaring success. If verification fails, it exits with a non-zero code and tells you to check the install directory manually.

## License

MIT, use it however you like.

---

Made by [devtint](https://github.com/devtint)
