"""Pydantic schemas for REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BusinessOut(BaseModel):
    id: str
    name: str
    twilio_whatsapp_from: str
    admin_whatsapp_number: str
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BusinessCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str
    twilio_whatsapp_from: str
    admin_whatsapp_number: str = ""
    pin: str | None = None
    is_default: bool = False


class MenuItemOut(BaseModel):
    id: int
    business_id: str
    external_id: str
    nombre: str
    precio: float
    categoria: str
    disponible: bool

    model_config = {"from_attributes": True}


class MenuItemCreate(BaseModel):
    nombre: str
    precio: float
    categoria: str = ""
    external_id: str = ""
    disponible: bool = True


class MenuItemUpdate(BaseModel):
    nombre: str | None = None
    precio: float | None = None
    categoria: str | None = None
    external_id: str | None = None
    disponible: bool | None = None


class MenuReplace(BaseModel):
    items: list[dict[str, Any]]


class OrderOut(BaseModel):
    id: int
    business_id: str
    order_id: str
    wa_id: str
    items: list[dict[str, Any]]
    total: float
    status: str
    customer_name: str
    address: str
    delivery_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    order_id: str
    wa_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: float = 0
    status: str = "pending"
    customer_name: str = ""
    address: str = ""
    delivery_type: str = ""


# --------------------------------------------------------------------------- #
# Customers                                                                    #
# --------------------------------------------------------------------------- #

class CustomerOut(BaseModel):
    id: int
    business_id: str
    wa_id: str
    name: str | None
    phone: str | None
    notes: str | None
    blocked: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerCreate(BaseModel):
    wa_id: str = Field(..., min_length=5, max_length=32)
    name: str | None = None
    phone: str | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    notes: str | None = None
    blocked: bool | None = None


# --------------------------------------------------------------------------- #
# WhatsBot app (chats + realtime)                                              #
# --------------------------------------------------------------------------- #

class ConversationOut(BaseModel):
    id: int
    business_id: str
    customer_wa_id: str
    customer_name: str | None
    last_message_preview: str | None
    last_message_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    direction: str
    body: str
    wa_id: str
    is_admin: bool
    channel: str
    status: str = "delivered"
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime
    client_id: str | None = None
    twilio_sid: str | None = None

    model_config = {"from_attributes": True}


class OwnerMessageCreate(BaseModel):
    customer_wa_id: str = Field(..., min_length=8)
    body: str = Field(..., min_length=1)
    client_id: str | None = Field(default=None, max_length=64)


class DeviceTokenRegister(BaseModel):
    token: str = Field(..., min_length=10, max_length=512)
    platform: str = Field(default="android", pattern=r"^(android|ios)$")


class OrderActionResponse(BaseModel):
    ok: bool
    message: str


class BusinessMeOut(BaseModel):
    id: str
    name: str
    twilio_whatsapp_from: str
    admin_whatsapp_number: str

    model_config = {"from_attributes": True}


class IntentsConfigOut(BaseModel):
    config: dict[str, Any]


class IntentsConfigUpdate(BaseModel):
    config: dict[str, Any]


class PromptsConfigOut(BaseModel):
    config: dict[str, str]


class PromptsConfigUpdate(BaseModel):
    config: dict[str, str]


class MenuAppOut(BaseModel):
    items: list[MenuItemOut]


class MenuAppUpdate(BaseModel):
    items: list[dict[str, Any]]
