| variant                                        | RES_word | RES_char | RES_raw | RES_sent | FINDINGS | IMPRESSION | cRecall |
|------------------------------------------------|---------:|---------:|--------:|---------:|---------:|-----------:|--------:|
| copy the template unchanged                    |   0.6393 |   0.5740 |  0.5723 |   0.6805 |   0.5656 |     0.8910 |   0.533 |
| full pipeline                                  |   0.3742 |   0.3184 |  0.3193 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| - coordinated-clause splitting                 |   0.3793 |   0.3224 |  0.3232 |   0.5476 |   0.3574 |     0.5575 |   0.932 |
| - sequence continuity in routing               |   0.3780 |   0.3216 |  0.3224 |   0.5442 |   0.3559 |     0.5574 |   0.930 |
| - abnormal findings first in a field           |   0.3841 |   0.3267 |  0.3276 |   0.5496 |   0.3639 |     0.5574 |   0.931 |
| - within-field de-duplication                  |   0.3753 |   0.3197 |  0.3205 |   0.5453 |   0.3523 |     0.5574 |   0.932 |
| - shorthand expansion                          |   0.3809 |   0.3250 |  0.3258 |   0.5531 |   0.3531 |     0.5768 |   0.927 |
| - corpus spell repair                          |   0.3765 |   0.3200 |  0.3208 |   0.5411 |   0.3532 |     0.5592 |   0.931 |
| - cue-mismatch penalty                         |   0.3755 |   0.3197 |  0.3205 |   0.5429 |   0.3523 |     0.5574 |   0.931 |
| - trailing paragraph for unroutable findings (drops content) |   0.3715 |   0.3166 |  0.3171 |   0.5337 |   0.3461 |     0.5574 |   0.923 |
| - dictated-summary reuse (impression)          |   0.4140 |   0.3595 |  0.3600 |   0.5698 |   0.3506 |     0.6789 |   0.904 |
| - detail trimming (impression)                 |   0.3805 |   0.3245 |  0.3254 |   0.5425 |   0.3506 |     0.5881 |   0.931 |
| + drop negatives from impression (rejected)    |   0.3798 |   0.3247 |  0.3255 |   0.5399 |   0.3506 |     0.5634 |   0.922 |
| - template closing line (impression)           |   0.3868 |   0.3286 |  0.3294 |   0.5730 |   0.3506 |     0.5955 |   0.922 |
| - numbered impression                          |   0.3784 |   0.3208 |  0.3221 |   0.5786 |   0.3506 |     0.5664 |   0.931 |
| - blank line between fields                    |   0.3742 |   0.3184 |  0.3221 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| + existential framing (rejected)               |   0.3780 |   0.3196 |  0.3205 |   0.5433 |   0.3552 |     0.5574 |   0.931 |
| + 'is present' framing (rejected)              |   0.3941 |   0.3329 |  0.3337 |   0.5550 |   0.3774 |     0.5574 |   0.931 |
| + soften blanket normals (rejected)            |   0.3787 |   0.3240 |  0.3248 |   0.5440 |   0.3570 |     0.5574 |   0.933 |
| + reference-phrasing transfer (rejected)       |   0.3806 |   0.3225 |  0.3233 |   0.5506 |   0.3594 |     0.5574 |   0.927 |
| + suppress redundant negatives (rejected)      |   0.3821 |   0.3241 |  0.3250 |   0.5516 |   0.3608 |     0.5574 |   0.926 |
| + severity-ranked impression (rejected)        |   0.3751 |   0.3192 |  0.3200 |   0.5422 |   0.3506 |     0.5622 |   0.931 |
| + recover summary into findings (rejected)     |   0.3888 |   0.3317 |  0.3325 |   0.5560 |   0.3676 |     0.5574 |   0.932 |
| + learned conditional-logit router (rejected)  |   0.3815 |   0.3250 |  0.3257 |   0.5516 |   0.3601 |     0.5575 |   0.931 |
| + template field-edit prior (rejected)         |   0.3803 |   0.3233 |  0.3241 |   0.5447 |   0.3588 |     0.5578 |   0.931 |
| + Viterbi sequence decoding (no change)        |   0.3742 |   0.3184 |  0.3193 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| + summary starts after last cue (rejected)     |   0.3861 |   0.3279 |  0.3287 |   0.5584 |   0.3581 |     0.6127 |   0.927 |
| + merge unrouted findings into one para        |   0.3742 |   0.3184 |  0.3192 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
| - abnormality gate on the impression           |   0.3830 |   0.3244 |  0.3253 |   0.5612 |   0.3506 |     0.6433 |   0.930 |
| - stricter mining threshold                    |   0.3748 |   0.3185 |  0.3193 |   0.5439 |   0.3514 |     0.5573 |   0.931 |
| + body-region-conditioned statistics (rejected) |   0.3765 |   0.3201 |  0.3209 |   0.5423 |   0.3536 |     0.5572 |   0.931 |
| + bigram routing features (rejected)           |   0.3757 |   0.3195 |  0.3204 |   0.5435 |   0.3529 |     0.5578 |   0.931 |
| + conjunction splitting (rejected)             |   0.3750 |   0.3189 |  0.3198 |   0.5435 |   0.3516 |     0.5574 |   0.931 |
| + trim detail in dictated summary (rejected)   |   0.3840 |   0.3279 |  0.3288 |   0.5493 |   0.3506 |     0.5847 |   0.926 |
| + cost-sensitive impression chooser (no change) |   0.3742 |   0.3184 |  0.3193 |   0.5423 |   0.3506 |     0.5574 |   0.931 |
