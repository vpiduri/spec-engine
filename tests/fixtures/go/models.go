package models

import "time"

type Address struct {
	Street  string `json:"street" validate:"required"`
	City    string `json:"city" validate:"required"`
	ZipCode string `json:"zip_code"`
}

type CreateAccountRequest struct {
	Name        string   `json:"name" validate:"required,min=1,max=100"`
	Email       string   `json:"email" validate:"required,email"`
	Address     *Address `json:"address,omitempty"`
	CreditLimit float64  `json:"credit_limit" validate:"min=0"`
}

type AccountResponse struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Email     string    `json:"email"`
	Active    bool      `json:"active"`
	CreatedAt time.Time `json:"created_at"`
}

type AccountStatus string

const (
	AccountStatusActive    AccountStatus = "ACTIVE"
	AccountStatusInactive  AccountStatus = "INACTIVE"
	AccountStatusSuspended AccountStatus = "SUSPENDED"
)
