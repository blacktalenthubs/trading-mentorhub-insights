# RC filter analysis — 2026-06-12 04:14 UTC
Scored 33 RC fires (last 14d). Outcome = R-multiple, +1R before -1R.


## rc_4h  —  n= 33 win= 48% (W16/L17/inc0)  avgMFE=+1.70R avgMAE=-0.80R

  by undercut depth %:
         0..0.25: n=  3 win= 67% (W2/L1/inc0)  avgMFE=+2.59R avgMAE=-0.74R
       0.25..0.5: n=  2 win=100% (W2/L0/inc0)  avgMFE=+1.70R avgMAE=-0.06R
          0.5..1: n=  4 win= 75% (W3/L1/inc0)  avgMFE=+2.25R avgMAE=-0.60R
            1..2: n=  4 win= 25% (W1/L3/inc0)  avgMFE=+0.70R avgMAE=-0.91R
             >=2: n= 18 win= 44% (W8/L10/inc0)  avgMFE=+1.76R avgMAE=-0.87R

  by risk (stop) %:
          0..0.5: n=  6 win= 50% (W3/L3/inc0)  avgMFE=+4.57R avgMAE=-1.14R
          0.5..1: n=  5 win= 80% (W4/L1/inc0)  avgMFE=+1.47R avgMAE=-0.30R
            1..2: n= 10 win= 60% (W6/L4/inc0)  avgMFE=+1.42R avgMAE=-0.65R
            2..4: n=  6 win= 33% (W2/L4/inc0)  avgMFE=+0.87R avgMAE=-0.87R
             >=4: n=  6 win= 17% (W1/L5/inc0)  avgMFE=+0.34R avgMAE=-1.04R

  by 4h volume ratio:
          0..0.8: n= 11 win= 73% (W8/L3/inc0)  avgMFE=+1.88R avgMAE=-0.39R
          0.8..1: n=  1 win=  0% (W0/L1/inc0)  avgMFE=+0.91R avgMAE=-1.16R
          1..1.5: n= 15 win= 40% (W6/L9/inc0)  avgMFE=+2.06R avgMAE=-1.05R
        1.5..2.5: n=  6 win= 33% (W2/L4/inc0)  avgMFE=+0.63R avgMAE=-0.85R

  by daily RSI:
           0..30: n=  8 win= 62% (W5/L3/inc0)  avgMFE=+1.65R avgMAE=-0.62R
          30..45: n=  6 win= 67% (W4/L2/inc0)  avgMFE=+2.59R avgMAE=-0.68R
          45..55: n=  5 win= 60% (W3/L2/inc0)  avgMFE=+1.59R avgMAE=-0.65R
          55..70: n= 11 win= 36% (W4/L7/inc0)  avgMFE=+1.76R avgMAE=-0.95R
            >=70: n=  3 win=  0% (W0/L3/inc0)  avgMFE=+0.08R avgMAE=-1.18R

  by hour ET:
          10..12: n= 16 win= 31% (W5/L11/inc0)  avgMFE=+0.72R avgMAE=-0.95R
          12..14: n=  2 win=  0% (W0/L2/inc0)  avgMFE=+2.78R avgMAE=-1.85R
           7..10: n= 13 win= 77% (W10/L3/inc0)  avgMFE=+2.65R avgMAE=-0.48R
            >=16: n=  2 win= 50% (W1/L1/inc0)  avgMFE=+2.33R avgMAE=-0.51R

  by SPY day %:
    (no data)

