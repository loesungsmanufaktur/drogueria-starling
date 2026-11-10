from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import AnyUser, Session, Staff
from app.core.errors import AppError, NotFound
from app.models import Customer, Prescription
from app.schemas.customers import (
    CustomerIn,
    CustomerOut,
    CustomerSearch,
    CustomerUpdate,
    PrescriptionMeta,
    PrescriptionOut,
)
from app.services import customers as customers_service

router = APIRouter(tags=["customers"])


# Customers are needed at the POS, so every role can read and create them.
@router.post("/customers/search", response_model=list[CustomerOut])
async def search_customers(session: Session, _: AnyUser, body: CustomerSearch) -> list[Customer]:
    return await customers_service.search_customers(session, body.q)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
async def get_customer(session: Session, _: AnyUser, customer_id: int) -> Customer:
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise NotFound("CUSTOMER_NOT_FOUND", "Customer not found")
    return customer


@router.post("/customers", response_model=CustomerOut, status_code=201)
async def create_customer(session: Session, _: AnyUser, body: CustomerIn) -> Customer:
    return await customers_service.save_customer(session, body)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
async def update_customer(
    session: Session, _: AnyUser, customer_id: int, body: CustomerUpdate
) -> Customer:
    return await customers_service.save_customer(session, body, customer_id)


@router.post("/prescriptions", response_model=PrescriptionOut, status_code=201)
async def create_prescription(
    session: Session,
    user: AnyUser,
    meta: Annotated[str, Form(description="PrescriptionMeta as JSON")],
    file: Annotated[UploadFile, File(description="JPG, JPEG, PNG or PDF")],
) -> Prescription:
    try:
        data = PrescriptionMeta.model_validate_json(meta)
    except ValidationError as exc:
        raise AppError("VALIDATION_ERROR", str(exc), 422) from exc
    content = await file.read()
    return await customers_service.create_prescription(
        session, user, data, file.filename or "", content
    )


@router.get("/customers/{customer_id}/prescriptions", response_model=list[PrescriptionOut])
async def customer_prescriptions(
    session: Session, _: AnyUser, customer_id: int
) -> list[Prescription]:
    stmt = (
        select(Prescription)
        .where(Prescription.customer_id == customer_id)
        .order_by(Prescription.issued_on.desc(), Prescription.id.desc())
    )
    return list((await session.execute(stmt)).unique().scalars())


@router.get("/prescriptions/{prescription_id}", response_model=PrescriptionOut)
async def get_prescription(session: Session, _: AnyUser, prescription_id: int) -> Prescription:
    return await customers_service.get_prescription(session, prescription_id)


# SEC-3: the scanned document itself is only for pharmacists and admins.
@router.get("/prescriptions/{prescription_id}/file", response_class=FileResponse)
async def prescription_file(session: Session, _: Staff, prescription_id: int) -> FileResponse:
    prescription = await customers_service.get_prescription(session, prescription_id)
    return FileResponse(
        customers_service.prescription_file(prescription),
        media_type=prescription.file_content_type,
        filename=prescription.file_name,
        headers={"Cache-Control": "no-store"},
    )
