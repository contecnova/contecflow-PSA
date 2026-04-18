from app.db.session import SessionLocal
from sqlalchemy import text
s = SessionLocal()
print(s.execute(text('SELECT name FROM sqlite_master WHERE type=\'table\';')).fetchall())