## raw fires (audit)
  rule         sym    fired          entry risk% under%  vol  rsi    out   mfe    mae
  rc_4h        BTC-USD 06-08 00:50 62806.58   0.3 -2.443  0.6 14.0 worked  4.31    0.0
  rc_4h        ETH-USD 06-08 03:25   1672.8   1.7  1.586 0.63 19.4 failed 0.341 -1.011
  rc_4h        BTC-USD 06-08 08:10 62968.83  0.38  0.403 1.61 14.0 worked 1.311 -0.115
  rc_4h        META   06-08 09:40   584.66  0.93  0.633 1.01 41.5 worked 1.249    0.0
  rc_4h        MDB    06-08 09:45   349.99  1.46  1.705 0.62 54.5 worked 1.491    0.0
  rc_4h        ZETA   06-08 09:50    21.71  1.15 -0.444 0.36 60.5 worked 1.523    0.0
  rc_4h        ORCL   06-08 10:10   210.51  0.55  0.057 1.05 60.1 worked   2.0    0.0
  rc_4h        SWMR   06-08 10:15    58.02   7.7  6.571 0.68 67.5 worked 1.517  -0.55
  rc_4h        AAOI   06-08 11:20   200.54 11.68 -1.619 1.71 56.6 failed 0.301 -1.047
  rc_4h        AAPL   06-08 11:20   314.28   1.8 -0.447 1.49 54.0 failed 0.551 -1.186
  rc_4h        AIP    06-08 11:20    35.41  3.98 -2.196 0.72 57.5 failed 0.635 -1.078
  rc_4h        ARM    06-08 11:20    363.8  6.78 -0.431 1.03 70.6 failed   0.0 -1.099
  rc_4h        AVGO   06-08 11:20   398.41  1.76 -1.494 1.22 43.8 worked 1.036 -0.767
  rc_4h        MDB    06-08 11:20   357.75   3.6  1.705 0.62 54.5 failed   0.0 -1.155
  rc_4h        META   06-08 11:20   589.39  1.72  0.633 1.01 41.5 failed 0.811 -1.093
  rc_4h        MRVL   06-08 11:20   302.91   7.1 -7.595 1.93 74.5 failed 0.095 -1.364
  rc_4h        NBIS   06-08 11:20   234.23  5.46 -2.197 1.25 55.4 failed   0.0 -1.088
  rc_4h        QQQ    06-08 11:20   722.77  1.34 -1.247 1.54 55.0 failed 0.299 -1.137
  rc_4h        TSLA   06-08 11:20   402.85  2.02 -1.577 1.52 49.6 worked 1.103 -0.429
  rc_4h        WDC    06-08 11:20   532.79  2.55 -1.502 1.33 64.1 failed 0.929 -1.372
  rc_4h        FROG   06-08 11:21    87.26  4.73 -0.169 1.18 72.1 failed 0.136 -1.075
  rc_4h        GOOGL  06-08 11:25   364.22  1.01  0.986 1.17 28.2 worked 2.136 -0.837
  rc_4h        ARM    06-09 09:35    346.0  0.21 11.487 1.43 65.3 failed 9.595 -3.041
  rc_4h        NFLX   06-09 09:35    82.05   0.5   None 1.66 18.5 failed 0.671   -1.0
  rc_4h        ARM    06-10 09:35   319.56  2.37 -4.806  0.6 58.0 worked 1.657    0.0
  rc_4h        GOOGL  06-10 09:35   364.03  0.56 -0.513 0.53 28.5 worked  1.35 -0.502
  rc_4h        NFLX   06-10 09:35    81.48  0.61  0.446 1.19 24.5 worked  2.09    0.0
  rc_4h        SWMR   06-10 09:35    60.46   2.8   None 0.86 66.5 failed 0.911  -1.16
  rc_4h        GOOGL  06-10 13:35    356.6  0.15   1.66 1.19 28.5 failed 0.981 -1.482
  rc_4h        SPY    06-10 13:35   728.83  0.06  0.236 1.21 37.2 failed 4.581 -2.209
  rc_4h        AAPL   06-11 09:35   291.42  0.13 -1.395 0.76 41.5 worked 6.658    0.0
  rc_4h        AVGO   06-11 09:35   375.24  1.19  0.167 0.73 43.2 worked 1.176    0.0
  rc_4h        IREN   06-11 09:35    51.27  1.01  0.898 1.15 48.6 worked 4.788 -0.462
