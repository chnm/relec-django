import re
from datetime import datetime
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from pages.models import BlogPost, Visualization


class Command(BaseCommand):
    help = "Import blog posts and visualizations from Hugo site"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hugo-path",
            type=str,
            default="relec-website",
            help="Path to Hugo site directory (default: relec-website)",
        )
        parser.add_argument(
            "--content-type",
            type=str,
            choices=["blog", "visualizations", "all"],
            default="all",
            help="Type of content to import (default: all)",
        )

    def handle(self, *args, **options):
        hugo_path = Path(options["hugo_path"])
        content_type = options["content_type"]

        if not hugo_path.exists():
            self.stdout.write(
                self.style.ERROR(f"Hugo path does not exist: {hugo_path}")
            )
            return

        if content_type in ["blog", "all"]:
            self.import_blog_posts(hugo_path)

        if content_type in ["visualizations", "all"]:
            self.import_visualizations(hugo_path)

        self.stdout.write(self.style.SUCCESS("Import completed!"))

    def parse_frontmatter(self, content):
        """Extract YAML frontmatter and content from markdown file."""
        # Match YAML frontmatter between --- markers
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not match:
            return None, content

        frontmatter_text = match.group(1)
        body = match.group(2)

        try:
            frontmatter = yaml.safe_load(frontmatter_text)
            return frontmatter, body
        except yaml.YAMLError as e:
            self.stdout.write(self.style.WARNING(f"Error parsing YAML: {e}"))
            return None, content

    def convert_hugo_shortcodes(self, content):
        """Convert Hugo shortcodes to HTML."""
        # Convert {{< figure >}} shortcode
        figure_pattern = r'{{% figure src="([^"]+)"(?:\s+caption="([^"]*)")?(?:\s+alt="([^"]*)")? %>}'
        content = re.sub(
            figure_pattern,
            lambda m: f'<figure><img src="{m.group(1)}" alt="{m.group(3) or ""}" />'
            + (f"<figcaption>{m.group(2)}</figcaption>" if m.group(2) else "")
            + "</figure>",
            content,
        )

        # Convert {{< fig >}} shortcode (similar to figure)
        fig_pattern = r'{{% fig src="([^"]+)"(?:\s+caption="([^"]*)")? %>}'
        content = re.sub(
            fig_pattern,
            lambda m: f'<figure><img src="{m.group(1)}" alt="" />'
            + (f"<figcaption>{m.group(2)}</figcaption>" if m.group(2) else "")
            + "</figure>",
            content,
        )

        # Convert {{< citation >}} shortcode to a placeholder
        content = re.sub(
            r"{{% citation %}}",
            '<div class="citation">Please cite this work.</div>',
            content,
        )

        return content

    def import_blog_posts(self, hugo_path):
        """Import blog posts from Hugo content/blog directory."""
        blog_dir = hugo_path / "content" / "blog"

        if not blog_dir.exists():
            self.stdout.write(
                self.style.WARNING(f"Blog directory not found: {blog_dir}")
            )
            return

        imported = 0
        skipped = 0

        # Process all markdown files
        for item in blog_dir.iterdir():
            # Handle both individual .md files and directories with index.md
            if item.is_file() and item.suffix == ".md":
                md_file = item
            elif item.is_dir() and (item / "index.md").exists():
                md_file = item / "index.md"
            else:
                continue

            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                frontmatter, body = self.parse_frontmatter(content)
                if not frontmatter:
                    self.stdout.write(
                        self.style.WARNING(f"No frontmatter in {md_file}")
                    )
                    skipped += 1
                    continue

                # Extract slug from filename or generate from title
                if item.is_file():
                    # Extract from filename like "2019-05-20-slug-name.md"
                    filename = item.stem
                    slug_parts = filename.split("-", 3)
                    if len(slug_parts) == 4:
                        slug = slug_parts[3]
                    else:
                        slug = slugify(frontmatter.get("title", filename))
                else:
                    # For directories, use directory name
                    slug = item.name

                # Parse date
                date_str = frontmatter.get("date")
                if isinstance(date_str, str):
                    published_date = datetime.fromisoformat(date_str)
                else:
                    published_date = date_str

                # Convert Hugo shortcodes to HTML
                body = self.convert_hugo_shortcodes(body)

                # Create or update blog post
                post, created = BlogPost.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "title": frontmatter.get("title", ""),
                        "author": frontmatter.get("author", ""),
                        "published_date": published_date,
                        "content": body.strip(),
                        "abstract": frontmatter.get("abstract", ""),
                        "featured_image": frontmatter.get("image", ""),
                        "image_alt_text": frontmatter.get("imagealt", ""),
                        "is_draft": frontmatter.get("draft", False),
                    },
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f"Imported blog post: {post.title}")
                    )
                    imported += 1
                else:
                    self.stdout.write(f"Updated blog post: {post.title}")
                    imported += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error importing {md_file}: {e}"))
                skipped += 1
                continue

        self.stdout.write(
            self.style.SUCCESS(f"Blog posts: {imported} imported, {skipped} skipped")
        )

    def import_visualizations(self, hugo_path):
        """Import visualizations from Hugo content/visualizations directory."""
        viz_dir = hugo_path / "content" / "visualizations"

        if not viz_dir.exists():
            self.stdout.write(
                self.style.WARNING(f"Visualizations directory not found: {viz_dir}")
            )
            return

        imported = 0
        skipped = 0

        # Process all visualization directories
        for item in viz_dir.iterdir():
            if not item.is_dir():
                continue

            md_file = item / "index.md"
            if not md_file.exists():
                continue

            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                frontmatter, body = self.parse_frontmatter(content)
                if not frontmatter:
                    self.stdout.write(
                        self.style.WARNING(f"No frontmatter in {md_file}")
                    )
                    skipped += 1
                    continue

                slug = item.name

                # Parse dates
                date_str = frontmatter.get("date")
                if isinstance(date_str, str):
                    published_date = datetime.fromisoformat(date_str)
                else:
                    published_date = date_str

                updated_str = frontmatter.get("updated")
                if updated_str:
                    if isinstance(updated_str, str):
                        updated_date = datetime.fromisoformat(updated_str)
                    else:
                        updated_date = updated_str
                else:
                    updated_date = None

                # Convert Hugo shortcodes to HTML
                body = self.convert_hugo_shortcodes(body)

                # Create or update visualization
                viz, created = Visualization.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "title": frontmatter.get("title", ""),
                        "published_date": published_date,
                        "updated_date": updated_date,
                        "content": body.strip(),
                        "abstract": frontmatter.get("abstract", ""),
                        "thumbnail": frontmatter.get("thumbnail", ""),
                        "thumbnail_description": frontmatter.get("thumbdesc", ""),
                        "doi": frontmatter.get("doi", ""),
                        "script_file": frontmatter.get("script", ""),
                        "style_file": frontmatter.get("styles", ""),
                    },
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f"Imported visualization: {viz.title}")
                    )
                    imported += 1
                else:
                    self.stdout.write(f"Updated visualization: {viz.title}")
                    imported += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error importing {md_file}: {e}"))
                skipped += 1
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f"Visualizations: {imported} imported, {skipped} skipped"
            )
        )
