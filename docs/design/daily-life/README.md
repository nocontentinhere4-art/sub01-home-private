# daily-life: day template (draft, pass 2)

Draft of SUB-01's typical week: a 20-year-old student who lives alone in a small Kichijoji apartment, Tokyo. Design data, read by `daily_plan.py`.

- Status: `daily_plan.hint()` reads this file, and `life.py` calls it on each update (except while he sleeps in bed) through `day_plan_hint()`. The result is `life.day_hint`: `PLAN_BONUS` (0.35) is added to that activity only when life already scores it above zero. The mind's `plan_hint` takes precedence, and needs still come first. Nothing here starts an activity by itself.
- Time: simulated Tokyo clock (HH:MM) at 24x. 24:00 or later is after midnight of the same day.
- Names: activity, place and route names are life.py's (`ACTIVITIES`, `PLACES`) and `web/tokyo_routes.json`. Needs are life.py's (hunger, boredom) or proposed (P10).
- `"activity": null` marks an entry life.py cannot run yet; its `"proposal"` id points to the list below. A null entry never blocks the hint.

## How hint() reads the template

- Shared part only: a typical weekday at home (weekday sleep, daily items, meals, leisure). `day_types` (class, library, job, weekend) need a weekday, which `hint()` does not have.
- An entry takes part from `earliest_start` to `latest_start`, both ends included. A sleep entry (one with `wake`) takes part from `target_start` to `wake.target`: the whole night, not only its bedtime window.
- The weights are chances on a day, or shares of a meal (a step has its option's weight). The weights of one activity add up, and the activity with the largest total wins. Ties go to the activity whose entry comes first in the file. Null and weight 0 are ignored.
- Windows past 24:00 work (25:00 is 01:00).

## The typical weekday at home

`hint()` for each minute of the day, as `tests/test_daily_plan.py` checks it:

| Time | Hint | Why (entries and weights) |
|---|---|---|
| 00:00-00:30 | listen_music | lz_music (0.12), in bed |
| 00:30-08:00 | sleep | sleep_weekday (1.00): target bedtime 00:30 to target wake 08:00 |
| 08:00-09:00 | phone | lz_phone (0.15), in bed; the breakfast bakery trip (0.10, from 08:30) is less |
| 09:00-10:00 | eat | breakfast: the eat steps of the four options add up to 1.00 |
| 10:00-11:00 | buy_bread | errand_bread_stock (0.40), while the bakery is open |
| 11:00-12:00 | research | lz_research (0.20), at the computer; the lunch ramen order (0.10) is less |
| 12:00-12:30 | eat | lunch: the eat steps add up to 1.00 |
| 12:30-16:30 | research | lz_research (0.20): the long afternoon at the desk |
| 16:30-17:30 | park | lz_park (0.18): the outing; life's park opens at 08:00 on weekdays |
| 17:30-18:15 | buy_bread | errand_bread_dinner (0.40): bread for dinner and the evening |
| 18:15-18:30 | phone | lz_phone (0.15); the dinner ramen order (0.10) is less |
| 18:30-19:00 | play_console | lz_console (0.25), before dinner; the dinner stock eat (0.20) is less |
| 19:00-21:00 | eat | dinner: the eat steps add up to 0.30 to 1.00 as options finish; the konbini trip (0.30, 20:00-20:30) is less than eating |
| 21:00-22:30 | play_console | lz_console (0.25): the evening TV or console |
| 22:30-23:30 | phone | lz_phone (0.15), in bed |
| 23:30-00:00 | listen_music | lz_music (0.12), in bed with headphones |

What the checks cover:

- Every hour has an activity from `life.ACTIVITIES`, so there are no dead hours. The night is sleep, from bedtime to wake. life.py never scores `sleep` (the sleep engine starts and ends it), so that span gives no bonus; it is the template's statement of the night.
- Every hinted activity is one life can start at that hour: `buy_bread` only while the bakery is open (06:58 to 19:58 with the walk), `buy_konbini` only while it is closed, `park` from 08:00 on weekdays and home by 20:00, `order_food` from 10:00 to 23:30, and desk activities not between 00:00 and 06:00.
- Delivery is never the plan. `order_food` and `get_delivery` never win an hour: the ramen options are 10% each, and the courier takes about 25 simulated minutes from order to eating, while bread at home is eaten at once. `buy_konbini` never wins one either, because eating is the more likely activity at dinner. `chat` and `use_computer` are in the template, but they never beat research or phone.
- Life still depends on its own state: eat needs food in stock (see P12), chat needs waiting messages, the console needs `home_enabled`, and order_food needs hunger.

**Away days.** On class days (3 a week, 12:50 to about 16:20), library days (about 09:30 to 12:00) and job days (12:50 to about 18:00: 40% of non-class weekdays, Saturday, half of Sundays), he is out. At 13:00 he is out on about three days in four. `hint()` has no away state, so on those days the sequence is not followed: life still scores home activities in those hours. This is the largest gap (proposal A1 below).

**Weekends.** The hint is a weekday. Friday and Saturday nights (`day_types.weekend`) are later: onset 01:15, wake 09:30. The weekend shifts and Sunday chores are in `day_types`, for a consumer that knows the weekday. sleep.py has one alarm, at 08:00, for every day.

## Null entries: proposals and decisions

No null entry can take an existing life activity without misrepresenting it, so all 17 stay null. The brief's examples fail the same test: a shower is not `use_bathroom` (a 1-2 minute bladder break), and study away at the library is not `research` (which is at the desk at home).

| Entries (id) | Proposal | Closest life.py activity | Why it stays null |
|---|---|---|---|
| hyg_body_am | P1 shower | use_bathroom | use_bathroom is a 1-2 min bladder break (`home_bladder`), not a wash |
| hyg_teeth_am, hyg_teeth_pm | P2 brush_teeth | use_bathroom | 3-5 min at the sink; no life activity for it |
| chore_after_meal | P4 dishes | none | life.py has no kitchen or cleaning activity |
| bf_home_make, ln_home_make, dn_home_make | P5 cook | eat | eating comes after cooking; mapping cook to eat starts a meal before any food exists |
| class_block_1, class_block_2 | P3 attend_class | research | away at campus for 90 min; research is at the desk at home |
| outside_library | P7 library_study | research | away at the library; the same reason as P3 |
| outside_job, weekend_job_sat, weekend_job_sun | P6 work_shift | none | away at the job for 300 min; no life activity |
| weekend_chore_clean | P8 clean_apartment | none | no life activity; once a week |
| weekend_chore_laundry | P9 laundry | none | no life activity; once a week; needs a washer or bathroom point |
| bf_konbini_buy, ln_konbini_buy | P12 konbini while the bakery is open | buy_konbini | life.py scores buy_konbini only while the bakery is closed (G1); the eat steps stay |

## TODO for life.py (not edited here)

1. **Away state (A1).** Class blocks, library and job: no home activity and no day hint while away. Needs campus, library and job places (P11). Travel is not modelled.
2. **Hygiene.** `shower` (bathroom, 10-15 min) and `brush_teeth` (3-5 min), with a bathroom place. `use_bathroom` stays the bladder break.
3. **Cooking and dishes.** `cook` (kitchen, 10-15 min, before a home meal) and `dishes` (after a meal), with a kitchen point.
4. **Cleaning and laundry.** `clean_apartment` and `laundry`, once a week on Sunday; needs chores and hygiene (P10).
5. **Konbini in the bakery's hours (P12).** Relax G1 for breakfast and lunch, or drop those two options from the template.
6. **A weekday for the hint.** `daily_plan.hint(hour)` takes no day. Pass one, so that weekend and class-day variants of `day_types` can be used.
7. **Alarm and wake.** The template's wake target is 08:00 (sleep.py's `ALARM_HOUR`); the brief's 8 to 9 is the wake window. If the owner wants the alarm at 08:30, move both together.
8. **Needs.** energy, hygiene, chores, obligation and curiosity (P10). life.py scores only hunger and boredom.
9. **Courier.** `get_delivery` is never scored: `update()` starts it when the courier arrives, so the courier windows are targets only.
10. **Caps on top of the hint.** Research past 3 sessions a day weighs a quarter (`RESEARCH_PER_DAY`), eating past 4 meals a day a fifth (`MEALS_PER_DAY`), one chess game a day, and the desk is off from 00:00 to 06:00.

