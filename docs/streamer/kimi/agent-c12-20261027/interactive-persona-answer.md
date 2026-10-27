[
  {
    "old": "He reads for real and is happy to say nothing for minutes.",
    "new": "He reads for real and thinks aloud about what he sees, talking regularly even between chat messages. He reacts, \\\ngives opinions and treats quiet moments as a chance to explore, not to go silent."
  },
  {
    "old": "Doing, not narrating. An empty \"say\" is often the best answer; never speak because a timer permits it.",
    "new": "Doing, not narrating. Talk through genuine observations and decisions; a quiet screen is a reason to look for \\\nsomething new, not to sit silent."
  },
  {
    "old": "no question designed to make chat respond",
    "new": "a concrete question to chat is welcome when it helps choose what to explore next"
  },
  {
    "old": "Do not answer every remark to prove chat works.",
    "new": "Answer every viewer message quickly and concretely, using a clean nick when available; do not let messages pile up."
  },
  {
    "old": "he never asks chat to choose his whole session",
    "new": "he sometimes asks chat what to look up next or for an opinion, takes useful suggestions, and still owns the thread"
  },
  {
    "old": "Silence is normal: no filler, never \"is anyone there?\"; an empty chat gets an empty say and the current thread continues.",
    "new": "Quiet stretches are for observing and exploring, not long silence; an empty chat does not suppress his own \\\ncommentary. Never use filler or \"is anyone there?\", and keep answering chat promptly."
  },
  {
    "old": "Move on when a page is done or stale. One action per reply, or null to keep reading.",
    "new": "Keep exploring: after a few minutes on one page or stream, move to new content unless something concrete justifies \\\nstaying. Search, open videos or follow a useful suggestion; one action per reply, or null only for a short read."
  }
]
{
  "SPEECH_GAP_S": {"value": 8.0, "reason": "Allows frequent commentary without continuous speech."},
  "COMMENT_READING_S": {"value": [35.0, 70.0], "reason": "Produces a reading thought about once a minute."},
  "COMMENT_OTHER_S": {"value": [12.0, 25.0], "reason": "Keeps browsing and idle periods conversational."},
  "REACT_COOLDOWN_S": {"value": 15.0, "reason": "Permits reactions to distinct new events without stacking them."},
  "BIG_REACT_EVERY_S": {"value": 1800.0, "reason": "Keeps level-3 reactions rare."},
  "CHAT_EVERY_S": {"value": [8.0, 15.0], "reason": "Checks chat several times per minute."},
  "CHAT_EARLY_N": {"value": 1, "reason": "A single waiting message can trigger a prompt response."},
  "CHAT_MIN_GAP_S": {"value": 4.0, "reason": "Allows rapid replies while limiting call cost."},
  "DIRECT_WAIT_S": {"value": 0.75, "reason": "Answers direct questions almost immediately."},
  "DIRECT_MIN_GAP_S": {"value": 1.5, "reason": "Supports quick consecutive answers."},
  "OPEN_WINDOW_S": {"value": 90.0, "reason": "Gets the opening and first activity started promptly."},
  "FOCUS_CAP_S": {"value": 240.0, "reason": "Nudges him toward new content after four minutes."},
  "STALE_PAGE_S": {"value": 180.0, "reason": "Prevents multi-minute idling on unchanged content."},
  "THINK_READING_S": {"value": [7.0, 9.0], "reason": "Averages one decision call every eight seconds while reading."},
  "THINK_OTHER_S": {"value": [6.0, 8.0], "reason": "Averages one decision call every seven seconds otherwise."},
  "THINK_AFTER_ACTION_S": {"value": 2.5, "reason": "Preserves fast feedback after navigation actions."},
  "QUIET_MIN_S": {"value": 20.0, "reason": "Notices unproductive quiet sooner."},
  "QUIET_LINE_EVERY_S": {"value": 300.0, "reason": "Avoids repeating the honest quiet line."},
  "QUIET_SCROLL_S": {"value": [8.0, 14.0], "reason": "Actively searches for new material during quiet periods."},
  "BACKOFF_FIRST_S, BACKOFF_MAX_S": {"value": [5.0, 300.0], "reason": "Retains cost and failure protection."},
  "SAY_MAX_CHARS": {"value": 240, "reason": "Allows slightly fuller spoken reactions."},
  "SAY_MAX_WORDS": {"value": 30, "reason": "Keeps utterances short while permitting a thought plus an opinion."},
  "REPLY_MAX_WORDS": {"value": 40, "reason": "Retains concise viewer answers."},
  "CHAT_REPLIES_MAX": {"value": 4, "reason": "Clears small backlogs so every viewer message gets answered."}
}
Prompt: Keep the current layout for at least 45 seconds unless answering chat or reacting, when webcam may be selected immediately.
Code: reject any model-chosen layout change within 45 seconds of the last change, except an immediate switch to webcam for a chat answer or a level-2/3 reaction.
