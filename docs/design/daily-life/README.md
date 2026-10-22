# daily-life: draft day template

Draft of SUB-01's typical week: a 20-year-old student who lives alone in a small Kichijoji apartment, Tokyo. Design data only.

- Status: life.py does NOT read day_template.json yet; loading it is a later change, and nothing here runs.
- Time: simulated Tokyo clock (HH:MM) at 24x, so one real hour is one simulated day. 24:00 or later is after midnight of the same day.
- Names: activity, place and route names are copied from life.py (ACTIVITIES, PLACES) and web/tokyo_routes.json. Needs are life.py's (hunger, boredom, energy) or proposed in notes (P10).
- "activity": null marks an entry life.py cannot run yet; its "proposal" id (P1 to P9) points to notes. No new activity name is used in the file.
- earliest_start / latest_start: the window in which the entry may start.
- duration_min: [min, max] simulated minutes, drawn uniformly as life.py does; [0, 0] for sleep means the sleep engine ends it.
- weight: a probability. Entries with the same "group" are alternatives whose weights sum to 1; without a group it is the chance the entry happens on an eligible day.
- steps: the ordered chain of one meal option; each step has weight 1.0 once its option is picked.
- away: true means outside the apartment (class, library, job). Nothing at home starts during it; travel is not modelled.
- shared.leisure: drawn again and again to fill free time; an entry takes part only inside its window.
- day_types and weekly_rules: 3 class days, 2 non-class weekdays (library or job), and Saturday and Sunday (job shifts, weekly laundry and cleaning on Sunday). Shared entries apply to every day.
- sleep: nights from Friday and Saturday use the weekend window, up to 90 minutes later for bedtime and wake.
- gate (G1 to G9) and notes: where life.py blocks an option today, for example konbini while the bakery is open.
- Not yet parsed or checked by any tool; check the JSON before the later change.
