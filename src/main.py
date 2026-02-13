import os
from os import path
import platform
import sys
from resource_path import resource_path
from sc_logging import logger
from http_server import stop_http_server


def _configure_qt_plugin_paths() -> None:
    """
    Force Qt plugin paths to the PySide6 bundle inside the active venv.
    This avoids accidental fallback to OpenCV/minimal platform plugins.
    """
    try:
        import PySide6  # type: ignore

        qt_root = path.join(path.dirname(PySide6.__file__), "Qt")
        plugins_path = path.join(qt_root, "plugins")
        platforms_path = path.join(plugins_path, "platforms")

        os.environ["QT_PLUGIN_PATH"] = plugins_path
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_path
    except Exception:
        # If path setup fails, Qt may still resolve defaults.
        pass


if __name__ == "__main__":
    _configure_qt_plugin_paths()

    from PySide6.QtCore import QLocale, QTranslator
    from PySide6.QtWidgets import QApplication
    from mainwindow import MainWindow

    # only attempt splash when not on Mac OSX
    os_name = platform.system()
    if os_name != "Darwin":
        try:
            import pyi_splash  # type: ignore

            pyi_splash.close()
        except ImportError:
            pass
    app = QApplication(sys.argv)

    # Get system locale
    locale = QLocale.system().name()

    # Load the translation file based on the locale
    translator = QTranslator()
    locale_file = resource_path("translations", f"scoresight_{locale}.qm")
    # check if the file exists
    if not path.exists(locale_file):
        # load the default translation file
        locale_file = resource_path("translations", "scoresight_en_US.qm")
    if translator.load(locale_file):
        app.installTranslator(translator)

    # show the main window
    mainWindow = MainWindow(translator, app)
    mainWindow.show()

    app.exec()
    logger.info("Exiting...")

    stop_http_server()
