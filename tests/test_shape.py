"""Фикстуры повторяют формат ответов Final Surge (Garmin -> Final Surge); все значения синтетические."""
from finalsurge_mcp import shape

RUN_ACTIVITY = {
    "activity_type_name": "Run", "activity_type_color": "#8c8c8c", "activity_sub_type_name": None,
    "planned_amount": 13.0, "planned_amount_type": "km", "planned_duration": None,
    "duration": 3912.3049, "time_elapsed": 4500.5, "time_timer": 3912.305, "time_moving": 3912.305,
    "amount": 12.8, "amount_type": "km", "pace_display": "5:06", "pace_display_type": "min/km",
    "speed_max": 7.5, "power_avg": 310, "power_max": 820, "weighted_power": 322, "variability": 1.04,
    "meanmax_power_30": 560, "cadence_avg": 172, "cadence_max": 188, "hr_avg": 148, "hr_max": 169,
    "elevation_gain": 41.0, "elevation_loss": 38.0, "calories": 860,
    "vertical_oscillation_avg": 88, "ground_contact_time_avg": 248.6, "ground_contact_balance_avg": 50.2,
    "stride_length_avg": 1262.0, "vertical_ratio_avg": 7.1, "equipment": None,
    "Laps": [
        {"number": 1, "duration": 300.4, "amount": 1.0, "amount_type": "km", "pace_display": "5:00",
         "pace_display_type": "min/km", "hr_avg": 140, "hr_max": 150, "power_avg": 400, "cadence_avg": 165,
         "elevation_gain": 0.0, "calories": 0},
        {"number": 2, "duration": 290.0, "amount": 1.0, "amount_type": "km", "pace_display": "4:50",
         "pace_display_type": "min/km", "hr_avg": 150, "hr_max": 160},
    ],
}

WORKOUT = {
    "key": "k1", "workout_date": "2026-09-15T00:00:00", "workout_time": "07:15:20",
    "workout_status_text": "Completed", "name": None, "description": None, "is_race": False,
    "CommentCount": 0, "has_structured_workout": False, "coach_name": None,
    "MapURL": "https://log.finalsurge.com/Delivery/WorkoutMap?d=...", "wahoo_sync_available": False,
    "external_data_source": "Garmin Connect Sync: 1-file -- Garmin Forerunner 965",
    "Activities": [RUN_ACTIVITY],
}

PLANNED = {
    "key": "k2", "workout_date": "2026-10-08T00:00:00", "workout_time": None, "workout_status_text": "Planned",
    "name": "Easy ride", "description": "Z1-Z2",
    "Activities": [{"activity_type_name": "Bike", "planned_duration": 5400.0, "elevation_gain_type": "me"}],
}


def test_hms():
    assert shape.hms(3725.4) == "1:02:05"
    assert shape.hms(95) == "1:35"
    assert shape.hms(None) is None


def test_list_item_is_compact_plan_vs_actual():
    w = shape.workout(WORKOUT)
    assert w["workout_key"] == "k1" and w["date"] == "2026-09-15" and w["time"] == "07:15"
    a = w["activities"][0]
    assert a["sport"] == "Run"
    assert a["planned"] == {"distance": "13 km"}
    assert a["actual"]["duration"] == "1:05:12" and a["actual"]["pace"] == "5:06 min/km"
    assert a["actual"]["elapsed"] == "1:15:01"          # пауза > минуты показывается
    assert "moving" not in a["actual"]                  # совпадает с duration
    assert a["actual"]["power_np"] == 322 and a["actual"]["hr_avg"] == 148
    assert a["laps_count"] == 2 and "laps" not in a
    assert "ground_contact_ms" not in a["actual"]       # динамика только в деталях
    for junk in ("MapURL", "wahoo_sync_available", "source", "comments", "race"):
        assert junk not in w
    assert len(str(w)) < 600


def test_planned_workout():
    w = shape.workout(PLANNED)
    assert w == {"workout_key": "k2", "date": "2026-10-08", "status": "Planned", "name": "Easy ride",
                 "description": "Z1-Z2", "activities": [{"sport": "Bike", "planned": {"duration": "1:30:00"}}]}


def test_detail_has_laps_and_running_dynamics():
    w = shape.workout(WORKOUT, detailed=True)
    a = w["activities"][0]
    assert a["actual"]["vertical_oscillation_cm"] == 8.8
    assert a["actual"]["stride_length_m"] == 1.26
    assert a["actual"]["ground_contact_ms"] == 249
    assert a["actual"]["speed_max_kmh"] == 27.0
    assert a["laps"][0] == {"n": 1, "time": "5:00", "distance": "1 km", "pace": "5:00 min/km",
                            "hr_avg": 140, "hr_max": 150, "power_avg": 400, "cadence_avg": 165}
    assert w["source"].startswith("Garmin")


