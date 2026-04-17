import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rename .json.js files to .data.js and update imports"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        viz_dir = Path(settings.BASE_DIR) / "static" / "viz"

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Renaming JSON modules"))
        self.stdout.write("=" * 60)

        # Step 1: Rename .json.js files to .data.js
        renamed_files = {}
        for json_js_file in viz_dir.rglob("*.json.js"):
            # New name: change .json.js to .data.js
            new_name = json_js_file.name.replace(".json.js", ".data.js")
            new_path = json_js_file.parent / new_name

            self.stdout.write(f"\n  Renaming: {json_js_file.name} → {new_name}")

            if not dry_run:
                json_js_file.rename(new_path)

            # Track the rename for updating imports
            renamed_files[json_js_file.name] = new_name

        # Step 2: Update imports in JS files
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Updating imports"))
        self.stdout.write("=" * 60)

        updated_count = 0
        for js_file in viz_dir.rglob("*.js"):
            if js_file.name.endswith(".data.js"):
                continue

            with open(js_file, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content

            # Update imports from .json.js to .data.js
            content = re.sub(r'\.json\.js(["\'])', r".data.js\1", content)

            if content != original_content:
                self.stdout.write(f"\n  → {js_file.relative_to(settings.BASE_DIR)}")
                self.stdout.write("    ✓ Updated imports")

                if not dry_run:
                    with open(js_file, "w", encoding="utf-8") as f:
                        f.write(content)

                updated_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Files renamed: {len(renamed_files)}")
        self.stdout.write(f"Imports updated: {updated_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a DRY RUN. Run without --dry-run to make changes."
                )
            )
