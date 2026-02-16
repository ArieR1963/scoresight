from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QStyledItemDelegate,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)

from text_detection_target import TextDetectionTarget
from ui_mainwindow import Ui_MainWindow
from vmix_output import VMixAPI
from sc_logging import logger
from storage import fetch_data, store_data


class VMixUIHanlder:
    def __init__(self, ui: Ui_MainWindow):
        self.ui = ui
        self.vmixUpdater = None
        self.vmixFieldNames: list[str] = []
        self.vmixFieldDelegate = VMixFieldDelegate(self.vmixFieldNames)
        self.comboBox_vmixMode = None
        self.lineEdit_vmixTcpPort = None
        self.pushButton_fetchVmixFields = None
        self.vmixUiSetup()

    def globalSettingsChanged(self, settingName, value):
        store_data("scoresight.json", settingName, value)

    def vmixConnectionChanged(self):
        mode = (
            self.comboBox_vmixMode.currentData()
            if self.comboBox_vmixMode is not None
            else "legacy_http"
        )
        tcp_port = (
            self.lineEdit_vmixTcpPort.text()
            if self.lineEdit_vmixTcpPort is not None
            else "8099"
        )
        self.vmixUpdater = VMixAPI(
            self.ui.lineEdit_vmixHost.text(),
            self.ui.lineEdit_vmixPort.text(),
            self.ui.inputLineEdit_vmix.text(),
            {},
            mode=mode,
            tcp_port=tcp_port,
        )
        self.globalSettingsChanged("vmix_host", self.ui.lineEdit_vmixHost.text())
        self.globalSettingsChanged("vmix_port", self.ui.lineEdit_vmixPort.text())
        self.globalSettingsChanged("vmix_input", self.ui.inputLineEdit_vmix.text())
        self.globalSettingsChanged("vmix_mode", mode)
        self.globalSettingsChanged("vmix_tcp_port", tcp_port)

    def vmixMappingChanged(self, _):
        # store entire mapping data in scoresight.json
        mapping = {}
        model = self.ui.tableView_vmixMapping.model()
        if isinstance(model, QStandardItemModel):
            for i in range(model.rowCount()):
                item = model.item(i, 0)
                value = model.item(i, 1)
                if item and value:
                    mapping[item.text()] = value.text()
            self.globalSettingsChanged("vmix_mapping", mapping)
            self.vmixUpdater.set_field_mapping(mapping)
        else:
            logger.error("vmixMappingChanged: model is not a QStandardItemModel")

    def vmixUiSetup(self):
        # populate the vmix connection from storage
        self.ui.lineEdit_vmixHost.setText(
            fetch_data("scoresight.json", "vmix_host", "localhost")
        )
        self.ui.lineEdit_vmixPort.setText(
            fetch_data("scoresight.json", "vmix_port", "8099")
        )
        self.ui.inputLineEdit_vmix.setText(
            fetch_data("scoresight.json", "vmix_input", "1")
        )
        self._ensureVmixPlusControls()
        self.comboBox_vmixMode.setCurrentIndex(
            1 if fetch_data("scoresight.json", "vmix_mode", "legacy_http") == "api_plus" else 0
        )
        self.lineEdit_vmixTcpPort.setText(fetch_data("scoresight.json", "vmix_tcp_port", "8099"))
        # connect the lineEdits to vmixConnectionChanged
        self.ui.lineEdit_vmixHost.textChanged.connect(self.vmixConnectionChanged)
        self.ui.lineEdit_vmixPort.textChanged.connect(self.vmixConnectionChanged)
        self.ui.inputLineEdit_vmix.textChanged.connect(self.vmixConnectionChanged)
        self.comboBox_vmixMode.currentIndexChanged.connect(self.vmixConnectionChanged)
        self.lineEdit_vmixTcpPort.textChanged.connect(self.vmixConnectionChanged)
        self.pushButton_fetchVmixFields.clicked.connect(self.fetchVmixFields)

        # create the vmixUpdater
        self.vmixUpdater = VMixAPI(
            self.ui.lineEdit_vmixHost.text(),
            self.ui.lineEdit_vmixPort.text(),
            self.ui.inputLineEdit_vmix.text(),
            {},
            mode=self.comboBox_vmixMode.currentData(),
            tcp_port=self.lineEdit_vmixTcpPort.text(),
        )
        # add standard item model to the tableView_vmixMapping
        self.ui.tableView_vmixMapping.setModel(QStandardItemModel())
        self.ui.tableView_vmixMapping.setItemDelegateForColumn(1, self.vmixFieldDelegate)
        mapping = fetch_data("scoresight.json", "vmix_mapping", {})
        if mapping:
            self.vmixUpdater.set_field_mapping(mapping)

        self.ui.tableView_vmixMapping.model().dataChanged.connect(
            self.vmixMappingChanged
        )

        self.ui.pushButton_startvmix.toggled.connect(self.togglevMix)

    def togglevMix(self, value):
        if not self.vmixUpdater:
            return
        if value:
            self.ui.pushButton_startvmix.setText("🛑 Stop vMix")
            self.vmixUpdater.running = True
        else:
            self.ui.pushButton_startvmix.setText("▶️ Start vMix")
            self.vmixUpdater.running = False

    def _ensureVmixPlusControls(self):
        layout = self.ui.connectionWidget.layout()
        if layout is None:
            return
        if self.comboBox_vmixMode is None:
            self.comboBox_vmixMode = QComboBox(self.ui.connectionWidget)
            self.comboBox_vmixMode.addItem("Legacy HTTP", "legacy_http")
            self.comboBox_vmixMode.addItem("vMix API+", "api_plus")
            self.comboBox_vmixMode.setMaximumWidth(130)
            layout.insertWidget(4, self.comboBox_vmixMode)
        if self.lineEdit_vmixTcpPort is None:
            tcp_label = QLabel("TCP", self.ui.connectionWidget)
            layout.insertWidget(5, tcp_label)
            self.lineEdit_vmixTcpPort = QLineEdit(self.ui.connectionWidget)
            self.lineEdit_vmixTcpPort.setMaximumWidth(50)
            layout.insertWidget(6, self.lineEdit_vmixTcpPort)
        if self.pushButton_fetchVmixFields is None:
            self.pushButton_fetchVmixFields = QPushButton("Fetch Fields", self.ui.connectionWidget)
            self.pushButton_fetchVmixFields.setMaximumWidth(110)
            layout.insertWidget(7, self.pushButton_fetchVmixFields)

    def fetchVmixFields(self):
        if self.vmixUpdater is None:
            return
        if self.comboBox_vmixMode.currentData() != "api_plus":
            QMessageBox.information(
                self.ui.tab_vmix,
                "vMix API+",
                "Switch mode to 'vMix API+' to fetch template field names.",
            )
            return
        fields = self.vmixUpdater.fetch_fields()
        if not fields:
            QMessageBox.warning(
                self.ui.tab_vmix,
                "vMix API+",
                "No template field names found. Check host/port/input and try again.",
            )
            return
        self.vmixFieldNames = fields
        self.vmixFieldDelegate.set_field_names(fields)
        self.ui.tableView_vmixMapping.setItemDelegateForColumn(1, self.vmixFieldDelegate)

    def updatevMixTable(self, detectionTargets: list[TextDetectionTarget]):
        mapping_storage = fetch_data("scoresight.json", "vmix_mapping")
        model = QStandardItemModel()
        model.blockSignals(True)

        for box in detectionTargets:
            # add the detection to the vmix output mapping: tableView_vmixMapping
            # check if the table already has the detectionTarget
            items = model.findItems(box.name, Qt.MatchFlag.MatchExactly)
            if len(items) == 0:
                # add the item to the list
                row = model.rowCount()
                model.insertRow(row)
                model.setItem(row, 0, QStandardItem(box.name))
                # the first item shouldn't be editable
                model.item(row, 0).setFlags(Qt.ItemFlag.NoItemFlags)
            else:
                # update the item in the list
                item = items[0]
                row = item.row()

            # get value from storage or use the box name
            if mapping_storage and box.name in mapping_storage:
                model.setItem(row, 1, QStandardItem(mapping_storage[box.name]))
            else:
                model.setItem(row, 1, QStandardItem(box.name))
        # remove the items that are not in the detectionTargets
        for i in range(model.rowCount()):
            item = model.item(i, 0)
            if not any([box.name == item.text() for box in detectionTargets]):
                model.removeRow(i)

        model.blockSignals(False)
        self.ui.tableView_vmixMapping.setModel(model)
        self.ui.tableView_vmixMapping.setItemDelegateForColumn(1, self.vmixFieldDelegate)
        self.ui.tableView_vmixMapping.model().dataChanged.connect(
            self.vmixMappingChanged
        )


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
