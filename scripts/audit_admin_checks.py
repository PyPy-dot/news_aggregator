#!/usr/bin/env python3
"""
Аудит проверок прав администратора в хендлерах.

Проверяет все @admin.message и @admin.message(Command) хендлеры,
фиксирует отсутствие проверок check_admin_access.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

# Корень проекта
project_root = Path(__file__).parent.parent
handlers_dir = project_root / 'services' / 'bot' / 'handlers'


def check_file_for_admin_access(filepath: Path) -> List[Tuple[int, str, str, bool]]:
    """
    Проверить файл на наличие проверок прав.

    Returns:
        List кортежей: (line_number, handler_type, handler_name, has_check)
    """
    results = []

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Ищем @admin.message или @admin.message(Command)
        if '@admin.message' in line or '@admin.message(' in line:
            # Определяем тип хендлера
            if 'Command(' in line:
                handler_type = 'COMMAND'
            elif 'F.text' in line or 'StateFilter' in line:
                handler_type = 'MESSAGE_STATE'
            else:
                handler_type = 'MESSAGE'

            # Находим название функции
            func_name = 'unknown'
            j = i
            while j < len(lines):
                if 'async def ' in lines[j]:
                    match = re.search(r'async def\s+(\w+)', lines[j])
                    if match:
                        func_name = match.group(1)
                    break
                j += 1

            # Проверяем, есть ли проверка check_admin_access в следующих строках
            has_check = False
            # Ищем начало функции и проверяем дальше
            func_start = i
            for k in range(i, min(i + 20, len(lines))):
                if 'async def ' in lines[k]:
                    func_start = k
                    break

            # Проверяем следующие 15 строк после начала функции
            for k in range(func_start, min(func_start + 15, len(lines))):
                if 'check_admin_access' in lines[k]:
                    has_check = True
                    break
                # Если дошли до следующего декоратора или функции — останавливаемся
                if k > func_start and ('@admin.' in lines[k] or 'async def ' in lines[k]):
                    break

            results.append((i + 1, handler_type, func_name, has_check))

        i += 1

    return results


def main():
    print("=" * 80)
    print("🔍 АУДИТ ПРОВЕРОК ПРАВ АДМИНИСТРАТОРА")
    print("=" * 80)
    print()

    all_issues = []

    # Проверяем все файлы хендлеров
    for filepath in sorted(handlers_dir.glob('*.py')):
        if filepath.name in ('__init__.py', 'router.py', 'access.py', 'keyboards.py', 'states.py', 'filters.py'):
            continue

        results = check_file_for_admin_access(filepath)

        if results:
            print(f"📄 {filepath.name}:")
            print("-" * 60)

            has_issues = False
            for line_num, handler_type, func_name, has_check in results:
                status = "✅" if has_check else "❌"
                print(f"  {status} {line_num}: {handler_type} {func_name}()")

                if not has_check:
                    has_issues = True
                    all_issues.append((filepath.name, line_num, handler_type, func_name))

            if has_issues:
                print()
            print()

    # Итог
    print("=" * 80)
    print("📊 ИТОГИ")
    print("=" * 80)
    print()

    if all_issues:
        print(f"⚠️  Найдено {len(all_issues)} хендлеров БЕЗ проверки прав:\n")
        for filename, line_num, handler_type, func_name in all_issues:
            print(f"  • {filename}:{line_num} — {handler_type} {func_name}()")
        print()
        print("📝 Рекомендация: Добавить 'if not await check_admin_access(message): return'")
        print("   в начало каждого хендлера, обрабатывающего пользовательский ввод.")
    else:
        print("✅ Все хендлеры имеют проверку прав администратора!")

    print()

    return len(all_issues)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
