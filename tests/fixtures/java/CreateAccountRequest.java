package com.example.demo.model;

import jakarta.validation.constraints.*;
import com.fasterxml.jackson.annotation.JsonProperty;

public class CreateAccountRequest {

    @NotBlank
    @Size(min = 1, max = 100)
    private String name;

    @NotNull
    @Email
    private String email;

    private Address address;

    private AccountStatus status;

    @JsonProperty("credit_limit")
    @Min(0)
    private Double creditLimit;

    public String getName() { return name; }
    public String getEmail() { return email; }
    public Address getAddress() { return address; }
    public AccountStatus getStatus() { return status; }
    public Double getCreditLimit() { return creditLimit; }
}
