import re

from django.core.management.base import BaseCommand

from pages.models import BlogPost


class Command(BaseCommand):
    help = "Fix interactive visualizations to use params injection"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without actually updating",
        )

    def fix_viz_interactive(self, content):
        """Update viz-interactive figures to use data URL approach"""

        # Pattern to match existing viz-interactive figures (all formats)
        # Format 1: Without any wrapper
        pattern1 = r'<figure class="viz-interactive">\s*(?:<h3>(.*?)</h3>\s*)?<div id="([^"]+)" class="viz-container"></div>\s*<script type="module" src="([^"]+)"(?:\s+data-viz-id="[^"]*")?></script>\s*<figcaption>(.*?)</figcaption>\s*</figure>'

        # Format 2: With old __vizParams wrapper
        pattern2 = r'<figure class="viz-interactive">\s*(?:<h3>(.*?)</h3>\s*)?<div id="([^"]+)" class="viz-container"></div>\s*<script type="module">\s*//.*?window\.__vizParams.*?</script>\s*<script type="module" src="([^"]+)"(?:\s+data-viz-id="[^"]*")?></script>\s*<figcaption>(.*?)</figcaption>\s*</figure>'

        # Format 3: With __currentVizParams wrapper
        pattern3 = r'<figure class="viz-interactive">\s*(?:<h3>(.*?)</h3>\s*)?<div id="([^"]+)" class="viz-container"></div>\s*<script type="module">\s*//.*?window\.__currentVizParams.*?import\([^)]+\);?\s*</script>\s*<figcaption>(.*?)</figcaption>\s*</figure>'

        def replace_viz(match):
            title = match.group(1) or ""
            div_id = match.group(2)
            # For pattern3, script_src is in the import() call, need to extract differently
            if len(match.groups()) >= 4:
                caption = match.group(4)
                script_src = match.group(3) if len(match.groups()) == 4 else None
            else:
                caption = match.group(3)
                script_src = None

            # Extract script path from the full figure if not captured
            if not script_src:
                import re

                src_match = re.search(r"import\('([^']+)'\)", match.group(0))
                if src_match:
                    script_src = src_match.group(1)

            # Create the updated HTML with data URL approach
            html = f"""<figure class="viz-interactive">
  {f"<h3>{title}</h3>" if title else ""}
  <div id="{div_id}" class="viz-container"></div>
  <script type="module">
    // Create a data URL that exports the params for this specific viz
    const paramsModule = `export default {{ id: '{div_id}' }}; export const id = '{div_id}';`;
    const paramsUrl = URL.createObjectURL(new Blob([paramsModule], {{ type: 'text/javascript' }}));

    // Fetch the viz script, replace @params import, and execute it
    fetch('{script_src}')
      .then(r => r.text())
      .then(code => {{
        // Replace the @params import with our data URL
        const modifiedCode = code.replace(/from ['"]@params['"]/g, `from '${{paramsUrl}}'`);
        const codeUrl = URL.createObjectURL(new Blob([modifiedCode], {{ type: 'text/javascript' }}));
        return import(codeUrl);
      }})
      .catch(err => console.error('Error loading visualization:', err));
  </script>
  <figcaption>{caption}</figcaption>
</figure>"""
            return html

        # Try all patterns
        content = re.sub(pattern3, replace_viz, content, flags=re.DOTALL)
        content = re.sub(pattern2, replace_viz, content, flags=re.DOTALL)
        content = re.sub(pattern1, replace_viz, content, flags=re.DOTALL)
        return content

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No content will be updated")
            )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Fixing Interactive Visualizations"))
        self.stdout.write("=" * 60)

        updated_count = 0
        skipped_count = 0

        # Only process posts with viz-interactive class
        for post in BlogPost.objects.filter(content__icontains="viz-interactive"):
            original_content = post.content

            # Check if already has the new data URL wrapper format
            if (
                "URL.createObjectURL" in original_content
                and "paramsModule" in original_content
            ):
                self.stdout.write(f"  ⊘ {post.slug}: Already updated")
                skipped_count += 1
                continue

            # Apply fix
            new_content = self.fix_viz_interactive(original_content)

            # Check if anything changed
            if new_content == original_content:
                self.stdout.write(f"  ⊘ {post.slug}: No changes needed")
                skipped_count += 1
                continue

            self.stdout.write(f"\n  → {post.slug}")
            self.stdout.write(
                self.style.SUCCESS("    ✓ Updated interactive visualizations")
            )

            if not dry_run:
                post.content = new_content
                post.save()
                updated_count += 1
            else:
                updated_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("UPDATE SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Posts updated: {updated_count}")
        self.stdout.write(f"Posts skipped: {skipped_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a DRY RUN. Run without --dry-run to actually update content."
                )
            )