def test_statistics_zones_and_power_curve():
    st = {
        "zone_heartrate": [
            {"number": 1, "name": "Zone 1", "unit_low": 115.0, "unit_high": 134.0, "unity_label": "bpm", "time": 300.0},
            {"number": 2, "name": "Zone 2", "unit_low": 135.0, "unit_high": 152.0, "unity_label": "bpm", "time": 900.0},
        ],
        "zone_power": None,
        "max_power": [{"period": p, "value": 600 - p / 10} for p in list(range(1, 61)) + [300, 1200, 3600]],
    }
    out = shape.statistics(st)
    assert out["time_in_zones_heart_rate"] == [
        {"zone": "Zone 1", "range": "115–134 bpm", "time": "5:00", "pct": 25},
        {"zone": "Zone 2", "range": "135–152 bpm", "time": "15:00", "pct": 75},
    ]
    assert out["best_power_w"] == {"0:05": 600, "0:15": 598, "0:30": 597, "1:00": 594, "5:00": 570,
                                   "20:00": 480, "1:00:00": 240}
    assert shape.statistics(None) == {}


def test_zones_and_zone_history():
    zl = [{"activity_type_name": "Run", "zone_key": "z", "zone_type": "H", "zone_threshold": 172.0, "zone_max": 190,
           "zone_last_modified": "2026-02-01T12:00:00", "zone_1_name": "Zone 1", "zone_1_low": 115.0, "zone_1_high": 134.0,
           "zone_2_name": "Zone 2", "zone_2_low": 135.0, "zone_2_high": 152.0, "zone_3_low": None, "zone_3_high": None}]
    z = shape.zones(zl)[0]
    assert z["type"] == "heart_rate" and z["threshold"] == 172 and z["updated"] == "2026-02-01"
    assert z["zones"] == [{"zone": "Zone 1", "low": 115, "high": 134}, {"zone": "Zone 2", "low": 135, "high": 152}]
    h = {"zone_data": [{"zone_name": "Zone 1", "zone_low": "115", "zone_high": "134", "zone_time": 3600.0},
                       {"zone_name": "Zone 2", "zone_low": "135", "zone_high": "152", "zone_time": 0.0}],
         "zone_label": "bpm", "total_time": 3600.0}
    out = shape.zone_history([(zl[0], h)])
    assert out[0]["total"] == "1:00:00"
    assert out[0]["zones"][0] == {"zone": "Zone 1", "range": "115–134 bpm", "time": "1:00:00", "pct": 100}
    assert out[0]["zones"][1] == {"zone": "Zone 2", "range": "135–152 bpm", "time": "0:00"}


def test_training_summary_by_week():
    days = [
        {"workout_date": "2026-09-28T00:00:00", "type_data": [  # понедельник
            {"activity_type_name": "Run", "count": 1, "total_amount": 15000.0, "total_duration": 3912.0, "total_calories": 860.0}]},
        {"workout_date": "2026-10-04T00:00:00", "type_data": [  # воскресенье той же недели
            {"activity_type_name": "Run", "count": 1, "total_amount": 10000.0, "total_duration": 3000.0, "total_calories": 700.0},
            {"activity_type_name": "Strength Training", "count": 1, "total_amount": 0.0, "total_duration": 1200.0, "total_calories": 0.0}]},
        {"workout_date": "2026-10-05T00:00:00", "type_data": [
            {"activity_type_name": "Bike", "count": 1, "total_amount": 30000.0, "total_duration": 3600.0, "total_calories": 600.0}]},
    ]
    out = shape.training_summary(days)
    assert out["total"] == {"count": 4, "duration": "3:15:12"}
    assert out["by_sport"]["Run"] == {"count": 2, "duration": "1:55:12", "distance_km": 25, "calories": 1560}
    assert out["by_sport"]["Strength Training"] == {"count": 1, "duration": "20:00"}
    assert [w["week_start"] for w in out["by_week"]] == ["2026-09-28", "2026-10-05"]
    assert out["by_week"][0]["count"] == 3
    assert "by_week" not in shape.training_summary(days, "total")
    months = shape.training_summary(days, "month")["by_month"]
    assert [(m["month"], m["count"]) for m in months] == [("2026-09", 1), ("2026-10", 3)]
    assert [d["date"] for d in shape.training_summary(days, "day")["by_day"]] == ["2026-09-28", "2026-10-04", "2026-10-05"]
