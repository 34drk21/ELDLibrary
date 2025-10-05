# -*- coding: utf-8 -*-
# ELD Browser (rev: 16:9 true cards, no delete button, rounded right thumb)
# Uses: /projects, /auth/login, /manifest (Bearer), /download

import os, pathlib, re, tempfile
import hou
from functools import partial
from PySide6 import QtCore, QtWidgets, QtGui

# ========= CONFIG =========
API_BASE  = "http://127.0.0.1:8080/"  # ex) http://100.xx.xx.xx:8080
THUMB_CACHE_DIR = str((pathlib.Path.home()/ "Documents" / "ELDLibrary" / ".thumbcache")).replace("\\","/")
CONTEXTS = ["sop","vop","dop","obj","rop","shop","chop","cop2","lop","top"]

# ========= UTILS =========
def ensure_thumb_cache():
    pathlib.Path(THUMB_CACHE_DIR).mkdir(parents=True, exist_ok=True)

def thumb_cache_path(rel_thumb: str) -> str:
    safe = rel_thumb.replace("/", "_")
    return f"{THUMB_CACHE_DIR}/{safe}"

def human_bytes(n) -> str:
    try: n = float(n)
    except Exception: return "-"
    for unit in ["B","KB","MB","GB","TB","PB"]:
        if n < 1024.0: return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}EB"

def infer_context_from_path(path: str) -> str:
    m = re.search(r"(?:^|/)cpio/([^/]+)/", (path or "").replace("\\","/"))
    return (m.group(1).lower() if m else "")

def rounded_pixmap(src: QtGui.QPixmap, radius: int) -> QtGui.QPixmap:
    if src.isNull(): return src
    pm = QtGui.QPixmap(src.size()); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    path = QtGui.QPainterPath(); path.addRoundedRect(QtCore.QRectF(0,0,src.width(),src.height()), radius, radius)
    p.setClipPath(path); p.drawPixmap(0,0,src); p.end()
    return pm

def placeholder_thumb(kind: str, w: int, h: int, radius: int=12) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(w, h); pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing)
    color = {
        "abc": QtGui.QColor(90,180,255),
        "vdb": QtGui.QColor(170,200,120),
        "bgeo": QtGui.QColor(255,170,110),
        "cpio": QtGui.QColor(200,160,240),
    }.get((kind or "").lower(), QtGui.QColor(200,200,200))
    p.setBrush(color); p.setPen(QtCore.Qt.NoPen)
    r = QtCore.QRectF(0,0,w,h); p.drawRoundedRect(r, radius, radius)
    font = QtGui.QFont(); font.setBold(True); font.setPointSize(int(min(w,h)*0.20))
    p.setPen(QtGui.QColor(30,30,30)); p.setFont(font)
    txt = (kind or "ASST").upper()[:5]; p.drawText(r, QtCore.Qt.AlignCenter, txt)
    p.end(); return pm

# ========= API CLIENT =========
class ApiClient(object):
    def __init__(self, api_base: str):
        self.api_base = api_base.rstrip("/")
        self._requests = self._import_requests()
        self.tokens = {}  # {project: token}

    def _import_requests(self):
        try:
            import requests
            return requests
        except Exception:
            raise RuntimeError("Python 'requests' が必要です（HoudiniのPython環境）。")

    def list_projects(self):
        r = self._requests.get(f"{self.api_base}/projects", timeout=10)
        r.raise_for_status()
        raw = r.json().get("projects", [])
        # 先頭が '.' と 'Script' / 'Scripts' を除外
        return [p for p in raw if p and not p.startswith(".") and p not in ("Script", "Scripts")]

    def login(self, project: str, password: str):
        r = self._requests.post(f"{self.api_base}/auth/login",
                                json={"project": project, "password": password},
                                timeout=10)
        r.raise_for_status()
        tok = r.json()["token"]
        self.tokens[project] = tok
        return tok

    def manifest(self, project: str):
        tok = self.tokens.get(project)
        if not tok:
            raise RuntimeError("Not signed in")
        r = self._requests.get(f"{self.api_base}/manifest",
                               headers={"Authorization": f"Bearer {tok}"},
                               timeout=15)
        r.raise_for_status()
        return r.json()

    def download_file(self, project: str, rel_path: str, dst_path: str):
        tok = self.tokens.get(project)
        headers = {"Authorization": f"Bearer {tok}"} if tok else {}
        url = f"{self.api_base}/download"
        params = {"path": rel_path}
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with self._requests.get(url, headers=headers, params=params, stream=True, timeout=60) as r:
            r.raise_for_status()
            tmp = dst_path + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk: f.write(chunk)
            os.replace(tmp, dst_path)

