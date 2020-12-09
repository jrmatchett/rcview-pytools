"""Tools for disasters."""

from arcgis import env
from arcgis.features import Feature, FeatureSet, FeatureLayer
from arcgis.mapping import WebMap
from shapely.ops import unary_union
from shapely.geometry import box as ShapelyBox
import re
import json
from .geometry import *
from .gis import RCViewGIS
from .extras import RCActivityIndicator as RCSpinner
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from urllib.parse import urlencode
import warnings
from .constants import IN_IPYTHON
if IN_IPYTHON:
    from tqdm import tqdm_notebook as tqdm
else:
    from tqdm import tqdm


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
    spinner = RCSpinner('Creating district features')
    spinner.start()
    warnings.simplefilter('always', UserWarning)

    if type == 'counties':
        if not state:
            raise ValueError("The 'state' argument must be specified when using counties.")
        units_layer = FeatureLayer('http://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_Counties_Generalized/FeatureServer/0')
        unit_attribute = 'NAME'
    elif type == 'chapters':
        units_layer = FeatureLayer('https://services.arcgis.com/pGfbNJoYypmNq86F/arcgis/rest/services/2015_ARC_Chapter_Boundaries/FeatureServer/0')
        unit_attribute = 'ECODE'
    elif type == 'regions':
         units_layer = FeatureLayer('https://services.arcgis.com/pGfbNJoYypmNq86F/arcgis/rest/services/2015_ARC_Chapter_Boundaries/FeatureServer/0')
         unit_attribute = 'RCODE'
    else:
         raise ValueError("The 'type' argument must be one of 'counties', 'chapters' or 'regions'.")

    spinner.stop_and_persist()

    # create features
    district_features = []
    for district, units in tqdm(enumerate(districts_list),
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
        unique_units = list(units_features.sdf[unit_attribute].unique())
        unique_units.sort()
        if len(unique_units) != len(units):
            warn_message = '{} not found'.format(
                [c for c in units if c not in unique_units])
            warnings.warn(warn_message)

        # create district feature
        district_polygon = unary_union([p.as_shapely2() for p in units_features.sdf.SHAPE])
        district_feature = dict(
            # pylint: disable=maybe-no-member
            geometry=dict(district_polygon.as_arcgis(units_features.spatial_reference)),
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
        # pylint: disable=maybe-no-member
        search_results = env.active_gis.content.search(
            districts_layer, item_type='Feature Service'
        )
        if any([t.title == districts_layer for t in search_results]):
            districts_fset = FeatureSet(district_features)
            spinner.fail('A feature layer named "{}" already exists. Either '\
                         'specify a new name or an existing layer to update.'\
                         .format(districts_layer))
        else:
            # create layer
            try:
                districts_item = FeatureSet(district_features)\
                                 .sdf.spatial.to_featurelayer(
                                     title=districts_layer,
                                     tags='districts'
                                 )
                # change layer name
                item_layer = districts_item.layers[0]
                r = item_layer.manager.update_definition({'name': 'districts'})

                # update description
                districts_fset = item_layer.query()
                r = districts_item.update(_districts_description(districts_fset.sdf, type))
                spinner.succeed('Created ' + districts_layer + ' layer')
            except Exception as e:
                districts_fset = FeatureSet(district_features)
                spinner.fail('Failed to create layer: {}'.format(e))

    elif isinstance(districts_layer, FeatureLayer):
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
                # pylint: disable=maybe-no-member
                districts_item = env.active_gis.content.get(
                    districts_layer.properties.serviceItemId)
                r = districts_item.update(_districts_description(districts_fset.sdf, type))
                spinner.succeed('Updated districts layer')
            else:
                districts_fset = FeatureSet(district_features)
                spinner.fail('Unable to update districts layer, please try again')
        except Exception as e:
            districts_fset = FeatureSet(district_features)
            spinner.fail('Failed to update layer: {}'.format(e))

    elif districts_layer:
        spinner.warn('The districts_layer argument must be a FeatureLayer, '\
                     'string, or None; No feature layer was created or updated')
        districts_fset = FeatureSet(district_features)

    else:
        districts_fset = FeatureSet(district_features)
        spinner.succeed('Created district features')

    return districts_fset


def initialize_dro(
    dro_id, gis,
    dro_template_id='19ecca09a38b445aa43841e7db4d0515',
    sit_map_template_id='55f5ec920b614e188074d53af564feca',
    sit_app_template_id='7f28edde49474819beaec5c61ee3f496',
    ops_template_id='e9c20858fdb342c9a6b0e514e7c9f9f7',
    dir_template_id='9e36639d9da741138b475e05b2f79f14'
    ):
    """Initializes mapping items for a disaster relief operation.

    Arguments:
    dro_id           Disaster relief operation identifier formatted as 'DR 000-00'.
    gis              RCViewGIS object.
    dro_template_id  Item ID of DRO feature file geodatabase template.
    sit_map_template_id  Item ID of situational awareness web map template.
    sit_app_template_id  Item ID of situational awareness web app template.
    ops_template_id  Item ID of operations dashboard template.
    dir_template_id  Item ID of director's brief story map template.
    """
    if (not gis._password) or (gis._password == 'none'):
        raise RuntimeError('The RCViewGIS object must include the account password. Please set it by using gis._password = "YOUR_PASSWORD".')

    dro_tags = {'tags': [dro_id, dro_id.replace(' ', ''), dro_id.replace('DR ', '')]}

    # create DRO folder
    spinner = RCSpinner('Creating folder')
    spinner.start()
    folders = gis.users.me.folders
    if not dro_id in [f['title'] for f in folders]:
        dro_folder = gis.content.create_folder(dro_id)
        if not dro_folder:
            spinner.fail('Failed to create DRO folder. Initialization aborted.')
            return
    else:
        dro_folder = [f for f in folders if f['title'] == dro_id][0]

    # copy DRO features template
    spinner.text = 'Copying features template'
    dro_id_under = re.sub(r'\W+', '_', dro_id)
    dro_template_item = gis.content.get(dro_template_id)
    dro_fgdb = dro_template_item.copy(title=dro_id_under + '_Features')
    move_result = dro_fgdb.move(dro_folder)
    if not move_result['success']:
        spinner.fail('Failed to move features template to DRO folder. Initialization aborted.')
        return

    # publish DRO feature service
    spinner.text = 'Publishing feature service'
    dro_features = dro_fgdb.publish()
    if not dro_features:
        spinner.fail('Failed to publish DRO feature service. Initialization aborted.')
        return
    _ = dro_features.update(dro_tags)

    # TODO: Add a few blank time periods to the operations table

    # create situational awareness map
    spinner.text = 'Creating situational awareness map'
    sit_map_template_item = gis.content.get(sit_map_template_id)
    sit_map_item = sit_map_template_item.copy(title=dro_id + ' Situational Awareness Map')
    if not sit_map_item:
        spinner.fail('Failed to copy situational awareness map. Initialization aborted.')
        return
    move_result = sit_map_item.move(dro_folder)
    if not move_result['success']:
        spinner.fail('Failed to move situational awareness map to DRO folder. Initialization aborted.')
        return
    _ = sit_map_item.update(dro_tags)
    # sit_map = WebMap(sit_map_item)
    # add_result = sit_map.add_layer(dro_features)
    # if not add_result:
    #     spinner.fail('Failed to add features to situational awareness map. Initialization aborted.')
    #     return
    # update_result = sit_map.update()
    # if not update_result:
    #     spinner.fail('Failed to update situational awareness map. Initialization aborted.')
    #     return

    # create situational awareness app
    # NOTE: Web AppBuilder apps don't initialize correctly when copied from another app,
    # so have to create new app via web interface.
    spinner.text = 'Creating situational awareness app'
    wab_params = {
        'title': dro_id + ' Situational Awareness App',
        'tags': dro_id,
        'summary': f'Situational awareness web map application for {dro_id}.',
        'folder': dro_folder['id'],
        'appType': 'HTML'
    }
    wab_url = f"{gis.url}/apps/webappbuilder/index.html?{urlencode(wab_params)}".replace('+', '%20')

    driver = webdriver.Chrome()
    driver.get(wab_url)

    delay = 60
    try:
        using_redcross_element = WebDriverWait(driver, delay).\
            until(EC.presence_of_element_located((By.XPATH, '//*[@id="enterprisePanel"]/div/div')))
    except TimeoutException:
        spinner.fail('Failed to log into RC View. Initialization aborted.')
        driver.quit()
        return

    using_redcross_element.click()

    try:
        username_element = WebDriverWait(driver, delay).\
            until(EC.presence_of_element_located((By.XPATH, '/html/body/main/div[4]/div/div/div/div/div/div/div/div[1]/div/div/div/div[4]/input')))
        password_element = WebDriverWait(driver, delay).\
            until(EC.presence_of_element_located((By.XPATH, '/html/body/main/div[4]/div/div/div/div/div/div/div/div[1]/div/div/div/div[5]/input')))
        signin_element = WebDriverWait(driver, delay).\
            until(EC.presence_of_element_located((By.XPATH, '/html/body/main/div[4]/div/div/div/div/div/div/div/div[1]/div/div/div/div[6]/button')))
    except TimeoutException:
        spinner.fail('Failed to log into RC View. Initialization aborted.')
        driver.quit()
        return

    username_element.send_keys(gis._username)
    password_element.send_keys(gis._password)
    signin_element.click()
    # wait until WAB editor loaded
    try:
        _ = WebDriverWait(driver, delay).\
            until(EC.presence_of_element_located((By.LINK_TEXT, 'Launch')))
    except TimeoutException:
        spinner.fail('Failed to create situational awareness app. Initialization aborted.')
        driver.quit()
        return

    sit_app_url = driver.current_url.replace('webappbuilder', 'webappviewer')
    driver.close()

    sit_app_template_item = gis.content.get(sit_app_template_id)
    sit_app_item = gis.content.get(sit_app_url.split('?id=')[1])
    sit_app_template_data = sit_app_template_item.get_data()
    sit_app_template_data['title'] = dro_id + ' Situational Awareness'
    sit_app_template_data['map']['itemId'] = sit_map_item.itemid
    sit_app_template_data['logo'] = sit_app_template_data['logo'].replace('${itemId}', sit_app_template_id)
    update_result = sit_app_item.update(data=json.dumps(sit_app_template_data))
    if not update_result:
        spinner.fail('Failed to update situational awareness app. Initialization aborted.')
        return
    _ = sit_app_item.update(dro_tags)

    # create operations dashboard
    spinner.text = 'Creating operations dashboard'
    ops_template_item = gis.content.get(ops_template_id)
    ops_item = ops_template_item.copy(title=dro_id + ' Operations Dashboard')
    move_result = ops_item.move(dro_folder)
    if not move_result['success']:
        spinner.fail('Failed to move operations dashboard to DRO folder. Initialization aborted.')
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
        spinner.fail('Failed to update operations dashboard. Initialization aborted.')
        return
    _ = ops_item.update(dro_tags)

    # create director's brief
    dir_template_item = gis.content.get(dir_template_id)
    dir_item = dir_template_item.copy(title=dro_id + " Director's Brief")
    move_result = dir_item.move(dro_folder)
    if not move_result['success']:
        spinner.fail("Failed to move director's brief to DRO folder. Initialization aborted.")
        return
    dir_template_data = dir_template_item.get_data()
    dir_template_data['values']['title'] = dro_id + " Relief Operation Director's Brief"
    dir_template_data['values']['story']['entries'][0]['media']['webpage']['url'] = sit_app_url
    dir_template_data['values']['story']['entries'][1]['media']['webpage']['hash'] = '/' + ops_item.id
    dir_template_data['values']['story']['entries'][1]['media']['webpage']['url'] = 'https://maps.rcview.redcross.org/portal/apps/opsdashboard/index.html#/' + ops_item.id
    update_result = dir_item.update(
        item_properties={'url': 'https://maps.rcview.redcross.org/portal/apps/MapSeries/index.html?appid=' + dir_item.id},
        data=json.dumps(dir_template_data)
    )
    if not update_result:
        spinner.fail("Failed to update director's brief. Initialization aborted.")
        return
    _ = dir_item.update(dro_tags)

    spinner.succeed('Finished initializing DRO.')


def _cell_polygon(x_cell, y_cell, cell_size, x_min, y_min, spatial_ref):
    x_org = x_min - cell_size / 2
    y_org = y_min - cell_size / 2
    box = ShapelyBox(
        minx=x_cell * cell_size + x_org,
        miny=y_cell * cell_size + y_org,
        maxx=x_cell * cell_size + x_org + cell_size,
        maxy=y_cell * cell_size + y_org + cell_size
    )
    return box.as_arcgis(spatial_ref)


def grid_dda(dda, dda_grid_layer, grid_size=250, verbose=True):
    """Grid-based summary of detailed damage assessments.

    Totals number of DDA points, by damage classification, within a fishnet
    grid.
    Arguments:
    dda             DDA Collect FeatureSet.
    dda_grid_layer  DDA summary grid polygon feature layer. The layer should
                    contain integer fields named x_cell, y_cell,
                    major_destroyed, destroyed, major, minor, affected, nvd,
                    inaccessible, and all.
    grid_size       Grid cell width. Default is 250 meters, assuming the
                    DDA FeatureSet has a spatial reference system in meters.
    verbose         Prints progress indicator.

    Returns:  A dictionary with the following:
              'grid' -- data frame of the DDA summary grid
              'deletes' -- dictionary of delete results to the grid layer
              'adds' -- dictionary of add results to the grid layer
    """
    if verbose:
        spinner = RCSpinner('Creating grid summary')
        spinner.start()
    # count DDAs within grid
    dda_sdf = dda.sdf
    dda_extent = dda_sdf.spatial.full_extent
    dda_sdf['x_cell'] = dda_sdf.SHAPE.apply(lambda s: int((s.x - dda_extent[0]) / grid_size + 0.5))
    dda_sdf['y_cell'] = dda_sdf.SHAPE.apply(lambda s: int((s.y - dda_extent[1]) / grid_size + 0.5))
    dda_grid = dda_sdf.pivot_table(values='objectid', index=['x_cell', 'y_cell'],
                                   columns='classification', aggfunc='count', fill_value=0).reset_index()
    dda_grid.columns = [x.lower() for x in dda_grid.columns]
    dda_grid['major_destroyed'] = dda_grid.major + dda_grid.destroyed
    dda_grid['all_dda'] = dda_grid.major_destroyed + dda_grid.minor + dda_grid.affected + dda_grid.nvd
    dda_grid['shape__area'] = grid_size * grid_size
    dda_grid['shape__length'] = grid_size * 4
    # create and add DDA grid features
    dda_grid['SHAPE'] = dda_grid.apply(lambda x: _cell_polygon(x.x_cell, x.y_cell, grid_size,
                                       dda_extent[0], dda_extent[1], dda.spatial_reference), axis=1)
    if verbose:
        spinner.text = 'Updating grid layer'
    results_delete = dda_grid_layer.delete_features(where='1=1')
    results_add = dda_grid_layer.edit_features(adds=dda_grid.spatial.to_featureset())
    if verbose:
        spinner.succeed('Grid summary complete')
    return {'grid': dda_grid, 'deletes': results_delete, 'adds': results_add}
