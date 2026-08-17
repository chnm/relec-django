import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from census.transcription.client import ClaudeAPIError
from census.transcription.worker import ClaudeTranscriptionWorker

logger = logging.getLogger(__name__)

#: Touched on every loop iteration so the container healthcheck can tell a
#: working worker from a wedged one. The compose healthcheck must test this
#: same path.
DEFAULT_LIVENESS_FILE = "/tmp/transcription-worker-alive"


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
        parser.add_argument(
            "--liveness-file",
            default=DEFAULT_LIVENESS_FILE,
            help=(
                "Path whose mtime is refreshed on every loop iteration. Pass an "
                "empty value to disable. Must match the compose healthcheck."
            ),
        )

    def handle(self, *args, **options):
        liveness = Path(options["liveness_file"]) if options["liveness_file"] else None
        self.mark_alive(liveness)

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
                # A deliberately disabled worker is still a healthy worker. Keep
                # the file fresh or the healthcheck will have it restarted in a
                # loop for doing exactly what it was configured to do.
                self.mark_alive(liveness)
                time.sleep(min(max(options["poll_seconds"], 1), 60))

        worker = ClaudeTranscriptionWorker()
        logger.info(
            "Claude transcription worker started poll_seconds=%s "
            "batch_size=%s max_active_batches=%s",
            options["poll_seconds"],
            settings.CLAUDE_TRANSCRIPTION_BATCH_SIZE,
            settings.CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES,
        )
        if options["once"]:
            worker.run_once()
            self.mark_alive(liveness)
            return

        while True:
            self.mark_alive(liveness)
            try:
                changed = worker.run_once()
            except ClaudeAPIError:
                logger.exception(
                    "Claude batch API operation failed; will retry polling"
                )
                changed = False
            # Refreshed on both sides of the unit of work, so the file only goes
            # stale while run_once() is genuinely stuck rather than merely slow.
            self.mark_alive(liveness)
            if not changed:
                time.sleep(max(options["poll_seconds"], 1))

    @staticmethod
    def mark_alive(path):
        """Refresh the liveness file, never failing the worker over it."""
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        except OSError:
            # Losing the file is itself a reason for the healthcheck to fail,
            # so log and carry on rather than killing an otherwise-fine worker.
            logger.warning("Could not refresh liveness file %s", path, exc_info=True)
