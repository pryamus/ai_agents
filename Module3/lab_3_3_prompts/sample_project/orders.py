"""Учебный сервис заказов (намеренно содержит проблемы для инструментов 2.6)."""

import os  # F401: импорт не используется — ruff должен это найти

# TODO: вынести лимит в конфиг — grep_search должен найти эту строку
DISCOUNT_LIMIT = 0.5


def apply_discount(price: float, rate: float) -> float:
    """Применить скидку к цене со строгой проверкой диапазона."""
    if rate < 0 or rate > DISCOUNT_LIMIT:
        raise ValueError("rate вне допустимого диапазона")
    return price * (1 - rate)
