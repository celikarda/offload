"""Dialog-Style application."""
import time
import sys
import psutil
import logging
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QDialog, QMainWindow
from PyQt5.QtWidgets import QLineEdit, QPushButton, QLabel, QFileDialog, QProgressBar, QComboBox
from PyQt5.QtWidgets import QSpacerItem, QSizePolicy, QFrame
from PyQt5.QtWidgets import QGridLayout, QVBoxLayout, QHBoxLayout, QFormLayout
from PyQt5.QtWidgets import QStyle
from PyQt5.QtGui import QIcon, QPixmap, QFontDatabase, QFont
from PyQt5 import QtCore
from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path

from offload import VERSION, utils
from offload.utils import setup_logger, disk_usage, Settings, File
from offload.app import Offloader
from offload.styles import STYLES, COLORS

setup_logger('debug')


# QStyle.SP_DriveHDIcon
class QHLine(QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)


class Timer(QThread):
    _time_signal = pyqtSignal(float)

    def __init__(self):
        super(Timer, self).__init__()
        self.start_time = time.time()
        self.time_left = 1
        self.running = True

    @property
    def running_time(self):
        return time.time() - self.start_time

    def run(self):
        print(self.time_left)
        while True:
            self._time_signal.emit(self.time_left)
            if self.time_left > 0:
                self.time_left -= 1
            time.sleep(1)
            if not self.running:
                break


class SettingsDialog(QDialog):
    def __init__(self):
        super(SettingsDialog, self).__init__()
        self.settings = Settings()
        self.example_file = File('IMG_01337.RAW')
        self.initUI()
        # Show UI
        # self.show()

    def initUI(self):
        self.resize(640, 260)
        fontDB = QFontDatabase()
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Regular.otf'))
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Bold.otf'))
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Light.otf'))
        font = QFont('Source Sans 3')
        font.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(font)

        # mainLayout = QVBoxLayout()
        mainLayout = QGridLayout()
        self.destinationLine = QLineEdit(str(self.settings.default_destination))
        self.destinationLine.textChanged.connect(self.defaultDestinationChange)
        # mainLayout.addWidget(QLabel('Default Destination:'), 0, 0, 1, 1)
        # mainLayout.addWidget(self.destinationLine, 0, 1, 1, 2)

        # Structure presets
        self.structureCombo = QComboBox()
        self.structureOptions = {0: 'original',
                                 1: 'taken_date',
                                 2: 'year_month',
                                 3: 'year',
                                 4: 'flat'}
        self.structureCombo.addItem('Keep original')
        self.structureCombo.addItem('YYYY/YYYY-MM-DD')
        self.structureCombo.addItem('YYYY/MM')
        self.structureCombo.addItem('YYYY')
        self.structureCombo.addItem('Flat')

        # Set current item from settings
        currentStructure = list(self.structureOptions.values()).index(self.settings.structure)
        self.structureCombo.setCurrentIndex(currentStructure)
        # Add to layout and add an action
        self.structureCombo.currentIndexChanged.connect(self.folderStructureChange)
        mainLayout.addWidget(QLabel('Folder Structure:'), 1, 0, 1, 1)
        mainLayout.addWidget(self.structureCombo, 1, 1, 1, 2)

        # Prefix presets
        self.prefixCombo = QComboBox()
        self.prefixOptions = {0: 'empty',
                              1: 'taken_date',
                              2: 'taken_date_time'}
        self.prefixCombo.addItem('No prefix')
        self.prefixCombo.addItem('YYMMDD')
        self.prefixCombo.addItem('YYMMDD_hhmmss')
        # Set current item from settings
        currentPrefix = list(self.prefixOptions.values()).index(self.settings.prefix)
        self.prefixCombo.setCurrentIndex(currentPrefix)
        # Connect action
        self.prefixCombo.currentIndexChanged.connect(self.prefixChange)
        # Add to layout
        mainLayout.addWidget(QLabel('Filename prefix:'), 2, 0, 1, 1)
        mainLayout.addWidget(self.prefixCombo, 2, 1, 1, 2)

        # Filename presets
        self.filenameCombo = QComboBox()
        self.filenameOptions = {0: None,
                                1: 'camera_make',
                                2: 'camera_model'}
        self.filenameCombo.addItem('Keep original')
        self.filenameCombo.addItem('Camera brand')
        self.filenameCombo.addItem('Camera model')
        # Set current item from settings
        if self.settings.filename != 'None':
            currentFilename = list(self.filenameOptions.values()).index(self.settings.filename)
        else:
            currentFilename = 0
        self.filenameCombo.setCurrentIndex(currentFilename)

        # Connect action
        self.filenameCombo.currentIndexChanged.connect(self.filenameChange)
        # Add to layout
        mainLayout.addWidget(QLabel('Filename:'), 3, 0, 1, 1)
        mainLayout.addWidget(self.filenameCombo, 3, 1, 1, 2)

        # Filename presets
        self.exampleLabel = QLabel('/Volumes/mcdaddy/media/photos/2021/2021-02-28/210228_IMG_01337.dng')
        self.updateExampleLabel()
        # Add to layout
        mainLayout.addWidget(QLabel('Example:'), 4, 0, 1, 3)
        mainLayout.addWidget(self.exampleLabel, 5, 0, 1, 3)

        # Close button
        self.closeButton = QPushButton('Close')
        self.closeButton.clicked.connect(self.close)
        mainLayout.addWidget(self.closeButton, 6, 0, 1, 3)

        # Font
        fontDB = QFontDatabase()
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Regular.otf'))
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Bold.otf'))
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Light.otf'))
        font = QFont('Source Sans 3')
        font.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(font)

        # Styling
        self.colors = COLORS
        self.styles = STYLES
        self.setStyleSheet(self.styles)

        self.setLayout(mainLayout)

    def updateExampleLabel(self):
        """Update the example label to be correct with the new settings"""
        label = ''
        path = Path('/Volumes/Storage/Pictures/IMG_01337.dng')
        prefix = utils.Preset.prefix(self.settings.prefix)
        structure = utils.Preset.structure(self.settings.structure)
        filename = path.name
        label = f'{path.parent}'

        if structure:
            subdir = f'{structure.format(date=datetime.now())}'
            label = f'{label}/{subdir}'

        if self.settings.filename == 'camera_make':
            filename = 'sony_003.dng'
        elif self.settings.filename == 'camera_model':
            filename = 'ilce-7m3_003.dng'

        if prefix:
            filename = f'{prefix.format(date=datetime.now())}_{filename}'

        label = f'{label}/{filename}'
        self.exampleLabel.setText(label)

    def defaultDestinationChange(self):
        self.settings.default_destination = self.destinationLine.text()
        self.updateExampleLabel()
        logging.info(f'Default destination changed to {self.settings.default_destination}')

    def folderStructureChange(self):
        self.settings.structure = self.structureOptions[self.structureCombo.currentIndex()]
        self.updateExampleLabel()
        logging.info(f'Folder structure changed to {self.structureOptions[self.structureCombo.currentIndex()]}')

    def filenameChange(self):
        self.settings.filename = self.filenameOptions[self.filenameCombo.currentIndex()]
        self.updateExampleLabel()
        logging.info(f'Filename changed to {self.filenameOptions[self.filenameCombo.currentIndex()]}')

    def prefixChange(self):
        self.settings.prefix = self.prefixOptions[self.prefixCombo.currentIndex()]
        self.updateExampleLabel()
        logging.info(f'Prefix changed to {self.prefixOptions[self.prefixCombo.currentIndex()]}')


