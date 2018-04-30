"""Tools for working with RC View Mapping.

Written by J. R. Matchett (john.matchett@redcross.org)
"""

import platform
from halo import Halo


spinner = Halo(
    text='Processing',
    spinner = 'line' if platform.system() == 'Windows' else 'circleHalves',
    color='white',
    interval=100)
