from django.core.management.base import BaseCommand

from pages.models import BlogPost
from visualizations.models import Visualization


class Command(BaseCommand):
    help = "Fix image paths to include /static/ prefix and correct slugs"

    def handle(self, *args, **options):
        # Fix blog post images
        blog_count = 0
        for post in BlogPost.objects.all():
            updated = False

            # Fix featured_image
            if post.featured_image:
                old_path = post.featured_image

                # Add /static/ prefix if not present
                if old_path.startswith("/blog-img/"):
                    post.featured_image = "/static" + old_path
                    updated = True
                elif old_path.startswith("/blog/"):
                    # For bundle posts, replace Hugo slug with actual post slug
                    # /blog/old-slug/image.png -> /static/blog/actual-slug/image.png
                    filename = old_path.split("/")[-1]
                    post.featured_image = f"/static/blog/{post.slug}/{filename}"
                    updated = True
                elif not old_path.startswith("/static/"):
                    # Add /static/ to any other path
                    post.featured_image = "/static" + old_path
                    updated = True

            if updated:
                post.save()
                blog_count += 1
                self.stdout.write(f"Updated blog post: {post.title}")

        # Fix visualization thumbnails
        viz_count = 0
        for viz in Visualization.objects.all():
            if viz.thumbnail and not viz.thumbnail.startswith("/static/"):
                viz.thumbnail = "/static/" + viz.thumbnail.lstrip("/")
                viz.save()
                viz_count += 1
                self.stdout.write(f"Updated visualization: {viz.title}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Fixed {blog_count} blog posts and {viz_count} visualizations"
            )
        )
