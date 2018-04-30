from rcview_pytools.gis import RCViewGIS
from rcview_pytools.demographics import population_housing
from pprint import pprint as pp

gis = RCViewGIS('john.matchett@redcross.org')
evacs_item = gis.content.get('57f4ec0755e6455aa2d2c16939a848d3')
evacs_layer = evacs_item.layers[0]

pops = population_housing(evacs_layer, "type = 'Test'")

#pops_enrich = population_housing(evacs_layer, "type = 'Test'", method='enrich',
#                                 enrich_id='c42dd79157064bb694702e091bef879c')
