from __future__ import unicode_literals

import re
from setuptools import setup, find_packages


def get_version(filename):
    content = open(filename).read()
    metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", content))
    return metadata['version']


setup(
    name='Mopidy-RadioBrowser',
    version=get_version('mopidy_radiobrowser/__init__.py'),
    url='https://github.com/RalfLangeDresden/mopidy-radiobrowser',
    license='Apache License, Version 2.0',
    author='Ralf Lange',
    author_email='ralf.lange@longsoft.de',
    description='Mopidy extension for selecting and playing internet radio stations from https://www.radio-browser.info.',
    long_description=open('README.rst').read(),
    packages=find_packages(exclude=['tests', 'tests.*']),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        'setuptools',
        'Mopidy >= 1.1',
        'Pykka >= 1.1',
        'requests >= 2.0.0',
    ],
    test_suite='nose.collector',
    tests_require=[
        'nose',
        'mock >= 1.0',
    ],
    entry_points={
        'mopidy.ext': [
            'radiobrowser = mopidy_radiobrowser:Extension',
        ],
    },
    classifiers=[
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Multimedia :: Sound/Audio :: Players',
    ],
)
