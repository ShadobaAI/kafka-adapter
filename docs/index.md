---
hide:
  - navigation
  - toc
---

<div class="portal-hero" markdown="1">

<div class="portal-hero-copy" markdown="1">

# Обмен между 1С и Kafka { #kafka-adapter }

<p class="portal-lead">Адаптер публикует изменения из 1С и передаёт сообщения Kafka прикладным обработчикам. Состояние обмена хранится в очередях 1С.</p>

<div class="portal-actions" markdown="1">

[Настроить первый обмен](start/index.md){ .portal-button }
[Открыть API](user/development/api.md){ .portal-button .portal-button-secondary }

</div>

</div>

<div class="portal-flow" role="img" aria-label="Двусторонний обмен между 1С, очередями адаптера и Kafka">
  <div class="portal-flow-node"><strong>1С</strong><span>Объекты и события</span></div>
  <div class="portal-flow-links"><span aria-hidden="true">↔</span></div>
  <div class="portal-flow-node"><strong>Адаптер</strong><span>Очереди и обработчики</span></div>
  <div class="portal-flow-links"><span aria-hidden="true">↔</span></div>
  <div class="portal-flow-node"><strong>Kafka</strong><span>Топики и сообщения</span></div>
</div>

</div>

## Что вы хотите сделать? { #tasks .portal-section-title }

<div class="portal-routes" markdown="1">

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-power-plug-outline:</span>

### Подключить адаптер { #install }

Проверьте требования и выберите способ установки.

[Установка и подключение](user/installation/index.md){ .portal-route-link }

</div>

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-code-braces:</span>

### Написать интеграцию { #integrate }

Справочник обработчиков, контракты сообщений и примеры.

[Разработка интеграции](user/development/index.md){ .portal-route-link }

</div>

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-lifebuoy:</span>

### Разобрать сбой { #troubleshoot }

Проверьте очереди, статусы и журнал сообщения.

[Эксплуатация и диагностика](user/operations/index.md){ .portal-route-link }

</div>

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-source-branch:</span>

### Изменить адаптер { #develop }

Подготовьте окружение и найдите исходники, тесты и правила работы.

[Разработка адаптера](project/index.md){ .portal-route-link }

</div>

</div>

## Быстрые ссылки { #quick-links .portal-section-title }

<div class="portal-quick-links" markdown="1">

[Брокеры](user/configuration/brokers.md)
[Продюсеры](user/configuration/producers.md)
[Консьюмеры](user/configuration/consumers.md)
[Статусы сообщений](user/operations/statuses.md)
[Примеры](user/examples/index.md)
[Потоки данных](overview/data-flow.md)

</div>

[Частые вопросы](faq/index.md) · [Глоссарий Kafka](glossary.md) · [Возможности адаптера](overview/capabilities.md)
