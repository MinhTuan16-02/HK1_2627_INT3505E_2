USERS = {
    1: {
        "id": 1,
        "first_name": "Văn",
        "last_name": "Nguyễn",
        "email": "van.nguyen@example.com",
    },
    2: {
        "id": 2,
        "first_name": "Trang",
        "last_name": "Trần",
        "email": "trang.tran@example.com",
    },
}


def get_user(uid):
    return USERS.get(uid)
