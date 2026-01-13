def disable_admin_sidebar(request):
    """Context processor used to keep admin sidebar hidden for our custom admin pages.

    Returns an empty dict so that templates needing this import won't error if it's present in settings.
    """
    return {}
