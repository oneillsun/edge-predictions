from fastapi import FastAPI

app = FastAPI(title="Edge Predictions")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
