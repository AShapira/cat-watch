"""Display-driven background admission; missing or stale signals stay quiet."""
import json
import math
import os
from pathlib import Path
import time


class QuietDeferred(Exception):
    """A background job yielded without consuming a failure attempt."""


def training_locked():
    return os.environ.get('CATWATCH_TRAINING_PAUSED') == '1'


class PerformancePolicy:
    def __init__(self, path=None):
        self.path = path if path is not None else os.environ.get('CATWATCH_DISPLAY_STATE', '')
        self._until = 0
        self._status = None

    def status(self):
        now = time.monotonic()
        if self._status is not None and now < self._until:
            return dict(self._status)
        state, reason, quiet = 'unknown', 'Display signal unavailable', True
        if not self.path:
            state, reason, quiet = 'unmanaged', 'Automatic quiet mode is not configured', False
        else:
            try:
                data = json.loads(Path(self.path).read_text())
                age = time.time() - float(data['updated_unix'])
                state = data['display']
                if data.get('schema') != 1 or state not in ('on', 'off', 'dimmed', 'unknown'):
                    raise ValueError('Invalid display state')
                if not math.isfinite(age) or not -5 <= age <= 20:
                    state, reason = 'unknown', 'Display signal expired; protecting workstation responsiveness'
                else:
                    quiet = state != 'off'
                    reason = {'on': 'Screen on', 'dimmed': 'Screen dimmed', 'off': 'Screen off',
                              'unknown': 'Waiting for Windows display notification'}[state]
            except (OSError, ValueError, TypeError, KeyError):
                state = 'unknown'
        self._status = {'quiet': quiet, 'display': state, 'reason': reason,
                        'managed': bool(self.path), 'detector_fps': 1 if quiet else 2,
                        'training_locked': training_locked()}
        self._until = now + .5
        return dict(self._status)

    def quiet(self):
        return self.status()['quiet']


def policy_for(runtime):
    # Small fixture runtimes and integrations need the same policy as the app.
    if not hasattr(runtime, 'performance'):
        runtime.performance = PerformancePolicy()
    return runtime.performance
