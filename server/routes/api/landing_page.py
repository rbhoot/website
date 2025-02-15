# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Defines endpoints for the landing page.

TODO(shifucun): once this is well tested, can deprecate corresponding code
in chart.py and place.py
"""

import copy
import json
import logging
import urllib.parse
from collections import defaultdict
import time

import lib.range as lib_range
import routes.api.place as place_api
import services.datacommons as dc_service
from cache import cache
from flask import Blueprint, Response, current_app, g, url_for, request
from flask_babel import gettext

# Define blueprint
bp = Blueprint("api.landing_page", __name__, url_prefix='/api/landingpage')

BAR_CHART_TYPES = ['parent', 'similar', 'nearby', 'child']
MAX_DENOMINATOR_BACK_YEAR = 3
MIN_CHART_TO_KEEP_TOPICS = 30
OVERVIEW = 'Overview'


def get_landing_page_data(dcid, new_stat_vars):
    return get_landing_page_data_helper(dcid, '^'.join(new_stat_vars))


@cache.memoize(timeout=3600 * 24)  # Cache for one day.
def get_landing_page_data_helper(dcid, stat_vars_string):
    data = {'place': dcid}
    if stat_vars_string:
        data['newStatVars'] = '^'.split(stat_vars_string)
    response = dc_service.fetch_data('/landing-page',
                                     data,
                                     compress=False,
                                     post=True,
                                     has_payload=False)
    return response


def build_url(dcids, statvar_to_denom, is_scaled=False):
    # Landing page chart could have multiple denominator for multiple numerator.
    # This is not supported in timeline tool, in which case, fallback to use
    # Count_Person.
    # TODO(shifucun): support more complicated denominator case when "Calculator"
    # tool is available
    anchor = '&place={}&statsVar={}'.format(','.join(dcids),
                                            '__'.join(statvar_to_denom.keys()))
    if is_scaled:
        denoms = set(statvar_to_denom.values())
        if len(denoms) > 1:
            denom = "Count_Person"
        else:
            denom = denoms.pop()
        anchor += '&pc&denom={}'.format(denom)
    return urllib.parse.unquote(url_for('tools.timeline', _anchor=anchor))


def fill_translation(chart):
    chart['title'] = gettext(chart['titleId'])
    del chart['titleId']
    if 'description' in chart:
        del chart['description']
    return chart


# TODO: add test for chart_config for assumption that each combination of stat vars will only have one config in chart_config.
def build_spec(chart_config, i18n=True):
    """Builds hierachical spec based on chart config.

    Args:
        chart_config: A list of chart config.
        i18: Whether to i18n the strings, only set to true for testing.
    """
    spec = defaultdict(lambda: defaultdict(list))
    # Map: category -> topic -> [config]
    # Within each category, the topics are sorted.
    for conf in chart_config:
        config = copy.deepcopy(conf)
        if i18n:
            config = fill_translation(config)
            if 'relatedChart' in config and config['relatedChart']['scale']:
                config['relatedChart'] = fill_translation(
                    config['relatedChart'])
        # Delete non-necessary fields
        is_overview = config.get('isOverview', False)
        if 'isOverview' in config:
            del config['isOverview']
        category = config['category']
        del config['category']
        topic = config.get('topic', '')
        if 'topic' in config:
            del config['topic']
        # Assign the config to "Overview" and corresponding category.
        if is_overview:
            # In "Overview", category is used as topic.
            spec[OVERVIEW][category].append(copy.deepcopy(config))
        spec[category][topic].append(copy.deepcopy(config))
    # Sort the config within each topic by title
    for _, topic_data in spec.items():
        for topic in topic_data:
            topic_data[topic].sort(key=lambda x: x['title'])
    return spec


def get_denom(cc, related_chart=False):
    """Get the numerator and denominator map."""
    # If chart requires denominator, use it for both primary and related charts.
    if 'denominator' in cc:
        result = {}
        if len(cc['denominator']) != len(cc['statsVars']):
            raise ValueError('Denominator number not matching: %s', cc)
        for num, denom in zip(cc['statsVars'], cc['denominator']):
            result[num] = denom
        return result
    # For related chart, use the denominator that is specified in the
    # 'relatedChart' field if present.
    if related_chart and cc.get('relatedChart', {}).get('scale', False):
        return cc['relatedChart'].get('denominator', 'Count_Person')
    return None


def get_series(data, place, stat_vars):
    """Get time series from the landing page data.

    Aggregate for all the stat vars and return empty series if any stat var data
    is missing

    Returns:
        series and sources.
    """
    all_series = []
    sources = set()
    num_sv = len(stat_vars)
    for sv in stat_vars:
        if 'data' not in data[place] or sv not in data[place]['data']:
            return {}, []
        series = data[place]['data'][sv]
        all_series.append(series['val'])
        sources.add(series['metadata']['provenanceUrl'])
    # One series, no need to aggregate
    if num_sv == 1:
        return all_series[0], sources
    merged_series = defaultdict(list)
    for series in all_series:
        for date, value in series.items():
            merged_series[date].append(value)
    # Aggregate
    agg_series = {}
    for date, values in merged_series.items():
        if len(values) == num_sv:
            agg_series[date] = sum(values)
    return agg_series, sources


def get_stat_var_group(cc, data, places):
    """Get the stat var grouping for aggregation."""
    if 'aggregate' in cc:
        agg_type = lib_range.get_aggregate_config(cc['aggregate'])
        place_stat_vars = defaultdict(list)
        for place in places:
            if place not in data or 'data' not in data[place]:
                continue
            for sv in cc['statsVars']:
                if sv in data[place]['data']:
                    place_stat_vars[place].append(sv)
        result = lib_range.aggregate_stat_var(place_stat_vars, agg_type)
        for place in places:
            if place not in result:
                result[place] = {}
    else:
        result = {}
        for place in places:
            result[place] = {sv: [sv] for sv in cc['statsVars']}
    return result


def get_snapshot_across_places(cc, data, places):
    """Get the snapshot used for bar data across a few places.

    This will scale the value if required and pick the latest date that has the
    most <place, stat_var> entries.
    """
    if not places:
        return {}, {}

    # date_to_data is a dictionary from date to place and a tuple of
    # (stat_var, value) pair.
    # Example:
    # {
    #     "2018": {
    #         "geoId/06":[("Count_Person", 200), ("Count_Person_Female", 100)],
    #         "geoId/08":[("Count_Person", 300), ("Count_Person_Female", 150)],
    #     },
    #     "2017": {
    #         "geoId/06":[("Count_Person", 300), ("Count_Person_Female", 150)],
    #         "geoId/08":[("Count_Person", 400), ("Count_Person_Female", 200)],
    #     },
    # }
    date_to_data = defaultdict(lambda: defaultdict(list))

    # TODO(shifucun/beets): add a unittest to ensure denominator is set
    # explicitly when scale==True
    num_denom = get_denom(cc, related_chart=True)
    sources = set()
    place_stat_var_group = get_stat_var_group(cc, data, places)
    statvar_to_denom = {}
    for place in places:
        if place not in data:
            continue
        stat_var_group = place_stat_var_group[place]
        for num_sv, sv_list in stat_var_group.items():
            num_series, num_sources = get_series(data, place, sv_list)
            if not num_series:
                continue
            sources.update(num_sources)
            if num_denom:
                if isinstance(num_denom, dict):
                    denom_sv = num_denom[num_sv]
                else:
                    denom_sv = num_denom
                statvar_to_denom[num_sv] = denom_sv
                denom_series, denom_sources = get_series(
                    data, place, [denom_sv])
                if not denom_series:
                    continue
                sources.update(denom_sources)
                result_series = scale_series(num_series, denom_series)
            else:
                result_series = num_series
                statvar_to_denom[num_sv] = None
            # Turn the value to be keyed by date.
            for date, value in result_series.items():
                date_to_data[date][place].append((num_sv, value))
    # Pick a date that has the most series across places.
    dates = sorted(date_to_data.keys(), reverse=True)
    if not dates:
        return {}, {}
    count = 0
    chosen_date = None
    for date in dates:
        if len(date_to_data[date]) > count:
            count = len(date_to_data[date])
            chosen_date = date
    result = {'date': chosen_date, 'data': [], 'sources': list(sources)}
    for place in places:
        points = {}
        for stat_var, value in date_to_data[chosen_date][place]:
            points[stat_var] = value
        if points:
            result['data'].append({'dcid': place, 'data': points})
    return result, statvar_to_denom


# TODO(shifucun): Add unittest for these helper functions
def get_bar(cc, data, places):
    """Get the bar data across a few places.

    This will scale the value if required and pick the latest date that has the
    most <place, stat_var> entries.
    """
    result, statvar_denom = get_snapshot_across_places(cc, data, places)
    if not result:
        return {}
    # Should have data other than the primary place. Return empty struct to
    # so client won't draw chart.
    if len(result['data']) <= 1:
        return {}
    is_scaled = (('relatedChart' in cc and
                  cc['relatedChart'].get('scale', False)) or
                 ('denominator' in cc))
    result['exploreUrl'] = build_url(places, statvar_denom, is_scaled)
    return result


def get_trend(cc, data, place):
    """Get the time series data for a place."""
    if place not in data:
        return {}

    result_series = {}
    sources = set()
    num_denom = get_denom(cc)
    stat_var_group = get_stat_var_group(cc, data, [place])[place]
    statvar_denom = {}
    for num_sv, sv_list in stat_var_group.items():
        num_series, num_sources = get_series(data, place, sv_list)
        if not num_series:
            continue
        sources.update(num_sources)
        if num_denom:
            if isinstance(num_denom, dict):
                denom_sv = num_denom[num_sv]
            else:
                denom_sv = num_denom
            denom_sv = num_denom[num_sv]
            statvar_denom[num_sv] = denom_sv
            denom_series, denom_sources = get_series(data, place, [denom_sv])
            if not denom_series:
                continue
            sources.update(denom_sources)
            result_series[num_sv] = scale_series(num_series, denom_series)
        else:
            result_series[num_sv] = num_series
            statvar_denom[num_sv] = None
    # filter out time series with single data point.
    for sv in list(result_series.keys()):
        if len(result_series[sv]) <= 1:
            del result_series[sv]
    if not result_series:
        return {}

    is_scaled = ('denominator' in cc)
    return {
        'series': result_series,
        'sources': list(sources),
        'exploreUrl': build_url([place], statvar_denom, is_scaled)
    }


def get_year(date):
    try:
        return int(date.split('-')[0])
    except IndexError:
        raise ValueError('no valid date format found %s', date)


# TODO(shifucun): Add unittest.
def scale_series(numerator, denominator):
    """Scale two time series.
    The date of the two time series may not be exactly aligned. Here we use
    year alignment to match two date. If no denominator is found for a
    numerator, then the data is removed.
    """
    data = {}
    for date, value in numerator.items():
        if date in denominator:
            if denominator[date] > 0:
                data[date] = value / denominator[date]
            else:
                data[date] = 0
        else:
            try:
                numerator_year = get_year(date)
                for i in range(0, MAX_DENOMINATOR_BACK_YEAR + 1):
                    year = str(numerator_year - i)
                    if year in denominator:
                        if denominator[year] > 0:
                            data[date] = value / denominator[year]
                        else:
                            data[date] = 0
                        break
            except ValueError:
                return {}
    return data


def get_i18n_all_child_places(raw_page_data):
    all_child_places = raw_page_data.get('allChildPlaces', {})
    all_dcids = []
    for place_type in list(all_child_places.keys()):
        for place in all_child_places[place_type]['places']:
            all_dcids.append(place.get('dcid', ''))
    i18n_names = place_api.get_i18n_name(all_dcids,
                                         False)  # Don't resolve en-only names
    for place_type in list(all_child_places.keys()):
        for place in all_child_places[place_type]['places']:
            dcid = place.get('dcid')
            i18n_name = i18n_names.get(dcid, '')
            if i18n_name:
                place['name'] = i18n_name
    for place_type in list(all_child_places.keys()):
        all_child_places[place_type] = all_child_places[place_type]['places']
    return all_child_places


@bp.route('/data/<path:dcid>')
@cache.cached(timeout=3600 * 24, query_string=True)  # Cache for one day.
def data(dcid):
    """
    Get chart spec and stats data of the landing page for a given place.
    """
    logging.info("Landing Page: cache miss for %s, fetch and process data ...",
                 dcid)
    target_category = request.args.get("category")
    spec_and_stat = build_spec(current_app.config['CHART_CONFIG'])
    new_stat_vars = current_app.config['NEW_STAT_VARS']
    raw_page_data = get_landing_page_data(dcid, new_stat_vars)

    if 'statVarSeries' not in raw_page_data:
        logging.info("Landing Page: No data for %s", dcid)
        return Response(json.dumps({}), 200, mimetype='application/json')

    # Filter out Metropolitan France parent place.
    parent_places = [
        el for el in raw_page_data.get('parentPlaces', [])
        if el != 'country/FXX'
    ]
    raw_page_data['parentPlaces'] = parent_places

    # Only US places have comparison charts.
    is_usa_place = False
    for place in [dcid] + raw_page_data.get('parentPlaces', []):
        if place == 'country/USA':
            is_usa_place = True
            break

    all_stat = raw_page_data['statVarSeries']

    # Remove empty category and topics
    for category in list(spec_and_stat.keys()):
        for topic in list(spec_and_stat[category].keys()):
            filtered_charts = []
            for chart in spec_and_stat[category][topic]:
                keep_chart = False
                for stat_var in chart['statsVars']:
                    if all_stat[dcid].get('data', {}).get(stat_var, {}):
                        keep_chart = True
                        break
                if keep_chart:
                    filtered_charts.append(chart)
            if not filtered_charts:
                del spec_and_stat[category][topic]
            else:
                spec_and_stat[category][topic] = filtered_charts
        if not spec_and_stat[category]:
            del spec_and_stat[category]

    # Populate the data for each chart.
    # This is heavy lifting, takes time to process.
    for category in spec_and_stat:
        # Only process the target category.
        if category != target_category:
            continue
        if category == OVERVIEW:
            if is_usa_place:
                chart_types = ['nearby', 'child']
            else:
                chart_types = ['similar']
        else:
            chart_types = BAR_CHART_TYPES
        for topic in spec_and_stat[category]:
            for chart in spec_and_stat[category][topic]:
                # Trend data
                chart['trend'] = get_trend(chart, all_stat, dcid)
                if 'aggregate' in chart:
                    aggregated_stat_vars = list(chart['trend'].get(
                        'series', {}).keys())
                    if aggregated_stat_vars:
                        chart['trend']['statsVars'] = aggregated_stat_vars
                    else:
                        chart['trend'] = {}
                # Bar data
                for t in chart_types:
                    chart[t] = get_bar(chart, all_stat, [dcid] +
                                       raw_page_data.get(t + 'Places', []))
                    if t == 'similar' and 'data' in chart[t]:
                        # If no data for current place, do not serve similar
                        # place data.
                        keep_chart = False
                        for d in chart[t]['data']:
                            if d['dcid'] == dcid:
                                keep_chart = True
                                break
                        if not keep_chart:
                            chart[t] = {}
                    # Update stat vars for aggregated stats
                    if 'aggregate' in chart and chart[t]:
                        chart[t]['statsVars'] = []
                        for place_data in chart[t].get('data', []):
                            stat_vars = list(place_data['data'].keys())
                            if len(stat_vars) > len(chart[t]['statsVars']):
                                chart[t]['statsVars'] = stat_vars
                            elif len(stat_vars) == 0:
                                chart[t] = {}
                if 'aggregate' in chart:
                    chart['statsVars'] = []

    # Get chart category name translations
    categories = {}
    for category in list(spec_and_stat.keys()) + list(spec_and_stat[OVERVIEW]):
        categories[category] = gettext(f'CHART_TITLE-CHART_CATEGORY-{category}')

    # Get display name for all places
    all_places = [dcid]
    for t in BAR_CHART_TYPES:
        all_places.extend(raw_page_data.get(t + 'Places', []))
    names = place_api.get_display_name('^'.join(sorted(all_places)), g.locale)

    # Pick data to highlight - only population for now
    highlight = {}
    pop_data = raw_page_data.get('latestPopulation', {}).get(dcid, {})
    if pop_data:
        population = {
            'date': pop_data['date'],
            'data': [{
                'dcid': dcid,
                'data': {
                    'Count_Person': pop_data['value']
                }
            }],
            'sources': [pop_data['metadata']['provenanceUrl']]
        }
        highlight = {gettext('CHART_TITLE-Population'): population}

    response = {
        'pageChart': spec_and_stat,
        'allChildPlaces': get_i18n_all_child_places(raw_page_data),
        'childPlacesType': raw_page_data.get('childPlacesType', ""),
        'childPlaces': raw_page_data.get('childPlaces', []),
        'parentPlaces': raw_page_data.get('parentPlaces', []),
        'similarPlaces': raw_page_data.get('similarPlaces', []),
        'nearbyPlaces': raw_page_data.get('nearbyPlaces', []),
        'categories': categories,
        'names': names,
        'highlight': highlight,
    }
    return Response(json.dumps(response), 200, mimetype='application/json')
