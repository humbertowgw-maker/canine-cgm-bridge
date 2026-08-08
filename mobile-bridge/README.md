# mobile-bridge

FastAPI service standing in for what would eventually be a native Android ingestion
app (architecturally modeled on xDrip+). Receives telemetry frames over HTTP or
WebSocket, parses them, keeps a local live-estimate calibration cache, and forwards
readings/profiles/calibration submissions to cloud-backend. Must always be launched
with this directory as the working directory (`uvicorn app.main:app`) — `mobile-bridge`
is not a valid Python package name because of the hyphen.

Run: `CLOUD_BACKEND_URL=http://localhost:8000 uvicorn app.main:app --reload --port 9000`
