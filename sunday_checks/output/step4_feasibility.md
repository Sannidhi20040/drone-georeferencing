ANTHROPIC_API_KEY: NOT set

Distance questions: 24. Fit entirely inside the centred 1080x1080 square: 10. Cannot fit: 14.

Cannot fit (object pixel positions in the 1920x1080 frame):
  f1619-met-AB: [[95.9, 752.3], [1164.4, 536.5]]
  f1619-met-BD: [[1164.4, 536.5], [1588.7, 1007.1]]
  f1706-met-AC: [[1030.8, 326.9], [1644.0, 109.1]]
  f1809-met-BC: [[1269.3, 445.8], [136.8, 239.3]]
  f1949-met-AB: [[1316.3, 461.4], [1858.5, 907.4]]
  f2071-met-AC: [[1255.8, 435.9], [1763.1, 970.3]]
  f2071-met-BC: [[1246.7, 201.9], [1763.1, 970.3]]
  f2340-met-BC: [[1368.0, 72.4], [1814.7, 775.5]]
  f2639-met-AD: [[747.4, 550.1], [1893.1, 797.3]]
  f2639-met-BD: [[1349.4, 104.0], [1893.1, 797.3]]
  f483-met-AB: [[790.4, 85.7], [102.5, 87.9]]
  f483-met-BC: [[102.5, 87.9], [1895.6, 167.7]]
  f545-met-AC: [[796.6, 96.7], [1886.5, 200.0]]
  f545-met-BC: [[1900.9, 630.8], [1886.5, 200.0]]

Saved Haiku 5.5 distance calls: mean 1921 input / 464 output tokens per call -> about US$0.0004 per call at $0.1/$0.5 per million tokens.
Noise floor: 24 questions x 4 repeats = 96 calls -> about US$0.041.
Square crops: 10 questions x 4 rotations = 40 calls -> about US$0.017 (the crop has fewer pixels than the 1568x882 frames, so this is if anything high).
Total about US$0.058; hard stop at US$1.00.
