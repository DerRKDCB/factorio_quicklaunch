#!/usr/bin/env python3
"""
Factorio Launcher for KDE Plasma / Fedora
https://github.com/DerRKDCB/factorio_quicklaunch
Features:
 - Launch Factorio normally
 - Continue with last local save
 - Manage server entries and securely store passwords using keyring
 - Connect directly to a chosen multiplayer server
Dependencies:
 - PySide6
 - keyring
"""

import sys
import os
import json
import subprocess
import time
from pathlib import Path
import keyring
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

APP_NAME = "FactorioLauncher"
CONFIG_FILE = Path.home() / ".config" / "factorio_launcher" / "config.json"
SERVICE_PREFIX = f"{APP_NAME}.server"


def ensure_config_path():
    cfgdir = CONFIG_FILE.parent
    cfgdir.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        default = {
            "factorio_path": "",
            "saves_dir": "",
            "servers": []
        }
        CONFIG_FILE.write_text(json.dumps(default, indent=2))


def load_config():
    ensure_config_path()
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {"factorio_path": "", "saves_dir": "", "servers": []}


def save_config(cfg):
    ensure_config_path()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def guess_default_paths():
    guesses = {}
    h = str(Path.home())

    candidates = [
        "/usr/bin/factorio",
        "/usr/local/bin/factorio",
        os.path.join(h, ".local/share/Steam/steamapps/common/Factorio/bin/x64/factorio"),
        os.path.join(h, ".factorio/bin/x64/factorio"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            guesses["factorio_path"] = c
            break
    else:
        guesses["factorio_path"] = ""

    possible_saves = [
        os.path.join(h, ".factorio/saves"),
        os.path.join(h, ".local/share/Factorio/saves"),
    ]
    for s in possible_saves:
        if os.path.isdir(s):
            guesses["saves_dir"] = s
            break
    else:
        guesses["saves_dir"] = os.path.join(h, ".factorio/saves")

    return guesses


def find_latest_save(saves_dir: str) -> Optional[str]:
    if not saves_dir:
        return None
    p = Path(saves_dir)
    if not p.exists() or not p.is_dir():
        return None

    exts = [".zip", ".save", ".dat", ".autosave", ".quicksave"]
    latest = None
    latest_time = 0

    for f in p.iterdir():
        if f.is_file() and f.suffix.lower() in exts:
            m = f.stat().st_mtime
            if m > latest_time:
                latest_time = m
                latest = str(f)
    return latest


def store_server_password(name: str, password: str):
    keyring.set_password(f"{SERVICE_PREFIX}:{name}", "password", password)


def get_server_password(name: str) -> Optional[str]:
    return keyring.get_password(f"{SERVICE_PREFIX}:{name}", "password")


def delete_server_password(name: str):
    try:
        keyring.delete_password(f"{SERVICE_PREFIX}:{name}", "password")
    except Exception:
        pass


class ServerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, server=None):
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Server")
        self.resize(420, 180)

        layout = QtWidgets.QFormLayout(self)

        self.name_edit = QtWidgets.QLineEdit()
        self.host_edit = QtWidgets.QLineEdit()
        self.port_edit = QtWidgets.QSpinBox()
        self.port_edit.setRange(1, 65535)
        self.user_edit = QtWidgets.QLineEdit()
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)

        layout.addRow("Name:", self.name_edit)
        layout.addRow("Host:", self.host_edit)
        layout.addRow("Port:", self.port_edit)
        layout.addRow("User:", self.user_edit)
        layout.addRow("Password:", self.password_edit)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        if server:
            self.name_edit.setText(server["name"])
            self.host_edit.setText(server["host"])
            self.port_edit.setValue(int(server["port"]))
            self.user_edit.setText(server.get("user", ""))

            pw = get_server_password(server["name"])
            if pw:
                self.password_edit.setText(pw)

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "port": int(self.port_edit.value()),
            "user": self.user_edit.text().strip(),
            "password": self.password_edit.text(),
        }


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, cfg=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(600, 160)
        layout = QtWidgets.QFormLayout(self)

        self.factorio_path = QtWidgets.QLineEdit()
        self.saves_dir = QtWidgets.QLineEdit()

        browse_exe = QtWidgets.QPushButton("Browse…")
        browse_saves = QtWidgets.QPushButton("Browse…")

        browse_exe.clicked.connect(self.browse_exe)
        browse_saves.clicked.connect(self.browse_saves)

        h1 = QtWidgets.QHBoxLayout()
        h1.addWidget(self.factorio_path)
        h1.addWidget(browse_exe)

        h2 = QtWidgets.QHBoxLayout()
        h2.addWidget(self.saves_dir)
        h2.addWidget(browse_saves)

        layout.addRow("Factorio executable:", h1)
        layout.addRow("Saves directory:", h2)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        if cfg:
            self.factorio_path.setText(cfg["factorio_path"])
            self.saves_dir.setText(cfg["saves_dir"])

    def browse_exe(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Factorio executable")
        if fn:
            self.factorio_path.setText(fn)

    def browse_saves(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select saves directory")
        if d:
            self.saves_dir.setText(d)

    def get_settings(self):
        return {
            "factorio_path": self.factorio_path.text().strip(),
            "saves_dir": self.saves_dir.text().strip(),
        }


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Factorio Launcher")
        self.resize(800, 420)

        self.cfg = load_config()
        guesses = guess_default_paths()

        if not self.cfg.get("factorio_path"):
            self.cfg["factorio_path"] = guesses["factorio_path"]
        if not self.cfg.get("saves_dir"):
            self.cfg["saves_dir"] = guesses["saves_dir"]

        save_config(self.cfg)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        v = QtWidgets.QVBoxLayout(central)

        row = QtWidgets.QHBoxLayout()
        btn_launch = QtWidgets.QPushButton("Launch Factorio (normal)")
        btn_launch.clicked.connect(self.launch_normal)

        btn_continue = QtWidgets.QPushButton("Continue last save")
        btn_continue.clicked.connect(self.continue_latest_save)

        btn_settings = QtWidgets.QPushButton("Settings")
        btn_settings.clicked.connect(self.open_settings)

        row.addWidget(btn_launch)
        row.addWidget(btn_continue)
        row.addStretch()
        row.addWidget(btn_settings)
        v.addLayout(row)

        self.saves_label = QtWidgets.QLabel("")
        v.addWidget(self.saves_label)
        self.update_saves_label()

        servers_group = QtWidgets.QGroupBox("Servers")
        sv_layout = QtWidgets.QVBoxLayout(servers_group)

        self.servers_table = QtWidgets.QTableWidget(0, 4)
        self.servers_table.setHorizontalHeaderLabels(["Name", "Host", "Port", "User"])
        self.servers_table.horizontalHeader().setStretchLastSection(True)
        self.servers_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        sv_layout.addWidget(self.servers_table)

        btns_h = QtWidgets.QHBoxLayout()
        btn_add = QtWidgets.QPushButton("Add")
        btn_edit = QtWidgets.QPushButton("Edit")
        btn_remove = QtWidgets.QPushButton("Remove")
        btn_connect = QtWidgets.QPushButton("Launch Game (open client)")

        btn_add.clicked.connect(self.add_server)
        btn_edit.clicked.connect(self.edit_server)
        btn_remove.clicked.connect(self.remove_server)
        btn_connect.clicked.connect(self.connect_to_server)

        btns_h.addWidget(btn_add)
        btns_h.addWidget(btn_edit)
        btns_h.addWidget(btn_remove)
        btns_h.addStretch()
        btns_h.addWidget(btn_connect)

        sv_layout.addLayout(btns_h)
        v.addWidget(servers_group)

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)

        self.refresh_servers_table()

    # -------- BASIC ACTIONS -------- #

    def update_saves_label(self):
        latest = find_latest_save(self.cfg["saves_dir"])
        if latest:
            mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(Path(latest).stat().st_mtime))
            self.saves_label.setText(f"Latest save: {Path(latest).name} — {mtime}")
        else:
            self.saves_label.setText("No saves found.")

    def open_settings(self):
        dlg = SettingsDialog(self, cfg=self.cfg)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new = dlg.get_settings()
            self.cfg.update(new)
            save_config(self.cfg)
            self.update_saves_label()
            self.status.showMessage("Settings saved.", 3000)

    def refresh_servers_table(self):
        rows = self.cfg.get("servers", [])
        self.servers_table.setRowCount(len(rows))
        for i, s in enumerate(rows):
            self.servers_table.setItem(i, 0, QtWidgets.QTableWidgetItem(s["name"]))
            self.servers_table.setItem(i, 1, QtWidgets.QTableWidgetItem(s["host"]))
            self.servers_table.setItem(i, 2, QtWidgets.QTableWidgetItem(str(s["port"])))
            self.servers_table.setItem(i, 3, QtWidgets.QTableWidgetItem(s.get("user", "")))

    # -------- SERVER OPERATIONS -------- #

    def add_server(self):
        dlg = ServerDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            d = dlg.get_data()
            if not d["name"]:
                QtWidgets.QMessageBox.warning(self, "Error", "Server must have a name.")
                return

            store_server_password(d["name"], d["password"])

            entry = {
                "name": d["name"],
                "host": d["host"],
                "port": d["port"],
                "user": d["user"]
            }
            self.cfg["servers"].append(entry)
            save_config(self.cfg)
            self.refresh_servers_table()

    def edit_server(self):
        sel = self.servers_table.selectionModel().selectedRows()
        if not sel:
            QtWidgets.QMessageBox.warning(self, "Edit", "Select a server to edit.")
            return

        row = sel[0].row()
        s = self.cfg["servers"][row]

        dlg = ServerDialog(self, server=s)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            d = dlg.get_data()

            # handle password
            if d["password"]:
                store_server_password(d["name"], d["password"])

            s.update({
                "name": d["name"],
                "host": d["host"],
                "port": d["port"],
                "user": d["user"],
            })
            save_config(self.cfg)
            self.refresh_servers_table()

    def remove_server(self):
        sel = self.servers_table.selectionModel().selectedRows()
        if not sel:
            return
        row = sel[0].row()
        name = self.cfg["servers"][row]["name"]

        self.cfg["servers"].pop(row)
        save_config(self.cfg)
        delete_server_password(name)
        self.refresh_servers_table()

    # -------- GAME LAUNCH ACTIONS -------- #

    def launch_normal(self):
        factorio = self.cfg["factorio_path"]
        if not Path(factorio).exists():
            QtWidgets.QMessageBox.warning(self, "Error", "Factorio executable not found.")
            return
        subprocess.Popen([factorio])
        self.status.showMessage("Launched Factorio.", 3000)

    def continue_latest_save(self):
        factorio = self.cfg["factorio_path"]
        latest = find_latest_save(self.cfg["saves_dir"])

        if not latest:
            QtWidgets.QMessageBox.warning(self, "Continue", "No save found.")
            return

        subprocess.Popen([factorio, "--load-game", latest])
        self.status.showMessage("Launching latest save…", 3000)

    def connect_to_server(self):
        """Launch Factorio and auto-connect to a server."""
        sel = self.servers_table.selectionModel().selectedRows()
        if not sel:
            QtWidgets.QMessageBox.warning(self, "Connect", "Select a server first.")
            return

        row = sel[0].row()
        s = self.cfg["servers"][row]

        factorio = self.cfg["factorio_path"]
        if not Path(factorio).exists():
            QtWidgets.QMessageBox.warning(self, "Error", "Factorio executable not found.")
            return

        host = s["host"]
        port = str(s["port"])
        pw = get_server_password(s["name"]) or ""

        args = [factorio, "--mp-connect", f"{host}:{port}"]
        if pw:
            args += ["--password", pw]

        try:
            subprocess.Popen(args)
            self.status.showMessage(f"Connecting to {host}:{port}…", 4000)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Launch Failed", str(e))


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
