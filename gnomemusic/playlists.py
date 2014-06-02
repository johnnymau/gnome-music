from gi.repository import TotemPlParser, Grl, GLib, Gio, GObject
from gi.repository import Tracker
from gnomemusic.grilo import grilo
from gnomemusic.query import Query

import os

from gnomemusic import log
import logging
logger = logging.getLogger(__name__)

try:
    tracker = Tracker.SparqlConnection.get(None)
except Exception as e:
    from sys import exit
    logger.error("Cannot connect to tracker, error '%s'\Exiting" % str(e))
    exit(1)


class Playlists(GObject.GObject):
    __gsignals__ = {
        'playlist-created': (GObject.SIGNAL_RUN_FIRST, None, (Grl.Media,)),
        'playlist-deleted': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        'song-added-to-playlist': (GObject.SIGNAL_RUN_FIRST, None, (str, Grl.Media)),
        'song-removed-from-playlist': (GObject.SIGNAL_RUN_FIRST, None, (str, str)),
    }
    instance = None

    @classmethod
    def get_default(self):
        if self.instance:
            return self.instance
        else:
            self.instance = Playlists()
        return self.instance

    @log
    def __init__(self):
        GObject.GObject.__init__(self)
        self.playlist_dir = os.path.join(GLib.get_user_data_dir(),
                                         'gnome-music',
                                         'playlists')

    @log
    def create_playlist(self, name):
        def get_callback(source, param, item, count, data, error):
            if item:
                self.emit('playlist-created', item)

        def query_callback(conn, res, data):
            cursor = conn.query_finish(res)
            if not cursor or not cursor.next():
                return
            playlist_id = cursor.get_integer(0)
            grilo.get_playlist_with_id(playlist_id, get_callback)

        def update_callback(conn, res, data):
            playlist_urn = conn.update_blank_finish(res)[0][0]['playlist']
            tracker.query_async(
                Query.get_playlist_with_urn(playlist_urn),
                None, query_callback, None
            )

        tracker.update_blank_async(
            Query.create_playlist(name), GLib.PRIORITY_DEFAULT,
            None, update_callback, None
        )

    @log
    def get_playlists(self):
        playlist_files = [pl_file for pl_file in os.listdir(self.playlist_dir)
                          if os.path.isfile(os.path.join(self.playlist_dir,
                                                         pl_file))]
        playlist_names = []
        for playlist_file in playlist_files:
            name, ext = os.path.splitext(playlist_file)
            if ext == '.pls':
                playlist_names.append(name)
        return playlist_names

    @log
    def add_to_playlist(self, playlist_name, uris):
        parser = TotemPlParser.Parser()
        playlist = TotemPlParser.Playlist()
        pl_file = Gio.file_new_for_path(self.get_path_to_playlist(playlist_name))

        def parse_callback(parser, uri, metadata, data):
            _iter = playlist.append()
            playlist.set_value(_iter, TotemPlParser.PARSER_FIELD_URI, uri)

        def end_callback(parser, uri, data):
            for uri in uris:
                _iter = playlist.append()
                playlist.set_value(_iter, TotemPlParser.PARSER_FIELD_URI, uri)

                def get_callback(source, param, item):
                    self.emit('song-added-to-playlist', playlist_name, item)
                grilo.get_media_from_uri(uri, get_callback)

            parser.save(playlist, pl_file, playlist_name, TotemPlParser.ParserType.PLS)

        parser.connect('entry-parsed', parse_callback, playlist)
        parser.connect('playlist-ended', end_callback, playlist)
        parser.parse_async(
            GLib.filename_to_uri(self.get_path_to_playlist(playlist_name), None),
            False, None, None, None
        )

    @log
    def remove_from_playlist(self, playlist_name, uris):
        parser = TotemPlParser.Parser()
        playlist = TotemPlParser.Playlist()
        pl_file = Gio.file_new_for_path(self.get_path_to_playlist(playlist_name))

        def parse_callback(parser, uri, metadata, data):
            if uri in uris:
                uris.remove(uri)
                self.emit('song-removed-from-playlist', playlist_name, uri)
            else:
                _iter = playlist.append()
                playlist.set_value(_iter, TotemPlParser.PARSER_FIELD_URI, uri)

        def end_callback(parser, uri, data):
            if playlist.size() == 0:
                playlist.append()
            parser.save(playlist, pl_file, playlist_name, TotemPlParser.ParserType.PLS)

        parser.connect('entry-parsed', parse_callback, playlist)
        parser.connect('playlist-ended', end_callback, playlist)
        parser.parse_async(
            GLib.filename_to_uri(self.get_path_to_playlist(playlist_name), None),
            False, None, None, None
        )

    @log
    def delete_playlist(self, playlist_name):
        playlist_file = self.get_path_to_playlist(playlist_name)
        if os.path.isfile(playlist_file):
            os.remove(playlist_file)
            self.emit('playlist-deleted', playlist_name)

    @log
    def get_path_to_playlist(self, playlist_name):
        return os.path.join(self.playlist_dir, "%s.pls" % playlist_name)

    @log
    def parse_playlist(self, playlist_name, callback):
        parser = TotemPlParser.Parser()
        parser.connect('entry-parsed', self._on_entry_parsed, callback)
        parser.parse_async(
            GLib.filename_to_uri(self.get_path_to_playlist(playlist_name), None),
            False, None, None, None
        )

    @log
    def _on_entry_parsed(self, parser, uri, metadata, data=None):
        filename = GLib.filename_from_uri(uri)[0]
        if filename and not os.path.isfile(filename):
            return

        grilo.get_media_from_uri(uri, data)
