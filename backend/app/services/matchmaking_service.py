import uuid

queue = {}  # user_id -> sid


def add_to_queue(user_id, sid):
    queue[user_id] = sid


def remove_from_queue(user_id):
    queue.pop(user_id, None)


def is_queued(user_id):
    return user_id in queue


def try_match():
    if len(queue) < 2:
        return None

    user_ids = list(queue.keys())[:2]
    user1_id, user2_id = user_ids
    sid1, sid2 = queue[user1_id], queue[user2_id]

    del queue[user1_id]
    del queue[user2_id]

    duel_id = str(uuid.uuid4())
    return {
        "duel_id": duel_id,
        "player1": {"user_id": user1_id, "sid": sid1},
        "player2": {"user_id": user2_id, "sid": sid2},
    }
