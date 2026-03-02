from fastapi import APIRouter, Path, Query
from typing import List
from .models import CreateAccountRequest, AccountResponse

router = APIRouter(prefix="/v1/accounts", tags=["Accounts"])


@router.get("/", response_model=List[AccountResponse])
def list_accounts(page: int = Query(0), size: int = Query(20)):
    pass


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: str = Path(...)):
    pass


@router.post("/", response_model=AccountResponse, status_code=201)
def create_account(request: CreateAccountRequest):
    pass


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(account_id: str, request: CreateAccountRequest):
    pass


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: str = Path(...)):
    pass
