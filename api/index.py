from fastapi import FastAPI

app = FastAPI(title="Ghost Trail API")


@app.get("/api")
def root():
    return {
        "status": "online",
        "service": "Ghost Trail API"
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy"
    }