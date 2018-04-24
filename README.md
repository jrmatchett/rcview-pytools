# Python Tools for RC View Mapping

This package contains tools for working with the American Red Cross's RC View Mapping platform, which is a web-based geographic information system (GIS) utilizing Esri's [Portal for ArcGIS](https://enterprise.arcgis.com/en/portal) platform.

## Installation

* Install the ChromeDriver application following these [instructions](https://sites.google.com/a/chromium.org/chromedriver/getting-started).

* Activate your desired [python virtual environment](https://docs.python.org/3/tutorial/venv.html).

* Install the ArcGIS API for Python following these [instructions](https://developers.arcgis.com/python/guide/install-and-set-up).

* Install the `selenium`, `shapely`, `mgrs`, and `tqdm` packages using your preferred package manager ([pip](https://pypi.org/project/pip/) or [conda](https://conda.io/docs/)).

* Install `rcview_pytools` by downloading the source code and running `python setup.py install` from the package's root directory.

## Getting Started

Programmatically interacting with feature layers, maps, and other data hosted on RC View typically begins with creating a `RCViewGIS` object. For example:

    from rcview_pytools.gis import RCViewGIS
    gis = RCViewGIS('your_email', 'your_password')

You must have access permission to the RC View system, which is granted to Red Cross staff and volunteers in Disaster Cycle Services positions. The login email and password are the same as your Red Cross single-sign-on credentials.

For additional guidance on interacting with an ArcGIS portal, see the [ArcGIS Python API Developer's Guide](https://developers.arcgis.com/python/guide).

## Modules

* `gis` provides the `RCViewGIS` class, which is a subclass of the `arcgis` `GIS` class connected specifically to the RC View mapping portal.

* `geometry` extends `arcgis` and `shapely` polygon classes. As of version 1.4, the `arcgis` package does not properly handle polygons with interior holes unless Esri's proprietary `arcpy` package is available. This module provides an `as_shapely2` method for the `arcgis` `Polygon` class, correctly handling interior holes. It also adds an `as_arcgis` method for `shapely` `Polygon` and `MultiPolygon` classes, so those objects can be converted back to `arcgis` polygons.

* `demographics` contains functions for summarizing demographic information, such as determining the population and housing units within areas impacted by a disaster.

* `extras` contains a variety of functions for working with spatial data, such as generating Google Maps URLs and US National Grid coordinates for points.
