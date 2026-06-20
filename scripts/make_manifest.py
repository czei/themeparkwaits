"""Generate an OTA release manifest + payload for ThemeParkWaits (T026).

The device's `scrollkit.ota.OTAClient.for_github` fetches `manifest.json` from a
public `releases` branch and each file from `{base}/files/{device-path}` (verified
API). This produces that layout from a source tree:

    out/
      manifest.json            # {version, files:{ "/src/app.py": {size, checksum}, ...}}
      files/src/app.py         # payload mirrored under files/<device-path>
      files/code.py
      ...

Device-local / private files are NEVER published (allowlist exclusions): secrets,
settings, logs, caches. Run on desktop as part of the release pipeline:

    python3 scripts/make_manifest.py src/ out/ --root /src --version 1.96
    python3 scripts/make_manifest.py code.py out/ --root / --version 1.96   # add top-level files

Copyright 2024 3DUPFitters LLC
"""
import argparse
import hashlib
import json
import os
import shutil

# Never ship these to fielded devices (review B3 / ota-release.md).
EXCLUDE_NAMES = {"secrets.py", "settings.json", "error_log", ".DS_Store", "credentials.json"}
EXCLUDE_DIRS = {"__pycache__", "logs", ".git"}
EXCLUDE_SUFFIXES = (".pyc", ".log", ".old.py")


def _excluded(name):
    return (name in EXCLUDE_NAMES or name.endswith(EXCLUDE_SUFFIXES))


def build_manifest(src, out_dir, *, device_root="/src", version="0.0.0"):
    """Walk ``src`` → return a manifest dict and copy payload under ``out_dir/files``.

    ``device_root`` is the on-device path prefix for the manifest keys (e.g. files
    under ``src/`` install to ``/src/...``). ``src`` may be a file or a directory.
    Returns the manifest dict (also written to ``out_dir/manifest.json``).
    """
    files = {}
    manifest_path = os.path.join(out_dir, "manifest.json")
    # Merge with an existing manifest so multiple invocations accumulate files.
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path) as f:
                files = json.load(f).get("files", {})
        except (OSError, ValueError):
            files = {}

    pairs = []  # (abs_src_path, device_path)
    if os.path.isfile(src):
        pairs.append((src, _join_device(device_root, os.path.basename(src))))
    else:
        for root, dirs, names in os.walk(src):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for name in names:
                if _excluded(name):
                    continue
                abs_path = os.path.join(root, name)
                rel = os.path.relpath(abs_path, src)
                pairs.append((abs_path, _join_device(device_root, rel)))

    for abs_path, device_path in pairs:
        with open(abs_path, "rb") as f:
            content = f.read()
        files[device_path] = {
            "size": len(content),
            "checksum": hashlib.sha256(content).hexdigest(),
        }
        dest = os.path.join(out_dir, "files", device_path.lstrip("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(abs_path, dest)

    manifest = {"version": version, "files": files,
                "pre_update_scripts": [], "post_update_scripts": []}
    os.makedirs(out_dir, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def _join_device(root, rel):
    rel = rel.replace(os.sep, "/")
    if not root.endswith("/"):
        root = root + "/"
    return (root + rel).replace("//", "/")


def _default_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "src", ".version")) as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def main(argv=None):
    p = argparse.ArgumentParser(description="Build a ThemeParkWaits OTA manifest")
    p.add_argument("src", help="source file or directory")
    p.add_argument("out", help="output dir (manifest.json + files/)")
    p.add_argument("--root", default="/src", help="on-device path prefix (default /src)")
    p.add_argument("--version", default=None, help="release version (default: src/.version)")
    args = p.parse_args(argv)
    version = args.version or _default_version()
    m = build_manifest(args.src, args.out, device_root=args.root, version=version)
    print("manifest %s: %d files -> %s" % (version, len(m["files"]), args.out))


if __name__ == "__main__":
    main()
