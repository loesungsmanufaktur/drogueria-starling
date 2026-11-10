from fastapi import APIRouter

from app.api.v1 import auth, catalog, customers, health, inventory, purchasing, sales, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(catalog.router)
api_router.include_router(inventory.router)
api_router.include_router(purchasing.router)
api_router.include_router(customers.router)
api_router.include_router(sales.router)
