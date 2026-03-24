from app.utils.helpers import format_datetime


def format_result_row(row):
    return {
        "id": row[0],
        "section": row[1],
        "level": row[2],
        "mode": row[3],
        "score": row[4],
        "total": row[5],
        "percent": row[6],
        "created_at": format_datetime(row[7]),
    }


def format_best_row(row):
    if not row:
        return None
    return format_result_row(row)
