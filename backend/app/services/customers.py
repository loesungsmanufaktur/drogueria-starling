import uuid
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.models import Customer, Prescription, PrescriptionItem, Product, User
from app.models.customers import CONSUMIDOR_FINAL
from app.schemas.customers import CustomerIn, CustomerUpdate, PrescriptionMeta, normalize_tax_id

# CAT-2: prescriptions are attached as JPG/JPEG, PNG or PDF, checked by
# extension *and* file signature so a renamed file is not accepted.
ALLOWED_FILES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "pdf": ("application/pdf", (b"%PDF-",)),
}


async def save_customer(
    session: AsyncSession, data: CustomerIn | CustomerUpdate, customer_id: int | None = None
) -> Customer:
    customer = Customer() if customer_id is None else await session.get(Customer, customer_id)
    if customer is None:
        raise NotFound("CUSTOMER_NOT_FOUND", "Customer not found")
    changes = data.model_dump(exclude_unset=customer_id is not None)
    if "document_id" in changes and changes["document_id"] is None:
        changes["document_id"] = CONSUMIDOR_FINAL  # SAL-13: no NIT/CUI means CF
    for key, value in changes.items():
        setattr(customer, key, value)
    session.add(customer)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict("DOCUMENT_TAKEN", "Another customer has this document number") from exc
    return customer


async def lookup_customer(session: AsyncSession, document_id: str) -> Customer:
    """Exact NIT/CUI match. CF is shared by many customers, so it never matches one."""
    if document_id == CONSUMIDOR_FINAL:
        raise AppError("CF_NOT_LOOKUP", "CF is not a customer number; sell as consumidor final")
    customer = (
        await session.execute(select(Customer).where(Customer.document_id == document_id))
    ).scalar_one_or_none()
    if customer is None:
        raise NotFound("CUSTOMER_NOT_FOUND", "No customer with this NIT/CUI")
    return customer


async def search_customers(session: AsyncSession, q: str, limit: int = 20) -> list[Customer]:
    term = q.strip().lower()
    try:
        tax_id: str | None = normalize_tax_id(q)
    except ValueError:
        tax_id = None
    stmt = (
        select(Customer)
        .where(
            or_(
                func.lower(Customer.full_name).contains(term),
                Customer.document_id == tax_id,
                Customer.phone == q.strip(),
            )
        )
        .order_by(Customer.full_name)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


def validate_upload(filename: str, head: bytes, size: int) -> tuple[str, str]:
    """Return (extension, content type) or raise if the file is not acceptable."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_FILES:
        raise AppError("INVALID_FILE_TYPE", "Prescription must be a JPG, JPEG, PNG or PDF file")
    content_type, signatures = ALLOWED_FILES[ext]
    if not any(head.startswith(sig) for sig in signatures):
        raise AppError("INVALID_FILE_TYPE", "File content does not match its extension")
    if size > get_settings().max_upload_mb * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", f"Maximum size is {get_settings().max_upload_mb} MB")
    if size == 0:
        raise AppError("FILE_EMPTY", "File is empty")
    return ext, content_type


def prescriptions_dir() -> Path:
    path = get_settings().upload_dir / "prescriptions"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def create_prescription(
    session: AsyncSession, user: User, meta: PrescriptionMeta, filename: str, content: bytes
) -> Prescription:
    ext, content_type = validate_upload(filename, content[:16], len(content))
    if await session.get(Customer, meta.customer_id) is None:
        raise NotFound("CUSTOMER_NOT_FOUND", "Customer not found")
    ids = [i.product_id for i in meta.items]
    if len(set(ids)) != len(ids):
        raise AppError("DUPLICATE_PRODUCT", "Each product can appear once per prescription")
    found = set((await session.execute(select(Product.id).where(Product.id.in_(ids)))).scalars())
    if missing := set(ids) - found:
        raise NotFound("PRODUCT_NOT_FOUND", f"Unknown products: {sorted(missing)}")

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    path = prescriptions_dir() / stored_name
    path.write_bytes(content)
    prescription = Prescription(
        customer_id=meta.customer_id,
        prescriber_name=meta.prescriber_name,
        prescriber_license=meta.prescriber_license,
        issued_on=meta.issued_on,
        notes=meta.notes,
        file_name=Path(filename).name[:200],
        file_path=f"prescriptions/{stored_name}",
        file_content_type=content_type,
        created_by=user.id,
        items=[
            PrescriptionItem(product_id=i.product_id, max_quantity=i.max_quantity)
            for i in meta.items
        ],
    )
    session.add(prescription)
    try:
        await session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return await get_prescription(session, prescription.id)


async def get_prescription(session: AsyncSession, prescription_id: int) -> Prescription:
    prescription = (
        (await session.execute(select(Prescription).where(Prescription.id == prescription_id)))
        .unique()
        .scalar_one_or_none()
    )
    if prescription is None:
        raise NotFound("PRESCRIPTION_NOT_FOUND", "Prescription not found")
    return prescription


def prescription_file(prescription: Prescription) -> Path:
    path = get_settings().upload_dir / prescription.file_path
    if not path.is_file():
        raise NotFound("FILE_NOT_FOUND", "Prescription file is missing")
    return path
