Claude Haiku 5.5, median distance spread [95% cluster-bootstrap interval over frames, 2000 resamples, seed 20261025].

| Measure | Median spread | Questions | Frames |
|---|---|---|---|
| Original rotation spread, all distance questions | 7% [6, 9] | 24 | 12 |
| Noise floor (4 repeats, unrotated), all distance questions | 11% [6, 13] | 24 | 12 |
| Original rotation spread, the square-crop questions only | 9% [4, 18] | 10 | 7 |
| Noise floor, the square-crop questions only | 15% [4, 29] | 10 | 7 |
| Square-crop rotation spread | 12% [4, 32] | 10 | 7 |

Questions dropped for an unparsed answer: noise floor [], square crop []. API errors: 0.
Stop reasons: ['end_turn']. Spend recorded: US$0.0609 over 136 calls.

Like-for-like (the 10 square-crop questions): original 9.3% | noise floor 15.0% | square-crop rotations 12.4%.

Per square-crop question (spread %): original rotations | noise floor | square-crop rotations

| Question | Original | Noise floor | Square crop |
|---|---|---|---|
| f1706-met-AB | 11 | 4 | 14 |
| f1809-met-AB | 18 | 11 | 4 |
| f1949-met-AC | 7 | 0 | 11 |
| f2340-met-AB | 20 | 18 | 35 |
| f2713-met-AB | 19 | 13 | 8 |
| f2713-met-BD | 4 | 22 | 4 |
| f2784-met-AD | 17 | 17 | 44 |
| f2784-met-BC | 7 | 11 | 4 |
| f3061-met-BC | 4 | 37 | 32 |
| f3061-met-CD | 2 | 29 | 27 |
