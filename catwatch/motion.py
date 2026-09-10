"""Class-independent full-frame motion; no GPU or visit-area dependency."""
import cv2
import numpy as np


class MotionDetector:
    def __init__(self, settings):
        self.settings = settings
        self.background = cv2.createBackgroundSubtractorMOG2(history=450, varThreshold=25, detectShadows=False)
        self.previous = None

    def observe(self, frame):
        height = max(1, round(frame.shape[0]*960/frame.shape[1]))
        small = cv2.resize(frame, (960, height), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5,5), 0)
        allowed = np.ones(gray.shape, dtype=np.uint8)
        for x1,y1,x2,y2 in self.settings['masks']:
            allowed[int(y1*height):int(y2*height),int(x1*960):int(x2*960)] = 0
        foreground = self.background.apply(gray)
        if self.previous is None:
            self.previous = gray
            return 0.0
        delta = cv2.absdiff(gray, self.previous)
        self.previous = gray
        # Actual frame change avoids MOG startup/sustained stationary foreground;
        # background difference also catches gradual movement.
        changed = ((delta > 12) | ((foreground > 0) & (delta > 4))).astype(np.uint8)
        changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((3,3),np.uint8))
        return float(np.count_nonzero(changed & allowed)/max(1,np.count_nonzero(allowed)))


class MotionTracker:
    def __init__(self, store, session):
        self.store, self.session = store, session
        self.pending = self.last = self.mid = None
        self.chunk_start = self.last_saved = None

    def observe(self, stamp, score):
        end = self.session['end']
        moving = self.session['start'] <= stamp < end and score >= self.session['settings']['motion_fraction']
        if moving:
            if self.pending is None:
                self.pending = stamp
            if self.mid is None and stamp-self.pending >= self.session['settings']['motion_seconds']-1e-6:
                self.mid = self.store.open_motion(self.session['id'],self.pending,score)
                self.chunk_start = self.pending
                self.last_saved = stamp
            self.last = stamp
            if self.mid is not None:
                if stamp-self.chunk_start >= 60:
                    self.store.update_motion(self.mid,stamp,score)
                    group = self.store.motion(self.mid)['group_id']
                    self.store.close_motion(self.mid)
                    self.mid = self.store.open_motion(self.session['id'],stamp,score,group)
                    self.chunk_start = stamp
                if stamp-self.last_saved >= .5:
                    self.store.update_motion(self.mid,stamp,score)
                    self.last_saved = stamp
        else:
            if self.mid is None:
                self.pending = None
            # Twenty seconds makes adjacent padded evidence intervals overlap.
            if self.mid is not None and (stamp-self.last >= 20 or stamp >= end):
                self.interrupt(False)

    def interrupt(self, interrupted=True):
        if self.mid is not None:
            self.store.update_motion(self.mid,self.last,0)
            self.store.close_motion(self.mid,interrupted)
        self.mid = self.pending = self.last = None
