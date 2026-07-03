import datetime

def get_prior_date(date: datetime.date) -> datetime.date:
    return date - datetime.timedelta(days=1)

def date_to_str(date: datetime.date) -> str:
    return date.strftime("%Y-%m-%d")

def str_to_date(date_str: str) -> datetime.date:
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()