"""Stress deck 7: Persian -- right-to-left slides, mixed with English, numbers, and maths."""

import sys
from pathlib import Path

from flexo_talk import Deck


def talk(theme="paper"):
    deck = Deck("fa", theme=theme or "paper")
    with deck.slide("سلام دنیا: ارائه به زبان فارسی") as s:
        s.bullets(
            "این یک جملهٔ فارسی است",
            "می‌خواهیم نیم‌فاصله درست کار کند",
            ["زیرمورد با فاصلهٔ بیشتر"],
            "اعداد فارسی: ۱۲۳ و انگلیسی: 123",
            "ترکیب با English words در وسط جمله",
            "مدل $f_\\theta(x)$ را آموزش می‌دهیم",
        )
    with deck.slide("English title, Persian body", layout="two-columns") as s:
        s.left.bullets("An English list", "stays on the left")
        s.right.bullets("فهرست فارسی", "در سمت راست", numbered=True)
    return deck


if __name__ == "__main__":
    print(talk(*sys.argv[1:2]).build(Path(__file__).resolve().parent / "build" / "persian").summary())
