from __future__ import unicode_literals

import configparser
import logging
import re
import time
import pycountry
from urllib.parse import urlparse
from collections import OrderedDict
from contextlib import closing
import requests
import io
import socket
import xml.etree.ElementTree as elementtree

# Constants
PREFIX_COUNTRY = 'country-'
PREFIX_STATE = 'state-'
PREFIX_LANGUAGE = 'language-'
PREFIX_TAG = 'tag-'


logger = logging.getLogger(__name__)


class PlaylistError(Exception):
    pass


class cache(object):
    # TODO: merge this to util library (copied from mopidy-spotify)

    def __init__(self, ctl=0, ttl=3600):
        logger.debug('RadioBrowser: Start radiobrowser.cache.__init__')

        self.cache = {}
        self.ctl = ctl
        self.ttl = ttl
        self._call_count = 0

    def __call__(self, func):
        logger.debug('RadioBrowser: Start radiobrowser.cache.__call__')

        def _memoized(*args):
            logger.debug('RadioBrowser: Start radiobrowser.cache.__call__._memoized')

            now = time.time()
            try:
                value, last_update = self.cache[args]
                age = now - last_update
                if (self._call_count > self.ctl or age > self.ttl):
                    self._call_count = 0
                    raise AttributeError
                if self.ctl:
                    self._call_count += 1
                return value

            except (KeyError, AttributeError):
                value = func(*args)
                if value:
                    self.cache[args] = (value, now)
                return value

            except TypeError:
                return func(*args)

        def clear():
            logger.debug('RadioBrowser: Start radiobrowser.cache.__call__.clear')

            self.cache.clear()

        _memoized.clear = clear
        return _memoized


def parse_m3u(data):
    logger.debug('RadioBrowser: Start radiobrowser.parse_m3u')

    # Copied from mopidy.audio.playlists
    # Mopidy version expects a header but it's not always present
    for line in data.readlines():
        if not line.startswith('#') and line.strip():
            yield line.strip()


def parse_pls(data):
    logger.debug('RadioBrowser: Start radiobrowser.parse_pls')

    # Copied from mopidy.audio.playlists
    try:
        cp = configparser.RawConfigParser()
        cp.readfp(data)
    except configparser.Error:
        return

    for section in cp.sections():
        if section.lower() != 'playlist':
            continue
        for i in range(cp.getint(section, 'numberofentries')):
            try:
                # TODO: Remove this horrible hack to avoid adverts
                if cp.has_option(section, 'length%d' % (i+1)):
                    if cp.get(section, 'length%d' % (i+1)) == '-1':
                        yield cp.get(section, 'file%d' % (i+1))
                else:
                    yield cp.get(section, 'file%d' % (i+1))
            except configparser.NoOptionError:
                return


def fix_asf_uri(uri):
    logger.debug('RadioBrowser: Start radiobrowser.fix_asf_uri')

    return re.sub(r'http://(.+\?mswmext=\.asf)', r'mms://\1', uri, flags=re.IGNORECASE)


def parse_old_asx(data):
    logger.debug('RadioBrowser: Start radiobrowser.parse_old_asx')

    try:
        cp = configparser.RawConfigParser()
        cp.readfp(data)
    except configparser.Error:
        return
    for section in cp.sections():
        if section.lower() != 'reference':
            continue
        for option in cp.options(section):
            if option.lower().startswith('ref'):
                uri = cp.get(section, option).lower()
                yield fix_asf_uri(uri)


def parse_new_asx(data):
    logger.debug('RadioBrowser: Start radiobrowser.parse_new_asx')

    # Copied from mopidy.audio.playlists
    try:
        for element in elementtree.iterparse(data):
            element.tag = element.tag.lower()  # normalize
    except elementtree.ParseError:
        return

    for ref in element.findall('entry/ref[@href]'):
        yield fix_asf_uri(ref.get('href', '').strip())

    for entry in element.findall('entry[@href]'):
        yield fix_asf_uri(entry.get('href', '').strip())


def parse_asx(data):
    logger.debug('RadioBrowser: Start radiobrowser.parse_asx')

    if 'asx' in data.getvalue()[0:50].lower():
        return parse_new_asx(data)
    else:
        return parse_old_asx(data)


# This is all broken: mopidy/mopidy#225
# from gi.repository import TotemPlParser
# def totem_plparser(uri):
#     results = []
#     def entry_parsed(parser, uri, metadata):
#         results.append(uri)

#     parser = TotemPlParser.Parser.new()
#     someid = parser.connect('entry-parsed', entry_parsed)
#     res = parser.parse(uri, False)
#     parser.disconnect(someid)
#     if res != TotemPlParser.ParserResult.SUCCESS:
#         logger.debug('Failed to parse playlist')
#     return results


