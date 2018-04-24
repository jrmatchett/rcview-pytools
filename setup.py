"""A setuptools based setup module.
See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='rcview_pytools',
    version='0.1.0',
    description='Python tools for RC View mapping',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='J. R. Matchett',
    author_email='john.matchett@redcross.org',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[
        'arcgis>=1.4',
        'mgrspy',
        'numpy',
        'selenium',
        'shapely',
        'six',
        'tqdm'
    ],
    python_requires='~=3.5',
    project_urls={
        'Bug Reports': 'https://github.com/jrmatchett/rcview-pytools/issues',
        'Source': 'https://github.com/jrmatchett/rcview-pytools',
    }
)
