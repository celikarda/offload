#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Camera Offload
---
This script is used for transferring files and verifying them using a checksum.
"""

import os
import logging
import argparse
import time
import csv
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal

from offload import APP_DATA_PATH, REPORTS_PATH, EXCLUDE_FILES, utils
from offload.utils import FileList, File, Settings, PresetManager


class Offloader(QThread):
    _progress_signal = pyqtSignal(dict)

    def __init__(self, source, dest,
                 mode='copy',
                 structure=None,
                 filename=None,
                 prefix=None,
                 dryrun=False,
                 log_level='info',
                 preset_settings: dict = None):
        super(Offloader, self).__init__()
        self.settings = Settings()
        self._logger = utils.setup_logger(log_level)
        self._today = datetime.now()
        self._source = Path(source)
        
        # Apply preset settings if provided, otherwise use general settings or defaults
        if preset_settings:
            self._destination = Path(preset_settings.get('target_location', dest))
            self._structure = preset_settings.get('folder_structure', structure if structure else self.settings.structure)
            self._filename = preset_settings.get('filename_preset', filename if filename else self.settings.filename)
            self._prefix = preset_settings.get('filename_prefix', prefix if prefix else self.settings.prefix)
            allowed_extensions = preset_settings.get('file_types') 
        else:
            self._destination = Path(dest)
            if structure:
                self._structure = structure
            else:
                self._structure = self.settings.structure

            if filename:
                self._filename = filename
            else:
                self._filename = self.settings.filename

            if prefix:
                self._prefix = prefix
            else:
                self._prefix = self.settings.prefix
            allowed_extensions = None # No preset, so no specific file_types initially

        self._mode = mode
        self._dryrun = dryrun
        self._exclude = EXCLUDE_FILES
        self._signal = {'percentage': 0, 'action': '', 'time': '', 'is_finished': False}
        self._running = True

        # Properties
        logging.info("Getting list of files")
        # Pass allowed_extensions to FileList
        self.source_files = FileList(self._source, exclude=self._exclude, allowed_extensions=allowed_extensions)
        self.source_files.sort()

        # Offload attributes
        self.ol_time_started = 0
        self.ol_bytes_transferred = 0

        # Set some variables
        self.destination_folders = []
        self.skipped_files = []
        self.processed_files = []
        self.errored_files = []

        # Report
        self.report = Report()

    def update_from_settings(self, preset_settings: dict = None):
        """Update structure, filename and prefix from settings or a preset"""
        if preset_settings:
            self._destination = Path(preset_settings.get('target_location', self._destination)) # Keep current dest if not in preset
            self._structure = preset_settings.get('folder_structure', self.settings.structure)
            self._filename = preset_settings.get('filename_preset', self.settings.filename)
            self._prefix = preset_settings.get('filename_prefix', self.settings.prefix)
            allowed_extensions = preset_settings.get('file_types')
            # Re-initialize FileList with new file_types if they changed
            # We should only re-scan if source or allowed_extensions change.
            # For now, let's assume source is fixed after initOffloader, and only extensions might change with preset.
            if self.source_files.allowed_extensions != allowed_extensions:
                 self.source_files = FileList(self._source, exclude=self._exclude, allowed_extensions=allowed_extensions)
                 self.source_files.sort()
            logging.debug(f"Offloader updated from preset: {preset_settings.get('name', 'Unnamed Preset')}")

        else: # Fallback to general settings if no preset
            self._structure = self.settings.structure
            self._filename = self.settings.filename
            self._prefix = self.settings.prefix
            # If we were on a preset and now go to no preset, reset file_types filter
            if self.source_files.allowed_extensions is not None:
                 self.source_files = FileList(self._source, exclude=self._exclude, allowed_extensions=None)
                 self.source_files.sort()
            logging.debug(f"Offloader updated from general settings.")

        logging.debug(f'Folder structure preset is {self._structure}')
        logging.debug(f'Filename preset is {self._filename}')
        logging.debug(f'Filename prefix preset is {self._prefix}')
        logging.debug(f'Allowed extensions are {self.source_files.allowed_extensions}')

    @property
    def source(self):
        """Get the source directory"""
        return self._source

    @source.setter
    def source(self, path):
        """Set the source directory and update FileList, respecting current preset's file_types"""
        if Path(path).is_dir():
            self._source = Path(path)
            current_allowed_extensions = self.source_files.allowed_extensions if hasattr(self, 'source_files') and self.source_files else None
            self.source_files = FileList(self._source, exclude=self._exclude, allowed_extensions=current_allowed_extensions)
            self.source_files.sort() # Sort after updating
        else:
            logging.error(f'{path} is not a valid directory')

    @property
    def destination(self):
        """Get the source directory"""
        return self._destination

    @destination.setter
    def destination(self, path):
        """Set the source directory"""
        self._destination = Path(path)

    @property
    def structure(self):
        """Get the folder structure preset"""
        return self._structure

    @structure.setter
    def structure(self, preset):
        """Set the folder structure preset"""
        self._structure = preset

    @property
    def ol_percentage(self):
        return round((self.ol_bytes_transferred / self.source_files.size) * 100, 2)

    @property
    def ol_time_elapsed(self):
        return time.time() - self.ol_time_started

    @property
    def ol_bytes_remaining(self):
        return self.source_files.size - self.ol_bytes_transferred

    @property
    def ol_time_remaining(self):
        return self.ol_bytes_remaining / self.ol_speed if self.ol_speed else 0

    @property
    def ol_speed(self):
        return self.ol_bytes_transferred / self.ol_time_elapsed

    def offload(self):
        """Offload files"""
        # Offload start time
        self.ol_time_started = time.time()

        # Get list of files in source folder
        logging.info(f"Total file size: {self.source_files.hsize}")
        logging.info(f"Average file size: {utils.convert_size(self.source_files.avg_file_size)}")
        logging.info("---\n")

        # Iterate over all the files
        for file_id, source_file in enumerate(self.source_files.files):
            skip = False

            # Display how far along the transfer we are
            logging.info(f"Processing file {file_id + 1}/{len(self.source_files.files)} "
                         f"(~{self.ol_percentage}%) | {source_file.filename}")

            # Send signal to GUI
            self._signal['percentage'] = int(self.ol_percentage)
            self._signal['action'] = f'Processing file {file_id + 1}/{len(self.source_files.files)}'
            self._signal['time'] = self.ol_time_remaining
            self._progress_signal.emit(self._signal)

            # Create File object for destination file
            dest_folder = self._destination / utils.destination_folder(source_file.mdate, preset=self._structure)
            dest_file = File(dest_folder / source_file.filename, prefix=self._prefix)

            # Change filename
            if self._filename:
                logging.debug(f'New user given filename is {self._filename}')
                new_name = source_file.exifdata.get(utils.Preset.filename(self._filename), "unknown").lower()
                logging.debug(new_name)
                dest_file.name = new_name

            # Add prefix to filename
            dest_file.set_prefix(self._prefix, custom_date=source_file.mdate)

            # Add destination folder to list of destination folders
            if dest_folder not in self.destination_folders:
                self.destination_folders.append(dest_folder)

            # Write to report
            if not self._running:
                self.report.write(source_file, dest_file, 'Not started', checksum=False)
                continue

            # Print meta
            logging.info(f"File modification date: {source_file.mdate}")
            logging.info(f"Source path: {source_file.path}")
            logging.info(f"Destination path: {dest_file.path}")

            # Check for existing files and update filename
            while True:
                # Check if destination file exists
                if dest_file.is_file:
                    # Send signal to GUI
                    self._signal['action'] = f'Processing file {file_id + 1}/{len(self.source_files.files)} [verifying]'
                    self._progress_signal.emit(self._signal)

                    # Add increment
                    if dest_file.inc < 1:
                        logging.info("File with the same name exists in destination, comparing attributes")
                    else:
                        logging.debug(
                            f"File with incremented name {dest_file.filename} exists, comparing checksums")

                    # If checksums are matching
                    # if utils.compare_checksums(source_file.checksum, dest_file.checksum):
                    if utils.compare_files(source_file, dest_file):
                        logging.warning(f"File ({dest_file.filename}) "
                                        f"already exists in destination, skipping")
                        # Write to report
                        self.report.write(source_file, dest_file, 'Skipped')

                        self.skipped_files.append(source_file.path)

                        skip = True
                        break
                    else:
                        logging.warning(
                            f"File ({dest_file.filename}) with the same name already exists in destination,"
                            f" adding incremental")
                        dest_file.increment_filename()
                        logging.debug(f'Incremented filename is {dest_file.filename}')
                        continue
                else:
                    break

            # Perform file actions
            if not skip:
                if source_file.path.is_file():
                    if self._dryrun:
                        logging.info("DRYRUN ENABLED, NOT PERFORMING FILE ACTIONS")
                    else:
                        # Create destination folder
                        dest_file.path.parent.mkdir(exist_ok=True, parents=True)

                        # Send signal to GUI
                        self._signal[
                            'action'] = f'Processing file {file_id + 1}/{len(self.source_files.files)} [copying]'
                        self._progress_signal.emit(self._signal)

                        # Copy file
                        utils.pathlib_copy(source_file.path, dest_file.path)

                        # Send signal to GUI
                        self._signal[
                            'action'] = f'Processing file {file_id + 1}/{len(self.source_files.files)} [verifying]'
                        self._progress_signal.emit(self._signal)

                        # Verify file transfer
                        logging.info("Verifying transferred file")

                        # File transfer successful
                        if utils.compare_checksums(source_file.checksum, dest_file.checksum):
                            logging.info("File transferred successfully")

                            # Write to report
                            self.report.write(source_file, dest_file, 'Successful')

                            # Delete source file
                            if self._mode == "move":
                                source_file.delete()

                        # File transfer unsuccessful
                        else:
                            logging.error("File NOT transferred successfully, mismatching checksums")

                            # Write to report
                            self.report.write(source_file, dest_file, 'Failed')

                            self.errored_files.append({source_file.path: "Mismatching checksum after transfer"})

            # Add file size to total
            self.ol_bytes_transferred += source_file.size

            # Add file to processed files
            self.processed_files.append(source_file.filename)

            # Calculate remaining time
            logging.info(f"Elapsed time: {utils.time_to_string(self.ol_time_elapsed)}")

            # Log transfer speed
            logging.info(f"Avg. transfer speed: {utils.convert_size(self.ol_speed)}/s")

            logging.info(f"Size remaining: {utils.convert_size(self.ol_bytes_remaining)}")
            logging.info(f"Approx. time remaining: {self.ol_time_remaining}")
            logging.info("---\n")

        # Print created destination folders
        if self.destination_folders:
            # Sort folder for better output
            self.destination_folders.sort()

            logging.info(f"Created the following folders {', '.join([str(x.name) for x in self.destination_folders])}")
            logging.debug([str(x.resolve()) for x in self.destination_folders])

        logging.info(f"{len(self.processed_files)} files processed")
        logging.debug(f"Processed files: {self.processed_files}")

        logging.info(f"{len(self.destination_folders)} destination folders")
        logging.debug(f"Destination folders: {self.destination_folders}")

        logging.info(f"{len(self.skipped_files)} files skipped")
        logging.debug(f"Skipped files: {self.skipped_files}")

        # Save report to desktop
        print(self._running)
        self.report.save()
        self.report.write_html()
        self._signal['time'] = 0
        self._signal['is_finished'] = True
        self._progress_signal.emit(self._signal)
        return True

    def run(self):
        logging.info('Hello')
        self.offload()


