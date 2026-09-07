# -*- coding: utf-8 -*-
"""
Модуль обновления генераторов пропусков.

Два сценария:
1. Онлайн — запрос к GitHub API, сравнение версий.
2. Из файла — пользователь копирует .zip с обновлением и указывает путь.

В обоих случаях: backup старого .exe в _backup/, распаковка нового,
предложение перезапуска.
"""
import os
import re
import sys
import shutil
import zipfile
import json
import urllib.request
import urllib.error
import ssl
from datetime import datetime

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
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "permit-generator-updater",
                },
            )
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
            "tag": tag,
            "name": name,
            "html_url": html_url,
            "body": body,
            "has_update": has_update,
        }


def _normalize_version(v):
    """'v0.1.5' или '0.1.5' -> (0, 1, 5). Неподдерживаемое -> None."""
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
    return 1 if a > b else -1


class LocalUpdater:
    """Применяет обновление из локального .zip-файла."""

    def __init__(self, exe_name, workdir=None):
        if workdir is not None:
            self.workdir = os.path.abspath(workdir)
        elif getattr(sys, "frozen", False):
            self.workdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            self.workdir = os.path.dirname(os.path.abspath(__file__))

        self.exe_name = exe_name
        self.backup_dir = os.path.join(self.workdir, "_backup")
        os.makedirs(self.backup_dir, exist_ok=True)

    def apply(self, zip_path):
        """Распаковывает zip поверх workdir с обходом блокировки запущенного .exe.

        Возвращает (ok, message).
        """
        zip_path = os.path.abspath(zip_path)
        if not os.path.exists(zip_path):
            return False, f"Файл не найден: {zip_path}"
        if not zipfile.is_zipfile(zip_path):
            return False, "Файл не является zip-архивом."

        exe_path = os.path.join(self.workdir, self.exe_name)
        backup_filename = self._make_backup_name()
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        # Временное имя файла для обхода блокировки запущенного .exe
        exe_renamed = exe_path + ".old"

        # 1. Проверка безопасных путей внутри архива (Защита от Zip-Slip)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    target_path = os.path.abspath(os.path.join(self.workdir, member))
                    if os.path.commonpath([self.workdir, target_path]) != self.workdir:
                        return False, f"Подозрительный путь в архиве: {member}"
        except Exception as e:
            return False, f"Ошибка при чтении архива: {e}"

        # 2. Безопасное переименование текущего .exe (Windows разрешает переименовать запущенный exe)
        renamed = False
        try:
            if os.path.exists(exe_path):
                if os.path.exists(exe_renamed):
                    os.remove(exe_renamed)
                os.rename(exe_path, exe_renamed)
                renamed = True
        except Exception as e:
            return False, f"Не удалось подготовить исполняемый файл к обновлению: {e}"

        # 3. Распаковка архива
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self.workdir)

            # Перемещаем старый переименованный файл в бэкап
            if renamed and os.path.exists(exe_renamed):
                shutil.move(exe_renamed, backup_path)

        except Exception as e:
            # Откат изменений при сбое
            if renamed and os.path.exists(exe_renamed):
                if os.path.exists(exe_path):
                    try:
                        os.remove(exe_path)
                    except Exception:
                        pass
                try:
                    os.rename(exe_renamed, exe_path)
                except Exception:
                    pass
            return False, f"Ошибка распаковки: {e}"

        return True, f"Обновление успешно применено. Резервная копия: _backup\\{backup_filename}"

    def _make_backup_name(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self.exe_name}.{ts}.bak"

    def list_backups(self):
        if not os.path.isdir(self.backup_dir):
            return []
        return sorted(
            [f for f in os.listdir(self.backup_dir) if f.startswith(self.exe_name) and f.endswith(".bak")],
            reverse=True,
        )

    def rollback(self, backup_filename):
        src = os.path.join(self.backup_dir, backup_filename)
        dst = os.path.join(self.workdir, self.exe_name)
        if not os.path.exists(src):
            return False, "Резервная копия не найдена."

        dst_renamed = dst + ".rollback_old"
        renamed = False

        try:
            # Переименовываем текущий запущенный exe перед откатом
            if os.path.exists(dst):
                if os.path.exists(dst_renamed):
                    os.remove(dst_renamed)
                os.rename(dst, dst_renamed)
                renamed = True

            shutil.copy2(src, dst)

            # Удаляем временный файл, если всё прошло успешно
            if renamed and os.path.exists(dst_renamed):
                try:
                    os.remove(dst_renamed)
                except Exception:
                    pass

            return True, "Откат выполнен. Перезапустите программу."
        except Exception as e:
            # Восстанавливаем оригинальный файл при ошибке
            if renamed and os.path.exists(dst_renamed):
                try:
                    os.rename(dst_renamed, dst)
                except Exception:
                    pass
            return False, f"Ошибка отката: {e}"
