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
        # Имя реально запущенного файла. В exe это sys.executable,
        # поэтому обновление встанет именно под ним.
        self.current_exe = (
            os.path.basename(sys.executable)
            if getattr(sys, "frozen", False)
            else exe_name
        )
        self.backup_dir = os.path.join(self.workdir, "_backup")
        os.makedirs(self.backup_dir, exist_ok=True)

    @staticmethod
    def _is_exe_name(name):
        """Подходит ли имя под маску нашего exe (подчёркивания или точки)."""
        low = (name or "").lower().replace("-", "_").replace(".", "_")
        return "dazvol" in low and "zonu" in low and (name or "").lower().endswith(".exe")

    def _find_current_exe(self):
        """Ищет запущенный exe в workdir: по точному имени, затем по маске.

        Нужно потому, что пользователь мог переименовать файл
        (dazvol_u_zonu.ver.0.1.14.exe вместо dazvol_u_zonu_ver.0.1.14.exe).
        """
        exact = os.path.join(self.workdir, self.current_exe)
        if os.path.exists(exact):
            return exact
        try:
            for name in os.listdir(self.workdir):
                full = os.path.join(self.workdir, name)
                if os.path.isfile(full) and self._is_exe_name(name):
                    return full
        except Exception:
            pass
        return None

    def apply(self, zip_path):
        """Устанавливает обновление из zip.

        Возвращает (ok, message). Особенности:
        - exe из архива кладётся ПОД ИМЕНЕМ ЗАПУЩЕННОГО файла;
        - поддерживаются вложенные папки внутри архива;
        - если exe в архиве нет — внятная ошибка, файлы не распаковываются.
        """
        zip_path = os.path.abspath(zip_path)
        if not os.path.exists(zip_path):
            return False, f"Файл не найден: {zip_path}"
        if not zipfile.is_zipfile(zip_path):
            return False, "Файл не является zip-архивом."

        # 0. Ищем запущенный exe (по точному имени или по маске)
        exe_path = self._find_current_exe()
        if exe_path is None:
            return False, (
                "Не найден запущенный файл программы в папке: "
                + self.workdir
                + ". Обновление можно ставить только рядом с .exe."
            )
        self.current_exe = os.path.basename(exe_path)

        backup_filename = self._make_backup_name()
        backup_path = os.path.join(self.backup_dir, backup_filename)
        exe_renamed = exe_path + ".old"

        # 1. Читаем архив: проверяем пути и ищем exe
        incoming = None
        self.incoming_version = None
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                for member in names:
                    target_path = os.path.abspath(os.path.join(self.workdir, member))
                    if os.path.commonpath([self.workdir, target_path]) != self.workdir:
                        return False, f"Подозрительный путь в архиве: {member}"
                    base = os.path.basename(member)
                    if base and self._is_exe_name(base):
                        incoming = member
                    # version.json внутри архива — источник номера версии
                    if base == "version.json":
                        try:
                            vd = json.loads(zf.read(member).decode("utf-8"))
                            self.incoming_version = (vd or {}).get("version")
                        except Exception:
                            pass
        except Exception as e:
            return False, f"Ошибка при чтении архива: {e}"

        if incoming is None:
            return False, (
                "В архиве нет файла программы (.exe). "
                "Для обновления в zip нужно положить сам .exe "
                "(например dazvol_u_zonu_ver.0.1.16.exe), а не исходники."
            )

        # 2. Переименовываем текущий exe (Windows разрешает для запущенного)
        renamed = False
        try:
            if os.path.exists(exe_renamed):
                os.remove(exe_renamed)
            os.rename(exe_path, exe_renamed)
            renamed = True
        except Exception as e:
            return False, f"Не удалось подготовить исполняемый файл к обновлению: {e}"

        # 3. Распаковка с учётом вложенной папки
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                prefix = self._common_prefix(zf.namelist())
                for member in zf.namelist():
                    rel = member[len(prefix):] if prefix else member
                    if not rel or rel.endswith("/"):
                        continue
                    dest = os.path.join(self.workdir, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)

            if renamed and os.path.exists(exe_renamed):
                shutil.move(exe_renamed, backup_path)

            self._adopt_incoming_exe(incoming, exe_path)
        except Exception as e:
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

        return True, (
            "Обновление успешно применено. "
            + "Резервная копия: " + backup_filename
        )

    @staticmethod
    def _common_prefix(names):
        """Общий префикс-папка архива, если все файлы внутри одной папки."""
        tops = set()
        for n in names:
            top = n.split("/", 1)[0]
            tops.add(top)
        if len(tops) == 1:
            only = tops.pop()
            if any(n.startswith(only + "/") for n in names):
                return only + "/"
        return ""

    def _adopt_incoming_exe(self, incoming, target_path):
        """Кладёт распакованный exe под текущим именем и пишет version.json."""
        try:
            base = os.path.basename(incoming)
            src = os.path.join(self.workdir, base)
            if not os.path.exists(src):
                # не сработал общий префикс — ищем по имени
                for root, _dirs, files in os.walk(self.workdir):
                    if base in files:
                        src = os.path.join(root, base)
                        break
            if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(target_path):
                if os.path.exists(target_path):
                    try:
                        os.remove(target_path)
                    except Exception:
                        pass
                os.replace(src, target_path)
            self._write_version_marker(base or self.current_exe, self.incoming_version)
            return True
        except Exception:
            return False

    def _write_version_marker(self, exe_filename, version=None):
        """Пишет version.json рядом с exe: оттуда приложение берёт версию.

        Версию передаём явно (из version.json внутри архива). С фиксированным
        именем exe номера в имени файла нет, поэтому по имени его не найти.
        """
        ver = version
        if not ver:
            m = re.search(r"(\d+\.\d+\.\d+)", exe_filename or "")
            ver = m.group(1) if m else None
        try:
            with open(os.path.join(self.workdir, "version.json"), "w", encoding="utf-8") as f:
                json.dump({"version": ver, "exe": os.path.basename(exe_filename or "")}, f, ensure_ascii=False)
        except Exception:
            pass

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
