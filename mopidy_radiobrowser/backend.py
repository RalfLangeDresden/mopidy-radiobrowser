from __future__ import unicode_literals

import logging
from mopidy import backend, httpclient
from mopidy.audio import scan
from mopidy.models import Ref, SearchResult, Image
import pykka
import requests
import mopidy_radiobrowser
from mopidy_radiobrowser import translator, radiobrowser


logger = logging.getLogger(__name__)


def get_requests_session(proxy_config, user_agent):
    logger.debug('RadioBrowser: Start backend.get_requests_session')

    proxy = httpclient.format_proxy(proxy_config)
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({'http': proxy, 'https': proxy})
    session.headers.update({'user-agent': full_user_agent})

    return session


class RadioBrowserBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes = ['radiobrowser']

    def __init__(self, config, audio):
        logger.debug('RadioBrowser: Start backend.RadioBrowserBackend.__init__')

        super(RadioBrowserBackend, self).__init__()

        self._session = get_requests_session(
            proxy_config = config['proxy'],
            user_agent = '%s/%s' % (
                mopidy_radiobrowser.Extension.dist_name,
                mopidy_radiobrowser.__version__))

        self._timeout = config['radiobrowser']['timeout']

        self._scanner = scan.Scanner(
            timeout = config['radiobrowser']['timeout'],
            proxy_config = config['proxy'])
        self.radiobrowser = radiobrowser.RadioBrowser(config['radiobrowser']['timeout'], self._session)
        self.library = RadioBrowserLibrary(self)
        self.playback = RadioBrowserPlayback(audio=audio, backend=self)


class RadioBrowserLibrary(backend.LibraryProvider):
    root_directory = Ref.directory(uri='radiobrowser:root', name='RadioBrowser')

    def __init__(self, backend):
        logger.debug('RadioBrowser: Start backend.RadioBrowserLibrary.__init__')

        super(RadioBrowserLibrary, self).__init__(backend)

    def browse(self, uri):
        logger.debug('RadioBrowser: Start backend.RadioBrowserLibrary.browse')

        result = []
        variant, identifier = translator.parse_uri(uri)
        logger.debug('RadioBrowser: Browsing %s' % uri)
        if variant == 'root':
            # root list: all categies
            for category in self.backend.radiobrowser.getCategories():
                result.append(translator.category_to_ref(category))
        elif "category" == variant:
            if "countries" == identifier:
                countries = self.backend.radiobrowser.browseCategory(identifier)
                for country in countries:
                    ret = self.backend.radiobrowser.addCountry(country)
                    if True == ret:
                        result.append(translator.country_to_ref(country))
            elif "languages" == identifier:
                languages = self.backend.radiobrowser.browseCategory(identifier)
                for language in languages:
                    ret = self.backend.radiobrowser.addLanguage(language)
                    if True == ret:
                        result.append(translator.language_to_ref(language))
            elif "tags" == identifier:
                tags = self.backend.radiobrowser.browseCategory(identifier)
                for tag in tags:
                    ret = self.backend.radiobrowser.addTag(tag)
                    if True == ret:
                        result.append(translator.tag_to_ref(tag))
            elif "clicks" == identifier:
                stations = self.backend.radiobrowser.browseCategory(identifier)
                for station in stations:
                    ret = self.backend.radiobrowser.addStation(station)
                    if True == ret:
                        result.append(translator.station_to_ref(station))
            elif "votes" == identifier:
                stations = self.backend.radiobrowser.browseCategory(identifier)
                for station in stations:
                    ret = self.backend.radiobrowser.addStation(station)
                    if True == ret:
                        result.append(translator.station_to_ref(station))
            else:
                logger.debug('RadioBrowser: Unknown URI: %s', uri)
        elif variant == "tag" and identifier:
            tag = self.backend.radiobrowser.getTag(identifier)
            stations = self.backend.radiobrowser.stations(tag)
            for station in stations:
                self.backend.radiobrowser.addStation(station)
                result.append(translator.station_to_ref(station))
        elif variant == "language" and identifier:
            language = self.backend.radiobrowser.getLanguage(identifier)
            stations = self.backend.radiobrowser.stations(language)
            for station in stations:
                self.backend.radiobrowser.addStation(station)
                result.append(translator.station_to_ref(station))
        elif variant == "country" and identifier:
            country = self.backend.radiobrowser.getCountry(identifier)
            states = self.backend.radiobrowser.browseDirectory(country)
            emptyState = {
                'name': country['a2'],
                'country': country['a2'],
                'stationcount' : 1
                }
            states.append(emptyState)
            for state in states:
                ret = self.backend.radiobrowser.addState(state)
                if True == ret:
                    result.append(translator.state_to_ref(state))
        elif variant == "state" and identifier:
            state = self.backend.radiobrowser.getState(identifier)
            stations = self.backend.radiobrowser.stations(state)
            for station in stations:
                if (state['name'] == state['country']):
                    if ('' == station['state']):
                        continue
                self.backend.radiobrowser.addStation(station)
                result.append(translator.station_to_ref(station))
        else:
            logger.debug('RadioBrowser: Unknown URI: %s', uri)

        return result

    def refresh(self, uri=None):
        logger.debug('RadioBrowser: Start backend.RadioBrowserLibrary.refresh')

        self.backend.radiobrowser.reload()

    def lookup(self, uri):
        logger.debug('RadioBrowser: Start backend.RadioBrowserLibrary.lookup')

        variant, identifier = translator.parse_uri(uri)
        if variant != 'station':
            return []
        station = self.backend.radiobrowser.getStation(identifier)
        if not station:
            return []

        track = translator.station_to_track(station)
        return [track]

    def search(self, query=None, uris=None, exact=False):
        logger.debug('RadioBrowser: Start backend.RadioBrowserLibrary.search')

        if query is None or not query:
            return
        radiobrowser_query = translator.mopidy_to_radiobrowser_query(query)
        tracks = []
        stations = self.backend.radiobrowser.search(radiobrowser_query)
        for station in stations:
            self.backend.radiobrowser.addStation(station)
            track = translator.station_to_track(station)
            tracks.append(track)
        return SearchResult(uri='radiobrowser:search', tracks=tracks)
    
    def get_images(self, uris):
        logger.debug('RadioBrowser: Start backend.RadioBrowserLibrary.get_images')

        result = {}
        for uri in uris:
            variant, identifier = translator.parse_uri(uri)
            if variant != 'station':
                continue

            station = self.backend.radiobrowser.getStation(identifier)
            if not station:
                continue
            
            result[uri] = [Image(uri=station.get('favicon'))]
        return result


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
