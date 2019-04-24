"""Tools for summarizing demographic information."""

from arcgis.features import Feature as _Feature
from arcgis.features import FeatureLayer as _FeatureLayer
from arcgis.geometry.filters import intersects as _intersects
from arcgis.features.analysis import enrich_layer as _enrich_layer
from .geometry import Polygon
from shapely.validation import explain_validity
from .extras import round_significant as _round_significant
from tqdm import tqdm as _tqdm
from .extras import RCActivityIndicator as _RCSpinner


def _population_housing_enrich(areas_layer, areas_query, areas_sr, enrich_id):
    if enrich_id is None:
        raise ValueError('A feature layer item ID must be specified for the enrich_id argument.')
    # query areas
    spinner = _RCSpinner('Retrieving areas')
    spinner.start()
    objectid = areas_layer.properties.objectIdField
    areas = areas_layer.query(
        where=areas_query,
        out_fields=objectid + ',population,housing,area_sq_mi,method',
        out_sr=areas_sr)

    # add areas to enrichment layer
    spinner.text = 'Summarizing population and housing'
    gis = areas_layer.container._gis
    enrich_item = gis.content.get(enrich_id)
    enrich_layer = enrich_item.layers[0]
    del_results = enrich_layer.delete_features(where='1=1')
    enrich_features = [
        {'geometry': {'rings': f.geometry['rings'],
                      'spatialReference': areas.spatial_reference},
         'attributes': {'origin_obj': f.get_value(objectid)}}
        for f in areas.features]
    add_results = enrich_layer.edit_features(adds=enrich_features)

    # enrich with current population and housing
    enrich_fc = _enrich_layer(enrich_layer, country='US',
                              analysis_variables=['TOTPOP_CY', 'TOTHH_CY'],
                              gis=gis)
    enrich_df = enrich_fc.query().sdf.merge(areas.sdf, left_on='origin_obj', right_on=objectid)

    # update area features
    spinner.text = 'Updating areas'
    areas_updates = []
    areas_summary = {}

    for i, f in enrich_df.iterrows():
        area_sq_mi = f.SHAPE_y.area / 4046.86 / 640

        areas_updates.append(
            {'attributes': {
                    objectid: f.origin_obj,
                    'population': _round_significant(f.TOTPOP_CY),
                    'housing': _round_significant(f.TOTHH_CY),
                    'method': 'Esri enrichment',
                    'area_sq_mi': area_sq_mi
                }
            }
        )

        areas_summary[f.origin_obj] = {
            'area_sq_mi': area_sq_mi,
            'hu_enrich': f.TOTHH_CY,
            'pop_enrich': f.TOTPOP_CY,
        }

    update_results = areas_layer.edit_features(updates=areas_updates)

    for k, v in areas_summary.items():
        v['update_results'] = [x for x in update_results['updateResults'] if x['objectId'] == int(k)]

    spinner.succeed('Finished updating areas')
    return areas_summary


