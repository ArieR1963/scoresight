from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    def __init__(self, ui: Ui_MainWindow):
        self.ui = ui
        self.vmixUpdater = None
        self.vmixApiPlusUpdater = None
        self.vmixApiPlusEnabled = False
        self.vmixApiPlusFieldNames: list[str] = []
        self.vmixApiPlusDelegate = VMixFieldDelegate(self.vmixApiPlusFieldNames)
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
        self.pushButton_startvmixApiPlus = QPushButton("▶ Start", row1)
        self.pushButton_startvmixApiPlus.setCheckable(True)
        h1.addWidget(self.pushButton_startvmixApiPlus)
        self.label_vmixApiPlusStatus = QLabel("● Off", row1)
        self.label_vmixApiPlusStatus.setStyleSheet("color:#8a8a8a;")
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
        self.vmixApiPlusUpdater.running = self.vmixApiPlusEnabled
        self.globalSettingsChanged("vmix_api_plus_host", self.lineEdit_vmixApiPlusHost.text())
        self.globalSettingsChanged("vmix_api_plus_port", self.lineEdit_vmixApiPlusPort.text())
        self._setApiPlusLed(self.vmixApiPlusEnabled)

    def vmixApiPlusMappingChanged(self, _):
        mapping = self._model_to_mapping(self.tableView_vmixApiPlusMapping.model())
        self.globalSettingsChanged("vmix_api_plus_mapping", mapping)
        if self.vmixApiPlusUpdater:
            self.vmixApiPlusUpdater.set_field_mapping(mapping)

    def _setApiPlusLed(self, enabled: bool):
        self.vmixApiPlusEnabled = enabled
        if enabled:
            self.label_vmixApiPlusStatus.setText("● Running")
            self.label_vmixApiPlusStatus.setStyleSheet("color:#6bd67a;")
            self.pushButton_startvmixApiPlus.setText("■ Stop")
        else:
            self.label_vmixApiPlusStatus.setText("● Off")
            self.label_vmixApiPlusStatus.setStyleSheet("color:#8a8a8a;")
            self.pushButton_startvmixApiPlus.setText("▶ Start")

    def togglevMixApiPlus(self, value: bool):
        self._setApiPlusLed(value)
        self.globalSettingsChanged("vmix_api_plus_enabled", value)
        if self.vmixApiPlusUpdater is not None:
            self.vmixApiPlusUpdater.running = value

    def fetchVmixApiPlusFields(self):
        if self.vmixApiPlusUpdater is None:
            return
        fields = self.vmixApiPlusUpdater.fetch_fields()
        if not fields:
            QMessageBox.warning(
                self.tab_vmix_api_plus,
                "vMix API+",
                "No text fields found. Check host/port and try again.",
            )
            return
        self.vmixApiPlusFieldNames = fields
        self.vmixApiPlusDelegate.set_field_names(fields)
        self.tableView_vmixApiPlusMapping.setItemDelegateForColumn(1, self.vmixApiPlusDelegate)
        self._showVmixApiPlusFieldsPopup(fields)

    def _showVmixApiPlusFieldsPopup(self, fields: list[str]):
        dialog = QDialog(self.tab_vmix_api_plus)
        dialog.setWindowTitle("vMix API+ Fields")
        dialog.setMinimumWidth(460)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"Found {len(fields)} field names from /api (<text name=\"...\">).",
            dialog,
        )
        layout.addWidget(label)
        list_widget = QListWidget(dialog)
        list_widget.addItems(fields)
        layout.addWidget(list_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
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
        self.pushButton_startvmixApiPlus.toggled.connect(self.togglevMixApiPlus)
        self.vmixApiPlusEnabled = fetch_data(
            "scoresight.json", "vmix_api_plus_enabled", False
        )
        self.pushButton_startvmixApiPlus.setChecked(self.vmixApiPlusEnabled)
        self.vmixApiPlusConnectionChanged()
        self._setApiPlusLed(self.vmixApiPlusEnabled)
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

    def updatevMixOutputs(self, results: list[TextDetectionTargetWithResult]):
        if self.vmixUpdater is not None:
            self.vmixUpdater.update_vmix(results)
        if self.vmixApiPlusUpdater is not None and self.vmixApiPlusEnabled:
            self.vmixApiPlusUpdater.update_vmix(results)
