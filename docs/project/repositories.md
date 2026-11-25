# Репозитории

Пути указаны от корня рабочего каталога Kafka, например `C:\EDT\projects\kafka`. Начните с [kafka-adapter-workspace](https://github.com/ShadobaAI/kafka-adapter-workspace). Корневой репозиторий хранит инструкции, профили и структуру каталогов. Вложенные репозитории клонируются отдельно. Порядок восстановления описан в README рабочего пространства.

## Адаптер, база и Конвертация данных { #adapter }

| Каталог | Состав |
|---|---|
| `adapter/adapter` | [kafka-adapter](https://github.com/ShadobaAI/kafka-adapter). Продуктовая подсистема, документация и конвейер релизов. |
| `adapter/base` | [kafka-adapter-base](https://github.com/ShadobaAI/kafka-adapter-base). Базовая конфигурация с БСП для разработки и отладки. |
| `adapter/examples` | [kafka-adapter-examples](https://github.com/ShadobaAI/kafka-adapter-examples). Расширение с демонстрационными обработчиками и сценариями. Предназначено для разработки. |
| `conversion/KFK` | [kafka-adapter-conv](https://github.com/ShadobaAI/kafka-adapter-conv). Расширение Конвертации данных 3.1 для подготовки модуля обмена с произвольным XDTO. |
| `conversion/КД` | Локальная базовая конфигурация Конвертации данных. Получается отдельно. |

## Тестирование { #testing }

| Каталог | Состав |
|---|---|
| `tests/unit/base` | База тестового проекта, собираемая из `adapter/base` и `adapter/adapter`. |
| `tests/unit/examples` | Отдельный checkout [расширения примеров](https://github.com/ShadobaAI/kafka-adapter-examples) для модульных тестов. |
| `tests/unit/unit` | [kafka-adapter-tests-unit](https://github.com/ShadobaAI/kafka-adapter-tests-unit). Модульные и интеграционные сценарии адаптера на YAxUnit. |
| `tests/unit/yaxunit` | Отдельный checkout [YAxUnit](https://github.com/bia-technologies/yaxunit). |
| `tests/ui` | [kafka-adapter-tests-ui](https://github.com/ShadobaAI/kafka-adapter-tests-ui). Сценарии Vanessa Automation для интерфейса 1С. |
| `tests/reports` | [kafka-adapter-tests-reports](https://github.com/ShadobaAI/kafka-adapter-tests-reports). Опубликованные отчёты Allure Unit, Allure UI и SonarQube. |

Для локального запуска используйте инструкции из README нужного тестового репозитория. Скрипты сборки для unit-контура пересоздают только `tests/unit/base`. Примеры, тесты и YAxUnit подключаются к базе отдельными расширениями.

[Как устроен запуск в CI](release-ci.md) · [Последние опубликованные отчёты](https://shadobaai.github.io/kafka-adapter-tests-reports/latest/)

## Инструменты и задачи { #tools-and-tasks }

| Каталог | Состав |
|---|---|
| `tools` | [kafka-tools](https://github.com/ShadobaAI/kafka-tools). Стенды Kafka и внешнего логирования, сборочные инструменты, генератор XSD. |
| `tasks` | [kfk-tasks](https://github.com/ShadobaAI/kfk-tasks). Задачи, спецификации изменений (SDD) и архитектурные решения (ADR). |

Профили 1C AI Core находятся в `adapter/.ai`, `conversion/.ai` и `tests/.ai`. Для работы выбирайте профиль нужного рабочего каталога. Правила владения источниками описаны в инструкциях корневого репозитория.

## Внешние проекты { #external-projects }

- [Simple Kafka Connector 1C](https://github.com/NuclearAPK/Simple-Kafka_Adapter) — транспортная компонента.
- [Kafka1CExtension](https://github.com/NuclearAPK/Kafka1CExtension) — проект, с которого начиналась разработка адаптера.
- [JSONEditor](https://github.com/josdejong/jsoneditor) — встроенный редактор JSON.
