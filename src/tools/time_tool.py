from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8), "Asia/Shanghai")


async def get_current_time() -> str:
    now = datetime.now(CST)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")
