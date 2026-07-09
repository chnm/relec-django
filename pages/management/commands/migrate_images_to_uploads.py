import shutil
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from pages.models import BlogPost
from visualizations.models import Visualization


class Command(BaseCommand):
    help = "Migrate existing static images to uploaded media files for BlogPost and Visualization models"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without actually copying files",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No files will be copied")
            )

        # Ensure media directories exist
        blog_media_dir = Path(settings.MEDIA_ROOT) / "blog" / "thumbnails"
        viz_media_dir = Path(settings.MEDIA_ROOT) / "visualizations" / "thumbnails"

        if not dry_run:
            blog_media_dir.mkdir(parents=True, exist_ok=True)
            viz_media_dir.mkdir(parents=True, exist_ok=True)
            self.stdout.write("Created media directories")

        # Migrate BlogPost images
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Migrating BlogPost images..."))
        self.stdout.write("=" * 60)

        blog_migrated = 0
        blog_skipped = 0
        blog_errors = 0

        for post in BlogPost.objects.all():
            # Skip if already has uploaded image
            if post.thumbnail_image:
                self.stdout.write(f"  ⊘ {post.slug}: Already has uploaded image")
                blog_skipped += 1
                continue

            # Skip if no featured_image path
            if not post.featured_image:
                self.stdout.write(f"  ⊘ {post.slug}: No featured_image path")
                blog_skipped += 1
                continue

            # Construct source path (remove leading /static/ if present)
            image_path = post.featured_image.lstrip("/")
            if image_path.startswith("static/"):
                image_path = image_path[7:]  # Remove "static/" prefix

            source_path = Path(settings.BASE_DIR) / "static" / image_path

            if not source_path.exists():
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ {post.slug}: Source file not found: {source_path}"
                    )
                )
                blog_errors += 1
                continue

            # Generate destination filename
            file_extension = source_path.suffix
            dest_filename = f"{post.slug}{file_extension}"
            dest_path = blog_media_dir / dest_filename

            self.stdout.write(f"  → {post.slug}")
            self.stdout.write(f"    Source: {source_path}")
            self.stdout.write(f"    Dest:   {dest_path}")

            if not dry_run:
                try:
                    # Copy file to media directory
                    shutil.copy2(source_path, dest_path)

                    # Update model with Django File
                    with open(dest_path, "rb") as f:
                        post.thumbnail_image.save(dest_filename, File(f), save=False)

                    post.save()
                    self.stdout.write(self.style.SUCCESS("    ✓ Migrated successfully"))
                    blog_migrated += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    ✗ Error: {e}"))
                    blog_errors += 1
            else:
                blog_migrated += 1

        # Migrate Visualization images
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Migrating Visualization images..."))
        self.stdout.write("=" * 60)

        viz_migrated = 0
        viz_skipped = 0
        viz_errors = 0

        for viz in Visualization.objects.all():
            # Skip if already has uploaded image
            if viz.thumbnail_image:
                self.stdout.write(f"  ⊘ {viz.slug}: Already has uploaded image")
                viz_skipped += 1
                continue

            # Skip if no thumbnail path
            if not viz.thumbnail:
                self.stdout.write(f"  ⊘ {viz.slug}: No thumbnail path")
                viz_skipped += 1
                continue

            # Construct source path (remove leading /static/ if present)
            image_path = viz.thumbnail.lstrip("/")
            if image_path.startswith("static/"):
                image_path = image_path[7:]  # Remove "static/" prefix

            source_path = Path(settings.BASE_DIR) / "static" / image_path

            if not source_path.exists():
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ {viz.slug}: Source file not found: {source_path}"
                    )
                )
                viz_errors += 1
                continue

            # Generate destination filename
            file_extension = source_path.suffix
            dest_filename = f"{viz.slug}{file_extension}"
            dest_path = viz_media_dir / dest_filename

            self.stdout.write(f"  → {viz.slug}")
            self.stdout.write(f"    Source: {source_path}")
            self.stdout.write(f"    Dest:   {dest_path}")

            if not dry_run:
                try:
                    # Copy file to media directory
                    shutil.copy2(source_path, dest_path)

                    # Update model with Django File
                    with open(dest_path, "rb") as f:
                        viz.thumbnail_image.save(dest_filename, File(f), save=False)

                    viz.save()
                    self.stdout.write(self.style.SUCCESS("    ✓ Migrated successfully"))
                    viz_migrated += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    ✗ Error: {e}"))
                    viz_errors += 1
            else:
                viz_migrated += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("MIGRATION SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write("BlogPost images:")
        self.stdout.write(f"  Migrated: {blog_migrated}")
        self.stdout.write(f"  Skipped:  {blog_skipped}")
        self.stdout.write(f"  Errors:   {blog_errors}")
        self.stdout.write("\nVisualization images:")
        self.stdout.write(f"  Migrated: {viz_migrated}")
        self.stdout.write(f"  Skipped:  {viz_skipped}")
        self.stdout.write(f"  Errors:   {viz_errors}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a DRY RUN. Run without --dry-run to actually migrate files."
                )
            )
