# Окружение разработки

## Подготовка рабочего каталога { #workspace-setup }

1. Получите [корневой репозиторий рабочего пространства](https://github.com/ShadobaAI/kafka-adapter-workspace).
2. Разместите проекты адаптера, базы и примеров по [карте репозиториев](repositories.md). Тестовый и конвертационный контуры можно подготовить отдельно.
3. Откройте проекты `adapter/adapter` и `adapter/base` в одном рабочем пространстве EDT. Подготовьте клиент-серверную ИБ на базе `adapter/base` для отладки расширения. Для сценариев с демонстрационными данными подключите `adapter/examples`.

Платформу и компоненты для запуска выбирайте по [требованиям адаптера](../user/installation/requirements.md). EDT должен открывать проекты в формате их исходников. При работе с 1C AI Core используйте профиль `adapter/.ai/project.yaml` и инструкции из корневого репозитория.

## Сервисы для проверки { #test-services }

| Что хотите проверить | Что подготовить |
|---|---|
| Реальную отправку и чтение в Kafka | Стенд Docker Compose из [kafka-tools/kafka](https://github.com/ShadobaAI/kafka-tools/tree/main/kafka) или отдельный доступный кластер с тестовыми топиками. |
| Обработчики и вызовы API | [Расширение примеров](https://github.com/ShadobaAI/kafka-adapter-examples). |
| Модульные или интерфейсные сценарии | Рабочий контур из раздела [Тестирование](repositories.md#testing) и инструкция соответствующего репозитория. |
| Выгрузку журналов | Совместимый [HTTP-приёмник](../user/configuration/logging.md#external-logging). Готовые стенды находятся в [kafka-tools](https://github.com/ShadobaAI/kafka-tools). |
| Преобразование с КД 3.1 | Проекты `conversion/KFK` и `conversion/КД`, модуль обмена и [XDTO-пакет](../user/development/conversion-data.md). |

## Локальная документация { #local-documentation }

Из корня `adapter/adapter` в отдельном окружении Python установите зависимости и запустите MkDocs.

```powershell
python -m pip install -r docs/requirements.txt
python -m mkdocs build --strict
python -m mkdocs serve --dev-addr 127.0.0.1:8000
```

Откройте адрес, который выводит MkDocs. В локальном предпросмотре используется путь `/kafka-adapter/`.

Как собираются артефакты и где искать результаты автоматических проверок, описано на странице [Сборка и проверка релиза](release-ci.md).
