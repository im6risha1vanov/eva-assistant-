# Серверный бот Евы

Снимок `/opt/eva` с сервера на 28.10.2026, без `.venv`, `.env`, баз и ключей. На сервере git нет, поэтому это первая версия под контролем. Отчёт сверки: [../docs/SERVER_CHECK_2026-10-28.md](../docs/SERVER_CHECK_2026-10-28.md).

| Файл | Назначение |
|---|---|
| `app/main.py` | FastAPI: приём Wazzup webhook, пересылка в AlfaCRM, черновики (сервис `eva`) |
| `app/vk_admin.py` | Служебный VK-бот для старшего администратора (сервис `eva-vk-admin`) |
| `app/routing.py`, `app/refresh_knowledge.py` | Маршрутизация по книге, обновление знаний (15.10) |
| `app/crm_context.py`, `app/alfacrm_readonly.py` | Чтение контекста AlfaCRM только на чтение (09.10) |
| `app/reference_sources.py` | Прайс и расписание из Google Sheets (09.10) |
| `app/vk_handoff.py`, `app/report_delivery.py` | Передача старшему и доставка отчётов |
| `app/vk_private_test.py` | Тестовый диалог владельца с LLM через OpenAI-совместимый шлюз |
| `knowledge/` | `server_draft.json` (40 шаблонов), `private_test_book.json` (книга продаж) |
| `deploy/` | systemd-юнит и скрипты обновления справочников |

Не запускать `deploy/install.sh` на рабочем сервере: он распаковывает старый `/root/eva-release.tar.gz` поверх кода.