## Changes in this pass

- Null entries 15 to 17: the two konbini buy steps (P12) are null, because life.py scores `buy_konbini` only while the bakery is closed (G1).
- Bread and delivery (G10): the two ramen options are 10% each (was 25%), with the other options renormalised to 1.00 per meal. The new `errand_bread_dinner` (17:30-18:15) keeps bread for dinner and the evening. Without it, the bread ran out after the afternoon meal, and the late meal became a delivery of about 29 simulated minutes above `EAT_AT` (seed 5 of `test_life_day`, which then read 69 min against a limit of 60; now 40 min).
- Entries 45 to 46 (life-mapped 28 to 29, nulls 17).
- Sleep: onset 00:30 (was 23:30), wake target 08:00 (was 07:00), wake window 07:30 to 09:00. Friday and Saturday nights moved to `day_types.weekend`.
- Morning: breakfast 09:00 to 10:00 after the 08:00 wake (was 07:00 to 10:00), phone from 08:00, hygiene 08:00 to 09:30, bakery errand 10:00 to 11:00 (was 09:30 to 11:00).
- Afternoon and evening: research 09:30 to 16:30 (was to 23:00); park 16:30 to 17:30 (was 09:00 to 19:30); console 18:30 to 22:30 at 0.25 (was 09:30 to 23:00 at 0.15); music 22:00 to 01:00 (was 18:00 to 24:00).
- Meals: lunch courier 12:00 to 12:20 (was 11:45 to 12:15); dinner stock from 18:30 (was 18:00), ramen order 18:15 to 19:00, ramen eat 19:00 to 20:15, home eat from 19:00 (was 18:45), konbini buy 20:00 to 20:30 (was 20:45).
- `daily_plan.py`: activities add up (was the single highest entry), sleep spans, shared part only, failed reads cached too, and `clear_cache()`.

## Tests

    BROWSE=0 /tmp/claude-0/-home-user/2e1bb17a-3c9c-5a3e-a624-f8c5a84eac68/scratchpad/venv/bin/python -m pytest -q -p no:cacheprovider tests/test_daily_plan.py

`tests/test_daily_plan.py` has 38 tests: windows, midnight, sleep spans, weights and ties, null entries, the activities filter, bad files and entries, bad hours and activities, the cache, 10k calls under a second, every half hour in `life.ACTIVITIES`, the sequence minute by minute, life's hour rules, and the entry counts.

The life simulations that read this template pass with it: `tests/test_life_day.py -k twelve_days` (research share, meals and above-threshold time per day) and `tests/test_needs_first.py`.
