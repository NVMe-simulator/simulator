# Как контрибьютить

```sh
cmake --preset dev                         # Настроить сборку
cmake --build --preset dev --parallel       # Собрать
cmake --build --preset dev --target lint    # Проверить кодстайл
cmake --build --preset dev --target format  # Исправить форматирование
```

Модули подключаем через `add_subdirectory` в `CMakeLists.txt`

## Кодстайл (слоп, исправления принимаются)

Основа — [Google C++ Style](https://google.github.io/styleguide/cppguide.html): **4 пробела, 120 символов**, UTF-8, LF.
Остальное форматирует clang-format. Используем `override` и `nullptr`.

### Имена

| Что | Пример |
| --- | --- |
| Классы, структуры, union | `TController` |
| Интерфейсы | `IBlockDevice` |
| Namespace | `NSimulator` |
| Типы enum | `EStatus` |
| Функции и методы | `SubmitCommand` |
| Переменные и параметры | `queue_id` |
| Public/protected поля классов и структур | `QueueId` |
| Private поля классов и структур | `QueueId_` |
| Глобальные/static константы, constexpr переменные | `kPageSize` |
| Макросы | `NVME_VERSION` |
| Алиасы, typedef, параметры шаблонов типов | `ValueType` |

**Интерфейс** — класс/структура без полей, но с виртуальными методами.
Учитываются наследование, статические поля и виртуальный деструктор; чисто виртуальные методы не обязательны.

Значения enum:

- Обычный enum вне класса/структуры: `EFetchType { FT_SIMPLE, FT_DEBUG }` — префикс из заглавных букв имени без `E`.
- `enum class` и enum внутри класса/структуры: `EStatus { Created, Running }` — без префикса.

### Include

В той же папке — `"foo.h"`, в остальных случаях — `<>` и для файлов проекта путь от корня репозитория.
Порядок: соответствующий заголовок → C/POSIX → C++ → остальные. Между группами пустая строка, внутри — алфавит.

```cpp
#include "foo.h"

#include <unistd.h>

#include <iostream>

#include <src/queue/command.h>
```
