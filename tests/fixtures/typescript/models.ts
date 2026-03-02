export interface Address {
    street: string;
    city: string;
    zipCode: string;
}

export interface CreateAccountRequest {
    name: string;
    email: string;
    address?: Address;
    creditLimit?: number;
}

export interface AccountResponse {
    id: string;
    name: string;
    email: string;
    active: boolean;
    createdAt: Date;
}

export type AccountStatus = 'ACTIVE' | 'INACTIVE' | 'SUSPENDED';
