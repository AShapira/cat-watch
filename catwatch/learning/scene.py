"""Local geometric camera-movement check against confirmed calibration pixels."""
import cv2
import numpy as np


def displacement(reference, current):
    if reference.shape[:2] != current.shape[:2]:
        return 1.
    height, width = reference.shape[:2]
    detector = cv2.ORB_create(nfeatures=1200)
    def features(frame):
        small = cv2.resize(frame, (640, max(1, round(height*640/width))))
        return detector.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), None)
    a, da = features(reference); b, db = features(current)
    if da is None or db is None or min(len(da), len(db)) < 30:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    matches = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .7*p[1].distance]
    if len(matches) < 30:
        return None
    x = np.float32([a[m.queryIdx].pt for m in matches])
    y = np.float32([b[m.trainIdx].pt for m in matches])
    transform, mask = cv2.estimateAffinePartial2D(x, y, method=cv2.RANSAC, ransacReprojThreshold=3)
    if transform is None or mask.sum() < 25 or mask.mean() < .6:
        return None
    inliers = x[mask.ravel().astype(bool)]
    if np.ptp(inliers[:, 0]) < 250 or np.ptp(inliers[:, 1]) < height*640/width*.35:
        return None
    corners = np.float32([[0,0],[640,0],[0,height*640/width],[640,height*640/width]])
    moved = corners @ transform[:, :2].T + transform[:, 2]
    return float(np.median(np.linalg.norm(moved-corners, axis=1))/640)


class SceneGuard:
    def __init__(self):
        self.identity = None
        self.reference = None
        self.strikes = 0

    def check(self, source, runtime, store):
        session = source.investigation()
        if not session or not runtime.frame:
            return
        calibration = session['config_snapshot'].get('calibration', {})
        if self.identity != calibration.get('id'):
            self.identity = calibration.get('id')
            path = (source.root/calibration.get('reference_image', '')).resolve()
            self.reference = cv2.imread(str(path)) if path.is_relative_to(source.root.resolve()) and path.is_file() else None
            self.strikes = 0
        if self.reference is None:
            store.set_meta('scene_check', 'Calibration reference unavailable')
            return
        current = cv2.imdecode(np.frombuffer(runtime.frame, np.uint8), cv2.IMREAD_COLOR)
        if current is None:
            return
        shift = displacement(self.reference, current)
        store.set_meta('scene_check', 'Insufficient scene detail to check camera movement' if shift is None else {'displacement': shift})
        self.strikes = self.strikes+1 if shift is not None and shift > .05 else 0
        if self.strikes >= 3:
            store.configure({'continuous': False}, internal=True)
            source.stop_investigation()
            store.notice('camera-moved:'+str(session['id']), 'system',
                         {'text': 'The camera view has moved. Monitoring is paused; confirm the camera areas again.'})
