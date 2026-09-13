from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from ..capture.obs import ObsCapture, load_image
from ..recognition import OpponentRecognizer, ALGORITHM_VERSION
from ..data.snapshot import SnapshotManager
from ..data.storage import digest


class AnalysisWorker(QObject):
    finished = Signal(int, str, object, str)

    def __init__(self, data_dir, layout_path=None, obs=None):
        super().__init__()
        self.data_dir, self.layout_path = data_dir, layout_path
        self.obs = obs or ObsCapture()
        self.recognizer = None
        self.snapshots = SnapshotManager(data_dir, layout_path)
        self.recognizer_token = None
        self.cancelled = Event()

    @Slot(int, str, object)
    def run(self, revision, operation, payload):
        result, error = None, ""
        try:
            if operation == "sources":
                result = self.obs.sources(payload)
            else:
                snapshot = self.snapshots.candidate()
                image = self.obs.screenshot(payload) if operation == "obs" else load_image(payload)
                if not self.cancelled.is_set():
                    recognition_key = (str(snapshot.data_dir), snapshot.layout_hash, ALGORITHM_VERSION)
                    recognizer = self.recognizer
                    if recognizer is None or self.recognizer_token != recognition_key:
                        recognizer = OpponentRecognizer(snapshot.data_dir, snapshot.layout_path)
                    if digest(snapshot.layout_path.read_bytes()) != snapshot.layout_hash:
                        raise ValueError('识别布局在加载期间变化，请重新分析。')
                    if not self.cancelled.is_set():
                        recognition, normalized, crops = recognizer.recognize(image)
                        if not self.cancelled.is_set():
                            self.recognizer, self.recognizer_token = recognizer, recognition_key
                            self.snapshots.current = snapshot
                            recognition['snapshot_token'] = snapshot.token
                            result = {"recognition": recognition, "image": image, "crops": crops,
                                      "snapshot": snapshot}
        except Exception as exc:
            error = str(exc)
        self.finished.emit(revision, operation, result, error)
