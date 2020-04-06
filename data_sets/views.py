"""Data sets UI"""
import datetime
import json

import flask
from mara_page import acl, navigation, response, bootstrap, _, html

from . import config

import google_auth_oauthlib.flow
from googleapiclient.discovery import build

# import google.oauth2.credentials

blueprint = flask.Blueprint('data_sets', __name__, static_folder='static',
                            url_prefix='/data-sets', template_folder='templates')

acl_resource = acl.AclResource(name='Data sets')
personal_data_acl_resource = acl.AclResource(name='Personal Data')
data_set_acl_resources = {}


@blueprint.before_app_first_request  # configuration needs to be loaded before we can access it
def _create_acl_resource_for_each_data_set():
    for ds in config.data_sets():
        resource = acl.AclResource(name=ds.name)
        data_set_acl_resources[ds.id] = resource
        acl_resource.add_child(resource)


def navigation_entry():
    return navigation.NavigationEntry(
        label='Data Sets', uri_fn=lambda: flask.url_for('data_sets.index_page'), icon='table',
        description='Raw data access & segmentation',
        children=[navigation.NavigationEntry(label='Overview', icon='list',
                                             uri_fn=lambda: flask.url_for('data_sets.index_page'))]
                 + [navigation.NavigationEntry(label=ds.name, icon='table',
                                               uri_fn=lambda id=ds.id: flask.url_for('data_sets.data_set_page',
                                                                                     data_set_id=id))
                    for ds in config.data_sets()])


@blueprint.route('')
def index_page():
    return response.Response(
        html=[bootstrap.card(
            header_left=_.a(href=flask.url_for('data_sets.data_set_page', data_set_id=ds.id))[ds.name],
            body=[html.asynchronous_content(flask.url_for('data_sets.data_set_preview', data_set_id=ds.id))])
            for i, ds in enumerate(config.data_sets())],
        title='Data sets',
        js_files=[flask.url_for('data_sets.static', filename='data-sets.js')],
        css_files=[flask.url_for('data_sets.static', filename='data-sets.css')])


