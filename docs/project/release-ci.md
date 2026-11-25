# Сборка и проверка релиза

Конвейер **Build & Release** запускается при публикации релиза или предрелиза. Берутся исходники из коммита тега. Для версии конфигурации используется числовая часть тега `X.X.X.X` до дефиса, а для публикации и `sonar.projectVersion` — полный тег. [Workflow релиза](https://github.com/ShadobaAI/kafka-adapter/blob/main/.github/workflows/release.yml)

## Тестовые задания { #test-jobs }

1. `prepare` готовит эталонную ИБ и определяет группы UI-сценариев по каталогам `features/<раздел>/<объект>`.
2. `unit` запускает обязательные модульные тесты на копии базы. В CI используется `YaxParams.json` из ветки `main` тестового репозитория с отбором по тегу `CI`. Расширение `unit.cfe` берётся из `ghcr.io/shadobaai/unit:latest`.
3. После успешного `unit` конвейер запускает UI-группы на отдельных копиях базы, до десяти одновременно. Ошибка одной группы сохраняется в результате проверки, другие группы продолжают работу.

Сборку базы и запуск сценариев выполняет Vanessa Runner. Для тестового и демонстрационного DT скрипт `create_test_dt.py` объединяет base и adapter, а ZIP с примерами загружает как отдельное расширение `ТестированиеАдаптераKafka`. Инструкции стенда и полный порядок работ находятся в [release-quality.yml](https://github.com/ShadobaAI/kafka-adapter/blob/main/.github/workflows/release-quality.yml) и [create_test_dt.py](https://github.com/ShadobaAI/kafka-adapter/blob/main/.github/scripts/create_test_dt.py).

## Покрытие и диагностика { #coverage }

Coverage41C собирает данные по исходникам адаптера. Перед выгрузкой в SonarQube конвейер проверяет файлы Generic Coverage XML и наличие покрытых строк. В диагностических артефактах `unit-test-diagnostics` и `ui-test-diagnostics` ищите `exit-code.txt`, вывод тестов, `ibsrv.log`, `coverage41c.log` и `dbgs.log`.

SonarQube выбирает проект по Git-ветке `target_commitish`. Для `main` используется `kafka-adapter`, для другой ветки — отдельный ключ. Конвейер публикует статический отчёт после успешной фоновой обработки анализа. [Workflow SonarQube](https://github.com/ShadobaAI/kafka-adapter/blob/main/.github/workflows/release-sonar.yml)

## Где смотреть отчёты { #ci-reports }

Страница запуска содержит ссылки на Allure Unit, Allure UI и SonarQube. Если какой-то отчёт отсутствует, откройте по ссылке логи и артефакты соответствующего запуска. Путь `latest/` указывает на последний опубликованный набор отчётов. [Открыть отчёты](https://shadobaai.github.io/kafka-adapter-tests-reports/latest/)

Локальные проверки сборочных скриптов выполняются из корня репозитория.

```powershell
python -B -m unittest discover -s .github/scripts -p 'test_*.py' -v
node --test .github/scripts/test_sonar_report.js
```
