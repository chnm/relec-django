import re

from django.core.management.base import BaseCommand

from pages.models import BlogPost


class Command(BaseCommand):
    help = "Convert Hugo shortcodes to HTML in blog post content"

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

    def convert_figure_shortcodes(self, content, post_slug):
        """Convert {{< figure >}} and {{< fig >}} shortcodes to HTML"""

        # Pattern to match the entire shortcode
        pattern = r"\{\{<\s*(?:figure|fig)\s+(.*?)\s*>\}\}"

        def replace_figure(match):
            attrs_str = match.group(1)

            # Extract individual attributes with regex
            src_match = re.search(r'src="([^"]+)"', attrs_str)
            caption_match = re.search(r'caption="((?:[^"\\]|\\.)*)"', attrs_str)
            alt_match = re.search(r'alt="((?:[^"\\]|\\.)*)"', attrs_str)
            title_match = re.search(r'title="((?:[^"\\]|\\.)*)"', attrs_str)

            src = src_match.group(1) if src_match else ""
            caption = caption_match.group(1) if caption_match else ""
            alt_text = alt_match.group(1) if alt_match else ""
            title = title_match.group(1) if title_match else ""

            # Unescape quotes in caption and alt
            caption = caption.replace('\\"', '"')
            alt_text = alt_text.replace('\\"', '"')

            # Convert markdown links in caption to HTML
            caption = self.convert_markdown_links(caption)

            # Build the HTML
            html = "<figure>\n"

            if src:
                # Handle relative image paths (no leading /)
                if not src.startswith("/"):
                    # Relative path - construct full path using post slug
                    src = f"/static/blog/{post_slug}/{src}"
                # Clean up src path - remove /static/ prefix if present since Django will handle it
                elif src.startswith("/static/"):
                    src = src[8:]  # Remove "/static/" prefix
                    src = f"/static/{src}"
                # Already has absolute path without /static/, add /static/
                else:
                    src = f"/static{src}"

                html += f'  <img src="{src}" alt="{alt_text}"'
                if title:
                    html += f' title="{title}"'
                html += " />\n"

            if caption:
                html += f"  <figcaption>{caption}</figcaption>\n"

            html += "</figure>"
            return html

        content = re.sub(pattern, replace_figure, content)

        # Handle shortcodes with backticks in caption (which breaks the simple pattern)
        # Pattern: {{< figure src="..." caption=`...` >}}
        pattern_backtick = (
            r'\{\{<\s*(?:figure|fig)\s+src="([^"]+)"\s+caption=`([^`]*)`\s*>\}\}'
        )

        def replace_figure_backtick(match):
            src = match.group(1)
            caption = match.group(2)

            # Convert markdown links in caption
            caption = self.convert_markdown_links(caption)

            # Handle relative vs absolute paths
            if not src.startswith("/"):
                src = f"/static/blog/{post_slug}/{src}"
            elif src.startswith("/static/"):
                src = src[8:]
                src = f"/static/{src}"
            else:
                src = f"/static{src}"

            html = f"""<figure>
  <img src="{src}" alt="" />
  <figcaption>{caption}</figcaption>
</figure>"""
            return html

        content = re.sub(pattern_backtick, replace_figure_backtick, content)

        return content

    def convert_fig_interactive(self, content):
        """Convert {{< fig-interactive >}} shortcodes to HTML with D3.js div"""

        # Pattern for {{< fig-interactive id="..." script="..." caption="..." title="..." >}}
        pattern = r'\{\{<\s*fig-interactive\s+id="([^"]+)"\s+script="([^"]+)"\s+caption="([^"]*)"\s+(?:title="([^"]*)")?\s*>\}\}'

        def replace_interactive(match):
            div_id = match.group(1)
            script = match.group(2)
            caption = match.group(3)
            title = match.group(4) or ""

            html = f"""<figure class="viz-interactive">
  {f"<h3>{title}</h3>" if title else ""}
  <div id="{div_id}" class="viz-container"></div>
  <script type="module" src="/static/{script}"></script>
  <figcaption>{caption}</figcaption>
</figure>"""
            return html

        content = re.sub(pattern, replace_interactive, content)
        return content

    def convert_youtube_shortcodes(self, content):
        """Convert {{< youtube VIDEO_ID >}} to HTML iframe embed"""

        pattern = r"\{\{<\s*youtube\s+([A-Za-z0-9_-]+)\s*>\}\}"

        def replace_youtube(match):
            video_id = match.group(1)
            html = f"""<div class="video-container" style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; margin: 2rem 0;">
  <iframe
    src="https://www.youtube.com/embed/{video_id}"
    style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen>
  </iframe>
</div>"""
            return html

        content = re.sub(pattern, replace_youtube, content)
        return content

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No content will be updated")
            )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Converting Hugo Shortcodes to HTML"))
        self.stdout.write("=" * 60)

        updated_count = 0
        skipped_count = 0

        for post in BlogPost.objects.all():
            original_content = post.content

            # Check if post has any shortcodes
            if "{{<" not in original_content and "{{%" not in original_content:
                skipped_count += 1
                continue

            # Apply conversions
            new_content = original_content
            new_content = self.convert_figure_shortcodes(new_content, post.slug)
            new_content = self.convert_fig_interactive(new_content)
            new_content = self.convert_youtube_shortcodes(new_content)

            # Check if anything changed
            if new_content == original_content:
                self.stdout.write(f"  ⊘ {post.slug}: No changes needed")
                skipped_count += 1
                continue

            self.stdout.write(f"\n  → {post.slug}")

            # Show sample of what changed
            if "{{<" in original_content or "{{%" in original_content:
                # Find first shortcode that was changed
                remaining = re.search(r"\{\{[<%].*?[>%]\}\}", new_content)
                if remaining:
                    self.stdout.write(
                        self.style.WARNING(
                            f"    ⚠ Still has shortcodes: {remaining.group(0)}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS("    ✓ All shortcodes converted")
                    )

            if not dry_run:
                post.content = new_content
                post.save()
                updated_count += 1
            else:
                updated_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CONVERSION SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Posts updated: {updated_count}")
        self.stdout.write(f"Posts skipped: {skipped_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a DRY RUN. Run without --dry-run to actually update content."
                )
            )
