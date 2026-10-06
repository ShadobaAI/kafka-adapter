---
hide:
  - navigation
  - toc
---

<div class="portal-hero" markdown="1">

<div class="portal-hero-copy" markdown="1">

<p class="portal-eyebrow">1С: Адаптер Kafka</p>

# Соедините 1С и Kafka.

<p class="portal-lead">Двусторонний событийный обмен: отправляйте данные из 1С в Kafka и обрабатывайте входящие сообщения в прикладном решении.</p>

<div class="portal-actions" markdown="1">

[Настроить первый обмен](start/index.md){ .portal-button }
[Открыть настройки](user/configuration/index.md){ .portal-button .portal-button-secondary }

</div>

</div>

<div class="portal-flow" aria-label="Двусторонний обмен между 1С, адаптером и Kafka">
<div class="portal-flow-node"><strong>1С</strong><span>Объекты и события</span></div>
<div class="portal-flow-links"><span aria-hidden="true">↔</span><small>Регистрация · обработка</small></div>
<div class="portal-flow-node"><strong>Адаптер</strong><span>Очереди и обработчики</span></div>
<div class="portal-flow-links"><span aria-hidden="true">↔</span><small>Публикация · чтение</small></div>
<div class="portal-flow-node"><strong>Kafka</strong><span>Топики и сообщения</span></div>
</div>

<button type="button" class="portal-search-trigger" data-portal-search aria-label="Открыть поиск по документации">Поиск по документации <span aria-hidden="true">↗</span></button>

</div>

## Уже используете адаптер? { .portal-section-title }

<div class="portal-quick-links" markdown="1">

[Брокеры](user/configuration/brokers.md)
[Выгрузка — продюсеры](user/configuration/producers.md)
[Загрузка — консьюмеры](user/configuration/consumers.md)
[Статусы сообщений](user/operations/statuses.md)
[Диагностика](user/operations/diagnostics.md)
[Готовые примеры](user/examples/index.md)

</div>

## Что вы хотите сделать? { .portal-section-title }

<div class="portal-routes" markdown="1">

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-power-plug-outline:</span>

### Подключить адаптер

Проверьте окружение, выберите способ установки и настройте первый обмен.

[Начать подключение](start/index.md){ .portal-route-link }

</div>

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-code-braces:</span>

### Разработать интеграцию

Подключите прикладной код: API, обработчики продюсера и консьюмера, примеры.

[Руководство по интеграции](user/development/index.md){ .portal-route-link }

</div>

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-lifebuoy:</span>

### Решить проблему

Найдите причину ошибок, проверьте очереди и фоновые задания.

[Диагностика и эксплуатация](user/operations/index.md){ .portal-route-link }

</div>

<div class="portal-route" markdown="1">

<span class="portal-route-icon" aria-hidden="true">:material-source-branch:</span>

### Развивать адаптер

Подготовьте окружение, изучите устройство подсистемы и правила участия.

[Руководство разработчика адаптера](project/index.md){ .portal-route-link }

</div>

</div>

## Два направления обмена { .portal-section-title }

<div class="portal-directions" markdown="1">

<div class="portal-route" markdown="1">

### 1С → Kafka

Настройте продюсер, зарегистрируйте данные и проверьте публикацию сообщения в топике.

[Маршрут отправки](start/outgoing.md){ .portal-route-link }

</div>

<div class="portal-route" markdown="1">

### Kafka → 1С

Настройте консьюмер и обработчик, получите сообщение и проверьте результат в 1С.

[Маршрут получения](start/incoming.md){ .portal-route-link }

</div>

</div>

## Частые вопросы { .portal-section-title }

<div class="portal-faq-preview" markdown="1">

- [Какие платформа и БСП нужны?](faq/index.md#installation)
- [Как настроить защищённое подключение?](faq/index.md#configuration)
- [Какие API использовать в прикладном коде?](faq/index.md#integration)
- [Что проверить, если сообщения остались в очереди?](faq/index.md#operations)
- [С чего начать разработку самого адаптера?](faq/index.md#contributors)

[Все вопросы и ответы](faq/index.md){ .portal-route-link }

</div>

[Возможности и быстрый старт](overview/capabilities.md) · [Глоссарий Kafka](glossary.md)
