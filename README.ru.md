# VS Code Feature Scout

[English version](README.md)

VS Code постепенно становится платформой для агентной разработки: custom
instructions, custom agents, MCP-серверы, browser tools, tasks, profiles, remote
tunnels, model providers и постоянный поток новых настроек. Сложность не в том,
чтобы прочитать каждое объявление. Сложность в том, чтобы заметить, какие
возможности действительно полезны именно для вашего рабочего процесса.

**VS Code Feature Scout** - это маленький CLI без runtime-зависимостей, который
превращает release notes VS Code и уже существующие возможности VS Code в
практичные рекомендации. Его можно запускать автоматически, не тратя токены на
полный анализ репозитория, а готовый Markdown-отчет удобно отдавать Codex,
Claude Code, Copilot или другому coding agent.

## Что Он Делает

У Feature Scout есть два взаимодополняющих режима:

- **Release mode** проверяет свежие release notes VS Code и находит новые
  пункты, которые совпадают с профилем вашего проекта.
- **Baseline mode** делает инвентаризацию уже существующих возможностей VS Code,
  которые могут быть полезны, даже если они появились несколько месяцев назад.

Инструмент пишет Markdown-отчеты, например:

```text
outputs/vscode_feature_scout/latest.md
outputs/vscode_feature_scout/baseline.md
```

Отчеты специально короткие и ориентированы на действие:

- название возможности;
- почему она может быть полезна;
- релевантные настройки;
- конкретные сигналы в репозитории;
- минимальное безопасное следующее действие.

## Зачем Это Нужно

Новые IDE-возможности часто появляются быстрее, чем команды успевают встроить
их в свои процессы. Разработчик может заметить новую настройку вроде
`workbench.browser.enableRemoteProxy`, но пропустить более старые возможности:
MCP-серверы, browser tools, custom agents, prompt files или task automation.

Из-за этого появляется тихий разрыв:

- AI-агенты не знают, какие возможности IDE они могут использовать.
- Документация проекта описывает workflow, но не говорит, какие editor features
  могут его улучшить.
- Команды либо игнорируют полезные возможности, либо внедряют их слишком широко
  без маленького безопасного эксперимента.

Feature Scout закрывает этот разрыв. Он работает как легкий переводчик между
возможностями VS Code и workflow конкретного проекта.

## Принципы

- **Без полного сканирования репозитория.** Scout читает компактный профиль
  проекта и проверяет короткий список конкретных сигналов.
- **Без LLM.** Отчеты генерируются детерминированным локальным Python-кодом.
- **Сначала официальная документация.** Baseline mode опирается на curated список
  официальных документов VS Code.
- **Маленькие следующие шаги.** Инструмент предлагает trial, settings и
  проверяемые действия, а не большие переписывания workflow.
- **Безопасная автоматизация.** Опциональный macOS LaunchAgent может запускаться
  на события старта/обновления VS Code без polling каждую минуту.

## Установка

Склонируйте репозиторий:

```bash
git clone https://github.com/Andrej-Ilin/vscode-feature-scout.git
cd vscode-feature-scout
```

Запуск из исходников через `uv`:

```bash
uv run vscode-feature-scout --help
```

Или editable install:

```bash
python -m pip install -e .
vscode-feature-scout --help
```

## Быстрый Старт

Создайте компактный профиль проекта:

```bash
mkdir -p docs/tooling
cat > docs/tooling/project_capability_profile.md <<'EOF'
# Project Capability Profile

Scout tags: agents, mcp, integrated browser, remote workspace, terminal, tasks, python

Current project shape:

- Python service with local tests and a browser-facing UI.
- Agents use AGENTS.md and project-specific review prompts.
- Generated reports belong under outputs/.
EOF
```

Более полный пример есть здесь:
[`docs/example-project-profile.md`](docs/example-project-profile.md).

Запуск release mode:

```bash
vscode-feature-scout \
  --profile docs/tooling/project_capability_profile.md \
  --output outputs/vscode_feature_scout/latest.md
```

Запуск baseline mode:

