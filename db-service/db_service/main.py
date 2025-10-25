
from sqlalchemy import create_engine

url = "postgresql+psycopg://user:password@localhost:5432/mydb"
print("TRY:", repr(url))
engine = create_engine(url)
print("✅ OK, parsed successfully")
