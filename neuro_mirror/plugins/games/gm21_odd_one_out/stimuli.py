"""Image categories and session settings for GM-21."""

MINIMUM_SESSION_MS = 60_000
REQUIRED_TRIALS = 12

CATEGORIES = {
    "Животные": (
        ("Кошка", "cat.png"),
        ("Собака", "dog.png"),
        ("Медведь", "bear.png"),
        ("Лиса", "fox.png"),
        ("Лягушка", "frog.png"),
        ("Лев", "lion.png"),
        ("Обезьяна", "monkey.png"),
        ("Мышь", "mouse.png"),
        ("Панда", "panda.png"),
        ("Кролик", "rabbit.png"),
    ),
    "Продукты": (
        ("Яблоко", "apple.png"),
        ("Хлеб", "bread.png"),
        ("Морковь", "carrot.png"),
        ("Кукуруза", "corn.png"),
        ("Виноград", "grapes.png"),
        ("Лимон", "lemon.png"),
        ("Апельсин", "orange.png"),
        ("Груша", "pear.png"),
        ("Клубника", "strawberry.png"),
        ("Помидор", "tomato.png"),
        ("Арбуз", "watermelon.png"),
    ),
    "Инструменты": (
        ("Ножницы", "scissors.png"),
        ("Ключ", "key.png"),
        ("Карандаш", "pencil.png"),
        ("Весы", "scales.png"),
    ),
}
