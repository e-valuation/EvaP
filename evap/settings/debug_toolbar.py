from evap.settings_resolver import derived

# Very helpful but eats a lot of performance on sql-heavy pages.
# Works only with DEBUG = True and Django's development server (so no apache).
ENABLE_DEBUG_TOOLBAR = False


@derived(final={"DEBUG", "ENABLE_DEBUG_TOOLBAR", "TESTING"})
def REALLY_ENABLE_DEBUG_TOOLBAR(prev, final):
    return final.ENABLE_DEBUG_TOOLBAR and final.DEBUG and not final.TESTING


@derived(prev={"INSTALLED_APPS"}, final={"REALLY_ENABLE_DEBUG_TOOLBAR"})
def INSTALLED_APPS(prev, final):
    if final.REALLY_ENABLE_DEBUG_TOOLBAR:
        return prev.INSTALLED_APPS + ["debug_toolbar"]
    return prev.INSTALLED_APPS


@derived(prev={"MIDDLEWARE"}, final={"REALLY_ENABLE_DEBUG_TOOLBAR"})
def MIDDLEWARE(prev, final):
    if final.REALLY_ENABLE_DEBUG_TOOLBAR:
        return ["debug_toolbar.middleware.DebugToolbarMiddleware"] + prev.MIDDLEWARE
    return prev.MIDDLEWARE


def show_toolbar(request):
    return True


@derived(prev={"DEBUG_TOOLBAR_CONFIG"}, final={"REALLY_ENABLE_DEBUG_TOOLBAR"})
def DEBUG_TOOLBAR_CONFIG(prev, final):
    if final.REALLY_ENABLE_DEBUG_TOOLBAR:
        return {
            "SHOW_TOOLBAR_CALLBACK": "evap.settings.debug_toolbar.show_toolbar",
            "JQUERY_URL": "",
        }
    return prev.DEBUG_TOOLBAR_CONFIG
