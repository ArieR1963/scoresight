from functools import partial
import os
import platform
import datetime
import json
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
    QStyleFactory,
)
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtCore import (
    Qt,
    Signal,
    Slot,
    QTranslator,
    QObject,
    QCoreApplication,
    QEvent,
    QMetaMethod,
    QUrl,
)
from dotenv import load_dotenv
from os import path
from platformdirs import user_data_dir

from api_output import update_out_api
from box_settings_ui_handler import BoxSettingsUIHandler
from camera_info import CameraInfo
from get_camera_info import get_camera_info
from http_server import start_http_server, update_http_server
from ocr_training_data import OCRTrainingDataDialog
from resource_path import resource_path
from screen_capture_source import ScreenCapture
from source_view import ImageViewer
from defaults import (
    default_boxes,
    default_info_for_box_name,
    format_prefixes,
    NUMBER_BASELINE,
    TIME_BASELINE,
    TEXT_BASELINE,
    normalize_settings_dict,
    FieldType,
)

from storage import (
    TextDetectionTargetMemoryStorage,
    fetch_data,
    remove_data,
    store_data,
    store_custom_box_name,
    rename_custom_box_name_in_storage,
    remove_custom_box_name_in_storage,
    fetch_custom_box_names,
)
from obs_websocket import (
    create_obs_scene_from_export,
    open_obs_websocket,
    update_text_source,
)

from template_fields import evaluate_template_field
from text_detection_target import TextDetectionTarget, TextDetectionTargetWithResult
from sc_logging import logger
from uno_ui_handler import UNOUIHandler
from update_check import check_for_updates
from log_view import LogViewerDialog
import file_output
from video_settings import VideoSettingsDialog
from ui_mainwindow import Ui_MainWindow
from ui_about import Ui_Dialog as Ui_About
from ui_connect_obs import Ui_Dialog as Ui_ConnectObs
from ui_url_source import Ui_Dialog as Ui_UrlSource
from ui_screen_capture import Ui_Dialog as Ui_ScreenCapture
from vmix_ui_handler import VMixUIHanlder


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
            widget = None
        else:
            clear_layout(item.layout())


