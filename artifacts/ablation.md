| variant                                        | RES_word | RES_char | RES_raw | RES_sent | FINDINGS | IMPRESSION | cRecall |
|------------------------------------------------|---------:|---------:|--------:|---------:|---------:|-----------:|--------:|
| copy the template unchanged                    |   0.6393 |   0.5740 |  0.5723 |   0.6805 |   0.5656 |     0.8910 |   0.533 |
| full pipeline                                  |   0.3748 |   0.3185 |  0.3193 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| - coordinated-clause splitting                 |   0.3804 |   0.3225 |  0.3234 |   0.5471 |   0.3589 |     0.5575 |   0.933 |
| - sequence continuity in routing               |   0.3780 |   0.3214 |  0.3223 |   0.5445 |   0.3559 |     0.5573 |   0.931 |
| - abnormal findings first in a field           |   0.3844 |   0.3268 |  0.3277 |   0.5506 |   0.3644 |     0.5573 |   0.931 |
| - within-field de-duplication                  |   0.3757 |   0.3197 |  0.3205 |   0.5469 |   0.3529 |     0.5573 |   0.932 |
| - shorthand expansion                          |   0.3817 |   0.3252 |  0.3260 |   0.5550 |   0.3540 |     0.5768 |   0.927 |
| - corpus spell repair                          |   0.3774 |   0.3203 |  0.3212 |   0.5424 |   0.3543 |     0.5592 |   0.931 |
| - cue-mismatch penalty                         |   0.3761 |   0.3198 |  0.3206 |   0.5445 |   0.3531 |     0.5573 |   0.931 |
| - trailing paragraph for unroutable findings (drops content) |   0.3722 |   0.3168 |  0.3173 |   0.5353 |   0.3470 |     0.5573 |   0.923 |
| - dictated-summary reuse (impression)          |   0.4146 |   0.3597 |  0.3602 |   0.5713 |   0.3514 |     0.6787 |   0.905 |
| - detail trimming (impression)                 |   0.3811 |   0.3246 |  0.3254 |   0.5441 |   0.3514 |     0.5880 |   0.931 |
| + drop negatives from impression (rejected)    |   0.3803 |   0.3248 |  0.3255 |   0.5415 |   0.3514 |     0.5633 |   0.922 |
| - template closing line (impression)           |   0.3874 |   0.3287 |  0.3295 |   0.5742 |   0.3514 |     0.5957 |   0.922 |
| - numbered impression                          |   0.3790 |   0.3208 |  0.3221 |   0.5799 |   0.3514 |     0.5664 |   0.931 |
| - blank line between fields                    |   0.3748 |   0.3185 |  0.3222 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| + existential framing (rejected)               |   0.3783 |   0.3195 |  0.3204 |   0.5448 |   0.3556 |     0.5573 |   0.931 |
| + 'is present' framing (rejected)              |   0.3947 |   0.3330 |  0.3338 |   0.5566 |   0.3783 |     0.5573 |   0.931 |
| + soften blanket normals (rejected)            |   0.3794 |   0.3242 |  0.3250 |   0.5457 |   0.3580 |     0.5573 |   0.933 |
| + reference-phrasing transfer (rejected)       |   0.3804 |   0.3219 |  0.3227 |   0.5525 |   0.3592 |     0.5569 |   0.927 |
| + suppress redundant negatives (rejected)      |   0.3823 |   0.3241 |  0.3250 |   0.5526 |   0.3612 |     0.5573 |   0.926 |
| + severity-ranked impression (rejected)        |   0.3757 |   0.3192 |  0.3201 |   0.5437 |   0.3514 |     0.5621 |   0.931 |
| + recover summary into findings (rejected)     |   0.3894 |   0.3318 |  0.3326 |   0.5575 |   0.3685 |     0.5573 |   0.933 |
| + learned conditional-logit router (rejected)  |   0.3818 |   0.3251 |  0.3258 |   0.5527 |   0.3608 |     0.5574 |   0.931 |
| + template field-edit prior (rejected)         |   0.3811 |   0.3236 |  0.3244 |   0.5463 |   0.3599 |     0.5578 |   0.931 |
| + Viterbi sequence decoding (no change)        |   0.3748 |   0.3185 |  0.3193 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| + summary starts after last cue (rejected)     |   0.3866 |   0.3279 |  0.3288 |   0.5597 |   0.3588 |     0.6126 |   0.927 |
| + merge unrouted findings into one para        |   0.3748 |   0.3185 |  0.3192 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| - abnormality gate on the impression           |   0.3836 |   0.3246 |  0.3254 |   0.5628 |   0.3514 |     0.6437 |   0.931 |
