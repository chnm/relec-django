import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Convert JSON data files to JavaScript modules for ES6 imports"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without creating files",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No files will be created")
            )

        viz_dir = Path(settings.BASE_DIR) / "static" / "viz"

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Converting JSON files to JS modules"))
        self.stdout.write("=" * 60)

        converted_count = 0
        error_count = 0

        # Find all JSON files in viz directory
        for json_file in viz_dir.rglob("*.json"):
            # Check if corresponding .js file already exists
            js_file = json_file.with_suffix(".json.js")

            self.stdout.write(f"\n  → {json_file.relative_to(settings.BASE_DIR)}")

            try:
                # Read JSON data
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Create JS module content
                js_content = f"// Auto-generated from {json_file.name}\n"
                js_content += "// Original JSON data exported as ES6 module\n\n"
                js_content += f"export default {json.dumps(data, indent=2)};\n"

                if not dry_run:
                    # Write JS module
                    with open(js_file, "w", encoding="utf-8") as f:
                        f.write(js_content)

                self.stdout.write(self.style.SUCCESS(f"    ✓ Created {js_file.name}"))
                converted_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ✗ Error: {e}"))
                error_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CONVERSION SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"JSON files converted: {converted_count}")
        self.stdout.write(f"Errors: {error_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a DRY RUN. Run without --dry-run to create files."
                )
            )
        else:
            self.stdout.write(
                "\nNote: Update import statements to use .json.js extension instead of .json"
            )
