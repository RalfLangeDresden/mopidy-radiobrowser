from __future__ import unicode_literals

import logging
import time

from mopidy import backend, exceptions, httpclient
from mopidy.audio import scan
# TODO: Something else, using internal APIs is not cool.
from mopidy.internal import http, playlists
from mopidy.models import Ref, SearchResult

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
            for state in states:
                ret = self.backend.radiobrowser.addState(state)
                if True == ret:
                    result.append(translator.state_to_ref(state))
        elif variant == "state" and identifier:
            state = self.backend.radiobrowser.getState(identifier)
            stations = self.backend.radiobrowser.stations(state)
            for station in stations:
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


class RadioBrowserPlayback(backend.PlaybackProvider):

    def translate_uri(self, uri):
        logger.debug('RadioBrowser: Start backend.RadioBrowserPlayback.translate_uri')

        variant, identifier = translator.parse_uri(uri)
        station = self.backend.radiobrowser.getStation(identifier)
        if not station:
            return None
        stream_uris = self.backend.radiobrowser.tune(station)
        while stream_uris:
            uri = stream_uris.pop(0)
            logger.debug('RadioBrowser: Looking up URI: %s.' % uri)
            new_uri = self.unwrap_stream(uri)
            if new_uri:
                return new_uri
            else:
                logger.debug('RadioBrowser: Mopidy translate_uri failed.')
                new_uris = self.backend.radiobrowser.parse_stream_url(uri)
                if new_uris == [uri]:
                    logger.debug('Last attempt, play stream anyway: %s.' % uri)
                    return uri
                stream_uris.extend(new_uris)
        logger.debug('RadioBrowser: RadioBrowser lookup failed.')
        return None

    def unwrap_stream(self, uri):
        logger.debug('RadioBrowser: Start backend.RadioBrowserPlayback.unwrap_stream')

        unwrapped_uri, _ = _unwrap_stream(
            uri,
            timeout=self.backend._timeout,
            scanner=self.backend._scanner,
            requests_session=self.backend._session)
        return unwrapped_uri


# Shamelessly taken from mopidy.stream.actor
def _unwrap_stream(uri, timeout, scanner, requests_session):
    logger.debug('RadioBrowser: Start backend._unwrap_stream')

    """
    Get a stream URI from a playlist URI, ``uri``.

    Unwraps nested playlists until something that's not a playlist is found or
    the ``timeout`` is reached.
    """

    original_uri = uri
    seen_uris = set()
    deadline = time.time() + timeout

    while time.time() < deadline:
        if uri in seen_uris:
            logger.info('Unwrapping stream from URI (%s) failed: playlist referenced itself', uri)
            return None, None
        else:
            seen_uris.add(uri)

        logger.debug('RadioBrowser: Unwrapping stream from URI: %s', uri)

        try:
            scan_timeout = deadline - time.time()
            if scan_timeout < 0:
                logger.info('Unwrapping stream from URI (%s) failed: timed out in %sms', uri, timeout)
                return None, None
            scan_result = scanner.scan(uri, timeout=scan_timeout)
        except exceptions.ScannerError as exc:
            logger.debug('RadioBrowser: GStreamer failed scanning URI (%s): %s', uri, exc)
            scan_result = None

        if scan_result is not None:
            if scan_result.playable or (
                not scan_result.mime.startswith('text/') and
                not scan_result.mime.startswith('application/')
            ):
                logger.debug('Unwrapped potential %s stream: %s', scan_result.mime, uri)
                return uri, scan_result

        download_timeout = deadline - time.time()
        if download_timeout < 0:
            logger.info('Unwrapping stream from URI (%s) failed: timed out in %sms', uri, timeout)
            return None, None
        content = http.download(requests_session, uri, timeout=download_timeout / 1000)

        if content is None:
            logger.info('Unwrapping stream from URI (%s) failed: error downloading URI %s', original_uri, uri)
            return None, None

        uris = playlists.parse(content)
        if not uris:
            logger.debug('Failed parsing URI (%s) as playlist; found potential stream.', uri)
            return uri, None

        # TODO Test streams and return first that seems to be playable
        logger.debug('Parsed playlist (%s) and found new URI: %s', uri, uris[0])
        uri = uris[0]
