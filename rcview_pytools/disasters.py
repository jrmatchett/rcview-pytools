"""Tools for disasters."""

from arcgis import env as _env
from arcgis.features import Feature as _Feature,\
                            FeatureSet as _FeatureSet,\
                            FeatureLayer as _FeatureLayer
from arcgis.mapping import WebMap
from shapely.ops import unary_union as _unary_union
import re
import json
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


def initialize_dro(
    dro_id, gis,
    dro_template_id='2df64ef2bc874bdb8393255375feb894',
    sit_template_id='a1dbcdad380840249d26ccc520d1c441',
    ops_template_id='e9c20858fdb342c9a6b0e514e7c9f9f7',
    dir_template_id='9e36639d9da741138b475e05b2f79f14'
    ):
    """Initializes mapping items for a disaster relief operation.

    Arguments:
    dro_id           Disaster relief operation identifier.
    gis              RCViewGIS object.
    dro_template_id  Item ID of DRO feature file geodatabase template.
    sit_template_id  Item ID of situational awareness web map template.
    ops_template_id  Item ID of operations dashboard template.
    dir_template_id  Item ID of director's brief story map template.
    """
    # create DRO folder
    spinner = _RCSpinner('Creating folder')
    spinner.start()
    folders = gis.users.me.folders
    if not dro_id in [f['title'] for f in folders]:
        dro_folder = gis.content.create_folder(dro_id)
        if not dro_folder:
            spinner.fail('Failed to create DRO folder. Intialization aborted.')
            return
    else:
        dro_folder = [f for f in folders if f['title'] == dro_id][0]

    # copy DRO features template
    spinner.text = 'Copying features template'
    dro_id_under = re.sub('\W+', '_', dro_id)
    dro_template_item = gis.content.get(dro_template_id)
    dro_fgdb = dro_template_item.copy(title=dro_id_under + '_Features')
    move_result = dro_fgdb.move(dro_folder)
    if not move_result['success']:
        spinner.fail('Failed to move features template to DRO folder. Intialization aborted.')
        return

    # publish DRO feature service
    spinner.text = 'Publishing feature service'
    dro_features = dro_fgdb.publish()
    if not dro_features:
        spinner.fail('Failed to publish DRO feature service. Initialization aborted.')
        return

    # create situational awareness map
    spinner.text = 'Creating situational awareness map'
    sit_template_item = gis.content.get(sit_template_id)
    sit_map_item = sit_template_item.copy(title=dro_id + ' Situational Awareness Map')
    if not sit_map_item:
        spinner.fail('Failed to copy situational awareness map. Initialization aborted.')
        return
    move_result = sit_map_item.move(dro_folder)
    if not move_result['success']:
        spinner.fail('Failed to move situational awareness map to DRO folder. Intialization aborted.')
        return
    sit_map = WebMap(sit_map_item)
    add_result = sit_map.add_layer(dro_features)
    if not add_result:
        spinner.fail('Failed to add features to situational awareness map. Initialization aborted.')
        return
    update_result = sit_map.update()
    if not update_result:
        spinner.fail('Failed to update situational awareness map. Initialization aborted.')
        return

    # create operations dashboard
    spinner.text = 'Creating operations dashboard'
    ops_template_item = gis.content.get(ops_template_id)
    ops_item = ops_template_item.copy(title=dro_id + ' Operations Dashboard')
    move_result = ops_item.move(dro_folder)
    if not move_result['success']:
        spinner.fail('Failed to move operations dashboard to DRO folder. Intialization aborted.')
        return
    ops_template_data = ops_template_item.get_data()
    ops_table = dro_features.tables[0]
    ops_table_id = ops_table.properties('id')
    for widget in ops_template_data['widgets']:
        dataSource = widget['datasets'][0]['dataSource']
        dataSource['itemId'] = dro_features.itemid
        dataSource['name'] = 'operations ({})'.format(dro_features.title)
        dataSource['layerId'] = ops_table_id
    update_result = ops_item.update(data=json.dumps(ops_template_data))
    if not update_result:
        spinner.fail('Failed to update operations dashboard. Intialization aborted.')
        return

    # create director's brief
    dir_template_item = gis.content.get(dir_template_id)
    dir_item = dir_template_item.copy(title=dro_id + " Director's Brief")
    move_result = dir_item.move(dro_folder)
    if not move_result['success']:
        spinner.fail("Failed to move director's brief to DRO folder. Intialization aborted.")
        return
    dir_template_data = dir_template_item.get_data()
    dir_template_data['values']['title'] = dro_id + " Relief Operation Director's Brief"
    dir_template_data['values']['story']['entries'][0]['media']['webmap']['id'] = sit_map_item.id
    dir_template_data['values']['story']['entries'][1]['media']['webpage']['hash'] = '/' + ops_item.id
    dir_template_data['values']['story']['entries'][1]['media']['webpage']['url'] = 'https://maps.rcview.redcross.org/portal/apps/opsdashboard/index.html#/' + ops_item.id
    update_result = dir_item.update(
        item_properties={'url': 'https://maps.rcview.redcross.org/portal/apps/MapSeries/index.html?appid=' + dir_item.id},
        data=json.dumps(dir_template_data)
    )
    if not update_result:
        spinner.fail("Failed to update director's brief. Intialization aborted.")
        return

    spinner.succeed('Finished initializing DRO.')