def find_playlist_parser(extension, content_type):
    logger.debug('RadioBrowser: Start radiobrowser.find_playlist_parser')

    extension_map = {'.asx': parse_asx,
                     '.wax': parse_asx,
                     '.m3u': parse_m3u,
                     '.pls': parse_pls}
    content_type_map = {'video/x-ms-asf': parse_asx,
                        'application/x-mpegurl': parse_m3u,
                        'audio/x-scpls': parse_pls}

    parser = extension_map.get(extension, None)
    if not parser and content_type:
        # Annoying case where the url gave us no hints so try and work it out
        # from the header's content-type instead.
        # This might turn out to be server-specific...
        parser = content_type_map.get(content_type.lower(), None)
    return parser


class RadioBrowser(object):
    # Wrapper for the RadioBrowser API.

    def __init__(self, timeout, session=None):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.__init__')
        
        hosts = []
        ips = socket.getaddrinfo('all.api.radio-browser.info', 80, 0, 0, socket.IPPROTO_TCP)
        for ip_tupel in ips:
            ip = ip_tupel[4][0]
            host_addr = socket.gethostbyaddr(ip)
            if host_addr[0] not in hosts:
                hosts.append(host_addr[0])
                
        hosts.sort()

        # old API: self._base_uri = 'http://www.radio-browser.info/webservice/json/%s'
        self._base_uri = 'http://' + hosts[0] + '/json/%s'
        self._session = session or requests.Session()
        self._timeout = timeout / 1000.0
        self._categories = []  # <type 'list'>
        self._directories = {}
        self._stations = {}

        category = {   # <type 'dict'>
            # Countries
            # _base_uri/countries
            'URL'    : self._base_uri % 'countrycodes',
            'uri'    : 'radiobrowser:category:countries',
            'element': 'outline',
            'key'    : 'countries',
            'text'   : 'Countries',
            'type'   : 'link'
        };
        self.addCategory(category);

        category = {
            # Languages
            # _base_uri/languages
            'URL': self._base_uri % 'languages',
            'uri'    : 'radiobrowser:category:languages',
            'element': 'outline',
            'text'   : 'Languages',
            'key'    : 'languages',
            'type'   : 'link'
        };
        self.addCategory(category);

        category = {
            # Tags
            # _base_uri/tags
            'URL'    : self._base_uri % 'tags',
            'uri'    : 'radiobrowser:category:tags',
            'element': 'outline',
            'text'   : 'Tags',
            'key'    : 'tags',
            'type'   : 'link'
        };
        self.addCategory(category);

        category = {
            # Top 50 clicked
            # _base_uri/stations/topclick
            'URL'    : self._base_uri % 'stations/topclick/50',
            'uri'    : 'radiobrowser:category:click',
            'element': 'outline',
            'text'   : 'Top 50 clicked',
            'key'    : 'clicks',
            'type'   : 'link'
        };
        self.addCategory(category);

        category = {
            # Top 50 voted
            # _base_uri/stations/topvote
            'URL'    : self._base_uri % 'stations/topvote/50',
            'uri'    : 'radiobrowser:category:vote',
            'element': 'outline',
            'text'   : 'Top 50 voted',
            'key'    : 'votes',
            'type'   : 'link'
        };
        self.addCategory(category);

    def reload(self):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.reload')

        self._stations.clear()
        self._radiobrowser.clear()
        self._get_playlist.clear()

    def addCategory(self, category):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.addCategory')

        self._categories.append(category);
        
        return True

    def getCategory(self, categoryId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getCategory')

        if categoryId in self._categories:
            category = self._categories[categoryId]
        else:
            logger.error('RadioBrowser: Unknown category with id=' + categoryId)
            category = None
        return category

    def getCategories(self):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getCategories')

        return self._categories

    def browseCategory(self, key):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.browseCategory (key="' + key + '")')

        # Use the key to find the category
        for category in self._categories:
            if key == category['key']:
                url = category['URL']
                results = list(self._radiobrowser(url, ''))
                return results

        return results

    def addDirectory(self, directory):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.addDirectory')

        directoryId = directory['key']
        if directoryId in self._directories:
            # The directory always exists
            return True
        
        self._directories[directoryId] = directory
        
        return True

    def getDirectory(self, directoryId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getDirectory')

        if directoryId in self._directories:
            directory = self._directories[directoryId]
        else:
            logger.error('RadioBrowser: Unknown directory with id=' + directoryId)
            directory = None
        return directory

    def getDirectories(self):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getDirectories')

        return self._directories

    def browseDirectory(self, directory):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.browseDirectory')

        url = directory['URL']
        results = list(self._radiobrowser(url, ''))

        return results

    def addStation(self, station):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.addStation')

        stationId = station['stationuuid']
        if stationId in self._stations:
            # The station always exist
            return True
        
        self._stations[stationId] = station
        
        return True

    def getStation(self, stationId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getStation')

        if stationId in self._stations:
            station = self._stations[stationId]
        else:
            station = self._station_info(stationId)
            self._stations['stationId'] = station
        return station

    def addCountry(self, country):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.addCountry')

        if '0' == country['stationcount']:
            return False

        # Add the url to browse the country
        # http://www.radio-browser.info/webservice/json/states/<country>
        alpha2 = country['name'].strip()
        # add some informations from pycountry
        try:
            isoCountry = pycountry.countries.get(alpha_2=alpha2)
            if isoCountry:
                country['a2'] = isoCountry.alpha_2
                country['a3'] = isoCountry.alpha_3
                country['name'] = isoCountry.name
                if hasattr(isoCountry, 'official_name'):
                    country['official'] = isoCountry.official_name
                else:
                    country['official'] = isoCountry.name
            else:
                country['a2'] = alpha2
                country['a3'] = '??'
                country['name'] = alpha2
                country['official'] = alpha2

        except LookupError:
            # Problem: no standard country name
            country['a2'] = alpha2
            country['a3'] = '??'
            country['name'] = alpha2
            country['official'] = alpha2
            
        country['URL'] = self._base_uri % ('states/' + country['name'] + '/')
        # country['URL'] = self._base_uri % ('states')
        country['key'] = PREFIX_COUNTRY + alpha2

        self.addDirectory(country)
        
        return True

    def getCountry(self, countryId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getCountry')

        return self.getDirectory(PREFIX_COUNTRY + countryId)

    def addState(self, state):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.addState')

        if '0' == state['stationcount']:
            return False

        # Add the url to browse the state
        # http://www.radio-browser.info/webservice/json/stations/bystate/<name>
        # http://www.radio-browser.info/webservice/json/stations/bystateexact/<name>
        name = state['name'].strip()
        identifier = name.replace(' ', '')
        if len(name) == 2 and name == state['country']:
            state['URL'] = self._base_uri % ('stations/bycountrycodeexact/' + name)
        else:
            state['URL'] = self._base_uri % ('stations/bystateexact/' + name)
        state['key'] = PREFIX_STATE + identifier

        self.addDirectory(state)
        
        return True

    def getState(self, stateId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getState')

        return self.getDirectory(PREFIX_STATE + stateId)

    def addLanguage(self, language):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.addLanguage')
        
        if '0' == language['stationcount']:
            return False

        # Add the url to browse the language
        # http://www.radio-browser.info/webservice/json/stations/bylanguage/<name>
        # http://www.radio-browser.info/webservice/json/stations/bylanguageexact/<name>
        name = language['name'].strip()
        language['URL'] = self._base_uri % ('stations/bylanguageexact/' + name)
        language['key'] = PREFIX_LANGUAGE + name.replace(' ', '')

        self.addDirectory(language)
        
        return True

    def getLanguage(self, languageId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getLanguage')

        return self.getDirectory(PREFIX_LANGUAGE + languageId)

    def addTag(self, tag):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.addTag')

        # Add the url to browse the tag
        # http://www.radio-browser.info/webservice/json/stations/bytag/<name>
        # http://www.radio-browser.info/webservice/json/stations/bytagexact/<name>
        name = tag['name'].strip()
        searchName = name.replace('#', '')
        tag['URL'] = self._base_uri % ('stations/bytagexact/' + searchName)
        tag['key'] = PREFIX_TAG + name.replace(' ', '')

        self.addDirectory(tag)
        
        return True

    def getTag(self, tagId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.getTag')

        directoryId = PREFIX_TAG + tagId
        return self.getDirectory(directoryId)

    ''' glaetten, abgleichen, abspecken, geraderichten
    def _flatten(self, data):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._flatten')

        results = []
        for item in data:
            if 'children' in item:
                results.extend(item['children'])
            else:
                results.append(item)
        return results

    def _grab_item(item):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._grab_item')

        if 'guide_id' not in item:
            return
        if map_func:
            station = map_func(item)
        elif item.get('type', 'link') == 'link':
            results.append(item)
            return
        else:
            station = item
        self._stations[station['guide_id']] = station
        results.append(station)

    def _filter_results(self, data, section_name=None, map_func=None):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._filter_results')

        results = []

        for item in data:
            if section_name is not None:
                section_key = item.get('key', '').lower()
                if section_key.startswith(section_name.lower()):
                    for child in item['children']:
                        self._grab_item(child)
            else:
                self._grab_item(item)
        return results

    def locations(self, location):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.locations')

        args = '&id=' + location
        results = self._radiobrowser('Browse.ashx', args)
        # TODO: Support filters here
        return [x for x in results if x.get('type', '') == 'link']
    '''

    def _browse(self, tag):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._browse')

        args = ''
        url = tag['URL']
        results = self._radiobrowser(url, args)
        return results

    def featured(self, guide_id):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.featured')

        return self._browse('Featured', guide_id)

    def local(self, guide_id):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.local')

        return self._browse('Local', guide_id)

    def stations(self, tag):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.stations')

        return self._browse(tag)

    def related(self, guide_id):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.related')

        return self._browse('Related', guide_id)

    def shows(self, guide_id):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.shows')

        return self._browse('Show', guide_id)

    def episodes(self, guide_id):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.episodes')

        args = '&c=pbrowse&id=' + guide_id
        results = self._radiobrowser('Tune.ashx', args)
        return self._filter_results(results, 'Topic')

    def _map_listing(self, listing):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._map_listing')

        # We've already checked 'guide_id' exists
        url_args = 'Tune.ashx?id=%s' % listing['guide_id']
        return {'text': listing.get('name', '???'),
                'guide_id': listing['guide_id'],
                'type': 'audio',
                'image': listing.get('logo', ''),
                'subtext': listing.get('slogan', ''),
                'URL': self._base_uri % url_args}

    def _station_info(self, stationId):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._station_info')

        logger.debug('RadioBrowser: Fetching info for station %s' % stationId)
        uri = self._base_uri % ('stations/byuuid/' + stationId)
        results = self._radiobrowser(uri, '')
        listings = self._filter_results(results, 'Listing', self._map_listing)
        if listings:
            return listings[0]

    def parse_stream_url(self, url):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.parse_stream_url')

        logger.debug('RadioBrowser: Extracting URIs from %s', url)
        extension = urlparse(url).path[-4:]
        if extension in ['.mp3', '.wma']:
            return [url]  # Catch these easy ones
        results = []
        playlist, content_type = self._get_playlist(url)
        if playlist:
            parser = find_playlist_parser(extension, content_type)
            if parser:
                playlist_data = io.StringIO(playlist)
                try:
                    results = [u for u in parser(playlist_data)
                               if u and u != url]
                except Exception as e:
                    logger.error('RadioBrowser playlist parsing failed %s' % e)
                if not results:
                    logger.debug('RadioBrowser: Parsing failure, '
                                 'malformed playlist: %s' % playlist)
        elif content_type:
            results = [url]
        logger.debug('RadioBrowser: Got %s', results)
        return list(OrderedDict.fromkeys(results))

    def tune(self, station):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.tune')

        logger.debug('RadioBrowser: Tuning station id %s' % station['name'])
        stream_uris = []
        stream_uris.append(station['url'])
        if not stream_uris:
            logger.error('Failed to tune station id %s' % station['guide_id'])
        return list(OrderedDict.fromkeys(stream_uris))

    def search(self, query):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser.search')

        # "Search.ashx?query=" + query + filterVal
        if not query:
            logger.debug('RadioBrowser: Empty search query')
            return []
        
        logger.debug('RadioBrowser: Searching RadioBrowser for "%s"' % query)
        url = self._base_uri % ('stations/byname/' + query)
        results = list(self._radiobrowser(url, ''))

        return results

    # @cache()   # Can't be debugged
    def _radiobrowser(self, url, args):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._radiobrowser')

        uri = url + args
        logger.debug('RadioBrowser: Request: %s', uri)
        try:
            # self._session.get(url, **kwargs)
            # self._session.post(url, data=None, json=None, **kwargs)
            #  url: URL for the new Request object.
            #  data: (optional) Dictionary, list of tuples, bytes, or file-like object to send in the body of the Request.
            #  json: (optional) json to send in the body of the Request.
            #  **kwargs: Optional arguments that request takes.
            with closing(self._session.get(uri, timeout=self._timeout)) as r:
                r.raise_for_status()
                ret = r.json() # ['body']
                return ret
        except Exception as e:
            logger.info('RadioBrowser API request for %s failed: %s' % (uri, e))
        return {}

    # @cache()   # Can't be debugged
    def _get_playlist(self, uri):
        logger.debug('RadioBrowser: Start radiobrowser.RadioBrowser._get_playlist')

        data, content_type = None, None
        try:
            # Defer downloading the body until know it's not a stream
            with closing(self._session.get(uri,
                                           timeout=self._timeout,
                                           stream=True)) as r:
                r.raise_for_status()
                content_type = r.headers.get('content-type', 'audio/mpeg')
                logger.debug('RadioBrowser: %s has content-type: %s' % (uri, content_type))
                if content_type != 'audio/mpeg':
                    data = r.content.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.info('RadioBrowser playlist request for %s failed: %s' % (uri, e))
        return (data, content_type)
