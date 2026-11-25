# 1С: Адаптер Kafka

[![OpenYellow](https://openyellow.openintegrations.dev/data/badges/1183456860.svg)](https://openyellow.org/grid?filter=top&repo=1183456860)
![Платформа](https://badgen.net/badge/Платформа/8.3.26+/blue)
![Лицензия](https://badgen.net/badge/Лицензия/MPL-2.0/green)
![БСП](https://badgen.net/badge/БСП/3.1.10+/blue)

Встраиваемая подсистема для двустороннего обмена между **1С:Предприятием** и **Apache Kafka** на базе [Simple Kafka Connector 1C](https://github.com/NuclearAPK/Simple-Kafka_Adapter). Например, из 1С можно публиковать изменения номенклатуры для интернет-магазина, а из Kafka получать заказы для записи в 1С.

Адаптер ведёт очереди и запускает фоновые задания. В прикладной конфигурации вы определяете, какие события публиковать, как выглядит сообщение и что делать с полученными данными.

## [Документация →](https://shadobaai.github.io/kafka-adapter/)

[Внедрение и настройка](https://shadobaai.github.io/kafka-adapter/user/) · [Справочник API](https://shadobaai.github.io/kafka-adapter/user/development/api/) · [Примеры](https://shadobaai.github.io/kafka-adapter/user/examples/) · [Эксплуатация](https://shadobaai.github.io/kafka-adapter/user/operations/)

## Быстрый старт

1. Скачайте файл поставки и подключите адаптер как расширение или встройте в основную конфигурацию. [Релизы](https://github.com/ShadobaAI/kafka-adapter/releases) · [Установка и подключение](https://shadobaai.github.io/kafka-adapter/user/installation/)
2. Включите подсистему, настройте брокер и добавьте продюсер для отправки или консьюмер для получения. Настройте расписание регламентного задания и включите его. [Начало работы](https://shadobaai.github.io/kafka-adapter/start/) · [Фоновые задания](https://shadobaai.github.io/kafka-adapter/user/configuration/jobs/)
3. Проверьте обмен со справочником. [Отправка из 1С в Kafka](https://shadobaai.github.io/kafka-adapter/user/examples/outgoing-catalog/) · [Загрузка из Kafka в 1С](https://shadobaai.github.io/kafka-adapter/user/examples/incoming-catalog/)

## Возможности

**1С → Kafka**

- Автоматическая регистрация объектов при записи по настройкам продюсера. Постановка в очередь также доступна вручную и через API.
- Формирование сообщений произвольным обработчиком или по правилам Конвертации данных 3.1.
- Фоновая отправка в Kafka с настраиваемым числом потоков.

**Kafka → 1С**

- Чтение топиков с сохранением сообщений во входящей очереди 1С.
- Фоновая обработка прикладным кодом или по правилам Конвертации данных 3.1.
- Отложенный повтор по запросу обработчика.

В обоих направлениях можно включить проверку повторов по содержимому. Адаптер сравнивает хэш тела с хэшем последнего успешно выгруженного или обработанного сообщения по тому же ключу записи. Для отправки и чтения из прикладного кода без очередей предусмотрен отдельный API. [Потоки данных](https://shadobaai.github.io/kafka-adapter/overview/data-flow/) · [Идемпотентность](https://shadobaai.github.io/kafka-adapter/user/examples/idempotency/) · [Прямой API](https://shadobaai.github.io/kafka-adapter/user/development/direct-api/)

**Эксплуатация**

- Статусы и журнал сообщений в 1С. Историю выгрузки объекта можно открыть из его формы или списка сочетанием `Ctrl+H`.
- Уведомления в Telegram об ошибках и нарушениях SLA при включённом контроле интеграции.
- Выгрузка журнала обмена через совместимый HTTP-приёмник для хранения и анализа логов.

## Требования

| Компонент | Требование |
|---|---|
| **Платформа запуска** | 1С:Предприятие 8.3.26 или новее |
| **Режим совместимости** | 8.3.21 |
| **Информационная база** | Клиент-серверный режим |
| **Лицензия 1С** | ПРОФ или КОРП |
| **ОС сервера 1С** | Windows x64 или Linux x64 с glibc 2.28 или новее |
| **БСП** | 1С:Библиотека стандартных подсистем 3.1.10 или новее |
| **Kafka** | Кластер, доступный с сервера 1С |
| **Внешняя компонента** | Simple Kafka Connector 1C входит в поставку адаптера |

[Требования к окружению](https://shadobaai.github.io/kafka-adapter/user/installation/requirements/)

## Лицензия

[Mozilla Public License 2.0](LICENSE).

## Участие в разработке

Для вопросов, сообщений об ошибках и предложений используйте [GitHub Issues](https://github.com/ShadobaAI/kafka-adapter/issues). Инструкции по подготовке рабочей среды и изменений собраны в документации. [Разработка адаптера](https://shadobaai.github.io/kafka-adapter/project/) · [Участие в разработке](https://shadobaai.github.io/kafka-adapter/project/contributing/)
