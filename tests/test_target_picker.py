"""Tests for the unified single-target picker (Sub-spec A / #64)."""

from analytics.target_picker import parse_nearby_levels, pick_target


# --- parse_nearby_levels ----------------------------------------------------

def test_parse_nearby_levels_basic():
    csv = "ema8|123.45|EMA 8,pdh|150.00|PDH,pwh|160.5|PWH"
    out = parse_nearby_levels(csv)
    assert out == [("EMA 8", 123.45), ("PDH", 150.00), ("PWH", 160.5)]


def test_parse_nearby_levels_blank_and_bad():
    assert parse_nearby_levels("") == []
    assert parse_nearby_levels(None) == []
    # bad value is skipped, good ones kept
    assert parse_nearby_levels("pdh|abc|PDH,pwh|160|PWH") == [("PWH", 160.0)]


# --- Case A: nearest level above (long) -------------------------------------

def test_long_picks_nearest_level_above():
    cands = [("PDH", 150.0), ("PWH", 160.0), ("PDL", 90.0)]
    t = pick_target(100.0, cands, "BUY")
    assert t["kind"] == "level"
    assert t["value"] == 150.0
    assert t["label"] == "PDH"


def test_long_skips_levels_within_03pct():
    # 100.2 is within 0.3% of entry 100 -> skipped; next real target is 150
    cands = [("noise", 100.2), ("PDH", 150.0)]
    t = pick_target(100.0, cands, "BUY")
    assert t["value"] == 150.0


def test_wall_clusters_within_1pct():
    # PDH 405.94 + EMA50 406.06 + EMA100 405.17 = one wall (within 1%)
    cands = [("PDH", 405.94), ("EMA50", 406.06), ("EMA100", 405.17), ("PMH", 450.0)]
    t = pick_target(400.0, cands, "BUY")
    assert t["kind"] == "level"
    assert t["value"] == 405.17          # nearest of the wall
    assert t["wall_size"] == 3           # three levels clustered


# --- Case A: nearest level below (short) ------------------------------------

def test_short_picks_nearest_level_below():
    cands = [("PDL", 90.0), ("PWL", 80.0), ("PDH", 150.0)]
    t = pick_target(100.0, cands, "SHORT")
    assert t["kind"] == "level"
    assert t["value"] == 90.0


# --- Case B: no level -> RSI / EOD ------------------------------------------

def test_blue_sky_long_rsi_below_70_targets_70():
    t = pick_target(100.0, [("PDL", 90.0)], "BUY", rsi=55.0)
    assert t["kind"] == "rsi"
    assert t["value"] == 70.0


def test_blue_sky_long_strong_momentum_targets_80():
    t = pick_target(100.0, [("PDL", 90.0)], "BUY", rsi=71.0)
    assert t["kind"] == "rsi"
    assert t["value"] == 80.0


def test_blue_sky_no_rsi_falls_back_to_eod():
    t = pick_target(100.0, [("PDL", 90.0)], "BUY", rsi=None)
    assert t["kind"] == "eod"
    assert t["value"] is None


def test_invalid_entry_returns_none():
    assert pick_target(None, [("PDH", 1.0)], "BUY") is None
    assert pick_target(0, [("PDH", 1.0)], "BUY") is None


# --- SNDK worked examples (Sub-spec A) --------------------------------------

SNDK = [
    ("PDH", 2074.59), ("PWH", 2021.65), ("PDL", 1938.00),
    ("PMH", 1708.83), ("PWL", 1536.00),
    ("EMA21", 1893.65), ("EMA50", 1720.67), ("EMA200", 1429.01),
]


def test_sndk_pwh_held_targets_pdh_not_plus_075pct():
    # The bug fix: PWH held @ 2021 must target PDH 2074 (old code ignored PDH).
    t = pick_target(2021.65, SNDK, "BUY")
    assert t["kind"] == "level"
    assert t["value"] == 2074.59


def test_sndk_pdl_held_targets_pwh():
    t = pick_target(1938.00, SNDK, "BUY")
    assert t["value"] == 2021.65         # nearest wall above = PWH, not a leap to PDH


def test_sndk_pwl_held_targets_pmh_ema_wall():
    # PMH 1708.83 + EMA50 1720.67 cluster within 1% -> wall, nearest = PMH
    t = pick_target(1536.00, SNDK, "BUY")
    assert t["value"] == 1708.83
    assert t["wall_size"] == 2


def test_sndk_blue_sky_gap_and_go_targets_rsi_80():
    # Entry @ 2184, every level below, RSI 71 -> momentum target RSI 80.
    t = pick_target(2184.75, SNDK, "BUY", rsi=70.93)
    assert t["kind"] == "rsi"
    assert t["value"] == 80.0