# ========= BIG TOGGLE =========
class BigToggle(QtWidgets.QToolButton):
    def __init__(self, text, on_color="#3fa76d", off_color="#3a3f45",
                 text_color="#e8e8e8", parent=None, checked=True, w=85, h=30):
        super().__init__(parent)
        self.setText(text); self.setCheckable(True); self.setChecked(checked)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumWidth(w); self.setFixedHeight(h)
        self._on=on_color; self._off=off_color; self._text=text_color
        self.setStyleSheet(f"""
            QToolButton {{
                border: 0px; padding: 6px 12px; border-radius: 9px;
                color: {self._text}; background-color: {self._on};
                font-weight: 600; font-size: 13px;
            }}
            QToolButton:checked {{ background-color: {self._on}; }}
            QToolButton:!checked {{ background-color: {self._off}; color: #bfc5cc; }}
        """)

# ========= THUMB CARD (16:9 真カード) =========
class ThumbCard(QtWidgets.QWidget):
    def __init__(self, pixmap: QtGui.QPixmap, title: str, subtitle: str, w: int, h: int, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(6,6,6,6); lay.setSpacing(6)

        self.img = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
        self.img.setFixedSize(w, h)
        self.img.setPixmap(pixmap)
        self.img.setStyleSheet("border:0px;")
        lay.addWidget(self.img, 0, QtCore.Qt.AlignHCenter)

        lab = QtWidgets.QLabel(f"{title}\n{subtitle}")
        lab.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        lab.setStyleSheet("QLabel{color:#dde2e6; font-size:11px;}")
        lay.addWidget(lab)

        self.setStyleSheet("QWidget{background:transparent;}")

# ========= MAIN UI =========
class EldBrowser(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(EldBrowser, self).__init__(parent)
        self.setWindowTitle("ELD Library")
        self.resize(600, 600)
        self.setStyleSheet("""
            QWidget { background-color: #1f2227; color: #e8e8e8; }
            QLineEdit, QPlainTextEdit, QListWidget {
                background-color: #252a31; border: 1px solid #2e343d; border-radius: 10px;
                selection-background-color: #344054;
            }
            QLabel#hint { color:#a7b0ba; font-size:12px; }
            QSplitter::handle { background: #2b313a; }
        """)

        self.api = ApiClient(API_BASE)

        # state
        self.current_project = None
        self.current_assets  = []
        self.types_on = {"vdb": True, "abc": True, "bgeo": True, "cpio": True}
        self.ctx_on   = {c: True for c in CONTEXTS}
        self._sync_types = False; self._sync_ctx = False

        # 16:9 thumbs (grid)
        self.thumb_w = 220
        self.thumb_h = int(self.thumb_w * 9 / 16)  # 16:9
        self.card_w  = self.thumb_w + 24
        self.card_h  = self.thumb_h + 72

        # Right big thumb (rounded)
        self.info_w = 340
        self.info_h = int(self.info_w * 9 / 16)

        # ===== layout =====
        outer = QtWidgets.QVBoxLayout(self)
        self.split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        outer.addWidget(self.split, 1)

        # Left: projects
        left = QtWidgets.QWidget(); llay = QtWidgets.QVBoxLayout(left); llay.setContentsMargins(8,8,8,8)
        llay.addWidget(QtWidgets.QLabel("Projects", objectName="hint"))
        self.projectList = QtWidgets.QListWidget()
        self.projectList.currentTextChanged.connect(self.on_project_selected)
        self.projectList.setMinimumWidth(200)
        llay.addWidget(self.projectList, 1)
        self.split.addWidget(left)

        # Center
        center = QtWidgets.QWidget(); cLay = QtWidgets.QVBoxLayout(center)
        cLay.setContentsMargins(8,8,8,8); cLay.setSpacing(8)

        self.edSearch = QtWidgets.QLineEdit()
        self.edSearch.setPlaceholderText("Search id/path/version …")
        self.edSearch.textChanged.connect(self.refresh_grid)
        self.edSearch.setFixedHeight(42)
        self.edSearch.setStyleSheet("QLineEdit{font-size:15px;padding:8px 12px;}")
        cLay.addWidget(self.edSearch)

        # Type toggles
        typeRowW = QtWidgets.QWidget()
        typeRow  = QtWidgets.QHBoxLayout(typeRowW); typeRow.setContentsMargins(0,0,0,0)
        self.btAllTypes = BigToggle("All")
        self.btVDB  = BigToggle("VDB"); self.btABC  = BigToggle("Alembic")
        self.btBGEO = BigToggle("BGEO"); self.btCPIO = BigToggle("CPIO")
        for w in (self.btAllTypes,self.btVDB,self.btABC,self.btBGEO,self.btCPIO): typeRow.addWidget(w)
        typeRow.addStretch(1); cLay.addWidget(typeRowW)
        self.btAllTypes.toggled.connect(self.on_all_types)
        self.btVDB.toggled.connect(partial(self.on_type_toggle,"vdb"))
        self.btABC.toggled.connect(partial(self.on_type_toggle,"abc"))
        self.btBGEO.toggled.connect(partial(self.on_type_toggle,"bgeo"))
        self.btCPIO.toggled.connect(partial(self.on_type_toggle,"cpio"))

        # Context toggles (no label text; only when CPIO on)
        self.ctxRowParent = QtWidgets.QWidget()
        ctxLay = QtWidgets.QHBoxLayout(self.ctxRowParent); ctxLay.setContentsMargins(0,0,0,0)
        self.btCtxAll = BigToggle("All")
        self.btCtxAll.toggled.connect(self.on_all_ctx)
        ctxLay.addWidget(self.btCtxAll)
        self.ctxButtons = {}
        for c in CONTEXTS:
            b = BigToggle(c.upper())
            b.toggled.connect(partial(self.on_ctx_toggle, c))
            self.ctxButtons[c] = b
            ctxLay.addWidget(b)
        ctxLay.addStretch(1)
        cLay.addWidget(self.ctxRowParent)
        self.ctxRowParent.setVisible(True)

        # Grid (use custom 16:9 card widgets)
        self.grid = QtWidgets.QListWidget()
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setWrapping(True)
        self.grid.setSpacing(10)
        self.grid.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.grid.itemSelectionChanged.connect(self.on_grid_selection_changed)
        cLay.addWidget(self.grid, 1)
        self.split.addWidget(center)

        # Right: info (rounded big thumb + compact labels + Load)
        right = QtWidgets.QWidget(); r = QtWidgets.QVBoxLayout(right)
        r.setContentsMargins(8,8,8,8); r.setSpacing(8)
        self.infoThumb = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
        self.infoThumb.setFixedSize(self.info_w, self.info_h)
        # label自体は枠線のみ。角丸は画像自体をrounded_pixmapで実現
        self.infoThumb.setStyleSheet("border:1px solid #2e343d; border-radius:12px;")
        r.addWidget(self.infoThumb, 0, QtCore.Qt.AlignHCenter)

        # compact info labels
        grid = QtWidgets.QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(4)
        def val_label():
            lab = QtWidgets.QLabel()
            lab.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            lab.setStyleSheet("QLabel{background:#252a31; border:1px solid #2e343d; border-radius:6px; padding:4px 6px; font-size:12px;}")
            return lab
        key_style = "QLabel{color:#a7b0ba; font-size:12px;}"
        def add_row(i, key, widget):
            k = QtWidgets.QLabel(key); k.setStyleSheet(key_style)
            grid.addWidget(k, i, 0); grid.addWidget(widget, i, 1)

        self.lbProj  = val_label();  add_row(0, "Project", self.lbProj)
        self.lbId    = val_label();  add_row(1, "ID",      self.lbId)
        self.lbType  = val_label();  add_row(2, "Type",    self.lbType)
        self.lbFrames= val_label();  add_row(3, "Frames",  self.lbFrames)
        self.lbBytes = val_label();  add_row(4, "Size",    self.lbBytes)
        self.lbVer   = val_label();  add_row(5, "Version", self.lbVer)
        self.lbPath  = QtWidgets.QPlainTextEdit(); self.lbPath.setReadOnly(True); self.lbPath.setFixedHeight(74)
        self.lbPath.setStyleSheet("QPlainTextEdit{background:#252a31; border:1px solid #2e343d; border-radius:6px; padding:6px; font-size:12px;}")
        grid.addWidget(QtWidgets.QLabel("Path", styleSheet=key_style), 6, 0); grid.addWidget(self.lbPath, 6, 1)
        r.addLayout(grid, 0)

        r.addStretch(1)

        # Buttons row (Load only)
        btnRow = QtWidgets.QHBoxLayout()
        self.btnLoad = BigToggle("Load", on_color="#4c8bf5", w=130, h=36)
        self.btnLoad.setCheckable(False)
        self.btnLoad.clicked.connect(self.on_load_clicked)
        btnRow.addStretch(1); btnRow.addWidget(self.btnLoad); btnRow.addStretch(1)
        r.addLayout(btnRow)

        self.split.addWidget(right)
        right.setMinimumWidth(400)

        # 初期ロード（起動時はパスワードを聞かない）
        self.reload_projects()

    # ===== Projects =====
    def reload_projects(self):
        self.projectList.clear()
        try:
            projs = self.api.list_projects()
        except Exception as e:
            hou.ui.displayMessage(f"/projects 取得に失敗: {e}")
            return
        if not projs: return
        self.projectList.addItems(sorted(projs))
        self.projectList.setCurrentRow(-1)

    def on_project_selected(self, project: str):
        if not project: return
        pw, ok = QtWidgets.QInputDialog.getText(self, "Sign in",
                                                f"Password for '{project}'",
                                                QtWidgets.QLineEdit.Password)
        if not ok: return
        try:
            self.api.login(project, pw)
            mani = self.api.manifest(project)
        except Exception as e:
            hou.ui.displayMessage(f"Sign-in/Manifest error: {e}")
            return
        self.current_project = project
        self.current_assets  = list(mani.get("assets", []))
        self.lbProj.setText(project)
        self.edSearch.setText("")
        self.refresh_grid()

    # ===== Type toggles =====
    def on_all_types(self, checked: bool):
        if self._sync_types: return
        self._sync_types = True
        try:
            for key, btn in [("vdb",self.btVDB),("abc",self.btABC),("bgeo",self.btBGEO),("cpio",self.btCPIO)]:
                btn.setChecked(checked); self.types_on[key] = checked
            self.ctxRowParent.setVisible(self.btCPIO.isChecked())
            self.refresh_grid()
        finally:
            self._sync_types = False

    def on_type_toggle(self, typ: str, checked: bool):
        if self._sync_types: return
        self.types_on[typ] = checked
        self._sync_types = True
        try:
            all_on  = all([self.btVDB.isChecked(), self.btABC.isChecked(), self.btBGEO.isChecked(), self.btCPIO.isChecked()])
            all_off = not any([self.btVDB.isChecked(), self.btABC.isChecked(), self.btBGEO.isChecked(), self.btCPIO.isChecked()])
            if all_on or all_off: self.btAllTypes.setChecked(all_on)
            self.ctxRowParent.setVisible(self.btCPIO.isChecked())
        finally:
            self._sync_types = False
        self.refresh_grid()

    # ===== Context toggles =====
    def on_all_ctx(self, checked: bool):
        if self._sync_ctx: return
        self._sync_ctx = True
        try:
            for c, btn in self.ctxButtons.items():
                btn.setChecked(checked); self.ctx_on[c] = checked
            self.refresh_grid()
        finally:
            self._sync_ctx = False

    def on_ctx_toggle(self, ctx: str, checked: bool):
        if self._sync_ctx: return
        self.ctx_on[ctx] = checked
        self._sync_ctx = True
        try:
            all_on  = all(btn.isChecked() for btn in self.ctxButtons.values())
            all_off = not any(btn.isChecked() for btn in self.ctxButtons.values())
            if all_on or all_off: self.btCtxAll.setChecked(all_on)
        finally:
            self._sync_ctx = False
        self.refresh_grid()

    # ===== Grid / Info =====
        # ===== Grid / Info =====
    def _make_thumb_pm(self, a: dict, w: int, h: int) -> QtGui.QPixmap:
        """
        1) asset['thumb'] があればそれを使う
        2) 無ければ、asset['path'] のベース名から
           thumbs/<basename>.jpg|.png を順に探して使う
        3) どれも無ければプレースホルダー
        """
        ensure_thumb_cache()

        # 候補を並べる
        candidates = []
        # 1) manifest に thumb がある場合
        rel = a.get("thumb")
        if rel:
            candidates.append(rel)

        # 2) 同名サムネ（thumbs/<basename>.jpg|.png）
        apath = (a.get("path") or "").replace("\\", "/")
        base  = os.path.splitext(os.path.basename(apath))[0]
        if base:
            candidates.extend([
                f"thumbs/{base}.jpg",
                f"thumbs/{base}.png",
            ])

        # 候補を順にトライ
        for rel_thumb in candidates:
            cache = thumb_cache_path(rel_thumb)
            # 未キャッシュならサーバから取得を試す
            if not os.path.exists(cache):
                try:
                    # 認証済みプロジェクトからダウンロード
                    self.api.download_file(self.current_project, rel_thumb, cache)
                except Exception:
                    # 404/401 等は無視して次の候補へ
                    pass

            # キャッシュが手に入っていればサムネ生成
            if os.path.exists(cache):
                qpm = QtGui.QPixmap(cache)
                if not qpm.isNull():
                    scaled = qpm.scaled(QtCore.QSize(w, h),
                                        QtCore.Qt.KeepAspectRatioByExpanding,
                                        QtCore.Qt.SmoothTransformation)
                    return rounded_pixmap(scaled, 12)

        # 3) すべて失敗 → プレースホルダー
        return placeholder_thumb(a.get("type",""), w, h, 12)


    def refresh_grid(self):
        self.grid.clear()
        self._clear_info()
        if not self.current_assets: return
        q = self.edSearch.text().lower().strip()

        def accept(a: dict) -> bool:
            typ = (a.get("type","") or "").lower()
            if not self.types_on.get(typ, False): return False
            blob = f"{a.get('id','')} {a.get('path','')} v{a.get('version','')}"
            if q and (q not in blob.lower()): return False
            if typ == "cpio" and self.types_on.get("cpio", False):
                ctx = (a.get("context") or infer_context_from_path(a.get("path",""))).lower()
                if ctx and not self.ctx_on.get(ctx, False): return False
            return True

        for a in self.current_assets:
            if not accept(a): continue
            typ = a.get("type","")
            title = a.get("id") or os.path.basename(a.get("path","")) or "(no id)"
            ver = a.get("version")
            sub = f"{typ}  v{ver}" if ver is not None else typ

            pm = self._make_thumb_pm(a, self.thumb_w, self.thumb_h)
            card = ThumbCard(pm, title, sub, self.thumb_w, self.thumb_h)

            it = QtWidgets.QListWidgetItem()
            it.setSizeHint(QtCore.QSize(self.card_w, self.card_h))
            it.setData(QtCore.Qt.UserRole, a)
            self.grid.addItem(it)
            self.grid.setItemWidget(it, card)

    def on_grid_selection_changed(self):
        items = self.grid.selectedItems()
        if not items:
            self._clear_info(); return
        a = items[0].data(QtCore.Qt.UserRole)
        self._set_info(a)

    # ===== Info panel =====
    def _clear_info(self):
        self.infoThumb.clear()
        for lab in (self.lbProj,self.lbId,self.lbType,self.lbFrames,self.lbBytes,self.lbVer):
            lab.setText("")
        self.lbPath.setPlainText("")

    def _set_info(self, a: dict):
        pm = self._make_thumb_pm(a, self.info_w, self.info_h)  # 角丸化済み
        self.infoThumb.setPixmap(pm)

        self.lbProj.setText(self.current_project or "")
        self.lbId.setText(a.get("id",""))
        self.lbType.setText(a.get("type",""))
        fr = a.get("frame_range"); self.lbFrames.setText(f"{fr[0]}-{fr[1]}" if fr else "-")
        self.lbBytes.setText(human_bytes(a.get("bytes_total",0)))
        v = a.get("version"); self.lbVer.setText(str(v) if v is not None else "-")
        self.lbPath.setPlainText(a.get("path",""))

    # ===== Buttons =====
    def _current_asset(self):
        items = self.grid.selectedItems()
        return items[0].data(QtCore.Qt.UserRole) if items else None

    def on_load_clicked(self):
        a = self._current_asset()
        if not a:
            hou.ui.displayMessage("何も選択されていません。"); return
        if (a.get("type","")).lower() != "cpio":
            hou.ui.displayMessage("Load は現在 CPIO のみ対応です。"); return
        rel = a.get("path")
        if not rel:
            hou.ui.displayMessage("パス情報がありません。"); return
        try:
            hip = hou.text.expandString("$HIP") or tempfile.gettempdir()
            local = os.path.join(hip, os.path.basename(rel))
            if not os.path.exists(local):
                self.api.download_file(self.current_project, rel, local)
            desktop = hou.ui.curDesktop()
            pane = desktop.paneTabOfType(hou.paneTabType.NetworkEditor)
            ctx = pane.pwd() if pane else hou.node("/obj")
            hou.clearAllSelected()
            ctx.loadItemsFromFile(local, ignore_load_warnings=False)
            sel = hou.selectedNodes()
            if sel and pane:
                first = sel[0].position()
                for n in sel:
                    n.setPosition(n.position() + pane.visibleBounds().center() - first)
            hou.ui.setStatusMessage(f"Loaded CPIO: {os.path.basename(local)}", severity=hou.severityType.Message)
        except Exception as e:
            hou.ui.displayMessage(f"Load failed: {e}")

# ========= RUN =========
def show_eld_browser():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, EldBrowser):
            w.showNormal(); w.raise_(); w.activateWindow(); return
    dlg = EldBrowser(hou.qt.mainWindow()); dlg.show()
show_eld_browser()
