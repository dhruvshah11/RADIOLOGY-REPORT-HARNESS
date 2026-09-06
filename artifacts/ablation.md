| variant                                        | RES_word | RES_char | RES_raw | FINDINGS | IMPRESSION | cRecall |
|------------------------------------------------|---------:|---------:|--------:|---------:|-----------:|--------:|
| copy the template unchanged                    |   0.6393 |   0.5740 |  0.5723 |   0.5656 |     0.8910 |   0.533 |
| full pipeline                                  |   0.3908 |   0.3317 |  0.3325 |   0.3612 |     0.6045 |   0.921 |
| - coordinated-clause splitting                 |   0.3972 |   0.3367 |  0.3374 |   0.3695 |     0.6057 |   0.923 |
| - abnormal findings first in a field           |   0.3999 |   0.3394 |  0.3403 |   0.3734 |     0.6045 |   0.921 |
| - within-field de-duplication                  |   0.3921 |   0.3330 |  0.3338 |   0.3632 |     0.6045 |   0.922 |
| - shorthand expansion                          |   0.3944 |   0.3344 |  0.3351 |   0.3638 |     0.6113 |   0.917 |
| - corpus spell repair                          |   0.3932 |   0.3331 |  0.3339 |   0.3636 |     0.6077 |   0.921 |
| - cue-mismatch penalty                         |   0.3918 |   0.3327 |  0.3335 |   0.3622 |     0.6045 |   0.921 |
| - trailing paragraph for unroutable findings   |   0.3873 |   0.3292 |  0.3297 |   0.3550 |     0.6045 |   0.912 |
| - dictated-summary reuse (impression)          |   0.4180 |   0.3613 |  0.3619 |   0.3612 |     0.6884 |   0.902 |
| - detail trimming (impression)                 |   0.3967 |   0.3371 |  0.3378 |   0.3612 |     0.6321 |   0.921 |
| - drop negatives from impression               |   0.3959 |   0.3339 |  0.3348 |   0.3612 |     0.6711 |   0.932 |
| - template closing line (impression)           |   0.4055 |   0.3439 |  0.3445 |   0.3612 |     0.6449 |   0.910 |
| - numbered impression                          |   0.3963 |   0.3345 |  0.3358 |   0.3612 |     0.6166 |   0.921 |
| - blank line between fields                    |   0.3908 |   0.3317 |  0.3354 |   0.3612 |     0.6045 |   0.921 |
| + existential framing (rejected)               |   0.3946 |   0.3328 |  0.3336 |   0.3657 |     0.6045 |   0.921 |
| + 'is present' framing (rejected)              |   0.4111 |   0.3462 |  0.3470 |   0.3888 |     0.6045 |   0.921 |
| + soften blanket normals (rejected)            |   0.3954 |   0.3375 |  0.3383 |   0.3678 |     0.6045 |   0.923 |
| + reference-phrasing transfer (rejected)       |   0.3965 |   0.3351 |  0.3359 |   0.3693 |     0.6036 |   0.916 |
| + suppress redundant negatives (rejected)      |   0.3985 |   0.3373 |  0.3381 |   0.3712 |     0.6045 |   0.916 |
| + severity-ranked impression (rejected)        |   0.3916 |   0.3326 |  0.3334 |   0.3612 |     0.6093 |   0.921 |
| + recover summary into findings (rejected)     |   0.4086 |   0.3470 |  0.3478 |   0.3838 |     0.6045 |   0.931 |
