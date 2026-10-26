"""One-click installation of pydsstools into the Python used by QGIS.

Runs ``python -m pip install --user pydsstools`` with the interpreter that QGIS
itself uses, so users never need the OSGeo4W Shell. pydsstools publishes
binary wheels for Windows and Linux (x86-64) only.
"""

import importlib
import os
import site
import sys

from qgis.PyQt.QtCore import QProcess
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
)

from .dss_reader import pydsstools_available

PACKAGE = "pydsstools"


def qgis_python():
    """Return the python executable belonging to this QGIS, or None."""
    candidates = [
        os.path.join(sys.exec_prefix, "python.exe"),  # Windows (standalone and OSGeo4W)
        os.path.join(sys.exec_prefix, "bin", "python3"),  # Linux, macOS bundle
        os.path.join(sys.exec_prefix, "bin", "python"),
    ]
    if os.path.basename(sys.executable).lower().startswith("python"):
        candidates.insert(0, sys.executable)
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def manual_command():
    return "python -m pip install --user {}".format(PACKAGE)


def refresh_import_paths():
    """Make a fresh --user install importable without restarting QGIS."""
    user_site = site.getusersitepackages()
    if os.path.isdir(user_site) and user_site not in sys.path:
        site.addsitedir(user_site)
    importlib.invalidate_caches()
    return pydsstools_available()


class InstallDialog(QDialog):
    """Run pip in the background and show its output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Install pydsstools")
        self.setMinimumSize(560, 360)
        self.installed = False
        layout = QVBoxLayout(self)

        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        layout.addWidget(self.busy)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._failed_to_start)
        self._start()

    def _start(self):
        if sys.platform == "darwin":
            self._done(
                False,
                "pydsstools publishes no ready-made package for macOS. It can only be "
                "built from source; see https://github.com/gyanz/pydsstools.",
            )
            return
        python = qgis_python()
        if python is None:
            self._done(
                False,
                "Could not find the Python used by QGIS. Install manually from a shell "
                "that uses QGIS Python:\n\n" + manual_command(),
            )
            return
        self.message.setText(
            "Downloading and installing <b>pydsstools</b> for this QGIS. This takes "
            "about a minute and needs an internet connection."
        )
        arguments = ["-m", "pip", "install", "--user", "--disable-pip-version-check", PACKAGE]
        self.log.appendPlainText("> {} {}\n".format(python, " ".join(arguments)))
        self.process.start(python, arguments)

    def _read_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.log.appendPlainText(data.rstrip())

    def _failed_to_start(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._done(False, "pip could not be started.\n\nInstall manually: " + manual_command())

    def _finished(self, exit_code, exit_status):
        output = self.log.toPlainText()
        if exit_code == 0 and refresh_import_paths():
            self._done(True, "<b>pydsstools is installed.</b> DSS Link is ready to open DSS files.")
        elif exit_code == 0:
            self._done(
                True,
                "pydsstools was installed. <b>Restart QGIS</b> to start using it.",
            )
        elif "externally-managed" in output:
            self._done(
                False,
                "This Linux Python does not allow pip installs (externally managed). "
                "Install with your package manager, or run:\n\n"
                "python3 -m pip install --user --break-system-packages pydsstools",
            )
        else:
            self._done(
                False,
                "Installation failed (exit code {}). See the log below; you can also "
                "install manually: {}".format(exit_code, manual_command()),
            )

    def _done(self, success, text):
        self.installed = success
        self.busy.setRange(0, 1)
        self.busy.setValue(1)
        self.busy.setVisible(False)
        self.message.setText(text)
        self.message.setStyleSheet("" if success else "color: #b3261e;")

    def reject(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(3000)
        super().reject()
