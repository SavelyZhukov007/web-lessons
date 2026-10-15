from datetime import date, timedelta 

def build_week(week_start: date, data: dict) -> list[dict]:
    if week_start.isoweekday() != 1:
        raise ValueError(f"Неверный день недели, должен быть Monday(Понедельник), а не {week_start.strftime('%A')}")
    
    res = []
     
    exc_by_id = {f"{item['session_id']}:{item['original_date']}": item for item in data["session_exceptions"]}

    active_clubs_by_id = {item["id"]: item for item in data["clubs"] if item["is_active"] == True}
    leaders_names_by_id = {item["id"]: item["name"] for item in data["leaders"]}
    categories_by_id = {item["id"]: item for item in data["categories"]}
    room_names_by_id = {item["id"]: item["name"] for item in data["rooms"]}
    session_by_id = {item["id"]: item for item in data["sessions"]}
    
    for cur_session in data["sessions"]:
        if cur_session["club_id"] not in active_clubs_by_id:
            continue

        session_date = week_start + timedelta(days=cur_session["weekday"] - 1)
        event_id = f"{cur_session["id"]}:{session_date}"

        cur_club = active_clubs_by_id[cur_session["club_id"]]
        cur_category = categories_by_id[cur_club["category_id"]]

        session_date_str = session_date.isoformat()
        
        scheduled_event = {
            "event_id": event_id,
            "session_id": cur_session["id"],
            "club_id": cur_session["club_id"],
            "club_name": cur_club["name"],
            "category_id": cur_category["id"],
            "category_name": cur_category["name"],
            "category_color": cur_category["color"],
            "leader_id": cur_club["leader_id"],
            "leader_name": leaders_names_by_id[cur_club["leader_id"]],
        }

        if event_id in exc_by_id:
            if exc_by_id[event_id]["type"] == "cancelled":
                scheduled_event.update({
                    "room_id": cur_session["room_id"],
                    "room_name": room_names_by_id[cur_session["room_id"]],
                    "date": session_date_str,
                    "start_time": cur_session["start_time"],
                    "end_time": cur_session["end_time"],
                    "status": "cancelled",
                    "original_date": session_date_str,
                    "comment": exc_by_id[event_id]["comment"]
                })
            else:
                # занятие перенесено
                cur_exception = exc_by_id[event_id]
                new_date = date.fromisoformat(cur_exception["new_date"])
                if week_start <= new_date <= week_start + timedelta(days=6):
                    # из этой недели в эту же
                    scheduled_event.update({
                        "room_id": cur_exception["new_room_id"],
                        "room_name": room_names_by_id[cur_exception["new_room_id"]],
                        "date": cur_exception["new_date"],
                        "start_time": cur_exception["new_start_time"],
                        "end_time": cur_exception["new_end_time"],
                        "status": "moved",
                        "original_date": session_date_str,
                        "comment": exc_by_id[event_id]["comment"]
                    })
                else: 
                    # из этой недели в другую - исключить из текущей недели
                    continue
        else:
            scheduled_event.update({
                "room_id": cur_session["room_id"],
                "room_name": room_names_by_id[cur_session["room_id"]],
                "date": session_date_str,
                "start_time": cur_session["start_time"],
                "end_time": cur_session["end_time"],
                "status": "scheduled",
                "original_date": session_date_str,
                "comment": ""
            })
        res.append(scheduled_event)

    # для обработки переноса из другой недели в текущую
    for exc in exc_by_id.values():
        if exc["type"] == "moved":
            new_date = date.fromisoformat(exc["new_date"])
            original_date = date.fromisoformat(exc["original_date"])
            if week_start <= new_date <= week_start + timedelta(days=6) and not (week_start <= original_date <= week_start + timedelta(days=6)):  
                if exc["session_id"] in session_by_id:
                    session = session_by_id[exc["session_id"]]
                    if session["club_id"] in active_clubs_by_id:
                        club = active_clubs_by_id[session["club_id"]]
                        category = categories_by_id[club["category_id"]]
                        res.append({
                            "event_id": f"{session['id']}:{exc['original_date']}",
                            "session_id": session["id"],
                            "club_id": session["club_id"],
                            "club_name": club["name"],
                            "category_id": category["id"],
                            "category_name": category["name"],
                            "category_color": category["color"],
                            "leader_id": club["leader_id"],
                            "leader_name": leaders_names_by_id[club["leader_id"]],
                            "room_id": exc["new_room_id"],
                            "room_name": room_names_by_id[exc["new_room_id"]],
                            "date": exc["new_date"],
                            "start_time": exc["new_start_time"],
                            "end_time": exc["new_end_time"],
                            "status": "moved",
                            "original_date": exc["original_date"],
                            "comment": exc["comment"]
                        })

    res.sort(key=lambda event: (event["date"], event["start_time"]))
    return res
