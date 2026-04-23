# Примеры

Готовые рецепты для типовых задач. Основаны на реальном коде из [тестового проекта](https://github.com/ShadobaAI/kafka-adapter-tester).

!!! note "Предварительные условия"
    Все примеры предполагают, что адаптер [установлен и подключён](../installation/index.md), подсистема включена и создан хотя бы один [брокер](../configuration/brokers.md).

## Отправка данных из 1С в Kafka

<div class="grid cards" markdown>

-   :material-database-outline: **[Сериализация справочника](outgoing-catalog.md)**

    ---

    Простейший случай — JSON-сообщение при записи элемента справочника.

-   :material-table:{ .lg } **[Документ с табличной частью](outgoing-document.md)**

    ---

    Сериализация документа с строками табличной части.

-   :material-database-sync:{ .lg } **[Независимый регистр сведений](outgoing-register.md)**

    ---

    Запись набора записей регистра — одна запись = одно сообщение.

-   :material-playlist-edit:{ .lg } **[Регистр по регистратору](outgoing-recorder.md)**

    ---

    Все движения документа в одном сообщении (пакетная модель).

-   :material-block-helper:{ .lg } **[Подавление регистрации](suppress.md)**

    ---

    Как исключить объект из обмена в обработчике `ПередЗаписью`.

-   :material-send:{ .lg } **[Принудительная регистрация](force-registration.md)**

    ---

    Отправка объектов из кода в обход подписок.

-   :material-message-flash:{ .lg } **[Произвольные события](custom-events.md)**

    ---

    Отправка событий, не связанных с объектами 1С.

</div>

## Получение данных из Kafka в 1С

<div class="grid cards" markdown>

-   :material-database-import:{ .lg } **[Upsert справочника](incoming-catalog.md)**

    ---

    Создание или обновление элемента справочника по UUID из сообщения.

-   :material-database-edit:{ .lg } **[Запись в регистр сведений](incoming-register.md)**

    ---

    Десериализация в независимый регистр сведений.

-   :material-close-circle-outline:{ .lg } **[Отмена обработки](incoming-cancel.md)**

    ---

    Отказ с сохранением причины в журнал обмена.

</div>

## Специальные сценарии

<div class="grid cards" markdown>

-   :material-security:{ .lg } **[Защищённое подключение](secure-connection.md)**

    ---

    SASL/PLAIN, SASL/SCRAM, SSL/TLS.

-   :material-flash:{ .lg } **[Прямой API](direct-api.md)**

    ---

    Синхронная отправка и чтение без фоновых заданий.

</div>
