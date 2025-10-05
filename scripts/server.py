# server.py
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os, pathlib, shutil
import bcrypt

BASE_DIR = pathlib.Path(__file__).parent.resolve()
PROJECTS_DIR = BASE_DIR / "projects"   # プロジェクトルート
TOKENS: dict[str, str] = {}            # {project: token} 超簡易セッション

app = FastAPI(title="ELD Library API")

# -----------------------
# モデル
# -----------------------
class LoginRequest(BaseModel):
    project: str
    password: str

# -----------------------
# パスワード関連ユーティリティ
# -----------------------
def _passwd_path(project: str) -> pathlib.Path:
    return PROJECTS_DIR / project / ".passwd"

def _has_passwd(project: str) -> bool:
    return _passwd_path(project).exists()

def _verify_password(project: str, plain_password: str) -> bool:
    """
    projects/<project>/.passwd を読み、bcryptで検証。
    - .passwd が存在しなければ False
    - 中身が bcrypt ではない（旧環境）の場合は「生文字列一致」も許容（互換目的）
    """
    p = _passwd_path(project)
    if not p.exists():
        return False
    raw = p.read_bytes().strip()
    # bcrypt 文字列はだいたい $2a/$2b などで始まる
    try:
        if raw.startswith(b"$2"):
            return bcrypt.checkpw(plain_password.encode("utf-8"), raw)
        else:
            # 互換（平文格納だった場合）
            return plain_password.encode("utf-8") == raw
    except Exception:
        return False

def _require_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization.split(" ", 1)[1]

def _project_from_token(token: str) -> str:
    for k, v in TOKENS.items():
        if v == token:
            return k
    raise HTTPException(status_code=401, detail="Invalid token")

# -----------------------
# エンドポイント
# -----------------------
@app.get("/projects")
def list_projects():
    if not PROJECTS_DIR.exists():
        return {"projects": []}
    projects = [
        p.name for p in PROJECTS_DIR.iterdir()
        if p.is_dir()
        and not p.name.startswith(".")
        and p.name not in ("Script", "Scripts")
    ]
    return {"projects": projects}

@app.post("/auth/login")
def login(req: LoginRequest):
    proj_dir = PROJECTS_DIR / req.project
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    if not _has_passwd(req.project):
        # .passwd 未作成なら拒否（必要に応じて 200 で通す運用も可）
        raise HTTPException(status_code=401, detail="Password not set for project")

    if not _verify_password(req.project, req.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    token = f"token-{req.project}"
    TOKENS[req.project] = token
    return {"token": token}

@app.get("/manifest")
def manifest(authorization: str = Header(None)):
    token = _require_bearer(authorization)
    proj = _project_from_token(token)

    proj_dir = PROJECTS_DIR / proj
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    # 簡易スキャン版の manifest 生成
    exts = {"bgeo", "abc", "vdb", "cpio", "jpg", "png"}
    assets = []
    for root, _dirs, files in os.walk(proj_dir):
        for fname in files:
            ext = pathlib.Path(fname).suffix.lower().lstrip(".")
            if ext not in exts:
                continue
            abspath = pathlib.Path(root) / fname
            relpath = abspath.relative_to(proj_dir).as_posix()
            assets.append({
                "id": pathlib.Path(fname).stem,
                "type": ext,
                "version": 1,
                "path": relpath,
                "thumb": relpath if ext in ("jpg", "png") else None,
                "bytes_total": abspath.stat().st_size,
            })
    return {"assets": assets}

@app.get("/download")
def download(path: str, authorization: str = Header(None)):
    token = _require_bearer(authorization)
    proj = _project_from_token(token)

    fpath = (PROJECTS_DIR / proj / path).resolve()
    # ルート外参照の防止
    if not str(fpath).startswith(str((PROJECTS_DIR / proj).resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(fpath)

@app.post("/upload")
def upload(path: str = Form(...),
           file: UploadFile = File(...),
           authorization: str = Header(None)):
    token = _require_bearer(authorization)
    proj = _project_from_token(token)

    # パス検証（プロジェクト外に出ない & 禁止文字をざっくり排除）
    rel = pathlib.Path(path.replace("\\", "/")).as_posix().lstrip("/")
    if ".." in rel or rel.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    dest = (PROJECTS_DIR / proj / rel).resolve()
    root = (PROJECTS_DIR / proj).resolve()
    if not str(dest).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")

    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"ok": True, "saved": str(dest.relative_to(root)).replace("\\", "/")}