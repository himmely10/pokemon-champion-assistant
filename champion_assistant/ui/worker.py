from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from ..capture.obs import ObsCapture, load_image
from ..recognition import OpponentRecognizer


class AnalysisWorker(QObject):
    finished = Signal(int, str, object, str)

    def __init__(self, data_dir, layout_path=None, obs=None):
        super().__init__()
        self.data_dir, self.layout_path = data_dir, layout_path
        self.obs = obs or ObsCapture()
        self.recognizer = None
        self.cancelled = Event()

    @Slot(int, str, object)
    def run(self, revision, operation, payload):
        result, error = None, ""
        try:
            if operation == "sources":
                result = self.obs.sources(payload)
            else:
                image = self.obs.screenshot(payload) if operation == "obs" else load_image(payload)
                if not self.cancelled.is_set():
                    if self.recognizer is None:
                        self.recognizer = OpponentRecognizer(self.data_dir, self.layout_path)
                    if not self.cancelled.is_set():
                        recognition, normalized, crops = self.recognizer.recognize(image)
                        result = {"recognition": recognition, "image": image, "crops": crops}
        except Exception as exc:
            error = str(exc)
        self.finished.emit(revision, operation, result, error)
