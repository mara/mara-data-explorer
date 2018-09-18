from data_sets import views, config, query

MARA_CONFIG_MODULES = [config]

MARA_FLASK_BLUEPRINTS = [views.blueprint]

MARA_AUTOMIGRATE_SQLALCHEMY_MODELS = [query.Query]

MARA_ACL_RESOURCES = [views.acl_resource, views.personal_data_acl_resource]

MARA_CLICK_COMMANDS = []

MARA_NAVIGATION_ENTRY_FNS = [views.navigation_entry]


