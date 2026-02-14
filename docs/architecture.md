# Архитектура Teledocs

## Обзор

Teledocs — Telegram-бот на Python (aiogram 3.x) с интеграцией OpenAI API для AI-чата и системой генерации документов из .docx шаблонов с Jinja2-тегами.

## Стек технологий

- **Python 3.11+**
- **aiogram 3.13+** — async Telegram-бот фреймворк
- **OpenAI API** — gpt-4o-mini для чата
- **python-docx-template** — Jinja2 шаблоны в .docx
- **LibreOffice headless** — конвертация в PDF
- **SQLite + aiosqlite** — хранение данных
- **pydantic-settings** — типизированная конфигурация

## Структура проекта

```
teledocs/
├── bot.py                    # Точка входа
├── config/settings.py        # Конфигурация (Pydantic Settings)
├── app/
│   ├── handlers/             # Роутеры aiogram
│   │   ├── common.py         # /start, /help, /cancel
│   │   ├── document.py       # FSM-поток создания документа
│   │   └── chat.py           # AI-чат (catch-all)
│   ├── states/document.py    # FSM-состояния
│   ├── keyboards/inline.py   # Inline-клавиатуры
│   ├── services/
│   │   ├── openai_service.py     # OpenAI клиент + память
│   │   ├── document_service.py   # Рендер шаблонов + PDF
│   │   └── template_registry.py  # Метаданные шаблонов
│   ├── database/
│   │   ├── connection.py     # Инициализация SQLite
│   │   └── repositories/     # CRUD-операции
│   ├── middlewares/           # DB-инжекция, авторегистрация
│   └── lexicon/ru.py         # Русские тексты
├── templates/                # .docx шаблоны + meta.json
├── output/                   # Временные файлы (gitignored)
└── data/                     # SQLite БД (gitignored)
```

## Ключевые решения

### 1. Динамический сбор реквизитов через FSM

Вместо отдельного состояния на каждое поле — один стейт `collecting_requisites` с `current_field_index` в state data. Поля описаны в `template_meta.json`. Добавление нового поля = правка JSON без изменения кода.

### 2. Метаданные шаблонов в JSON

`templates/template_meta.json` описывает для каждого шаблона:
- Какие поля собирать
- Промпты для пользователя (на русском)
- Тип данных и regex-валидация
- Дефолтные значения

### 3. PDF через LibreOffice headless

На сервере нет Microsoft Word. Используем `libreoffice --headless --convert-to pdf` через `asyncio.create_subprocess_exec` для неблокирующей конвертации.

### 4. Сервисы как singleton через workflow_data

OpenAIService, DocumentService, TemplateRegistry создаются один раз в `bot.py` и передаются через `dp["service_name"]`. Aiogram автоматически инжектит их в хэндлеры.

### 5. Память диалогов

MVP: in-memory dict (теряется при рестарте). В БД есть таблица `conversation_history` для будущей персистентности.

## Поток создания документа

```
/newdoc
  → Inline-клавиатура с шаблонами
    → Пользователь выбирает шаблон
      → Бот спрашивает поля по очереди (из template_meta.json)
        → Валидация каждого поля
          → Показ сводки для подтверждения
            → Рендер .docx через docxtpl
              → Конвертация в PDF через LibreOffice
                → Отправка PDF пользователю
```

## База данных (SQLite)

### Таблицы:
- **users** — Telegram-пользователи (id, username, name)
- **conversation_history** — история AI-диалогов
- **generated_documents** — лог сгенерированных документов (шаблон, реквизиты, дата)

## Запуск

```bash
# Установка зависимостей
pip install -r requirements.txt

# Генерация .docx шаблонов (один раз)
python scripts/create_templates.py

# Создать .env из .env.dist и заполнить токены
cp .env.dist .env

# Запуск бота
python bot.py
```

## Требования к серверу

- Python 3.11+
- LibreOffice (`apt install libreoffice-writer`)
- ~512 MB RAM для MVP
