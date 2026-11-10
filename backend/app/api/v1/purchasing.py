from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import Session, Staff
from app.models.purchasing import PurchaseOrder, PurchaseStatus, Supplier
from app.schemas.purchasing import (
    PurchaseOrderIn,
    PurchaseOrderOut,
    ReceiptIn,
    SupplierIn,
    SupplierOut,
)
from app.services import purchasing as purchasing_service

router = APIRouter(tags=["purchasing"])


@router.get("/suppliers", response_model=list[SupplierOut])
async def list_suppliers(session: Session, _: Staff) -> list[Supplier]:
    return list((await session.execute(select(Supplier).order_by(Supplier.name))).scalars())


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
async def create_supplier(session: Session, _: Staff, body: SupplierIn) -> Supplier:
    return await purchasing_service.save_supplier(session, body)


@router.put("/suppliers/{supplier_id}", response_model=SupplierOut)
async def update_supplier(
    session: Session, _: Staff, supplier_id: int, body: SupplierIn
) -> Supplier:
    return await purchasing_service.save_supplier(session, body, supplier_id)


@router.get("/purchase-orders", response_model=list[PurchaseOrderOut])
async def list_orders(
    session: Session,
    _: Staff,
    status: PurchaseStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[PurchaseOrder]:
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.id.desc()).limit(limit).offset(offset)
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)
    return list((await session.execute(stmt)).unique().scalars())


@router.get("/purchase-orders/{order_id}", response_model=PurchaseOrderOut)
async def get_order(session: Session, _: Staff, order_id: int) -> PurchaseOrder:
    return await purchasing_service.get_order(session, order_id)


@router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=201)
async def create_order(session: Session, user: Staff, body: PurchaseOrderIn) -> PurchaseOrder:
    return await purchasing_service.create_order(session, user, body)


@router.put("/purchase-orders/{order_id}", response_model=PurchaseOrderOut)
async def update_order(
    session: Session, _: Staff, order_id: int, body: PurchaseOrderIn
) -> PurchaseOrder:
    return await purchasing_service.update_order(session, order_id, body)


@router.post("/purchase-orders/{order_id}/cancel", response_model=PurchaseOrderOut)
async def cancel_order(session: Session, _: Staff, order_id: int) -> PurchaseOrder:
    return await purchasing_service.cancel_order(session, order_id)


@router.post("/purchase-orders/{order_id}/receive", response_model=PurchaseOrderOut)
async def receive_order(
    session: Session, user: Staff, order_id: int, body: ReceiptIn
) -> PurchaseOrder:
    return await purchasing_service.receive_order(session, user, order_id, body)
