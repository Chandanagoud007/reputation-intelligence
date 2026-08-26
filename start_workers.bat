@echo off
cd C:\Users\chand\OneDrive\Desktop\rip\backend

start "Normalize" cmd /k ".venv\Scripts\activate && python -m app.services.workers.normalize_worker"
start "Archive" cmd /k ".venv\Scripts\activate && python -m app.services.workers.raw_archive_writer"
start "Dedup" cmd /k ".venv\Scripts\activate && python -m app.services.workers.dedup_worker"
start "Entity" cmd /k ".venv\Scripts\activate && python -m app.services.workers.entity_resolve_worker"
start "Sentiment" cmd /k ".venv\Scripts\activate && python -m app.services.workers.sentiment_worker"
start "Topic" cmd /k ".venv\Scripts\activate && python -m app.services.workers.topic_worker"
start "Risk" cmd /k ".venv\Scripts\activate && python -m app.services.workers.risk_worker"
start "Merge" cmd /k ".venv\Scripts\activate && python -m app.services.workers.merge_worker"
start "Scoring" cmd /k ".venv\Scripts\activate && python -m app.services.workers.scoring_engine"
start "Alert" cmd /k ".venv\Scripts\activate && python -m app.services.workers.alert_engine"
start "Search" cmd /k ".venv\Scripts\activate && python -m app.services.workers.search_indexer"
start "Vector" cmd /k ".venv\Scripts\activate && python -m app.services.workers.vector_indexer"
start "Analytics" cmd /k ".venv\Scripts\activate && python -m app.services.workers.analytics_writer"
start "DigiComm" cmd /k ".venv\Scripts\activate && python -m app.services.workers.digicomm_dispatcher"