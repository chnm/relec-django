import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Update JSON imports in JS files to use .json.js extension"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without updating files",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No files will be updated")
            )

        viz_dir = Path(settings.BASE_DIR) / "static" / "viz"

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Updating JSON imports in JS files"))
        self.stdout.write("=" * 60)

        updated_count = 0
        skipped_count = 0

        # Find all JS files in viz directory (excluding .json.js files)
        for js_file in viz_dir.rglob("*.js"):
            if js_file.name.endswith(".json.js"):
                continue

            # Read file content
            with open(js_file, "r", encoding="utf-8") as f:
                original_content = f.read()

            # Pattern to match: import ... from "./something.json"
            # Replace with: import ... from "./something.json.js"
            pattern = r'(import\s+.*?\s+from\s+["\'])([^"\']+\.json)(["\'])'
            new_content = re.sub(pattern, r"\1\2.js\3", original_content)

            # Check if anything changed
            if new_content == original_content:
                skipped_count += 1
                continue

            self.stdout.write(f"\n  → {js_file.relative_to(settings.BASE_DIR)}")

            # Show what changed
            old_imports = re.findall(r'import.*?\.json["\']', original_content)
            new_imports = re.findall(r'import.*?\.json\.js["\']', new_content)

            for old, new in zip(old_imports, new_imports):
                self.stdout.write(f"    - {old}")
                self.stdout.write(f"    + {new}")

            if not dry_run:
                # Write updated content
                with open(js_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
                self.stdout.write(self.style.SUCCESS("    ✓ Updated"))

            updated_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("UPDATE SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"JS files updated: {updated_count}")
        self.stdout.write(f"JS files skipped: {skipped_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a DRY RUN. Run without --dry-run to update files."
                )
            )
