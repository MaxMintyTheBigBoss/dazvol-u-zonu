# dazvol_u_zonu

Единый генератор пропусков по белорусским процедурам **14.3 / 14.5 / 19.17.1**.

## Возможности
- Выбор процедуры при запуске (3 кнопки: 14.3, 14.5, 19.17.1)
- Единая SQLite база данных всех выданных пропусков
- Выгрузка базы в JSON / CSV / Excel
- Обновление через GitHub Releases
- Установка обновлений из локального .zip файла

## Установка
Скачайте `dazvol_u_zonu.exe` из [Releases](https://github.com/MaxMintyTheBigBoss/dazvol-u-zonu/releases) и запустите.

## Запуск из исходников
```bash
pip install -r requirements.txt
python app.py
```

## Сборка .exe
```bash
pyinstaller --noconfirm dazvol_u_zonu.spec
```

## Версия
**0.0.2**

## Автор
Соломейчук Алексей / Salamiaichuk Aliaksei
Email: al.vl.solo@yandex.by
