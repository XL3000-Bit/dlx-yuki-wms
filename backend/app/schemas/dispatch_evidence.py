from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.operational_document import DocumentType
from app.models.user import UserRole


class DocumentRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: DocumentType
    scope: Literal["ORDER", "LOAD"]
    allow_generated: bool
    # Explicit even when generated BOL is not allowed. No permissive default.
    bol_statuses: list[int]

    @model_validator(mode="after")
    def valid_generated_rules(self):
        from app.models.bol import BOLStatus
        known = {BOLStatus.DRAFT, BOLStatus.GENERATED, BOLStatus.PRINTED, BOLStatus.COMPLETED, BOLStatus.CANCELED}
        if len(self.bol_statuses) != len(set(self.bol_statuses)) or not set(self.bol_statuses) <= known:
            raise ValueError("BOL statuses must be unique known status codes")
        if self.allow_generated and (self.document_type != DocumentType.BOL or self.scope != 'ORDER' or not self.bol_statuses):
            raise ValueError("Generated evidence requires ORDER BOL and explicit accepted statuses")
        if not self.allow_generated and self.bol_statuses:
            raise ValueError("BOL statuses must be empty when generated evidence is disabled")
        return self


class ReviewRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[UserRole] = Field(min_length=1)
    valid_seconds: int = Field(gt=0, le=31536000)

    @model_validator(mode="after")
    def unique_roles(self):
        if len(self.roles) != len(set(self.roles)):
            raise ValueError("Review roles must be unique")
        return self


class EvidenceRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[DocumentRequirement] = Field(min_length=1)
    document_review: ReviewRule
    approval: ReviewRule
    exception_review: ReviewRule
    independent_approver: bool
    # Explicit handling of canceled exceptions; never infer cancellation acceptance.
    allow_canceled_exceptions: bool

    @model_validator(mode="after")
    def unique_requirements(self):
        keys = [(x.document_type, x.scope) for x in self.documents]
        if len(keys) != len(set(keys)):
            raise ValueError("Document type and scope requirements must be unique")
        return self


class EvidenceReviewWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["DOCUMENTS", "APPROVAL", "EXCEPTIONS"]
    decision: Literal["ACCEPT", "REJECT"]
    plan_id: int = Field(gt=0)
    content_revision: int = Field(ge=0)
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation_id: str = Field(min_length=1, max_length=64)
    note: str = Field(min_length=1, max_length=4000)