class Report:
    def __init__(self, report_format='csv'):
        self._date = datetime.now()
        self.format = report_format
        self.path = REPORTS_PATH / f"{self._date.strftime('%y%m%d%H%M')}_report.csv"
        self.html_path = self.path.parent / f'{self.path.stem}.html'
        self.html_template_path = APP_DATA_PATH / 'data' / 'report_template.html'

        if not self.path.parent.is_dir():
            self.path.parent.mkdir(exist_ok=True, parents=True)
        columns = ['Source Filename', 'Destination Filename', 'Status', 'Source Checksum', 'Destination Checksum',
                   'Source Path', 'Destination Path', 'Size', 'Modification Date']

        if not self.path.is_file():
            with self.path.open('w') as report:
                writer = csv.writer(report, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(columns)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.write_html()

    def write_html(self):
        """Create html file from csv"""
        with self.path.open('r') as report:
            csv_reader = csv.reader(report, delimiter=',')
            line_count = 0
            table_columns = ''
            table_rows = []
            for row in csv_reader:
                if line_count == 0:
                    table_columns = '\n'.join([f'<th scope="col">{x}</th>' for x in row])
                    line_count += 1
                else:
                    cols = []
                    for col in row:
                        if col == 'Successful':
                            cols.append(f'\t<td><span class="text-success">{col}</span></td>')
                        elif col == 'Skipped':
                            cols.append(f'\t<td><span class="text-info">{col}</span></td>')
                        elif col == 'Failed':
                            cols.append(f'\t<td><span class="text-failed">{col}</span></td>')
                        else:
                            cols.append(f'\t<td>{col}</td>')
                    td = '\n'.join(cols)
                    table_rows.append(td)
                    line_count += 1
            table_rows = '\n'.join([f'<tr>\n{x}\n</tr>' for x in table_rows])

        html_report = self.html_template_path.read_text()
        html_report = html_report.format(date=self._date.strftime('%Y-%m-%d %H:%M'),
                                         table_columns=table_columns,
                                         table_rows=table_rows)
        self.html_path.write_text(html_report)
        return self.html_path

    def write(self, source: File, destination: File, status, checksum=True):
        with self.path.open('a') as report:
            writer = csv.writer(report, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            if checksum:
                columns = [source.filename, destination.filename, status,
                           source.checksum, destination.checksum,
                           source.path, destination.path, utils.convert_size(source.size), source.mdate]
            else:
                columns = [source.filename, destination.filename, status,
                           None, None,
                           source.path, destination.path, utils.convert_size(source.size), source.mdate]
            writer.writerow(columns)

    def save(self, path=None):
        if path is None:
            path = Path().home() / 'Desktop' / f"Offload_Report_{self._date.strftime('%Y-%m-%d_%H%M')}.csv"
        utils.pathlib_copy(self.path, path)


def cli():
    """Command line interface"""
    # Create the parser
    parser = argparse.ArgumentParser(
        description="Offload files with checksum verification")

    # Add the arguments
    parser.add_argument("-s", "--source",
                        type=str,
                        help="The source folder",
                        action="store")

    parser.add_argument("-d", "--destination",
                        type=str,
                        help="The destination folder",
                        action="store")

    parser.add_argument("-f", "--folder-structure",
                        choices=["original", "taken_date",
                                 "offload_date", "year", "year_month", "flat"],
                        dest="structure",
                        default="taken_date",
                        help="Set the folder structure.\nDefault: taken_date",
                        action="store")

    parser.add_argument("-n", "--name",
                        type=str,
                        help="Set a new filename",
                        action="store")

    parser.add_argument("-p", "--prefix",
                        help="Set the filename prefix. Enter a custom prefix, \"taken_date\", \"taken_date_time\" or "
                             "\"offload_date\" for templates. \"none\" for no prefix.\nDefault: taken_date",
                        default="taken_date",
                        action="store")

    parser.add_argument("-m", "--move",
                        help="Move files instead of copy",
                        action="store_true")

    parser.add_argument("--dryrun",
                        help="Run the script without actually changing any files",
                        action="store_true")

    parser.add_argument("--debug-log",
                        dest="log_level",
                        help="Show the log with debugging messages",
                        action="store_true")

    # Execute the parse_args() method
    args = parser.parse_args()

    # Print the title
    print("================")
    print("CAMERA OFFLOADER")
    print("================")
    print("")

    confirmation = False

    if args.source is None:
        confirmation = True
        volumes = {}
        if os.name == "posix":
            volumes = {n: str(v) for (n, v) in enumerate(
                Path("/Volumes").iterdir(), 1)}
        print(f"Choose a volume to offload from, or enter a custom path:")
        for n, vol in volumes.items():
            print(f"{n}: {vol}")

        while True:
            try:
                source_input = input("> ").strip()
                if Path(source_input).is_dir():
                    source = Path(source_input)
                    break
                elif volumes.get(int(source_input)):
                    source = volumes[int(source_input)]
                    break
                else:
                    print("Invalid choice. Try again.")

            except Exception as e:
                print("Invalid selection")

                exit(1)
    else:
        source = args.source

    print("")

    if args.destination is None:
        confirmation = True
        recent_paths = {n: str(v) for (n, v) in enumerate(
            utils.get_recent_paths(), 1)}
        if recent_paths:
            print(
                f"Enter the path to your destination folder or use one of these recent paths:")
            for n, path in recent_paths.items():
                print(f"{n}: {path}")
        else:
            print(f"Enter the path to your destination folder:")

        while True:
            try:
                dest_input = input("> ").strip()
                if dest_input.isdigit():
                    destination = recent_paths[int(dest_input)]
                    break
                else:
                    if Path(dest_input).exists():
                        destination = dest_input
                        break

                    else:
                        print("Path does not exist. Try again.")

            except Exception as e:
                print("Invalid input")
                exit(1)

    else:
        destination = args.destination

    # Save destination path for history
    # utils.update_recent_paths(destination)
    Settings.latest_destination = destination

    # Set the folder structure
    folder_structure = args.structure

    # Set the transfer mode
    if args.move:
        mode = "move"
    else:
        mode = "copy"

    # Set the log level
    if args.log_level:
        log_level = "debug"
    else:
        log_level = "info"

    # Confirmation dialog
    if confirmation:
        print("---")
        print("\nPre-transfer summary\n")
        print(f"Source path: {source}")
        print(f"Destination path: {destination}")
        print("")
        print(f"Mode: {mode}")
        print(f"Folder structure: {folder_structure}")
        if args.name:
            print(f"Name: {args.name}")
        print(f"Prefix: {args.prefix}")
        print(f"Log level: {log_level}")
        if args.dryrun:
            print("")
            print("THIS IS A DRYRUN. NO FILES WILL BE TRANSFERRED.")
        print("")
        print("Press enter to continue or any other key to cancel")
        if input():
            quit()
        print("")

    # Run offload
    ol = Offloader(source=source,
                   dest=destination,
                   structure=folder_structure,
                   filename=args.name,
                   prefix=args.prefix,
                   mode=mode,
                   dryrun=args.dryrun,
                   log_level=log_level
                   )
    ol.offload()


if __name__ == "__main__":
    cli()
