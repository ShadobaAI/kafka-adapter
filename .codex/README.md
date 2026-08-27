# Codex для kafka-adapter

Файл `config.toml` содержит repository-local MCP для EDT, BSL LS и SonarQube. Копировать, создавать example-конфиг или исправлять абсолютные пути не требуется. Общий `code-index`, `v8std` и runtime BSL LS устанавливаются командой `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\ai\setup.ps1` из корня workspace `Kafka`.

Bootstrap проверяет Node.js 18+ и Java и устанавливает executable JAR в `%CODEX_HOME%\bsl-ls`. Proxy использует текущую `.bsl-language-server.json`, фиксирует root репозитория и отклоняет file-аргументы вне него. На Windows для файлов с не-ASCII путями требуется доступный 8.3 short path; при отключённом short-name creation proxy завершает запрос явной ошибкой совместимости, не подменяя путь временным alias.

Перед запуском Codex задайте токен SonarQube в пользовательской переменной окружения Windows:

```powershell
[Environment]::SetEnvironmentVariable("SONARQUBE_TOKEN", "<token>", "User")
```

После изменения переменной перезапустите Codex. Значение токена не должно попадать в `config.toml`, Git или документацию.