def population_housing(areas_layer, areas_query='population is null',
                       areas_sr=102039, method='gt50', enrich_id=None):
    """Calculates and updates population and housing units within areas.

    Returns a list of population ('pop') and housing unit ('hu') counts
    (unrounded) for each area. Item keys are the feature objectids. Updated
    population and housing values are rounded to 2 significant digits to avoid a
    false sense of precision.

    Arguments:
    areas_layer  A polygon FeatureLayer. The layer must contain attributes named
                 'population' (integer), 'housing' (integer),
                 'area_sq_mi' (double), and 'method' (string). It also must be
                 editable by the GIS user.
    areas_query  Selection query to filter features for analysis.
    areas_sr     Spatial reference for analysis. Default is USA Contiguous
                 Albers Equal Area Conic (USGS), which is appropriate for the
                 continental US. If another spatial reference is specified, its
                 measurement units must be in meters.
    method       Method used for feature layer population and housing unit
                 counts ('all', 'gt50', 'wtd', 'enrich').
    enrich_id    If using the 'enrich' method, the item ID of a RC View hosted
                 feature layer that is used to temporarily store polygons that
                 will be enriched. The layer must have a long integer attribute
                 named 'origin_obj', which is used to store the object ids of
                 the analysis areas.

    Summary method details:
    'all'     Includes all census blocks intersecting the area.
    'gt50'    Includes only census blocks where >50% of the block intersects the
              area.
    'wtd'     Weights census block values by the proportion of the block
              intersecting the area.
    'enrich'  Utilizes Esri's GeoEnrichment service, providing estimates for the
              current year. This method consumes credits and is only available
              to RC View users having analysis privileges.

    The 'all', 'gt50', and 'wtd' methods all use census block data from 2010,
    while the 'enrich' method uses the most recent population and housing unit
    projections developed by Esri.
    """
    if method == 'enrich':
        return _population_housing_enrich(areas_layer, areas_query, areas_sr,
                                          enrich_id)

    spinner = _RCSpinner('Retrieving areas')
    spinner.start()
    objectid = areas_layer.properties.objectIdField
    areas = areas_layer.query(
        where=areas_query,
        out_fields=objectid + ',population,housing,area_sq_mi,method',
        out_sr=areas_sr)

    spinner.text = 'Summarizing population and housing'
    census_layer = _FeatureLayer(url='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/12')
    areas_summary = {}
    processing_issues = False
    spinner.stop_and_persist()
    #print('  Summarizing population and housing', flush=True)
    for i, area in _tqdm(areas.sdf.iterrows(), total=len(areas)):
        processing_errors = []
        processing_warnings = []
        # query census blocks intersecting area
        area_poly = area.SHAPE.as_shapely2()
        if not area_poly.is_valid:
            processing_warnings.append(
                'Unable to convert area to valid polygon ({}).'\
                    .format(explain_validity(area_poly))
            )

        area_bbox = area_poly.envelope.as_arcgis({'wkid': areas_sr})
        area_filter = _intersects(area_bbox, sr=areas_sr)
        census_blocks = census_layer.query(
            out_fields='OBJECTID,POP100,HU100,GEOID',
            geometry_filter=area_filter, out_sr=areas_sr)

        # calculate area square miles
        area_sq_mi = area_poly.area / 4046.86 / 640

        # summarize population and housing units
        pop_all = 0
        pop_gt50 = 0
        blocks_gt50 = 0
        pop_wtd = 0
        hu_all = 0
        hu_gt50 = 0
        hu_wtd = 0

        for j, block in census_blocks.sdf.iterrows():
            block_poly = block.SHAPE.as_shapely2()
            if not block_poly.is_valid:
                processing_warnings.append(
                    'Unable to convert census block {} to valid polygon ({}).'\
                    .format(block.GEOID, explain_validity(block_poly)))
                continue

            try:
                intersection = block_poly.intersection(area_poly)
            except Exception as e:
                processing_errors.append(
                    'Unable to intersect census block {} ({}).'\
                    .format(block.GEOID, e))
                continue

            int_prop = intersection.area / block_poly.area

            pop = block.POP100
            pop_all += pop
            pop_gt50 += pop * (int_prop > 0.5)
            pop_wtd += round(pop * int_prop)

            hu = block.HU100
            hu_all += hu
            hu_gt50 += hu * (int_prop > 0.5)
            hu_wtd += round(hu * int_prop)

            blocks_gt50 += int_prop > 0.5

        areas_summary[area[objectid]] = {
            'no_blocks_all': len(census_blocks),
            'no_blocks_gt50': blocks_gt50,
            'pop_all': pop_all,
            'pop_gt50': pop_gt50,
            'pop_wtd': pop_wtd,
            'hu_all': hu_all,
            'hu_gt50': hu_gt50,
            'hu_wtd': hu_wtd,
            'area_sq_mi': area_sq_mi
        }

        if processing_errors:
            processing_issues = True
            areas_summary[area[objectid]]['ERRORS'] = processing_errors
        if processing_warnings:
            processing_issues = True
            areas_summary[area[objectid]]['WARNINGS'] = processing_warnings

        # update area values
        if method == 'all':
            area.population = _round_significant(pop_all)
            area.housing = _round_significant(hu_all)
            area.method = 'all'
        elif method == 'gt50':
            area.population = _round_significant(pop_gt50)
            area.housing = _round_significant(hu_gt50)
            area.method = 'greater than 50%'
        elif method == 'wtd':
            area.population = _round_significant(pop_wtd)
            area.housing = _round_significant(hu_wtd)
            area.method = 'weighted'
        else:
            method = None

        if method is not None:
            area.area_sq_mi = area_sq_mi
            area.drop('SHAPE', inplace=True)
            areas_summary[area[objectid]]['update_results'] = \
                areas_layer.edit_features(
                updates=[_Feature(attributes=area.to_dict())])['updateResults']

    spinner.succeed('Finished updating areas')
    if processing_issues:
        print('WARNING: There were some processing issues. See results for details.\n',
               flush=True)
    return areas_summary
