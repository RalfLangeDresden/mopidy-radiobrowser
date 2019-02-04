from __future__ import unicode_literals

import logging
import re
import urllib

from mopidy.models import Album, Artist, Ref, Track

logger = logging.getLogger(__name__)

RADIOBROWSER_API_ENCODING = 'utf-8'

RADIOBROWSER_ID_PROGRAM = 'program'
RADIOBROWSER_ID_STATION = 'station'
RADIOBROWSER_ID_GROUP = 'group'
RADIOBROWSER_ID_TOPIC = 'topic'
RADIOBROWSER_ID_CATEGORY = 'category'
RADIOBROWSER_ID_REGION = 'region'
RADIOBROWSER_ID_PODCAST = 'podcast_category'
RADIOBROWSER_ID_AFFILIATE = 'affiliate'
RADIOBROWSER_ID_STREAM = 'stream'
RADIOBROWSER_ID_UNKNOWN = 'unknown'


def unparse_uri(variant, identifier):
    logger.debug('RadioBrowser: Start translator.unparse_uri')

    return b'radiobrowser:%s:%s' % (variant, identifier)


def parse_uri(uri):
    logger.debug('RadioBrowser: Start translator.parse_uri')

    result = re.findall(r'^radiobrowser:([a-z]+)(?::(\w+))?$', uri)
    if result:
        return result[0]
    return None, None


def station_to_ref(station):
    logger.debug('RadioBrowser: Start translator.station_to_ref')

    if station['type'] != 'audio':
        logger.debug('RadioBrowser: Expecting station but got %s' % station['type'])
    guide_id = station.get('guide_id', '??')
    uri = unparse_uri('station', guide_id)
    name = station.get('text', station['URL'])
    # TODO: Should the name include 'now playing' for all stations?
    if get_id_type(guide_id) == RADIOBROWSER_ID_TOPIC:
        name = name + ' [%s]' % station.get('subtext', '??')
    return Ref.track(uri=uri, name=name)


def station_to_track(station):
    logger.debug('RadioBrowser: Start translator.station_to_track')

    ref = station_to_ref(station)
    return Track(uri=ref.uri,
                 name=station.get('subtext', ref.name),
                 album=Album(name=ref.name,
                             uri=ref.uri,
                             images=[station.get('image')]),
                 artists=[Artist(name=ref.name, uri=ref.uri)])


def show_to_ref(show):
    logger.debug('RadioBrowser: Start translator.show_to_ref')

    if show['item'] != 'show':
        logger.debug('RadioBrowser: Expecting show but got %s' % show['item'])
    uri = unparse_uri('episodes', show.get('guide_id', '??'))
    name = show.get('text', show['URL'])
    return Ref.directory(uri=uri, name=name)


def category_to_ref(category):
    logger.debug('RadioBrowser: Start translator.category_to_ref')

    uri = unparse_uri('category', category['key'])
    return Ref.directory(uri=uri, name=category['text'])


def section_to_ref(section, identifier=''):
    logger.debug('RadioBrowser: Start translator.section_to_ref')

    if section.get('type', 'link') == 'audio':
        return station_to_ref(section)
    guide_id = section.get('guide_id', '??')
    if get_id_type(guide_id) == RADIOBROWSER_ID_REGION or identifier == 'local':
        uri = unparse_uri('location', guide_id)
    else:
        uri = unparse_uri('section', guide_id)
    return Ref.directory(uri=uri, name=section['text'])


def get_id_type(guide_id):
    logger.debug('RadioBrowser: Start translator.get_id_type')

    return {'p': RADIOBROWSER_ID_PROGRAM,
            's': RADIOBROWSER_ID_STATION,
            'g': RADIOBROWSER_ID_GROUP,
            't': RADIOBROWSER_ID_TOPIC,
            'c': RADIOBROWSER_ID_CATEGORY,
            'r': RADIOBROWSER_ID_REGION,
            'f': RADIOBROWSER_ID_PODCAST,
            'a': RADIOBROWSER_ID_AFFILIATE,
            'e': RADIOBROWSER_ID_STREAM}.get(guide_id[0], RADIOBROWSER_ID_UNKNOWN)


def mopidy_to_radiobrowser_query(mopidy_query):
    logger.debug('RadioBrowser: Start translator.mopidy_to_radiobrowser_query')

    radiobrowser_query = []
    for (field, values) in mopidy_query.iteritems():
        if not hasattr(values, '__iter__'):
            values = [values]
        for value in values:
            if field == 'any':
                radiobrowser_query.append(value)
    query = ' '.join(radiobrowser_query).encode(RADIOBROWSER_API_ENCODING)
    return urllib.pathname2url(query)
