# Copyright 2015 Adafruit Industries.
# Author: Tony DiCola
# License: GNU GPLv2, see LICENSE.txt
import os
import shutil
import subprocess
import tempfile
import time

from .alsa_config import parse_hw_device

class OMXPlayer:

    def __init__(self, config):
        """Create an instance of a video player that runs omxplayer in the
        background.
        """
        self._process = None
        self._temp_directory = None
        self._load_config(config)

    def __del__(self):
        if self._temp_directory:
            shutil.rmtree(self._temp_directory)

    def _get_temp_directory(self):
        if not self._temp_directory:
            self._temp_directory = tempfile.mkdtemp()
        return self._temp_directory

    def _load_config(self, config):
        self._extensions = config.get('omxplayer', 'extensions') \
                                 .translate(str.maketrans('', '', ' \t\r\n.')) \
                                 .split(',')
        self._extra_args = config.get('omxplayer', 'extra_args').split()
        self._sound = config.get('omxplayer', 'sound').lower()
        assert self._sound in ('hdmi', 'local', 'both', 'alsa'), 'Unknown omxplayer sound configuration value: {0} Expected hdmi, local, both or alsa.'.format(self._sound)
        self._alsa_hw_device = parse_hw_device(config.get('alsa', 'hw_device'))
        if self._alsa_hw_device != None and self._sound == 'alsa':
            self._sound = 'alsa:hw:{},{}'.format(self._alsa_hw_device[0], self._alsa_hw_device[1])
        self._show_titles = config.getboolean('omxplayer', 'show_titles')
        if self._show_titles:
            title_duration = config.getint('omxplayer', 'title_duration')
            if title_duration >= 0:
                self._subtitle_end = self._ass_timestamp(title_duration)
            else:
                self._subtitle_end = '99:59:59.00'

    def supported_extensions(self):
        """Return list of supported file extensions."""
        return self._extensions

    def play(self, movie, loop=None, vol=0):
        """Play the provided movie file, optionally looping it repeatedly."""
        self.stop(0)  # Up to 3 second delay to let the old player stop.
        # Assemble list of arguments.
        args = ['omxplayer']
        args.extend(['-o', self._sound])  # Add sound arguments.
        args.extend(self._extra_args)     # Add extra arguments from config.
        if vol != 0:
            args.extend(['--vol', str(vol)])
        if loop is None:
            loop = movie.repeats
        if loop <= -1:
            args.append('--loop')  # Add loop parameter if necessary.
        if self._show_titles and movie.title:
            ass_path = os.path.join(self._get_temp_directory(), 'video_looper.ass')
            with open(ass_path, 'w') as f:
                f.write(self._ass_document(movie.title))
            args.extend(['--subtitles', ass_path])
        args.append(movie.target)       # Add movie file path.
        # Run omxplayer process and direct standard output to /dev/null.
        # Establish input pipe for commands
        self._process = subprocess.Popen(args,
                                         stdout=open(os.devnull, 'wb'),
                                         stdin=subprocess.PIPE,
                                         close_fds=True)

    def pause(self):
        self.sendKey("p")
    
    def sendKey(self, key: str):
        if self.is_playing():
            self._process.stdin.write(key.encode())
            self._process.stdin.flush()

    def _ass_document(self, title):
        return (
            '[Script Info]\n'
            'ScriptType: v4.00+\n'
            'PlayResX: 640\n'
            'PlayResY: 480\n'
            '\n'
            '[V4+ Styles]\n'
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
            'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, '
            'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
            'Style: RickTVTitle,Arial,28,&H00FFFFFF,&H000000FF,&H90000000,&H90000000,'
            '0,0,0,0,100,100,0,0,1,2,1,7,20,20,20,1\n'
            '\n'
            '[Events]\n'
            'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
            'Dialogue: 0,0:00:00.00,{end},RickTVTitle,,0,0,0,,{title}\n'
        ).format(end=self._subtitle_end, title=self._escape_ass_text(title))

    def _ass_timestamp(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return '{:d}:{:02d}:{:02d}.00'.format(h, m, s)

    def _escape_ass_text(self, value):
        return str(value).replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}').replace('\n', '\\N')

    def is_playing(self):
        """Return true if the video player is running, false otherwise."""
        if self._process is None:
            return False
        self._process.poll()
        return self._process.returncode is None

    def stop(self, block_timeout_sec=0):
        """Stop the video player.  block_timeout_sec is how many seconds to
        block waiting for the player to stop before moving on.
        """
        # Stop the player if it's running.
        if self._process is not None and self._process.returncode is None:
            # There are a couple processes used by omxplayer, so kill both
            # with a pkill command.
            subprocess.call(['pkill', '-9', 'omxplayer'])
        # If a blocking timeout was specified, wait up to that amount of time
        # for the process to stop.
        start = time.time()
        while self._process is not None and self._process.returncode is None:
            if (time.time() - start) >= block_timeout_sec:
                break
            time.sleep(0)
        # Let the process be garbage collected.
        self._process = None

    @staticmethod
    def can_loop_count():
        return False


def create_player(config, **kwargs):
    """Create new video player based on omxplayer."""
    return OMXPlayer(config)
