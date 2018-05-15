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


def _districts_description(districts_df, type):
    desc = 'This layer contains incident districts. Following are the '\
            '{} within each district:<ul>'.format(type)
    for i, d in districts_df.sort_values('name').iterrows():
        desc += '<li>Distict {}: {}</li>'.format(d.number, d.units)
    desc += '</ul>'
    return {'description': desc}


def define_districts(type, districts_list, state=None, districts_layer=None):
    """Create incident district boundaries.

    Returns a FeatureSet and optionally creates or updates a feature layer of
    district boundaries based on a list of counties, chapters, or regions in
    each district. Generalized boundaries are used to simply rendering in online
    maps. Each feature has a 'name', 'number', and 'units' attribute.
    Arguments:
    type            Type of units used to define districts: 'counties' uses
                    state counties, 'chapters' uses Red Cross chapters, and
                    'regions' uses Red Cross regions.
    districts_list  A list of lists specifying units within each district.
                    The lists of units should be in order of the desired
                    district number. For example, 3 county-based districts
                    could be defined as:

                    districts = [
                        ['Tuolumne', 'Stanislaus'],
                        ['Mariposa', 'Madera', 'Merced'],
                        ['Fresno', 'Tulare']
                    ]

                    'Tuolumne' and 'Stanislaus' will be named 'District 1';
                    'Mariposa', 'Madera', and 'Merced' will be 'District 2';
                    and so on.

                    For chapter- and region-based districts, the units
                    are the ECODE and RCODE values, respectively. See
                    https://maps.rcview.redcross.org/portal/home/item.html?id=ff62f2b66a204c6ab09b35e10e7c7821
                    for chapter and region boundaries.

    state           Full name of the state if creating county-based districts.
    districts_layer (optional) Either an existing FeatureLayer to update with
                    the district boundaries (any existing boundaries will be
                    deleted) or a string specifying the name of a new layer
                    item to be created. You must be logged into RC View
                    (e.g., have created an RCViewGIS object) and have editting
                    permissions to the existing FeatureLayer or publishing
                    rights to create a new layer. Newly created layers with be
                    located in the users 'Home' folder.

    """
    spinner = _RCSpinner('Creating district features')
    spinner.start()
    _warnings.simplefilter('always', UserWarning)

    if type == 'counties':
        if not state:
            raise ValueError("The 'state' argument must be specified when using counties.")
        units_layer = _FeatureLayer('http://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_Counties_Generalized/FeatureServer/0')
        unit_attribute = 'NAME'
    elif type == 'chapters':
        units_layer = _FeatureLayer('https://services.arcgis.com/pGfbNJoYypmNq86F/arcgis/rest/services/2015_ARC_Chapter_Boundaries/FeatureServer/0')
        unit_attribute = 'ECODE'
    elif type == 'regions':
         units_layer = _FeatureLayer('https://services.arcgis.com/pGfbNJoYypmNq86F/arcgis/rest/services/2015_ARC_Chapter_Boundaries/FeatureServer/0')
         unit_attribute = 'RCODE'
    else:
         raise ValueError("The 'type' argument must be one of 'counties', 'chapters' or 'regions'.")

    spinner.stop_and_persist()

    # create features
    district_features = []
    for district, units in _tqdm(enumerate(districts_list),
                                    total=len(districts_list),
                                    leave=False):
        # query units
        units_string = ','.join(["'{}'".format(c) for c in units])
        if type == 'counties':
            query_string = "(STATE_NAME='{}') AND (NAME IN ({}))".format(
                state.title(), units_string)
        else:
            query_string = "{} IN ({})".format(unit_attribute, units_string)

        units_features = units_layer.query(query_string)

        # warn user if any units not found
        unique_units = list(units_features.df[unit_attribute].unique())
        unique_units.sort()
        if len(unique_units) != len(units):
            warn_message = '{} not found'.format(
                [c for c in units if c not in unique_units])
            _warnings.warn(warn_message)

        # create district feature
        district_polygon = _unary_union([p.as_shapely2() for p in units_features.df.SHAPE])
        district_feature = _Feature(
            geometry=district_polygon.as_arcgis(units_features.spatial_reference),
            attributes={
                'number': district + 1,
                'name': 'District {}'.format(district + 1),
                'units': ', '.join(unique_units)
            }
        )
        district_features.append(district_feature)

    if isinstance(districts_layer, str):
        # create new feature layer
        spinner.text = 'Creating districts layer (be patient)'
        spinner.start()

        # check for existing item name and skip creation
        search_results = _env.active_gis.content.search(
            districts_layer, item_type='Feature Service'
        )
        if any([t.title == districts_layer for t in search_results]):
            districts_fset = _FeatureSet(district_features)
            spinner.fail('A feature layer named "{}" already exists. Either '\
                         'specify a new name or an existing layer to update.'\
                         .format(districts_layer))
        else:
            # create layer
            try:
                districts_item = _FeatureSet(district_features)\
                                 .df.drop('OBJECTID', axis=1)\
                                 .to_featurelayer(
                                     title=districts_layer,
                                     tags='districts'
                                 )
                # change layer name
                item_layer = districts_item.layers[0]
                r = item_layer.manager.update_definition({'name': 'districts'})

                # update description
                districts_fset = item_layer.query()
                r = districts_item.update(_districts_description(districts_fset.df, type))
                spinner.succeed('Created ' + districts_layer + ' layer')
            except Exception as e:
                districts_fset = _FeatureSet(district_features)
                spinner.fail('Failed to create layer: {}'.format(e))

    elif isinstance(districts_layer, _FeatureLayer):
        # update existing feature layer
        spinner.text = 'Updating districts layer'
        spinner.start()
        try:
            del_results = districts_layer.delete_features(where='1=1')
            add_results = districts_layer.edit_features(adds=district_features)
            if all([a['success'] for a in add_results['addResults']]) and \
                   all([d['success'] for d in del_results['deleteResults']]):
                # update description
                districts_fset = districts_layer.query()
                districts_item = _env.active_gis.content.get(
                    districts_layer.properties.serviceItemId)
                r = districts_item.update(_districts_description(districts_fset.df, type))
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
