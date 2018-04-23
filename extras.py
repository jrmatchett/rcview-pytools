"""Various functions for working with GIS data."""

import os
import urllib
from mgrspy import mgrs
import numpy


def round_significant(x, p=2):
    """Round positive numeric value to significant digits.

    Arguments:
    x  A numeric value.
    p  Number of significant digits.
    """
    if x == 0.0:
        return x
    elif x < 0:
        raise ValueError('Value must be positive.')
    else:
        return numpy.around(x, -int(numpy.floor(numpy.log10(x))) + (p - 1))


def fix_fgdb_files(dir):
    """Fix ESRI file geodatabase file names.

    Sometimes a windows-style directory name is prepended to each file name.
    This function strips that directory name from each file.
    Arguments:
    dir  Directory containing the geodatabase files.
    """
    os.chdir(dir)
    for file in os.listdir():
        os.rename(file, file.split('\\')[1])


def google_maps_url(latitude, longitude):
    """Google Maps URL for a point location.

    Arguments:
    latitude   Latitude in decimal degrees.
    longitude  Longitude in decimal degrees.
    """
    return 'https://www.google.com/maps/place/{0:2.5f},{1:3.5f}/@{0:2.5f},{1:3.5f},18z'.\
        format(latitude, longitude)


def apple_maps_url(latitude, longitude, label='X'):
    """Apple Maps URL for a point location.

    Arguments:
    latitude   Latitude in decimal degrees.
    longitude  Longitude in decimal degrees.
    label      Text label for map point.
    """
    return 'http://maps.apple.com/?ll={0:2.5f},{1:3.5f}&q={2:s}'.format(
        latitude, longitude, urllib.parse.quote(label))


def usng(latitude, longitude, precision=4):
    """US National Grid value for a point location.

    Arguments:
    latitude   Latitude in decimal degrees.
    longitude  Longitude in decimal degrees.
    precision  Grid value precision.
    """
    usng = mgrs.toMgrs(latitude, longitude, precision)
    usng_fmt = []
    usng_fmt.append(usng[0:3])
    usng_fmt.append(usng[3:5])
    if precision > 0:
        gc =  usng[5:]
        idx_split = int(len(gc) / 2)
        usng_fmt.append(gc[0:idx_split])
        usng_fmt.append(gc[idx_split:])
    return ' '.join(usng_fmt)
