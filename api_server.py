
"""
InstaBot Production API

This file will contain the FastAPI backend.
Existing Instagram automation scripts remain unchanged.
"""

from fastapi import FastAPI

app = FastAPI(
    title="InstaBot Automation API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "InstaBot Backend"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