@blueprint.route('/<data_set_id>', defaults={'query_id': None})
@blueprint.route('/<data_set_id>/<query_id>')
def data_set_page(data_set_id, query_id):
    from .data_set import find_data_set
    ds = find_data_set(data_set_id)
    if not ds:
        flask.flash(f'Data set "{data_set_id}" does not exist anymore', category='danger')
        return flask.redirect(flask.url_for('data_sets.index_page'))

    action_buttons = []
    if config.google_oauth2_client_secrets_file():
        action_buttons.append(response.ActionButton(action='javascript:dataSetPage.exportToSpreadsheet()',
                                                    icon='cloud-upload',
                                                    label='Spreadsheet', title='Export to a Google Spreadsheet'))
    action_buttons.append(response.ActionButton(action='javascript:dataSetPage.downloadCSV()',
                                                icon='download',
                                                label='CSV', title='Download as CSV'))
    action_buttons.append(response.ActionButton(action='javascript:dataSetPage.load()',
                                                icon='folder-open',
                                                label='Load', title='Load previously saved query'))
    action_buttons.append(response.ActionButton(action='javascript:dataSetPage.save()',
                                                icon='save',
                                                label='Save', title='Save query'))
    action_buttons.append(response.ActionButton(action='javascript:dataSetPage.displayQuery()',
                                                icon='eye',
                                                label='SQL', title='Display query'))

    if query_id:
        action_buttons.insert(1, response.ActionButton(
            action=flask.url_for('data_sets._delete_query', data_set_id=data_set_id, query_id=query_id),
            icon='trash', label='Delete', title='Delete query'))

    return response.Response(
        title=f'Query "{query_id}" on "{ds.name}"' if query_id else f'New query on "{ds.name}"',
        html=[_.div(class_='row')[
                  _.div(class_='col-md-3')[
                      bootstrap.card(header_left='Query', body=_.div(id='query-details')[html.spinner()]),
                      bootstrap.card(header_left='Columns',
                                     body=[_.div(class_="form-group")[
                                               _.input(type="search", class_="columns-search form-control",
                                                       value="", placeholder="Filter")],
                                           _.div(id='columns-list')[html.spinner()]])],
                  _.div(class_='col-md-9')[
                      bootstrap.card(
                          id='filter-card',
                          header_left=[_.div(class_="dropdown")[
                                           _.a(**{'class': 'dropdown-toggle', 'data-toggle': 'dropdown', 'href': '#'})[
                                               _.span(class_='fa fa-plus')[' '], ' Add filter'],
                                           _.div(class_="dropdown-menu", id='filter-menu')[
                                               _.div(class_="dropdown-item")[
                                                   _.input(type="text", class_="columns-search form-control", value="",
                                                           placeholder="Filter")]]]],
                          fixed_header_height=False,
                          body=_.div(id='filters')[html.spinner()]),
                      bootstrap.card(header_left=_.div(id='row-counts')[html.spinner()],
                                     header_right=_.div(id='pagination')[html.spinner()],
                                     body=_.div(id='preview')[html.spinner()]),
                      _.div(class_='row', id='distribution-charts')['']
                  ]], _.script[f"""
var dataSetPage = null;                  
document.addEventListener('DOMContentLoaded', function() {{
    dataSetPage = DataSetPage('{flask.url_for('data_sets.index_page')}', 
                              {json.dumps(
            {'data_set_id': data_set_id, 'query_id': query_id, 'query': flask.request.get_json()})},
                              15, '{config.charts_color()}');
}});
            """],
              html.spinner_js_function(),
              _.div(class_='col-xl-4 col-lg-6', id='distribution-chart-template', style='display: none')[
                  bootstrap.card(header_left=html.spinner(), body=_.div(class_='chart-container google-chart')[
                      html.spinner()])],
              _.div(class_='modal fade', id='load-query-dialog', tabindex="-1")[
                  _.div(class_='modal-dialog', role='document')[
                      _.div(class_='modal-content')[
                          _.div(class_='modal-header')[
                              _.h5(class_='modal-title')['Load query'],
                              _.button(**{'type': "button", 'class': "close", 'data-dismiss': "modal",
                                          'aria-label': "Close"})[
                                  _.span(**{'aria-hidden': 'true'})['&times']]],
                          _.div(class_='modal-body', id='query-list')['']
                      ]
                  ]
              ],
              _.div(class_='modal fade', id='display-query-dialog', tabindex="-1")[
                  _.div(class_='modal-dialog', role='document')[
                      _.div(class_='modal-content')[
                          _.div(class_='modal-header')[
                              _.h5(class_='modal-title')['Query statement'],
                              _.button(**{'type': "button", 'class': "close", 'data-dismiss': "modal",
                                          'aria-label': "Close"})[
                                  _.span(**{'aria-hidden': 'true'})['&times']]],
                          _.div(class_='modal-body', id='query-display')['']
                      ]
                  ]
              ],
              _.form(action=flask.url_for('data_sets.download_csv', data_set_id=data_set_id), method='post')[
                  _.div(class_="modal fade", id="download-csv-dialog", tabindex="-1")[
                      _.div(class_="modal-dialog", role='document')[
                          _.div(class_="modal-content")[
                              _.div(class_="modal-header")[
                                  _.h5(class_='modal-title')['Download as CSV'],
                                  _.button(**{'type': "button", 'class': "close", 'data-dismiss': "modal",
                                              'aria-label': "Close"})[
                                      _.span(**{'aria-hidden': 'true'})['&times']]],
                              _.div(class_="modal-body")[
                                  'Delimiter: &nbsp',
                                  _.input(type="radio", value="\t", name="delimiter",
                                          checked="checked"), ' tab &nbsp&nbsp',

                                  _.input(type="radio", value=";", name="delimiter"), ' semicolon &nbsp&nbsp',
                                  _.input(type="radio", value=",", name="delimiter"), ' comma &nbsp&nbsp',
                                  _.hr,
                                  'Number format: &nbsp',
                                  _.input(type="radio", value=".", name="decimal-mark",
                                          checked="checked"), ' 42.7 &nbsp&nbsp',
                                  _.input(type="radio", value=",", name="decimal-mark"), ' 42,7 &nbsp&nbsp',
                                  _.input(type="hidden", name="query")],
                              _.div(class_="modal-footer")[
                                  _.button(id="csv-download-button", type="submit", class_="btn btn-primary")[
                                      'Download']]]]]],

              _.form(action=flask.url_for('data_sets.oauth2_export_to_spreadsheet', data_set_id=data_set_id),
                     method='post',
                     target="_blank")[
                  _.div(class_="modal fade", id="spreadsheet-export-dialog", tabindex="-1")[
                      _.div(class_="modal-dialog", role='document')[
                          _.div(class_="modal-content")[
                              _.div(class_="modal-header")[
                                  _.h5(class_='modal-title')['Google Spreadsheet export'],
                                  _.button(**{'type': "button", 'class': "close", 'data-dismiss': "modal",
                                              'aria-label': "Close"})[
                                      _.span(**{'aria-hidden': 'true'})['&times']]],
                              _.div(class_="modal-body")[
                                  'By clicking Export below:',
                                  _.br,
                                  _.ul[
                                      _.li['Google authentication will be required.'],
                                      _.li['A maximum limit of 100.000 rows will be applied.'],
                                      _.li['A maximum limit of 50.000 characters per cell will be applied.'],
                                      _.li['A Spreadsheet with the selected data will be available in a new tab.']
                                  ],
                                  _.input(type="hidden", name="query")
                              ],
                              _.div(class_="modal-footer")[
                                  _.button(id="export-to-spreadsheet", type="submit", class_="btn btn-primary")[
                                      'Export']]]]]]

              ],
        action_buttons=action_buttons,
        js_files=['https://www.gstatic.com/charts/loader.js',
                  flask.url_for('data_sets.static', filename='tagsinput.js'),
                  flask.url_for('data_sets.static', filename='typeahead.js'),
                  flask.url_for('data_sets.static', filename='data-sets.js')],
        css_files=[flask.url_for('data_sets.static', filename='tagsinput.css'),
                   flask.url_for('data_sets.static', filename='data-sets.css')])


