"""
datetime_info.py — built-in Skill

Returns the current date, time, weekday and timezone information.
The agent should call this tool whenever it needs to know the current
date/time, or when the user asks time-related questions.
"""

from datetime import datetime, timezone, timedelta

from skills.base import Skill

_WEEKDAYS_CN = ["Monday/星期一", "Tuesday/星期二", "Wednesday/星期三",
                "Thursday/星期四", "Friday/星期五", "Saturday/星期六", "Sunday/星期日"]


class DateTimeInfoSkill(Skill):
    name = "datetime_info"
    description = (
        "Get the current date, time, day of week, and timezone. "
        "Call this tool whenever you need to know the current date or time, "
        "for example when the user asks 'what day is it', 'what time is it', "
        "'today's date', or when you need the current date to search for recent news."
    )
    parameters = {
        "type": "object",
        "properties": {
            "timezone_offset": {
                "type": "integer",
                "description": (
                    "UTC offset in hours. Default is 8 (Asia/Shanghai, CST). "
                    "Use 0 for UTC, -5 for US Eastern, 9 for Japan, etc."
                ),
                "default": 8,
            },
        },
        "required": [],
    }

    def execute(self, timezone_offset: int = 8) -> str:
        tz = timezone(timedelta(hours=timezone_offset))
        now = datetime.now(tz)
        weekday = _WEEKDAYS_CN[now.weekday()]

        tz_name = f"UTC{'+' if timezone_offset >= 0 else ''}{timezone_offset}"

        return (
            f"Current date: {now.strftime('%Y-%m-%d')}\n"
            f"Current time: {now.strftime('%H:%M:%S')}\n"
            f"Day of week: {weekday}\n"
            f"Timezone: {tz_name}\n"
            f"ISO format: {now.isoformat()}"
        )
