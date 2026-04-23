# Генерация XSD из AsyncAPI

Для работы адаптера с произвольным контрактом данных (не EnterpriseData) потребуется **XDTO-пакет**. Создать его можно двумя способами — вручную в EDT или сгенерировать из AsyncAPI-спецификации.

## Скрипт `asyncapi2xsd.py`

Скрипт из [набора скриптов](https://github.com/ShadobaAI/kafka-tools) принимает YAML-файл в формате [AsyncAPI](https://studio.asyncapi.com/) и генерирует XSD-схему, которую затем импортируют в XDTO-пакет.

## Запуск

```bash
python asyncapi2xsd.py spec.yaml out.xsd \
  -n http://example.com/ns \
  --prefix crm. \
  --suffix .changed
```

| Аргумент | Назначение |
|----------|------------|
| `spec.yaml` | Входной файл AsyncAPI |
| `out.xsd` | Результирующий файл XSD |
| `-n` | targetNamespace — пространство имён XDTO-пакета |
| `--prefix` | Префикс адреса канала (обрезается при формировании имени типа) |
| `--suffix` | Суффикс адреса канала (обрезается при формировании имени типа) |

## Правила генерации

### Именование типов

Из адреса канала `<prefix><имя><suffix>` тип получает имя `<Имя>` (первая буква **заглавная**). Для схем без канала — имя схемы с заглавной первой буквой.

**Пример:**

- Канал: `crm.order.changed`
- Префикс: `crm.`, суффикс: `.changed`
- Результат: `Order`

### Соответствие JSON Schema → XSD

| JSON Schema | XSD-тип |
|------------|---------|
| `string` | `xs:string` |
| `string`, `format: uuid` | `tns:UUID` (restriction с паттерном UUID) |
| `string`, `format: date-time` | `xs:dateTime` |
| `string`, `format: date` | `xs:date` |
| `string`, `format: time` | `xs:time` |
| `string`, `maxLength: 36` или `minLength: 36` | `tns:UUID` |
| `integer` | `xs:int` |
| `number` | `xs:decimal` |
| `boolean` | `xs:boolean` |

### Структурные конструкции

| Конструкция в схеме | Результат в XSD |
|---------------------|----------------|
| `enum` (inline) | `xs:simpleType` с именем `{ТипРодитель}.{ИмяПоля}` |
| `$ref` на enum-схему | отдельный `xs:simpleType` |
| `$ref` на объект | ссылка `tns:{ИмяТипа}` |
| `type: object` (вложенный) | `xs:complexType` с именем `{ТипРодитель}.{ИмяПоля}` |
| `type: array`, items — объект | два типа: `{ТипРодитель}.{ИмяПоля}` (таблица с элементом `row` `maxOccurs="unbounded"`) и `{ТипРодитель}.{ИмяПоля}.Row` (тип строки) |
| `type: array`, items — примитив | элемент с `maxOccurs="unbounded"` |

### Опциональные поля

Поля, **не перечисленные** в массиве `required`, получают атрибут `nillable="true"`.

### Параметры XSD

- `elementFormDefault="qualified"`;
- `attributeFormDefault="unqualified"`;
- `targetNamespace` задаётся через аргумент `-n`.

## Импорт XSD в XDTO-пакет

После генерации XSD:

1. Откройте XDTO-пакет в EDT или Конфигураторе.
2. Импортируйте XSD через стандартное меню импорта.
3. Проверьте типы — структура должна соответствовать схеме.
4. Используйте полученный XDTO-пакет в настройках продюсера/консьюмера в поле **Формат сериализации / десериализации**.

## Смотрите также

- [Расширение адаптера](extending.md).
- [Конвертация данных 3.1 (руководство пользователя)](../user/development/conversion-data.md).
- [Набор скриптов](https://github.com/ShadobaAI/kafka-tools) — репозиторий с `asyncapi2xsd.py` и другими утилитами.
