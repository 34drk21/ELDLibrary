# -*- coding: utf-8 -*-
# ELD CPIO Exporter (dup-check: overwrite or auto-increment)
# 依存: requests, Pillow (PIL)

import os, io, tempfile
from functools import partial

import hou
from PySide6 import QtWidgets, QtCore, QtGui
from PIL import Image

# ======== 設定 ========
API_BASE = "http://127.0.0.1:8080"  # Tailscale/公開時はここを置換
TIMEOUT  = 20

# ===================== API Client =====================
class ApiClient(object):
    def __init__(self, base):
        self.base = base.rstrip("/")
        self._requests = self._import_requests()
        self.token = None
        self.project = None

    def _import_requests(self):
        try:
            import requests
            return requests
        except Exception:
            raise RuntimeError("Python 'requests' が必要です。")

    def list_projects(self):
        r = self._requests.get(f"{self.base}/projects", timeout=TIMEOUT)
        r.raise_for_status()
        raw = r.json().get("projects", [])
        return [p for p in raw if p and not p.startswith(".") and p not in ("Script","Scripts")]

    def login(self, project: str, password: str):
        r = self._requests.post(f"{self.base}/auth/login",
                                json={"project": project, "password": password},
                                timeout=TIMEOUT)
        r.raise_for_status()
        self.token = r.json()["token"]
        self.project = project
        return self.token

    def manifest(self):
        if not self.token:
            raise RuntimeError("Not authenticated")
        r = self._requests.get(f"{self.base}/manifest",
                               headers={"Authorization": f"Bearer {self.token}"},
                               timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def upload_file(self, rel_path: str, local_path: str):
        if not (self.project and self.token):
            raise RuntimeError("Not authenticated")
        url = f"{self.base}/upload"
        headers = {"Authorization": f"Bearer {self.token}"}
        files = {"file": (os.path.basename(local_path), open(local_path, "rb"))}
        data  = {"path": rel_path}
        try:
            r = self._requests.post(url, headers=headers, data=data, files=files, timeout=120)
            r.raise_for_status()
        finally:
            try: files["file"][1].close()
            except Exception: pass
        return True

# ===================== 便利関数 =====================
def _context_of(node):
    try:
        return node.type().category().name().lower()  # sop/vop/dop/...
    except Exception:
        return "unknown"

def _save_cpio_to_tmp(name: str, nodes):
    path = nodes[0].path()
    parent = "/".join(path.split("/")[:-1])
    contextnode = hou.node(parent)
    tmp = os.path.join(tempfile.gettempdir(), f"{name}.cpio")
    contextnode.saveItemsToFile(nodes, tmp, save_hda_fallbacks=False)
    return tmp

def _save_clipboard_thumb(tmp_base_noext: str) -> str | None:
    cb = QtWidgets.QApplication.clipboard()
    qimg = cb.image()
    if qimg.isNull():
        return None
    pix = QtGui.QPixmap.fromImage(qimg)
    buf = QtCore.QBuffer(); buf.open(QtCore.QIODevice.WriteOnly)
    pix.save(buf, "PNG")
    data = bytes(buf.data())
    img = Image.open(io.BytesIO(data)).convert("RGB").resize((512,512), Image.LANCZOS)
    out = tmp_base_noext + ".jpg"
    img.save(out, "JPEG", quality=90)
    return out

def _paths_for(ctx: str, base_name: str):
    """rel-paths for cpio & thumb"""
    rel_cpio  = f"cpio/{ctx}/{base_name}.cpio"
    rel_thumb = f"thumbs/{base_name}.jpg"
    return rel_cpio, rel_thumb

def _uniquify_base(ctx: str, base_name: str, existing_paths: set[str]) -> str:
    """existing_paths に被らない base_name_### を返す"""
    i = 1
    while True:
        cand = f"{base_name}_{i:03d}"
        rel1, rel2 = _paths_for(ctx, cand)
        if (rel1 not in existing_paths) and (rel2 not in existing_paths):
            return cand
        i += 1

# ===================== メインUI =====================
class ExportDlg(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or hou.qt.mainWindow())
        self.api = ApiClient(API_BASE)
        self.setWindowTitle("ELD CPIO Export")
        self.setModal(False)
        self.setFixedSize(420, 240)

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(14,14,14,14)
        v.setSpacing(10)

        # プロジェクト行
        projRow = QtWidgets.QHBoxLayout()
        projRow.addWidget(QtWidgets.QLabel("Project:", self))
        self.cmbProject = QtWidgets.QComboBox(self)
        self.cmbProject.setMinimumWidth(260)
        projRow.addWidget(self.cmbProject, 1)
        self.btnReload = QtWidgets.QPushButton("Reload")
        self.btnReload.clicked.connect(self.reload_projects)
        projRow.addWidget(self.btnReload)
        v.addLayout(projRow)

        # 名前
        self.edName = QtWidgets.QLineEdit(self)
        self.edName.setPlaceholderText("Export name (例: fire_setup)")
        v.addWidget(self.edName)

        # ヒント
        hint = QtWidgets.QLabel("Thumbnails get from Clipboard（Win+Shift+S → excute）", self)
        hint.setStyleSheet("color:#aaa; font-size:11px;")
        v.addWidget(hint)

        # ボタン
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.btnExport = QtWidgets.QPushButton("Export")
        self.btnExport.clicked.connect(self.on_export)
        row.addWidget(self.btnExport)
        v.addLayout(row)

        # 初回ロード
        self.reload_projects()

    def reload_projects(self):
        self.cmbProject.clear()
        try:
            projs = self.api.list_projects()
        except Exception as e:
            hou.ui.displayMessage(f"/projects failed to get: {e}")
            return
        if not projs:
            self.cmbProject.addItem("(no projects)")
            self.cmbProject.setEnabled(False)
        else:
            self.cmbProject.setEnabled(True)
            self.cmbProject.addItems(sorted(projs))

    def on_export(self):
        sel = hou.selectedNodes()
        if not sel:
            hou.ui.displayMessage("please select nodes."); return
        name = (self.edName.text() or "").strip()
        if not name:
            hou.ui.displayMessage("file name is empty."); return
        project = self.cmbProject.currentText()
        if not project or project == "(no projects)":
            hou.ui.displayMessage("select project"); return

        # 認証
        pw, ok = QtWidgets.QInputDialog.getText(self, "Sign in",
                                                f"Password for '{project}'",
                                                QtWidgets.QLineEdit.Password)
        if not ok:
            return
        try:
            self.api.login(project, pw)
        except Exception as e:
            hou.ui.displayMessage(f"failed to log in: {e}")
            return

        # 既存ファイルの有無を /manifest で確認
        try:
            mani = self.api.manifest()
        except Exception as e:
            hou.ui.displayMessage(f"manifest failed to get: {e}")
            return

        existing = { (a.get("path") or "") for a in mani.get("assets", []) }

        ctx = _context_of(sel[0])  # sop/vop/dop...
        base_name = f"{ctx}_{name}"
        rel_cpio, rel_thumb = _paths_for(ctx, base_name)

        # 衝突するか？
        if (rel_cpio in existing) or (rel_thumb in existing):
            ret = QtWidgets.QMessageBox.question(
                self, "the file is aleady exist.",
                f"the same name file is already exist\n\n"
                f"CPIO : {rel_cpio if rel_cpio in existing else '(none)'}\n"
                f"Thumb: {rel_thumb if rel_thumb in existing else '(none)'}\n\n"
                f"do you want to override？\n"
                f"[yes] … override\n"
                f"[No] … save with incremanted number",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if ret == QtWidgets.QMessageBox.No:
                base_name = _uniquify_base(ctx, base_name, existing)
                rel_cpio, rel_thumb = _paths_for(ctx, base_name)

        # CPIO を一時保存
        tmp_cpio = _save_cpio_to_tmp(base_name, sel)
        tmp_thumb = _save_clipboard_thumb(os.path.splitext(tmp_cpio)[0])  # ある時だけ

        # アップロード
        try:
            self.api.upload_file(rel_cpio, tmp_cpio)
            if tmp_thumb and os.path.exists(tmp_thumb):
                self.api.upload_file(rel_thumb, tmp_thumb)
        except Exception as e:
            hou.ui.displayMessage(f"failed to upload: {e}")
            return

        hou.ui.displayMessage(
            f"upload complited！\n"
            f"Project : {project}\n"
            f"CPIO   : {rel_cpio}\n"
            f"Thumb  : {os.path.basename(tmp_thumb) if tmp_thumb else '(none)'}"
        )
        self.close()

def main():
    dlg = ExportDlg()
    dlg.show()

main()
