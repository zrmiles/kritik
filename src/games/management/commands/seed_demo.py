from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from games.models import Game, Genre, Platform
from reviews.models import Review

# Slug жанров и платформ совпадают со slug RAWG, чтобы импорт не создавал дубликатов в фильтрах.
GENRES = {
    "action": "Экшен",
    "adventure": "Приключения",
    "rpg": ("role-playing-games-rpg", "Ролевая"),
    "simulation": "Симулятор",
    "platformer": "Платформер",
    "indie": "Инди",
    "strategy": "Стратегия",
    "shooter": "Шутер",
    "puzzle": "Головоломка",
    "racing": "Гонки",
    "card": "Карточная",
}
PLATFORMS = {
    "pc": "PC",
    "ps5": ("playstation5", "PlayStation 5"),
    "ps4": ("playstation4", "PlayStation 4"),
    "xsx": ("xbox-series-x", "Xbox Series S/X"),
    "xone": ("xbox-one", "Xbox One"),
    "switch": ("nintendo-switch", "Nintendo Switch"),
    "ios": ("ios", "iOS"),
    "android": ("android", "Android"),
    "mac": ("macos", "macOS"),
}

CRITICS = {
    "maria": "Мария",
    "nikita": "Никита",
    "ilya": "Илья",
    "anya": "Аня",
    "dasha": "Даша",
    "roman": "Роман",
    "lera": "Лера",
    "maks": "Макс",
    "katya": "Катя",
    "artem": "Артём",
    "misha": "Миша",
    "sonya": "Соня",
    "gleb": "Глеб",
    "vera": "Вера",
}

