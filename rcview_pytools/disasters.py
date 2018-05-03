"""Tools for disasters."""

from arcgis import env as _env
from arcgis.features import Feature as _Feature,\
                            FeatureSet as _FeatureSet,\
                            FeatureLayer as _FeatureLayer
from shapely.ops import unary_union as _unary_union
from .geometry import *
from .gis import RCViewGIS as _RCViewGIS
from .extras import RCActivityIndicator as _RCSpinner
import warnings as _warnings
from .constants import IN_IPYTHON
if IN_IPYTHON:
    from tqdm import tqdm_notebook as _tqdm
else:
    from tqdm import tqdm as _tqdm


def districtsFromCounties(state, districts_list, districts_layer=None):
    """Create district boundaries from counties.

    Returns a FeatureSet and optionally creates or updates a feature layer of
    district boundaries based on a list of counties in each district.
    Generalized county boundaries are used to simply rendering in online maps.
    Each feature has a 'name', 'number', and 'counties' attribute.
    Arguments:
    state           Full name of the state.
    districts_list  A list of lists specifying counties within each district.
                    The lists of counties should be in order of the desired
                    district number. For example, 3 districts could be
                    defined as:

                    districts = [
                        ['Tuolumne', 'Stanislaus'],
                        ['Mariposa', 'Madera', 'Merced'],
                        ['Fresno', 'Tulare']
                    ]

                    'Mariposa', 'Madera', and 'Merced' will be named
                    'District 1'; 'Fresno' and 'Visalia' named 'District 2', and
                    so on.
    districts_layer (optional) Either an existing FeatureLayer to update with
                    the district boundaries (any existing boundaries will be
                    deleted) or a string specifying the name of a new
                    FeatureLayer to be created. You must be logged into RC View
                    (e.g., have created an RCViewGIS object) and have editting
                    permissions to the existing FeatureLayer or publishing
                    rights to create a new layer.

    """
    spinner = _RCSpinner('Creating district features')
    spinner.start()
    _warnings.simplefilter('always', UserWarning)
    counties_layer = _FeatureLayer('http://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_Counties_Generalized/FeatureServer/0')
    spinner.stop_and_persist()

    district_features = []
    for district, counties in _tqdm(enumerate(districts_list),
                                    total=len(districts_list),
                                    leave=False):
        # query counties
        query_string = "(STATE_NAME='{}') AND (NAME IN ({}))".format(
            state.title(), ','.join(["'{}'".format(c) for c in counties]))
        county_features = counties_layer.query(query_string)

        # warn user if any counties not found
        if len(county_features) != len(counties):
            warn_message = '{} not found'.format(
                [c for c in counties if c not in list(county_features.df.NAME)])
            _warnings.warn(warn_message)

        # create district feature
        district_polygon = _unary_union([p.as_shapely2() for p in county_features.df.SHAPE])
        district_feature = _Feature(
            geometry=district_polygon.as_arcgis(county_features.spatial_reference),
            attributes={
                'number': district + 1,
                'name': 'District {}'.format(district + 1),
                'counties': ', '.join(county_features.df.NAME.sort_values())
            }
        )
        district_features.append(district_feature)

    # create/update feature layer
    if isinstance(districts_layer, str):
        spinner.text = 'Creating districts layer'
        spinner.start()

        # check for existing item name
        search_results = _env.active_gis.content.search(
            districts_layer, item_type='Feature Service'
        )
        if any([t.title == districts_layer for t in search_results]):
            districts_fset = _FeatureSet(district_features)
            spinner.fail('The feature layer "{}" already exists. Either '\
                         'specify a new name or an existing layer to update.'\
                         .format(districts_layer))
        else:
            try:
                districts_item = _FeatureSet(district_features)\
                                 .df.drop('OBJECTID', axis=1)\
                                 .to_featurelayer(
                                     title=districts_layer,
                                     tags='districts'
                                 )
                districts_fset = districts_item.layers[0].query()
                spinner.succeed('Created ' + districts_layer + ' layer')
            except Exception as e:
                districts_fset = _FeatureSet(district_features)
                spinner.fail('Failed to create layer: {}'.format(e))

    elif isinstance(districts_layer, _FeatureLayer):
        spinner.text = 'Updating districts layer'
        spinner.start()
        try:
            del_results = districts_layer.delete_features(where='1=1')
            add_results = districts_layer.edit_features(adds=district_features)
            if all([a['success'] for a in add_results['addResults']]) and \
                   all([d['success'] for d in del_results['deleteResults']]):
                districts_fset = districts_layer.query()
                spinner.succeed('Updated districts layer')
            else:
                districts_fset = _FeatureSet(district_features)
                spinner.fail('Unable to update districts layer, please try again')
        except Exception as e:
            districts_fset = _FeatureSet(district_features)
            spinner.fail('Failed to update layer: {}'.format(e))

    elif districts_layer:
        spinner.warn('The districts_layer argument must be a FeatureLayer, '\
                     'string, or None; No feature layer was created or updated')
        districts_fset = _FeatureSet(district_features)
    else:
        districts_fset = _FeatureSet(district_features)
        spinner.succeed('Created district features')

    return districts_fset
