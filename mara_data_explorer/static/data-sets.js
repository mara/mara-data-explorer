/**
 * Manages the state and interactions of a data set page
 * @param baseUrl The url prefix of the data sets flask blueprint
 * @param initializeArgs A dictionary of arguments needed for issueing an initialization request
 * @param pageSize How many rows to show in preview
 * @param chartColor The color in which to draw charts
 * @constructor
 */
function DataSetPage(baseUrl, args, pageSize, chartColor) {

    /** the current query */
    var query = null;

    /** the name of the data set, needed for showing row counts (e.g. "20 Orders") */
    var dataSetName = null;

    /** All columns as a list (for maintaining order). List of {column_name: 'Foo', type: text} dictionaries. */
    var allColumns = [];

    /** A dictionary of column_names to their types */
    var columnTypesByColumnName = {};

    /** The current page (needed in pagination) */
    var currentPage = 0;

    /** The total number of rows of the data set table */
    var dataSetRowCount = 0;

    /** The number of rows returned by the current query */
    var filteredRowCount = 0;


    /**
     * An ordered list of requests that need to be sent and processed,
     * a means of not bombarding the database with too many parallel queries.
     * A request is a dictionary with the keys 'url', 'data', 'handler', 'targets'.
     */
    var queue = [];

    /** All currently running Ajax requests by url */
    var runningRequests = {};

    /**
     * Cancels previous XHR requests for the same url and then puts the request in a queue
     * @param url the url to query
     * @param data data to post to the url
     * @param targets a list of dom elements that are updated with the data, will be temporarily filled by a spinner
     * @param handler the function that handles the request
     * @param highPrio when true, then the request is put at the front of the queue
     */
    function enqueueRequest(url, data, targets, handler, highPrio) {
        // cancel a running ajax request for the url
        if (runningRequests[url] != undefined) {
            console.log('abort running request for ' + url);
            runningRequests[url].abort();
            delete runningRequests[url];
        }

        // remove previous request for url from queue
        queue.forEach(function (request, i) {
            if (request.url == url) {
                console.log('removing queued request for ' + request.url);
                queue.splice(i);
            }
        });

        // replace targets with spinners
        targets.forEach(function (target) {
            target.html('<div style="height:' + target.innerHeight() + 'px">' + spinner() + '</div>');
        });

        // queue request
        var request = {'url': url, 'data': data, 'handler': handler, 'targets': targets};
        if (highPrio) {
            queue.unshift(request);
        } else {
            queue.push(request);
        }
        processQueue();
    }

    /** starts new requests if possible */
    function processQueue() {
        // don't run more than 4 requests concurrently
        while (Object.keys(runningRequests).length < 3 && queue.length > 0) {
            var request = queue.shift();

            runningRequests[request.url] = $.ajax({
                type: "POST",
                url: request.url,
                contentType: "application/json; charset=utf-8",
                data: JSON.stringify(request.data),
                success: function (data) {
                    request.handler(data);
                },
                error: function (xhr, textStatus, errorThrown) {
                    if (errorThrown != 'abort') {
                        if (xhr.status == 403) {
                            console.log(xhr);
                            for (var i in request.targets) {
                                request.targets[i].empty().append(xhr.responseText);
                            }
                        } else {
                            var icon = $('<span class="fa fa-bug" style="color:red" data-toggle="tooltip"> </span>');
                            icon.attr('title', textStatus + ' while posting to "' + request.url + '": ' + errorThrown);

                            for (var i in request.targets) {
                                request.targets[i].empty().append(icon.clone());
                            }
                            $('[data-toggle="tooltip"]').tooltip();
                        }
                    }
                },

                complete: function (ajax) {
                    delete runningRequests[request.url];
                    processQueue();
                }
            });
        }
    }

    var allTargets = [$('#columns-list'), $('#preview'), $('#filters'), $('#row-counts'), $('#pagination'), $('#query-details')];

    // get query object from server and initialize ui
    enqueueRequest(
        baseUrl + '/.initialize', args,
        allTargets,
        function (data) {
            query = data.query;
            allColumns = data.all_columns;

            if (data.all_columns.length == 0) {
                allTargets.forEach(function (target) {
                    target.html('∅');
                });
                return;
            }

            columnTypesByColumnName = {};
            allColumns.forEach(function (column, i) {
                columnTypesByColumnName[column.column_name] = column.type;
                var distributionChartCard = $('#distribution-chart-template').clone();
                distributionChartCard.attr('id', 'distribution-chart-' + i);
                distributionChartCard.find('.card-header-left').html(column.column_name);
                $('#distribution-charts').append(distributionChartCard);
            });

            dataSetName = data.data_set_name;
            dataSetRowCount = data.row_count;

            updateFilters();
            updatePreview();
            updateRowCount();
            updateDistributionCharts(true);


            $('#select-all').click(function (e) {
                e.preventDefault();

                var allSelected = query.column_names.length == allColumns.length;

                var checkboxes = document.getElementsByName('columns_checkbox');
                for (var i = 0, n = checkboxes.length; i < n; i++) {
                    checkboxes[i].checked = !allSelected;
                }
                updateColumns();
                this.blur();
            });

            // fill columns card
            column_check_boxes = [];
            allColumns.forEach(function (column) {
                var columnType = columnTypesByColumnName[column.column_name];
                column_check_boxes.push($('<label><input type="checkbox" name="columns_checkbox" value="' + column.column_name + '" '
                    + ($.inArray(column.column_name, query.column_names) > -1 ? ' checked="checked" ' : '')
                    + '/> ' + column.column_name + '</label>').change(updateColumns));

                if (columnType != 'json') {
                    $('#filter-menu').append($('<span class="dropdown-item"/>').append(column.column_name).click(function () {
                        addFilter(column.column_name, null, false);
                    }));
                }
            });

            $('#columns-list').empty().hide().append(column_check_boxes).fadeIn(300);

            $(".columns-search").on("keyup change", function () {
                var searchString = $(this).val();
                searchString = searchString == null ? "" : searchString.toLowerCase();

                var foundMatch = false;
                $(this).parent().parent().find("#columns-list label, span.dropdown-item").each(function () {
                    var column_name = $(this).text().trim();
                    var match = searchString == "" || column_name.toLowerCase().indexOf(searchString) != -1;
                    $(this).css("display", match ? "block" : "none");
                    foundMatch |= match;
                });
                $(this).css("color", foundMatch ? "" : "#d2322d");
            });
            $(".columns-search").click(function (ev) {
                ev.stopPropagation();
            });

            $('#query-details').empty().append(
                $('<input id="query-id" type="text" class="form-control" placeholder="Query name"/>')
                    .attr('value', query.query_id));
            if (query.created_at) {
                $('#query-details').append($('<div>Created : ' + query.created_at + ' (' + query.created_by + ')</div>'));
                $('#query-details').append($('<div>Updated : ' + query.updated_at + ' (' + query.updated_by + ')</div>'));
            }

        });

    /**
     * Adds a filter to the query
     * @param columnName The column to filter
     * @param value the filter value
     * @param updateExistingFilter When the True and a filter for the column already exists, then update that one.
     */
    function addFilter(columnName, value, updateExistingFilter) {
        var existingFilterPos = query.filters.findIndex(function (filter) {
            if (filter.column_name == columnName) return true;
        });

        if (existingFilterPos != -1 && updateExistingFilter) {
            changeFilter(existingFilterPos, 'value', value);
        } else {
            var columnType = columnTypesByColumnName[columnName];

            var filter = {
                column_name: columnName,
                operator: {
                    'text': '=',
                    'text[]': '=',
                    'number': '>',
                    'date': '<='
                }[columnType],
                value: value ? value : {
                    'text': [],
                    'text[]': [],
                    'number': 0,
                    'date': new Date().toJSON().slice(0, 10)
                }[columnType]
            };
            query.filters.push(filter);
            currentPage = 0;
            updateFilterRow(query.filters.length - 1);
            updateDistributionCharts(true);
            addColumn(columnName);
            updateRowCount();
        }
        $('html, body').animate({scrollTop: 0}, 500);
    }

    /** Remove a filter from the query */
    function deleteFilter(pos) {
        query.filters.splice(pos, 1);
        updateFilters();
        currentPage = 0;
        updatePreview();
        updateRowCount();
        updateDistributionCharts(true);

    }

    /**
     * Change an aspect of afilter
     * @param pos The position of the filter in the query
     * @param key Which par of the filter to change (i.e. 'operator' or 'value')
     * @param value The new value for the key
     */
    function changeFilter(pos, key, value) {
        query.filters[pos][key] = value;
        currentPage = 0;
        updatePreview();
        updateRowCount();
        updateFilterRow(pos);
        updateDistributionCharts(true);
    }

    /** Redraws the whole filters table */
    function updateFilters() {
        $('#filters').empty().append($('<table class="mara-table table table-condensed table-sm"><tbody/></table>'));
        query.filters.forEach(function (filter, pos) {
            updateFilterRow(pos);
        });
    }

    /** Redraws one row of the filters table */
    function updateFilterRow(pos) {
        var type = columnTypesByColumnName[query.filters[pos].column_name];
        var operators = {
            'number': ['>=', '>', '=', '<', '<='],
            'date': ['>=', '>', '=', '<', '<='],
            'text': ['=', '!=', '~'],
            'text[]': ['=', '!=']
        }[type];

        // build table row
        var input = $('<input class="form-control" required="required"/>').attr('type', type);
        var row = $('<tr/>')
            .append($('<td class="filter-controls"/>')
                .append($('<div/>')
                    .append(query.filters[pos].column_name)
                    .append($('<select/>')
                        .append(operators.map(function (operator) {
                            var option = $('<option>').attr('value', operator).append(operator);
                            if (operator == query.filters[pos].operator) {
                                option.attr('selected', 'selected');
                            }
                            return option;
                        }))
                        .change(function () {
                            changeFilter(pos, 'operator', $(this).val());
                            $(this).blur();
                        }))
                    .append(input)))
            .append($('<td><div id="filter-counts-' + pos.toString() + '"/></td>'))
            .append($('<td/>')
                .append($('<a href="#" class="delete-button fa fa-trash"/>')
                    .click(function () {
                        deleteFilter(pos);
                    })));

        // replace existing row or append to table
        if ($('#filters table > tbody > tr').length <= pos) {

            $('#filters table > tbody').append(row);
        } else {
            $('#filters table > tbody > tr:nth-child(' + (pos + 1) + ')').replaceWith(row);
        }

        // update filter row count
        enqueueRequest(baseUrl + '/.filter-row-count-' + pos, query, [$('#filter-counts-' + pos)],
            function (filterCount) {
                $('#filter-counts-' + pos).empty().append('' + filterCount + ' ' + dataSetName + ' ('
                    + (Math.round(1000.0 * filterCount / dataSetRowCount) / 10.0) + '%)');
            }, false);

        // add auto-completion and event handlers
        if (type == 'text' || type == 'text[]') {
            var source = new Bloodhound({
                datumTokenizer: Bloodhound.tokenizers.obj.whitespace("value"),
                queryTokenizer: Bloodhound.tokenizers.whitespace,
                cache: false,
                remote: {
                    url: baseUrl + '/.auto-complete?term=%QUERY'
                        + "&data-set-id=" + encodeURIComponent(query.data_set_id)
                        + "&column-name=" + encodeURIComponent(query.filters[pos].column_name),
                    wildcard: "%QUERY"
                }
            });


            input.tagsinput({
                tagClass: "",
                freeInput: true,
                confirmKeys: [13],
                typeaheadjs: [{minLength: 0}, {source: source, limit: 100}]
            });

            if (query.filters[pos].value != null) {
                for (var i = 0; i < query.filters[pos].value.length; i++) {
                    input.tagsinput("add", query.filters[pos].value[i]);
                }
            }

            input.on("itemAdded itemRemoved", function () {
                changeFilter(pos, 'value', input.tagsinput("items"));
            });

            var typeAheadInput = input.parent().find('.tt-input');
            var menu = null;

            // special handling of copy + paste
            typeAheadInput.on("paste", function (e) {
                var pastedText = e.originalEvent.clipboardData.getData('text');
                // split by whitespace, ',' and ';', then filter empty strings
                var values = pastedText.split(/[\s,;]/).filter(Boolean);
                changeFilter(pos, 'value', [].concat(query.filters[pos].value, values));
                $('div.tt-menu').hide();
                return false;
            });


        } else {
            var typeTimeout;

            input.attr('value', query.filters[pos].value);
            input.change(function () {
                changeFilter(pos, 'value', $(this).val());
            }).keyup(function () {
                if (typeTimeout) {
                    clearTimeout(typeTimeout);
                }
                var value = $(this).val();

                typeTimeout = setTimeout(function () {
                    changeFilter(pos, 'value', value);
                }, 2000);

            });
        }
    }

    function copyToClipboard(text) {
        var input = $("<input>");
        $("body").append(input);
        input.val(text).select();
        document.execCommand("copy");
        input.remove();
    }

    /** replace the content of the preview card */
    function updatePreview() {
        enqueueRequest(
            baseUrl + '/.preview',
            {query: query, limit: pageSize, offset: pageSize * currentPage},
            [$("#preview")],
            function (data) {
                $("#preview").html(data);
                $("#preview th a").click(function () {
                    column_name = $(this)[0].name;
                    if (query.sort_column_name == column_name) {
                        query.sort_order = (query.sort_order == 'ASC' ? 'DESC' : query.sort_order == 'DESC' ? null : 'ASC');
                    } else {
                        query.sort_column_name = column_name;
                        query.sort_order = 'ASC';
                    }
                    updatePreview();
                });
                query.column_names.forEach(function (columnName, i) {
                    var columnType = columnTypesByColumnName[columnName];
                    var valueContainers = $("#preview td:nth-child(" + (i + 1) + ") span.preview-value");
                    valueContainers.each(function (i, valueContainer) {
                        var value = $(valueContainer).contents().get(0).nodeValue;
                        var controls = $('<div class="hover-controls"/>');

                        var filterFunction = null;


                        if (columnType == 'text' || columnType == 'text[]') {
                            filterFunction = function () {
                                addFilter(columnName, [value], true);
                            };
                        } else if (columnType == 'date') {
                            filterFunction = function () {
                                addFilter(columnName, new Date(value).toJSON().slice(0, 10), true);
                            };
                        } else if (columnType == 'number') {
                            filterFunction = function () {
                                addFilter(columnName, value, true);
                            };
                        }
                        if (filterFunction) {
                            var filterLink = $('<a href="#"><span class="fa fa-filter"> </span> Filter</a>')
                                .click(filterFunction);
                            controls.append(filterLink);
                            $(valueContainer).click(filterFunction);
                        }
                        controls.append($('<a href="#"><span class="fa fa-copy"> </span> Copy to clipboard</a>')
                            .click(function () {
                                copyToClipboard(value);
                                return false;
                            }));


                        $(valueContainer).append(controls);
                    });
                });
                floatMaraTableHeaders();
            }, true);

    }

    /** Redraws the left and right title of the preview card */
    function updateRowCount() {
        enqueueRequest(
            baseUrl + '/.row-count', query, [$('#row-counts'), $('#pagination')],
            function (_filteredRowCount) {
                filteredRowCount = _filteredRowCount;

                $('#row-counts').empty().append(
                    '' + filteredRowCount + ' ' + dataSetName + ' ('
                    + (Math.round(1000.0 * filteredRowCount / dataSetRowCount) / 10.0) + '%)');

                // reset pagination
                $('#pagination').empty().append('Rows <span id="pagination-from">1</span> - <span id="pagination-to">'
                    + Math.min(pageSize, filteredRowCount) + '</span>');

                if (filteredRowCount > pageSize) {
                    $('#pagination').append('&#160;&#160;').append(
                        $('<a id="pagination-backward-button" href="#" style="display:none" title="Previous page (Previous page (⇠ key))"><span class="fa fa-angle-left"> </span> Previous</a>').click(paginateBackward)
                    );
                    $('#pagination').append('&#160;&#160;').append(
                        $('<a href="#" id="pagination-forward-button" title="Next page (⇢ key)">Next <span class="fa fa-angle-right"> </span></a>').click(paginateForward)
                    );
                }

            }, false);
    }

    /**
     * Updates the column distribution charts at the bottom of the page according
     * @param reloadAll When true, also reload contents of visible cards
     */
    function updateDistributionCharts(reloadAll) {
        allColumns.forEach(function (column, i) {
            var div = $("#distribution-chart-" + i);
            if ($.inArray(column['column_name'], query.column_names) != -1) {
                var isVisible = div.is(":visible");
                if (!isVisible) {
                    div.slideDown();
                }

                if (!isVisible || reloadAll) {
                    var cardBody = div.find('.chart-container');

                    enqueueRequest(baseUrl + '/.distribution-chart-' + i, query, [cardBody],
                        function (data) {
                            if (!data.data || data.data.length < 1) {
                                cardBody.html('∅');
                            } else {
                                switch (data.column.type) {
                                    case 'number':
                                        drawNumberDistributionChart(cardBody[0], data.column.column_name, data.data);
                                        break;
                                    case 'text':
                                    case 'text[]':
                                        drawTextDistributionChart(cardBody[0], data.column.column_name, data.data);
                                        break;
                                    case 'date':
                                        drawDateDistributionChart(cardBody[0], data.column.column_name, data.data);
                                        break;
                                }
                            }
                        });
                }
            } else {
                div.slideUp();
            }
        });
    }

    /** Update the output columns of the query */
    function updateColumns() {
        query['column_names'] = $("#columns-list input:checked").map(
            function () {
                return this.value;
            }).get();

        $('#select-all').text(query.column_names.length < allColumns.length ? 'Select all' : 'Deselect all');
        updatePreview();
        updateDistributionCharts(false);
    }

    /** Adds a column to the query, indirectly by checking the column input on the left */
    function addColumn(columnName) {
        $('#columns-list input[value="' + columnName + '"]').prop('checked', true);
        updateColumns();
    }

    /** Helper function for stepping through preview table */
    function paginate() {
        $('#pagination-from').html(currentPage * pageSize + 1);
        $('#pagination-to').html((currentPage + 1) * pageSize);
        $('#pagination-forward-button').css('display', (currentPage + 1) * pageSize < filteredRowCount ? 'inline' : 'none');
        $('#pagination-backward-button').css('display', currentPage > 0 ? 'inline' : 'none');
        updatePreview();
    }

    /** Shows the next rows in the preview table */
    function paginateForward() {
        if ((currentPage + 1) * pageSize < filteredRowCount) {
            currentPage++;
            paginate();
        }
        return false;
    }

    /** Shows the previous rows in the preview table */
    function paginateBackward() {
        if (currentPage > 0) {
            currentPage--;
            paginate();
        }
        return false;
    }

    // paginate with left + right cursor keys
    $(document).keydown(function (e) {
        if (e.keyCode == 37) {
            return paginateBackward();
        } else if (e.keyCode == 39) {
            return paginateForward();
        }
    });

    /** saves the current query in the mara database */
    function save() {
        $('#missing-query-id-alert').detach();
        if (!$('#query-id').val()) {
            $('<div id="missing-query-id-alert" class="alert alert-danger">Please enter a query name</div>').insertBefore('#query-id');
            $('#query-id').focus();
        } else {
            query.query_id = $('#query-id').val();

            $.ajax({
                type: "POST",
                url: baseUrl + '/.save',
                contentType: "application/json; charset=utf-8",
                data: JSON.stringify(query),
                success: function (data) {
                    window.location.replace(data);
                },
                error: function (xhr, textStatus, errorThrown) {
                    showAlert('Could not save query ' + query.query_id, 'danger');
                }
            });

        }
    }

    /** loads a query from the mara database */
    function load() {
        $('#query-list').empty().append(spinner());
        loadContentAsynchronously('query-list', baseUrl + '/' + query.data_set_id + '/.query-list');
        $('#load-query-dialog').modal();
    }

    /** downloads the curreny query a CSV file */
    function downloadCSV() {
        $('#download-csv-dialog input[name=query]').val(JSON.stringify(query));
        $('#download-csv-dialog').modal();
    }

    /** exports current query's output to a google sheet (modal) */
    function exportToGoogleSheet() {
        $('#google-sheet-export-dialog input[name=query]').val(JSON.stringify(query));
        $('#google-sheet-export-dialog').modal();
    }

    // options for drawing the distribution charts
    var chartOptions = {
        chartArea: {left: 0, top: 0, width: '100%', height: '100%'},
        legend: {position: "none"},
        curveType: 'function', pointSize: 3, lineWidth: 1.5, colors: [chartColor],
        //fontName: '"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
        fontSize: '14',
        tooltip: {isHtml: true},
        hAxis: {
            baselineColor: '#eee',
            textPosition: 'in', gridlines: {color: '#eee'}, textStyle: {color: '#888'}
        },
        vAxis: {
            textPosition: 'in', format: 'short', gridlines: {color: '#eee'},
            textStyle: {color: '#888'},
            baselineColor: '#eee', viewWindow: {min: 0}
        }
    };

    /** Draw a histogram of numeric values */
    function drawNumberDistributionChart(container, columnName, rows) {
        google.charts.load('current', {'packages': ['corechart']});

        google.charts.setOnLoadCallback(function () {
            var data = new google.visualization.DataTable();
            data.addColumn('number', columnName);
            data.addColumn('number', '# ' + dataSetName);
            data.addColumn({type: 'string', role: 'tooltip', 'p': {'html': true}});
            rows.forEach(function (row, i) {
                data.addRow([row[0] + (row[1] - row[0]) / 2, row[2], '<div style="padding:5px;white-space: nowrap">≥ ' + row[0]
                + '<br/>< ' + row[1] + '<br/><b>' + row[2] + '</b> ' + dataSetName + '</div>']);
            });
            var chart = new google.visualization.ColumnChart(container);
            chart.draw(data, Object.assign({}, chartOptions, {'bar': {'groupWidth': '100%'}}));

            google.visualization.events.addListener(chart, 'select', function () {
                var selectedItem = chart.getSelection()[0];
                if (selectedItem) {
                    addFilter(columnName, rows[selectedItem.row][0], true);
                }
            });

            $(window).resize(function () {
                chart.draw(data, chartOptions);
            });
        });
    }

    /** Draw a time histogram */
    function drawDateDistributionChart(container, columnName, rows) {
        google.charts.load('current', {'packages': ['corechart']});

        google.charts.setOnLoadCallback(function () {
            var data = new google.visualization.DataTable();
            data.addColumn('date', columnName);

            data.addColumn('number', '# ' + dataSetName);
            data.addColumn({type: 'string', role: 'tooltip', 'p': {'html': true}});

            rows.forEach(function (row, i) {
                var date = new Date(row[0]);
                var n = row[2];
                var caption = row[1];

                data.addRow([date, n,
                    '<div style="padding:5px;white-space: nowrap">' + caption
                    + '<br/><b>' + n + '</b> ' + dataSetName + '</div>']);
            });

            var chart = new google.visualization.LineChart(container);
            chart.draw(data, chartOptions);

            google.visualization.events.addListener(chart, 'select', function () {
                var selectedItem = chart.getSelection()[0];
                if (selectedItem) {
                    addFilter(columnName, new Date(rows[selectedItem.row][0]).toJSON().slice(0, 10), true);
                }
            });

            $(window).resize(function () {
                chart.draw(data, chartOptions);
            });
        })
    }

    /** draw a histogram of the most frequent text categories */
    function drawTextDistributionChart(container, columnName, rows) {
        google.charts.load('current', {'packages': ['corechart']});

        google.charts.setOnLoadCallback(function () {
            var data = new google.visualization.DataTable();
            data.addColumn('string', columnName);
            data.addColumn('number', '# ' + dataSetName);
            data.addColumn({type: 'string', role: 'tooltip', 'p': {'html': true}});
            rows.forEach(function (row, i) {
                data.addRow([row[0], row[1], '<div style="padding:5px;white-space: nowrap">' + row[0] + '<br/><b>' + row[1] + '</b> ' + dataSetName + '</div>']);
            });

            var chart = new google.visualization.BarChart(container);
            chart.draw(data, chartOptions);

            google.visualization.events.addListener(chart, 'select', function () {
                var selectedItem = chart.getSelection()[0];
                if (selectedItem) {
                    addFilter(columnName, [rows[selectedItem.row][0]], true);
                }
            });

            $(window).resize(function () {
                chart.draw(data, chartOptions);
            });
        });
    }

    /** display a query */
    function displayQuery() {
        $('#display-query-dialog').modal();
        $('#query-display').empty().append(spinner());

        $.ajax({
            type: "POST",
            url: baseUrl + '/.display-query',
            contentType: "application/json; charset=utf-8",
            data: JSON.stringify(query),
            success: function (data) {
                $('#query-display').empty().append(data).fadeIn(300);
            },
            error: function () {
                showAlert('Could not display query', 'danger');
            }
        });
    }

    // make some function externally available (mainly for use in action buttons)
    return {
        'save': save,
        'load': load,
        'downloadCSV': downloadCSV,
        'displayQuery': displayQuery,
        'exportToGoogleSheet': exportToGoogleSheet
    };
}