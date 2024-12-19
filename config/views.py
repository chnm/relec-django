def dashboard_callback(request, context):
    context.update(
        {
            "total_churches": "value",
        }
    )

    return context
