"""Constants"""

import platform as _platform

OS_WINDOWS = _platform.system() == 'Windows'

# ArcPy availablity
try:
    import arcpy as _arcpy
    HAS_ARCPY = True
except:
    HAS_ARCPY = False
