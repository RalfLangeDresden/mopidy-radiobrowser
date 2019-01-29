*******************************
***** Mopidy-RadioBrowser *****
*******************************

.. image:: https://img.shields.io/pypi/v/Mopidy-RadioBrowser.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-RadioBrowser/
    :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/dm/Mopidy-RadioBrowser.svg?style=flat
    :target: https://pypi.python.org/pypi/Mopidy-RadioBrowser/
    :alt: Number of PyPI downloads

`Mopidy <http://www.mopidy.com/>`_ extension for playing music from
`RadioBrowser <http://www.radiobrowser.info>`_. Listen to the world’s radio with 25,000 stations of music,
sports and news streaming from every continent.

Acknowledgement and thanks to Nick Steel's `TuneIn plugin <https://github.com/kingosticks/mopidy-tunein>`_ that was based on.

This product uses RadioBrowser API but is not endorsed, certified or otherwise approved in any way by RadioBrowser.


Installation
============

Install by running::

    pip install Mopidy-RadioBrowser

Some radio streams may require additional audio plugins.
These can be found in the gstreamer plugin packages for your system.
For versions of Mopidy prior to v2.0.0, these might include:
 * `gstreamer0.10-plugins-ugly`
 * `gstreamer0.10-plugins-bad`
 * `gstreamer0.10-ffmpeg`
For Mopidy v2.0.0 and above, use the gstreamer1.0-plugins-* packages instead.


Configuration
=============

You can add configuration for
Mopidy-RadioBrowser to your Mopidy configuration file but it's not required::

    [radiobrowser]
    timeout = 5000


Project resources
=================

- `Source code <https://github.com/RalfLangeDresden/mopidy-radiobrowser>`_
- `Issue tracker <https://github.com/RalfLangeDresden/mopidy-radiobrowser/issues>`_
- `Download development snapshot <https://github.com/RalfLangeDresden/mopidy-radiobrowser/tarball/master#egg=Mopidy-RadioBrowser-dev>`_


Changelog
=========

v0.1.0 (2019-01-26)
-------------------

- Initial release based in Mopidy-RuneIn.
