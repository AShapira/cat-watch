# Cat activities v1

Label visible actions, not assumed intentions or area names. A cat next to a bowl
may be sniffing, grooming, drinking, eating or doing something unclear.

Choose the subject assessment and whether this clip is fully or partially labeled.
Drag on the video timeline to mark each interval. Label transitions separately:
sniffing -> eating -> grooming. Prefer a specific action over moving/stationary.
Use one primary behavior at a time; incompatible overlaps need correction.

Fully labeled means every frame has a label, including unclear and no-cat time.
Partially labeled clips contribute only explicitly marked intervals. Unmarked time
is never negative training data. Skipping a task is not a no-cat annotation.

Use unclear when the mouth or body is obscured, image quality is insufficient, or
the action cannot be distinguished. Do not label eating/drinking from head position
alone. Grooming a paw beside a water bowl is grooming, not drinking.

Litter digging, elimination posture and covering are distinct visible behaviors.
Do not infer successful elimination, urine/feces, health, hunger or quantities.
Choose digging when digging versus covering cannot be distinguished.

Mark activity beginning/ending outside the clip with the boundary flags. These
describe incomplete observation, not a guessed start/end. Flag clips containing
multiple cats; they are excluded from the initial single-cat supervised dataset.

Model notes and predictions are suggestions. Check them against the video before
submitting. Camera capture times are estimates from the recording cadence, not
precision measurements. Frame labels refer to the exported review video's frames.
