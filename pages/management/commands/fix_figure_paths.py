import re

from django.core.management.base import BaseCommand

from pages.models import BlogPost


class Command(BaseCommand):
    help = "Fix image paths in existing HTML figures and convert markdown links in captions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without actually updating",
        )

    def convert_markdown_links(self, text):
        """Convert markdown links [text](url) to HTML <a href="url">text</a>"""
        pattern = r"\[([^\]]+)\]\(([^\)]+)\)"
        return re.sub(pattern, r'<a href="\2">\1</a>', text)

    def fix_image_paths(self, content, post_slug):
        """Fix image paths in existing <figure> tags"""

        # Pattern to match img tags within figures
        pattern = r'(<figure>.*?<img src=")((?:/static/)?/?([^"]+))(".*?</figure>)'

        def replace_img(match):
            prefix = match.group(1)  # "<figure>...<img src="
            current_src = match.group(2)  # Current src value
            suffix = match.group(4)  # " .../> ... </figure>"

            # If it's a relative path (no leading /)
            if not current_src.startswith("/"):
                # Construct full path
                new_src = f"/static/blog/{post_slug}/{current_src}"
            # If it has double slashes (already tried to be fixed)
            elif current_src.startswith("/static//"):
                # Remove the double slash
                new_src = current_src.replace("/static//", "/static/")
            # If it's a simple filename at /static/filename.ext (needs blog slug path)
            elif current_src.startswith("/static/") and "/" not in current_src[8:]:
                # Extract just the filename
                filename_only = current_src.split("/")[-1]
                new_src = f"/static/blog/{post_slug}/{filename_only}"
            # If it's missing /static/ prefix
            elif not current_src.startswith("/static/") and current_src.startswith("/"):
                new_src = f"/static{current_src}"
            else:
                # Already correct
                new_src = current_src

            return f"{prefix}{new_src}{suffix}"

        content = re.sub(pattern, replace_img, content, flags=re.DOTALL)
        return content

    def fix_figcaptions(self, content):
        """Convert markdown links in figcaptions to HTML"""

        # Pattern to match figcaption contents
        pattern = r"(<figcaption>)(.*?)(</figcaption>)"

        def replace_caption(match):
            prefix = match.group(1)
            caption_text = match.group(2)
            suffix = match.group(3)

            # Convert any markdown links to HTML
            new_caption = self.convert_markdown_links(caption_text)

            return f"{prefix}{new_caption}{suffix}"

        content = re.sub(pattern, replace_caption, content, flags=re.DOTALL)
        return content

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No content will be updated")
            )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Fixing Figure Paths and Captions"))
        self.stdout.write("=" * 60)

        updated_count = 0
        skipped_count = 0

        for post in BlogPost.objects.all():
            original_content = post.content

            # Check if post has any figures
            if "<figure>" not in original_content:
                skipped_count += 1
                continue

            # Apply fixes
            new_content = original_content
            new_content = self.fix_image_paths(new_content, post.slug)
            new_content = self.fix_figcaptions(new_content)

            # Check if anything changed
            if new_content == original_content:
                self.stdout.write(f"  ⊘ {post.slug}: No changes needed")
                skipped_count += 1
                continue

            self.stdout.write(f"  → {post.slug}: Fixed")

            if not dry_run:
                post.content = new_content
                post.save()
                updated_count += 1
            else:
                updated_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("FIX SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Posts updated: {updated_count}")
        self.stdout.write(f"Posts skipped: {skipped_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a DRY RUN. Run without --dry-run to actually update content."
                )
            )
