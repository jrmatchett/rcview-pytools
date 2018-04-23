"""Tools for summarizing demographic information."""

from arcgis.features import Feature
from arcgis.features import FeatureLayer
from arcgis.geometry.filters import intersects
from .geometry import Polygon
from .extras import round_significant
from pprint import pprint as pp
from tqdm import tqdm


def population_housing(areas_layer, areas_query='population is null',
                       areas_sr=102039, method='gt50'):
    """Calculates and updates population and housing units within areas.

    Returns a list of population ('pop') and housing unit ('hu') counts
    (unrounded) for each area. Item keys are the feature objectids. The list
    includes counts using each of the 3 summary methods (see below), while
    the area layer values are updated using the technique specified for the
    method argument. Updated population and housing values are rounded to 2
    significant digits to avoid a false sense of precision.

    Arguments:
    areas_layer  A polygon FeatureLayer. The layer must contain attributes named
                 'objectid', 'population' (integer), 'housing' (integer),
                 'area_sq_mi' (double), and 'method' (string). It also must be
                 editable by the GIS user.
    areas_query  Selection query to filter features for analysis.
    areas_sr     Spatial reference for analysis. Default is USA Contiguous
                 Albers Equal Area Conic (USGS), which is appropriate for the
                 continental US. If another spatial reference is specified, its
                 measurement units must be in meters.
    method       Method used for feature layer population and housing unit
                 counts ('all', 'gt50', or 'wtd').

    Summary method details:
    'all'   Includes all census blocks intersecting the area.
    'gt50'  Includes only census blocks where >50% of area intersects the area.
    'wtd'   Weights census block values by the proportion of the block
            intersecting the area.
    """
    print('\nSummarizing areas...', flush=True)
    areas = areas_layer.query(
        where=areas_query,
        out_fields='objectid,population,housing,area_sq_mi,method',
        out_sr=areas_sr)
    census_layer = FeatureLayer(url='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/12')

    areas_summary = {}
    processing_issues = False
    for i, area in tqdm(areas.df.iterrows(), total=len(areas)):
        processing_errors = []
        processing_warnings = []
        # query census blocks intersecting area
        area_poly = area.SHAPE.as_shapely2()
        if not area_poly.is_valid:
            processing_warnings.append(
                'Unable to convert area to valid polygon ({}).'\
                    .format(explain_validity(area_poly))
            )

        area_filter = intersects(area.SHAPE, sr=areas_sr)
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

        for j, block in census_blocks.df.iterrows():
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

        areas_summary[area.objectid] = {
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
            areas_summary[area.objectid]['ERRORS'] = processing_errors
        if processing_warnings:
            processing_issues = True
            areas_summary[area.objectid]['WARNINGS'] = processing_warnings

        # update area values
        if method == 'all':
            area.population = round_significant(pop_all)
            area.housing = round_significant(hu_all)
            area.method = 'all'
        elif method == 'gt50':
            area.population = round_significant(pop_gt50)
            area.housing = round_significant(hu_gt50)
            area.method = 'greater than 50%'
        elif method == 'wtd':
            area.population = round_significant(pop_wtd)
            area.housing = round_significant(hu_wtd)
            area.method = 'weighted'
        else:
            method = None

        if method is not None:
            area.area_sq_mi = area_sq_mi
            area.drop('SHAPE', inplace=True)
            areas_summary[area.objectid]['update_results'] = \
                areas_layer.edit_features(
                updates=[Feature(attributes=area.to_dict())])['updateResults']

    print('\nFinished.\n', flush=True)
    if processing_issues:
        print('WARNING: There were some processing issues. See results for details.\n',
               flush=True)
    return areas_summary
