#!/usr/bin/env python3
"""
Исправление callback_query хендлеров: замена answer на edit_text с try/except.
Запускается из корня проекта.
"""

import re

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    result = []
    i = 0
    in_callback_handler = False

    while i < len(lines):
        line = lines[i]

        # Определяем начало callback_query хендлера
        if '@admin.callback_query' in line:
            in_callback_handler = True
            result.append(line)
            i += 1
            continue

        # Определяем конец callback_query хендлера
        if in_callback_handler and (line.startswith('@') or (line.strip().startswith('async def') and i > 0)):
            in_callback_handler = False

        # Если в callback_handler и нашли answer без try
        if in_callback_handler and 'await callback.message.answer(' in line:
            # Проверяем есть ли try в предыдущих строках
            has_try = False
            for j in range(max(0, len(result)-5), len(result)):
                if 'try:' in result[j]:
                    has_try = True
                    break

            if not has_try:
                indent = len(line) - len(line.lstrip())
                indent_str = ' ' * indent

                # Собираем весь блок answer (может быть многострочным)
                block_lines = [line]
                j = i + 1
                paren_count = line.count('(') - line.count(')')
                while j < len(lines) and paren_count > 0:
                    block_lines.append(lines[j])
                    paren_count += lines[j].count('(') - lines[j].count(')')
                    j += 1

                # Создаём новый блок с try/except
                # Извлекаем аргументы answer
                args_lines = []
                for bl in block_lines:
                    # Заменяем answer на edit_text в первой строке
                    if 'await callback.message.answer(' in bl:
                        new_bl = bl.replace('await callback.message.answer(', 'await callback.message.edit_text(')
                        args_lines.append(new_bl)
                    else:
                        args_lines.append(bl)

                # Добавляем try блок
                result.append(f'{indent_str}try:')
                result.extend(args_lines)

                # Добавляем except блок с answer
                result.append(f'{indent_str}except Exception:')
                answer_args_lines = []
                for bl in block_lines:
                    if 'await callback.message.edit_text(' in bl:
                        new_bl = bl.replace('await callback.message.edit_text(', 'await callback.message.answer(')
                        answer_args_lines.append(new_bl)
                    else:
                        answer_args_lines.append(bl)
                result.extend(answer_args_lines)

                # Пропускаем обработанные строки
                i = j
                continue

        result.append(line)
        i += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(''.join(result))

    print(f"✅ Файл {filepath} исправлен")

if __name__ == '__main__':
    fix_file('services/bot/handlers/tasks.py')