@blueprint.route('/.initialize', methods=['POST'])
def initialize_query():
    from .query import Query

    data_set_id = flask.request.json['data_set_id']
    query_id = flask.request.json['query_id']
    query_dict = flask.request.json['query']

    if query_dict:
        query = Query.from_dict(query_dict)
    elif query_id:
        query = Query.load(query_id, data_set_id)
    else:
        query = Query(data_set_id=data_set_id)

    return flask.jsonify({'query': query.to_dict(),
                          'all_columns': [column.to_dict() for column in query.data_set.columns.values()],
                          'row_count': query.data_set.row_count(),
                          'data_set_name': query.data_set.name})


def _render_preview_row(query, row):
    values = []
    for pos, value in enumerate(row):
        if value == '🔒':
            values.append(acl.inline_permission_denied_message('Restricted personal data'))
        elif query.column_names[pos] in query.data_set.custom_column_renderers:
            values.append(query.data_set.custom_column_renderers[query.column_names[pos]](value))
        elif not value:
            values.append('')
        elif query.data_set.columns[query.column_names[pos]].type == 'text[]':
            values.append(_.ul[[_.li[_.span(class_='preview-value')[str(array_element)]] for array_element in value]])
        elif query.data_set.columns[query.column_names[pos]].type == 'json':
            values.append(_.pre(class_='preview-value')[flask.escape(json.dumps(value, indent=2))])
        else:
            values.append(_.span(class_='preview-value')[str(value)])
    return _.tr[[_.td[value] for value in values]]


@blueprint.route('/<data_set_id>/.preview')
def data_set_preview(data_set_id):
    from .query import Query

    query = Query(data_set_id=data_set_id)
    if query.column_names:
        if current_user_has_permission(query):
            rows = [_render_preview_row(query, row) for row
                    in query.run(limit=7, offset=0,
                                 include_personal_data=acl.current_user_has_permission(personal_data_acl_resource))]
        else:
            rows = _.tr[_.td(colspan=len(query.column_names))[acl.inline_permission_denied_message()]]

        return str(
            bootstrap.table(headers=[flask.escape(column_name) for column_name in query.column_names], rows=rows))

    else:
        return '∅'


@blueprint.route('/.preview', methods=['POST'])
def preview():
    from .query import Query
    from .data_set import Column

    query = Query.from_dict(flask.request.json['query'])

    def header(column: Column):
        if column.sortable():
            if query.sort_column_name == column.column_name and query.sort_order == 'ASC':
                icon = _.span(class_=('fa fa-sort-amount-asc'))['']
            elif query.sort_column_name == column.column_name and query.sort_order == 'DESC':
                icon = _.span(class_=('fa fa-sort-amount-desc'))['']
            else:
                icon = ''

            return _.a(href="#", name=flask.escape(column.column_name))[
                icon, ' ',
                flask.escape(column.column_name)]
        else:
            return flask.escape(column.column_name)

    if current_user_has_permission(query):
        rows = [_render_preview_row(query, row)
                for row in query.run(limit=flask.request.json['limit'], offset=flask.request.json['offset'],
                                     include_personal_data=acl.current_user_has_permission(personal_data_acl_resource))]
    else:
        rows = _.tr[_.td(colspan=len(query.column_names))[acl.inline_permission_denied_message()]]

    return str(bootstrap.table(headers=[header(query.data_set.columns[c]) for c in query.column_names], rows=rows))