```bash
vscode-feature-scout \
  --baseline \
  --repo . \
  --output outputs/vscode_feature_scout/baseline.md
```

Напечатать отчет в stdout, чтобы вставить его в prompt агенту:

```bash
vscode-feature-scout --baseline --output -
```

## Release Mode

Release mode загружает:

```text
https://code.visualstudio.com/updates
```

Он парсит секции release notes и оценивает их по:

- встроенным ключевым словам вроде `agent`, `mcp`, `integrated browser`,
  `remote`, `task`, `debug`, `model provider`;
- строке `Scout tags:` из профиля проекта;
- найденным в release notes ключам настроек.

Пример:

```bash
vscode-feature-scout --include-seen
```

По умолчанию state хранится здесь:

```text
outputs/vscode_feature_scout/state.json
```

Если страница последнего релиза не изменилась, команда быстро завершится.

## Baseline Mode

Baseline mode отвечает на другой вопрос:

> Какие полезные возможности VS Code уже существуют, и используем ли мы их?

Он проверяет curated список официальных возможностей VS Code:

- Custom Instructions
- Custom Agents
- Model Context Protocol (MCP)
- Integrated Browser Tools
- Prompt Files and Slash Commands
- Agent Skills
- Tasks
- Profiles
- Remote Tunnels and Remote Workspaces

Для каждой возможности отчет показывает:

- приоритет;
- состояние внедрения (`not-wired`, `candidate`, `partially-present`);
- ссылку на официальную документацию;
- сигналы в репозитории, например `AGENTS.md`, `.claude/agents/`,
  `.vscode/mcp.json`, `.vscode/tasks.json`;
- рекомендованное следующее действие.

Запуск без загрузки документации, удобно для тестов или offline-сред:

```bash
vscode-feature-scout --baseline --baseline-no-fetch
```

## macOS LaunchAgent

Feature Scout включает опциональный установщик macOS LaunchAgent. Он может
запускать scout, когда VS Code стартует/перезапускается или когда metadata
приложения меняется после обновления.

Перед включением LaunchAgent установите Feature Scout в стабильное Python-
окружение. Сгенерированный plist сохраняет путь к Python-интерпретатору, который
использует `vscode-feature-scout-launchd`.

Установить и загрузить:

```bash
vscode-feature-scout-launchd --install --load --repo /path/to/your/project
```

Это создаст:

```text
~/Library/LaunchAgents/dev.vscode-feature-scout.plist
```

По умолчанию используется `WatchPaths`, а не polling:

- `~/Library/Application Support/Code/logs`
- `/Applications/Visual Studio Code.app/Contents/Info.plist`
- `~/Applications/Visual Studio Code.app/Contents/Info.plist`

Статус:

```bash
vscode-feature-scout-launchd --status
```

Удалить:

```bash
vscode-feature-scout-launchd --uninstall
```

Если нужен fallback polling interval:

```bash
vscode-feature-scout-launchd --install --load --repo /path/to/your/project --poll-interval 300
```

## Хорошие Первые Сценарии

Feature Scout особенно полезен, если:

- вы используете coding agents и хотите, чтобы они понимали возможности IDE;
- вы поддерживаете `AGENTS.md`, `CLAUDE.md`, custom prompts или MCP config;
- в проекте есть локальные UI/API smoke checks, которым могут помочь VS Code
  browser tools;
- вы хотите легкий отчет "что изменилось в VS Code?" после обновлений;
- вы хотите baseline-инвентаризацию перед внедрением MCP, custom agents или
  tasks.

## Чего Он Не Делает

- Не запускает LLM.
- Не отправляет содержимое репозитория наружу.
- Не инспектирует базы данных, секреты, raw data или приватные файлы.
- Не меняет настройки VS Code автоматически.
- Не заменяет человеческое решение о внедрении workflow.

## Разработка

Запустить тесты:

```bash
uv run --extra dev python -m pytest -q
```

Запустить lint:

```bash
uv run --extra dev python -m ruff check src tests
uv run --extra dev python -m ruff format --check src tests
```

## Лицензия

MIT
