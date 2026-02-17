from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from text_detection_target import TextDetectionTarget, TextDetectionTargetWithResult
from ui_mainwindow import Ui_MainWindow
from vmix_output import VMixAPI
from sc_logging import logger
from storage import fetch_data, store_data


class VMixFieldDelegate(QStyledItemDelegate):
    def __init__(self, field_names: list[str]):
        super().__init__()
        self.field_names = field_names or []

    def set_field_names(self, field_names: list[str]):
        self.field_names = field_names or []

    def createEditor(self, parent, option, index):
        if index.column() != 1:
            return super().createEditor(parent, option, index)
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.addItems(self.field_names)
        return editor

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            value = index.data(Qt.ItemDataRole.EditRole) or index.data() or ""
            editor.setCurrentText(str(value))
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText())
            return
        super().setModelData(editor, model, index)


class VMixUIHanlder:
    def __init__(self, ui: Ui_MainWindow, add_target_callback=None):
        self.ui = ui
        self.add_target_callback = add_target_callback
        self.vmixUpdater = None
        self.vmixApiPlusUpdater = None
        self.vmixApiPlusConnected = False
        self.vmixApiPlusFieldNames: list[str] = []
        self.vmixApiPlusDelegate = VMixFieldDelegate(self.vmixApiPlusFieldNames)
        self._apiPlusProbeTimer = QTimer()
        self._apiPlusProbeTimer.setSingleShot(True)
        self._apiPlusProbeTimer.timeout.connect(self._probeVmixApiPlusConnection)
        self.vmixUiSetup()

    def globalSettingsChanged(self, settingName, value):
        store_data("scoresight.json", settingName, value)

    # -------- Legacy vMix --------
    def vmixConnectionChanged(self):
        self.vmixUpdater = VMixAPI(
            self.ui.lineEdit_vmixHost.text(),
            self.ui.lineEdit_vmixPort.text(),
            self.ui.inputLineEdit_vmix.text(),
            {},
            mode="legacy_http",
        )
        self.globalSettingsChanged("vmix_host", self.ui.lineEdit_vmixHost.text())
        self.globalSettingsChanged("vmix_port", self.ui.lineEdit_vmixPort.text())
        self.globalSettingsChanged("vmix_input", self.ui.inputLineEdit_vmix.text())

    def vmixMappingChanged(self, _):
        mapping = self._model_to_mapping(self.ui.tableView_vmixMapping.model())
        self.globalSettingsChanged("vmix_mapping", mapping)
        if self.vmixUpdater:
            self.vmixUpdater.set_field_mapping(mapping)

    def togglevMix(self, value):
        if not self.vmixUpdater:
            return
        if value:
            self.ui.pushButton_startvmix.setText("🛑 Stop vMix")
            self.vmixUpdater.running = True
        else:
            self.ui.pushButton_startvmix.setText("▶️ Start vMix")
            self.vmixUpdater.running = False

    # -------- vMix API+ --------
    def _createVmixApiPlusTab(self):
        self.tab_vmix_api_plus = QWidget()
        self.tab_vmix_api_plus.setObjectName("tab_vmix_api_plus")
        grid = QGridLayout(self.tab_vmix_api_plus)
        grid.setVerticalSpacing(2)

        self.tableView_vmixApiPlusMapping = QTableView(self.tab_vmix_api_plus)
        self.tableView_vmixApiPlusMapping.horizontalHeader().setVisible(False)
        self.tableView_vmixApiPlusMapping.horizontalHeader().setStretchLastSection(True)
        self.tableView_vmixApiPlusMapping.setModel(QStandardItemModel())
        self.tableView_vmixApiPlusMapping.setItemDelegateForColumn(
            1, self.vmixApiPlusDelegate
        )
        grid.addWidget(self.tableView_vmixApiPlusMapping, 1, 0, 1, 1)

        wrapper = QWidget(self.tab_vmix_api_plus)
        vbox = QVBoxLayout(wrapper)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(3)

        row1 = QWidget(wrapper)
        h1 = QHBoxLayout(row1)
        h1.setContentsMargins(0, 0, 0, 0)
        h1.setSpacing(3)
        h1.addWidget(QLabel("Connection", row1))
        self.lineEdit_vmixApiPlusHost = QLineEdit(row1)
        self.lineEdit_vmixApiPlusHost.setText(
            fetch_data("scoresight.json", "vmix_api_plus_host", "localhost")
        )
        h1.addWidget(self.lineEdit_vmixApiPlusHost)
        h1.addWidget(QLabel(":", row1))
        self.lineEdit_vmixApiPlusPort = QLineEdit(row1)
        self.lineEdit_vmixApiPlusPort.setMaximumWidth(60)
        self.lineEdit_vmixApiPlusPort.setText(
            fetch_data("scoresight.json", "vmix_api_plus_port", "8088")
        )
        h1.addWidget(self.lineEdit_vmixApiPlusPort)
        self.pushButton_fetchVmixApiPlusFields = QPushButton("Fetch Fields", row1)
        h1.addWidget(self.pushButton_fetchVmixApiPlusFields)
        self.label_vmixApiPlusStatus = QLabel("● Disconnected", row1)
        self.label_vmixApiPlusStatus.setStyleSheet("color:#d96f6f;")
        h1.addWidget(self.label_vmixApiPlusStatus)
        vbox.addWidget(row1)

        self.checkBox_vmix_api_plus_send_same = self.ui.checkBox_vmix_send_same

        grid.addWidget(wrapper, 0, 0, 1, 1)
        vmix_index = self.ui.tabWidget_outputs.indexOf(self.ui.tab_vmix)
        if vmix_index >= 0:
            self.ui.tabWidget_outputs.insertTab(
                vmix_index + 1, self.tab_vmix_api_plus, "vMix API+"
            )
        else:
            self.ui.tabWidget_outputs.addTab(self.tab_vmix_api_plus, "vMix API+")

    def vmixApiPlusConnectionChanged(self):
        self.vmixApiPlusUpdater = VMixAPI(
            self.lineEdit_vmixApiPlusHost.text(),
            self.lineEdit_vmixApiPlusPort.text(),
            "",
            {},
            mode="api_plus",
            tcp_port="8099",
        )
        self.vmixApiPlusUpdater.running = True
        self.globalSettingsChanged("vmix_api_plus_host", self.lineEdit_vmixApiPlusHost.text())
        self.globalSettingsChanged("vmix_api_plus_port", self.lineEdit_vmixApiPlusPort.text())
        self._setApiPlusStatus(False)
        self._apiPlusProbeTimer.start(350)

    def vmixApiPlusMappingChanged(self, _):
        mapping = self._model_to_mapping(self.tableView_vmixApiPlusMapping.model())
        self.globalSettingsChanged("vmix_api_plus_mapping", mapping)
        if self.vmixApiPlusUpdater:
            self.vmixApiPlusUpdater.set_field_mapping(mapping)

    def _setApiPlusStatus(self, connected: bool):
        self.vmixApiPlusConnected = connected
        if connected:
            self.label_vmixApiPlusStatus.setText("● Connected")
            self.label_vmixApiPlusStatus.setStyleSheet("color:#6bd67a;")
        else:
            self.label_vmixApiPlusStatus.setText("● Disconnected")
            self.label_vmixApiPlusStatus.setStyleSheet("color:#d96f6f;")

    def _probeVmixApiPlusConnection(self):
        if self.vmixApiPlusUpdater is None:
            self._setApiPlusStatus(False)
            return
        self._setApiPlusStatus(self.vmixApiPlusUpdater.ping_api())

    def fetchVmixApiPlusFields(self):
        if self.vmixApiPlusUpdater is None:
            return
        fields = self.vmixApiPlusUpdater.fetch_fields()
        if not fields:
            self._setApiPlusStatus(False)
            QMessageBox.warning(
                self.tab_vmix_api_plus,
                "vMix API+",
                "No text fields found. Check host/port and try again.",
            )
            return
        self.vmixApiPlusFieldNames = fields
        self.vmixApiPlusDelegate.set_field_names(fields)
        self.tableView_vmixApiPlusMapping.setItemDelegateForColumn(1, self.vmixApiPlusDelegate)
        self._setApiPlusStatus(True)
        self._showVmixApiPlusFieldsPopup(fields)

    def _showVmixApiPlusFieldsPopup(self, fields: list[str]):
        dialog = QDialog(self.tab_vmix_api_plus)
        dialog.setWindowTitle("vMix API+ Fields")
        dialog.setMinimumWidth(540)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"Found {len(fields)} field names from /api (<text name=\"...\">).",
            dialog,
        )
        layout.addWidget(label)

        list_widget = QListWidget(dialog)
        list_widget.addItems(fields)
        layout.addWidget(list_widget)

        target_row = QWidget(dialog)
        target_layout = QHBoxLayout(target_row)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.addWidget(QLabel("Target", target_row))
        target_name_edit = QLineEdit(target_row)
        target_layout.addWidget(target_name_edit)
        target_layout.addWidget(QLabel("Preset", target_row))
        preset_combo = QComboBox(target_row)
        preset_names = [
            self.ui.comboBox_formatPrefix.itemText(i)
            for i in range(self.ui.comboBox_formatPrefix.count())
        ]
        for i, name in enumerate(preset_names):
            preset_combo.addItem(name, i)
        target_layout.addWidget(preset_combo)
        layout.addWidget(target_row)

        status_label = QLabel("", dialog)
        layout.addWidget(status_label)

        buttons_row = QWidget(dialog)
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        add_button = QPushButton("Add Target", buttons_row)
        add_draw_button = QPushButton("Add + Draw Box", buttons_row)
        close_button = QPushButton("Close", buttons_row)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(add_draw_button)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(close_button)
        layout.addWidget(buttons_row)

        def suggest_from_field(field_name: str):
            if not field_name:
                return
            plain = field_name.replace(".Text", "").replace(".TEXT", "")
            upper = plain.upper()
            if "HOME" in upper and "SCORE" in upper:
                target_name_edit.setText("Home Score")
                preset_combo.setCurrentIndex(5)
                return
            if ("AWAY" in upper or "GUEST" in upper) and "SCORE" in upper:
                target_name_edit.setText("Away Score")
                preset_combo.setCurrentIndex(5)
                return
            if "SHOT" in upper and "CLOCK" in upper:
                target_name_edit.setText("Shot Clock")
                preset_combo.setCurrentIndex(4)
                return
            if (
                "TIME" in upper
                or "CLOCK" in upper
                or "MINUTE" in upper
                or "SECOND" in upper
            ):
                target_name_edit.setText("Time")
                preset_combo.setCurrentIndex(0)
                return
            if "PERIOD" in upper or "PART" in upper:
                target_name_edit.setText("Period")
                preset_combo.setCurrentIndex(7)
                return

            target_name_edit.setText(plain.replace("_", " ").strip().title())
            preset_combo.setCurrentIndex(12)

        def selected_field_name() -> str:
            item = list_widget.currentItem()
            return item.text().strip() if item is not None else ""

        def add_selected(draw_box: bool):
            if self.add_target_callback is None:
                status_label.setText("Add callback is not available.")
                return
            field_name = selected_field_name()
            if not field_name:
                status_label.setText("Select a vMix field first.")
                return
            target_name = target_name_edit.text().strip()
            if not target_name:
                status_label.setText("Set a target name first.")
                return
            preset_index = preset_combo.currentData()
            if not isinstance(preset_index, int):
                preset_index = 12
            if draw_box:
                ok = self.add_target_callback(
                    target_name, field_name, int(preset_index), False
                )
                if ok:
                    dialog.accept()
                    QTimer.singleShot(
                        0,
                        lambda: self.add_target_callback(
                            target_name, field_name, int(preset_index), True
                        ),
                    )
                else:
                    status_label.setText("Could not add the target.")
                return

            ok = self.add_target_callback(target_name, field_name, int(preset_index), False)
            if ok:
                status_label.setText(
                    f"Added '{target_name}' mapped to '{field_name}'."
                )
            else:
                status_label.setText("Could not add the target.")

        list_widget.currentTextChanged.connect(lambda value: suggest_from_field(value))
        add_button.clicked.connect(lambda: add_selected(False))
        add_draw_button.clicked.connect(lambda: add_selected(True))
        close_button.clicked.connect(dialog.accept)

        if fields:
            list_widget.setCurrentRow(0)

        dialog.exec()

    # -------- Shared --------
    def _model_to_mapping(self, model) -> dict:
        mapping = {}
        if isinstance(model, QStandardItemModel):
            for i in range(model.rowCount()):
                item = model.item(i, 0)
                value = model.item(i, 1)
                if item and value:
                    mapping[item.text()] = value.text()
        else:
            logger.error("vMix mapping model is not a QStandardItemModel")
        return mapping

    def vmixUiSetup(self):
        # Legacy setup (existing tab kept)
        self.ui.lineEdit_vmixHost.setText(fetch_data("scoresight.json", "vmix_host", "localhost"))
        self.ui.lineEdit_vmixPort.setText(fetch_data("scoresight.json", "vmix_port", "8099"))
        self.ui.inputLineEdit_vmix.setText(fetch_data("scoresight.json", "vmix_input", "1"))
        self.ui.lineEdit_vmixHost.textChanged.connect(self.vmixConnectionChanged)
        self.ui.lineEdit_vmixPort.textChanged.connect(self.vmixConnectionChanged)
        self.ui.inputLineEdit_vmix.textChanged.connect(self.vmixConnectionChanged)
        self.vmixConnectionChanged()
        self.ui.tableView_vmixMapping.setModel(QStandardItemModel())
        self.ui.tableView_vmixMapping.model().dataChanged.connect(self.vmixMappingChanged)
        self.ui.pushButton_startvmix.toggled.connect(self.togglevMix)

        mapping = fetch_data("scoresight.json", "vmix_mapping", {})
        if mapping and self.vmixUpdater:
            self.vmixUpdater.set_field_mapping(mapping)

        # API+ setup (new tab)
        self._createVmixApiPlusTab()
        self.lineEdit_vmixApiPlusHost.textChanged.connect(self.vmixApiPlusConnectionChanged)
        self.lineEdit_vmixApiPlusPort.textChanged.connect(self.vmixApiPlusConnectionChanged)
        self.pushButton_fetchVmixApiPlusFields.clicked.connect(self.fetchVmixApiPlusFields)
        self.vmixApiPlusConnectionChanged()
        self.tableView_vmixApiPlusMapping.model().dataChanged.connect(self.vmixApiPlusMappingChanged)

        mapping_plus = fetch_data("scoresight.json", "vmix_api_plus_mapping", {})
        if mapping_plus and self.vmixApiPlusUpdater:
            self.vmixApiPlusUpdater.set_field_mapping(mapping_plus)

    def updatevMixTable(self, detectionTargets: list[TextDetectionTarget]):
        mapping_storage = fetch_data("scoresight.json", "vmix_mapping", {})
        model = QStandardItemModel()
        model.blockSignals(True)
        for box in detectionTargets:
            row = model.rowCount()
            model.insertRow(row)
            model.setItem(row, 0, QStandardItem(box.name))
            model.item(row, 0).setFlags(Qt.ItemFlag.NoItemFlags)
            model.setItem(row, 1, QStandardItem(mapping_storage.get(box.name, box.name)))
        model.blockSignals(False)
        self.ui.tableView_vmixMapping.setModel(model)
        self.ui.tableView_vmixMapping.model().dataChanged.connect(self.vmixMappingChanged)
        if self.vmixUpdater is not None:
            self.vmixUpdater.set_field_mapping(mapping_storage)

        mapping_plus = fetch_data("scoresight.json", "vmix_api_plus_mapping", {})
        model_plus = QStandardItemModel()
        model_plus.blockSignals(True)
        for box in detectionTargets:
            row = model_plus.rowCount()
            model_plus.insertRow(row)
            model_plus.setItem(row, 0, QStandardItem(box.name))
            model_plus.item(row, 0).setFlags(Qt.ItemFlag.NoItemFlags)
            model_plus.setItem(row, 1, QStandardItem(mapping_plus.get(box.name, box.name)))
        model_plus.blockSignals(False)
        self.tableView_vmixApiPlusMapping.setModel(model_plus)
        self.tableView_vmixApiPlusMapping.setItemDelegateForColumn(
            1, self.vmixApiPlusDelegate
        )
        self.tableView_vmixApiPlusMapping.model().dataChanged.connect(
            self.vmixApiPlusMappingChanged
        )
        if self.vmixApiPlusUpdater is not None:
            self.vmixApiPlusUpdater.set_field_mapping(mapping_plus)

    def updatevMixOutputs(self, results: list[TextDetectionTargetWithResult]):
        if self.vmixUpdater is not None:
            self.vmixUpdater.update_vmix(results)
        if self.vmixApiPlusUpdater is not None and self.vmixApiPlusConnected:
            self.vmixApiPlusUpdater.update_vmix(results)
