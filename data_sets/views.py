"""Data sets UI"""
import datetime
import json

import flask
from mara_page import acl, navigation, response, bootstrap, _, html

from . import config

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

    action_buttons = [response.ActionButton(action='javascript:dataSetPage.downloadCSV()', icon='download',
                                            label='CSV', title='Download as CSV'),
                      response.ActionButton(action='javascript:dataSetPage.load()', icon='folder-open',
                                            label='Load', title='Load previously saved query'),
                      response.ActionButton(action='javascript:dataSetPage.save()', icon='save',
                                            label='Save', title='Save query'),
                      response.ActionButton(action='javascript:dataSetPage.displayQuery()', icon='eye',
                                            label='Display query', title='Display query')]

    if query_id:
        action_buttons.insert(1, response.ActionButton(
            action=flask.url_for('data_sets._delete_query', data_set_id=data_set_id, query_id=query_id),
            icon='trash', label='Delete', title='Delete query'))

    return response.Response(
        title=f'Query "{query_id}" on "{ds.name}"' if query_id else f'New query on "{ds.name}"',
        html=[_.div(class_='row')[
                  _.div(class_='col-md-3')[
                      bootstrap.card(header_left='Query', body=_.div(id='query-details')['']),
                      bootstrap.card(header_left='Columns',
                                     body=[_.div(class_="form-group")[
                                               _.input(type="search", class_="columns-search form-control",
                                                       value="", placeholder="Filter")],
                                           _.div(id='columns-list')['']])],
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
                          body=_.div(id='filters')['']),
                      bootstrap.card(header_left=_.div(id='row-counts')[''],
                                     header_right=_.div(id='pagination')[''],
                                     body=_.div(id='preview')['']),
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
                                      'Download']]]]]]],
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
