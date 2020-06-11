"""Make the functionalities of this package auto-discoverable by mara-app"""


def MARA_CONFIG_MODULES():
    from . import config
    return [config]


def MARA_FLASK_BLUEPRINTS():
    from . import views
    return [views.blueprint]


def MARA_AUTOMIGRATE_SQLALCHEMY_MODELS():
    from . import query
    return [query.Query]


def MARA_ACL_RESOURCES():
    from . import views
    return {'Explore': views.acl_resource,
            'Personal Data': views.personal_data_acl_resource}


def MARA_CLICK_COMMANDS():
    return []


def MARA_NAVIGATION_ENTRIES():
    from . import views
    return {'Explore': views.navigation_entry()}
