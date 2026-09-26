from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from games.models import ImportRun
from games.rawg import RawgClient, RawgError, save_rawg_game


class Command(BaseCommand):
    help = "Загружает или обновляет игры из RAWG API. Повторный запуск не создаёт дубликатов."

    def add_arguments(self, parser):
        parser.add_argument("--pages", type=int, default=1, help="Сколько страниц загрузить (по умолчанию 1).")
        parser.add_argument("--page-size", type=int, default=40, help="Игр на странице, максимум 40.")
        parser.add_argument("--search", default="", help="Загрузить только игры, найденные по этому запросу.")
        parser.add_argument("--ordering", default="-added", help="Порядок RAWG, например -rating или -released.")
        parser.add_argument(
            "--details",
            action="store_true",
            help="Дополнительно запросить описание каждой игры (один запрос на игру).",
        )

    def handle(self, *args, **options):
        pages, page_size = options["pages"], options["page_size"]
        if pages < 1 or not 1 <= page_size <= 40:
            raise CommandError("--pages должен быть не меньше 1, а --page-size — от 1 до 40.")

        run = ImportRun.objects.create(
            parameters={key: options[key] for key in ("pages", "page_size", "search", "ordering", "details")},
        )
        try:
            client = RawgClient()
            for page in range(1, pages + 1):
                results = client.list_games(
                    page=page, page_size=page_size, search=options["search"], ordering=options["ordering"]
                )
                for item in results:
                    details = client.game_details(item["id"]) if options["details"] and item.get("id") else None
                    game, created = save_rawg_game(item, details)
                    if created:
                        run.created_count += 1
                    else:
                        run.updated_count += 1
                    self.stdout.write(f"{'+' if created else '~'} {game.title}")
                if len(results) < page_size:
                    break
        except RawgError as exc:
            self._finish(run, ImportRun.Status.FAILED, str(exc))
            raise CommandError(
                f"Импорт прерван: {exc} Уже сохранено: новых {run.created_count}, обновлено {run.updated_count}."
            ) from exc
        except Exception as exc:
            self._finish(run, ImportRun.Status.FAILED, f"Непредвиденная ошибка: {exc!r}")
            raise

        self._finish(run, ImportRun.Status.SUCCESS)
        self.stdout.write(
            self.style.SUCCESS(f"Импорт завершён: новых игр {run.created_count}, обновлено {run.updated_count}.")
        )

    @staticmethod
    def _finish(run, status, error=""):
        run.status = status
        run.error = error
        run.finished_at = timezone.now()
        run.save()