@blueprint.route('/.row-count', methods=['POST'])
def row_count():
    from .query import Query

    query = Query.from_dict(flask.request.json)

    if current_user_has_permission(query):
        return flask.jsonify(query.row_count())
    else:
        return flask.make_response(acl.inline_permission_denied_message(), 403)


@blueprint.route('/.filter-row-count-<int:filter_pos>', methods=['POST'])
def filter_row_count(filter_pos):
    from .query import Query

    query = Query.from_dict(flask.request.json)

    if current_user_has_permission(query):
        return flask.jsonify(query.filter_row_count(filter_pos))
    else:
        return flask.make_response(acl.inline_permission_denied_message(), 403)


@blueprint.route('/.auto-complete')
def auto_complete():
    from .data_set import find_data_set
    ds = find_data_set(flask.request.args['data-set-id'])
    column_name = flask.request.args['column-name']
    if not acl.current_user_has_permission(data_set_acl_resources[ds.id]):
        return flask.jsonify([])
    elif not acl.current_user_has_permission(
            personal_data_acl_resource) and column_name in ds.personal_data_column_names:
        return flask.jsonify([])
    else:
        return flask.jsonify(ds.autocomplete_text_column(column_name, flask.request.args['term']))


@blueprint.route('/<data_set_id>/.download-csv', methods=['POST'])
def download_csv(data_set_id):
    from .query import Query

    query = Query.from_dict(json.loads(flask.request.form['query']))
    if not current_user_has_permission(query):
        return flask.abort(403, 'Not enough permissions to download this data set')
    else:
        file_name = query.data_set_id + ('-' + query.query_id if query.query_id else '') \
                    + '-' + datetime.date.today().isoformat() + '.csv'
        response = flask.make_response(query.as_csv(flask.request.form['delimiter'], flask.request.form['decimal-mark'],
                                                    acl.current_user_has_permission(personal_data_acl_resource)))
        response.headers['Content-type'] = 'text/csv; charset = utf-8'
        response.headers['Content-disposition'] = f'attachment; filename="{file_name}"'

        return response


def credentials_to_dict(credentials):
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes}


