"""Tools for disasters."""

from arcgis.features import Feature as _Feature,\
                            FeatureSet as _FeatureSet,\
                            FeatureLayer as _FeatureLayer
from shapely.ops import unary_union as _unary_union
from tqdm import tqdm as _tqdm
from .geometry import *
import warnings as _warnings


def districtsFromCounties(state, districts_list):
    """Create district boundaries from counties.

    Returns a FeatureSet of district boundaries based on a list of counties
    in each district. Generalized county boundaries are used to simply
    rendering in online maps. Each feature has a 'name', 'number', and
    'counties' attribute.
    attribute.
    Arguments:
    state           Full name of the state.
    districts_list  A list of lists specifying counties within each district.
                    The lists of counties should be in order of the desired
                    district number. For example, 3 districts would be
                    defined as:

                    districts = [
                        ['Tuolumne', 'Stanislaus'],
                        ['Mariposa', 'Madera', 'Merced'],
                        ['Fresno', 'Visalia']
                    ]

                    'Mariposa', 'Madera', and 'Merced' will be named
                    'District 1'; 'Fresno' and 'Visalia' named 'District 2', and
                    so on.

    """
    counties_layer = _FeatureLayer('http://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_Counties_Generalized/FeatureServer/0')
    district_features = []
    for district, counties in _tqdm(enumerate(districts_list),
                                    total=len(districts_list)):
        # query counties
        query_string = "(STATE_NAME='{}') AND (NAME IN ({}))".format(
            state.title(), ','.join(["'{}'".format(c) for c in counties]))
        county_features = counties_layer.query(query_string)

        # warn user if any counties not found
        if len(county_features) != len(counties):
            warn_message = '{} not found'.format(
                [c for c in counties if c not in list(county_features.df.NAME)])
            _warnings.simplefilter('always', UserWarning)
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

    return _FeatureSet(district_features)
