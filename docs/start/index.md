# Начало работы

Первый обмен можно проверить в одном направлении. Для двустороннего обмена пройдите оба маршрута.

## Что подготовить { #prerequisites }

1. Проверьте [требования](../user/installation/requirements.md) и [подключите адаптер](../user/installation/index.md).
2. Откройте **Kafka → Администрирование** и [включите подсистему](../user/configuration/index.md#enable-integration).
3. Создайте [брокер](../user/configuration/brokers.md) с адресом кластера и его параметрами подключения. Подготовьте тестовые топики и права для чтения или отправки.

## Выберите направление { #direction }

<div class="portal-directions" markdown="1">

<div class="portal-route" markdown="1">

### Из 1С в Kafka { #outgoing }

Настройте продюсер, запишите объект и найдите сообщение в топике.

[Настроить отправку](outgoing.md){ .portal-button }

</div>

<div class="portal-route" markdown="1">

### Из Kafka в 1С { #incoming }

Настройте консьюмер, опубликуйте тестовое сообщение и проверьте запись в 1С.

[Настроить получение](incoming.md){ .portal-button }

</div>

</div>

[Как движется сообщение](../overview/data-flow.md) · [Примеры интеграции](../user/examples/index.md)