class MainWindow(QMainWindow):
    # add a signal to update sources
    update_sources = Signal(list)
    get_sources = Signal()

    def __init__(self, translator: QTranslator, parent: QObject):
        super(MainWindow, self).__init__()
        self.parent_object = parent
        self.ui = Ui_MainWindow()
        logger.info("Starting ScoreSight")
        self.ui.setupUi(self)
        self.auto_tune_states = {}
        self.pending_vmix_api_plus_presets = {}
        self._auto_enable_binary_after_four_corners = False
        self._set_auto_tune_status("idle")
        self.ui.pushButton_autoTuneStatus.clicked.connect(self.rerunAutoTuneSelected)
        self.translator = translator
        # load env variables
        load_dotenv()
        self.setWindowTitle(f"ScoreSight - v{os.getenv('LOCAL_RELEASE_TAG')}")
        if platform.system() == "Windows":
            # set the icon
            self.setWindowIcon(QIcon(resource_path("icons", "Windows-icon-open.ico")))

        self.menubar = self.menuBar()
        file_menu = self.menubar.addMenu("File")

        # check for updates
        check_for_updates(False)
        file_menu.addAction("Check for Updates", lambda: check_for_updates(True))
        file_menu.addAction("About", self.openAboutDialog)
        file_menu.addAction("View Current Log", self.openLogsDialog)
        file_menu.addAction("Import Configuration", self.importConfiguration)
        file_menu.addAction("Export Configuration", self.exportConfiguration)
        file_menu.addAction("Open Configuration Folder", self.openConfigurationFolder)
        file_menu.addAction("OCR Training Data Setup", self.openOCRTrainingDataDialog)

        # Add "Language" menu
        languageMenu = file_menu.addMenu("Language")

        # Add language options
        self.addLanguageOption(languageMenu, "English (US)", "en_US")
        self.addLanguageOption(languageMenu, "French (France)", "fr_FR")
        self.addLanguageOption(languageMenu, "Spanish (Spain)", "es_ES")
        self.addLanguageOption(languageMenu, "German", "de_DE")
        self.addLanguageOption(languageMenu, "Italian", "it_IT")
        self.addLanguageOption(languageMenu, "Japanese", "ja_JP")
        self.addLanguageOption(languageMenu, "Korean", "ko_KR")
        self.addLanguageOption(languageMenu, "Dutch", "nl_NL")
        self.addLanguageOption(languageMenu, "Polish", "pl_PL")
        self.addLanguageOption(languageMenu, "Portuguese (Brazil)", "pt_BR")
        self.addLanguageOption(languageMenu, "Portuguese (Portugal)", "pt_PT")
        self.addLanguageOption(languageMenu, "Russian", "ru_RU")
        self.addLanguageOption(languageMenu, "Chinese (Simplified)", "zh_CN")

        # add a menu item to change the theme
        theme_menu = file_menu.addMenu("Theme")
        for theme in QStyleFactory.keys():
            theme_menu.addAction(theme, lambda theme=theme: self.setStyleTheme(theme))

        # Hide the menu bar by default
        self.menubar.setVisible(True)

        # Show the menu bar when the Alt key is pressed
        self.installEventFilter(self)

        self.ui.pushButton_connectObs.clicked.connect(self.openOBSConnectModal)

        self.vmixUiHandler = VMixUIHanlder(self.ui, self.addTargetFromVmixApiPlusField)
        self.unoUiHandler = UNOUIHandler(self.ui)
        self.boxSettingsUiHandler = BoxSettingsUIHandler(self.ui)

        self.ui.checkBox_templatefield.toggled.connect(self.makeTemplateField)

        start_http_server()

        self.ui.pushButton_stabilize.setEnabled(True)
        self.ui.pushButton_stabilize.clicked.connect(self.toggleStabilize)

        self.ui.toolButton_topCrop.clicked.connect(self.cropMode)
        # check configuation if crop is enabled
        self.ui.toolButton_topCrop.setChecked(
            fetch_data("scoresight.json", "crop_mode", False)
        )
        self.ui.widget_cropPanel.setVisible(self.ui.toolButton_topCrop.isChecked())
        self.ui.widget_cropPanel.setEnabled(self.ui.toolButton_topCrop.isChecked())
        self.ui.spinBox_leftCrop.valueChanged.connect(
            partial(self.globalSettingsChanged, "left_crop")
        )
        self.ui.spinBox_leftCrop.setValue(fetch_data("scoresight.json", "left_crop", 0))
        self.ui.spinBox_rightCrop.valueChanged.connect(
            partial(self.globalSettingsChanged, "right_crop")
        )
        self.ui.spinBox_rightCrop.setValue(
            fetch_data("scoresight.json", "right_crop", 0)
        )
        self.ui.spinBox_topCrop.valueChanged.connect(
            partial(self.globalSettingsChanged, "top_crop")
        )
        self.ui.spinBox_topCrop.setValue(fetch_data("scoresight.json", "top_crop", 0))
        self.ui.spinBox_bottomCrop.valueChanged.connect(
            partial(self.globalSettingsChanged, "bottom_crop")
        )
        self.ui.spinBox_bottomCrop.setValue(
            fetch_data("scoresight.json", "bottom_crop", 0)
        )
        self.ui.checkBox_enableOutAPI.toggled.connect(
            partial(self.globalSettingsChanged, "enable_out_api")
        )
        self.ui.checkBox_enableOutAPI.setChecked(
            fetch_data("scoresight.json", "enable_out_api", False)
        )

        # connect toolButton_rotate
        self.ui.toolButton_rotate.clicked.connect(self.rotateImage)

        self.ui.widget_detectionCadence.setVisible(True)
        self.ui.horizontalSlider_detectionCadence.setValue(
            fetch_data("scoresight.json", "detection_cadence", 5)
        )
        self.ui.horizontalSlider_detectionCadence.valueChanged.connect(
            self.detectionCadenceChanged
        )
        self.ui.toolButton_addBox.clicked.connect(self.addBox)
        self.ui.toolButton_removeBox.clicked.connect(self.removeCustomBox)

        self.video_settings_dialog = None
        self.ui.toolButton_videoSettings.clicked.connect(self.openVideoSettings)

        self.ui.lineEdit_api_url.textChanged.connect(
            partial(self.globalSettingsChanged, "out_api_url")
        )
        self.ui.lineEdit_api_url.setText(
            fetch_data("scoresight.json", "out_api_url", "")
        )

        self.ui.checkBox_enableOutAPI.toggled.connect(
            partial(self.globalSettingsChanged, "enable_out_api")
        )
        self.ui.checkBox_enableOutAPI.setChecked(
            fetch_data("scoresight.json", "enable_out_api", False)
        )
        self.ui.comboBox_api_encode.currentTextChanged.connect(
            partial(self.globalSettingsChanged, "out_api_encoding")
        )
        self.ui.comboBox_api_encode.setCurrentIndex(
            self.ui.comboBox_api_encode.findText(
                fetch_data("scoresight.json", "out_api_encoding", "JSON")
            )
        )
        self.ui.comboBox_outApiMethod.currentTextChanged.connect(
            partial(self.globalSettingsChanged, "out_api_method")
        )
        self.ui.comboBox_outApiMethod.setCurrentIndex(
            self.ui.comboBox_outApiMethod.findText(
                fetch_data("scoresight.json", "out_api_method", "POST")
            )
        )

        self.obs_websocket_client = None

        ocr_models = [
            "Daktronics",
            "General Scoreboard",
            "General Fonts (English)",
            "General Scoreboard Large",
            "Load External OCR Model",
        ]
        self.ui.comboBox_ocrModel.addItems(ocr_models)
        # default to General Scoreboard
        ocr_model_from_storage = fetch_data("scoresight.json", "ocr_model", 1)
        if type(ocr_model_from_storage) == str:
            ocr_model_from_storage = 4
        self.ui.comboBox_ocrModel.setCurrentIndex(ocr_model_from_storage)

        self.ui.frame_source_view.setEnabled(False)
        self.ui.groupBox_target_settings.setEnabled(False)
        self.ui.pushButton_makeBox.clicked.connect(self.makeBox)
        self.ui.pushButton_removeBox.clicked.connect(self.removeBox)
        self.ui.tableWidget_boxes.itemClicked.connect(self.listItemClicked)
        # connect the edit triggers
        self.ui.tableWidget_boxes.itemDoubleClicked.connect(self.editBoxName)
        self.ui.pushButton_refresh_sources.clicked.connect(
            lambda: self.get_sources.emit()
        )
        self.detectionTargetsStorage = TextDetectionTargetMemoryStorage()
        self.detectionTargetsStorage.data_changed.connect(self.detectionTargetsChanged)
        self.ui.pushButton_createOBSScene.clicked.connect(self.createOBSScene)
        self.ui.pushButton_selectFolder.clicked.connect(self.selectOutputFolder)
        self.ui.toolButton_trashFolder.clicked.connect(self.clearOutputFolder)
        self.ui.pushButton_stopUpdates.toggled.connect(self.toggleStopUpdates)
        self.ui.comboBox_ocrModel.currentIndexChanged.connect(self.ocrModelChanged)
        self.ui.toolButton_zoomReset.clicked.connect(self.resetZoom)
        self.ui.toolButton_osd.toggled.connect(self.toggleOSD)
        self.ui.comboBox_boxDisplayStyle.currentIndexChanged.connect(
            partial(self.globalSettingsChanged, "box_display_style")
        )
        box_display_style = fetch_data("scoresight.json", "box_display_style", 3)
        self.ui.comboBox_boxDisplayStyle.setCurrentIndex(
            box_display_style if type(box_display_style) == int else 3
        )

        self.ui.checkBox_updateOnchange.toggled.connect(self.toggleUpdateOnChange)

        # populate the tableWidget_boxes with the default and custom boxes
        custom_boxes_names = fetch_custom_box_names()

        for box_name in [box["name"] for box in default_boxes] + custom_boxes_names:
            item = QTableWidgetItem(
                QIcon(resource_path("icons", "circle-x.svg")),
                box_name,
            )
            item.setData(Qt.ItemDataRole.UserRole, "unchecked")
            self.ui.tableWidget_boxes.insertRow(self.ui.tableWidget_boxes.rowCount())
            self.ui.tableWidget_boxes.setItem(
                self.ui.tableWidget_boxes.rowCount() - 1, 0, item
            )
            disabledItem = QTableWidgetItem()
            disabledItem.setFlags(Qt.ItemFlag.NoItemFlags)
            self.ui.tableWidget_boxes.setItem(
                self.ui.tableWidget_boxes.rowCount() - 1, 1, disabledItem
            )

        self.image_viewer = None
        self.obs_connect_modal = None
        self.source_name = None
        self.updateOCRResults = True
        self.log_dialog = None
        if fetch_data("scoresight.json", "open_on_startup", False):
            logger.info("Opening log dialog on startup")
            self.openLogsDialog()

        if fetch_data("scoresight.json", "obs"):
            self.connectObs()

        self.out_folder = fetch_data("scoresight.json", "output_folder")
        if self.out_folder:
            if not path.exists(self.out_folder):
                self.out_folder = None
                remove_data("scoresight.json", "output_folder")
            else:
                self.ui.lineEdit_folder.setText(self.out_folder)

        self.first_csv_append = True
        self.last_aggregate_save = datetime.datetime.now()
        self.ui.checkBox_saveCsv.toggled.connect(
            partial(self.globalSettingsChanged, "save_csv")
        )
        self.ui.checkBox_saveCsv.setChecked(
            fetch_data("scoresight.json", "save_csv", False)
        )
        self.ui.checkBox_saveXML.toggled.connect(
            partial(self.globalSettingsChanged, "save_xml")
        )
        self.ui.checkBox_saveXML.setChecked(
            fetch_data("scoresight.json", "save_xml", False)
        )
        self.ui.comboBox_appendMethod.currentIndexChanged.connect(
            partial(self.globalSettingsChanged, "append_method")
        )
        self.ui.horizontalSlider_aggsPerSecond.valueChanged.connect(
            partial(self.globalSettingsChanged, "aggs_per_second")
        )
        self.ui.comboBox_appendMethod.setCurrentIndex(
            fetch_data("scoresight.json", "append_method", 3)
        )
        self.ui.horizontalSlider_aggsPerSecond.setValue(
            fetch_data("scoresight.json", "aggs_per_second", 5)
        )
        self.ui.checkBox_updateOnchange.setChecked(
            fetch_data("scoresight.json", "update_on_change", True)
        )
        self.ui.checkBox_vmix_send_same.setChecked(
            fetch_data("scoresight.json", "vmix_send_same", False)
        )
        self.ui.checkBox_vmix_send_same.toggled.connect(
            partial(self.globalSettingsChanged, "vmix_send_same")
        )

        self.ui.pushButton_saveOCRTrainingData.clicked.connect(self.saveOCRTrainingData)
        self.ui.pushButton_saveOCRTrainingData.setChecked(
            fetch_data("scoresight.json", "save_ocr_training_data", False)
        )

        self.ui.toolButton_speed.clicked.connect(self.toggleSpeed)
        self.ui.toolButton_playPauseFile.clicked.connect(self.togglePlaybackPause)
        self.ui.toolButton_rewindToStartFile.clicked.connect(self.seekPlaybackToStart)
        self.ui.toolButton_rewindFile.clicked.connect(
            lambda: self.seekPlaybackFrames(-150)
        )
        self.ui.toolButton_forwardFile.clicked.connect(
            lambda: self.seekPlaybackFrames(150)
        )

        self.update_sources.connect(self.updateSources)
        self.get_sources.connect(self.getSources)
        self.get_sources.emit()

    def setStyleTheme(self, theme):
        QApplication.instance().setStyle(theme)

    def toggleSpeed(self):
        # check the current speed and toggle it
        # possible speeds are x2, x4, x8, x16, x32 and back to x1
        # change the button text to the current speed
        # change the speed of the image viewer
        if self.image_viewer and self.image_viewer.timerThread is not None:
            speed = self.image_viewer.timerThread.getSpeed()
            if speed == 1:
                speed = 2
            elif speed == 2:
                speed = 4
            elif speed == 4:
                speed = 8
            elif speed == 8:
                speed = 16
            elif speed == 16:
                speed = 32
            else:
                speed = 1
            self.image_viewer.timerThread.setSpeed(speed)
            self.ui.toolButton_speed.setText(f"x{speed}")

    def _setFilePlaybackControls(self, enabled: bool, paused: bool = False):
        self.ui.toolButton_rewindToStartFile.setEnabled(enabled)
        self.ui.toolButton_rewindFile.setEnabled(enabled)
        self.ui.toolButton_playPauseFile.setEnabled(enabled)
        self.ui.toolButton_forwardFile.setEnabled(enabled)
        self.ui.toolButton_playPauseFile.setText("Play" if paused else "Pause")

    def togglePlaybackPause(self):
        if not self.image_viewer or not self.image_viewer.timerThread:
            return
        if self.image_viewer.getCameraInfo().type != CameraInfo.CameraType.FILE:
            return
        paused = self.image_viewer.timerThread.togglePaused()
        self._setFilePlaybackControls(True, paused)

    def seekPlaybackFrames(self, delta_frames: int):
        if not self.image_viewer or not self.image_viewer.timerThread:
            return
        if self.image_viewer.getCameraInfo().type != CameraInfo.CameraType.FILE:
            return
        self.image_viewer.timerThread.seekRelativeFrames(delta_frames)

    def seekPlaybackToStart(self):
        if not self.image_viewer or not self.image_viewer.timerThread:
            return
        if self.image_viewer.getCameraInfo().type != CameraInfo.CameraType.FILE:
            return
        self.image_viewer.timerThread.seekToStart()

    def saveOCRTrainingData(self):
        self.globalSettingsChanged(
            "save_ocr_training_data", self.ui.pushButton_saveOCRTrainingData.isChecked()
        )

    def openVideoSettings(self):
        # only allow opening the video settings for an OpenCV type source
        if not self.image_viewer or self.image_viewer is None:
            return

        if self.image_viewer.getCameraInfo().type != CameraInfo.CameraType.OPENCV:
            return

        if self.video_settings_dialog is None:
            # open the logs dialog
            self.video_settings_dialog = VideoSettingsDialog()
            self.video_settings_dialog.setWindowTitle("Video Settings")

        self.video_settings_dialog.init_ui(self.image_viewer.getCameraCapture())

        # show the dialog, non modal
        self.video_settings_dialog.show()

    def rotateImage(self):
        # store the rotation in the scoresight.json
        rotation = fetch_data("scoresight.json", "rotation", 0)
        rotation += 90
        if rotation >= 360:
            rotation = 0
        self.globalSettingsChanged("rotation", rotation)

    def cropMode(self):
        # if the toolButton_topCrop is unchecked, go to crop mode
        if self.ui.toolButton_topCrop.isChecked():
            self.ui.widget_cropPanel.setVisible(True)
            self.ui.widget_cropPanel.setEnabled(True)
            self.globalSettingsChanged("crop_mode", True)
        else:
            self.ui.widget_cropPanel.setVisible(False)
            self.ui.widget_cropPanel.setEnabled(False)
            self.globalSettingsChanged("crop_mode", False)

    def globalSettingsChanged(self, settingName, value):
        store_data("scoresight.json", settingName, value)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                # deselect any selected item
                self.itemSelected(None)
                if self.image_viewer is not None:
                    self.image_viewer.selectBox(None)
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowDeactivate and self.menubar.isVisible():
            self.menubar.setVisible(False)
        super().changeEvent(event)

    def changeLanguage(self, locale):
        locale_file = resource_path("translations", f"scoresight_{locale}.qm")
        logger.info(f"Changing language to {locale_file}")
        if not self.translator.load(locale_file):
            logger.error(f"Could not load translation for {locale_file}")
            return
        appInstance = QApplication.instance()
        if appInstance:
            logger.info(f"installing translator for {locale}")
            appInstance.installTranslator(self.translator)
            try:
                self.ui.retranslateUi(self)
            except Exception as e:
                logger.error(f"Error retranslating UI: {e}")

    def addLanguageOption(self, menu: QMenu, language_name: str, locale: str):
        menu.addAction(language_name, lambda: self.changeLanguage(locale))

    def toggleUpdateOnChange(self, value):
        self.globalSettingsChanged("update_on_change", value)
        if self.image_viewer:
            self.image_viewer.setUpdateOnChange(value)

    def importConfiguration(self):
        # open a file dialog to select a configuration file
        file, _ = QFileDialog.getOpenFileName(
            self, "Open Configuration File", "", "Configuration Files (*.json)"
        )
        if not file:
            return
        try:
            with open(file, "r") as f:
                config = json.load(f)
        except Exception:
            # show an error qmessagebox
            logger.error("Error loading configuration file")
            QMessageBox.critical(
                self,
                "Error",
                "Error loading configuration file",
                QMessageBox.StandardButton.Ok,
            )
            return

        boxes = config
        four_corners = None
        vmix_api_plus = None
        # New format: {"boxes": [...], "four_corners": [[x,y], ...]}
        if isinstance(config, dict):
            boxes = config.get("boxes")
            four_corners = config.get("four_corners")
            vmix_api_plus = config.get("vmix_api_plus")

        if not isinstance(boxes, list) or not self.detectionTargetsStorage.loadBoxesFromDict(boxes):
            logger.error("Error loading configuration file")
            QMessageBox.critical(
                self,
                "Error",
                "Error loading configuration file",
                QMessageBox.StandardButton.Ok,
            )
            return

        if isinstance(config, dict):
            if isinstance(four_corners, list) and len(four_corners) == 4:
                store_data("scoresight.json", "four_corners", four_corners)
                if self.image_viewer is not None:
                    self.image_viewer.setFourCorners(four_corners)
                    self.fourCornersApplied(four_corners)
            else:
                remove_data("scoresight.json", "four_corners")
                if self.image_viewer is not None:
                    self.image_viewer.setFourCorners(None)
                    self.ui.pushButton_fourCorner.setChecked(False)

            if isinstance(vmix_api_plus, dict):
                host = vmix_api_plus.get("host")
                port = vmix_api_plus.get("port")
                mapping = vmix_api_plus.get("mapping")
                send_same = vmix_api_plus.get("send_same")

                if isinstance(host, str):
                    store_data("scoresight.json", "vmix_api_plus_host", host)
                    if hasattr(self.vmixUiHandler, "lineEdit_vmixApiPlusHost"):
                        self.vmixUiHandler.lineEdit_vmixApiPlusHost.setText(host)
                if isinstance(port, str):
                    store_data("scoresight.json", "vmix_api_plus_port", port)
                    if hasattr(self.vmixUiHandler, "lineEdit_vmixApiPlusPort"):
                        self.vmixUiHandler.lineEdit_vmixApiPlusPort.setText(port)
                if isinstance(mapping, dict):
                    store_data("scoresight.json", "vmix_api_plus_mapping", mapping)
                if isinstance(send_same, bool):
                    store_data("scoresight.json", "vmix_send_same", send_same)
                    self.ui.checkBox_vmix_send_same.setChecked(send_same)

    def exportConfiguration(self):
        # open a file dialog to select the output file
        file, _ = QFileDialog.getSaveFileName(
            self, "Save Configuration File", "", "Configuration Files (*.json)"
        )
        if not file:
            return
        config = {
            "boxes": self.detectionTargetsStorage.getBoxesForStorage(),
            "four_corners": fetch_data("scoresight.json", "four_corners"),
            "vmix_api_plus": {
                "host": fetch_data("scoresight.json", "vmix_api_plus_host", "localhost"),
                "port": fetch_data("scoresight.json", "vmix_api_plus_port", "8088"),
                "mapping": fetch_data("scoresight.json", "vmix_api_plus_mapping", {}),
                "send_same": fetch_data("scoresight.json", "vmix_send_same", False),
            },
        }
        with open(file, "w") as f:
            json.dump(config, f, indent=2)

    def openOCRTrainingDataDialog(self):
        # open the OCR training data dialog
        dialog = OCRTrainingDataDialog()
        dialog.setWindowTitle("OCR Training Data Setup")
        dialog.exec()

    def openConfigurationFolder(self):
        # open the configuration folder in the file explorer
        QDesktopServices.openUrl(
            QUrl(
                "file:///" + user_data_dir("scoresight"), QUrl.ParsingMode.TolerantMode
            )
        )

    def toggleOSD(self, value):
        if self.image_viewer:
            self.image_viewer.toggleOSD(value)

    def resetZoom(self):
        if self.image_viewer:
            self.image_viewer.resetZoom()

    def detectionCadenceChanged(self, detections_per_second):
        self.globalSettingsChanged("detection_cadence", detections_per_second)
        if self.image_viewer and self.image_viewer.timerThread:
            # convert the detections_per_second to milliseconds
            self.image_viewer.timerThread.update_frame_interval = (
                1000 / detections_per_second
            )

    def ocrModelChanged(self, index: int | str):
        ocrModel = None
        if index == 4:
            # load a custom OCR model
            file, _ = QFileDialog.getOpenFileName(
                self, "Open OCR Model File", "", "OCR Model Files (*.traineddata)"
            )
            if not file:
                return
            # get absolute file path
            file = path.abspath(file)
            self.globalSettingsChanged("ocr_model", file)
            ocrModel = file
        elif type(index) == int:
            self.globalSettingsChanged("ocr_model", index)
            ocrModel = index
        elif type(index) == str:
            # check if the index is a valid existing file
            if path.exists(index):
                self.globalSettingsChanged("ocr_model", index)
                ocrModel = index

        # update the ocr model in the text detector
        if (
            self.image_viewer
            and self.image_viewer.timerThread
            and self.image_viewer.timerThread.textDetector
        ):
            self.image_viewer.timerThread.textDetector.setOcrModel(ocrModel)

    def openLogsDialog(self):
        if self.log_dialog is None:
            # open the logs dialog
            self.log_dialog = LogViewerDialog()
            self.log_dialog.setWindowTitle("Logs")

        # show the dialog, non modal
        self.log_dialog.show()

    def openAboutDialog(self):
        # open the about dialog
        about_dialog = QDialog()
        about_dialog_ui = Ui_About()
        about_dialog_ui.setupUi(about_dialog)
        about_dialog.setWindowTitle("About ScoreSight")
        about_dialog.exec()

    def toggleStabilize(self):
        if not self.image_viewer:
            return
        # start or stop the stabilization
        self.image_viewer.toggleStabilization(self.ui.pushButton_stabilize.isChecked())

    def toggleStopUpdates(self, value):
        self.updateOCRResults = not value
        # change the text on the button
        self.ui.pushButton_stopUpdates.setText(
            self.translator.translate("MainWindow", "Resume Updates")
            if value
            else self.translator.translate("MainWindow", "Stop Updates")
        )

    def selectOutputFolder(self):
        # open a Qt dialog to select the output folder
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            fetch_data("scoresight.json", "output_folder", ""),
            options=QFileDialog.Option.ShowDirsOnly,
        )
        if folder and len(folder) > 0:
            self.ui.lineEdit_folder.setText(folder)
            self.out_folder = folder
            self.globalSettingsChanged("output_folder", folder)

    def clearOutputFolder(self):
        # clear the output folder
        self.ui.lineEdit_folder.setText("")
        self.out_folder = None
        remove_data("scoresight.json", "output_folder")

    def detectionTargetsChanged(self, detectionTargets: list[TextDetectionTarget]):
        for box in detectionTargets:
            logger.debug(f"Change: Detection target: {box.name}")
            # change the list icon to green checkmark
            items = self.ui.tableWidget_boxes.findItems(
                box.name, Qt.MatchFlag.MatchExactly
            )
            if len(items) == 0:
                logger.warning(f"Item not found: {box.name}. Adding it to the list.")
                # add the item to the list
                self.ui.tableWidget_boxes.insertRow(
                    self.ui.tableWidget_boxes.rowCount()
                )
                item = QTableWidgetItem(box.name)
                self.ui.tableWidget_boxes.setItem(
                    self.ui.tableWidget_boxes.rowCount() - 1, 0, item
                )
                disabledItem = QTableWidgetItem()
                disabledItem.setFlags(Qt.ItemFlag.NoItemFlags)
                self.ui.tableWidget_boxes.setItem(
                    self.ui.tableWidget_boxes.rowCount() - 1, 1, disabledItem
                )
            else:
                item = items[0]

            if box.settings is None or not box.settings["templatefield"]:
                # this is a detection target
                item.setIcon(QIcon(resource_path("icons", "circle-check.svg")))
                item.setData(Qt.ItemDataRole.UserRole, "checked")
            else:
                # this is a template field
                item.setIcon(QIcon(resource_path("icons", "template-field.svg")))
                item.setData(Qt.ItemDataRole.UserRole, "templatefield")

        self.vmixUiHandler.updatevMixTable(detectionTargets)
        self.unoUiHandler.updateUNOTable(detectionTargets)

        # if save_csv is enabled, truncate the aggregate file
        if self.ui.checkBox_saveCsv.isChecked() and self.out_folder:
            csv_output_file_path = path.abspath(
                path.join(self.out_folder, "results.csv")
            )
            try:
                with open(csv_output_file_path, "w") as f:
                    f.write("")
                self.first_csv_append = True
                self.last_aggregate_save = datetime.datetime.now()
            except Exception as e:
                logger.error(f"Error truncating aggregate file: {e}")

    def listItemClicked(self, item):
        user_role = item.data(Qt.ItemDataRole.UserRole)
        if user_role in ["checked", "templatefield"] and item.column() == 0:
            # enable the remove box button and disable the make box button
            self.ui.pushButton_makeBox.setEnabled(False)
            self.ui.pushButton_removeBox.setEnabled(user_role == "checked")
            self.ui.groupBox_target_settings.setEnabled(user_role == "checked")
            self.boxSettingsUiHandler.populateSettings(item.text())
        else:
            # enable the make box button and disable the remove box button
            self.ui.pushButton_removeBox.setEnabled(False)
            self.ui.pushButton_makeBox.setEnabled(item.column() == 0)
            self.ui.groupBox_target_settings.setEnabled(False)
            self.boxSettingsUiHandler.populateSettings("")

        if item.column() == 0:
            # if this is not a default box - enable the template field checkbox
            if item.text() not in [box["name"] for box in default_boxes]:
                self.ui.checkBox_templatefield.setEnabled(True)
                self.ui.lineEdit_templatefield.setEnabled(True)
            else:
                self.ui.checkBox_templatefield.setEnabled(False)
                self.ui.lineEdit_templatefield.setEnabled(False)

        # notify the image viewer to select the box
        if self.image_viewer:
            self.image_viewer.selectBox(item.text())

    def openOBSConnectModal(self):
        # disable OBS options
        self.ui.lineEdit_sceneName.setEnabled(False)
        self.ui.checkBox_recreate.setEnabled(False)
        self.ui.pushButton_createOBSScene.setEnabled(False)

        # load the ui from "connect_obs.ui"
        self.obs_modal_ui = Ui_ConnectObs()
        self.obs_connect_modal = QDialog()
        self.obs_modal_ui.setupUi(self.obs_connect_modal)
        self.obs_connect_modal.setWindowTitle("Connect to OBS")

        # connect the "connect" button to a function
        self.obs_modal_ui.pushButton_connect.clicked.connect(self.connectObs)

        # load the saved data from scoresight.json
        obs_data = fetch_data("scoresight.json", "obs")
        if obs_data:
            self.obs_modal_ui.lineEdit_ip.setText(obs_data["ip"])
            self.obs_modal_ui.lineEdit_port.setText(obs_data["port"])
            self.obs_modal_ui.lineEdit_password.setText(obs_data["password"])
        # show the modal
        self.obs_connect_modal.show()
        # focus the connect button
        self.obs_modal_ui.pushButton_connect.setFocus()

    def connectObs(self):
        # open a websocket connection to OBS using obs_websocket.py
        # enable the save button in the modal if the connection is successful
        if self.obs_connect_modal is not None:
            self.obs_websocket_client = open_obs_websocket(
                {
                    "ip": self.obs_modal_ui.lineEdit_ip.text(),
                    "port": self.obs_modal_ui.lineEdit_port.text(),
                    "password": self.obs_modal_ui.lineEdit_password.text(),
                }
            )
        else:
            self.obs_websocket_client = open_obs_websocket(
                fetch_data("scoresight.json", "obs")
            )
        if not self.obs_websocket_client:
            # show error in label_error
            if self.obs_connect_modal:
                self.obs_modal_ui.label_error.setText("Cannot connect to OBS")
            return

        # connection was successful
        if self.obs_connect_modal:
            store_data(
                "scoresight.json",
                "obs",
                {
                    "ip": self.obs_modal_ui.lineEdit_ip.text(),
                    "port": self.obs_modal_ui.lineEdit_port.text(),
                    "password": self.obs_modal_ui.lineEdit_password.text(),
                },
            )
            self.obs_connect_modal.close()

        self.ui.lineEdit_sceneName.setEnabled(True)
        self.ui.checkBox_recreate.setEnabled(True)
        self.ui.pushButton_createOBSScene.setEnabled(True)

        logger.info("OBS: Connected")

    @Slot()
    def getSources(self):
        self.update_sources.emit(get_camera_info())

    @Slot(list)
    def updateSources(self, camera_sources: list[CameraInfo]):
        self.reset_playing_source()
        # clear all the items after "Screen Capture"
        for i in range(4, self.ui.comboBox_camera_source.count()):
            self.ui.comboBox_camera_source.removeItem(4)

        # populate the combobox with the sources
        for source in camera_sources:
            self.ui.comboBox_camera_source.addItem(source.description, source)

        self.ui.comboBox_camera_source.setEnabled(True)
        currentIndexChangedSignal = QMetaMethod.fromSignal(
            self.ui.comboBox_camera_source.currentIndexChanged
        )
        if self.ui.comboBox_camera_source.isSignalConnected(currentIndexChangedSignal):
            self.ui.comboBox_camera_source.currentIndexChanged.disconnect()
        self.ui.comboBox_camera_source.currentIndexChanged.connect(self.sourceChanged)

        # enable the source view frame
        self.ui.frame_source_view.setEnabled(True)

        selected_source_from_storage = fetch_data("scoresight.json", "source_selected")
        if type(selected_source_from_storage) == str:
            logger.info(
                "Source selected from storage: %s", selected_source_from_storage
            )
            # check if the source is a file path
            if path.exists(selected_source_from_storage):
                logger.info("File exists: %s", selected_source_from_storage)
                self.ui.comboBox_camera_source.blockSignals(True)
                self.ui.comboBox_camera_source.setCurrentIndex(1)
                self.ui.comboBox_camera_source.blockSignals(False)
                self.source_name = selected_source_from_storage
                self.sourceSelectionSucessful()
            else:
                # select the last selected source
                self.ui.comboBox_camera_source.setCurrentText(
                    selected_source_from_storage
                )

    def reset_playing_source(self):
        if self.image_viewer:
            # remove the image viewer from the layout frame_for_source_view_label
            self.ui.frame_for_source_view_label.layout().removeWidget(self.image_viewer)
            self.image_viewer.close()
            self.image_viewer = None
        # add a label with markdown text
        label_select_source = QLabel("### Open a Camera or Load a File")
        label_select_source.setTextFormat(Qt.TextFormat.MarkdownText)
        label_select_source.setEnabled(False)
        label_select_source.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clear_layout(self.ui.frame_for_source_view_label.layout())
        self.ui.frame_for_source_view_label.layout().addWidget(label_select_source)

    def sourceChanged(self, index):
        # get the source name from the combobox
        self.source_name = None
        self.ui.groupBox_sb_info.setEnabled(False)
        self.ui.tableWidget_boxes.setEnabled(False)
        self.ui.widget_viewTools.setEnabled(False)
        self.ui.widget_cropPanel.setEnabled(False)
        if self.ui.comboBox_camera_source.currentIndex() == 0:
            self.reset_playing_source()
            return
        elif self.ui.comboBox_camera_source.currentIndex() == 1:
            logger.info("Open File selection dialog")
            # open a file dialog to select a video file
            file, _ = QFileDialog.getOpenFileName(
                self, "Open Video File", "", "Video Files (*.mp4 *.avi *.mov)"
            )
            if not file or not path.exists(file):
                # no file selected - change source to "Select a source"
                logger.error("No file selected")
                self.ui.comboBox_camera_source.setCurrentText("Select a source")
                return
            else:
                logger.info("File selected: %s", file)
            self.source_name = file
        elif self.ui.comboBox_camera_source.currentIndex() == 2:
            # open a dialog to enter the url
            url_dialog = QDialog()
            ui_urlsource = Ui_UrlSource()
            ui_urlsource.setupUi(url_dialog)
            url_dialog.setWindowTitle("URL Source")
            # focus on url input
            ui_urlsource.lineEdit_url.setFocus()
            url_dialog.exec()  # wait for the dialog to close
            # check if the dialog was accepted
            if url_dialog.result() != QDialog.DialogCode.Accepted:
                self.ui.comboBox_camera_source.setCurrentIndex(0)
                return
            self.source_name = ui_urlsource.lineEdit_url.text()
            if self.source_name == "":
                self.ui.comboBox_camera_source.setCurrentIndex(0)
                return
        elif self.ui.comboBox_camera_source.currentIndex() == 3:
            # open a dialog to select the screen
            screen_dialog = QDialog()
            ui_screencapture = Ui_ScreenCapture()
            ui_screencapture.setupUi(screen_dialog)
            # set width and height of the dialog
            screen_dialog.setFixedWidth(400)

            screen_dialog.setWindowTitle(
                QCoreApplication.translate(
                    "MainWindow", "Screen Capture Selection", None
                )
            )
            # populate comboBox_window with the available windows
            ui_screencapture.comboBox_window.clear()
            ui_screencapture.comboBox_window.addItem(
                QCoreApplication.translate(
                    "MainWindow", "Capture the entire screen", None
                ),
                -1,
            )
            for window in ScreenCapture.list_windows():
                ui_screencapture.comboBox_window.addItem(window[0], window[1])
            screen_dialog.exec()
            # check if the dialog was accepted
            if screen_dialog.result() != QDialog.DialogCode.Accepted:
                self.ui.comboBox_camera_source.setCurrentIndex(0)
                return
            # get the window ID from the comboBox_window
            window_id = ui_screencapture.comboBox_window.currentData()
            self.source_name = window_id

        # store the source selection in scoresight.json
        self.globalSettingsChanged("source_selected", self.source_name)
        self.sourceSelectionSucessful()

    def itemSelected(self, item_name):
        if item_name is None:
            # clear the selected item
            self.ui.tableWidget_boxes.clearSelection()
            self.ui.groupBox_target_settings.setEnabled(False)
            self.boxSettingsUiHandler.populateSettings("")
            return
        # select the item in the tableWidget_boxes
        items = self.ui.tableWidget_boxes.findItems(
            item_name, Qt.MatchFlag.MatchExactly
        )
        if len(items) == 0:
            return
        item = items[0]
        item.setSelected(True)
        self.ui.tableWidget_boxes.setCurrentItem(item)
        self.listItemClicked(item)

    def fourCornersApplied(self, corners):
        # Leave the button visually off after apply; checked state is only for
        # "selection mode", not for "four-corner is active".
        self.ui.pushButton_fourCorner.blockSignals(True)
        self.ui.pushButton_fourCorner.setChecked(False)
        self.ui.pushButton_fourCorner.blockSignals(False)
        self._auto_enable_binary_after_four_corners = True
        self._maybeEnableBinaryPreviewAfterFourCorners()

    def _setBinaryPreview(self, enabled: bool):
        if not self.image_viewer or not self.image_viewer.timerThread:
            return
        current = self.image_viewer.timerThread.show_binary
        if current != enabled:
            self.image_viewer.toggleBinary()
        self.ui.pushButton_binary.setChecked(enabled)

    def _maybeEnableBinaryPreviewAfterFourCorners(self):
        if not self._auto_enable_binary_after_four_corners:
            return
        if not self.image_viewer or not self.image_viewer.timerThread:
            return
        self._setBinaryPreview(True)
        self._auto_enable_binary_after_four_corners = False

    def _resetActiveFieldStateForNewSource(self):
        self.auto_tune_states.clear()
        self._set_auto_tune_status("idle")
        self._auto_enable_binary_after_four_corners = False
        self.detectionTargetsStorage.clear()
        self._setFilePlaybackControls(False)
        self.ui.pushButton_binary.setChecked(False)
        self.ui.pushButton_fourCorner.setChecked(False)
        self.ui.tableWidget_boxes.clearSelection()
        for row in range(self.ui.tableWidget_boxes.rowCount()):
            item = self.ui.tableWidget_boxes.item(row, 0)
            if item is None:
                continue
            item.setIcon(QIcon(resource_path("icons", "circle-x.svg")))
            item.setData(Qt.ItemDataRole.UserRole, "unchecked")
            value_item = self.ui.tableWidget_boxes.item(row, 1)
            if value_item is not None:
                value_item.setText("")

    def sourceSelectionSucessful(self):
        if self.ui.comboBox_camera_source.currentIndex() == 0:
            return

        self.ui.frame_source_view.setEnabled(False)
        self._resetActiveFieldStateForNewSource()
        remove_data("scoresight.json", "four_corners")

        if self.ui.comboBox_camera_source.currentIndex() == 1:
            if self.source_name is None or not path.exists(self.source_name):
                logger.error("No file selected")
                self.ui.comboBox_camera_source.setCurrentIndex(0)
                return
            logger.info("Loading file selected: %s", self.source_name)
            camera_info = CameraInfo(
                self.source_name,
                self.source_name,
                self.source_name,
                CameraInfo.CameraType.FILE,
            )
        elif self.ui.comboBox_camera_source.currentIndex() == 2:
            if self.source_name is None or self.source_name == "":
                logger.error("No url entered")
                self.ui.comboBox_camera_source.setCurrentIndex(0)
                return
            logger.info("Loading url: %s", self.source_name)
            camera_info = CameraInfo(
                self.source_name,
                self.source_name,
                self.source_name,
                CameraInfo.CameraType.URL,
            )
        elif self.ui.comboBox_camera_source.currentIndex() == 3:
            if self.source_name is None:
                logger.error("No screen capture selected")
                self.ui.comboBox_camera_source.setCurrentIndex(0)
                return
            logger.info("Loading screen capture: %s", self.source_name)
            camera_info = CameraInfo(
                self.source_name,
                self.source_name,
                self.source_name,
                CameraInfo.CameraType.SCREEN_CAPTURE,
            )
        else:
            if self.ui.comboBox_camera_source.currentData() is None:
                return

            logger.info(
                "Loading camera: %s", self.ui.comboBox_camera_source.currentText()
            )
            camera_info = self.ui.comboBox_camera_source.currentData()

        if self.image_viewer:
            # remove the image viewer from the layout frame_for_source_view_label
            self.ui.frame_for_source_view_label.layout().removeWidget(self.image_viewer)
            self.image_viewer.close()
            self.image_viewer = None

        # clear self.ui.frame_for_source_view_label
        clear_layout(self.ui.frame_for_source_view_label.layout())

        # set the pixmap to the image viewer
        self.image_viewer = ImageViewer(
            camera_info,
            self.fourCornersApplied,
            self.detectionTargetsStorage,
            self.itemSelected,
            self.boxPlacementFinished,
        )
        self.ui.toolButton_videoSettings.setEnabled(
            camera_info.type == CameraInfo.CameraType.OPENCV
        )
        self._setFilePlaybackControls(camera_info.type == CameraInfo.CameraType.FILE)
        self.image_viewer.first_frame_received_signal.connect(
            self.cameraConnectedEnableUI
        )
        self.image_viewer.error_signal.connect(self.updateError)
        self.ocrModelChanged(fetch_data("scoresight.json", "ocr_model", 1))

        # set the image viewer to the layout frame_for_source_view_label
        self.ui.frame_for_source_view_label.layout().addWidget(self.image_viewer)

    def cameraConnectedEnableUI(self):
        if self.image_viewer is None:
            self.updateError("Image viewer is None")
            return
        self.ui.pushButton_fourCorner.toggled.connect(
            self.image_viewer.toggleFourCorner
        )
        self.ui.pushButton_binary.clicked.connect(self.image_viewer.toggleBinary)
        if self.image_viewer.timerThread:
            self.image_viewer.timerThread.ocr_result_signal.connect(self.ocrResult)
            self.image_viewer.timerThread.update_error.connect(self.updateError)

        # enable groupBox_sb_info
        self.ui.groupBox_sb_info.setEnabled(True)
        self.ui.tableWidget_boxes.setEnabled(True)
        self.ui.frame_source_view.setEnabled(True)
        self.ui.widget_viewTools.setEnabled(True)
        self.ui.widget_cropPanel.setEnabled(True)

        self._maybeEnableBinaryPreviewAfterFourCorners()
        self.updateError(None)

    def updateError(self, error):
        if not error:
            return
        logger.error(error)
        self.ui.frame_source_view.setEnabled(True)
        self.ui.widget_viewTools.setEnabled(False)
        self.ui.widget_cropPanel.setEnabled(False)

    def ocrResult(self, results: list[TextDetectionTargetWithResult]):
        self._auto_tune_update(results)

        # update template fields
        for targetWithResult in results:
            if not targetWithResult.settings["templatefield"]:
                continue
            template_result = evaluate_template_field(results, targetWithResult)
            targetWithResult.result = (
                template_result if template_result is not None else ""
            )
            targetWithResult.result_state = (
                TextDetectionTargetWithResult.ResultState.Success
                if targetWithResult.result is not None
                else TextDetectionTargetWithResult.ResultState.Empty
            )

        # update the table widget value items
        for targetWithResult in results:
            if (
                targetWithResult.result_state
                == TextDetectionTargetWithResult.ResultState.Success
            ):
                items = self.ui.tableWidget_boxes.findItems(
                    targetWithResult.name, Qt.MatchFlag.MatchExactly
                )
                if len(items) == 0:
                    continue
                item = items[0]
                # get the value (1 column) of the item
                item = self.ui.tableWidget_boxes.item(item.row(), 1)
                item.setText(targetWithResult.result)

        if not self.updateOCRResults:
            # don't update the results, the user has disabled updates
            return

        update_http_server(results)

        if self.ui.checkBox_enableOutAPI.isChecked():
            update_out_api(results)

        # update vmix and uno
        self.vmixUiHandler.updatevMixOutputs(results)
        if self.unoUiHandler.unoUpdater is not None:
            self.unoUiHandler.unoUpdater.update_uno(results)

        if self.out_folder is None:
            return

        if not path.exists(path.abspath(self.out_folder)):
            self.out_folder = None
            remove_data("scoresight.json", "output_folder")
            logger.warning("Output folder does not exist")
            return

        # check if enough time has passed since last file save according to aggs per second
        if (
            datetime.datetime.now() - self.last_aggregate_save
        ).total_seconds() < 1.0 / self.ui.horizontalSlider_aggsPerSecond.value():
            return

        self.last_aggregate_save = datetime.datetime.now()

        # update the obs scene sources with the results, use update_text_source
        for targetWithResult in results:
            if targetWithResult.result is None:
                continue
            if (
                targetWithResult.settings is not None
                and "skip_empty" in targetWithResult.settings
                and targetWithResult.settings["skip_empty"]
                and len(targetWithResult.result) == 0
            ):
                continue
            if (
                targetWithResult.result_state
                != TextDetectionTargetWithResult.ResultState.Success
            ):
                continue

            if (
                self.obs_websocket_client is not None
                and targetWithResult.settings is not None
            ):
                # find the source name for the target from the default boxes
                update_text_source(
                    self.obs_websocket_client,
                    targetWithResult.settings["obs_source_name"],
                    targetWithResult.result,
                )

        # save the results to text files
        file_output.save_text_files(
            results, self.out_folder, self.ui.comboBox_appendMethod.currentIndex()
        )

        # save the results to a csv file
        if self.ui.checkBox_saveCsv.isChecked():
            file_output.save_csv(
                results,
                self.out_folder,
                self.ui.comboBox_appendMethod.currentIndex(),
                self.first_csv_append,
            )

        # save the results to an xml file
        if self.ui.checkBox_saveXML.isChecked():
            file_output.save_xml(
                results,
                self.out_folder,
            )

    def addBox(self):
        # add a new box to the tableWidget_boxes
        # find the number of custom boxes
        custom_boxes = []
        for i in range(self.ui.tableWidget_boxes.rowCount()):
            item = self.ui.tableWidget_boxes.item(i, 0)
            if item.text() not in [o["name"] for o in default_boxes]:
                custom_boxes.append(item.text())

        i = len(custom_boxes)
        new_box_name = f"Custom {i + 1}"
        custom_boxes_names = fetch_data("scoresight.json", "custom_boxes_names", [])
        # find if the name already exists
        while new_box_name in custom_boxes or new_box_name in custom_boxes_names:
            i += 1
            new_box_name = f"Custom {i + 1}"

        store_custom_box_name(new_box_name)
        item = QTableWidgetItem(
            QIcon(resource_path("icons", "circle-x.svg")),
            new_box_name,
        )
        item.setData(Qt.ItemDataRole.UserRole, "unchecked")
        self.ui.tableWidget_boxes.insertRow(self.ui.tableWidget_boxes.rowCount())
        self.ui.tableWidget_boxes.setItem(
            self.ui.tableWidget_boxes.rowCount() - 1, 0, item
        )
        disabledItem = QTableWidgetItem()
        disabledItem.setFlags(Qt.ItemFlag.NoItemFlags)
        self.ui.tableWidget_boxes.setItem(
            self.ui.tableWidget_boxes.rowCount() - 1, 1, disabledItem
        )

    def _ensureTargetInList(self, target_name: str):
        items = self.ui.tableWidget_boxes.findItems(target_name, Qt.MatchFlag.MatchExactly)
        if len(items) > 0:
            return items[0]

        if target_name not in [o["name"] for o in default_boxes]:
            existing_custom = fetch_custom_box_names()
            if target_name not in existing_custom:
                store_custom_box_name(target_name)

        item = QTableWidgetItem(
            QIcon(resource_path("icons", "circle-x.svg")),
            target_name,
        )
        item.setData(Qt.ItemDataRole.UserRole, "unchecked")
        self.ui.tableWidget_boxes.insertRow(self.ui.tableWidget_boxes.rowCount())
        self.ui.tableWidget_boxes.setItem(
            self.ui.tableWidget_boxes.rowCount() - 1, 0, item
        )
        disabledItem = QTableWidgetItem()
        disabledItem.setFlags(Qt.ItemFlag.NoItemFlags)
        self.ui.tableWidget_boxes.setItem(
            self.ui.tableWidget_boxes.rowCount() - 1, 1, disabledItem
        )
        return item

    def _fieldTypeForPreset(self, preset_index: int) -> int:
        if preset_index in [0, 1, 2, 3]:
            return FieldType.TIME
        if preset_index in [9, 10]:
            return FieldType.TEXT
        return FieldType.NUMBER

    def _applyPresetToTarget(self, target_name: str, preset_index: int):
        item_obj = self.detectionTargetsStorage.find_item_by_name(target_name)
        if item_obj is None:
            return False

        settings = dict(item_obj.settings or {})
        preset_index = (
            preset_index
            if isinstance(preset_index, int) and 0 <= preset_index < len(format_prefixes)
            else 12
        )
        field_type = self._fieldTypeForPreset(preset_index)
        baseline = NUMBER_BASELINE
        if field_type == FieldType.TIME:
            baseline = TIME_BASELINE
        elif field_type == FieldType.TEXT:
            baseline = TEXT_BASELINE

        settings.update(baseline)
        settings["type"] = field_type
        settings["format_regex"] = format_prefixes[preset_index]
        item_obj.settings = settings
        self.detectionTargetsStorage.edit_item(target_name, item_obj)
        return True

    def addTargetFromVmixApiPlusField(
        self, target_name: str, field_name: str, preset_index: int, draw_box: bool
    ) -> bool:
        name = (target_name or "").strip()
        vmix_field = (field_name or "").strip()
        if not name or not vmix_field:
            return False

        row_item = self._ensureTargetInList(name)
        self.ui.tableWidget_boxes.setCurrentItem(row_item)
        self.listItemClicked(row_item)

        mapping = fetch_data("scoresight.json", "vmix_api_plus_mapping", {})
        if not isinstance(mapping, dict):
            mapping = {}
        mapping[name] = vmix_field
        store_data("scoresight.json", "vmix_api_plus_mapping", mapping)

        if not self._applyPresetToTarget(name, int(preset_index)):
            self.pending_vmix_api_plus_presets[name] = int(preset_index)

        if draw_box:
            self.makeBox()
        return True

    def removeCustomBox(self):
        item = self.ui.tableWidget_boxes.currentItem()
        if not item:
            logger.info("No item selected")
            return
        if item.column() != 0:
            item = self.ui.tableWidget_boxes.item(item.row(), 0)
        self.removeBox()
        remove_custom_box_name_in_storage(item.text())
        # only allow removing custom boxes
        if item.text() in [o["name"] for o in default_boxes]:
            logger.info("Cannot remove default box")
            return
        # remove the selected item from the tableWidget_boxes
        self.ui.tableWidget_boxes.removeRow(item.row())

    def editBoxName(self, item):
        if item.text() in [o["name"] for o in default_boxes]:
            # dont allow editing default boxes
            return
        new_name, ok = QInputDialog.getText(
            self, "Edit Box Name", "New Name:", text=item.text()
        )
        old_name = item.text()
        if ok and new_name != "" and new_name != old_name:
            # check if name doesn't exist already
            for i in range(self.ui.tableWidget_boxes.rowCount()):
                if new_name == self.ui.tableWidget_boxes.item(i, 0).text():
                    logger.info("Name '%s' already exists", new_name)
                    return
            # rename the item in the tableWidget_boxes
            rename_custom_box_name_in_storage(old_name, new_name)
            item.setText(new_name)
            # rename the item in the detectionTargetsStorage
            if not self.detectionTargetsStorage.rename_item(old_name, new_name):
                logger.info("Error renaming item in application storage")
                return
            else:
                # check if the item role isn't "templatefield"
                if item.data(Qt.ItemDataRole.UserRole) != "templatefield":
                    # remove the item from the tableWidget_boxes
                    self.ui.tableWidget_boxes.removeRow(item.row())

    def makeBox(self):
        item = self.ui.tableWidget_boxes.currentItem()
        if not item:
            return
        if item.column() != 0:
            item = self.ui.tableWidget_boxes.item(item.row(), 0)
        if not self.image_viewer:
            self._set_auto_tune_status("select source")
            return
        self.image_viewer.beginBoxPlacement(item.text())
        self._set_auto_tune_status(f"draw {item.text()}")

    def boxPlacementFinished(self, item_name, rect):
        items = self.ui.tableWidget_boxes.findItems(item_name, Qt.MatchFlag.MatchExactly)
        if len(items) == 0:
            return
        item = items[0]
        item.setIcon(QIcon(resource_path("icons/circle-check.svg")))
        item.setData(Qt.ItemDataRole.UserRole, "checked")
        self.ui.tableWidget_boxes.setCurrentItem(item)
        self.listItemClicked(item)

        info = default_info_for_box_name(item_name)
        existing_item = self.detectionTargetsStorage.find_item_by_name(item_name)
        if existing_item is None:
            self.detectionTargetsStorage.add_item(
                TextDetectionTarget(
                    rect.x(),
                    rect.y(),
                    rect.width(),
                    rect.height(),
                    item_name,
                    normalize_settings_dict({}, info),
                )
            )
        else:
            existing_item.setX(rect.x())
            existing_item.setY(rect.y())
            existing_item.setWidth(rect.width())
            existing_item.setHeight(rect.height())
            self.detectionTargetsStorage.edit_item(item_name, existing_item)

        pending_preset_index = self.pending_vmix_api_plus_presets.pop(item_name, None)
        if pending_preset_index is not None:
            self._applyPresetToTarget(item_name, int(pending_preset_index))

        self._auto_tune_start(item_name)

    def removeBox(self):
        item = self.ui.tableWidget_boxes.currentItem()
        if not item:
            return
        # change the list icon to red x
        item.setIcon(QIcon(resource_path("icons", "circle-x.svg")))
        item.setData(Qt.ItemDataRole.UserRole, "unchecked")
        self.listItemClicked(item)
        self.detectionTargetsStorage.remove_item(item.text())
        self.auto_tune_states.pop(item.text(), None)

    def _auto_tune_candidates(self, field_type: int) -> list[dict]:
        if field_type == FieldType.TIME:
            return [
                {"binarization_method": 2, "cleanup_thresh": 0.0, "dilate": 1, "skew": 2, "vscale": 10, "rescale_patch": True},
                {"binarization_method": 2, "cleanup_thresh": 0.0, "dilate": 2, "skew": 2, "vscale": 10, "rescale_patch": True},
                {"binarization_method": 1, "cleanup_thresh": 0.0, "dilate": 1, "skew": 2, "vscale": 10, "rescale_patch": True},
                {"binarization_method": 2, "cleanup_thresh": 0.01, "dilate": 1, "skew": 1, "vscale": 9, "rescale_patch": True},
                {"binarization_method": 0, "cleanup_thresh": 0.0, "dilate": 1, "skew": 2, "vscale": 10, "rescale_patch": True},
            ]
        if field_type == FieldType.NUMBER:
            return [
                {"binarization_method": 2, "cleanup_thresh": 0.0, "dilate": 1, "skew": 0, "vscale": 10, "rescale_patch": True},
                {"binarization_method": 2, "cleanup_thresh": 0.0, "dilate": 2, "skew": 0, "vscale": 10, "rescale_patch": True},
                {"binarization_method": 1, "cleanup_thresh": 0.0, "dilate": 1, "skew": 0, "vscale": 10, "rescale_patch": True},
                {"binarization_method": 2, "cleanup_thresh": 0.01, "dilate": 1, "skew": 0, "vscale": 9, "rescale_patch": True},
                {"binarization_method": 0, "cleanup_thresh": 0.0, "dilate": 1, "skew": 0, "vscale": 10, "rescale_patch": True},
            ]
        return [
            {"binarization_method": 0, "cleanup_thresh": 0.0, "dilate": 1, "skew": 0, "vscale": 10, "rescale_patch": True},
            {"binarization_method": 2, "cleanup_thresh": 0.0, "dilate": 1, "skew": 0, "vscale": 10, "rescale_patch": True},
            {"binarization_method": 1, "cleanup_thresh": 0.0, "dilate": 1, "skew": 0, "vscale": 10, "rescale_patch": True},
        ]

    def _auto_tune_apply(self, item_name: str, settings_updates: dict) -> bool:
        item_obj = self.detectionTargetsStorage.find_item_by_name(item_name)
        if item_obj is None:
            return False
        new_settings = dict(item_obj.settings)
        new_settings.update(settings_updates)
        item_obj.settings = new_settings
        self.detectionTargetsStorage.edit_item(item_name, item_obj)
        return True

    def _auto_tune_start(self, item_name: str):
        item_obj = self.detectionTargetsStorage.find_item_by_name(item_name)
        if item_obj is None or item_obj.settings is None:
            return
        field_type = item_obj.settings.get("type", FieldType.NUMBER)
        candidates = self._auto_tune_candidates(field_type)
        if not candidates:
            return
        # restart tuning state for this item if it already exists
        self.auto_tune_states[item_name] = {
            "field_type": field_type,
            "candidates": candidates,
            "scores": [0.0 for _ in candidates],
            "samples_per_candidate": 8,
            "current_idx": 0,
            "sample_count": 0,
            "prev_text": "",
        }
        self._auto_tune_apply(item_name, candidates[0])
        self._set_auto_tune_status(f"tuning {item_name} (1/{len(candidates)})")
        logger.info("Auto-tune started for '%s' (%d candidates)", item_name, len(candidates))

    def rerunAutoTuneSelected(self):
        item = self.ui.tableWidget_boxes.currentItem()
        if item is None:
            self._set_auto_tune_status("select field")
            return
        if item.column() != 0:
            item = self.ui.tableWidget_boxes.item(item.row(), 0)
        item_name = item.text()
        if self.detectionTargetsStorage.find_item_by_name(item_name) is None:
            self._set_auto_tune_status("field not active")
            return
        self._auto_tune_start(item_name)

    def _auto_tune_score(self, target_with_result: TextDetectionTargetWithResult, prev_text: str) -> float:
        score = 0.0
        if target_with_result.result_state == TextDetectionTargetWithResult.ResultState.Success:
            score += 2.0
            if target_with_result.result and len(target_with_result.result) > 0:
                score += 0.2
            if prev_text and target_with_result.result == prev_text:
                score += 0.4
        elif (
            target_with_result.result_state
            == TextDetectionTargetWithResult.ResultState.SameNoChange
        ):
            score += 1.4
        elif (
            target_with_result.result_state
            == TextDetectionTargetWithResult.ResultState.FailedFilter
        ):
            score -= 0.7
        else:
            score -= 0.5
        return score

    def _auto_tune_finish(self, item_name: str):
        state = self.auto_tune_states.get(item_name)
        if state is None:
            return
        best_idx = max(range(len(state["scores"])), key=lambda i: state["scores"][i])
        best_settings = state["candidates"][best_idx]
        self._auto_tune_apply(item_name, best_settings)
        self.auto_tune_states.pop(item_name, None)
        current_item = self.ui.tableWidget_boxes.currentItem()
        if current_item is not None and current_item.text() == item_name:
            self.boxSettingsUiHandler.populateSettings(item_name)
        logger.info(
            "Auto-tune finished for '%s' -> candidate %d (score %.2f)",
            item_name,
            best_idx,
            state["scores"][best_idx],
        )
        if self.auto_tune_states:
            next_item = next(iter(self.auto_tune_states))
            next_state = self.auto_tune_states[next_item]
            self._set_auto_tune_status(
                f"tuning {next_item} ({next_state['current_idx'] + 1}/{len(next_state['candidates'])})"
            )
        else:
            self._set_auto_tune_status("done")

    def _auto_tune_update(self, results: list[TextDetectionTargetWithResult]):
        if not self.auto_tune_states:
            return
        by_name = {r.name: r for r in results}
        done_items = []
        for item_name, state in self.auto_tune_states.items():
            if item_name not in by_name:
                continue
            target_result = by_name[item_name]
            idx = state["current_idx"]
            state["scores"][idx] += self._auto_tune_score(target_result, state["prev_text"])
            state["prev_text"] = target_result.result
            state["sample_count"] += 1
            if state["sample_count"] < state["samples_per_candidate"]:
                continue

            # Move to next candidate, or finalize if we've tested all.
            state["sample_count"] = 0
            next_idx = idx + 1
            if next_idx >= len(state["candidates"]):
                done_items.append(item_name)
                continue
            state["current_idx"] = next_idx
            state["prev_text"] = ""
            self._auto_tune_apply(item_name, state["candidates"][next_idx])
            self._set_auto_tune_status(
                f"tuning {item_name} ({next_idx + 1}/{len(state['candidates'])})"
            )

        for item_name in done_items:
            self._auto_tune_finish(item_name)

    def _set_auto_tune_status(self, status: str):
        if not hasattr(self.ui, "pushButton_autoTuneStatus"):
            return
        self.ui.pushButton_autoTuneStatus.setText(f"Auto-tune: {status}")

    def makeTemplateField(self, toggled: bool):
        item = self.ui.tableWidget_boxes.currentItem()
        if not item:
            return

        if not toggled:
            self.removeBox()
            return

        # create a new box on self.image_viewer with the name of the selected item from the tableWidget_boxes
        # change the list icon to green checkmark
        item.setIcon(QIcon(resource_path("icons", "template-field.svg")))
        item.setData(Qt.ItemDataRole.UserRole, "templatefield")

        self.detectionTargetsStorage.add_item(
            TextDetectionTarget(
                0,
                0,
                0,
                0,
                item.text(),
                normalize_settings_dict({"templatefield": True}, None),
            )
        )

        self.listItemClicked(item)

    def createOBSScene(self):
        # get the scene name from the lineEdit_sceneName
        scene_name = self.ui.lineEdit_sceneName.text()
        # clear or create a new scene
        create_obs_scene_from_export(self.obs_websocket_client, scene_name)

    # on destroy, close the OBS connection
    def closeEvent(self, event):
        logger.info("Closing")
        if self.image_viewer:
            self.image_viewer.close()
            self.image_viewer = None

        if self.log_dialog:
            self.log_dialog.close()
            self.log_dialog = None

        # store the boxes to scoresight.json
        self.detectionTargetsStorage.saveBoxesToStorage()
        if self.obs_websocket_client:
            # destroy the client object
            self.obs_websocket_client = None

        super().closeEvent(event)
