"""Constants"""

# ArcPy availablity
try:
    import arcpy as _arcpy
    HAS_ARCPY = True
except:
    HAS_ARCPY = False