# (slug, название, тема обложки, дата выхода, жанры, платформы, описание, [(критик, оценка, текст)])
GAMES = [
    (
        "hades", "Hades", "oxblood", date(2020, 9, 17), "action indie", "pc switch ps5 ps4 xsx xone",
        "Побег из подземного мира, который никогда не проходит одинаково. Каждый забег меняет набор "
        "способностей, а сюжет продвигается даже после поражения.",
        [
            ("maria", 9, "Бои быстрые, а персонажи раскрываются даже после десятков попыток."),
            ("nikita", 10, "Редкий случай, когда хочется начать ещё один забег сразу после финала."),
            ("gleb", 8, "Отличный ритм, но к сороковому забегу оружия начинают повторяться."),
        ],
    ),
    (
        "outer-wilds", "Outer Wilds", "indigo", date(2019, 5, 28), "adventure puzzle indie", "pc ps4 xone switch",
        "Солнечная система, которая взрывается каждые двадцать две минуты. Единственное, что сохраняется "
        "между циклами, — ваши знания.",
        [
            ("ilya", 10, "Лучше идти без подсказок: открытия здесь и есть главный игровой процесс."),
            ("anya", 9, "Необычный мир, к которому мысленно возвращаешься ещё долго."),
            ("roman", 6, "Идея гениальная, но управление кораблём меня регулярно бесило."),
        ],
    ),
    (
        "hollow-knight", "Hollow Knight", "slate", date(2017, 2, 24), "action platformer indie", "pc switch ps4 xone",
        "Огромное заброшенное королевство насекомых. Карту нужно покупать, дорогу — запоминать, "
        "а боссов — изучать до последнего движения.",
        [
            ("dasha", 10, "Большой мир, который постоянно вознаграждает за любопытство."),
            ("roman", 9, "Сложно, но каждая победа ощущается заслуженной."),
            ("vera", 7, "Красиво, но слишком много бега обратно к боссу после смерти."),
        ],
    ),
    (
        "disco-elysium", "Disco Elysium", "mustard", date(2019, 10, 15), "rpg", "pc ps4 ps5 xone xsx switch mac",
        "Ролевая игра без боёв: детектив с амнезией расследует убийство, споря с собственными навыками.",
        [
            ("lera", 10, "Потрясающий текст и персонажи, о которых хочется спорить."),
            ("maks", 9, "Необычная ролевая игра для тех, кто любит читать и выбирать."),
            ("nikita", 10, "Лучший сценарий, что я встречал в играх. Точка."),
            ("artem", 5, "Честно пытался, но столько текста — это уже книга, а не игра."),
        ],
    ),
    (
        "stardew-valley", "Stardew Valley", "bottle", date(2016, 2, 26), "simulation rpg indie",
        "pc switch ps4 xone ios android mac",
        "Заброшенная дедушкина ферма, городок с соседями и календарь, в котором всегда есть чем заняться.",
        [
            ("katya", 10, "Возвращаюсь сюда, когда хочется спокойного вечера."),
            ("artem", 9, "Каждый сезон приносит что-то новое."),
            ("sonya", 8, "Затягивает сильнее, чем ожидаешь от игры про репу."),
        ],
    ),
    (
        "celeste", "Celeste", "plum", date(2018, 1, 25), "platformer indie", "pc switch ps4 xone",
        "Точный платформер о подъёме на гору и о тревоге, с которой героиня учится жить.",
        [
            ("misha", 9, "Очень отзывчивое управление: ошибки чувствуются честными."),
            ("sonya", 10, "Сильная история и музыка, которая остаётся в памяти."),
        ],
    ),
    (
        "the-witcher-3-wild-hunt", "The Witcher 3: Wild Hunt", "rust", date(2015, 5, 19), "rpg action",
        "pc ps4 xone switch ps5 xsx",
        "Геральт ищет Цири в мире, где у каждого побочного задания есть своя маленькая драма.",
        [
            ("gleb", 10, "Побочные квесты сильнее основных сюжетов многих других игр."),
            ("maria", 9, "Боевая система так себе, но мир и истории всё перекрывают."),
            ("ilya", 8, "Слишком много вопросиков на карте Скеллиге, в остальном шедевр."),
            ("vera", 9, "«Кровавый барон» — лучший квест, что я проходила."),
        ],
    ),
    (
        "elden-ring", "Elden Ring", "ink", date(2022, 2, 25), "rpg action", "pc ps5 ps4 xsx xone",
        "Открытый мир от FromSoftware: никаких подсказок, много смертей и ощущение настоящего открытия "
        "за каждым холмом.",
        [
            ("roman", 10, "Первый выход в Лимгрейв я запомню надолго."),
            ("dasha", 9, "Сложно, но открытый мир даёт уйти и вернуться сильнее."),
            ("katya", 4, "Не моё: слишком жёстко и почти ничего не объясняют."),
        ],
    ),
    (
        "baldurs-gate-3", "Baldur's Gate 3", "oxblood", date(2023, 8, 3), "rpg strategy", "pc ps5 xsx mac",
        "Пошаговая ролевая игра по правилам D&D, где почти любую проблему можно решить тремя разными способами.",
        [
            ("lera", 10, "Игра честно отвечает на самые странные решения игрока."),
            ("maks", 9, "Третий акт проседает по производительности, но это мелочь."),
            ("artem", 9, "Прошёл с другом в кооперативе — лучший вечер года."),
            ("anya", 8, "Потрясающе, но на третьем акте я устала от объёма."),
        ],
    ),
    (
        "portal-2", "Portal 2", "slate", date(2011, 4, 19), "puzzle shooter", "pc mac",
        "Головоломки с порталами, язвительный искусственный интеллект и кооператив, который проверяет дружбу.",
        [
            ("misha", 10, "Идеальная длина, идеальные шутки, ни одной лишней комнаты."),
            ("nikita", 9, "Кооперативная кампания — отдельное удовольствие."),
        ],
    ),
    (
        "red-dead-redemption-2", "Red Dead Redemption 2", "rust", date(2018, 10, 26), "action adventure",
        "ps4 xone pc",
        "Закат эпохи Дикого Запада глазами банды, которая не успевает за временем.",
        [
            ("gleb", 10, "Артур Морган — один из лучших героев в играх."),
            ("vera", 7, "История сильная, но темп очень медленный."),
            ("roman", 8, "Мир живой до мелочей, но миссии слишком жёстко ведут за руку."),
        ],
    ),
    (
        "inside", "Inside", "ink", date(2016, 6, 29), "adventure puzzle platformer indie",
        "xone pc ps4 switch ios",
        "Мальчик бежит через мрачный индустриальный мир. Без единого слова и с одним из самых странных финалов.",
        [
            ("ilya", 9, "Три часа, которые ощущаются как хороший короткометражный фильм."),
            ("sonya", 8, "Финал до сих пор не могу развидеть."),
        ],
    ),
    (
        "slay-the-spire", "Slay the Spire", "teal", date(2019, 1, 23), "strategy card indie",
        "pc switch ps4 xone ios android",
        "Колодостроительный рогалик: собираете колоду по пути наверх и учитесь не жадничать с картами.",
        [
            ("artem", 10, "Триста часов и всё ещё интересно пробовать новые сборки."),
            ("misha", 9, "Лучший вход в жанр колодостроительных игр."),
            ("maria", 7, "Затягивает, но визуально довольно скромно."),
        ],
    ),
    (
        "cyberpunk-2077", "Cyberpunk 2077", "mustard", date(2020, 12, 10), "rpg shooter",
        "pc ps4 xone ps5 xsx",
        "Найт-Сити, чип в голове и цифровой призрак рок-звезды. После многих обновлений — совсем другая игра, "
        "чем на старте.",
        [
            ("maks", 8, "С дополнением Phantom Liberty игра наконец раскрылась."),
            ("katya", 4, "Играла на старте на PS4 — до сих пор обидно."),
            ("nikita", 7, "Город роскошный, но системы прокачки поверхностные."),
            ("dasha", 9, "Квесты с Джонни вытянули всё."),
        ],
    ),
    (
        "it-takes-two", "It Takes Two", "plum", date(2021, 3, 26), "adventure platformer",
        "pc ps4 ps5 xone xsx switch",
        "Кооператив только на двоих: разводящаяся пара превращается в кукол и чинит отношения через "
        "постоянно меняющиеся механики.",
        [
            ("anya", 9, "Каждый уровень — новая игра, ни разу не заскучали."),
            ("gleb", 8, "Механики великолепны, сюжет местами натянутый."),
        ],
    ),
    (
        "return-of-the-obra-dinn", "Return of the Obra Dinn", "sand", date(2018, 10, 18), "puzzle adventure indie",
        "pc mac switch ps4 xone",
        "Страховой следователь выясняет судьбу шестидесяти членов экипажа корабля-призрака по застывшим "
        "моментам их смерти.",
        [
            ("lera", 10, "Чувствуешь себя настоящим детективом — без единой подсказки."),
            ("ilya", 9, "Однобитная графика выглядит лучше многих современных игр."),
        ],
    ),
    (
        "forza-horizon-5", "Forza Horizon 5", "teal", date(2021, 11, 9), "racing", "pc xone xsx ps5",
        "Аркадные гонки по Мексике: пустыни, джунгли, вулкан и сотни машин.",
        [
            ("roman", 8, "Отличная аркада, чтобы отключить голову на час."),
        ],
    ),
    (
        "balatro", "Balatro", "oxblood", date(2024, 2, 20), "strategy card indie",
        "pc ps5 ps4 xsx xone switch ios android mac",
        "Покерные комбинации, джокеры с безумными эффектами и математика, которая ломает игру в вашу пользу.",
        [
            ("artem", 9, "«Ещё одна раздача» — и уже три часа ночи."),
            ("sonya", 8, "Простая идея, доведённая до совершенства."),
            ("maks", 10, "Самая затягивающая игра последних лет."),
        ],
    ),
    (
        "pathologic-2", "Мор (Pathologic 2)", "bottle", date(2019, 5, 23), "adventure indie", "pc xone ps4",
        "Врач возвращается в степной город, где начинается эпидемия. На всех не хватит ни времени, ни лекарств.",
        [
            ("vera", 9, "Мучительно, неудобно и именно поэтому незабываемо."),
            ("katya", 3, "Голод, усталость и болезнь одновременно — это не для меня."),
            ("lera", 10, "Лучшая игра о выборе, в котором нет правильного ответа."),
        ],
    ),
    (
        "hi-fi-rush", "Hi-Fi Rush", "mustard", date(2023, 1, 25), "action", "pc xsx ps5",
        "Слэшер, в котором всё — от ударов до прыжков врагов — происходит в такт музыке.",
        [
            ("misha", 9, "Невероятно стильно и весело, прямо мультфильм, в который можно играть."),
            ("anya", 8, "Не думала, что ритм-игры могут так хорошо сочетаться с боями."),
        ],
    ),
    (
        "metro-exodus", "Metro Exodus", "slate", date(2019, 2, 15), "shooter action",
        "pc ps4 xone ps5 xsx",
        "Артём и его отряд покидают московское метро и едут на поезде «Аврора» через постапокалиптическую Россию.",
        [
            ("gleb", 8, "Волга и Каспий — лучшие локации в серии."),
            ("nikita", 7, "Атмосфера на месте, но стрельба сыровата."),
        ],
    ),
    (
        "death-stranding", "Death Stranding", "indigo", date(2019, 11, 8), "action adventure", "ps4 pc ps5",
        "Курьер соединяет разрозненную Америку. Главный враг — рельеф и собственный рюкзак.",
        [
            ("ilya", 10, "Самое странное и самое трогательное путешествие в моей жизни."),
            ("artem", 4, "Симулятор доставки на сорок часов — это слишком."),
            ("dasha", 7, "Первые десять часов тяжело, потом не оторваться."),
        ],
    ),
    (
        "pentiment", "Pentiment", "sand", date(2022, 11, 15), "adventure rpg", "pc xone xsx",
        "Детектив в баварском монастыре XVI века, нарисованный как иллюстрированная рукопись.",
        [],
    ),
    (
        "tunic", "Tunic", "teal", date(2022, 3, 16), "action adventure indie", "pc xone xsx switch ps4 ps5",
        "Маленький лис в большом мире, где инструкция к игре написана на выдуманном языке и спрятана по страницам.",
        [],
    ),
]


