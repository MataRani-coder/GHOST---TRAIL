from fastapi import FastAPI

app = FastAPI(title="Ghost Trail API")


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Ghost Trail API"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }