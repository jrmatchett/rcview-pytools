"""Geometry class modifications and additions.

This module refines methods and properties in arcgis and Shapely geometry
classes. See help for the Polygon, ShapelyPolygon, and ShapelyMultiPolygon
classes for details.
"""

from arcgis.geometry import Polygon
from arcgis.geometry import Geometry
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import MultiPoint as ShapelyMultiPoint
from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import MultiLineString as ShapelyMultiLineString
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.geometry import MultiPolygon as ShapelyMultiPolygon
from shapely.geometry.polygon import LinearRing as _ShapelyLinearRing
from shapely.validation import explain_validity as _explain_validity
import warnings as _warnings
from .constants import HAS_ARCPY


def _custom_formatwarning(msg, *args, **kwargs):
    # include only exception category and message
    return '{}: {}\n'.format(args[0].__name__, msg)

_warnings.formatwarning = _custom_formatwarning


def _as_shapely2(self, fix_self_intersections=True, warn_invalid=True):
    """Return a Shapely [Mulit]Polygon.

    Alternative to arcgis as_shapely which handles polygons with holes and fixes
    self-intersecting rings (as_shapely may not work properly when the python
    environment does not have ArcPy available).

    Arguments:
    fix_self_intersections  Fix self-intersecting polygons.
    warn_invalid            Issue a warning if polygon is invalid.
    """
    # extract exterior and interior rings
    exterior_rings, interior_rings = [], []
    for ring in map(_ShapelyLinearRing, self.rings):
        interior_rings.append(ring) if ring.is_ccw else exterior_rings.append(ring)

    # create polygons for each exterior ring
    polys = []
    for exterior_ring in exterior_rings:
        exterior_poly = ShapelyPolygon(exterior_ring)
        if len(interior_rings) > 0:
            # determine which interior rings are within the exterior ring
            within_rings, outside_rings = [], []
            for interior_ring in interior_rings:
                within_rings.append(interior_ring)\
                    if ShapelyPolygon(interior_ring).intersects(exterior_poly)\
                    else outside_rings.append(interior_ring)
            polys.append(ShapelyPolygon(exterior_ring, within_rings))
            interior_rings = outside_rings
        else:
            polys.append(exterior_poly)

    if len(polys) == 1:
        poly_shp = ShapelyPolygon(polys[0])
    else:
        poly_shp = ShapelyMultiPolygon(polys)

    # check validity and fix any self-intersecting rings
    if not poly_shp.is_valid:
        invalid_reason = _explain_validity(poly_shp)
        invalid_message = 'Polygon is not valid ({})'.format(invalid_reason)
        if 'Self-intersection' in invalid_reason and fix_self_intersections:
            # fix with buffer trick
            poly_shp = poly_shp.buffer(0.0)
            invalid_message += '; self-intersections were automatically fixed'
        if warn_invalid:
            invalid_message += '.'
            _warnings.simplefilter('always', UserWarning)
            _warnings.warn(invalid_message)

    return poly_shp

Polygon.as_shapely2 = _as_shapely2


def _as_shapely(self):
    """Return a Shapely [Multi]Polygon.

    Overrides the arcgis method, returning a properly-constructed Shapely
    geometry using the as_shapely2 method. Self-intersecting rings are not
    automatically fixed.
    """
    return self.as_shapely2(False, True)

if not HAS_ARCPY:
    Polygon.as_shapely = property(_as_shapely)


def _as_arcgis(self, spatial_reference):
    """Return an arcgis Geometry.

    Arguments:
    spatial_reference  A spatial reference integer code or definition
                       dictionary, for example {'wkid': 3857}
    """

    if isinstance(spatial_reference, int):
        spatial_reference = {'wkid': spatial_reference}

    if isinstance(self, ShapelyPoint) or \
       isinstance(self, ShapelyMultiPoint) or \
       isinstance(self, ShapelyLineString) or \
       isinstance(self, ShapelyMultiLineString):
        geom = Geometry(self.__geo_interface__)
        geom['spatialReference'] = spatial_reference

    elif isinstance(self, ShapelyPolygon):
        linear_rings = [self.exterior]
        linear_rings += self.interiors
        rings = [list(r.__geo_interface__['coordinates']) for r in linear_rings]
        geom = Geometry({'rings': rings, 'spatialReference': spatial_reference})

    elif isinstance(self, ShapelyMultiPolygon):
        linear_rings = []
        for poly in self.geoms:
            linear_rings += [poly.exterior]
            linear_rings += poly.interiors
        rings = [list(r.__geo_interface__['coordinates']) for r in linear_rings]
        geom = Geometry({'rings': rings, 'spatialReference': spatial_reference})

    return geom

ShapelyPoint.as_arcgis = _as_arcgis
ShapelyMultiPoint.as_arcgis = _as_arcgis
ShapelyLineString.as_arcgis = _as_arcgis
ShapelyMultiLineString.as_arcgis = _as_arcgis
ShapelyPolygon.as_arcgis = _as_arcgis
ShapelyMultiPolygon.as_arcgis = _as_arcgis