def _named(model, spec, key):
    slug, name = spec[key] if isinstance(spec[key], tuple) else (key, spec[key])
    return model.objects.update_or_create(slug=slug, defaults={"name": name})[0]


class Command(BaseCommand):
    help = "Создаёт или обновляет демонстрационный каталог и отзывы. Повторный запуск безопасен."

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        critics = {}
        for username, display_name in CRITICS.items():
            user, created = user_model.objects.get_or_create(
                username=f"{username}-demo", defaults={"display_name": display_name}
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=("password",))
            critics[username] = user

        now = timezone.now()
        review_index = 0
        for slug, title, theme, released, genres, platforms, description, reviews in GAMES:
            game, _ = Game.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "description": description,
                    "release_date": released,
                    "poster_theme": theme,
                    "data_source": Game.DataSource.MANUAL,
                },
            )
            game.genres.set([_named(Genre, GENRES, key) for key in genres.split()])
            game.platforms.set([_named(Platform, PLATFORMS, key) for key in platforms.split()])

            for username, score, text in reviews:
                review, _ = Review.objects.update_or_create(
                    author=critics[username], game=game, defaults={"score": score, "text": text}
                )
                # Разносим даты, чтобы лента выглядела накопленной за несколько недель, а не «изменённой».
                review_index += 1
                posted = now - timedelta(hours=7 * review_index)
                Review.objects.filter(pk=review.pk).update(created_at=posted, updated_at=posted)

        self.stdout.write(self.style.SUCCESS(f"Демонстрационный каталог готов. Игр в наборе: {len(GAMES)}."))
