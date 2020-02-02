from __future__ import unicode_literals

import logging
from mopidy import backend
from mopidy_radiobrowser import translator


logger = logging.getLogger(__name__)


class RadioBrowserPlayback(backend.PlaybackProvider):

    def translate_uri(self, uri):
        logger.debug('RadioBrowser: Start backend.RadioBrowserPlayback.translate_uri')

        identifier = translator.parse_uri(uri)
        if identifier[0] == 'station':
            station = self.backend.radiobrowser.getStation(identifier[1])
        else:
            station = self.backend.radiobrowser.getStation(identifier[0])
        if not station:
            return None
        stream_uris = self.backend.radiobrowser.tune(station)
        while stream_uris:
            uri = stream_uris.pop(0)
            logger.debug('RadioBrowser: Looking up URI: %s.' % uri)
            if uri:
                return uri
        logger.debug('RadioBrowser: RadioBrowser lookup failed.')
        return None
