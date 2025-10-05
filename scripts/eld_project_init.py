# eld_project_init.py
# Create ELDLibrary project skeletons under ~/Documents/ELDLibrary (default)
# - Folders: bgeo, vdb, abc, cpio/<contexts>
# - manifest.json stub
# - optional .passwd (bcrypt hash) per project

import os, sys, json, pathlib, getpass, argparse

try:
    import bcrypt  # optional; only needed if --set-password
except Exception:
    bcrypt = None

CONTEXTS = ["sop", "vop", "dop", "obj", "rop", "shop", "chop", "cop2", "lop", "top"]

def default_root():
    home = pathlib.Path.home()
    docs = home / "Documents"
    eld = docs / "ELDLibrary"
    eld.mkdir(parents=True, exist_ok=True)
    return str(eld)

def make_dirs(root, project):
    proj = os.path.join(root, project)
    paths = [
        f"{proj}/bgeo",
        f"{proj}/vdb",
        f"{proj}/abc",
        f"{proj}/cpio",
        f"{proj}/thumbs",               # 任意：サムネ置き場（必要なら）
    ] + [f"{proj}/cpio/{c}" for c in CONTEXTS]
    for p in paths:
        os.makedirs(p, exist_ok=True)
    return proj

def write_manifest_stub(proj_path, project):
    manifest_path = os.path.join(proj_path, "manifest.json")
    if not os.path.exists(manifest_path):
        data = {"project": project, "updated_at": None, "assets": []}
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return manifest_path

def set_password(proj_path, project):
    if bcrypt is None:
        print("[WARN] bcrypt が見つかりません。'pip install bcrypt' を実行するか、--set-password を外してください。")
        return
    pw1 = getpass.getpass(f"[{project}] New password: ")
    pw2 = getpass.getpass(f"[{project}] Repeat      : ")
    if not pw1 or pw1 != pw2:
        print("[ERR ] Password mismatch / empty. Skip.")
        return
    hashed = bcrypt.hashpw(pw1.encode(), bcrypt.gensalt())
    with open(os.path.join(proj_path, ".passwd"), "wb") as f:
        f.write(hashed)
    print(f"[ OK ] .passwd written: {proj_path}")

def main():
    ap = argparse.ArgumentParser(description="Init ELDLibrary project skeleton(s).")
    ap.add_argument("projects", nargs="+", help="Project IDs to create, e.g., PROJECT_A PROJECT_B")
    ap.add_argument("--root", default=default_root(), help="Base library root (default: ~/Documents/ELDLibrary)")
    ap.add_argument("--set-password", action="store_true", help="Create .passwd for each project (requires 'bcrypt')")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    print(f"[INFO] Root: {root}")
    if not os.path.exists(root):
        if args.dry_run:
            print(f"Would create root: {root}")
        else:
            os.makedirs(root, exist_ok=True)

    for project in args.projects:
        proj_path = os.path.join(root, project)
        if args.dry_run:
            print(f"Would create: {proj_path}")
            print("  - bgeo, vdb, abc, cpio/<" + ",".join(CONTEXTS) + ">, thumbs, manifest.json")
            continue

        proj_path = make_dirs(root, project)
        man = write_manifest_stub(proj_path, project)
        print(f"[ OK ] Project ready: {proj_path}")
        print(f"       manifest: {man}")
        if args.set_password:
            set_password(proj_path, project)

    print("[DONE] Initialization complete.")

if __name__ == "__main__":
    main()
