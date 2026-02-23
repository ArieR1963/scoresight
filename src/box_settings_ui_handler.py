from functools import partial
from typing import Callable
from PySide6.QtCore import QSignalBlocker, QCoreApplication, QTranslator
from PySide6.QtWidgets import (
    QSpinBox,
    QWidget,
    QLabel,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
)

from defaults import (
    default_info_for_box_name,
    normalize_settings_dict,
    format_prefixes,
    FieldType,
)
from storage import TextDetectionTargetMemoryStorage
from ui_mainwindow import Ui_MainWindow
from sc_logging import logger


class BoxSettingsUIHandler:
    def __init__(
        self,
        ui: Ui_MainWindow,
        translator: QTranslator | None = None,
        locale_provider: Callable[[], str] | None = None,
    ):
        self.ui = ui
        self.translator = translator
        self.locale_provider = locale_provider
        self.sliderValueInputs = {}
        self.shotclockPresets = [
            {"label_key": "Custom", "max": None, "regex": None},
            {
                "label_key": "Basketball (24)",
                "max": 24,
                "regex": r"^(?:(?:[6-9]|1\d|2[0-4])|(?:[0-5](?:\.[0-9])?))$",
            },
            {
                "label_key": "NCAA Basketball (30)",
                "max": 30,
                "regex": r"^(?:(?:[6-9]|[12]\d|30)|(?:[0-5](?:\.[0-9])?))$",
            },
            {
                "label_key": "Waterpolo (24)",
                "max": 24,
                "regex": r"^(?:(?:1\d|2[0-4])|(?:[0-9](?:\.[0-9])?))$",
            },
            {
                "label_key": "Korfball (25)",
                "max": 25,
                "regex": r"^(?:0\d|1\d|2[0-5])$",
            },
            {
                "label_key": "Roller Hockey (45)",
                "max": 45,
                "regex": r"^(?:(?:[6-9]|[1-3]\d|4[0-5])|(?:[0-5](?:\.[0-9])?))$",
            },
        ]
        self.widget_shotclock = None
        self.label_shotclockMax = None
        self.label_shotclockFormat = None
        self.comboBox_shotclockPreset = None
        self.spinBox_shotclockMax = None
        self.lineEdit_shotclockFormatInfo = None
        self._setupEditableSliderValues()
        self._setupShotclockControls()
        self.boxSettingsUiSetup()
        self.detectionTargetsStorage = TextDetectionTargetMemoryStorage()

    def _setupShotclockControls(self):
        self.widget_shotclock = QWidget(self.ui.groupBox_target_settings)
        layout = QHBoxLayout(self.widget_shotclock)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label_shotclockMax = QLabel(self.widget_shotclock)
        self.comboBox_shotclockPreset = QComboBox(self.widget_shotclock)
        self.spinBox_shotclockMax = QSpinBox(self.widget_shotclock)
        self.spinBox_shotclockMax.setRange(1, 59)
        self.spinBox_shotclockMax.setValue(39)
        self.spinBox_shotclockMax.setSuffix(" s")
        self.spinBox_shotclockMax.setKeyboardTracking(False)
        self.lineEdit_shotclockFormatInfo = QLineEdit(self.widget_shotclock)
        self.lineEdit_shotclockFormatInfo.setReadOnly(False)
        self.lineEdit_shotclockFormatInfo.setMinimumWidth(180)
        self.label_shotclockFormat = QLabel(self.widget_shotclock)

        layout.addWidget(self.label_shotclockMax)
        layout.addWidget(self.comboBox_shotclockPreset)
        layout.addWidget(self.spinBox_shotclockMax)
        layout.addWidget(self.label_shotclockFormat)
        layout.addWidget(self.lineEdit_shotclockFormatInfo)
        self.retranslateShotclockControls()

        # Place shotclock controls directly below the target row.
        self.ui.gridLayout_6.addWidget(self.widget_shotclock, 1, 2, 1, 2)
        self._setShotclockControlsVisible(False)

    def _tr(self, text: str) -> str:
        locale = self.locale_provider() if self.locale_provider is not None else ""
        locale = self._normalize_locale(locale)
        locale_overrides = {
            "ja_JP": {
                "Custom": "カスタム",
                "Shotclock": "ショットクロック",
                "Basketball (24)": "バスケットボール (24)",
                "NCAA Basketball (30)": "NCAA バスケットボール (30)",
                "Waterpolo (24)": "水球 (24)",
                "Korfball (25)": "コーフボール (25)",
                "Roller Hockey (45)": "ローラーホッケー (45)",
            },
            "nl_NL": {
                "Custom": "Aangepast",
                "Shotclock": "Shotklok",
                "Basketball (24)": "Basketbal (24)",
                "NCAA Basketball (30)": "NCAA Basketbal (30)",
                "Waterpolo (24)": "Waterpolo (24)",
                "Korfball (25)": "Korfbal (25)",
                "Roller Hockey (45)": "Rolschaatshockey (45)",
            },
        }
        manual = locale_overrides.get(locale, {}).get(text)
        if manual:
            return manual
        if self.translator is not None:
            translated = self.translator.translate("MainWindow", text)
            if translated and translated != text:
                return translated
        return QCoreApplication.translate("MainWindow", text)

    @staticmethod
    def _normalize_locale(locale: str) -> str:
        l = (locale or "").replace("-", "_")
        ll = l.lower()
        if ll.startswith("jp_") or ll.startswith("ja"):
            return "ja_JP"
        if ll.startswith("nl"):
            return "nl_NL"
        return l

    def retranslateShotclockControls(self):
        if self.comboBox_shotclockPreset is None:
            return
        try:
            current_index = self.comboBox_shotclockPreset.currentIndex()
        except RuntimeError:
            return
        self.comboBox_shotclockPreset.blockSignals(True)
        self.comboBox_shotclockPreset.clear()
        for i, preset in enumerate(self.shotclockPresets):
            self.comboBox_shotclockPreset.addItem(
                self._tr(str(preset["label_key"])),
                i,
            )
        if current_index < 0:
            current_index = 0
        self.comboBox_shotclockPreset.setCurrentIndex(
            max(0, min(current_index, self.comboBox_shotclockPreset.count() - 1))
        )
        self.comboBox_shotclockPreset.blockSignals(False)
        if self.label_shotclockMax is not None:
            try:
                self.label_shotclockMax.setText(self._tr("Shotclock"))
            except RuntimeError:
                self.label_shotclockMax = None
        if self.label_shotclockFormat is not None:
            try:
                self.label_shotclockFormat.setText(self._tr("Format"))
            except RuntimeError:
                self.label_shotclockFormat = None
        if self.lineEdit_shotclockFormatInfo is not None:
            try:
                self.lineEdit_shotclockFormatInfo.setPlaceholderText(self._tr("Format"))
            except RuntimeError:
                self.lineEdit_shotclockFormatInfo = None

    def translationDebugInfo(self) -> dict:
        raw_locale = self.locale_provider() if self.locale_provider is not None else ""
        normalized_locale = self._normalize_locale(raw_locale)
        keys = [
            "Custom",
            "Shotclock",
            "Basketball (24)",
            "NCAA Basketball (30)",
            "Waterpolo (24)",
            "Korfball (25)",
            "Roller Hockey (45)",
        ]
        translated = {k: self._tr(k) for k in keys}
        current_items = []
        if self.comboBox_shotclockPreset is not None:
            current_items = [
                self.comboBox_shotclockPreset.itemText(i)
                for i in range(self.comboBox_shotclockPreset.count())
            ]
        return {
            "raw_locale": raw_locale,
            "normalized_locale": normalized_locale,
            "translated": translated,
            "current_items": current_items,
        }

    def _replaceLabelWithSpinBox(self, label_widget, minimum, maximum, suffix=""):
        container = label_widget.parentWidget()
        if container is None or container.layout() is None:
            return None
        layout = container.layout()
        spin = QSpinBox(container)
        spin.setRange(minimum, maximum)
        spin.setAlignment(label_widget.alignment())
        spin.setMinimumSize(label_widget.minimumSize())
        spin.setMaximumWidth(70)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        layout.replaceWidget(label_widget, spin)
        label_widget.hide()
        return spin

    def _setupEditableSliderValues(self):
        conf_input = self._replaceLabelWithSpinBox(
            self.ui.label_conf_thresh_value,
            self.ui.horizontalSlider_conf_thresh.minimum(),
            self.ui.horizontalSlider_conf_thresh.maximum(),
            "%",
        )
        cleanup_input = self._replaceLabelWithSpinBox(
            self.ui.label_cleanup_value,
            self.ui.horizontalSlider_cleanup.minimum(),
            self.ui.horizontalSlider_cleanup.maximum(),
            "%",
        )
        dilate_input = self._replaceLabelWithSpinBox(
            self.ui.label_dilate_value,
            self.ui.horizontalSlider_dilate.minimum(),
            self.ui.horizontalSlider_dilate.maximum(),
        )
        skew_input = self._replaceLabelWithSpinBox(
            self.ui.label_skew_value,
            self.ui.horizontalSlider_skew.minimum(),
            self.ui.horizontalSlider_skew.maximum(),
        )
        vscale_input = self._replaceLabelWithSpinBox(
            self.ui.label_vscale_value,
            self.ui.horizontalSlider_vscale.minimum(),
            self.ui.horizontalSlider_vscale.maximum(),
        )
        self.sliderValueInputs = {
            "conf": (self.ui.horizontalSlider_conf_thresh, conf_input),
            "cleanup": (self.ui.horizontalSlider_cleanup, cleanup_input),
            "dilate": (self.ui.horizontalSlider_dilate, dilate_input),
            "skew": (self.ui.horizontalSlider_skew, skew_input),
            "vscale": (self.ui.horizontalSlider_vscale, vscale_input),
        }

        for _, pair in self.sliderValueInputs.items():
            slider, spin = pair
            if spin is None:
                continue
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)

    def _setShotclockControlsVisible(self, visible: bool):
        if self.widget_shotclock is None:
            return
        self.widget_shotclock.setVisible(visible)
        self.widget_shotclock.setEnabled(visible)
        # For shotclock targets, use dedicated max/preset controls instead of
        # the generic format row.
        self.ui.widget_7.setVisible(not visible)
        self.ui.widget_7.setEnabled(not visible)
        self.ui.comboBox_formatPrefix.setVisible(not visible)
        self.ui.comboBox_formatPrefix.setEnabled(not visible)

    def _buildShotclockRegex(self, max_seconds: int) -> str:
        max_seconds = max(1, min(int(max_seconds), 59))
        if max_seconds < 10:
            return f"^0?[0-{max_seconds}]$"
        tens = max_seconds // 10
        ones = max_seconds % 10
        if ones == 9:
            return f"^[0-{tens}]\\d$"
        if tens == 0:
            return f"^0?[0-{ones}]$"
        return f"^(?:[0-{tens - 1}]\\d|{tens}[0-{ones}])$"

    def _selectedShotclockPreset(self):
        if self.comboBox_shotclockPreset is None:
            return None
        preset_index = self.comboBox_shotclockPreset.currentData()
        if preset_index is None:
            return None
        if int(preset_index) < 0 or int(preset_index) >= len(self.shotclockPresets):
            return None
        return self.shotclockPresets[int(preset_index)]

    def _isShotClockTarget(self, item_name: str, item_obj) -> bool:
        if "shot" in item_name.lower() and "clock" in item_name.lower():
            return True
        if item_obj is None or item_obj.settings is None:
            return False
        return item_obj.settings.get("shotclock_max") is not None

    def _applyShotclockSettings(self, max_seconds: int, regex: str):
        max_seconds = int(max_seconds)
        self.ui.lineEdit_format.setText(regex)
        if self.lineEdit_shotclockFormatInfo is not None:
            self.lineEdit_shotclockFormatInfo.setText(regex)
        self.genericSettingsChanged("format_regex", regex)
        self.genericSettingsChanged("shotclock_max", max_seconds)
        self.ui.comboBox_formatPrefix.setCurrentIndex(12)

    def _applyShotclockMax(self, max_seconds: int):
        self._applyShotclockSettings(max_seconds, self._buildShotclockRegex(max_seconds))

    def shotclockPresetChanged(self, index: int):
        if self.comboBox_shotclockPreset is None or self.spinBox_shotclockMax is None:
            return
        preset_index = self.comboBox_shotclockPreset.itemData(index)
        if preset_index is None:
            return
        preset = self.shotclockPresets[int(preset_index)]
        if preset["max"] is None:
            return
        with QSignalBlocker(self.spinBox_shotclockMax):
            self.spinBox_shotclockMax.setValue(int(preset["max"]))
        self._applyShotclockSettings(int(preset["max"]), str(preset["regex"]))

    def shotclockMaxChanged(self, value: int):
        if self.comboBox_shotclockPreset is None:
            return
        selected_preset = self._selectedShotclockPreset()
        if (
            selected_preset is not None
            and selected_preset["max"] is not None
            and int(selected_preset["max"]) != int(value)
        ):
            with QSignalBlocker(self.comboBox_shotclockPreset):
                self.comboBox_shotclockPreset.setCurrentIndex(0)
        self._applyShotclockMax(value)

    def shotclockFormatEdited(self, format_regex: str):
        self.ui.lineEdit_format.setText(format_regex)
        self.genericSettingsChanged("format_regex", format_regex)
        # Editing the format manually means we are using a custom setup.
        if self.comboBox_shotclockPreset is not None:
            with QSignalBlocker(self.comboBox_shotclockPreset):
                self.comboBox_shotclockPreset.setCurrentIndex(0)

    def editSettings(self, settingsMutatorCallback):
        # update the selected item's settings in the detectionTargetsStorage
        item = self.ui.tableWidget_boxes.currentItem()
        if item is None:
            logger.info("no item selected")
            return
        item_name = item.text()
        item_obj = self.detectionTargetsStorage.find_item_by_name(item_name)
        if item_obj is None:
            logger.info("item not found: %s", item_name)
            return
        item_obj = settingsMutatorCallback(item_obj)
        self.detectionTargetsStorage.edit_item(item_name, item_obj)

    def restoreDefaults(self):
        # restore the default settings for the selected item
        def restoreDefaultsSettings(item_obj):
            info = default_info_for_box_name(item_obj.name)
            item_obj.settings = normalize_settings_dict({}, info)
            return item_obj

        self.editSettings(restoreDefaultsSettings)
        self.populateSettings(self.ui.tableWidget_boxes.currentItem().text())

    def confThreshChanged(self):
        self.genericSettingsChanged(
            "conf_thresh", float(self.ui.horizontalSlider_conf_thresh.value()) / 100.0
        )
        self.updateSliderValueLabels()

    def cleanupThreshChanged(self):
        self.genericSettingsChanged(
            "cleanup_thresh", float(self.ui.horizontalSlider_cleanup.value()) / 100.0
        )
        self.updateSliderValueLabels()

    def formatPrefixChanged(self, index):
        if index == 12:
            return  # do nothing if "Select Preset" is selected
        # based on the selected index, set the format prefix
        # change lineEdit_format to the selected format prefix
        self.ui.lineEdit_format.setText(format_prefixes[index])

    def _apply_baseline_by_type_to_item(self, item_obj, field_type):
        item_obj.settings["type"] = field_type

        if field_type == FieldType.TIME:
            item_obj.settings["format_regex"] = format_prefixes[0]
            item_obj.settings["cleanup_thresh"] = 0.0
            item_obj.settings["dilate"] = 1
            item_obj.settings["skew"] = 2
            item_obj.settings["vscale"] = 10
            item_obj.settings["rescale_patch"] = True
            item_obj.settings["binarization_method"] = 2
            item_obj.settings["conf_thresh"] = 0.5
            return item_obj

        if field_type == FieldType.NUMBER:
            item_obj.settings["format_regex"] = format_prefixes[11]
            item_obj.settings["cleanup_thresh"] = 0.0
            item_obj.settings["dilate"] = 1
            item_obj.settings["skew"] = 0
            item_obj.settings["vscale"] = 10
            item_obj.settings["rescale_patch"] = True
            item_obj.settings["binarization_method"] = 2
            item_obj.settings["conf_thresh"] = 0.5
            return item_obj

        # FieldType.TEXT
        item_obj.settings["format_regex"] = format_prefixes[10]
        item_obj.settings["cleanup_thresh"] = 0.0
        item_obj.settings["dilate"] = 1
        item_obj.settings["skew"] = 0
        item_obj.settings["vscale"] = 10
        item_obj.settings["rescale_patch"] = True
        item_obj.settings["binarization_method"] = 0
        item_obj.settings["conf_thresh"] = 0.5
        return item_obj

    def _apply_time_baseline_to_item(self, item_obj):
        return self._apply_baseline_by_type_to_item(item_obj, FieldType.TIME)

    def applyTimeBaseline(self):
        self.editSettings(self._apply_time_baseline_to_item)
        current_item = self.ui.tableWidget_boxes.currentItem()
        if current_item is not None:
            self.populateSettings(current_item.text())

    def fieldTypeChanged(self, index):
        self.editSettings(lambda item_obj: self._apply_baseline_by_type_to_item(item_obj, index))
        current_item = self.ui.tableWidget_boxes.currentItem()
        if current_item is not None:
            self.populateSettings(current_item.text())

    def genericSettingsChanged(self, settingName, value):
        def editGenericSettings(item_obj):
            item_obj.settings[settingName] = value
            return item_obj

        self.editSettings(editGenericSettings)

    def boxSettingsUiSetup(self):
        self.ui.pushButton_restoreDefaults.clicked.connect(self.restoreDefaults)
        self.ui.pushButton_applyTimeBaseline.clicked.connect(self.applyTimeBaseline)
        self.ui.checkBox_smoothing.toggled.connect(
            partial(self.genericSettingsChanged, "smoothing")
        )
        self.ui.checkBox_skip_empty.toggled.connect(
            partial(self.genericSettingsChanged, "skip_empty")
        )
        self.ui.horizontalSlider_conf_thresh.valueChanged.connect(
            self.confThreshChanged
        )
        self.ui.lineEdit_format.textChanged.connect(
            partial(self.genericSettingsChanged, "format_regex")
        )
        self.ui.comboBox_fieldType.currentIndexChanged.connect(self.fieldTypeChanged)
        self.ui.checkBox_skip_similar_image.toggled.connect(
            partial(self.genericSettingsChanged, "skip_similar_image")
        )
        self.ui.checkBox_autocrop.toggled.connect(
            partial(self.genericSettingsChanged, "autocrop")
        )
        self.ui.horizontalSlider_cleanup.valueChanged.connect(self.cleanupThreshChanged)
        self.ui.horizontalSlider_dilate.valueChanged.connect(
            partial(self.genericSettingsChanged, "dilate")
        )
        self.ui.horizontalSlider_skew.valueChanged.connect(
            partial(self.genericSettingsChanged, "skew")
        )
        self.ui.horizontalSlider_vscale.valueChanged.connect(
            partial(self.genericSettingsChanged, "vscale")
        )
        # Keep UI value labels in sync with sliders
        self.ui.horizontalSlider_conf_thresh.valueChanged.connect(
            self.updateSliderValueLabels
        )
        self.ui.horizontalSlider_cleanup.valueChanged.connect(
            self.updateSliderValueLabels
        )
        self.ui.horizontalSlider_dilate.valueChanged.connect(
            self.updateSliderValueLabels
        )
        self.ui.horizontalSlider_skew.valueChanged.connect(
            self.updateSliderValueLabels
        )
        self.ui.horizontalSlider_vscale.valueChanged.connect(
            self.updateSliderValueLabels
        )
        self.ui.checkBox_removeLeadingZeros.toggled.connect(
            partial(self.genericSettingsChanged, "remove_leading_zeros")
        )
        self.ui.checkBox_rescalePatch.toggled.connect(
            partial(self.genericSettingsChanged, "rescale_patch")
        )
        self.ui.checkBox_normWHRatio.toggled.connect(
            partial(self.genericSettingsChanged, "normalize_wh_ratio")
        )
        self.ui.checkBox_invertPatch.toggled.connect(
            partial(self.genericSettingsChanged, "invert_patch")
        )
        self.ui.checkBox_dotDetector.toggled.connect(
            partial(self.genericSettingsChanged, "dot_detector")
        )
        self.ui.checkBox_ordinalIndicator.toggled.connect(
            partial(self.genericSettingsChanged, "ordinal_indicator")
        )
        self.ui.comboBox_binarizationMethod.currentIndexChanged.connect(
            partial(self.genericSettingsChanged, "binarization_method")
        )
        self.ui.lineEdit_templatefield.textChanged.connect(
            partial(self.genericSettingsChanged, "templatefield_text")
        )
        self.ui.checkBox_compositeBox.toggled.connect(
            partial(self.genericSettingsChanged, "composite_box")
        )
        self.ui.comboBox_formatPrefix.currentIndexChanged.connect(
            self.formatPrefixChanged
        )
        self.comboBox_shotclockPreset.currentIndexChanged.connect(
            self.shotclockPresetChanged
        )
        self.spinBox_shotclockMax.valueChanged.connect(self.shotclockMaxChanged)
        self.lineEdit_shotclockFormatInfo.textChanged.connect(self.shotclockFormatEdited)

    def populateSettings(self, name):
        self.ui.lineEdit_format.blockSignals(True)
        self.ui.comboBox_fieldType.blockSignals(True)
        self.ui.checkBox_smoothing.blockSignals(True)
        self.ui.checkBox_skip_empty.blockSignals(True)
        self.ui.horizontalSlider_conf_thresh.blockSignals(True)
        self.ui.checkBox_autocrop.blockSignals(True)
        self.ui.checkBox_skip_similar_image.blockSignals(True)
        self.ui.horizontalSlider_cleanup.blockSignals(True)
        self.ui.horizontalSlider_dilate.blockSignals(True)
        self.ui.horizontalSlider_skew.blockSignals(True)
        self.ui.horizontalSlider_vscale.blockSignals(True)
        self.ui.checkBox_removeLeadingZeros.blockSignals(True)
        self.ui.checkBox_rescalePatch.blockSignals(True)
        self.ui.checkBox_normWHRatio.blockSignals(True)
        self.ui.checkBox_invertPatch.blockSignals(True)
        self.ui.checkBox_ordinalIndicator.blockSignals(True)
        self.ui.comboBox_binarizationMethod.blockSignals(True)
        self.ui.comboBox_formatPrefix.blockSignals(True)
        self.ui.checkBox_templatefield.blockSignals(True)
        self.ui.lineEdit_templatefield.blockSignals(True)
        self.ui.checkBox_compositeBox.blockSignals(True)
        if self.comboBox_shotclockPreset is not None:
            self.comboBox_shotclockPreset.blockSignals(True)
        if self.spinBox_shotclockMax is not None:
            self.spinBox_shotclockMax.blockSignals(True)

        # populate the settings from the detectionTargetsStorage
        item_obj = self.detectionTargetsStorage.find_item_by_name(name)
        is_shotclock_target = self._isShotClockTarget(name, item_obj)
        self._setShotclockControlsVisible(is_shotclock_target)
        if item_obj is None:
            self.ui.lineEdit_format.setText("")
            self.ui.comboBox_fieldType.setCurrentIndex(0)
            self.ui.checkBox_smoothing.setChecked(True)
            self.ui.checkBox_skip_empty.setChecked(True)
            self.ui.horizontalSlider_conf_thresh.setValue(50)
            self.ui.checkBox_autocrop.setChecked(False)
            self.ui.checkBox_skip_similar_image.setChecked(False)
            self.ui.horizontalSlider_cleanup.setValue(0)
            self.ui.horizontalSlider_dilate.setValue(1)
            self.ui.horizontalSlider_skew.setValue(0)
            self.ui.horizontalSlider_vscale.setValue(10)
            self.ui.label_selectedInfo.setText("")
            self.ui.checkBox_removeLeadingZeros.setChecked(False)
            self.ui.checkBox_rescalePatch.setChecked(False)
            self.ui.checkBox_normWHRatio.setChecked(False)
            self.ui.checkBox_invertPatch.setChecked(False)
            self.ui.checkBox_ordinalIndicator.setChecked(False)
            self.ui.comboBox_binarizationMethod.setCurrentIndex(0)
            self.ui.checkBox_templatefield.setChecked(False)
            self.ui.lineEdit_templatefield.setText("")
            self.ui.checkBox_compositeBox.setChecked(False)
            if self.spinBox_shotclockMax is not None:
                self.spinBox_shotclockMax.setValue(39)
            if self.comboBox_shotclockPreset is not None:
                self.comboBox_shotclockPreset.setCurrentIndex(0)
            if self.lineEdit_shotclockFormatInfo is not None:
                self.lineEdit_shotclockFormatInfo.setText("")
        else:
            item_obj.settings = normalize_settings_dict(
                item_obj.settings, default_info_for_box_name(item_obj.name)
            )
            self.ui.label_selectedInfo.setText(f"{item_obj.name}")
            self.ui.lineEdit_format.setText(item_obj.settings["format_regex"])
            self.ui.comboBox_fieldType.setCurrentIndex(item_obj.settings["type"])
            self.ui.checkBox_smoothing.setChecked(item_obj.settings["smoothing"])
            self.ui.checkBox_skip_empty.setChecked(item_obj.settings["skip_empty"])
            self.ui.horizontalSlider_conf_thresh.setValue(
                int(item_obj.settings["conf_thresh"] * 100)
            )
            self.ui.checkBox_autocrop.setChecked(item_obj.settings["autocrop"])
            self.ui.checkBox_skip_similar_image.setChecked(
                item_obj.settings["skip_similar_image"]
            )
            self.ui.horizontalSlider_cleanup.setValue(
                int(item_obj.settings["cleanup_thresh"] * 100)
            )
            self.ui.horizontalSlider_dilate.setValue(item_obj.settings["dilate"])
            self.ui.horizontalSlider_skew.setValue(item_obj.settings["skew"])
            self.ui.horizontalSlider_vscale.setValue(item_obj.settings["vscale"])
            self.ui.checkBox_removeLeadingZeros.setChecked(
                item_obj.settings["remove_leading_zeros"]
            )
            self.ui.checkBox_rescalePatch.setChecked(item_obj.settings["rescale_patch"])
            self.ui.checkBox_normWHRatio.setChecked(
                item_obj.settings["normalize_wh_ratio"]
            )
            self.ui.checkBox_invertPatch.setChecked(item_obj.settings["invert_patch"])
            self.ui.checkBox_dotDetector.setChecked(item_obj.settings["dot_detector"])
            self.ui.checkBox_ordinalIndicator.setChecked(
                item_obj.settings["ordinal_indicator"]
            )
            self.ui.comboBox_binarizationMethod.setCurrentIndex(
                item_obj.settings["binarization_method"]
            )
            self.ui.checkBox_templatefield.setChecked(
                item_obj.settings["templatefield"]
            )
            self.ui.lineEdit_templatefield.setText(
                item_obj.settings["templatefield_text"]
            )
            self.ui.checkBox_compositeBox.setChecked(item_obj.settings["composite_box"])
            if is_shotclock_target and self.spinBox_shotclockMax is not None:
                max_seconds = item_obj.settings.get("shotclock_max")
                if max_seconds is None:
                    max_seconds = 39
                max_seconds = int(max_seconds)
                self.spinBox_shotclockMax.setValue(max_seconds)
                if self.lineEdit_shotclockFormatInfo is not None:
                    self.lineEdit_shotclockFormatInfo.setText(
                        item_obj.settings.get("format_regex", "")
                    )
                preset_index = 0
                current_regex = item_obj.settings.get("format_regex", "")
                for i, preset in enumerate(self.shotclockPresets):
                    if preset["max"] is None:
                        continue
                    if int(preset["max"]) == max_seconds and str(preset["regex"]) == current_regex:
                        preset_index = i
                        break
                self.comboBox_shotclockPreset.setCurrentIndex(preset_index)

        self.ui.comboBox_formatPrefix.setCurrentIndex(12)
        self.updateSliderValueLabels()

        self.ui.lineEdit_format.blockSignals(False)
        self.ui.comboBox_fieldType.blockSignals(False)
        self.ui.checkBox_smoothing.blockSignals(False)
        self.ui.checkBox_skip_empty.blockSignals(False)
        self.ui.horizontalSlider_conf_thresh.blockSignals(False)
        self.ui.checkBox_autocrop.blockSignals(False)
        self.ui.checkBox_skip_similar_image.blockSignals(False)
        self.ui.horizontalSlider_cleanup.blockSignals(False)
        self.ui.horizontalSlider_dilate.blockSignals(False)
        self.ui.horizontalSlider_skew.blockSignals(False)
        self.ui.horizontalSlider_vscale.blockSignals(False)
        self.ui.checkBox_removeLeadingZeros.blockSignals(False)
        self.ui.checkBox_rescalePatch.blockSignals(False)
        self.ui.checkBox_normWHRatio.blockSignals(False)
        self.ui.checkBox_invertPatch.blockSignals(False)
        self.ui.checkBox_ordinalIndicator.blockSignals(False)
        self.ui.comboBox_binarizationMethod.blockSignals(False)
        self.ui.comboBox_formatPrefix.blockSignals(False)
        self.ui.checkBox_templatefield.blockSignals(False)
        self.ui.lineEdit_templatefield.blockSignals(False)
        self.ui.checkBox_compositeBox.blockSignals(False)
        if self.comboBox_shotclockPreset is not None:
            self.comboBox_shotclockPreset.blockSignals(False)
        if self.spinBox_shotclockMax is not None:
            self.spinBox_shotclockMax.blockSignals(False)

    def updateSliderValueLabels(self):
        self.ui.label_conf_thresh_value.setText(
            f"{self.ui.horizontalSlider_conf_thresh.value()}%"
        )
        self.ui.label_cleanup_value.setText(
            f"{self.ui.horizontalSlider_cleanup.value()}%"
        )
        self.ui.label_dilate_value.setText(str(self.ui.horizontalSlider_dilate.value()))
        self.ui.label_skew_value.setText(str(self.ui.horizontalSlider_skew.value()))
        self.ui.label_vscale_value.setText(str(self.ui.horizontalSlider_vscale.value()))
        for _, pair in self.sliderValueInputs.items():
            slider, spin = pair
            if spin is None:
                continue
            with QSignalBlocker(spin):
                spin.setValue(slider.value())