@blueprint.route('/.oauth2_export_to_spreadsheet', methods=['POST'])
def oauth2_export_to_spreadsheet():
    import os
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    from .query import Query
    query = Query.from_dict(json.loads(flask.request.form['query']))

    if current_user_has_permission(query):
        flask.session['query_for_callback'] = json.loads(flask.request.form['query'])  # flask.request.json

        # Use the client_secret.json file to identify the application requesting
        # authorization. The client ID (from that file) and access scopes are required.
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            config.google_oauth2_client_secrets_file(),
            scopes=['https://www.googleapis.com/auth/userinfo.profile', 'openid',
                    'https://www.googleapis.com/auth/drive.file',
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/userinfo.email'])

        # Indicate where the API server will redirect the user after the user completes
        # the authorization flow. The redirect URI is required.
        flow.redirect_uri = flask.url_for('data_sets.oauth2callback', _external=True)

        # Generate URL for request to Google's OAuth 2.0 server
        authorization_url, state = flow.authorization_url(
            # Enable offline access so that you can refresh an access token without
            # re-prompting the user for permission. Recommended for web server apps.
            access_type='offline',
            # Enable incremental authorization. Recommended as a best practice
            include_granted_scopes='true')

        # Store the state so the callback can verify the auth server response.
        flask.session['state'] = state

        return flask.redirect(authorization_url)
    else:
        return flask.make_response(acl.inline_permission_denied_message(), 403)


@blueprint.route('oauth2callback', methods=['GET'])
def oauth2callback():
    from .query import Query
    query = Query.from_dict(flask.session['query_for_callback'])

    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = flask.session['state']

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        config.google_oauth2_client_secrets_file(),
        scopes=['https://www.googleapis.com/auth/userinfo.profile', 'openid',
                'https://www.googleapis.com/auth/drive.file',
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/userinfo.email'],
        state=state)
    flow.redirect_uri = flask.url_for('data_sets.oauth2callback', _external=True)

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    authorization_response = flask.request.url
    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    credentials = flow.credentials
    flask.session['credentials'] = credentials_to_dict(credentials)

    spreadsheet_title = query.data_set_id + ('-' + query.query_id if query.query_id else '') \
                        + '-' + datetime.date.today().isoformat()

    service = build('sheets', 'v4', credentials=credentials)
    spreadsheet_body = {
        'properties': {
            'title': spreadsheet_title
        }
    }

    spreadsheet = service.spreadsheets().create(body=spreadsheet_body, fields='spreadsheetId')
    response = spreadsheet.execute()
    spreadsheet_id = response.get('spreadsheetId')

    data = query.as_spreadsheet(limit=100000)

    body = {
        "data": [
            {
                # data as list of lists (rows). Double quotes mandatory
                "values": data,
                "range": "A1",
                "majorDimension": "ROWS"
            }
        ],
        # RAW: The values the user has entered will not be parsed and will be stored as-is.
        # USER_ENTERED: The values will be parsed as if the user typed them into the UI.
        # Numbers will stay as numbers, but strings may be converted to numbers, dates, etc.
        # following the same rules that are applied when entering text into a cell via the Google Sheets UI.
        "valueInputOption": "USER_ENTERED"
    }

    result = service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()

    return flask.redirect('https://docs.google.com/spreadsheets/d/' + str(spreadsheet_id))


@blueprint.route('/.distribution-chart-<int:pos>', methods=['POST'])
def distribution_chart(pos: int):
    from .query import Query

    query = Query.from_dict(flask.request.json)
    column = list(query.data_set.columns.values())[pos]
    if not current_user_has_permission(query):
        return flask.make_response(acl.inline_permission_denied_message(), 403)
    elif column.column_name in query.data_set.personal_data_column_names \
            and not acl.current_user_has_permission(personal_data_acl_resource):
        return flask.make_response(
            acl.inline_permission_denied_message('Restricted personal data'), 403)
    else:

        if column.type == 'number':
            data = query.number_distribution(column.column_name)
        elif column.type == 'text':
            data = query.text_distribution(column.column_name)
        elif column.type == 'text[]':
            data = query.text_array_distribution(column.column_name)
        elif column.type == 'date':
            data = query.date_distribution(column.column_name)
        else:
            data = []

        return flask.jsonify({'column': column.to_dict(), 'data': data})


@blueprint.route('/.save', methods=['POST'])
def save():
    from .query import Query

    query = Query.from_dict(flask.request.json)
    if current_user_has_permission(query):
        query.save()
        flask.flash(f'Saved query ' + query.query_id, 'success')
        return flask.jsonify(
            flask.url_for('data_sets.data_set_page', data_set_id=query.data_set.id, query_id=query.query_id))
    else:
        flask.make_response(f'Not enough permissions to save query "{query.query_id}"', 403)


@blueprint.route('/<data_set_id>/.query-list')
def query_list(data_set_id):
    from .query import list_queries

    queries = list_queries(data_set_id)
    if queries:
        return str(bootstrap.table(
            headers=['Query', 'Last changed', 'By'],
            rows=[_.tr[_.td[
                           _.a(href=flask.url_for('data_sets.data_set_page', data_set_id=data_set_id, query_id=row[0]))[
                               row[0]]],
                       _.td[row[1].strftime('%Y-%m-%d')],
                       _.td[row[2]]] for row in queries]))
    else:
        return 'No queries saved yet'


@blueprint.route('/.display-query', methods=['POST'])
def display_query():
    from .query import Query

    query = Query.from_dict(flask.request.json)

    query_statement = query.to_sql()

    if query_statement:
        return str(_.tt[html.highlight_syntax(query_statement, language='sql')])
    else:
        return 'Can not display query statement.'


@blueprint.route('/<data_set_id>/<query_id>/.delete')
def _delete_query(data_set_id, query_id):
    from .query import delete_query

    if not acl.current_user_has_permission(data_set_acl_resources[data_set_id]):
        flask.flash(f'Not enough permissions to delete queries from "{data_set_id}"', 'danger')
    else:
        delete_query(data_set_id, query_id)
        flask.flash(f'Deleted query "{query_id}" from "{data_set_id}"', 'success')

    return flask.redirect(flask.url_for('data_sets.data_set_page', data_set_id=data_set_id))


def current_user_has_permission(query: 'Query') -> bool:
    """Checks whether the current user has permissions to query the data set"""
    return acl.current_user_has_permission(data_set_acl_resources[query.data_set.id])
