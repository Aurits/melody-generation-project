# models.py
import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# Ensure your app directory is in the path so that models can be imported
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mydb")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Job(Base):
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="pending")
    input_file = Column(Text)
    output_file = Column(Text)
    parameters = Column(Text)  # Parameters field for storing job configuration
    gcp_url = Column(Text)  # GCP URL field for storing public access URLs
    gcp_urls_json = Column(Text)  # New column for storing all GCP URLs as JSON
    variant_mixes_json = Column(Text)  # New column for storing variant mixes JSON
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

def init_db():
    # Note: Alembic will handle migrations, but you can create tables on first run if needed.
    Base.metadata.create_all(bind=engine)