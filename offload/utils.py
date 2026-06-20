#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
script_name.py
Description of script_name.py.
"""

import logging
import shutil
import math
import time
import json
import subprocess
import hashlib
import string
import random
import os
import xxhash
from PIL import Image
from PIL import UnidentifiedImageError
from PIL.ExifTags import TAGS
from pathlib import Path
from pathlib import PosixPath
from datetime import datetime
from collections import namedtuple
from offload import APP_DATA_PATH, LOGS_PATH, REPORTS_PATH
import psutil
import sys

# Define EXCLUDE_FILES and other constants if they are not already defined
EXCLUDE_FILES = ['Thumbs.db', '.DS_Store']

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except Exception:
        # Not bundled, base_path is project root (one level up from 'offload' where utils.py is)
        base_path = Path(__file__).resolve().parent.parent
    return base_path / relative_path

class Preset:
    @staticmethod
    def structure(preset):
        presets = {'taken_date': '{date.year}/{date:%Y-%m-%d}',
                   # The datetime needs to be formatted here to prevent KeyError
                   'offload_date': f'{datetime.now().strftime("%Y")}/{datetime.now().strftime("%Y-%m-%d")}',
                   'year_month': '{date.year}/{date:%m}',
                   'year': '{date.year}',
                   'flat': ''}
        return presets.get(preset)

    @staticmethod
    def filename(preset):
        presets = {'original': None,
                   'camera_make': 'Make',
                   'camera_model': 'Model'}
        return presets.get(preset)

    @staticmethod
    def prefix(preset):
        presets = {'None': None,
                   '': None,
                   'empty': None,
                   'taken_date': '{date:%y%m%d}',
                   'taken_date_time': '{date:%y%m%d_%H%M%S}',
                   # The datetime needs to be formatted here to prevent KeyError
                   'offload_date': f'{datetime.now().strftime("%y%m%d")}'}
        return presets.get(preset)


class FileList:
    def __init__(self, path, exclude=None, allowed_extensions=None):
        """A list of files as File objects

        Args:
            path: path to the root directory to scan for files
            exclude: list of filenames to ignore when adding files to list
            allowed_extensions: list of lowercase file extensions to include (e.g., ['.jpg', '.mp4']). If None or empty, all files are included.
        """
        self._path = Path(path)
        self.files = []
        self.allowed_extensions = allowed_extensions

        self.exclude = []
        if isinstance(exclude, list):
            self.exclude.extend(exclude)
        elif isinstance(exclude, str):
            self.exclude.append(exclude)

        # Update file list
        self.update()

    def sort(self):
        """Sort list by modification date"""
        self.files.sort(key=lambda f: f.mtime)

    def update(self):
        """Get list of files in a folder and its subfolders"""
        # Get all files in path
        all_files = [x for x in self._path.rglob("*") if x.is_file() and x.name not in self.exclude]
        
        # Filter by allowed_extensions if provided
        if self.allowed_extensions:
            filtered_files = []
            for f in all_files:
                if f.suffix.lower() in self.allowed_extensions:
                    filtered_files.append(f)
            logging.debug(f"Files after extension filtering: {filtered_files}")
            files_to_process = filtered_files
        else:
            files_to_process = all_files
            logging.debug(f"No extension filtering. All files in source: {files_to_process}")

        # Create a dict with all files that aren't in exclude list
        self.files = [] # Clear previous files
        for n, f in enumerate(files_to_process):
            logging.debug(f.name)
            self.files.append(File(f))
            logging.debug(f"Added {f.name} to file list ({n + 1}/{len(files_to_process)})")

    @property
    def size(self) -> int:
        """Return total file size of all files in list"""
        return sum([x.size for x in self.files])

    @property
    def hsize(self) -> str:
        return convert_size(self.size)

    @property
    def count(self) -> int:
        """Return the number of files in list"""
        return len(self.files)

    @property
    def avg_file_size(self) -> int:
        """Return average file size of files in list"""
        if self.count == 0:
            return 0
        return int(self.size / self.count)


class File:
    def __init__(self, path, prefix=None, incremental_padding=3):
        """File object.

        Args:
            path: path to an existing file or a placeholder path for new file
            prefix: custom prefix or based on a template
            incremental_padding: the amount of zero's too put before the incremental number
        """
        self._path = Path(path)
        # Discard object if given path is a directory
        if self._path.is_dir():
            logging.error(f'{path} is a folder')
            exit()
        # Setup attributes
        self._checksum = ''
        self._size = 0
        self._prefix = prefix
        self._name = self._path.stem
        self.inc = 0
        self.inc_pad = incremental_padding
        self.ext = self._path.suffix.strip('.')
        self.relative_path = None

    @property
    def is_file(self):
        """Check if the file exists"""
        exists = self.path.is_file()
        # if exists:
        #     logging.debug(f'{self.path} exists')
        # else:
        #     logging.debug(f'{self.path} does not exist')
        return exists

    @property
    def filename(self):
        """Update the current filename with prefix and padding"""
        fname = self.name
        if self.prefix:
            fname = f"{self.prefix}_{fname}"
        if self.inc >= 1:
            inc = pad_number(self.inc, padding=self.inc_pad)
            fname = f"{fname}_{inc}"

        fname = f"{fname}.{self.ext}"

        return fname

    @property
    def name(self):
        """Return the name of the file without prefix, incremental or extension"""
        return self._name

    @name.setter
    def name(self, name, validate=True):
        """Change the name property

        Args:
            name: the new name of the file. Presets available:
                - camera_model
                - camera_make
            validate: validate filename to make sure it works on all filesystems"""

        new_name = str(name)

        # Set name from exif data based on a preset
        preset = Preset()
        if preset.filename(name):
            logging.debug(self.exifdata)
            new_name = self.exifdata.get(preset.filename(name), "unknown").lower()

        # Validate file name and remove/replace illegal characters
        if validate:
            new_name = validate_string(new_name)

        self._name = new_name

    @property
    def path(self):
        """Return the path property"""
        return self._path.parent / self.filename

    @path.setter
    def path(self, path):
        """Change the path"""
        path = Path(path)
        if path.is_file():
            self._path = path.parent / self.filename
        else:
            self._path = path / self.filename

    @property
    def checksum(self):
        """Return the xxhash checksum of the file

        Returns: file checksum
        """
        if self.is_file:
            self._checksum = file_checksum(self.path)
        return self._checksum

    @property
    def size(self) -> int:
        """Return the size of the file if it exists"""
        if self.is_file:
            self._size = self.path.stat().st_size
        return self._size

    @property
    def mdate(self):
        """Modification date"""
        return datetime.fromtimestamp(self.mtime)

    @property
    def mtime(self):
        """Modification time of the file"""
        if self.is_file:
            if self.path.stat().st_mtime:
                return self.path.stat().st_mtime

        elif self._path.is_file():
            if self._path.stat().st_mtime:
                return self._path.stat().st_mtime

        return datetime.timestamp(datetime.now())

    @property
    def ctime(self):
        """Modification time of the file"""
        if self.is_file:
            if self.path.stat().st_ctime:
                return self.path.stat().st_ctime

        elif self._path.is_file():
            if self._path.stat().st_ctime:
                return self._path.stat().st_ctime

        return datetime.timestamp(datetime.now())

    @property
    def exifdata(self) -> dict:
        """Get the file exifdata using Pillow for images, or exiftool as a fallback."""
        if self.is_file:
            # Try Pillow first for images
            data = exifdata(self.path) # This function already calls is_image_file
            if data: # If Pillow returned data (i.e., it's an image and had EXIF)
                return data
            # If Pillow returned no data, try exiftool (for videos or images Pillow couldn't read)
            return file_metadata(self.path)
        elif self._path.is_file(): # Fallback for the original _path if self.path isn't set/valid yet
            data = exifdata(self._path)
            if data:
                return data
            return file_metadata(self._path)
        return {}

    @property
    def prefix(self):
        """Return the set prefix"""
        return self._prefix

    @prefix.setter
    def prefix(self, prefix):
        """Set a new prefix for the file

        Args:
            prefix: new prefix value. Presets are:
                - taken_date: %y%m%d
                - taken_date_time: %y%m%d_%H%M%S
                - offload_date: %y%m%d
        """
        self.set_prefix(prefix)

    def set_prefix(self, prefix, custom_date=None):
        """Set a new prefix for the file

        Args:
            prefix: new prefix value. Presets are:
                - taken_date: %y%m%d
                - taken_date_time: %y%m%d_%H%M%S
                - offload_date: %y%m%d
            custom_date: a custom date to use with presets
        """
        # Use file modification date if custom date is none
        if custom_date is None:
            date = self.mdate
        else:
            date = custom_date

        # Get filename prefix presets
        logging.debug(f'Given prefix is {prefix}')
        if Preset.prefix(prefix) or prefix in ('empty', ''):
            self._prefix = Preset.prefix(prefix)
            if self._prefix:
                logging.debug(f'self._prefix = {self._prefix}')
                self._prefix = self._prefix.format(date=date)
        else:
            self._prefix = prefix

    @property
    def duration(self):
        """Get duration if possible"""
        video = cv2.VideoCapture(self._path)
        duration = video.get(cv2.CAP_PROP_POS_MSEC)

        return duration

    @property
    def frames(self):
        """Get frame count"""
        video = cv2.VideoCapture(self._path)
        frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)
        return frame_count

    def increment_filename(self):
        """Add incremental or count up"""
        self.inc += 1

    def set_relative_path(self, relative_to):
        """Add/update the relative path property"""
        self.relative_path = self._path.relative_to(relative_to)
        return self.relative_path

    def delete(self):
        """Delete the file"""
        if self.path.is_file():
            self.path.unlink()


class Settings:
    def __init__(self):
        """
        Object for storing and getting offloader settings
        """

        self._default_settings = {
            'latest_destination': None,
            'default_destination': None,
            'structure': 'original',
            'prefix': 'empty',
            'filename': None,
            'window_width': 900, # Matched the recent default from gui.py
            'window_height': 550 # Matched the recent default from gui.py
        }

        # Path to the user-writable settings file in APP_DATA_PATH
        self.user_settings_file = APP_DATA_PATH / 'settings.json'

        # Path to the template/default settings file (bundled or in project data folder)
        self.template_settings_file = resource_path('data/settings.json')

        # Ensure APP_DATA_PATH directory exists
        APP_DATA_PATH.mkdir(parents=True, exist_ok=True)

        if not self.user_settings_file.is_file():
            logging.info(f"User settings file not found at {self.user_settings_file}. Attempting to copy from template.")
            try:
                if self.template_settings_file.is_file():
                    shutil.copyfile(self.template_settings_file, self.user_settings_file)
                    logging.info(f"Copied template settings from {self.template_settings_file} to {self.user_settings_file}")
                else:
                    logging.warning(f"Template settings file not found at {self.template_settings_file}. Creating default user settings.")
                    with self.user_settings_file.open('w') as f:
                        json.dump(self._default_settings, f, indent=4)
            except Exception as e:
                logging.error(f"Error copying/creating settings file {self.user_settings_file}: {e}. Using in-memory defaults.")
                # Fallback to in-memory defaults if file operations fail
                self.settings = self._default_settings.copy()
                return # Skip trying to read from a problematic file
        
        self.settings = self._read_settings() # Now reads from user_settings_file

    def _read_settings(self):
        """Read settings from the user_settings_file."""
        try:
            with self.user_settings_file.open('r') as json_file:
                json_data = json.load(json_file)
                # Ensure all default keys are present
                updated = False
                for key, default_value in self._default_settings.items():
                    if key not in json_data:
                        json_data[key] = default_value
                        updated = True
                if updated:
                    self._save_settings_to_file(json_data) # Save if new keys were added
                return json_data
        except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
            logging.warning(f"Error reading user settings file {self.user_settings_file}: {e}. Attempting to create with defaults.")
            try:
                with self.user_settings_file.open('w') as f:
                    json.dump(self._default_settings, f, indent=4)
                return self._default_settings.copy()
            except IOError as e_write:
                logging.error(f"Failed to create default settings file {self.user_settings_file}: {e_write}. Using in-memory defaults.")
                return self._default_settings.copy()

    def _save_settings_to_file(self, settings_dict):
        """Directly saves the provided dictionary to the user_settings_file."""
        try:
            with self.user_settings_file.open('w') as json_file:
                json.dump(settings_dict, json_file, indent=4)
        except IOError as e:
            logging.error(f"Error writing to user settings file {self.user_settings_file}: {e}")

    def _write_settings(self, **settings_to_update):
        """Update specific keys in the current self.settings and save to disk."""
        # current_settings = self._read_settings() # No, operate on self.settings
        for k, v in settings_to_update.items():
            self.settings[k] = str(v) # Ensure values are stored as strings if needed by current logic, or adjust
        self._save_settings_to_file(self.settings)

    @property
    def latest_destination(self):
        """Get latest offload destination

        Returns:
            Path: path to latest offload destination
        """
        logging.info("LATEST_DEST_PROP_DIAG: Entered latest_destination property.")
        # logging.shutdown() # REMOVED from original troubleshooting
        dest_str = self.settings.get('latest_destination')
        # ... rest of the logic to process dest_str into a Path, with fallbacks ...
        # The original logic with LATEST_DEST_PROP_DIAG was extensive, retain its structure but use self.settings.get()
        # For brevity, I won't repeat the full extensive logging here but it should be adapted.

        if dest_str and dest_str != 'None':
            try:
                return Path(dest_str)
            except Exception as e:
                logging.error(f"Error converting latest_destination string '{dest_str}' to Path: {e}. Falling back to home.")
                return Path().home()
        else:
            # Fallback to default_destination or home if latest is not set
            default_dest_str = self.settings.get('default_destination')
            if default_dest_str and default_dest_str != 'None':
                try:
                    return Path(default_dest_str)
                except Exception as e:
                    logging.error(f"Error converting default_destination string '{default_dest_str}' to Path: {e}. Falling back to home.")
                    return Path().home()
            return Path().home()

    @latest_destination.setter
    def latest_destination(self, path):
        """Set latest offload destination"""
        path = Path(path)
        self._write_settings(latest_destination=str(path.resolve()))

    @property
    def default_destination(self):
        """Get default offload destination

        Returns:
            Path: path to latest offload destination
        """
        dest = self.settings.get('default_destination')
        # Return home path if no former destination stored
        if dest:
            dest_path = Path(dest)

            if dest_path.is_dir():
                return dest_path

        return None

    @default_destination.setter
    def default_destination(self, path):
        """Set latest offload destination"""
        path = Path(path)
        self._write_settings(default_destination=str(path.resolve()))

    def destination(self):
        """Return the destination path. If no latest_destination is set,
        return default_destination. If no default_destination is set, return home
        
        IMPORTANT DIAGNOSTIC CHANGE:
        If latest_destination exists and is not 'None', this will return it as a RAW STRING
        to prevent premature Path() object creation for potentially problematic (e.g., NAS) paths.
        Otherwise, for defaults, it returns a Path object.
        """
        logging.info("SETTINGS_DEST_METHOD_DIAG: Entered destination() method.")
        logging.shutdown() # Ensure this first log is flushed.

        latest_dest_value_from_prop = None
        try:
            logging.info("SETTINGS_DEST_METHOD_DIAG: Attempting to access self.latest_destination property...")
            logging.shutdown()
            latest_dest_value_from_prop = self.latest_destination # THIS IS THE PROPERTY ACCESS
            logging.info(f"SETTINGS_DEST_METHOD_DIAG: self.latest_destination property access successful. Value: '{latest_dest_value_from_prop}' (type: {type(latest_dest_value_from_prop)})")
            logging.shutdown()
        except Exception as e_prop_access:
            logging.critical(f"SETTINGS_DEST_METHOD_DIAG: CRITICAL PYTHON EXCEPTION accessing self.latest_destination property: {e_prop_access}", exc_info=True)
            logging.shutdown()
            # If property access itself fails at Python level, fallback (though SIGABRT is more likely)
            # Fall through to default logic
            pass # Explicitly doing nothing, will proceed to check default_destination logic

        # Check the value obtained from the property
        if latest_dest_value_from_prop and str(latest_dest_value_from_prop) != 'None':
            # The LATEST_DEST_PROP_DIAG logs inside the property getter should tell us if Path() was made
            # This method is now designed to just return the string if the property getter succeeded
            # and returned a string (or a Path that can be str()-ed here safely).
            logging.info(f"SETTINGS_DEST_METHOD_DIAG: latest_destination property had a value ('{latest_dest_value_from_prop}'). Returning str() of it.")
            logging.shutdown()
            return str(latest_dest_value_from_prop) 

        logging.info("SETTINGS_DEST_METHOD_DIAG: latest_destination (from property) is None, 'None', or prop access failed. Checking default_destination.")
        logging.shutdown()

        default_dest_path_obj = None
        if self.default_destination and str(self.default_destination) != 'None': # Access default_destination property
            logging.info(f"SETTINGS_DEST_METHOD_DIAG: default_destination property value: '{self.default_destination}'")
            logging.shutdown()
            try:
                # Assuming default_destination property returns a Path object or a convertible string for local paths
                default_dest_path_obj = Path(self.default_destination) 
                logging.info(f"SETTINGS_DEST_METHOD_DIAG: Path(default_destination) is: {default_dest_path_obj}")
                logging.shutdown()
                if default_dest_path_obj.exists() and default_dest_path_obj.is_dir():
                    logging.info(f"SETTINGS_DEST_METHOD_DIAG: Returning default_destination ('{default_dest_path_obj}') as Path object.")
                    logging.shutdown()
                    return default_dest_path_obj
                else:
                    logging.warning(f"SETTINGS_DEST_METHOD_DIAG: Default destination '{default_dest_path_obj}' does not exist or not a dir.")
                    logging.shutdown()
            except Exception as e:
                logging.error(f"SETTINGS_DEST_METHOD_DIAG: Error processing default_destination '{self.default_destination}': {e}. Falling back.")
                logging.shutdown()
        else:
            logging.info("SETTINGS_DEST_METHOD_DIAG: default_destination property is None or 'None'.")
            logging.shutdown()

        logging.info("SETTINGS_DEST_METHOD_DIAG: Falling back to Path.home() as Path object.")
        logging.shutdown()
        try:
            home_path = Path.home()
            return home_path
        except Exception as e:
            logging.critical(f"SETTINGS_DEST_METHOD_DIAG: CRITICAL - Failed to get Path.home(): {e}. Returning Path('.') as last resort.")
            logging.shutdown()
            return Path(".") # Last resort fallback

    @property
    def structure(self):
        """Get folder structure preset

        Returns:
            str: a folder structure preset
        """
        dest = self.settings.get('structure', self._default_settings['structure'])

        return dest

    @structure.setter
    def structure(self, preset: str):
        """Set folder structure preset"""
        self.settings['structure'] = preset
        self._save_settings_to_file(self.settings)

    @property
    def prefix(self):
        """Get prefix preset

        Returns:
            str: a filename prefix preset
        """
        prefix = self.settings.get('prefix', self._default_settings['prefix'])

        return prefix

    @prefix.setter
    def prefix(self, preset: str):
        """Set prefix preset"""
        self.settings['prefix'] = preset
        self._save_settings_to_file(self.settings)

    @property
    def filename(self):
        """Get filename preset

        Returns:
            str: a filename preset
        """
        filename = self.settings.get('filename', self._default_settings['filename'])

        return filename

    @filename.setter
    def filename(self, preset: str):
        """Set prefix preset"""
        self.settings['filename'] = preset
        self._save_settings_to_file(self.settings)


class PresetManager:
    def __init__(self):
        self._presets_file = APP_DATA_PATH / 'presets.json'
        self._presets = {}
        self._load_presets()

    def _load_presets(self):
        if not self._presets_file.is_file():
            self._presets = {}
            self._save_presets() # Create an empty file if it doesn't exist
        else:
            try:
                with self._presets_file.open('r') as f:
                    self._presets = json.load(f)
            except json.JSONDecodeError:
                logging.error(f"Error decoding presets file: {self._presets_file}. Initializing with empty presets.")
                self._presets = {} # Initialize with empty if file is corrupt

    def _save_presets(self):
        try:
            with self._presets_file.open('w') as f:
                json.dump(self._presets, f, indent=4)
        except IOError as e:
            logging.error(f"Could not write presets to {self._presets_file}: {e}")

    def get_preset(self, name: str):
        return self._presets.get(name)

    def get_all_presets(self) -> dict:
        return self._presets.copy() # Return a copy to prevent direct modification

    def add_or_update_preset(self, name: str, settings: dict):
        '''Adds a new preset or updates an existing one.
        
        Args:
            name: The name of the preset.
            settings: A dictionary containing:
                - target_location (str)
                - folder_structure (str)
                - filename_prefix (str)
                - filename_preset (str)
                - file_types (list of str, e.g., [".jpg", ".mp4"])
        '''
        required_keys = ['target_location', 'folder_structure', 'filename_prefix', 'filename_preset', 'file_types']
        if not all(key in settings for key in required_keys):
            logging.error(f"Preset '{name}' is missing one or more required settings: {required_keys}")
            return False
        if not isinstance(settings.get('file_types'), list):
            logging.error(f"Preset '{name}' has invalid 'file_types'. It should be a list of strings.")
            return False
            
        self._presets[name] = settings
        self._save_presets()
        logging.info(f"Preset '{name}' added/updated.")
        return True

    def delete_preset(self, name: str):
        if name in self._presets:
            del self._presets[name]
            self._save_presets()
            logging.info(f"Preset '{name}' deleted.")
            return True
        logging.warning(f"Preset '{name}' not found for deletion.")
        return False

    def get_preset_names(self) -> list:
        return list(self._presets.keys())


def setup_logger(level="info"):
    # Determine log level
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % level)

    # Basic formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level)

    # --- Temporary Startup Debug Logger ---
    # Attempt to log to a simple file in the home directory first
    # This helps diagnose if basic file logging is possible before APP_DATA_PATH logic
    temp_log_path = Path.home() / "offload_debug_startup.log"
    try:
        temp_file_handler = logging.FileHandler(temp_log_path, mode='w') # Overwrite for each run
        temp_file_handler.setFormatter(formatter)
        temp_file_handler.setLevel(logging.DEBUG) # Capture everything for this temp log
        logger.addHandler(temp_file_handler)
        logging.info(f"Temporary startup logger initialized at: {temp_log_path}")
    except Exception as e_temp_log:
        # If this fails, print to stderr as a last resort
        print(f"CRITICAL: Failed to initialize temporary startup logger at {temp_log_path}: {e_temp_log}", file=sys.stderr)
    # --- End Temporary Startup Debug Logger ---

    # Stream handler (console)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # File handler (standard location)
    try:
        if not LOGS_PATH.exists(): # LOGS_PATH is APP_DATA_PATH / 'logs'
            LOGS_PATH.mkdir(parents=True, exist_ok=True) # This should create APP_DATA_PATH as well
        
        log_file = LOGS_PATH / "offload.log"
        # Check if log file can be created/written to
        try:
            with open(log_file, 'a') as lf_test:
                 lf_test.write(f"[{datetime.now().isoformat()}] Logger test write.\\n")
            logging.info(f"Successfully tested write to standard log file: {log_file}")
        except Exception as e_write_test:
            logging.error(f"Failed to perform initial write test to {log_file}: {e_write_test}")
            # Fallback or error indication if necessary (e.g., log only to console or temp)
            # For now, we'll still try to add the handler.

        file_handler = logging.FileHandler(log_file, mode='a') # Append mode for the main log
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logging.info(f"Standard file logger initialized at: {log_file}. Previous startup messages might be in home dir log.")
    except Exception as e_standard_log:
        logging.error(f"Failed to initialize standard file logger at {LOGS_PATH / 'offload.log'}: {e_standard_log}", exc_info=True)
        logging.info("Standard file logging failed. Logs will go to console and temporary home directory log if enabled.")


def file_checksum(filename, hashtype="xxhash", block_size=65536):
    """Get the checksum for a file"""
    # Choose a hash type
    if hashtype == "xxhash":
        return checksum_xxhash(filename, block_size=block_size)
    elif hashtype == "md5":
        return checksum_md5(filename, block_size=block_size)
    elif hashtype == "sha256":
        return checksum_sha256(filename, block_size=block_size)


def checksum_xxhash(file_path, block_size=65536):
    """Get xxhash checksum for a file"""
    if xxhash is None:
        raise Exception("xxhash not available on this platform.  Try 'pip install xxhash'")
    else:
        h = xxhash.xxh3_64()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
        return h.hexdigest()


def checksum_md5(file_path, block_size=65536):
    """Get md5 checksum for a file"""
    h = hashlib.md5()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
        return h.hexdigest()


def checksum_sha256(file_path, block_size=65536):
    """Get sha256 checksum for a file"""
    h = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
        return h.hexdigest()


def timestamp_to_datetime(timestamp):
    """Convert date from timestamp
    :return datetime object"""
    return datetime.fromtimestamp(timestamp)


def create_folder(folder):
    """Create a folder if it doesn't exist"""
    folder = Path(folder)
    if not folder.is_dir():
        folder.mkdir(parents=True)
    return folder


