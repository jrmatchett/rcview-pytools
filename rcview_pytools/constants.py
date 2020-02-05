"""Constants"""

import platform

OS_WINDOWS = platform.system() == 'Windows'

# ArcPy availablity
try:
    import arcpy as _arcpy  # pylint: disable=import-error
    HAS_ARCPY = True
except ModuleNotFoundError:
    HAS_ARCPY = False

# Running in IPython or Jupyter Notebook
try:
    get_ipython
    IN_IPYTHON = True
except NameError:
    IN_IPYTHON = False
