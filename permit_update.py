# -*- coding: utf-8 -*-
"""
Модуль обновления генераторов пропусков.

Два сценария:
1. Онлайн — запрос к GitHub API, сравнение версий.
2. Из файла — пользователь копирует .zip с обновлением и указывает путь.

В обоих случаях: backup старого .exe в _backup/, распаковка нового,
предложение перезапуска.

API:
  OnlineChecker(repo_owner, repo_name).check(APP_VERSION) -> (latest_tag, latest_name, html_url, body)
  LocalUpdater.apply(zip_path, exe_name) -> (ok: bool, message: str, needs_restart: bool)
"""
import os
import re
import sys
import shutil
import zipfile
import tempfile
import json
import urllib.request
import urllib.error
import ssl

GITHUB_API_TIMEOUT = 8  # секунд


def _has_network():
    """Грубая проверка наличия сети без подвисания на DNS."""
    try:
        urllib.request.urlopen("https://api.github.com", timeout=3)
        return True
    except Exception:
        return False


class OnlineChecker:
    """Сверяет текущую версию с последним релизом на GitHub."""

    def __init__(self, owner, repo):
        self.url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    def check(self, current_version):
        """Возвращает dict {tag, name, html_url, body, has_update: bool}
        или None при ошибке сети/парсинга.
        """
        try:
            req = urllib.request.Request(
                self.url,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "permit-generator-updater"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=GITHUB_API_TIMEOUT, context=ctx) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

        tag = data.get("tag_name") or ""
        name = data.get("name") or tag
        html_url = data.get("html_url") or ""
        body = data.get("body") or ""

        latest = _normalize_version(tag)
        current = _normalize_version(current_version)
        has_update = bool(latest and current and _compare(latest, current) > 0)

        return {
            "tag": tag, "name": name, "html_url": html_url,
            "body": body, "has_update": has_update,
        }


def _normalize_version(v):
    """'v0.1.5' или '0.1.5' -> (0,1,5). Неподдерживаемое -> None."""
    if not v:
        return None
    v = v.strip().lstrip("vV")
    m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", v)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


def _compare(a, b):
    if a == b:
        return 0
    if a > b:
        return 1
    return -1


class LocalUpdater:
    """Применяет обновление из локального .zip-файла."""

    def __init__(self, exe_name, workdir=None):
        # Папка, где лежит текущий exe (для frozen-режима) или исходники
        if workdir is not None:
            self.workdir = workdir
        elif getattr(sys, "frozen", False):
            self.workdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            self.workdir = os.path.dirname(os.path.abspath(__file__))
        self.exe_name = exe_name
        self.backup_dir = os.path.join(self.workdir, "_backup")
        os.makedirs(self.backup_dir, exist_ok=True)

    def apply(self, zip_path):
        """Распаковывает zip поверх workdir, бэкапя текущий exe.

        Возвращает (ok, message).
        """
        if not os.path.exists(zip_path):
            return False, "Файл не найден: %s" % zip_path
        if not zipfile.is_zipfile(zip_path):
            return False, "Файл не является zip-архивом."

        # 1. Бэкап текущего exe
        backup_name = self._make_backup_name()
        try:
            exe_path = os.path.join(self.workdir, self.exe_name)
            if os.path.exists(exe_path):
                shutil.copy2(exe_path, os.path.join(self.backup_dir, backup_name))
        except Exception as e:
            return False, "Не удалось создать резервную копию: %s" % e

        # 2. Распаковка
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Проверка путей (защита от zip-slip)
                for name in zf.namelist():
                    target = os.path.join(self.workdir, name)
                    if not os.path.abspath(target).startswith(os.path.abspath(self.workdir)):
                        return False, "Подозрительный путь в архиве: %s" % name
                zf.extractall(self.workdir)
        except Exception as e:
            # Восстановление из бэкапа при ошибке
            try:
                exe_path = os.path.join(self.workdir, self.exe_name)
                backup_path = os.path.join(self.backup_dir, backup_name)
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, exe_path)
            except Exception:
                pass
            return False, "Ошибка распаковки: %s" % e

        return True, "Обновление применено. Резервная копия: _backup\\%s" % backup_name

    def _make_backup_name(self):
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return "%s.%s.bak" % (self.exe_name, ts)

    def list_backups(self):
        if not os.path.isdir(self.backup_dir):
            return []
        return sorted(
            [f for f in os.listdir(self.backup_dir) if f.startswith(self.exe_name) and f.endswith(".bak")],
            reverse=True)

    def rollback(self, backup_filename):
        src = os.path.join(self.backup_dir, backup_filename)
        dst = os.path.join(self.workdir, self.exe_name)
        if not os.path.exists(src):
            return False, "Резервная копия не найдена."
        try:
            shutil.copy2(src, dst)
            return True, "Откат выполнен. Перезапустите программу."
        except Exception as e:
            return False, "Ошибка отката: %s" % e