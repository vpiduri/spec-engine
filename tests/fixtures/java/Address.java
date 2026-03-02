package com.example.demo.model;

import jakarta.validation.constraints.NotBlank;

public class Address {

    @NotBlank
    private String street;

    @NotBlank
    private String city;

    private String zipCode;

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getZipCode() { return zipCode; }
}
