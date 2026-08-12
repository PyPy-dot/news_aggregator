#!/usr/bin/env python3
"""
Скрипт для замены callback.message.answer на edit_text с try/except.
"""

import re

filepath = 'services/bot/handlers/tasks.py'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Простая замена - ищем паттерны где callback.message.answer используется без try
# Заменяем на try/except блок

# Паттерн: строка с отступом, затем await callback.message.answer(
pattern = r'(    +)await callback\.message\.answer\(\s*\n'

def replace_with_try(match):
    indent = match.group(1)
    return f'{indent}try:\n{indent}    await callback.message.edit_text(\n'

# Сначала заменим начала
content = re.sub(pattern, replace_with_try, content)

# Теперь нужно добавить except после закрывающей скобки reply_markup=keyboard
# Паттерн: reply_markup=keyboard\n        )\n\n
pattern2 = r'(reply_markup=keyboard\s*\n\s*\))\n(\s*)except Exception:'
# Проверяем есть ли уже except
if 'except Exception:' not in content:
    content = re.sub(r'(reply_markup=keyboard\s*\n\s*\))(\n)', r'\1\n\2    except Exception:\n\2        await callback.message.answer(', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Готово! Проверьте файл.")