class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set central widget
        self._centralWidget = QWidget(self)
        self.setCentralWidget(self._centralWidget)

        self.offloader = None
        self.settings = Settings()

        # Paths
        self.sourcePath = None
        # self.sourcePath = Path().home()

        # Load smallest drive as source path
        vols = self.volumes()
        if vols:
            smallest_vol = min(vols, key=vols.get)
            # Only pick volumes smaller than 129 GB
            if vols[smallest_vol] / 1024 ** 3 < 129:
                self.sourcePath = Path(smallest_vol)

        # Setup custom font
        fontDB = QFontDatabase()
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Regular.otf'))
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Bold.otf'))
        fontDB.addApplicationFont(str(Path(__file__).parent / 'data' / 'fonts' / 'SourceSans3-Light.otf'))
        font = QFont('Source Sans 3')
        font.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(font)

        self.sourceSize = 0
        
        # Pre-flight checks before calling self.settings.destination()
        try:
            logging.info(f"PRE_DEST_CALL_DIAG: About to interact with self.settings.")
            logging.info(f"PRE_DEST_CALL_DIAG: Type of self.settings: {type(self.settings)}")
            logging.shutdown()
            if hasattr(self.settings, 'destination'):
                logging.info(f"PRE_DEST_CALL_DIAG: self.settings has attribute 'destination'. Type: {type(self.settings.destination)}")
                logging.shutdown()
                # For extreme check, see if we can even get the method object itself
                # method_obj = getattr(self.settings, 'destination')
                # logging.info(f"PRE_DEST_CALL_DIAG: getattr(self.settings, 'destination') is {method_obj}")
                # logging.shutdown()
            else:
                logging.info("PRE_DEST_CALL_DIAG: self.settings has NO 'destination' attribute.")
                logging.shutdown()
        except Exception as e_pre_log:
            logging.critical(f"PRE_DEST_CALL_DIAG: CRITICAL - Error in pre-call logging for self.settings.destination: {e_pre_log}", exc_info=True)
            logging.shutdown()

        # The problematic call
        try:
            logging.info("PRE_DEST_CALL_DIAG: Attempting to call self.settings.destination()...")
            logging.shutdown()
            self.destPath = self.settings.destination()
            logging.info(f"PRE_DEST_CALL_DIAG: self.settings.destination() call completed.")
            logging.shutdown()
        except Exception as e_dest_call: # Catch Python-level exceptions from the call itself
            logging.critical(f"PRE_DEST_CALL_DIAG: CRITICAL PYTHON EXCEPTION during self.settings.destination() call: {e_dest_call}", exc_info=True)
            logging.shutdown()
            # Fallback self.destPath if the call fails at Python level (though SIGABRT is more likely)
            self.destPath = Path().home() 

        # Log self.destPath value and type AFTER the call
        try:
            logging.info(f"INIT_UI_DIAG: self.destPath value after call: '{self.destPath}' (type: {type(self.destPath)})")
            logging.shutdown()
        except Exception as e_log_init:
            logging.critical(f"INIT_UI_DIAG: CRITICAL - Error logging self.destPath post-call: {e_log_init}", exc_info=True)
            logging.shutdown()

        self.destSize = 0
        self.iconSize = 48
        self.colors = COLORS
        self.styles = STYLES
        self.styleOffloadBtnActive = f"""
                border-radius: 21px;
                padding: 10px 30px;
                background:{self.colors['gray']}; 
                color: {self.colors['bg']};
            """
        self.styleOffloadBtnFinished = f"""
                        border-radius: 21px;
                        padding: 10px 30px;
                        background:{self.colors['green']}; 
                        color: {self.colors['bg']};
                    """

        # App settings
        self.setWindowTitle(f'Offload {VERSION}')
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_DirLinkIcon))
        # self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setStyleSheet(self.styles)
        self.initUI()

        # Show UI
        self.show()

        # Init offload
        if self.sourcePath:
            self.initOffloader()

    def initUI(self):
        mainLayout = QVBoxLayout()
        mainColsLayout = QHBoxLayout()

        # mainColsLayout
        # Source column
        mainColsLayout.addSpacerItem(QSpacerItem(100, 10, QSizePolicy.MinimumExpanding))
        mainColsLayout.addLayout(self.sourceColumn())

        # Arrow
        mainColsLayout.addSpacerItem(QSpacerItem(100, 10, QSizePolicy.MinimumExpanding))
        midLayout = QVBoxLayout()
        arrow = QLabel('→')
        arrow.setObjectName('arrow')
        midLayout.addWidget(arrow)

        # Settings
        settingsButton = QPushButton('...')
        settingsButton.clicked.connect(self.settingsDialog)
        midLayout.addWidget(settingsButton)

        # Add middle layout and spacer
        mainColsLayout.addLayout(midLayout)
        mainColsLayout.addSpacerItem(QSpacerItem(100, 10, QSizePolicy.MinimumExpanding))

        # Destination column
        try:
            logging.info("INIT_UI_DIAG: Calling self.destColumn()...")
            logging.shutdown()
            dest_col_layout = self.destColumn()
            logging.info("INIT_UI_DIAG: self.destColumn() returned.")
            logging.shutdown()
            mainColsLayout.addLayout(dest_col_layout)
        except Exception as e_destcol:
            logging.critical(f"INIT_UI_DIAG: CRITICAL - Error calling or adding self.destColumn(): {e_destcol}")
            logging.shutdown()
            # Add a placeholder if it fails
            mainColsLayout.addLayout(QVBoxLayout())

        mainColsLayout.addSpacerItem(QSpacerItem(100, 10, QSizePolicy.MinimumExpanding))

        # mainLayout
        mainLayout.addStretch()
        mainLayout.addSpacerItem(QSpacerItem(0, 50, QSizePolicy.MinimumExpanding))
        mainLayout.addLayout(mainColsLayout)
        mainLayout.addSpacerItem(QSpacerItem(0, 50, QSizePolicy.MinimumExpanding))
        mainLayout.addStretch()
        # mainLayout.addWidget(QHLine())

        # Paths
        mainPathsLayout = QHBoxLayout()
        # Source path
        mainPathsLayout.addWidget(QLabel('Source:'))
        self.sourcePathLabel = self.pathLabel('')
        if self.sourcePath:
            self.sourcePathLabel = self.pathLabel(self.sourcePath)
        self.sourcePathLabel.setObjectName('source-path')
        mainPathsLayout.addWidget(self.sourcePathLabel)
        mainPathsLayout.addSpacerItem(QSpacerItem(50, 10, QSizePolicy.MinimumExpanding))

        # Destination path
        mainPathsLayout.addWidget(QLabel('Destination:'))
        self.destPathLabel = self.pathLabel(self.destPath)
        self.destPathLabel.setObjectName('dest-path')
        try:
            logging.info(f"INIT_UI_DIAG: Attempting self.destPathLabel.setText(self.pathLabelText(self.destPath)) for path: {self.destPath}")
            logging.shutdown()
            path_label_text_val = self.pathLabelText(self.destPath)
            logging.info(f"INIT_UI_DIAG: self.pathLabelText returned: '{path_label_text_val}'")
            logging.shutdown()
            self.destPathLabel.setText(path_label_text_val)
            logging.info("INIT_UI_DIAG: Successfully set destPathLabel text.")
            logging.shutdown()
        except Exception as e_dpl_settext:
            logging.critical(f"INIT_UI_DIAG: CRITICAL - Error in destPathLabel.setText or pathLabelText: {e_dpl_settext}")
            logging.shutdown()
            try:
                self.destPathLabel.setText("Error displaying path")
            except: pass # Ignore if this also fails

        mainPathsLayout.addWidget(self.destPathLabel)
        try:
            logging.info("INIT_UI_DIAG: Calling self.updateDestInfo()...")
            logging.shutdown()
            self.updateDestInfo()
            logging.info("INIT_UI_DIAG: self.updateDestInfo() returned.")
            logging.shutdown()
        except Exception as e_upd_dest_info:
            logging.critical(f"INIT_UI_DIAG: CRITICAL - Error calling self.updateDestInfo(): {e_upd_dest_info}")
            logging.shutdown()

        mainLayout.addLayout(mainPathsLayout)
        # Progress
        self.progressBar = QProgressBar()
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(False)
        self.progressBar.setFixedHeight(10)
        mainLayout.addWidget(self.progressBar)

        subProgressBarLayout = QHBoxLayout()
        self.progressFiles = QLabel('1. Pick a source folder')
        self.progressFiles.setMinimumWidth(250)
        self.progressFiles.setAlignment(QtCore.Qt.AlignLeft)
        self.progressPercent = QLabel('2. Pick a destination folder')
        self.progressPercent.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignTop)
        self.progressTime = QLabel('3. Press Offload')
        self.progressTime.setMinimumWidth(250)
        self.progressTime.setAlignment(QtCore.Qt.AlignRight)
        subProgressBarLayout.addWidget(self.progressFiles)
        subProgressBarLayout.addStretch()
        subProgressBarLayout.addWidget(self.progressPercent)
        subProgressBarLayout.addStretch()
        subProgressBarLayout.addWidget(self.progressTime)
        mainLayout.addLayout(subProgressBarLayout)

        # Offload button
        self.offloadButton = QPushButton('Offload')
        self.offloadButton.setObjectName('offload-btn')
        self.offloadButton.clicked.connect(self.offload)
        mainLayout.addWidget(self.offloadButton, 0, QtCore.Qt.AlignCenter)
        # mainLayout.addSpacing(5)
        # mainLayout.addWidget(QTextBrowser())

        self._centralWidget.setLayout(mainLayout)

    def settingsDialog(self):
        """Open the settings dialog to make changes to settings"""
        # app = QApplication(sys.argv)
        logging.debug(f'Settings dialog opened')
        settings = SettingsDialog()
        settings.exec_()

        # Load settings from file
        # self.offloader.update_from_settings()

    def updateProgressBar(self, progress):
        self.progressBar.setValue(int(progress.get('percentage', 0)))
        self.progressFiles.setText(progress.get('action', ''))
        self.progressPercent.setText(f'{int(progress.get("percentage", ""))}%')
        self.timer.time_left = progress.get('time')
        if progress['is_finished'] and self.offloader._running:
            self.finished()
        elif progress['is_finished'] and not self.offloader._running:
            self.canceled()
        self.updateDestInfo()

    def canceled(self):
        self.timer.running = False
        self.progressFiles.setText('Writing report')
        self.progressTime.setText('Offload canceled')
        self.offloadButton.setText('Canceled')
        self.offloadButton.setStyleSheet(
            f"#offload-btn {{background:{self.colors['dark-orange']};color:{self.colors['bg']};}}")
        self.offloadButton.clicked.disconnect()
        self.offloadButton.clicked.connect(self.close)

    def finished(self):
        self.progressBar.setValue(100)
        self.progressBar.setStyleSheet(
            f"QProgressBar::chunk {{background: {COLORS['green']}; border-radius: 5px;}}")
        self.progressPercent.setText(f'100%')
        self.progressTime.setText(f"Finished")
        self.timer.running = False
        self.offloadButton.setText('Done')
        self.offloadButton.setStyleSheet(
            f"#offload-btn {{background:{self.colors['green']};color:{self.colors['bg']};}}")
        self.offloadButton.clicked.disconnect()
        self.offloadButton.clicked.connect(self.close)

    def updateTime(self, value):
        self.progressTime.setText(f"Approx. {utils.time_to_string(value)} left")

    def offload(self):
        if self.sourcePath:
            self.timer.start()
            self.offloader.start()
            self.offloadButton.setText('Offloading')
            self.offloadButton.setStyleSheet(self.styleOffloadBtnActive)
            self.offloadButton.clicked.disconnect()
            self.offloadButton.clicked.connect(self.stopOffload)

    def stopOffload(self):
        """Cancel the running offload"""
        self.offloader._running = False

    def initOffloader(self):
        self.offloader = Offloader(source=self.sourcePath,
                                   dest=self.destPath,
                                   structure=self.settings.structure,
                                   filename=self.settings.filename,
                                   prefix=self.settings.prefix,
                                   mode='copy',
                                   dryrun=False,
                                   log_level='debug')
        self.offloader._progress_signal.connect(self.updateProgressBar)
        self.timer = Timer()
        self.timer._time_signal.connect(self.updateTime)
        self.updateSourceInfo()
        self.updateDestInfo()

    def updateSourceInfo(self):
        self.sourceInfoLabel.setText(f'{self.offloader.source_files.count} files, {self.offloader.source_files.hsize}')

    def updateDestInfo(self):
        try:
            if self.destPath:
                # Ensure utils.disk_usage is called, which is now robust
                usage = utils.disk_usage(self.destPath, human=True) 
                if usage.free == 0 and usage.total == 0: # Indicates an error from robust disk_usage
                    self.destInfoLabel.setText("Free: N/A")
                else:
                    self.destInfoLabel.setText(f'{usage.free} free')
            else:
                self.destInfoLabel.setText("Free: N/A")
        except Exception as e:
            logging.error(f"Error updating destination info: {e}")
            try:
                self.destInfoLabel.setText("Free: Error")
            except Exception as e2:
                logging.error(f"Critical error setting destInfoLabel fallback text: {e2}")

    def sourceColumn(self):
        # Source title
        self.sourceTitleLabel = QLabel('Press Browse')
        if self.sourcePath:
            self.sourceTitleLabel = QLabel(self.sourcePath.name)
        self.sourceTitleLabel.setMinimumWidth(250)
        self.sourceTitleLabel.setObjectName('source-title')
        self.sourceTitleLabel.setAlignment(QtCore.Qt.AlignCenter)

        # Source info
        self.sourceInfoLabel = QLabel()
        self.sourceInfoLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.sourceInfoLabel.setText(f'0 files, 0 MB')

        # Browse button
        sourceBrowseButton = QPushButton('Browse')
        sourceBrowseButton.clicked.connect(self.browseSource)

        # Full layout
        sourceLayout = QVBoxLayout()
        sourceLayout.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignCenter)
        sourceLayout.addWidget(self.sourceTitleLabel)
        sourceLayout.addWidget(self.sourceInfoLabel)
        sourceLayout.addWidget(sourceBrowseButton)
        return sourceLayout

    def destColumn(self):
        # dest title
        try:
            logging.info(f"DEST_COL_DIAG: Creating destTitleLabel. self.destPath: {self.destPath} (type: {type(self.destPath)})") 
            logging.shutdown()
            dest_display_name = "N/A"

            if isinstance(self.destPath, str):
                try:
                    # If it's a string (potentially NAS path), get basename via Path conversion temporarily for display
                    # This is a controlled point where Path(NAS_string) might occur.
                    logging.info(f"DEST_COL_DIAG: self.destPath is string '{self.destPath}'. Attempting Path() for .name.")
                    logging.shutdown()
                    temp_path_obj = Path(self.destPath)
                    dest_display_name = temp_path_obj.name
                    logging.info(f"DEST_COL_DIAG: For string self.destPath, .name is '{dest_display_name}'")
                    logging.shutdown()
                except Exception as e_str_name:
                    logging.critical(f"DEST_COL_DIAG: CRITICAL - Error getting .name from string self.destPath '{self.destPath}': {e_str_name}. This could be the SIGABRT point for NAS string.", exc_info=True)
                    logging.shutdown()
                    dest_display_name = "Error (str-path)"
            elif isinstance(self.destPath, Path):
                if hasattr(self.destPath, 'name'):
                    try:
                        # If it's a Path object, get .name. This is the SIGABRT point if it's a NAS Path object.
                        logging.info(f"DEST_COL_DIAG: self.destPath is Path. Attempting .name for {self.destPath}")
                        logging.shutdown()
                        dest_display_name = self.destPath.name
                        logging.info(f"DEST_COL_DIAG: For Path self.destPath, .name is '{dest_display_name}'")
                        logging.shutdown()
                    except Exception as e_path_name:
                        logging.critical(f"DEST_COL_DIAG: CRITICAL - Error accessing .name for Path self.destPath {self.destPath}: {e_path_name}. This IS THE SIGABRT point for NAS Path object.", exc_info=True)
                        logging.shutdown()
                        dest_display_name = "Error (path-obj)"
                else:
                    logging.info(f"DEST_COL_DIAG: self.destPath is Path but has no .name attribute: {self.destPath}")
                    logging.shutdown()
                    # dest_display_name remains "N/A"
            else: # self.destPath is None or other type
                logging.info(f"DEST_COL_DIAG: self.destPath is None or type '{type(self.destPath)}'. Using 'N/A'.")
                logging.shutdown()
                # dest_display_name remains "N/A"
            
            self.destTitleLabel = QLabel(str(dest_display_name)) # Ensure string for QLabel
            logging.info(f"DEST_COL_DIAG: QLabel created with text: '{str(dest_display_name)}'")
            logging.shutdown()

        except Exception as e_title:
            logging.critical(f"DEST_COL_DIAG: CRITICAL - Error creating destTitleLabel: {e_title}")
            logging.shutdown()
            # Fallback
            self.destTitleLabel = QLabel("Error")
            try:
                logging.info("DEST_COL_DIAG: destTitleLabel fallback to 'Error'")
                logging.shutdown()
            except: pass

        self.destTitleLabel.setMinimumWidth(250)
        self.destTitleLabel.setObjectName('dest-title')
        self.destTitleLabel.setAlignment(QtCore.Qt.AlignCenter)

        # dest info
        self.destInfoLabel = QLabel()
        self.destInfoLabel.setAlignment(QtCore.Qt.AlignCenter)

        # Browse button
        destBrowseButton = QPushButton('Browse')
        destBrowseButton.clicked.connect(self.browseDest)

        # Full layout
        destLayout = QVBoxLayout()
        destLayout.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignCenter)
        destLayout.addWidget(self.destTitleLabel)
        destLayout.addWidget(self.destInfoLabel)
        destLayout.addWidget(destBrowseButton)

        return destLayout

    def browse(self, start_dir=''):
        """Open a file browser dialog, returns RAW STRING path or None."""
        dialog = QFileDialog()
        folder_path_str = None
        try:
            logging.info("BROWSE_RAW: Calling QFileDialog.getExistingDirectory...")
            logging.shutdown()
            folder_path_str = dialog.getExistingDirectory(None, 'Select Folder', str(start_dir), QFileDialog.ShowDirsOnly)
            logging.info(f"BROWSE_RAW: QFileDialog.getExistingDirectory returned: '{folder_path_str}'")
            logging.shutdown()
            # DO NOT CONVERT TO PATH HERE. Return raw string.
            return folder_path_str 
        except Exception as e:
            logging.critical(f"BROWSE_RAW: CRITICAL PYTHON EXCEPTION: {e}", exc_info=True)
            logging.shutdown()
            return None

    def browseSource(self):
        start_dir = self.sourcePath
        if not self.sourcePath:
            start_dir = Path().home()
        path = self.browse(start_dir=start_dir)

        if path:
            self.sourcePath = path
            if not self.offloader:
                self.initOffloader()
            self.updateSource()

    def browseDest(self):
        raw_path_str_from_dialog = None
        try:
            logging.info("BROWSE_DEST_RAW: Calling self.browse() ...")
            logging.shutdown()
            # Revert diagnostic hardcoding, use self.destPath (which can be str or Path)
            start_dir_for_browse = str(self.destPath if self.destPath is not None else Path().home())
            logging.info(f"BROWSE_DEST_RAW: Using start_dir: '{start_dir_for_browse}' for QFileDialog.")
            logging.shutdown()
            raw_path_str_from_dialog = self.browse(start_dir=start_dir_for_browse)
            logging.info(f"BROWSE_DEST_RAW: self.browse() returned raw string: '{raw_path_str_from_dialog}'")
            logging.shutdown()
        except Exception as e: 
            logging.critical(f"BROWSE_DEST_RAW: CRITICAL PYTHON EXCEPTION calling self.browse(): {e}", exc_info=True)
            logging.shutdown()
            raw_path_str_from_dialog = None

        if raw_path_str_from_dialog:
            # Step 1: Attempt to save raw string to settings
            try:
                logging.info(f"BROWSE_DEST_RAW_STEP1: Attempting to set settings.latest_destination with raw string: '{raw_path_str_from_dialog}'")
                logging.shutdown()
                self.settings.latest_destination = raw_path_str_from_dialog # Settings class handles Path conversion & str()
                logging.info(f"BROWSE_DEST_RAW_STEP1: Successfully set settings.latest_destination.")
                logging.shutdown()
            except Exception as e_settings:
                logging.critical(f"BROWSE_DEST_RAW_STEP1: CRITICAL PYTHON EXCEPTION during settings.latest_destination: {e_settings}", exc_info=True)
                logging.shutdown()
                # Attempt to update UI to show error, then return to prevent further processing
                try:
                    self.destTitleLabel.setText("Error Saving Settings")
                    self.destPathLabel.setText(f"Path: '{raw_path_str_from_dialog[:30]}...'") # Show truncated raw path
                    self.destInfoLabel.setText("Free: Error")
                except Exception as e_ui_settings:
                    logging.error(f"BROWSE_DEST_RAW_STEP1: Failed to set error UI: {e_ui_settings}", exc_info=True)
                    logging.shutdown()
                return # Stop further processing if settings save fails at Python level

            # Step 2: Attempt to create Path object
            path_obj_for_nas = None
            try:
                logging.info(f"BROWSE_DEST_RAW_STEP2: Attempting Path('{raw_path_str_from_dialog}')...")
                logging.shutdown()
                path_obj_for_nas = Path(raw_path_str_from_dialog)
                logging.info(f"BROWSE_DEST_RAW_STEP2: Successfully created Path object: {path_obj_for_nas}")
                logging.shutdown()
            except Exception as e_path_create:
                logging.critical(f"BROWSE_DEST_RAW_STEP2: CRITICAL PYTHON EXCEPTION during Path() creation: {e_path_create}", exc_info=True)
                logging.shutdown()
                try:
                    self.destTitleLabel.setText("Error Processing Path String")
                    self.destPathLabel.setText(f"Path: '{raw_path_str_from_dialog[:30]}...'")
                    self.destInfoLabel.setText("Free: Error")
                except Exception as e_ui_path:
                    logging.error(f"BROWSE_DEST_RAW_STEP2: Failed to set error UI: {e_ui_path}", exc_info=True)
                    logging.shutdown()
                return # Stop further processing
            
            # Step 3: Assign to self.destPath
            try:
                logging.info(f"BROWSE_DEST_RAW_STEP3: Assigning Path object to self.destPath: {path_obj_for_nas}")
                logging.shutdown()
                self.destPath = path_obj_for_nas
                logging.info(f"BROWSE_DEST_RAW_STEP3: Successfully assigned to self.destPath.")
                logging.shutdown()
            except Exception as e_assign:
                logging.critical(f"BROWSE_DEST_RAW_STEP3: CRITICAL PYTHON EXCEPTION during self.destPath assignment: {e_assign}", exc_info=True)
                logging.shutdown()
                # Unlikely to fail here if Path object creation succeeded, but good practice
                return

            # Step 4: Attempt to log self.destPath (which triggers str() on Path object)
            try:
                logging.info(f"BROWSE_DEST_RAW_STEP4: Attempting to log self.destPath (triggers str()): {self.destPath}")
                logging.shutdown()
            except Exception as e_log_str:
                logging.critical(f"BROWSE_DEST_RAW_STEP4: CRITICAL PYTHON EXCEPTION during logging f-string (str(self.destPath)): {e_log_str}", exc_info=True)
                logging.shutdown()
                # If this fails, the crash is str(Path_object) related
                # UI might be in an intermediate state, updateDest might not be called.
                return

            # Step 5: Call updateDest()
            try:
                logging.info(f"BROWSE_DEST_RAW_STEP5: Calling self.updateDest() for path: {self.destPath}")
                logging.shutdown()
                self.updateDest()
                logging.info(f"BROWSE_DEST_RAW_STEP5: self.updateDest() completed for path: {self.destPath}")
                logging.shutdown()
            except Exception as e_update_dest:
                logging.critical(f"BROWSE_DEST_RAW_STEP5: CRITICAL PYTHON EXCEPTION during self.updateDest(): {e_update_dest}", exc_info=True)
                logging.shutdown()
                # UI might be partially updated or error state shown within updateDest already.

            # Original logic for offloader destination update
            if self.offloader: 
                try:
                    logging.info(f"BROWSE_DEST_RAW: Updating offloader destination with: {self.destPath}")
                    logging.shutdown()
                    self.offloader.destination = self.destPath
                    logging.info("BROWSE_DEST_RAW: Successfully updated offloader destination.")
                    logging.shutdown()
                except Exception as e_offloader:
                    logging.error(f"BROWSE_DEST_RAW: Error updating offloader destination: {e_offloader}", exc_info=True)
                    logging.shutdown()
            else:
                logging.warning("BROWSE_DEST_RAW: Offloader not initialized when trying to set destination path.")
                logging.shutdown()
        else:
            logging.warning("BROWSE_DEST_RAW: No path received from self.browse().")
            logging.shutdown()

    def updateSource(self):
        # Update ui
        current_path_obj = None
        path_name = "N/A"

        if isinstance(self.sourcePath, str):
            try:
                # Assuming sourcePath string is a valid local path if it's a string here
                current_path_obj = Path(self.sourcePath)
                path_name = current_path_obj.name
                logging.info(f"UPDATE_SOURCE_DIAG: Converted sourcePath string '{self.sourcePath}' to Path. Name: '{path_name}'")
            except Exception as e:
                logging.error(f"UPDATE_SOURCE_DIAG: Error converting sourcePath string '{self.sourcePath}' to Path: {e}")
                path_name = "Error"
        elif isinstance(self.sourcePath, Path):
            current_path_obj = self.sourcePath
            path_name = self.sourcePath.name
            logging.info(f"UPDATE_SOURCE_DIAG: sourcePath is Path object. Name: '{path_name}'")
        else: # It's None or unexpected type
            logging.info(f"UPDATE_SOURCE_DIAG: sourcePath is None or unexpected type: {type(self.sourcePath)}")
            path_name = "N/A" # Stays N/A or as initialized
        logging.shutdown()

        self.sourceTitleLabel.setText(path_name)
        # pathLabelText should handle str, Path, or None for self.sourcePath
        self.sourcePathLabel.setText(self.pathLabelText(self.sourcePath))

        # Update offload
        if self.offloader:
            if current_path_obj: # current_path_obj is guaranteed to be Path or None here
                self.offloader.source = current_path_obj
                logging.info(f"UPDATE_SOURCE_DIAG: Set offloader.source to Path: {current_path_obj}")
            elif isinstance(self.sourcePath, str): # Should ideally be caught by current_path_obj logic
                # This case is less likely if above logic is correct, but as a fallback:
                try:
                    logging.warning(f"UPDATE_SOURCE_DIAG: sourcePath is string '{self.sourcePath}', attempting direct Path() conversion for offloader.")
                    self.offloader.source = Path(self.sourcePath) 
                except Exception as e_offload_path:
                    logging.error(f"UPDATE_SOURCE_DIAG: Failed to convert string sourcePath '{self.sourcePath}' to Path for offloader: {e_offload_path}")
                    self.offloader.source = None # Or handle error appropriately
            else: # self.sourcePath is None or other non-Path/non-str type
                self.offloader.source = None
                logging.info(f"UPDATE_SOURCE_DIAG: Set offloader.source to None as sourcePath is {type(self.sourcePath)}")
            logging.shutdown()
            self.updateSourceInfo() # This uses self.offloader.source_files which should be updated by Offloader.source setter
        else:
            logging.warning("UPDATE_SOURCE_DIAG: Offloader not initialized.")
            logging.shutdown()

    def updateDest(self):
        """Update all the destination related UI elements. Path label, progress bar"""
        try:
            if self.destPath:
                if isinstance(self.destPath, str):
                    # If it's a string (e.g. NAS path from settings or fresh from dialog that became string)
                    # For display name, try to get basename by converting to Path temporarily
                    try:
                        logging.info(f"UPDATE_DEST_DIAG: self.destPath is string '{self.destPath}', getting .name via Path() for title.")
                        logging.shutdown()
                        temp_path = Path(self.destPath)
                        self.destTitleLabel.setText(temp_path.name)
                    except Exception as e_title_str:
                        logging.error(f"UPDATE_DEST_DIAG: Error getting name for string destPath '{self.destPath}': {e_title_str}")
                        self.destTitleLabel.setText("Error")
                elif isinstance(self.destPath, Path):
                    self.destTitleLabel.setText(self.destPath.name)
                else: # None or other type
                    self.destTitleLabel.setText("N/A")
            else: # self.destPath is None
                self.destTitleLabel.setText("N/A")
            logging.info(f"UPDATE_DEST_DIAG: destTitleLabel set to '{self.destTitleLabel.text()}'")
            logging.shutdown()
        except Exception as e:
            logging.error(f"UPDATE_DEST_DIAG: Error setting destination title label: {e}", exc_info=True)
            try:
                self.destTitleLabel.setText("Error")
            except Exception as e2:
                logging.error(f"UPDATE_DEST_DIAG: Critical error setting destTitleLabel fallback text: {e2}")
            logging.shutdown()

        try:
            path_text = self.pathLabelText(self.destPath) # self.destPath can be str or Path
            self.destPathLabel.setText(path_text)
            logging.info(f"UPDATE_DEST_DIAG: destPathLabel set to '{path_text}'")
            logging.shutdown()
        except Exception as e:
            logging.error(f"UPDATE_DEST_DIAG: Error setting destination path label: {e}", exc_info=True)
            try:
                self.destPathLabel.setText("Error displaying path")
            except Exception as e2:
                logging.error(f"UPDATE_DEST_DIAG: Critical error setting destPathLabel fallback text: {e2}")
            logging.shutdown()

        try:
            self.updateDestInfo() # Call the now robust updateDestInfo
            logging.info("UPDATE_DEST_DIAG: updateDestInfo() called.")
            logging.shutdown()
        except Exception as e:
            logging.error(f"UPDATE_DEST_DIAG: Error calling updateDestInfo from updateDest: {e}", exc_info=True)
            # Fallback for destInfoLabel if updateDestInfo itself fails badly
            try:
                self.destInfoLabel.setText("Free: Error") 
            except Exception as e2:
                logging.error(f"UPDATE_DEST_DIAG: Critical error setting destInfoLabel fallback from updateDest: {e2}")
            logging.shutdown()

        # Save to settings
        try:
            if self.destPath: # Only save if destPath is not None
                # Use the property setter for latest_destination, which handles resolve() and writing to JSON
                # self.destPath here could be a string (if from settings initially, or if browseDest returned string that wasn't converted)
                # or a Path object (if browseDest converted it to Path for self.destPath, or if it was a default local Path).
                # The latest_destination setter expects a path string or Path convertible to string.
                logging.info(f"UPDATE_DEST_DIAG: Attempting to save to settings.latest_destination with value: '{self.destPath}' (type: {type(self.destPath)})")
                logging.shutdown()
                self.settings.latest_destination = str(self.destPath) # Ensure it's a string for the setter
                logging.info(f'UPDATE_DEST_DIAG: Destination successfully saved to settings.latest_destination.')
                logging.shutdown()
            else:
                logging.warning("UPDATE_DEST_DIAG: Attempted to save a None destination path to settings. Skipped.")
                logging.shutdown()
        except Exception as e_save:
            logging.error(f"UPDATE_DEST_DIAG: Error saving destination to settings.latest_destination: {e_save}", exc_info=True)
            logging.shutdown()

    def pathLabel(self, path):
        text = path
        if isinstance(path, Path):
            text = self.pathLabelText(path)
        label = QLabel()
        label.setText(text)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse | QtCore.Qt.TextSelectableByMouse)
        return label

    def pathLabelText(self, path_input: any):
        """Make path shorter if it is too long.
        Return the path as a string"""
        try:
            logging.info(f"PATH_LABEL_TEXT_DIAG: Received path_input: '{path_input}' (type: {type(path_input)})")
            logging.shutdown()
            
            path_to_process = path_input
            path_string = ""

            if path_to_process is None:
                logging.info("PATH_LABEL_TEXT_DIAG: path_input is None, returning 'No path selected'")
                logging.shutdown()
                return 'No path selected'

            if isinstance(path_to_process, str):
                path_string = path_to_process # Already a string
                logging.info(f"PATH_LABEL_TEXT_DIAG: path_input is already string: '{path_string}'")
                logging.shutdown()
            elif isinstance(path_to_process, Path):
                # This is THE DANGER ZONE if path_to_process is a NAS Path object.
                # We must attempt str() conversion here and catch potential SIGABRT source.
                logging.info(f"PATH_LABEL_TEXT_DIAG: path_input is Path object. Attempting str(): {path_to_process}")
                logging.shutdown()
                try:
                    path_string = str(path_to_process)
                    logging.info(f"PATH_LABEL_TEXT_DIAG: str(Path) successful, path_string: '{path_string}'")
                    logging.shutdown()
                except Exception as e_str_conv:
                    # This will catch Python-level exceptions. A SIGABRT will crash before this.
                    logging.critical(f"PATH_LABEL_TEXT_DIAG: CRITICAL PYTHON EXCEPTION - str(Path) FAILED for {path_to_process}: {e_str_conv}", exc_info=True)
                    logging.shutdown()
                    return "Error converting Path to string (SIGABRT likely occurred)"
            else: # Other unexpected type
                logging.warning(f"PATH_LABEL_TEXT_DIAG: path_input is unexpected type '{type(path_to_process)}'. Attempting str().")
                logging.shutdown()
                try:
                    path_string = str(path_to_process)
                    logging.info(f"PATH_LABEL_TEXT_DIAG: str(unexpected type) result: '{path_string}'")
                    logging.shutdown()
                except Exception as e_unknown_str:
                    logging.error(f"PATH_LABEL_TEXT_DIAG: Failed to str(unexpected type {type(path_to_process)}): {e_unknown_str}", exc_info=True)
                    logging.shutdown()
                    return "Error: Invalid path type"

            # Shorten path if it is too long
            if len(path_string) > 50:
                # For shortening, we need a Path object if we don't have one, 
                # or if the original was a string to begin with.
                path_obj_for_parts = None
                if isinstance(path_to_process, Path):
                    path_obj_for_parts = path_to_process # Use original Path obj if available
                else: # It was a string or other, try to make a Path from path_string
                    try:
                        logging.info(f"PATH_LABEL_TEXT_DIAG: Path string ('{path_string}') > 50. Attempting Path() for shortening parts.")
                        logging.shutdown()
                        path_obj_for_parts = Path(path_string) # DANGER for NAS string
                        logging.info(f"PATH_LABEL_TEXT_DIAG: Path(path_string) for shortening successful.")
                        logging.shutdown()
                    except Exception as e_path_conv_parts:
                        logging.critical(f"PATH_LABEL_TEXT_DIAG: CRITICAL - Path(path_string) for shortening FAILED for '{path_string}': {e_path_conv_parts}. This could be SIGABRT for NAS string.", exc_info=True)
                        logging.shutdown()
                        # Return the long string if Path conversion fails, rather than erroring further.
                        return path_string 

                if path_obj_for_parts and hasattr(path_obj_for_parts, 'parts') and path_obj_for_parts.parts:
                    shortened_path_string = f'{path_obj_for_parts.parts[0]}...{path_obj_for_parts.parts[-1]}'
                    logging.info(f"PATH_LABEL_TEXT_DIAG: Shortened path to: '{shortened_path_string}'")
                    logging.shutdown()
                    return shortened_path_string
                else:
                    logging.warning(f"PATH_LABEL_TEXT_DIAG: Path string '{path_string}' > 50 but couldn't get parts. Returning full string.")
                    logging.shutdown()
                    return path_string 
            
            logging.info(f"PATH_LABEL_TEXT_DIAG: Path string '{path_string}' <= 50. Returning as is.")
            logging.shutdown()
            return path_string
        except Exception as e_outer:
            logging.critical(f"PATH_LABEL_TEXT_DIAG: CRITICAL - Outer unhandled exception in pathLabelText for input '{path_input}': {e_outer}", exc_info=True)
            logging.shutdown()
            return "Error processing path (outer)"

    @staticmethod
    def volumes():
        """Return a list of volumes mounted on the system"""
        if sys.platform == 'darwin':
            vols = {}
            for p in psutil.disk_partitions():
                if 'Volumes' in p.mountpoint:
                    if 'Recovery' not in p.mountpoint:
                        vols[p.mountpoint] = psutil.disk_usage(p.mountpoint).total
            if vols:
                logging.debug(vols)
                logging.debug(min(vols, key=vols.get))
            return vols


def run():
    """Run the app"""
    app = QApplication(sys.argv)
    app.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    # app.main = GUI()
    gui = MainWindow()
    sys.exit(app.exec_())


if __name__ == '__main__':
    run()
