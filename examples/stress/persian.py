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
    with deck.slide("جدول نتایج") as s:
        s.table([["مدل", "دقت (٪)", "پارامترها"], ["ترنسفورمر", "۸۱٫۲", "86M"], ["شبکهٔ کانولوشنی", "76.1", "25M"]])
    with deck.slide("یک شکل", layout="two-columns") as s:
        with s.right.figure() as figure:
            x = figure.text("x", "ورودی $x$")
            encoder = figure.block("enc", label="رمزگذار", input=x, tone="encoder")
            figure.block("head", label="طبقه‌بند", input=encoder, tone="head")
        s.left.bullets("شکل‌ها هم فارسی می‌شوند")
    with deck.slide("نمودار") as s:
        import matplotlib

        matplotlib.use("svg")
        import matplotlib.pyplot as plt

        with deck.plotting():
            figure, axes = plt.subplots()
            axes.plot([0, 1, 2, 3], [3, 2, 1.5, 1.2], label="خطای آموزش")
            axes.set_xlabel("دوره")
            axes.set_ylabel("خطا")
            axes.legend()
        s.plot(figure)
    return deck


if __name__ == "__main__":
    print(talk(*sys.argv[1:2]).build(Path(__file__).resolve().parent / "build" / "persian").summary())
