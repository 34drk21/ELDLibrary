# setup_dirs.py
import os
import pathlib

BASE_DIR = pathlib.Path(__file__).parent.resolve()
PROJECTS_DIR = BASE_DIR / "projects"
THUMB_DIR    = BASE_DIR / "thumbs"

def main():
    # プロジェクト用のフォルダ
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Projects dir: {PROJECTS_DIR}")

    # サムネイル用のフォルダ
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Thumbs dir: {THUMB_DIR}")

    # デモ用にプロジェクトをいくつか作る
    demo_proj = PROJECTS_DIR / "DemoProject"
    demo_proj.mkdir(parents=True, exist_ok=True)

    # ダミーファイル作成
    (demo_proj / "cache.abc").write_text("dummy alembic file")
    (demo_proj / "smoke.vdb").write_text("dummy vdb file")
    (demo_proj / "geo.bgeo").write_text("dummy bgeo file")

    print(f"[OK] DemoProject initialized with dummy files")

if __name__ == "__main__":
    main()
