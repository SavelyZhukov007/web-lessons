from backend.app.auth import hash_password
from backend.app.database import SessionLocal
from backend.app.models import Admin

PASSWORD = "Password123"


def make_admin(login="admin", password=PASSWORD):
    with SessionLocal() as db:
        db.add(Admin(login=login, password_hash=hash_password(password)))
        db.commit()


def login(client, login_name="admin", password=PASSWORD):
    return client.post("/api/admin/login", json={"login": login_name, "password": password})