def time_to_string(seconds):
    """Return a readable time format"""
    if seconds == 0:
        return '0 seconds'

    h, s = divmod(seconds, 3600)
    m, s = divmod(s, 60)
    if h != 1:
        h_s = 'hours'
    else:
        h_s = 'hour'
    if m != 1:
        m_s = 'minutes'
    else:
        m_s = 'minute'
    if s != 1:
        s_s = 'seconds'
    else:
        s_s = 'second'
    time_string = ''
    if h:
        time_string = f'{int(h)} {h_s}, {int(m)} {m_s} and {int(s)} {s_s}'
    elif m:
        time_string = f'{int(m)} {m_s} and {int(s)} {s_s}'
    else:
        time_string = f'{int(s)} {s_s}'
    return time_string


def convert_size(size_bytes, binary=False):
    """Convert a file size from bytes to a human readable format"""
    if size_bytes == 0:
        return "0B"
    if binary:
        mult = 1024
        size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    else:
        mult = 1000
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, mult)))
    p = math.pow(mult, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def move_file(source, destination):
    """Move a file"""
    shutil.move(source, destination)
    return True


def copy_file(source: Path, destination: Path):
    """Copy a file"""
    # shutil.copyfile
    # shutil.copyfile(source, destination)

    # shutil.copy2
    shutil.copy2(source, destination)

    # pathlib
    # destination.write_bytes(source.read_bytes())
    return True


def pathlib_copy(source: Path, destination: Path, chunk_size=262144):
    """Use pathlib to copy a file"""
    if source.stat().st_size >= (1024 ** 2 * 64):
        with source.open('rb') as src, destination.open('wb') as dest:
            for chunk in iter(lambda: src.read(chunk_size), b''):
                dest.write(chunk)
    else:
        destination.write_bytes(source.read_bytes())


def file_mod_date(file_path):
    """Return the modification time of a file"""
    file_path = Path(file_path)

    return file_path.stat().st_mtime


def get_file_info(file_path):
    """Get basic info about the file
    :return file info dict
    :rtype dict"""
    file_path = Path(file_path)
    file_timestamp = file_mod_date(file_path)
    info = {
        "name": file_path.name,
        "path": file_path,
        "timestamp": file_timestamp,
        "date": datetime.fromtimestamp(file_timestamp),
        "size": file_path.stat().st_size
    }

    return info


def compare_checksums(a, b):
    """Compare two string values to see if they match

    Returns:
        Bool: True if checksums match, False if they don't
    """
    if a == b:
        logging.info(f"Checksums match: {a} (source) | {b} (destination)")
        return True
    logging.info(f"Checksums mismatch: {a} (source)| {b} (destination)")
    return False


def compare_file_mtime(a, b):
    """Compare the modification time of two files

    Args:
        a: Path to first file
        b: Path to second file

    Returns:
        bool: True if the files have the same modification time
    """
    path_a = Path(a)
    path_b = Path(b)
    if path_a.stat().st_mtime == path_b.stat().st_mtime:
        logging.debug(f'{path_a.name}({path_a.stat().st_mtime}) and {path_b.name}({path_b.stat().st_mtime}) '
                      f'have the same modification time')
        return True

    logging.debug(f'{path_a.name}({path_a.stat().st_mtime}) and {path_b.name}({path_b.stat().st_mtime}) '
                  f'don\'t have the same modification time')
    return False


def compare_file_size(a, b):
    """Compare the size of two files

    Args:
        a: Path to first file
        b: Path to second file

    Returns:
        bool: True if the files have the same size
    """
    path_a = Path(a)
    path_b = Path(b)
    if path_b.is_file():
        if path_a.stat().st_size == path_b.stat().st_size:
            # logging.debug(f'{path_a.stat().st_size} | {path_b.stat().st_size}')
            logging.debug(
                f'{path_a.name}({path_a.stat().st_size}) and {path_b.name}({path_b.stat().st_size}) are the same size')
            return True
    logging.debug(
        f'{path_a.name}({path_a.stat().st_size}) and {path_b.name}({path_b.stat().st_size}) are NOT the same size')
    return False


def compare_files(a: File, b: File):
    a_path = Path(a.path)
    b_path = Path(b.path)
    if a.size == b.size:
        logging.info(f"Sizes match: {a.size} (source) | {b.size} (destination)")
        logging.debug(f'ctime - {a.ctime} | {b.ctime}')
        logging.debug(f'mtime - {a.mtime} | {b.mtime}')
        if a.mtime == b.mtime:
            logging.info(f"Modification times match: {a.mtime} (source) | {b.mtime} (destination)")
            return True
        else:
            logging.info(f"Modification times mismatch: {a.mtime} (source) | {b.mtime} (destination)")
    else:
        logging.info(f"Sizes mismatch: {a.size} (source) | {b.size} (destination)")

    if compare_checksums(a.checksum, b.checksum):
        return True

    return False


def update_recent_paths(path):
    """Output path to recent paths"""
    # TODO use plain text instead of json
    output_path = Path(__file__).parent / "recent_paths.json"
    recent_paths = []

    try:
        with output_path.open("r") as file:
            recent_paths = json.load(file)
    except FileNotFoundError as e:
        pass

    # Remove path from list
    for n, p in enumerate(recent_paths):
        if path == p:
            recent_paths.pop(n)

    # Add path to top of list
    recent_paths.insert(0, path)

    # Write data
    try:
        with output_path.open("w") as file:
            json_file = json.dump(recent_paths[:5], file)
            return json_file
    except Exception as e:
        logging.error(e)


def get_recent_paths():
    """Get recent destination paths from file"""
    output_path = Path(__file__).parent / "recent_paths.json"
    recent_paths = []

    try:
        with output_path.open(mode="r") as file:
            data = json.load(file)
            if isinstance(data, list):
                recent_paths.extend(data)
            else:
                recent_paths.append(data)

    except FileNotFoundError:
        logging.debug("File not found. No recent paths stored yet")

    logging.debug(recent_paths)
    return recent_paths


def pad_number(number, padding=3):
    """Add zero padding to number"""
    number_string = str(number)
    padded_number = number_string.zfill(padding)
    return padded_number


def destination_folder(file_date, preset):
    """Get a destination path depending on the structure setting"""
    # TODO original file structure
    today = datetime.now()

    if preset == "taken_date":
        # Construct new structure from modification date
        if file_date is None:
            logging.warning("File has no date, using today's date")
            file_date = datetime.today()
        return f"{file_date.year}/{file_date.strftime('%Y-%m-%d')}"

    elif preset == "offload_date":
        # Construct new structure from modification date
        return f"{today.year}/{today.strftime('%Y-%m-%d')}"

    elif preset == "year":
        # Construct new structure from modification date
        return f"{file_date.year}"

    elif preset == "year_month":
        # Construct new structure from modification date
        return f"{file_date.year}/{file_date.strftime('%m')}"

    elif preset == "flat":
        # Put files straight into destination folder
        return ""


def random_string(length=50):
    """Return a string of random letters"""
    chars = string.ascii_letters
    r_int = random.randint
    return "".join([chars[r_int(0, len(chars) - 1)] for x in range(length)])


def disk_usage(path: Path, human=False):
    """Get disk usage statistics about the given path. Will return the total, used and free space using psutil"""
    empty_usage = namedtuple('usage', 'total used free percent')(0, 0, 0, 0)
    try:
        path_obj = Path(path)
        if not path_obj.exists():
            logging.error(f'{path} does not exist.')
            return empty_usage
    except Exception as e:
        logging.error(f"Error checking existence of path '{path}': {e}")
        return empty_usage

    path_str = str(path_obj) # Use path_obj after successful existence check
    try:
        usage = psutil.disk_usage(path_str)
        # Add a percent value to the named tuple
        usage = usage._replace(percent=int(usage.percent))
    except (psutil.Error, OSError, Exception) as e: # Catch psutil specific, OS, and general errors
        logging.error(f"Error getting disk usage for '{path_str}': {e}")
        return empty_usage

    if human:
        return namedtuple('usage', 'total used free percent')(convert_size(usage.total),
                                                           convert_size(usage.used),
                                                           convert_size(usage.free),
                                                           usage.percent)
    return usage


def validate_string(invalid_string):
    """Replace or remove invalid characters in a string"""
    valid_string = str(invalid_string)
    valid_chars = f"-_.{string.ascii_letters}{string.digits}"
    char_table = {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "Å": "A",
        "Ä": "A",
        "Ö": "O",
        " ": "_"
    }
    for k, v in char_table.items():
        valid_string = valid_string.replace(k, v)

    valid_string = "".join(c for c in valid_string if c in valid_chars)

    return valid_string


def folder_size(path):
    path = Path(path)
    size = sum([x.stat().st_size for x in path.rglob("*") if x.is_file()])
    return size


def get_file_list(folder_path, exclude=None):
    """Get a list of files in a folder and its subfolders"""
    # Start timer
    start_time = time.time()
    # Convert path to Path object
    directory = Path(folder_path)

    logging.info(f"Looking for files in {directory.resolve()}")
    files = [x for x in directory.rglob("*") if x.is_file()]
    logging.info(f"{len(files)} files found")
    logging.info(f"Getting file info for {len(files)} files")

    # Setup exclude list
    if exclude is None:
        exclude = []

    # Set some other variables
    file_list = {}
    file_id = 1
    total_file_size = 0

    # Iterate through the file list
    for file in files:
        if file.name not in exclude:
            logging.info(f"Getting file info for {file.name}")
            file_list[file_id] = get_file_info(file)
            logging.info(f"File info: {file_list[file_id]}")

            # Append file size to total file size
            total_file_size += file_list[file_id]["size"]

            # Increment file id
            file_id += 1

            logging.info(f"{file_id - 1} files collected")
            logging.info(
                f"Total size collected: {convert_size(total_file_size)}")

    elapsed_time = time.time() - start_time

    logging.info(
        f"Collected file info for {len(file_list)} files in {time.strftime('%-S seconds', time.gmtime(elapsed_time))}")
    logging.info(f"Total size collected: {convert_size(total_file_size)}")

    return file_list


def exiftool(file_path):
    """Run exiftool in subprocess and return the output"""
    cmd = ['exiftool', '-G', '-j', '-sort', file_path]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    try:
        outs, errs = proc.communicate(timeout=15)
        return outs.decode("utf-8").strip()
    except subprocess.TimeoutExpired:
        proc.kill()
        outs, errs = proc.communicate()
        return errs.decode("utf-8").strip()


def exiftool_exists():
    """Checks if exiftool exists"""
    if shutil.which("exiftool"):
        return True
    else:
        logging.error("Exiftool could not be found")
        return False


def exifdata(path: Path):
    """Get exifdata from a picture using pillow"""
    if is_image_file(path):
        with Image.open(path) as img:
            exifdata = {TAGS.get(k, k): v for k, v in img.getexif().items()}
            logging.debug(f'Exifdata for {path}')
            logging.debug(exifdata)
            return exifdata
    return {}


def get_camera_make(path: Path):
    """Get the camera make from image metadata"""
    exif = exifdata(path)
    return exif.get('Make', 'unknown')


def get_camera_model(path: Path):
    """Get the camera model from image metadata"""
    exif = exifdata(path)
    return exif.get('Model', 'unknown')


def is_image_file(path):
    """Check if a file is a recognized image file"""
    try:
        with Image.open(path) as img:
            return True
    except UnidentifiedImageError as e:
        logging.error(f'{path} is not a recognized image file')
        return False


def file_metadata(file_path):
    """Get exif data using exiftool"""
    if exiftool_exists():
        raw_meta = exiftool(file_path)
        if raw_meta:
            return json.loads(raw_meta)[0]
        else:
            return raw_meta
    else:
        return None
