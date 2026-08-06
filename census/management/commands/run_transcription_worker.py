import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from census.transcription.client import ClaudeAPIError
from census.transcription.worker import ClaudeTranscriptionWorker

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Submit and collect restart-safe Claude transcription batches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Perform at most one bounded unit of work, then exit.",
        )
        parser.add_argument(
            "--idle-when-disabled",
            action="store_true",
            help="Remain alive when provider configuration is intentionally absent.",
        )
        parser.add_argument(
            "--poll-seconds",
            type=int,
            default=settings.CLAUDE_TRANSCRIPTION_POLL_SECONDS,
        )

    def handle(self, *args, **options):
        if not settings.CLAUDE_TRANSCRIPTION_ENABLED or not settings.ANTHROPIC_API_KEY:
            if not options["idle_when_disabled"]:
                raise CommandError(
                    "Claude transcription is disabled or ANTHROPIC_API_KEY is absent."
                )
            self.stdout.write(
                "Claude transcription is disabled; worker is idle until restarted "
                "with provider configuration."
            )
            while True:
                time.sleep(min(max(options["poll_seconds"], 1), 60))

        worker = ClaudeTranscriptionWorker()
        if options["once"]:
            worker.run_once()
            return

        while True:
            try:
                changed = worker.run_once()
            except ClaudeAPIError:
                logger.exception(
                    "Claude batch API operation failed; will retry polling"
                )
                changed = False
            if not changed:
                time.sleep(max(options["poll_seconds"], 1))
