from django.shortcuts import render

from .models import Denomination


def map_view(request):
    """Render the map view with denomination filters"""
    # Get all denominations for the filter dropdown
    denominations = Denomination.objects.all().order_by("name")

    # Get unique denomination families for the family filter dropdown
    census_families = (
        Denomination.objects.values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )
    arda_families = (
        Denomination.objects.values_list("family_arda", flat=True)
        .distinct()
        .order_by("family_arda")
    )

    context = {
        "denominations": denominations,
        "census_families": census_families,
        "arda_families": arda_families,
    }

    return render(request, "census/map.html", context)
