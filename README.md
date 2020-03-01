# Python Tools for RC View Mapping

This package contains tools for working with the American Red Cross's RC View Mapping platform, which is a web-based geographic information system (GIS) utilizing Esri's [Portal for ArcGIS](https://enterprise.arcgis.com/en/portal) platform.

## Installation

* Install the ChromeDriver application following these [instructions](https://sites.google.com/a/chromium.org/chromedriver/getting-started).

* Activate your desired [python virtual environment](https://docs.python.org/3/tutorial/venv.html).

* Install `rcview_pytools` by downloading the source code and running `python setup.py install` from the package's root directory.

* Setup an application client in RC View:
  * Log into RC View, click the `Map Portal` tile, click `Content`, and click `My Content` tab.
  * Click `Add Item` and choose `An application`.
  * Select `Application` for the type, set the title to `Python Authentication`, set a tag to `Python`, and click `Add Item`.
  * Click the `Settings` tab, scroll down to `Application Settings`, and click `Registered Info`.
  * The `App ID` is the `client_id` value you'll need to use for creating an `RCViewGIS` object.

## Getting Started

Programmatically interacting with feature layers, maps, and other data hosted on RC View typically begins with creating a `RCViewGIS` object. For example:

    from rcview_pytools.gis import RCViewGIS
    gis = RCViewGIS('your_email', 'your_password', 'your_client_id')

For additional guidance on interacting with an ArcGIS portal, see the [ArcGIS Python API Developer's Guide](https://developers.arcgis.com/python/guide).

## Modules

* `gis` provides the `RCViewGIS` class, which is a subclass of the `arcgis` `GIS` class connected specifically to the RC View mapping portal.

* `geometry` extends `arcgis` and `shapely` polygon classes. This module provides an `as_shapely2` method for the `arcgis` `Polygon` class, correctly handling interior holes. It also adds an `as_arcgis` method for `shapely` `Polygon` and `MultiPolygon` classes, so those objects can be converted back to `arcgis` polygons. Also includes a `to_SpatialDataFrame` method for converting a `geopandas` `GeoDataFrame` to an `arcgis` spatially-enabled dataframe.

* `demographics` contains functions for summarizing demographic information, such as determining the population and housing units within areas impacted by a disaster.

* `disasters` contains functions for creating DRO districts, initializing DRO maps, and creating gridded summaries of detailed damage assessments.

* `extras` contains a variety of functions for working with spatial data, such as generating Google Maps URLs and US National Grid coordinates for points.
